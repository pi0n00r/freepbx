# Telephony

## Current Assembly

The current production amendment is native FreePBX endpoint-1
`rtp_keepalive=1`, applied through Config Edit with Direct Media still true.
The actual outgoing Rita-to-Extn-1 call passed three human turns, and Gary
accepted farewell/hangup and authorised production retention. See `DEPLOY.md`
for the exact recovery and readback procedure. No component binary changed.
Extn 7 alone may conclude its narrow receptionist task without sustaining an
open-ended conversation. Extn 6 retains full contextual multi-turn behaviour.
The extended human recall, interruption/isolation and fresh-host gates are
separate; this brief call does not certify them.

Offline recovery verification now uses the retained current-Core owner's
existing relocation flag, so it works from `Projects/` without recreating
Sonyhal build directories. Its exact captured Core is checked without replaying
historical patchers. The separately accepted relay remains `71794f4`; the older
relay bundled with the Core capture is not a deployment candidate. See
`DEPLOY.md` for the current command and the remaining native/fresh-host gates.

The deployed Extn 6 memo, spoken farewell and clean hangup gate is **GREEN**.
Call `1789439347.39` deposited exactly one native Voicemail message (UID 21),
then said Goodbye and hung up. Gary accepted its functional behaviour.
The missed first Yes, 21.236-second save and 101.209-second farewell wait are
separate follow-ups. Calendar-answer work and the Incident Controller remain
outside this telephony gate. This is not a fresh-host or complete multi-turn
incoming/outgoing qualification.

| Component | Current retained delivery | Scope |
| --- | --- | --- |
| FreePBX / VIP | Native configuration R2 plus the Password and Thank-you amendments below | Native Extn 6 mailbox-1 gate, Extn 7 selection, internal originate and routing |
| Ava | `Projects/Ava/staging/ava-accepted-four-payload-92e848b-20260914`; runtime `27b936e`, packaging-only source `92e848b`; includes the already-deployed STT correction | Shared speech/media; Extn 7 local Ministral receptionist, Extn 6 full Crustacea route |
| Rita | `Projects/Rita/staging/current-producer-20260914-r2` | Provider-neutral native originate, current-call control and voicemail helper; identical private skeleton and inspectable kit, with current Tessa selector |
| Tessa | `Projects/Tessa/staging/tessa-standalone-173c3bf-r2` | Standalone on Ava; uses Ava's Kokoro, not Avril |
| Voice Organ | `Projects/Voice-Organ` and its retained executor/recovery packet in the assembly bindings | Compatible native executor; Isla remains its API owner |
| Crustacea relay | `Projects/openclaw/staging/aimee-main-voice-71794f4-20260914-r1` | Exact source archive, per-file manifest, populated private skeleton and inspectable kit |
| AIgis presence/attention | `Projects/AIgis/staging/aigis-package-2026.9.4-942-g108ca20b059-20260914` | Existing evidence projection and attention routes, not the Incident Controller |

Relay `71794f4df835cc5e772c120e12a45fca107ca042` is deployed and published
in `bajaj/crustacea`. It preserves predecessor disconnect handling and projects
the existing memo tool into the full main-agent route. The native receipt is
`Projects/VIP/receipts/ext6-native-imap-deposit-1789439347.39-20260914.md`.
The saved WAV is Tessa synthesis of the confirmed text, not original caller
audio. Packaging changes no service, image, model, configuration or call route.

**Recovery uses PVE snapshots.** Garden VM 105 has checkpoint
`telephony-relay-8f86228`; its earlier `OK` snapshot is preserved. Do not use
historical file-level rollback helpers for further live changes. Check active
calls and preserve accrued work before a whole-VM restore. The populated kits
remain reconstruction inputs, not permission to replace a newer live assembly
with independently selected historical files.

The sealed R12 coordinator packet at
`staging/jd-vip-current-core-r12-4779657/package-r12-4779657-r2` is retained
reconstruction evidence. Its relay binding predates `71794f4`: use the current
relay packet above, not its older relay activation sidecars. R12's native Core
restore compatibility gap and fresh-host restoration remain unqualified; no
new Core changes are authorised by this relay update.

