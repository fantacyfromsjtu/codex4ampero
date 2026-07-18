import json
import tempfile
import unittest
from pathlib import Path

from ampero_control.catalog import EffectCatalog


CATALOG_FIXTURE = {
    "PluginProperties": {
        "Modules": {
            "Catalog": [
                {
                    "Name": "AMP",
                    "Index": "4",
                    "Alg": [
                        {
                            "Name": "Test Clean",
                            "Code": "117440600",
                            "Index": "1",
                            "classify": "Clean",
                            "descriptionEN": "Clear American clean amp.",
                            "Widget": [
                                {
                                    "Name": "Gain",
                                    "ID": "0",
                                    "DefaultValue": "30",
                                    "DisplayMin": "0",
                                    "DisplayMax": "100",
                                    "Step": "1",
                                    "Type": "0",
                                }
                            ],
                        },
                        {
                            "Name": "Single Control",
                            "Code": "117440601",
                            "Index": "2",
                            "classify": "Utility",
                            "Widget": {
                                "Name": "Level",
                                "ID": "0",
                                "DefaultValue": "50",
                                "DisplayMin": "0",
                                "DisplayMax": "100",
                                "Step": "1",
                                "Type": "0"
                            },
                        }
                    ],
                }
            ]
        }
    }
}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_directory.name) / "v1.0.0_alg_data.json"
        self.path.write_text(json.dumps(CATALOG_FIXTURE), encoding="utf-8")
        self.catalog = EffectCatalog.from_file(self.path)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_exact_lookup_and_parameter_metadata(self):
        effect = self.catalog.find_exact("test clean", "amp")
        self.assertEqual(effect.category_id, 4)
        self.assertEqual(effect.model_code, 117440600)
        self.assertEqual(effect.parameter("gain").default, 30.0)

    def test_search_uses_description_and_category(self):
        results = self.catalog.search("american clean", category="AMP")
        self.assertEqual([effect.name for effect in results], ["Test Clean"])

    def test_single_widget_object_is_normalized(self):
        effect = self.catalog.find_exact("Single Control", "AMP")
        self.assertEqual(effect.parameter("Level").maximum, 100.0)


if __name__ == "__main__":
    unittest.main()
