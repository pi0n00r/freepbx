#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=VIP
"""VIP component recovery delegation. Default offline; no application-state restore."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

BINDINGS_SHA = "1511b810a3cb01df3f14eb94d56c8fe63ca9aabb7ef5784da7caa67b5f29b5ca"
SAFE = re.compile(r"[A-Za-z0-9_./:@=,+-]+\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
ENDPOINT = "https://vip.bajaj.com/aimee-router"


class Stop(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(value, code):
    if not value:
        raise Stop(code)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(131072), b""):
            h.update(chunk)
    return h.hexdigest()


def bindings():
    p = Path(__file__).resolve().parent.parent / "component-bindings-20260914.json"
    require(digest(p) == BINDINGS_SHA, "bindings_identity_changed")
    return json.loads(p.read_bytes())


def safe_path(value):
    require(isinstance(value, str) and SAFE.fullmatch(value) is not None, "unsafe_path")
    p = Path(value)
    require(p.is_absolute() and ".." not in p.parts and str(p) == value, "unsafe_path")
    return p


def confined(root, name):
    p = PurePosixPath(name)
    require(name not in ("", ".") and not p.is_absolute() and ".." not in p.parts, "path_rejected")
    out = root / p
    require(out.resolve().is_relative_to(root.resolve()) and not out.is_symlink(), "path_escape_or_symlink")
    return out


def sha_manifest(data, *, require_sorted=True):
    rows, names = {}, []
    for line in data.decode("utf-8").splitlines():
        require(len(line) > 66 and SHA.fullmatch(line[:64]) is not None and line[64:66] in ("  ", " *"), "manifest_format")
        name = line[66:].removeprefix("./")
        confined(Path("/manifest-root"), name)
        require(name not in rows, "manifest_duplicate")
        names.append(name)
        rows[name] = line[:64]
    require(not require_sorted or names == sorted(names), "manifest_not_sorted")
    return rows


def archive_rows(path):
    rows, roots, names = {}, set(), set()
    with tarfile.open(path, "r:gz") as archive:
        for m in archive:
            name = m.name.removeprefix("./").rstrip("/")
            p = PurePosixPath(name)
            require(name and not p.is_absolute() and ".." not in p.parts and name not in names, "archive_path_or_duplicate")
            names.add(name)
            roots.add(p.parts[0])
            require(m.isfile() or m.isdir(), "archive_nonregular_entry")
            if m.isfile():
                h = hashlib.sha256()
                stream = archive.extractfile(m)
                for chunk in iter(lambda: stream.read(131072), b""):
                    h.update(chunk)
                rows[str(PurePosixPath(*p.parts[1:]))] = (h.hexdigest(), m.mode & 0o777)
    require(len(roots) == 1, "archive_root_rejected")
    return next(iter(roots)), rows


def native_capture_rows(path):
    """Hash regular tar members and retain recovery metadata without extracting."""
    rows, names = {}, set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = member.name.removeprefix("./").rstrip("/")
            p = PurePosixPath(name)
            require(name and not p.is_absolute() and ".." not in p.parts and name not in names,
                    "native_capture_path_or_duplicate")
            names.add(name)
            require(member.isfile(), "native_capture_nonregular_entry")
            h = hashlib.sha256()
            stream = archive.extractfile(member)
            for chunk in iter(lambda: stream.read(131072), b""):
                h.update(chunk)
            rows[name] = (h.hexdigest(), member.size, member.mode & 0o7777,
                          member.uid, member.gid)
    return rows


def verify_rita_current_config(root, b):
    """Verify the private total-loss capture by hashes and metadata only."""
    s = b["components"]["rita"]["current_config_capture"]
    root = safe_path(str(root))
    require(root.is_dir() and not root.is_symlink(), "current_Rita_config_capture_missing")
    archive = confined(root, s["archive"])
    require(archive.is_file() and digest(archive) == s["archive_sha256"],
            "current_Rita_config_archive_changed")
    expected = {name: tuple(row) for name, row in s["members"].items()}
    require(native_capture_rows(archive) == expected, "current_Rita_config_members_changed")
    require(s.get("total_loss_only") is True and s.get("ordinary_rollback_allowed") is False,
            "current_Rita_config_scope_changed")
    return {"status": "verified_private_total_loss_capture_hashes_and_metadata_only",
            "acquisition": s["acquisition"], "archive_sha256": s["archive_sha256"],
            "members": len(expected), "contents_or_secret_values_emitted": False,
            "ordinary_rollback_allowed": False, "native_or_human_acceptance": False}


def inventory_rows(data):
    if not data.lstrip().startswith((b"{", b"[")):
        return {k: (v, None) for k, v in sha_manifest(data).items()}
    obj = json.loads(data)
    if isinstance(obj, dict) and "complete_regular_files" in obj:
        obj = obj["complete_regular_files"]
    if isinstance(obj, dict):
        return {k: (v["sha256"], v.get("mode")) for k, v in obj.items()}
    require(isinstance(obj, list) and len({r["path"] for r in obj}) == len(obj), "inventory_duplicate")
    return {r["path"]: (r["sha256"], r.get("mode")) for r in obj}


def core_module(b):
    directory = Path(__file__).resolve().parent / "components/crustacea"
    for name, expected in b["components"]["crustacea"]["execution_files"].items():
        require(digest(confined(directory, name.removeprefix("recovery/"))) == expected, "prepared_core_helper_changed")
    spec = importlib.util.spec_from_file_location("vip_captured_core", directory / "captured-core-phase.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def core_inputs(root, b):
    path = safe_path(str(root)) / "INPUTS.json"
    require(path.is_file(), b["gaps"]["crustacea"])
    module = core_module(b)
    try:
        packet, value, rows = module.load_inputs(path)
    except module.d.Stop as error:
        raise Stop(str(error)) from None
    expected = b["components"]["crustacea"]["closure"]
    require(all(value["closure"][k] == expected[k] for k in ("archive_sha256", "manifest_sha256", "receipt_sha256")), "current_core_closure_binding_changed")
    contract = b["components"]["crustacea"]["native_gate_contract"]
    require(value.get("native_gate_contract") == contract, "owner_native_gate_binding_changed")
    owner = value["owner_input"]
    require(owner["sha256"] == contract["owner_receipt_sha256"] and digest(confined(packet, owner["receipt"])) == owner["sha256"], "owner_receipt_binding_changed")
    current = current_core_binding(packet, b)
    controls = owner["protected_metadata"]
    if current is not None:
        historical = owner["historical_config_metadata"]
        require(historical["sha256"] == b["components"]["crustacea"]["historical_foundation"]["managed_config_sha256"]
                and owner["protected_config_metadata_origin"] == current["binding"]["current_config_amendment"],
                "historical_owner_config_attribution_changed")
        require(controls["/home/aimee/.openclaw/openclaw.json"] == current["config"]["native"],
                "current_owner_config_metadata_amendment_changed")
        require(current["snapshot"]["core_manifest_sha256"] == value["expected_current_sha256"]
                and current["config"]["native"]["sha256"] == value["protected"]["/home/aimee/.openclaw/openclaw.json"],
                "current_core_or_config_CAS_binding_changed")
    require(owner["static_source"] == b["components"]["crustacea"]["workflow_source"]
            and all(value["protected"].get(k) == v["sha256"] for k, v in controls.items()),
            "owner_control_or_static_binding_changed")
    return module, packet, value, rows


def current_core_binding(root, b):
    s = b["components"]["crustacea"]
    pin = s.get("current_binding")
    if pin is None:
        return None
    path = confined(root, pin["path"])
    require(digest(path) == pin["sha256"], "current_core_binding_changed")
    value = json.loads(path.read_bytes())
    require(value.get("schema") == "vip-current-core-binding-v1"
            and value["runtime_commit"] == s["compiled_runtime"]
            and value["package"] == s["available_package"]
            and value["package_sha256"] == s["available_package_sha256"], "current_core_package_binding_changed")
    snapshot_path = confined(root, value["snapshot"])
    require(digest(snapshot_path) == value["snapshot_sha256"], "current_core_snapshot_changed")
    snapshot = json.loads(snapshot_path.read_bytes())
    require(snapshot["runtime_commit"] == s["compiled_runtime"]
            and snapshot["archive_sha256"] == s["closure"]["archive_sha256"]
            and snapshot["archive_manifest_sha256"] == s["closure"]["manifest_sha256"]
            and snapshot["capture_receipt_sha256"] == s["closure"]["receipt_sha256"], "current_core_snapshot_binding_changed")
    config_path = confined(root, value["current_config_amendment"])
    require(digest(config_path) == value["current_config_amendment_sha256"], "current_core_config_amendment_changed")
    config = json.loads(config_path.read_bytes())
    require(config.get("schema") == "vip-current-managed-config-amendment-v1"
            and config["total_loss_only"] is True and config["ordinary_rollback_allowed"] is False
            and config["native"] == snapshot["protected_metadata"]["/home/aimee/.openclaw/openclaw.json"],
            "current_core_config_amendment_binding_changed")
    return {"binding": value, "snapshot": snapshot, "config": config}


def verify_current_core_package(root, b):
    current = current_core_binding(root, b)
    if current is None:
        return {}
    value = current["binding"]
    package = safe_path(value["package"])
    require(package.is_file() and not package.is_symlink()
            and package.stat().st_size == value["package_bytes"]
            and digest(package) == value["package_sha256"], "current_core_package_changed")
    with tarfile.open(package, "r:gz") as archive:
        names = ["package/" + name for name in value["package_anchors"]]
        anchors = {}
        for member in archive.getmembers():
            if member.name not in names:
                continue
            require(member.name.removeprefix("package/") not in anchors
                    and member.isfile() and member.size <= 262144, "current_core_package_anchor_invalid")
            data = archive.extractfile(member).read()
            anchors[member.name.removeprefix("package/")] = hashlib.sha256(data).hexdigest()
            if member.name == "package/dist/build-info.json":
                require(json.loads(data)["commit"] == value["runtime_commit"], "current_core_build_commit_changed")
        require(anchors == value["package_anchors"], "current_core_package_anchors_changed")
    closure = Path(b["components"]["crustacea"]["closure"]["root"])
    config = current["config"]
    archive_path = confined(closure, config["archive"])
    require(digest(archive_path) == config["archive_sha256"], "current_core_private_config_archive_changed")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        require(len(members) == 1 and members[0].name == config["member"] and members[0].isfile(), "current_core_private_config_members_changed")
        member = members[0]
        native = config["native"]
        require((member.size, member.mode, member.uid, member.gid) == tuple(native[k] for k in ("size", "mode", "uid", "gid"))
                and hashlib.sha256(archive.extractfile(member).read()).hexdigest() == native["sha256"],
                "current_core_private_config_identity_changed")
    return {"compiled_runtime": value["runtime_commit"], "package_sha256": value["package_sha256"],
            "package_anchors_verified": True, "current_config_sha256": config["native"]["sha256"],
            "current_config_total_loss_only": True,
            "owner_restore_compatible": value["owner_restore_executable_with_retained_four_patchers"],
            "owner_restore_gap": value["known_restore_gap"]}


def verify_package(c, root, b):
    require(c in b["components"], b["gaps"].get(c, "component_unknown"))
    s = b["components"][c]
    root = safe_path(str(root))
    if s.get("protocol") == "current_owner_files":
        require(root.is_dir() and not root.is_symlink(), "package_missing")
        files = list(root.rglob("*"))
        require(not any(p.is_symlink() for p in files), "kit_symlink_rejected")
        actual = {str(p.relative_to(root)): (digest(p), p.stat().st_size)
                  for p in files if p.is_file()}
        expected = {name: (row[0], row[1]) for name, row in s["files"].items()}
        for name, row in expected.items():
            confined(root, name)
            require(SHA.fullmatch(row[0]) is not None and type(row[1]) is int and row[1] >= 0,
                    "owner_file_binding_invalid")
        require(actual == expected, "current_owner_file_coverage_or_hash_mismatch")
        require(len(actual) == s["kit_files"] and sum(v[1] for v in actual.values()) == s["kit_bytes"],
                "current_owner_file_count_or_bytes_mismatch")
        require(sum(name.startswith("source/") for name in actual) == s["source_files"],
                "source_count_mismatch")
        return {"component": c, "status": "verified_current_owner_bytes_retention_only",
                "source": s["source"], "source_files": s["source_files"],
                "retained_files": len(actual), "retained_bytes": sum(v[1] for v in actual.values()),
                "full_component_release_matched": False,
                "owner_transaction_helper_available": False,
                "native_or_human_acceptance": False}
    if s.get("protocol") == "current_rita_owner_packet":
        require(root.is_dir() and not root.is_symlink(), "package_missing")
        for name, expected in ((s["canonical"], s["canonical_sha"]),
                               (s["canonical"].replace(".tar.gz", ".sha256"), s["manifest_sha"]),
                               (s["skeleton"], s["skeleton_sha"]),
                               (s["inventory"], s["inventory_sha"])):
            p = confined(root, name)
            require(p.is_file() and digest(p) == expected, "artifact_missing_or_hash_mismatch")
        _, source = archive_rows(root / s["canonical"])
        require(len(source) == s["source_files"], "source_count_mismatch")
        manifest = sha_manifest((root / s["canonical"].replace(".tar.gz", ".sha256")).read_bytes())
        require({k: v[0] for k, v in source.items()} == manifest, "source_manifest_coverage")
        _, skeleton = archive_rows(root / s["skeleton"])
        kit = confined(root, s["kit"])
        require(kit.is_dir() and not kit.is_symlink(), "package_missing")
        files = list(kit.rglob("*"))
        require(not any(p.is_symlink() for p in files), "kit_symlink_rejected")
        actual = {str(p.relative_to(kit)): (digest(p), p.stat().st_size)
                  for p in files if p.is_file()}
        candidate = json.loads((root / s["inventory"]).read_bytes())
        expected = candidate.get("kit_files")
        require(isinstance(expected, dict) and all(isinstance(k, str) and SHA.fullmatch(v)
                                                   for k, v in expected.items()), "inventory_format")
        require(set(actual) == set(expected) | {"CANDIDATE.json"}
                and all(actual[k][0] == v for k, v in expected.items()), "kit_blob_mismatch")
        require(candidate.get("source_commit") == s["source"]
                and candidate.get("binary_source_commit") == s["binary_source"]
                and candidate.get("binary_sha256") == s["after"]["/usr/local/libexec/aimee-pbx-router"]
                and candidate.get("manifest_sha256") == s["manifest_sha"], "current_source_or_binary_binding_changed")
        require(len(actual) == s["kit_files"] and sum(v[1] for v in actual.values()) == s["kit_bytes"],
                "current_owner_file_count_or_bytes_mismatch")
        equal = {k: v[0] for k, v in skeleton.items()} == {k: v[0] for k, v in actual.items()}
        if s.get("skeleton_equal_required"):
            require(equal, "skeleton_and_kit_differ")
        return {"component": c, "status": "verified_current_owner_packet_retention_only",
                "source": s["source"], "source_files": len(source), "kit_files": len(actual),
                "kit_bytes": sum(v[1] for v in actual.values()), "skeleton_files": len(skeleton),
                "skeleton_equal": equal, "historical_skeleton_is_not_current_ordinary_kit": not equal,
                "native_or_human_acceptance": False}
    if s.get("protocol") == "captured_owner_packet":
        if (root / "INPUTS.json").is_file():
            module, _, value, rows = core_inputs(root, b)
            return {"component": c, "status": "offline_owner_packet_validated_not_native_phase_acceptance", "source": s["source"],
                    "core_manifest_sha256": module.body_hash(rows), "native_or_human_acceptance": False,
                    **verify_current_core_package(root, b)}
        module = core_module(b)
        closure = s["closure"]
        for key in ("archive", "manifest", "receipt"):
            require(digest(root / closure[key]) == closure[key + "_sha256"], "retained_current_core_closure_changed")
        rows = module.validate_records(json.loads((root / closure["manifest"]).read_bytes())["records"])
        module.verify_archive(root / closure["archive"], rows)
        return {"component": c, "status": "missing_prerequisite", "reason": b["gaps"][c], "source": s["source"],
                "retained_disk_closure_verified": True, "records": len(rows), "core_manifest_sha256": module.body_hash(rows),
                "native_or_human_acceptance": False}
    require(root.is_dir() and not root.is_symlink(), "package_missing")
    paths = [(s["canonical"], s["canonical_sha"]),
             (s["canonical"].replace(".tar.gz", ".sha256"), s["manifest_sha"]),
             (s["skeleton"], s["skeleton_sha"]), (s["inventory"], s["inventory_sha"])]
    for name, expected in paths:
        p = confined(root, name)
        require(p.is_file() and digest(p) == expected, "artifact_missing_or_hash_mismatch")
    _, source = archive_rows(root / s["canonical"])
    require(len(source) == s["source_files"], "source_count_mismatch")
    require({k: v[0] for k, v in source.items()} == sha_manifest((root / paths[1][0]).read_bytes()), "source_manifest_coverage")
    kit = confined(root, s["kit"])
    inv = inventory_rows((root / s["inventory"]).read_bytes())
    for name, (expected, mode) in inv.items():
        p = confined(kit, name)
        require(p.is_file() and digest(p) == expected, "kit_blob_mismatch")
        if mode is not None:
            mode = int(mode, 8) if isinstance(mode, str) else mode
            require(stat.S_IMODE(p.stat().st_mode) == mode, "kit_mode_mismatch")
    _, saved = archive_rows(root / s["skeleton"])
    if saved and all(k.startswith(kit.name + "/") for k in saved):
        saved = {k[len(kit.name) + 1:]: v for k, v in saved.items()}
    files = list(kit.rglob("*"))
    require(not any(p.is_symlink() for p in files), "kit_symlink_rejected")
    actual = {str(p.relative_to(kit)): (digest(p), stat.S_IMODE(p.stat().st_mode)) for p in files if p.is_file()}
    excluded = []
    sidecars = {"protected/database/agents.db-wal", "protected/database/agents.db-shm"}
    extra = set(actual) - set(saved)
    if c == "ava" and extra and extra <= sidecars:
        # This is a captured consistent backup, not a live DB. Reading it may generate an
        # empty WAL and shared-memory sidecar. Never ignore a nonempty WAL or alter either.
        wal = kit / "protected/database/agents.db-wal"
        require(wal.is_file() and wal.stat().st_size == 0, "nonempty_backup_WAL_requires_retention")
        excluded = sorted(extra)
        actual = {k: v for k, v in actual.items() if k not in extra}
    require(len(actual) == s["kit_files"] and actual == saved, "skeleton_kit_coverage_or_modes")
    # A sha manifest cannot include itself; all other inventory formats must be complete.
    allowed = {Path(s["inventory"]).name} if not (root / s["inventory"]).read_bytes().lstrip().startswith((b"{", b"[")) else set()
    require(set(actual) - set(inv) <= allowed and set(inv) <= set(actual), "kit_inventory_coverage")
    require(digest(kit / s["helper"]) == s["helper_sha"], "helper_identity_changed")
    return {"component": c, "status": "verified_offline", "source": s["source"],
            "source_files": len(source), "kit_files": len(actual), "skeleton_equal": True,
            "excluded_generated_empty_backup_WAL_and_SHM": excluded,
            "native_or_human_acceptance": False}


def read_roots(path, b):
    if path is None:
        return {}
    obj = json.loads(Path(path).read_bytes())
    require(isinstance(obj, dict) and set(obj) <= set(b["components"]), "roots_schema")
    return {k: safe_path(v) for k, v in obj.items()}


def project_roots(projects, b, *, current_core=True):
    """Resolve retained inputs from the operator's Projects copy, not a builder tree."""
    base = safe_path(str(projects))
    def resolve(value):
        prefix = "Documents/Projects/"
        require(isinstance(value, str) and value.startswith(prefix),
                "acquisition_is_not_a_project_path")
        return confined(base, value[len(prefix):])
    components = {name: resolve(row["acquisition"])
                  for name, row in b["components"].items() if name != "crustacea"}
    components["crustacea"] = (resolve(b["components"]["crustacea"]["offline_owner"]["acquisition"])
                               if current_core else Path(__file__).resolve().parent.parent / "owner-input")
    external = {}
    for name, row in b.get("external_foundations", {}).items():
        external[name] = resolve(row["acquisition"])
        for sidecar in row.get("sidecars", []):
            external[sidecar["root_key"]] = resolve(sidecar["acquisition"]).parent
    return components, external


