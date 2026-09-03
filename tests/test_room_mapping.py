"""Edge-case tests for RoomMappingDiscovery (spec.md 4).

The happy-path (1:1 and non-1:1 actor/sensor mappings) is already covered by
test_specification.py; this file covers the defensive branches around
malformed input.
"""

from custom_components.viega_fonterra_modbus.room_mapping import RoomMappingDiscovery


def test_discover_returns_empty_dict_when_rooms_is_missing():
    assert RoomMappingDiscovery.discover({}) == {}


def test_discover_returns_empty_dict_when_rooms_is_not_a_dict():
    assert RoomMappingDiscovery.discover({"rooms": "not a dict"}) == {}


def test_discover_skips_room_entries_that_are_not_dicts():
    payload = {"rooms": {"room_1": "not a dict", "room_2": {"actor": 2, "sensor": 11}}}

    mapping = RoomMappingDiscovery.discover(payload)

    assert "room_1" not in mapping
    assert mapping["room_2"] == {"actor": 2, "sensor": 11}


def test_discover_skips_rooms_without_actor_or_sensor():
    payload = {"rooms": {"room_1": {"name": "Wohnzimmer"}}}

    mapping = RoomMappingDiscovery.discover(payload)

    assert mapping == {}


def test_discover_keeps_a_room_with_only_an_actor():
    payload = {"rooms": {"room_1": {"actor": 1}}}

    mapping = RoomMappingDiscovery.discover(payload)

    assert mapping == {"room_1": {"actor": 1, "sensor": None}}


def test_discover_keeps_a_room_with_only_a_sensor():
    payload = {"rooms": {"room_1": {"sensor": 10}}}

    mapping = RoomMappingDiscovery.discover(payload)

    assert mapping == {"room_1": {"actor": None, "sensor": 10}}
