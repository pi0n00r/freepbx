# Crustacea recovery owner input — read-only

Date: 2026-09-14 EDT  
Scope: inputs for `/home/aimee/work/jd-vip-recovery-coordinator-successor-20260914-qhbig4dd`; no deployment, restart, state rewind, package recreation, or production write.

## Authority and identity boundary

- The verified captured current core/dependency/launcher closure remains the restoration input: archive SHA-256 `717a7eb89dbc5bf68a21b4e11691720059da13787c485fc4e3531234544d43cb`. It is not an instruction to invoke the historical npm installer.
- Compiled runtime source identity remains `6fd2c526...`; the clean Crustacea repository source observed for static workspace files is `108ca20b05932f058d7cddb8bbfef29c1a598f6c`. Neither identifies every loaded module by itself.
- The coordinator draft is an in-progress Junior-owned tree. Current observed file hashes are:
  - `deployment/recovery-coordinator.py`: `a0d87f81fff3ec6fdcf4f0ef174d1e4c371966589327dbca211851a207059c83`
  - `deployment/components/crustacea/captured-core-phase.py`: `d5f719405147017558995a78666c6d05c6dde6ce23edbcd70c04e4f5791e2faf`
  - `component-bindings-20260914.json`: `987c69bab8c7bebe0d801056944bd1447eaa5feee96b2ad4039d3911c32073e1`
- The supplied frozen phase label `ab5780b` is not resolvable as a Git object in this draft checkout. Treat Gary/Senior's independently retained `ab5780b` receipt as the phase authority; do not infer it from the mutable worktree hashes above.

## Existing zero-call and readiness contracts

### VIP native zero-call contract — already present; no new checker

Source: `deployment/recovery-coordinator.py`, method `Native.zero()`.

Exact remote argv through its existing authenticated fleet SSH primitive:

```text
/usr/sbin/asterisk -rx 'core show channels'
```

Acceptance is exit 0 plus both complete output lines:

```text
0 active channels
0 active calls
```

This is the coordinator-native primitive requested by Senior. `evidence/8-restore-zero-call.sh` is an offline restore verifier, not a production quiescence checker, and must not be substituted.

The captured phase currently requires a packet-file object shaped exactly as `{path, sha256, runner, args}` for both `zero_checker` and `ready_checker`. That schema is mismatched with the already-owned coordinator method. The bounded integration seam is to delegate the phase gate to `Native.zero()`/the coordinator observation interface (or pass a callable/native observation object), rather than create another executable. Junior owns that adapter choice.

### Ava zero/readiness contract — retained accepted helper

Source path on maintained Ava branch: `deploy/deploy-ava-prior-message-reference.py` at commit `87b4106748ac6e219ce45bb0f229911fca3b2d82`; file SHA-256 `4972d3a3151777fe9f0fb466ceaa4a3b04fbc1f84c998efc8e7e0265caa69139`.

Read-only argv when staged with its source candidate:

```text
/usr/bin/python3 -B deploy/deploy-ava-prior-message-reference.py --check-only
```

Its accepted contract requires: HTTP health `status=healthy`; `ari_connected=true`; integer `active_calls=0`, `active_sessions=0`, `asterisk_channels=0`; a separately authenticated native ARI `GET /ari/channels` returning an empty list/count 0; unchanged container ID, image and mount-set hash; unchanged logical all-agent snapshot and `config_hash`; and unchanged protected `.env`, YAML and Compose fingerprints. This is Ava's own phase gate and should not be simplified into only an HTTP status check.

### Crustacea code/readiness contract

Existing installed code-integrity verifier:

```text
/bin/bash /usr/local/lib/openclaw-py/verify-all.sh
```

File SHA-256 `44340e030e40770416bf1dbec9bac5b84efcf5868ed3c22701c70291e38234e5`, size 4,865, mode `0755`, owner `0:0`. It verifies the retained four dist patchers and the source-maintained CSR, dual-stack presence/UI/listener, and MCP private-network contracts. It is not alone a service-readiness test.

Existing service/readiness readback primitives are:

```text
/usr/bin/systemctl show openclaw.service --property=Job,MainPID,ActiveState,SubState,InvocationID
curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:18789/healthz
curl --noproxy '*' -g -fsS --max-time 5 'http://[::1]:18789/healthz'
```

Acceptance: no pending `Job`; `ActiveState=active`; `SubState=running`; numeric `MainPID>0`; and HTTP 200 on both loopback families. Read-only observation at receipt creation returned PID `352178`, no job, active/running, and HTTP 200 for IPv4 and IPv6. The phase must additionally rerun `verify-all.sh` and compare protected controls and plugin/workspace projections after restoration. This is an exact primitive/readback contract; no separate readiness executable presently exists.

## Current protected controls — metadata and hashes only

| Path | SHA-256 | Size | Mode | UID:GID |
|---|---|---:|---:|---:|
| `/home/aimee/.openclaw/openclaw.json` | `a7a91c99846211ea9c9d9bfbcb4c860f1ca5572dd1e42c0ae27b13319b2943bb` | 41,719 | 0600 | 1000:1000 |
| `/etc/systemd/system/openclaw.service` | `320d091c69bdcb77a97718d8a632a3fb57654359a723f0d62277e8bc6dab8977` | 674 | 0644 | 0:0 |
| `/etc/aimee-main-voice-relay.env` | `937039ef54b4306e3ce134f9c59c8e4f0c797103a165333df775d0cc8b12c9e9` | 833 | 0640 | 0:1000 |
| `/etc/systemd/system/aimee-main-voice-relay.service` | `edd47e7bf521890c0e0749255dd1e15bbb5f27de97edd0c0072c0e728b6f0077` | 641 | 0644 | 0:0 |

