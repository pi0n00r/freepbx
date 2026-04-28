# FreePBX Calibration Notes

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
