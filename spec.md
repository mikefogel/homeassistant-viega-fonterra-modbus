# Viega Fonterra Smart Control – system specification

## 1. Purpose

This repository defines a Home Assistant custom integration for Viega Fonterra Smart Control installations. It must support local Modbus TCP communication, room-level discovery, multiple device installation, and a thermostat model for basic automation.

## 2. Core objectives

- Connect to one or more Viega Fonterra Smart Control devices over Modbus TCP.
- Discover room-to-actor and room-to-sensor mappings when the first read is performed.
- Represent room thermostats as entities.
- Support multi-device configuration in a single installation.
- Keep a modular register model aligned with the device documentation.

## 3. Device model

Each device represents one Fonterra Smart Control controller and is identified by:

- device_id
- device_name (human-readable name, configurable by user)
- wlan_module_serial_number
- base_unit_serial_number
- base_unit_name (human-readable name reported by the base unit)
- base_unit_error_code
- host
- port
- polling_interval (in seconds, default 30)
- modbus_timeout (in seconds, default 5)
- rooms
- actors
- sensors

A room can map to:

- room_id
- room_name (human-readable name from device configuration)
- actor_id
- sensor_id
- thermostat settings
- target temperature
- current temperature

## 3a. Module and base-unit identity

The integration must read and retain the identity and status information of both
the WLAN module and the Fonterra base unit. These values belong to the module's
Home Assistant device and must not be confused with the user-editable device
name:

- WLAN module serial number
- base-unit serial number
- base-unit designation/name
- base-unit error code

The serial numbers and base-unit designation must be exposed as diagnostic
read-only entities and as device diagnostics where Home Assistant supports
those metadata fields. The base-unit error code must be exposed as a diagnostic
sensor using the raw code and, when available, its human-readable description.
The existing base-unit error indicator must derive its state from this code:
an active non-zero code indicates an error, while the documented no-error value
indicates normal operation.

Identity values must be discovered during the first successful device read and
refreshed according to the configured polling interval. The last valid value
must be retained when a read returns `-99`, times out, or otherwise fails. A
missing identity register must not prevent room, sensor, or thermostat entities
from being created; it must instead be reported by the diagnostic status.

Diagnostic entities (identity, base-unit error, per-room diagnosis) must update
through the same polling cycle as the room and Climate entities — no diagnostic
entity may perform an additional, independent Modbus poll of its own. A
successful poll distributes the newly read error code, identity values, and
textual status to every entity of the config entry that needs them.

The register map must define the address, encoding, and length for each serial
number and text field. Serial numbers and names may span multiple registers.

Text fields (serial numbers, base-unit name) are decoded as two ASCII
characters per register using Big-Endian byte order within each register,
with trailing NUL and space characters stripped. This encoding is confirmed
against real hardware: decoding with the previously documented
Little-Endian order scrambled every string by swapping the two characters
within each register (e.g. "Bad" came back as "aBd" and "Dachgeschoss" as
"aDhcegcsohss"). This encoding is normative and must be covered by fixtures
containing normal text and padding. The same decoder must be used
consistently by `ViegaBaseUnitIdentitySensor` and all future text-register
entities.

### 3b. Base-unit and room error codes

The base-unit error code register (`error_code`, manual address `30024`) and
each room's own error register (manual `30051`/`30053`/`...`/`30073`, one per
room, §5b) are `0` when no error/warning is active (see §3a); any other value
is active. A single code-to-description table (`BASE_UNIT_ERROR_CODES` in
`registers.py`) maps known codes to human-readable text, since the two
registers share one code space per the device manual's "Fehlercodes" table
(page 94): codes `3`, `4`, `5`, `6`, `7`, `9`, `10` are base-unit-scoped
faults/warnings, and codes `21`, `22`, `24` are room-scoped (thermostat
connectivity/battery). A room's diagnostic text entity (§10) must read that
room's own error register, not the shared base-unit one, so two different
rooms' diagnostics do not always show identical text. Every code not in the
table must render as `"Unknown error (code N)"`. New codes must be appended
to the table rather than guessed inline in the entity layer.

## 4. Initial discovery requirement

On the first successful connection to a device, the system must resolve the
room-to-actor association before sensor and thermostat entities are created.
§4a defines the only supported discovery mechanism: reading the association
directly from the device's own registers. An earlier version of this
requirement instead described resolving an already-assembled, manually typed
`{"rooms": {...}}` mapping dictionary — matching how rooms were once
collected at setup time (§6b) before that was replaced by automatic
discovery. That code path has been removed and must not be reintroduced as
the primary discovery mechanism; a manually typed mapping remains only as
the fallback §4a itself describes.

The mapping must support non-1:1 relationships. One room may map to multiple actors and sensors. One actor may also participate in more than one room configuration, depending on the actual device topology.

When a room maps to a list of actors, its Climate entity (§5) uses only the
first actor as the primary control surface, matching "the primary control
surface is the room's Climate entity" in §5a. Every additional actor in the
list must still be exposed, as linked position and return-temperature
sensors carrying that actor's own registers — it must not be silently
dropped.

### 4a. Automatic discovery via the actuator Raum-ID register

The device itself is the source of truth for the room mapping above; it must
not be left to guesswork in a manually typed configuration field. Each of the
up to 12 actuators reports its own current room assignment in a dedicated
input register (manual `30252`/`30255`/`...`/`30285`, i.e. actuator base
address `+2`, PDU per §5b): an `int16` in range `1`-`12` naming the room that
actuator serves (device manual page 91, "Aktor N Raum ID"). Each room's
display name is likewise stored on the device as a 24-character string
register (manual `30074`/`30086`/`...`/`30206`, one set of 12 registers per
room, spaced 12 registers apart — device manual page 90).

