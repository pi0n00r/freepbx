# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=telephony
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("coordinator", Path(__file__).with_name("recovery-coordinator.py"))
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class ProjectRecoveryPaths(unittest.TestCase):
    def test_current_inputs_resolve_without_sonyhal_worktrees(self):
        roots, external = c.project_roots(Path("/retained/Projects"), c.bindings())
        self.assertEqual(roots["rita"], Path("/retained/Projects/Rita/staging/current-producer-20260914-r2"))
        self.assertEqual(external["relay-current"], Path("/retained/Projects/openclaw/staging/aimee-main-voice-71794f4-20260914-r1"))
        self.assertEqual(external["aigis-erratum"], Path("/retained/Projects/VIP/receipts"))
        self.assertTrue(str(roots["tessa"]).endswith("tessa-standalone-173c3bf-r2/tessa"))
        self.assertEqual(roots["crustacea"], Path("/retained/Projects/openclaw/staging/current-telephony-recovery-fa3323b-20260914-r4/package"))
        retained = list(roots.values())
        self.assertNotIn("/home/aimee/work", " ".join(map(str, retained + list(external.values()))))

    def test_builder_paths_and_traversal_are_rejected(self):
        for acquisition in ("/home/aimee/work/transient", "Documents/Projects/../../secret"):
            with self.subTest(acquisition=acquisition):
                bindings = copy.deepcopy(c.bindings())
                bindings["components"]["rita"]["acquisition"] = acquisition
                with self.assertRaises(c.Stop):
                    c.project_roots(Path("/retained/Projects"), bindings)

    def test_native_plan_roots_are_not_retargeted_by_offline_verification(self):
        roots, _ = c.project_roots(Path("/retained/Projects"), c.bindings(), current_core=False)
        self.assertEqual(roots["crustacea"], Path(c.__file__).resolve().parent.parent / "owner-input")

    def test_private_capture_is_verified_without_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture = root / "private.tar.gz"
            capture.write_bytes(b"opaque-private-capture")
            row = {"kind": "artifact", "archive": capture.name,
                   "archive_sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
                   "acquisition": "Documents/Projects/example", "role": "fixture", "fresh_host_restore": "fixture"}
            result = c.verify_external_foundation("private", {"private": root}, {"external_foundations": {"private": row}})
            self.assertEqual(result["entries"], 1)
            self.assertFalse(result["archive_extracted_or_links_dereferenced"])
            capture.write_bytes(b"changed")
            with self.assertRaisesRegex(c.Stop, "external_archive_hash_mismatch"):
                c.verify_external_foundation("private", {"private": root}, {"external_foundations": {"private": row}})


if __name__ == "__main__":
    unittest.main()
