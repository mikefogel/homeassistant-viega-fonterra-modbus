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
number and text field. Serial numbers and names may span multiple registers and
must be decoded according to the device manual rather than by guessing byte
order or character encoding.

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
display names without creating duplicate entities. The Climate entity and all
linked entities must reference the same Home Assistant device registry entry.

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
    "target_temperature_register": 1200,
    "power_level_register": 1201,
    "actuator_position_register": 1202,
    "operating_mode_register": 1203,
    "profile_mode_register": 1204,
    "flow_temperature_register": 1000,
    "return_temperature_register": 1001,
}
```

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
