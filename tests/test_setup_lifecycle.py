"""Setup, reload, retry and removal through Home Assistant's real config-entry
manager, using pytest-homeassistant-custom-component (spec.md 12a).

test_init.py covers `async_setup_entry`/`async_unload_entry` at unit level
with stand-ins for `hass`; this file checks the same lifecycle the way Home
Assistant actually drives it: entry state transitions, entities and devices
in the registries, and that every connection opened is closed again.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

ROOMS = {
    "room_1": {"name": "Wohnzimmer", "room_number": 1, "sensor": 1, "actor": [1, 2]},
    "room_2": {"name": "Bad", "room_number": 2, "sensor": 2, "actor": 3},
}


class FakeClient:
    """Stand-in for `ViegaModbusClient`: every register reads 0; every
    instance is recorded so a test can check it was disconnected."""

    instances: list["FakeClient"] = []
    ERROR_SENTINEL = -99
    connect_error: Exception | None = None

    def __init__(self, host, port=502, timeout=5, reconnect_backoff_max=30):
        self.host = host
        self.port = port
        self.connected = False
        self.disconnect_calls = 0
        FakeClient.instances.append(self)

    async def connect(self):
        if FakeClient.connect_error is not None:
            raise FakeClient.connect_error
        self.connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False

    async def read_holding_registers(self, address, count=1):
        return [0] * count

    async def read_input_registers(self, address, count=1):
        return [0] * count

    async def write_register(self, address, value):
        return None


@pytest.fixture
def fake_device():
    FakeClient.instances = []
    FakeClient.connect_error = None
    with patch(
        "custom_components.viega_fonterra_modbus.ViegaModbusClient", FakeClient
    ), patch(
        "custom_components.viega_fonterra_modbus.RoomMappingDiscovery.discover_from_device",
        new=AsyncMock(return_value=ROOMS),
    ):
        yield FakeClient


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Fonterra",
        unique_id="192.168.1.50:502",
        data={
            "host": "192.168.1.50",
            "port": 502,
            "device_name": "Fonterra",
            "polling_interval": 30,
            "modbus_timeout": 5,
        },
    )


def _entity_ids(hass, entry) -> set[str]:
    return {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }


async def test_setup_creates_a_climate_entity_per_room(hass, fake_device):
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    unique_ids = _entity_ids(hass, entry)
    assert f"{entry.entry_id}_room_1_thermostat" in unique_ids
    assert f"{entry.entry_id}_room_2_thermostat" in unique_ids


async def test_reload_closes_the_old_connection_and_keeps_entities_stable(hass, fake_device):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = _entity_ids(hass, entry)
    first_client = fake_device.instances[-1]

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert first_client.disconnect_calls == 1
    second_client = fake_device.instances[-1]
    assert second_client is not first_client and second_client.connected
    # Same unique IDs after the reload: no duplicate entities (spec.md 5a).
    assert _entity_ids(hass, entry) == before


async def test_connection_failure_during_setup_lets_home_assistant_retry(hass, fake_device):
    fake_device.connect_error = ModbusClientError("Connection timeout after 5s")
    entry = _entry()
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]


async def test_removing_the_entry_disconnects_and_cleans_up(hass, fake_device):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = fake_device.instances[-1]

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert client.disconnect_calls == 1
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)


async def test_removal_succeeds_even_when_disconnect_fails(hass, fake_device):
    """spec.md 6a/13: a module must always be deletable, also when its
    connection is already broken."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fake_device.instances[-1].disconnect = AsyncMock(side_effect=OSError("broken pipe"))

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(entry.entry_id) is None


async def test_one_module_reload_does_not_touch_another_module(hass, fake_device):
    first = _entry()
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Keller",
        unique_id="192.168.1.51:502",
        data={**first.data, "host": "192.168.1.51", "device_name": "Keller"},
    )
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    # Setting up the first entry loads the integration, which sets up every
    # entry of the domain.
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.LOADED
    second_client = next(c for c in fake_device.instances if c.host == "192.168.1.51")

    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()

    assert second.state is ConfigEntryState.LOADED
    assert second_client.disconnect_calls == 0
    assert hass.data[DOMAIN][second.entry_id]["client"] is second_client


async def test_setup_connects_once_and_does_not_reload_itself(hass, fake_device):
    """Persisting the discovered rooms into the entry's options must not
    trigger the update listener into a second, immediate setup (a second
    discovery run and a second connection)."""
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.options["rooms"] == ROOMS
    assert len(fake_device.instances) == 1
    assert fake_device.instances[0].disconnect_calls == 0


async def test_a_user_change_to_the_entry_still_reloads_it(hass, fake_device):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "polling_interval": 60}
    )
    await hass.async_block_till_done()

    assert len(fake_device.instances) == 2
    assert fake_device.instances[0].disconnect_calls == 1
    assert hass.data[DOMAIN][entry.entry_id]["polling_interval"] == 60


async def test_entities_are_updated_by_the_coordinator_not_polled(hass, fake_device, monkeypatch):
    """spec.md 16i: one polling cycle feeds every entity; Home Assistant no
    longer polls them one by one."""
    from custom_components.viega_fonterra_modbus.registers import BASE_UNIT_REGISTERS

    values = {BASE_UNIT_REGISTERS["flow_temperature"]: 352}

    async def read_input_registers(self, address, count=1):
        return [values.get(address + i, 0) for i in range(count)]

    monkeypatch.setattr(FakeClient, "read_input_registers", read_input_registers)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.fonterra_flow_temperature").state == "35.2"

    values[BASE_UNIT_REGISTERS["flow_temperature"]] = 400
    await hass.data[DOMAIN][entry.entry_id]["polling"].async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.fonterra_flow_temperature").state == "40.0"
    platform_entities = [
        entity
        for registry in hass.data[DOMAIN][entry.entry_id]["platform_entities"].values()
        for entities in registry.by_room.values()
        for entity in entities
    ]
    assert platform_entities
    assert all(entity.should_poll is False for entity in platform_entities)
