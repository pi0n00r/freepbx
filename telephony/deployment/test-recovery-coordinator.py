#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=VIP
"""Owned disposable fixtures only. No production SSH, HTTP, PBX or service commands."""
import argparse
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("vip_recovery", HERE / "recovery-coordinator.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
B = c.bindings()
AVA_PACKAGE = Path(os.environ.get("TELEPHONY_AVA_PACKAGE", HERE.parent.parent / "inputs/ava-current"))
RITA_PACKAGE = Path(os.environ.get("TELEPHONY_RITA_PACKAGE", HERE.parent.parent / "inputs/rita-current"))
TESSA_CURRENT = Path(os.environ.get("TELEPHONY_TESSA_KIT", HERE.parent.parent / "inputs/tessa-current"))


class FakeNative:
    def __init__(self, component, before, b):
        self.component, self.b = component, b
        self.current = dict(before)
        self.protected = {p: "a" * 64 for p in b["components"][component]["protected"]}
        self.protected["/etc/asterisk/extensions_custom.conf"] = b["custom_sha256"]
        self.protected["/etc/systemd/system/aimee-pbx-router.service"] = b["unit"]["sha256"]
        self.events = []
        self.rc, self.output = 0, b"ok"
        self.zero_error = False
        self.drift_on_second_snapshot = False
        self.snapshot_count = 0
        self.rollback_to = None
        self.snapshot = None
        self.blobs = {}
        self.ledger = b"accrued-ledger-never-restore"
        self.corrupt_stage_on_last_check = False
        self.stage_checks = 0

    def hashes(self, component, paths, b):
        self.events.append(("hashes", component, tuple(paths)))
        if component == "rita" and self.component != "rita" and set(paths) == set(b["components"]["rita"]["after"]):
            return dict(b["components"]["rita"]["after"])
        if set(paths) == set(b["components"][component]["protected"]):
            self.snapshot_count += 1
            rows = {p: self.protected[p] for p in paths}
            if self.drift_on_second_snapshot and self.snapshot_count > 1:
                rows[next(iter(rows))] = "b" * 64
            return rows
        if set(paths) == set(b["components"][component]["after"]):
            return dict(self.current)
        if self.blobs and set(paths) == set(self.blobs):
            return dict(self.blobs)
        if set(paths) == set(b["components"][component].get("foundation_files", {})):
            return dict(b["components"][component]["foundation_files"])
        self.stage_checks += 1
        rows = {}
        s = b["components"][component]
        for p in paths:
            execution = next((v for k, v in s.get("execution_files", {}).items() if p.endswith(k)), None)
            if execution is not None: rows[p] = execution
            elif s.get("installed_verifier") and p.endswith(s["installed_verifier"]): rows[p] = s["installed_verifier_sha"]
            elif p.endswith(s["helper"]): rows[p] = s["helper_sha"]
            elif p.endswith("scripts/rollback.sh"): rows[p] = s["rollback_helper_sha"]
            elif p.endswith("source/index.js"): rows[p] = next(iter(s["after"].values()))
            elif p.endswith("verify-executor-abi.sh"): rows[p] = "8e204f2c34940351567b52960867f35b95449996417f664e0a9ccf2b66eec4db"
            elif p.endswith("artifacts/avril-call-executor"): rows[p] = next(iter(s["after"].values()))
            else:
                suffix = p.split("/src/")[-1]
                rows[p] = next(v for k, v in s["after"].items() if k.endswith("/" + suffix))
        if self.corrupt_stage_on_last_check and self.stage_checks > 1:
            rows[next(iter(rows))] = "f" * 64
        return rows

    def unit(self): self.events.append(("unit",))
    def zero(self):
        self.events.append(("zero",))
        if self.zero_error: raise c.Stop("native_not_zero")
    def helper(self, component, args, b, mutation=False):
        self.events.append(("helper", component, tuple(args), mutation))
        if mutation:
            if self.rc == 0:
                self.current = dict(self.rollback_to if self.rollback_to is not None else b["components"][component]["after"])
            return self.rc, self.output
        return 0, b"check_ok"
    def document(self, component, backup, name, b):
        self.events.append(("snapshot", name))
        return json.dumps(self.snapshot).encode()


def stages():
    return {k: Path("/home/aimee/.local/share/vip-recovery-20260914/" + k) for k in B["components"]}


def rita_snapshot(n, backup):
    s = B["components"]["rita"]
    targets = list(s["after"])
    n.snapshot = {"binary_target": targets[0], "helper_target": targets[1],
                  "unit_target": "/etc/systemd/system/aimee-pbx-router.service",
                  "candidate_binary_sha256": s["after"][targets[0]],
                  "candidate_helper_sha256": s["after"][targets[1]], "unit_sha256": B["unit"]["sha256"],
                  "old_binary_sha256": "1" * 64, "old_helper_sha256": "2" * 64}
    n.blobs = {backup + "/binary": "1" * 64, backup + "/helper": "2" * 64, backup + "/unit": B["unit"]["sha256"]}
    return {targets[0]: "1" * 64, targets[1]: "2" * 64}


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.verify = mock.patch.object(c, "verify_package", return_value={"status": "verified_offline"})
        self.verify.start()
        self.addCleanup(self.verify.stop)
        self.before = {k: "0" * 64 for k in B["components"]["rita"]["after"]}
        self.n = FakeNative("rita", self.before, B)
        self.backup = None

    def run_action(self, mode="install", expected=None):
        return c.execute("rita", mode, {"rita": Path("/fixture")}, stages(), self.n, self.backup,
                         self.before if expected is None else expected, {"native_FreePBX_UI_checked": True}, B)

    def assert_no_mutation(self):
        self.assertFalse(any(e[0] == "helper" and e[-1] for e in self.n.events))

    def test_rita_install_exact_owner_flags_and_unit(self):
        result = self.run_action()
        self.assertEqual(result["status"], "delegated_install_passed")
        args = next(e[2] for e in self.n.events if e[0] == "helper" and e[-1])
        self.assertEqual(args[-1], "--apply")
        self.assertEqual(args[args.index("--expected-unit") + 1], B["unit"]["sha256"])
        self.assertEqual(args[args.index("--expected-environment") + 1], B["components"]["rita"]["environment_sha"])
        self.assertTrue(args[args.index("--kit") + 1].endswith("/rita"))

    def test_immediate_helper_hash_recheck(self):
        self.run_action()
        mutation = next(i for i,e in enumerate(self.n.events) if e[0] == "helper" and e[-1])
        self.assertEqual(self.n.events[mutation-1][0], "hashes")
        self.assertTrue(any(p.endswith(B["components"]["rita"]["helper"]) for p in self.n.events[mutation-1][2]))

    def test_changed_staged_helper_stops_before_mutation(self):
        self.n.corrupt_stage_on_last_check = True
        with self.assertRaises(c.Stop): self.run_action()
        self.assert_no_mutation()

    def test_expected_preimage_drift_stops(self):
        with self.assertRaises(c.Stop): self.run_action(expected={k:"f"*64 for k in self.before})
        self.assert_no_mutation()

    def test_config_drift_stops_before_mutation(self):
        self.n.drift_on_second_snapshot = True
        with self.assertRaises(c.Stop): self.run_action()
        self.assert_no_mutation()

    def test_template_unit_not_accepted(self):
        self.n.protected["/etc/systemd/system/aimee-pbx-router.service"] = "a0298a6368e3a9905b37119059b401bda104ce52fe7705165bb06336670fc98f"
        with self.assertRaises(c.Stop): self.run_action()
        self.assert_no_mutation()

    def test_nonzero_calls_prevents_actuation(self):
        self.n.zero_error = True
        with self.assertRaises(c.Stop): self.run_action()
        self.assert_no_mutation()

    def test_helper_failure_and_rollback_failure_independent(self):
        self.n.rc = 7
        self.n.output = b"primary_failure rollback=failed SECRET_MUST_NOT_APPEAR"
        result = self.run_action()
        self.assertEqual(result["helper_exit"], 7)
        self.assertTrue(result["owner_rollback_reported_failed"])
        self.assertNotIn("SECRET_MUST_NOT_APPEAR", json.dumps(result))
        self.assertEqual(self.n.ledger, b"accrued-ledger-never-restore")

    def test_rollback_matches_snapshot_not_previous_live_bytes(self):
        with self.assertRaisesRegex(c.Stop, "automatic_older_reader_rollback_forbidden"):
            c.owner_argv("rita", "rollback", stages(), self.before, None, B)
        self.assert_no_mutation()
        self.assertEqual(self.n.ledger, b"accrued-ledger-never-restore")

    def test_exit_zero_unchanged_rollback_is_rejected(self):
        with self.assertRaisesRegex(c.Stop, "automatic_older_reader_rollback_forbidden"):
            c.owner_argv("rita", "rollback", stages(), self.before, None, B)

    def test_exit_zero_wrong_rollback_is_rejected(self):
        with self.assertRaisesRegex(c.Stop, "automatic_older_reader_rollback_forbidden"):
            c.owner_argv("rita", "rollback", stages(), self.before, "/var/backups/aimee-pbx-router-producer-20260914/producer-fixture", B)

    def test_snapshot_malformed_refuses_before_mutation(self):
        wrong = dict(self.before); wrong.pop(next(iter(wrong)))
        with self.assertRaisesRegex(c.Stop, "paired_preimages_required"):
            c.owner_argv("rita", "install", stages(), wrong, None, B)
        self.assert_no_mutation()

    def test_snapshot_blob_tamper_refuses_before_mutation(self):
        wrong = dict(self.before); wrong[next(iter(wrong))] = "not-a-sha"
        with self.assertRaisesRegex(c.Stop, "paired_preimages_required"):
            c.owner_argv("rita", "install", stages(), wrong, None, B)
        self.assert_no_mutation()

    def test_existing_postimage_skips_old_preimage_helper(self):
        self.n.current = B["components"]["rita"]["after"]
        result = self.run_action(expected=self.n.current)
        self.assertEqual(result["status"], "already_matching_files_no_actuation")
        self.assertFalse(result["health_certification"])
        self.assert_no_mutation()

    def test_ava_fixed_preimage_and_unique_backup(self):
        s = B["components"]["ava"]
        n = FakeNative("ava", s["before"], B)
        path = "/home/aimee/.local/share/ava-rollback/runtime-fixture-unique"
        result = c.execute("ava", "install", {"ava":Path("/fixture")}, stages(), n, path, s["before"],
                           {"native_FreePBX_UI_checked": True}, B)
        self.assertEqual(result["status"], "delegated_install_passed")
        args = next(e[2] for e in n.events if e[0] == "helper" and e[1] == "ava" and e[-1])
        self.assertEqual(args[-3:], ("--apply", "--backup", path))
        self.assertNotIn("--backup-root", args)
        self.assertEqual(result["owner_backup_path"], path)

    def test_ava_current_postimage_never_reapplied(self):
        s = B["components"]["ava"];n = FakeNative("ava", s["after"], B)
        result = c.execute("ava", "install", {"ava":Path("/fixture")}, {}, n, None, s["after"],
                           {"native_FreePBX_UI_checked":True}, B)
        self.assertEqual(result["status"], "already_matching_files_no_actuation")
        self.assertFalse(any(e[0] == "helper" for e in n.events))

    def test_new_guard_native_identity_requires_binding_refresh(self):
        s = B["components"]["ava"]
        successor = dict(s["after"])
        successor["/opt/AVA-AI-Voice-Agent-for-Asterisk/src/core/pipeline_message_deposit.py"] = "f" * 64
        n = FakeNative("ava", successor, B)
        with self.assertRaisesRegex(c.Stop, "Ava_fixed_preimage_not_matching"):
            c.execute("ava", "install", {"ava": Path("/fixture")}, stages(), n,
                      "/home/aimee/.local/share/ava-rollback/runtime-obsolete-binding",
                      successor, {"native_FreePBX_UI_checked": True}, B)
        self.assertFalse(any(e[0] == "helper" for e in n.events))

    def test_unknown_component_is_visibly_unsupported(self):
        with self.assertRaisesRegex(c.Stop, "operator_host_local_staging"):
            c.execute("crustacea", "install", {}, {}, self.n, None, {}, {}, B)

    def test_voice_organ_rollback_never_claimed(self):
        n = FakeNative("voice-organ", B["components"]["voice-organ"]["after"], B)
        with self.assertRaisesRegex(c.Stop, "protected_manifest_pin_required"):
            c.execute("voice-organ", "rollback", {"voice-organ":Path("/fixture")}, stages(), n,
                      "/root/avril-call-executor-pre-abi-legacy", n.current, {"native_FreePBX_UI_checked":True}, B)
        self.assertFalse(any(e[0] == "helper" for e in n.events))

    def test_native_root_not_package_root(self):
        with self.assertRaisesRegex(c.Stop, "native_stage_scope"):
            c.staged_check(self.n, "rita", {"rita":RITA_PACKAGE}, B)

    def test_checkpoint_false_or_integer_not_authority(self):
        for value in (False, 1, None):
            with self.subTest(value=value), self.assertRaises(c.Stop):
                c.execute("rita", "install", {"rita":Path("/fixture")}, stages(), self.n, self.backup,
                          self.before, {"native_FreePBX_UI_checked":value}, B)
        self.assert_no_mutation()

    def test_plans_order_and_missing_components(self):
        p = c.plan("install", stages(), {"rita":self.before}, {"rita":self.backup}, B)
        self.assertEqual(p["order"][:3], ["tessa", "rita", "ava"])
        self.assertIn("INCOMPLETE", p["whole_assembly_status"])
        self.assertEqual(p["components"][-1]["retained_closure"], B["components"]["crustacea"]["closure"])
        self.assertIn("host-local staging", p["components"][-1]["foundation_gaps"][0])
        r = c.plan("rollback", stages(), {}, {}, B)
        self.assertLess(r["order"].index("ava"), r["order"].index("rita"))
        self.assertTrue(any(x.get("reason") == "automatic_older_reader_rollback_forbidden" for x in r["components"]))


class VoiceRollbackDelegation(unittest.TestCase):
    def fixture(self):
        s = B["components"]["voice-organ"]
        n = FakeNative("voice-organ", s["after"], B)
        n.snapshot = {"schema": "voice-organ-executor-transaction-v1", "target": next(iter(s["after"])),
            "unit": "avril-call-executor.service", "config_restored": False, "state_restored": False,
            "after": {"sha256": next(iter(s["after"].values()))}, "before": {"sha256": "1" * 64}}
        pin = hashlib.sha256(json.dumps(n.snapshot).encode()).hexdigest()
        backup = {"path": "/root/avril-call-executor-pre-abi-fixture", "manifest_sha256": pin}
        n.blobs = {backup["path"] + "/snapshot.json": pin, backup["path"] + "/executor.before": "1" * 64}
        n.rollback_to = {next(iter(s["after"])): "1" * 64}
        return n, backup

    def run_action(self, n, backup):
        with mock.patch.object(c, "verify_package", return_value={}):
            return c.execute("voice-organ", "rollback", {"voice-organ": Path("/fixture")}, stages(), n, backup,
                             B["components"]["voice-organ"]["after"], {"native_FreePBX_UI_checked": True}, B)

    def test_pinned_rollback_authoritative_restored_bytes_and_owner_argv(self):
        n, backup = self.fixture()
        self.assertEqual(self.run_action(n, backup)["status"], "delegated_rollback_passed")
        args = next(e[2] for e in n.events if e[0] == "helper" and e[-1])
        self.assertTrue(args[1].endswith("recovery/deploy/replace-vip-executor.sh"))
        self.assertEqual(args[args.index("--backup-manifest-sha256") + 1], backup["manifest_sha256"])
        self.assertEqual(n.ledger, b"accrued-ledger-never-restore")

    def test_zero_exit_wrong_or_unchanged_bytes_never_pass(self):
        for wrong in (B["components"]["voice-organ"]["after"], {"/usr/local/sbin/avril-call-executor": "f" * 64}):
            with self.subTest(wrong=wrong):
                n, backup = self.fixture(); n.rollback_to = wrong
                with self.assertRaisesRegex(c.Stop, "rollback_snapshot_postimage_mismatch"): self.run_action(n, backup)

    def test_wrong_manifest_and_backup_bytes_stop_before_mutation(self):
        for kind in ("manifest", "blob"):
            with self.subTest(kind=kind):
                n, backup = self.fixture()
                if kind == "manifest": backup["manifest_sha256"] = "f" * 64
                else: n.blobs[backup["path"] + "/executor.before"] = "f" * 64
                with self.assertRaises(c.Stop): self.run_action(n, backup)
                self.assertFalse(any(e[0] == "helper" and e[-1] for e in n.events))

    def test_nonzero_calls_and_rollback_failure_no_retry(self):
        n, backup = self.fixture(); n.zero_error = True
        with self.assertRaises(c.Stop): self.run_action(n, backup)
        self.assertFalse(any(e[0] == "helper" and e[-1] for e in n.events))
        n, backup = self.fixture(); n.rc = 9; n.output = b"rollback=failed"
        result = self.run_action(n, backup)
        self.assertEqual(result["status"], "helper_failed_stop_no_retry")
        self.assertEqual(len([e for e in n.events if e[0] == "helper" and e[-1]]), 1)


class CoreDelegation(unittest.TestCase):
    def setUp(self):
        self.module = c.core_module(B)
        root, link = self.module.ROOT, self.module.LINK
        self.before = {root: {"type": "directory", "mode": 493, "uid": 1000, "gid": 1000},
            link: {"type": "symlink", "mode": 511, "uid": 1000, "gid": 1000, "target": "../lib/node_modules/openclaw/openclaw.mjs"},
            root + "/openclaw.mjs": {"type": "file", "mode": 493, "uid": 1000, "gid": 1000, "size": 8, "sha256": "1" * 64}}
        self.after = copy.deepcopy(self.before); self.after[root + "/openclaw.mjs"]["sha256"] = "9" * 64
        self.skill = "skills/avril-call/rita_internal_calls.js"
        self.controls = {"/home/aimee/.openclaw/openclaw.json": "a" * 64}
        self.packet = {"closure": dict(B["components"]["crustacea"]["closure"]), "protected": self.controls,
            "expected_current_sha256": self.module.body_hash(self.before),
            "workspace": [{"target": self.skill, "sha256": "9" * 64, "before_sha256": "1" * 64}]}
        outer = self
        class Native:
            def __init__(self):
                self.current = {"core_manifest_sha256": outer.module.body_hash(outer.before), outer.skill: "1" * 64}
                self.target = {"core_manifest_sha256": outer.module.body_hash(outer.after), outer.skill: "9" * 64}
                self.events = []; self.rc = 0; self.wrong = False; self.missing = False; self.packet_drift = False
                self.snapshot = {"schema": outer.module.SCHEMA, "phase_helper_sha256": B["components"]["crustacea"]["helper_sha"],
                    "DB_restored": False, "config_restored": False, "closure": {k: outer.packet["closure"][k] for k in ("archive_sha256", "manifest_sha256", "receipt_sha256")},
                    "before": outer.before, "workspace": [{"target": outer.skill, "before": {"sha256": "1" * 64}}],
                    "captured_archive_sha256": "7" * 64}
                self.data = json.dumps(self.snapshot).encode(); self.pin = hashlib.sha256(self.data).hexdigest()
                self.path = "/root/crustacea-core-recovery-fixture"
                self.blobs = {self.path + "/snapshot.json": self.pin, self.path + "/captured-core-launcher.tar.gz": "7" * 64,
                              self.path + "/0.before": "1" * 64}
                self.ledger = b"new accrued state"
            def hashes(self, component, paths, b):
                self.events.append("hashes")
                if set(paths) == set(outer.controls): return dict(outer.controls)
                if set(paths) == set(self.blobs): return dict(self.blobs)
                rows = {}
                for p in paths:
                    if p.endswith("coordinator/deployment/recovery-coordinator.py"): rows[p] = c.digest(c.__file__)
                    elif p.endswith("coordinator/component-bindings-20260914.json"): rows[p] = c.BINDINGS_SHA
                    else: rows[p] = next(v for k, v in b["components"]["crustacea"]["execution_files"].items() if p.endswith(k.removeprefix("recovery/")))
                return rows
            def owner_packet(self, root, b):
                value = copy.deepcopy(outer.packet)
                if self.packet_drift: value["protected"] = {}
                return value
            def zero(self): self.events.append("zero")
            def core_observe(self, roots, b):
                self.events.append("observe")
                if self.missing:
                    self.missing = False; raise c.Stop("core_authoritative_observation_unavailable")
                return dict(self.current)
            def document(self, *args): return self.data
            def helper(self, component, args, b, mutation=False):
                self.events.append(tuple(args))
                rollback = "rollback" in args
                if not self.wrong and self.rc == 0:
                    self.current = {"core_manifest_sha256": outer.module.body_hash(outer.before), outer.skill: "1" * 64} if rollback else self.target
                result = {"status": "captured_rollback_passed" if rollback else "captured_install_passed", "snapshot": self.path, "snapshot_sha256": self.pin}
                if self.rc: result.update(primary_error="candidate_failed", rollback_error="pending_job", rollback_status="deferred_no_retry")
                return self.rc, json.dumps(result).encode()
        self.n = Native()
        self.backup = {"path": self.n.path, "manifest_sha256": self.n.pin}
        self.patch = mock.patch.object(c, "core_inputs", return_value=(self.module, Path("/fixture/packet"), self.packet, self.after))
        self.patch.start(); self.addCleanup(self.patch.stop)
    def run_action(self, mode):
        return c.execute_core(mode, Path("/fixture"), stages(), self.n, self.backup if mode == "rollback" else None,
                              dict(self.n.current), {"native_FreePBX_UI_checked": True}, B)
    def test_install_uses_captured_phase_not_npm_or_relay_installer(self):
        self.assertEqual(self.run_action("install")["status"], "delegated_install_passed")
        argv = next(e for e in self.n.events if isinstance(e, tuple))
        self.assertTrue(argv[2].endswith("coordinator/deployment/recovery-coordinator.py"))
        self.assertEqual(argv[3:6], ("core-phase", "--phase-mode", "apply"))
        self.assertFalse(any("npm" in v or "relay.sh" in v for v in argv))
    def test_rollback_exact_snapshot_core_and_static_not_pre_rollback_bytes(self):
        self.n.current = dict(self.n.target)
        self.assertEqual(self.run_action("rollback")["status"], "delegated_rollback_passed")
        self.assertEqual(self.n.current["core_manifest_sha256"], self.module.body_hash(self.before))
        self.assertEqual(self.n.current[self.skill], "1" * 64); self.assertEqual(self.n.ledger, b"new accrued state")
    def test_missing_candidate_observation_does_not_block_owned_snapshot_restore(self):
        self.n.missing = True
        self.assertEqual(self.run_action("rollback")["status"], "delegated_rollback_passed")
    def test_missing_candidate_observation_blocks_install(self):
        self.n.missing = True
        with self.assertRaisesRegex(c.Stop, "observation_required_for_install"): self.run_action("install")
        self.assertFalse(any(isinstance(e, tuple) for e in self.n.events))
    def test_zero_exit_wrong_or_unchanged_snapshot_bytes_rejected(self):
        self.n.current = dict(self.n.target); self.n.wrong = True
        with self.assertRaisesRegex(c.Stop, "postimage_mismatch"): self.run_action("rollback")
    def test_wrong_snapshot_pin_or_capture_hash_blocks_before_mutation(self):
        self.n.blobs[self.n.path + "/captured-core-launcher.tar.gz"] = "f" * 64
        with self.assertRaisesRegex(c.Stop, "backup_bytes_mismatch"): self.run_action("rollback")
        self.assertFalse(any(isinstance(e, tuple) for e in self.n.events))
    def test_owner_packet_drift_rejected_before_delegation(self):
        self.n.packet_drift = True
        with self.assertRaisesRegex(c.Stop, "semantics_changed"): self.run_action("install")
    def test_failed_owner_retains_separate_coded_errors_no_retry(self):
        self.n.rc = 7
        result = self.run_action("install")
        self.assertEqual(result["helper_exit"], 7); self.assertEqual(result["rollback_error"], "pending_job")
        self.assertEqual(len([e for e in self.n.events if isinstance(e, tuple)]), 1)


class SafetyTests(unittest.TestCase):
    def test_path_injection_rejected(self):
        for p in ("/tmp/a;id", "/tmp/a b", "/tmp/../etc", "relative", "/tmp/a\n"):
            with self.subTest(p=p), self.assertRaises(c.Stop): c.safe_path(p)

    def test_archive_escape_and_links_rejected(self):
        with tempfile.TemporaryDirectory(prefix="vip-archive-",dir=HERE.parent) as tmp:
            p = Path(tmp)/"a.tar.gz"
            for name, kind in (("../escape",tarfile.REGTYPE),("root/link",tarfile.SYMTYPE),("/etc/foo",tarfile.REGTYPE)):
                with self.subTest(name=name):
                    with tarfile.open(p,"w:gz") as t:
                        m=tarfile.TarInfo(name);m.type=kind;t.addfile(m)
                    with self.assertRaises(c.Stop): c.archive_rows(p)

    def test_manifest_duplicate_unsorted_rejected(self):
        for data in (("a"*64+"  x\n")*2, "a"*64+"  z\n"+"b"*64+"  a\n"):
            with self.assertRaises(c.Stop): c.sha_manifest(data.encode())

    def test_private_receipt_exclusive_mode_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="vip-receipt-",dir=HERE.parent) as tmp:
            p=Path(tmp)/"proof.json";c.write_receipt(p,{"status":"fixture"})
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError): c.write_receipt(p,{})
            self.assertEqual(json.loads(p.read_bytes())["status"],"fixture")

    def test_unknown_roots_keys_rejected(self):
        with tempfile.TemporaryDirectory(prefix="vip-roots-",dir=HERE.parent) as tmp:
            p=Path(tmp)/"roots.json";p.write_text('{"shell":"/tmp"}')
            with self.assertRaises(c.Stop):c.read_roots(p,B)

    def test_native_actor_argv(self):
        n=object.__new__(c.Native);n.key=Path("/fixture/key");n.active_pid=None
        for host,actor in B["actors"].items():
            with self.subTest(host=host):
                child=mock.Mock(pid=42);child.wait.return_value=0;child.poll.return_value=0
                with mock.patch.object(c.subprocess,"Popen",return_value=child) as p:
                    n._run(host,["/usr/bin/true"])
                self.assertIn(actor+"@"+host,p.call_args.args[0])
                self.assertIn("sudo",p.call_args.args[0])

    def test_readonly_timeout_reaps_only_owned_child(self):
        n=object.__new__(c.Native);n.key=Path("/fixture/key");n.active_pid=None
        child=mock.Mock(pid=43);child.wait.side_effect=[subprocess.TimeoutExpired("fixture",45),0];child.poll.return_value=0
        with mock.patch.object(c.subprocess,"Popen",return_value=child):
            with self.assertRaises(c.Stop):n._run("vip.bajaj.com",["/usr/bin/true"])
        child.kill.assert_called_once();self.assertEqual(child.wait.call_count,2)

    def test_mutation_has_no_outer_timeout_or_retry(self):
        n=object.__new__(c.Native);n.key=Path("/fixture/key");n.active_pid=None
        child=mock.Mock(pid=44);child.wait.return_value=1;child.poll.return_value=1
        with mock.patch.object(c.subprocess,"Popen",return_value=child):
            rc,_=n._run("vip.bajaj.com",["/usr/bin/true"],mutation=True)
        self.assertEqual(rc,1);child.wait.assert_called_once_with(timeout=None);child.kill.assert_not_called()

    def test_actual_zero_parser_does_not_accept_false_or_error(self):
        n=object.__new__(c.Native)
        for data in (b"False active channels\nFalse active calls\n",b"Unable to connect to Asterisk",b"1 active channels\n0 active calls\n"):
            with self.subTest(data=data),mock.patch.object(n,"_run",return_value=(0,data)):
                with self.assertRaises(c.Stop):n.zero()
        with mock.patch.object(n,"_run",return_value=(0,b"0 active channels\n0 active calls\n")):n.zero()

    def test_dry_run_no_native_constructor_and_incomplete(self):
        with tempfile.TemporaryDirectory(prefix="vip-dry-",dir=HERE.parent) as tmp:
            root=Path(tmp)/"roots.json";root.write_text("{}")
            with mock.patch.object(c,"Native",side_effect=AssertionError("native prohibited")),contextlib.redirect_stdout(io.StringIO()) as out:
                code=c.main(["install","--dry-run","--roots",str(root)])
            self.assertEqual(code,2);self.assertIn("INCOMPLETE",out.getvalue())

    def test_failure_receipt_survives_readonly_timeout(self):
        with tempfile.TemporaryDirectory(prefix="vip-failure-",dir=HERE.parent) as tmp:
            root=Path(tmp)/"roots.json";root.write_text("{}")
            cp=Path(tmp)/"cp.json";cp.write_text('{"native_FreePBX_UI_checked":true}')
            proof=Path(tmp)/"attempt.json"
            with mock.patch.object(c,"Native",return_value=mock.Mock(active_pid=None)),mock.patch.object(c,"execute",side_effect=c.Stop("readonly_transport_timeout")),contextlib.redirect_stdout(io.StringIO()):
                code=c.main(["install","--component","rita","--roots",str(root),"--checkpoints",str(cp),
                             "--ssh-key","/fixture/key","--receipt",str(proof)])
            self.assertEqual(code,2);self.assertTrue(proof.is_file())
            self.assertEqual(json.loads(Path(str(proof)+".final.json").read_bytes())["reason"],"readonly_transport_timeout")


