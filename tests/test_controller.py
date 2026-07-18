import json
import tempfile
import time
import unittest
from pathlib import Path

from ampero_control.catalog import EffectCatalog
from ampero_control.constants import Command
from ampero_control.controller import DeviceController, prepare_plan
from ampero_control.errors import PlanValidationError
from ampero_control.installation import EditorInstallation
from ampero_control.plan import TonePlan
from ampero_control.protocol import ReceivedMessage, encode_set_parameter
from ampero_control.protocol import encode_set_model

from test_catalog import CATALOG_FIXTURE
from preset_fixture import build_current_preset_fixture


class FakeTransport:
    instances = []

    def __init__(self, installation):
        self.sent = []
        self.connected = False
        FakeTransport.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def scan(self):
        return {"input_indices": [1], "output_indices": [2]}

    def request(self, address, data=b"", timeout=2.0):
        if address == int(Command.CURRENT_SCENE):
            return ReceivedMessage(
                address=address,
                data=b"\x00\x00\x00\x00",
                flag=0x12,
                received_at=time.time(),
            )
        if address == int(Command.CURRENT_PRESET):
            return ReceivedMessage(
                address=address,
                data=build_current_preset_fixture(),
                flag=0x12,
                received_at=time.time(),
            )
        if address == int(Command.PRESET_SLOT_MODULE):
            slot = data[0]
            return ReceivedMessage(
                address=address,
                data=encode_set_model(slot, 4, 117440600, True),
                flag=0x14,
                received_at=time.time(),
            )
        slot = int.from_bytes(data[0:2], "little") if data else 2
        parameter_id = int.from_bytes(data[2:4], "little") if len(data) >= 4 else 0
        return ReceivedMessage(
            address=address,
            data=encode_set_parameter(slot, parameter_id, 30.0),
            flag=0x14,
            received_at=time.time(),
        )

    def send(self, address, data, flag):
        self.sent.append((address, data, int(flag)))
        return len(self.sent)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        FakeTransport.instances.clear()
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        catalog_path = root / "v1.0.0_alg_data.json"
        catalog_path.write_text(json.dumps(CATALOG_FIXTURE), encoding="utf-8")
        self.catalog = EffectCatalog.from_file(catalog_path)
        self.installation = EditorInstallation(
            root=root,
            executable=root / "Ampero II.exe",
            native_library=root / "HTUSBTools.dll",
            catalog_directory=root,
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_apply_records_verified_rollback(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Test",
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
        journal_path = Path(self.temp_directory.name) / "change.journal.json"
        controller = DeviceController(
            self.installation, self.catalog, transport_factory=FakeTransport
        )
        result = controller.apply(prepared, journal_path=journal_path)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(len(result["rollback"]), 1)
        self.assertEqual(
            result["rollback"][0]["command"], int(Command.PRESET_SLOT_PARAMETER)
        )
        self.assertTrue(journal_path.is_file())

    def test_rollback_rejects_tampered_unknown_command(self):
        journal_path = Path(self.temp_directory.name) / "tampered.journal.json"
        journal_path.write_text(
            json.dumps(
                {
                    "rollback": [
                        {
                            "command": 0x7FFFFFFF,
                            "payload_hex": "00",
                            "description": "tampered",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        controller = DeviceController(
            self.installation, self.catalog, transport_factory=FakeTransport
        )
        with self.assertRaises(PlanValidationError):
            controller.rollback(journal_path)

    def test_snapshot_reads_models_and_parameters(self):
        controller = DeviceController(
            self.installation, self.catalog, transport_factory=FakeTransport
        )
        snapshot = controller.snapshot(slot_count=2, include_parameters=True)
        self.assertEqual(snapshot["slot_count"], 2)
        self.assertEqual(snapshot["preset_name"], "Fixture")
        self.assertEqual(snapshot["slots"][0]["effect"]["name"], "Test Clean")
        self.assertEqual(snapshot["slots"][0]["parameters"][0]["value"], 42.0)
        self.assertTrue(snapshot["slots"][1]["empty"])


if __name__ == "__main__":
    unittest.main()
