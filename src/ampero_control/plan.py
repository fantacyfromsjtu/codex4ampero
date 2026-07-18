import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .catalog import EffectCatalog, EffectSpec, ParameterSpec
from .constants import (
    MAX_PARAMETER_ID,
    MAX_SCENE_ID,
    MAX_SLOT_ID,
    Command,
)
from .errors import PlanValidationError
from .protocol import (
    EncodedCommand,
    encode_scene,
    encode_set_model,
    encode_set_parameter,
    ensure_finite,
)


@dataclass(frozen=True)
class EffectReference:
    name: str
    category: Optional[str] = None

    @classmethod
    def from_dict(cls, value: dict) -> "EffectReference":
        name = str(value.get("name", "")).strip()
        if not name:
            raise PlanValidationError("effect.name is required")
        category = value.get("category")
        return cls(name=name, category=str(category) if category else None)


@dataclass(frozen=True)
class SetModelAction:
    slot: int
    effect: EffectReference
    enabled: bool = True


@dataclass(frozen=True)
class SetParameterAction:
    slot: int
    effect: EffectReference
    parameter: Union[str, int]
    value: float
    expected_before: Optional[float] = None


@dataclass(frozen=True)
class SetSceneAction:
    scene: int


PlanAction = Union[SetModelAction, SetParameterAction, SetSceneAction]


@dataclass(frozen=True)
class TonePlan:
    schema_version: int
    title: str
    reason: str
    actions: tuple[PlanAction, ...]

    @classmethod
    def from_file(cls, path: Path) -> "TonePlan":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, value: dict) -> "TonePlan":
        schema_version = int(value.get("schema_version", 0))
        if schema_version != 1:
            raise PlanValidationError("schema_version must be 1")
        title = str(value.get("title", "Untitled tone change")).strip()
        reason = str(value.get("reason", "")).strip()
        raw_actions = value.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise PlanValidationError("actions must be a non-empty list")
        actions = tuple(_parse_action(action) for action in raw_actions)
        return cls(
            schema_version=schema_version,
            title=title,
            reason=reason,
            actions=actions,
        )


@dataclass(frozen=True)
class ResolvedAction:
    source: PlanAction
    effect: Optional[EffectSpec]
    parameter: Optional[ParameterSpec]
    command: EncodedCommand

    def to_dict(self) -> dict:
        result = self.command.to_dict()
        if self.effect:
            result["effect"] = {
                "name": self.effect.name,
                "category": self.effect.category_name,
                "category_id": self.effect.category_id,
                "model_code": self.effect.model_code,
            }
        if self.parameter:
            result["parameter"] = self.parameter.to_dict()
        return result


def resolve_plan(plan: TonePlan, catalog: EffectCatalog) -> tuple[ResolvedAction, ...]:
    resolved = []
    selected_models = {}
    for action in plan.actions:
        if isinstance(action, SetModelAction):
            effect = catalog.find_exact(action.effect.name, action.effect.category)
            selected_models[action.slot] = effect
            command = EncodedCommand(
                command=Command.PRESET_SLOT_MODULE,
                payload=encode_set_model(
                    action.slot,
                    effect.category_id,
                    effect.model_code,
                    action.enabled,
                ),
                description=(
                    f"Set slot {action.slot} to {effect.category_name}/{effect.name} "
                    f"({'on' if action.enabled else 'off'})"
                ),
            )
            resolved.append(ResolvedAction(action, effect, None, command))
        elif isinstance(action, SetParameterAction):
            effect = catalog.find_exact(action.effect.name, action.effect.category)
            selected = selected_models.get(action.slot)
            if selected and selected.model_code != effect.model_code:
                raise PlanValidationError(
                    f"slot {action.slot} parameter effect {effect.name} does not match "
                    f"the model selected earlier in the plan ({selected.name})"
                )
            parameter = effect.parameter(action.parameter)
            command = EncodedCommand(
                command=Command.PRESET_SLOT_PARAMETER,
                payload=encode_set_parameter(
                    action.slot, parameter.parameter_id, action.value
                ),
                description=(
                    f"Set slot {action.slot} {effect.name}/{parameter.name} "
                    f"to {action.value:g}"
                ),
            )
            resolved.append(ResolvedAction(action, effect, parameter, command))
        elif isinstance(action, SetSceneAction):
            command = EncodedCommand(
                command=Command.CURRENT_SCENE,
                payload=encode_scene(action.scene),
                description=f"Switch to scene {action.scene + 1}",
            )
            resolved.append(ResolvedAction(action, None, None, command))
        else:
            raise PlanValidationError(f"unsupported action: {action}")
    return tuple(resolved)


def _parse_action(value: dict) -> PlanAction:
    if not isinstance(value, dict):
        raise PlanValidationError("each action must be an object")
    action_type = value.get("type")
    if action_type == "set_model":
        slot = _slot(value.get("slot"))
        effect = EffectReference.from_dict(_mapping(value.get("effect"), "effect"))
        return SetModelAction(slot=slot, effect=effect, enabled=bool(value.get("enabled", True)))
    if action_type == "set_parameter":
        slot = _slot(value.get("slot"))
        effect = EffectReference.from_dict(_mapping(value.get("effect"), "effect"))
        parameter = value.get("parameter")
        if not isinstance(parameter, (str, int)) or parameter == "":
            raise PlanValidationError("set_parameter.parameter must be a name or ID")
        if isinstance(parameter, int) and not 0 <= parameter <= MAX_PARAMETER_ID:
            raise PlanValidationError(
                f"parameter ID must be between 0 and {MAX_PARAMETER_ID}"
            )
        numeric_value = float(value.get("value"))
        ensure_finite(numeric_value, "set_parameter.value")
        expected_before = value.get("expected_before")
        if expected_before is not None:
            expected_before = float(expected_before)
            ensure_finite(expected_before, "set_parameter.expected_before")
        return SetParameterAction(
            slot=slot,
            effect=effect,
            parameter=parameter,
            value=numeric_value,
            expected_before=expected_before,
        )
    if action_type == "set_scene":
        scene = int(value.get("scene"))
        if not 0 <= scene <= MAX_SCENE_ID:
            raise PlanValidationError(f"scene must be between 0 and {MAX_SCENE_ID}")
        return SetSceneAction(scene=scene)
    raise PlanValidationError(f"unsupported action type: {action_type}")


def _slot(value) -> int:
    slot = int(value)
    if not 0 <= slot <= MAX_SLOT_ID:
        raise PlanValidationError(f"slot must be between 0 and {MAX_SLOT_ID}")
    return slot


def _mapping(value, field: str) -> dict:
    if not isinstance(value, dict):
        raise PlanValidationError(f"{field} must be an object")
    return value
