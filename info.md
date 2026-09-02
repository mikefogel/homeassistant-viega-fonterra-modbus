[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

## Viega Fonterra Smart Control for Home Assistant

This custom integration connects Home Assistant to one or more Viega Fonterra Smart Control installations over local Modbus TCP, enabling room-level monitoring and control of heating systems.

### Features

- **Multi-device support**: Configure and manage multiple Viega Fonterra devices independently
- **Room thermostats**: Climate entities per room with configurable target and current temperature
- **Writable thermostat controls**: Target temperature, operating mode, and profile mode through holding registers
- **Power-level control**: Room actuator power level as a Number entity
- **Sensor monitoring**: Room, flow, actuator return, actuator position, system pressure, and pump values
- **Device diagnostics**: WLAN module serial number, base-unit serial number and name, and base-unit error code
- **Simple actuators**: Switch entities for basic on/off control
- **Diagnostic entities**: Textual error states for failed unit values and communication issues
- **Configurable polling**: Adjustable update interval (5–300 seconds, default: 30s)
- **Configurable timeouts**: Modbus TCP response timeout (1–30 seconds, default: 5s)
- **Room naming**: Display room names instead of IDs in entity names; names and mappings can be edited through reconfiguration
- **Error handling**: Preserves last valid sensor value on communication errors; `-99` sentinel rejection
- **Transaction validation**: Modbus/TCP transaction ID verification before payload acceptance
- **Frame debugging**: Optional TX/RX frame logging with protocol metadata

### Installation

1. Install via HACS: `Settings > Devices & Services > Integrations > + > Viega Fonterra Smart Control`
2. Restart Home Assistant
3. Add the integration: `Settings > Devices & Services > + Add Integration > Viega Fonterra Smart Control`
4. Follow the config flow:
  - Enter device IP or hostname and port (defaults: `192.168.8.20`, `502`)
   - Set device name, polling interval, and Modbus timeout
  - Optionally configure rooms with names, room numbers, and actor/sensor mappings

### Configuration Example

```json
{
  "room_1": {
    "name": "Living room",
    "room_number": 1,
    "actor": 1,
    "sensor": 10
  }
}
```

Each room creates:
- A climate (thermostat) entity
- A power-level Number entity
- A switch entity
- A diagnostic text entity

### Notes

This repository is a local custom integration for Home Assistant. The register map follows the supplied Viega manual, including signed Int16 input registers and holding-register writes. Room mappings can override register addresses where required by an installation.

For technical details and specification, see `spec.md` in the repository.

### Related Documentation

- Viega Fonterra: https://web-catalog.viega.com/de_AT/html/Montage/Flaechentemperierung/Fonterra/
- Home Assistant: https://www.home-assistant.io/
- Modbus TCP: https://en.wikipedia.org/wiki/Modbus
