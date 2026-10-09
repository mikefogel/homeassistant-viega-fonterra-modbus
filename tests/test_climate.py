"""Tests for the room Climate entity beyond the basics already covered in
test_specification.py (feature flags, scaled target-temperature write).
"""

import asyncio
from types import SimpleNamespace

from homeassistant.components.climate import ClimateEntityFeature

from custom_components.viega_fonterra_modbus.climate import ViegaRoomClimateEntity
from custom_components.viega_fonterra_modbus.const import DOMAIN


class _RecordingClient:
    def __init__(self):
        self.writes: list[tuple[int, int]] = []

    async def write_register(self, address, value):
        self.writes.append((address, value))


class _RecordingReadClient:
    def __init__(self, value: int = 100):
        self.holding_reads: list[int] = []
        self.input_reads: list[int] = []
        self._value = value

    async def read_holding_registers(self, address, count=1):
        self.holding_reads.append(address)
        return [self._value]

    async def read_input_registers(self, address, count=1):
        self.input_reads.append(address)
        return [self._value]


class _ErrorSentinelClient:
    """Every register reads back the `-99` device error sentinel."""

    async def read_holding_registers(self, address, count=1):
        return [-99]

    async def read_input_registers(self, address, count=1):
        return [-99]


class _PartiallyFailingClient:
    def __init__(self, fail_address: int):
        self.fail_address = fail_address

    async def read_holding_registers(self, address, count=1):
        if address == self.fail_address:
            raise RuntimeError("boom")
        return [123]

    async def read_input_registers(self, address, count=1):
        if address == self.fail_address:
            raise RuntimeError("boom")
        return [456]


def _entity(room_id="room_1", room_config=None) -> ViegaRoomClimateEntity:
    return ViegaRoomClimateEntity(
        "entry_1", room_id, "Wohnzimmer", 21.5, 22.0, room_config
    )


def test_hvac_mode_and_preset_mode_reflect_initial_state():
    entity = _entity()

    assert entity.hvac_mode == "heat"
    assert entity.preset_mode == "manual"


def test_set_hvac_mode_writes_the_operating_mode_register_and_updates_state():
    entity = _entity()
    client = _RecordingClient()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})

    asyncio.run(entity.async_set_hvac_mode("off"))

    assert client.writes == [(entity._registers["operating_mode"], 0)]
    assert entity.hvac_mode == "off"


def test_set_hvac_mode_does_not_change_current_or_target_temperature():
    """spec.md 5a.1: "Selecting a new mode must not change
    current_temperature or target_temperature"."""
    entity = _entity()
    entity._attr_current_temperature = 21.5
    entity._attr_target_temperature = 22.0
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _RecordingClient()}}})

    asyncio.run(entity.async_set_hvac_mode("off"))

    assert entity._attr_current_temperature == 21.5
    assert entity._attr_target_temperature == 22.0


def test_set_preset_mode_does_not_change_current_or_target_temperature():
    entity = _entity()
    entity._attr_current_temperature = 21.5
    entity._attr_target_temperature = 22.0
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _RecordingClient()}}})

    asyncio.run(entity.async_set_preset_mode("profile"))

    assert entity._attr_current_temperature == 21.5
    assert entity._attr_target_temperature == 22.0


def test_set_hvac_mode_rejects_an_unsupported_mode():
    entity = _entity()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _RecordingClient()}}})

    try:
        asyncio.run(entity.async_set_hvac_mode("auto"))
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for an unsupported hvac_mode")


def test_set_preset_mode_writes_the_profile_mode_register_and_updates_state():
    entity = _entity()
    client = _RecordingClient()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})

    asyncio.run(entity.async_set_preset_mode("profile"))

    assert client.writes == [(entity._registers["profile_mode"], 1)]
    assert entity.preset_mode == "profile"


def test_set_preset_mode_rejects_an_unsupported_mode():
    entity = _entity()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _RecordingClient()}}})

    try:
        asyncio.run(entity.async_set_preset_mode("eco"))
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for an unsupported preset_mode")


def test_room_without_a_resolvable_target_register_excludes_the_feature_and_is_a_noop():
    """spec.md 5b: a room without a configured target register must remain
    readable but must not advertise target-temperature write support."""
    entity = _entity(room_id="wohnzimmer", room_config={"name": "Wohnzimmer"})

    assert not (entity._attr_supported_features & ClimateEntityFeature.TARGET_TEMPERATURE)

    client = _RecordingClient()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})
    asyncio.run(entity.async_set_temperature(temperature=25.0))

    assert client.writes == []
    assert entity._attr_target_temperature == 22.0


def test_set_temperature_out_of_register_range_raises():
    entity = _entity(room_config={"target_temperature_register": 50})
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _RecordingClient()}}})

    try:
        asyncio.run(entity.async_set_temperature(temperature=10000.0))
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError for a register value outside 0..65535")


