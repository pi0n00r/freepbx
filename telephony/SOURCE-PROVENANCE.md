<!--
AI-NOTICE:Schema-Version=0.1
AI-NOTICE:License=AGPL-3.0-or-later
AI-NOTICE:Project=VIP
-->
# Source Attribution And Provenance

The current packaging amendment binds Ava runtime `27b936e` through exact
packaging source `92e848b` and relay source `71794f4`. It retains the other
component packets without changing any telephony runtime. Ava's entire current
source includes the retained receptionist-history and STT corrections; no
standalone historical patch is required to recover those changes. The
packaging helper and focused tests are fleet-authored under AGPL-3.0-or-later,
consistent with this coordinator.
Populated native configuration is confined to private deployment payloads.

This current-binding successor starts from immutable R10
`b066ea90232cfb6ad3d0a5bfcc6867961b7e38ab` plus accepted two-file Rita
producer-helper commit `435ec6f1af9bf0ff5aa466fc363f860fd6fac2de`.
`COPYING` is
the unmodified GNU Affero General Public License version 3 downloaded from
https://www.gnu.org/licenses/agpl-3.0.txt, SHA-256
`0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`.
Existing AGPL-3.0-or-later notices retain their later-version election.

The records below identify actual source and retained notices, not an inferred
copyright assignment from a Git author. No runtime package, model weights,
Matrix plugin dependencies, private capture or configuration is included in
this public source. Independently retained component packages remain governed
by their own source and notices. Their reference here is not relicensing.

## Copied Owner Helpers

The Rita producer helper and focused test are byte-exact donor files from
`435ec6f1af9bf0ff5aa466fc363f860fd6fac2de`. The helper loads only the retained
Rita module pinned at
`52c9182469c86c94f1406bfff8d495a9c29e78c5230711a5d5fe2bb4a93ed7f4`.

| This Source Path | SHA-256 |
|---|---|
| deployment/rita-producer/promote-producer.py | 85c02b6ce3d8c62281922959f495f50b3af951669d60feaff527eeb0ae1528a9 |
| deployment/rita-producer/test-promotion.py | 3a1bf4ff3102919c1ad1facf94ef36f114720304e10ae618963393d4c2d87665 |

The tracked historical Ava helper and test remain accepted bytes from the
owner's source archive at
`4d7a4214b9eaa0f82ecc527b0f99b4cdc940df88`. Both explicitly state
`AI-NOTICE:License=AGPL-3.0-or-later` and `AI-NOTICE:Project=Ava`.
They are not the current consumer helper. Current coordination directly consumes
the unmodified owner6f1788a helper from the hash-pinned retained Ava kit; it is
not copied into or relabelled as this source.

| This Source Path | SHA-256 |
|---|---|
| deployment/components/ava/deploy/deploy-ava-prior-message-reference.py | 3a7ca29ae24efbac26a1ba43711891c60a0024adef1e3c68059f1a6a42ad8f1f |
| deployment/components/ava/deploy/test-deploy-ava-prior-message-reference.py | 815205ce30d4f35601d79a5353b72d94370c9f9488a3ca54c5fd416f31f2279a |

The Voice Organ executor transaction and bridge source are bound to
`e9d197df7aa6a854e823c3f6012298f536bcbf81`, in the retained owner repository
`source/voice-organ/`. The transaction, replacement bridge and test explicitly
state AGPL-3.0-or-later and Project Voice-Organ. No calld implementation or Rust
executor binary is bundled here.

| This Source Path | SHA-256 |
|---|---|
| deployment/components/voice-organ/deploy/executor-transaction.py | b13dba8d35eeebcb3ed9eca470fee3547518c4d25a18892175f54eff59bbe95e |
| deployment/components/voice-organ/test_executor_transaction.py | a1f3eb84c3dac0c9f3f5fac7d0171ffa12f5b1ea214450aa0e6749eeaf1eff72 |

Crustacea recovery helpers match actual owner source
`89c461ae642815907c3dd8f4653490979be89ab4`. They explicitly state
AGPL-3.0-or-later and Project crustacea. The command template and retained
patcher/verifier notices identify https://github.com/pi0n00r/crustacea-backup;
their existing network-service notices are retained unmodified.

