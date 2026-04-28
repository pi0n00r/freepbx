#!/bin/bash
# /usr/local/bin/freepbx-restore-nag-css.sh
#
# Restore the Suppress-Nag CSS rule into FreePBX's dashboard LESS source after
# a module update overwrites it. Idempotent: if the rule is already present
# (detected by marker comment) the script is a no-op.
#
# Companion units:
#   /etc/systemd/system/freepbx-nag-css.path     — inotify watcher
#   /etc/systemd/system/freepbx-nag-css.service  — runs this script
#
# Trigger model: the .path unit fires whenever dashboard.less is modified
# (overwritten by fwconsole ma upgrade dashboard, framework upgrade, manual
# edit, etc.). Same shape as the Proxmox VE nag-suppression hook but driven
# by inotify (via systemd) rather than dpkg post-invoke, because FreePBX
# module updates are not apt-driven.
#
# See Trilium note: FreePBX > Suppress Nag (kuk7RrPvh93c).
#
# Author: Gary Bajaj
# License: same as the host system; this script is plain shell, no dependencies.

set -euo pipefail

# --- Configuration ---------------------------------------------------------

# The LESS source we patch. dashboard.less is the natural home for the rule
# because the nag is rendered by the dashboard's notifications widget. Picking
# the dashboard module's LESS keeps the rule semantically scoped to where it
# applies.
LESS_FILE="/var/www/html/admin/modules/dashboard/assets/less/dashboard.less"

# Marker comment used for idempotency. Do not change without also changing
# the grep pattern below.
MARKER="freepbx-nag-suppression"

# The CSS rule to inject. Targets only the support-contract-expired
# notification by its derived panel ID. Source-verified against:
#   FreePBX/dashboard repo, dashboard.less @ master  (no custom-CSS hook)
#   live DOM @ vip.bajaj.com FreePBX 17.0.28         (data-notid="support-contract-expired", data-notmod="sysadmin")
read -r -d '' RULE <<'CSS' || true

/* freepbx-nag-suppression: do not remove. Auto-restored by /usr/local/bin/freepbx-restore-nag-css.sh
 * after FreePBX module updates overwrite this file. See FreePBX > Suppress Nag.
 * Suppresses the dashboard notification panel for the inapplicable
 * "Expired Support Contract" notice (no support contract was ever entered into).
 * Cosmetic only: does not modify any module code, license state, or feature.
 */
#panel_support-contract-expired { display: none !important; }
CSS

# --- Restoration ----------------------------------------------------------

# Bail (success) if the file does not exist — module is uninstalled or the
# path moved. Don't fail the systemd unit on this.
if [[ ! -f "$LESS_FILE" ]]; then
    logger -t freepbx-nag-suppression "LESS file not found at $LESS_FILE; skipping (module uninstalled or path changed)"
    exit 0
fi

# Idempotency: marker present means rule is already in place.
if grep -q "$MARKER" "$LESS_FILE"; then
    exit 0
fi

# Append the rule. mtime change will invalidate any LESS-compile cache on
# next page load. We do NOT call fwconsole reload here because the trigger
# event (a module update) will perform its own reload at end-of-update; calling
# reload mid-update would race against that and is wasteful for the
# manual-edit case.
printf '%s\n' "$RULE" >> "$LESS_FILE"
logger -t freepbx-nag-suppression "Restored CSS rule to $LESS_FILE"

# If you patched the file manually outside of an update, you may need to
# trigger a recompile yourself:
#   fwconsole reload
# (Not run here; see comment above.)
