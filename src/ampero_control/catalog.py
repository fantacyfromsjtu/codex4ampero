import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .installation import EditorInstallation


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    parameter_id: int
    default: float
    minimum: float
    maximum: float
    step: float
    value_type: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "parameter_id": self.parameter_id,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
            "value_type": self.value_type,
        }


@dataclass(frozen=True)
class EffectSpec:
    name: str
    category_name: str
    category_id: int
    model_code: int
    model_index: int
    classification: str
    description: str
    parameters: tuple[ParameterSpec, ...]

    def parameter(self, name_or_id) -> ParameterSpec:
        if isinstance(name_or_id, int):
            for parameter in self.parameters:
                if parameter.parameter_id == name_or_id:
                    return parameter
        else:
            wanted = _normalize(str(name_or_id))
            for parameter in self.parameters:
                if _normalize(parameter.name) == wanted:
                    return parameter
        raise KeyError(f"parameter not found for {self.name}: {name_or_id}")

    def to_dict(self, *, include_description: bool = False) -> dict:
        result = {
            "name": self.name,
            "category_name": self.category_name,
            "category_id": self.category_id,
            "model_code": self.model_code,
            "model_index": self.model_index,
            "classification": self.classification,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
        }
        if include_description:
            result["description"] = self.description
        return result


class EffectCatalog:
    def __init__(self, effects: Iterable[EffectSpec], source: Path):
        self.effects = tuple(effects)
        self.source = source

    @classmethod
    def from_installation(cls, installation: EditorInstallation) -> "EffectCatalog":
        files = list(installation.catalog_directory.glob("v*_alg_data.json"))
        if not files:
            raise FileNotFoundError(
                f"no algorithm catalog found in {installation.catalog_directory}"
            )
        source = max(files, key=_version_key)
        return cls.from_file(source)

    @classmethod
    def from_file(cls, source: Path) -> "EffectCatalog":
        raw = json.loads(source.read_text(encoding="utf-8"))
        categories = raw["PluginProperties"]["Modules"]["Catalog"]
        effects = []
        for category in categories:
            category_name = str(category["Name"])
            category_id = int(category["Index"])
            for algorithm in category.get("Alg", []):
                widgets = algorithm.get("Widget", [])
                if isinstance(widgets, dict):
                    widgets = [widgets]
                if not isinstance(widgets, list):
                    widgets = []
                parameters = tuple(
                    ParameterSpec(
                        name=str(widget["Name"]),
                        parameter_id=int(widget["ID"]),
                        default=float(widget.get("DefaultValue", 0)),
                        minimum=float(widget.get("DisplayMin", 0)),
                        maximum=float(widget.get("DisplayMax", 100)),
                        step=float(widget.get("Step", 1)),
                        value_type=str(widget.get("Type", "0")),
                    )
                    for widget in widgets
                    if isinstance(widget, dict) and "Name" in widget and "ID" in widget
                )
                effects.append(
                    EffectSpec(
                        name=str(algorithm["Name"]),
                        category_name=category_name,
                        category_id=category_id,
                        model_code=int(algorithm["Code"]),
                        model_index=int(algorithm["Index"]),
                        classification=str(algorithm.get("classify", "")),
                        description=str(algorithm.get("descriptionEN", "")),
                        parameters=parameters,
                    )
                )
        return cls(effects, source)

    def find_exact(self, name: str, category: Optional[str] = None) -> EffectSpec:
        wanted = _normalize(name)
        category_wanted = _normalize(category) if category else None
        matches = [
            effect
            for effect in self.effects
            if _normalize(effect.name) == wanted
            and (
                category_wanted is None
                or _normalize(effect.category_name) == category_wanted
            )
        ]
        if not matches:
            raise KeyError(f"effect not found: {name}")
        if len(matches) > 1:
            categories = ", ".join(effect.category_name for effect in matches)
            raise KeyError(f"effect name is ambiguous; specify a category: {categories}")
        return matches[0]

    def find_by_code(self, category_id: int, model_code: int) -> Optional[EffectSpec]:
        for effect in self.effects:
            if effect.category_id == category_id and effect.model_code == model_code:
                return effect
        return None

    def search(
        self, query: str, *, category: Optional[str] = None, limit: int = 20
    ) -> list[EffectSpec]:
        terms = [_normalize(term) for term in query.split() if term.strip()]
        category_wanted = _normalize(category) if category else None
        scored = []
        for effect in self.effects:
            if category_wanted and _normalize(effect.category_name) != category_wanted:
                continue
            haystack = " ".join(
                (
                    _normalize(effect.name),
                    _normalize(effect.category_name),
                    _normalize(effect.classification),
                    _normalize(effect.description),
                )
            )
            if not all(term in haystack for term in terms):
                continue
            name = _normalize(effect.name)
            score = sum(10 if term == name else 5 if name.startswith(term) else 1 for term in terms)
            scored.append((score, effect))
        scored.sort(key=lambda item: (-item[0], item[1].category_id, item[1].model_index))
        return [effect for _, effect in scored[:limit]]


def _normalize(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _version_key(path: Path) -> tuple[int, ...]:
    match = re.search(r"v(\d+(?:\.\d+)*)", path.name)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))
