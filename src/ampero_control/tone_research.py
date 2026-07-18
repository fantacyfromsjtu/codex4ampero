from dataclasses import dataclass
from datetime import date
from typing import Optional

from .errors import PlanValidationError


RESEARCH_CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})
RESEARCH_SOURCE_TYPES = frozenset(
    {
        "official_release",
        "artist_interview",
        "manufacturer",
        "transcription",
        "technical_reference",
        "community",
        "local_catalog",
    }
)


@dataclass(frozen=True)
class ToneResearchSource:
    title: str
    source_type: str
    tier: int
    finding: str
    reference: Optional[str] = None

    @classmethod
    def from_dict(cls, value: dict) -> "ToneResearchSource":
        if not isinstance(value, dict):
            raise PlanValidationError("research.sources entries must be objects")
        title = _required_text(value.get("title"), "research.sources[].title")
        source_type = _required_text(
            value.get("source_type"), "research.sources[].source_type"
        ).lower()
        if source_type not in RESEARCH_SOURCE_TYPES:
            supported = ", ".join(sorted(RESEARCH_SOURCE_TYPES))
            raise PlanValidationError(
                f"research.sources[].source_type must be one of: {supported}"
            )
        try:
            tier = int(value.get("tier"))
        except (TypeError, ValueError) as exc:
            raise PlanValidationError(
                "research.sources[].tier must be an integer from 1 to 3"
            ) from exc
        if tier not in (1, 2, 3):
            raise PlanValidationError(
                "research.sources[].tier must be an integer from 1 to 3"
            )
        finding = _required_text(
            value.get("finding"), "research.sources[].finding"
        )
        reference_value = value.get("reference")
        reference = (
            _required_text(reference_value, "research.sources[].reference")
            if reference_value is not None
            else None
        )
        return cls(
            title=title,
            source_type=source_type,
            tier=tier,
            finding=finding,
            reference=reference,
        )

    def to_dict(self) -> dict:
        result = {
            "title": self.title,
            "source_type": self.source_type,
            "tier": self.tier,
            "finding": self.finding,
        }
        if self.reference:
            result["reference"] = self.reference
        return result


@dataclass(frozen=True)
class ToneResearch:
    target: str
    researched_on: str
    confidence: str
    facts: tuple[str, ...]
    inferences: tuple[str, ...]
    limitations: tuple[str, ...]
    sources: tuple[ToneResearchSource, ...]

    @classmethod
    def from_dict(cls, value: dict) -> "ToneResearch":
        if not isinstance(value, dict):
            raise PlanValidationError("research must be an object")
        target = _required_text(value.get("target"), "research.target")
        researched_on = _required_text(
            value.get("researched_on"), "research.researched_on"
        )
        try:
            date.fromisoformat(researched_on)
        except ValueError as exc:
            raise PlanValidationError(
                "research.researched_on must use YYYY-MM-DD"
            ) from exc
        confidence = _required_text(
            value.get("confidence"), "research.confidence"
        ).lower()
        if confidence not in RESEARCH_CONFIDENCE_LEVELS:
            supported = ", ".join(sorted(RESEARCH_CONFIDENCE_LEVELS))
            raise PlanValidationError(
                f"research.confidence must be one of: {supported}"
            )
        facts = _text_list(value.get("facts", []), "research.facts")
        inferences = _text_list(value.get("inferences", []), "research.inferences")
        limitations = _text_list(value.get("limitations", []), "research.limitations")
        raw_sources = value.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise PlanValidationError("research.sources must be a non-empty list")
        sources = tuple(ToneResearchSource.from_dict(source) for source in raw_sources)
        if not facts and not inferences:
            raise PlanValidationError(
                "research must include at least one fact or inference"
            )
        return cls(
            target=target,
            researched_on=researched_on,
            confidence=confidence,
            facts=facts,
            inferences=inferences,
            limitations=limitations,
            sources=sources,
        )

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "researched_on": self.researched_on,
            "confidence": self.confidence,
            "facts": list(self.facts),
            "inferences": list(self.inferences),
            "limitations": list(self.limitations),
            "sources": [source.to_dict() for source in self.sources],
        }


def _required_text(value: object, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise PlanValidationError(f"{field} is required")
    return text


def _text_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PlanValidationError(f"{field} must be a list")
    result = []
    for item in value:
        text = str(item).strip()
        if not text:
            raise PlanValidationError(f"{field} entries must not be empty")
        result.append(text)
    return tuple(result)
