[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

## Viega Fonterra Smart Control for Home Assistant

This custom integration connects Home Assistant to one or more Viega Fonterra Smart Control installations over Modbus TCP, enabling local monitoring and control of heating systems.

### Features

- **Multi-device support**: Configure and manage multiple Viega Fonterra devices independently
- **Room thermostats**: Climate entities per room with configurable target and current temperature
- **Sensor monitoring**: Register-based sensor values (flow/return temperature, system pressure, pump state)
- **Simple actuators**: Switch entities for basic on/off control
- **Diagnostic entities**: Textual error states for failed unit values and communication issues
- **Configurable polling**: Adjustable update interval (5–300 seconds, default: 30s)
- **Configurable timeouts**: Modbus TCP response timeout (1–30 seconds, default: 5s)
- **Room naming**: Display room names instead of IDs in entity names
- **Error handling**: Preserves last valid sensor value on communication errors; `-99` sentinel rejection
- **Transaction validation**: Modbus/TCP transaction ID verification before payload acceptance

### Installation

1. Install via HACS: `Settings > Devices & Services > Create Automation > Integrations > + > Viega Fonterra Smart Control`
2. Restart Home Assistant
3. Add the integration: `Settings > Devices & Services > + Create Integration > Viega Fonterra Smart Control`
4. Follow the config flow:
   - Enter device IP and port (default 502)
   - Set device name, polling interval, and Modbus timeout
   - Configure rooms with names and actor/sensor mappings

### Configuration Example

```python
Rooms configuration:
{
  "room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10},
  "room_2": {"name": "Schlafzimmer", "actor": 2, "sensor": 11}
}
```

Each room creates:
- A climate (thermostat) entity
- A switch entity
- A diagnostic text entity

### Notes

This repository is a local custom integration for Home Assistant. The register map is modular and can be extended as the Fonterra device documentation is mapped in detail.

For technical details and specification, see `spec.md` in the repository.

### Related Documentation

- Viega Fonterra: https://web-catalog.viega.com/de_AT/html/Montage/Flaechentemperierung/Fonterra/
- Home Assistant: https://www.home-assistant.io/
- Modbus TCP: https://en.wikipedia.org/wiki/Modbus
