#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
# AI-NOTICE:Repository=https://github.com/pi0n00r/crustacea-backup
# AI-NOTICE:Network-Service=AGPL §13 applies when this file is part of a network-exposed service

"""
oc-narrative-timeout-extend-patch.py — Phase 5.19i (2026-06-01)

Raises NARRATIVE_TIMEOUT_MS in dreaming-narrative dist JS from 60s to 300s.

Target file: /usr/lib/node_modules/openclaw/dist/dreaming-narrative-*.js
              (the hash suffix changes on each OpenClaw build)

## Why this is not another incremental timeout bump

The pre-existing 60s value (`const NARRATIVE_TIMEOUT_MS = 6e4`) is shorter than
the current production workload. Dreaming now uses `gemma4-aimee` through
LocalAI on the aimee LXC's integrated Intel GPU. This is a shared-memory,
single-hot-model deployment, so prompt evaluation and generation can vary with
cache state and concurrent consumers.

The undersize issue is iGPU compute capacity, not CPU/GPU framing:

  • The 2026-07-26 production run was aborted by OpenClaw at 59.14s.
  • The same managed job remained healthy and running beyond 240s after the
    timeout gate was lifted.
  • Fleet agent and subagent ceilings are 900s, but a dream-diary narrative
    should fail much sooner than a general agent task if it is genuinely stuck.

This is a sizing correction to match actual hardware capacity, not an
unbounded wait. 300s provides:

  • five times the upstream 60s allowance;
  • enough room for the observed Gemma4 production run;
  • a bounded five-minute failure signal, rather than inheriting the general
    900s agent ceiling.

The prior incremental bumps (TimeoutStartSec 120→180 on the prewarm service) were
on the WRONG KNOB — prewarm was succeeding within its budget; the failure was at
the runtime NARRATIVE_TIMEOUT_MS downstream. This patch fixes the right knob.

## Anchor

Gary 2026-06-01: "Look into [dreaming timeouts] for a better fix than bumping the
timeout incrementally every troubleshooting session."

## Companion future work (not in this patch)

  • KV cache survival between prewarm (02:55) and dreaming (03:00) — verify
    the SOUL system-prompt prefix the dreaming-narrative subagent sends is
    bit-identical to what dreaming-prewarm.sh sends. If yes, prewarm gives a
    cache hit at 03:00 and prompt_eval is sub-second. If no, full re-eval
    happens at dreaming time. The 300s value covers cache-miss; prefix
    alignment would let dreaming finish much faster.
  • Aimee LXC contention pressure — what else hits LocalAI at 03:00 EDT
    (UMMA, booltool, heartbeat ticks)? If significant,
    consider shifting dreaming cron away from peak.
  • Upstream PR opportunity: expose NARRATIVE_TIMEOUT_MS via configSchema rather
    than hardcoded constant. Would eliminate the dist-patch requirement entirely
    (Tier-1 customization instead of Tier-2). See `feedback_openclaw_fork_avoidance_warn_on_tier3_drift.md`
    for the tier framework.

## Re-apply discipline

Per PATCHES.md, re-apply after every OpenClaw upgrade. The glob deliberately
absorbs the build-specific hash suffix.

Idempotent. Atomic install (.tmp.<ts>.js → node --check → install).
"""
import os
import glob
import shutil
import subprocess
import sys
from datetime import datetime, timezone

DIST = os.environ.get("OPENCLAW_DIST", "/usr/lib/node_modules/openclaw/dist")
TARGET_GLOB = os.path.join(DIST, "dreaming-narrative-*.*js")
SENTINEL = "Phase 5.19i: LocalAI Gemma4 needs 300s narrative timeout"

# Anchor must be unique. 6.6 upstream inserted intermediate constants between
# NARRATIVE_TIMEOUT_MS and DREAMING_SESSION_KEY_PREFIX (lines 45+53), so the
# 2-line composite anchor no longer matches. The single-line anchor below is
# uniquely present (verified 2026-06-12 against dreaming-narrative-msOWBXVS.js).
OLD = '''const NARRATIVE_TIMEOUT_MS = 6e4;'''

NEW = '''// Phase 5.19i: LocalAI Gemma4 needs 300s narrative timeout.
// The 2026-07-26 production run hit upstream's 60s abort while healthy and the
// same managed workload remained active beyond 240s. Five minutes covers the
// observed integrated-GPU variance without inheriting the general 900s agent
// ceiling.
// See oc-narrative-timeout-extend-patch.py for derivation.
const NARRATIVE_TIMEOUT_MS = 3e5;'''


def main():
    matches = [path for path in glob.glob(TARGET_GLOB) if ".bak." not in path]
    assert matches, f"target not found: {TARGET_GLOB}"
    target = max(matches, key=os.path.getsize)
    assert os.path.isfile(target), f"target not found: {target}"
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content) > 1000, f"target file unexpectedly small: {len(content)} bytes"

    if SENTINEL in content:
        print(f"already patched (sentinel '{SENTINEL[:50]}…' present) — skipping")
        return 0

    if OLD not in content:
        print("MISSING anchor — file may have been upgraded; check dist source", file=sys.stderr)
        print(f"expected anchor (first 120 chars):\n{OLD[:120]}", file=sys.stderr)
        return 1
    if content.count(OLD) != 1:
        print(f"DUPLICATE anchor ({content.count(OLD)}); aborting", file=sys.stderr)
        return 1

    new_content = content.replace(OLD, NEW, 1)
    assert SENTINEL in new_content, "patched content missing sentinel"
    assert new_content.count(NEW) == 1, "replacement didn't apply exactly once"
    # P10 assertion: new content has the intended five-minute constant.
    assert "const NARRATIVE_TIMEOUT_MS = 3e5;" in new_content, "patched constant missing"

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
        os.unlink(tmp)
        return 1
    print(f"node --check OK")

    # Atomic install — preserves ownership + mode
    shutil.move(tmp, target)
    print(f"patched: {target}")
    print(f"sentinel: {SENTINEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
