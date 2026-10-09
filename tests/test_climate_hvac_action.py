"""Climate presentation: hvac_action (spec.md 5a.2), presets only while
heating (5a.1a), and turn on/off (5a.1b)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACAction
from homeassistant.exceptions import ServiceValidationError

from custom_components.viega_fonterra_modbus.climate import ViegaRoomClimateEntity
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.registers import actor_registers


class _DeviceClient:
    """Answers reads from `values` (default 0) and records writes."""

    def __init__(self, values: dict[int, int] | None = None):
        self.values = dict(values or {})
        self.writes: list[tuple[int, int]] = []

    async def write_register(self, address, value):
        self.writes.append((address, value))
        self.values[address] = value

    async def read_holding_registers(self, address, count=1):
        return [self.values.get(address, 0)]

    async def read_input_registers(self, address, count=1):
        return [self.values.get(address, 0)]


class _SharedPolling:
    def __init__(self, client):
        self._client = client
        self.generation = 0

    async def read(self, hass, entry_id, bank, address, count=1):
        reader = (
            self._client.read_holding_registers
            if bank == "holding"
            else self._client.read_input_registers
        )
        return await reader(address, count)


def _entity(actors=(3, 4)) -> tuple[ViegaRoomClimateEntity, _DeviceClient]:
    entity = ViegaRoomClimateEntity(
        "entry_1",
        "room_1",
        "Wohnzimmer",
        21.5,
        22.0,
        {"name": "Wohnzimmer", "actor": list(actors)},
    )
    client = _DeviceClient()
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": _SharedPolling(client)}}}
    )
    return entity, client


def _position(actor: int) -> int:
    return actor_registers(actor)["position"]


def _poll(entity, client, *, mode: int, positions: dict[int, int]) -> None:
    client.values[entity._registers["operating_mode"]] = mode
    for actor, position in positions.items():
        client.values[_position(actor)] = position
    asyncio.run(entity.async_update())


# --- hvac_action (spec.md 5a.2) -------------------------------------------


@pytest.mark.parametrize(
    ("mode", "positions", "expected"),
    [
        (0, {3: 1, 4: 1}, HVACAction.OFF),
        (1, {3: 0, 4: 0}, HVACAction.IDLE),
        (1, {3: 1, 4: 0}, HVACAction.HEATING),
        (2, {3: 0, 4: 0}, HVACAction.IDLE),
        (2, {3: 0, 4: 1}, HVACAction.COOLING),
    ],
)
def test_hvac_action_follows_mode_and_actuators(mode, positions, expected):
    entity, client = _entity()
    _poll(entity, client, mode=mode, positions=positions)

    assert entity.hvac_action == expected


def test_any_actuator_of_the_room_counts_not_only_the_first():
    """Only the second circuit is open: the room is still heating."""
    entity, client = _entity()
    _poll(entity, client, mode=1, positions={3: 0, 4: 1})

    assert entity.hvac_action == HVACAction.HEATING
    assert entity._actuator_position == 0  # the primary actuator's attribute is unchanged


def test_hvac_action_is_none_before_any_position_was_read():
    entity, _ = _entity()

    assert entity.hvac_action is None


def test_hvac_action_is_none_for_an_unknown_operating_mode():
    entity, client = _entity()
    _poll(entity, client, mode=7, positions={3: 1, 4: 1})

    assert entity.hvac_action is None


def test_failed_or_sentinel_position_reads_keep_the_last_position():
    entity, client = _entity()
    _poll(entity, client, mode=1, positions={3: 1, 4: 0})
    for _ in range(3):
        _poll(entity, client, mode=1, positions={3: -99, 4: -99})

    assert entity.hvac_action == HVACAction.HEATING


def test_hvac_action_is_not_debounced():
    entity, client = _entity()
    _poll(entity, client, mode=1, positions={3: 0, 4: 0})
    assert entity.hvac_action == HVACAction.IDLE

    _poll(entity, client, mode=1, positions={3: 1, 4: 0})
    assert entity.hvac_action == HVACAction.HEATING


def test_restart_restores_all_actuator_positions():
    entity, client = _entity()
    _poll(entity, client, mode=2, positions={3: 0, 4: 1})
    attributes = dict(entity.extra_state_attributes)
    assert attributes["actuator_positions"] == {"3": 0, "4": 1}

    restored, _ = _entity()

    async def _last_state():
        return SimpleNamespace(state="cool", attributes=attributes)

    restored.async_get_last_state = _last_state
    asyncio.run(restored.async_added_to_hass())

    assert restored.hvac_action == HVACAction.COOLING


def test_restore_from_an_older_state_uses_the_single_actuator_position():
    """States saved before actuator_positions existed only carry the primary
    actuator's position; it is still used after the upgrade."""
    restored, _ = _entity(actors=(3,))

    async def _last_state():
        return SimpleNamespace(state="heat", attributes={"actuator_position": 1})

    restored.async_get_last_state = _last_state
    asyncio.run(restored.async_added_to_hass())

    assert restored.hvac_action == HVACAction.HEATING


