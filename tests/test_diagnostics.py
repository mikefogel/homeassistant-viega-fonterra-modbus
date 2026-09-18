"""Tests for the Home Assistant diagnostics export.

Exercises `async_get_config_entry_diagnostics`, which Home Assistant's
built-in diagnostics platform discovers by module/function name convention
(like config_flow.py) and exposes as "Download diagnostics" - so a user can
check their unit identity and resolved room/actuator register mapping
without reading debug logs.
"""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _hass(entry_data: dict) -> SimpleNamespace:
    return SimpleNamespace(data={DOMAIN: {"entry_1": entry_data}})


def test_diagnostics_includes_unit_identity_and_redacts_the_host():
    hass = _hass(
        {
            "device_name": "Fonterra",
            "host": "192.168.0.188",
            "port": 502,
            "polling_interval": 30,
            "modbus_timeout": 5,
            "identity": {
                "wlan_serial_number": "1710200090",
                "base_unit_serial_number": "1504240002",
                "base_unit_name": "Haus A, 1 OG",
            },
            "rooms": {},
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert result["unit"] == {
        "device_name": "Fonterra",
        "host": "**REDACTED**",
        "port": 502,
        "polling_interval": 30,
        "modbus_timeout": 5,
        "wlan_module_serial_number": "1710200090",
        "base_unit_serial_number": "1504240002",
        "base_unit_name": "Haus A, 1 OG",
    }
    assert result["rooms"] == []


def test_diagnostics_lists_each_room_with_its_resolved_registers():
    hass = _hass(
        {
            "rooms": {
                "room_1": {
                    "name": "Wohnzimmer",
                    "room_number": 1,
                    "actor": 1,
                    "sensor": 1,
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert result["rooms"] == [
        {
            "room_id": "room_1",
            "room_number": 1,
            "name": "Wohnzimmer",
            "registers": {
                "current_temperature": 50,
                "target_temperature": 51,
                "power_level": 50,
                "error_code": 51,
            },
            "actuators": [
                {
                    "actuator_id": 1,
                    "registers": {
                        "position": 250,
                        "return_temperature": 251,
                        "room_id_register": 252,
                    },
                }
            ],
        }
    ]


def test_diagnostics_lists_every_actuator_in_a_multi_actor_room():
    """spec.md 4: a room may map to more than one actuator; every one of
    them must show up, not just the primary."""
    hass = _hass(
        {"rooms": {"room_2": {"name": "Bad", "room_number": 2, "actor": [2, 3]}}}
    )
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    actuator_ids = [a["actuator_id"] for a in result["rooms"][0]["actuators"]]
    assert actuator_ids == [2, 3]


def test_diagnostics_resolves_room_number_from_room_id_when_not_explicit():
    """spec.md 5b: a room without an explicit room_number falls back to the
    trailing digits of its room_id."""
    hass = _hass({"rooms": {"room_3": {"name": "Küche", "actor": 3}}})
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert result["rooms"][0]["room_number"] == 3
    assert result["rooms"][0]["registers"]["current_temperature"] == 54


def test_diagnostics_skips_non_dict_room_entries():
    hass = _hass({"rooms": {"room_1": "not a dict"}})
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert result["rooms"] == []


def test_diagnostics_handles_a_module_with_no_data_yet():
    """A module that has not finished setup must still produce a (mostly
    empty) diagnostics payload rather than raising."""
    hass = SimpleNamespace(data={DOMAIN: {}})
    entry = SimpleNamespace(entry_id="entry_1")

    result = asyncio.run(async_get_config_entry_diagnostics(hass, entry))

    assert result["rooms"] == []
    assert result["unit"]["device_name"] is None
