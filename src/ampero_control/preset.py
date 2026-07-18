import struct
from typing import Optional

from .catalog import EffectCatalog
from .errors import PresetFormatError


DEFAULT_SLOT_PARAMETER_COUNT = 25
DEFAULT_NAME_SIZE = 17
DEFAULT_AUTHOR_SIZE = 20
DEFAULT_INFO_SIZE = 50
DEFAULT_TYPE_SIZE = 10
DEFAULT_SCENE_NAME_SIZE = 8


def parse_current_preset(
    data: bytes,
    catalog: EffectCatalog,
    *,
    current_scene: int,
    include_parameters: bool,
) -> dict:
    if len(data) < 12:
        raise PresetFormatError("current-preset payload is too short")
    preset_index = _signed(data[0:4])
    blocks = _parse_blocks(data[4:])
    define = blocks.get(0)
    effect_data = blocks.get(4)
    scene_data = blocks.get(5)
    if define is None or effect_data is None:
        raise PresetFormatError("current preset is missing define or effect blocks")
    if len(define) < 10:
        raise PresetFormatError("preset define block is shorter than ten bytes")

    dimensions = {
        "fs_num": define[0],
        "fs_comb_num": define[1],
        "slot_num": define[2],
        "exp_mode_num": define[3],
        "control_num": define[4],
        "scene_num": define[5],
        "exp_num": define[6],
        "external_exp_num": define[7],
        "fs_midi_num": define[8],
        "patch_midi_num": define[9],
        "slot_parameter_num": DEFAULT_SLOT_PARAMETER_COUNT,
    }
    slot_num = dimensions["slot_num"]
    scene_num = dimensions["scene_num"]
    if slot_num <= 0 or scene_num <= 0:
        raise PresetFormatError(f"invalid preset dimensions: {dimensions}")

    info = _parse_info(blocks.get(1, b""))
    effect = _parse_effect(effect_data, slot_num)
    scenes = _parse_scenes(scene_data, scene_num, slot_num) if scene_data else {}
    selected_scene = min(max(current_scene, 0), scene_num - 1)
    states = scenes.get("states", [])
    parameters = scenes.get("parameters", [])

    positions = {
        slot_id: position
        for position, slot_id in enumerate(effect["sequence"])
        if 0 <= slot_id < slot_num
    }
    slots = []
    for slot_id in range(slot_num):
        category_id = effect["modules"][slot_id]
        model_code = effect["models"][slot_id]
        empty = category_id < 0 or model_code < 0
        state_index = selected_scene * slot_num + slot_id
        enabled = bool(states[state_index]) if state_index < len(states) else False
        slot = {
            "slot": slot_id,
            "position": positions.get(slot_id),
            "empty": empty,
            "category_id": category_id,
            "model_code": model_code,
            "enabled": enabled,
        }
        effect_spec = catalog.find_by_code(category_id, model_code)
        if effect_spec:
            slot["effect"] = {
                "name": effect_spec.name,
                "category": effect_spec.category_name,
            }
            if include_parameters:
                base = (
                    selected_scene * slot_num * DEFAULT_SLOT_PARAMETER_COUNT
                    + slot_id * DEFAULT_SLOT_PARAMETER_COUNT
                )
                slot["parameters"] = [
                    {
                        "name": parameter.name,
                        "parameter_id": parameter.parameter_id,
                        "value": parameters[base + parameter.parameter_id],
                        "minimum": parameter.minimum,
                        "maximum": parameter.maximum,
                    }
                    for parameter in effect_spec.parameters
                    if base + parameter.parameter_id < len(parameters)
                ]
        elif not empty:
            slot["catalog_match"] = False
        slots.append(slot)

    return {
        "device": "Ampero II Stomp",
        "preset_index": preset_index,
        "preset_name": info.get("name", ""),
        "preset_author": info.get("author", ""),
        "preset_info": info.get("info", ""),
        "preset_type": info.get("type", ""),
        "current_scene": selected_scene,
        "scene_names": scenes.get("names", []),
        "slot_count": slot_num,
        "parameters_included": include_parameters,
        "dimensions": dimensions,
        "slots": slots,
    }