def test_async_update_reads_holding_registers_for_writable_values_and_input_registers_for_sensors():
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _RecordingReadClient()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})

    asyncio.run(entity.async_update())

    assert set(client.holding_reads) == {
        entity._registers["target_temperature"],
        entity._registers["power_level"],
        entity._registers["operating_mode"],
        entity._registers["profile_mode"],
    }
    assert set(client.input_reads) == {
        entity._registers["current_temperature"],
        entity._registers["flow_temperature"],
        entity._registers["return_temperature"],
        entity._registers["actuator_position"],
        entity._registers["error_code"],
    }


def test_async_update_isolates_a_single_register_failure():
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _PartiallyFailingClient(fail_address=entity._registers["target_temperature"])
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})

    asyncio.run(entity.async_update())

    # The target_temperature read failed, but the unrelated current_temperature
    # read must still have gone through.
    assert entity._attr_current_temperature == 45.6
    assert entity._attr_target_temperature == 22.0


def test_async_update_skips_the_read_when_the_polling_gate_is_not_due():
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _RecordingReadClient()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})

    asyncio.run(entity.async_update())
    reads_after_first_update = len(client.holding_reads) + len(client.input_reads)

    asyncio.run(entity.async_update())

    assert len(client.holding_reads) + len(client.input_reads) == reads_after_first_update


def test_async_update_keeps_the_previous_temperature_across_repeated_error_sentinel_reads():
    """spec.md 10: a `-99` read must never be divided by 10 into a
    fabricated -9.9 - the previous valid value must survive any number of
    consecutive `-99` reads, not just a single one."""
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _ErrorSentinelClient()}}}
    )
    entity._attr_current_temperature = 21.5
    entity._attr_target_temperature = 22.0

    for _ in range(3):
        asyncio.run(entity.async_update())
        assert entity._attr_current_temperature == 21.5
        assert entity._attr_target_temperature == 22.0


def test_async_update_keeps_previous_attributes_across_repeated_error_sentinel_reads():
    """The same guarantee applies to every other register-backed attribute:
    a `-99`/failed read must retain the last known-good value instead of
    being cleared to `None`, which previously made hvac_mode/preset_mode
    and the extra_state_attributes flap on every transient device error."""
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _ErrorSentinelClient()}}}
    )
    entity._power_level = 5
    entity._flow_temperature = 35.2
    entity._return_temperature = 28.1
    entity._actuator_position = 1
    entity._base_error_code = 0
    entity._operating_mode = 1
    entity._profile_mode = 0

    for _ in range(3):
        asyncio.run(entity.async_update())
        assert entity._power_level == 5
        assert entity._flow_temperature == 35.2
        assert entity._return_temperature == 28.1
        assert entity._actuator_position == 1
        assert entity._base_error_code == 0
        assert entity.hvac_mode == "heat"
        assert entity.preset_mode == "manual"


def test_multi_actor_room_uses_the_first_actor_for_linked_registers():
    """spec.md 4: the Climate entity uses only the primary (first) actuator;
    the rest are exposed as extra sensors (see sensor.py's
    _extra_actor_sensors, covered in test_sensor_entities.py)."""
    multi = _entity(room_config={"name": "Wohnzimmer", "actor": [3, 4]})
    single = _entity(room_config={"name": "Wohnzimmer", "actor": 3})

    assert multi._registers["actuator_position"] == single._registers["actuator_position"]
    assert multi._registers["return_temperature"] == single._registers["return_temperature"]


def test_extra_state_attributes_exposes_room_and_controller_values():
    entity = _entity(room_config={"name": "Wohnzimmer", "room_number": 1})
    entity._power_level = 5
    entity._flow_temperature = 35.2
    entity._return_temperature = 28.1
    entity._actuator_position = 60
    entity._base_error_code = 0

    assert entity.extra_state_attributes == {
        "room_id": 1,
        "power_level": 5,
        "flow_temperature": 35.2,
        "return_temperature": 28.1,
        "actuator_position": 60,
        "base_unit_error_code": 0,
    }


def test_device_info_uses_the_configured_device_name():
    entity = _entity()
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"device_name": "Heizung Wohnzimmer"}}}
    )

    assert entity.device_info["name"] == "Heizung Wohnzimmer"


# --- State restoration across restarts (spec.md 15) ---------------------


def test_restores_current_and_target_temperature_on_add():
    """A restart must not be visible in the displayed values: the last known
    current/target temperature must come back exactly as it was."""
    entity = _entity()

    async def _fake_last_state():
        return SimpleNamespace(
            state="heat",
            attributes={"current_temperature": 21.5, "temperature": 23.0},
        )

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_current_temperature == 21.5
    assert entity._attr_target_temperature == 23.0


