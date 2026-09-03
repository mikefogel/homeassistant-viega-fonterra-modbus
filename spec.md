# Viega Fonterra Smart Control – system specification

## 1. Purpose

This repository defines a Home Assistant custom integration for Viega Fonterra Smart Control installations. It must support local Modbus TCP communication, room-level discovery, multiple device installation, and a simple switch/thermostat model for basic automation.

## 2. Core objectives

- Connect to one or more Viega Fonterra Smart Control devices over Modbus TCP.
- Discover room-to-actor and room-to-sensor mappings when the first read is performed.
- Represent room thermostats as entities.
- Support multi-device configuration in a single installation.
- Support simple on/off control for basic functionality.
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
characters per register, high byte first (big-endian byte order within each
register), with trailing NUL and space characters stripped. This convention
is provisional: it is the implementation's best-effort reading of common
Modbus text-register practice, not a value confirmed against the Viega
device manual. It must be corrected to match the manual as soon as real
hardware or documentation is available to verify it, and any change must be
applied consistently to `ViegaBaseUnitIdentitySensor` in `sensor.py`.

### 3b. Base-unit error codes

The base-unit error code register (`error_code`, manual address `30024`) is
`0` when the unit reports no error (see §3a); any other value is an active
error. A code-to-description table (`BASE_UNIT_ERROR_CODES` in
`registers.py`) maps known codes to human-readable text. Only `0` → "No
error" is currently confirmed; every other code must render as
`"Unknown error (code N)"` until it is added to the table with a
manual-confirmed description. New codes must be appended to the table
rather than guessed inline in the entity layer.

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
| Show actuator position | Linked percentage sensor | Read the actuator-position register |
| Show whether the base unit has an error | Linked binary sensor or diagnostic sensor | `on`/error when any base-unit error is active |
| Show which base-unit error exists | Linked diagnostic text sensor | Expose the error code and human-readable message |
| Show operating mode | Climate `hvac_mode` where applicable | Read the active operating mode |
| Change operating mode | Climate `set_hvac_mode` | Write the operating-mode holding register |
| Show profile mode | Climate preset or linked Select entity | Read the active profile mode |
| Change profile mode | Climate `set_preset_mode` or linked Select entity | Write the profile-mode holding register |

All linked entities must use stable unique IDs based on the module entry ID and
`room_id`, not on the editable room name. Renaming a room must therefore change
display names without creating duplicate entities. This applies to every
platform, including the switch platform (§8) — a switch's unique ID must be
built from the entry ID and `room_id`, never from the room's display name.
The Climate entity and all
linked entities must reference the same Home Assistant device registry entry,
using the module's configured `device_name` (§6a) as the device's display
name — never a fixed string, so multiple modules remain distinguishable in
the device registry.

The operating-mode and profile-mode value sets (`hvac_mode`/`heat`/`off` and
the `manual`/`profile`/`setback` presets) are implementation-defined
placeholders pending confirmation against the device manual or firmware
documentation. They must be treated as provisional and corrected once the
actual register value semantics are confirmed.

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
    temperature. The base-unit operating and profile modes use holding registers
    `40001` and `40002`.

    The conversion from a manual (Modicon-style) address to a PDU address is:
    `pdu = manual_address - 40001` for holding registers (`4xxxx`) and
    `pdu = manual_address - 30001` for input registers (`3xxxx`) — each
    register bank is zero-based on its own `x0001` origin. Subtracting a flat
    `1` from the full five-digit manual address instead of the correct
    per-bank origin produces PDU addresses that are off by roughly 30000-40000
    and must never be used; every address in this section and in
    `registers.py` must satisfy this formula.

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
Modbus function code `0x06`, then update the entity's target temperature only
after a successful write response. A room without a configured target register
must remain readable but must not advertise target-temperature write support.

## 6. Multi-device support

The integration must allow multiple devices to be configured and stored independently. Each entry must remain separate and should not overwrite the others.

## 6a. Home Assistant UI configuration

The integration must provide a native Home Assistant configuration flow. Users
must be able to configure Viega modules through the Home Assistant UI without
editing YAML or JSON files manually.

### Adding a module

The setup form for each Viega module must provide these fields:

- `host`: IP address or DNS hostname of the Modbus TCP device, default
    `192.168.8.20`
