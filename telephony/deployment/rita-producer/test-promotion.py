import importlib.util
from pathlib import Path
import unittest
import os
import tempfile
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("promotion", Path(__file__).with_name("promote-producer.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SelectorTests(unittest.TestCase):
    def test_only_selector_changes(self):
        raw = b"# retained\nPBX_ROUTER_TOKEN=fixture\nAVRIL_AIMEE_TTS_URL=http://avril:6013/text-to-speech-stream\nOTHER=value\n"
        actual = module.selector(raw)
        self.assertEqual(actual, raw.replace(b"http://avril:6013/text-to-speech-stream", module.TESSA_URL.encode()))

    def test_duplicate_or_absent_rejected(self):
        for raw in (b"OTHER=value\n", b"AVRIL_AIMEE_TTS_URL=a\nAVRIL_AIMEE_TTS_URL=b\n"):
            with self.assertRaises(ValueError):
                module.selector(raw)

    def test_crlf_preserved(self):
        self.assertEqual(module.selector(b"AVRIL_AIMEE_TTS_URL=old\r\nX=1\r\n"),
                         ("AVRIL_AIMEE_TTS_URL=" + module.TESSA_URL + "\r\nX=1\r\n").encode())


@unittest.skipUnless(os.geteuid() == 0, "protected environment fixture requires root")
class PromotionTests(unittest.TestCase):
    def exercise(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, unit, env = (root / name for name in ("binary", "unit", "env"))
            binary.write_bytes(b"old")
            unit.write_bytes(b"unit unchanged\n")
            env.write_bytes(b"TOKEN=fixture\nAVRIL_AIMEE_TTS_URL=old\n")
            env.chmod(0o600)
            events = []

            def check(*args):
                return binary.stat(), unit.stat(), unit.read_bytes(), unit.read_bytes()

            def atomic(path, data, metadata):
                events.append(path.name)
                path.write_bytes(data)

            retained = SimpleNamespace(check_site=check, regular=lambda path: path.stat(),
                                       recheck_site=lambda *args: None,
                                       sync_directory=lambda path: None, atomic=atomic)
            native = SimpleNamespace(zero=lambda: events.append("zero"),
                                     stop=lambda: events.append("stop"),
                                     start=lambda: events.append("start"))

            def smoke():
                events.append("smoke")
                if fail:
                    raise RuntimeError("fixture health failure")

            args = (retained, b"new", binary, unit, env, root / "backups", "old",
                    module.sha(unit.read_bytes()), module.sha(env.read_bytes()), native, smoke)
            if fail:
                with self.assertRaises(RuntimeError):
                    module.promote(*args)
            else:
                result = module.promote(*args)
                self.assertFalse(result["automatic_rollback"])
            self.assertEqual(binary.read_bytes(), b"new")
            self.assertEqual(unit.read_bytes(), b"unit unchanged\n")
            self.assertNotIn("unit", events)
            self.assertEqual(events.count("start"), 1)
            self.assertEqual(events.count("stop"), 1)
            self.assertIn(module.TESSA_URL.encode(), env.read_bytes())
            backup = next((root / "backups").iterdir())
            self.assertEqual((backup / "binary.before").read_bytes(), b"old")

    def test_success_unit_preserved(self):
        self.exercise()

    def test_failed_health_never_restores_old_reader(self):
        self.exercise(fail=True)


if __name__ == "__main__":
    unittest.main()
