"""Which registers report -99 (spec.md 16b "Invalid registers")."""

from __future__ import annotations


import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.coordinator import ViegaDataCoordinator
from custom_components.viega_fonterra_modbus.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.viega_fonterra_modbus.registers import (
    actor_registers,
    register_labels,
    room_registers,
)
from tests.test_setup_lifecycle import FakeClient, _entry, fake_device  # noqa: F401

ROOMS = {
    "room_1": {"name": "Bad", "room_number": 1, "actor": 1},
    "room_3": {"name": "Gast", "room_number": 3, "actor": [4, 5]},
}
GAST_TEMPERATURE = room_registers(3)["current_temperature"]
ACTUATOR_5_RETURN = actor_registers(5)["return_temperature"]


class _Client:
    def __init__(self, invalid: set[int]):
        self.invalid = invalid

    async def read_input_registers(self, address, count=1):
        return [-99 if address + i in self.invalid else 0 for i in range(count)]

    async def read_holding_registers(self, address, count=1):
        return [0] * count


def _coordinator(hass, client) -> ViegaDataCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = ViegaDataCoordinator(hass, entry, client, 30)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"rooms": ROOMS, "polling": coordinator}
    return coordinator


def test_register_labels_name_every_topology_register():
    labels = register_labels(ROOMS)

    assert labels[("input", GAST_TEMPERATURE)] == ("room_3.current_temperature", "Gast")
    assert labels[("holding", room_registers(1)["target_temperature"])] == (
        "room_1.target_temperature", "Bad")
    assert labels[("input", ACTUATOR_5_RETURN)] == ("actuator_5.return_temperature", "Gast")
    assert labels[("input", 25)] == ("base_unit.flow_temperature", None)


async def test_cycle_tracks_which_registers_are_invalid(hass):
    client = _Client({GAST_TEMPERATURE, ACTUATOR_5_RETURN})
    coordinator = _coordinator(hass, client)

    for _ in range(3):
        await coordinator.async_refresh()

    assert coordinator.invalid_register_ids() == [
        "actuator_5.return_temperature", "room_3.current_temperature"]
    report = {row["register"]: row for row in coordinator.invalid_registers_report()}
    assert report["room_3.current_temperature"] == {
        "register": "room_3.current_temperature", "room": "Gast", "bank": "input",
        "address": GAST_TEMPERATURE, "manual_address": 30000 + GAST_TEMPERATURE,
        "count": 1, "invalid_cycles": 3, "invalid_now": True,
    }


async def test_a_register_that_recovers_leaves_the_current_set_but_keeps_its_history(hass):
    client = _Client({GAST_TEMPERATURE})
    coordinator = _coordinator(hass, client)
    await coordinator.async_refresh()

    client.invalid = set()
    await coordinator.async_refresh()

    assert coordinator.invalid_register_ids() == []
    (row,) = coordinator.invalid_registers_report()
    assert row["invalid_cycles"] == 1 and row["invalid_now"] is False


async def test_failed_reads_are_not_counted_as_invalid(hass):
    class _Failing(_Client):
        async def read_input_registers(self, address, count=1):
            raise OSError("unreachable")

    coordinator = _coordinator(hass, _Failing(set()))
    await coordinator.async_refresh()

    assert coordinator.invalid_register_ids() == []


async def test_unknown_registers_are_named_by_bank_and_address(hass):
    coordinator = _coordinator(hass, _Client({999}))
    with pytest.raises(Exception):
        await coordinator.read(hass, coordinator.entry_id, "input", 999, 1)
    await coordinator.async_refresh()

    assert coordinator.invalid_register_ids() == ["input_999"]


# --- End to end with a real Home Assistant ---------------------------------


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_sensor_and_diagnostics_show_the_invalid_register(hass, fake_device, monkeypatch):
    bad_temperature = room_registers(1)["current_temperature"]

    async def read_input_registers(self, address, count=1):
        return [-99 if address + i == bad_temperature else 0 for i in range(count)]

    monkeypatch.setattr(FakeClient, "read_input_registers", read_input_registers)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.fonterra_invalid_registers")
    assert state.state == "1"
    assert state.attributes["invalid_registers"] == ["room_1.current_temperature"]

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    (row,) = diagnostics["extended"]["invalid_registers"]
    assert row["register"] == "room_1.current_temperature"
    assert row["room"] == "Wohnzimmer"
    assert row["manual_address"] == 30000 + bad_temperature


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_sensor_shows_zero_when_everything_is_valid(hass, fake_device):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.fonterra_invalid_registers")
    assert state.state == "0"
    assert state.attributes["invalid_registers"] == []
