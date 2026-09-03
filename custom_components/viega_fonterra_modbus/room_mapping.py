"""Discovery of room-to-actor and room-to-sensor mapping for Fonterra devices."""

from __future__ import annotations


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
