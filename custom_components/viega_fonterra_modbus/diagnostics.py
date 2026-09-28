"""Home Assistant diagnostics export for a Viega Fonterra module.

Home Assistant auto-discovers this module by name/function signature (the
same convention as `config_flow.py`) and exposes it as the "Download
diagnostics" action on the integration entry, entirely through Home
Assistant's own built-in diagnostics platform - no extra entity, dashboard,
or manual export code is needed on our side.

The exported structure mirrors what a user would need to cross-check their
installation against the device manual/RegisterMap.md: the base unit's
identity, and every discovered room with its actuator(s) and the exact
register addresses each entity reads/writes.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .registers import (
    actor_registers,
    known_addresses_for_topology,
    resolve_room_number,
    room_actor_numbers,
    room_registers,
)

# The host is a local LAN address, not a secret, but diagnostics dumps are
# routinely pasted into public GitHub issues - redact it like any other
# network-identifying detail per Home Assistant's own diagnostics guidance.
TO_REDACT = {"host"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the module's identity and resolved room/actuator topology."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    identity = entry_data.get("identity", {})
    rooms = entry_data.get("rooms", {})

    return async_redact_data(
        {
            "unit": {
                "device_name": entry_data.get("device_name"),
                "host": entry_data.get("host"),
                "port": entry_data.get("port"),
                "polling_interval": entry_data.get("polling_interval"),
                "modbus_timeout": entry_data.get("modbus_timeout"),
                "wlan_module_serial_number": identity.get("wlan_serial_number"),
                "base_unit_serial_number": identity.get("base_unit_serial_number"),
                "base_unit_name": identity.get("base_unit_name"),
            },
            "rooms": [
                _room_diagnostics(room_id, room_config)
                for room_id, room_config in rooms.items()
                if isinstance(room_config, dict)
            ],
            "extended": _extended_diagnostics(entry_data),
        },
        TO_REDACT,
    )


def _extended_diagnostics(entry_data: dict[str, Any]) -> dict[str, Any]:
    """Optional, bounded extended snapshot (spec.md 16e): connection-health
    counters, a bounded history of recent Modbus exception codes, the
    documented register addresses a normal polling cycle actually reads for
    the resolved topology, and the most recent rediscovery's topology diff.

    Built entirely from data already held in `hass.data[DOMAIN][entry_id]`,
    like the rest of this module - no extra Modbus read. Every field is a
    small scalar or a fixed-size collection (`recent_exception_codes` is
    itself bounded on the client, see `modbus_handler.py`), so the overall
    size is fixed regardless of how long the module has been running; no
    raw TX/RX frame or other unbounded data ever goes into it. There is no
    documented register reporting a firmware/software version, so none is
    fabricated here - spec.md 16e only allows one "when reported by a
    documented device source".
    """
    client = entry_data.get("client")
    holding, input_ = known_addresses_for_topology(entry_data.get("rooms", {}))

    return {
        "connection_health": {
            "last_success_time": _isoformat(getattr(client, "last_success_time", None)),
            "last_failure_time": _isoformat(getattr(client, "last_failure_time", None)),
            "consecutive_failures": getattr(client, "consecutive_failures", None),
            "invalid_value_count": getattr(client, "invalid_value_count", None),
            "last_exception_code": getattr(client, "last_exception_code", None),
            "recent_exception_codes": list(getattr(client, "recent_exception_codes", None) or []),
            "last_success_duration": getattr(client, "last_success_duration", None),
        },
        "resolved_addresses": {
            "holding": sorted(holding),
            "input": sorted(input_),
        },
        "last_rediscovery": entry_data.get("last_rediscovery"),
    }


def _isoformat(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _room_diagnostics(room_id: str, room_config: dict[str, object]) -> dict[str, Any]:
    """Return one room's name, id, and resolved actuator/register mapping."""
    room_number = resolve_room_number(room_id, room_config)
    registers = room_registers(room_number) if room_number else {}

    return {
        "room_id": room_id,
        "room_number": room_number or None,
        "name": room_config.get("name", room_id),
        "registers": {
            "current_temperature": registers.get("current_temperature"),
            "target_temperature": room_config.get(
                "target_temperature_register", registers.get("target_temperature")
            ),
            "power_level": room_config.get(
                "power_level_register", registers.get("power_level")
            ),
            "error_code": registers.get("error_code"),
        },
        "actuators": [
            _actuator_diagnostics(actuator_number)
            for actuator_number in room_actor_numbers(room_config)
        ],
    }


def _actuator_diagnostics(actuator_number: int) -> dict[str, Any]:
    """Return one actuator's id and its resolved register addresses."""
    try:
        registers = actor_registers(actuator_number)
    except ValueError:
        registers = {}
    return {
        "actuator_id": actuator_number,
        "registers": {
            "position": registers.get("position"),
            "return_temperature": registers.get("return_temperature"),
            "room_id_register": registers.get("room_id"),
        },
    }
