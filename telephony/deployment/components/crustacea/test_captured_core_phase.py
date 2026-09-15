#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
"""Dummy files and native state only; no service, npm, model, or network operations."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("captured",HERE/"captured-core-phase.py")
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
d=c.d


class FakeNative:
    def __init__(self,layout):
        self.layout=layout;self.events=[];self.active=True;self.job=0;self.calls=0
        self.stop_hook=None;self.start_hook=None;self.ready_error=False
    def state(self):
        self.events.append("state");d.require(self.job==0,"pending_native_job")
        return {"Job":"0","MainPID":"19" if self.active else "0",
                "ActiveState":"active" if self.active else "inactive","SubState":"running" if self.active else "dead"}
    def zero(self):
        self.events.append("zero");d.require(type(self.calls) is int and self.calls==0,"not_idle")
    def verify(self):self.events.append("verify")
    def ready(self):
        self.events.append("ready");d.require(not self.ready_error,"runtime_readiness_unavailable")
    def stop(self):
        self.events.append("stop");self.active=False
        if self.stop_hook:self.stop_hook()
    def start(self):
        self.events.append("start");self.active=True
        if self.start_hook:self.start_hook()


class CapturedPhase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="captured-core-fixture-",dir=HERE.parent)
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.layout=d.Layout();self.layout.core=self.root/"usr/lib/node_modules/openclaw"
        self.layout.core.mkdir(parents=True);self.layout.core.chmod(0o755)
        self.layout.entrypoint=self.root/"usr/bin/openclaw";self.layout.entrypoint.parent.mkdir(parents=True)
        self.layout.entrypoint.symlink_to("../lib/node_modules/openclaw/openclaw.mjs")
        self.layout.workspace=self.root/"workspace";self.layout.backups=self.root
        self.layout.workspace.mkdir()
        self.entry=self.layout.core/"openclaw.mjs";self.entry.write_bytes(b"before core")
        self.entry.chmod(0o755)
        deps=self.layout.core/"node_modules/test";deps.mkdir(parents=True)
        (deps/"dependency.js").write_bytes(b"exact captured dependency")
        (self.layout.core/"node_modules/dependency-link").symlink_to("test/dependency.js")
        self.skill=self.layout.workspace/"skills/avril-call/client.js"
        self.skill.parent.mkdir(parents=True);self.skill.write_bytes(b"before client");self.skill.chmod(0o664)
        self.control=self.root/"openclaw.json";self.control.write_bytes(b"same configured model")
        self.ledger=self.root/"agent.sqlite";self.ledger.write_bytes(b"live WAL-backed state")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(d,"PROTECTED",(str(self.control),)).start()
        self.packet=self.root/"packet";self.packet.mkdir()
        self.closure=self.root/"owner-closure";self.closure.mkdir()
        self.expected_current=c.body_hash(c.inventory(self.layout))
        self.archive=self.closure/"core.tar.gz"
        self.make_archive()
        self.records=self.archive_records()
        (self.closure/"manifest.json").write_text(json.dumps({"schema":"crustacea-installed-closure-archive-v1","records":self.records}))
        self.rows=c.validate_records(self.records)
        self.m={"schema":c.SCHEMA,"base_source":"bdd99b1827360ce72d00b8d30bc0acc346cb27af",
                "closure":{"root":str(self.closure),"archive":self.archive.name,"archive_sha256":d.digest(self.archive),
                           "manifest":"manifest.json","manifest_sha256":d.digest(self.closure/"manifest.json"),"receipt":"receipt.json"},
                "expected_current_sha256":self.expected_current,"protected":{str(self.control):d.digest(self.control)},
                "patchers":[],"patch_targets":{},"workspace":[]}
        receipt={"schema":"crustacea-installed-closure-receipt-v1","archive":{"sha256":d.digest(self.archive)},
                 "inventories":{"archiveManifestSha256":d.digest(self.closure/"manifest.json"),"archiveMatchesDisk":True,"byteEqual":True},
                 "serviceUnchanged":True,"scope":"dummy fixture, not native loaded proof"}
        (self.closure/"receipt.json").write_text(json.dumps(receipt));self.m["closure"]["receipt_sha256"]=d.digest(self.closure/"receipt.json")
        for prefix in ("session-ingestion","dreaming-phases","dreaming-narrative"):
            self.m["patch_targets"][prefix]=c.ROOT+"/dist/"+prefix+"-fixture.js"
        for name in c.PATCHERS:
            p=self.packet/name;p.write_bytes(b"# fixture no-op retained-patcher stand-in\n")
            self.m["patchers"].append({"name":name,"source":name,"sha256":d.digest(p)})
        checker=self.packet/"accepted-owner-check.sh";checker.write_bytes(b"exit 0\n")
        for key in ("zero_checker","ready_checker"):
            self.m[key]={"path":checker.name,"sha256":d.digest(checker),"runner":"sh","args":["--check-only"]}
        verifier=self.packet/"verify-all.sh";verifier.write_bytes(b"exit 0\n")
        self.m["retention_verifier_sha256"]=d.digest(verifier)
        # Stand-ins are explicit and cannot become a native owner packet.
        mock.patch.object(c,"PATCH_SHA",{p["name"]:p["sha256"] for p in self.m["patchers"]}).start()
        mock.patch.object(c,"VERIFIER_SHA",self.m["retention_verifier_sha256"]).start()
        source=self.packet/"client.js";source.write_bytes(b"after client")
        self.m["workspace"]=[{"target":"skills/avril-call/client.js","source":source.name,"sha256":d.digest(source),"before_sha256":d.digest(self.skill)}]
        self.inputs=self.packet/"INPUTS.json";self.save()
        self.n=FakeNative(self.layout)
    def save(self):self.inputs.write_text(json.dumps(self.m))
    def native_contract(self):
        self.m.pop("zero_checker"); self.m.pop("ready_checker")
        self.m["native_gate_contract"] = {"kind":"vip-owner-native-v1", "owner_receipt_sha256":"1a0e7d55123e0da725e27716ed13e44969a6404c6cf001bf5c5b0987524c16f2"}
        self.save()
    def test_owner_native_packet_requires_no_checker_executables(self):
        self.native_contract()
        with mock.patch.object(c,"Native",side_effect=AssertionError("native forbidden")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(["verify","--inputs",str(self.inputs)]),0)
        root,m,rows=c.load_inputs(self.inputs)
        self.assertNotIn("zero_checker",m); self.assertNotIn("ready_checker",m)
    def test_owner_native_missing_or_untyped_callbacks_fail_before_mutation(self):
        self.native_contract()
        with mock.patch.object(c.os,"geteuid",return_value=0), mock.patch.object(c.os,"open",side_effect=AssertionError("no lock/mutation")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(["apply","--inputs",str(self.inputs)]),2)
        with self.assertRaises(d.Stop): c.OwnerNative(self.packet,self.m,object())
        self.assert_before()
    def test_real_owner_native_callbacks_apply_restore_and_preserve_projection(self):
        self.native_contract()
        outer=self
        class Gates:
            def zero(self):outer.n.zero()
            def ready(self):outer.n.ready()
            def preservation(self):return {"plugins":{"dummy":"persisted"},"controls":c.metadata(outer.control)}
        native=c.OwnerNative(self.packet,self.m,Gates())
        def run(argv):
            if argv[0]=="/usr/bin/systemctl":return ("\n".join(k+"="+v for k,v in self.n.state().items())+"\n").encode()
            self.assertEqual(argv,["/bin/bash",str(self.packet/"verify-all.sh")]);self.n.verify();return b"verified"
        def mutate(argv):
            self.assertEqual(argv[0],"/usr/bin/systemctl")
            (self.n.stop if argv[1]=="stop" else self.n.start)()
        root,m,rows=c.load_inputs(self.inputs)
        with mock.patch.object(native,"run",side_effect=run),mock.patch.object(native,"mutate",side_effect=mutate):
            applied=c.execute("apply",root,m,rows,native,self.layout)
            self.assertEqual(applied["status"],"captured_install_passed")
            self.ledger.write_bytes(b"new accrued state")
            restored=c.execute("rollback",root,m,rows,native,self.layout,applied["snapshot"],applied["snapshot_sha256"])
            self.assertEqual(restored["status"],"captured_rollback_passed")
            again=c.execute("rollback",root,m,rows,native,self.layout,applied["snapshot"],applied["snapshot_sha256"])
            self.assertEqual(again["status"],"captured_rollback_already_restored")
        self.assert_before();self.assertEqual(self.ledger.read_bytes(),b"new accrued state")
        self.assertIn("ready",self.n.events)
    def test_owner_native_changed_plugin_projection_never_passes(self):
        native=c.OwnerNative(self.packet,self.m,mock.Mock())
        native.gates.preservation.side_effect=[{"plugins":"before"},{"plugins":"foreign"}]
        native.owner_capture()
        with self.assertRaisesRegex(d.Stop,"projection_changed"):native.ready()
    def make_archive(self):
        uid=os.geteuid();gid=os.getgid()
        rows={
            c.ROOT:("directory",None,0o755),
            c.ROOT+"/openclaw.mjs":("file",b"after core",0o755),
            c.ROOT+"/node_modules":("directory",None,0o755),
            c.ROOT+"/node_modules/test":("directory",None,0o755),
            c.ROOT+"/node_modules/test/dependency.js":("file",b"after exact dependency",0o644),
            c.ROOT+"/node_modules/dependency-link":("symlink","test/dependency.js",0o777),
            c.ROOT+"/dist":("directory",None,0o755),
            c.LINK:("symlink","../lib/node_modules/openclaw/openclaw.mjs",0o777)}
        for prefix in ("session-ingestion","dreaming-phases","dreaming-narrative"):
            rows[c.ROOT+"/dist/"+prefix+"-fixture.js"]=("file",b"dummy patched chunk",0o644)
        with tarfile.open(self.archive,"w:gz") as archive:
            for name,(kind,value,mode) in sorted(rows.items()):
                info=tarfile.TarInfo(name.removeprefix("/"));info.uid=uid;info.gid=gid;info.mode=mode;info.mtime=1
                if kind=="directory":info.type=tarfile.DIRTYPE
                elif kind=="symlink":info.type=tarfile.SYMTYPE;info.linkname=value
                else:info.size=len(value)
                archive.addfile(info,io.BytesIO(value) if kind=="file" else None)
    def archive_records(self):
        result=[]
        with tarfile.open(self.archive,"r:gz") as archive:
            for member in archive:
                row={"path":"/"+member.name,"mode":member.mode,"uid":member.uid,"gid":member.gid,
                     "type":"file" if member.isfile() else "directory" if member.isdir() else "symlink"}
                if member.isfile():row.update(size=member.size,sha256=hashlib.sha256(archive.extractfile(member).read()).hexdigest())
                if member.issym():row["target"]=member.linkname
                result.append(row)
        return result
    def apply(self):
        root,m,rows=c.load_inputs(self.inputs);return c.execute("apply",root,m,rows,self.n,self.layout)
    def rollback(self,result):
        root,m,rows=c.load_inputs(self.inputs)
        return c.execute("rollback",root,m,rows,self.n,self.layout,result["snapshot"],result["snapshot_sha256"])
    def assert_before(self):
        self.assertEqual(self.entry.read_bytes(),b"before core")
        self.assertEqual((self.layout.core/"node_modules/test/dependency.js").read_bytes(),b"exact captured dependency")
        self.assertEqual(self.skill.read_bytes(),b"before client")
        self.assertEqual(self.skill.stat().st_mode&0o777,0o664)
        self.assertEqual(os.readlink(self.layout.entrypoint),"../lib/node_modules/openclaw/openclaw.mjs")
    def test_offline_verification_no_native_or_npm(self):
        with mock.patch.object(c,"Native",side_effect=AssertionError("native forbidden")):
            self.assertEqual(c.main(["verify","--inputs",str(self.inputs)]),0)
    def test_exact_dependencies_launcher_metadata_and_repeat_rollback_preserve_new_state(self):
        original_link=c.metadata(self.layout.entrypoint,True)
        result=self.apply();self.assertEqual(result["status"],"captured_install_passed")
        self.assertEqual(self.entry.read_bytes(),b"after core")
        self.assertEqual(c.metadata(self.layout.entrypoint,True),original_link)
        self.ledger.write_bytes(b"new accrued state");self.n.events=[]
        rolled=self.rollback(result);self.assertEqual(rolled["status"],"captured_rollback_passed");self.assert_before()
        self.assertEqual(self.ledger.read_bytes(),b"new accrued state");self.assertEqual(self.control.read_bytes(),b"same configured model")
        self.n.events=[]
        self.assertEqual(self.rollback(result)["status"],"captured_rollback_already_restored")
        self.assertNotIn("stop",self.n.events);self.assertNotIn("start",self.n.events)
    def test_same_or_different_content_foreign_inode_during_stop_never_overwritten(self):
        for same in (True,False):
            with self.subTest(same=same):
                data=self.entry.read_bytes() if same else b"foreign"
                def drift():
                    p=self.entry.with_name("foreign");p.write_bytes(data);p.chmod(0o755);os.replace(p,self.entry)
                self.n.stop_hook=drift
                result=self.apply();self.assertEqual(result["rollback_status"],"deferred_no_retry")
                self.assertEqual(self.entry.read_bytes(),data);self.assertEqual(self.n.events.count("stop"),1)
                self.assertNotIn("start",self.n.events)
                self.n.events=[];self.n.stop_hook=None;self.n.active=True
                self.entry.write_bytes(b"before core");self.m["expected_current_sha256"]=c.body_hash(c.inventory(self.layout));self.save()
    def test_config_drift_during_stop_no_second_service_action(self):
        self.n.stop_hook=lambda:self.control.write_bytes(b"operator changed config")
        result=self.apply()
        self.assertEqual(result["rollback_status"],"deferred_no_retry");self.assertEqual(self.entry.read_bytes(),b"before core")
        self.assertEqual(self.n.events.count("stop"),1);self.assertNotIn("start",self.n.events)
    def test_pending_systemd_job_after_timeout_no_concurrent_recovery(self):
        def timeout():
            self.n.job=71
            raise subprocess.TimeoutExpired("systemctl observation",45)
        self.n.stop_hook=timeout
        result=self.apply();self.assertEqual(result["rollback_status"],"deferred_no_retry")
        self.assertEqual(self.n.events.count("stop"),1);self.assertNotIn("start",self.n.events);self.assert_before()
    def test_bool_or_nonzero_calls_no_capture_or_stop(self):
        for value in (False,1):
            with self.subTest(value=value):
                self.n.calls=value
                with self.assertRaises(d.Stop):self.apply()
                self.assertNotIn("stop",self.n.events)
    def test_wrong_manifest_archive_or_receipt_fails_before_native(self):
        for key in ("archive_sha256","manifest_sha256","receipt_sha256"):
            with self.subTest(key=key):
                old=self.m["closure"][key];self.m["closure"][key]="f"*64;self.save()
                with self.assertRaises(d.Stop):c.load_inputs(self.inputs)
                self.m["closure"][key]=old
    def test_reordered_extra_or_wrong_patcher_fails_closed(self):
        old=list(self.m["patchers"]);self.m["patchers"].reverse();self.save()
        with self.assertRaises(d.Stop):c.load_inputs(self.inputs)
        self.m["patchers"]=old;self.m["patchers"][0]["sha256"]="0"*64;self.save()
        with self.assertRaises(d.Stop):c.load_inputs(self.inputs)
    def test_static_or_whole_state_rewind_payload_rejected(self):
        for name in ("Documents/Notes/TASKS.md","agents/aimee-voice/store.sqlite","skills/new.db"):
            with self.subTest(name=name):
                self.m["workspace"][0]["target"]=name;self.save()
                with self.assertRaises(d.Stop):c.load_inputs(self.inputs)
    def test_four_patcher_exact_argv_and_no_csr_or_direct_silent(self):
        prepared=c.extract_pair(self.archive,self.rows,self.layout)
        called=[]
        def run(argv,**kwargs):called.append((argv,kwargs));return subprocess.CompletedProcess(argv,0)
        with mock.patch.object(c.subprocess,"run",side_effect=run):
            c.patch_staging(self.packet,self.m,self.rows,prepared)
        self.assertEqual([Path(row[0][2]).name for row in called[:4]],list(c.PATCHERS))
        self.assertTrue(all(row[0][1]=="-B" for row in called[:4]))
        self.assertEqual(Path(called[-1][0][1]).name,"verify-all.sh")
        self.assertTrue(all(row[1]["env"]["OPENCLAW_DIST"]==str(prepared.core/"dist") for row in called))
    def test_snapshot_wrong_private_metadata_pin_or_blob_no_stop(self):
        applied=self.apply()
        base=Path(applied["snapshot"]);self.n.events=[]
        for corrupt in ("pin","archive","mode"):
            with self.subTest(corrupt=corrupt):
                if corrupt=="pin":
                    changed={**applied,"snapshot_sha256":"f"*64}
                elif corrupt=="archive":
                    path=base/"captured-core-launcher.tar.gz";original=path.read_bytes();path.write_bytes(b"wrong")
                    changed=applied
                else:
                    (base/"snapshot.json").chmod(0o644);changed=applied
                with self.assertRaises(d.Stop):self.rollback(changed)
                self.assertNotIn("stop",self.n.events)
                if corrupt=="archive":path.write_bytes(original)
                if corrupt=="mode":(base/"snapshot.json").chmod(0o600)
    def test_same_content_foreign_live_generation_before_rollback_rejected(self):
        applied=self.apply();self.n.events=[]
        p=self.entry.with_name("foreign");p.write_bytes(self.entry.read_bytes());p.chmod(0o755);os.replace(p,self.entry)
        result=self.rollback(applied)
        self.assertEqual(result["status"],"rollback_deferred_no_retry");self.assertNotIn("stop",self.n.events)
        self.assertEqual(self.entry.read_bytes(),b"after core")
    def test_postrename_fsync_failure_journal_allows_restoration_and_repeat_rollback(self):
        original=c.fsync_dir;failed=False
        def fsync(path):
            nonlocal failed
            if not failed and self.entry.exists() and self.entry.read_bytes()==b"after core":
                failed=True;raise OSError("dummy directory fsync failed after rename")
            return original(path)
        with mock.patch.object(c,"fsync_dir",side_effect=fsync):
            result=self.apply()
        self.assertEqual(result["status"],"captured_install_failed")
        self.assertEqual(result["rollback_status"],"captured_rollback_passed");self.assert_before()
        self.n.events=[]
        self.assertEqual(self.rollback(result)["status"],"captured_rollback_already_restored")
        self.assertNotIn("stop",self.n.events)
    def test_retire_rename_fsync_failure_missing_root_has_durable_provenance(self):
        original=c.fsync_dir;failed=False
        def fsync(path):
            nonlocal failed
            if not failed and not self.layout.core.exists():
                failed=True;raise OSError("dummy fsync after retirement")
            return original(path)
        with mock.patch.object(c,"fsync_dir",side_effect=fsync):
            result=self.apply()
        self.assertEqual(result["status"],"captured_install_failed")
        self.assertEqual(result["rollback_status"],"captured_rollback_passed");self.assert_before()
        self.assertEqual(self.rollback(result)["status"],"captured_rollback_already_restored")
    def test_restore_postrename_fsync_failure_repeat_rollback_remains_possible(self):
        result=self.apply();original=c.fsync_dir;failed=False
        def fsync(path):
            nonlocal failed
            if not failed and self.entry.exists() and self.entry.read_bytes()==b"before core":
                failed=True;raise OSError("dummy fsync during restoration")
            return original(path)
        with mock.patch.object(c,"fsync_dir",side_effect=fsync):
            rolled=self.rollback(result)
        self.assertEqual(rolled["status"],"rollback_deferred_no_retry")
        self.assertEqual(self.entry.read_bytes(),b"before core")
        self.assertEqual(self.skill.read_bytes(),b"after client")
        self.assertEqual(self.rollback(result)["status"],"captured_rollback_passed");self.assert_before()
    def test_exit_zero_wrong_restored_bytes_not_passed(self):
        result=self.apply()
        self.n.start_hook=lambda:self.entry.write_bytes(b"wrong zero-exit restored code")
        rolled=self.rollback(result);self.assertEqual(rolled["status"],"rollback_deferred_no_retry")
        self.assertIn("final_restored_code_hash",rolled["rollback_error"])
    def test_start_failure_separate_primary_and_rollback_errors_no_retry_with_active_job(self):
        def start_error():
            self.n.job=9;raise d.Stop("start_outcome_indeterminate")
        self.n.start_hook=start_error
        result=self.apply();self.assertEqual(result["primary_error"],"start_outcome_indeterminate")
        self.assertEqual(result["rollback_status"],"deferred_no_retry");self.assertEqual(result["rollback_error"],"pending_native_job")
        self.assertEqual(self.n.events.count("stop"),1);self.assertEqual(self.n.events.count("start"),1)
    def test_capture_or_preparation_drift_never_stops_or_overwrites_foreign_code(self):
        original=c.capture
        def capture(*args,**kw):
            result=original(*args,**kw)
            p=self.entry.with_name("foreign");p.write_bytes(b"changed during capture");p.chmod(0o755);os.replace(p,self.entry)
            return result
        with mock.patch.object(c,"capture",side_effect=capture):result=self.apply()
        self.assertEqual(result["rollback_status"],"deferred_no_retry")
        self.assertNotIn("stop",self.n.events);self.assertNotIn("start",self.n.events)
        self.assertEqual(self.entry.read_bytes(),b"changed during capture")
    def test_snapshot_retained_when_candidate_staging_root_moves(self):
        result=self.apply()
        moved=self.root/"restaged-closure";shutil.copytree(self.closure,moved)
        self.m["closure"]["root"]=str(moved);self.save()
        self.assertEqual(self.rollback(result)["status"],"captured_rollback_passed");self.assert_before()
    def test_archive_path_or_symlink_escape_not_extracted(self):
        bad=[{"path":c.ROOT,"type":"directory","mode":0o755,"uid":os.geteuid(),"gid":os.getgid()},
             {"path":c.LINK,"type":"symlink","mode":0o777,"uid":os.geteuid(),"gid":os.getgid(),
              "target":"../../etc/passwd"}]
        with self.assertRaises(d.Stop):c.validate_records(bad)
        bad[1]["target"]="../lib/node_modules/openclaw/openclaw.mjs"
        bad.append({"path":c.ROOT+"/../foreign","type":"file","size":0,"sha256":"0"*64,"mode":0o644,"uid":0,"gid":0})
        with self.assertRaises(d.Stop):c.validate_records(bad)
    def test_missing_runtime_checker_no_native_and_no_invented_replacement(self):
        self.m.pop("ready_checker");self.save()
        with mock.patch.object(c,"Native",side_effect=AssertionError("native forbidden")):
            self.assertEqual(c.main(["apply","--inputs",str(self.inputs)]),2)
    def test_actual_cli_missing_root_crash_rollback_and_repeated_restoration(self):
        original_replace=os.replace
        def crash(source,target):
            original_replace(source,target)
            if Path(source)==self.layout.core and Path(target).name=="retired":
                raise KeyboardInterrupt("dummy crash after durable retire intent")
        with mock.patch.object(c.os,"replace",side_effect=crash),self.assertRaises(KeyboardInterrupt):self.apply()
        base=next(self.root.glob("crustacea-core-recovery-*"))
        def verify():
            self.n.events.append("verify")
            d.require(self.entry.exists() and self.entry.read_bytes()==b"before core","candidate_dist_unavailable")
        self.n.verify=verify;self.n.events=[]
        real_open=os.open;real_execute=c.execute;uid=os.geteuid()
        def lock(path,*args,**kw):
            return real_open(self.root/".component.lock" if str(path)=="/root/.crustacea-core-workspace-recovery.lock" else path,*args,**kw)
        def execute(*args,**kw):
            with mock.patch.object(c.os,"geteuid",return_value=uid):return real_execute(*args,**kw)
        def layout():
            v=type("Layout",(),{})()
            for key in ("core","entrypoint","workspace","backups"):setattr(v,key,getattr(self.layout,key))
            return v
        argv=["rollback","--inputs",str(self.inputs),"--snapshot",str(base),"--snapshot-sha256",d.digest(base/"snapshot.json")]
        with mock.patch.object(c.os,"geteuid",return_value=0),mock.patch.object(c.os,"open",side_effect=lock),\
             mock.patch.object(c,"execute",side_effect=execute),mock.patch.object(c,"Native",return_value=self.n),\
             mock.patch.object(d,"Layout",side_effect=layout),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(argv),0);self.assertEqual(c.main(argv),0)
        self.assert_before();self.assertEqual(self.n.events.count("start"),1)
    def test_prepared_boundary_foreign_code_or_config_edit_not_overwritten(self):
        original=c.journal
        for config in (False,True):
            with self.subTest(config=config):
                def record(base,pin,phase,**fields):
                    original(base,pin,phase,**fields)
                    if phase=="prepared":
                        if config:self.control.write_bytes(b"foreign operator config")
                        else:
                            path=self.entry.with_name("foreign");path.write_bytes(b"foreign boundary code")
                            path.chmod(0o755);os.replace(path,self.entry)
                with mock.patch.object(c,"journal",side_effect=record):
                    result=self.apply()
                self.assertEqual(result["rollback_status"],"deferred_no_retry")
                self.assertEqual(self.n.events.count("stop"),1);self.assertNotIn("start",self.n.events)
                if not config:self.assertEqual(self.entry.read_bytes(),b"foreign boundary code")
                self.n.events=[];self.n.active=True
                self.entry.write_bytes(b"before core");self.control.write_bytes(b"same configured model")
                self.m["expected_current_sha256"]=c.body_hash(c.inventory(self.layout));self.save()
    def test_current_whole_manifest_and_space_fail_before_stop(self):
        self.m["expected_current_sha256"]="e"*64;self.save()
        with self.assertRaises(d.Stop):self.apply()
        self.assertNotIn("stop",self.n.events)
        self.m["expected_current_sha256"]=self.expected_current;self.save()
        space=type("Space",(),{"f_bavail":0,"f_frsize":4096})()
        with mock.patch.object(c.os,"statvfs",return_value=space),self.assertRaises(d.Stop):self.apply()
        self.assertNotIn("stop",self.n.events)
    def test_native_mutation_delegation_without_outer_timeout_and_pending_state_guard(self):
        native=c.Native(self.packet,self.m);calls=[]
        def run(argv,**kwargs):
            calls.append((argv,kwargs))
            out=b"Job=0\nMainPID=0\nActiveState=inactive\nSubState=dead\n"
            return subprocess.CompletedProcess(argv,0,out,b"")
        with mock.patch.object(d.subprocess,"run",side_effect=run):
            native.stop();native.start()
        mutations=[row for row in calls if row[0][1] in ("stop","start")]
        self.assertEqual(len(mutations),2);self.assertTrue(all("timeout" not in row[1] for row in mutations))
        calls=[]
        def pending(argv,**kwargs):
            calls.append(argv);return subprocess.CompletedProcess(argv,0,b"Job=71 /job/71\n",b"")
        with mock.patch.object(d.subprocess,"run",side_effect=pending),self.assertRaises(d.Stop):native.stop()
        self.assertEqual(len(calls),1)
    def test_native_checker_immediate_source_hash_and_fixed_argv(self):
        native=c.Native(self.packet,self.m)
        with mock.patch.object(native,"run") as run:
            native.ready()
        self.assertEqual(run.call_args.args[0],["/bin/sh",str(self.packet/"accepted-owner-check.sh"),"--check-only"])
        (self.packet/"accepted-owner-check.sh").write_bytes(b"foreign")
        with mock.patch.object(native,"run") as run,self.assertRaises(d.Stop):native.ready()
        run.assert_not_called()
    def test_actual_cli_install_and_rollback_uses_snapshot_pin_and_preserves_state(self):
        real_open=os.open;real_execute=c.execute;uid=os.geteuid()
        def root_lock(path,*args,**kw):
            return real_open(self.root/".component.lock" if str(path)=="/root/.crustacea-core-workspace-recovery.lock" else path,*args,**kw)
        def execute(*args,**kw):
            with mock.patch.object(c.os,"geteuid",return_value=uid):return real_execute(*args,**kw)
        def layout():
            v=type("Layout",(),{})()
            for key in ("core","entrypoint","workspace","backups"):setattr(v,key,getattr(self.layout,key))
            return v
        stdout=io.StringIO()
        with mock.patch.object(c.os,"geteuid",return_value=0),mock.patch.object(c.os,"open",side_effect=root_lock),\
             mock.patch.object(c,"execute",side_effect=execute),mock.patch.object(c,"Native",return_value=self.n),\
             mock.patch.object(d,"Layout",side_effect=layout),contextlib.redirect_stdout(stdout):
            self.assertEqual(c.main(["apply","--inputs",str(self.inputs)]),0)
            result=json.loads(stdout.getvalue().splitlines()[-1]);self.ledger.write_bytes(b"new state after CLI apply")
            argv=["rollback","--inputs",str(self.inputs),"--snapshot",result["snapshot"],"--snapshot-sha256",result["snapshot_sha256"]]
            self.assertEqual(c.main(argv),0);self.assertEqual(c.main(argv),0)
        self.assert_before();self.assertEqual(self.ledger.read_bytes(),b"new state after CLI apply")
    def test_execute_rollback_missing_root_after_retire_skips_candidate_verifier(self):
        original=os.replace
        def crash(source,target):
            original(source,target)
            if Path(source)==self.layout.core and Path(target).name=="retired":
                raise KeyboardInterrupt("fixture process crash after retire rename")
        with mock.patch.object(c.os,"replace",side_effect=crash),self.assertRaises(KeyboardInterrupt):self.apply()
        self.assertFalse(self.layout.core.exists())
        base=next(self.root.glob("crustacea-core-recovery-*"))
        def verify():
            self.n.events.append("verify")
            d.require(self.entry.exists() and self.entry.read_bytes()==b"before core","current_dist_absent_or_bad")
        self.n.verify=verify;self.n.events=[]
        result=self.rollback({"snapshot":str(base),"snapshot_sha256":d.digest(base/"snapshot.json")})
        self.assertEqual(result["status"],"captured_rollback_passed");self.assert_before()
        self.assertEqual(self.n.events.count("start"),1)
    def test_execute_rollback_owned_candidate_with_failing_verifier_reaches_exact_restore(self):
        self.n.start_hook=lambda:(_ for _ in ()).throw(KeyboardInterrupt("fixture crash before postflight"))
        with self.assertRaises(KeyboardInterrupt):self.apply()
        self.assertEqual(self.entry.read_bytes(),b"after core")
        base=next(self.root.glob("crustacea-core-recovery-*"))
        self.n.start_hook=None;self.n.events=[]
        def verify():
            self.n.events.append("verify")
            d.require(self.entry.read_bytes()==b"before core","candidate_retention_check_failed")
        self.n.verify=verify
        result=self.rollback({"snapshot":str(base),"snapshot_sha256":d.digest(base/"snapshot.json")})
        self.assertEqual(result["status"],"captured_rollback_passed");self.assert_before()
        self.assertEqual(self.n.events.count("stop"),1);self.assertEqual(self.n.events.count("start"),1)


if __name__=="__main__":unittest.main()
