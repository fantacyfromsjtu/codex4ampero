import json
import struct
import tempfile
import time
import unittest
from pathlib import Path

from ampero_control.catalog import EffectCatalog
from ampero_control.constants import Command
from ampero_control.controller import DeviceController, prepare_plan
from ampero_control.errors import (
    DeviceTimeoutError,
    DeviceWriteVerificationError,
    PlanValidationError,
)
from ampero_control.installation import EditorInstallation
from ampero_control.plan import TonePlan
from ampero_control.preset_save import prepare_preset_save
from ampero_control.protocol import (
    ReceivedMessage,
    decode_zero_terminated_utf8,
    decode_model,
    decode_parameter,
    encode_set_model,
    encode_set_parameter,
    pack_int,
)

from test_catalog import CATALOG_FIXTURE
from preset_fixture import build_current_preset_fixture


class FakeTransport:
    instances = []

    def __init__(self, installation):
        self.sent = []
        self.connected = False
        self.models = {}
        self.parameters = {}
        self.patch_index = 150
        self.preset_name = "Fixture"
        self.routing_split_node = 0
        self.routing_mix_node = 6
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
        if address == int(Command.SOFTWARE_STATE):
            return ReceivedMessage(
                address=address,
                data=b"",
                flag=0x12,
                received_at=time.time(),
            )
        if address == int(Command.PRESET_INDEX):
            return ReceivedMessage(
                address=address,
                data=pack_int(self.patch_index, 2),
                flag=0x12,
                received_at=time.time(),
            )
        if address == int(Command.CURRENT_PRESET):
            return ReceivedMessage(
                address=address,
                data=build_current_preset_fixture(
                    split_node_address=self.routing_split_node,
                    mix_node_address=self.routing_mix_node,
                ),
                flag=0x12,
                received_at=time.time(),
            )
        if address == int(Command.ROUTING_TEMPLATE):
            return ReceivedMessage(
                address=address,
                data=self._routing_response_data(),
                flag=0x12,
                received_at=time.time(),
            )
        if address == int(Command.PRESET_SLOT_MODULE):
            slot = data[0]
            category_id, model_code, enabled = self.models.get(
                slot, (4, 117440600, True)
            )
            return ReceivedMessage(
                address=address,
                data=encode_set_model(slot, category_id, model_code, enabled),
                flag=0x14,
                received_at=time.time(),
            )
        slot = int.from_bytes(data[0:2], "little") if data else 2
        parameter_id = int.from_bytes(data[2:4], "little") if len(data) >= 4 else 0
        return ReceivedMessage(
            address=address,
            data=encode_set_parameter(
                slot, parameter_id, self.parameters.get((slot, parameter_id), 30.0)
            ),
            flag=0x14,
            received_at=time.time(),
        )

    def send(self, address, data, flag):
        self.sent.append((address, data, int(flag)))
        if address == int(Command.PRESET_INDEX):
            self.patch_index = int.from_bytes(data[0:4], "little", signed=False)
        elif address == int(Command.PRESET_SLOT_MODULE):
            slot, category_id, model_code, enabled = decode_model(data)
            self.models[slot] = (category_id, model_code, enabled)
        elif address == int(Command.PRESET_SLOT_PARAMETER):
            slot, parameter_id, value = decode_parameter(data)
            self.parameters[(slot, parameter_id)] = value
        return len(self.sent)

    def send_and_wait(
        self, address, response_address, data, flag, timeout=3.0
    ):
        message_id = self.send(address, data, flag)
        if address == int(Command.PRESET_SAVE):
            self.patch_index = int.from_bytes(data[0:4], "little", signed=False)
            self.preset_name = decode_zero_terminated_utf8(data[4:21])
            return message_id, ReceivedMessage(
                address=response_address,
                data=b"",
                flag=0x12,
                received_at=time.time(),
            )
        template_id = int.from_bytes(data[0:4], "little", signed=True)
        topology = {
            0: (-1, -1),
            1: (0, 6),
            2: (-1, 6),
            3: (0, -1),
            4: (6, -1),
        }[template_id]
        self.routing_split_node, self.routing_mix_node = topology
        return message_id, ReceivedMessage(
            address=response_address,
            data=self._routing_response_data(template_id),
            flag=0x12,
            received_at=time.time(),
        )

    def _routing_response_data(self, template_id=None):
        if template_id is None:
            template_id = {
                (-1, -1): 0,
                (0, 6): 1,
                (-1, 6): 2,
                (0, -1): 3,
                (6, -1): 4,
            }[(self.routing_split_node, self.routing_mix_node)]
        routing_data = (
            struct.pack("<2h", 0, 5)
            + struct.pack("<2h", 2, 0)
            + struct.pack("<8f", *([0.0] * 8))
            + struct.pack("<8f", *([0.0] * 8))
            + struct.pack(
                "<bbbb",
                self.routing_split_node,
                self.routing_mix_node,
                0,
                0,
            )
            + struct.pack("<10f", *([0.0] * 10))
            + struct.pack("<10f", *([0.0] * 10))
        )
        return pack_int(template_id, 4) + bytes(12) + routing_data


