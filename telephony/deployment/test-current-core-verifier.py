#!/usr/bin/env python3
# AI-NOTICE:License=AGPL-3.0-or-later
"""Offline delegation contracts, with no native calls or production inputs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("coordinator", Path(__file__).with_name("recovery-coordinator.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CurrentCoreVerifier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.kit = self.root / "crustacea"
        self.kit.mkdir()
        self.b = c.bindings()
        self.packet = {
            "runtime_commit": self.b["components"]["crustacea"]["compiled_runtime"],
            "restore_transform": "exact_captured_current_no_transform",
            "expected_current_sha256": "1" * 64,
            "protected": {"/usr/local/libexec/aimee-main-voice-relay": "2" * 64},
        }
        self.inputs = self.kit / "INPUTS.json"
        self.inputs.write_text(json.dumps(self.packet))
        self.receipt = {
            "status": "offline_exact_closure_verified",
            "archive_sha256": self.b["components"]["crustacea"]["closure"]["archive_sha256"],
            "core_manifest_sha256": "1" * 64,
            "native_execution": False, "config_restored": False,
            "DB_restored": False, "dependency_resolution": False,
        }

    def run_fixture(self, receipt=None, returncode=0):
        response = subprocess.CompletedProcess([], returncode,
                                               json.dumps(self.receipt if receipt is None else receipt),
                                               "private diagnostic must not escape")
        with mock.patch.object(c, "verify_external_foundation") as verify, \
                mock.patch.object(c.subprocess, "run", return_value=response) as run:
            result = c.verify_current_core_owner(self.root, self.b)
        return result, verify, run

    def test_exact_existing_verify_command_and_relocation(self):
        result, verify, run = self.run_fixture()
        self.assertEqual(run.call_args.args[0], [
            c.sys.executable, "-B", str(self.kit / "deploy/captured-core-phase.py"),
            "verify", "--inputs", str(self.inputs), "--closure-root", str(self.kit / "core")])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("shell", run.call_args.kwargs)
        verify.assert_called_once_with("current-core", {"current-core": self.root},
                                       {"external_foundations": {"current-core": self.b["components"]["crustacea"]["offline_owner"]}})
        self.assertFalse(result["native_or_human_acceptance"])
        self.assertFalse(result["fresh_host_recovery"])
        self.assertFalse(result["retained_relay_is_current"])
        self.assertEqual(result["current_relay_source"], "71794f4df835cc5e772c120e12a45fca107ca042")

    def test_package_drift_stops_before_executing_helper(self):
        with mock.patch.object(c, "verify_external_foundation", side_effect=c.Stop("external_manifest_member_hash_mismatch")), \
                mock.patch.object(c.subprocess, "run") as run:
            with self.assertRaisesRegex(c.Stop, "external_manifest_member_hash_mismatch"):
                c.verify_current_core_owner(self.root, self.b)
        run.assert_not_called()

    def test_obsolete_transform_is_rejected_before_helper(self):
        self.packet["restore_transform"] = "run_old_patchers"
        self.inputs.write_text(json.dumps(self.packet))
        with mock.patch.object(c, "verify_external_foundation"), mock.patch.object(c.subprocess, "run") as run:
            with self.assertRaisesRegex(c.Stop, "current_core_owner_contract_changed"):
                c.verify_current_core_owner(self.root, self.b)
        run.assert_not_called()

    def test_failed_helper_does_not_leak_diagnostics(self):
        with self.assertRaisesRegex(c.Stop, "^current_core_owner_verify_failed$"):
            self.run_fixture(returncode=2)

    def test_mutating_or_incorrect_receipt_cannot_pass(self):
        for key, value in (("native_execution", True), ("config_restored", True),
                           ("DB_restored", True), ("dependency_resolution", True),
                           ("archive_sha256", "0" * 64), ("core_manifest_sha256", "0" * 64),
                           ("status", "captured_install_passed")):
            with self.subTest(key=key), self.assertRaisesRegex(c.Stop, "current_core_owner_receipt_invalid"):
                self.run_fixture({**self.receipt, key: value})


if __name__ == "__main__":
    unittest.main()
