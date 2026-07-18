from dataclasses import dataclass
from typing import Iterable

from .errors import PlanValidationError
from .plan import ResolvedAction, SetParameterAction


SENSITIVE_LEVEL_NAMES = {
    "level",
    "output",
    "master",
    "volume",
    "patchvol",
    "mixlevel",
}


@dataclass(frozen=True)
class SafetyReport:
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"safe": True, "warnings": list(self.warnings)}


def validate_actions(actions: Iterable[ResolvedAction]) -> SafetyReport:
    warnings = []
    for resolved in actions:
        source = resolved.source
        if not isinstance(source, SetParameterAction):
            continue
        parameter = resolved.parameter
        if parameter is None:
            raise PlanValidationError("parameter metadata is missing")
        tolerance = max(abs(parameter.step) / 1000.0, 1e-6)
        if source.value < parameter.minimum - tolerance or source.value > parameter.maximum + tolerance:
            raise PlanValidationError(
                f"{resolved.effect.name}/{parameter.name} value {source.value:g} is outside "
                f"{parameter.minimum:g}..{parameter.maximum:g}"
            )
        normalized_name = "".join(character for character in parameter.name.lower() if character.isalnum())
        if normalized_name in SENSITIVE_LEVEL_NAMES:
            span = parameter.maximum - parameter.minimum
            if span > 0:
                ratio = (source.value - parameter.minimum) / span
                if ratio > 0.75:
                    raise PlanValidationError(
                        f"refusing high output-sensitive value for {parameter.name}: "
                        f"{source.value:g} exceeds the 75% safety ceiling"
                    )
            warnings.append(
                f"{resolved.effect.name}/{parameter.name} affects output level; monitor at low volume"
            )
        if source.expected_before is not None:
            span = parameter.maximum - parameter.minimum
            if span > 0 and abs(source.value - source.expected_before) / span > 0.4:
                warnings.append(
                    f"large change for {resolved.effect.name}/{parameter.name}: "
                    f"{source.expected_before:g} -> {source.value:g}"
                )
    return SafetyReport(tuple(dict.fromkeys(warnings)))
