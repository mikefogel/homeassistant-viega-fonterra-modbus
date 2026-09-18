"""The Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .modbus_handler import ModbusClientError, ViegaModbusClient
from .polling import SharedPolling
from .room_mapping import RoomMappingDiscovery
from .registers import (
    BASE_UNIT_REGISTERS,
    actor_registers,
    decode_text_registers,
    resolve_room_number,
    room_registers,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Viega Fonterra from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    timeout = float(entry.data.get("modbus_timeout", 5))
    client = ViegaModbusClient(entry.data["host"], entry.data["port"], timeout=timeout)
    try:
        await client.connect()
    except ModbusClientError as err:
        # Let Home Assistant retry with backoff instead of leaving the entry
        # stuck in a hard error state (spec.md 6a: a failed module must not
        # block the rest of the setup or require a manual reload).
        raise ConfigEntryNotReady(
            f"Could not connect to {entry.data['host']}:{entry.data['port']}: {err}"
        ) from err

    # Discovery is deliberately completed before forwarding platforms: entity
    # constructors must only see the persisted, resolved topology. Rooms are
    # (re)discovered from the device's own actor "Raum ID" and room-name
    # registers (manual pages 90-91) on every setup, since that reflects the
    # actual installed topology; the manually configured/options-flow rooms
    # are used only as a fallback when the device can't be read (e.g. some
    # actuators unreachable this cycle).
    rooms = entry.options.get("rooms", {})
    try:
        discovered = await RoomMappingDiscovery.discover_from_device(client)
    except Exception:
        discovered = {}
        _LOGGER.debug("Automatic room discovery failed", exc_info=True)
    if discovered:
        rooms = discovered
    elif not rooms:
        # Note: the options flow can only edit rooms that already exist in
        # `rooms` (spec.md "Editing an existing module") - it has no "add a
        # room from scratch" field, so it cannot recover from this case.
        # Reloading once the device/actuators are reachable is currently the
        # only way forward; do not promise an options-flow fix here.
        _LOGGER.warning(
            "Viega Fonterra entry %s: no rooms discovered from the device and "
            "none configured previously; no room, climate, or number "
            "entities will be created until at least one actuator reports a "
            "valid room ID. Check that Modbus TCP is enabled on the base unit "
            "and that it is reachable, then reload this integration entry",
            entry.entry_id,
        )
    identity: dict[str, object] = {}
    for key, count in (("wlan_serial_number", 5), ("base_unit_serial_number", 5), ("base_unit_name", 12)):
        try:
            values = await client.read_input_registers(BASE_UNIT_REGISTERS[key], count)
            if values and values[0] != ViegaModbusClient.ERROR_SENTINEL:
                identity[key] = decode_text_registers(values)
        except Exception:
            _LOGGER.debug("Initial identity read failed for %s", key, exc_info=True)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "host": entry.data["host"],
        "port": entry.data["port"],
        "client": client,
        "device_name": entry.data.get("device_name", "Fonterra"),
        "polling_interval": entry.data.get("polling_interval", 30),
        "modbus_timeout": timeout,
        "rooms": rooms,
        "device_id": entry.options.get("device_id", ""),
        "polling": SharedPolling(),
        "identity": identity,
    }

    update_entry = getattr(hass.config_entries, "async_update_entry", None)
    if update_entry and (
        rooms != entry.options.get("rooms", {}) or identity
    ):
        update_entry(
            entry,
            options={**entry.options, "rooms": rooms, "_identity": identity},
        )
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _log_resolved_topology(entry.entry_id, rooms, identity)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Set up Viega Fonterra entry %s", entry.entry_id)
    return True


def _log_resolved_topology(
    entry_id: str, rooms: dict[str, object], identity: dict[str, object]
) -> None:
    """Log which registers each room/actor decision was derived from.

    This is the "what did the integration decide, and why" counterpart to
    the raw TX/RX frame log in `modbus_handler.py`: it lets an installer
    cross-check a room's name, its assigned actuator(s), and the exact
    registers backing its entities against the physical installation and
    the device manual, both gated by the same `logger.logs:
    custom_components.viega_fonterra_modbus: debug` setting (see README).
    """
    _LOGGER.debug("Entry %s: resolved base-unit identity=%s", entry_id, identity)
    if not rooms:
        _LOGGER.debug("Entry %s: no rooms in the resolved topology", entry_id)
        return
    for room_id, room_config in rooms.items():
        if not isinstance(room_config, dict):
            _LOGGER.debug(
                "Entry %s: room %s has a non-dict config=%r, skipped",
                entry_id, room_id, room_config,
            )
            continue
        room_number = resolve_room_number(room_id, room_config)
        registers = room_registers(room_number) if room_number else {}
        actor = room_config.get("actor")
        actor_numbers = actor if isinstance(actor, list) else (
            [actor] if actor is not None else []
        )
        actor_regs = {}
        for actor_number in actor_numbers:
            try:
                actor_regs[actor_number] = actor_registers(int(actor_number))
            except (TypeError, ValueError):
                continue
        _LOGGER.debug(
            "Entry %s: room %s -> name=%r room_number=%s actor(s)=%s sensor=%s | "
            "room registers (PDU) current_temperature=%s error_code=%s "
            "power_level=%s target_temperature=%s | actor registers (PDU)=%s",
            entry_id,
            room_id,
            room_config.get("name", room_id),
            room_number,
            actor,
            room_config.get("sensor"),
            registers.get("current_temperature"),
            registers.get("error_code"),
            registers.get("power_level"),
            registers.get("target_temperature"),
            actor_regs,
        )


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after settings are changed in the UI."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry so the module (and its device) can be removed.

    Must succeed even when the device is offline or its socket is already
    broken (spec.md 6a/13: a module must always be deletable through the
    Home Assistant UI).
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        client = entry_data.get("client") if entry_data else None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                # A disconnect failure must never block removal.
                _LOGGER.warning(
                    "Error disconnecting Viega client for %s", entry.entry_id, exc_info=True
                )
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing this module's device from the device page.

    Without this hook, Home Assistant does not show a "Delete" control for a
    device on its own device page while the owning config entry is still
    loaded - only removing the whole config entry (module) would work. Each
    config entry here always corresponds to exactly one device (the Fonterra
    module, `device.py::build_device_info`), so unlinking it is always safe;
    removing the module entirely still happens through the normal config
    entry removal flow (spec.md 6a/13).
    """
    return True
