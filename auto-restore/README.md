# Auto-Restore Hook for FreePBX 17 Nag Suppression

A systemd Path-unit + oneshot Service-unit that re-applies a CSS-hide rule to FreePBX's dashboard LESS source after any module update overwrites the file. Equivalent to the well-known Proxmox VE pvenag hook in spirit, adapted to FreePBX's fwconsole-driven update model.

## Why this exists (and why the prior PHP shim doesn't work on FreePBX 17)

The repo's earlier SysadminOverride.class.php shim was written for the FreePBX 13–15 era when the "Expired Support Contract" notification was computed at render time by a global-namespace Sysadmin class. Defining an early-loaded stub in admin/libraries/ could pre-empt the real class and override getSupportStatus() / getExpiry().

On FreePBX 17 (verified against 17.0.28, 2026-04-27), that approach doesn't take, for two structural reasons:

1. **The Sangoma Sysadmin class is namespaced.** class_exists('Sysadmin') against the global namespace is always false even when the namespaced class is defined, so the shim defines a class no rendering code looks at.
2. **The notification is data-driven, not class-method-computed.** The "Expired Support Contract" panel renders directly from a row in FreePBX's notifications table inserted by the sysadmin module's periodic check. The dashboard widget reads the table; the shim's class methods are never called.

DOM evidence (FreePBX 17.0.28):

```html
<div class="panel panel-default panel-danger in" id="panel_support-contract-expired">
  <div class="panel-heading collapsed"
       data-notid="support-contract-expired"
       data-notmod="sysadmin"
       data-toggle="collapse"
       data-parent="#notifications_group"
       href="#link_support-contract-expired">
    <div class="actions">…</div>
    <div class="panel-title">Expired Support Contract.</div>
  </div>
  <div id="link_support-contract-expired" class="panel-collapse collapsed">…</div>
</div>
```

The notification's panel ID is derived from its data-notid panel_<notid>), so a single CSS rule indexes it precisely:

```css
#panel_support-contract-expired { display: none !important; }
```

This rule lives in the dashboard module's tracked LESS source /var/www/html/admin/modules/dashboard/assets/less/dashboard.less). Because FreePBX 17 ships **no custom-CSS hook** anywhere in the framework or dashboard module — verified by reading framework/amp_conf/htdocs/admin/assets/less/freepbx/ (no _custom.less, user.less, or override-import) and dashboard/assets/less/dashboard.less (no @import of any user file) — the rule has to live in a tracked file, which means a module update will overwrite it. The auto-restore hook is what keeps the rule in place across updates without human intervention.

## What this hook does NOT do

- **Does not bypass licensing.** The notification's underlying state is whatever Sangoma's License Manager reports; the hook doesn't touch it.
- **Does not unlock features.** SysAdmin Pro features remain inaccessible unless a valid license is present.
- **Does not impersonate a support contract.** UI-layer suppression of an inapplicable notice; no claim of an entitlement that doesn't exist.
- **Does not modify obfuscated module code or trigger any checksum check.** All edits are to plain LESS source, which is compiled by FreePBX's lessphp on next reload.

## Files

| File | Install location | Mode |
|---|---|---|
| freepbx-restore-nag-css.sh | /usr/local/bin/freepbx-restore-nag-css.sh | 0755 |
| freepbx-nag-css.path | /etc/systemd/system/freepbx-nag-css.path | 0644 |
| freepbx-nag-css.service | /etc/systemd/system/freepbx-nag-css.service | 0644 |

## Install

```bash
# 1. Drop the script and units into place
sudo install -m 0755 freepbx-restore-nag-css.sh /usr/local/bin/freepbx-restore-nag-css.sh
sudo install -m 0644 freepbx-nag-css.path    /etc/systemd/system/freepbx-nag-css.path
sudo install -m 0644 freepbx-nag-css.service /etc/systemd/system/freepbx-nag-css.service

# 2. Reload systemd so it sees the new units
sudo systemctl daemon-reload

# 3. Apply the rule for the FIRST time (the path watcher only fires on
#    changes; the initial state needs a manual application).
sudo /usr/local/bin/freepbx-restore-nag-css.sh

# 4. Trigger LESS recompile so the rule lands in the served CSS bundle
sudo fwconsole reload

# 5. Enable and start the path watcher
sudo systemctl enable --now freepbx-nag-css.path
```

## Verify

```bash
# The path watcher is active
systemctl status freepbx-nag-css.path
# Expected: Active: active (waiting)

# The rule is in the LESS file
grep freepbx-nag-suppression /var/www/html/admin/modules/dashboard/assets/less/dashboard.less
# Expected: at least one match

# Visit the FreePBX admin in a browser — the "Expired Support Contract" panel
# should no longer appear in the dashboard's notifications widget.
```

## Test the auto-restore behaviour

```bash
# Simulate the post-update overwrite by stripping the rule manually
sudo sed -i '/freepbx-nag-suppression/,/}$/d' /var/www/html/admin/modules/dashboard/assets/less/dashboard.less

# The path watcher should fire within ~2 seconds (sleep in service unit) +
# inotify latency
journalctl -u freepbx-nag-css.service -n 20
# Expected: a "Restored CSS rule to ..." log line within seconds of the sed

# Confirm the rule is back
grep freepbx-nag-suppression /var/www/html/admin/modules/dashboard/assets/less/dashboard.less

# Recompile LESS so the served CSS picks up the restored rule
sudo fwconsole reload
```

## Uninstall

```bash
sudo systemctl disable --now freepbx-nag-css.path
sudo rm /etc/systemd/system/freepbx-nag-css.path
sudo rm /etc/systemd/system/freepbx-nag-css.service
sudo rm /usr/local/bin/freepbx-restore-nag-css.sh
sudo systemctl daemon-reload

# Remove the rule from the LESS file
sudo sed -i '/freepbx-nag-suppression/,/}$/d' /var/www/html/admin/modules/dashboard/assets/less/dashboard.less
sudo fwconsole reload
```

## Architecture notes

**Why systemd Path units instead of dpkg post-invoke (Proxmox-style)?**

Proxmox VE's nag is in a deb-package-managed file, so its hook ties into apt/dpkg's post-invoke chain. FreePBX module updates are not apt-driven — they go through FreePBX's own fwconsole ma upgrade <module> mechanism, which downloads tarballs and overwrites files directly without ever invoking apt. dpkg hooks therefore wouldn't fire on the events we care about. systemd Path units use inotify on the file itself, catching the overwrite regardless of cause — apt update, fwconsole, manual edit, or any other process.

**Why no fwconsole reload inside the script?**

The triggering event in the common case is a module update. FreePBX runs its own reload at the end of every module update, which compiles the restored rule into served CSS. Adding a redundant reload mid-update would race against the in-flight reload (and is wasteful). For non-update triggers (manual file edit), the script's documented manual follow-up is fwconsole reload. The 2-second ExecStartPre=/bin/sleep 2 in the service unit gives multi-write update sequences time to settle before the marker check runs.

**Idempotency guard.**

The script checks for the freepbx-nag-suppression marker comment in the file before appending. If the marker is present, the script is a no-op. This makes it safe to run repeatedly (manual, scripted, or path-triggered) without bloating the file with duplicate rules.