On every `async_setup_entry`, after connecting, the integration must read all
12 actuators' position/return-temperature/Raum-ID registers (one 3-register
read per actuator) and every reporting actuator's room's name register, and
build the room mapping from that — actor-to-room association and room names
both come from the device, not from user input. A manually configured room
mapping (§6b) is used only as a fallback when the device can't be read for a
given setup cycle (e.g. actuators temporarily unreachable); it must not
silently override a successful live discovery, since a manual mapping can
drift from the physical installation (an actuator moved to a different room,
a room renamed on the base unit) with nothing to catch the mismatch.

## 5. Room thermostat specification

Each room thermostat entity must expose:

 room_id
 current_temperature
 target_temperature
 device_class = "temperature"

### 5a. Room thermostat capability matrix

The integration must expose the following room and controller information. The
primary control surface is the room's Climate entity wherever Home Assistant's
Climate model supports the value. Values that do not have a native Climate
property must be exposed as linked entities belonging to the same Home
Assistant device and carrying the same `room_id`.

The room thermostat must use Home Assistant's native `ClimateEntity` presentation
so it appears as a thermostat rather than as separate temperature sensors. The
visual and behavioral model should follow the Daikin Onecta climate integration
([reference implementation](https://github.com/jwillemsen/daikin_onecta/blob/master/custom_components/daikin_onecta/climate.py)):

- The Climate entity is the single primary control surface for the room. Its
  state must provide both `current_temperature` (Ist-Temperatur) and
  `target_temperature` (Soll-Temperatur), in degrees Celsius.
- The entity must set `temperature_unit`,
  `target_temperature_step`, `min_temp`, and `max_temp` from the Viega register
  definition. These values allow the standard Home Assistant thermostat card to
  render the temperature control with the correct range and increment.
- `ClimateEntityFeature.TARGET_TEMPERATURE` must be advertised only when a
  writable target-temperature holding register is configured and supported.
  Read-only rooms must still expose the current and target values when available,
  but must not show a non-functional temperature control.
- `async_set_temperature` must accept the Home Assistant `temperature` service
  field, convert Celsius to the register's declared scale, validate the declared
  range, write the holding register, and update `target_temperature` only after
  the Modbus write is acknowledged. A failed write must leave the previous target
  value unchanged and be reported through the integration's normal diagnostics.
- After a successful write, the entity may update the displayed target
  optimistically, but the next read cycle must reconcile it with the device value.
  The current temperature must always come from the room sensor and must never be
  replaced with the requested target.
- The entity must expose the normal Climate state (`hvac_mode`) and only advertise
  additional features such as presets when their registers are actually
  readable and writable. Unsupported controls must not be rendered as available
  controls.
- Use a stable unique ID based on the config entry and `room_id`; use the
  configured room name as the display name and the module's configured device
  information for device association. Renaming must not create a second
  thermostat entity.

| Requirement | Home Assistant representation | Behavior |
| --- | --- | --- |
| Show current room temperature | Climate `current_temperature` | Read from the room sensor |
| Show target temperature | Climate `target_temperature` | Read from the target register |
| Change target temperature | Climate `climate.set_temperature` | Write to the target holding register |
| Show output power level | Linked sensor, with optional Climate attribute | Read the actuator power-level register |
| Change output power level | Linked Number entity | Write the actuator power-level holding register |
| Show manifold flow temperature | Linked temperature sensor | Read the manifold flow register |
| Show actuator return temperature | Linked temperature sensor | Read the actuator return register |
| Show room name | Climate and linked entity names | Use the configured room name |
| Show room number | Diagnostic/entity attribute and unique room metadata | Preserve the configured `room_id` or room number |
| Show actuator position | Linked binary sensor (`open`/`closed`) | Read the actuator-position register |
| Show whether the base unit has an error | Linked binary sensor or diagnostic sensor | `on`/error when any base-unit error is active |
| Show which base-unit error exists | Linked diagnostic text sensor | Expose the error code and human-readable message |
| Show operating mode | Climate `hvac_mode` where applicable | Read the active operating mode |
| Change operating mode | Climate `set_hvac_mode` | Write the operating-mode holding register |
| Show profile mode | Climate preset or linked Select entity | Read the active profile mode |
| Change profile mode | Climate `set_preset_mode` or linked Select entity | Write the profile-mode holding register |

The actuator-position register (manual `30250`/`30253`/`...`/`30283`, one per
actuator, page 91) is `int16` with exactly two documented values - `0 =
geschlossen` (closed) and `1 = offen` (open) - not a percentage; a prior
version of this table incorrectly described it as one and must not be
reintroduced. It is exposed as a binary sensor with device class `opening`
(`on` = open), one per actuator.

The manifold flow-temperature register (manual `30025`, page 89) is measured
once for the whole base unit, not per room. It must be exposed as a single
linked sensor on the module's Home Assistant device, not duplicated as a
separate per-room entity, even though every room's Climate entity may read
the same register for its own `flow_temperature` attribute for convenience.

### 5a.1. Heating and cooling operation

The thermostat must also model the room's heating/cooling operating function,
not only display two temperature values. The standard Home Assistant Climate
card must be able to show the current operating mode and, where the controller
supports it, let the user switch between:

- `HVACMode.HEAT` for heating,
- `HVACMode.COOL` for cooling, and
- `HVACMode.OFF` for standby/frost protection.

The Viega manual confirms exactly these three modes in holding register `40001`
(manual page 91): raw `0` = standby, raw `1` = heating, and raw `2` = cooling.
Therefore `heat_cool`/automatic mode must not be advertised. The manual
describes automatic changeover only as an external installation function using
the optional relay box and its Change-over contact (manual pages 11 and 21);
it is not a fourth Modbus operating-mode value.

`hvac_mode` must reflect the value read from the device, and
`async_set_hvac_mode` must validate the requested mode, translate it to the
documented register value, perform the write, and update the entity state only
after an acknowledged response. Selecting a new mode must not change
`current_temperature` or `target_temperature`; those remain the measured
Ist-Temperatur and configured Soll-Temperatur. The target-temperature control
must remain available in every operating mode in which the device reports a
writable target setpoint.

The register mapping must document the following operating-mode values:

| Climate mode | Register | Raw value | Meaning |
| --- | --- | --- | --- |
| `off` | holding `40001` (PDU `0`) | `0` | Standby; frost protection remains active |
| `heat` | holding `40001` (PDU `0`) | `1` | Regulation in heating mode |
| `cool` | holding `40001` (PDU `0`) | `2` | Regulation in cooling mode |

All three values are readable through function `0x03` and writable through
Modbus function `0x10` (Write Multiple Registers, quantity `1`) — see §5b
for the confirmed wire example this is based on. Unknown raw values must be
reported diagnostically and must not be silently mapped to a different
mode. Automatic changeover must not be modelled as `HVACMode.HEAT_COOL`
unless a future Viega manual defines such a Modbus value.

All linked entities must use stable unique IDs based on the module entry ID and
`room_id`, not on the editable room name. Renaming a room must therefore change
display names without creating duplicate entities. This applies to every
platform. The Climate entity and all
linked entities must reference the same Home Assistant device registry entry,
using the module's configured `device_name` (§6a) as the device's display
name — never a fixed string, so multiple modules remain distinguishable in
the device registry.

The operating-mode and profile-mode registers (holding `40001`/`40002`) are
defined on the "Basiseinheit" (base unit), not per room (manual page 92):
there is exactly one of each for the whole installation. Every room's Climate
entity reads and writes the same shared registers, so changing `hvac_mode` or
`preset_mode` from any one room's thermostat card changes it for every room
at once; this matches the physical device, which has no per-room heating/
cooling or profile-mode control, and is not a bug in the integration.

The operating-mode and profile-mode value sets are based on the Viega manual.
The operating-mode mapping is `0 = standby`, `1 = heating`, and `2 = cooling`;
there is no documented automatic heating/cooling value. Profile mode uses
`0 = manual` ("Manuell"), `1 = profile` ("Profil"), and `2 = setback`
("Absenkbetrieb" — an automatic reduced-temperature mode), and is available
only in heating mode (manual page 91). The `preset_mode` values returned by
the Climate entity (`manual`/`profile`/`setback`) are stable, untranslated
identifiers; their user-facing labels must be localized through Home
Assistant's entity translation mechanism (`translation_key` plus
`entity.climate.<key>.state_attributes.preset_mode.state` in
`translations/*.json`), not hardcoded to English.

The base-unit error indicator ("Show whether the base unit has an error") and
the error code/description sensor ("Show which base-unit error exists") are
two distinct entities: a binary sensor that is `on` when the error code (§3b)
is non-zero, and a separate diagnostic sensor exposing the raw code plus its
description from the error-code table.

If a requested value is not supported by a particular firmware version or its
register address is not configured, the entity must not advertise a write
feature that cannot work. Readable values must remain available where possible,
and unavailable register values must be reported through the diagnostic status
without overwriting the last valid value.

### 5b. Required room register mapping

The room mapping must be able to define the registers needed by the capability
matrix. Register addresses and scaling are device-specific and must not be
guessed by the entity layer. The mapping may contain at least:

```python
"room_1": {
    "name": "Wohnzimmer",
    "room_number": 1,
    "actor": 1,
    "sensor": 10,
    "target_temperature_register": 50,
    "power_level_register": 49,
    "actuator_position_register": 249,
    "flow_temperature_register": 24,
    "return_temperature_register": 250,
}
```

    The values above are Modbus PDU addresses derived from the manual's one-based
    addresses: room 1 uses holding registers `40050`/`40051` for power and target
    temperature, input registers `30050`/`30051` for room value and error, and
    actuator 1 uses input registers `30250`/`30251` for position and return
    temperature (plus `30252` for its Raum-ID register, §4a). The base-unit
    operating and profile modes use holding registers `40001` and `40002`.

    The conversion from a manual (Modicon-style) address to a PDU address is:
    `pdu = manual_address - 40000` for holding registers (`4xxxx`) and
    `pdu = manual_address - 30000` for input registers (`3xxxx`) — i.e. the
    last four digits of the manual address *are* the PDU address, unchanged.
    This is confirmed by the device manual's own worked wire examples
    (`Fonterra Smart Control-de-DE.pdf`, "Beispiele", pages 94-95): manual
    `40001` is sent on the wire as PDU `0001`, manual `40053` as PDU `0035`
    (53), and manual `30250` as PDU `00FA` (250). A formula that instead
    treats `x0001` as PDU `0` (`pdu = manual_address - 40001` /
    `manual_address - 30001`, the more common Modicon convention, and a
    formula this document previously specified) does not match the manual's
    examples or real hardware and makes every register in `registers.py` off
    by exactly one from the device's actual map; it must never be
    reintroduced. Every address in this section and in `registers.py` must
    satisfy the `-40000`/`-30000` formula.

    A room mapping without an explicit `room_number` resolves it from the
    trailing digits of its `room_id` (e.g. `"room_1"` → `1`), so the minimal
    room example in §4/§6b (`name`/`actor`/`sensor` only) still gets working
    default registers via `room_registers()`. Room numbers 1 through 12 are
    supported, matching the register spacing above; a topology with more
    rooms or actuators is out of scope for this register map.

Each writable register must define its data type, valid range, and scaling. A
temperature register using tenths of a degree, for example, must declare a
scale of `10`; a percentage register must declare a range of `0` to `100`.
Writes must be acknowledged by the Modbus response before the entity state is
updated.
This entity represents a room-level thermostat and is the primary control surface for a room in Home Assistant.

The target temperature must be writable through the room's Modbus holding
register. Each room mapping may define:

```python
"target_temperature_register": 1200
```

When the user calls `climate.set_temperature`, the integration must write the
requested Celsius value multiplied by `10` as an unsigned 16-bit value using
Modbus function code `0x10` (Write Multiple Registers, quantity `1`, byte
count `2`) - confirmed by the manual's own worked wire example ("Beispiel 2
- Soll-Temperatur für Raum 2 setzen", `Fonterra Smart Control-de-DE.pdf`
page 95: `... 01 10 00 35 00 01 02 00 D2`) - then update the entity's target
temperature only after a successful write response. Every write this
integration performs (target temperature, power level, operating mode,
profile mode) must use function `0x10`, not `0x06`; no confirmed wire
example in the manual ever uses `0x06`. A room without a configured target
register must remain readable but must not advertise target-temperature
write support.