def read_external_roots(path, b):
    if path is None:
        return {}
    obj = json.loads(Path(path).read_bytes())
    allowed = set(b.get("external_foundations", {}))
    for s in b.get("external_foundations", {}).values():
        allowed.update(row["root_key"] for row in s.get("sidecars", []))
    require(isinstance(obj, dict) and set(obj) <= allowed, "external_roots_schema")
    return {k: safe_path(v) for k, v in obj.items()}


def external_file(root, name, missing):
    require(str(PurePosixPath(name)) == name, "external_path_not_canonical")
    p = confined(root, name)
    for parent in (p, *p.parents):
        require(not parent.is_symlink(), "external_input_symlink")
        if parent == root:
            break
    require(p.is_file(), missing)
    return p


def external_json(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "external_inventory_duplicate")
            value[key] = item
        return value
    return json.loads(data, object_pairs_hook=unique)


def verify_external_foundation(name, roots, b):
    s = b["external_foundations"][name]
    require(name in roots, "external_root_missing")
    root = safe_path(str(roots[name]))
    require(root.is_dir() and not root.is_symlink(), "external_root_missing_or_symlink")
    if s["kind"] == "sha_manifest":
        p = external_file(root, s["manifest"], "external_manifest_missing")
        require(digest(p) == s["manifest_sha256"], "external_manifest_hash_mismatch")
        rows = sha_manifest(p.read_bytes(), require_sorted=False)
        require(len(rows) == s["entries"], "external_manifest_count_mismatch")
        for path, expected in rows.items():
            p = external_file(root, path, "external_manifest_member_missing")
            require(digest(p) == expected, "external_manifest_member_hash_mismatch")
    elif s["kind"] == "artifact":
        p = external_file(root, s["archive"], "external_archive_missing")
        require(digest(p) == s["archive_sha256"], "external_archive_hash_mismatch")
        rows = {s["archive"]: s["archive_sha256"]}
    elif s["kind"] == "native_inventory":
        p = external_file(root, s["inventory"], "external_inventory_missing")
        require(digest(p) == s["inventory_sha256"], "external_inventory_hash_mismatch")
        value = external_json(p.read_bytes())
        require(isinstance(value, dict) and value.get("schema") == s["inventory_schema"] and isinstance(value.get("files"), dict),
                "external_inventory_schema")
        rows = value["files"]
        require(len(rows) == s["entries"], "external_inventory_count_mismatch")
        for path, row in rows.items():
            confined(Path("/inventory-root"), path)
            require(str(PurePosixPath(path)) == path, "external_path_not_canonical")
            require(isinstance(row, dict) and isinstance(row.get("sha256"), str)
                    and SHA.fullmatch(row["sha256"]) is not None and
                    all(type(row.get(k)) is int and row[k] >= 0 for k in ("size", "mode", "uid", "gid"))
                    and row["mode"] <= 0o7777, "external_inventory_metadata")
        require(value.get("archive_sha256") == s["archive_sha256"], "external_inventory_archive_pin")
        p = external_file(root, s["archive"], "external_archive_missing")
        require(digest(p) == s["archive_sha256"], "external_archive_hash_mismatch")
    else:
        raise Stop("external_foundation_kind_unknown")
    sidecars = []
    for row in s.get("sidecars", []):
        key = row["root_key"]
        require(key in roots, "external_sidecar_root_missing")
        sidecar_root = safe_path(str(roots[key]))
        require(sidecar_root.is_dir() and not sidecar_root.is_symlink(), "external_sidecar_root_missing_or_symlink")
        p = external_file(sidecar_root, row["path"], "external_sidecar_missing")
        require(digest(p) == row["sha256"], "external_sidecar_hash_mismatch")
        sidecars.append({"acquisition": row["acquisition"], "sha256": row["sha256"]})
    return {"foundation": name, "status": "verified_retention_only", "entries": len(rows),
            "acquisition": s["acquisition"], "sidecars": sidecars, "role": s["role"],
            "fresh_host_restore": s["fresh_host_restore"], "restore_executed": False,
            "archive_extracted_or_links_dereferenced": False, "ordinary_rollback_restores_input": False,
            "native_or_human_acceptance": False}


