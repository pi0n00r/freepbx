#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=pi0n00r-freepbx-integration
# AI-NOTICE:Repository=https://github.com/pi0n00r/freepbx
# AI-NOTICE:Network-Service=No
"""Verify retained integration components without touching a FreePBX host."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "release/freepbx-integration-lock.json"
SCHEMA = "pi0n00r-freepbx-integration-lock-v1"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(131072), b""):
            value.update(block)
    return value.hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def verify(root: Path = ROOT, lock_path: Path = LOCK) -> dict:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        fail("integration_lock_schema_invalid")
    if data.get("project") != "pi0n00r/freepbx":
        fail("integration_project_invalid")
    if data.get("independent_project") is not True or data.get("upstream_affiliation") is not False:
        fail("independent_project_boundary_invalid")

    seen_components = set()
    seen_paths = set()
    verified = 0
    for component in data.get("components", []):
        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id or component_id in seen_components:
            fail("component_identity_invalid")
        seen_components.add(component_id)
        if component.get("status") != "retained":
            fail("component_status_invalid")
        for row in component.get("files", []):
            name = row.get("path")
            pure = PurePosixPath(name) if isinstance(name, str) else None
            if pure is None or pure.is_absolute() or ".." in pure.parts or str(pure) != name:
                fail("component_path_invalid")
            if name in seen_paths:
                fail("component_path_duplicate")
            seen_paths.add(name)
            path = root / name
            if not path.is_file() or path.is_symlink():
                fail(f"component_regular_file_required:{name}")
            if path.stat().st_size != row.get("size"):
                fail(f"component_size_changed:{name}")
            if digest(path) != row.get("sha256"):
                fail(f"component_sha256_changed:{name}")
            if row.get("git_mode") != "100644":
                fail(f"component_git_mode_invalid:{name}")
            if row.get("install_mode") not in (None, "0644", "0755"):
                fail(f"component_install_mode_invalid:{name}")
            verified += 1

    if verified == 0:
        fail("no_integration_component_files")

    script = (root / "auto-restore/freepbx-restore-nag-css.sh").read_text(encoding="utf-8")
    service = (root / "auto-restore/freepbx-nag-css.service").read_text(encoding="utf-8")
    path_unit = (root / "auto-restore/freepbx-nag-css.path").read_text(encoding="utf-8")
    if "freepbx-nag-suppression" not in script:
        fail("notice_calibration_marker_missing")
    if "freepbx-restore-nag-css.sh" not in service:
        fail("notice_calibration_service_binding_missing")
    if "dashboard.less" not in path_unit:
        fail("notice_calibration_path_binding_missing")

    return {
        "ok": True,
        "status": "integration_components_verified",
        "components": len(seen_components),
        "files": verified,
        "native_action": False,
    }


def main() -> int:
    try:
        print(json.dumps(verify(), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "status": "integration_verification_failed", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
