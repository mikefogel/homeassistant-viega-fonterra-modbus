"""Tests for RoomMappingDiscovery.discover_from_device (spec.md 4)."""

import asyncio

from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError
from custom_components.viega_fonterra_modbus.registers import actor_registers, room_name_register
from custom_components.viega_fonterra_modbus.room_mapping import RoomMappingDiscovery


def _encode_name(name: str) -> list[int]:
    raw = name.encode("ascii").ljust(24, b"\x00")
    return [int.from_bytes(raw[i : i + 2], "big") for i in range(0, 24, 2)]


class _FakeDiscoveryClient:
    """A module as a table of input registers. Actor `assignments[n]`
    (1-based) reports room `assignments[n]` in its Raum-ID register; an
    absent actor reports the -99 sentinel. Room names come from
    `room_names`. With `reject_multi_reads`, data registers can only be read
    one at a time, like modules updated by Viega (spec.md 4a, 16d).
    """

    def __init__(
        self,
        assignments: dict[int, int],
        room_names: dict[int, str] | None = None,
        reject_multi_reads: bool = False,
    ):
        self.registers: dict[int, int] = {}
        self.reads: list[tuple[int, int]] = []
        self._name_addresses: set[int] = set()
        self._reject_multi_reads = reject_multi_reads
        for actor_number in range(1, 13):
            registers = actor_registers(actor_number)
            room_number = assignments.get(actor_number)
            self.registers[registers["position"]] = -99 if room_number is None else 0
            self.registers[registers["return_temperature"]] = -99 if room_number is None else 193
            self.registers[registers["room_id"]] = -99 if room_number is None else room_number
        for room_number, name in (room_names or {}).items():
            address, length = room_name_register(room_number)
            self._name_addresses.add(address)
            for offset, value in enumerate(_encode_name(name)):
                self.registers[address + offset] = value

    async def read_input_registers(self, address, count=1):
        self.reads.append((address, count))
        if address in self._name_addresses:
            return [self.registers[address + i] for i in range(count)]
        if count > 1 and self._reject_multi_reads:
            raise ModbusClientError("Modbus exception 4", exception_code=4)
        if address not in self.registers:
            return []
        return [self.registers.get(address + i, -99) for i in range(count)]


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
            if address == actor_registers(1)["room_id"]:
                raise RuntimeError("timeout")
            return await super().read_input_registers(address, count)

    client = _FlakyClient({1: 1, 2: 4}, {4: "Kueche"})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert "room_1" not in rooms
    assert rooms["room_4"]["actor"] == 2


def test_discovery_finds_rooms_when_the_module_rejects_multi_register_reads():
    """GitHub issue #2: channels 1 and 2 are not wired, rooms 3-5 are, and
    the module (updated by Viega) rejects multi-register data reads with
    Modbus exception 4. Discovery must still find rooms 3-5."""
    client = _FakeDiscoveryClient(
        {3: 3, 4: 4, 5: 5},
        {3: "Kueche", 4: "Bad", 5: "Flur"},
        reject_multi_reads=True,
    )

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert set(rooms) == {"room_3", "room_4", "room_5"}
    assert rooms["room_3"]["actor"] == 3
    assert rooms["room_4"]["name"] == "Bad"


def test_discovery_reads_each_raum_id_register_on_its_own():
    """spec.md 4a: one register per read for the actuators."""
    client = _FakeDiscoveryClient({1: 1})

    asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    actor_reads = [read for read in client.reads if read[0] >= actor_registers(1)["position"]]
    assert actor_reads == [(actor_registers(n)["room_id"], 1) for n in range(1, 13)]


def test_discovery_skips_channels_that_answer_with_a_modbus_exception():
    """An empty channel may answer with an exception instead of -99."""

    class _EmptyChannelsClient(_FakeDiscoveryClient):
        async def read_input_registers(self, address, count=1):
            if address in (actor_registers(1)["room_id"], actor_registers(2)["room_id"]):
                raise ModbusClientError("Modbus exception 4", exception_code=4)
            return await super().read_input_registers(address, count)

    client = _EmptyChannelsClient({3: 3, 4: 4})

    rooms = asyncio.run(RoomMappingDiscovery.discover_from_device(client))

    assert set(rooms) == {"room_3", "room_4"}
