#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
"""Restore a verified installed closure, never re-resolve dependencies or rewind state."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

BASE_SHA = "d4c8606c0b3206a8903d4e58bcc4651214e43e00ade749d0dad34b4105774f3f"
HERE = Path(__file__).resolve().parent
if hashlib.sha256((HERE/"core-workspace-recovery.py").read_bytes()).hexdigest() != BASE_SHA:
    raise SystemExit("accepted_base_helper_changed")
spec = importlib.util.spec_from_file_location("accepted_core", HERE/"core-workspace-recovery.py")
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
ROOT = "/usr/lib/node_modules/openclaw"
LINK = "/usr/bin/openclaw"
SCHEMA = "crustacea-captured-core-phase-v1"
PATCHERS = ("oc-corpus-noise-filter-patch.py", "oc-corpus-taint-filter-patch.py",
            "oc-rem-narrative-firegate-patch.py", "oc-narrative-timeout-extend-patch.py")
PATCH_SHA = dict(zip(PATCHERS, (
    "dc73c56899332816cbc9887b8c0f82b55f91f1cda36b0048ae1497186fd8b486",
    "bfb69d7c14f6a95855eb4791ee16b139f41759c4190cb3cfcacf78a8a31e5a49",
    "7989b4a2a07cf86b389a9bc22643e6807297d9c9cea06704fd3b779271169c23",
    "4273afbe1b28e640028739737cd31a382e169a5f74c64dc159343841643987e6")))
VERIFIER_SHA = "44340e030e40770416bf1dbec9bac5b84efcf5868ed3c22701c70291e38234e5"


def normalized(value):
    p = PurePosixPath(value)
    d.require(isinstance(value, str) and ".." not in p.parts and str(p) == value
              and (value == LINK or value == ROOT or p.is_relative_to(ROOT)), "closure_scope_invalid")
    return value


def metadata(path, physical=False):
    s = path.lstat()
    row = {"mode": stat.S_IMODE(s.st_mode), "uid": s.st_uid, "gid": s.st_gid}
    if stat.S_ISREG(s.st_mode):
        row.update(type="file", size=s.st_size, sha256=d.digest(path))
    elif stat.S_ISLNK(s.st_mode):
        row.update(type="symlink", target=os.readlink(path))
    elif stat.S_ISDIR(s.st_mode):
        row.update(type="directory")
    else:
        raise d.Stop("special_code_object_forbidden")
    if physical:
        after = path.lstat()
        d.require((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_gid)
                  == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns,
                      after.st_mode,after.st_uid,after.st_gid), "code_changed_during_hash")
        row.update(dev=s.st_dev, ino=s.st_ino, mtime_ns=s.st_mtime_ns)
    return row


def comparable(row):
    fields = ("type", "mode", "uid", "gid")
    fields += ("sha256", "size") if row["type"] == "file" else ("target",) if row["type"] == "symlink" else ()
    return {key: row[key] for key in fields}


def inventory(layout, physical=False):
    d.require(layout.core.is_dir() and not layout.core.is_symlink()
              and layout.core.parent.resolve()==layout.core.parent
              and layout.entrypoint.parent.resolve()==layout.entrypoint.parent,"native_code_root_or_ancestor_invalid")
    rows = {}
    for directory, names, files in os.walk(layout.core, followlinks=False):
        base = Path(directory)
        for path in [base]+[base/name for name in names+files if (base/name).is_symlink() or not (base/name).is_dir()]:
            name = ROOT + ("/"+str(path.relative_to(layout.core)) if path != layout.core else "")
            rows[name] = metadata(path, physical)
    d.require(ROOT in rows and layout.entrypoint.is_symlink(), "existing_core_launcher_required")
    rows[LINK] = metadata(layout.entrypoint, physical)
    return rows


def body_hash(rows):
    return d.manifest_digest({name: comparable(row) for name,row in rows.items()})


def local_path(layout, name):
    normalized(name)
    return layout.entrypoint if name == LINK else layout.core/PurePosixPath(name).relative_to(ROOT)


def validate_records(records):
    rows = {}
    for row in records:
        name = normalized(row["path"])
        d.require(name not in rows and row["type"] in ("file","directory","symlink"), "closure_duplicate_or_type_invalid")
        for field in ("mode","uid","gid"):
            d.require(type(row[field]) is int and row[field] >= 0, "closure_metadata_invalid")
        d.require(row["mode"] <= 0o7777, "closure_mode_invalid")
        if row["type"] == "file":
            d.require(type(row["size"]) is int and row["size"] >= 0 and d.SHA.fullmatch(row["sha256"]), "closure_file_invalid")
        if row["type"] == "symlink":
            target = row["target"]
            d.require(isinstance(target,str) and target and not target.startswith("/"), "closure_link_invalid")
            resolved = Path(os.path.normpath(str(PurePosixPath(name).parent/target)))
            d.require(resolved == Path(ROOT) or resolved.is_relative_to(ROOT), "closure_link_escape")
        rows[name] = comparable(row)
    d.require(rows.get(ROOT,{}).get("type") == "directory" and rows.get(LINK,{}).get("type") == "symlink",
              "closure_roots_or_launcher_missing")
    for name in rows:
        if name not in (ROOT,LINK):
            parent = str(PurePosixPath(name).parent)
            d.require(rows.get(parent,{}).get("type") == "directory", "closure_parent_missing_or_symlink")
    d.require(rows[LINK]["target"] == "../lib/node_modules/openclaw/openclaw.mjs", "native_launcher_spelling_changed")
    return rows


def verify_archive(path, rows):
    seen = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = normalized("/"+member.name.removeprefix("./"))
            d.require(name not in seen and (member.isfile() or member.isdir() or member.issym()),
                      "closure_archive_duplicate_or_special")
            row = {"type":"file" if member.isfile() else "directory" if member.isdir() else "symlink",
                   "mode":member.mode, "uid":member.uid, "gid":member.gid, "path":name}
            if member.isfile():
                h=hashlib.sha256()
                stream=archive.extractfile(member)
                for block in iter(lambda:stream.read(131072),b""):h.update(block)
                row.update(size=member.size,sha256=h.hexdigest())
            if member.issym():row["target"]=member.linkname
            seen[name]=row
    d.require(validate_records(list(seen.values())) == rows, "closure_archive_manifest_mismatch")


def load_inputs(path):
    root=Path(path).resolve().parent
    m=json.loads(d.regular(path).read_bytes())
    d.require(m.get("schema")==SCHEMA and m.get("base_source")=="bdd99b1827360ce72d00b8d30bc0acc346cb27af",
              "captured_phase_owner_packet_required")
    owner_native = m.get("native_gate_contract") == {"kind": "vip-owner-native-v1", "owner_receipt_sha256": "1a0e7d55123e0da725e27716ed13e44969a6404c6cf001bf5c5b0987524c16f2"}
    required = ("closure", "expected_current_sha256", "protected", "retention_verifier_sha256", "patchers", "patch_targets", "workspace")
    for key in required + (() if owner_native else ("zero_checker", "ready_checker")):
        d.require(key in m, "missing_"+key)
    d.require(set(m["protected"]) >= set(d.PROTECTED), "current_native_controls_required")
    for value in m["protected"].values():d.require(d.SHA.fullmatch(value), "control_pin_invalid")
    d.require(d.SHA.fullmatch(m["expected_current_sha256"]), "current_closure_CAS_required")
    closure=m["closure"]
    closure_root=Path(closure["root"])
    d.require(closure_root.is_absolute() and closure_root.resolve()==closure_root and closure_root.is_dir(),
              "retained_closure_absolute_root_required")
    for key in ("archive", "manifest", "receipt"):
        d.require(d.digest(d.packet_file(closure_root,closure[key]))==closure[key+"_sha256"], "closure_"+key+"_changed")
    declared=json.loads(d.packet_file(closure_root,closure["manifest"]).read_bytes())
    d.require(declared.get("schema")=="crustacea-installed-closure-archive-v1", "closure_manifest_schema_invalid")
    rows=validate_records(declared["records"])
    receipt=json.loads(d.packet_file(closure_root,closure["receipt"]).read_bytes())
    d.require(receipt.get("schema")=="crustacea-installed-closure-receipt-v1"
              and receipt["archive"]["sha256"]==closure["archive_sha256"]
              and receipt["inventories"]["archiveManifestSha256"]==closure["manifest_sha256"]
              and receipt["inventories"]["archiveMatchesDisk"] is True
              and receipt["inventories"]["byteEqual"] is True
              and receipt["serviceUnchanged"] is True, "closure_capture_receipt_binding_invalid")
    verify_archive(d.packet_file(closure_root,closure["archive"]), rows)
    d.require(tuple(p["name"] for p in m["patchers"]) == PATCHERS, "four_retained_patcher_order_required")
    for p in m["patchers"]:
        d.require(p["sha256"]==PATCH_SHA[p["name"]]
                  and d.digest(d.packet_file(root,p["source"]))==p["sha256"],
                  "retained_patcher_changed")
    d.require(set(m["patch_targets"])=={"session-ingestion","dreaming-phases","dreaming-narrative"}, "retained_patch_targets_required")
    for prefix,target in m["patch_targets"].items():
        name=normalized(target)
        d.require(name.startswith(ROOT+"/dist/"+prefix+"-") and rows[name]["type"]=="file", "retained_patch_target_invalid")
    for key in (() if owner_native else ("zero_checker","ready_checker")):
        z=m[key]
        d.require(set(z)=={"path","sha256","runner","args"} and z["runner"] in ("python3","bash","sh")
                  and isinstance(z["args"],list) and len(z["args"])<=16
                  and all(isinstance(a,str) and d.re.fullmatch("[A-Za-z0-9_./:@=,+-]+",a) for a in z["args"]),
                  "existing_owner_checker_typed_contract_required")
        d.require(d.digest(d.packet_file(root,z["path"]))==z["sha256"],
                  "existing_owner_observation_contract_changed")
    d.require(m["retention_verifier_sha256"]==VERIFIER_SHA
              and d.digest(d.regular(root/"verify-all.sh"))==m["retention_verifier_sha256"],
              "full_retention_verifier_changed")
    seen=set()
    for row in m["workspace"]:
        name=str(d.relative(row["target"]))
        d.require(name.startswith("skills/") and name not in seen and d.SHA.fullmatch(row["before_sha256"]), "existing_static_skill_CAS_required")
        seen.add(name)
        d.require(d.digest(d.packet_file(root,row["source"]))==row["sha256"], "static_skill_payload_changed")
    return root,m,rows


def fsync_dir(path):
    fd=os.open(path,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def capture(base, layout, physical):
    archive_path=base/"captured-core-launcher.tar.gz"
    with tarfile.open(archive_path,"x:gz",format=tarfile.PAX_FORMAT) as archive:
        for name,row in sorted(physical.items()):
            path=local_path(layout,name)
            info=tarfile.TarInfo(name.removeprefix("/"))
            info.mode=row["mode"];info.uid=row["uid"];info.gid=row["gid"]
            info.mtime=row["mtime_ns"]/1e9
            if row["type"]=="directory":info.type=tarfile.DIRTYPE
            elif row["type"]=="symlink":info.type=tarfile.SYMTYPE;info.linkname=row["target"]
            else:info.type=tarfile.REGTYPE;info.size=row["size"]
            if row["type"]=="file":
                with path.open("rb") as stream:archive.addfile(info,stream)
            else:archive.addfile(info)
    archive_path.chmod(0o600)
    with archive_path.open("rb") as stream:os.fsync(stream.fileno())
    fsync_dir(base)
    d.require(inventory(layout,True)==physical, "live_code_changed_during_capture")
    rows={n:comparable(r) for n,r in physical.items()}
    verify_archive(archive_path, rows)
    return archive_path, rows


def extract_pair(archive_path, rows, layout):
    work=Path(tempfile.mkdtemp(prefix=".openclaw-prepared-",dir=layout.core.parent));work.chmod(0o700)
    linkwork=Path(tempfile.mkdtemp(prefix=".openclaw-launcher-",dir=layout.entrypoint.parent));linkwork.chmod(0o700)
    prepared=d.Layout();prepared.core=work/"core";prepared.entrypoint=linkwork/"openclaw"
    prepared.workspace=layout.workspace;prepared.backups=layout.backups
    seen=set();times={}
    with tarfile.open(archive_path,"r:gz") as archive:
        members=archive.getmembers()
        for member in sorted(members,key=lambda v:len(PurePosixPath(v.name).parts)):
            name=normalized("/"+member.name.removeprefix("./"))
            d.require(name in rows and name not in seen,"extract_scope_or_duplicate")
            seen.add(name);row=rows[name];path=local_path(prepared,name)
            d.require(path.parent.is_dir() and not path.parent.is_symlink(),"extract_parent_invalid")
            if row["type"]=="directory":
                path.mkdir(mode=0o700)
            elif row["type"]=="symlink":
                path.symlink_to(row["target"]);os.chown(path,row["uid"],row["gid"],follow_symlinks=False)
            else:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                h=hashlib.sha256();stream=archive.extractfile(member)
                with os.fdopen(fd,"wb") as target:
                    for block in iter(lambda:stream.read(131072),b""):target.write(block);h.update(block)
                    d.require(h.hexdigest()==row["sha256"] and target.tell()==row["size"],"prepared_file_hash_changed")
                    target.flush();os.fchown(target.fileno(),row["uid"],row["gid"])
                    os.fchmod(target.fileno(),row["mode"]);os.fsync(target.fileno())
            times[name]=member.mtime
    d.require(seen==set(rows),"prepared_manifest_coverage_incomplete")
    for name,row in sorted(rows.items(),key=lambda v:len(PurePosixPath(v[0]).parts),reverse=True):
        path=local_path(prepared,name)
        if row["type"]=="directory":
            os.chown(path,row["uid"],row["gid"]);path.chmod(row["mode"]);fsync_dir(path)
        os.utime(path,ns=(int(times[name]*1e9),int(times[name]*1e9)),follow_symlinks=False)
        if row["type"]!="symlink":
            fd=os.open(path,os.O_RDONLY | (os.O_DIRECTORY if row["type"]=="directory" else 0))
            try:os.fsync(fd)
            finally:os.close(fd)
        fsync_dir(path.parent)
    d.require({n:comparable(r) for n,r in inventory(prepared).items()}==rows,"prepared_full_closure_mismatch")
    fsync_dir(work);fsync_dir(linkwork)
    return prepared


def patch_staging(root,m,rows,prepared):
    before=inventory(prepared)
    dist=prepared.core/"dist"
    for p in m["patchers"]:
        script=d.packet_file(root,p["source"])
        d.require(p["sha256"]==PATCH_SHA[p["name"]] and d.digest(script)==p["sha256"],"retained_patcher_changed_before_execution")
        args=[sys.executable,"-B",str(script)]
        if p["name"] in PATCHERS[:2]:
            target=local_path(prepared,m["patch_targets"]["session-ingestion"])
            args.extend((str(target),str(target)))
        env=dict(os.environ,OPENCLAW_DIST=str(dist))
        result=subprocess.run(args,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=45)
        d.require(result.returncode==0,"retained_staging_patcher_failed")
    d.require(inventory(prepared)==before
              and {n:comparable(r) for n,r in before.items()}==rows,
              "captured_patched_closure_bytes_or_metadata_changed")
    verifier=d.regular(root/"verify-all.sh")
    d.require(d.digest(verifier)==m["retention_verifier_sha256"],"retention_verifier_changed_before_staged_gate")
    result=subprocess.run(["/bin/bash",str(verifier)],env=dict(os.environ,OPENCLAW_DIST=str(dist)),
                          stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45)
    d.require(result.returncode==0,"full_staged_retention_verifier_failed")


def journal(base,pin,phase,**fields):
    path=base/(str(time.time_ns())+"-"+phase+".json")
    d.private_write(path,(json.dumps({"snapshot_sha256":pin,"phase":phase,**fields},sort_keys=True)+"\n").encode())


def journals(base,pin):
    result=[]
    for path in sorted(base.glob("[0-9]*-*.json")):
        s=d.regular(path).stat()
        d.require(s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o600,"transaction_journal_metadata_changed")
        row=json.loads(path.read_bytes())
        d.require(row.get("snapshot_sha256")==pin,"transaction_journal_snapshot_changed")
        result.append(row)
    return result


def pair_owned(base,pin,current,snapshot):
    if current==snapshot["physical_before"]:return True
    return any(row.get("physical")==current or row.get("final_physical")==current for row in journals(base,pin)
               if row["phase"] in ("prepared","installed","restore_prepared","restored"))


def require_stopped(native):
    state=native.state()
    d.require(state.get("MainPID")=="0" and state.get("ActiveState") in ("inactive","failed")
              and state.get("SubState") in ("dead","failed"),"native_unit_not_authoritatively_stopped")


def gate(m,native,layout,expected,static):
    require_stopped(native);native.zero();d.controls(m)
    d.require(inventory(layout,True)==expected,"foreign_code_generation_no_overwrite")
    for name,value in static.items():
        d.require(d.identity(d.workspace_path(layout,name))==value,"foreign_static_generation_no_overwrite")


def switch_pair(base,pin,mode,m,native,layout,prepared,expected,static):
    gate(m,native,layout,expected,static)
    candidate=inventory(prepared,True)
    # Native launcher spelling/metadata already agrees: keep its physical generation.
    same_link=comparable(candidate[LINK])==comparable(expected[LINK])
    if same_link:candidate[LINK]=expected[LINK]
    phase="restore_prepared" if mode=="rollback" else "prepared"
    journal(base,pin,phase,physical={**candidate,LINK:expected[LINK]},final_physical=candidate)
    gate(m,native,layout,expected,static)
    retired=prepared.core.parent/"retired"
    journal(base,pin,"retire_prepared",physical=expected,retired=str(retired),mode=mode)
    gate(m,native,layout,expected,static)
    os.replace(layout.core,retired);fsync_dir(layout.core.parent);fsync_dir(retired.parent)
    # Only our exact retired generation may explain the temporary missing root.
    old=d.Layout();old.core=retired;old.entrypoint=layout.entrypoint
    d.require(not layout.core.exists() and not layout.core.is_symlink()
              and inventory(old,True)==expected,"foreign_or_missing_root_during_pair_switch")
    require_stopped(native);native.zero();d.controls(m)
    for name,value in static.items():d.require(d.identity(d.workspace_path(layout,name))==value,"static_drift_before_core_replace")
    d.require(not layout.core.exists() and not layout.core.is_symlink()
              and inventory(old,True)==expected,"foreign_generation_at_prepared_replace_boundary")
    os.replace(prepared.core,layout.core);fsync_dir(layout.core.parent)
    interim={**candidate,LINK:expected[LINK]}
    gate(m,native,layout,interim,static)
    if not same_link:
        os.replace(prepared.entrypoint,layout.entrypoint);fsync_dir(layout.entrypoint.parent)
    d.require(inventory(layout,True)==candidate,"pair_postimage_generation_rejected")
    journal(base,pin,"restored" if mode=="rollback" else "installed",physical=candidate)
    return candidate


class Native(d.Native):
    def ready(self):
        z=self.m["ready_checker"];path=d.packet_file(self.root,z["path"])
        d.require(d.digest(path)==z["sha256"],"accepted_runtime_readiness_checker_changed")
        runners={"python3":["/usr/bin/python3","-B"],"bash":["/bin/bash"],"sh":["/bin/sh"]}
        self.run(runners[z["runner"]]+[str(path)]+z["args"])


class OwnerNative(Native):
    """Only the maintained coordinator injects these trusted native operations."""
    def __init__(self, root, m, gates):
        d.require(all(callable(getattr(gates, k, None)) for k in ("zero", "ready", "preservation")), "trusted_native_owner_interface_required")
        super().__init__(root, m)
        self.gates = gates
        self.owner_expected = None
    def zero(self):
        self.gates.zero()
    def ready(self):
        self.gates.ready()
        d.require(self.gates.preservation() == self.owner_expected, "owner_plugin_controls_projection_changed")
    def owner_capture(self):
        self.owner_expected = self.gates.preservation()
        return self.owner_expected
    def owner_restore(self, value):
        d.require(isinstance(value, dict), "captured_owner_projection_required")
        self.owner_expected = value


def snapshot_load(base,pin,layout,m):
    d.require(base.is_absolute() and base.parent==layout.backups and base.resolve()==base
              and base.name.startswith("crustacea-core-recovery-")
              and base.stat().st_uid==os.geteuid() and stat.S_IMODE(base.stat().st_mode)==0o700,
              "owned_protected_snapshot_required")
    path=d.regular(base/"snapshot.json");s=path.stat()
    d.require(s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o600
              and d.SHA.fullmatch(pin or "") and d.digest(path)==pin,"protected_snapshot_pin_changed")
    value=json.loads(path.read_bytes())
    d.require(value.get("schema")==SCHEMA and value.get("protected")==m["protected"]
              and value.get("closure")==closure_pins(m)
              and value.get("phase_helper_sha256")==d.digest(__file__) and value.get("config_restored") is False
              and value.get("DB_restored") is False,"snapshot_phase_or_controls_changed")
    archived=d.regular(base/"captured-core-launcher.tar.gz");s=archived.stat()
    d.require(stat.S_IMODE(s.st_mode)==0o600 and s.st_uid==os.geteuid()
              and d.digest(archived)==value["captured_archive_sha256"],"exact_captured_archive_changed")
    rows=validate_records([{"path":n,**r} for n,r in value["before"].items()])
    verify_archive(archived,rows)
    for i,row in enumerate(value["workspace"]):
        path=d.regular(base/(str(i)+".before"));s=path.stat()
        d.require(s.st_uid==os.geteuid() and stat.S_IMODE(s.st_mode)==0o600
                  and d.digest(path)==row["before"]["sha256"],"captured_static_file_changed")
    return value,archived,rows


def repair_missing_root(base,pin,m,native,layout,snapshot):
    if layout.core.exists() or layout.core.is_symlink():return
    row=next((r for r in reversed(journals(base,pin)) if r["phase"]=="retire_prepared"),None)
    d.require(row is not None,"missing_core_without_own_retire_journal")
    retired=Path(row["retired"])
    d.require(retired.name=="retired" and retired.parent.parent==layout.core.parent
              and retired.parent.name.startswith(".openclaw-prepared-")
              and retired.parent.resolve()==retired.parent
              and stat.S_IMODE(retired.parent.stat().st_mode)==0o700
              and retired.parent.stat().st_uid==os.geteuid(),"retired_generation_path_invalid")
    old=d.Layout();old.core=retired;old.entrypoint=layout.entrypoint
    expected=row["physical"]
    require_stopped(native);native.zero();d.controls(m)
    d.require(inventory(old,True)==expected,"retired_generation_foreign_no_restore")
    journal(base,pin,"restore_prepared",physical=expected)
    require_stopped(native);native.zero();d.controls(m)
    d.require(not layout.core.exists() and not layout.core.is_symlink()
              and inventory(old,True)==expected,"missing_root_restore_CAS_changed")
    os.replace(retired,layout.core);fsync_dir(layout.core.parent);fsync_dir(retired.parent)
    journal(base,pin,"restored",physical=inventory(layout,True))


def static_current(base,pin,snapshot,layout,allow_before=False):
    result={}
    for row in snapshot["workspace"]:
        current=d.identity(d.workspace_path(layout,row["target"]))
        d.require(d.workspace_owned(base,pin,row["target"],current,row["before"]) if allow_before
                  else current==row["before"],"foreign_static_generation_no_overwrite")
        result[row["target"]]=current
    return result


def restore_static(base,pin,m,native,layout,snapshot,physical,static):
    for i,row in enumerate(snapshot["workspace"]):
        target=d.workspace_path(layout,row["target"])
        if static[row["target"]]==row["before"]:continue
        old=row["before"];data=d.regular(base/(str(i)+".before")).read_bytes()
        d.require(hashlib.sha256(data).hexdigest()==old["sha256"],"captured_static_blob_changed")
        def prepared(path):
            d.workspace_record(base,pin,row["target"],"restore_prepared",path)
            gate(m,native,layout,physical,static)
        gate(m,native,layout,physical,static)
        d.atomic(target,data,old["uid"],old["gid"],old["mode"],prepared)
        static[row["target"]]=d.identity(target)
        d.workspace_record(base,pin,row["target"],"restored",target)


def postflight(m,native,layout,rows,static):
    native.verify();native.zero();native.ready()
    state=native.state()
    d.require(state.get("ActiveState")=="active" and state.get("SubState")=="running"
              and state.get("MainPID","").isdigit() and int(state["MainPID"])>0,"runtime_not_ready")
    d.controls(m)
    d.require({n:comparable(r) for n,r in inventory(layout).items()}==rows,"final_restored_code_hash_or_metadata_rejected")
    for name,value in static.items():d.require(d.identity(d.workspace_path(layout,name))==value,"postflight_static_generation_changed")


def restore(base,pin,m,native,layout,snapshot,archive,rows):
    # State observation precedes any second systemd operation; an active job fails closed.
    state=native.state();native.zero();d.controls(m)
    static=static_current(base,pin,snapshot,layout,True)
    repair_missing_root(base,pin,m,native,layout,snapshot)
    current=inventory(layout,True)
    d.require(pair_owned(base,pin,current,snapshot),"foreign_core_generation_no_recovery_mutation")
    already=body_hash(current)==body_hash(rows) and all(
        comparable_static(static[r["target"]])==comparable_static(r["before"]) for r in snapshot["workspace"])
    if already and state.get("ActiveState")=="active":
        postflight(m,native,layout,rows,static)
        return "captured_rollback_already_restored"
    prepared=extract_pair(archive,rows,layout)
    d.require(inventory(layout,True)==current,"core_drift_during_restore_prepare")
    if state.get("ActiveState") not in ("inactive","failed") or state.get("MainPID")!="0":
        native.state();native.zero();d.controls(m)
        d.require(inventory(layout,True)==current,"core_drift_before_restore_stop")
        native.stop()
    gate(m,native,layout,current,static)
    restored=switch_pair(base,pin,"rollback",m,native,layout,prepared,current,static)
    restore_static(base,pin,m,native,layout,snapshot,restored,static)
    gate(m,native,layout,restored,static)
    native.start()
    postflight(m,native,layout,rows,static)
    journal(base,pin,"rollback_passed",core_manifest_sha256=body_hash(restored))
    return "captured_rollback_passed"


def comparable_static(value):
    return {k:value[k] for k in ("sha256","uid","gid","mode","size")}


def safe_error(error):
    return str(error) if isinstance(error,d.Stop) else "native_observation_or_filesystem_indeterminate"


def execute(mode,root,m,rows,native,layout,backup=None,pin=None):
    preserved=d.controls(m);native.zero();native.state()
    if mode=="rollback":
        base=Path(backup or "")
        snapshot,archive,before=snapshot_load(base,pin,layout,m)
        if isinstance(native, OwnerNative): native.owner_restore(snapshot.get("owner_preservation"))
        result={"snapshot":str(base),"snapshot_sha256":pin,"DB_restored":False,"config_restored":False,"native_human_acceptance":False}
        try:result["status"]=restore(base,pin,m,native,layout,snapshot,archive,before)
        except (d.Stop,OSError,subprocess.SubprocessError) as error:
            result.update(status="rollback_deferred_no_retry",rollback_error=safe_error(error))
        journal(base,pin,"rollback_receipt",result=result)
        return result
    native.verify()
    owner_preservation = native.owner_capture() if isinstance(native, OwnerNative) else None
    physical=inventory(layout,True)
    d.require(body_hash(physical)==m["expected_current_sha256"],"current_full_closure_CAS_changed")
    # A failed install may need a second prepared tree plus the durable capture.
    estimate=sum(r.get("size",0) for r in rows.values())*2 + sum(r.get("size",0) for r in physical.values())
    estimate+=len(json.dumps(physical))*8+16*1024*1024
    for parent in (layout.core.parent,layout.entrypoint.parent,layout.backups):
        space=os.statvfs(parent)
        d.require(space.f_bavail*space.f_frsize>=estimate,"insufficient_capture_restore_headroom_no_mutation")
    base=Path(tempfile.mkdtemp(prefix="crustacea-core-recovery-",dir=layout.backups));base.chmod(0o700)
    archive,before=capture(base,layout,physical)
    static=[]
    for i,row in enumerate(m["workspace"]):
        path=d.workspace_path(layout,row["target"]);value=d.identity(path)
        d.require(value["sha256"]==row["before_sha256"],"static_preimage_changed")
        d.private_write(base/(str(i)+".before"),path.read_bytes())
        static.append({"target":row["target"],"before":value,"after":row["sha256"]})
    snapshot={"schema":SCHEMA,"closure":closure_pins(m),"phase_helper_sha256":d.digest(__file__),
              "closure_acquisition_root":m["closure"]["root"],"protected":preserved,"before":before,"physical_before":physical,
              "captured_archive_sha256":d.digest(archive),"workspace":static,"config_restored":False,"DB_restored":False}
    if owner_preservation is not None: snapshot["owner_preservation"] = owner_preservation
    d.private_write(base/"snapshot.json",(json.dumps(snapshot,sort_keys=True)+"\n").encode());pin=d.digest(base/"snapshot.json")
    result={"snapshot":str(base),"snapshot_sha256":pin,"DB_restored":False,"config_restored":False,"native_human_acceptance":False}
    try:
        closure_root=Path(m["closure"]["root"]);source=d.packet_file(closure_root,m["closure"]["archive"])
        d.require(d.digest(source)==m["closure"]["archive_sha256"],"closure_changed_before_prepare")
        prepared=extract_pair(source,rows,layout);patch_staging(root,m,rows,prepared)
        static_now=static_current(base,pin,snapshot,layout)
        d.require(inventory(layout,True)==physical,"live_core_changed_during_preparation")
        native.state();native.zero();d.controls(m);native.stop()
        gate(m,native,layout,physical,static_now)
        installed=switch_pair(base,pin,"apply",m,native,layout,prepared,physical,static_now)
        for i,row in enumerate(static):
            path=d.workspace_path(layout,row["target"]);data=d.packet_file(root,m["workspace"][i]["source"]).read_bytes()
            d.require(hashlib.sha256(data).hexdigest()==row["after"],"static_payload_changed_before_IO")
            def record(path):
                d.workspace_record(base,pin,row["target"],"prepared",path)
                gate(m,native,layout,installed,static_now)
            gate(m,native,layout,installed,static_now)
            old=row["before"];d.atomic(path,data,old["uid"],old["gid"],old["mode"],record)
            static_now[row["target"]]=d.identity(path)
            d.workspace_record(base,pin,row["target"],"installed",path)
        gate(m,native,layout,installed,static_now);native.start()
        postflight(m,native,layout,rows,static_now)
        result["status"]="captured_install_passed"
    except (d.Stop,OSError,subprocess.SubprocessError) as error:
        result.update(status="captured_install_failed",primary_error=safe_error(error))
        try:result["rollback_status"]=restore(base,pin,m,native,layout,snapshot,archive,before)
        except (d.Stop,OSError,subprocess.SubprocessError) as rollback_error:
            result.update(rollback_status="deferred_no_retry",rollback_error=safe_error(rollback_error))
    journal(base,pin,"install_receipt",result=result)
    return result


def closure_pins(m):
    return {key:m["closure"][key] for key in ("archive_sha256","manifest_sha256","receipt_sha256")}


def main(argv=None, native_gates=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",nargs="?",default="verify",choices=("verify","plan","observe","apply","rollback"))
    parser.add_argument("--inputs",required=True);parser.add_argument("--snapshot");parser.add_argument("--snapshot-sha256")
    args=parser.parse_args(argv)
    try:
        root,m,rows=load_inputs(args.inputs)
        if args.mode in ("verify","plan"):
            result={"status":"offline_exact_closure_verified","archive_sha256":m["closure"]["archive_sha256"],
                    "core_manifest_sha256":body_hash(rows),"native_execution":False,"not_loaded_module_proof":True,
                    "dependency_resolution":False,"config_restored":False,"DB_restored":False}
        elif args.mode=="observe":
            d.controls(m)
            result={"status":"installed_code_observed","core_manifest_sha256":body_hash(inventory(d.Layout())),
                    "workspace":{row["target"]:d.digest(d.workspace_path(d.Layout(),row["target"])) for row in m["workspace"]},
                    "native_execution":False,"not_loaded_module_proof":True}
        else:
            owner_native = "native_gate_contract" in m
            if owner_native: d.require(native_gates is not None, "trusted_native_owner_interface_required")
            d.require(os.geteuid()==0,"existing_operator_root_privilege_required")
            fd=os.open("/root/.crustacea-core-workspace-recovery.lock",os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"w") as lock:
                d.fcntl.flock(lock,d.fcntl.LOCK_EX|d.fcntl.LOCK_NB)
                native = OwnerNative(root,m,native_gates) if owner_native else Native(root,m)
                result=execute(args.mode,root,m,rows,native,d.Layout(),args.snapshot,args.snapshot_sha256)
        print(json.dumps(result,sort_keys=True))
        return 0 if result["status"] in ("offline_exact_closure_verified","installed_code_observed","captured_install_passed",
                                        "captured_rollback_passed","captured_rollback_already_restored") else 1
    except (d.Stop,OSError,ValueError,KeyError,TypeError,tarfile.TarError) as error:
        print(json.dumps({"status":"blocked_no_mutation","error":safe_error(error)}));return 2


if __name__=="__main__":raise SystemExit(main())
