import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .constants import Command
from .errors import PlanValidationError
from .patch_location import PatchLocation, parse_patch_label
from .protocol import EncodedCommand, encode_fixed_utf8, pack_int


PRESET_NAME_SIZE = 17
PRESET_NAME_MAX_LENGTH = PRESET_NAME_SIZE - 1
PRESET_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9~!@#%.&^*.,?_+\-'\"();:<=>\[\]\\`{}| $]+$"
)


@dataclass(frozen=True)
class PreparedPresetSave:
    source_journal: Path
    target_patch: PatchLocation
    preset_name: str
    command: EncodedCommand

    @property
    def confirmation_token(self) -> str:
        return f"SAVE:{self.target_patch.label}"

    def to_dict(self) -> dict:
        return build_preset_save_preview(
            self.target_patch,
            self.preset_name,
            source_journal=self.source_journal,
        )


def build_preset_save_preview(
    target_patch: PatchLocation,
    preset_name: str,
    source_journal: Optional[Path] = None,
) -> dict:
    normalized_name = validate_preset_name(preset_name)
    command = _build_preset_save_command(target_patch, normalized_name)
    result = {
        "journal_bound": source_journal is not None,
        "target_patch": {
            "label": target_patch.label,
            "index": target_patch.index,
            "bank": target_patch.bank,
            "patch": target_patch.patch,
        },
        "preset_name": normalized_name,
        "command": command.to_dict(),
        "confirmation_token": f"SAVE:{target_patch.label}",
        "irreversible": True,
        "rollback_supported": False,
        "warning": (
            "Saving overwrites the stored preset at the exact target and cannot be "
            "rolled back by the control layer."
        ),
    }
    if source_journal is not None:
        result["source_journal"] = str(source_journal.resolve())
    else:
        result["notice"] = (
            "This save preview will become journal-bound only after the tone plan "
            "applies successfully. No preset save is included in plan apply."
        )
    return result


def _build_preset_save_command(
    target_patch: PatchLocation, preset_name: str
) -> EncodedCommand:
    return EncodedCommand(
        command=Command.PRESET_SAVE,
        payload=encode_preset_save(target_patch, preset_name),
        description=(
            f"Save the verified live buffer to {target_patch.label} as "
            f"{preset_name!r}"
        ),
    )


def validate_preset_name(name: str) -> str:
    normalized = str(name).strip()
    if not normalized:
        raise PlanValidationError("preset name must not be empty")
    if len(normalized) > PRESET_NAME_MAX_LENGTH:
        raise PlanValidationError(
            f"preset name must contain at most {PRESET_NAME_MAX_LENGTH} characters"
        )
    if not PRESET_NAME_PATTERN.fullmatch(normalized):
        raise PlanValidationError(
            "preset name contains unsupported characters; use the same printable "
            "ASCII subset accepted by the official editor"
        )
    return normalized


def encode_preset_save(target_patch: PatchLocation, preset_name: str) -> bytes:
    normalized_name = validate_preset_name(preset_name)
    return pack_int(target_patch.index, 4) + encode_fixed_utf8(
        normalized_name, PRESET_NAME_SIZE
    )


def prepare_preset_save(journal_path: Path, preset_name: str) -> PreparedPresetSave:
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal.get("status") != "applied":
        raise PlanValidationError(
            "preset save requires a successful apply journal with status 'applied'"
        )
    applied = journal.get("applied")
    if not isinstance(applied, list) or not applied:
        raise PlanValidationError("apply journal does not contain verified commands")
    if any(entry.get("readback_verified") is not True for entry in applied):
        raise PlanValidationError(
            "apply journal contains commands without verified device readback"
        )
    target_value = journal.get("target_patch")
    if not isinstance(target_value, dict) or not target_value.get("label"):
        raise PlanValidationError(
            "apply journal does not contain an exact target patch"
        )
    target_patch = parse_patch_label(target_value["label"])
    if target_value.get("index") != target_patch.index:
        raise PlanValidationError("apply journal target patch index is inconsistent")
    current_patch = journal.get("current_patch")
    if not isinstance(current_patch, dict) or current_patch.get("index") != target_patch.index:
        raise PlanValidationError(
            "apply journal does not verify that the target patch was current"
        )
    normalized_name = validate_preset_name(preset_name)
    return PreparedPresetSave(
        source_journal=journal_path.resolve(),
        target_patch=target_patch,
        preset_name=normalized_name,
        command=_build_preset_save_command(target_patch, normalized_name),
    )