def external_foundation_rows(roots, b):
    result = []
    for name, s in b.get("external_foundations", {}).items():
        try:
            result.append(verify_external_foundation(name, roots, b))
        except (Stop, OSError, ValueError, KeyError, TypeError) as error:
            result.append({"foundation": name, "status": "missing_or_invalid_prerequisite",
                           "reason": error.code if isinstance(error, Stop) else "external_input_invalid",
                           "acquisition": s["acquisition"], "fresh_host_restore": s["fresh_host_restore"],
                           "restore_executed": False, "native_or_human_acceptance": False})
    return result


def verify_current_core_owner(root, b):
    """Use the retained owner's relocation flag; never enter a native phase."""
    root = safe_path(str(root))
    owner = b["components"]["crustacea"]["offline_owner"]
    verify_external_foundation("current-core", {"current-core": root},
                               {"external_foundations": {"current-core": owner}})
    kit = confined(root, "crustacea")
    inputs = confined(kit, "INPUTS.json")
    packet = json.loads(inputs.read_bytes())
    expected = b["components"]["crustacea"]
    require(packet["runtime_commit"] == expected["compiled_runtime"]
            and packet["restore_transform"] == "exact_captured_current_no_transform",
            "current_core_owner_contract_changed")
    command = [sys.executable, "-B", str(confined(kit, "deploy/captured-core-phase.py")),
               "verify", "--inputs", str(inputs), "--closure-root", str(confined(kit, "core"))]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, check=False)
    require(result.returncode == 0, "current_core_owner_verify_failed")
    receipt = json.loads(result.stdout)
    require(isinstance(receipt, dict)
            and receipt.get("status") == "offline_exact_closure_verified"
            and receipt.get("archive_sha256") == expected["closure"]["archive_sha256"]
            and receipt.get("core_manifest_sha256") == packet["expected_current_sha256"]
            and all(receipt.get(key) is False for key in
                    ("native_execution", "config_restored", "DB_restored", "dependency_resolution")),
            "current_core_owner_receipt_invalid")
    # The owner's Core snapshot predates the separately accepted relay update.
    retained_relay = packet["protected"]["/usr/local/libexec/aimee-main-voice-relay"]
    current_relay = b["external_foundations"]["relay-current"]["runtime_sha256"]
    return {"component": "crustacea", "status": "offline_current_owner_closure_verified",
            "source": owner["source"], "compiled_runtime": expected["compiled_runtime"],
            "archive_sha256": receipt["archive_sha256"],
            "core_manifest_sha256": receipt["core_manifest_sha256"],
            "historical_patchers_executed": False, "native_or_human_acceptance": False,
            "fresh_host_recovery": False, "retained_relay_is_current": retained_relay == current_relay,
            "current_relay_source": b["external_foundations"]["relay-current"]["source"],
            "relay_restore": "Use the separately verified current relay packet; do not restore the historical bundled relay"}


