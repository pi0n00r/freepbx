#!/usr/bin/env python3
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=telephony
"""Seal the retained Rita binary with the current private native configuration."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--producer", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected_config = "9a416f37e4f47a07447b781a3d6f18f21b42ac3f920ae8ed87626b985269b449"
    if sha(args.config) != expected_config:
        raise RuntimeError("current native configuration hash mismatch")
    args.output.mkdir(mode=0o700)
    skeleton = next(args.producer.glob("*-skeleton.tar.gz"))
    with tarfile.open(skeleton, "r:gz") as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != "rita" or ".." in parts or not (member.isfile() or member.isdir()):
                raise RuntimeError("unexpected skeleton member")
        archive.extractall(args.output, filter="data")
    kit = args.output / "rita"
    for path in args.producer.glob("*-canonical.*"):
        shutil.copy2(path, args.output / path.name)
    metadata_path = kit / "private/native-config-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    expected = {row["target"].lstrip("/"): row for row in metadata["records"]}
    with tarfile.open(args.config, "r:gz") as archive:
        members = archive.getmembers()
        if {m.name for m in members} != set(expected) or not all(m.isfile() for m in members):
            raise RuntimeError("native configuration coverage mismatch")
        for member in members:
            row = expected[member.name]
            data = archive.extractfile(member).read()
            target = args.output / row["skeleton_member"]
            target.write_bytes(data)
            target.chmod(member.mode)
            row.update(sha256=hashlib.sha256(data).hexdigest(), size=member.size,
                       mode=f"{member.mode:04o}", uid=member.uid, gid=member.gid,
                       mtime=member.mtime)
            row.pop("same_as_previous_capture", None)
    shutil.copy2(args.config, kit / "private/private-native-current.tar.gz")
    metadata.update(capture_sha256=expected_config, capture_size=args.config.stat().st_size)
    write_json(metadata_path, metadata)
    recovery_path = kit / "CURRENT-RECOVERY.json"
    recovery = json.loads(recovery_path.read_text())
    recovery.update(authoritative_native_capture_sha256=expected_config,
                    recovery_revision="current-20260914-r2")
    write_json(recovery_path, recovery)
    deploy = Path(__file__).with_name("RITA-CURRENT-DEPLOY.md")
    shutil.copy2(deploy, kit / "DEPLOY.md")
    candidate_path = kit / "CANDIDATE.json"
    candidate = json.loads(candidate_path.read_text())
    candidate.update(current_recovery_capture_sha256=expected_config,
                     recovery_revision="current-20260914-r2")
    candidate["kit_files"] = {str(p.relative_to(kit)): sha(p) for p in sorted(kit.rglob("*"))
                              if p.is_file() and p != candidate_path}
    write_json(candidate_path, candidate)
    inventory = {str(p.relative_to(kit)): {"sha256": sha(p), "size": p.stat().st_size,
                                          "mode": p.stat().st_mode & 0o777}
                 for p in sorted(kit.rglob("*")) if p.is_file()}
    write_json(args.output / "KIT-INVENTORY.json", inventory)
    new_skeleton = args.output / "rita-6b0efd9-current-20260914-r2-skeleton.tar.gz"
    with tarfile.open(new_skeleton, "w:gz") as archive:
        archive.add(kit, arcname="rita")
    with tarfile.open(new_skeleton, "r:gz") as archive:
        observed = {m.name.removeprefix("rita/"): hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                    for m in archive.getmembers() if m.isfile()}
    if observed != {name: row["sha256"] for name, row in inventory.items()}:
        raise RuntimeError("skeleton and inspectable kit differ")
    sums = args.output / "SHA256SUMS"
    sums.write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(args.output.iterdir()) if p.is_file()), encoding="ascii")
    print(json.dumps({"output": str(args.output), "kit_files": len(inventory),
                      "kit_bytes": sum(r["size"] for r in inventory.values()),
                      "skeleton_equal": True, "skeleton_sha256": sha(new_skeleton),
                      "candidate_sha256": sha(candidate_path),
                      "kit_inventory_sha256": sha(args.output / "KIT-INVENTORY.json"),
                      "manifest_sha256": sha(sums), "production_changed": False}))


if __name__ == "__main__":
    main()
