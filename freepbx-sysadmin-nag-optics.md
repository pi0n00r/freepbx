# Calibration Note: FreePBX Sysadmin Module — Nag Optics Suppression

## Context
Fresh FreePBX installs trigger a “Service Contract Expired” nag via the Sysadmin module — even without purchasing a support contract. This note documents a maneuver to suppress that optic without breaching licensing or support entitlements.

## Intent
Restore congruence between actual licensing state and UI behavior. No features unlocked. No support impersonated. No vendor revenue displaced.

## Maneuver
Disable the Sysadmin module (or Sysadmin Pro if purchased) to suppress the nag:
```bash
fwconsole ma disable sysadmin