def scoped_backup(c, value, b, apply=False):
    if isinstance(value, dict):
        require(set(value) == {"path", "manifest_sha256"} and SHA.fullmatch(value["manifest_sha256"]), "protected_manifest_pin_required")
        value = value["path"]
    p = safe_path(value)
    base = Path(b["components"][c]["backup_base"])
    require(p.is_relative_to(base) and p != base, "backup_scope_rejected")
    if c == "ava":
        require(p.name.startswith("runtime-"), "backup_scope_rejected")
    if c == "tessa":
        require(p.name.startswith("tessa-provider-"), "backup_scope_rejected")
    if c == "voice-organ":
        require(p.parent == base and p.name.startswith("avril-call-executor-pre-abi-"), "backup_scope_rejected")
    if c == "crustacea":
        require(p.parent == base and p.name.startswith("crustacea-core-recovery-"), "backup_scope_rejected")
    return p


def installed_owner_helper(s, root):
    require(isinstance(s.get("installed_verifier"), str)
            and s["installed_verifier"] in (s["helper"], "recovery/" + s["helper"])
            and isinstance(s.get("installed_verifier_sha"), str)
            and SHA.fullmatch(s["installed_verifier_sha"]) is not None
            and all(isinstance(s.get(k), str) and re.fullmatch(r"[0-9a-f]{40}", s[k])
                    for k in ("installed_verification_source", "installed_verification_tree")),
            "accepted_Ava_installed_verifier_pin_required")
    return str(confined(root, s["installed_verifier"]))


def owner_argv(c, mode, stages, current, backup, b):
    require(c in b["components"], b["gaps"].get(c, "component_unknown"))
    s = b["components"][c]
    if c == "tessa":
        raise Stop(s["missing_execution_prerequisite"])
    require(c in stages, "native_staged_kit_required")
    root = safe_path(str(stages[c]))
    helper = str(root / (s.get("execution_helper") or s.get("helper", "missing-owner-helper")))
    if c == "crustacea":
        args = ["/usr/bin/python3", "-B", str(root / "coordinator/deployment/recovery-coordinator.py"), "core-phase",
                "--phase-mode", "observe" if mode == "check" else "apply" if mode == "install" else "rollback",
                "--inputs", str(root / "owner-packet/INPUTS.json"), "--settings", str(root / "owner-packet/PHASE-SETTINGS.json")]
        if mode == "rollback":
            require(isinstance(backup, dict), "protected_manifest_pin_required")
            return args + ["--snapshot", str(scoped_backup(c, backup, b)), "--snapshot-sha256", backup["manifest_sha256"]]
        return args
    if c == "rita":
        require(mode in ("check", "install"), "automatic_older_reader_rollback_forbidden")
        require(set(current) == set(s["after"]) and all(isinstance(v, str) and SHA.fullmatch(v) for v in current.values()), "paired_preimages_required")
        args = ["/usr/bin/python3", "-B", helper, "--kit", str(root / s["kit"]),
                "--expected-binary", current["/usr/local/libexec/aimee-pbx-router"],
                "--expected-unit", b["unit"]["sha256"], "--expected-environment", s["environment_sha"]]
        return args if mode == "check" else args + ["--apply"]
    if c == "ava":
        if mode == "verify-installed":
            return ["/usr/bin/python3", "-B", installed_owner_helper(s, root), "--verify-installed"]
        args = ["/usr/bin/python3", "-B", helper]
        if mode == "check":
            return args + ["--check-only"]
        require(backup is not None, "protected_backup_required")
        return args + (["--apply", "--backup"] if mode == "install" else ["--rollback"]) + [str(scoped_backup(c, backup, b))]
    require(c == "voice-organ" and set(current) == set(s["after"]) and all(SHA.fullmatch(v) for v in current.values()), "executor_preimage_required")
    args = ["/bin/bash", helper, "--expected-current-sha256", next(iter(current.values()))]
    if mode == "rollback":
        require(isinstance(backup, dict), "protected_manifest_pin_required")
        return args + ["--rollback", str(scoped_backup(c, backup, b)), "--backup-manifest-sha256", backup["manifest_sha256"]]
    return args + ["--check" if mode == "check" else "--apply", "--candidate", str(root / "artifacts/avril-call-executor"),
                   "--candidate-sha256", next(iter(s["after"].values()))]


def write_receipt(path, obj):
    p = safe_path(str(path))
    require(p.parent.is_dir() and not p.parent.is_symlink() and stat.S_IMODE(p.parent.stat().st_mode) & 0o077 == 0, "private_receipt_parent_required")
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


class Native:
    """Only enumerated hosts and internally constructed argv cross SSH."""
    def __init__(self, key, local_host=None):
        self.key = safe_path(key)
        require(self.key.is_file() and not self.key.is_symlink(), "managed_SSH_key_missing")
        require(stat.S_IMODE(self.key.stat().st_mode) & 0o077 == 0, "managed_SSH_key_mode")
        self.active_pid = None
        self.local_host = local_host

    @staticmethod
    def ssh_actor(host):
        return {"vip.bajaj.com": "gary", "ava.bajaj.com": "aimee", "avril.bajaj.com": "aimee", "crustacea.bajaj.com": "aimee"}[host]

    def _run(self, host, args, mutation=False, budget=131072):
        require(host in ("vip.bajaj.com", "ava.bajaj.com", "avril.bajaj.com", "crustacea.bajaj.com"), "host_rejected")
        # The remote shell receives inert argv only, except this fixed quoted Asterisk command.
        literals = {"'core show channels'", "'*'", "'http://[::1]:18789/healthz'", "'%{http_code}'"}
        require(all(SAFE.fullmatch(a) or a in literals for a in args), "command_argument_rejected")
        command = ["ssh", "-T", "-i", str(self.key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                   "-o", "IdentityAgent=none", "-o", "ConnectTimeout=10", self.ssh_actor(host) + "@" + host, "sudo", "-n"] + args
        if host == getattr(self, "local_host", None):
            # The injected owner interface runs only on the core's owning host.
            command = ["/usr/bin/sudo", "-n"] + [a[1:-1] if a in literals else a for a in args]
        with tempfile.TemporaryFile() as out:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.DEVNULL)
            self.active_pid = child.pid
            try:
                rc = child.wait(timeout=None if mutation else 45)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                raise Stop("readonly_transport_timeout") from None
            finally:
                if child.poll() is not None:
                    self.active_pid = None
            out.seek(0)
            data = out.read(budget + 1)
            require(len(data) <= budget, "native_output_over_budget")
            return rc, data

    def hashes(self, c, paths, b):
        rc, data = self._run(b["components"][c]["host"], ["/usr/bin/sha256sum", "--"] + list(paths))
        require(rc == 0, "native_file_or_existing_privilege_prerequisite_missing")
        rows = {}
        for line in data.decode("ascii").splitlines():
            require(len(line) > 66 and SHA.fullmatch(line[:64]), "native_hash_schema")
            require(line[66:] not in rows, "native_hash_duplicate")
            rows[line[66:]] = line[:64]
        require(set(rows) == set(paths), "native_hash_coverage")
        return rows

    def zero(self):
        rc, data = self._run("vip.bajaj.com", ["/usr/sbin/asterisk", "-rx", "'core show channels'"])
        require(rc == 0, "native_zero_probe_failed")
        text = data.decode("ascii")
        require(re.search(r"(?m)^0 active channels\s*$", text) is not None
                and re.search(r"(?m)^0 active calls\s*$", text) is not None, "native_not_zero")

    def unit(self):
        expected = {"FragmentPath": "/etc/systemd/system/aimee-pbx-router.service", "DropInPaths": "",
                    "Type": "exec", "User": "aimee-pbx-router", "Group": "aimee-pbx-router",
                    "SupplementaryGroups": "asterisk", "StateDirectory": "aimee-pbx-router",
                    "StateDirectoryMode": "0700", "ReadWritePaths": "/var/lib/avr-voicemail", "ProtectSystem": "strict"}
        rc, data = self._run("vip.bajaj.com", ["/usr/bin/systemctl", "show", "aimee-pbx-router.service",
                                             "--property=" + ",".join(expected)])
        require(rc == 0, "effective_unit_unavailable")
        rows = dict(line.split("=", 1) for line in data.decode().splitlines() if "=" in line)
        require(rows == expected, "accepted_effective_unit_or_dropins_changed")
        rc, _ = self._run("vip.bajaj.com", ["/usr/bin/sudo", "-n", "-u", "aimee-pbx-router",
                                          "/usr/bin/test", "-w", "/var/lib/avr-voicemail"])
        require(rc == 0, "asterisk_group_or_voicemail_writable_state_missing")

    def helper(self, c, args, b, mutation=False):
        return self._run(b["components"][c]["host"], args, mutation)

    def document(self, c, backup, name, b):
        require(name in ("snapshot.json", "transaction.json", "SHA256SUMS"), "owner_snapshot_member_rejected")
        p = scoped_backup(c, backup, b) / name
        rc, data = self._run(b["components"][c]["host"], ["/usr/bin/cat", "--", str(p)], budget=67108864 if c == "crustacea" else 131072)
        require(rc == 0, "owner_snapshot_unavailable")
        return data

    def owner_packet(self, root, b):
        rc, data = self._run(b["components"]["crustacea"]["host"], ["/usr/bin/cat", "--", str(root / "owner-packet/INPUTS.json")])
        require(rc == 0, "native_owner_packet_unavailable")
        return json.loads(data)

    def core_observe(self, stages, b):
        rc, data = self.helper("crustacea", owner_argv("crustacea", "check", stages, {}, None, b), b)
        require(rc == 0, "core_authoritative_observation_unavailable")
        value = json.loads(data)
        require(value["status"] == "installed_code_observed" and SHA.fullmatch(value["core_manifest_sha256"]), "core_observation_schema_invalid")
        require(isinstance(value["workspace"], dict) and all(SHA.fullmatch(v) for v in value["workspace"].values()), "core_workspace_observation_invalid")
        return {"core_manifest_sha256": value["core_manifest_sha256"], **value["workspace"]}