class AcquiredPackageLayouts(unittest.TestCase):
    @contextlib.contextmanager
    def package(self, component):
        with tempfile.TemporaryDirectory(prefix="vip-package-layout-", dir=HERE.parent) as tmp:
            root = Path(tmp)
            b = copy.deepcopy(B)
            s = b["components"][component]
            kit = root / s["kit"]
            helper = kit / s["helper"]
            protected = kit / "protected/native.env"
            for path, data, mode in (
                    (helper, b"#!/bin/sh\n# Offline fixture only.\n", 0o755),
                    (protected, b"# Dummy protected fixture, not a credential.\n", 0o600)):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(mode)
            inventory = root / ("KIT-INVENTORY.json" if component == "voice-organ"
                                else "deployment-kit/tessa/MANIFEST.sha256")
            rows = {str(path.relative_to(kit)): {"sha256": c.digest(path),
                                                "mode": format(path.stat().st_mode & 0o777, "04o")}
                    for path in (helper, protected)}
            if component == "voice-organ":
                inventory.write_text(json.dumps({"complete_regular_files": rows}, sort_keys=True))
            else:
                inventory.write_text("".join(rows[name]["sha256"] + "  " + name + "\n"
                                             for name in sorted(rows)))
                inventory.chmod(0o644)

            def archive(path, contents):
                with tarfile.open(path, "w:gz") as out:
                    for name, data, mode in sorted(contents):
                        member = tarfile.TarInfo(name)
                        member.size, member.mode = len(data), mode
                        out.addfile(member, io.BytesIO(data))

            canonical = root / s["canonical"]
            source = b"# Public source layout fixture.\n"
            archive(canonical, [(component + "/source.py", source, 0o644)])
            manifest = root / s["canonical"].replace(".tar.gz", ".sha256")
            manifest.write_text(hashlib.sha256(source).hexdigest() + "  source.py\n")
            files = [path for path in kit.rglob("*") if path.is_file()]
            skeleton = root / s["skeleton"]
            archive(skeleton, [("skeleton/" + kit.name + "/" + str(path.relative_to(kit)),
                                path.read_bytes(), path.stat().st_mode & 0o777)
                               for path in files])
            s.update(canonical_sha=c.digest(canonical), manifest_sha=c.digest(manifest),
                     skeleton_sha=c.digest(skeleton), inventory_sha=c.digest(inventory),
                     source_files=1, kit_files=len(files), helper_sha=c.digest(helper))
            yield root, b

    def test_voice_organ_inventory_is_at_acquisition_root(self):
        self.assertEqual(B["components"]["voice-organ"]["inventory"], "KIT-INVENTORY.json")
        self.assertEqual(B["components"]["voice-organ"]["inventory_sha"],
                         "1b83e108002fff01634bd539f233581ec90fa0ecf1abf366f1d26b4ad2c409b8")
        with self.package("voice-organ") as (root, b):
            result = c.verify_package("voice-organ", root, b)
            self.assertEqual((result["source_files"], result["kit_files"]), (1, 2))
            self.assertTrue(result["skeleton_equal"])
            self.assertFalse(result["native_or_human_acceptance"])

    def test_voice_organ_obsolete_evidence_layout_has_no_fallback(self):
        with self.package("voice-organ") as (root, b):
            target = root / "evidence/KIT-INVENTORY.json"
            target.parent.mkdir()
            (root / "KIT-INVENTORY.json").rename(target)
            with self.assertRaisesRegex(c.Stop, "artifact_missing_or_hash_mismatch"):
                c.verify_package("voice-organ", root, b)

    def test_voice_organ_inventory_hash_drift_is_rejected(self):
        with self.package("voice-organ") as (root, b):
            with (root / "KIT-INVENTORY.json").open("a") as stream:
                stream.write(" ")
            with self.assertRaisesRegex(c.Stop, "artifact_missing_or_hash_mismatch"):
                c.verify_package("voice-organ", root, b)

    def test_tessa_current_owner_files_and_standalone_root(self):
        s = B["components"]["tessa"]
        result = c.verify_package("tessa", TESSA_CURRENT, B)
        self.assertEqual((result["source_files"], result["retained_files"]), (16, 19))
        self.assertEqual(s["native_root"], "/opt/tessa")
        self.assertEqual(s["compose"], "/opt/tessa/deployment/docker-compose.yml")
        self.assertFalse(result["full_component_release_matched"])

    def test_tessa_wrong_or_extra_current_file_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="tessa-current-", dir=HERE.parent) as tmp:
            root = Path(tmp)
            for name in B["components"]["tessa"]["files"]:
                p = root / name; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes((TESSA_CURRENT / name).read_bytes())
            (root / "unexpected").write_bytes(b"extra")
            with self.assertRaisesRegex(c.Stop, "current_owner_file_coverage_or_hash_mismatch"):
                c.verify_package("tessa", root, B)

    def test_package_layout_checks_reject_changed_installed_modes(self):
        for component in ("voice-organ",):
            with self.subTest(component=component), self.package(component) as (root, b):
                (root / b["components"][component]["kit"] /
                 b["components"][component]["helper"]).chmod(0o644)
                with self.assertRaisesRegex(c.Stop, "kit_mode_mismatch|skeleton_kit_coverage_or_modes"):
                    c.verify_package(component, root, b)


