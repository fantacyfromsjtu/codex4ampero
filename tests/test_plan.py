import json
import tempfile
import unittest
from pathlib import Path

from ampero_control.catalog import EffectCatalog
from ampero_control.controller import prepare_plan
from ampero_control.errors import PlanValidationError
from ampero_control.plan import TonePlan

from test_catalog import CATALOG_FIXTURE


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        path = Path(self.temp_directory.name) / "v1.0.0_alg_data.json"
        path.write_text(json.dumps(CATALOG_FIXTURE), encoding="utf-8")
        self.catalog = EffectCatalog.from_file(path)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_plan_resolves_names_to_protocol_command(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Test",
                "reason": "Test",
                "actions": [
                    {
                        "type": "set_parameter",
                        "slot": 2,
                        "effect": {"name": "Test Clean", "category": "AMP"},
                        "parameter": "Gain",
                        "value": 42,
                    }
                ],
            }
        )
        prepared = prepare_plan(plan, self.catalog)
        self.assertEqual(prepared.actions[0].command.payload.hex(), "0200000000002842")

    def test_out_of_range_parameter_is_rejected(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "actions": [
                    {
                        "type": "set_parameter",
                        "slot": 2,
                        "effect": {"name": "Test Clean", "category": "AMP"},
                        "parameter": "Gain",
                        "value": 101,
                    }
                ],
            }
        )
        with self.assertRaises(PlanValidationError):
            prepare_plan(plan, self.catalog)

    def test_routing_template_resolves_to_official_serial_id(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "actions": [
                    {
                        "type": "set_routing_template",
                        "template": "Serial",
                        "expected_before": "Parallel",
                    }
                ],
            }
        )
        prepared = prepare_plan(plan, self.catalog)
        action = prepared.actions[0]
        self.assertEqual(action.command.payload.hex(), "04000000")
        self.assertEqual(action.to_dict()["routing_template"]["template_id"], 4)

    def test_routing_template_allows_dynamic_preflight(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "actions": [
                    {
                        "type": "set_routing_template",
                        "template": "Serial",
                    }
                ],
            }
        )
        prepared = prepare_plan(plan, self.catalog)
        routing = prepared.actions[0].to_dict()["routing_template"]
        self.assertIsNone(routing["expected_before"])
        self.assertIsNone(routing["expected_before_id"])

    def test_routing_template_requires_known_expected_before(self):
        with self.assertRaises(PlanValidationError):
            TonePlan.from_dict(
                {
                    "schema_version": 1,
                    "actions": [
                        {
                            "type": "set_routing_template",
                            "template": "Serial",
                            "expected_before": "Unknown",
                        }
                    ],
                }
            )

    def test_automatic_patch_selection_requires_target_patch(self):
        with self.assertRaises(PlanValidationError):
            TonePlan.from_dict(
                {
                    "schema_version": 1,
                    "select_target_patch": True,
                    "actions": [{"type": "set_scene", "scene": 0}],
                }
            )

    def test_research_metadata_is_preserved_in_preview(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Researched lead tone",
                "reason": "Translate sourced rig context into a conservative plan.",
                "research": {
                    "target": "Example artist lead tone",
                    "researched_on": "2026-07-18",
                    "confidence": "medium",
                    "facts": ["The source track is transcribed as overdriven guitar."],
                    "inferences": ["Use moderate pedal gain into a clean amp."],
                    "limitations": ["No isolated studio guitar stem was available."],
                    "sources": [
                        {
                            "title": "Official algorithm catalog",
                            "source_type": "local_catalog",
                            "tier": 1,
                            "finding": "The selected drive model is classified as overdrive.",
                            "reference": "v1.0.8_alg_data.json",
                        }
                    ],
                },
                "actions": [{"type": "set_scene", "scene": 0}],
            }
        )

        preview = prepare_plan(plan, self.catalog).to_dict()

        self.assertEqual(preview["research"]["confidence"], "medium")
        self.assertEqual(preview["research"]["sources"][0]["tier"], 1)
        self.assertEqual(
            preview["research"]["inferences"],
            ["Use moderate pedal gain into a clean amp."],
        )

    def test_research_requires_traceable_sources(self):
        with self.assertRaises(PlanValidationError):
            TonePlan.from_dict(
                {
                    "schema_version": 1,
                    "research": {
                        "target": "Untraceable tone",
                        "researched_on": "2026-07-18",
                        "confidence": "high",
                        "facts": ["Unsupported claim"],
                        "sources": [],
                    },
                    "actions": [{"type": "set_scene", "scene": 0}],
                }
            )

    def test_research_rejects_invalid_date_and_confidence(self):
        for researched_on, confidence in (
            ("18-07-2026", "medium"),
            ("2026-07-18", "certain"),
        ):
            with self.subTest(researched_on=researched_on, confidence=confidence):
                with self.assertRaises(PlanValidationError):
                    TonePlan.from_dict(
                        {
                            "schema_version": 1,
                            "research": {
                                "target": "Invalid research",
                                "researched_on": researched_on,
                                "confidence": confidence,
                                "facts": ["Claim"],
                                "sources": [
                                    {
                                        "title": "Source",
                                        "source_type": "technical_reference",
                                        "tier": 2,
                                        "finding": "Finding",
                                    }
                                ],
                            },
                            "actions": [{"type": "set_scene", "scene": 0}],
                        }
                    )

    def test_save_preview_is_included_without_saving(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "target_patch": "A50-1",
                "save_preview_name": "Hana Solo",
                "actions": [{"type": "set_scene", "scene": 0}],
            }
        )

        preview = prepare_plan(plan, self.catalog).to_dict()

        save_preview = preview["post_apply_save_preview"]
        self.assertFalse(save_preview["journal_bound"])
        self.assertEqual(save_preview["target_patch"]["label"], "A50-1")
        self.assertEqual(save_preview["preset_name"], "Hana Solo")
        self.assertEqual(save_preview["confirmation_token"], "SAVE:A50-1")

    def test_save_preview_requires_exact_target(self):
        with self.assertRaises(PlanValidationError):
            TonePlan.from_dict(
                {
                    "schema_version": 1,
                    "save_preview_name": "Hana Solo",
                    "actions": [{"type": "set_scene", "scene": 0}],
                }
            )


if __name__ == "__main__":
    unittest.main()
