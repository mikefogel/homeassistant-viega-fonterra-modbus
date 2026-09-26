"""Per-config-entry, per-room bookkeeping of live entities.

Every platform's `async_setup_entry` registers the room-scoped entities it
builds here, alongside the `async_add_entities` callback it was given. This
is what lets the explicit rediscovery action (`rediscovery.py`, spec.md 16a)
add, remove, or rebuild a single room's entities after a live topology
change - without reloading the whole config entry, which would drop the
shared Modbus connection and disturb every other room's state too.

Entities with no room association (e.g. base-unit-level identity or health
sensors) are never registered here - rediscovery only ever touches
room-scoped entities.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PlatformEntities:
    """One platform's (climate/sensor/number/binary_sensor) live entities
    for a config entry, grouped by the room_id they belong to."""

    def __init__(self, add_entities) -> None:
        self._add_entities = add_entities
        self.by_room: dict[str, list] = {}

    def add_room(self, room_id: str, entities: list) -> None:
        """Register and add a room's freshly built entities, if any."""
        if not entities:
            return
        self.by_room.setdefault(room_id, []).extend(entities)
        self._add_entities(entities)

    async def remove_room(self, room_id: str) -> None:
        """Remove every entity previously registered for `room_id`.

        A no-op if the room was never tracked here (e.g. it never resolved
        to any entity on this platform to begin with). `force_remove=True`
        also drops the entity registry entry, matching a room that the
        device itself no longer reports - it is gone, not just unavailable.
        """
        entities = self.by_room.pop(room_id, [])
        for entity in entities:
            try:
                await entity.async_remove(force_remove=True)
            except Exception:
                _LOGGER.debug(
                    "Failed to remove entity %s for room %s during rediscovery",
                    getattr(entity, "entity_id", entity),
                    room_id,
                    exc_info=True,
                )


def register_platform(
    hass: HomeAssistant, entry_id: str, platform_name: str, add_entities
) -> PlatformEntities:
    """Create the tracking registry for one platform of one config entry."""
    entry_data = hass.data[DOMAIN][entry_id]
    registry = PlatformEntities(add_entities)
    entry_data.setdefault("platform_entities", {})[platform_name] = registry
    return registry
