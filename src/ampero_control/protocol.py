import struct
from dataclasses import dataclass
from typing import Iterable, Optional

from .constants import Command
from .errors import PlanValidationError


def pack_int(value: int, length: int, *, signed: bool = True) -> bytes:
    if length not in (1, 2, 4, 8):
        raise ValueError(f"unsupported integer length: {length}")
    return int(value).to_bytes(length, byteorder="little", signed=signed)


def unpack_int(data: bytes, *, signed: bool = True) -> int:
    return int.from_bytes(data, byteorder="little", signed=signed)


def pack_float(value: float) -> bytes:
    return struct.pack("<f", float(value))


def unpack_float(data: bytes) -> float:
    if len(data) != 4:
        raise ValueError("a device float must contain exactly four bytes")
    return struct.unpack("<f", data)[0]


def pack_float_array(values: Iterable[float]) -> bytes:
    return b"".join(pack_float(value) for value in values)


def encode_set_parameter(slot_id: int, parameter_id: int, value: float) -> bytes:
    return pack_int(slot_id, 2) + pack_int(parameter_id, 2) + pack_float(value)


def decode_parameter(data: bytes) -> tuple[int, int, float]:
    if len(data) < 8:
        raise ValueError("parameter response is shorter than eight bytes")
    return unpack_int(data[0:2]), unpack_int(data[2:4]), unpack_float(data[4:8])


def encode_set_model(
    slot_id: int, category_id: int, model_code: int, enabled: bool
) -> bytes:
    return (
        pack_int(slot_id, 1)
        + pack_int(category_id, 1)
        + pack_int(model_code, 4)
        + pack_int(1 if enabled else 0, 1)
    )


def decode_model(data: bytes) -> tuple[int, int, int, bool]:
    if len(data) < 7:
        raise ValueError("model response is shorter than seven bytes")
    return (
        unpack_int(data[0:1]),
        unpack_int(data[1:2]),
        unpack_int(data[2:6]),
        bool(unpack_int(data[6:7])),
    )


def encode_scene(scene_id: int) -> bytes:
    return pack_int(scene_id, 1)


def encode_routing_template(template_id: int) -> bytes:
    return pack_int(template_id, 4)


def encode_fixed_utf8(value: str, length: int) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > length:
        raise ValueError(
            f"UTF-8 value is {len(encoded)} bytes; maximum is {length} bytes"
        )
    return encoded + bytes(length - len(encoded))


def decode_zero_terminated_utf8(data: bytes) -> str:
    value = data.split(b"\x00", 1)[0]
    return value.decode("utf-8")


@dataclass(frozen=True)
class ReceivedMessage:
    address: int
    data: bytes
    flag: int
    received_at: float

    @property
    def command(self) -> Optional[Command]:
        try:
            return Command(self.address)
        except ValueError:
            return None


@dataclass(frozen=True)
class EncodedCommand:
    command: Command
    payload: bytes
    description: str

    def to_dict(self) -> dict:
        return {
            "command": self.command.name,
            "address": f"0x{int(self.command):08x}",
            "payload_hex": self.payload.hex(" "),
            "description": self.description,
        }


def ensure_finite(value: float, field: str) -> None:
    if value != value or value in (float("inf"), float("-inf")):
        raise PlanValidationError(f"{field} must be a finite number")
