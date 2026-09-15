#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=pi0n00r-freepbx-integration
# AI-NOTICE:Repository=https://github.com/pi0n00r/freepbx
# AI-NOTICE:Network-Service=No

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "verify_telephony_backup", ROOT / "scripts/verify-telephony-backup.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TelephonyBackupTests(unittest.TestCase):
    def copy_backup(self, target: Path) -> Path:
        shutil.copytree(ROOT / "telephony", target / "telephony")
        manifest = target / "release/telephony-source-backup.sha256"
        manifest.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "release/telephony-source-backup.sha256", manifest)
        return manifest

    def test_current_source_backup_verifies(self):
        result = MODULE.verify()
        self.assertEqual(result["status"], "telephony_source_backup_verified")
        self.assertEqual(result["source_commit"], MODULE.SOURCE_COMMIT)
        self.assertEqual(result["source_tree"], MODULE.SOURCE_TREE)
        self.assertEqual(result["files"], 60)
        self.assertFalse(result["private_payloads"])
        self.assertFalse(result["native_action"])

    def test_unmanifested_private_file_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="telephony-backup-test-") as directory:
            root = Path(directory)
            manifest = self.copy_backup(root)
            (root / "telephony/.env").write_text("TOKEN=not-a-real-secret\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "backup_tree_members_changed"):
                MODULE.verify(root, manifest)

    def test_secret_literal_fails_closed_even_if_rehashed(self):
        with tempfile.TemporaryDirectory(prefix="telephony-backup-test-") as directory:
            root = Path(directory)
            manifest = self.copy_backup(root)
            target = root / "telephony/README.md"
            target.write_text("access_token=abcdefghijklmnop0123456789\n", encoding="utf-8")
            rows = manifest.read_text(encoding="utf-8").splitlines()
            replacement = f"{MODULE.digest(target)}  telephony/README.md"
            manifest.write_text(
                "\n".join(replacement if row.endswith("  telephony/README.md") else row for row in rows) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "backup_secret_pattern_rejected"):
                MODULE.verify(root, manifest)

    def test_changed_source_file_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="telephony-backup-test-") as directory:
            root = Path(directory)
            manifest = self.copy_backup(root)
            with (root / "telephony/README.md").open("ab") as stream:
                stream.write(b"changed\n")
            with self.assertRaisesRegex(ValueError, "backup_sha256_changed"):
                MODULE.verify(root, manifest)


if __name__ == "__main__":
    unittest.main()