| This Source Path | SHA-256 |
|---|---|
| deployment/components/crustacea/captured-core-phase.py | ff5d727547490ac2ec821ba51b58b343d70102fb548c85813888ac0fe03523b7 |
| deployment/components/crustacea/core-workspace-recovery.py | d4c8606c0b3206a8903d4e58bcc4651214e43e00ade749d0dad34b4105774f3f |
| deployment/components/crustacea/install-core-phase.sh | e23bd07dcd48a69ef026b6ed2e2b188592ad7c8dbe4fe38eee3588ef0c32da64 |
| deployment/components/crustacea/openclaw-core-install.commands | 5ea4363ee5402b636a5c59eba8e4497953deb2c943fa1a0e1e3ba1f7a71d880d |

`component-bindings-20260914.json` records exact hashes for the replacement
bridge/ABI checker and all recovery execution files, including the four
retained patchers and verifier. `owner-input/INPUTS.json` binds their duplicate
owner packet copies, static source and owner receipt. Those retained notices
were inspected in the exact copied bytes; no absent donor copyright name has
been supplied by this index.

## Retained Avril Skill Source

All nine files below are byte-equal to actual Crustacea repository source at
`108ca20b05932f058d7cddb8bbfef29c1a598f6c`, under
`deploy/bajaj/workspace/skills/avril-call/`. They are retained at
`owner-input/static/skills/avril-call/` here.

| Relative Skill Path | SHA-256 |
|---|---|
| SKILL.md | de143326ed1e914aae7099d6a94874be89c60eae45e1aa51ec9ca1bcaec4545d |
| VERSION | 7970711952a452e93ae80a3836e2198c2c4112973a58068ab08588aae2dfbc2d |
| agents/openai.yaml | 0156d9b4c41ca29ea0d4fd95b68f8906ed7a389291c88b3860a58fd3d86fc95c |
| references/contract.md | d3e2e9c7a5c4c6c07f0f15bf7539582c6763e3b89cc58b769d2caa286834a1d1 |
| references/google-voice-acceptance.md | 3e4d0f2f60e9417a8758c349586267d7d0bec575672e3f76922543364cb7d533 |
| scripts/materialize_call_recording.py | eaa691fbf15a92434b5f76462431126df413780391d8631b908dc7c586c0869b |
| scripts/package.json | caf719503b85c719147cbc7609d0a297aa907fa3ce6cfd1907f8263108dd6ab3 |
| scripts/rita_internal_calls.js | e1a36c69ae89532f9e1159152eba9bee983bf4b2c9be92c2893b1d680210b930 |
| scripts/rita_internal_calls.d.ts | 33c5026217bec052a16f30797cdd02b3fa668ac2b433c4b5b7dd3784c7cdd9f9 |

The scripts package declares AGPL-3.0-or-later; the JS and declaration file
explicitly retain AI-NOTICE licence/Project rita/network-service statements.
The six other files have no file-level copyright, SPDX or AI-NOTICE statements
in the actual owner source inspected. This is recorded absence, not a fabricated
copyright holder or assertion that a notice was removed.

## Actual Donor Root Notices

The Ava owner's `ava/LICENSE` is MIT, SHA-256
`16d5df7ce103c3a94a0fc5d22275d5e79b029f7822c748bb0f65bf6efc3e951d`.
Its notice is reproduced verbatim below while the copied deployment files'
explicit AGPL-3.0-or-later statements remain unchanged.

```text
MIT License

Copyright (c) 2025 Asterisk AI Voice Agent contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

The Crustacea source owner's root `LICENSE` at source108ca is MIT, SHA-256
`73571b25326281d369087f469842c02444fe39faaecebda4d82ed21ff3a1c29d`.
Its notice is reproduced verbatim, not inferred from a repository name.
The referenced `THIRD_PARTY_NOTICES.md`, SHA-256
`c1d1bbc550feee74853eba104e347341569cbbbe37a9f77659993ca0766277d5`,
was also inspected: it records Pi/pi-mono and Control UI Octicon portions.
Neither those modules nor the Control UI is bundled in this source subset;
their runtime notices remain in the separately retained core package.

```text
MIT License

Copyright (c) 2026 OpenClaw Foundation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Third-party notices for incorporated or adapted code are recorded in
THIRD_PARTY_NOTICES.md.
```
