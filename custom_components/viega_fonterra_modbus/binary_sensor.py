"""Binary sensor platform exposing the base-unit error indicator.

spec.md 13 requires that a non-zero base-unit error code activates a
dedicated error indicator, separate from the raw/human-readable error code
sensor exposed by sensor.py.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MIN_SCAN_INTERVAL
from .device import build_device_info
from .entity_tracking import register_platform
from .modbus_handler import ViegaModbusClient
from .polling import PollingGate
from .registers import BASE_UNIT_REGISTERS, actor_registers, room_actor_numbers

SCAN_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)

#: Synthetic "room" key the circulation pump entity (module-level, not
#: room-scoped) is tracked under, so rediscovery can rebuild it through the
#: same `PlatformEntities` machinery used for real rooms.
PUMP_TRACKING_KEY = "__circulation_pump__"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the base-unit error indicator and per-actuator position sensors."""
    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    async_add_entities([ViegaBaseUnitErrorBinarySensor(entry.entry_id)])

    registry = register_platform(hass, entry.entry_id, "binary_sensor", async_add_entities)
    for room_id, room_config in rooms.items():
        registry.add_room(room_id, build_room_entities(entry.entry_id, room_id, room_config))

    pump_entity = build_pump_entity(entry.entry_id, rooms)
    if pump_entity is not None:
        registry.add_room(PUMP_TRACKING_KEY, [pump_entity])


def build_room_entities(
    entry_id: str, room_id: str, room_config: object
) -> list["ViegaActuatorPositionBinarySensor"]:
    """Build every actuator-position entity a single room contributes.

    Shared by the initial `async_setup_entry` above and by the explicit
    rediscovery action (`rediscovery.py`, spec.md 16a).
    """
    if not isinstance(room_config, dict):
        return []
    return _actor_position_sensors(SimpleNamespace(entry_id=entry_id), {room_id: room_config})


def build_pump_entity(
    entry_id: str, rooms: dict[str, object]
) -> "ViegaCirculationPumpBinarySensor | None":
    """Build the single circulation-pump entity for the whole module, or
    `None` when no room currently has a used actuator (spec.md 5c)."""
    addresses = _all_actuator_position_addresses(rooms)
    return ViegaCirculationPumpBinarySensor(entry_id, addresses) if addresses else None


def _all_actuator_position_addresses(rooms: dict[str, object]) -> dict[int, int]:
    """Return every used actuator's number mapped to its position register.

    "Used" means actually assigned to a room by discovery (spec.md 4a/5c),
    not every one of the device's up to 12 physical actuator slots - an
    actuator with no room association contributes nothing to the
    circulation-pump indicator. Deduplicated by actuator number in case a
    (malformed) manual room mapping listed the same actuator twice.
    """
    addresses: dict[int, int] = {}
    for room_config in rooms.values():
        if not isinstance(room_config, dict):
            continue
        for actuator_number in room_actor_numbers(room_config):
            if actuator_number in addresses:
                continue
            try:
                addresses[actuator_number] = actor_registers(actuator_number)["position"]
            except ValueError:
                continue
    return addresses


def _actor_position_sensors(
    entry: ConfigEntry, rooms: dict[str, object]
) -> list["ViegaActuatorPositionBinarySensor"]:
    """Build an open/closed binary sensor for every actuator of every room.

    The device manual (page 91, "Aktor N Stellung") documents this register
    as strictly binary - `0 = geschlossen, 1 = offen` - not a percentage
    (spec.md 5a previously described it as one; that table entry was wrong
    and has been corrected to match the manual).
    """
    sensors: list[ViegaActuatorPositionBinarySensor] = []
    for room_id, room_config in rooms.items():
        if not isinstance(room_config, dict):
            continue
        room_name = room_config.get("name", room_id)
        for actor_number in room_actor_numbers(room_config):
            try:
                registers = actor_registers(actor_number)
            except ValueError:
                continue
            sensors.append(
                ViegaActuatorPositionBinarySensor(
                    entry.entry_id,
                    room_id,
                    actor_number,
                    room_name,
                    registers["position"],
                )
            )
    return sensors