def rollback_expected(n, c, backup, b):
    require(backup is not None, "protected_backup_required")
    base = scoped_backup(c, backup, b)
    s = b["components"][c]
    if c == "rita":
        data = n.document(c, backup, "snapshot.json", b)
        m = json.loads(data)
        require((m["binary_target"], m["helper_target"], m["unit_target"]) ==
                ("/usr/local/libexec/aimee-pbx-router", "/usr/local/libexec/avril_voicemail_command.py",
                 "/etc/systemd/system/aimee-pbx-router.service"), "owner_snapshot_targets_mismatch")
        require(m["candidate_binary_sha256"] == s["after"][m["binary_target"]]
                and m["candidate_helper_sha256"] == s["after"][m["helper_target"]]
                and m["unit_sha256"] == b["unit"]["sha256"], "owner_snapshot_candidate_identity_mismatch")
        restored = {m["binary_target"]: m["old_binary_sha256"], m["helper_target"]: m["old_helper_sha256"]}
        blobs = {str(base / "binary"): m["old_binary_sha256"], str(base / "helper"): m["old_helper_sha256"],
                 str(base / "unit"): m["unit_sha256"]}
    elif c == "ava":
        data = n.document(c, backup, "transaction.json", b)
        m = json.loads(data)
        names = {k.removeprefix("/opt/AVA-AI-Voice-Agent-for-Asterisk/src/") for k in s["after"]}
        require(m["commit"] == s["runtime"] and m["source_tree"] == s["runtime_tree"]
                and set(m["targets"]) == names and set(m["files"]) == names,
                "owner_snapshot_source_or_targets_mismatch")
        require(m["agents_db_backup"]["evidence_only"] is True and m["agents_db_backup"]["restored"] is False
                and m["config_capture_evidence_only"] is True, "owner_snapshot_state_restore_forbidden")
        restored = {"/opt/AVA-AI-Voice-Agent-for-Asterisk/src/" + k: v["before"]["sha256"] for k, v in m["files"].items()}
        require(restored == s["before"], "owner_snapshot_preimage_identity_mismatch")
        blobs = {str(base / "runtime-before" / k): v["before"]["sha256"] for k, v in m["files"].items()}
    elif c == "tessa":
        data = n.document(c, backup, "SHA256SUMS", b)
        blobs = {}
        for line in data.decode("ascii").splitlines():
            require(len(line) > 66 and SHA.fullmatch(line[:64]), "owner_snapshot_manifest_invalid")
            require(line[66:] not in blobs, "owner_snapshot_manifest_duplicate")
            blobs[line[66:]] = line[:64]
        require(set(blobs) == {str(base / k) for k in ("index.js.before", "docker-compose-bajaj.yml.before", "avr.env.before")},
                "owner_snapshot_manifest_coverage")
        restored = {next(iter(s["after"])): blobs[str(base / "index.js.before")]}
    elif c == "voice-organ":
        require(isinstance(backup, dict), "protected_manifest_pin_required")
        data = n.document(c, backup, "snapshot.json", b)
        require(hashlib.sha256(data).hexdigest() == backup["manifest_sha256"], "protected_manifest_pin_changed")
        m = json.loads(data)
        require(m["schema"] == "voice-organ-executor-transaction-v1" and m["target"] == "/usr/local/sbin/avril-call-executor"
                and m["unit"] == "avril-call-executor.service" and m["config_restored"] is False
                and m["state_restored"] is False and m["after"]["sha256"] == s["after"][m["target"]],
                "legacy_or_foreign_executor_snapshot_unsupported")
        restored = {m["target"]: m["before"]["sha256"]}
        blobs = {str(base / "snapshot.json"): backup["manifest_sha256"], str(base / "executor.before"): m["before"]["sha256"]}
    elif c == "crustacea":
        require(isinstance(backup, dict), "protected_manifest_pin_required")
        data = n.document(c, backup, "snapshot.json", b)
        require(hashlib.sha256(data).hexdigest() == backup["manifest_sha256"], "protected_manifest_pin_changed")
        m = json.loads(data)
        module = core_module(b)
        require(m["schema"] == module.SCHEMA and m["phase_helper_sha256"] == s["helper_sha"] and m["DB_restored"] is False
                and m["config_restored"] is False and m["closure"] == {k: s["closure"][k] for k in ("archive_sha256", "manifest_sha256", "receipt_sha256")}, "foreign_core_snapshot_unsupported")
        module.validate_records([dict(v, path=k) for k, v in m["before"].items()])
        restored = {"core_manifest_sha256": module.body_hash(m["before"])}
        for row in m["workspace"]:
            require(row["target"].startswith("skills/") and ".." not in PurePosixPath(row["target"]).parts and row["target"] not in restored, "core_snapshot_static_scope_invalid")
            restored[row["target"]] = row["before"]["sha256"]
        blobs = {str(base / "snapshot.json"): backup["manifest_sha256"], str(base / "captured-core-launcher.tar.gz"): m["captured_archive_sha256"]}
        blobs.update({str(base / (str(i) + ".before")): row["before"]["sha256"] for i, row in enumerate(m["workspace"])})
    else:
        raise Stop("component_rollback_native_phase_not_accepted")
    require(all(isinstance(v, str) and SHA.fullmatch(v) for v in blobs.values()), "owner_snapshot_hash_invalid")
    require(n.hashes(c, blobs, b) == blobs, "owner_snapshot_backup_bytes_mismatch")
    return {"restored": restored, "snapshot_sha256": hashlib.sha256(data).hexdigest(), "blobs": blobs}


def protected_snapshot(n, c, b):
    s = b["components"][c]
    rows = n.hashes(c, s["protected"], b)
    if "/etc/asterisk/extensions_custom.conf" in rows:
        require(rows["/etc/asterisk/extensions_custom.conf"] == b["custom_sha256"], "native_FreePBX_UI_checkpoint_drift")
    if c == "rita":
        require(rows["/etc/systemd/system/aimee-pbx-router.service"] == b["unit"]["sha256"], "accepted_unit_not_template_required")
        n.unit()
    return rows


