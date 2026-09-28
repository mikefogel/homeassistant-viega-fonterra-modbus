"""Optional aggregate diagnostic view across every configured Viega
Fonterra module (spec.md 16g).

Built entirely from data already held in `hass.data[DOMAIN]` - the same
constraint `diagnostics.py` already follows - so calling this never issues
an extra Modbus read. One module's failure while being summarized is
isolated to that module's own entry in the result; it never aborts the
summary for any other module.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .registers import room_actor_numbers


def async_multi_module_overview(hass: HomeAssistant) -> dict[str, Any]:
    """Return a per-module summary for every currently loaded config entry.

    Two different modules' rooms are never merged even when they share a
    display name: every room entry in the result carries its own
    `entry_id`, and every module entry carries its own `entry_id` and
    `device_name` - the source config entry and device identity are never
    dropped in favor of a deduplicated/aggregated view.
    """
    modules: list[dict[str, Any]] = []
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        try:
            modules.append(_module_summary(entry_id, entry_data))
        except Exception as err:  # a malformed/partial entry must not break the rest
            modules.append(
                {
                    "entry_id": entry_id,
                    "device_name": (
                        entry_data.get("device_name") if isinstance(entry_data, dict) else None
                    ),
                    "error": str(err),
                }
            )
    return {"modules": modules}


def _module_summary(entry_id: str, entry_data: dict[str, Any]) -> dict[str, Any]:
    client = entry_data.get("client")
    rooms = entry_data.get("rooms", {})
    dict_rooms = {
        room_id: room_config
        for room_id, room_config in rooms.items()
        if isinstance(room_config, dict)
    }

    last_success_time = getattr(client, "last_success_time", None)
    consecutive_failures = getattr(client, "consecutive_failures", None)
    error_code = entry_data.get("base_unit_error_code")

    return {
        "entry_id": entry_id,
        "device_name": entry_data.get("device_name"),
        "reachable": bool(getattr(client, "_connected", False)),
        "has_base_unit_error": None if error_code is None else error_code != 0,
        "stale_or_failed": last_success_time is None or bool(consecutive_failures),
        "room_count": len(dict_rooms),
        "actuator_count": sum(
            len(room_actor_numbers(room_config)) for room_config in dict_rooms.values()
        ),
        "rooms": [
            {"entry_id": entry_id, "room_id": room_id, "name": room_config.get("name", room_id)}
            for room_id, room_config in dict_rooms.items()
        ],
    }
