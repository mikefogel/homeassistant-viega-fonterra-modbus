"""Explicit, user-triggered rediscovery of the room/actuator topology
(spec.md 16a).

Re-reads the same actuator Raum-ID and room-name registers that
`room_mapping.py` already uses for the one-time discovery at setup, diffs
the result against the cached topology, and updates only the entities for
rooms that actually changed - added, removed, renamed, or reassigned to a
different set of actuators - without reloading the config entry (which
would drop the shared Modbus connection and disturb every other room).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import binary_sensor as binary_sensor_platform
from . import climate as climate_platform
from . import number as number_platform
from . import sensor as sensor_platform
from .const import DOMAIN
from .registers import room_actor_numbers
from .room_mapping import RoomMappingDiscovery

_LOGGER = logging.getLogger(__name__)

EVENT_REDISCOVERY_COMPLETE = f"{DOMAIN}_rediscovery"

_BUILDERS = {
    "climate": climate_platform.build_room_entities,
    "number": number_platform.build_room_entities,
    "sensor": sensor_platform.build_room_entities,
    "binary_sensor": binary_sensor_platform.build_room_entities,
}


@dataclass
class RediscoveryReport:
    """Summary of what changed between the cached and freshly read topology."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    renamed: dict[str, tuple[str, str]] = field(default_factory=dict)
    reassigned: dict[str, tuple[list, list]] = field(default_factory=dict)
    failed: bool = False
    error: str | None = None

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.renamed or self.reassigned)

    def as_dict(self) -> dict[str, object]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "renamed": dict(self.renamed),
            "reassigned": dict(self.reassigned),
            "failed": self.failed,
            "error": self.error,
        }


def _room_name(room_config: object, room_id: str) -> str:
    return room_config.get("name", room_id) if isinstance(room_config, dict) else room_id


def diff_topology(
    old_rooms: dict[str, object], new_rooms: dict[str, object]
) -> RediscoveryReport:
    """Compare a previously cached room mapping with a freshly read one."""
    report = RediscoveryReport()
    old_ids = set(old_rooms)
    new_ids = set(new_rooms)
    report.added = sorted(new_ids - old_ids)
    report.removed = sorted(old_ids - new_ids)

    for room_id in sorted(old_ids & new_ids):
        old_config = old_rooms.get(room_id)
        new_config = new_rooms.get(room_id)

        old_name = _room_name(old_config, room_id)
        new_name = _room_name(new_config, room_id)
        if old_name != new_name:
            report.renamed[room_id] = (old_name, new_name)

        old_actors = room_actor_numbers(old_config) if isinstance(old_config, dict) else []
        new_actors = room_actor_numbers(new_config) if isinstance(new_config, dict) else []
        if old_actors != new_actors:
            report.reassigned[room_id] = (old_actors, new_actors)

    return report


async def async_rediscover_entry(hass: HomeAssistant, entry: ConfigEntry) -> RediscoveryReport:
    """Re-read the device's actuator/room-name registers and reconcile
    entities to match, in place, without reloading `entry`."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is None:
        return RediscoveryReport(failed=True, error="config entry is not loaded")

    client = entry_data["client"]
    polling = entry_data.get("polling")
    old_rooms = entry_data.get("rooms", {})

    try:
        if polling is not None:
            # Reuses the existing connection and the same lock every
            # regular poll cycle already serializes through - not a second
            # connection or a second poller (spec.md 16a).
            new_rooms = await polling.run_exclusive(
                lambda: RoomMappingDiscovery.discover_from_device(client)
            )
        else:
            new_rooms = await RoomMappingDiscovery.discover_from_device(client)
    except Exception as err:
        _LOGGER.warning(
            "Rediscovery failed for entry %s: %s", entry.entry_id, err, exc_info=True
        )
        return RediscoveryReport(failed=True, error=str(err))

    if not new_rooms:
        # A live discovery that comes back empty must never silently
        # replace a previously working topology (spec.md 4a) - this is
        # exactly the "device unreachable this cycle" case the fallback
        # mapping exists for, not a real "all rooms removed" result.
        _LOGGER.warning(
            "Rediscovery for entry %s found no rooms; keeping the last known "
            "topology instead of clearing it",
            entry.entry_id,
        )
        return RediscoveryReport(failed=True, error="no rooms discovered from the device")

    report = diff_topology(old_rooms, new_rooms)
    entry_data["rooms"] = new_rooms
    _update_config_entry_rooms(hass, entry, new_rooms)
    await _reconcile_entities(hass, entry.entry_id, old_rooms, new_rooms, report)
    _log_and_fire_report(hass, entry.entry_id, report)
    return report


def _update_config_entry_rooms(
    hass: HomeAssistant, entry: ConfigEntry, rooms: dict[str, object]
) -> None:
    update_entry = getattr(hass.config_entries, "async_update_entry", None)
    if update_entry is None:
        return
    update_entry(entry, options={**entry.options, "rooms": rooms})


async def _reconcile_entities(
    hass: HomeAssistant,
    entry_id: str,
    old_rooms: dict[str, object],
    new_rooms: dict[str, object],
    report: RediscoveryReport,
) -> None:
    """Add, remove, or rebuild only the entities for rooms that changed."""
    entry_data = hass.data[DOMAIN][entry_id]
    platforms = entry_data.get("platform_entities", {})

    for room_id in report.removed:
        for registry in platforms.values():
            await registry.remove_room(room_id)

    changed_room_ids = list(
        dict.fromkeys(report.added + list(report.renamed) + list(report.reassigned))
    )
    for room_id in changed_room_ids:
        room_config = new_rooms.get(room_id)
        for platform_name, registry in platforms.items():
            builder = _BUILDERS.get(platform_name)
            if builder is None:
                continue
            await registry.remove_room(room_id)
            registry.add_room(room_id, builder(entry_id, room_id, room_config))

    await _rebuild_pump_if_needed(entry_id, old_rooms, new_rooms, platforms)


async def _rebuild_pump_if_needed(
    entry_id: str,
    old_rooms: dict[str, object],
    new_rooms: dict[str, object],
    platforms: dict[str, object],
) -> None:
    """The circulation-pump indicator (spec.md 5c) is module-level, derived
    from every room's actuator set combined - rebuild it whenever that
    combined set changes, regardless of which single room changed."""
    registry = platforms.get("binary_sensor")
    if registry is None:
        return
    if binary_sensor_platform._all_actuator_position_addresses(
        old_rooms
    ) == binary_sensor_platform._all_actuator_position_addresses(new_rooms):
        return
    await registry.remove_room(binary_sensor_platform.PUMP_TRACKING_KEY)
    pump_entity = binary_sensor_platform.build_pump_entity(entry_id, new_rooms)
    if pump_entity is not None:
        registry.add_room(binary_sensor_platform.PUMP_TRACKING_KEY, [pump_entity])


def _log_and_fire_report(hass: HomeAssistant, entry_id: str, report: RediscoveryReport) -> None:
    if not report.changed:
        _LOGGER.info("Rediscovery for entry %s found no topology changes", entry_id)
    else:
        _LOGGER.warning(
            "Rediscovery for entry %s: added=%s removed=%s renamed=%s reassigned=%s",
            entry_id, report.added, report.removed, report.renamed, report.reassigned,
        )
    hass.bus.async_fire(EVENT_REDISCOVERY_COMPLETE, {"entry_id": entry_id, **report.as_dict()})
