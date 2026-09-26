# Viega Fonterra Smart Control – Home Assistant Custom Integration

> **⚠️ IMPORTANT DISCLAIMER – PLEASE READ CAREFULLY**
>
> **This is a PRIVATE, UNOFFICIAL, COMMUNITY-DEVELOPED custom integration for Home Assistant.**
>
> - It is **NOT** created, authorized, endorsed, maintained, or supported by **Viega GmbH** or any of its affiliates.
> - "Viega", "Fonterra", "Fonterra Smart Control", and related product names are **registered trademarks** of Viega GmbH.
> - This integration was developed independently by reverse-engineering the Modbus/TCP protocol used by the hardware. No official documentation, SDK, or API from Viega was used.
> - **Use at your own risk.** The author(s) accept no liability for any damage to your heating system, property, or data arising from the use of this integration.
> - Viega's official warranty and support terms may be affected by the use of third-party software. Consult your installer or Viega directly if in doubt.
> - This integration is provided "as is", without warranty of any kind, express or implied.

---

## Overview

This custom integration connects **Viega Fonterra Smart Control** room thermostats (base unit + room modules/actuators) to **Home Assistant** via the local Modbus/TCP interface exposed by the Fonterra base controller.

It enables **local control and monitoring** without any cloud dependency. All communication happens directly between Home Assistant and the Fonterra base unit over your local network.

### Supported Hardware

- Viega Fonterra Smart Control **Base Unit** (Modbus/TCP gateway)
- Connected **room modules / actuators** (one entity per configured room)
- Tested with firmware versions commonly shipped 2022–2024; other versions may work but are untested.

### Features

| Feature | Description |
|---------|-------------|
| **Climate entities** | One `climate` entity per room – target temperature, current temperature, HVAC mode (off/heat/cool), preset modes (manual/profile/setback) |
| **Sensor entities** | Flow temperature, return temperature, actuator position (%), communication status, diagnostic text, base-unit error codes |
| **Number entity** | Power level (0–10) per room |
| **Binary sensor** | Connectivity / communication health per room |
| **State restoration** | After Home Assistant or integration restart, all entities resume with their **last known valid values** – no defaults, no "unavailable", no "unknown" (per spec.md §15) |
| **Configurable polling** | Polling interval and Modbus timeout adjustable via UI (Options flow) without re-adding the integration |
| **Diagnostics download** | Full diagnostic snapshot (register map, communication stats, error history) available via Home Assistant's built-in *Download Diagnostics* button |
| **Local-only** | No cloud, no internet access required, no telemetry |

---

## Requirements

- **Home Assistant** 2023.12 or newer (Core or OS/Supervised/Container)
- **Network access** from Home Assistant to the Fonterra base unit on TCP port **1502** (default)
- The Fonterra base unit must have the **Modbus/TCP interface enabled** (installer setting)
- Basic understanding of Home Assistant *Custom Integrations* (manual copy to `config/custom_components/` or HACS)

> **Note:** "Custom integrations enabled" is not a setting in Home Assistant. Custom integrations are always supported; you only need to place the integration files in the correct location.

---

## Installation

### Option A – Manual (recommended for full control)

1. Download the latest release ZIP from the [Releases page](https://github.com/matrover/viega-fonterra-modbus/releases) (or clone this repository).
2. Extract the `viega_fonterra_modbus` folder into your Home Assistant configuration directory:
   ```
   <config>/custom_components/viega_fonterra_modbus/
   ```
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for **Viega Fonterra Smart Control**, and configure.

### Option B – HACS (community store)

1. Open HACS → Integrations → ⋮ (three dots) → Custom repositories.
2. Add this repository URL, category **Integration**.
3. Search for "Viega Fonterra Smart Control" in HACS and install.
4. Restart Home Assistant.
5. Configure via **Settings → Devices & Services → Add Integration**.

> HACS installation is provided as a convenience. The integration itself is not published in the official Home Assistant Core repository.

---

## Configuration

After adding the integration you will be prompted for:

| Field | Description | Default |
|-------|-------------|---------|
| **Host** | IP address or hostname of the Fonterra base unit | — |
| **Port** | Modbus/TCP port | `1502` |
| **Device name** | Friendly name used for entity prefixes | `Viega Thermostat` |
| **Polling interval** | Seconds between Modbus polls (per room) | `30` |
| **Modbus timeout** | Seconds to wait for a Modbus response | `5` |
| **Room mapping** *(optional, advanced)* | JSON mapping `room_name → actor_id` for custom room/actor assignment | Auto-discovery |

All options except *Room mapping* can be changed later via **Settings → Devices & Services → Viega Fonterra Smart Control → Configure** (Options flow).

---

## Entities Created

Per configured room the following entities are created (prefixed with your *Device name*):

| Entity ID suffix | Type | Description |
|------------------|------|-------------|
| `_thermostat` | `climate` | Main thermostat – temperature, mode, preset |
| `_temperature` | `sensor` | Current room temperature (°C) |
| `_flow_temperature` | `sensor` | Flow / supply temperature (°C) |
| `_actuator_position` | `sensor` | Actuator opening (%) |
| `_actuator_return` | `sensor` | Return temperature (°C) |
| `_power_level` | `number` | Heating power level 0–10 |
| `_communication_status` | `binary_sensor` | Connectivity OK / Lost |
| `_diagnostic` | `sensor` | Text diagnostic (communication state, errors) |

All numeric sensor/number entities implement **state restoration**: after a restart they show the last valid reading, never a default or "unavailable".

---

## Diagnostics

Home Assistant's native **Download Diagnostics** (Settings → Devices & Services → Viega Fonterra Smart Control → ⋮ → Download diagnostics) provides a JSON snapshot containing:

- Current register map (all rooms)
- Communication success/failure counters per room
- Last error codes and timestamps
- Configuration (sanitized – no passwords)

Use this when filing issues.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Entities show "unavailable" | Base unit unreachable / wrong IP/port | Verify ping, port 1502 open, Modbus enabled on base unit |
| "Config flow could not be loaded: 500" | Stale browser cache / HA core bug | Hard-refresh browser (Ctrl+Shift+R), restart HA |
| Wrong room temperatures | Incorrect room mapping / actor IDs | Check *Room mapping* JSON or re-run auto-discovery |
| Values jump to 0 / -99 | Register read error (sentinel -99) | Increase *Modbus timeout*, check wiring |
| Climate entity missing HVAC modes | Firmware variant without cool mode | Integration falls back gracefully; modes depend on hardware |

Enable debug logging for deeper analysis:

```yaml
logger:
  default: info
  logs:
    custom_components.viega_fonterra_modbus: debug
```

---

## Development / Contributing

This is a private project. Issues and PRs are welcome but response time is not guaranteed.

### Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```

### Project structure

```
custom_components/viega_fonterra_modbus/
├── __init__.py          # Integration setup, coordinator
├── config_flow.py       # Config & Options flow
├── climate.py           # Climate entity (RestoreEntity)
├── sensor.py            # Temperature, diagnostic sensors
├── number.py            # Power level number
├── binary_sensor.py     # Communication status
├── modbus.py            # Modbus client wrapper
├── polling.py           # Polling gate with configurable interval
├── registers.py         # Register address map & scaling
├── const.py             # Constants, defaults
├── diagnostic.py        # Diagnostics provider
├── spec.md              # Functional specification
└── manifest.json        # Metadata (version, domain, etc.)
```

---

## License

MIT License – see [LICENSE](LICENSE) for details.

---

## Trademarks

**Viega**, **Fonterra**, **Fonterra Smart Control** are trademarks of **Viega GmbH**. This project is not affiliated with Viega GmbH.