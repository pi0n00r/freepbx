#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
# AI-NOTICE:Repository=https://github.com/pi0n00r/crustacea-backup
# AI-NOTICE:Network-Service=AGPL §13 applies when this file is part of a network-exposed service

"""
oc-rem-narrative-firegate-patch.py — Phase 5.19f (2026-05-25)

Removes REM phase fallback to raw entries when post-filter snippets is empty,
in /usr/lib/node_modules/openclaw/dist/dreaming-phases-nNBnlLlq.js. With this
patch, the existing empty-array guard in generateAndAppendDreamNarrative
(line ~654: `if (params.data.snippets.length === 0 && !params.data.promotions?.length) return;`)
fires cleanly — no narrative attempted, no model time wasted, no journalctl
"status=timeout for rem phase" noise. The synthetic-empty REM stub remains
the legitimate output when there's nothing meaningful to dream about.

Anchor (Gary 2026-05-25): "If there's legit no artifacts to dream about,
that is not an exception."

Pairs with Patches 1+2 (corpus filters) on the same file. Idempotent.
Atomic install (.tmp.<ts>.js → node --check → mv).

Re-apply after openclaw upgrade per PATCHES.md.
"""
import os
import glob
import shutil
import subprocess
import sys
from datetime import datetime, timezone

DIST = os.environ.get("OPENCLAW_DIST", "/usr/lib/node_modules/openclaw/dist")
TARGET_GLOB = os.path.join(DIST, "dreaming-phases-*.*js")
SENTINEL = "Phase 5.19f: no-artifacts is legitimate clean exit"

OLD = """		const snippets = preview.candidateTruths.map((t) => t.snippet).filter(Boolean);
		const themes = preview.reflections.filter((r) => !r.startsWith("- No strong") && !r.startsWith("  -"));
		const data = {
			phase: "rem",
			sourceEntryKeys: entries.map((entry) => entry.key),
			snippets: snippets.length > 0 ? snippets : entries.slice(0, 8).map((e) => e.snippet).filter(Boolean),
			...themes.length > 0 ? { themes } : {}
		};"""

NEW = """		const snippets = preview.candidateTruths.map((t) => t.snippet).filter(Boolean);
		const themes = preview.reflections.filter((r) => !r.startsWith("- No strong") && !r.startsWith("  -"));
		if (snippets.length === 0) params.logger.info(`memory-core: rem phase narrative skipped — no post-filter corpus (Phase 5.19f: no-artifacts is legitimate clean exit, not exception).`);
		const data = {
			phase: "rem",
			sourceEntryKeys: entries.map((entry) => entry.key),
			snippets,
			...themes.length > 0 ? { themes } : {}
		};"""


def main():
	matches = [path for path in glob.glob(TARGET_GLOB) if ".bak." not in path]
	assert matches, f"target not found: {TARGET_GLOB}"
	target = max(matches, key=os.path.getsize)
	assert os.path.isfile(target), f"target not found: {target}"
	with open(target, "r", encoding="utf-8") as f:
		content = f.read()
	assert len(content) > 1000, f"target file unexpectedly small: {len(content)} bytes"

	if SENTINEL in content:
		print(f"already patched (sentinel '{SENTINEL[:40]}…' present) — skipping")
		return 0

	if OLD not in content:
		print("MISSING anchor — file may have been upgraded; check dist source", file=sys.stderr)
		return 1
	if content.count(OLD) != 1:
		print(f"DUPLICATE anchor ({content.count(OLD)}); aborting", file=sys.stderr)
		return 1

	new_content = content.replace(OLD, NEW, 1)
	assert SENTINEL in new_content, "patched content missing sentinel"
	assert new_content.count(NEW) == 1, "replacement didn't apply exactly once"

	ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
	backup = f"{target}.bak.{ts}"
	shutil.copy2(target, backup)
	print(f"backup created: {backup}")

	tmp = f"{target}.tmp.{ts}.js"
	with open(tmp, "w", encoding="utf-8") as f:
		f.write(new_content)
	os.chmod(tmp, os.stat(target).st_mode)
	check = subprocess.run(["node", "--check", tmp], capture_output=True)
	if check.returncode != 0:
		print(f"node --check FAILED:\n{check.stderr.decode()}", file=sys.stderr)
		os.remove(tmp)
		return 1
	os.rename(tmp, target)
	print(f"patch installed at {target} ({len(new_content)} bytes)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