# --- Presets only while heating (spec.md 5a.1a) ---------------------------


def test_preset_control_is_only_offered_in_heating_mode():
    entity, client = _entity()

    _poll(entity, client, mode=1, positions={})
    assert entity.supported_features & ClimateEntityFeature.PRESET_MODE

    for mode in (0, 2):
        _poll(entity, client, mode=mode, positions={})
        assert not entity.supported_features & ClimateEntityFeature.PRESET_MODE
        assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE


def test_preset_change_outside_heating_mode_is_rejected_without_a_write():
    entity, client = _entity()
    _poll(entity, client, mode=2, positions={})

    with pytest.raises(ServiceValidationError) as excinfo:
        asyncio.run(entity.async_set_preset_mode("profile"))

    assert excinfo.value.translation_key == "preset_requires_heating"
    assert client.writes == []


def test_switching_mode_keeps_the_preset_and_does_not_write_it():
    entity, client = _entity()
    _poll(entity, client, mode=1, positions={})
    asyncio.run(entity.async_set_preset_mode("setback"))
    client.writes.clear()

    asyncio.run(entity.async_set_hvac_mode("cool"))
    asyncio.run(entity.async_set_hvac_mode("heat"))

    assert entity.preset_mode == "setback"
    assert [address for address, _ in client.writes] == [
        entity._registers["operating_mode"],
        entity._registers["operating_mode"],
    ]


# --- Turn on / off (spec.md 5a.1b) ----------------------------------------


def test_turn_on_and_off_are_supported():
    entity, _ = _entity()

    assert entity.supported_features & ClimateEntityFeature.TURN_ON
    assert entity.supported_features & ClimateEntityFeature.TURN_OFF


def test_turn_off_writes_standby_and_turn_on_restores_the_last_mode():
    entity, client = _entity()
    _poll(entity, client, mode=2, positions={})  # device reports cooling
    operating_mode = entity._registers["operating_mode"]

    asyncio.run(entity.async_turn_off())
    assert entity.hvac_mode == "off"

    asyncio.run(entity.async_turn_on())
    assert entity.hvac_mode == "cool"
    assert client.writes == [(operating_mode, 0), (operating_mode, 2)]


def test_turn_on_defaults_to_heat():
    entity, client = _entity()
    _poll(entity, client, mode=0, positions={})

    asyncio.run(entity.async_turn_on())

    assert entity.hvac_mode == "heat"


def test_turn_on_and_off_do_not_write_when_already_in_that_state():
    entity, client = _entity()
    _poll(entity, client, mode=1, positions={})
    asyncio.run(entity.async_turn_on())

    _poll(entity, client, mode=0, positions={})
    asyncio.run(entity.async_turn_off())

    assert client.writes == []


def test_last_active_mode_survives_a_restart():
    entity, client = _entity()
    _poll(entity, client, mode=2, positions={})
    asyncio.run(entity.async_turn_off())
    attributes = dict(entity.extra_state_attributes)

    restored, restored_client = _entity()

    async def _last_state():
        return SimpleNamespace(state="off", attributes=attributes)

    restored.async_get_last_state = _last_state
    asyncio.run(restored.async_added_to_hass())
    asyncio.run(restored.async_turn_on())

    assert restored.hvac_mode == "cool"
    assert restored_client.writes == [(restored._registers["operating_mode"], 2)]
