#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
"""Guarded delegation to the existing core install phase; never restore runtime DBs."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import time

WORKFLOW_COMMIT = "108ca20b05932f058d7cddb8bbfef29c1a598f6c"
PHASE_SHA = "5ea4363ee5402b636a5c59eba8e4497953deb2c943fa1a0e1e3ba1f7a71d880d"
WRAPPER_SHA = "e23bd07dcd48a69ef026b6ed2e2b188592ad7c8dbe4fe38eee3588ef0c32da64"
SHA = re.compile(r"[0-9a-f]{64}\Z")
UNIT = "openclaw.service"
PROTECTED = ("/home/aimee/.openclaw/openclaw.json", "/etc/systemd/system/openclaw.service",
             "/etc/aimee-main-voice-relay.env", "/etc/systemd/system/aimee-main-voice-relay.service")


class Stop(Exception): pass


def require(value, code):
    if not value: raise Stop(code)


def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(131072), b""):h.update(b)
    return h.hexdigest()


def regular(p):
    p=Path(p)
    require(p.is_file() and not p.is_symlink(), "regular_input_required")
    return p


def relative(value):
    p=PurePosixPath(value)
    require(value and not p.is_absolute() and ".." not in p.parts, "relative_path_invalid")
    # A skill's native agent descriptor is code, not the agents runtime store.
    skill_manifest = len(p.parts) >= 4 and p.parts[-4] == "skills" and p.parts[-2:] == ("agents", "openai.yaml")
    require(not any(x in ("Documents", "Notes", ".git", "data", "credentials")
                    or (x == "agents" and not (skill_manifest and i == len(p.parts)-2))
                    or x.endswith((".sqlite", ".sqlite-wal", ".sqlite-shm", ".db", ".db-wal", ".db-shm")) for i,x in enumerate(p.parts)),
            "runtime_or_canonical_state_payload_forbidden")
    return p


def packet_file(root,value):
    p=root/relative(value)
    require(p.resolve()==p,"owner_packet_ancestor_symlink_or_escape")
    return regular(p)


def tree(root):
    rows={}
    for p in Path(root).rglob("*"):
        if p.is_symlink():
            require(p.resolve().is_relative_to(Path(root).resolve()), "external_link_requires_owner_recovery_contract")
            rows[str(p.relative_to(root))]="link:"+os.readlink(p)
        elif p.is_file():rows[str(p.relative_to(root))]=digest(p)
    return rows


def manifest_digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def require_entrypoint(m,layout):
    require(layout.entrypoint.is_symlink() and os.readlink(layout.entrypoint)==m["bin_link"],
            "core_entrypoint_link_spelling_changed")
    target=PurePosixPath(m["bin_resolved_target"]).relative_to("/usr/lib/node_modules/openclaw")
    require(layout.entrypoint.resolve()==(layout.core/target).resolve(),"core_entrypoint_resolved_target_changed")


def observe_installed(m,layout):
    controls(m)
    require_entrypoint(m,layout)
    return {"status":"installed_code_observed","core_manifest_sha256":manifest_digest(tree(layout.core)),
            "workspace":{r["target"]:digest(workspace_path(layout,r["target"])) for r in m["workspace"]},
            "config_preserved":True,"native_human_acceptance":False}


def private_write(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(value);f.flush();os.fsync(f.fileno())
    fd=os.open(Path(path).parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def identity(path):
    p=regular(path);s=p.stat()
    return {"sha256":digest(p),"uid":s.st_uid,"gid":s.st_gid,"mode":s.st_mode&0o777,
            "size":s.st_size,"dev":s.st_dev,"ino":s.st_ino,"mtime_ns":s.st_mtime_ns}


def workspace_path(layout,name):
    p=layout.workspace/relative(name)
    require(layout.workspace.resolve()==layout.workspace and p.resolve()==p,
            "workspace_ancestor_symlink_or_escape")
    return regular(p)


def workspace_record(base,pin,name,phase,path):
    private_write(base/("workspace-"+str(time.time_ns())+"-"+phase+".json"),
                  (json.dumps({"snapshot_sha256":pin,"target":name,"identity":identity(path)},sort_keys=True)+"\n").encode())


def workspace_owned(base,pin,name,current,before):
    if current==before:return True
    for p in base.glob("workspace-*.json"):
        s=regular(p).stat()
        require(s.st_uid==os.geteuid() and s.st_mode&0o777==0o600,"workspace_journal_metadata_changed")
        value=json.loads(p.read_bytes())
        if value.get("snapshot_sha256")==pin and value.get("target")==name and value.get("identity")==current:
            return True
    return False


def load_inputs(path):
    root=Path(path).resolve().parent
    m=json.loads(regular(path).read_bytes())
    require(m.get("schema")=="crustacea-core-workspace-recovery-v1", "accepted_owner_input_packet_required")
    require(m.get("workflow_source")==WORKFLOW_COMMIT, "workflow_source_pin_changed")
    for field in ("before", "after", "workspace", "protected", "retention_verifier_sha256", "zero_checker", "loaded_identity_receipt_sha256",
                  "bin_link", "bin_resolved_target"):
        require(field in m, "missing_"+field)
    require(set(m["protected"]) >= set(PROTECTED), "actual_config_unit_and_model_invariants_required")
    # These fixed existing owner contracts require independently retained/read-back proofs.
    for name,field in (("verify-all.sh","retention_verifier_sha256"),
                       ("LOADED-IDENTITY.json","loaded_identity_receipt_sha256")):
        require(SHA.fullmatch(m[field]) and digest(regular(root/name))==m[field], "owner_contract_missing_or_changed_"+name)
    loaded=json.loads((root/"LOADED-IDENTITY.json").read_bytes())
    require(loaded.get("before_source_commit")==m["before"]["source_commit"]
            and loaded.get("before_package_sha256")==m["before"]["sha256"]
            and loaded.get("after_source_commit")==m["after"]["source_commit"]
            and loaded.get("after_package_sha256")==m["after"]["sha256"],
            "owner_loaded_and_package_proof_binding_changed")
    require(isinstance(m["bin_link"],str) and re.fullmatch("[A-Za-z0-9_./-]+",m["bin_link"]),
            "accepted_exact_entrypoint_link_spelling_required")
    resolved=PurePosixPath(m["bin_resolved_target"])
    require(resolved.is_absolute() and resolved.is_relative_to("/usr/lib/node_modules/openclaw")
            and ".." not in resolved.parts,"accepted_entrypoint_resolved_target_required")
    z=m["zero_checker"]
    require(isinstance(z,dict) and set(z)=={"path","sha256","runner","args"}
            and z["runner"] in ("python3","bash","sh") and isinstance(z["args"],list)
            and len(z["args"])<=16 and all(isinstance(a,str) and re.fullmatch("[A-Za-z0-9_./:@=,+-]+",a) for a in z["args"]),
            "existing_owner_checker_typed_contract_required")
    require(SHA.fullmatch(z["sha256"]) and digest(packet_file(root,z["path"]))==z["sha256"],
            "existing_owner_checker_missing_or_changed")
    for sha in m["protected"].values():require(SHA.fullmatch(sha),"protected_fingerprint_invalid")
    for key in ("before","after"):
        p=m[key]
        require(isinstance(p.get("source_commit"),str) and re.fullmatch("[0-9a-f]{40}",p["source_commit"]), "exact_package_source_commit_required")
        require(isinstance(p.get("files"),dict) and p["files"], "complete_package_manifest_required")
        archive=packet_file(root,p["archive"])
        require(SHA.fullmatch(p["sha256"]) and digest(archive)==p["sha256"], "package_archive_changed")
        names=set()
        with tarfile.open(archive,"r:gz") as t:
            for member in t:
                n=PurePosixPath(member.name)
                normalized=str(n)
                require(n.parts and not n.is_absolute() and ".." not in n.parts and n.parts[0]=="package"
                        and normalized not in names and (member.isfile() or member.isdir()), "npm_package_containment_or_links_invalid")
                names.add(normalized)
        for name,sha in p["files"].items():
            relative(name)
            require(SHA.fullmatch(sha) or (isinstance(sha,str) and sha.startswith("link:")),"package_manifest_value_invalid")
    seen=set()
    for row in m["workspace"]:
        name=str(relative(row["target"]))
        require(name.startswith("skills/") and name not in seen, "static_skill_payload_required_no_duplicate")
        seen.add(name)
        source=packet_file(root,row["source"])
        require(SHA.fullmatch(row["sha256"]) and digest(source)==row["sha256"], "workspace_payload_changed")
        require(isinstance(row.get("before_sha256"),str) and SHA.fullmatch(row["before_sha256"]),
                "existing_skill_preimage_required_fresh_host_contract_missing")
    require(digest(Path(__file__).with_name("openclaw-core-install.commands"))==PHASE_SHA, "accepted_install_phase_changed")
    return root,m


class Layout:
    core=Path("/usr/lib/node_modules/openclaw")
    workspace=Path("/home/aimee/.openclaw/workspace")
    backups=Path("/root")
    entrypoint=Path("/usr/bin/openclaw")


class Native:
    def __init__(self,root,m):self.root=root;self.m=m
    def run(self,argv):
        p=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=45)
        require(p.returncode==0,"native_observation_failed")
        return p.stdout
    def zero(self):
        z=self.m["zero_checker"];p=packet_file(self.root,z["path"])
        require(digest(p)==z["sha256"],"native_zero_checker_changed_before_execution")
        runners={"python3":["/usr/bin/python3","-B"],"bash":["/bin/bash"],"sh":["/bin/sh"]}
        self.run(runners[z["runner"]]+[str(p)]+z["args"])
    def verify(self):
        p=regular(self.root/"verify-all.sh")
        require(digest(p)==self.m["retention_verifier_sha256"],"retention_verifier_changed_before_execution")
        self.run(["/bin/bash",str(p)])
    def state(self):
        raw=self.run(["/usr/bin/systemctl","show",UNIT,"--property=Job,MainPID,ActiveState,SubState,InvocationID"])
        p=dict(line.split("=",1) for line in raw.decode().splitlines() if "=" in line)
        require("Job" in p and (not p["Job"] or p["Job"].split()[0]=="0"),"systemd_job_pending_no_mutation")
        return p
    def stop(self):
        self.state();self.mutate(["/usr/bin/systemctl","stop",UNIT]);self.state()
    def start(self):
        self.state();self.mutate(["/usr/bin/systemctl","start",UNIT]);self.state()
    def mutate(self,argv):
        p=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        require(p.returncode==0,"native_mutation_failed_no_retry")
    def install(self,path):
        phase=Path(__file__).with_name("install-core-phase.sh")
        require(digest(regular(phase))==WRAPPER_SHA,"executed_install_wrapper_changed")
        require(digest(Path(__file__).with_name("openclaw-core-install.commands"))==PHASE_SHA,
                "accepted_install_phase_changed_before_execution")
        # The owner npm phase retains its own lifecycle; no outer kill or retry.
        p=subprocess.run(["/bin/bash",str(phase),str(path)],stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        require(p.returncode==0,"owner_npm_phase_failed_independent_state_review_required")


def controls(m):
    rows={}
    for name,sha in m["protected"].items():
        p=regular(name);require(digest(p)==sha,"config_model_plugin_or_unit_drift")
        rows[name]=sha
    return rows


def atomic(path,data,uid,gid,mode,prepared=None):
    require(not path.is_symlink(),"workspace_symlink_invalid")
    require(path.parent.exists(),"existing_workspace_parent_required")
    fd,name=tempfile.mkstemp(prefix=".skill-recovery-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fchown(f.fileno(),uid,gid);os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
        if prepared is not None:prepared(Path(name))
        os.replace(name,path)
        fd=os.open(path.parent,os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(name):os.unlink(name)


def execute(mode,root,m,native,layout,backup=None,manifest_pin=None):
    preserved=controls(m);native.zero();native.verify();native.state()
    require_entrypoint(m,layout)
    current=tree(layout.core)
    if mode=="apply":
        require(current==m["before"]["files"],"current_complete_core_CAS_changed")
        base=Path(tempfile.mkdtemp(prefix="crustacea-core-recovery-",dir=layout.backups));base.chmod(0o700)
        archive=root/m["before"]["archive"]
        private_write(base/"before-package.tgz",archive.read_bytes())
        snapshots=[]
        for i,row in enumerate(m["workspace"]):
            path=workspace_path(layout,row["target"]);old=identity(path)
            require(old["sha256"]==row["before_sha256"],"workspace_preimage_changed")
            private_write(base/(str(i)+".before"),path.read_bytes())
            snapshots.append({"target":row["target"],"before":old,"after":row["sha256"]})
        snapshot={"schema":"crustacea-code-only-snapshot-v1","before":m["before"],"after":m["after"],
                  "protected":preserved,"workspace":snapshots,"DB_restored":False,"config_restored":False}
        private_write(base/"snapshot.json",(json.dumps(snapshot,sort_keys=True)+"\n").encode())
        action=m["after"];package=root/action["archive"]
    else:
        base=Path(backup)
        require(base.parent==layout.backups and base.name.startswith("crustacea-core-recovery-") and base.resolve()==base
                and base.stat().st_mode&0o777==0o700 and base.stat().st_uid==os.geteuid(),"protected_snapshot_required")
        meta=regular(base/"snapshot.json").stat()
        require(meta.st_uid==os.geteuid() and meta.st_mode&0o777==0o600,"snapshot_private_metadata_changed")
        require(SHA.fullmatch(manifest_pin or "") and digest(regular(base/"snapshot.json"))==manifest_pin,"snapshot_pin_changed")
        snapshot=json.loads((base/"snapshot.json").read_bytes())
        require(snapshot["schema"]=="crustacea-code-only-snapshot-v1" and snapshot["protected"]==preserved
                and snapshot["before"]==m["before"] and snapshot["after"]==m["after"]
                and snapshot["DB_restored"] is False and snapshot["config_restored"] is False,"snapshot_identity_changed")
        require(current in (m["before"]["files"],m["after"]["files"]),"foreign_or_partial_core_requires_owner_review")
        package=regular(base/"before-package.tgz")
        require(digest(package)==m["before"]["sha256"],"independent_before_package_changed")
        action=m["before"]
    pin=digest(base/"snapshot.json")
    generations={}
    for i,row in enumerate(snapshot["workspace"]):
        target=workspace_path(layout,row["target"]);observed=identity(target)
        require(observed["sha256"] in (row["before"]["sha256"],row["after"]),"workspace_generation_changed")
        if mode=="apply":require(observed==row["before"],"workspace_capture_generation_changed")
        else:
            require(workspace_owned(base,pin,row["target"],observed,row["before"]),"foreign_workspace_generation_requires_owner_review")
            require(digest(regular(base/(str(i)+".before")))==row["before"]["sha256"],"saved_skill_preimage_changed")
        generations[row["target"]]=observed
    if mode=="rollback" and current==action["files"] and all(
            generations[row["target"]]["sha256"]==row["before"]["sha256"] for row in snapshot["workspace"]):
        native.verify();native.zero()
        require(controls(m)==preserved,"idempotent_settings_drift")
        return {"status":"delegated_rollback_already_restored","snapshot":str(base),"snapshot_sha256":pin,
                "DB_restored":False,"config_restored":False,"native_human_acceptance":False}
    require(controls(m)==preserved and tree(layout.core)==current,"fresh_core_or_config_CAS_changed")
    native.zero();native.state()
    result={"snapshot":str(base),"snapshot_sha256":digest(base/"snapshot.json"),"DB_restored":False,"config_restored":False}
    private_write(base/("operation-"+str(time.time_ns())+".json"),(json.dumps({**result,"phase":"before_owner_npm","mode":mode},sort_keys=True)+"\n").encode())
    try:
        def fresh(verify_core=False):
            native.state();require(controls(m)==preserved,"protected_settings_drift_before_owner_mutation")
            if verify_core:require(tree(layout.core)==current,"core_drift_during_stop")
            for name,generation in generations.items():
                require(identity(workspace_path(layout,name))==generation,"workspace_drift_during_owner_operation")
        native.stop();fresh(verify_core=True)
        native.install(package)
        require(tree(layout.core)==action["files"],"installed_core_manifest_mismatch")
        require_entrypoint(m,layout)
        fresh()
        for i,row in enumerate(snapshot["workspace"]):
            target=workspace_path(layout,row["target"])
            old=row["before"]
            def prepared(path,name=row["target"]):
                workspace_record(base,pin,name,"prepared",path)
                fresh()
            if mode=="apply":
                source=root/m["workspace"][i]["source"]
                require(digest(source)==row["after"],"source_skill_changed_before_replacement")
                atomic(target,source.read_bytes(),old["uid"],old["gid"],old["mode"],prepared)
                require(digest(target)==row["after"],"skill_postimage_rejected")
            else:
                data=regular(base/(str(i)+".before")).read_bytes()
                require(hashlib.sha256(data).hexdigest()==old["sha256"],"skill_saved_preimage_changed")
                atomic(target,data,old["uid"],old["gid"],old["mode"],prepared)
                require(digest(target)==old["sha256"],"skill_restoration_rejected")
            generations[row["target"]]=identity(target)
            workspace_record(base,pin,row["target"],"installed",target)
        require(controls(m)==preserved,"protected_settings_changed_during_owner_phase")
        native.start();native.verify();native.zero()
        native.state()
        require(tree(layout.core)==action["files"] and controls(m)==preserved
                and all(identity(workspace_path(layout,name))==g for name,g in generations.items()),
                "final_code_or_settings_rejected")
        result.update(status="delegated_"+mode+"_passed",core_source=action["source_commit"],native_human_acceptance=False)
    except (Stop,OSError,subprocess.SubprocessError) as e:
        # npm is not atomic. Unknown/partial package results must not trigger a second npm.
        result.update(status="stopped_owner_operation_review_required_no_retry",error=str(e) if isinstance(e,Stop) else "native_observation_indeterminate",
                      rollback="explicit_snapshot_only_after_complete_generation_and_idle_job_proof")
    private_write(base/("receipt-"+str(time.time_ns())+".json"),(json.dumps(result,sort_keys=True)+"\n").encode())
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",nargs="?",default="verify",choices=("verify","plan","observe","apply","rollback"))
    p.add_argument("--inputs",required=True);p.add_argument("--snapshot");p.add_argument("--snapshot-sha256")
    a=p.parse_args(argv)
    try:
        root,m=load_inputs(a.inputs)
        if a.mode in ("verify","plan"):
            result={"status":"offline_inputs_verified_not_native_acceptance","workflow_source":WORKFLOW_COMMIT,
                    "core_after_source":m["after"]["source_commit"],"preserve":"current model/defaults/config/external plugins/runtime DB/ledger",
                    "apply_argv":["python3","-B",str(Path(__file__).resolve()),"apply","--inputs",str(Path(a.inputs).resolve())],
                    "rollback_argv_requires_actual_snapshot":True,"native_execution":False}
        elif a.mode=="observe":
            result=observe_installed(m,Layout())
        else:
            require(os.geteuid()==0,"existing_operator_root_privilege_required")
            fd=os.open("/root/.crustacea-core-workspace-recovery.lock",os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"w") as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                result=execute(a.mode,root,m,Native(root,m),Layout(),a.snapshot,a.snapshot_sha256)
        print(json.dumps(result,sort_keys=True));return 0 if "passed" in result["status"] or a.mode in ("verify","plan","observe") or result["status"]=="delegated_rollback_already_restored" else 1
    except (Stop,OSError,ValueError,KeyError,TypeError,tarfile.TarError) as e:
        print(json.dumps({"status":"missing_or_invalid_prerequisite_no_mutation","error":str(e) if isinstance(e,Stop) else "owner_input_or_native_schema_invalid"}));return 2


if __name__=="__main__":raise SystemExit(main())
