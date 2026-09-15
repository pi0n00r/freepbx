#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=pi0n00r-freepbx-integration
# AI-NOTICE:Repository=https://github.com/pi0n00r/freepbx
# AI-NOTICE:Network-Service=No
"""Verify the public, source-only backup of the Bajaj telephony integration."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


ROOT = Path(__file__).resolve().parent.parent
TREE = ROOT / "telephony"
MANIFEST = ROOT / "release/telephony-source-backup.sha256"
SOURCE_COMMIT = "f023339aba06c7e6990737b431a0ef546243a272"
SOURCE_TREE = "9d7d59477daeb5a6911a731988764e118da487c2"

DENIED_NAMES = re.compile(
    r"(^|/)(\.env($|\.)|id_(rsa|ed25519)|authorized_keys|known_hosts|"
    r"[^/]*\.(db|sqlite|sqlite3|pem|p12|pfx|key|jks|kdbx|age|tar|tgz|gz|zip))$",
    re.IGNORECASE,
)
DENIED_CONTENT = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(rb"\b(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{16,}", re.I),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(131072), b""):
            value.update(block)
    return value.hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def load_manifest(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (telephony/[^\r\n]+)", line)
        if not match:
            fail("backup_manifest_row_invalid")
        checksum, name = match.groups()
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != name:
            fail("backup_manifest_path_invalid")
        if name in rows:
            fail("backup_manifest_path_duplicate")
        rows[name] = checksum
    if not rows:
        fail("backup_manifest_empty")
    return rows


def verify(root: Path = ROOT, manifest_path: Path | None = None) -> dict:
    manifest = manifest_path or root / MANIFEST.relative_to(ROOT)
    tree = root / TREE.relative_to(ROOT)
    rows = load_manifest(manifest)
    actual = {
        path.relative_to(root).as_posix()
        for path in tree.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != set(rows):
        fail("backup_tree_members_changed")

    total_bytes = 0
    for name, checksum in rows.items():
        path = root / name
        if not path.is_file() or path.is_symlink():
            fail(f"backup_regular_file_required:{name}")
        if DENIED_NAMES.search(name):
            fail(f"backup_private_filename_rejected:{name}")
        body = path.read_bytes()
        if b"\0" in body:
            fail(f"backup_binary_payload_rejected:{name}")
        for pattern in DENIED_CONTENT:
            if pattern.search(body):
                fail(f"backup_secret_pattern_rejected:{name}")
        if hashlib.sha256(body).hexdigest() != checksum:
            fail(f"backup_sha256_changed:{name}")
        total_bytes += len(body)

    return {
        "ok": True,
        "status": "telephony_source_backup_verified",
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "files": len(rows),
        "bytes": total_bytes,
        "private_payloads": False,
        "native_action": False,
    }


def main() -> int:
    try:
        print(json.dumps(verify(), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        print(json.dumps({"ok": False, "status": "telephony_source_backup_failed", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