class IgnoringWriteTransport(FakeTransport):
    def send(self, address, data, flag):
        self.sent.append((address, data, int(flag)))
        return len(self.sent)


class CurrentPresetTimeoutTransport(FakeTransport):
    def request(self, address, data=b"", timeout=2.0):
        if address == int(Command.CURRENT_PRESET):
            raise DeviceTimeoutError("current preset unavailable")
        return super().request(address, data, timeout)


class UnknownPatchTransport(FakeTransport):
    def __init__(self, installation):
        super().__init__(installation)
        self.patch_index = -1


class WrongSaveTargetTransport(FakeTransport):
    def __init__(self, installation):
        super().__init__(installation)
        self.patch_index = 149


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
            self.installation,
            self.catalog,
            transport_factory=FakeTransport,
        )
        result = controller.apply(prepared, journal_path=journal_path)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(len(result["rollback"]), 1)
        self.assertEqual(
            result["rollback"][0]["command"], int(Command.PRESET_SLOT_PARAMETER)
        )
        self.assertTrue(journal_path.is_file())
        self.assertTrue(result["applied"][0]["readback_verified"])
        self.assertEqual(result["current_patch"]["label"], "A50-1")

    def test_apply_rejects_unconfirmed_device_write(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Ignored write",
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
        journal_path = Path(self.temp_directory.name) / "ignored.journal.json"
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=IgnoringWriteTransport,
        )
        with self.assertRaises(DeviceWriteVerificationError):
            controller.apply(prepared, journal_path=journal_path)
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "rolled_back_after_failure")
        self.assertEqual(journal["applied"], [])

    def test_apply_rejects_wrong_target_patch(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Wrong target",
                "target_patch": "A49-3",
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
        journal_path = Path(self.temp_directory.name) / "wrong-target.journal.json"
        controller = DeviceController(
            self.installation, self.catalog, transport_factory=FakeTransport
        )
        with self.assertRaises(PlanValidationError):
            controller.apply(prepared, journal_path=journal_path)
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "refused_target_patch_mismatch")
        self.assertEqual(journal["current_patch"]["label"], "A50-1")

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
        self.assertTrue(snapshot["patch_location_verified"])
        self.assertEqual(snapshot["patch_index"], 150)
        self.assertEqual(snapshot["patch_label"], "A50-1")
        self.assertEqual(snapshot["slots"][0]["effect"]["name"], "Test Clean")
        self.assertEqual(snapshot["slots"][0]["parameters"][0]["value"], 42.0)
        self.assertTrue(snapshot["slots"][1]["empty"])

    def test_snapshot_keeps_preset_when_patch_location_is_unknown(self):
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=UnknownPatchTransport,
        )
        snapshot = controller.snapshot(slot_count=2)
        self.assertEqual(snapshot["preset_name"], "Fixture")
        self.assertFalse(snapshot["patch_location_verified"])
        self.assertNotIn("patch_index", snapshot)
        self.assertEqual(
            snapshot["patch_location_read_error"]["error"],
            "PatchLocationUnknownError",
        )
        self.assertIn("0xffff", snapshot["patch_location_read_error"]["message"])

    def test_apply_requires_manual_confirmation_when_patch_index_is_unknown(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Unknown patch",
                "target_patch": "A50-1",
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
        journal_path = Path(self.temp_directory.name) / "unknown-patch.journal.json"
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=UnknownPatchTransport,
        )
        with self.assertRaises(PlanValidationError):
            controller.apply(prepared, journal_path=journal_path)
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "refused_unverified_target_patch")

    def test_apply_accepts_matching_device_display_confirmation(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Confirmed patch",
                "target_patch": "A50-1",
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
        journal_path = Path(self.temp_directory.name) / "confirmed-patch.journal.json"
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=UnknownPatchTransport,
        )
        result = controller.apply(
            prepared,
            journal_path=journal_path,
            confirmed_device_patch="A50-1",
        )
        self.assertEqual(result["status"], "applied")
        self.assertEqual(
            result["current_patch"]["verification"],
            "user_confirmed_device_display",
        )
        self.assertEqual(result["confirmed_device_patch"], "A50-1")

    def test_apply_verifies_and_journals_routing_template_change(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Serial routing",
                "target_patch": "A50-1",
                "actions": [
                    {
                        "type": "set_routing_template",
                        "template": "Serial",
                        "expected_before": "Split->Mix",
                    }
                ],
            }
        )
        prepared = prepare_plan(plan, self.catalog)
        journal_path = Path(self.temp_directory.name) / "routing.journal.json"
        controller = DeviceController(
            self.installation, self.catalog, transport_factory=FakeTransport
        )
        result = controller.apply(prepared, journal_path=journal_path)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["applied"][0]["routing_template"]["template_id"], 4)
        self.assertEqual(
            result["rollback"][0]["command"],
            int(Command.ROUTING_TEMPLATE_SELECT),
        )
        self.assertEqual(result["rollback"][0]["payload_hex"], "01000000")

    def test_routing_template_can_capture_dynamic_rollback(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Dynamic routing rollback",
                "target_patch": "A50-1",
                "actions": [
                    {
                        "type": "set_routing_template",
                        "template": "Serial",
                    }
                ],
            }
        )
        prepared = prepare_plan(plan, self.catalog)
        journal_path = Path(self.temp_directory.name) / "dynamic-routing.journal.json"
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=CurrentPresetTimeoutTransport,
        )
        result = controller.apply(prepared, journal_path=journal_path)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["rollback"][0]["payload_hex"], "01000000")

    def test_save_preset_verifies_target_and_name(self):
        apply_journal_path = Path(self.temp_directory.name) / "apply.journal.json"
        apply_journal_path.write_text(
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
        prepared = prepare_preset_save(apply_journal_path, "Hana Solo")
        save_journal_path = Path(self.temp_directory.name) / "save.journal.json"
        controller = DeviceController(
            self.installation, self.catalog, transport_factory=FakeTransport
        )
        result = controller.save_preset(prepared, journal_path=save_journal_path)
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["verified_patch"], "A50-1")
        self.assertEqual(result["requested_name"], "Hana Solo")
        self.assertTrue(result["save_response_verified"])
        self.assertTrue(result["target_preflight_verified"])
        self.assertFalse(result["rollback_supported"])

    def test_save_preset_refuses_different_current_patch(self):
        apply_journal_path = Path(self.temp_directory.name) / "apply.journal.json"
        apply_journal_path.write_text(
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
        prepared = prepare_preset_save(apply_journal_path, "Hana Solo")
        save_journal_path = Path(self.temp_directory.name) / "save.journal.json"
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=WrongSaveTargetTransport,
        )
        with self.assertRaises(PlanValidationError):
            controller.save_preset(prepared, journal_path=save_journal_path)
        journal = json.loads(save_journal_path.read_text(encoding="utf-8"))
        self.assertEqual(journal["status"], "refused_target_patch_mismatch")

    def test_apply_can_auto_select_unknown_target_patch(self):
        plan = TonePlan.from_dict(
            {
                "schema_version": 1,
                "title": "Automatic patch selection",
                "target_patch": "A50-1",
                "select_target_patch": True,
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
        journal_path = Path(self.temp_directory.name) / "auto-select.journal.json"
        controller = DeviceController(
            self.installation,
            self.catalog,
            transport_factory=UnknownPatchTransport,
        )
        result = controller.apply(prepared, journal_path=journal_path)
        self.assertEqual(result["status"], "applied")
        self.assertTrue(result["target_patch_selection"]["performed"])
        self.assertEqual(
            result["target_patch_selection"]["reason"],
            "protocol_location_unknown",
        )
        self.assertEqual(result["current_patch"]["label"], "A50-1")
        self.assertEqual(
            result["current_patch"]["verification"],
            "auto_selected_and_device_verified",
        )


if __name__ == "__main__":
    unittest.main()
