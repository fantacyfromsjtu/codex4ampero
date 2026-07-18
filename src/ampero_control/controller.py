import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .catalog import EffectCatalog
from .constants import Command, MessageFlag, SAFE_WRITE_COMMANDS
from .dart_bridge import DartBridgeTransport
from .errors import DeviceTimeoutError, PlanValidationError
from .installation import EditorInstallation
from .plan import (
    ResolvedAction,
    SetModelAction,
    SetParameterAction,
    SetSceneAction,
    TonePlan,
    resolve_plan,
)
from .protocol import (
    decode_model,
    decode_parameter,
    encode_set_model,
    encode_set_parameter,
    pack_int,
    unpack_int,
)
from .preset import parse_current_preset
from .safety import SafetyReport, validate_actions


@dataclass(frozen=True)
class PreparedPlan:
    plan: TonePlan
    actions: tuple[ResolvedAction, ...]
    safety: SafetyReport

    def to_dict(self) -> dict:
        return {
            "schema_version": self.plan.schema_version,
            "title": self.plan.title,
            "reason": self.plan.reason,
            "safety": self.safety.to_dict(),
            "commands": [action.to_dict() for action in self.actions],
        }


def prepare_plan(plan: TonePlan, catalog: EffectCatalog) -> PreparedPlan:
    actions = resolve_plan(plan, catalog)
    safety = validate_actions(actions)
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

    def snapshot(
        self,
        *,
        slot_count: int = 12,
        include_parameters: bool = False,
        timeout: float = 1.5,
    ) -> dict:
        with self._transport_factory(self.installation) as transport:
            transport.connect()
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
        return snapshot

    def apply(
        self,
        prepared: PreparedPlan,
        *,
        journal_path: Path,
        allow_unverified_reads: bool = False,
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
                    message_id = transport.send(
                        int(resolved.command.command),
                        resolved.command.payload,
                        MessageFlag.SEND,
                    )
                    journal["applied"].append(
                        {
                            **resolved.to_dict(),
                            "message_id": message_id,
                        }
                    )
                    _write_json(journal_path, journal)
                    time.sleep(0.06)
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
        return None

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
    }
    expected_length = exact_lengths.get(command)
    if expected_length is not None and len(payload) != expected_length:
        raise PlanValidationError(
            f"invalid payload length for {command.name}: "
            f"expected {expected_length}, got {len(payload)}"
        )
