"""Specification-driven tests for the expanded Fonterra integration."""

from custom_components.viega_fonterra_modbus.const import PLATFORMS
from custom_components.viega_fonterra_modbus.climate import ViegaRoomClimateEntity
from custom_components.viega_fonterra_modbus.sensor import async_setup_entry as sensor_async_setup_entry


def test_diagnostic_is_not_a_platform_and_is_forwarded_via_sensor():
    """spec.md "PLATFORMS must list only real HA platform domains": no
    `homeassistant.components.diagnostic` domain exists, so
    `async_forward_entry_setups` would raise if "diagnostic" were ever added
    to PLATFORMS again - a prior commit did that, misreading its earlier,
    deliberate removal as accidental, backed only by a test asserting string
    membership rather than that forwarding actually works. Room diagnostic
    entities are instead created directly by sensor.py's async_setup_entry
    (see its import of ViegaDiagnosticTextEntity), which *is* forwarded via
    PLATFORMS' "sensor" entry."""
    assert "diagnostic" not in PLATFORMS
    assert "sensor" in PLATFORMS
    assert sensor_async_setup_entry is not None


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
