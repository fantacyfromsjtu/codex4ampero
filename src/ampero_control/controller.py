import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .catalog import EffectCatalog
from .constants import Command, MessageFlag, SAFE_WRITE_COMMANDS
from .dart_bridge import DartBridgeTransport
from .errors import (
    AmperoError,
    DeviceTimeoutError,
    DeviceWriteVerificationError,
    PatchLocationUnknownError,
    PlanValidationError,
)
from .installation import EditorInstallation
from .patch_location import parse_patch_label, patch_location_from_index
from .plan import (
    ResolvedAction,
    SetModelAction,
    SetParameterAction,
    SetRoutingTemplateAction,
    SetSceneAction,
    TonePlan,
    resolve_plan,
)
from .preset_save import PreparedPresetSave, build_preset_save_preview
from .protocol import (
    decode_model,
    decode_parameter,
    encode_set_model,
    encode_set_parameter,
    pack_int,
    unpack_int,
)
from .preset import parse_current_preset, parse_routing_template_response
from .safety import SafetyReport, validate_actions


@dataclass(frozen=True)
class PreparedPlan:
    plan: TonePlan
    actions: tuple[ResolvedAction, ...]
    safety: SafetyReport

    def to_dict(self) -> dict:
        result = {
            "schema_version": self.plan.schema_version,
            "title": self.plan.title,
            "reason": self.plan.reason,
            "safety": self.safety.to_dict(),
            "commands": [action.to_dict() for action in self.actions],
        }
        if self.plan.research:
            result["research"] = self.plan.research.to_dict()
        if self.plan.target_patch:
            location = parse_patch_label(self.plan.target_patch)
            result["target_patch"] = location.label
            result["target_patch_index"] = location.index
            if self.plan.save_preview_name:
                result["post_apply_save_preview"] = build_preset_save_preview(
                    location, self.plan.save_preview_name
                )
        if self.plan.select_target_patch:
            result["target_patch_selection"] = {
                "enabled": True,
                "behavior": (
                    "Load target_patch before actions when the current protocol location "
                    "is unknown or different, then require an exact device readback."
                ),
                "warning": (
                    "Loading a patch can discard unsaved edits in the current live buffer."
                ),
            }
        return result


def prepare_plan(plan: TonePlan, catalog: EffectCatalog) -> PreparedPlan:
    actions = resolve_plan(plan, catalog)
    safety = validate_actions(actions)
    if plan.select_target_patch:
        safety = SafetyReport(
            tuple(
                dict.fromkeys(
                    (
                        *safety.warnings,
                        "automatic target-patch loading can discard unsaved live edits",
                    )
                )
            )
        )
    return PreparedPlan(plan=plan, actions=actions, safety=safety)


