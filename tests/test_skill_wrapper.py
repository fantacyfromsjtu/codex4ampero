import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_apply_timeout_is_bounded(self):
        self.assertEqual(
            self.wrapper._timeout_seconds(["--json", "plan", "apply"]), 90.0
        )

    def test_save_timeout_is_bounded(self):
        self.assertEqual(
            self.wrapper._timeout_seconds(["--json", "plan", "save"]), 45.0
        )

    def test_public_project_root_environment_variable_is_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "CODEX4AMPERO_ROOT": directory,
                    "VIBE_AMPERO_ROOT": "legacy-path",
                },
            ):
                self.assertEqual(self.wrapper._project_root(), Path(directory))

    def test_wrapper_has_no_machine_specific_fallback(self):
        source = WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("E:\\vibe_ampere", source)


if __name__ == "__main__":
    unittest.main()