def _parse_blocks(data: bytes) -> dict[int, bytes]:
    blocks = {}
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise PresetFormatError(f"truncated TLV header at offset {offset}")
        block_type = _signed(data[offset : offset + 4])
        block_size = _signed(data[offset + 4 : offset + 8])
        if block_size < 0 or offset + 8 + block_size > len(data):
            raise PresetFormatError(
                f"invalid TLV block size {block_size} for type {block_type}"
            )
        blocks[block_type] = data[offset + 8 : offset + 8 + block_size]
        offset += 8 + block_size
    return blocks


def _parse_info(data: bytes) -> dict:
    required = (
        4
        + DEFAULT_NAME_SIZE
        + DEFAULT_AUTHOR_SIZE
        + DEFAULT_INFO_SIZE
        + DEFAULT_TYPE_SIZE
    )
    if len(data) < required:
        return {}
    offset = 4
    name = _text(data[offset : offset + DEFAULT_NAME_SIZE])
    offset += DEFAULT_NAME_SIZE
    author = _text(data[offset : offset + DEFAULT_AUTHOR_SIZE])
    offset += DEFAULT_AUTHOR_SIZE
    info = _text(data[offset : offset + DEFAULT_INFO_SIZE])
    offset += DEFAULT_INFO_SIZE
    preset_type = _text(data[offset : offset + DEFAULT_TYPE_SIZE])
    return {"name": name, "author": author, "info": info, "type": preset_type}


def _parse_effect(data: bytes, slot_num: int) -> dict:
    required = slot_num + slot_num + slot_num * 4
    if len(data) < required:
        raise PresetFormatError(
            f"effect block is {len(data)} bytes; expected at least {required}"
        )
    offset = 0
    sequence = [_signed(data[offset + index : offset + index + 1]) for index in range(slot_num)]
    offset += slot_num
    modules = [_signed(data[offset + index : offset + index + 1]) for index in range(slot_num)]
    offset += slot_num
    models = [
        _signed(data[offset + index * 4 : offset + (index + 1) * 4])
        for index in range(slot_num)
    ]
    return {"sequence": sequence, "modules": modules, "models": models}


def _parse_scenes(data: bytes, scene_num: int, slot_num: int) -> dict:
    parameter_count = scene_num * slot_num * DEFAULT_SLOT_PARAMETER_COUNT
    parameter_bytes = parameter_count * 4
    state_count = scene_num * slot_num
    minimum = parameter_bytes + state_count + scene_num * 5
    if len(data) < minimum:
        raise PresetFormatError(
            f"scene block is {len(data)} bytes; expected at least {minimum}"
        )
    offset = 0
    parameters = list(struct.unpack_from(f"<{parameter_count}f", data, offset))
    offset += parameter_bytes
    states = [
        _signed(data[offset + index : offset + index + 1])
        for index in range(state_count)
    ]
    offset += state_count
    patch_volumes = [
        _signed(data[offset + index * 2 : offset + (index + 1) * 2])
        for index in range(scene_num)
    ]
    offset += scene_num * 2
    tempos = [
        _signed(data[offset + index * 2 : offset + (index + 1) * 2])
        for index in range(scene_num)
    ]
    offset += scene_num * 2
    empty_flags = list(data[offset : offset + scene_num])
    offset += scene_num
    follow_size = 2 + slot_num + slot_num * DEFAULT_SLOT_PARAMETER_COUNT
    offset += follow_size
    names = []
    for _ in range(scene_num):
        names.append(_text(data[offset : offset + DEFAULT_SCENE_NAME_SIZE]))
        offset += DEFAULT_SCENE_NAME_SIZE
    return {
        "parameters": parameters,
        "states": states,
        "patch_volumes": patch_volumes,
        "tempos": tempos,
        "empty_flags": empty_flags,
        "names": names,
    }


def _signed(data: bytes) -> int:
    return int.from_bytes(data, byteorder="little", signed=True)


def _text(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
