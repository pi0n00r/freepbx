# Deployment Notes: SysadminOverride.class.php

## Purpose
This override neutralizes false-positive "Expired Support Contract" notices in FreePBX Sysadmin.  
It does not enable or impersonate a support contract.  
It only restores congruence between actual licensing state and UI behavior.

## Placement
Copy the file into the FreePBX libraries directory:
/var/www/html/admin/libraries/

## Activation
Reload FreePBX services after placement:
```bash
fwconsole reload
systemctl restart apache2   # Debian/Ubuntu
systemctl restart httpd     # RHEL/CentOS/Alma/Rocky
```

## Verification
Log into the FreePBX GUI.

Confirm the "Service Contract Expired" banner is suppressed.

If the banner persists, clear browser cache and reload.

## Rollback
To remove the override:
rm -f /var/www/html/admin/libraries/SysadminOverride.class.php
fwconsole reload
systemctl restart apache2   # or httpd
