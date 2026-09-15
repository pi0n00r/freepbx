#!/usr/bin/env python3
"""Verify the narrow native amendment without contacting a PBX."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class NativeKeepalive(unittest.TestCase):
    def test_only_endpoint_one_keepalive_changes(self):
        content = (ROOT / "deployment/native/pjsip.endpoint_custom_post.conf").read_text()
        self.assertEqual(content, "[1](+)\nrtp_keepalive=1\n")

    def test_native_authority_and_preserved_media(self):
        guide = (ROOT / "DEPLOY.md").read_text()
        for requirement in ("Config Edit", "Save and Apply Config", "Direct Media",
                            "true", "sdes", "180", "300", "zero active calls",
                            "Extn 7 alone", "Extn 6", "full contextual"):
            self.assertIn(requirement, guide)


if __name__ == "__main__":
    unittest.main()