The phase should compare these as protected controls before and after. It must not restore configuration, SQLite, sessions, plugin registry state, or the relay environment from an old snapshot.

## Static Avril skill source-to-target bindings

Authoritative source for this recovery phase is the clean Crustacea checkout at source commit `108ca20b05932f058d7cddb8bbfef29c1a598f6c`, under `deploy/bajaj/workspace/skills/avril-call/`. Target root is `/home/aimee/.openclaw/workspace/skills/avril-call/`. The following nine deployable files are byte-equal source-to-target now:

| Relative path | SHA-256 | Target mode |
|---|---|---:|
| `SKILL.md` | `de143326ed1e914aae7099d6a94874be89c60eae45e1aa51ec9ca1bcaec4545d` | 0644 |
| `VERSION` | `7970711952a452e93ae80a3836e2198c2c4112973a58068ab08588aae2dfbc2d` | 0644 |
| `agents/openai.yaml` | `0156d9b4c41ca29ea0d4fd95b68f8906ed7a389291c88b3860a58fd3d86fc95c` | 0644 |
| `references/contract.md` | `d3e2e9c7a5c4c6c07f0f15bf7539582c6763e3b89cc58b769d2caa286834a1d1` | 0644 |
| `references/google-voice-acceptance.md` | `3e4d0f2f60e9417a8758c349586267d7d0bec575672e3f76922543364cb7d533` | 0644 |
| `scripts/materialize_call_recording.py` | `eaa691fbf15a92434b5f76462431126df413780391d8631b908dc7c586c0869b` | 0775 |
| `scripts/package.json` | `caf719503b85c719147cbc7609d0a297aa907fa3ce6cfd1907f8263108dd6ab3` | 0644 |
| `scripts/rita_internal_calls.d.ts` | `33c5026217bec052a16f30797cdd02b3fa668ac2b433c4b5b7dd3784c7cdd9f9` | 0644 |
| `scripts/rita_internal_calls.js` | `e1a36c69ae89532f9e1159152eba9bee983bf4b2c9be92c2893b1d680210b930` | 0644 |

Source-only tests `scripts/rita_internal_calls.test.js` (`cbc4cfdb...`) and `scripts/rita_opening_fields.test.js` (`1f54b003...`) are intentionally not installed into the workspace and should remain source/package QA, not static runtime targets.

Installed target-only `.openclaw/source-origin.json` has SHA-256 `778080838dd5eb08185b91517108d02f51475d015407184833f8222708714894`, size 145, mode 0600. It says source path `/home/aimee/.codex/skills/avril-call`, but that local source is currently older and byte-different in `SKILL.md`, `google-voice-acceptance.md`, and both Rita client files. Therefore it is metadata to preserve as a current target preimage, not an authority from which to repopulate the skill. The source binding above is the clean Crustacea commit.

## Plugin/index preservation contract

Use the native read-only command, before and after:

```text
/usr/bin/openclaw plugins list --json
```

Compare a sorted semantic projection containing top-level `workspaceDir`, `workspaceScope`, `registry`, `diagnostics`, and for every plugin: `id`, `version`, `source`, `rootDir`, `origin`, `trustedOfficialInstall`, `status`, `enabled`, `trust`, plus dependency installed/missing fields. Require exact projection equality, `workspaceDir=/home/aimee/.openclaw/workspace`, `workspaceScope=selected`, registry source `persisted`, and empty top-level/registry diagnostics. Current projection contains 80 plugins, 62 loaded/enabled; its sorted projection SHA-256 at observation was `d90e2ff84b4e30692508bfafd63206957ae32c1fdcf62ba124b28a26aacadee2`.

The current Matrix entry is a trusted official global install rooted under `/home/aimee/.openclaw/npm/projects/openclaw-matrix-e2adb32e7f__openclaw-generation__g-ecd0f1a7214b03c3/node_modules/@openclaw/matrix`, version `2026.9.4`, with all required and optional dependencies installed. Preserve its root and dependency projection exactly. Do not restore or rewrite `/home/aimee/.openclaw/state/openclaw.sqlite`; the semantic command readback is the index preservation gate.

## Genuinely unavailable / unresolved inputs

1. No standalone Crustacea readiness checker file exists. The coordinator should bridge the exact systemd + dual-family health + `verify-all.sh` primitives above instead of manufacturing a parallel checker.
2. No standalone VIP zero-call checker is needed or authorized; the existing `Native.zero()` contract is authoritative.
3. The asserted frozen `ab5780b` object is not present in the mutable coordinator checkout inspected here; its independently retained source packet/receipt must supply that immutable identity.
4. A current loaded-module origin certificate remains unavailable by design. The captured closure certifies current disk bytes, while the systemd/health/plugin checks certify post-restore operation and projection; neither should be relabelled as proof of historical loaded origin.

