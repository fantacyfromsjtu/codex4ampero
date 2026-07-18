import struct


def build_current_preset_fixture(
    *, split_node_address: int = 2, mix_node_address: int = 7
) -> bytes:
    slot_num = 2
    scene_num = 1
    parameter_num = 25

    define = bytes([3, 2, slot_num, 2, 3, scene_num, 1, 1, 3, 6])
    info = (
        _int32(2)
        + _text("Fixture", 17)
        + _text("Codex", 20)
        + _text("Synthetic preset", 50)
        + _text("Test", 10)
    )
    effect = (
        bytes([0, 1])
        + bytes([4, 0xFF])
        + _int32(117440600)
        + _int32(-1)
    )
    parameters = [0.0] * (scene_num * slot_num * parameter_num)
    parameters[0] = 42.0
    scene = (
        struct.pack(f"<{len(parameters)}f", *parameters)
        + bytes([1, 0])
        + _int16(0)
        + _int16(120)
        + bytes([0])
        + bytes(2 + slot_num + slot_num * parameter_num)
        + _text("Scene 1", 8)
    )
    source_parameters = [0.0] * (2 * 7 * 4)
    routing = (
        struct.pack("<2h", 0, 1)
        + struct.pack("<2h", 0, 1)
        + struct.pack(f"<{len(source_parameters)}f", *source_parameters)
        + struct.pack(f"<{len(source_parameters)}f", *source_parameters)
        + struct.pack(
            "<bbbb", split_node_address, mix_node_address, 0, 0
        )
        + struct.pack("<10f", *([0.0] * 10))
        + struct.pack("<10f", *([0.0] * 10))
    )
    return (
        _int32(7)
        + _block(0, define)
        + _block(1, info)
        + _block(4, effect)
        + _block(5, scene)
        + _block(6, routing)
    )


def _block(block_type: int, payload: bytes) -> bytes:
    return _int32(block_type) + _int32(len(payload)) + payload


def _int16(value: int) -> bytes:
    return int(value).to_bytes(2, "little", signed=True)


def _int32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=True)


def _text(value: str, size: int) -> bytes:
    encoded = value.encode("utf-8")[: size - 1]
    return encoded + bytes(size - len(encoded))