- `port`: Modbus TCP port, default `1502`
- `device_name`: editable display name for the module
- `polling_interval`: polling interval in seconds
- `modbus_timeout`: Modbus response timeout in seconds

The `host` field must accept IPv4 addresses such as `192.168.1.10` and
resolvable hostnames such as `fonterra-01.local`. The connection must be
validated before the config entry is created. Invalid host, port, polling, or
timeout values must be reported in the form.

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
entity names for the corresponding thermostats, switches, and diagnostics.

### Removing a module

Each Viega module's Home Assistant device must be deletable through the
standard Home Assistant UI (removing the integration entry from Settings →
Devices & Services), without editing YAML/JSON or restarting Home Assistant.
Removal must:

- disconnect that module's Modbus connection and remove all of its entities
  and its device registry entry
- succeed even when the device is offline, unreachable, or its socket
  connection is already broken — a failed disconnect attempt must be logged
  and must not block the removal
- affect only that module; every other configured module's connection,
  polling, and entities must keep working unchanged (see "Multiple modules"
  above)
## 6b. Configuration parameters

When setting up a Viega Fonterra device, the user must configure:

- `host`: IP address of the Modbus TCP device (default `192.168.8.20`)
- `port`: Modbus TCP port (default `1502`)
- `device_name`: Human-readable name for the device (e.g., "Heizung Wohnzimmer")
- `polling_interval`: How often to update sensor values, in seconds (default 30, minimum 5)
- `modbus_timeout`: Maximum time to wait for a Modbus response, in seconds (default 5, minimum 1)

Room names must also be provided during device configuration:

```python
rooms = {
    "room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10},
    "room_2": {"name": "Schlafzimmer", "actor": 2, "sensor": 11},
}
```

Each room's `name` field will be used as the display name for the thermostat entity in Home Assistant.

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

## 8. Simple switch support

The project must support a minimal switch entity for basic actuator control, with the following state flow:

- is_on = False initially
- turn_on() sets the state to True
- turn_off() sets the state to False

## 9. Register mapping

The register map is a flexible, modular schema. The initial set must include:

- temperature_flow: address 1000, unit °C
- temperature_return: address 1001, unit °C
- temperature_room: address 1002, unit °C
- system_pressure: address 1010, unit bar
- pump_state: address 1020, unit None

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

## 11. Modbus transaction validation

If a Modbus/TCP response contains a transaction ID, the client must validate it before accepting the payload as valid.

Required behavior:

- compare the response transaction ID with the expected request transaction ID
- reject mismatches with a `ValueError`
- ignore any payload whose transaction ID does not match the outstanding request

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
- tests must cover protocol framing, register definitions, room discovery, multi-device support, thermostat behavior, and switch behavior

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
- room thermostats exist as entities with target and current temperature
- simple switch functionality is present
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
- every linked entity's (including switches) unique ID is based on entry ID and `room_id`, not the display name
- the configured `device_name` is used as the Home Assistant device name everywhere, not a fixed string
- a room mapping without an explicit `room_number` still resolves working default registers from its `room_id`
- additional actuators in a multi-actor room are exposed as their own linked sensors, not dropped

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
manual address (e.g. `40001 - 1 = 40000`) instead of the correct per-bank
origin (`40001` for holding registers, `30001` for input registers), so
`BASE_UNIT_REGISTERS`, `room_registers()`, and `actor_registers()` all
produced PDU addresses roughly 30000-40000 too high — while other code paths
(`climate.py`'s hard-coded fallbacks for `flow_temperature`/`error_code`/
`operating_mode`/`profile_mode`) already used the correct values, so the two
never agreed. No test exercised these functions, only `REGISTER_DEFINITIONS`.
Any change to register-address arithmetic must be covered by a test that
checks the resulting PDU address against the worked example in §5b, not just
against the module's own formula.

### Ambiguous constructor overloads

`ViegaDiagnosticTextEntity` originally branched its behavior on the number of
positional constructor arguments (2 vs. 3) to support two call shapes. Both
real call sites (`diagnostic.py` and a duplicate in `sensor.py`) passed only
two arguments, always hitting the unintended branch, and the accompanying
test only ever exercised the 2-argument form directly — so the bug was
invisible in CI. An entity's constructor must have a single, unambiguous
signature (default values instead of argument-count branching), and any test
covering it must call it the same way `async_setup_entry` does.
