"""Changes are shown at once, sent once stable, and confirmed (spec.md 16c),
tested with a real Home Assistant: entities are not polled, so Home
Assistant does not refresh their state after a service call by itself."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.viega_fonterra_modbus.climate import ViegaRoomClimateEntity
from custom_components.viega_fonterra_modbus.const import DOMAIN, NUMERIC_SEND_DELAY
from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError
from custom_components.viega_fonterra_modbus.registers import room_registers
from tests.test_setup_lifecycle import FakeClient, _entry, fake_device  # noqa: F401

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")
CLIMATE = "climate.fonterra_wohnzimmer"
NUMBER = "number.fonterra_wohnzimmer_power_level"
TARGET = room_registers(1)["target_temperature"]
LEVEL = room_registers(1)["power_level"]


def _module(holding: dict[int, int], writes: list, delay_reads: int = 0):
    """Patch FakeClient into a module that keeps written holding registers;
    with `delay_reads`, it reports the old value for that many reads after
    each write, like the real base unit."""
    delayed: dict[int, list] = {}

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
        writes.append((address, value))
        if delay_reads:
            delayed[address] = [value, delay_reads]
        else:
            holding[address] = value

    return read_holding_registers, write_register


@pytest.fixture
def device(monkeypatch, fake_device):
    holding = {TARGET: 200, LEVEL: 3, 1: 1, 2: 0}
    writes: list = []
    read, write = _module(holding, writes)
    monkeypatch.setattr(FakeClient, "read_holding_registers", read)
    monkeypatch.setattr(FakeClient, "write_register", write)
    return SimpleNamespace(holding=holding, writes=writes)


async def _setup(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _wait(hass, seconds: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def _set_temperature(hass, value: float) -> None:
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": CLIMATE, "temperature": value}, blocking=True
    )


def _target(hass) -> float:
    return hass.states.get(CLIMATE).attributes["temperature"]


# --- Shown at once, sent once stable ---------------------------------------


async def test_new_target_is_shown_at_once_and_sent_after_five_seconds(hass, device):
    await _setup(hass)
    assert _target(hass) == 20.0

    await _set_temperature(hass, 21.5)

    assert _target(hass) == 21.5  # shown without any polling cycle
    assert device.writes == []  # not sent yet

    await _wait(hass, NUMERIC_SEND_DELAY + 1)

    assert device.writes == [(TARGET, 215)]
    assert _target(hass) == 21.5


async def test_quick_clicks_are_sent_once_with_the_final_value(hass, device):
    """Each "+" starts from the current state, like the button-card example;
    three clicks add up and only the result reaches the module."""
    await _setup(hass)

    for _ in range(3):
        await _set_temperature(hass, _target(hass) + 0.5)

    assert _target(hass) == 21.5
    assert device.writes == []

    await _wait(hass, NUMERIC_SEND_DELAY + 1)

    assert device.writes == [(TARGET, 215)]


async def test_every_change_restarts_the_wait(hass, device, freezer):
    await _setup(hass)

    async def advance(seconds: float) -> None:  # real clock moves forward
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    await _set_temperature(hass, 20.5)
    await advance(3)
    await _set_temperature(hass, 21.0)
    await advance(3)  # 6 s after the first click, 3 s after the second
    assert device.writes == []

    await advance(3)
    assert device.writes == [(TARGET, 210)]


async def test_polling_does_not_overwrite_a_waiting_value(hass, device):
    entry = await _setup(hass)
    await _set_temperature(hass, 22.5)

    await hass.data[DOMAIN][entry.entry_id]["polling"].async_refresh()
    await hass.async_block_till_done()

    assert _target(hass) == 22.5  # the device still reports 20.0


async def test_mode_and_preset_are_sent_immediately_power_level_when_stable(hass, device):
    await _setup(hass)

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": CLIMATE, "hvac_mode": "off"}, blocking=True
    )
    assert hass.states.get(CLIMATE).state == "off"
    assert device.holding[1] == 0

    await hass.services.async_call("climate", "turn_on", {"entity_id": CLIMATE}, blocking=True)
    assert hass.states.get(CLIMATE).state == "heat"

    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": CLIMATE, "preset_mode": "setback"}, blocking=True
    )
    assert hass.states.get(CLIMATE).attributes["preset_mode"] == "setback"
    assert device.holding[2] == 2

    await hass.services.async_call(
        "number", "set_value", {"entity_id": NUMBER, "value": 7}, blocking=True
    )
    assert hass.states.get(NUMBER).state == "7"
    assert device.holding[LEVEL] == 3

    await _wait(hass, NUMERIC_SEND_DELAY + 1)
    assert device.holding[LEVEL] == 7


async def test_invalid_value_is_rejected_at_once(hass, device):
    from homeassistant.exceptions import ServiceValidationError

    await _setup(hass)

    with pytest.raises(ServiceValidationError):
        await _set_temperature(hass, 40.0)

    assert _target(hass) == 20.0
    await _wait(hass, NUMERIC_SEND_DELAY + 1)
    assert device.writes == []


async def test_failed_send_returns_to_the_previous_value(hass, device, monkeypatch, caplog):
    await _setup(hass)

    async def failing_write(self, address, value):
        raise ModbusClientError("Modbus write timeout after 5s")

    monkeypatch.setattr(FakeClient, "write_register", failing_write)
    await _set_temperature(hass, 21.0)
    await _set_temperature(hass, 21.5)
    assert _target(hass) == 21.5

    with caplog.at_level(logging.WARNING):
        await _wait(hass, NUMERIC_SEND_DELAY + 1)

    assert _target(hass) == 20.0
    assert "sending target_temperature failed" in caplog.text


async def test_a_waiting_value_is_sent_when_the_module_is_unloaded(hass, device):
    entry = await _setup(hass)
    await _set_temperature(hass, 23.0)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert device.writes == [(TARGET, 230)]


# --- Confirmation (grace period for a slow device) -------------------------


async def test_value_is_confirmed_by_the_next_cycle(hass, device):
    entry = await _setup(hass)
    await _set_temperature(hass, 22.0)
    await _wait(hass, NUMERIC_SEND_DELAY + 1)

    await hass.data[DOMAIN][entry.entry_id]["polling"].async_refresh()
    await hass.async_block_till_done()

    assert _target(hass) == 22.0
    entity = hass.data["climate"].get_entity(CLIMATE)
    assert entity._pending_writes == {}


async def test_delayed_device_does_not_flicker_back(hass, monkeypatch, fake_device):
    """Reported: the new target appeared, jumped back to the old one, and
    only later showed the new one again."""
    holding = {TARGET: 200, LEVEL: 3, 1: 1, 2: 0}
    writes: list = []
    read, write = _module(holding, writes, delay_reads=2)
    monkeypatch.setattr(FakeClient, "read_holding_registers", read)
    monkeypatch.setattr(FakeClient, "write_register", write)
    entry = await _setup(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]["polling"]

    await _set_temperature(hass, 22.0)
    await _wait(hass, NUMERIC_SEND_DELAY + 1)
    seen = [_target(hass)]
    for _ in range(3):  # the device still reports 20.0 twice, then 22.0
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        seen.append(_target(hass))

    assert seen == [22.0, 22.0, 22.0, 22.0]
    assert holding[TARGET] == 220
    entity = hass.data["climate"].get_entity(CLIMATE)
    assert entity._pending_writes == {}
    assert entity.last_error_message == ""


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
