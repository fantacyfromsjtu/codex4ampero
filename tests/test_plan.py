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


if __name__ == "__main__":
    unittest.main()