class BackupSidecarContracts(unittest.TestCase):
    def verify_fixture(self, wal_bytes):
        with tempfile.TemporaryDirectory(prefix="vip-empty-backup-WAL-", dir=HERE.parent) as tmp:
            root = Path(tmp)
            kit = root / "ava"
            helper = kit / "deploy/fixture-helper.py"
            db = kit / "protected/database/agents.db"
            for p, data in ((helper, b"# public fixture helper\n"), (db, b"consistent dummy backup")):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                p.chmod(0o600)
            def archive(path, rows):
                with tarfile.open(path, "w:gz") as out:
                    for name, data in sorted(rows.items()):
                        m = tarfile.TarInfo(name)
                        m.size, m.mode = len(data), 0o600
                        out.addfile(m, io.BytesIO(data))
            canonical = root / "fixture-canonical.tar.gz"
            archive(canonical, {"ava/source.py": b"# public source fixture\n"})
            manifest = root / "fixture-canonical.sha256"
            manifest.write_text(hashlib.sha256(b"# public source fixture\n").hexdigest() + "  source.py\n")
            skeleton = root / "fixture-skeleton.tar.gz"
            archive(skeleton, {"ava/" + str(p.relative_to(kit)): p.read_bytes() for p in (helper, db)})
            inventory = root / "fixture-inventory.json"
            inventory.write_text(json.dumps({str(p.relative_to(kit)): {"sha256": c.digest(p), "mode": "0600"}
                                             for p in (helper, db)}, sort_keys=True))
            wal = db.with_name("agents.db-wal")
            shm = db.with_name("agents.db-shm")
            wal.write_bytes(wal_bytes)
            shm.write_bytes(b"dummy derived shared-memory state")
            for p in (wal, shm): p.chmod(0o600)
            before = {str(p): c.digest(p) for p in (db, wal, shm)}
            b = copy.deepcopy(B)
            b["components"]["ava"].update(canonical=canonical.name, canonical_sha=c.digest(canonical),
                manifest_sha=c.digest(manifest), skeleton=skeleton.name, skeleton_sha=c.digest(skeleton),
                inventory=inventory.name, inventory_sha=c.digest(inventory), source_files=1, kit_files=2,
                helper="deploy/fixture-helper.py", helper_sha=c.digest(helper))
            try:
                return c.verify_package("ava", root, b)
            finally:
                self.assertEqual({str(p): c.digest(p) for p in (db, wal, shm)}, before)

    def test_empty_WAL_and_derived_SHM_only_excluded_without_alteration(self):
        result = self.verify_fixture(b"")
        self.assertEqual(result["kit_files"], 2)
        self.assertTrue(result["skeleton_equal"])
        self.assertEqual(result["excluded_generated_empty_backup_WAL_and_SHM"],
                         ["protected/database/agents.db-shm", "protected/database/agents.db-wal"])

    def test_nonempty_backup_WAL_blocks_without_alteration(self):
        with self.assertRaisesRegex(c.Stop, "nonempty_backup_WAL_requires_retention"):
            self.verify_fixture(b"dummy pending backup transaction")


