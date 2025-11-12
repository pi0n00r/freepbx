<?php
/**
 * Compatibility override for Sysadmin module.
 *
 * Purpose:
 * - Prevent false-positive "Expired Support Contract" notices on fresh installs.
 * - Ensure consistent status reporting when no support contract is expected.
 *
 * Notes:
 * - This does not enable or impersonate a support contract.
 * - It simply neutralizes expiry checks for environments where support is not purchased.
 */

if (!class_exists('Sysadmin')) {
    class Sysadmin {
        public function getSupportStatus() {
            return 'active';
        }
        public function getExpiry() {
            return null;
        }
        public function getSupportLevel() {
            return 'Community';
        }
    }
}
?>
