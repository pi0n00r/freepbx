#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=VIP
"""Consumer delegation fixtures only; no Ava owner edits or native transport."""
import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("installed_owner_consumer", HERE / "recovery-coordinator.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
B = c.bindings()


class InstalledOwnerBindingContracts(unittest.TestCase):
    def setUp(self):
        self.b = copy.deepcopy(B)
        self.s = self.b["components"]["ava"]
        self.stages = {"ava": Path("/home/aimee/.local/share/vip-recovery-fixture/ava")}
        self.fleet = mock.Mock()
        self.phase = c.core_module(self.b)
        self.gate = c.CoreOwnerGates(self.fleet, {"owner_input": {"protected_metadata": {}}},
                                    self.stages, self.b, self.phase)
        self.fleet.helper.return_value = (0, json.dumps(self.owner_result()).encode())
        self.fleet.hashes.side_effect = self.stage_hashes

    def owner_result(self):
        prefix = "/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"
        return {"commit": self.s["runtime"], "status": "installed_verify_pass",
                "installed": {name.removeprefix(prefix): {"sha256": sha} for name, sha in self.s["after"].items()},
                "health": {}, "configuration": {}, "logical_agent_config": {}}

    def stage_hashes(self, component, paths, binding):
        self.assertEqual(component, "ava")
        if set(paths) == set(self.s["foundation_files"]):
            return dict(self.s["foundation_files"])
        stage = self.stages["ava"]
        expected = {str(stage / self.s["helper"]): self.s["helper_sha"],
                    str(stage / self.s["installed_verifier"]): self.s["installed_verifier_sha"]}
        prefix = "/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"
        expected.update({str(stage / "src" / name.removeprefix(prefix)): sha
                         for name, sha in self.s["after"].items()})
        return {path: expected[path] for path in paths}

    def argv(self, mode, binding=None):
        return c.owner_argv("ava", mode, self.stages, {}, None, binding or self.b)

    def test_installed_argv_uses_owner_mode_not_activation(self):
        self.assertEqual(self.argv("verify-installed"),
                         ["/usr/bin/python3", "-B",
                          str(self.stages["ava"] / self.s["installed_verifier"]), "--verify-installed"])

    def test_activation_check_argv_is_preserved(self):
        expected = ["/usr/bin/python3", "-B", str(self.stages["ava"] / self.s["helper"]), "--check-only"]
        self.assertEqual(self.argv("check"), expected)
        self.assertEqual(self.argv("check", B), expected)

    def test_unbound_installed_mode_has_no_activation_fallback(self):
        legacy = copy.deepcopy(B)
        for key in tuple(legacy["components"]["ava"]):
            if key.startswith("installed_ver"): del legacy["components"]["ava"][key]
        with self.assertRaisesRegex(c.Stop, "accepted_Ava_installed_verifier_pin_required"):
            self.argv("verify-installed", legacy)

    def test_missing_or_invalid_owner_source_and_hash_are_blocked(self):
        for key, invalid in (("installed_verifier_sha", None), ("installed_verifier_sha", "bad"),
                             ("installed_verification_source", None), ("installed_verification_tree", "bad"),
                             ("installed_verifier", "../owner.py")):
            with self.subTest(key=key, invalid=invalid):
                b = copy.deepcopy(self.b)
                b["components"]["ava"][key] = invalid
                with self.assertRaises(c.Stop):
                    self.argv("verify-installed", b)

    def test_core_zero_delegates_full_owner_installed_verification(self):
        self.gate.zero()
        self.fleet.zero.assert_called_once_with()
        self.fleet.helper.assert_called_once_with("ava", self.argv("verify-installed"), self.b)
        queried = self.fleet.hashes.call_args_list[-2].args[1]
        self.assertIn(str(self.stages["ava"] / self.s["installed_verifier"]), queried)
        self.assertNotIn("--check-only", self.fleet.helper.call_args.args[1])

    def test_native_calls_block_before_installed_verifier(self):
        self.fleet.zero.side_effect = c.Stop("native_not_zero")
        with self.assertRaisesRegex(self.phase.d.Stop, "native_not_zero"):
            self.gate.zero()
        self.fleet.helper.assert_not_called()

    def test_changed_staged_owner_helper_blocks_before_launch(self):
        original = self.stage_hashes
        def changed(component, paths, binding):
            result = original(component, paths, binding)
            name = str(self.stages["ava"] / self.s["installed_verifier"])
            if name in result:
                result[name] = "f" * 64
            return result
        self.fleet.hashes.side_effect = changed
        with self.assertRaisesRegex(self.phase.d.Stop, "native_staged_bytes_changed"):
            self.gate.zero()
        self.fleet.helper.assert_not_called()

    def test_owner_native_rejection_blocks_core_phase(self):
        self.fleet.helper.return_value = (1, b"bounded-owner-rejection")
        with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_native_zero_readiness_failed"):
            self.gate.zero()

    def test_helper_hash_observation_immediately_precedes_owner_delegation(self):
        events = []
        self.fleet.hashes.side_effect = lambda component, paths, binding: (
            events.append("hash") or self.stage_hashes(component, paths, binding))
        self.fleet.helper.side_effect = lambda *args: (events.append("owner") or (0, json.dumps(self.owner_result()).encode()))
        self.gate.zero()
        self.assertEqual(events, ["hash", "hash", "owner", "hash"])
        self.assertIn(str(self.stages["ava"] / self.s["installed_verifier"]),
                      self.fleet.hashes.call_args_list[-2].args[1])

    def test_zero_exit_without_exact_owner_schema_does_not_pass(self):
        for body in (b"check_only_pass", b"[]", b"{}", b"invalid-json"):
            with self.subTest(body=body):
                self.fleet.helper.return_value = (0, body)
                with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_installed_result_invalid"):
                    self.gate.zero()
        for field, value in (("status", "check_only_pass"), ("commit", "a" * 40), ("installed", {}),
                             ("configuration", None), ("logical_agent_config", None)):
            with self.subTest(field=field):
                body = self.owner_result(); body[field] = value
                self.fleet.helper.return_value = (0, json.dumps(body).encode())
                with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_installed_result_invalid"):
                    self.gate.zero()

    def test_foundation_drift_before_or_during_owner_verification_blocks(self):
        for when in ("before", "during"):
            with self.subTest(when=when):
                self.fleet.reset_mock(); reads = 0
                def observed(component, paths, binding):
                    nonlocal reads
                    result = self.stage_hashes(component, paths, binding)
                    if set(paths) == set(self.s["foundation_files"]):
                        reads += 1
                        if when == "before" or reads == 2: result[next(iter(result))] = "f" * 64
                    return result
                self.fleet.hashes.side_effect = observed
                with self.assertRaisesRegex(self.phase.d.Stop, "installed_Ava_fb_foundation_not_matching_R4"):
                    self.gate.zero()
                self.assertEqual(self.fleet.helper.call_count, 0 if when == "before" else 1)

    def test_installed_owner_uses_existing_privileged_native_aimee_actor(self):
        n = object.__new__(c.Native); n.key = Path("/fixture/existing-key"); n.local_host = None; n.active_pid = None
        child = mock.Mock(pid=123); child.wait.return_value = 0; child.poll.return_value = 0
        def launch(args, **kw):
            kw["stdout"].write(json.dumps(self.owner_result()).encode())
            return child
        with mock.patch.object(c.subprocess, "Popen", side_effect=launch) as started:
            n.helper("ava", self.argv("verify-installed"), self.b)
        args = started.call_args.args[0]
        index = args.index("aimee@ava.bajaj.com")
        self.assertEqual(args[index + 1:], ["sudo", "-n", *self.argv("verify-installed")])

    def test_plan_shows_exact_current_owner_command_without_assembly_acceptance(self):
        stages = {k: Path("/home/aimee/.local/share/vip-recovery-fixture/" + k) for k in self.b["components"]}
        plan = c.plan("install", stages, {}, {}, self.b)
        row = next(r for r in plan["components"] if r["component"] == "crustacea")
        self.assertEqual(row["current_Ava_readonly_gate"]["argv_on_Ava_as_existing_root_actor"],
                         c.owner_argv("ava", "verify-installed", stages, {}, None, self.b))
        self.assertEqual(row["current_Ava_readonly_gate"]["sha256"], self.s["installed_verifier_sha"])
        self.assertEqual(row["status"], "missing_prerequisite")
        self.assertEqual(plan["whole_assembly_status"], "INCOMPLETE_NATIVE_EXECUTION_AND_FOUNDATION_CHECKPOINTS")

    def test_plan_missing_Ava_native_stage_is_typed_not_fallback(self):
        stages = {"crustacea": Path("/home/aimee/.local/share/vip-recovery-fixture/crustacea")}
        row = next(r for r in c.plan("install", stages, {}, {}, self.b)["components"] if r["component"] == "crustacea")
        self.assertEqual(row["status"], "missing_prerequisite")
        self.assertEqual(row["reason"], "native_staged_kit_required")
        self.assertNotIn("current_Ava_readonly_gate", row)


class ActualInstalledOwnerCLI(unittest.TestCase):
    def setUp(self):
        directory = HERE.parent.parent / "inputs/ava-current/ava/deploy"
        helper = directory / "deploy-ava-prior-message-reference.py"
        test = directory / "test-deploy-ava-prior-message-reference.py"
        s = B["components"]["ava"]
        self.assertEqual(c.digest(helper), s["installed_verifier_sha"])
        self.assertEqual(c.digest(test), s["installed_verification_test_sha"])
        spec = importlib.util.spec_from_file_location("frozen_installed_owner_fixtures", test)
        t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
        self.d = t.deploy
        self.frame = t.TransactionTests("test_installed_verify_accepts_after_and_is_nonactuating")
        self.frame.setUp(); self.addCleanup(self.frame.doCleanups)
        self.b = copy.deepcopy(B)
        prefix = "/opt/AVA-AI-Voice-Agent-for-Asterisk/src/"
        self.b["components"]["ava"]["after"] = {prefix + name: value["sha256"] for name, value in self.frame.after.items()}
        self.stages = {"ava": Path("/home/aimee/.local/share/vip-recovery-fixture/ava")}
        self.fleet = mock.Mock()
        self.fleet.hashes.side_effect = lambda component, paths, b: dict(paths)
        self.fleet.helper.side_effect = self.invoke
        self.phase = c.core_module(self.b)
        self.gate = c.CoreOwnerGates(self.fleet, {"owner_input": {"protected_metadata": {}}},
                                    self.stages, self.b, self.phase)
        original = self.d.verify_installed
        patch = mock.patch.object(self.d, "verify_installed", side_effect=lambda native, root=None: original(native, self.frame.root))
        patch.start(); self.addCleanup(patch.stop)
        patch = mock.patch.object(self.d, "Native", return_value=self.frame.native)
        patch.start(); self.addCleanup(patch.stop)
        patch = mock.patch.object(self.d, "with_lock", side_effect=AssertionError("read-only mode must not lock"))
        patch.start(); self.addCleanup(patch.stop)

    def invoke(self, component, args, b):
        self.assertEqual(component, "ava")
        self.assertEqual(args, c.owner_argv("ava", "verify-installed", self.stages, {}, None, b))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = self.d.main(args[3:])
        self.result = json.loads(out.getvalue())
        return rc, out.getvalue().encode()

    def test_actual_cli_after_accepts_without_candidate_stage_or_mutation(self):
        self.frame.install_candidate()
        self.gate.zero()
        self.assertEqual(self.result["status"], "installed_verify_pass")
        self.assertEqual(self.result["commit"], B["components"]["ava"]["runtime"])
        self.assertNotIn("stop", self.frame.native.events)
        self.assertNotIn("start", self.frame.native.events)
        self.assertNotIn("configuration_capture", self.frame.native.events)
        self.assertNotIn("snapshot_backup", self.frame.native.events)
        self.assertFalse(self.frame.backups.exists())

    def test_actual_cli_before_unknown_and_active_call_are_blocked(self):
        with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_native_zero_readiness_failed"):
            self.gate.zero()
        self.frame.install_candidate(); self.frame.native.counts["active_calls"] = 1
        with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_native_zero_readiness_failed"):
            self.gate.zero()
        self.frame.native.counts["active_calls"] = 0
        (self.frame.root / self.d.TARGETS[0]).write_bytes(b"FOREIGN=True\n")
        with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_native_zero_readiness_failed"):
            self.gate.zero()
        self.assertNotIn("stop", self.frame.native.events)
        self.assertNotIn("start", self.frame.native.events)

    def test_actual_cli_protected_or_logical_drift_blocks_without_mutation(self):
        self.frame.install_candidate()
        original = self.frame.native.agent_snapshot; calls = 0
        def changed(*args, **kw):
            nonlocal calls
            calls += 1; value = original(*args, **kw)
            if calls == 2: value["sha256"] = "b" * 64
            return value
        with mock.patch.object(self.frame.native, "agent_snapshot", side_effect=changed):
            with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_native_zero_readiness_failed"):
                self.gate.zero()
        self.assertNotIn("stop", self.frame.native.events)
        self.assertNotIn("start", self.frame.native.events)

    def test_actual_cli_protected_config_drift_blocks_without_mutation(self):
        self.frame.install_candidate()
        original = self.frame.native.configuration; reads = 0
        def changed(*args, **kw):
            nonlocal reads
            reads += 1; value = original(*args, **kw)
            if reads == 2: value[".env"]["sha256"] = "b" * 64
            return value
        with mock.patch.object(self.frame.native, "configuration", side_effect=changed):
            with self.assertRaisesRegex(self.phase.d.Stop, "accepted_Ava_native_zero_readiness_failed"):
                self.gate.zero()
        self.assertNotIn("stop", self.frame.native.events)
        self.assertNotIn("start", self.frame.native.events)


if __name__ == "__main__":
    unittest.main(verbosity=2)