def plugin_fixture():
    return {"workspaceDir": "/home/aimee/.openclaw/workspace", "workspaceScope": "selected",
            "registry": {"source": "persisted", "diagnostics": []}, "diagnostics": [],
            "plugins": [{"id": name, "version": "fixture", "source": "official", "rootDir": "/fixture/"+name,
                "origin": "global", "trustedOfficialInstall": True, "status": "loaded", "enabled": True,
                "trust": {"source": "official"}, "dependencyStatus": {"installed": ["fixture-dependency"], "missing": []}}
                for name in ("matrix", "nodes")]}


def plugin_discovery_payload(size=147211, value=None):
    """Synthetic 80-plugin catalogue at the measured native byte size, not live data."""
    if value is None:
        value = plugin_fixture()
        template = value["plugins"][0]
        value["plugins"] = []
        for index in range(80):
            row = copy.deepcopy(template)
            row.update(id="fixture-plugin-" + str(index), rootDir="/fixture/plugins/" + str(index),
                       status="loaded" if index < 62 else "disabled", enabled=index < 62,
                       description="Offline synthetic capability documentation. " * 25)
            value["plugins"].append(row)
    data = json.dumps(value, sort_keys=True).encode("utf-8")
    if len(data) > size:
        raise ValueError("fixture_catalogue_exceeds_requested_size")
    return data + b" " * (size - len(data))


