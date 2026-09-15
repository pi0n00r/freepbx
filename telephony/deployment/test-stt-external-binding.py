import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("coordinator", HERE / "recovery-coordinator.py")
coordinator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinator)
INPUT = HERE.parent.parent / "inputs/ava-stt-current"


class SttExternalBinding(unittest.TestCase):
    def setUp(self):
        self.bindings = coordinator.bindings()

    def verify(self, root):
        with patch.object(coordinator.subprocess, "run", side_effect=AssertionError("Native transport forbidden")):
            return coordinator.verify_external_foundation("ava-stt-current", {"ava-stt-current": root}, self.bindings)

    def test_actual_retained_set_and_call_engine_are_separately_bound(self):
        self.verify(INPUT)
        stt = self.bindings["external_foundations"]["ava-stt-current"]
        self.assertEqual(stt["entries"], 17)
        self.assertFalse(stt["coordinator_native_dispatch"])
        self.assertFalse(stt["ordinary_configuration_overwrite"])
        self.assertEqual(self.bindings["components"]["ava"]["runtime"],
                         "52768f25309b81bb1d5d67a25d8b936c54b749dd")
        self.assertNotIn("ava-stt-current", self.bindings["order"])

    def tamper(self, relative, expected):
        with tempfile.TemporaryDirectory(prefix="jd-stt-binding-test-") as directory:
            root = Path(directory) / "kit"
            shutil.copytree(INPUT, root)
            path = root / relative
            with path.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(coordinator.Stop, expected):
                self.verify(root)

    def test_source_archive_change_is_rejected(self):
        self.tamper("ava-pi0n00r-6d87dfc-canonical.tar.gz", "external_manifest_member_hash_mismatch")

    def test_private_configuration_change_is_rejected(self):
        self.tamper("ava/protected/runtime-root/.env", "external_manifest_member_hash_mismatch")

    def test_manifest_change_is_rejected(self):
        self.tamper("SHA256SUMS", "external_manifest_hash_mismatch")

    def test_owner_receipt_keeps_historical_configuration_metadata(self):
        packet = HERE.parent / "owner-input"
        value = json.loads((packet / "INPUTS.json").read_bytes())
        historical = value["owner_input"]["historical_config_metadata"]
        self.assertEqual(historical["sha256"],
                         self.bindings["components"]["crustacea"]["historical_foundation"]["managed_config_sha256"])
        self.assertEqual(historical["size"], 41719)
        receipt = packet / value["owner_input"]["receipt"]
        self.assertEqual(coordinator.digest(receipt), value["owner_input"]["sha256"])
        self.assertIn(historical["sha256"], receipt.read_text())
        _, _, current, _ = coordinator.core_inputs(packet, self.bindings)
        self.assertNotEqual(current["protected"]["/home/aimee/.openclaw/openclaw.json"], historical["sha256"])

    def test_relabelling_historical_owner_metadata_as_current_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="jd-owner-attribution-test-") as directory:
            packet = Path(directory) / "owner-input"
            shutil.copytree(HERE.parent / "owner-input", packet)
            path = packet / "INPUTS.json"
            value = json.loads(path.read_bytes())
            value["owner_input"]["historical_config_metadata"]["sha256"] = value["protected"]["/home/aimee/.openclaw/openclaw.json"]
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(coordinator.Stop, "historical_owner_config_attribution_changed"):
                coordinator.core_inputs(packet, self.bindings)

    def test_native_gate_uses_current_amendment_without_rewriting_owner(self):
        root = HERE.parent / "owner-input"
        value = json.loads((root / "INPUTS.json").read_bytes())
        current = coordinator.current_core_binding(root, self.bindings)
        controls = value["owner_input"]["protected_metadata"]
        self.assertEqual(controls["/home/aimee/.openclaw/openclaw.json"], current["config"]["native"])
        phase = Mock()
        phase.metadata.side_effect = lambda path: dict(controls[str(path)])
        gates = coordinator.CoreOwnerGates(None, value, {}, self.bindings, phase)
        self.assertEqual(gates.control_metadata(), controls)
        name = "/home/aimee/.openclaw/openclaw.json"
        self.assertNotEqual(controls[name], value["owner_input"]["historical_config_metadata"])
        phase.metadata.side_effect = lambda path: {**controls[str(path)], "sha256": "0" * 64}
        with self.assertRaisesRegex(coordinator.Stop, "current_owner_control_metadata_changed"):
            gates.control_metadata()


if __name__ == "__main__":
    unittest.main()
