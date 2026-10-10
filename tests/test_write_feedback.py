"""A change is shown right away and read back soon (spec.md 16c), with a
real Home Assistant: entities are not polled, so Home Assistant does not
refresh their state after a service call by itself."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.viega_fonterra_modbus.climate import ViegaRoomClimateEntity
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.registers import room_registers
from tests.test_setup_lifecycle import FakeClient, _entry, fake_device  # noqa: F401

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
CLIMATE = "climate.fonterra_wohnzimmer"
NUMBER = "number.fonterra_wohnzimmer_power_level"
TARGET = room_registers(1)["target_temperature"]
LEVEL = room_registers(1)["power_level"]


@pytest.fixture
def device(monkeypatch, fake_device):
    """Fake module that keeps written holding registers."""
    holding = {TARGET: 200, LEVEL: 3, 1: 1, 2: 0}

    async def read_holding_registers(self, address, count=1):
        return [holding.get(address + i, 0) for i in range(count)]

    async def write_register(self, address, value):
        holding[address] = value

    monkeypatch.setattr(FakeClient, "read_holding_registers", read_holding_registers)
    monkeypatch.setattr(FakeClient, "write_register", write_register)
    return holding


async def _setup(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_new_target_temperature_is_shown_immediately(hass, device):
    await _setup(hass)
    assert hass.states.get(CLIMATE).attributes["temperature"] == 20.0

    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 21.5}, blocking=True
    )

    # No polling cycle has run in between: the state comes from the write.
    assert hass.states.get(CLIMATE).attributes["temperature"] == 21.5
    assert device[TARGET] == 215


async def test_two_quick_increments_add_up(hass, device):
    """Each "+" is computed from the current state, like the button-card
    example does; the second one must start from the first one's result."""
    await _setup(hass)

    for _ in range(2):
        current = hass.states.get(CLIMATE).attributes["temperature"]
        await hass.services.async_call(
            "climate", "set_temperature",
            {"entity_id": CLIMATE, "temperature": current + 0.5}, blocking=True,
        )

    assert hass.states.get(CLIMATE).attributes["temperature"] == 21.0
    assert device[TARGET] == 210


async def test_mode_preset_and_power_level_are_shown_immediately(hass, device):
    await _setup(hass)

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": CLIMATE, "hvac_mode": "off"}, blocking=True
    )
    assert hass.states.get(CLIMATE).state == "off"

    await hass.services.async_call(
        "climate", "turn_on", {"entity_id": CLIMATE}, blocking=True
    )
    assert hass.states.get(CLIMATE).state == "heat"

    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": CLIMATE, "preset_mode": "setback"}, blocking=True
    )
    assert hass.states.get(CLIMATE).attributes["preset_mode"] == "setback"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": NUMBER, "value": 7}, blocking=True
    )
    assert hass.states.get(NUMBER).state == "7"
    assert device[LEVEL] == 7


async def test_value_is_confirmed_by_the_next_cycle(hass, device):
    await _setup(hass)
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 22.0}, blocking=True
    )
    await hass.data[DOMAIN][next(iter(hass.data[DOMAIN]))]["polling"].async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE).attributes["temperature"] == 22.0


def test_older_data_does_not_flicker_the_written_value_back():
    """A cycle that is not newer than the write still carries the old
    target; the entity keeps the written value until a newer cycle."""

    class _Shared:
        generation = 5

        def __init__(self):
            self.values = {}

        async def read(self, hass, entry_id, bank, address, count=1):
            return [self.values.get(address, 0)]

    shared = _Shared()
    entity = ViegaRoomClimateEntity("entry_1", "room_1", "Wohnzimmer", 21.0, 20.0, {"actor": 1})
    shared.values[entity._registers["target_temperature"]] = 200  # old 20.0 °C

    class _Client:
        async def write_register(self, address, value):
            pass

        async def read_holding_registers(self, address, count=1):
            raise AssertionError("must be served from the polling cycle")

        read_input_registers = read_holding_registers

    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _Client(), "polling": shared}}}
    )
    asyncio.run(entity.async_set_temperature(temperature=22.5))

    asyncio.run(entity.async_update())  # same generation: old data
    assert entity.target_temperature == 22.5

    shared.generation = 6
    shared.values[entity._registers["target_temperature"]] = 225
    asyncio.run(entity.async_update())  # newer cycle confirms
    assert entity.target_temperature == 22.5
    assert entity._pending_writes == {}


# --- Device applies writes with a delay (spec.md 16c grace period) ---------


@pytest.fixture
def slow_device(monkeypatch, fake_device):
    """Fake module that keeps reporting the old holding value for the first
    reads after a write, like the real base unit does."""
    holding = {TARGET: 200, LEVEL: 3, 1: 1, 2: 0}
    delayed: dict[int, list] = {}  # address -> [new value, reads left]

    async def read_holding_registers(self, address, count=1):
        result = []
        for a in range(address, address + count):
            if a in delayed:
                new, left = delayed[a]
                if left <= 0:
                    holding[a] = new
                    del delayed[a]
                else:
                    delayed[a][1] = left - 1
            result.append(holding.get(a, 0))
        return result

    async def write_register(self, address, value):
        delayed[address] = [value, 2]  # old value for the next two reads

    monkeypatch.setattr(FakeClient, "read_holding_registers", read_holding_registers)
    monkeypatch.setattr(FakeClient, "write_register", write_register)
    return holding


async def test_delayed_device_does_not_flicker_back(hass, slow_device):
    """Reported: the new target appeared, jumped back to the old one, and
    only later showed the new one again."""
    await _setup(hass)
    coordinator = hass.data[DOMAIN][next(iter(hass.data[DOMAIN]))]["polling"]

    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": 22.0}, blocking=True
    )
    await hass.async_block_till_done()
    seen = [hass.states.get(CLIMATE).attributes["temperature"]]
    for _ in range(3):  # device still reports 20.0 twice, then 22.0
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        seen.append(hass.states.get(CLIMATE).attributes["temperature"])

    assert seen == [22.0, 22.0, 22.0, 22.0]
    assert slow_device[TARGET] == 220
    entity = hass.data["climate"].get_entity(CLIMATE)
    assert entity._pending_writes == {}
    assert entity.last_error_message == ""
