"""Tests for the per-room live-entity bookkeeping used by the explicit
rediscovery action (spec.md 16a)."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.entity_tracking import (
    PlatformEntities,
    register_platform,
)


class _FakeEntity:
    def __init__(self, name: str):
        self.entity_id = name
        self.removed = False

    async def async_remove(self, force_remove: bool = False) -> None:
        assert force_remove is True
        self.removed = True


def test_add_room_registers_entities_and_calls_add_entities():
    added: list = []
    registry = PlatformEntities(added.extend)
    entities = [_FakeEntity("a"), _FakeEntity("b")]

    registry.add_room("room_1", entities)

    assert added == entities
    assert registry.by_room["room_1"] == entities


def test_add_room_is_a_noop_for_an_empty_list():
    added: list = []
    registry = PlatformEntities(added.extend)

    registry.add_room("room_1", [])

    assert added == []
    assert "room_1" not in registry.by_room


def test_remove_room_force_removes_every_tracked_entity():
    registry = PlatformEntities(lambda entities: None)
    entities = [_FakeEntity("a"), _FakeEntity("b")]
    registry.add_room("room_1", entities)

    asyncio.run(registry.remove_room("room_1"))

    assert all(entity.removed for entity in entities)
    assert "room_1" not in registry.by_room


def test_remove_room_is_a_noop_for_an_untracked_room():
    registry = PlatformEntities(lambda entities: None)

    asyncio.run(registry.remove_room("room_1"))  # must not raise


def test_remove_room_does_not_abort_when_one_entity_removal_raises():
    class _RaisingEntity(_FakeEntity):
        async def async_remove(self, force_remove: bool = False) -> None:
            raise RuntimeError("removal failed")

    registry = PlatformEntities(lambda entities: None)
    good = _FakeEntity("a")
    registry.add_room("room_1", [_RaisingEntity("bad"), good])

    asyncio.run(registry.remove_room("room_1"))  # must not raise

    assert good.removed is True


def test_register_platform_stores_the_registry_on_hass_data():
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {}}})

    registry = register_platform(hass, "entry_1", "climate", lambda entities: None)

    assert hass.data[DOMAIN]["entry_1"]["platform_entities"]["climate"] is registry


def test_register_platform_can_register_multiple_platforms_independently():
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {}}})

    climate_registry = register_platform(hass, "entry_1", "climate", lambda e: None)
    sensor_registry = register_platform(hass, "entry_1", "sensor", lambda e: None)

    platforms = hass.data[DOMAIN]["entry_1"]["platform_entities"]
    assert platforms["climate"] is climate_registry
    assert platforms["sensor"] is sensor_registry
    assert climate_registry is not sensor_registry
