"""Register definitions for the Viega Fonterra Smart Control integration.

This module keeps the Modbus register layout separated from the HA platform code
so it can be extended with real device mappings without mixing transport logic
and entity registration.
"""

from __future__ import annotations

REGISTER_DEFINITIONS: dict[str, dict[str, int | str | None]] = {
    "temperature_flow": {"address": 1000, "name": "Flow temperature", "unit": "°C"},
    "temperature_return": {"address": 1001, "name": "Return temperature", "unit": "°C"},
    "temperature_room": {"address": 1002, "name": "Room temperature", "unit": "°C"},
    "system_pressure": {"address": 1010, "name": "System pressure", "unit": "bar"},
    "pump_state": {"address": 1020, "name": "Pump state", "unit": None},
}
