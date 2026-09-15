#!/usr/bin/env python3
# relaxes P10 rule 2 because a bounded 512 KiB decoded response is allocated per chunk.
"""Materialize one hash-bound Avril recording through authenticated Isla MCP."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_ISLA_URL = "https://isla.bajaj.com/mcp/codex"
CHUNK_BYTES = 512 * 1024
MAX_CHUNKS = 64
MAX_RECORDING_BYTES = 25 * 1024 * 1024


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        fail(f"{name} is required")
    if len(value) < 16:
        fail(f"{name} is unexpectedly short")
    return value


def call_chunk(url: str, token: str, run_id: str, offset: int) -> dict[str, Any]:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": offset + 1,
            "method": "tools/call",
            "params": {
                "name": "isla_telephony_get_call_recording",
                "arguments": {
                    "run_id": run_id,
                    "offset": offset,
                    "limit": CHUNK_BYTES,
                },
            },
        }
    ).encode()
    request = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            rpc = json.load(response)
    except HTTPError as error:
        fail(f"Isla returned HTTP {error.code}")
    except URLError as error:
        fail(f"Isla connection failed: {error.reason}")
    content = rpc.get("result", {}).get("content", [])
    if not content or not isinstance(content[0].get("text"), str):
        fail("Isla returned no recording result")
    result = json.loads(content[0]["text"])
    if result.get("ok") is not True:
        fail(f"recording read failed: {result.get('error', 'unknown')}")
    return result


def validate_chunk(chunk: dict[str, Any], offset: int, expected_sha: str | None) -> bytes:
    if chunk.get("offset") != offset:
        fail("recording chunk offset mismatch")
    sha = chunk.get("audio_sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        fail("recording hash is missing or invalid")
    if expected_sha is not None and sha != expected_sha:
        fail("recording hash changed during materialization")
    try:
        data = base64.b64decode(chunk["data_base64"], validate=True)
    except (KeyError, ValueError, binascii.Error) as error:
        fail(f"recording chunk is not valid base64: {error}")
    if len(data) > CHUNK_BYTES:
        fail("recording chunk exceeds the bounded size")
    return data


def write_chunks(
    file: Any, url: str, token: str, run_id: str
) -> tuple[int, int, str, str]:
    digest = hashlib.sha256()
    offset = 0
    expected_sha: str | None = None
    expected_total: int | None = None
    for _ in range(MAX_CHUNKS):
        chunk = call_chunk(url, token, run_id, offset)
        data = validate_chunk(chunk, offset, expected_sha)
        expected_sha = chunk["audio_sha256"]
        total = chunk.get("total_bytes")
        if not isinstance(total, int) or total > MAX_RECORDING_BYTES:
            fail("recording total size is invalid")
        if expected_total is not None and total != expected_total:
            fail("recording total size changed during materialization")
        expected_total = total
        file.write(data)
        digest.update(data)
        next_offset = chunk.get("next_offset")
        if not isinstance(next_offset, int) or next_offset != offset + len(data):
            fail("recording chunk did not advance monotonically")
        offset = next_offset
        if offset > MAX_RECORDING_BYTES:
            fail("recording exceeds the 25 MiB transcription limit")
        if chunk.get("eof") is True:
            return offset, expected_total, expected_sha, digest.hexdigest()
    fail("recording exceeded the maximum chunk count")


def materialize(url: str, token: str, run_id: str, output: Path) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".{os.getpid()}.part")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(temporary, flags, 0o600), "wb") as file:
            offset, expected_total, expected_sha, materialized_sha = write_chunks(
                file, url, token, run_id
            )
        if materialized_sha != expected_sha:
            fail("materialized recording hash does not match Avril evidence")
        if offset != expected_total:
            fail("materialized recording length does not match Avril evidence")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"run_id": run_id, "path": str(output), "bytes": offset, "sha256": expected_sha}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--isla-url", default=os.getenv("ISLA_MCP_URL", DEFAULT_ISLA_URL))
    args = parser.parse_args()
    if not args.run_id.startswith("run_"):
        fail("run_id must be an Avril run identifier")
    token = require_env("ISLA_AUTH_TOKEN")
    result = materialize(args.isla_url, token, args.run_id, args.out)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