The wider remaining call gates are ordinary incoming and purpose-bearing
outgoing multi-turn Extn 6 conversation and Extn 7 behavioural preservation.
The focused incoming memo/native IMAP and spoken-farewell gate above passed;
do not reopen it solely for latency tuning.
The retained Ava LKG comparison found no lost speech/media configuration;
see `receipts/ava-lkg-current-configuration-comparison-20260914T172707-0400.md`.
Legible's current telephony guide was amended and raw-read back after deployment.

## Retained Project Inputs

The current acquisition paths are rooted at `Documents/Projects`, not at a
disposable Sonyhal checkout. Run this read-only check on Linux, preserving
the skeleton's Unix modes during extraction:

```sh
python3 -B deployment/recovery-coordinator.py verify --projects-root /absolute/path/to/Projects --component rita
```

Repeat with `--component ava`, `--component tessa`, and `--component voice-organ`.
Selecting one component verifies only that packet, not the external foundations
or complete assembly.

Rita's `current-producer-20260914-r2` repack changes no executable. It brings the
four private native files and standalone Tessa selector into both matching
deployment payloads. The source archive and source manifest are unchanged.
Tessa uses its current 19-file standalone kit, and relay verification binds the
50-entry `71794f4` packet. The former `retained-roots.json` was generated from
one builder's disposable directories and is superseded by `--projects-root`.

The dedicated Crustacea successor supplies current captured-Core recovery.
Its own verification and deployment procedure takes precedence over retained
historical Core patchers. No package verification is a handset, live IMAP,
fresh-host restoration, or behavioural acceptance receipt.

## Current PIN Prompt Amendment

The deployed Extn 6 female `af_bella` recording of `Password` is retained in
`staging/ext6-af-bella-password-prompt-final-20260914/`, with its exact source
manifest, installed configuration capture and `DEPLOYMENT-RECEIPT.md`.
FreePBX Config Edit and Apply Config loaded the original-language-preserving
override around native `VMAuthenticate(1@default)`. Wait(2), all other prompts
and Extn 7 remain unchanged. Installed audio hashes and loaded routing passed;
Gary subsequently confirmed the password prompt audibly female. The native
`auth-thankyou` acknowledgement was male on that test. Its matching female
assets are now installed; fresh handset audibility remains a separate open gate.

Its matching af_bella audio and build/install/rollback kit are retained at
`staging/oc-af-bella-auth-thankyou-20260914-r1/`, with the adjacent archive
and checksum. Senior independently verified the archive hash and all 26
package members, then installed its 14 native audio assets at zero calls with
matching hashes and ownership. The custom dialplan hash remained unchanged;
no reload or restart occurred. It contains no password, dialplan,
language-selection or routing changes. See
`receipts/auth-thankyou-package-parent-review-20260914.md` for activation.

Extn 7 retains the proven deposit adapter and existing Voicemail namespace.
Extn 6's repaired confirmed-message guard is installed; its native installed
verification passes. A new substantive message, caller confirmation and native
Voicemail content/date/receipt remain unverified. The two latest bounded
observations were unexercised, not failed calls. Spoken confirmation alone is
not a deposited-message receipt. See `receipts/telephony-closure-gates-20260914.md`.

## Retained Recovery Checkpoints

The following source checkpoints are historical evidence, not the current
live deployment or recovery procedure. The Current Assembly section above
takes precedence for component selection and PVE snapshot recovery.

Frozen coordinator R8 is retained under
`staging/jd-vip-plugin-budget-r8-20260914-2puZvamR/`. Senior independently
verified all 42 committed blobs, 61 retained aggregate hashes and 94 tests in
each Python mode. It raises only the native plugin-discovery output budget to
1 MiB; ordinary operations retain 131,072 bytes, with no capability filtering.
See `receipts/coordinator-r8-parent-acceptance-20260914.md`. The separate native
R8 stage is prepared. Parent passed the existing complete owner gates:
protected controls/plugin preservation before and after, PBX/Ava zero and
installed-state verification, and Crustacea readiness. See
`receipts/coordinator-r8-parent-native-gates-20260914.md`. No install or restart
occurred; native recovery execution and cold reconstruction remain unproved.
OC's separately retained root-transport receipt qualifies strict verified trust
and privileged access across all four owner hosts. That access is not a
restoration or human-call certificate.

Frozen coordinator R7 source and evidence are retained under
`staging/jd-vip-installed-owner-r7-20260914-v8upnn4q/`. Senior independently
passed 86 tests in each Python mode, verified 42 committed source files and
all 69 retained aggregate entries. It consumes Ava's maintained installed-state
verifier separately from the unchanged activation/apply/rollback helper.

