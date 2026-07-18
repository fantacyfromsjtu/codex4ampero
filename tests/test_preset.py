import json
import tempfile
import unittest
from pathlib import Path

from ampero_control.catalog import EffectCatalog
from ampero_control.preset import parse_current_preset

from preset_fixture import build_current_preset_fixture
from test_catalog import CATALOG_FIXTURE


class PresetParserTests(unittest.TestCase):
    def test_parses_effect_chain_and_scene_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "v1.0.0_alg_data.json"
            catalog_path.write_text(json.dumps(CATALOG_FIXTURE), encoding="utf-8")
            catalog = EffectCatalog.from_file(catalog_path)
            snapshot = parse_current_preset(
                build_current_preset_fixture(),
                catalog,
                current_scene=0,
                include_parameters=True,
            )
        self.assertEqual(snapshot["preset_name"], "Fixture")
        self.assertEqual(snapshot["scene_names"], ["Scene 1"])
        self.assertEqual(snapshot["slots"][0]["effect"]["name"], "Test Clean")
        self.assertEqual(snapshot["slots"][0]["parameters"][0]["value"], 42.0)
        self.assertTrue(snapshot["slots"][1]["empty"])


if __name__ == "__main__":
    unittest.main()
