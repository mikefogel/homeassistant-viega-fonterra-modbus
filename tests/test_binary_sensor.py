"""Tests for the base-unit error indicator (spec.md 13: a non-zero
base-unit error code activates the base-unit error indicator)."""

import asyncio
import itertools
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import binary_sensor as binary_sensor_module
from custom_components.viega_fonterra_modbus.binary_sensor import (
    ActuatorStatistics,
    ViegaActuatorPositionBinarySensor,
    ViegaBaseUnitErrorBinarySensor,
    ViegaCirculationPumpBinarySensor,
    _actor_position_sensors,
    _all_actuator_position_addresses,
    async_setup_entry,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient


class _FakeClient:
    def __init__(self, values=None, raises=False):
        self._values = values
        self._raises = raises

    async def read_input_registers(self, address, count=1):
        if self._raises:
            raise RuntimeError("device offline")
        return self._values


def _entity_with_client(client) -> ViegaBaseUnitErrorBinarySensor:
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})
    return entity


def test_base_unit_error_name_is_localized_via_translation_key():
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")

    assert not hasattr(entity, "_attr_name")
    assert entity._attr_translation_key == "base_unit_error"


def test_actuator_position_name_is_localized_via_translation_key():
    entity = ViegaActuatorPositionBinarySensor("entry_1", "room_1", 1, "Wohnzimmer", 250)

    assert not hasattr(entity, "_attr_name")
    assert entity._attr_translation_key == "actuator_position"
    assert entity._attr_translation_placeholders == {"room": "Wohnzimmer", "actor": "1"}


def test_stays_off_and_does_not_crash_on_communication_failure():
    entity = _entity_with_client(_FakeClient(raises=True))

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is False


def test_keeps_last_state_on_error_sentinel():
    """-99 must not be misread as a real (non-zero, thus "error") code."""
    entity = _entity_with_client(_FakeClient(values=[ViegaModbusClient.ERROR_SENTINEL]))
    entity._attr_is_on = True  # simulate a previously known state

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is True


def test_turns_on_for_a_nonzero_error_code():
    entity = _entity_with_client(_FakeClient(values=[7]))

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is True


def test_mirrors_the_raw_error_code_onto_entry_data_for_the_multi_module_overview():
    """spec.md 16g: the overview reports "modules with base-unit errors"
    without an extra Modbus read - it reads this mirrored value instead."""
    entity = _entity_with_client(_FakeClient(values=[7]))

    asyncio.run(entity.async_update())

    assert entity.hass.data[DOMAIN]["entry_1"]["base_unit_error_code"] == 7


def test_turns_off_for_error_code_zero():
    entity = _entity_with_client(_FakeClient(values=[7]))
    asyncio.run(entity.async_update())
    assert entity._attr_is_on is True

    entity.hass.data[DOMAIN]["entry_1"]["client"] = _FakeClient(values=[0])
    entity._polling_gate._next_due = 0.0  # force the next update to actually read

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is False


def test_setup_entry_creates_a_single_indicator_per_module():
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {}}})
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert len(added) == 1
    assert added[0]._attr_unique_id == "entry_1_base_unit_error"


def test_setup_entry_adds_a_position_sensor_per_actuator():
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {
                    "rooms": {"room_1": {"name": "Wohnzimmer", "actor": [1, 2]}}
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    unique_ids = {getattr(e, "_attr_unique_id", None) for e in added}
    assert unique_ids == {
        "entry_1_base_unit_error",
        "entry_1_room_1_actor1_position",
        "entry_1_room_1_actor2_position",
        "entry_1_circulation_pump",
    }


def test_actuator_position_sensor_is_on_when_open():
    """Manual page 91: Aktor Stellung is 0=geschlossen, 1=offen."""
    entity = ViegaActuatorPositionBinarySensor("entry_1", "room_1", 1, "name", 250)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeClient(values=[1])}}}
    )

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is True


def test_actuator_position_sensor_is_off_when_closed():
    entity = ViegaActuatorPositionBinarySensor("entry_1", "room_1", 1, "name", 250)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeClient(values=[0])}}}
    )

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is False


def test_actuator_position_sensors_built_for_every_actor_in_the_room():
    entry = SimpleNamespace(entry_id="entry_1")
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": [1, 2, 3]}}

    sensors = _actor_position_sensors(entry, rooms)

    assert {s._attr_unique_id for s in sensors} == {
        "entry_1_room_1_actor1_position",
        "entry_1_room_1_actor2_position",
        "entry_1_room_1_actor3_position",
    }