Actual protected native stages/checks are verified for Rita, Ava, Voice Organ
and Tessa; their receipts are under `receipts/`. These checks install nothing.
Crustacea's corrected full native stage is now independently verified against
R7 source, input semantics, closure hashes and the expected key fingerprint.
Genuine rollback identities, actual native planning/recovery, cold-host
reconstruction and human acceptance remain open.
Do not promote this source checkpoint as a completed recovery release or use
the proposed staging layout as proof that a directory exists.

### Surrounding Recovery Inputs

The coordinator is not a complete replacement for these component foundations:

| Foundation | Existing recovery authority | Assembly requirement |
| --- | --- | --- |
| FreePBX | Native configuration R2 and the later Password/Thank-you packages listed above | Restore native configuration through UI/Config Edit; include later audio amendments rather than relying on R2 alone |
| Tessa | `Documents/Projects/Tessa/README.md` | Restore standalone Tessa on Ava with Ava's Kokoro prerequisite; Avril is optional standby, not a dependency |
| Voice Organ | `Documents/Projects/Voice-Organ` and `Documents/Projects/Isla/README.md` | Retain the Isla application/managed authentication foundation, not just the executor |
| Model and document connectors | `Documents/Projects/Jaime/README.md` and `Documents/Projects/Bridgette/README.md` | Verify the managed model provider and enabled authenticated MCP services independently |
| Crustacea and presence/attention | `Documents/Projects/openclaw/README.md` and `Documents/Projects/AIgis/README.md` | Retain the current projection modules, external Matrix/plugin dependencies and managed HA/Isla/node/channel configuration in addition to the core closure |

The nine-file Avril skill overlay is not the whole presence/attention recovery
payload. Existing-host rollback preserves current controls, registries and
accrued state; total-loss reconstruction needs their independently retained
recovery inputs. These links identify owners, not proof that each dependency
has passed fresh-host recovery. No Incident Controller is included here.

Current additional inputs are retained in their owning projects:

- AIgis: `Documents/Projects/AIgis/staging/aigis-package-2026.9.4-942-g108ca20b059-20260914/`. Parent verified the 53-file transfer, exact predecessor delta and 206 passing tests in both Node modes; the separate receipt erratum corrects one recorded log hash without changing payloads.
- Matrix: `Documents/Projects/openclaw/staging/matrix-generation-g-ecd0f1a7214b03c3-20260914-r1/`. The complete private generation has 4,542 regular files, 337 directories and four symlinks, independently archive-verified; its external core link requires the separately retained compiled-core foundation.
- Managed Crustacea configuration: the current amendment is `Documents/Projects/openclaw/staging/current-managed-config-20260914-df5b26d5/`, after the reviewed obsolete disabled-provider cleanup. The older `current-managed-config-20260914-a7a91c99/` remains immutable historical evidence. Parent matched the final current archive to the protected owner postimage and checked the published source branch and Legible guidance; see `Documents/Projects/AIgis/receipts/custom-anthropic-cleanup-parent-review-20260914.md`. Use the current amendment for total-loss reconstruction, not an older frozen map's configuration snapshot. Preserve current configuration and accrued session/ledger state on ordinary rollback; do not substitute an older whole-kit configuration.
- AVR foundation: `Documents/Projects/Avril/staging/avr-foundation-private-20260914-ifc4hm4k/`. Its protected 32-file host-input amendment complements, rather than replaces, Tessa's component kit and image/model acquisition requirements.
- LocalAI 4.8.2: `Documents/Projects/LocalAI/AImee/staging/localai-4.8.2-recovery-6ef8d6d-20260914/`. The recipe revision is distinct from the application version. Parent verified 22 aggregate entries and the package verifier in both Python modes. Exact GGUF acquisition is bound separately in `receipts/localai-model-acquisition-20260914.md`.

These are retained candidates/amendments, not completed whole-host recovery
releases. Their independent acceptance receipts live under `receipts/`.
Junior's full-byte direct Nextcloud readback verified all 86 requested entries:
LocalAI 22/22, AIgis 53/53 and Matrix 11/11, without retries or mismatches. See
`receipts/jd-server-retention-20260914-localai-aigis-matrix-r1/SERVER-RETENTION-SUMMARY.md`.
This closes server retention, not package promotion or restoration acceptance.
Seedpod's active `/opt` EIO remains a separate unresolved storage gate despite
Garden's currently healthy backing pool; see
`receipts/seedpod-parent-hypervisor-storage-20260914.md`. Do not activate or
certify an assembled restore merely because file manifests pass.

