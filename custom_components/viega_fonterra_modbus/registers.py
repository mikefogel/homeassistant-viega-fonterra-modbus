"""Register definitions for the Viega Fonterra Smart Control integration.

This module keeps the Modbus register layout separated from the HA platform code
so it can be extended with real device mappings without mixing transport logic
and entity registration.
"""

from __future__ import annotations

BASE_REGISTER_OFFSET = 1


def pdu_address(manual_address: int) -> int:
    """Convert a one-based manual register address to a Modbus PDU address."""
    return manual_address - BASE_REGISTER_OFFSET


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

REGISTER_DEFINITIONS: dict[str, dict[str, int | str | None]] = {
    "temperature_flow": {"address": 1000, "name": "Flow temperature", "unit": "°C"},
    "temperature_return": {"address": 1001, "name": "Return temperature", "unit": "°C"},
    "temperature_room": {"address": 1002, "name": "Room temperature", "unit": "°C"},
    "system_pressure": {"address": 1010, "name": "System pressure", "unit": "bar"},
    "pump_state": {"address": 1020, "name": "Pump state", "unit": None},
}