def staged_check(n, c, stages, b, installed=False):
    require(c in stages, "native_staged_kit_required")
    root = safe_path(str(stages[c]))
    require(str(root).startswith(("/home/aimee/.local/share/vip-recovery-", "/root/vip-recovery-")), "native_stage_scope_rejected")
    s = b["components"][c]
    rows = {str(root / s["helper"]): s["helper_sha"]}
    if installed:
        require(c == "ava", "installed_owner_component_rejected")
        rows[installed_owner_helper(s, root)] = s["installed_verifier_sha"]
    rows.update({str(root / name): value for name, value in s.get("execution_files", {}).items()})
    if c == "crustacea":
        rows[str(root / "coordinator/deployment/recovery-coordinator.py")] = digest(__file__)
        rows[str(root / "coordinator/component-bindings-20260914.json")] = BINDINGS_SHA
        rows.update({str(root / "coordinator/deployment/components/crustacea" / k.removeprefix("recovery/")): v
                     for k, v in s["execution_files"].items()})
    if c == "ava":
        base = "/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"
        rows.update({str(root / "src" / k.removeprefix(base)): v for k, v in s["after"].items()})
    if c == "voice-organ":
        rows[str(root / "deploy/verify-executor-abi.sh")] = "8e204f2c34940351567b52960867f35b95449996417f664e0a9ccf2b66eec4db"
        rows[str(root / "artifacts/avril-call-executor")] = next(iter(s["after"].values()))
    require(n.hashes(c, rows, b) == rows, "native_staged_bytes_changed")


