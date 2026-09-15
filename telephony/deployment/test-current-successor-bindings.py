#!/usr/bin/env python3
"""Focused current Rita/Tessa/relay bindings; local fixtures only."""
import contextlib
import ast
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("current_successor", HERE / "recovery-coordinator.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
B = c.bindings()
INPUTS = HERE.parent.parent / "inputs"
RELAY = INPUTS / "relay-current"
ACTIVATION = INPUTS / "relay-activation-current"


def relay_roots():
    return {"relay-current": RELAY, "relay-activation-current": ACTIVATION}


class CurrentSuccessorBindings(unittest.TestCase):
    def test_current_core_package_and_full_closure_are_actual_verified_inputs(self):
        result = c.verify_package("crustacea", HERE.parent / "owner-input", B)
        self.assertEqual(result["compiled_runtime"], "2f02f65dc6dce2eb203d2d1a468919d3b471e457")
        self.assertTrue(result["package_anchors_verified"])
        self.assertEqual(result["package_sha256"], "c840aebb3cee7df7b2829864de5d11d0fb5ddc01f4df388715949190373c8ef8")
        self.assertFalse(result["native_or_human_acceptance"])
        self.assertFalse(result["owner_restore_compatible"])
        self.assertIn("noise_taint", result["owner_restore_gap"])

    def test_current_core_package_tamper_fails_before_archive_read(self):
        original = c.digest
        package = B["components"]["crustacea"]["available_package"]
        def changed(path):
            return "0" * 64 if str(path) == package else original(path)
        with mock.patch.object(c, "digest", side_effect=changed), mock.patch.object(c.tarfile, "open") as opened:
            with self.assertRaisesRegex(c.Stop, "current_core_package_changed"):
                c.verify_current_core_package(HERE.parent / "owner-input", B)
        opened.assert_not_called()

    def test_current_core_package_anchor_budget_and_duplicates_are_bounded(self):
        for sizes in ((262145,), (1, 1)):
            with self.subTest(sizes=sizes):
                archive = mock.Mock()
                members = []
                for size in sizes:
                    member = tarfile.TarInfo('package/package.json')
                    member.size = size
                    members.append(member)
                archive.getmembers.return_value = members
                archive.extractfile.side_effect = lambda _: io.BytesIO(b'x')
                manager = mock.MagicMock()
                manager.__enter__.return_value = archive
                with mock.patch.object(c.tarfile, 'open', return_value=manager):
                    with self.assertRaisesRegex(c.Stop, 'current_core_package_anchor_invalid'):
                        c.verify_current_core_package(HERE.parent / 'owner-input', B)

    def test_current_core_snapshot_or_sidecar_drift_is_rejected(self):
        source = HERE.parent / "owner-input"
        for name, error in (("CURRENT-CORE-BINDING.json", "current_core_binding_changed"),
                            ("CURRENT-CORE-SNAPSHOT.json", "current_core_snapshot_changed"),
                            ("CURRENT-CONFIG-AMENDMENT.json", "current_core_config_amendment_changed")):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for p in source.glob("CURRENT-*.json"):
                    shutil.copy2(p, root / p.name)
                (root / name).write_bytes((root / name).read_bytes() + b" ")
                with self.assertRaisesRegex(c.Stop, error):
                    c.current_core_binding(root, B)

    def test_current_core_old_package_or_closure_cannot_be_called_current(self):
        for field, value, error in (("compiled_runtime", "6fd2c52616977226522e759ecbcfcca093e76295", "current_core_package_binding_changed"),
                                    ("available_package_sha256", "1a1dc62f6ef705bc2e516588cd6768638637e261c289562fc64e58e3018b912f", "current_core_package_binding_changed")):
            changed = copy.deepcopy(B)
            changed["components"]["crustacea"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(c.Stop, error):
                c.current_core_binding(HERE.parent / "owner-input", changed)
        changed = copy.deepcopy(B)
        changed["components"]["crustacea"]["closure"]["archive_sha256"] = "717a7eb89dbc5bf68a21b4e11691720059da13787c485fc4e3531234544d43cb"
        with self.assertRaisesRegex(c.Stop, "current_core_snapshot_binding_changed"):
            c.current_core_binding(HERE.parent / "owner-input", changed)

    def test_current_config_supersedes_old_capture_without_ordinary_rewind(self):
        current = c.current_core_binding(HERE.parent / "owner-input", B)
        value = json.loads((HERE.parent / "owner-input/INPUTS.json").read_bytes())
        self.assertEqual(value["protected"]["/home/aimee/.openclaw/openclaw.json"], current["config"]["native"]["sha256"])
        self.assertEqual(current["config"]["native"], {"sha256": "df5b26d5473880104b27ff12120edb9c776e007d8e3a3fc52d4465d537caaefc", "size": 41657, "mode": 0o600, "uid": 1000, "gid": 1000})
        self.assertTrue(current["config"]["total_loss_only"])
        self.assertFalse(current["config"]["ordinary_rollback_allowed"])
        self.assertEqual(current["config"]["supersedes_sha256"], B["components"]["crustacea"]["historical_foundation"]["managed_config_sha256"])
        self.assertIn("historical", B["external_foundations"]["managed-config"]["role"])

    def test_current_dist_targets_and_real_patcher_gap_are_not_waived(self):
        current = c.current_core_binding(HERE.parent / "owner-input", B)
        snapshot = current["snapshot"]
        value = json.loads((HERE.parent / "owner-input/INPUTS.json").read_bytes())
        self.assertEqual(value["patch_targets"], snapshot["patch_targets"])
        self.assertEqual(snapshot["archive_records"], 37886)
        self.assertFalse(snapshot["four_retained_patchers_current_byte_equal_twice"])
        self.assertTrue(snapshot["patcher_second_pass_idempotent"])
        for name in ("dreaming-phases-C-w6u2U1.mjs", "dreaming-narrative-OOe1PAul.mjs"):
            self.assertEqual(snapshot["patch_target_hashes"][name], snapshot["patch_target_hashes_after_fixture"][name])
        name = "session-ingestion-6vy4mT7v.mjs"
        self.assertNotEqual(snapshot["patch_target_hashes"][name], snapshot["patch_target_hashes_after_fixture"][name])

    def test_r11_native_dispatch_and_other_component_bindings_are_unchanged(self):
        base = "c26af5b3ec1f235ee3452b0ac199f2f8efc3e7d2"
        before = json.loads(subprocess.check_output(["git", "show", base + ":component-bindings-20260914.json"], cwd=HERE))
        for name in ("rita", "ava", "voice-organ", "tessa"):
            self.assertEqual(B["components"][name], before["components"][name])
        for key in ("actors", "unit", "order", "custom_sha256"):
            self.assertEqual(B[key], before[key])
        self.assertEqual(B["external_foundations"]["relay-current"], before["external_foundations"]["relay-current"])
        old = subprocess.check_output(["git", "show", base + ":deployment/recovery-coordinator.py"], cwd=HERE, text=True)
        new = (HERE / "recovery-coordinator.py").read_text()
        selected = ("Native", "CoreOwnerGates", "execute", "execute_core", "owner_argv", "rollback_expected")
        for name in selected:
            def segment(text):
                node = next(n for n in ast.parse(text).body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
                return ast.get_source_segment(text, node)
            self.assertEqual(segment(new), segment(old), name)

    def test_acceptance_is_amber_not_calendar_or_outgoing_smoke_success(self):
        current = c.current_core_binding(HERE.parent / "owner-input", B)["binding"]["acceptance"]
        self.assertEqual(current["schedule_latency_seconds"], 223)
        self.assertEqual(current["calendar_verification"], "deferred")
        self.assertEqual(current["latest_outgoing_smoke"], "failed_STTfinal_count_0_before_model")
        self.assertEqual(current["confirmed_message_to_IMAP"], "mandatory_unproven")
        self.assertFalse(c.current_core_binding(HERE.parent / "owner-input", B)["binding"]["builder_native_changes"])

    def test_current_rita_packet_reports_historical_skeleton_difference(self):
        result = c.verify_package("rita", (INPUTS / "rita-current").resolve(), B)
        self.assertEqual((result["kit_files"], result["skeleton_files"]), (108, 114))
        self.assertFalse(result["skeleton_equal"])
        changed = copy.deepcopy(B)
        changed["components"]["rita"]["source"] = "f" * 40
        with self.assertRaisesRegex(c.Stop, "current_source_or_binary_binding_changed"):
            c.verify_package("rita", (INPUTS / "rita-current").resolve(), changed)

    def test_current_tessa_is_exact_retention_not_release_or_execution(self):
        result = c.verify_package("tessa", (INPUTS / "tessa-current").resolve(), B)
        self.assertEqual((result["retained_files"], result["retained_bytes"]), (19, 111123))
        self.assertFalse(result["full_component_release_matched"])
        with self.assertRaisesRegex(c.Stop, "automated_Tessa_transaction"):
            c.owner_argv("tessa", "install", {"tessa": Path("/home/aimee/.local/share/vip-recovery-fixture/tessa")}, {}, None, B)

    def test_tessa_dispatch_stops_before_native_transport(self):
        with tempfile.TemporaryDirectory(prefix="tessa-dispatch-", dir=HERE.parent) as tmp:
            root = Path(tmp)
            roots = root / "roots.json"; roots.write_text("{}")
            checkpoints = root / "checkpoints.json"; checkpoints.write_text("{}")
            receipt_dir = root / "receipt"; receipt_dir.mkdir(mode=0o700)
            with mock.patch.object(c, "Native", side_effect=AssertionError("native transport forbidden")), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                rc = c.main(["install", "--component", "tessa", "--roots", str(roots),
                             "--checkpoints", str(checkpoints), "--ssh-key", "/fixture/key",
                             "--receipt", str(receipt_dir / "attempt.json")])
            self.assertEqual(rc, 2)
            self.assertIn("automated_Tessa_transaction", output.getvalue())
            self.assertFalse((receipt_dir / "attempt.json").exists())
        native = mock.Mock()
        with self.assertRaisesRegex(c.Stop, "automated_Tessa_transaction"):
            c.execute("tessa", "install", {}, {}, native, None, {}, {}, B)
        native.assert_not_called()

    def test_rita_exact_argv_and_rollback_rejection(self):
        stage = {"rita": Path("/home/aimee/.local/share/vip-recovery-fixture/rita")}
        current = copy.deepcopy(B["components"]["rita"]["after"])
        check = c.owner_argv("rita", "check", stage, current, None, B)
        self.assertEqual(check[-6:], ["--expected-binary", current["/usr/local/libexec/aimee-pbx-router"],
                                      "--expected-unit", B["unit"]["sha256"],
                                      "--expected-environment", B["components"]["rita"]["environment_sha"]])
        self.assertEqual(c.owner_argv("rita", "install", stage, current, None, B), check + ["--apply"])
        with self.assertRaisesRegex(c.Stop, "automatic_older_reader_rollback_forbidden"):
            c.owner_argv("rita", "rollback", stage, current, None, B)

    def test_current_rita_private_config_capture_is_hash_metadata_only(self):
        result = c.verify_rita_current_config((INPUTS / "rita-current-config").resolve(), B)
        self.assertEqual(result["members"], 4)
        self.assertFalse(result["ordinary_rollback_allowed"])
        self.assertFalse(result["contents_or_secret_values_emitted"])
        self.assertNotIn("rita-current-environment", B["gaps"])

    def test_current_ava_is_live_and_uses_exact_single_owner_helper(self):
        s = B["components"]["ava"]
        result = c.verify_package("ava", (INPUTS / "ava-current").resolve(), B)
        self.assertEqual(result["kit_files"], 228)
        self.assertEqual(s["runtime"], "52768f25309b81bb1d5d67a25d8b936c54b749dd")
        self.assertEqual(s["after"][next(iter(s["after"]))],
                         "f1b2ce1fece75c6c0870c82c8266f8c82a7fc1df8aece96d350af1bc0f07e0be")
        self.assertEqual(s["helper"], s["installed_verifier"])
        self.assertEqual(s["helper_sha"],
                         "3b6b0f269d17527a298767ed5aa5af2778afecd4fe36919fa8a5dcec200e26e7")
        stage = {"ava": Path("/home/aimee/.local/share/vip-recovery-fixture/ava")}
        self.assertEqual(c.owner_argv("ava", "verify-installed", stage, {}, None, B)[-1],
                         "--verify-installed")

    def test_relay_handoff_hash_drift_is_rejected(self):
        roots = relay_roots()
        self.assertEqual(c.verify_external_foundation("relay-current", roots, B)["entries"], 19)
        with tempfile.TemporaryDirectory(prefix="relay-retention-", dir=HERE.parent) as tmp:
            copied = Path(tmp) / "handoff"
            shutil.copytree(RELAY, copied)
            (copied / "FINAL-HANDOFF.json").write_bytes(b"changed")
            with self.assertRaisesRegex(c.Stop, "external_manifest_member_hash_mismatch"):
                c.verify_external_foundation("relay-current", {**relay_roots(), "relay-current": copied}, B)

    def test_core_owner_input_cas_includes_current_relay_and_controls(self):
        value = json.loads((HERE.parent / "owner-input/INPUTS.json").read_bytes())
        self.assertEqual(value["protected"]["/usr/local/libexec/aimee-main-voice-relay"],
                         B["external_foundations"]["relay-current"]["runtime_sha256"])
        self.assertEqual(value["protected"]["/etc/aimee-main-voice-relay.env"],
                         "937039ef54b4306e3ce134f9c59c8e4f0c797103a165333df775d0cc8b12c9e9")

    def test_current_guard_is_live_not_pending_or_R4(self):
        text = (HERE / "RECOVERY-COORDINATOR.md").read_text()
        self.assertIn("CURRENT LIVE", text)
        self.assertNotIn("pending owner deployment only", text)

    def test_manual_tessa_recovery_and_order_are_actionable_not_unusable(self):
        result = c.plan("install", {}, {}, {}, B, {})
        self.assertEqual(result["order"], ["tessa", "rita", "ava", "voice-organ", "crustacea"])
        row = next(x for x in result["components"] if x["component"] == "tessa")
        self.assertTrue(row["manual_owner_install_supported"])
        self.assertFalse(row["automated_transaction_supported"])
        self.assertEqual(row["manual_owner_commands"], ["cd /opt/tessa/deployment", "docker compose build", "docker compose up -d"])
        self.assertIn("relay_continuity", result["conversational_qualification_prerequisite"])
        self.assertNotIn("before Tessa", B["external_foundations"]["avr-foundation"]["fresh_host_restore"])

    def test_original_owner_receipt_and_current_ava_citation_are_not_reattributed(self):
        original = c.digest(HERE.parent / "owner-input/CRUSTACEA-RECOVERY-OWNER-INPUT-20260914.md")
        self.assertEqual(original, "1a0e7d55123e0da725e27716ed13e44969a6404c6cf001bf5c5b0987524c16f2")
        text = (HERE / "RECOVERY-COORDINATOR.md").read_text()
        self.assertIn("Projects/VIP/receipts/ava-guard-live-20260914.md", text)
        self.assertNotIn("complete AVR foundation\nthrough", text)

    def test_retained_relay_activation_sidecar_drift_is_rejected(self):
        result = c.verify_external_foundation("relay-current", relay_roots(), B)
        self.assertEqual(len(result["sidecars"]), 2)
        with tempfile.TemporaryDirectory(prefix="relay-activation-", dir=HERE.parent) as tmp:
            copied = Path(tmp) / "activation"
            shutil.copytree(ACTIVATION, copied)
            (copied / "activate-relay-file.py").write_bytes(b"changed")
            with self.assertRaisesRegex(c.Stop, "external_sidecar"):
                c.verify_external_foundation("relay-current", {**relay_roots(), "relay-activation-current": copied}, B)


if __name__ == "__main__":
    unittest.main(verbosity=2)
