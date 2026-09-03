"""Register definitions for the Viega Fonterra Smart Control integration.

This module keeps the Modbus register layout separated from the HA platform code
so it can be extended with real device mappings without mixing transport logic
and entity registration.
"""

from __future__ import annotations

import re


def decode_text_registers(values: list[int] | tuple[int, ...]) -> str:
    """Decode Viega text registers using little-endian bytes per register."""
    raw = b"".join((int(value) & 0xFFFF).to_bytes(2, "little") for value in values)
    return raw.decode("ascii", errors="replace").rstrip("\x00 ")

HOLDING_REGISTER_BASE = 40001
INPUT_REGISTER_BASE = 30001


def pdu_address(manual_address: int) -> int:
    """Convert a one-based Modicon-style manual address to a Modbus PDU address.

    Holding registers (4xxxx) are zero-based relative to 40001 and input
    registers (3xxxx) are zero-based relative to 30001, per the device
    manual's addressing convention (see spec.md 5b). Subtracting a flat `1`
    from the full five-digit address (the previous behavior of this
    function) produced PDU addresses tens of thousands too high and must
    not be reintroduced.
    """
    if 40001 <= manual_address <= 49999:
        return manual_address - HOLDING_REGISTER_BASE
    if 30001 <= manual_address <= 39999:
        return manual_address - INPUT_REGISTER_BASE
    raise ValueError(
        f"manual_address {manual_address} is outside the supported 3xxxx/4xxxx ranges"
    )


BASE_UNIT_REGISTERS = {
    "operating_mode": pdu_address(40001),
    "profile_mode": pdu_address(40002),
    "error_code": pdu_address(30024),
    "flow_temperature": pdu_address(30025),
    "wlan_serial_number": pdu_address(30001),
    "base_unit_serial_number": pdu_address(30006),
    "base_unit_name": pdu_address(30011),
}


def room_registers(room_number: int) -> dict[str, int]:
    """Return the manual register addresses for a room number (1 through 12)."""
    if not 1 <= room_number <= 12:
        raise ValueError("room_number must be between 1 and 12")
    input_base = 30050 + (room_number - 1) * 2
    holding_base = 40050 + (room_number - 1) * 2
    return {
        "current_temperature": pdu_address(input_base),
        "error_code": pdu_address(input_base + 1),
        "power_level": pdu_address(holding_base),
        "target_temperature": pdu_address(holding_base + 1),
    }


def actor_registers(actor_number: int) -> dict[str, int]:
    """Return the manual input-register addresses for an actuator (1 through 12)."""
    if not 1 <= actor_number <= 12:
        raise ValueError("actor_number must be between 1 and 12")
    base = 30250 + (actor_number - 1) * 3
    return {
        "position": pdu_address(base),
        "return_temperature": pdu_address(base + 1),
        "room_id": pdu_address(base + 2),
    }


_TRAILING_DIGITS = re.compile(r"(\d+)$")


def resolve_room_number(room_id: str, room_config: dict[str, object]) -> int:
    """Return the numeric room number used to resolve default registers.

    An explicit `room_number` in the room mapping always wins. Otherwise the
    trailing digits of the room id are used (e.g. "room_1" -> 1), so a room
    configured with only `name`/`actor`/`sensor` (see spec.md 4/6b) still
    resolves to a working set of default registers instead of silently
    ending up without a target-temperature register.
    """
    room_number = room_config.get("room_number")
    if room_number:
        return int(room_number)
    match = _TRAILING_DIGITS.search(str(room_id))
    return int(match.group(1)) if match else 0


# Known base-unit error codes. `0` is the documented no-error value (see
# spec.md 3a); additional codes should be added here as they are confirmed
# against the device manual rather than guessed.
BASE_UNIT_ERROR_CODES: dict[int, str] = {
    0: "No error",
}


def describe_error_code(code: int | None) -> str:
    """Return a human-readable description for a base-unit error code."""
    if code is None:
        return "Unknown"
    return BASE_UNIT_ERROR_CODES.get(code, f"Unknown error (code {code})")


REGISTER_DEFINITIONS: dict[str, dict[str, int | str | None]] = {
    "temperature_flow": {"address": 1000, "name": "Flow temperature", "unit": "°C"},
    "temperature_return": {"address": 1001, "name": "Return temperature", "unit": "°C"},
    "temperature_room": {"address": 1002, "name": "Room temperature", "unit": "°C"},
    "system_pressure": {"address": 1010, "name": "System pressure", "unit": "bar"},
    "pump_state": {"address": 1020, "name": "Pump state", "unit": None},
}
