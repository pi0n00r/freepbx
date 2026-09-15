#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=Voice-Organ
"""Disposable filesystem transactions and dummy native services only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("executor_transaction", HERE / "deploy/executor-transaction.py")
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)


class FakeNative:
    def __init__(self, layout):
        self.layout = layout
        self.events = []
        self.calls = 0
        self.health_error = False
        self.post_failures = 0
        self.drift = False
        self.job = 0
        self.stop_timeout = False

    def controls(self):
        return {str(p): d.fingerprint(p) for p in self.layout.controls}
    def abi(self, path):
        self.events.append("abi")
        data = Path(path).read_bytes()
        d.require(data.startswith(b"ELF64 x86_64 GLIBC2.34"), "fixture_ABI_rejected")
    def zero(self):
        self.events.append("zero")
        d.require(type(self.calls) is int and self.calls == 0, "fixture_nonzero_calls")
    def check(self, expected):
        self.zero(); self.events.append("health")
        d.require(not self.health_error, "fixture_health_unavailable")
        d.require(d.digest(self.layout.live) == expected, "fixture_runtime_hash_wrong")
        return {"pid": 19, "restarts": "0", "sha256": expected}
    def idle(self): d.require(self.job == 0, "fixture_job_pending")
    def operation_state(self):
        self.events.append("operation_observation")
        return {"job": self.job, "pid": 19, "active": "active", "substate": "running"}
    def stop(self):
        self.events.append("stop")
        if self.stop_timeout:
            self.job=99
            raise d.IndeterminateOperation("fixture_systemd_stop_timeout")
    def start(self): self.events.append("start")
    def post(self, expected):
        self.events.append("post")
        if self.post_failures:
            self.post_failures -= 1; raise d.Stop("fixture_post_failed")
        self.health_error = False
        self.check(expected)
        if self.drift: self.layout.controls[0].write_bytes(b"concurrent config")


class Transactions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="executor-rollback-fixture-", dir=HERE.parent)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.layout = d.Layout()
        self.layout.live = root / "executor"
        self.layout.backup_base = root
        self.layout.controls = (root / "env", root / "unit")
        self.layout.live.write_bytes(b"ELF64 x86_64 GLIBC2.34 old")
        self.layout.live.chmod(0o751)
        for p in self.layout.controls: p.write_bytes(b"retained protected control")
        self.candidate = root / "candidate"
        self.candidate.write_bytes(b"ELF64 x86_64 GLIBC2.34 new"); self.candidate.chmod(0o755)
        self.old = d.fingerprint(self.layout.live)
        self.new = d.digest(self.candidate)
        self.n = FakeNative(self.layout)
        self.ledger = root / "ledger"; self.ledger.write_bytes(b"initial")

    def apply(self):
        return d.transaction("apply", self.n, self.layout, self.old["sha256"], self.candidate, self.new)
    def rollback(self, applied):
        return d.transaction("rollback", self.n, self.layout, d.digest(self.layout.live),
                             backup=applied["backup"], expected_manifest=applied["backup_manifest_sha256"])

    def assert_no_stop(self): self.assertNotIn("stop", self.n.events)

    def test_apply_rollback_repeat_preserve_new_state(self):
        controls = self.n.controls()
        applied = self.apply(); self.assertEqual(applied["status"], "apply_passed")
        self.ledger.write_bytes(b"newly accrued ledger")
        result = self.rollback(applied)
        self.assertEqual(result["status"], "rollback_passed")
        self.assertEqual(d.fingerprint(self.layout.live), self.old)
        self.assertEqual(self.rollback(applied)["status"], "already_restored")
        self.assertEqual(self.n.controls(), controls)
        self.assertEqual(self.ledger.read_bytes(), b"newly accrued ledger")
        phases=[json.loads(p.read_bytes())["phase"] for p in Path(applied["backup"]).glob("journal-*.json")]
        self.assertIn("prepared", phases); self.assertIn("restore_prepared", phases)
        self.assertIn("restored", phases)

    def test_new_capture_manifest_and_blob_private(self):
        applied = self.apply(); base=Path(applied["backup"])
        self.assertEqual(base.stat().st_mode & 0o777,0o700)
        for p in base.iterdir(): self.assertEqual(p.stat().st_mode & 0o777,0o600)
        m=json.loads((base/"snapshot.json").read_bytes())
        self.assertEqual(m["before"],self.old)
        self.assertFalse(m["config_restored"]);self.assertFalse(m["state_restored"])
        self.assertEqual((base/"executor.before").read_bytes(),b"ELF64 x86_64 GLIBC2.34 old")

    def test_wrong_current_prevents_stop(self):
        with self.assertRaises(d.Stop):
            d.transaction("apply",self.n,self.layout,"f"*64,self.candidate,self.new)
        self.assert_no_stop()

    def test_wrong_candidate_prevents_stop(self):
        with self.assertRaises(d.Stop):
            d.transaction("apply",self.n,self.layout,self.old["sha256"],self.candidate,"f"*64)
        self.assert_no_stop()

    def test_nonzero_and_bool_false_calls_block(self):
        for value in (1,False):
            with self.subTest(value=value):
                self.n.calls=value
                with self.assertRaises(d.Stop):self.apply()
        self.assert_no_stop()

    def test_candidate_ABI_failure_prevents_stop(self):
        self.candidate.write_bytes(b"ELF64 ARM GLIBC2.37")
        self.new=d.digest(self.candidate)
        with self.assertRaises(d.Stop):self.apply()
        self.assert_no_stop()

    def test_wrong_manifest_prevents_rollback_stop(self):
        applied=self.apply();self.n.events=[]
        applied["backup_manifest_sha256"]="f"*64
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.assert_no_stop()

    def test_tampered_backup_prevents_stop(self):
        applied=self.apply();self.n.events=[]
        (Path(applied["backup"])/"executor.before").write_bytes(b"tampered")
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.assert_no_stop()

    def test_legacy_backup_not_adopted(self):
        base=self.layout.backup_base/"avril-call-executor-pre-abi-legacy"
        base.mkdir(mode=0o700);(base/"executor.before").write_bytes(self.layout.live.read_bytes())
        with self.assertRaises((OSError,d.Stop)):
            d.transaction("rollback",self.n,self.layout,self.old["sha256"],backup=base,expected_manifest="a"*64)
        self.assert_no_stop()

    def test_backup_symlink_refused(self):
        applied=self.apply();self.n.events=[]
        base=Path(applied["backup"]);blob=base/"executor.before"
        blob.unlink();blob.symlink_to(self.candidate)
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.assert_no_stop()

    def test_concurrent_config_drift_refuses_rollback(self):
        applied=self.apply();self.n.events=[]
        self.layout.controls[0].write_bytes(b"new operator config")
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.assert_no_stop()

    def test_unrelated_native_generation_not_overwritten(self):
        applied=self.apply();self.n.events=[]
        self.layout.live.write_bytes(b"ELF64 x86_64 GLIBC2.34 foreign")
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.assert_no_stop()

    def test_post_start_failure_restores_with_separate_primary(self):
        self.n.post_failures=1
        result=self.apply()
        self.assertEqual(result["status"],"transaction_failed_no_retry")
        self.assertEqual(result["primary_error"],"fixture_post_failed")
        self.assertEqual(result["rollback_status"],"pretransaction_executor_restored")
        self.assertEqual(d.fingerprint(self.layout.live),self.old)

    def test_rollback_failure_separate_no_retry(self):
        self.n.post_failures=2
        result=self.apply()
        self.assertEqual(result["rollback_status"],"failed_or_refused_no_retry")
        self.assertEqual(result["rollback_error"],"fixture_post_failed")
        self.assertEqual(self.n.events.count("start"),2)

    def test_postrename_fsync_error_owned_prepared_image_recovers(self):
        real=d.os.fsync; failed=[False]
        def fsync(fd):
            if d.digest(self.layout.live)==self.new and not failed[0]:
                failed[0]=True;raise OSError("dummy postrename fsync failure")
            return real(fd)
        with mock.patch.object(d.os,"fsync",side_effect=fsync):result=self.apply()
        self.assertTrue(failed[0]);self.assertEqual(result["rollback_status"],"pretransaction_executor_restored")
        self.assertEqual(d.fingerprint(self.layout.live),self.old)
        self.assertEqual(self.rollback(result)["status"],"already_restored")

    def test_restore_postrename_fsync_error_repeat_restoration(self):
        applied=self.apply();real=d.os.fsync;failed=[False]
        def fsync(fd):
            if d.digest(self.layout.live)==self.old["sha256"] and not failed[0]:
                failed[0]=True;raise OSError("dummy restore fsync failure")
            return real(fd)
        with mock.patch.object(d.os,"fsync",side_effect=fsync):result=self.rollback(applied)
        self.assertEqual(result["rollback_status"],"pretransaction_executor_restored")
        self.assertEqual(d.digest(self.layout.live),self.new)
        self.assertEqual(self.rollback(applied)["status"],"rollback_passed")
        self.assertEqual(self.rollback(applied)["status"],"already_restored")

    def test_zero_exit_wrong_restored_bytes_never_pass(self):
        applied=self.apply(); real=d.atomic
        def wrong(path,data,identity,record=None):
            if path==self.layout.live:return real(path,b"wrong",identity,record)
            return real(path,data,identity,record)
        with mock.patch.object(d,"atomic",side_effect=wrong):result=self.rollback(applied)
        self.assertEqual(result["status"],"transaction_failed_no_retry")
        self.assertNotEqual(d.digest(self.layout.live),self.old["sha256"])

    def test_owned_crash_generation_explicit_rollback(self):
        applied=self.apply();self.n.health_error=True
        result=self.rollback(applied)
        self.assertEqual(result["status"],"rollback_passed")
        self.assertEqual(result["preflight_runtime"]["status"],"unavailable_owned_crash_generation")

    def test_unhealthy_unjournaled_generation_rejected(self):
        applied=self.apply()
        for p in Path(applied["backup"]).glob("journal-*.json"):p.unlink()
        self.n.health_error=True;self.n.events=[]
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.assert_no_stop()

    def test_read_only_check_no_stop(self):
        result=d.transaction("check",self.n,self.layout,self.old["sha256"],self.candidate,self.new)
        self.assertEqual(result["status"],"check_only_pass");self.assert_no_stop()

    def test_timeout_pending_systemd_job_no_recovery_mutation(self):
        self.n.stop_timeout=True;self.n.job=0
        result=self.apply()
        self.assertEqual(result["status"],"transaction_failed_no_retry")
        self.assertEqual(result["systemd_operation_observation"]["job"],99)
        self.assertEqual(result["rollback_error"],"systemd_job_pending_recovery_deferred")
        self.assertEqual(self.n.events.count("stop"),1)
        self.assertNotIn("start",self.n.events)
        self.assertEqual(d.fingerprint(self.layout.live),self.old)

    def test_same_content_new_inode_not_owned_by_snapshot(self):
        applied=self.apply();current=d.fingerprint(self.layout.live)
        duplicate=self.layout.live.with_name("new-inode")
        duplicate.write_bytes(self.layout.live.read_bytes());duplicate.chmod(current["mode"])
        os.replace(duplicate,self.layout.live);self.n.events=[]
        with self.assertRaisesRegex(d.Stop,"physical_executor_generation_not_snapshot_owned"):
            self.rollback(applied)
        self.assert_no_stop()

    def inject_foreign_change(self, kind):
        if kind == "config":
            self.layout.controls[0].write_bytes(b"operator changed control while stopped")
        elif kind == "job":
            self.n.job = 98
        else:
            duplicate = self.layout.live.with_name("foreign-executor")
            before = d.fingerprint(self.layout.live)
            duplicate.write_bytes(self.layout.live.read_bytes() if kind == "same" else
                                  b"ELF64 x86_64 GLIBC2.34 foreign stopped generation")
            duplicate.chmod(before["mode"])
            os.replace(duplicate, self.layout.live)

    def run_drift_case(self, mode, kind, boundary):
        self.setUp()
        applied = self.apply() if mode == "rollback" else None
        self.n.events = []
        if mode == "failure_restore": self.n.post_failures = 1
        trigger = 2 if mode == "failure_restore" else 1
        observed = []
        def inject():
            self.inject_foreign_change(kind)
            observed.append((d.physical(self.layout.live), self.n.controls()))
        if boundary:
            original = d.journal
            def during_preparation(base, manifest_sha, target, phase, path):
                original(base, manifest_sha, target, phase, path)
                if (phase in ("prepared", "restore_prepared") and
                        self.n.events.count("stop") == trigger and not observed):
                    inject()
            scope = mock.patch.object(d, "journal", side_effect=during_preparation)
        else:
            original = self.n.stop
            def during_stop():
                original()
                if self.n.events.count("stop") == trigger: inject()
            scope = mock.patch.object(self.n, "stop", side_effect=during_stop)
        with scope:
            result = self.rollback(applied) if mode == "rollback" else self.apply()
        self.assertEqual(len(observed), 1)
        self.assertEqual(result["status"], "transaction_failed_no_retry")
        self.assertEqual(result["rollback_status"], "failed_or_refused_no_retry")
        self.assertEqual(d.physical(self.layout.live), observed[0][0])
        self.assertEqual(self.n.controls(), observed[0][1])
        self.assertEqual(self.n.events.count("stop"), trigger)
        self.assertEqual(self.n.events.count("start"), 1 if mode == "failure_restore" else 0)
        self.assertIn("rollback_error", result)
        self.assertEqual((Path(result["backup"]) / "executor.before").read_bytes(),
                         b"ELF64 x86_64 GLIBC2.34 old")

    def test_stop_drift_apply_explicit_rollback_and_failure_restore(self):
        for mode in ("apply", "rollback", "failure_restore"):
            for kind in ("config", "different", "same"):
                with self.subTest(mode=mode, kind=kind):
                    self.run_drift_case(mode, kind, boundary=False)

    def test_prepared_boundary_rechecks_generation_controls_and_idle(self):
        for mode in ("apply", "rollback", "failure_restore"):
            for kind in ("config", "different", "same", "job"):
                with self.subTest(mode=mode, kind=kind):
                    self.run_drift_case(mode, kind, boundary=True)

    def test_timeout_HTTP_child_kill_reap_only_owned(self):
        native=d.Native(self.layout)
        child=mock.Mock(returncode=None)
        child.communicate.side_effect=[subprocess.TimeoutExpired("dummy",3),(b"",None)]
        with mock.patch.object(d.subprocess,"Popen",return_value=child) as popen:
            with self.assertRaisesRegex(d.Stop,"http_total_deadline_exceeded"):
                native.request(6022,"/healthz")
        child.kill.assert_called_once();self.assertEqual(child.communicate.call_count,2)
        self.assertNotIn("token",popen.call_args.args[0])


class RetainedGate(unittest.TestCase):
    def test_actual_native_systemctl_timeout_is_indeterminate(self):
        native=d.Native(d.Layout())
        with mock.patch.object(native,"operation_state",return_value={"job":0}), \
             mock.patch.object(native,"run",side_effect=subprocess.TimeoutExpired("systemctl",10)) as run:
            with self.assertRaisesRegex(d.IndeterminateOperation,"systemd_stop_observation_timeout"):
                native.stop()
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[0],["/usr/bin/systemctl","stop",d.UNIT])

    def test_real_retained_version_gate(self):
        gate=HERE/"deploy/verify-executor-abi.sh"
        self.assertEqual(d.digest(gate),d.ABI_GATE_SHA)
        for version,expected in (("2.34",0),("2.36",0),("2.37",1)):
            with self.subTest(version=version):
                result=subprocess.run(["bash",str(gate),"--check-version",version,"2.36"],capture_output=True)
                self.assertEqual(result.returncode,expected)

    def test_private_blob_ABI_probe_keeps_original_metadata(self):
        with tempfile.TemporaryDirectory(prefix="ABI-blob-fixture-",dir=HERE.parent) as tmp:
            layout=d.Layout();layout.backup_base=Path(tmp)
            layout.abi_gate=HERE/"deploy/verify-executor-abi.sh"
            blob=Path(tmp)/"blob";blob.write_bytes(b"dummy ELF");blob.chmod(0o600)
            before=d.physical(blob);native=d.Native(layout)
            def inspect(args):
                probe=Path(args[2]);self.assertEqual(probe.read_bytes(),blob.read_bytes())
                self.assertTrue(probe.stat().st_mode & 0o111);return b"fixture parser only"
            with mock.patch.object(native,"run",side_effect=inspect):native.abi(blob)
            self.assertEqual(d.physical(blob),before)
            self.assertEqual(list(Path(tmp).iterdir()),[blob])


if __name__=="__main__":unittest.main(verbosity=2)
