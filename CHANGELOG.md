# Changelog

All notable changes to this integration are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### ⚠️ Please check after updating

- 🗄️ To keep the database small, **Last successful Modbus response**,
  **Last Modbus request duration**, and **Invalid Modbus value count** are
  now disabled by default for newly set-up modules; on existing
  installations they stay enabled. The README
  section "Keeping the database small" shows how to keep their history out
  of the recorder.

### ✨ Added

- 🔎 New diagnostic sensor **Invalid registers**: how many registers the
  device reports as `-99` right now and which ones (e.g.
  `room_3.current_temperature`) – the cause behind a steadily growing
  invalid-value count. "Download diagnostics" lists every such register
  with room, address, and number of cycles.
- 🔁 The circulation-pump blueprint accepts several indicators, so one pump
  shared by several Viega modules (e.g. three floors) runs while any of them
  needs heat. Automations created with a single indicator keep working.
- 📖 README: step-by-step guide for creating the pump automation, for one
  shared pump and for one pump per module.
- 🖼️ README: three example dashboards (standard, tiles with built-in cards,
  and a German button-card layout from HACS based on a real, anonymised
  user dashboard) with real screenshots from Home Assistant 2026.10 and
  their complete YAML.

### 🔄 Changed

- 🗄️ The cumulative open time of the actuator statistics now changes once
  per open period instead of on every polling cycle (far fewer database
  rows).

### 🐛 Fixed

- 🔢 The open-transition count and cumulative open time started again at
  0 after every restart instead of continuing from their restored values.
- 📖 The README dashboard example used `sensor.fonterra_wlan_serial_number`;
  the entity is `sensor.fonterra_wlan_module_serial_number`.

## [1.2.0] - 2026-10-10

### ⚠️ Please check after updating

- 🔑 The room diagnostic sensor's state and the base-unit error-code
  sensor's `description` attribute now hold a key such as `no_error` or
  `error_22` (shown translated in the UI). Automations or templates that
  compared the old English text, e.g. `state == "No error"`, need to use the
  key instead. States saved by older versions are converted automatically.

### ✨ Added

- 🛠️ **Repairs notifications** under Settings → Repairs when a module has
  not responded for 30 minutes or the base unit reports an error code, with
  the meaning of each code translated. They clear themselves.
- 🔁 **Circulation-pump blueprint**, importable with one click: switches a
  separately wired pump from the circulation-pump indicator, with a run-on
  time.
- ⏱️ **Heating time per room**: README guide for daily heating time with
  built-in helpers, shown as a bar chart per day.
- 🎨 **Icons**: actuator positions show a valve, the pump indicator a pump,
  the room diagnostic a check mark or warning symbol.
- 🤖 **Automatic checks** on GitHub for every change (tests, Home
  Assistant's hassfest validator, HACS validation) and a weekly test
  against the newest Home Assistant version.

### 🔄 Changed

- ⚡ **One polling cycle per module**: all of a module's values are read
  once per polling interval and update every entity together, instead of
  every entity being polled by Home Assistant every 5 seconds. A change you
  make is read back from the device right away instead of after a full
  interval.
- 🌍 **More translations**: the room diagnostic and the error-code
  description appear in your language ("Kein Fehler" instead of "No
  error"), and the power level's unit is translated ("Stufe").

### 🐛 Fixed

- 💬 Error messages in the setup and options dialogs (e.g. "Unable to
  connect to the Viega module") were shown as raw keys such as
  `cannot_connect` instead of translated text.
- 🧹 `manifest.json` code owner, a missing UI-only `CONFIG_SCHEMA`, and
  `hacs.json` keys the current HACS no longer accepts, found by the new
  automatic checks.

## [1.1.0] - 2026-10-09

### ✨ Added

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

### 🔄 Changed

- The preset (profile mode) control is only offered while the module is
  heating, matching the device, which supports profile mode only in heating
  mode.
- A read that fails because the connection broke is retried once on a new
  connection; writes are never repeated automatically.

### 🐛 Fixed

- After a connection loss every request failed until the integration was
  reloaded by hand, while all values silently froze.
- A late or misaligned response after a timeout could be taken for the
  answer to a later request.
- The first setup of a module (and every topology change) immediately ran a
  second setup, repeating discovery and opening a second connection.
- A refused connection during setup is now retried by Home Assistant instead
  of failing the entry.

## [1.0.1] - 2026-09-29

### 🐛 Fixed

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

[Unreleased]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/releases/tag/v1.0.0
