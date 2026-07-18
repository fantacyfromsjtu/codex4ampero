import re
from dataclasses import dataclass

from .errors import PlanValidationError


PATCHES_PER_BANK = 3
PATCH_LABEL_PATTERN = re.compile(r"^A(\d+)-([1-3])$", re.IGNORECASE)


@dataclass(frozen=True)
class PatchLocation:
    index: int
    bank: int
    patch: int

    @property
    def label(self) -> str:
        return f"A{self.bank:02d}-{self.patch}"


def patch_location_from_index(index: int) -> PatchLocation:
    if index < 0:
        raise PlanValidationError(f"patch index must be non-negative, got {index}")
    return PatchLocation(
        index=index,
        bank=index // PATCHES_PER_BANK,
        patch=index % PATCHES_PER_BANK + 1,
    )


def parse_patch_label(label: str) -> PatchLocation:
    normalized = str(label).strip().upper()
    match = PATCH_LABEL_PATTERN.fullmatch(normalized)
    if not match:
        raise PlanValidationError(
            f"target_patch must use Ampero II Stomp format A00-1, got {label!r}"
        )
    bank = int(match.group(1))
    patch = int(match.group(2))
    return PatchLocation(
        index=bank * PATCHES_PER_BANK + patch - 1,
        bank=bank,
        patch=patch,
    )
