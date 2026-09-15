<!--
AI-NOTICE:Schema-Version=0.1
AI-NOTICE:License=AGPL-3.0-or-later
AI-NOTICE:Project=pi0n00r-freepbx-integration
AI-NOTICE:Repository=https://github.com/pi0n00r/freepbx
AI-NOTICE:Network-Service=No
-->

# Independent FreePBX Integration Layer

This is an independently maintained integration and release layer for systems
built on FreePBX and Asterisk. It is not affiliated with, sponsored by,
endorsed by, or an official distribution of Sangoma Technologies or the
FreePBX project. FreePBX and Asterisk remain separately versioned upstream
dependencies.

The repository now also retains a source-only backup of the accepted Bajaj
telephony integration release. It is the integration and release layer around
FreePBX/Asterisk, Ava, Rita, Tessa, Voice Organ and Crustacea; it is not a copy
of FreePBX core or any component's private recovery kit. The backup is imported
from private source commit `f023339aba06c7e6990737b431a0ef546243a272`
(tree `9d7d59477daeb5a6911a731988764e118da487c2`) under `telephony/`.

The existing FreePBX 17 Sysadmin-notice calibration remains at its original
paths and is pinned by `release/freepbx-integration-lock.json`. Run both
offline verifiers before using retained source:

```sh
python3 -B scripts/verify-integration.py
python3 -B scripts/verify-telephony-backup.py
```

`release/telephony-source-backup.sha256` pins every imported file. The verifier
requires exact membership and hashes and rejects private-key material, bearer
credentials, common token assignments, environment files, databases, key
stores and private archives. This repository contains source and release
metadata only. Machine-specific configuration bytes, credentials, populated
recovery payloads, databases, ledgers, recordings and deployment receipts do
not belong here.

The tracked owner-input JSON files are schemas, content hashes and restoration
contracts from the accepted source—not secret values or captured payloads.
Restoration still requires separately retained private material and current
owner approval. Nothing in this repository performs a deployment merely by
being cloned or verified.

`release/telephony-source-backup.json` records the source identity, offline
test results and one preserved historical Ava-test limitation. The `telephony/`
subtree itself is byte- and mode-exact to the accepted private source tree;
public-backup metadata lives outside it so provenance remains directly
checkable with Git's subtree hash.

See `INDEPENDENT-FORK-NOTICE.md` for the project boundary. The historical
calibration documentation follows unchanged below.

## FreePBX Calibration Notes

Sterile documentation and overrides related to FreePBX Sysadmin / dashboard nag behavior. **Clarity only — not for advertising, endorsement, or feature unlocking.**

## Two approaches in this repo

| Approach | Where | FreePBX version | Status |
|---|---|---|---|
| **Auto-restore CSS-hide hook** (current) | auto-restore/ | **FreePBX 17+** | **Recommended.** Targets the data-driven notification panel directly; restored automatically across module updates via systemd Path-unit watcher (inotify-based, no cron). |
| **PHP class shim** (legacy) | SysadminOverride.class.php, DEPLOYMENT.md | FreePBX 13–15 | Historical. **Does not work on FreePBX 17** because the Sangoma Sysadmin class is namespaced and the nag is rendered from the notifications DB table, not from a class method. Kept for reference; see auto-restore/README.md for the diagnosis. |
| **Module-disable maneuver** | freepbx-sysadmin-nag-optics.md | All versions | Documented for completeness. **Not viable for SysAdmin Pro users** — disabling the sysadmin module disables the Pro extension as well. |

If you are on **FreePBX 17 with SysAdmin Pro purchased** and seeing the false "Expired Support Contract" nag despite never having entered into a support agreement (no trial signed, no maintenance purchased), use the auto-restore hook in auto-restore/. The legacy PHP shim approach in this repo's top level will not suppress the nag on FreePBX 17, regardless of how it's deployed.

## Files

| File | Purpose |
|---|---|
| auto-restore/README.md | Auto-restore hook overview, diagnosis of why the PHP shim doesn't work on v17, install / verify / test / uninstall steps |
| auto-restore/freepbx-restore-nag-css.sh | Idempotent restoration script |
| auto-restore/freepbx-nag-css.path | systemd Path unit (inotify watcher) |
| auto-restore/freepbx-nag-css.service | systemd oneshot Service unit (runs the script) |
| freepbx-sysadmin-nag-optics.md | Module-disable maneuver — historical |
| SysadminOverride.class.php | PHP shim — historical (FreePBX 13–15 era) |
| DEPLOYMENT.md | Install steps for the historical PHP shim |

## Scope

- Cosmetic suppression of misleading UI banners only.
- No impersonation of support contracts.
- No modification of obfuscated module code.
- No bypass of license checks; SysAdmin Pro features remain inaccessible unless properly licensed.
- Rationale for suppression: restoring UI accuracy where a banner asserts a contract state ("Expired Support Contract") that does not correspond to any agreement actually entered into. The OSS-community workarounds (unregister the install, re-register under a fresh deployment ID) are not viable for users who have purchased modules tied to the original deployment ID — both workarounds orphan the paid module's entitlement.

## Compatibility matrix

| FreePBX major | PHP shim | Module-disable | Auto-restore hook |
|---|---|---|---|
| 13 | ✓ works | ✓ disables nag (and module) | not needed |
| 14 | ✓ works | ✓ disables nag (and module) | not needed |
| 15 | ✓ works | ✓ disables nag (and module) | not needed |
| 16 | partial / unverified | ✓ disables nag (and module) | recommended for SysAdmin Pro users |
| 17 | **does not work** | ✓ disables nag (and module) | **recommended** |
