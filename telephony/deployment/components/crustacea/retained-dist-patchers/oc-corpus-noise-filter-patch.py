#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
# AI-NOTICE:Repository=https://github.com/pi0n00r/crustacea-backup
# AI-NOTICE:Network-Service=AGPL §13 applies when this file is part of a network-exposed service

"""Patch the compiled session-ingestion chunk to filter known noise placeholders.
P10: single purpose, anchor assertions on input + output, idempotent."""
import sys
src_path = sys.argv[1]
dst_path = sys.argv[2]
with open(src_path) as f:
    content = f.read()
if "isCorpusNoiseSnippet" in content:
    print("already patched (isCorpusNoiseSnippet present) - skipping")
    raise SystemExit(0)
assert "async function scanSessionIngestionSource" in content, "anchor missing: scanSessionIngestionSource"
compact_guard = "\t\tif (snippet.length < SESSION_INGESTION_MIN_SNIPPET_CHARS) continue;\n"
expanded_guard = "\t\tif (snippet.length < SESSION_INGESTION_MIN_SNIPPET_CHARS) {\n\t\t\tcontinue;\n\t\t}\n"
matching_guards = [guard for guard in (compact_guard, expanded_guard) if guard in content]
assert len(matching_guards) == 1, "anchor missing or ambiguous: MIN_SNIPPET_CHARS check"
helper = """//#region OC noise-suppression patch 2026-05-23 (Gary directive, Sat-pattern-informed)
const OC_STREAM_ERROR_FALLBACK_LITERAL = "[assistant turn failed before producing content]";
const OC_RETRY_MARKER_PREFIX = "[Retry after the previous model attempt failed or timed out]";
function isCorpusNoiseSnippet(snippet) {
\tif (typeof snippet !== "string") return false;
\tconst trimmed = snippet.trim();
\tconst stripped = trimmed.replace(/^(?:User|Assistant|System):\\s*/, "");
\tif (stripped === OC_STREAM_ERROR_FALLBACK_LITERAL) return true;
\tif (stripped.startsWith(OC_RETRY_MARKER_PREFIX)) {
\t\tconst tail = stripped.slice(OC_RETRY_MARKER_PREFIX.length).trim();
\t\tif (tail.length < 16) return true;
\t}
\tif (stripped.length < 8) return true;
\treturn false;
}
//#endregion OC noise-suppression patch

"""
content = content.replace(
    "async function scanSessionIngestionSource(params) {",
    helper + "async function scanSessionIngestionSource(params) {",
    1,
)
old_pair = matching_guards[0]
new_pair = old_pair + "\t\t\tif (isCorpusNoiseSnippet(snippet)) continue;\n"
assert old_pair in content, "second-pass anchor missing after helper insert"
content = content.replace(old_pair, new_pair, 1)
references = content.count("isCorpusNoiseSnippet")
assert references == 2, f"expected 2 isCorpusNoiseSnippet refs after patch, got {references}"
with open(dst_path, "w") as f:
    f.write(content)
print(f"patched: src={src_path} dst={dst_path} refs={references}")