class OwnerNativeGateContracts(unittest.TestCase):
    def setUp(self):
        self.phase = c.core_module(B)
        self.fleet = mock.Mock()
        self.gate = c.CoreOwnerGates(self.fleet, {"owner_input": {"protected_metadata": {}}}, stages(), B, self.phase)

    def test_plugin_native_aimee_HOME_workspace_actor_and_root_delegation_argv(self):
        self.fleet._run.return_value = (0, json.dumps(plugin_fixture()).encode())
        projected = self.gate.preservation()
        args = ["/usr/sbin/runuser", "-u", "aimee", "--", "/usr/bin/env", "HOME=/home/aimee", "/usr/bin/env", "-C",
                "/home/aimee/.openclaw/workspace", "/usr/bin/openclaw", "plugins", "list", "--json"]
        self.fleet._run.assert_called_once_with("crustacea.bajaj.com", args, budget=1048576)
        self.assertEqual(projected["plugins"]["workspaceScope"], "selected")
        n = object.__new__(c.Native); n.key = Path("/fixture/key"); n.active_pid = None
        for local in (None, "crustacea.bajaj.com"):
            with self.subTest(local=local):
                n.local_host = local
                child = mock.Mock(pid=31); child.wait.return_value = 0; child.poll.return_value = 0
                with mock.patch.object(c.subprocess, "Popen", return_value=child) as launch: n._run("crustacea.bajaj.com", args)
                observed = launch.call_args.args[0]
                self.assertEqual(observed[-len(args):], args)
                self.assertIn("-n", observed)
                self.assertIn("aimee", observed)
                if local is None: self.assertIn("aimee@crustacea.bajaj.com", observed)
                else: self.assertEqual(observed[:2], ["/usr/bin/sudo", "-n"])

    @contextlib.contextmanager
    def native_output(self, data):
        native = object.__new__(c.Native)
        native.key, native.active_pid = Path("/fixture/key"), None
        native.local_host = "crustacea.bajaj.com"
        child = mock.Mock(pid=37)
        child.wait.return_value = child.poll.return_value = 0
        def launch(args, **kwargs):
            kwargs["stdout"].write(data)
            kwargs["stdout"].flush()
            return child
        with mock.patch.object(c.subprocess, "Popen", side_effect=launch) as spawned:
            yield native, spawned, child

    def test_measured_size_plugin_discovery_reads_complete_native_payload(self):
        data = plugin_discovery_payload()
        self.assertEqual(len(data), 147211)
        with self.native_output(data) as (native, spawned, child):
            self.gate.fleet = native
            result = self.gate.preservation()
        self.assertEqual(result, {"controls": {}, "plugins": c.plugin_projection(json.loads(data))})
        self.assertEqual(len(result["plugins"]["plugins"]), 80)
        self.assertEqual(sum(row["enabled"] for row in result["plugins"]["plugins"]), 62)
        self.assertEqual(spawned.call_args.args[0], ["/usr/bin/sudo", "-n", "/usr/sbin/runuser", "-u",
                         "aimee", "--", "/usr/bin/env", "HOME=/home/aimee", "/usr/bin/env", "-C",
                         "/home/aimee/.openclaw/workspace", "/usr/bin/openclaw", "plugins", "list", "--json"])
        child.wait.assert_called_once_with(timeout=45)
        self.assertIsNone(native.active_pid)

    def test_discovery_exact_one_MiB_is_accepted_without_truncation(self):
        data = plugin_discovery_payload(1048576)
        self.assertEqual(len(data), 1048576)
        with self.native_output(data) as (native, _, __):
            self.gate.fleet = native
            self.assertEqual(self.gate.preservation()["plugins"], c.plugin_projection(json.loads(data)))

    def test_discovery_above_one_MiB_is_rejected_before_projection(self):
        with self.native_output(plugin_discovery_payload(1048577)) as (native, _, __):
            self.gate.fleet = native
            with mock.patch.object(c, "plugin_projection") as projection:
                with self.assertRaisesRegex(self.phase.d.Stop, "native_output_over_budget"):
                    self.gate.preservation()
                projection.assert_not_called()

    def test_ordinary_exact_original_budget_is_accepted(self):
        data = b"x" * 131072
        with self.native_output(data) as (native, _, __):
            self.assertEqual(native._run("crustacea.bajaj.com", ["/usr/bin/true"]), (0, data))

    def test_ordinary_above_original_budget_still_rejects_measured_size(self):
        for size in (131073, 147211):
            with self.subTest(bytes=size), self.native_output(b"x" * size) as (native, _, __):
                with self.assertRaisesRegex(c.Stop, "native_output_over_budget"):
                    native._run("crustacea.bajaj.com", ["/usr/bin/true"])

    def test_large_malformed_JSON_is_still_rejected(self):
        with self.native_output(b"{" + b" " * 147210) as (native, _, __):
            self.gate.fleet = native
            with self.assertRaisesRegex(self.phase.d.Stop, "native_owner_observation_invalid"):
                self.gate.preservation()

    def test_large_malformed_projection_is_still_rejected(self):
        for field, replacement, code in (("workspaceScope", "global", "plugin_workspace_projection_changed"),
                                         ("registry", {"source": "transient"}, "plugin_registry_not_current_persisted")):
            wrong = json.loads(plugin_discovery_payload())
            wrong[field] = replacement
            with self.subTest(field=field), self.native_output(plugin_discovery_payload(value=wrong)) as (native, _, __):
                self.gate.fleet = native
                with self.assertRaisesRegex(self.phase.d.Stop, code):
                    self.gate.preservation()

    def test_plugin_order_independent_but_selected_workspace_strict(self):
        value = plugin_fixture(); reordered = copy.deepcopy(value); reordered["plugins"].reverse()
        self.assertEqual(c.plugin_projection(value), c.plugin_projection(reordered))
        for field, replacement in (("workspaceDir", "/root/.openclaw/workspace"), ("workspaceScope", "global"), ("diagnostics", ["fixture-error"])):
            with self.subTest(field=field):
                wrong = copy.deepcopy(value); wrong[field] = replacement
                with self.assertRaises(c.Stop): c.plugin_projection(wrong)

    def test_plugin_dependency_trust_or_registry_drift_remains_visible(self):
        original = c.plugin_projection(plugin_fixture())
        for field, replacement in (("dependencyStatus", {"installed": [], "missing": ["fixture-dependency"]}), ("trust", {"source": "changed"}), ("rootDir", "/fixture/foreign")):
            with self.subTest(field=field):
                value = plugin_fixture(); value["plugins"][0][field] = replacement
                self.assertNotEqual(c.plugin_projection(value), original)
        value = plugin_fixture(); value["registry"]["source"] = "transient"
        with self.assertRaises(c.Stop): c.plugin_projection(value)

    def test_zero_delegates_existing_native_zero_and_full_Ava_installed_owner_check(self):
        result = {"commit": B["components"]["ava"]["runtime"], "status": "installed_verify_pass",
                  "installed": {p.removeprefix("/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"): {"sha256": h}
                                for p, h in B["components"]["ava"]["after"].items()},
                  "health": {}, "configuration": {}, "logical_agent_config": {}}
        self.fleet.helper.return_value = (0, json.dumps(result).encode())
        self.fleet.hashes.side_effect = lambda component, paths, b: dict(b["components"][component]["foundation_files"])
        with mock.patch.object(c, "staged_check") as stage: self.gate.zero()
        self.fleet.zero.assert_called_once_with(); stage.assert_called_once_with(self.fleet, "ava", stages(), B, installed=True)
        self.fleet.helper.assert_called_once_with("ava", c.owner_argv("ava", "verify-installed", stages(), {}, None, B), B)
        self.fleet.zero.side_effect = c.Stop("native_not_zero")
        with self.assertRaisesRegex(self.phase.d.Stop, "native_not_zero"): self.gate.zero()

    def test_controls_preserve_exact_metadata_not_just_hash(self):
        expected = {"sha256": "a"*64, "size": 7, "mode": 0o640, "uid": 0, "gid": 1000}
        self.gate.packet["owner_input"]["protected_metadata"] = {"/fixture/control": expected}
        with mock.patch.object(self.phase, "metadata", return_value=dict(expected, type="file")):
            self.assertEqual(self.gate.control_metadata()["/fixture/control"], expected)
        for field in ("sha256", "mode", "uid", "gid", "size"):
            with self.subTest(field=field):
                wrong = dict(expected); wrong[field] = "b"*64 if field == "sha256" else expected[field]+1
                with mock.patch.object(self.phase, "metadata", return_value=wrong), self.assertRaises(c.Stop): self.gate.control_metadata()

    def ready_transport(self, host, args):
        self.assertEqual(host, "crustacea.bajaj.com")
        if args[0] == "/usr/bin/systemctl": return 0, b"Job=0\nMainPID=19\nActiveState=active\nSubState=running\nInvocationID=fixture\n"
        return 0, b"200" if args[0] == "/usr/bin/curl" else b"verified"

    def test_ready_root_service_full_verifier_and_both_loopback_families(self):
        self.fleet._run.side_effect = self.ready_transport
        with mock.patch.object(c, "digest", return_value=self.phase.VERIFIER_SHA): self.gate.ready()
        calls = [x.args[1] for x in self.fleet._run.call_args_list]
        self.assertEqual(calls[0], ["/usr/bin/systemctl", "show", "openclaw.service", "--property=Job,MainPID,ActiveState,SubState,InvocationID"])
        self.assertEqual(calls[1], ["/bin/bash", "/usr/local/lib/openclaw-py/verify-all.sh"])
        self.assertEqual([args[-1] for args in calls[2:]], ["http://127.0.0.1:18789/healthz", "'http://[::1]:18789/healthz'"])
        self.assertFalse(any("runuser" in " ".join(args) for args in calls))

    def test_ready_pending_job_or_bad_family_not_passed(self):
        self.fleet._run.return_value = (0, b"Job=12 start\nMainPID=19\nActiveState=active\nSubState=running\n")
        with self.assertRaises(self.phase.d.Stop): self.gate.ready()
        self.assertEqual(self.fleet._run.call_count, 1)
        self.fleet.reset_mock(); self.fleet._run.side_effect = lambda host, args: (0, b"503") if args[-1] == "'http://[::1]:18789/healthz'" else self.ready_transport(host, args)
        with mock.patch.object(c, "digest", return_value=self.phase.VERIFIER_SHA), self.assertRaises(self.phase.d.Stop): self.gate.ready()

    def test_wrapper_requires_private_existing_settings_before_dispatch(self):
        with tempfile.TemporaryDirectory(prefix="owner-settings-", dir=HERE.parent) as tmp:
            path = Path(tmp)/"PHASE-SETTINGS.json"
            packet = {"native_gate_contract": B["components"]["crustacea"]["native_gate_contract"]}
            with mock.patch.object(c, "core_inputs", return_value=(self.phase, Path(tmp), packet, {})), mock.patch.object(c, "Native", side_effect=AssertionError("no native constructor")), contextlib.redirect_stdout(io.StringIO()):
                for content, mode in ((None, None), ({"ssh_key": "/fixture/key", "native_roots": {"ava": str(stages()["ava"])}}, 0o644), ({"shell": "not-allowed"}, 0o600)):
                    with self.subTest(mode=mode):
                        if content is not None: path.write_text(json.dumps(content)); path.chmod(mode)
                        self.assertEqual(c.main(["core-phase", "--phase-mode", "apply", "--inputs", str(Path(tmp)/"INPUTS.json"), "--settings", str(path)]), 2)

    def test_wrapper_observe_needs_no_key_or_checker(self):
        with mock.patch.object(c, "core_inputs", return_value=(self.phase, Path("/fixture"), {}, {})), mock.patch.object(c, "Native", side_effect=AssertionError("no transport")), mock.patch.object(self.phase, "main", return_value=0) as native:
            self.assertEqual(c.owner_core_main(["--phase-mode", "observe", "--inputs", "/fixture/INPUTS.json", "--settings", "/fixture/not-required"]), 0)
        native.assert_called_once_with(["observe", "--inputs", "/fixture/INPUTS.json"], native_gates=None)


