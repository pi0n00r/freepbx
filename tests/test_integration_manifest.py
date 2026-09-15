#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=pi0n00r-freepbx-integration
# AI-NOTICE:Repository=https://github.com/pi0n00r/freepbx
# AI-NOTICE:Network-Service=No

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("verify_integration", ROOT / "scripts/verify-integration.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntegrationManifestTests(unittest.TestCase):
    def copy_component(self, target: Path) -> Path:
        for source in (
            ROOT / "release/freepbx-integration-lock.json",
            ROOT / "auto-restore/README.md",
            ROOT / "auto-restore/freepbx-nag-css.path",
            ROOT / "auto-restore/freepbx-nag-css.service",
            ROOT / "auto-restore/freepbx-restore-nag-css.sh",
        ):
            destination = target / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return target / "release/freepbx-integration-lock.json"

    def test_current_component_verifies(self):
        result = MODULE.verify()
        self.assertEqual(result["status"], "integration_components_verified")
        self.assertEqual(result["components"], 1)
        self.assertEqual(result["files"], 4)
        self.assertFalse(result["native_action"])

    def test_changed_patch_file_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="freepbx-integration-test-") as directory:
            root = Path(directory)
            lock = self.copy_component(root)
            with (root / "auto-restore/freepbx-restore-nag-css.sh").open("ab") as stream:
                stream.write(b"changed\n")
            with self.assertRaisesRegex(ValueError, "component_size_changed"):
                MODULE.verify(root, lock)

    def test_affiliation_claim_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="freepbx-integration-test-") as directory:
            root = Path(directory)
            lock = self.copy_component(root)
            data = json.loads(lock.read_text(encoding="utf-8"))
            data["upstream_affiliation"] = True
            lock.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "independent_project_boundary_invalid"):
                MODULE.verify(root, lock)


if __name__ == "__main__":
    unittest.main()
