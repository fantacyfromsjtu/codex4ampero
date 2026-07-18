import json
import tempfile
import unittest
from pathlib import Path

from ampero_control.cli import _build_apply_response, build_parser
from ampero_control.plan import TonePlan


class CliTests(unittest.TestCase):
    def test_public_cli_uses_project_name(self):
        self.assertEqual(build_parser().prog, "codex4ampero")

    def test_apply_response_includes_journal_bound_save_preview(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "target_patch": "A50-1",
                "save_preview_name": "Hana Solo",
                "actions": [{"type": "set_scene", "scene": 0}],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "apply.journal.json"
            journal_path.write_text(
                json.dumps(
                    {
                        "status": "applied",
                        "target_patch": {"label": "A50-1", "index": 150},
                        "current_patch": {"label": "A50-1", "index": 150},
                        "applied": [{"readback_verified": True}],
                    }
                ),
                encoding="utf-8",
            )

            response = _build_apply_response(plan, journal_path, {"status": "applied"})

        self.assertTrue(response["ok"])
        self.assertTrue(response["save_preview"]["journal_bound"])
        self.assertEqual(
            response["save_preview"]["confirmation_token"], "SAVE:A50-1"
        )
        self.assertIn("preset was not saved", response["save_notice"])

    def test_apply_response_omits_save_preview_when_not_requested(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "target_patch": "A50-1",
                "actions": [{"type": "set_scene", "scene": 0}],
            }
        )

        response = _build_apply_response(
            plan, Path("unused.journal.json"), {"status": "applied"}
        )

        self.assertNotIn("save_preview", response)


if __name__ == "__main__":
    unittest.main()
