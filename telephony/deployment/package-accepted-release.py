#!/usr/bin/env python3
# AI-NOTICE:License=AGPL-3.0-or-later
"""Amend the existing private coordinator kit without touching deployed services."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--relay", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    repo = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("coordinator", repo / "deployment/recovery-coordinator.py")
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    b = c.bindings()
    c.require(not subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]).strip(), "dirty_source")
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    c.require(c.digest(args.base) == "887c7cee1611a6b543f200036d229419dd05b62f9b8e63d968473c3b54497a6b", "base_skeleton_changed")
    c.verify_external_foundation("relay-current", {"relay-current": args.relay.resolve()}, b)
    _, base_rows = c.archive_rows(args.base)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    slug = "telephony-" + commit[:7]
    source = args.output / (slug + "-canonical.tar.gz")
    subprocess.run(["git", "-C", str(repo), "archive", "--format=tar.gz", "--prefix=telephony/", "-o", str(source), commit], check=True)
    _, source_rows = c.archive_rows(source)
    (args.output / (slug + "-canonical.sha256")).write_text("".join(row[0] + "  " + name + "\n" for name, row in sorted(source_rows.items())))
    for archive_path in (args.base, source):
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(args.output, filter="data")
    kit = args.output / "telephony"
    old_relay = (kit / "current-relay").resolve()
    c.require(old_relay.is_relative_to(args.output.resolve()), "replacement_outside_output")
    shutil.rmtree(old_relay)
    shutil.copytree(args.relay, old_relay)
    identity = {"source_commit": commit, "source_repository": "http://gittoit.bajaj.com:3000/bajaj/telephony",
                "source_files": len(source_rows), "runtime_changes_by_packaging": False,
                "ava_source": b["components"]["ava"]["source"], "ava_runtime": b["components"]["ava"]["runtime"],
                "relay_source": b["external_foundations"]["relay-current"]["source"],
                "human_memo_farewell_hangup": "GREEN", "call_id": "1789439347.39", "native_imap_uid": "21",
                "native_rtp_keepalive": 1, "direct_media": True,
                "native_amendment_sha256": c.digest(repo / "deployment/native/pjsip.endpoint_custom_post.conf"),
                "brief_outgoing_human_conversation": "PASS: three recognised turns",
                "farewell_hangup": "operator accepted; existing drained-audio fallback",
                "production_retention_authorised": True,
                "extended_human_nine_turn_recall_isolation": "not certified by brief call",
                "ext7_short_conversation_exception_applies_to_ext6": False,
                "whole_telephony_acceptance": False, "cold_host_recovery": False,
                "skeleton_is_private": True, "base_skeleton_sha256": c.digest(args.base)}
    encoded = json.dumps(identity, indent=2, sort_keys=True) + "\n"
    (kit / "PACKAGE-IDENTITY.json").write_text(encoded)
    (args.output / "SOURCE-IDENTITY.json").write_text(encoded)
    for name, row in source_rows.items():
        c.require(c.digest(kit / name) == row[0], "kit_source_changed:" + name)
    for name, row in base_rows.items():
        if name not in source_rows and not name.startswith("current-relay/") and name != "PACKAGE-IDENTITY.json":
            c.require(c.digest(kit / name) == row[0], "unrelated_retained_input_changed:" + name)
    inventory = {p.relative_to(kit).as_posix(): {"sha256": c.digest(p), "mode": p.stat().st_mode & 0o777, "size": p.stat().st_size}
                 for p in sorted(kit.rglob("*")) if p.is_file()}
    c.require(not any(p.is_symlink() for p in kit.rglob("*")), "kit_symlink")
    (args.output / "KIT-INVENTORY.json").write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    skeleton = args.output / (slug + "-skeleton.tar.gz")
    with tarfile.open(skeleton, "x:gz") as tar:
        tar.add(kit, arcname="telephony")
    _, readback = c.archive_rows(skeleton)
    c.require(readback == {n: (r["sha256"], r["mode"]) for n, r in inventory.items()}, "kit_skeleton_mismatch")
    (args.output / "SHA256SUMS").write_text("".join(c.digest(p) + "  " + p.name + "\n" for p in sorted(args.output.iterdir()) if p.is_file()))
    print(json.dumps({**identity, "kit_files": len(inventory), "kit_skeleton_equal": True,
                      "manifest_sha256": c.digest(args.output / "SHA256SUMS"), "output": str(args.output)}))


if __name__ == "__main__":
    main()