# --- Circulation pump indicator (spec.md 5c) ---------------------------


class _MultiActuatorClient:
    """A fake Modbus client returning a distinct, mutable value per address,
    so a test can change one actuator's reading between async_update() calls
    without affecting the others."""

    def __init__(self, values_by_address: dict[int, int]):
        self.values_by_address = dict(values_by_address)

    async def read_input_registers(self, address, count=1):
        if address not in self.values_by_address:
            raise RuntimeError(f"no fixture value for address {address}")
        return [self.values_by_address[address]]


def _pump_entity(actuator_addresses: dict[int, int], client) -> ViegaCirculationPumpBinarySensor:
    entity = ViegaCirculationPumpBinarySensor("entry_1", actuator_addresses)
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})
    return entity


def _tick(entity) -> None:
    """Force the polling gate open and run one update cycle."""
    entity._polling_gate._next_due = 0.0
    asyncio.run(entity.async_update())


def test_pump_name_is_localized_via_translation_key():
    entity = ViegaCirculationPumpBinarySensor("entry_1", {1: 250})

    assert not hasattr(entity, "_attr_name")
    assert entity._attr_translation_key == "circulation_pump"


def test_pump_is_unknown_before_any_actuator_has_settled():
    client = _MultiActuatorClient({250: 1})
    entity = _pump_entity({1: 250}, client)

    _tick(entity)
    assert entity._attr_is_on is None
    _tick(entity)
    assert entity._attr_is_on is None  # only 2 consecutive reads so far


def test_pump_turns_on_after_three_consecutive_open_reads():
    client = _MultiActuatorClient({250: 1})
    entity = _pump_entity({1: 250}, client)

    _tick(entity)
    _tick(entity)
    _tick(entity)

    assert entity._attr_is_on is True


def test_a_differing_read_resets_the_debounce_counter():
    client = _MultiActuatorClient({250: 1})
    entity = _pump_entity({1: 250}, client)

    _tick(entity)  # open (1)
    _tick(entity)  # open (2)
    client.values_by_address[250] = 0
    _tick(entity)  # closed (reset, 1) - not yet settled, still None
    assert entity._attr_is_on is None

    client.values_by_address[250] = 1
    _tick(entity)  # open (reset, 1)
    _tick(entity)  # open (2)
    assert entity._attr_is_on is None
    _tick(entity)  # open (3) -> settles

    assert entity._attr_is_on is True


def test_pump_stays_on_while_one_actuator_is_still_unsettled():
    """spec.md 5c: on as soon as ANY used actuator is confirmed open, even
    if another actuator hasn't finished debouncing yet."""
    client = _MultiActuatorClient({250: 1, 253: 0})
    entity = _pump_entity({1: 250, 2: 253}, client)

    for _ in range(3):
        _tick(entity)  # settles actuator 1 as open

    assert entity._attr_is_on is True


def test_pump_turns_off_once_every_settled_actuator_is_closed():
    client = _MultiActuatorClient({250: 1, 253: 1})
    entity = _pump_entity({1: 250, 2: 253}, client)
    for _ in range(3):
        _tick(entity)
    assert entity._attr_is_on is True

    client.values_by_address = {250: 0, 253: 0}
    for _ in range(3):
        _tick(entity)

    assert entity._attr_is_on is False


def test_error_sentinel_reads_do_not_advance_or_reset_the_counter():
    client = _MultiActuatorClient({250: 1})
    entity = _pump_entity({1: 250}, client)

    _tick(entity)  # open (1)
    _tick(entity)  # open (2)
    client.values_by_address[250] = ViegaModbusClient.ERROR_SENTINEL
    _tick(entity)  # ignored, counter stays at 2
    assert entity._attr_is_on is None

    client.values_by_address[250] = 1
    _tick(entity)  # open (3) -> settles, as if the sentinel read never happened

    assert entity._attr_is_on is True


def test_all_actuator_position_addresses_dedupes_and_resolves_registers():
    rooms = {
        "room_1": {"name": "Wohnzimmer", "actor": [1, 2]},
        "room_2": {"name": "Bad", "actor": 3},
        "room_3": "not a dict",
    }

    addresses = _all_actuator_position_addresses(rooms)

    assert addresses == {1: 250, 2: 253, 3: 256}