class ViegaBaseUnitErrorBinarySensor(BinarySensorEntity, RestoreEntity):
    """Report whether the base unit currently reports a non-zero error code."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._address = BASE_UNIT_REGISTERS["error_code"]
        self._attr_unique_id = f"{entry_id}_base_unit_error"
        self._attr_translation_key = "base_unit_error"
        self._attr_is_on = False
        self._polling_gate = PollingGate()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value across restarts (spec.md 15)."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        self._attr_is_on = last_state.state == "on"

    async def async_update(self) -> None:
        entry_data = self.hass.data[DOMAIN][self._entry_id]
        if "polling" not in entry_data and not self._polling_gate.is_due(self.hass, self._entry_id):
            return
        client = entry_data["client"]
        try:
            shared = entry_data.get("polling")
            values = await (shared.read(self.hass, self._entry_id, "input", self._address, 1)
                            if shared else client.read_input_registers(self._address, 1))
        except Exception:
            return
        if not values or values[0] == ViegaModbusClient.ERROR_SENTINEL:
            return
        self._attr_is_on = values[0] != 0

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)


class ViegaActuatorPositionBinarySensor(BinarySensorEntity, RestoreEntity):
    """Report an actuator's open/closed state (manual: 0=closed, 1=open)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(
        self,
        entry_id: str,
        room_id: str,
        actor_number: int,
        room_name: str,
        address: int,
    ) -> None:
        self._entry_id = entry_id
        self._address = address
        self._attr_unique_id = f"{entry_id}_{room_id}_actor{actor_number}_position"
        self._attr_translation_key = "actuator_position"
        self._attr_translation_placeholders = {
            "room": str(room_name),
            "actor": str(actor_number),
        }
        self._attr_is_on = None
        self._polling_gate = PollingGate()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value across restarts (spec.md 15)."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        self._attr_is_on = last_state.state == "on"

    async def async_update(self) -> None:
        if not self._polling_gate.is_due(self.hass, self._entry_id):
            return
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        try:
            shared = self.hass.data[DOMAIN][self._entry_id].get("polling")
            values = await (shared.read(self.hass, self._entry_id, "input", self._address, 1)
                            if shared else client.read_input_registers(self._address, 1))
        except Exception:
            return
        if not values or values[0] == ViegaModbusClient.ERROR_SENTINEL:
            return
        self._attr_is_on = values[0] == 1

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)


class ViegaCirculationPumpBinarySensor(BinarySensorEntity, RestoreEntity):
    """Derived on/off indicator for an externally controlled circulation pump.

    The Viega register map has no dedicated pump register - this is a
    computed indicator, not a device read/write (spec.md 5c). It is on
    whenever any used actuator is open and off once every one of them is
    confirmed closed. Each actuator's own raw position reading is debounced
    (`PUMP_DEBOUNCE_READS` identical consecutive reads) before it is allowed
    to affect the aggregate, so one noisy/transitional read cannot toggle
    the pump. Intended to drive the user's own automation for a physically
    separate pump relay, not to write anything back to the base unit.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    #: Number of consecutive identical raw reads an actuator's position
    #: register must produce before that value is accepted into the
    #: aggregate (spec.md 5c).
    PUMP_DEBOUNCE_READS = 3

    def __init__(self, entry_id: str, actuator_addresses: dict[int, int]) -> None:
        """`actuator_addresses` maps actuator number -> its position register."""
        self._entry_id = entry_id
        self._actuator_addresses = actuator_addresses
        self._attr_unique_id = f"{entry_id}_circulation_pump"
        self._attr_translation_key = "circulation_pump"
        self._attr_is_on = None
        # Per actuator: the most recently read raw value ("candidate"), how
        # many consecutive reads have produced it, and the last value that
        # actually reached the debounce threshold ("accepted" - what the
        # aggregate is computed from).
        self._candidate: dict[int, int | None] = dict.fromkeys(actuator_addresses)
        self._candidate_count: dict[int, int] = dict.fromkeys(actuator_addresses, 0)
        self._accepted: dict[int, int | None] = dict.fromkeys(actuator_addresses)
        self._polling_gate = PollingGate()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value across restarts (spec.md 15)."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        self._attr_is_on = last_state.state == "on"

    async def async_update(self) -> None:
        if not self._polling_gate.is_due(self.hass, self._entry_id):
            return
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        shared = self.hass.data[DOMAIN][self._entry_id].get("polling")

        for actuator_number, address in self._actuator_addresses.items():
            try:
                values = await (shared.read(self.hass, self._entry_id, "input", address, 1)
                                if shared else client.read_input_registers(address, 1))
            except Exception:
                # A failed/timed-out read must not disturb this actuator's
                # debounce progress or force a spurious pump-state change.
                continue
            if not values or values[0] == ViegaModbusClient.ERROR_SENTINEL:
                continue

            raw = values[0]
            if raw == self._candidate[actuator_number]:
                self._candidate_count[actuator_number] += 1
            else:
                self._candidate[actuator_number] = raw
                self._candidate_count[actuator_number] = 1
            if self._candidate_count[actuator_number] >= self.PUMP_DEBOUNCE_READS:
                self._accepted[actuator_number] = raw

        settled = [value for value in self._accepted.values() if value is not None]
        if not settled:
            self._attr_is_on = None
        else:
            self._attr_is_on = any(value == 1 for value in settled)

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)
