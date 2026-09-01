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

- room_id
- current_temperature
- target_temperature
- device_class = "temperature"

This entity represents a room-level thermostat and is the primary control surface for a room in Home Assistant.

## 6. Multi-device support

The integration must allow multiple devices to be configured and stored independently. Each entry must remain separate and should not overwrite the others.

## 6a. Configuration parameters

When setting up a Viega Fonterra device, the user must configure:

- `host`: IP address of the Modbus TCP device (e.g., 192.168.1.10)
- `port`: Modbus TCP port (default 502)
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

## 12. Technical implementation requirements

- Python 3.12 compatible code
- type-annotated modules
- clear separation between registry, device registry, sensor layer, and Modbus transport
- no placeholder-only final state
- tests must cover protocol framing, register definitions, room discovery, multi-device support, thermostat behavior, and switch behavior

## 13. Acceptance criteria

The integration is considered ready for the next phase when:

- multiple devices can be configured and kept separate
- initial room discovery reveals actor/sensor mappings including non-1:1 topologies
- room thermostats exist as entities with target and current temperature
- simple switch functionality is present
- register definitions are externally defined and not hardcoded in the sensor layer
- Modbus request/response handling is covered by tests
- an error sentinel of `-99` keeps the previous valid value instead of overwriting it
- Modbus TCP transaction IDs are validated before payload acceptance
- failed unit values are exposed via diagnosis text entities that show the textual error state
