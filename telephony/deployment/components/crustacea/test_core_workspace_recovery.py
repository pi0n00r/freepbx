#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
"""Owned dummy package/filesystem fixtures; never invoke native transports/npm."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import tarfile
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("core_recovery",HERE/"core-workspace-recovery.py")
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


class FakeNative:
    def __init__(self,layout):
        self.layout=layout;self.events=[];self.job=0;self.calls=0
        self.stop_hook=None;self.install_hook=None;self.install_error=False;self.wrong=False
    def zero(self):
        self.events.append("zero");d.require(type(self.calls) is int and self.calls==0,"fixture_nonzero_calls")
    def verify(self):self.events.append("verify")
    def state(self):
        self.events.append("state");d.require(self.job==0,"fixture_pending_job")
        return {"Job":"0","MainPID":"19","ActiveState":"active","SubState":"running"}
    def stop(self):
        self.events.append("stop")
        if self.stop_hook:self.stop_hook()
    def start(self):self.events.append("start")
    def install(self,path):
        self.events.append("install")
        if self.install_error:
            (self.layout.core/"entry.mjs").write_bytes(b"partial npm")
            raise d.Stop("fixture_npm_failed")
        with tarfile.open(path,"r:gz") as archive:
            for member in archive:
                if member.isfile():
                    target=self.layout.core/Path(member.name).relative_to("package")
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
        if self.wrong:(self.layout.core/"entry.mjs").write_bytes(b"wrong zero-exit npm")
        if self.install_hook:self.install_hook()


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="core-recovery-fixture-",dir=HERE.parent)
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.layout=d.Layout()
        self.layout.core=self.root/"core";self.layout.core.mkdir()
        self.layout.workspace=self.root/"workspace";self.layout.workspace.mkdir()
        self.layout.backups=self.root
        self.layout.entrypoint=self.root/"openclaw"
        self.link="core/entry.mjs"
        self.layout.entrypoint.symlink_to(self.link)
        self.skill=self.layout.workspace/"skills/avril-call/client.js"
        self.skill.parent.mkdir(parents=True);self.skill.write_bytes(b"accepted skill before");self.skill.chmod(0o640)
        (self.layout.core/"entry.mjs").write_bytes(b"accepted core before")
        self.control=self.root/"openclaw.json";self.control.write_bytes(b"unchanged model config")
        self.ledger=self.root/"runtime.sqlite";self.ledger.write_bytes(b"accrued live state")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(d,"PROTECTED",(str(self.control),)).start()
        self.n=FakeNative(self.layout)
        self.packet=self.root/"inputs";self.packet.mkdir()
        self.m={"schema":"crustacea-core-workspace-recovery-v1","workflow_source":d.WORKFLOW_COMMIT,
                "workspace":[],"protected":{str(self.control):d.digest(self.control)},"bin_link":self.link,
                "bin_resolved_target":"/usr/lib/node_modules/openclaw/entry.mjs"}
        for key,content in (("before",b"accepted core before"),("after",b"accepted core after")):
            path=self.packet/(key+".tgz")
            with tarfile.open(path,"w:gz") as archive:
                info=tarfile.TarInfo("package/entry.mjs");info.size=len(content)
                archive.addfile(info,io.BytesIO(content))
            self.m[key]={"archive":path.name,"sha256":d.digest(path),"source_commit":("1" if key=="before" else "2")*40,
                         "files":{"entry.mjs":__import__("hashlib").sha256(content).hexdigest()}}
        source=self.packet/"skill.js";source.write_bytes(b"accepted skill after")
        self.m["workspace"]=[{"source":source.name,"target":"skills/avril-call/client.js",
                               "sha256":d.digest(source),"before_sha256":d.digest(self.skill)}]
        (self.packet/"verify-all.sh").write_bytes(b"fixture read-only verifier")
        (self.packet/"accepted-vip-telephony-check.py").write_bytes(b"fixture existing owner checker")
        self.m["retention_verifier_sha256"]=d.digest(self.packet/"verify-all.sh")
        self.m["zero_checker"]={"path":"accepted-vip-telephony-check.py","sha256":d.digest(self.packet/"accepted-vip-telephony-check.py"),
                                "runner":"python3","args":["--check-only"]}
        loaded={"before_source_commit":self.m["before"]["source_commit"],"after_source_commit":self.m["after"]["source_commit"],
                "before_package_sha256":self.m["before"]["sha256"],"after_package_sha256":self.m["after"]["sha256"],
                "fixture_only":True}
        (self.packet/"LOADED-IDENTITY.json").write_text(json.dumps(loaded))
        self.m["loaded_identity_receipt_sha256"]=d.digest(self.packet/"LOADED-IDENTITY.json")
        self.inputs=self.packet/"INPUTS.json";self.save()
    def save(self):self.inputs.write_text(json.dumps(self.m))
    def apply(self):
        root,m=d.load_inputs(self.inputs)
        return d.execute("apply",root,m,self.n,self.layout)
    def rollback(self,applied):
        root,m=d.load_inputs(self.inputs)
        return d.execute("rollback",root,m,self.n,self.layout,applied["snapshot"],applied["snapshot_sha256"])
    def no_stop(self):self.assertNotIn("stop",self.n.events)

    def test_offline_verify_never_constructs_native(self):
        with mock.patch.object(d,"Native",side_effect=AssertionError("native forbidden")):
            self.assertEqual(d.main(["verify","--inputs",str(self.inputs)]),0)
    def test_readonly_installed_observation_returns_actual_tree_not_expected_tree(self):
        (self.layout.core/"entry.mjs").write_bytes(b"foreign observed bytes")
        with mock.patch.object(d,"Layout",return_value=self.layout),mock.patch.object(d,"Native",side_effect=AssertionError("native forbidden")):
            observed=d.observe_installed(self.m,self.layout)
            self.assertEqual(d.main(["observe","--inputs",str(self.inputs)]),0)
        self.assertEqual(observed["core_manifest_sha256"],d.manifest_digest(d.tree(self.layout.core)))
        self.assertNotEqual(observed["core_manifest_sha256"],d.manifest_digest(self.m["after"]["files"]))
        self.no_stop()
    def test_missing_actual_packets_blocks_before_native(self):
        self.m.pop("before");self.save()
        with mock.patch.object(d,"Native",side_effect=AssertionError("native forbidden")):
            self.assertEqual(d.main(["apply","--inputs",str(self.inputs)]),2)
    def test_wrong_workflow_pin_rejected(self):
        self.m["workflow_source"]="9"*40;self.save()
        with self.assertRaises(d.Stop):d.load_inputs(self.inputs)
    def test_package_bytes_and_identity_pin_rejected(self):
        (self.packet/"after.tgz").write_bytes(b"foreign")
        with self.assertRaises(d.Stop):d.load_inputs(self.inputs)
    def test_owner_receipt_wrong_package_provenance_rejected(self):
        p=self.packet/"LOADED-IDENTITY.json";p.write_text("{}")
        self.m["loaded_identity_receipt_sha256"]=d.digest(p);self.save()
        with self.assertRaisesRegex(d.Stop,"owner_loaded"):d.load_inputs(self.inputs)
    def test_package_links_and_escape_rejected(self):
        for member_name,kind in (("package/link",tarfile.SYMTYPE),("../escape",tarfile.REGTYPE)):
            with self.subTest(name=member_name):
                p=self.packet/"after.tgz"
                with tarfile.open(p,"w:gz") as archive:
                    member=tarfile.TarInfo(member_name);member.type=kind;member.linkname="/etc/passwd"
                    archive.addfile(member,io.BytesIO(b""))
                self.m["after"]["sha256"]=d.digest(p)
                loaded=json.loads((self.packet/"LOADED-IDENTITY.json").read_text())
                loaded["after_package_sha256"]=d.digest(p)
                (self.packet/"LOADED-IDENTITY.json").write_text(json.dumps(loaded))
                self.m["loaded_identity_receipt_sha256"]=d.digest(self.packet/"LOADED-IDENTITY.json");self.save()
                with self.assertRaises(d.Stop):d.load_inputs(self.inputs)
    def test_no_db_canonical_or_agent_rewind_payload(self):
        for target in ("Documents/Notes/TASKS.md","agents/aimee-voice/agent.sqlite","skills/backup.db-wal"):
            with self.subTest(target=target):
                self.m["workspace"][0]["target"]=target;self.save()
                with self.assertRaises(d.Stop):d.load_inputs(self.inputs)
    def test_fresh_host_new_skill_is_explicit_missing_contract(self):
        self.m["workspace"][0]["before_sha256"]=None;self.save()
        with self.assertRaisesRegex(d.Stop,"fresh_host_contract_missing"):d.load_inputs(self.inputs)
    def test_apply_rollback_repeat_keeps_new_state_and_model_bytes(self):
        original=self.control.read_bytes();mode=self.skill.stat().st_mode&0o777
        applied=self.apply();self.assertEqual(applied["status"],"delegated_apply_passed")
        self.ledger.write_bytes(b"newly accrued state");self.n.events=[]
        result=self.rollback(applied);self.assertEqual(result["status"],"delegated_rollback_passed")
        self.assertEqual(d.tree(self.layout.core),self.m["before"]["files"])
        self.assertEqual(self.skill.read_bytes(),b"accepted skill before")
        self.assertEqual(self.skill.stat().st_mode&0o777,mode)
        self.assertEqual(self.control.read_bytes(),original);self.assertEqual(self.ledger.read_bytes(),b"newly accrued state")
        self.n.events=[]
        self.assertEqual(self.rollback(applied)["status"],"delegated_rollback_already_restored");self.no_stop()
    def test_wrong_core_and_skill_preimage_before_stop(self):
        (self.layout.core/"entry.mjs").write_bytes(b"foreign")
        with self.assertRaises(d.Stop):self.apply()
        self.no_stop()
        (self.layout.core/"entry.mjs").write_bytes(b"accepted core before")
        self.skill.write_bytes(b"foreign skill")
        with self.assertRaises(d.Stop):self.apply()
        self.no_stop()
    def test_symlink_ancestor_escape_rejected(self):
        other=self.root/"foreign";other.mkdir()
        self.skill.unlink();self.skill.parent.rmdir();self.skill.parent.symlink_to(other,target_is_directory=True)
        (other/"client.js").write_bytes(b"accepted skill before")
        with self.assertRaises(d.Stop):self.apply()
        self.no_stop()
    def test_nonzero_and_bool_calls_rejected(self):
        for count in (1,False):
            with self.subTest(count=count):
                self.n.calls=count
                with self.assertRaises(d.Stop):self.apply()
        self.no_stop()
    def test_active_job_rejected_without_stop(self):
        self.n.job=9
        with self.assertRaises(d.Stop):self.apply()
        self.no_stop()
    def test_stop_timeout_job_no_second_operation(self):
        def blocked():
            self.n.job=19;raise subprocess.TimeoutExpired("dummy systemctl",45)
        self.n.stop_hook=blocked
        result=self.apply()
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertEqual(self.n.events.count("stop"),1);self.assertNotIn("install",self.n.events);self.assertNotIn("start",self.n.events)
    def test_config_drift_during_stop_not_overwritten(self):
        self.n.stop_hook=lambda:self.control.write_bytes(b"new owner model config")
        result=self.apply()
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertNotIn("install",self.n.events);self.assertEqual(self.control.read_bytes(),b"new owner model config")
    def test_foreign_skill_edit_during_owner_npm_no_overwrite(self):
        self.n.install_hook=lambda:self.skill.write_bytes(b"foreign during npm")
        result=self.apply()
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertEqual(self.skill.read_bytes(),b"foreign during npm");self.assertEqual(self.n.events.count("install"),1)
    def test_pending_stop_or_wrong_core_zeroexit_no_retry(self):
        self.n.wrong=True
        result=self.apply()
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertEqual(self.n.events.count("install"),1);self.assertNotIn("start",self.n.events)
    def test_partial_npm_error_no_automatic_rollback(self):
        self.n.install_error=True
        result=self.apply()
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertEqual(self.n.events.count("install"),1);self.assertNotIn("start",self.n.events)
    def test_wrong_rollback_saved_blob_blocks_before_stop(self):
        applied=self.apply();self.n.events=[]
        (Path(applied["snapshot"])/"0.before").write_bytes(b"wrong snapshot")
        with self.assertRaises(d.Stop):self.rollback(applied)
        self.no_stop()
    def test_wrong_restored_skill_zeroexit_never_passes(self):
        applied=self.apply();original=d.atomic
        def wrong(path,data,uid,gid,mode,prepared=None):
            return original(path,b"wrong restored",uid,gid,mode,prepared)
        with mock.patch.object(d,"atomic",side_effect=wrong):result=self.rollback(applied)
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertNotEqual(self.skill.read_bytes(),b"accepted skill before")
    def test_foreign_same_content_new_inode_rollback_rejected(self):
        applied=self.apply();duplicate=self.skill.with_name("new-inode")
        duplicate.write_bytes(self.skill.read_bytes());duplicate.chmod(self.skill.stat().st_mode&0o777)
        os.replace(duplicate,self.skill);self.n.events=[]
        with self.assertRaisesRegex(d.Stop,"foreign_workspace_generation"):self.rollback(applied)
        self.no_stop()
    def test_native_readonly_contract_hash_rechecked(self):
        n=d.Native(self.packet,self.m)
        (self.packet/"verify-all.sh").write_bytes(b"foreign owner script")
        with mock.patch.object(n,"run",side_effect=AssertionError("no execution")):
            with self.assertRaisesRegex(d.Stop,"changed_before_execution"):n.verify()
    def test_prepared_workspace_generation_survives_postrename_fsync_failure(self):
        real=d.os.fsync;failed=[]
        def fsync(fd):
            if self.skill.read_bytes()==b"accepted skill after" and not failed:
                failed.append(True);raise OSError("dummy postrename fsync")
            return real(fd)
        with mock.patch.object(d.os,"fsync",side_effect=fsync):applied=self.apply()
        self.assertEqual(applied["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertEqual(self.n.events.count("install"),1)
        self.n.events=[]
        self.assertEqual(self.rollback(applied)["status"],"delegated_rollback_passed")
        self.assertEqual(self.skill.read_bytes(),b"accepted skill before")
    def test_prepared_boundary_foreign_skill_drift_never_overwritten(self):
        original=d.workspace_record;changed=[]
        def record(base,pin,name,phase,path):
            original(base,pin,name,phase,path)
            if phase=="prepared" and not changed:
                self.skill.write_bytes(b"foreign prepared edit");changed.append(True)
        with mock.patch.object(d,"workspace_record",side_effect=record):result=self.apply()
        self.assertEqual(result["status"],"stopped_owner_operation_review_required_no_retry")
        self.assertEqual(self.skill.read_bytes(),b"foreign prepared edit")
        self.assertNotIn("start",self.n.events)
    def test_exact_native_owner_argv_and_phase_no_outer_timeout(self):
        n=d.Native(self.packet,self.m)
        with mock.patch.object(n,"run",return_value=b"") as run:
            n.zero();n.verify()
        self.assertEqual(run.call_args_list[0].args[0],["/usr/bin/python3","-B",str(self.packet/"accepted-vip-telephony-check.py"),"--check-only"])
        self.assertEqual(run.call_args_list[1].args[0],["/bin/bash",str(self.packet/"verify-all.sh")])
        with mock.patch.object(d.subprocess,"run",return_value=mock.Mock(returncode=0)) as run:n.install(self.packet/"after.tgz")
        self.assertEqual(run.call_args.args[0],["/bin/bash",str(HERE/"install-core-phase.sh"),str(self.packet/"after.tgz")])
        self.assertNotIn("timeout",run.call_args.kwargs)
    def test_native_relative_launcher_spelling_preserved_with_resolved_target(self):
        prefix=self.root/"usr"
        new_core=prefix/"lib/node_modules/openclaw";new_core.parent.mkdir(parents=True)
        shutil.move(str(self.layout.core),str(new_core));self.layout.core=new_core
        self.layout.entrypoint.unlink()
        self.layout.entrypoint=prefix/"bin/openclaw";self.layout.entrypoint.parent.mkdir()
        raw="../lib/node_modules/openclaw/entry.mjs"
        self.layout.entrypoint.symlink_to(raw);self.m["bin_link"]=raw;self.save()
        observed=d.observe_installed(self.m,self.layout)
        self.assertEqual(observed["status"],"installed_code_observed")
        self.assertEqual(os.readlink(self.layout.entrypoint),raw)
        self.assertEqual(self.apply()["status"],"delegated_apply_passed")
        self.assertEqual(os.readlink(self.layout.entrypoint),raw)
    def test_link_spelling_and_resolved_target_drift_both_rejected(self):
        self.m["bin_link"]="core/../core/entry.mjs"
        with self.assertRaises(d.Stop):d.require_entrypoint(self.m,self.layout)
        self.m["bin_link"]=self.link;self.m["bin_resolved_target"]="/usr/lib/node_modules/openclaw/wrong.mjs"
        with self.assertRaises(d.Stop):d.require_entrypoint(self.m,self.layout)
    def test_native_service_mutations_have_no_outer_timeout_and_pending_observation_blocks(self):
        n=d.Native(self.packet,self.m)
        with mock.patch.object(n,"state",return_value={}) as state, mock.patch.object(d.subprocess,"run",return_value=mock.Mock(returncode=0)) as run:
            n.stop();n.start()
        self.assertEqual(state.call_count,4)
        self.assertEqual([r.args[0] for r in run.call_args_list],
                         [["/usr/bin/systemctl","stop",d.UNIT],["/usr/bin/systemctl","start",d.UNIT]])
        self.assertTrue(all("timeout" not in r.kwargs for r in run.call_args_list))
        with mock.patch.object(n,"state",side_effect=d.Stop("pending_job")),mock.patch.object(d.subprocess,"run") as run:
            with self.assertRaises(d.Stop):n.stop()
        run.assert_not_called()
    def test_executed_wrapper_hash_drift_blocks_delegation(self):
        n=d.Native(self.packet,self.m);real=d.digest
        def changed(path):
            return "f"*64 if Path(path).name=="install-core-phase.sh" else real(path)
        with mock.patch.object(d,"digest",side_effect=changed),mock.patch.object(d.subprocess,"run") as run:
            with self.assertRaisesRegex(d.Stop,"executed_install_wrapper_changed"):n.install(self.packet/"after.tgz")
        run.assert_not_called()
    def test_native_skill_agent_descriptor_is_static_code_not_runtime_agents(self):
        target="skills/avril-call/agents/openai.yaml"
        source="static/"+target
        self.assertEqual(str(d.relative(target)),target)
        payload=self.packet/source;payload.parent.mkdir(parents=True);payload.write_bytes(b"interface: fixture\n")
        self.assertEqual(d.packet_file(self.packet,source),payload)
        runtime=self.layout.workspace/target;runtime.parent.mkdir(parents=True);runtime.write_bytes(payload.read_bytes())
        self.assertEqual(d.workspace_path(self.layout,target),runtime)
    def test_skill_descriptor_exception_does_not_open_runtime_or_other_agent_payloads(self):
        for value in ("agents/aimee/agent/openclaw-agent.sqlite", "agents/openai.yaml", "skills/avril-call/agents/state.db",
                      "static/agents/skills/avril-call/agents/openai.yaml", "skills/avril-call/agents/other.yaml",
                      "Documents/skills/avril-call/agents/openai.yaml", "skills/../agents/openai.yaml"):
            with self.subTest(value=value),self.assertRaises(d.Stop):d.relative(value)
    def test_skill_agent_descriptor_ancestor_symlink_still_rejected(self):
        folder=self.packet/"outside";folder.mkdir();(folder/"openai.yaml").write_bytes(b"fixture descriptor\n")
        prefix=self.packet/"static/skills/avril-call";prefix.mkdir(parents=True);(prefix/"agents").symlink_to(folder)
        with self.assertRaises(d.Stop):d.packet_file(self.packet,"static/skills/avril-call/agents/openai.yaml")
    def test_existing_checker_shell_contract_and_argument_injection_rejection(self):
        self.m["zero_checker"].update(runner="bash",args=[]);self.save();d.load_inputs(self.inputs)
        n=d.Native(self.packet,self.m)
        with mock.patch.object(n,"run",return_value=b"") as run:n.zero()
        self.assertEqual(run.call_args.args[0],["/bin/bash",str(self.packet/"accepted-vip-telephony-check.py")])
        self.m["zero_checker"]["args"]=[";service"];self.save()
        with self.assertRaises(d.Stop):d.load_inputs(self.inputs)


if __name__=="__main__":unittest.main(verbosity=2)