def test_restores_hvac_mode_preset_mode_and_extra_attributes_on_add():
    """The entity's `state` *is* the HVAC mode (ClimateEntity.state returns
    hvac_mode) - a restart must not silently fall back to this class's
    __init__ defaults ("heat"/"manual") for a room that was actually off
    and on the profile preset."""
    entity = _entity()

    async def _fake_last_state():
        return SimpleNamespace(
            state="off",
            attributes={
                "current_temperature": 21.5,
                "temperature": 23.0,
                "preset_mode": "profile",
                "power_level": 4,
                "flow_temperature": 35.2,
                "return_temperature": 28.1,
                "actuator_position": 1,
                "base_unit_error_code": 0,
            },
        )

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity.hvac_mode == "off"
    assert entity.preset_mode == "profile"
    assert entity.extra_state_attributes == {
        "room_id": entity.room_number,
        "power_level": 4,
        "flow_temperature": 35.2,
        "return_temperature": 28.1,
        "actuator_position": 1,
        "base_unit_error_code": 0,
    }


def test_ignores_unknown_or_unavailable_restored_state():
    entity = _entity()
    entity._attr_current_temperature = 19.0
    entity._attr_target_temperature = 20.0

    async def _fake_last_state():
        return SimpleNamespace(state="unavailable", attributes={})

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_current_temperature == 19.0
    assert entity._attr_target_temperature == 20.0


class _RecordingWriteThenReadClient:
    """Records writes; subsequent reads return whatever `set_values` holds
    for that address, defaulting to the write's own value if unset."""

    def __init__(self):
        self.writes: list[tuple[int, int]] = []
        self.values_by_address: dict[int, int] = {}

    async def write_register(self, address, value):
        self.writes.append((address, value))
        self.values_by_address.setdefault(address, value)

    async def read_holding_registers(self, address, count=1):
        return [self.values_by_address.get(address, 0)]

    async def read_input_registers(self, address, count=1):
        return [self.values_by_address.get(address, 0)]


class _FakeSharedPolling:
    """Minimal stand-in for `SharedPolling`: bumps `generation` once per
    `bump()` call, mirroring a real polling window reopening."""

    def __init__(self, client):
        self._client = client
        self.generation = 0

    def bump(self) -> None:
        self.generation += 1

    async def read(self, hass, entry_id, bank, address, count=1):
        reader = (
            self._client.read_holding_registers
            if bank == "holding"
            else self._client.read_input_registers
        )
        return await reader(address, count)


# --- Read-after-write verification (spec.md 16c) -------------------------


def test_verified_write_that_matches_leaves_no_warning():
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _RecordingWriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_hvac_mode("off"))
    shared.bump()  # simulate the poll cache refreshing after the write
    asyncio.run(entity.async_update())

    assert entity.last_error_message == ""


def test_a_mismatched_verification_reports_a_warning_and_keeps_the_device_value():
    """spec.md 16c: "the device value remains authoritative" - a mismatch
    must both report a diagnostic warning and reconcile the displayed state
    to what the device actually reports, not the optimistically-written
    value."""
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _RecordingWriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_hvac_mode("off"))
    assert entity.hvac_mode == "off"

    # The device rejected/overrode the write and actually holds "heat" (1).
    client.values_by_address[entity._registers["operating_mode"]] = 1
    shared.bump()
    asyncio.run(entity.async_update())

    assert entity.hvac_mode == "heat"
    assert "operating_mode" in entity.last_error_message
    assert "warning" in entity.last_error_message


def test_verification_ignores_a_read_still_from_the_write_time_cache_generation():
    """A read served from the same cache generation active at write time may
    still be the pre-write value - it must not be judged yet, only a read
    from a strictly newer generation counts as verification."""
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _RecordingWriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_hvac_mode("off"))
    # Simulate a pre-write value still cached under the *same* generation.
    client.values_by_address[entity._registers["operating_mode"]] = 1
    asyncio.run(entity.async_update())  # generation unchanged - must not judge yet

    assert entity.last_error_message == ""
    # The pending check is still armed for the next, genuinely newer read.
    assert "operating_mode" in entity._pending_writes


def test_verification_waits_for_a_valid_value_skipping_the_error_sentinel():
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})
    client = _RecordingWriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_preset_mode("profile"))
    shared.bump()
    client.values_by_address[entity._registers["profile_mode"]] = -99
    asyncio.run(entity.async_update())

    # Still pending - a -99 read is not a "suitable" read to verify against.
    assert "profile_mode" in entity._pending_writes
    assert entity.last_error_message == ""

    client.values_by_address[entity._registers["profile_mode"]] = 1
    asyncio.run(entity.async_update())

    assert "profile_mode" not in entity._pending_writes
    assert entity.last_error_message == ""


def test_a_failed_write_never_schedules_verification_or_changes_state():
    entity = _entity(room_config={"name": "Wohnzimmer", "actor": 1})

    class _FailingClient:
        async def write_register(self, address, value):
            raise RuntimeError("device offline")

    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FailingClient()}}})

    try:
        asyncio.run(entity.async_set_hvac_mode("off"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the write failure to propagate")

    assert entity.hvac_mode == "heat"  # unchanged default
    assert entity._pending_writes == {}


def test_restore_is_a_noop_without_a_previous_state():
    entity = _entity()

    async def _fake_last_state():
        return None

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_current_temperature == 21.5
    assert entity._attr_target_temperature == 22.0
