#!/usr/bin/env python3
# AI-NOTICE:License=AGPL-3.0-or-later
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "vm-shutdown" / "install-freepbx-vm-shutdown.sh"
DROPIN = ROOT / "vm-shutdown" / "10-vm-shutdown-budget.conf"


class VmShutdownInstallerTests(unittest.TestCase):
    def fixture(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        unit = root / "lib/systemd/system/freepbx.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\nExecStop=/usr/sbin/fwconsole stop\n")
        digest = hashlib.sha256(unit.read_bytes()).hexdigest()
        env = os.environ.copy()
        env["FREEPBX_VM_FIXTURE_ROOT"] = str(root)
        return td, root, digest, env

    def run_installer(self, action, digest, env):
        return subprocess.run(
            [str(INSTALLER), action, "--expected-unit-sha256", digest],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_check_does_not_install(self):
        td, root, digest, env = self.fixture()
        with td:
            result = self.run_installer("--check", digest, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "check_pass_not_installed")
            self.assertFalse((root / "etc/systemd/system/freepbx.service.d/10-vm-shutdown-budget.conf").exists())

    def test_install_is_atomic_and_idempotent(self):
        td, root, digest, env = self.fixture()
        with td:
            for _ in range(2):
                result = self.run_installer("--install", digest, env)
                self.assertEqual(result.returncode, 0, result.stderr)
            target = root / "etc/systemd/system/freepbx.service.d/10-vm-shutdown-budget.conf"
            self.assertEqual(target.read_bytes(), DROPIN.read_bytes())
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_unit_preimage_mismatch_fails_closed(self):
        td, _, _, env = self.fixture()
        with td:
            result = self.run_installer("--install", "0" * 64, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("freepbx_unit_preimage_mismatch", result.stderr)

    def test_existing_different_dropin_is_not_overwritten(self):
        td, root, digest, env = self.fixture()
        with td:
            target = root / "etc/systemd/system/freepbx.service.d/10-vm-shutdown-budget.conf"
            target.parent.mkdir(parents=True)
            target.write_text("[Service]\nTimeoutStopSec=1min\n")
            result = self.run_installer("--install", digest, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dropin_conflict", result.stderr)
            self.assertIn("TimeoutStopSec=1min", target.read_text())


if __name__ == "__main__":
    unittest.main()