def qualified_module(path, name, expected):
    require_hash = c.digest(path) == expected
    if not require_hash:
        raise AssertionError("qualified helper hash mismatch")
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ActualOwnerContracts(unittest.TestCase):
    def test_voice_actual_cli_check_apply_rollback_repeat_preserves_controls_and_state(self):
        path = HERE / "components/voice-organ/test_executor_transaction.py"
        t = qualified_module(path, "voice_owner_fixtures", "a1f3eb84c3dac0c9f3f5fac7d0171ffa12f5b1ea214450aa0e6749eeaf1eff72")
        frame = t.Transactions("test_apply_rollback_repeat_preserve_new_state"); frame.setUp()
        self.addCleanup(frame.doCleanups)
        d = t.d; original = d.transaction; euid = os.geteuid; original_open = os.open
        def transaction(*args, **kw):
            with mock.patch.object(d.os, "geteuid", euid): return original(*args, **kw)
        def fixture_open(path, *args, **kw):
            if str(path) == "/root/.avril-call-executor-replacement.lock": path = frame.layout.backup_base / "owned.lock"
            return original_open(path, *args, **kw)
        b = copy.deepcopy(B); b["components"]["voice-organ"]["backup_base"] = str(frame.layout.backup_base)
        current = {"/usr/local/sbin/avril-call-executor": frame.old["sha256"]}
        controls = frame.n.controls()
        with mock.patch.object(d, "Layout", return_value=frame.layout), mock.patch.object(d, "Native", return_value=frame.n), \
             mock.patch.object(d, "transaction", side_effect=transaction), mock.patch.object(d.os, "geteuid", return_value=0), \
             mock.patch.object(d.os, "open", side_effect=fixture_open), contextlib.redirect_stdout(io.StringIO()) as out:
            def invoke(mode, backup=None):
                argv = c.owner_argv("voice-organ", mode, stages(), current, backup, b)
                # The accepted bash wrapper only execs this exact Python helper with unchanged argv.
                argv = argv[2:]
                if "--candidate" in argv: argv[argv.index("--candidate") + 1] = str(frame.candidate)
                if "--candidate-sha256" in argv: argv[argv.index("--candidate-sha256") + 1] = frame.new
                self.assertEqual(d.main(argv), 0, out.getvalue())
                return json.loads(out.getvalue().splitlines()[-1])
            invoke("check"); self.assertNotIn("stop", frame.n.events)
            installed = invoke("install"); frame.ledger.write_bytes(b"new accrued ledger")
            current[next(iter(current))] = frame.new
            backup = {"path": installed["backup"], "manifest_sha256": installed["backup_manifest_sha256"]}
            invoke("rollback", backup); current[next(iter(current))] = frame.old["sha256"]
            invoke("rollback", backup)
        self.assertEqual(d.fingerprint(frame.layout.live), frame.old)
        self.assertEqual(frame.n.controls(), controls)
        self.assertEqual(frame.ledger.read_bytes(), b"new accrued ledger")

    def core_actual_owner_cli(self, fail_plugin=False, plugin_drift=False):
        path = HERE / "components/crustacea/test_captured_core_phase.py"
        t = qualified_module(path, "core_owner_fixtures", "d833f53cdce1fc128d700c142d7f9ebd40bdb8feafd0d4a8aa16026167225c5d")
        frame = t.CapturedPhase("test_actual_cli_install_and_rollback_uses_snapshot_pin_and_preserves_state"); frame.setUp()
        self.addCleanup(frame.doCleanups)
        frame.native_contract()
        frame.m["owner_input"] = {"protected_metadata": {str(frame.control): {k: t.c.metadata(frame.control)[k] for k in ("sha256", "size", "mode", "uid", "gid")}}}
        frame.save()
        settings = frame.packet / "PHASE-SETTINGS.json"
        settings.write_text(json.dumps({"ssh_key": "/fixture/existing-key", "native_roots": {"ava": str(stages()["ava"])}})); settings.chmod(0o600)
        phase = t.c; original = phase.execute; original_open = os.open; euid = os.geteuid
        def execute(*args, **kw):
            with mock.patch.object(phase.os, "geteuid", euid): return original(*args, **kw)
        def fixture_open(path, *args, **kw):
            if str(path) == "/root/.crustacea-core-workspace-recovery.lock": path = frame.root / "owned.lock"
            return original_open(path, *args, **kw)
        b = copy.deepcopy(B); b["components"]["crustacea"]["backup_base"] = str(frame.root)
        def layout():
            value = type("OwnedFixtureLayout", (), {})()
            for key in ("core", "entrypoint", "workspace", "backups"): setattr(value, key, getattr(frame.layout, key))
            return value
        outer = self
        class Fleet:
            def __init__(self): self.plugins = 0; self.argv = []
            def zero(self): frame.n.zero()
            def hashes(self, component, paths, b): return FakeNative("ava", b["components"]["ava"]["before"], b).hashes(component, paths, b)
            def helper(self, component, args, b):
                outer.assertEqual(component, "ava"); outer.assertEqual(args, c.owner_argv("ava", "verify-installed", stages(), {}, None, b))
                result = {"commit": b["components"]["ava"]["runtime"], "status": "installed_verify_pass",
                          "installed": {p.removeprefix("/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"): {"sha256": h}
                                        for p, h in b["components"]["ava"]["after"].items()},
                          "health": {}, "configuration": {}, "logical_agent_config": {}}
                self.argv.append(args); return 0, json.dumps(result).encode()
            def _run(self, host, args, budget=131072):
                outer.assertEqual(host, "crustacea.bajaj.com")
                if args[0] == "/usr/sbin/runuser":
                    outer.assertEqual(budget, 1048576)
                    self.plugins += 1
                    if fail_plugin and self.plugins == 2: return 1, b"dummy failure"
                    if plugin_drift:
                        value = json.loads(plugin_discovery_payload())
                        if self.plugins == 2:
                            value["plugins"][0]["dependencyStatus"]["missing"] = ["fixture-missing-dependency"]
                        return 0, plugin_discovery_payload(value=value)
                    return 0, json.dumps(plugin_fixture()).encode()
                outer.assertEqual(budget, 131072)
                if args[0] == "/usr/bin/systemctl": return 0, ("\n".join(k+"="+v for k,v in frame.n.state().items())+"\n").encode()
                if args[0] == "/bin/bash": frame.n.verify(); return 0, b"verified"
                outer.assertEqual(args[0], "/usr/bin/curl"); return 0, b"200"
        fleet = Fleet()
        def run(args):
            if args[0] == "/usr/bin/systemctl": return ("\n".join(k+"="+v for k,v in frame.n.state().items())+"\n").encode()
            self.assertEqual(args, ["/bin/bash", str(frame.packet/"verify-all.sh")]); frame.n.verify(); return b"verified"
        def mutate(args):
            self.assertEqual(args[0], "/usr/bin/systemctl"); (frame.n.stop if args[1] == "stop" else frame.n.start)()
        original_digest = c.digest
        def digest(path):
            return phase.VERIFIER_SHA if str(path) == "/usr/local/lib/openclaw-py/verify-all.sh" else original_digest(path)
        with mock.patch.object(phase.d, "Layout", side_effect=layout), mock.patch.object(c, "Native", return_value=fleet), \
             mock.patch.object(c, "bindings", return_value=b), mock.patch.object(c, "digest", side_effect=digest), \
             mock.patch.object(c, "core_inputs", side_effect=lambda root, b: (phase, *phase.load_inputs(frame.inputs))), \
             mock.patch.object(phase.OwnerNative, "run", side_effect=run), mock.patch.object(phase.OwnerNative, "mutate", side_effect=mutate), \
             mock.patch.object(phase, "execute", side_effect=execute), mock.patch.object(phase.os, "geteuid", return_value=0), \
             mock.patch.object(phase.os, "open", side_effect=fixture_open), contextlib.redirect_stdout(io.StringIO()) as out:
            def invoke(mode, backup=None):
                argv = c.owner_argv("crustacea", mode, stages(), {}, backup, b)[3:]
                argv[argv.index("--inputs") + 1] = str(frame.inputs)
                argv[argv.index("--settings") + 1] = str(settings)
                self.assertEqual(c.main(argv), 1 if (fail_plugin or plugin_drift) and mode == "install" else 0, out.getvalue())
                return json.loads(out.getvalue().splitlines()[-1])
            applied = invoke("install"); frame.ledger.write_bytes(b"new accrued state")
            if fail_plugin or plugin_drift:
                self.assertEqual(applied["status"], "captured_install_failed")
                self.assertEqual(applied["primary_error"], "owner_plugin_controls_projection_changed" if plugin_drift
                                 else "native_plugin_semantic_observation_failed")
                self.assertEqual(applied["rollback_status"], "captured_rollback_passed")
            backup = {"path": applied["snapshot"], "manifest_sha256": applied["snapshot_sha256"]}
            invoke("rollback", backup); invoke("rollback", backup)
        frame.assert_before()
        self.assertEqual(frame.ledger.read_bytes(), b"new accrued state")
        self.assertEqual(frame.control.read_bytes(), b"same configured model")
        self.assertGreater(len(fleet.argv), 0)

    def test_core_actual_owner_cli_captured_apply_rollback_repeat(self):
        self.core_actual_owner_cli()

    def test_core_actual_poststart_callback_failure_journals_and_restores(self):
        self.core_actual_owner_cli(fail_plugin=True)

    def test_core_actual_large_plugin_drift_rejects_and_repeat_rollback_preserves_state(self):
        self.core_actual_owner_cli(plugin_drift=True)

    def test_rita_actual_argparse_all_modes(self):
        path=HERE/"rita-producer/promote-producer.py"
        self.assertEqual(c.digest(path),B["components"]["rita"]["helper_sha"])
        hashes={k:"0"*64 for k in B["components"]["rita"]["after"]}
        check=c.owner_argv("rita","check",stages(),hashes,None,B)
        apply=c.owner_argv("rita","install",stages(),hashes,None,B)
        self.assertEqual(apply,check+["--apply"])
        self.assertEqual(check[check.index("--expected-unit")+1],B["unit"]["sha256"])
        self.assertEqual(check[check.index("--expected-environment")+1],B["components"]["rita"]["environment_sha"])
        self.assertEqual(check[check.index("--expected-binary")+1],"0"*64)
        with self.assertRaisesRegex(c.Stop,"automatic_older_reader_rollback_forbidden"):
            c.owner_argv("rita","rollback",stages(),hashes,None,B)

    def test_ava_actual_cli_current_oneguard_apply_and_rollback(self):
        helper=AVA_PACKAGE/"ava"/B["components"]["ava"]["helper"]
        self.assertEqual(c.digest(helper),B["components"]["ava"]["helper_sha"])
        t_path=helper.with_name("test-deploy-ava-prior-message-reference.py")
        spec=importlib.util.spec_from_file_location("qualified_ava_fixtures",t_path)
        t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
        original_temp=tempfile.TemporaryDirectory
        with mock.patch.object(t.tempfile,"TemporaryDirectory",side_effect=lambda **kw:original_temp(dir=HERE.parent,**kw)):
            frame=t.TransactionTests("test_check_only_nonactuating");frame.setUp()
        self.addCleanup(frame.doCleanups)
        d=t.deploy
        old_apply,old_restore,old_check=d.apply,d.rollback,d.check
        fixture_euid=os.geteuid
        def fixture_operation(operation,*args):
            with mock.patch.object(d.os,"geteuid",fixture_euid):
                return operation(*args)
        b=copy.deepcopy(B);b["components"]["ava"]["backup_base"]=str(frame.backups)
        native_stage={"ava":AVA_PACKAGE/"ava"}
        chosen=frame.backups/"runtime-chosen-once"
        with mock.patch.object(d,"Native",return_value=frame.native),mock.patch.object(d.os,"geteuid",return_value=0),\
             mock.patch.object(d,"with_lock",side_effect=lambda fn:fn()),\
             mock.patch.object(d,"apply",side_effect=lambda native,backup=None:fixture_operation(old_apply,native,frame.root,frame.candidate,frame.backups,backup)),\
             mock.patch.object(d,"rollback",side_effect=lambda native,backup:fixture_operation(old_restore,native,backup,frame.root,frame.backups)),\
             mock.patch.object(d,"check",side_effect=lambda native,root=frame.root,candidate=frame.candidate:fixture_operation(old_check,native,root,candidate)),\
             contextlib.redirect_stdout(io.StringIO()) as captured:
            check=c.owner_argv("ava","check",native_stage,{},None,b)
            self.assertEqual(d.main(check[3:]),0);self.assertNotIn("stop",frame.native.events)
            apply=c.owner_argv("ava","install",native_stage,{},str(chosen),b)
            self.assertEqual(d.main(apply[3:]),0,captured.getvalue());self.assertTrue(chosen.is_dir())
            self.assertEqual(set(d.identities(frame.root)),set(d.TARGETS))
            frame.native.database += b"newly_accrued_state"
            current_database=frame.native.database
            rollback=c.owner_argv("ava","rollback",native_stage,{},str(chosen),b)
            self.assertEqual(d.main(rollback[3:]),0)
            self.assertEqual(d.main(rollback[3:]),0)
            frame.assert_original()
            self.assertEqual(frame.native.database,current_database)
            self.assertEqual(d.TARGETS,("core/pipeline_message_deposit.py", "engine.py"))
            self.assertEqual(B["components"]["ava"]["runtime"],"27b936e93b61b35981a411eaede2fc4e42e461e7")
            self.assertEqual(d.main(["--check-only","--backup",str(chosen)]),1)

    def test_rita_actual_pair_restore_preserves_unit_config_and_new_ledger(self):
        result=c.verify_package("rita",RITA_PACKAGE,B)
        self.assertEqual(result["status"],"verified_current_owner_packet_retention_only")
        self.assertEqual(result["source"],"6b0efd9a6ed9d702fcc5eb8901b76fbae74fa6d4")
        self.assertEqual(result["kit_files"],115)
        self.assertEqual(result["skeleton_files"],115)
        self.assertTrue(result["skeleton_equal"])
        self.assertFalse(result["historical_skeleton_is_not_current_ordinary_kit"])
        config = B["components"]["rita"]["current_config_capture"]
        capture = RITA_PACKAGE / "rita/private/private-native-current.tar.gz"
        self.assertEqual(c.digest(capture), config["archive_sha256"])
        self.assertEqual(c.native_capture_rows(capture), {k: tuple(v) for k, v in config["members"].items()})


