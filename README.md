# Viega Fonterra Smart Control for Home Assistant

This custom integration connects one or more Viega Fonterra Smart Control systems to Home Assistant over local Modbus TCP. It provides room thermostats, register sensors, actuator controls, and diagnostic information.

## Features

- Multiple independently configured Viega modules
- Home Assistant UI setup and reconfiguration
- IP address or hostname and configurable Modbus TCP port
- Editable module and room names
- Room climate entities with current and target temperature
- Target-temperature writes through documented holding registers
- Operating mode and profile mode controls
- Room power-level Number entities
- Flow, actuator return, and actuator-position values
- WLAN module and base-unit identity diagnostics
- Base-unit error code and error status
- Optional Modbus TX/RX frame-level debug logging
- Transaction-ID validation
- Preservation of the last valid value for invalid readings (`-99`) and communication failures

## Requirements

- Home Assistant with custom integrations enabled
- A Viega Fonterra Smart Control system with Modbus TCP enabled
- Network access from Home Assistant to the WLAN module or base unit

The Fonterra manual states that Modbus TCP must be enabled in the device software. The documented default endpoint for this integration is:

- Host: `192.168.8.20`
- Port: `1502`

Both values can be changed during setup or later through reconfiguration.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Search for **Viega Fonterra Smart Control**.
3. Install the integration.
4. Restart Home Assistant.

### Manual

Copy the `custom_components/viega_fonterra_modbus` directory into the `custom_components` directory of your Home Assistant configuration, then restart Home Assistant.

## Setup

Open **Settings > Devices & services > Add integration** and select **Viega Fonterra Smart Control**.

The setup form accepts:

- **Host**: an IPv4 address or resolvable hostname
- **Port**: Modbus TCP port, default `1502`
- **Device name**: the Home Assistant device name
- **Polling interval**: `5` to `300` seconds, default `30`
- **Modbus timeout**: `1` to `30` seconds, default `5`
- **Room mapping**: optional JSON mapping of room IDs to actors and sensors

The integration validates the connection before creating the entry. To add another Fonterra module, repeat the setup flow. Each module receives its own connection, device, polling configuration, and entities.

Example room mapping:

```json
{
  "room_1": {
    "name": "Living room",
    "room_number": 1,
    "actor": 1,
    "sensor": 10
  },
  "room_2": {
    "name": "Bedroom",
    "room_number": 2,
    "actor": 2,
    "sensor": 11
  }
}
```

Room names are used for climate, switch, Number, and diagnostic entity names. Room mappings can also contain explicit register overrides when a device installation requires them.

## Reconfiguration

Open the integration entry and select **Configure** to change the module name, host, port, polling interval, timeout, room names, room numbers, and actor or sensor mappings. The connection is tested before changes are accepted. The integration reloads the module automatically after a successful change.

Entity unique IDs are based on the config entry and room ID, so renaming a module or room does not create duplicate entities.

## Entities

Depending on the configured room mapping and available registers, the integration creates:

- **Climate**: room current temperature, target temperature, operating mode, and profile mode
- **Number**: room actuator power level (`0` to `10`)
- **Sensors**: flow temperature, actuator return temperature, actuator position, room error, and base-unit values
- **Switch**: basic actuator control
- **Diagnostics**: communication status and base-unit error information

The Fonterra register map uses signed 16-bit input values. Temperatures are scaled according to the manual: room and target temperatures use tenths of a degree Celsius, as do flow and return temperatures. The integration converts these values before exposing them to Home Assistant.

## Modbus debug logging

Frame logging is disabled by default. It can be enabled on the Modbus client for troubleshooting. Debug entries contain direction, host, port, frame length, transaction ID, unit ID, function code, and hexadecimal frame data. Do not enable verbose logging permanently on a busy installation.

## Troubleshooting

### Connection failed

Check that Modbus TCP is enabled in the Fonterra software and that Home Assistant can reach the configured host and port. The default endpoint is `192.168.8.20:1502`.

### Values are unavailable

Check the room and actor mappings and confirm that the corresponding sensors are configured in the Fonterra system. A register value of `-99` means that the device considers the value unavailable. The integration keeps the previous valid value and exposes the error through diagnostics.

### Home Assistant reports an integration or platform error

Restart Home Assistant after installing or upgrading the integration. Confirm that `manifest.json` contains `config_flow: true` and that the integration is located at `custom_components/viega_fonterra_modbus/`.

## Documentation

- [System specification](spec.md)
- [Viega Fonterra Smart Control manual](Fonterra%20Smart%20Control-de-DE.pdf)
- [Home Assistant documentation](https://www.home-assistant.io/)

## License

MIT. See [LICENSE](LICENSE).
