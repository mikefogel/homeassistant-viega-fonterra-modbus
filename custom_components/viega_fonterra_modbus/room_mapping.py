"""Discovery of room-to-actor and room-to-sensor mapping for Fonterra devices."""

from __future__ import annotations

import logging

from .registers import (
    actor_registers,
    decode_text_registers,
    room_name_register,
)

_LOGGER = logging.getLogger(__name__)


class RoomMappingDiscovery:
    """Discover the association of room IDs to actor and sensor addresses."""

    @staticmethod
    def discover(device_payload: dict[str, object]) -> dict[str, dict[str, object]]:
        """Return room mapping for the initial discovery pass.

        The layout is intentionally flexible: one room may map to one or more
        actors and sensors, and one actor/sensor can also participate in multiple
        room mappings depending on the device topology.
        """
        # Some clients return the complete payload while lightweight clients
        # return the room dictionary itself.
        rooms = device_payload.get("rooms", device_payload)
        if not isinstance(rooms, dict):
            return {}

        result: dict[str, dict[str, object]] = {}
        for room_name, details in rooms.items():
            if not isinstance(details, dict):
                continue
            actor_id = details.get("actor")
            sensor_id = details.get("sensor")
            if actor_id is None and sensor_id is None:
                continue
            result[str(room_name)] = {
                "actor": actor_id,
                "sensor": sensor_id,
            }
        return result

    @staticmethod
    async def discover_from_device(client) -> dict[str, dict[str, object]]:
        """Read the real room/actor topology from the device over Modbus.

        The device manual documents an explicit "Raum ID" input register for
        each of the up to 12 actuators (manual 30252/30255/.../30285,
        `actor_registers()["room_id"]`): an int16 in range 1-12 naming the
        room that actuator currently serves. Reading all 12 actuators'
        position/return-temperature/room-id registers (one 3-register read
        each, matching the device manual's own "Aktor 1 lesen" example)
        gives the real actor-to-room association directly from the device,
        instead of trusting a manually typed mapping that can drift from the
        physical installation. Each room's display name is then read from
        its own 24-character name register (manual 30074 + 12*(room-1)).

        A room with no actuator currently reporting it is omitted; a room
        whose name register can't be read keeps a generic "room_<n>" name.
        Communication failures for one actuator or room name do not abort
        discovery for the others.
        """
        rooms: dict[str, dict[str, object]] = {}
        for actor_number in range(1, 13):
            registers = actor_registers(actor_number)
            try:
                values = await client.read_input_registers(registers["position"], 3)
            except Exception:
                _LOGGER.debug(
                    "Room discovery: read failed for actor %s", actor_number, exc_info=True
                )
                continue
            if not values or len(values) < 3:
                continue
            room_number = values[2]
            if not isinstance(room_number, int) or not 1 <= room_number <= 12:
                # -99 (unassigned/no actuator installed at this slot) and any
                # other out-of-range value are not a valid room association.
                continue
            room_id = f"room_{room_number}"
            room = rooms.setdefault(
                room_id, {"room_number": room_number, "sensor": room_number, "actor": []}
            )
            actors = room["actor"]
            if isinstance(actors, list) and actor_number not in actors:
                actors.append(actor_number)
            _LOGGER.debug(
                "Room discovery: actor %s -> room_id=%s (position=%s return_temperature=%s)",
                actor_number,
                room_id,
                values[0],
                values[1],
            )

        for room_id, room in rooms.items():
            actors = room.get("actor")
            if isinstance(actors, list) and len(actors) == 1:
                room["actor"] = actors[0]

            room_number = room["room_number"]
            assert isinstance(room_number, int)
            address, length = room_name_register(room_number)
            name = room_id
            try:
                values = await client.read_input_registers(address, length)
                if values:
                    decoded = decode_text_registers(values)
                    if decoded:
                        name = decoded
            except Exception:
                _LOGGER.debug(
                    "Room discovery: name read failed for %s", room_id, exc_info=True
                )
            room["name"] = name
            _LOGGER.debug("Room discovery: resolved %s -> %r", room_id, room)

        return rooms
