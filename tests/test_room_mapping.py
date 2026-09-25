"""Tests for RoomMappingDiscovery.discover_from_device (spec.md 4)."""

import asyncio

from custom_components.viega_fonterra_modbus.registers import actor_registers, room_name_register
from custom_components.viega_fonterra_modbus.room_mapping import RoomMappingDiscovery


def _encode_name(name: str) -> list[int]:
    raw = name.encode("ascii").ljust(24, b"\x00")
    return [int.from_bytes(raw[i : i + 2], "big") for i in range(0, 24, 2)]


class _FakeDiscoveryClient:
    """Actor `assignments[n]` (1-based) reports room `assignments[n]`, or is
    treated as not installed (ERROR_SENTINEL) when absent from the dict.
    Room names come from `room_names`, defaulting to "Room N" when missing.
    """

    def __init__(self, assignments: dict[int, int], room_names: dict[int, str] | None = None):
        self._assignments = assignments
        self._room_names = room_names or {}

    async def read_input_registers(self, address, count=1):
        if count == 3:
            for actor_number, room_number in self._assignments.items():
                if address == actor_registers(actor_number)["position"]:
                    return [0, 193, room_number]
            return [-99, -99, -99]
        if count == 12:
            for room_number, name in self._room_names.items():
                if address == room_name_register(room_number)[0]:
                    return _encode_name(name)
            return []
        return []


def test_discover_from_device_associates_actors_with_the_room_they_report():
    client = _FakeDiscoveryClient({1: 3, 2: 3}, {3: "Wohnzimmer"})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert rooms["room_3"]["actor"] == [1, 2]
    assert rooms["room_3"]["name"] == "Wohnzimmer"
    assert rooms["room_3"]["room_number"] == 3


def test_discover_from_device_uses_a_single_int_for_a_single_actor_room():
    client = _FakeDiscoveryClient({5: 1}, {1: "Schlafzimmer"})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert rooms["room_1"]["actor"] == 5
    assert rooms["room_1"]["name"] == "Schlafzimmer"


def test_discover_from_device_ignores_an_unassigned_actuator():
    """An actuator with no room association reports the -99 sentinel."""
    client = _FakeDiscoveryClient({})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert rooms == {}


def test_discover_from_device_keeps_a_generic_name_when_the_name_read_fails():
    class _NoNameClient(_FakeDiscoveryClient):
        async def read_input_registers(self, address, count=1):
            if count == 12:
                raise RuntimeError("device offline")
            return await super().read_input_registers(address, count)

    client = _NoNameClient({1: 2})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert rooms["room_2"]["name"] == "room_2"


def test_discover_from_device_tolerates_a_single_actuator_read_failure():
    class _FlakyClient(_FakeDiscoveryClient):
        async def read_input_registers(self, address, count=1):
            if count == 3 and address == actor_registers(1)["position"]:
                raise RuntimeError("timeout")
            return await super().read_input_registers(address, count)

    client = _FlakyClient({1: 1, 2: 4}, {4: "Kueche"})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert "room_1" not in rooms
    assert rooms["room_4"]["actor"] == 2