def test_setup_entry_creates_the_pump_entity_when_actuators_exist():
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {"rooms": {"room_1": {"name": "Wohnzimmer", "actor": 1}}}
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    pumps = [e for e in added if isinstance(e, ViegaCirculationPumpBinarySensor)]
    assert len(pumps) == 1
    assert pumps[0]._attr_unique_id == "entry_1_circulation_pump"


def test_setup_entry_skips_the_pump_entity_without_any_actuators():
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"rooms": {}}}})
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert not any(isinstance(e, ViegaCirculationPumpBinarySensor) for e in added)


# --- Derived actuator statistics (spec.md 16f) ---------------------------


def test_statistics_stay_unavailable_until_any_actuator_settles():
    stats = ActuatorStatistics()

    stats.update({1: None, 2: None})

    assert stats.open_actuator_count is None
    assert stats.open_transition_count == 0
    assert stats.last_transition_time is None


def test_statistics_count_currently_open_actuators_once_settled():
    stats = ActuatorStatistics()

    stats.update({1: 1, 2: 0, 3: 1})

    assert stats.open_actuator_count == 2


def test_statistics_count_the_first_settle_as_a_transition_when_aggregate_is_open():
    stats = ActuatorStatistics()

    stats.update({1: 1})

    assert stats.open_transition_count == 1
    assert stats.last_transition_time is not None


def test_statistics_do_not_count_a_first_settle_into_closed_as_an_open_transition():
    stats = ActuatorStatistics()

    stats.update({1: 0})

    assert stats.open_transition_count == 0
    assert stats.last_transition_time is not None  # still a confirmed transition, just not "open"


def test_statistics_count_only_off_to_on_flips_as_open_transitions():
    stats = ActuatorStatistics()

    stats.update({1: 0})  # settle closed - not an open-transition
    stats.update({1: 0})  # unchanged - no transition at all
    stats.update({1: 1})  # closed -> open: one open-transition
    stats.update({1: 0})  # open -> closed: not an open-transition
    stats.update({1: 1})  # closed -> open again: a second open-transition

    assert stats.open_transition_count == 2


def test_statistics_accumulate_confirmed_open_seconds_only_while_open(monkeypatch):
    stats = ActuatorStatistics()
    times = [0.0, 1.0, 3.0, 3.0, 10.0]
    sequence = itertools.chain(times, itertools.repeat(times[-1]))
    monkeypatch.setattr(binary_sensor_module.time, "monotonic", lambda: next(sequence))

    stats.update({1: 1})  # t=0: settles open (first settle: no elapsed time yet to add)
    stats.update({1: 1})  # t=1: 1s elapsed while open -> +1s
    stats.update({1: 1})  # t=3: 2s elapsed while open -> +2s
    stats.update({1: 0})  # t=3: aggregate flips to closed (0s elapsed this call)
    stats.update({1: 0})  # t=10: elapsed while *closed* -> no addition

    assert stats.confirmed_open_seconds == 3.0


def test_pump_entity_update_feeds_the_shared_actuator_statistics():
    client = _MultiActuatorClient({250: 1})
    entity = _pump_entity({1: 250}, client)

    for _ in range(3):
        _tick(entity)

    stats = entity.hass.data[DOMAIN]["entry_1"]["actuator_statistics"]
    assert isinstance(stats, ActuatorStatistics)
    assert stats.open_actuator_count == 1


# --- State restoration across restarts (spec.md 15) ---------------------


def _with_restored_state(entity, state):
    """Stub RestoreEntity.async_get_last_state() without a real hass/store."""

    async def _fake_last_state():
        return None if state is None else SimpleNamespace(state=state, attributes={})

    entity.async_get_last_state = _fake_last_state
    return entity


def test_base_unit_error_indicator_restores_on_state():
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")
    _with_restored_state(entity, "on")

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_is_on is True


def test_base_unit_error_indicator_ignores_unknown_restored_state():
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")
    entity._attr_is_on = False
    _with_restored_state(entity, "unknown")

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_is_on is False


def test_actuator_position_sensor_restores_off_state():
    entity = ViegaActuatorPositionBinarySensor("entry_1", "room_1", 1, "name", 250)
    _with_restored_state(entity, "off")

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_is_on is False


def test_circulation_pump_restores_last_aggregate_state():
    entity = ViegaCirculationPumpBinarySensor("entry_1", {1: 250})
    _with_restored_state(entity, "on")

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_is_on is True