The R9 assembly-verification candidate is retained at
`staging/jd-vip-external-foundations-r9-20260914-wgk03z7g/`, source commit
`cd02a19acc1f62fbc7aa19d9ceed392f9ee29432`. Read its `vip/README.md` before
using the component and external root maps. Parent independently verified
119 tests in each Python mode, actual retained-input verification, both archives
and the full 98-entry transfer. See
`receipts/coordinator-r9-parent-source-verification-20260914.md`.
This wires external foundations into verification without changing native
dispatch. Direct server readback now verifies all 98 entries plus the manifest;
the parent independently checked all 99 receipt rows and stable ETags. It is
not promotion, restoration or human-call acceptance; the licence/provenance
successor remains a separate publication gate.

The licence/provenance-only R10 successor is frozen at
`staging/jd-vip-licensing-r10-20260914-sc24fbdy/`, source commit
`b066ea90232cfb6ad3d0a5bfcc6867961b7e38ab`. It adds the complete received
AGPL text and explicit source provenance without changing the 42 existing
source files or operational behaviour. Parent independently checked 119 tests
in each Python mode, 44 canonical files, 74 kit files, and the retained server
receipt's 109 hashes/sizes. See
`receipts/coordinator-r10-parent-source-verification-20260914.md` and
`receipts/jd-r10-server-retention-20260914.json`. This closes the known
licence-text/attribution and private-retention gaps; public repository
designation/publication, native recovery and human acceptance remain open.

## Current Native Configuration Recovery Amendment

The current affected-configuration set is
`staging/native-config-recovery-2026.09.13-r2/`:

- `vip-freepbx-2026.09.13-native-config-r2-canonical.tar.gz` and matching `.sha256` manifest.
- `v2026.09.13-native-config-r2-skeleton.tar.gz`, populated privately.
- `vip/`, the ordinary inspectable matching kit; read `VIP-NATIVE-CONFIG-RESTORE.md` first.

It captures the applied mailbox-1 PIN lead-in Wait(2), Extension 1 RTP Timeout
180/current SDES media settings, and the existing Rita manager's read classes
`system,call,reporting,dialplan` with writes unchanged. Restore custom entries
only through native FreePBX UI/Config Edit, Save and Apply Config; do not
overwrite generated endpoint files. Protected manager configuration contains
the managed secret and must remain private.

Parent verified 30 aggregate entries, six canonical regular files and 15 matching
kit/skeleton files, including the post-apply manager hash. A subsequent native
call proved correlated answer, Extn 6 gate and mailbox-1 PIN acceptance. The
`.orig` file is now confirmed absent. Full human-call acceptance, current-call
action and external recording gates remain open. This is not a complete FreePBX
disaster-recovery certificate. This sealed R2 set predates the prompt amendment
above; do not mistake it for the latest sound/configuration capture.
The sealed R1 prechange amendment and older release artifacts remain intact.

## Retained Adapter Delivery

Current integration checkpoint: Crustacea core `2f02f65`, relay `8f86228`, and
the reviewed Ava STT successor `6d87dfc` are deployed. STT has now finalised a
real incoming caller question. That call still failed because its model answer
arrived after Gary hung up; it did not reach TTS. The subsequent relay fix
proves disconnect cancellation and ordinary reply/recall without changing
speech/media or model selection. These component checks do not replace the
remaining real-call and IMAP gate.

Release closure still requires contextual incoming/outgoing conversation and a
newly confirmed substantive message delivered to native IMAP Voicemail on this
same assembly, plus matching recovery deliverables. Schedule-reading and the
Incident Controller are excluded from this telephony gate. Earlier source,
health, PIN or speech-only passes do not replace the human and delivery gates.

Current FreePBX adapter delivery for Ava, Avril, the selector and Rita's native
voicemail helper. FreePBX generated files are not included or edited.

Current operator documentation is maintained in Legible as **VIP FreePBX —
Setup and Configuration Guide** and **VIP FreePBX — Operator Guide**. The
canonical archive retains its frozen release-era guide snapshots.
