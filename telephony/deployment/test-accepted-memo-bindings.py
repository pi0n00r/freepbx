#!/usr/bin/env python3
# AI-NOTICE:License=AGPL-3.0-or-later
"""Current accepted packet checks. Local retained files only; no production calls."""
import importlib.util
import os
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("coordinator", Path(__file__).with_name("recovery-coordinator.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
B = c.bindings()


class AcceptedMemoBindings(unittest.TestCase):
    def test_paired_targets_are_not_immutable_foundations(self):
        ava = B["components"]["ava"]
        self.assertEqual(set(ava["before"]), set(ava["after"]))
        self.assertEqual(len(ava["after"]), 2)
        self.assertFalse(set(ava["after"]) & set(ava["foundation_files"]))
        self.assertEqual(ava["runtime"], "27b936e93b61b35981a411eaede2fc4e42e461e7")
        self.assertEqual(B["external_foundations"]["relay-current"]["source"],
                         "71794f4df835cc5e772c120e12a45fca107ca042")

    def test_complete_ava_packet(self):
        root = Path(os.environ["TELEPHONY_AVA_PACKAGE"]).resolve()
        result = c.verify_package("ava", root, B)
        self.assertEqual(result["source_files"], 753)
        for key in ("helper", "installed_verifier"):
            self.assertEqual(c.digest(root / "ava" / B["components"]["ava"][key]),
                             B["components"]["ava"][key + "_sha"])

    def test_complete_relay_packet(self):
        root = Path(os.environ["TELEPHONY_RELAY_PACKAGE"]).resolve()
        result = c.verify_external_foundation("relay-current", {"relay-current": root}, B)
        self.assertEqual(result["entries"], 50)


if __name__ == "__main__":
    unittest.main()
