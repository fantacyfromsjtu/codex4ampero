import json
import struct
import tempfile
import unittest
from pathlib import Path

from ampero_control.catalog import EffectCatalog
from ampero_control.preset import (
    parse_current_preset,
    parse_routing_template_response,
)

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
        self.assertEqual(snapshot["preset_payload_header"], 7)
        self.assertEqual(snapshot["scene_names"], ["Scene 1"])
        self.assertEqual(snapshot["slots"][0]["effect"]["name"], "Test Clean")
        self.assertEqual(snapshot["slots"][0]["parameters"][0]["value"], 42.0)
        self.assertTrue(snapshot["slots"][1]["empty"])
        self.assertEqual(snapshot["routing"]["effect_chain_count"], 2)
        self.assertEqual(snapshot["routing"]["input_sources"], [0, 1])
        self.assertEqual(snapshot["routing"]["split_node_address"], 2)
        self.assertEqual(snapshot["routing"]["mix_node_address"], 7)
        self.assertEqual(snapshot["routing"]["template"], "Custom")
        self.assertIsNone(snapshot["routing"]["template_id"])

    def test_identifies_factory_routing_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "v1.0.0_alg_data.json"
            catalog_path.write_text(json.dumps(CATALOG_FIXTURE), encoding="utf-8")
            catalog = EffectCatalog.from_file(catalog_path)
            snapshot = parse_current_preset(
                build_current_preset_fixture(
                    split_node_address=0, mix_node_address=6
                ),
                catalog,
                current_scene=0,
                include_parameters=False,
            )
        self.assertEqual(snapshot["routing"]["template"], "Split->Mix")
        self.assertEqual(snapshot["routing"]["template_id"], 1)

    def test_parses_verified_serial_template_response(self):
        current_preset = build_current_preset_fixture(
            split_node_address=6, mix_node_address=-1
        )
        routing_block_offset = current_preset.index((6).to_bytes(4, "little", signed=True))
        routing_size = int.from_bytes(
            current_preset[routing_block_offset + 4 : routing_block_offset + 8],
            "little",
            signed=True,
        )
        routing_data = current_preset[
            routing_block_offset + 8 : routing_block_offset + 8 + routing_size
        ]
        response = (4).to_bytes(4, "little", signed=True) + bytes(12) + routing_data
        routing = parse_routing_template_response(response)
        self.assertEqual(routing["response_template_id"], 4)
        self.assertEqual(routing["template"], "Serial")
        self.assertEqual(routing["template_id"], 4)

    def test_parses_compact_serial_template_response(self):
        compact = (
            struct.pack("<2h", 0, 5)
            + struct.pack("<2h", 2, 0)
            + struct.pack("<8f", *([0.0] * 8))
            + struct.pack("<8f", *([0.0] * 8))
            + struct.pack("<bbbb", 6, -1, 0, 0)
            + struct.pack("<10f", *([0.0] * 10))
            + struct.pack("<10f", *([0.0] * 10))
        )
        response = (4).to_bytes(4, "little", signed=True) + bytes(12) + compact
        routing = parse_routing_template_response(response)
        self.assertEqual(len(compact), 156)
        self.assertEqual(routing["response_template_id"], 4)
        self.assertEqual(routing["template"], "Serial")
        self.assertEqual(routing["template_id"], 4)


if __name__ == "__main__":
    unittest.main()