class DeviceController:
    def __init__(
        self,
        installation: EditorInstallation,
        catalog: EffectCatalog,
        transport_factory=DartBridgeTransport,
    ):
        self.installation = installation
        self.catalog = catalog
        self._transport_factory = transport_factory

    def scan(self) -> dict:
        with self._transport_factory(self.installation) as transport:
            return transport.scan()

    def routing(self, *, timeout: float = 5.0) -> dict:
        with self._transport_factory(self.installation) as transport:
            transport.connect()
            return self._read_routing_template(transport, timeout=timeout)

    def snapshot(
        self,
        *,
        slot_count: int = 12,
        include_parameters: bool = False,
        timeout: float = 1.5,
    ) -> dict:
        with self._transport_factory(self.installation) as transport:
            transport.connect()
            patch_index = None
            patch_location_read_error = None
            try:
                patch_index = self._read_patch_index(transport, timeout=timeout)
            except AmperoError as error:
                patch_location_read_error = {
                    "error": type(error).__name__,
                    "message": str(error),
                }
            scene_response = transport.request(
                int(Command.CURRENT_SCENE), timeout=timeout
            )
            current_scene = (
                unpack_int(scene_response.data[0:2])
                if len(scene_response.data) >= 2
                else 0
            )
            preset_response = transport.request(
                int(Command.CURRENT_PRESET), timeout=max(timeout, 5.0)
            )
        snapshot = parse_current_preset(
            preset_response.data,
            self.catalog,
            current_scene=current_scene,
            include_parameters=include_parameters,
        )
        snapshot["slots"] = snapshot["slots"][:slot_count]
        snapshot["slot_count"] = len(snapshot["slots"])
        snapshot["patch_location_verified"] = patch_index is not None
        if patch_index is None:
            snapshot["patch_location_read_error"] = patch_location_read_error
        else:
            patch_location = patch_location_from_index(patch_index)
            snapshot["patch_index"] = patch_location.index
            snapshot["patch_bank"] = patch_location.bank
            snapshot["patch_number"] = patch_location.patch
            snapshot["patch_label"] = patch_location.label
        return snapshot

    def apply(
        self,
        prepared: PreparedPlan,
        *,
        journal_path: Path,
        allow_unverified_reads: bool = False,
        confirmed_device_patch: Optional[str] = None,
    ) -> dict:
        journal = {
            "schema_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "plan": prepared.to_dict(),
            "rollback": [],
            "applied": [],
            "status": "started",
        }
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(journal_path, journal)
        with self._transport_factory(self.installation) as transport:
            transport.connect()
            target_patch = None
            if prepared.plan.target_patch:
                target_patch = parse_patch_label(prepared.plan.target_patch)
                journal["target_patch"] = {
                    "index": target_patch.index,
                    "bank": target_patch.bank,
                    "patch": target_patch.patch,
                    "label": target_patch.label,
                }
            current_patch = None
            patch_location_error = None
            try:
                current_patch_index = self._read_patch_index(transport)
                current_patch = patch_location_from_index(current_patch_index)
                journal["current_patch"] = {
                    "index": current_patch.index,
                    "bank": current_patch.bank,
                    "patch": current_patch.patch,
                    "label": current_patch.label,
                    "verification": "device_protocol",
                }
            except PatchLocationUnknownError as error:
                patch_location_error = error
                journal["patch_location_read_error"] = {
                    "error": type(error).__name__,
                    "message": str(error),
                }
            if (
                target_patch is not None
                and prepared.plan.select_target_patch
                and (
                    current_patch is None
                    or current_patch.index != target_patch.index
                )
            ):
                previous_patch = (
                    {
                        "index": current_patch.index,
                        "bank": current_patch.bank,
                        "patch": current_patch.patch,
                        "label": current_patch.label,
                    }
                    if current_patch is not None
                    else None
                )
                selection_reason = (
                    "protocol_location_unknown"
                    if current_patch is None
                    else "protocol_location_mismatch"
                )
                current_patch = self._select_target_patch(transport, target_patch)
                journal["target_patch_selection"] = {
                    "performed": True,
                    "reason": selection_reason,
                    "previous_patch": previous_patch,
                    "selected_patch": target_patch.label,
                    "selected_index": target_patch.index,
                    "readback_verified": True,
                }
                journal["current_patch"] = {
                    "index": current_patch.index,
                    "bank": current_patch.bank,
                    "patch": current_patch.patch,
                    "label": current_patch.label,
                    "verification": "auto_selected_and_device_verified",
                }
                patch_location_error = None
            if current_patch is None:
                error = patch_location_error
                if target_patch is None or confirmed_device_patch is None:
                    journal["status"] = "refused_unverified_target_patch"
                    _write_json(journal_path, journal)
                    raise PlanValidationError(
                        "device reports an unknown current patch index; provide an exact "
                        "device-screen confirmation matching plan target_patch or enable "
                        "select_target_patch in the reviewed plan"
                    ) from error
                confirmed_patch = parse_patch_label(confirmed_device_patch)
                if confirmed_patch.index != target_patch.index:
                    journal["confirmed_device_patch"] = confirmed_patch.label
                    journal["status"] = "refused_manual_target_patch_mismatch"
                    _write_json(journal_path, journal)
                    raise PlanValidationError(
                        f"device-screen confirmation is {confirmed_patch.label}, but the "
                        f"plan targets {target_patch.label}"
                    ) from error
                current_patch = confirmed_patch
                journal["current_patch"] = {
                    "index": current_patch.index,
                    "bank": current_patch.bank,
                    "patch": current_patch.patch,
                    "label": current_patch.label,
                    "verification": "user_confirmed_device_display",
                    "protocol_index_unknown": True,
                }
            elif prepared.plan.select_target_patch:
                journal.setdefault(
                    "target_patch_selection",
                    {
                        "performed": False,
                        "reason": "already_on_target",
                        "selected_patch": target_patch.label if target_patch else None,
                        "selected_index": target_patch.index if target_patch else None,
                        "readback_verified": True,
                    },
                )
            if confirmed_device_patch is not None:
                confirmed_patch = parse_patch_label(confirmed_device_patch)
                journal["confirmed_device_patch"] = confirmed_patch.label
                if confirmed_patch.index != current_patch.index:
                    journal["status"] = "refused_manual_target_patch_mismatch"
                    _write_json(journal_path, journal)
                    raise PlanValidationError(
                        f"device-screen confirmation is {confirmed_patch.label}, but the "
                        f"device protocol reports {current_patch.label}"
                    )
            if target_patch is not None:
                if current_patch.index != target_patch.index:
                    journal["status"] = "refused_target_patch_mismatch"
                    _write_json(journal_path, journal)
                    raise PlanValidationError(
                        f"target patch is {target_patch.label} (index {target_patch.index}) "
                        f"but device reports {current_patch.label} "
                        f"(index {current_patch.index})"
                    )
            _write_json(journal_path, journal)
            try:
                for resolved in prepared.actions:
                    _validate_write(
                        int(resolved.command.command), resolved.command.payload
                    )
                    rollback = self._capture_rollback(
                        transport, resolved, allow_unverified_reads
                    )
                    if rollback:
                        journal["rollback"].insert(0, rollback)
                        _write_json(journal_path, journal)
                    verification_response = None
                    if isinstance(resolved.source, SetRoutingTemplateAction):
                        message_id, verification_response = transport.send_and_wait(
                            int(resolved.command.command),
                            int(Command.ROUTING_TEMPLATE),
                            resolved.command.payload,
                            MessageFlag.SEND,
                            timeout=5.0,
                        )
                    else:
                        message_id = transport.send(
                            int(resolved.command.command),
                            resolved.command.payload,
                            MessageFlag.SEND,
                        )
                        time.sleep(0.08)
                    self._verify_applied(
                        transport, resolved, response=verification_response
                    )
                    journal["applied"].append(
                        {
                            **resolved.to_dict(),
                            "message_id": message_id,
                            "readback_verified": True,
                        }
                    )
                    _write_json(journal_path, journal)
            except Exception:
                journal["status"] = "failed; attempting rollback"
                _write_json(journal_path, journal)
                self._apply_rollback_entries(transport, journal["rollback"])
                journal["status"] = "rolled_back_after_failure"
                _write_json(journal_path, journal)
                raise
        journal["status"] = "applied"
        _write_json(journal_path, journal)
        return journal

    def save_preset(
        self,
        prepared: PreparedPresetSave,
        *,
        journal_path: Path,
    ) -> dict:
        journal = {
            "schema_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source_apply_journal": str(prepared.source_journal),
            "save": prepared.to_dict(),
            "status": "preflight",
            "rollback_supported": False,
        }
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(journal_path, journal)
        try:
            with self._transport_factory(self.installation) as transport:
                transport.connect()
                current_index = self._read_patch_index(transport, timeout=3.0)
                if current_index != prepared.target_patch.index:
                    current_patch = patch_location_from_index(current_index)
                    journal["status"] = "refused_target_patch_mismatch"
                    journal["current_patch"] = {
                        "label": current_patch.label,
                        "index": current_patch.index,
                    }
                    _write_json(journal_path, journal)
                    raise PlanValidationError(
                        f"save targets {prepared.target_patch.label}, but device reports "
                        f"{current_patch.label}"
                    )
                journal["current_patch"] = {
                    "label": prepared.target_patch.label,
                    "index": prepared.target_patch.index,
                }
                journal["target_preflight_verified"] = True
                journal["status"] = "ready_to_save"
                _write_json(journal_path, journal)
                if len(prepared.command.payload) != 21:
                    raise PlanValidationError(
                        "preset save payload must contain exactly 21 bytes"
                    )
                journal["status"] = "sending_save"
                _write_json(journal_path, journal)
                message_id, response = transport.send_and_wait(
                    int(Command.PRESET_SAVE),
                    int(Command.PRESET_SAVE),
                    prepared.command.payload,
                    MessageFlag.SEND,
                    timeout=5.0,
                )
                journal["message_id"] = message_id
                journal["response"] = {
                    "address": f"0x{response.address:08x}",
                    "flag": response.flag,
                    "payload_hex": response.data.hex(" "),
                }
                journal["verified_patch"] = prepared.target_patch.label
                journal["requested_name"] = prepared.preset_name
                journal["save_response_verified"] = True
                journal["status"] = "saved"
                _write_json(journal_path, journal)
                return journal
        except Exception as error:
            failed_stage = journal.get("status")
            if failed_stage not in ("refused_target_patch_mismatch", "saved"):
                journal["status"] = "save_failed_no_rollback"
                journal["failed_stage"] = failed_stage
            journal["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            _write_json(journal_path, journal)
            raise

    def _select_target_patch(self, transport, target_patch):
        payload = pack_int(target_patch.index, 4)
        if len(payload) != 4:
            raise PlanValidationError("patch selection payload must contain four bytes")
        transport.send(int(Command.PRESET_INDEX), payload, MessageFlag.SEND)
        time.sleep(0.25)
        transport.request(int(Command.CURRENT_PRESET), timeout=10.0)
        selected_index = self._read_patch_index(transport, timeout=3.0)
        if selected_index != target_patch.index:
            selected_patch = patch_location_from_index(selected_index)
            raise DeviceWriteVerificationError(
                f"automatic patch selection expected {target_patch.label} "
                f"(index {target_patch.index}), but device reports "
                f"{selected_patch.label} (index {selected_patch.index})"
            )
        return patch_location_from_index(selected_index)

    def rollback(self, journal_path: Path) -> dict:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        entries = journal.get("rollback", [])
        if not entries:
            raise PlanValidationError("journal does not contain rollback entries")
        with self._transport_factory(self.installation) as transport:
            transport.connect()
            self._apply_rollback_entries(transport, entries)
        journal["status"] = "rolled_back"
        journal["rolled_back_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        _write_json(journal_path, journal)
        return journal

    def _capture_rollback(
        self,
        transport: DartBridgeTransport,
        resolved: ResolvedAction,
        allow_unverified_reads: bool,
    ) -> Optional[dict]:
        source = resolved.source
        if isinstance(source, SetParameterAction):
            assert resolved.parameter is not None
            try:
                response = transport.request(
                    int(Command.PRESET_SLOT_PARAMETER),
                    pack_int(source.slot, 2)
                    + pack_int(resolved.parameter.parameter_id, 2),
                )
                slot, parameter_id, value = decode_parameter(response.data)
                if slot != source.slot or parameter_id != resolved.parameter.parameter_id:
                    raise PlanValidationError(
                        "device returned a different slot/parameter during preflight read"
                    )
            except DeviceTimeoutError:
                if source.expected_before is not None:
                    value = source.expected_before
                elif allow_unverified_reads:
                    return None
                else:
                    raise PlanValidationError(
                        "could not read the current parameter value; add expected_before "
                        "or use --allow-unverified-reads after manual verification"
                    )
            return {
                "command": int(Command.PRESET_SLOT_PARAMETER),
                "payload_hex": encode_set_parameter(
                    source.slot, resolved.parameter.parameter_id, value
                ).hex(),
                "description": (
                    f"Restore slot {source.slot} {resolved.effect.name}/"
                    f"{resolved.parameter.name} to {value:g}"
                ),
            }
        if isinstance(source, SetModelAction):
            try:
                response = transport.request(
                    int(Command.PRESET_SLOT_MODULE), pack_int(source.slot, 1)
                )
                slot, category_id, model_code, enabled = decode_model(response.data)
                if slot != source.slot:
                    raise PlanValidationError(
                        "device returned a different slot during model preflight read"
                    )
            except DeviceTimeoutError:
                if allow_unverified_reads:
                    return None
                raise PlanValidationError(
                    "could not read the current model; model changes require a verified "
                    "preflight read unless --allow-unverified-reads is supplied"
                )
            return {
                "command": int(Command.PRESET_SLOT_MODULE),
                "payload_hex": encode_set_model(
                    slot, category_id, model_code, enabled
                ).hex(),
                "description": f"Restore slot {source.slot} model",
            }
        if isinstance(source, SetSceneAction):
            return None
        if isinstance(source, SetRoutingTemplateAction):
            routing = self._read_routing_template(transport, timeout=5.0)
            current_template_id = routing.get("template_id")
            current_template = routing.get("template", "Unknown")
            if (
                source.expected_before_id is not None
                and current_template_id != source.expected_before_id
            ):
                raise PlanValidationError(
                    "routing preflight mismatch: plan expects "
                    f"{source.expected_before} ({source.expected_before_id}), but device "
                    f"reports {current_template} ({current_template_id})"
                )
            return {
                "command": int(Command.ROUTING_TEMPLATE_SELECT),
                "payload_hex": pack_int(current_template_id, 4).hex(),
                "response_address": int(Command.ROUTING_TEMPLATE),
                "description": (
                    f"Restore routing template to {current_template}"
                ),
            }
        return None

    @staticmethod
    def _read_routing_template(transport, *, timeout: float) -> dict:
        response = transport.request(int(Command.ROUTING_TEMPLATE), timeout=timeout)
        return parse_routing_template_response(response.data)

    def _read_patch_index(
        self, transport: DartBridgeTransport, timeout: float = 2.0
    ) -> int:
        transport.send(int(Command.SCREEN_LOCK), b"", MessageFlag.REQUEST)
        time.sleep(0.1)
        for _ in range(5):
            transport.send(
                int(Command.SOFTWARE_STATE), b"", MessageFlag.REQUEST
            )
            time.sleep(0.2)
        response = transport.request(int(Command.PRESET_INDEX), timeout=timeout)
        if len(response.data) < 2:
            raise PlanValidationError(
                "device returned fewer than two bytes for current patch index"
            )
        patch_index = int.from_bytes(response.data[0:2], "little", signed=False)
        if patch_index == 0xFFFF:
            raise PatchLocationUnknownError(
                "device returned 0xffff for current patch index; patch location is unknown"
            )
        return patch_index

    def _verify_applied(
        self,
        transport: DartBridgeTransport,
        resolved: ResolvedAction,
        response=None,
    ) -> None:
        source = resolved.source
        if isinstance(source, SetModelAction):
            assert resolved.effect is not None
            response = transport.request(
                int(Command.PRESET_SLOT_MODULE), pack_int(source.slot, 1)
            )
            slot, category_id, model_code, enabled = decode_model(response.data)
            expected = (
                source.slot,
                resolved.effect.category_id,
                resolved.effect.model_code,
                source.enabled,
            )
            actual = (slot, category_id, model_code, enabled)
            if actual != expected:
                raise DeviceWriteVerificationError(
                    f"model write readback mismatch: expected {expected}, got {actual}"
                )
            return
        if isinstance(source, SetParameterAction):
            assert resolved.parameter is not None
            response = transport.request(
                int(Command.PRESET_SLOT_PARAMETER),
                pack_int(source.slot, 2)
                + pack_int(resolved.parameter.parameter_id, 2),
            )
            slot, parameter_id, value = decode_parameter(response.data)
            tolerance = max(abs(resolved.parameter.step) / 2.0, 1e-4)
            if (
                slot != source.slot
                or parameter_id != resolved.parameter.parameter_id
                or abs(value - source.value) > tolerance
            ):
                raise DeviceWriteVerificationError(
                    "parameter write readback mismatch: expected "
                    f"slot {source.slot} parameter {resolved.parameter.parameter_id} "
                    f"value {source.value:g}, got slot {slot} parameter {parameter_id} "
                    f"value {value:g}"
                )
            return
        if isinstance(source, SetSceneAction):
            response = transport.request(int(Command.CURRENT_SCENE))
            scene = unpack_int(response.data[0:2]) if len(response.data) >= 2 else -1
            if scene != source.scene:
                raise DeviceWriteVerificationError(
                    f"scene write readback mismatch: expected {source.scene}, got {scene}"
                )
            return
        if isinstance(source, SetRoutingTemplateAction):
            if response is None:
                raise DeviceWriteVerificationError(
                    "routing template write did not return a complete template response"
                )
            routing = parse_routing_template_response(response.data)
            response_template_id = routing["response_template_id"]
            topology_template_id = routing["template_id"]
            if (
                response_template_id != source.template_id
                or topology_template_id != source.template_id
            ):
                raise DeviceWriteVerificationError(
                    "routing template response mismatch: expected "
                    f"{source.template} ({source.template_id}), got response ID "
                    f"{response_template_id} and topology {routing['template']} "
                    f"({topology_template_id})"
                )
            return
        raise DeviceWriteVerificationError(
            f"unsupported action verification: {type(source).__name__}"
        )

    def _read_parameters(self, transport, slot_id, effect, timeout: float) -> list:
        parameters = []
        for parameter in effect.parameters:
            result = {
                "name": parameter.name,
                "parameter_id": parameter.parameter_id,
                "minimum": parameter.minimum,
                "maximum": parameter.maximum,
            }
            try:
                response = transport.request(
                    int(Command.PRESET_SLOT_PARAMETER),
                    pack_int(slot_id, 2) + pack_int(parameter.parameter_id, 2),
                    timeout=timeout,
                )
                returned_slot, returned_parameter, value = decode_parameter(
                    response.data
                )
                if returned_slot != slot_id or returned_parameter != parameter.parameter_id:
                    raise PlanValidationError(
                        "device returned a different parameter during snapshot"
                    )
                result["value"] = value
            except (DeviceTimeoutError, ValueError, PlanValidationError) as error:
                result["read_error"] = str(error)
            parameters.append(result)
        return parameters

    def _apply_rollback_entries(
        self, transport: DartBridgeTransport, entries: list
    ) -> None:
        for entry in entries:
            command = int(entry["command"])
            payload = bytes.fromhex(entry["payload_hex"])
            _validate_write(command, payload)
            response_address = entry.get("response_address")
            if response_address is not None:
                transport.send_and_wait(
                    command,
                    int(response_address),
                    payload,
                    MessageFlag.SEND,
                    timeout=5.0,
                )
            else:
                transport.send(
                    command,
                    payload,
                    MessageFlag.SEND,
                )
            time.sleep(0.06)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _validate_write(command_value: int, payload: bytes) -> None:
    try:
        command = Command(command_value)
    except ValueError as error:
        raise PlanValidationError(
            f"refusing unknown write command 0x{command_value:08x}"
        ) from error
    if command not in SAFE_WRITE_COMMANDS:
        raise PlanValidationError(f"write command is not whitelisted: {command.name}")
    exact_lengths = {
        Command.PRESET_SLOT_MODULE: 7,
        Command.PRESET_SLOT_PARAMETER: 8,
        Command.CURRENT_SCENE: 1,
        Command.ROUTING_TEMPLATE_SELECT: 4,
    }
    expected_length = exact_lengths.get(command)
    if expected_length is not None and len(payload) != expected_length:
        raise PlanValidationError(
            f"invalid payload length for {command.name}: "
            f"expected {expected_length}, got {len(payload)}"
        )
