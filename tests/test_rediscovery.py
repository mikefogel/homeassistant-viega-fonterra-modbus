"""Tests for the explicit rediscovery action (spec.md 16a)."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import binary_sensor as binary_sensor_platform
from custom_components.viega_fonterra_modbus import rediscovery
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.entity_tracking import register_platform
from custom_components.viega_fonterra_modbus.polling import SharedPolling
from custom_components.viega_fonterra_modbus.room_mapping import RoomMappingDiscovery


# --- diff_topology (pure) -------------------------------------------------


def test_diff_topology_detects_an_added_room():
    report = rediscovery.diff_topology({}, {"room_1": {"name": "Wohnzimmer"}})

    assert report.added == ["room_1"]
    assert report.removed == []
    assert report.changed is True


def test_diff_topology_detects_a_removed_room():
    report = rediscovery.diff_topology({"room_1": {"name": "Wohnzimmer"}}, {})

    assert report.removed == ["room_1"]
    assert report.added == []


def test_diff_topology_detects_a_rename():
    old = {"room_1": {"name": "Wohnzimmer", "actor": 1}}
    new = {"room_1": {"name": "Salon", "actor": 1}}

    report = rediscovery.diff_topology(old, new)

    assert report.renamed == {"room_1": ("Wohnzimmer", "Salon")}
    assert report.reassigned == {}


def test_diff_topology_detects_a_reassigned_actuator():
    old = {"room_1": {"name": "Wohnzimmer", "actor": 1}}
    new = {"room_1": {"name": "Wohnzimmer", "actor": [1, 2]}}

    report = rediscovery.diff_topology(old, new)

    assert report.reassigned == {"room_1": ([1], [1, 2])}
    assert report.renamed == {}


def test_diff_topology_reports_no_changes_for_identical_topologies():
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    report = rediscovery.diff_topology(rooms, dict(rooms))

    assert report.changed is False


# --- async_rediscover_entry ------------------------------------------------


class _FakeConfigEntries:
    def __init__(self):
        self.updated_options = None

    def async_update_entry(self, entry, options):
        self.updated_options = options
        entry.options = options


class _FakeBus:
    def __init__(self):
        self.fired: list[tuple[str, dict]] = []

    def async_fire(self, event_type, data):
        self.fired.append((event_type, data))


def _make_hass(entry_data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        data={DOMAIN: {"entry_1": entry_data}},
        config_entries=_FakeConfigEntries(),
        bus=_FakeBus(),
    )


def _make_entry() -> SimpleNamespace:
    return SimpleNamespace(entry_id="entry_1", options={})


def test_rediscover_updates_rooms_and_config_entry_options(monkeypatch):
    new_rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    async def fake_discover(client):
        return new_rooms

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": {}})
    entry = _make_entry()

    report = asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert report.failed is False
    assert report.added == ["room_1"]
    assert hass.data[DOMAIN]["entry_1"]["rooms"] == new_rooms
    assert hass.config_entries.updated_options["rooms"] == new_rooms
    assert entry.options["rooms"] == new_rooms


def test_rediscover_fires_a_report_event(monkeypatch):
    async def fake_discover(client):
        return {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": {}})
    entry = _make_entry()

    asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert len(hass.bus.fired) == 1
    event_type, data = hass.bus.fired[0]
    assert event_type == rediscovery.EVENT_REDISCOVERY_COMPLETE
    assert data["added"] == ["room_1"]
    assert data["failed"] is False


def test_rediscover_keeps_the_previous_topology_when_discovery_finds_nothing(monkeypatch):
    """spec.md 4a: a live discovery that comes back empty (device
    unreachable this cycle) must never silently replace a working
    topology."""
    async def fake_discover(client):
        return {}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    old_rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}
    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": old_rooms})
    entry = _make_entry()

    report = asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert report.failed is True
    assert hass.data[DOMAIN]["entry_1"]["rooms"] == old_rooms
    assert hass.config_entries.updated_options is None


def test_rediscover_keeps_the_previous_topology_when_discovery_raises(monkeypatch):
    async def fake_discover(client):
        raise RuntimeError("device offline")

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    old_rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}
    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": old_rooms})
    entry = _make_entry()

    report = asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert report.failed is True
    assert report.error == "device offline"
    assert hass.data[DOMAIN]["entry_1"]["rooms"] == old_rooms


def test_rediscover_is_a_noop_report_when_the_entry_is_not_loaded():
    hass = SimpleNamespace(data={DOMAIN: {}}, config_entries=_FakeConfigEntries(), bus=_FakeBus())
    entry = _make_entry()

    report = asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert report.failed is True
    assert hass.bus.fired == []


def test_rediscover_reuses_the_shared_connection_and_polling_lock(monkeypatch):
    """spec.md 16a: "The action must reuse the existing connection and
    polling lock" - it must go through `SharedPolling.run_exclusive`, not
    open a second connection or bypass the lock every other read goes
    through."""
    calls: list[str] = []

    class _TrackingSharedPolling(SharedPolling):
        async def run_exclusive(self, action):
            calls.append("run_exclusive")
            return await super().run_exclusive(action)

    async def fake_discover(client):
        calls.append("discover")
        return {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    hass = _make_hass(
        {"client": object(), "polling": _TrackingSharedPolling(), "rooms": {}}
    )
    entry = _make_entry()

    asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert calls == ["run_exclusive", "discover"]


def test_rediscover_adds_entities_for_a_newly_discovered_room(monkeypatch):
    async def fake_discover(client):
        return {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": {}})
    entry = _make_entry()

    added_by_platform: dict[str, list] = {"climate": [], "number": [], "sensor": [], "binary_sensor": []}
    for platform_name, added in added_by_platform.items():
        register_platform(hass, "entry_1", platform_name, added.extend)

    asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert len(added_by_platform["climate"]) == 1
    assert added_by_platform["climate"][0].room_id == "room_1"
    assert len(added_by_platform["number"]) == 1
    # sensor: one diagnostic text entity + one actor return-temperature sensor
    assert len(added_by_platform["sensor"]) == 2
    # binary_sensor: one actuator-position sensor + the rebuilt pump entity
    # (the actuator set changed from empty to {1}).
    assert len(added_by_platform["binary_sensor"]) == 2


def test_rediscover_removes_entities_for_a_room_the_device_no_longer_reports(monkeypatch):
    async def fake_discover_removed(client):
        return {"room_2": {"name": "Bad", "actor": 2}}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover_removed)

    old_rooms = {
        "room_1": {"name": "Wohnzimmer", "actor": 1},
        "room_2": {"name": "Bad", "actor": 2},
    }
    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": old_rooms})
    entry = _make_entry()

    class _FakeClimateEntity:
        def __init__(self):
            self.removed = False

        async def async_remove(self, force_remove: bool = False) -> None:
            self.removed = True

    climate_added: list = []
    registry = register_platform(hass, "entry_1", "climate", climate_added.extend)
    room_1_entity = _FakeClimateEntity()
    registry.add_room("room_1", [room_1_entity])

    report = asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert report.removed == ["room_1"]
    assert room_1_entity.removed is True
    assert "room_1" not in registry.by_room


def test_rediscover_rebuilds_the_pump_entity_when_the_actuator_set_changes(monkeypatch):
    async def fake_discover(client):
        return {"room_1": {"name": "Wohnzimmer", "actor": [1, 2]}}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    old_rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}
    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": old_rooms})
    entry = _make_entry()

    added: list = []
    registry = register_platform(hass, "entry_1", "binary_sensor", added.extend)
    old_pump = binary_sensor_platform.build_pump_entity("entry_1", old_rooms)
    registry.add_room(binary_sensor_platform.PUMP_TRACKING_KEY, [old_pump])

    asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    new_pump_entities = registry.by_room[binary_sensor_platform.PUMP_TRACKING_KEY]
    assert len(new_pump_entities) == 1
    assert new_pump_entities[0] is not old_pump
    assert set(new_pump_entities[0]._actuator_addresses) == {1, 2}


def test_rediscover_does_not_rebuild_the_pump_when_the_actuator_set_is_unchanged(monkeypatch):
    async def fake_discover(client):
        # Same actuator set as before, just a renamed room.
        return {"room_1": {"name": "Salon", "actor": 1}}

    monkeypatch.setattr(RoomMappingDiscovery, "discover_from_device", fake_discover)

    old_rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}
    hass = _make_hass({"client": object(), "polling": SharedPolling(), "rooms": old_rooms})
    entry = _make_entry()

    added: list = []
    registry = register_platform(hass, "entry_1", "binary_sensor", added.extend)
    old_pump = binary_sensor_platform.build_pump_entity("entry_1", old_rooms)
    registry.add_room(binary_sensor_platform.PUMP_TRACKING_KEY, [old_pump])

    asyncio.run(rediscovery.async_rediscover_entry(hass, entry))

    assert registry.by_room[binary_sensor_platform.PUMP_TRACKING_KEY] == [old_pump]
