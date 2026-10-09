# Changelog

All notable changes to this integration are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Entries under Settings → Repairs when a module has not responded for
  30 minutes and when the base unit reports an error code, with the
  meaning of each code translated; they clear themselves.
- Importable blueprint that switches a separately wired circulation pump
  from the circulation-pump indicator, with a run-on time.
- README guide: daily heating time per room with built-in helpers and a
  bar chart of the daily totals.
- Automatic checks on GitHub for every change (tests, Home Assistant's
  hassfest validator, HACS validation) and a weekly test against the
  newest Home Assistant version.

### Changed

- Each module is now polled by one central update cycle at its polling
  interval, which updates all of its entities together, instead of every
  entity being polled by Home Assistant every 5 seconds. Same values, fewer
  wake-ups, and a change you make is read back from the device right away
  instead of after a full interval.

### Fixed

- Error messages in the setup and options dialogs (e.g. "Unable to connect
  to the Viega module") were shown as raw keys such as `cannot_connect`
  instead of translated text.
- `manifest.json` code owner and the missing UI-only `CONFIG_SCHEMA`, both
  reported by Home Assistant's hassfest validator.

## [1.1.0] - 2026-10-09

### Added

- Each room's climate entity shows what the room is doing right now —
  heating, cooling, idle, or off — on the built-in thermostat and tile cards,
  with colored heating/cooling bands in the history graph. A room counts as
  heating/cooling as soon as any of its actuators is open.
- On/off control for the climate entity: off puts the module into standby
  (frost protection stays active), on restores the last active mode.
- Automatic reconnection after a lost Modbus connection (device restart,
  Wi-Fi or router outage), with back-off; no manual reload needed anymore.
- Diagnostic sensors for the number of reconnections and the time of the
  last one.
- Clear, translated (German/English) error messages when a change cannot be
  applied, e.g. a temperature outside the allowed range or an unreachable
  module, and for a failed rediscovery.
- Tile-card dashboard example in the README.

### Changed

- The preset (profile mode) control is only offered while the module is
  heating, matching the device, which supports profile mode only in heating
  mode.
- A read that fails because the connection broke is retried once on a new
  connection; writes are never repeated automatically.

### Fixed

- After a connection loss every request failed until the integration was
  reloaded by hand, while all values silently froze.
- A late or misaligned response after a timeout could be taken for the
  answer to a later request.
- The first setup of a module (and every topology change) immediately ran a
  second setup, repeating discovery and opening a second connection.
- A refused connection during setup is now retried by Home Assistant instead
  of failing the entry.

## [1.0.1] - 2026-09-29

### Fixed

- HACS could not detect the integration because compiled `__pycache__`
  folders were committed; they are removed and ignored.

## [1.0.0] - 2026-09-29

First release.

- Multiple independently configured Viega modules, set up and reconfigured
  in the Home Assistant UI.
- Automatic room and actuator discovery from the device.
- Room climate entities with current/target temperature, operating mode and
  profile mode; room power-level number entities.
- Flow temperature, per-actuator return temperature and position.
- Derived, debounced circulation-pump indicator and actuator statistics.
- Identity, error-code, and connection-health diagnostics, an on-demand
  rediscovery action, a multi-module overview, and downloadable
  configuration diagnostics.
- German and English translations.

[Unreleased]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/releases/tag/v1.0.0
