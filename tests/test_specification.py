"""Specification-driven tests for the expanded Fonterra integration."""

from custom_components.viega_fonterra_modbus.device_registry import DeviceRegistry
from custom_components.viega_fonterra_modbus.climate import ViegaRoomClimateEntity
from custom_components.viega_fonterra_modbus.room_mapping import RoomMappingDiscovery
from custom_components.viega_fonterra_modbus.switch import ViegaBasicSwitch
from custom_components.viega_fonterra_modbus.thermostat import ViegaRoomThermostatEntity


def test_room_mapping_discovers_actor_and_sensor_pairs():
    """The first read must discover room-to-actor and room-to-sensor relationships."""
    payload = {
        "rooms": {
            "room_1": {"actor": 1, "sensor": 10},
            "room_2": {"actor": 2, "sensor": 11},
        }
    }

    mapping = RoomMappingDiscovery.discover(payload)

    assert mapping["room_1"]["actor"] == 1
    assert mapping["room_1"]["sensor"] == 10
    assert mapping["room_2"]["actor"] == 2
    assert mapping["room_2"]["sensor"] == 11


def test_room_mapping_supports_multiple_actors_per_room_and_multiple_rooms_per_actor():
    """The room mapping is not strictly 1:1 between rooms and actors."""
    payload = {
        "rooms": {
            "room_1": {"actor": [1, 2], "sensor": [10, 11]},
            "room_2": {"actor": 2, "sensor": 12},
        }
    }

    mapping = RoomMappingDiscovery.discover(payload)

    assert mapping["room_1"]["actor"] == [1, 2]
    assert mapping["room_1"]["sensor"] == [10, 11]
    assert mapping["room_2"]["actor"] == 2


def test_multiple_devices_can_be_registered():
    """The registry must keep several device entries independent from one another."""
    registry = DeviceRegistry()
    registry.add_device("device_1", {"host": "192.168.1.10", "port": 502})
    registry.add_device("device_2", {"host": "192.168.1.11", "port": 502})

    assert len(registry.devices) == 2
    assert registry.devices["device_1"]["host"] == "192.168.1.10"
    assert registry.devices["device_2"]["host"] == "192.168.1.11"


def test_room_thermostat_has_room_identifier_and_target_temperature():
    """A thermostat entity must expose room-level data required for HA control."""
    entity = ViegaRoomThermostatEntity("room_1", 21.5, 22.0)

    assert entity.room_id == "room_1"
    assert entity.current_temperature == 21.5
    assert entity.target_temperature == 22.0


def test_climate_entity_uses_feature_flags():
    """Climate capabilities must use a Home Assistant feature flag container."""
    entity = ViegaRoomClimateEntity("entry_1", "room_1", "Wohnzimmer", 21.5, 22.0)

    assert entity.supported_features


def test_climate_entity_writes_scaled_target_temperature():
    """A target temperature is written as tenths of a degree."""
    import asyncio
    from types import SimpleNamespace

    class FakeClient:
        async def write_register(self, address, value):
            self.address = address
            self.value = value

    client = FakeClient()
    entity = ViegaRoomClimateEntity(
        "entry_1", "room_1", "Wohnzimmer", 21.5, 22.0, 1200
    )
    entity.hass = SimpleNamespace(
        data={"viega_fonterra_modbus": {"entry_1": {"client": client}}}
    )

    asyncio.run(entity.async_set_temperature(temperature=20.5))

    assert client.address == 1200
    assert client.value == 205
    assert entity.target_temperature == 20.5


def test_basic_switch_can_be_enabled_and_disabled():
    """A simple switch entity must support the no-frills operation mode."""
    switch = ViegaBasicSwitch("heating_enable")

    assert switch.is_on is False
    switch.turn_on()
    assert switch.is_on is True
    switch.turn_off()
    assert switch.is_on is False
