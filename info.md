[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

## Viega Fonterra Smart Control for Home Assistant

This custom integration connects Home Assistant to a Viega Fonterra Smart Control installation over Modbus TCP and exposes selected register-derived sensor values.

The project is currently in an active development phase and is intended to provide a local, self-hosted solution for monitoring heating-related values without relying on a cloud dependency.

### Current status

- Integration scaffold is in place
- Config flow supports host and port input
- Modbus TCP client structure is implemented
- Sensor entities are based on a configurable register map
- The project is being refined step by step toward a stable Home Assistant integration

### Planned features

- Reading of flow and return temperatures
- Monitoring of pressure and system state
- Sensor entities for heating-related values
- Safe Modbus error handling and reconnect logic
- Home Assistant-friendly config and update flow

### Notes

This repository is a local custom integration for Home Assistant and is not yet a finished production release for all devices and configurations.

The register map is intentionally kept modular so it can be extended as the real Fonterra device documentation is mapped in more detail.

### Related documentation

- Viega documentation: https://web-catalog.viega.com/de_AT/html/Montage/Flaechentemperierung/Fonterra/
