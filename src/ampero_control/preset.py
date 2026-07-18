import math
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
DEFAULT_EFFECT_CHAIN_COUNT = 2
DEFAULT_INPUT_SOURCE_COUNT = 7
DEFAULT_INPUT_SOURCE_PARAMETER_COUNT = 4
DEFAULT_NODE_PARAMETER_COUNT = 10


def parse_current_preset(
    data: bytes,
    catalog: EffectCatalog,
    *,
    current_scene: int,
    include_parameters: bool,
) -> dict:
    if len(data) < 12:
        raise PresetFormatError("current-preset payload is too short")
    preset_payload_header = _signed(data[0:4])
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
    routing = _parse_routing(blocks.get(6, b""))
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

    result = {
        "device": "Ampero II Stomp",
        "preset_payload_header": preset_payload_header,
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
    if routing:
        result["routing"] = routing
    return result


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


def _parse_routing(data: bytes) -> dict:
    source_bytes = DEFAULT_EFFECT_CHAIN_COUNT * 2
    source_parameter_count = (
        DEFAULT_EFFECT_CHAIN_COUNT
        * DEFAULT_INPUT_SOURCE_COUNT
        * DEFAULT_INPUT_SOURCE_PARAMETER_COUNT
    )
    source_parameter_bytes = source_parameter_count * 4
    node_parameter_bytes = DEFAULT_NODE_PARAMETER_COUNT * 4
    required = (
        source_bytes * 2
        + source_parameter_bytes * 2
        + 4
        + node_parameter_bytes * 2
    )
    if not data:
        return {}
    if len(data) < required:
        raise PresetFormatError(
            f"routing block is {len(data)} bytes; expected at least {required}"
        )
    offset = 0
    input_sources = list(
        struct.unpack_from(f"<{DEFAULT_EFFECT_CHAIN_COUNT}h", data, offset)
    )
    offset += source_bytes
    output_sources = list(
        struct.unpack_from(f"<{DEFAULT_EFFECT_CHAIN_COUNT}h", data, offset)
    )
    offset += source_bytes + source_parameter_bytes * 2
    split_node_address, mix_node_address, split_mode, mix_mode = struct.unpack_from(
        "<bbbb", data, offset
    )
    offset += 4
    split_parameters = list(
        struct.unpack_from(f"<{DEFAULT_NODE_PARAMETER_COUNT}f", data, offset)
    )
    offset += node_parameter_bytes
    mix_parameters = list(
        struct.unpack_from(f"<{DEFAULT_NODE_PARAMETER_COUNT}f", data, offset)
    )
    template_name, template_id = _routing_template_from_nodes(
        split_node_address, mix_node_address
    )
    return {
        "template": template_name,
        "template_id": template_id,
        "effect_chain_count": DEFAULT_EFFECT_CHAIN_COUNT,
        "input_sources": input_sources,
        "output_sources": output_sources,
        "split_node_address": split_node_address,
        "mix_node_address": mix_node_address,
        "split_mode": split_mode,
        "mix_mode": mix_mode,
        "split_parameters": [_finite_or_none(value) for value in split_parameters],
        "mix_parameters": [_finite_or_none(value) for value in mix_parameters],
    }


def parse_routing_template_response(data: bytes) -> dict:
    if len(data) < 16:
        raise PresetFormatError("routing template response is shorter than 16 bytes")
    template_id = _signed(data[0:4])
    routing_data = data[16:]
    routing = (
        _parse_routing(routing_data)
        if len(routing_data) >= 540
        else _parse_compact_routing(routing_data)
    )
    routing["response_template_id"] = template_id
    return routing


def _parse_compact_routing(data: bytes) -> dict:
    source_bytes = DEFAULT_EFFECT_CHAIN_COUNT * 2
    selected_source_parameter_count = (
        DEFAULT_EFFECT_CHAIN_COUNT * DEFAULT_INPUT_SOURCE_PARAMETER_COUNT
    )
    selected_source_parameter_bytes = selected_source_parameter_count * 4
    node_parameter_bytes = DEFAULT_NODE_PARAMETER_COUNT * 4
    required = (
        source_bytes * 2
        + selected_source_parameter_bytes * 2
        + 4
        + node_parameter_bytes * 2
    )
    if len(data) < required:
        raise PresetFormatError(
            f"compact routing block is {len(data)} bytes; expected at least {required}"
        )
    offset = 0
    input_sources = list(
        struct.unpack_from(f"<{DEFAULT_EFFECT_CHAIN_COUNT}h", data, offset)
    )
    offset += source_bytes
    output_sources = list(
        struct.unpack_from(f"<{DEFAULT_EFFECT_CHAIN_COUNT}h", data, offset)
    )
    offset += source_bytes
    input_parameters = list(
        struct.unpack_from(f"<{selected_source_parameter_count}f", data, offset)
    )
    offset += selected_source_parameter_bytes
    output_parameters = list(
        struct.unpack_from(f"<{selected_source_parameter_count}f", data, offset)
    )
    offset += selected_source_parameter_bytes
    split_node_address, mix_node_address, split_mode, mix_mode = struct.unpack_from(
        "<bbbb", data, offset
    )
    offset += 4
    split_parameters = list(
        struct.unpack_from(f"<{DEFAULT_NODE_PARAMETER_COUNT}f", data, offset)
    )
    offset += node_parameter_bytes
    mix_parameters = list(
        struct.unpack_from(f"<{DEFAULT_NODE_PARAMETER_COUNT}f", data, offset)
    )
    template_name, topology_template_id = _routing_template_from_nodes(
        split_node_address, mix_node_address
    )
    return {
        "template": template_name,
        "template_id": topology_template_id,
        "effect_chain_count": DEFAULT_EFFECT_CHAIN_COUNT,
        "input_sources": input_sources,
        "output_sources": output_sources,
        "input_parameters": [_finite_or_none(value) for value in input_parameters],
        "output_parameters": [_finite_or_none(value) for value in output_parameters],
        "split_node_address": split_node_address,
        "mix_node_address": mix_node_address,
        "split_mode": split_mode,
        "mix_mode": mix_mode,
        "split_parameters": [_finite_or_none(value) for value in split_parameters],
        "mix_parameters": [_finite_or_none(value) for value in mix_parameters],
    }


def _routing_template_from_nodes(
    split_node_address: int, mix_node_address: int
) -> tuple[str, Optional[int]]:
    templates = {
        (-1, -1): ("Parallel", 0),
        (0, 6): ("Split->Mix", 1),
        (-1, 6): ("A/B->Y", 2),
        (0, -1): ("Y->A/B", 3),
        (6, -1): ("Serial", 4),
    }
    return templates.get(
        (split_node_address, mix_node_address), ("Custom", None)
    )


def _finite_or_none(value: float) -> Optional[float]:
    return value if math.isfinite(value) else None


def _signed(data: bytes) -> int:
    return int.from_bytes(data, byteorder="little", signed=True)


def _text(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
