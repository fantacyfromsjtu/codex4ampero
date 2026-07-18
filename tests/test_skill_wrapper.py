import importlib.util
import unittest
from pathlib import Path


WRAPPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ampero-tone"
    / "scripts"
    / "ampero.py"
)


class SkillWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ampero_skill_wrapper", WRAPPER_PATH)
        cls.wrapper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.wrapper)

    def test_native_scan_timeout_is_bounded(self):
        self.assertEqual(
            self.wrapper._timeout_seconds(["--json", "doctor", "--scan"]), 10.0
        )

    def test_snapshot_timeout_is_bounded(self):
        self.assertEqual(
            self.wrapper._timeout_seconds(["--json", "device", "snapshot"]), 30.0
        )


if __name__ == "__main__":
    unittest.main()