## 5c. Circulation pump indicator

The device manual defines no dedicated circulation-pump register — this
capability is entirely derived from the actuator-position registers already
defined in §4a/§5b, not a new register. It must be exposed as a single
binary sensor per config entry (device class `running`), one per module,
not one per room, since a module's circulation pump serves every room's
actuator together.

- The indicator is `on` when at least one of the module's *used* actuators
  (an actuator with a room association from discovery, §4a — not merely one
  of the device's up to 12 physical actuator slots) is confirmed open, and
  `off` once every used actuator is confirmed closed. These two conditions
  are exhaustive: there is no third state once at least one actuator has
  been read, only "unknown" before any actuator has been read at all.
- Each actuator's own raw position reading must be debounced before it may
  affect the aggregate: an actuator's contribution only updates once its
  position register has returned the **same** raw value on **3 consecutive
  reads** (`PUMP_DEBOUNCE_READS` in `binary_sensor.py`). A read that differs
  from the actuator's current in-progress candidate value resets that
  actuator's counter to `1` rather than incrementing it; a failed read or
  the `-99` error sentinel (§10) must be skipped entirely — it must neither
  advance nor reset that actuator's counter, and must never affect the
  aggregate. This debouncing is per actuator, independent of every other
  actuator's own debounce progress: the aggregate must switch to `on` as
  soon as any single actuator's debounced state is confirmed open, without
  waiting for other actuators to finish debouncing.
- Before any actuator has completed its first debounce cycle, the indicator
  must report an unknown/unavailable state (`is_on = None`), not `off` —
  reporting `off` before any real data has settled would misrepresent an
  unread pump as confirmed idle.
- This entity performs no Modbus write and controls nothing on the Viega
  device — it is a read-only aggregate meant to drive the user's own
  automation for a circulation pump that is wired and controlled outside
  the Fonterra system (e.g. a smart relay). It must not be modeled as a
  switch (§8): a write-capable entity with no real device-side effect is
  misleading and must not be reintroduced.

## 6. Multi-device support

The integration must allow multiple devices to be configured and stored independently. Each entry must remain separate and should not overwrite the others.

## 6a. Home Assistant UI configuration

The integration must provide a native Home Assistant configuration flow. Users
must be able to configure Viega modules through the Home Assistant UI without
editing YAML or JSON files manually.

### Adding a module

The setup form for each Viega module must provide these fields:

- `host`: IP address or DNS hostname of the Modbus TCP device, default
    `192.168.0.188`
- `port`: Modbus TCP port, default `502` (per the device manual: port `502`
    for a normal/DHCP network connection; `192.168.1.1` is only used in
    point-to-point mode)
- `device_name`: editable display name for the module
- `polling_interval`: polling interval in seconds
- `modbus_timeout`: Modbus response timeout in seconds

The `host` field must accept IPv4 addresses such as `192.168.1.10` and
resolvable hostnames such as `fonterra-01.local`. The connection must be
validated before the config entry is created. Invalid host, port, polling, or
timeout values must be reported in the form, and every error message the
form can show (a validation error or a failed connection) must be localized
in every language `translations/*.json` supports, not only English.

The combination of `host` and `port` must be unique across config entries:
attempting to add a module with a host/port already used by an existing
entry must be rejected (Home Assistant's standard unique-ID/
`already_configured` abort mechanism) rather than creating a second,
uncoordinated set of entities and Modbus connections against the same
physical device.

This form must not ask for a room mapping. Rooms are discovered
automatically from the device itself once it connects (§4a) and require no
user input to create a working module; requiring one here would make setup
depend on the user already knowing the installation's actor/sensor topology,
which is exactly what discovery exists to avoid guessing.

### Multiple modules

The UI must allow more than one Viega module to be configured in the same Home
Assistant installation. Every module must have its own config entry, device
registry entry, connection, polling schedule, and entities. A failure or reload
of one module must not overwrite or disable another module.

### Editing an existing module

An options flow must be available from each integration entry so users can edit
the following values after setup:

- module display name
- IP address or hostname
- Modbus TCP port
- polling interval
- Modbus timeout
- room names and room-to-actor/sensor assignments

After saving, the integration must reconnect using the new host or port and
apply the new settings without manual file edits. Entity unique IDs must remain
stable when only the display name changes. The configured module name must be
used as the Home Assistant device name, while configured room names remain the
entity names for the corresponding thermostats, sensors, and diagnostics.

A room's actor assignment can be a single actuator or a list of several (§4).
The options flow's room-editing fields must be able to represent and save
either shape; saving the form for any reason (even one unrelated to that
room) must never collapse a multi-actuator room's assignment down to a
single actuator.

The options flow must resolve `self.config_entry` through Home Assistant's
own `OptionsFlow` base class (via the flow's `handler`), not by accepting a
`config_entry` argument in its own `__init__` and assigning it directly -
that pattern is deprecated as of Home Assistant 2024.12 and is scheduled for
removal in 2025.12. `async_get_options_flow` may still receive `config_entry`
as a parameter (Home Assistant's calling convention), but must not pass it
into the options flow's constructor.

### Removing a module

Each Viega module's Home Assistant device must be deletable through the
standard Home Assistant UI (removing the integration entry from Settings →
Devices & Services), without editing YAML/JSON or restarting Home Assistant.
Removal must:

- disconnect that module's Modbus connection and remove all of its entities
  and its device registry entry
- succeed even when the device is offline, unreachable, or its socket
  connection is already broken — a failed *or hung* disconnect attempt must
  be logged and must not block the removal; every blocking call in the
  disconnect path must be bounded by the configured `modbus_timeout`. An
  unbounded `await` on a socket close is not "handled" by wrapping it in
  `try`/`except` alone — a hang never raises, so it never reaches the
  `except` clause; it must be wrapped in a timeout too.
- be reachable from the device's own page as well as from the integration
  entry, per Home Assistant's `async_remove_config_entry_device` mechanism —
  each module maps to exactly one device, so removing that device is always
  safe
- affect only that module; every other configured module's connection,
  polling, and entities must keep working unchanged (see "Multiple modules"
  above)

## 6b. Configuration parameters

When setting up a Viega Fonterra device, the user must configure:

- `host`: IP address of the Modbus TCP device (default `192.168.0.188`)
- `port`: Modbus TCP port (default `502`)
- `device_name`: Human-readable name for the device (e.g., "Heizung Wohnzimmer")
- `polling_interval`: How often to update sensor values, in seconds (default 30, minimum 5)
- `modbus_timeout`: Maximum time to wait for a Modbus response, in seconds (default 5, minimum 1)

Room mapping is deliberately **not** collected at setup time. Earlier
versions of this spec required a `rooms` JSON field on the setup form (shown
pre-filled with an example mapping), which made every new module's creation
form look like it needed a hand-typed, correct room/actor/sensor topology
before the module could be added at all — misleading, since §4a's automatic
discovery from the device's own actuator Raum-ID and room-name registers is
the actual source of truth and runs on every setup regardless of what (if
anything) was typed manually. The setup form therefore only asks for the
five fields above; rooms populate themselves once the module successfully
connects. A manually typed room mapping remains available, but only as an
edit made afterward through the options flow ("Editing an existing module",
§6a) — used purely as a fallback for a setup cycle where the device can't be
read (§4a), never as a precondition for creating the module in the first
place.

```python
rooms = {
    "room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10},
    "room_2": {"name": "Schlafzimmer", "actor": 2, "sensor": 11},
}
```

Each room's `name` field is used as the display name for the thermostat
entity in Home Assistant, whether the mapping came from automatic discovery
or a manual options-flow edit.

### 6c. Polling model

`polling_interval` gates how often each entity performs an actual Modbus
read, not how often Home Assistant calls the entity's update method. Every
platform polls at a fixed 5-second `SCAN_INTERVAL` (the spec-mandated
minimum), and each entity tracks the time of its last real read; it skips
the Modbus request and keeps its last known value whenever less than
`polling_interval` seconds have passed, and performs the read otherwise.
This lets each config entry honor its own configured interval without a
shared per-device scheduler, while still allowing `polling_interval` values
down to the 5-second minimum.

If the initial Modbus TCP connection cannot be established when a config
entry is set up, the integration must signal Home Assistant to retry with
backoff (rather than leaving the entry in a hard error state that requires
a manual reload). A connection failure or reload of one module must not
affect any other module's connection, polling, or entities.

## 7. Distinguishable devices

Every module's Home Assistant device (`device_info`, built by
`device.py::build_device_info`) must be identified by that module's own
config entry and use that module's configured `device_name` as its display
name (§6a) — never a fixed string shared across modules. Two modules must
therefore always be distinguishable in the device registry, entity picker,
and dashboards, purely from their own configuration, with no manual
disambiguation step required from the user.

## 8. (Removed) Simple switch support

This section previously required a minimal per-room switch entity with a
local `is_on`/`turn_on()`/`turn_off()` state flow. That switch never read or
wrote any Modbus register — the device manual documents no discrete,
writable per-room on/off holding register (the closest control is the
Leistungsstufe/power-level register, §5b, already exposed as a Number
entity). The switch was scaffolding from before the real register map
(§3a-§5b) was confirmed against the manual, and it shipped unchanged: every
room got an entity that toggled a value in Home Assistant's memory with no
effect on the installation. It has been removed rather than kept as a
misleading control. The section number is kept unused rather than
reassigned, so old issue/commit references to §8 are not silently repointed
at unrelated content.

## 9. Register mapping

The register map is a flexible, modular schema. `REGISTER_DEFINITIONS` in
`registers.py` illustrates the schema's shape with a placeholder example set:

- temperature_flow: address 1000, unit °C
- temperature_return: address 1001, unit °C
- temperature_room: address 1002, unit °C
- system_pressure: address 1010, unit bar
- pump_state: address 1020, unit None

These addresses are illustrative only, not confirmed Viega register
addresses — the real device map (§3a-§5b, confirmed against `Fonterra Smart
Control-de-DE.pdf`) only spans roughly PDU 0-285, nowhere near 1000. The
sensor platform must not instantiate `REGISTER_DEFINITIONS` as live entities
against real hardware; a placeholder register address is not a substitute
for one confirmed against the manual or logged frame data, the same mistake
an earlier, unrelated draft of the automatic room discovery in §4a once
made by treating illustrative example data as if it were real device
output. `REGISTER_DEFINITIONS` remains available as a mechanism for
genuinely mapped registers to be added later, each with its real address
confirmed first.

## 9a. int16 read compatibility

This integration uses its own raw Modbus/TCP client (`modbus_handler.py`),
not Home Assistant's YAML Modbus platform — so the YAML platform's `count`
option (which some Home Assistant/base-unit firmware combinations reject for
`data_type: int16`, causing cyclic connection failures — see the reported
[Fonterra Smart Control update issue](https://community.simon42.com/t/modbus-problem-nach-update-fonterra-smart-control-viega/29014))
does not apply here. It must not be confused with the Modbus *protocol*
quantity field, which every function-code `0x03`/`0x04` request must still
carry on the wire regardless of client implementation — `1` for a single
register. If a YAML Modbus configuration is ever offered as an alternative
to this client, its `int16` entities must omit `count`, matching the
upstream issue above.

## 10. Error handling and data validity

The Modbus communication layer must treat the device error sentinel value `-99` as a failed read, not as a valid measurement.

When a read returns `-99`:

- the entity must not replace the last known valid value
- the previous value remains active
- the update cycle continues without throwing an exception
- a diagnostic text entity must be created for the affected unit and show the textual error state

This behavior must also apply to any read where a Modbus communication issue is detected.

A diagnosis entity is a textual entity that exposes the last device error message or status string, for example:

- `error: sensor invalid`
- `error: communication timeout`
- `error: unit unavailable`

These entities are not numeric; they are intended for diagnostics and troubleshooting.

The sensor layer must also record the last error message on each sensor entity itself. When a device value is invalid or a communication error occurs, the sensor keeps the last valid value but stores the latest textual error string in `last_error_message` for downstream diagnosis entities or logs.

Register values (both holding and input registers) must be decoded as signed
16-bit integers. Decoding holding registers as unsigned would make the `-99`
sentinel unrepresentable on that read path (`-99` two's-complement is
`0xFF9D`/`65437` unsigned), silently defeating this section's requirement for
any register read through function code `0x03`. Ordinary holding-register
values used by this integration (temperatures, power levels, mode codes) stay
well under `32768` and are unaffected by signed interpretation; writes remain
unsigned 16-bit values on the wire as specified in §5b.

This "keep the previous value" rule applies to every register-backed value an
entity holds, not only the ones an entity's own read directly produces: the
Climate entity's `-99`/failed-read handling must cover the raw value on the
wire *before* scaling (e.g. a raw `-99` current/target temperature divided by
10 into a fabricated `-9.9`, rather than being recognized as the error
sentinel first, is the same bug this section forbids) and every one of its
other register-backed attributes (power level, flow/return temperature,
actuator position, base-unit error code, operating mode, profile mode) -
none of them may be overwritten with `None`/`-99` on a failed or sentinel
read, including across any number of consecutive failed reads (at least 3
consecutive `-99` reads must be tolerated without the value being lost or
the entity's reported mode/preset changing), matching the debounce guarantee
§5c already gives the circulation-pump indicator.

## 11. Modbus transaction validation

If a Modbus/TCP response contains a transaction ID, the client must validate it before accepting the payload as valid.

Required behavior:

- compare the response transaction ID with the expected request transaction ID
- reject mismatches with a `ValueError`
- ignore any payload whose transaction ID does not match the outstanding request
- validate that the response's function code echoes the function code that
  was sent; a function code with the high bit set (e.g. `0x03` -> `0x83`)
  is a Modbus exception response and must be rejected as such (surfacing
  the device's exception code) rather than being handed to the register
  decoder, which cannot tell an exception response apart from a
  short/garbled payload
- validate that a read response decodes to exactly as many registers as the
  request asked for; a response with a different register count must be
  rejected rather than silently handed to the caller at the wrong list index

These checks (transaction ID, function code, register count) are all
transport-level integrity checks on the same response and must all pass
before a read's decoded values are treated as valid.

TCP is a byte stream, not message-framed: a single read from the socket can
legitimately return fewer bytes than a complete response even without EOF,
if the response is delivered split across more than one TCP segment. The
client must reassemble a complete frame before any of the checks above run,
by reading the 6-byte MBAP header first and then reading exactly as many
further bytes as that header's length field states follow it — not by
issuing one fixed-size read and assuming it returned the whole frame.

## 11a. Frame-level logging and diagnostics

The Modbus transport must provide optional frame-level debug logging for
diagnosing connection and protocol problems. When enabled, each transmitted
(`TX`) and received (`RX`) frame must be logged at DEBUG level with:

- direction (`TX` or `RX`)
- target host and port
- frame length
- transaction ID
- unit ID
- function code
- complete frame bytes in hexadecimal form

Frame logging must be disabled by default and must be controllable without
changing the protocol behavior. Logs must not contain passwords, credentials,
or unrelated Home Assistant state. A malformed or truncated frame must still
be safe to log and must not cause a secondary logging exception.

Frame logging must be gated purely on Home Assistant's standard
`logger.logs` mechanism for this integration's logger
(`isEnabledFor(logging.DEBUG)`) — there must be no separate per-client or
per-config-entry toggle to keep in sync with it. One control surface means
raising the logger to DEBUG is always sufficient to turn frame logging on,
and dropping back below DEBUG is always sufficient to turn it off.

The same response transaction-ID validation used by normal operation must run
after an RX frame is logged. This ensures that debug output can be correlated
with the request while mismatched responses are still rejected.

## 11b. Request serialization

A single Modbus/TCP connection is shared by every entity belonging to a
config entry (one room's Climate entity alone can perform several reads per
cycle, plus separate sensor, number, and binary sensor entities). Home
Assistant may invoke these entities' update methods concurrently, so the
transport must serialize requests on a given connection — at most one
request may be in flight, and its response must be read before the next
request is sent — so that TX/RX frames from different entities can never
interleave on the wire and be misattributed to the wrong request.

## 12. Technical implementation requirements

- Python 3.12 compatible code
- type-annotated modules
- clear separation between registry, device registry, sensor layer, and Modbus transport
- no placeholder-only final state
- tests must cover protocol framing, register definitions, room discovery, multi-device support, and thermostat behavior

Packaging and release:

- `manifest.json` must declare `config_flow: true` and contain a
  `config_flow.py` using the same domain as the manifest — a UI config flow
  implemented without the manifest flag makes Home Assistant report the
  integration as YAML-only.
- `hacs.json`'s `content_in_root` must stay `false` for this repository's
  layout (the integration lives under
  `custom_components/viega_fonterra_modbus/`), and its `domains` value must
  match the manifest domain exactly; a mismatch here makes HACS look for
  `custom_components/None/manifest.json` and fail to install.
- A release must use the same version number in `manifest.json` and its Git
  tag (e.g. manifest `0.1.5` with tag `v0.1.5`); verify the manifest content
  actually committed at that tag, not only the working tree, before
  publishing. Existing remote tags must not be silently replaced.
- A release is only complete once both the branch and the tag are confirmed
  on the remote (a working, authenticated Git remote — SSH key or HTTPS
  credentials); a local commit or tag alone is not a release.

## 12a. Test coverage and diagnostics export

Two implementation requirements that do not fit naturally under a single
register or entity section above:

### Full configuration-flow tests

The test suite must use the official
`pytest-homeassistant-custom-component` test harness with a real Home Assistant
fixture for setup, reconfiguration, reload, connection retry, and removal
flows. Pure parsing tests remain appropriate for isolated input validation, but
they do not replace end-to-end flow tests. The harness and its pinned compatible
dependencies must be declared in `requirements-test.txt`.

The harness is set up (`tests/conftest.py`) and covers the setup flow's
successful-connection, cannot-connect, and duplicate-host/port-rejection
paths, and the options flow's save/cannot-connect paths, including a
multi-actuator room round trip (`tests/test_config_flow_flows.py`). Reload
and removal flows through the harness (as opposed to the unit-level
coverage already in `tests/test_init.py`/`tests/test_modbus_handler.py`)
remain open.

### Configuration diagnostics export

The integration must implement Home Assistant's built-in diagnostics
platform (`diagnostics.py::async_get_config_entry_diagnostics`) so a user
can download a JSON snapshot of a module's resolved configuration from the
standard "Download diagnostics" action, without reading debug logs. The
export must contain:

- the unit: configured `device_name`, `host` (redacted), `port`,
  `polling_interval`, `modbus_timeout`, and the discovered WLAN-module and
  base-unit serial numbers and base-unit name (§3a)
- every room: `room_id`, resolved `room_number`, `name`, and its resolved
  current-temperature/target-temperature/power-level/error-code register
  addresses (§5b)
- every actuator of every room (not only the primary one, §4): its
  actuator id and its resolved position/return-temperature/Raum-ID register
  addresses (§4a)

This must be built entirely from data already held in `hass.data[DOMAIN]`
`[entry_id]` and the pure register-resolution helpers in `registers.py`; it
must not perform additional Modbus reads. `host` is redacted via
`async_redact_data` since diagnostics dumps are routinely pasted into public
issue trackers.

## 13. Acceptance criteria

The integration is considered ready for the next phase when:

- multiple devices can be configured and kept separate
- WLAN module serial number is discovered and exposed as a read-only diagnostic value
- base-unit serial number is discovered and exposed as a read-only diagnostic value
- base-unit designation is discovered and exposed independently from the user-defined device name
- base-unit error code and human-readable error status are exposed diagnostically
- a non-zero base-unit error code activates the base-unit error indicator
- Viega modules can be added through the Home Assistant UI without YAML or JSON
    editing
- each module accepts an IP address or hostname and a configurable Modbus TCP port
- each module has an editable display name in the setup and options flows
- changing a module's name, host, or port through the UI is persisted and applied
    to that module only
- a module (its device, entities, and connection) can be deleted through the
    Home Assistant UI, including while the device is offline, without
    affecting any other configured module
- initial room discovery reveals actor/sensor mappings including non-1:1 topologies
- a module can be added through the setup form without typing any room mapping
- room thermostats exist as entities with target and current temperature
- room thermostats expose the measured Ist-Temperatur and writable Soll-Temperatur
  through one native Climate entity
- supported heating, cooling, and off modes are represented by the Climate
  `hvac_mode`; automatic heating/cooling is not exposed because Viega
  documents it as an external Change-over relay function
- changing the heating/cooling mode writes the documented operating-mode value
  and does not overwrite either temperature value
- manifold flow temperature, per-actuator return temperature, and per-actuator
  position are each exposed as their own linked entity (not only as Climate
  attributes)
- register definitions are externally defined and not hardcoded in the sensor layer
- Modbus request/response handling is covered by tests
- an error sentinel of `-99` keeps the previous valid value instead of overwriting it
- Modbus TCP transaction IDs are validated before payload acceptance
- optional DEBUG logging records every Modbus TX/RX frame with protocol metadata
- frame logging is disabled by default and does not alter normal communication
- failed unit values are exposed via diagnosis text entities that show the textual error state
- each config entry's `polling_interval` governs how often its entities perform actual Modbus reads
- a connection failure during setup lets Home Assistant retry instead of leaving the entry broken
- concurrent entity updates on one config entry never interleave requests on the shared connection
- every linked entity's unique ID is based on entry ID and `room_id`, not the display name
- the configured `device_name` is used as the Home Assistant device name everywhere, not a fixed string
- a room mapping without an explicit `room_number` still resolves working default registers from its `room_id`
- the Climate entity's `preset_mode` labels ("manual"/"profile"/"setback") are localized through Home Assistant's entity translation mechanism, not shown as raw English identifiers
- every linked entity's display name (identity/diagnostic sensors, flow/return-temperature sensors, actuator position, power level, room diagnostics) is localized through `translation_key`/`translation_placeholders` and `translations/en.json`+`translations/de.json`, not a hardcoded English string set on `_attr_name`
- additional actuators in a multi-actor room are exposed as their own linked sensors, not dropped
- a module's "Download diagnostics" export lists the unit identity and every room's name, id, and actuator(s) with their resolved register addresses, with `host` redacted
- one circulation-pump binary sensor per module is `on` when any used actuator is confirmed open and `off` once all are confirmed closed, `None` before any actuator has settled, with each actuator's contribution debounced to 3 consecutive identical reads and unaffected by failed/`-99` reads
- adding a module whose host/port already belongs to an existing config entry is rejected instead of creating a duplicate, uncoordinated set of entities and connections
- every entity on every platform (climate, sensor, binary_sensor, number, diagnostic) restores its last known value after a restart via `RestoreEntity`, including the Climate entity's `hvac_mode`, `preset_mode`, and every `extra_state_attributes` value, not only current/target temperature (§15)
- every config/options flow validation and connection error is shown as a translated message in every language `translations/*.json` supports, not a raw error key
- a Modbus response split across more than one TCP segment is still reassembled and decoded correctly, not rejected as truncated

## 14. (Merged) Session lessons and resolved errors

This section used to be a standalone, append-only log of implementation and
release lessons. Each entry's substance has been folded into the normative
section it actually concerns (register addressing → §5b; write function
code → §5b; write-serialization/packaging/release process → §12; state
restoration scope → §15; multi-actuator room editing → §6a; Modbus TCP
frame reassembly → §11; config-flow error translation → §6a; duplicate
device prevention → §6a; frame-logging's single control surface → §11a),
so the same information is visible next to the requirement it clarifies
instead of only in a separate history. The section number is kept unused
rather than reassigned, matching §8's convention, so existing references to
§14 are not silently repointed at unrelated content.

## 15. State restoration after a restart

After a restart of Home Assistant or of this integration, once setup has
completed successfully, every register-based entity on every platform
(`climate`, `sensor`, `binary_sensor`, `number`, and the diagnostic text
entities) must restore and display the last value that was valid before the
restart, via Home Assistant's `RestoreEntity` mechanism. Neither a
hardcoded default, nor `unavailable`, nor `unknown` may be shown while
waiting for the first post-restart poll to complete — a restart must not be
visible in the displayed values at all.

This applies to an entity's *entire* displayed state, not only to whichever
attribute a first pass at implementing this happened to cover. For the
Climate entity in particular, that means restoring `hvac_mode` (the
entity's `state`) and `preset_mode` (a `last_state.attributes` key) in
addition to `current_temperature`/`target_temperature`, and every value in
`extra_state_attributes` (`power_level`, `flow_temperature`,
`return_temperature`, `actuator_position`, `base_unit_error_code`) — an
entity that only restores two of its eight displayed values still violates
this section for the other six. A commit or release note claiming this
requirement is met is not a substitute for checking it against every entity
class it names.

## 16. Future operational improvements

The following improvements are approved as future integration capabilities.
They must not introduce undocumented register addresses or change the
documented register map. The manual room/actor mapping fallback described by
older versions of this specification is explicitly **not** part of this
section and must not be reintroduced.

### 16a. Explicit rediscovery

The integration should provide a user-triggered `Rediscover device` action
for an already configured entry. It must re-read documented actuator room-ID
and room-name registers, compare the topology with the cached topology, update
entities without recreating the config entry, preserve stable unique IDs, and
report added, removed, renamed, or reassigned rooms and actuators. It must
never replace successful live discovery with user-entered mapping data. The
action must reuse the existing connection and polling lock.

### 16b. Connection health metrics

Each configured module should expose diagnostic metrics derived from existing
Modbus activity without an additional polling request:

- last successful response timestamp;
- last failed request timestamp;
- consecutive communication-failure count;
- invalid-value count, including the `-99` sentinel;
- last Modbus exception code, when available;
- duration of the most recent successful request.

These metrics are diagnostic only. Communication failures must not overwrite
last valid device values, and network-identifying data must not be exposed as
state or attributes.

### 16c. Read-after-write verification

Acknowledged writes to documented holding registers should be verified on the
next suitable read cycle. The device value remains authoritative: if it differs
from the requested value, the entity must reconcile to the device value and
report a diagnostic warning. Failed writes or failed verification must not be
treated as successful state changes. Verification must use the existing polling
cycle and must not create a second independent poll.

### 16d. Contiguous register-block reads

The polling layer should combine compatible adjacent reads when this reduces
Modbus traffic. Input and holding registers must never be combined. Values may
only be assigned to their declared addresses; response length and
transaction/function-code validation remain mandatory; partial or invalid
blocks must not corrupt unrelated cached values; and undocumented gaps must
not be interpreted as real registers. This optimization must not alter polling
intervals, availability semantics, scaling, or the public register map.

### 16e. Extended downloadable diagnostics

The diagnostics download should optionally include a bounded, privacy-safe
snapshot containing resolved documented addresses, last valid raw and converted
values, read/write counters, recent Modbus exception codes, and discovery
changes. Firmware or software versions may be included only when reported by a
documented device source. Hostnames, IP addresses, credentials, and other
network-identifying data must be redacted. The snapshot must have a fixed
maximum size and must not contain unbounded frames or arbitrary memory data.

### 16f. Derived actuator statistics

Optional diagnostic statistics may be derived from already read, debounced
actuator-position registers: confirmed open time, confirmed open-transition
count, time since the last confirmed transition, and the number of currently
open actuators. These are derived values, not device registers. They must be
unavailable until a valid debounced reading exists, use state restoration where
practical, and must not be presented as pump-status registers.

### 16g. Multi-module overview

For multiple configured modules, an optional aggregate diagnostic view may show
reachable modules, modules with base-unit errors, stale/failed communication,
and room/actuator counts per module. Rooms with equal display names from
different modules must not be merged. Every value must retain its source
config entry and device identity, and one module's failure must not make
another module unavailable.

### 16h. Explicitly excluded capabilities

The following remain excluded until Viega documents or independent hardware
tests reproduce them: manual room mapping as a replacement for automatic
discovery; undocumented outdoor-temperature or pump-status registers; time
schedules, holiday programs, humidity, dew point, or firmware-version
registers without a confirmed source; and automatic probing or writing of
unknown or reserved addresses.