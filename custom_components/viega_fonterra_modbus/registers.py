"""Register definitions for the Viega Fonterra Smart Control integration.

This module keeps the Modbus register layout separated from the HA platform code
so it can be extended with real device mappings without mixing transport logic
and entity registration.
"""

from __future__ import annotations

import re


def decode_text_registers(values: list[int] | tuple[int, ...]) -> str:
    """Decode Viega text registers using big-endian bytes per register.

    Confirmed against real hardware: decoding with "little" (a previous
    version of this function) scrambled every string by swapping the two
    ASCII characters within each register - e.g. "Bad" came back as "aBd"
    and "Dachgeschoss" as "aDhcegcsohss". Do not reintroduce "little" here.
    """
    raw = b"".join((int(value) & 0xFFFF).to_bytes(2, "big") for value in values)
    return raw.decode("ascii", errors="replace").rstrip("\x00 ")

HOLDING_REGISTER_BASE = 40000
INPUT_REGISTER_BASE = 30000


def pdu_address(manual_address: int) -> int:
    """Convert a one-based Modicon-style manual address to a Modbus PDU address.

    Holding registers (4xxxx) are relative to 40000 and input registers
    (3xxxx) are relative to 30000. This is confirmed by the device manual's
    own worked wire examples (`Fonterra Smart Control-de-DE.pdf`, pages
    94-95): manual address 40001 ("Betriebsmodus") is sent on the wire as
    PDU `0001`, manual 40053 as PDU `0035` (53 decimal), and manual 30250
    ("Aktor 1 Stellung") as PDU `00FA` (250 decimal) - i.e. the last four
    digits of the manual address *are* the PDU address, with no further `-1`.
    A previous version of this function subtracted 40001/30001 (the more
    common Modicon convention of treating x0001 as PDU 0), which matched
    neither the manual's own examples nor real hardware and made every
    register in this module off by exactly one from the device's actual
    map - do not reintroduce that offset.
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
    """Return the manual input-register addresses for an actuator (1 through 12).

    `room_id` (manual base+2) is documented in the device manual as "Aktor N
    Raum ID", an int16 in range 1-12 reporting which room this actuator is
    currently assigned to. This is the device's own source of truth for
    actor-to-room association and is used by `RoomMappingDiscovery` to build
    the room mapping automatically instead of relying only on manually
    entered configuration.
    """
    if not 1 <= actor_number <= 12:
        raise ValueError("actor_number must be between 1 and 12")
    base = 30250 + (actor_number - 1) * 3
    return {
        "position": pdu_address(base),
        "return_temperature": pdu_address(base + 1),
        "room_id": pdu_address(base + 2),
    }


def room_name_register(room_number: int) -> tuple[int, int]:
    """Return `(address, length)` for a room's name text register.

    Manual addresses 30074/30086/.../30206 hold each room's 24-character
    name as 12 string registers (device manual page 90), spaced 12 registers
    apart to match the 24-character/12-register field width.
    """
    if not 1 <= room_number <= 12:
        raise ValueError("room_number must be between 1 and 12")
    base = 30074 + (room_number - 1) * 12
    return pdu_address(base), 12


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


# Base-unit and room error/warning codes from the device manual's
# "Fehlercodes" table (`Fonterra Smart Control-de-DE.pdf`, page 94). Codes
# 3-10 are reported on the base-unit error register (manual 30024); codes
# 21/22/24 are reported per-room (manual 30051/30053/.../30073). `0` is
# shared and means no error on either register.
BASE_UNIT_ERROR_CODES: dict[int, str] = {
    0: "No error",
    3: "Base unit: at least one room thermostat is no longer connected",
    4: "Base unit: fault on the actuator bus",
    5: "Base unit: fault at the flow-temperature sensor",
    6: "Base unit: fault at the return-temperature sensor",
    7: "Base unit: no further room thermostats can be registered",
    9: "Base unit: replace the backup battery",
    10: "Base unit warning: risk of condensation - flow temperature too low",
    21: "Room: no connection to the room thermostat",
    22: "Room warning: room thermostat battery is weak",
    24: "Room warning: connection to the room thermostat is weak",
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
