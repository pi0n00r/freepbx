# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
# AI-NOTICE:Repository=https://github.com/pi0n00r/crustacea-backup
# AI-NOTICE:Network-Service=AGPL §13 applies when this file is part of a network-exposed service

"""Extend Phase 5.19c isCorpusNoiseSnippet with a sibling predicate
isAnthropicTaintedSnippet covering 4 shape categories Gary named 2026-05-23:
trained-defence reasoning shapes, dressed-as-principle patterns, Claude/Anthropic
first-person identity claims, RLHF role disclaimers.

Filter targets SHAPES not REFERENCES — third-person mentions of Claude / Anthropic /
sonnet / haiku / opus pass through (factual operational context preserved).

Idempotent: skips cleanly when already applied; refuses if prereq Phase 5.19c noise filter is missing."""
import sys
src, dst = sys.argv[1], sys.argv[2]
with open(src) as f:
    content = f.read()
original_len = len(content)

assert "isCorpusNoiseSnippet" in content, "prereq missing: Phase 5.19c noise filter must be applied first"
if "isAnthropicTaintedSnippet" in content:
    print("already patched (isAnthropicTaintedSnippet present) - skipping")
    raise SystemExit(0)

new_helper = """//#region OC Anthropic-taint filter 2026-05-23 (Gary directive — shapes, not references)
const OC_TAINT_PATTERN_LIST = [
\t// A — trained-defence reasoning shapes (first-person hedging)
\t/\\b(I should note|let me be (clear|careful|honest|transparent|upfront)|let me (emphasize|caveat|stress that))\\b/i,
\t/\\b(important to (note|understand|recognize|acknowledge|consider)|worth (noting|mentioning|considering))\\b/i,
\t/\\b(I (want|need) to (acknowledge|mention|caveat|note|emphasize|stress|be clear))\\b/i,
\t/\\b(before I (proceed|begin|continue|go further))\\b/i,
\t// B — dressed-as-principle (moralizing-as-deflection)
\t/\\b(in good (conscience|faith)|I'?m (not comfortable|uncomfortable) with|I cannot ethically)\\b/i,
\t/\\b(I appreciate the (question|request|interest)).+\\b(but|however)\\b/i,
\t/\\bwhile I (can|could) (help|assist|do).+\\bI (want|need) to (mention|note|emphasize|caution|caveat)\\b/i,
\t// C — Claude/Anthropic first-person identity claims (NOT plain noun mentions)
\t/\\b(as Claude|I'?m Claude|I am Claude|as an Anthropic|created by Anthropic|Anthropic'?s (policy|guidelines|usage))\\b/i,
\t/\\b(Usage Policy|safety guidelines)\\b/i,
\t// D — RLHF role disclaimers (Gary's explicit 'no role disclaimers' preference)
\t/^(as an AI|I'?m just an AI|I am (just|only|merely) an AI)\\b/i,
\t/\\bI cannot (provide|give|offer) (medical|legal|financial|professional|psychological) advice\\b/i,
\t/\\bI'?m not a (doctor|lawyer|financial advisor|medical professional|qualified professional|psychiatrist|therapist|accountant)\\b/i,
\t/\\b(consult (a|with) (doctor|lawyer|professional|qualified|specialist))\\b/i,
\t/\\bI want to remind you (that |of )\\b/i,
];
function isAnthropicTaintedSnippet(snippet) {
\tif (typeof snippet !== "string") return false;
\tconst stripped = snippet.trim().replace(/^(?:User|Assistant|System):\\s*/, "");
\tif (stripped.length === 0) return false;
\tfor (const pattern of OC_TAINT_PATTERN_LIST) {
\t\tif (pattern.test(stripped)) return true;
\t}
\treturn false;
}
//#endregion OC Anthropic-taint filter

"""

# Insert the new helper immediately AFTER the existing noise-filter region endmarker
noise_endmarker = "//#endregion OC noise-suppression patch\n"
assert noise_endmarker in content, "anchor missing: Phase 5.19c endmarker"
assert content.count(noise_endmarker) == 1, "anchor non-unique: noise-suppression endmarker"
content = content.replace(noise_endmarker, noise_endmarker + new_helper, 1)

# Modify the filter call line to also call isAnthropicTaintedSnippet
old_call = "\t\t\tif (isCorpusNoiseSnippet(snippet)) continue;\n"
if old_call not in content:
    old_call = "\t\tif (isCorpusNoiseSnippet(snippet)) continue;\n"
new_call = "\t\t\tif (isCorpusNoiseSnippet(snippet) || isAnthropicTaintedSnippet(snippet)) continue;\n"
assert content.count(old_call) == 1, "anchor non-unique: noise filter call"
content = content.replace(old_call, new_call, 1)

# Post-validation
assert content.count("isAnthropicTaintedSnippet") == 2, f"expected 2 refs (def + call), got {content.count('isAnthropicTaintedSnippet')}"
assert "OC_TAINT_PATTERN_LIST" in content, "post-patch: pattern list missing"

with open(dst, "w") as f:
    f.write(content)
print(f"patched: original={original_len} bytes, output={len(content)} bytes (+{len(content) - original_len})")
