import json
import tempfile
import unittest
from pathlib import Path

from ampero_control.errors import PlanValidationError
from ampero_control.patch_location import parse_patch_label
from ampero_control.preset_save import (
    build_preset_save_preview,
    prepare_preset_save,
    validate_preset_name,
)


class PresetSaveTests(unittest.TestCase):
    def _write_apply_journal(self, directory: str, **overrides) -> Path:
        value = {
            "status": "applied",
            "target_patch": {"label": "A50-1", "index": 150},
            "current_patch": {"label": "A50-1", "index": 150},
            "applied": [{"readback_verified": True}],
        }
        value.update(overrides)
        path = Path(directory) / "apply.journal.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_prepares_official_save_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = prepare_preset_save(
                self._write_apply_journal(directory), "Hana Solo"
            )
        self.assertEqual(prepared.target_patch.index, 150)
        self.assertEqual(prepared.confirmation_token, "SAVE:A50-1")
        self.assertEqual(len(prepared.command.payload), 21)
        self.assertEqual(prepared.command.payload[0:4], b"\x96\x00\x00\x00")
        self.assertEqual(prepared.command.payload[4:13], b"Hana Solo")
        self.assertEqual(prepared.command.payload[13:21], bytes(8))

    def test_builds_unbound_post_apply_save_preview(self):
        preview = build_preset_save_preview(
            parse_patch_label("A50-1"), "Hana Solo"
        )

        self.assertFalse(preview["journal_bound"])
        self.assertNotIn("source_journal", preview)
        self.assertEqual(preview["confirmation_token"], "SAVE:A50-1")
        self.assertEqual(preview["command"]["payload_hex"].split()[0:4], [
            "96",
            "00",
            "00",
            "00",
        ])

    def test_rejects_unverified_apply_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_apply_journal(
                directory, applied=[{"readback_verified": False}]
            )
            with self.assertRaises(PlanValidationError):
                prepare_preset_save(path, "Hana Solo")

    def test_rejects_invalid_preset_names(self):
        for name in ("", "12345678901234567", "含中文", "bad/name"):
            with self.subTest(name=name):
                with self.assertRaises(PlanValidationError):
                    validate_preset_name(name)


if __name__ == "__main__":
    unittest.main()