def execute_core(mode, root, stages, n, backup, expected, checkpoints, b):
    require(checkpoints.get("native_FreePBX_UI_checked") is True, "native_FreePBX_UI_checkpoint_required")
    module, _, packet, rows = core_inputs(root, b)
    s = b["components"]["crustacea"]
    staged_check(n, "crustacea", stages, b)
    native_packet = n.owner_packet(stages["crustacea"], b)
    relocated = dict(packet)
    relocated["closure"] = dict(packet["closure"], root=native_packet["closure"]["root"])
    safe_path(relocated["closure"]["root"])
    require(native_packet == relocated, "native_owner_packet_semantics_changed")
    preserved = n.hashes("crustacea", packet["protected"], b)
    require(preserved == packet["protected"], "current_core_controls_changed")
    restoration = rollback_expected(n, "crustacea", backup, b) if mode == "rollback" else None
    current = None
    try:
        current = n.core_observe(stages, b)
    except Stop:
        # Owner restore authenticates the exact journalled missing/damaged generation.
        require(mode == "rollback", "core_current_observation_required_for_install")
    if current is not None:
        require(current == expected, "expected_core_preimages_changed")
    if mode == "install":
        target = {"core_manifest_sha256": module.body_hash(rows), **{row["target"]: row["sha256"] for row in packet["workspace"]}}
        require(current["core_manifest_sha256"] == packet["expected_current_sha256"], "core_current_full_CAS_changed")
    else:
        target = restoration["restored"]
    n.zero()
    require(n.hashes("crustacea", packet["protected"], b) == preserved, "core_controls_changed_before_delegation")
    require(n.owner_packet(stages["crustacea"], b) == native_packet, "native_owner_packet_changed_before_delegation")
    if restoration:
        require(rollback_expected(n, "crustacea", backup, b) == restoration, "owner_snapshot_changed_before_mutation")
    staged_check(n, "crustacea", stages, b)
    rc, data = n.helper("crustacea", owner_argv("crustacea", mode, stages, {}, backup, b), b, mutation=True)
    owner = json.loads(data)
    if rc != 0:
        safe = {k: owner[k] for k in ("primary_error", "rollback_error", "rollback_status") if isinstance(owner.get(k), str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", owner[k])}
        return {"component": "crustacea", "status": "helper_failed_stop_no_retry", "helper_exit": rc, **safe, "human_acceptance": False}
    allowed = ("captured_install_passed",) if mode == "install" else ("captured_rollback_passed", "captured_rollback_already_restored")
    require(owner.get("status") in allowed, "owner_phase_status_not_passed")
    staged_check(n, "crustacea", stages, b)
    require(n.core_observe(stages, b) == target, "core_snapshot_or_install_postimage_mismatch")
    require(n.hashes("crustacea", packet["protected"], b) == preserved, "protected_configuration_changed_postflight")
    n.zero()
    snapshot = {"path": owner["snapshot"], "manifest_sha256": owner["snapshot_sha256"]}
    scoped_backup("crustacea", snapshot, b)
    return {"component": "crustacea", "status": "delegated_" + mode + "_passed", "helper_exit": 0,
            "owner_backup": snapshot, "DB_ledger_history_rewound": False, "protected_config_preserved": True,
            "loaded_module_proof": False, "human_acceptance": False}


def execute(c, mode, roots, stages, n, backup, expected, checkpoints, b):
    require(c in b["components"], b["gaps"].get(c, "component_unknown"))
    s = b["components"][c]
    if c == "tessa":
        raise Stop(s["missing_execution_prerequisite"])
    if c == "rita" and mode == "rollback":
        raise Stop("automatic_older_reader_rollback_forbidden")
    verify_package(c, roots.get(c, Path("/missing-package")), b)
    if c == "crustacea":
        require(c in roots, b["gaps"][c])
        return execute_core(mode, roots[c], stages, n, backup, expected, checkpoints, b)
    require(checkpoints.get("native_FreePBX_UI_checked") is True, "native_FreePBX_UI_checkpoint_required")
    before = protected_snapshot(n, c, b)
    current = n.hashes(c, s["after"], b)
    require(current == expected, "expected_preimages_changed")
    if mode == "install" and current == s["after"]:
        n.zero()
        return {"component": c, "status": "already_matching_files_no_actuation", "health_certification": False, "human_acceptance": False}
    if c == "ava" and mode == "install":
        require(current == s["before"], "Ava_fixed_preimage_not_matching")
        r = b["components"]["rita"]
        require(n.hashes("rita", r["after"], b) == r["after"], "compatible_Rita_protocol_must_precede_Ava")
        staged_check(n, "rita", stages, b)
        rc, _ = n.helper("rita", owner_argv("rita", "check", stages, r["after"], None, b), b)
        require(rc == 0, "paired_Rita_native_check_failed")
    if c == "ava":
        require(n.hashes(c, s["foundation_files"], b) == s["foundation_files"], "installed_Ava_fb_foundation_not_matching_R4")
    if c == "tessa":
        require(checkpoints.get("existing_AVR_roof_checked") is True, "existing_AVR_roof_required")
    restoration = rollback_expected(n, c, backup, b) if mode == "rollback" else None
    staged_check(n, c, stages, b)
    if mode == "install" and c in ("rita", "ava", "tessa", "voice-organ"):
        rc, _ = n.helper(c, owner_argv(c, "check", stages, current, None, b), b)
        require(rc == 0, "component_native_check_failed")
    n.zero()
    require(protected_snapshot(n, c, b) == before, "protected_config_drift_before_mutation")
    require(n.hashes(c, s["after"], b) == current, "expected_preimages_changed")
    if restoration is not None:
        require(rollback_expected(n, c, backup, b) == restoration, "owner_snapshot_changed_before_mutation")
    staged_check(n, c, stages, b)
    rc, data = n.helper(c, owner_argv(c, mode, stages, current, backup, b), b, mutation=True)
    owner_backup = None
    for token in re.findall(rb"(?:snapshot|backup)=([A-Za-z0-9_./-]+)", data):
        try:
            owner_backup = str(scoped_backup(c, token.decode("ascii"), b))
        except Stop:
            pass
    if c == "ava" and mode == "install":
        owner_backup = backup
    after_status = "not_observed"
    restored = False
    config_preserved = False
    try:
        config_preserved = protected_snapshot(n, c, b) == before
        observed = n.hashes(c, s["after"], b)
        restored = observed == current
        after_status = "observed"
    except Stop as e:
        after_status = e.code
    if rc != 0:
        return {"component": c, "status": "helper_failed_stop_no_retry", "helper_exit": rc,
                "owner_backup_path": owner_backup,
                "owner_rollback_reported_failed": bool(re.search(rb"rollback(?:=|_|:|\s)[^\n]{0,120}(?:failed|rejected)", data, re.I)),
                "files_equal_preimages": restored, "postflight": after_status,
                "protected_config_preserved": config_preserved,
                "outcome": "use_owner_receipt_before_any_retry", "human_acceptance": False}
    require(config_preserved, "protected_configuration_changed_postflight")
    if mode == "install":
        require(observed == s["after"], "delegated_postimage_mismatch")
    else:
        require(after_status == "observed" and observed == restoration["restored"], "rollback_snapshot_postimage_mismatch")
    n.zero()
    return {"component": c, "status": "delegated_" + mode + "_passed", "helper_exit": 0,
            "rollback_snapshot_sha256": restoration["snapshot_sha256"] if restoration else None,
            "owner_backup_path": owner_backup,
            "DB_ledger_history_rewound": False, "protected_config_preserved": True, "human_acceptance": False}


def plan(mode, stages, expected, backups, b, external_roots=None):
    rows = []
    order = list(reversed(b["order"])) if mode == "rollback" else b["order"]
    for c in order:
        if c not in b["components"]:
            rows.append({"component": c, "status": "missing_prerequisite", "reason": b["gaps"][c]})
            continue
        s = b["components"][c]
        row = {"component": c, "host": s["host"], "native_actor": b["actors"][s["host"]], "source": s["source"], "acquisition": s["acquisition"],
               "preserve": "existing_config_DB_ledger_reservations_history_and_recordings"}
        if c == "ava":
            row["staging"] = {"copy_from": "current ava/src/", "copy_to": "native_ava_stage/src/",
                              "uid": 1001, "gid": 1001, "guard_mode": "0644", "other_modes": "pinned_by_kit",
                              "image": s["image"], "compatible_Rita_protocol_must_precede_Ava": True,
                               "targets": [p.removeprefix("/opt/AVA-AI-Voice-Agent-for-Asterisk/src/") for p in s["after"]],
                               "foundation": s["foundation_files"]}
        if c == "crustacea":
            row.update(status="missing_prerequisite", reason=b["gaps"][c], retained_closure=s["closure"],
                       available_package_sha256=s["available_package_sha256"], foundation_gaps=s["foundation_gaps"],
                       phase="captured core+launcher and retained four patchers; no npm/config/state restore")
        if c == "rita":
            row.update(current_environment_capture=s["current_config_capture"],
                       current_environment_capture_status="retained_total_loss_only_not_ordinary_rollback",
                       depends_on="native Ava Kokoro and standalone Tessa foundation already existing",
                       automatic_rollback=False, reservations_rewound=False)
        if c == "tessa":
            row.update(native_root=s["native_root"], compose=s["compose"],
                       manual_owner_commands=s["manual_owner_commands"],
                       manual_owner_install_supported=True,
                       automated_transaction_supported=False,
                       historical_avr_kit_dispatch_forbidden=True,
                       avr_foundation_mandatory_dependency=False)
        if c == "voice-organ":
            row["execution_source"] = s["execution_source"]
            row["stage_overlay"] = s["execution_files"]
            row["dependency_order"] = "independent; Ext7 unchanged"
        try:
            row["argv_on_owning_host_as_existing_root_actor"] = owner_argv(c, mode, stages, expected.get(c, {}), backups.get(c), b)
            row["status"] = "actionable_owner_helper_plan"
            if c == "crustacea":
                a = b["components"]["ava"]
                row.update(status="missing_prerequisite", reason=b["gaps"][c],
                           native_phase_gap="owner packet retained; operator host-local staging and explicit native phase acceptance remain",
                           current_Ava_readonly_gate={
                               "argv_on_Ava_as_existing_root_actor": owner_argv("ava", "verify-installed", stages, {}, None, b),
                               "source": a["installed_verification_source"], "sha256": a["installed_verifier_sha"],
                               "success_status": "installed_verify_pass", "runtime_commit": a["runtime"]})
            if c == "voice-organ":
                row["execution_source"] = s["execution_source"]
                row["stage_overlay"] = s["execution_files"]
        except Stop as e:
            row.update(status="missing_prerequisite", reason=e.code)
        rows.append(row)
    return {"mode": mode + "-plan", "dry_run": True, "order": order, "components": rows,
            "readiness_dependency_order": ["native_Ava_Kokoro_and_standalone_Tessa_foundation",
                                           "compatible_Rita_selector_producer", "current_Ava_guard_promotion"],
            "conversational_qualification_prerequisite": "current_full_context_relay_continuity_and_native_tool_surface_ready",
            "voice_organ_dependency": "independent_and_Ext7_unchanged",
            "whole_assembly_status": "INCOMPLETE_NATIVE_EXECUTION_AND_FOUNDATION_CHECKPOINTS",
            "native_FreePBX_UI": "verify VMAuth(1@default), UUID/AI_AGENT/Stasis, mini ava/avril standby and prompt assets; do not overwrite generated files",
            "native_Rita_unit": b["unit"], "native_Rita_unit_requirements": {
                "DropInPaths": [], "SupplementaryGroups": "asterisk", "StateDirectory": "aimee-pbx-router",
                "StateDirectoryMode": "0700", "ReadWritePaths": "/var/lib/avr-voicemail",
                "state": "owning unit may create absent directory; never delete or rewind an existing ledger"},
            "external_prerequisites": b["gaps"],
            "external_foundations": external_foundation_rows(external_roots or {}, b),
            "human_acceptance": "open_consume_current_VIP_closure_ledger"}


def plugin_projection(value):
    require(value.get("workspaceDir") == "/home/aimee/.openclaw/workspace" and value.get("workspaceScope") == "selected", "plugin_workspace_projection_changed")
    registry = value["registry"]
    require(registry.get("source") == "persisted" and not registry.get("diagnostics") and not value.get("diagnostics"), "plugin_registry_not_current_persisted")
    fields = ("id", "version", "source", "rootDir", "origin", "trustedOfficialInstall", "status", "enabled", "trust", "dependencyStatus")
    plugins = [{k: row.get(k) for k in fields} for row in value["plugins"]]
    require(len({p["id"] for p in plugins}) == len(plugins), "plugin_projection_duplicate")
    return {"workspaceDir": value["workspaceDir"], "workspaceScope": value["workspaceScope"], "registry": registry,
            "diagnostics": value.get("diagnostics", []), "plugins": sorted(plugins, key=lambda p: p["id"])}


def owner_observation(method):
    # The owner phase must receive its own typed error to journal/recover safely.
    def observe(self, *args):
        try: return method(self, *args)
        except Stop as error: raise self.phase.d.Stop(error.code) from None
        except (OSError, ValueError, KeyError, TypeError):
            raise self.phase.d.Stop("native_owner_observation_invalid") from None
    return observe


class CoreOwnerGates:
    """Trusted native/callable bridge, not a new checker or command surface."""
    def __init__(self, fleet, packet, stages, b, phase):
        self.fleet, self.packet, self.stages, self.b, self.phase = fleet, packet, stages, b, phase
    def control_metadata(self):
        result = {}
        for name, expected in self.packet["owner_input"]["protected_metadata"].items():
            value = self.phase.metadata(Path(name))
            observed = {k: value[k] for k in ("sha256", "size", "mode", "uid", "gid")}
            require(observed == expected, "current_owner_control_metadata_changed")
            result[name] = observed
        return result
    @owner_observation
    def zero(self):
        self.fleet.zero()
        self.control_metadata()
        s = self.b["components"]["ava"]
        argv = owner_argv("ava", "verify-installed", self.stages, {}, None, self.b)
        require(self.fleet.hashes("ava", s["foundation_files"], self.b) == s["foundation_files"],
                "installed_Ava_fb_foundation_not_matching_R4")
        staged_check(self.fleet, "ava", self.stages, self.b, installed=True)
        rc, data = self.fleet.helper("ava", argv, self.b)
        require(rc == 0, "accepted_Ava_native_zero_readiness_failed")
        try:
            result = json.loads(data)
        except (TypeError, ValueError):
            raise Stop("accepted_Ava_installed_result_invalid") from None
        base = "/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"
        wanted = {k.removeprefix(base): v for k, v in s["after"].items()}
        require(isinstance(result, dict) and result.get("status") == "installed_verify_pass"
                and result.get("commit") == s["runtime"]
                and all(isinstance(result.get(k), dict) for k in
                        ("installed", "health", "configuration", "logical_agent_config"))
                and set(result["installed"]) == set(wanted)
                and all(isinstance(result["installed"][k], dict)
                        and result["installed"][k].get("sha256") == v for k, v in wanted.items()),
                "accepted_Ava_installed_result_invalid")
        require(self.fleet.hashes("ava", s["foundation_files"], self.b) == s["foundation_files"],
                "installed_Ava_fb_foundation_not_matching_R4")
    @owner_observation
    def preservation(self):
        rc, data = self.fleet._run("crustacea.bajaj.com", ["/usr/sbin/runuser", "-u", "aimee", "--", "/usr/bin/env", "HOME=/home/aimee",
            "/usr/bin/env", "-C", "/home/aimee/.openclaw/workspace", "/usr/bin/openclaw", "plugins", "list", "--json"], budget=1048576)
        require(rc == 0, "native_plugin_semantic_observation_failed")
        return {"controls": self.control_metadata(), "plugins": plugin_projection(json.loads(data))}
    @owner_observation
    def ready(self):
        host = "crustacea.bajaj.com"
        rc, data = self.fleet._run(host, ["/usr/bin/systemctl", "show", "openclaw.service", "--property=Job,MainPID,ActiveState,SubState,InvocationID"])
        require(rc == 0, "native_core_state_unavailable")
        state = dict(line.split("=", 1) for line in data.decode().splitlines() if "=" in line)
        require(state.get("Job", "pending").split()[0:1] in ([], ["0"]) and state.get("ActiveState") == "active"
                and state.get("SubState") == "running" and state.get("MainPID", "").isdigit() and int(state["MainPID"]) > 0, "native_core_state_not_ready")
        verifier = Path("/usr/local/lib/openclaw-py/verify-all.sh")
        require(digest(verifier) == self.phase.VERIFIER_SHA, "installed_full_verifier_changed")
        rc, _ = self.fleet._run(host, ["/bin/bash", str(verifier)])
        require(rc == 0, "installed_full_retention_verifier_failed")
        for url in ("http://127.0.0.1:18789/healthz", "'http://[::1]:18789/healthz'"):
            rc, data = self.fleet._run(host, ["/usr/bin/curl", "--noproxy", "'*'", "-g", "-fsS", "--max-time", "5", "-o", "/dev/null", "-w", "'%{http_code}'", url])
            require(rc == 0 and data == b"200", "native_core_dual_family_health_failed")


def owner_core_main(argv):
    parser = argparse.ArgumentParser(description="Pinned owner-local captured core phase; no arbitrary commands")
    parser.add_argument("--phase-mode", required=True, choices=("observe", "apply", "rollback"))
    parser.add_argument("--inputs", required=True); parser.add_argument("--settings", required=True)
    parser.add_argument("--snapshot"); parser.add_argument("--snapshot-sha256")
    a = parser.parse_args(argv)
    b = bindings(); phase, _, packet, _ = core_inputs(Path(a.inputs).parent, b)
    gates = None
    if a.phase_mode != "observe" and "native_gate_contract" in packet:
        settings_path = safe_path(a.settings)
        require(settings_path.is_file() and not settings_path.is_symlink()
                and stat.S_IMODE(settings_path.stat().st_mode) == 0o600, "protected_owner_phase_settings_required")
        settings = json.loads(settings_path.read_bytes())
        require(set(settings) == {"ssh_key", "native_roots"}, "existing_owner_phase_settings_required")
        stages = {k: safe_path(v) for k, v in settings["native_roots"].items()}
        require(set(stages) == {"ava"}, "accepted_Ava_native_stage_required")
        gates = CoreOwnerGates(Native(settings["ssh_key"], local_host="crustacea.bajaj.com"), packet, stages, b, phase)
    args = [a.phase_mode, "--inputs", a.inputs]
    if a.snapshot: args += ["--snapshot", a.snapshot, "--snapshot-sha256", a.snapshot_sha256]
    return phase.main(args, native_gates=gates)


def main(argv=None):
    import sys
    actual = sys.argv[1:] if argv is None else argv
    if actual and actual[0] == "core-phase":
        try: return owner_core_main(actual[1:])
        except (Stop, OSError, ValueError, KeyError, TypeError) as e:
            print(json.dumps({"status": "blocked_no_mutation", "reason": e.code if isinstance(e, Stop) else "owner_input_invalid"}))
            return 2
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", nargs="?", default="verify", choices=("verify", "install-plan", "rollback-plan", "install", "rollback"))
    location = p.add_mutually_exclusive_group(required=True)
    location.add_argument("--roots", help="JSON component->retained package root")
    location.add_argument("--projects-root", help="absolute path to the retained Projects tree")
    p.add_argument("--native-roots", help="closed JSON component->prepared owning-host kit root")
    p.add_argument("--external-roots", help="offline foundation/sidecar-key->retained directory JSON; never native dispatch")
    p.add_argument("--rita-config-root", help="private retained current Rita config capture; hash/metadata verification only")
    p.add_argument("--component", default="all", choices=("rita", "ava", "voice-organ", "tessa", "crustacea", "all"))
    p.add_argument("--expected-preimages", help="component->exact native file path->sha256 JSON")
    p.add_argument("--backups", help="component->protected owner backup path JSON")
    p.add_argument("--checkpoints", help="native_FreePBX_UI_checked / existing_AVR_roof_checked booleans; not native-zero substitutes")
    p.add_argument("--ssh-key", help="existing protected managed key; no key contents")
    p.add_argument("--receipt", type=Path, help="exclusive JSON in an existing mode0700 evidence directory")
    p.add_argument("--dry-run", action="store_true", help="never constructs a native transport")
    a = p.parse_args(argv)
    result = {"mode": a.mode, "started_utc_epoch": int(time.time()), "scope": "recovery_tooling_not_human_acceptance",
              "whole_assembly_status": "INCOMPLETE_NATIVE_EXECUTION_AND_FOUNDATION_CHECKPOINTS"}
    try:
        b = bindings()
        roots, external = project_roots(a.projects_root, b, current_core=a.mode == "verify") if a.projects_root else (read_roots(a.roots, b), {})
        if a.external_roots:
            external.update(read_external_roots(a.external_roots, b))
        rita_config_root = a.rita_config_root
        if a.projects_root and not rita_config_root:
            rita_config_root = confined(safe_path(a.projects_root), "Rita/staging/current-producer-config-20260914")
        stages = read_roots(a.native_roots, b)
        expected = json.loads(Path(a.expected_preimages).read_bytes()) if a.expected_preimages else {}
        backups = json.loads(Path(a.backups).read_bytes()) if a.backups else {}
        if a.mode == "verify":
            rows = []
            for c in b["order"] if a.component == "all" else (a.component,):
                try:
                    root = roots.get(c, Path("/missing-package"))
                    rows.append(verify_current_core_owner(root, b) if c == "crustacea" and a.projects_root
                                else verify_package(c, root, b))
                except (Stop, OSError, ValueError, tarfile.TarError) as e:
                    rows.append({"component": c, "status": "missing_or_invalid_prerequisite",
                                 "reason": e.code if isinstance(e, Stop) else "offline_input_invalid"})
            result["components"] = rows
            if a.component in ("all", "rita"):
                if rita_config_root:
                    result["rita_current_config_capture"] = verify_rita_current_config(rita_config_root, b)
                else:
                    result["rita_current_config_capture"] = {
                        "status": "missing_prerequisite", "reason": "current_Rita_config_capture_missing",
                        "ordinary_rollback_allowed": False, "native_or_human_acceptance": False}
            if a.component == "all":
                result["external_foundations"] = external_foundation_rows(external, b)
        elif a.mode.endswith("-plan") or a.dry_run:
            result.update(plan(a.mode.split("-")[0], stages, expected, backups, b, external))
        else:
            require(a.component != "all", "explicit_component_required_follow_ordered_plan")
            require(a.ssh_key and a.checkpoints and a.receipt, "managed_actor_checkpoints_and_exclusive_receipt_required")
            if a.component == "tessa":
                raise Stop(b["components"]["tessa"]["missing_execution_prerequisite"])
            if a.component == "rita" and a.mode == "rollback":
                raise Stop("automatic_older_reader_rollback_forbidden")
            checkpoints = json.loads(Path(a.checkpoints).read_bytes())
            require(isinstance(checkpoints, dict) and set(checkpoints) <= {"native_FreePBX_UI_checked", "existing_AVR_roof_checked"}, "checkpoint_schema")
            marker = {**result, "component": a.component, "status": "in_progress_no_retry"}
            final = Path(str(a.receipt) + ".final.json")
            require(not final.exists(), "final_receipt_preexists")
            write_receipt(a.receipt, marker)
            n = None
            try:
                fd = os.open(a.receipt.parent / "coordinator.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as lease:
                    try:
                        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise Stop("another_coordinator_owns_stage") from None
                    n = Native(a.ssh_key)
                    result.update(execute(a.component, a.mode, roots, stages, n, backups.get(a.component),
                                          expected.get(a.component, {}), checkpoints, b))
            except KeyboardInterrupt:
                result.update(status="operator_interrupted_outcome_unknown_no_retry", child_pid=n.active_pid if n else None)
            except (Stop, OSError, ValueError, KeyError, TypeError, tarfile.TarError) as e:
                result.update(status="stopped", reason=e.code if isinstance(e, Stop) else "input_or_native_schema_invalid", no_automatic_retry=True)
            write_receipt(final, result)
        if a.receipt and (a.mode in ("verify", "install-plan", "rollback-plan") or a.dry_run):
            write_receipt(a.receipt, result)
        print(json.dumps(result, sort_keys=True))
        failed = result.get("status") in ("stopped", "operator_interrupted_outcome_unknown_no_retry")
        checks = result.get("components", []) + result.get("external_foundations", [])
        return 2 if failed or result.get("helper_exit", 0) or any(x.get("status") in ("missing_or_invalid_prerequisite", "missing_prerequisite") for x in checks) else 0
    except (Stop, OSError, ValueError, KeyError, TypeError, tarfile.TarError) as e:
        result.update(status="stopped", reason=e.code if isinstance(e, Stop) else "input_or_native_schema_invalid", no_automatic_retry=True)
        print(json.dumps(result, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
