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
each room's own error register (manual `30051`/`30053`/.../`30073`, one per
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

On the first read cycle, the system must detect the room association from the device configuration:

```python
payload = {
    "rooms": {
        "room_1": {"actor": 1, "sensor": 10},
        "room_2": {"actor": 2, "sensor": 11},
    }
}
```

This association must be resolved into a room mapping dictionary before sensor and thermostat generation begins.

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
input register (manual `30252`/`30255`/.../`30285`, i.e. actuator base
address `+2`, PDU per §5b): an `int16` in range `1`-`12` naming the room that
actuator serves (device manual page 91, "Aktor N Raum ID"). Each room's
display name is likewise stored on the device as a 24-character string
register (manual `30074`/`30086`/.../`30206`, one set of 12 registers per
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

The actuator-position register (manual `30250`/`30253`/.../`30283`, one per
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
Modbus function `0x10` (Write Multiple Registers, quantity `1`) - see §5b for
why, and §14 "The write command used the wrong function code" for the
history. Unknown raw values must be reported diagnostically and must not be silently
mapped to a different mode. Automatic changeover must not be modelled as
`HVACMode.HEAT_COOL` unless a future Viega manual defines such a Modbus value.

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
    `manual_address - 30001`, the more common Modicon convention, and the
    formula this document previously specified — see §14 "PDU address
    offset, take two") does not match the manual's examples or real hardware
    and makes every register in `registers.py` off by exactly one from the
    device's actual map; it must never be reintroduced. Every address in this
    section and in `registers.py` must satisfy the `-40000`/`-30000` formula.

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
  switch; §14 "A switch that never touched the device" documents why a
  write-capable entity with no real device-side effect must not be
  reintroduced.

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
timeout values must be reported in the form.

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
  disconnect path must be bounded by the configured `modbus_timeout` (an
  unbounded `await` on a socket close is not "handled" by wrapping it in
  `try`/`except` — a hang never raises, see §14 "A hung socket close could
  silently block module removal")
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

## 7. Multi-device support

The integration must allow multiple devices to be configured and stored independently. Each entry must remain separate and should not overwrite the others.

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
misleading control; see §14 "A switch that never touched the device" for the
full account. The section number is kept unused rather than reassigned, so
old issue/commit references to §8 are not silently repointed at unrelated
content.

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
against real hardware (see §14, "Automatic discovery was never wired to
anything real" — the same "placeholder treated as real" mistake applies
here); it remains available as a mechanism for genuinely mapped registers to
be added to later, each with its real address confirmed against the manual
or logged frame data first.

## 9a. int16 read compatibility

For Home Assistant Modbus configuration syntax, an `int16` register must not
receive an explicit `count` parameter. Recent Home Assistant and base-unit
firmware combinations can reject `count` for `data_type: int16`, which may lead
to cyclic connection failures. The `count` parameter is reserved for data types
that require an explicit length, such as `custom` or `string`.

This rule is based on the reported Fonterra Smart Control update issue:
[Modbus-Problem nach Update Fonterra Smart Control (Viega)](https://community.simon42.com/t/modbus-problem-nach-update-fonterra-smart-control-viega/29014).

The current integration uses its own raw Modbus/TCP client rather than Home
Assistant's YAML Modbus platform. Its binary function-code `0x03` request must
still contain the Modbus protocol quantity field. For a single `int16` register,
the wire-level quantity is therefore `1`; this is not the Home Assistant YAML
`count` option and must not be removed from the protocol frame.

Any future Home Assistant Modbus YAML or native platform adapter must verify:

- `int16` entities omit the user-facing `count` option
- `custom` and `string` entities set an explicit length only where required
- raw Modbus frames retain the protocol quantity field
- a representative `int16` read is tested after Home Assistant or base-unit
    firmware updates to detect connection cycling

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

## 12a. Resolution of previously open points

The following decisions are binding implementation requirements:

### Live diagnostic updates

Diagnostic entities must update through the same coordinator/polling cycle as
the room and Climate entities. A successful poll distributes the newly read
error code, identity values, and textual status to all entities of the config
entry. No diagnostic entity may perform an additional independent Modbus poll.
On `-99`, timeout, or another read failure, the entity retains its last valid
value and exposes the communication problem through the existing diagnostic
status.

### Automatic room discovery

After the first successful connection, the integration must read the documented
room, actor, and sensor registers and construct the room mapping before
creating platform entities. The resolved mapping must be persisted in the
config entry, including non-1:1 room/actor/sensor relationships. Subsequent
polls refresh values but must not recreate entities or change stable unique IDs.
If discovery is incomplete, available rooms and diagnostics must still be
created and the missing registers must be reported explicitly.

### Full configuration-flow tests

The test suite must use the official
`pytest-homeassistant-custom-component` test harness with a real Home Assistant
fixture for setup, reconfiguration, reload, connection retry, and removal
flows. Pure parsing tests remain appropriate for isolated input validation, but
they do not replace end-to-end flow tests. The harness and its pinned compatible
dependencies must be declared in `requirements-test.txt`.

### Heating and cooling

The Climate entity must implement the Viega operating-mode register exactly as
documented: holding register `40001` / PDU `0`, with `0 = off/standby`,
`1 = heat`, and `2 = cool`. All three modes must be covered by read/write
tests. The target-temperature range must be mode-dependent: `5-30 °C` in
heating and `16-30 °C` in cooling. Automatic `heat_cool` remains unsupported
because Viega documents change-over as an external relay function, not as a
Modbus mode.

### Text-register encoding

All Viega string registers must use Big-Endian byte order within each 16-bit
register (confirmed against real hardware; Little-Endian was tried first and
scrambled every decoded string - see §3a). Tests must include serial numbers
and names with padding and verify that trailing NUL and space characters are
removed. The decoder must be shared by all text-register entities.

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

This must be built entirely from data already held in `hass.data[DOMAIN]
[entry_id]` and the pure register-resolution helpers in `registers.py`; it
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

## 14. Session lessons and resolved errors

The following issues occurred during implementation and release preparation. They
are recorded here to prevent the same failures in future releases.

### HACS content layout

At one point `hacs.json` contained `content_in_root: true`, although the
integration was stored below `custom_components/viega_fonterra_modbus/`. HACS
then searched for `custom_components/None/manifest.json` and could not install
the integration. For this repository layout, `content_in_root` must remain
`false`, and the `domains` value must match the manifest domain exactly.

### Missing UI config-flow declaration

The Python config flow and options flow were implemented before the manifest
declared `config_flow: true`. Home Assistant consequently displayed the message
that the integration could only be added through `configuration.yaml`. Every
release with a UI configuration flow must include `config_flow: true` in the
manifest and must contain `config_flow.py` with the same domain as the manifest.

### Version and tag drift

Manifest versions and Git tags became temporarily inconsistent during release
updates. A release must use the same version in the manifest and tag, for
example manifest `0.1.5` with tag `v0.1.5`. Before publishing, verify the exact
manifest stored in the tag rather than only the working tree. Existing remote
tags must not be silently replaced; corrections require an explicitly
documented tag update and a corresponding HACS refresh.

### Remote authentication

The release push failed because the configured GitHub SSH remote rejected the
local key with `Permission denied (publickey)`. Creating a local commit or tag
does not publish it. A release is only complete after both the branch and tag
are confirmed on the remote, using a configured SSH key or authenticated HTTPS.

### PDU address offset

`registers.py::pdu_address` subtracted a flat `1` from the full five-digit
manual address (e.g. `40001 - 1 = 40000`) instead of a per-bank origin, so
`BASE_UNIT_REGISTERS`, `room_registers()`, and `actor_registers()` all
produced PDU addresses roughly 30000-40000 too high. No test exercised these
functions, only `REGISTER_DEFINITIONS`. Any change to register-address
arithmetic must be covered by a test that checks the resulting PDU address
against a worked example, not just against the module's own formula.

### PDU address offset, take two

The fix above replaced the flat `-1` with `manual_address - 40001` (holding)
/ `manual_address - 30001` (input) — the common Modicon convention that
treats `x0001` as PDU `0` — and a new test (`test_pdu_address_uses_the_
correct_bank_origin`) plus a §5b "worked example" were written to match that
formula. Both the test and the spec text were themselves wrong: they were
never checked against the device manual's own worked wire examples
(`Fonterra Smart Control-de-DE.pdf`, "Beispiele", pages 94-95), which show
manual `40001` on the wire as PDU `0001` (not `0000`) and manual `30250` as
PDU `00FA`/250 (not `249`) — i.e. the correct formula is `manual_address -
40000` / `manual_address - 30000`, with no `-1` at all. Because
`climate.py`'s hard-coded fallback registers (`flow_temperature=24`,
`error_code=23`, `operating_mode=0`, `profile_mode=1`) had been updated to
match the same wrong formula, every code path agreed with every other code
path while still being off by exactly one register from the real device —
internal self-consistency and passing tests gave no signal that the
addresses were wrong. This is why every register read/write against real
hardware landed one register away from the intended one (§14 "Session
lessons" exists precisely so this class of error is written down): a test
asserting a formula's own arithmetic, or a spec worked example authored from
that same formula, cannot catch the formula itself being wrong. Register
arithmetic must be verified against the vendor's own documented protocol
bytes (a full request/response frame from the manual, decoded field by
field), not only against a written-down "worked example" that could itself
have been transcribed from the same incorrect assumption.

### Ambiguous constructor overloads

`ViegaDiagnosticTextEntity` originally branched its behavior on the number of
positional constructor arguments (2 vs. 3) to support two call shapes. Both
real call sites (`diagnostic.py` and a duplicate in `sensor.py`) passed only
two arguments, always hitting the unintended branch, and the accompanying
test only ever exercised the 2-argument form directly — so the bug was
invisible in CI. An entity's constructor must have a single, unambiguous
signature (default values instead of argument-count branching), and any test
covering it must call it the same way `async_setup_entry` does.

### "diagnostic" is not a Home Assistant platform

A later commit moved diagnostic-entity creation out of a separate
`diagnostic` platform and into `sensor.py`'s `async_setup_entry`, removing
`"diagnostic"` from `PLATFORMS` (§9) because Home Assistant's
`async_forward_entry_setups`/`async_unload_platforms` resolve every entry in
`PLATFORMS` to a real core integration domain, and no `homeassistant.
components.diagnostic` domain exists. A subsequent, unrelated change re-added
`"diagnostic"` to `PLATFORMS`, misreading the earlier removal as accidental
(it was not — see git history of `const.py`) and adding a regression test
that only asserted string membership in the list, never that forwarding to
it actually works. `"diagnostic"` must never be added to `PLATFORMS`; a
change to that list must be checked against what each entry's
`async_setup_entry`/`async_unload_entry` actually does, not just against
whichever behavior the most recent commit happened to leave behind.

### A working debug switch is one switch

Frame-level debug logging (§11a) was briefly implemented as two independent
gates: a `modbus_debug` config-entry option (an instance flag on the client)
*and* Home Assistant's own logger level, both of which had to be enabled for
a frame to actually be logged, with no code keeping them in sync. This is
strictly worse than gating solely on `_LOGGER.isEnabledFor(logging.DEBUG)`
(the standard Home Assistant pattern): it adds a second place to look when
"I turned on debug logging and see nothing" is reported, for no additional
capability. A debug/diagnostic toggle must have exactly one control surface.

### Automatic discovery was never wired to anything real

`__init__.py`'s `async_setup_entry` probed for a `discover`/`discover_rooms`/
`read_discovery`/`read_device_configuration` method on `ViegaModbusClient`
via `getattr(..., None)` before ever implementing any of them, so the
probe always resolved to `None` and the "automatic room discovery"
code path documented in §4/§12a silently never ran on any installation —
every room mapping came from whatever was typed into the setup or options
flow's JSON/UI fields, with nothing to verify it against the physical
topology, and no log line indicating discovery wasn't happening. §4a now
documents the device's own actuator Raum-ID and room-name registers, which
make real discovery possible; a "best effort, silently falls back" pattern
like the old `getattr` chain must not be reintroduced for a capability the
client does not actually implement — either implement it, or don't claim to
attempt it.

### A switch that never touched the device

Every room got a `switch` entity (§8, now removed) whose `turn_on`/`turn_off`
only flipped an in-memory `is_on` flag; `async_setup_entry` never read or
wrote a Modbus register for it, and the device manual documents no writable
per-room on/off holding register for it to control. A user who found this
entity in Home Assistant had no way to tell what it did, because it did
nothing to the installation. §8 was written before the real register map
(§3a-§5b) was confirmed against the manual and was never revisited once real
registers existed for every other capability. A requirement written against
an assumed/generic device model must be re-validated once the real register
map is known, and an entity with no device-side effect must not ship without
saying so, ideally by not shipping it at all.

### Linked entities that were only Climate attributes

§5a's capability matrix required "Show manifold flow temperature", "Show
actuator return temperature", and "Show actuator position" as their own
linked sensor/binary-sensor entities. `climate.py` read all three registers
correctly but only ever exposed them through the Climate entity's
`extra_state_attributes`, never as separate entities — so they existed in
the entity's attribute dict but never appeared as their own row in the
Home Assistant UI, were not selectable in the history/statistics graphs, and
had no device class. A capability matrix entry that says "Linked sensor" is
only satisfied by an actual entity of that platform; a value merely present
in another entity's attributes does not meet it, even if the underlying
register read is correct.

### Actuator position is binary, not a percentage

§5a previously described "Show actuator position" as a percentage sensor.
The device manual (page 91, "Aktor N Stellung") documents this register as
strictly `0 = geschlossen` / `1 = offen` — there is no percentage anywhere
in the actuator register block. This was never checked against the manual
when the capability matrix was written; it has been corrected to a binary
`open`/`closed` sensor (device class `opening`) to match the documented
register.

### Preset-mode labels were shown as raw English identifiers

`ClimateEntity.preset_modes` returned `["manual", "profile", "setback"]`,
and Home Assistant renders a preset's raw value verbatim in the UI unless
the entity declares a `translation_key` and the integration ships a matching
`entity.climate.<key>.state_attributes.preset_mode.state` block in
`translations/*.json`. Neither existed, so a German-language installation
still showed "manual"/"profile"/"setback" instead of translated labels.
Separately, "setback" itself was never defined anywhere in the spec or the
UI — the device manual's own term for profile-mode value `2` is
"Absenkbetrieb" (an automatic reduced-temperature mode, available only in
heating mode), which is now the documented and translated label. A raw
value used as a Home Assistant preset/mode identifier is not automatically
a specification of its user-facing meaning; both need to be written down.

### A hung socket close could silently block module removal

`ViegaModbusClient.disconnect()` called `await self._writer.wait_closed()`
with no timeout. `wait_closed()` has none of its own: if the peer never
completes the TCP close handshake — exactly the "device offline/unreachable"
case §6a/§13 require removal to survive — it can block forever. Because
`async_unload_entry` awaits `client.disconnect()` directly, a stuck close
did not raise an exception (the existing `try`/`except` around it never
triggered) and instead hung the whole removal request with no error message,
so the config entry's "Delete" action in the UI appeared to do nothing. A
second, independent bug in the same method: the `_reader`/`_writer`/
`_connected` reset ran only *after* `wait_closed()` returned, so on the rare
occasions it *did* raise (e.g. `ConnectionResetError`) instead of hanging,
the client was left thinking it was still connected. `disconnect()` now
bounds the close with the configured Modbus timeout and always resets state
in the same call, regardless of how the close attempt ends. A "must succeed
even when offline" requirement is only met when every blocking call in the
teardown path has a bound — an unbounded await is a hang, not merely a
missing error path, and neither `try`/`except` nor `ConfigEntryNotReady`
guards against it.

### Setup asked for a room mapping that discovery was going to overwrite anyway

The setup form's `rooms` field (§6b, since removed) was `vol.Optional` but
pre-filled with a two-room example as its default value, so it rendered as a
non-empty JSON text box a user had to notice, understand, and either clear
or correctly edit before adding a module — for a value that §4a's automatic
discovery (already wired into `async_setup_entry`) would read from the
device and use instead on every setup where the device is reachable. Once
discovery existed, the field's only real effect was to make setup look like
it needed information the user usually didn't have yet (which actuator/
sensor number maps to which physical room) and, when left at its literal
default, to seed a fallback mapping ("room_1"/"Wohnzimmer"/actor 1) that
almost never matched the real installation. Removed from the setup step
entirely (`config_flow.py::async_step_user`/`_show_user_form`, and the now-
dead `parse_rooms_input` helper and its tests); manual room edits remain
available afterward through the options flow, which is also where §4a
already said the fallback belongs. A field must be dropped from a form once
the mechanism it was standing in for is fully implemented, not left in
"just in case" — an optional field with a plausible-looking default is still
a requirement in practice if users can't tell it's safe to ignore.

### Entity names were hardcoded English, translation_key was never used

Every entity across `sensor.py`, `binary_sensor.py`, `number.py`, and
`diagnostic.py` set `self._attr_name`/`self.name` directly to a fixed
English string ("WLAN module serial number", "{room} actuator {n} position",
etc.), even though `_attr_has_entity_name = True` was set everywhere and
`translations/de.json` already carried a `entity.climate.room.
state_attributes.preset_mode` block for the Climate entity's preset labels.
Home Assistant's own `Entity._name_internal()` checks `hasattr(self,
"_attr_name")` *before* ever looking at `translation_key`: since `_attr_name`
on the base `Entity` class is a bare type annotation with no default value,
`hasattr` is only `True` once something actually assigns it - so setting
`_attr_name` to anything, including an already-`None` default, permanently
opts an entity out of translation-based naming, and `self.name = "..."`
(seen in `diagnostic.py`) is worse still: `Entity.name` is a `cached_property`,
so a direct assignment seeds its cache and skips the property's computation
(and thus `_name_translation_key`) entirely. Every entity's display name is
now supplied via `_attr_translation_key` (+ `_attr_translation_placeholders`
for per-room/per-actuator values, substituted with Python `str.format`) with
no `_attr_name` set at all, matching both `translations/en.json` and
`translations/de.json`. The room-id-less construction shape of
`ViegaDiagnosticTextEntity` (used by tests and any future non-room-scoped
diagnostic entity) is the one deliberate exception: with no room to build a
placeholder from, it still falls back to `self.name = name`. A hardcoded
`_attr_name` is not "a name that happens to be in English" - it is a
different, incompatible code path from translation-based naming, and the two
cannot be mixed by simply also adding translation strings on the side.

### The write command used the wrong function code

`ViegaModbusClient.build_write_request()` hardcoded Modbus function `0x06`
(Write Single Register) for every write this integration performs - target
temperature, power level, operating mode, profile mode - and the spec text
and tests agreed with it. But the manual's own worked wire example for a
write ("Beispiel 2 - Soll-Temperatur für Raum 2 setzen", `Fonterra Smart
Control-de-DE.pdf` page 95) uses function `16`/`0x10` (Write Multiple
Registers) with quantity `1` and byte count `2`, not `0x06` - the exact same
example whose *address* byte (`00 35` = PDU `53` = manual `40053`) had
already been used to confirm the PDU-address formula in §5b/§14 "PDU address
offset, take two". The write function code sitting three bytes away in that
same worked example was never checked, because nothing was actually
exercising a write against real hardware to surface the mismatch - reads
(§3a's text-register bug, §14's PDU-offset bugs) had already been confirmed
against the device, but no write had. This is the same failure mode §14
describes repeatedly for reads, now found in the write path: code, spec
text, and tests all agreeing with each other is not evidence of matching the
device - only a worked example's *individual bytes*, checked one by one
against what the code actually sends, is. `build_write_request` now builds a
function-`0x10` frame (`>HHHBBHHBH`: transaction/protocol/length, unit,
function, address, quantity, byte count, value); every write must use it.

### A raw `-99` reached the UI as `-9.9`, and register errors could flip the reported mode

The Climate entity's `async_update` divided the raw `current_temperature`/
`target_temperature` register values by 10 unconditionally - it only
skipped the assignment when the read itself failed (`None`), never when the
device answered with the valid-looking but sentinel raw value `-99` (§10).
`-99 / 10 = -9.9`, so a room with no paired thermostat, or a transient
device-side fault, showed a temperature of `-9.9°C` in the UI instead of
its last known-good reading - the exact same class of mistake §10 already
forbids for the *unscaled* value, just missed for the two attributes that
happen to need a division first. The same method also assigned
`power_level`, `flow_temperature`, `return_temperature`, `actuator_position`,
and `base_unit_error_code` unconditionally on every update, with no `None`/
`-99` guard at all, clearing each one to `None` on a single failed or
sentinel read rather than keeping the previous value - and `operating_mode`/
`profile_mode` were guarded against `None` but not against `-99`, so a
sentinel read on the shared mode register could make `hvac_mode`/
`preset_mode` fall back to a mode the base unit was never actually in.
Fixed by scaling only after checking for the sentinel (a `_scaled` helper
already existed and was used for two of the seven affected attributes; it is
now used for all temperature attributes) and by never assigning `None`/`-99`
over a previous value for any of them (a new `_valid` helper), verified
across at least 3 consecutive `-99` reads in a row, not just one - see §10.