class ExternalFoundationRetention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vip-external-fixture-", dir=HERE.parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.b = copy.deepcopy(B)
        self.b["external_foundations"] = {}
        self.roots = {}

    def packet(self, name="fixture", members=None, sidecar=False):
        root = self.root / name
        root.mkdir()
        members = members or {"data.bin": b"bounded fixture bytes"}
        for path, data in members.items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        manifest = root / "SHA256SUMS"
        manifest.write_text("".join(hashlib.sha256(data).hexdigest() + "  " + path + "\n"
                                    for path, data in sorted(members.items())))
        s = {"kind": "sha_manifest", "manifest": manifest.name, "manifest_sha256": c.digest(manifest),
             "entries": len(members), "acquisition": "Documents/Projects/fixture/" + name,
             "role": "fixture retained input", "sidecars": [], "fresh_host_restore": "owner procedure still required"}
        if sidecar:
            side = self.root / (name + "-sidecar")
            side.mkdir()
            p = side / "AMENDMENT.txt"
            p.write_bytes(b"separate immutable amendment")
            self.roots[name + "-sidecar"] = side
            s["sidecars"] = [{"root_key": name + "-sidecar", "path": p.name, "sha256": c.digest(p),
                              "acquisition": "Documents/Projects/fixture/AMENDMENT.txt"}]
        self.b["external_foundations"][name] = s
        self.roots[name] = root
        return root, s

    def set_manifest(self, root, s, text):
        p = root / s["manifest"]
        p.write_text(text)
        s["manifest_sha256"] = c.digest(p)

    def native_packet(self):
        root = self.root / "avr-foundation"
        root.mkdir()
        archive = root / "capture.tar.gz"
        archive.write_bytes(b"opaque private archive fixture; never extracted")
        row = {"sha256": "a" * 64, "size": 10, "mode": 0o640, "uid": 0, "gid": 1001}
        value = {"schema": "avr-foundation-private-amendment-v1", "files": {"etc/example.env": row},
                 "archive_sha256": c.digest(archive)}
        inventory = root / "NATIVE-INPUT-INVENTORY.json"
        inventory.write_text(json.dumps(value))
        s = {"kind": "native_inventory", "inventory": inventory.name, "inventory_sha256": c.digest(inventory),
             "inventory_schema": value["schema"], "archive": archive.name, "archive_sha256": c.digest(archive),
             "entries": 1, "acquisition": "Documents/Projects/fixture/avr", "role": "private capture",
             "sidecars": [], "fresh_host_restore": "native metadata retained, no routine config restore"}
        self.b["external_foundations"]["avr-foundation"] = s
        self.roots["avr-foundation"] = root
        return root, s, value

    def test_valid_packet_and_amendment_are_retention_not_restore(self):
        self.packet(sidecar=True)
        result = c.verify_external_foundation("fixture", self.roots, self.b)
        self.assertEqual(result["status"], "verified_retention_only")
        self.assertEqual(len(result["sidecars"]), 1)
        for key in ("restore_executed", "archive_extracted_or_links_dereferenced",
                    "ordinary_rollback_restores_input", "native_or_human_acceptance"):
            self.assertIs(result[key], False)

    def test_external_roots_are_separate_from_component_roots(self):
        self.packet(sidecar=True)
        p = self.root / "external.json"
        p.write_text(json.dumps({k: str(v) for k, v in self.roots.items()}))
        self.assertEqual(c.read_external_roots(p, self.b), self.roots)
        with self.assertRaisesRegex(c.Stop, "roots_schema"):
            c.read_roots(p, self.b)
        p.write_text(json.dumps({"unregistered-root": str(self.root)}))
        with self.assertRaisesRegex(c.Stop, "external_roots_schema"):
            c.read_external_roots(p, self.b)

    def test_missing_root_is_explicit(self):
        self.packet()
        result = c.external_foundation_rows({}, self.b)
        self.assertEqual(result[0]["reason"], "external_root_missing")
        self.assertIs(result[0]["restore_executed"], False)

    def test_missing_manifest_rejected(self):
        root, s = self.packet()
        (root / s["manifest"]).unlink()
        with self.assertRaisesRegex(c.Stop, "external_manifest_missing"):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_manifest_tamper_rejected(self):
        root, s = self.packet()
        (root / s["manifest"]).write_bytes(b"tamper")
        with self.assertRaisesRegex(c.Stop, "external_manifest_hash_mismatch"):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_missing_or_wrong_member_rejected(self):
        root, _ = self.packet()
        p = root / "data.bin"
        p.write_bytes(b"wrong bytes")
        with self.assertRaisesRegex(c.Stop, "external_manifest_member_hash_mismatch"):
            c.verify_external_foundation("fixture", self.roots, self.b)
        p.unlink()
        with self.assertRaisesRegex(c.Stop, "external_manifest_member_missing"):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_count_mismatch_rejected(self):
        _, s = self.packet()
        s["entries"] = 2
        with self.assertRaisesRegex(c.Stop, "external_manifest_count_mismatch"):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_pinned_external_manifest_preserves_original_order_only(self):
        root, s = self.packet(members={"a.bin": b"a", "z.bin": b"z"})
        p = root / s["manifest"]
        original = "\n".join(reversed(p.read_text().splitlines())) + "\n"
        self.set_manifest(root, s, original)
        with self.assertRaisesRegex(c.Stop, "manifest_not_sorted"):
            c.sha_manifest(p.read_bytes())
        result = c.verify_external_foundation("fixture", self.roots, self.b)
        self.assertEqual(result["entries"], 2)
        self.assertEqual(p.read_text(), original)

    def test_manifest_escape_duplicate_and_alias_rejected(self):
        root, s = self.packet()
        cases = [("../outside", "path_rejected"), ("/absolute", "path_rejected"),
                 ("data.bin\n" + "a" * 64 + "  data.bin", "manifest_duplicate"),
                 ("nested//data.bin", "external_path_not_canonical")]
        for path, code in cases:
            with self.subTest(path=path):
                self.set_manifest(root, s, "a" * 64 + "  " + path + "\n")
                with self.assertRaisesRegex(c.Stop, code):
                    c.verify_external_foundation("fixture", self.roots, self.b)

    def test_sidecar_missing_or_drift_rejected(self):
        _, s = self.packet(sidecar=True)
        p = self.roots["fixture-sidecar"] / s["sidecars"][0]["path"]
        p.write_bytes(b"drift")
        with self.assertRaisesRegex(c.Stop, "external_sidecar_hash_mismatch"):
            c.verify_external_foundation("fixture", self.roots, self.b)
        p.unlink()
        with self.assertRaisesRegex(c.Stop, "external_sidecar_missing"):
            c.verify_external_foundation("fixture", self.roots, self.b)
        self.roots.pop("fixture-sidecar")
        with self.assertRaisesRegex(c.Stop, "external_sidecar_root_missing"):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_sidecar_escape_rejected(self):
        _, s = self.packet(sidecar=True)
        s["sidecars"][0]["path"] = "../escape.txt"
        with self.assertRaises(c.Stop):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_symlink_member_or_root_not_dereferenced(self):
        root, _ = self.packet()
        p = root / "data.bin"
        p.unlink()
        p.symlink_to("/must-not-read")
        with self.assertRaises(c.Stop):
            c.verify_external_foundation("fixture", self.roots, self.b)
        alias = self.root / "alias"
        alias.symlink_to(root, target_is_directory=True)
        self.roots["fixture"] = alias
        with self.assertRaisesRegex(c.Stop, "external_root_missing_or_symlink"):
            c.verify_external_foundation("fixture", self.roots, self.b)

    def test_matrix_archive_links_are_only_raw_hashed(self):
        root = self.root / "matrix"
        root.mkdir()
        archive = root / "generation.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            link = tarfile.TarInfo("matrix/must-not-follow")
            link.type = tarfile.SYMTYPE
            link.linkname = "/must-not-read"
            tar.addfile(link)
        members = {archive.name: archive.read_bytes(), "before.jsonl": b"link inventory\n",
                   "after.jsonl": b"link inventory\n", "extracted.jsonl": b"link inventory\n"}
        archive_bytes = archive.read_bytes()
        archive.unlink()
        root.rmdir()
        self.packet("matrix", members)
        with mock.patch.object(c, "archive_rows", side_effect=AssertionError("no regular-only tar parser")), \
             mock.patch.object(tarfile, "open", side_effect=AssertionError("no archive extraction")):
            result = c.verify_external_foundation("matrix", self.roots, self.b)
        self.assertEqual(result["entries"], 4)
        self.assertIs(result["archive_extracted_or_links_dereferenced"], False)
        self.assertEqual(archive_bytes, (root / "generation.tar.gz").read_bytes())

    def test_native_inventory_metadata_and_archive_pin_verified(self):
        _, _, _ = self.native_packet()
        result = c.verify_external_foundation("avr-foundation", self.roots, self.b)
        self.assertEqual(result["entries"], 1)
        self.assertIs(result["ordinary_rollback_restores_input"], False)

    def test_native_inventory_boolean_metadata_rejected(self):
        root, s, value = self.native_packet()
        for key in ("mode", "size", "uid", "gid"):
            with self.subTest(key=key):
                altered = copy.deepcopy(value)
                altered["files"]["etc/example.env"][key] = False
                p = root / s["inventory"]
                p.write_text(json.dumps(altered))
                s["inventory_sha256"] = c.digest(p)
                with self.assertRaisesRegex(c.Stop, "external_inventory_metadata"):
                    c.verify_external_foundation("avr-foundation", self.roots, self.b)

    def test_native_inventory_duplicate_paths_rejected(self):
        root, s, value = self.native_packet()
        row = json.dumps(value["files"]["etc/example.env"])
        text = '{"schema":"avr-foundation-private-amendment-v1","files":{"same":' + row + ',"same":' + row + '}}'
        p = root / s["inventory"]
        p.write_text(text)
        s["inventory_sha256"] = c.digest(p)
        with self.assertRaisesRegex(c.Stop, "external_inventory_duplicate"):
            c.verify_external_foundation("avr-foundation", self.roots, self.b)

    def test_native_inventory_escape_rejected(self):
        root, s, value = self.native_packet()
        value["files"] = {"../escape": value["files"]["etc/example.env"]}
        p = root / s["inventory"]
        p.write_text(json.dumps(value))
        s["inventory_sha256"] = c.digest(p)
        with self.assertRaisesRegex(c.Stop, "path_rejected"):
            c.verify_external_foundation("avr-foundation", self.roots, self.b)

    def test_native_inventory_nonobject_is_coded(self):
        root, s, _ = self.native_packet()
        p = root / s["inventory"]
        p.write_text("[]")
        s["inventory_sha256"] = c.digest(p)
        rows = c.external_foundation_rows(self.roots, self.b)
        self.assertEqual(rows[0]["reason"], "external_inventory_schema")

    def test_native_archive_or_inventory_pin_drift_rejected(self):
        root, s, value = self.native_packet()
        p = root / s["archive"]
        p.write_bytes(b"changed archive")
        with self.assertRaisesRegex(c.Stop, "external_archive_hash_mismatch"):
            c.verify_external_foundation("avr-foundation", self.roots, self.b)
        value["archive_sha256"] = "b" * 64
        p = root / s["inventory"]
        p.write_text(json.dumps(value))
        s["inventory_sha256"] = c.digest(p)
        with self.assertRaisesRegex(c.Stop, "external_inventory_archive_pin"):
            c.verify_external_foundation("avr-foundation", self.roots, self.b)

    def cli(self, mode="verify", component="all", supply=True):
        roots = self.root / "component-roots.json"
        roots.write_text("{}")
        external = self.root / "external-roots.json"
        external.write_text(json.dumps({k: str(v) for k, v in self.roots.items()}))
        args = [mode, "--roots", str(roots), "--component", component]
        if supply:
            args += ["--external-roots", str(external)]
        out = io.StringIO()
        with mock.patch.object(c, "bindings", return_value=self.b), \
             mock.patch.object(c, "verify_package", return_value={"status": "verified_offline"}), \
             mock.patch.object(c, "Native", side_effect=AssertionError("no native transport")), \
             contextlib.redirect_stdout(out):
            rc = c.main(args)
        return rc, json.loads(out.getvalue())

    def test_verify_invalid_foundation_nonzero(self):
        root, _ = self.packet(sidecar=True)
        (root / "data.bin").write_bytes(b"tamper")
        rc, result = self.cli()
        self.assertNotEqual(rc, 0)
        self.assertEqual(result["external_foundations"][0]["reason"], "external_manifest_member_hash_mismatch")

    def test_default_all_missing_roots_visibly_incomplete(self):
        self.b = copy.deepcopy(B)
        rc, result = self.cli(supply=False)
        self.assertNotEqual(rc, 0)
        self.assertEqual(len(result["external_foundations"]), len(self.b["external_foundations"]))
        self.assertEqual({row["foundation"] for row in result["external_foundations"]},
                         set(self.b["external_foundations"]))
        self.assertTrue(all(row["reason"] == "external_root_missing" for row in result["external_foundations"]))
        self.assertTrue(result["whole_assembly_status"].startswith("INCOMPLETE"))

    def test_plans_missing_or_invalid_foundation_nonzero_no_restore(self):
        root, _ = self.packet()
        for mode in ("install-plan", "rollback-plan"):
            for supply in (False, True):
                with self.subTest(mode=mode, supply=supply):
                    (root / "data.bin").write_bytes(b"changed")
                    rc, result = self.cli(mode=mode, supply=supply)
                    self.assertNotEqual(rc, 0)
                    self.assertIs(result["dry_run"], True)
                    self.assertIs(result["external_foundations"][0]["restore_executed"], False)
                    self.assertTrue(result["whole_assembly_status"].startswith("INCOMPLETE"))

    def test_component_only_verify_does_not_claim_external_restore(self):
        self.packet()
        rc, result = self.cli(component="rita", supply=False)
        self.assertEqual(rc, 0)
        self.assertNotIn("external_foundations", result)
        self.assertTrue(result["whole_assembly_status"].startswith("INCOMPLETE"))

    def test_retained_external_roots_do_not_clear_fresh_host_gaps(self):
        self.packet()
        rc, result = self.cli()
        self.assertEqual(rc, 0)
        self.assertTrue(result["whole_assembly_status"].startswith("INCOMPLETE"))
        self.assertIs(result["external_foundations"][0]["native_or_human_acceptance"], False)

    def test_native_dispatch_and_control_code_equal_frozen_r8(self):
        before = subprocess.check_output(["git", "show", "f36d0bee5f1f873fc9b5234742abdb0c79ca328a:deployment/recovery-coordinator.py"], cwd=HERE.parent)
        after = (HERE / "recovery-coordinator.py").read_bytes()
        def nodes(data):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(data).body
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        old, new = nodes(before), nodes(after)
        for name in ("Native", "CoreOwnerGates", "owner_core_main",
                     "rollback_expected", "protected_snapshot", "scoped_backup", "write_receipt"):
            with self.subTest(name=name):
                self.assertEqual(old[name], new[name])
        old_bindings = json.loads(subprocess.check_output(["git", "show", "f36d0bee5f1f873fc9b5234742abdb0c79ca328a:component-bindings-20260914.json"], cwd=HERE.parent))
        for name in ("actors", "unit", "custom_sha256"):
            self.assertEqual(old_bindings[name], B[name])
        self.assertEqual(B["order"], ["tessa", "rita", "ava", "voice-organ", "crustacea"])


if __name__=="__main__":
    unittest.main(verbosity=2)
