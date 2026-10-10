# Changelog

All notable changes to this integration are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### 📚 Documentation

- 🛠️ New README section *After a Viega Fonterra firmware update*: a Viega
  update can switch Modbus TCP off and give the module a new MAC and IP
  address – how to get it back and how to prevent it: use the hostname
  `smart-<serial number>`, which the module sends itself and which survives
  a MAC change (names assigned in the router and fixed IP reservations do
  not).

## [1.3.2] - 2026-10-10

🌟 **Highlights:** the integration finally shows its own icon in Home
Assistant.

### ✨ Added

- 🎨 **Integration icon in Home Assistant:** a new icon – a house with
  underfloor-heating loops and a thermometer on an orange tile – now ships
  inside the integration. Home Assistant 2026.3 or newer shows it under
  *Settings → Devices & services* after this update (you may need to
  reload the browser tab); older versions simply keep the placeholder.

### 📚 Documentation

- 🏷️ README section *Icon / branding* explains where the icon lives and
  how Home Assistant picks it up.

## [1.3.1] - 2026-10-10

🌟 **Highlights:** changing the temperature now feels calm and reliable –
clicks are collected, sent once, and the display never jumps back while
the module catches up.

### 🔄 Changed

- ⏳ **Changes are collected before sending:** a new target temperature or
  power level is shown at once and sent to the module only after it has
  been unchanged for 5 seconds. Several quick clicks on "+" or "−" lead to
  one single write of the final value.
- ⚡ Operating mode, on/off, and preset are still sent immediately.
- 🛡️ An invalid value (e.g. 40 °C) is still rejected right away; if
  sending fails after the wait, the previous value is shown again and a
  warning is logged.
- 💾 A value still waiting when the integration is reloaded is sent right
  away instead of being lost.

### 🐛 Fixed

- 🔙 **No more jumping back:** after a change, the new value appeared,
  jumped back to the old one, and only returned after the next polling
  cycle. The base unit applies a write a few seconds later; the quick
  read-back right after the write took the still-old value for a
  rejection. The written value now stays on screen while the module
  catches up (up to 60 s); only a value the module still reports
  differently after that is taken over, with a warning in the log.

## [1.3.0] - 2026-10-10

🌟 **Highlights:** changes on your thermostat cards appear instantly again,
a new sensor tells you *which* registers report invalid values, the pump
blueprint now drives one pump for several modules, and the database stays
much smaller.

### ⚠️ Please check after updating

- 🗄️ To keep the database small, three diagnostic sensors that change on
  every polling cycle are now **disabled by default** for newly set-up
  modules: *Last successful Modbus response*, *Last Modbus request
  duration*, and *Invalid Modbus value count*. On existing installations
  they stay enabled – see the README section *Keeping the database small*
  for how to keep their history out of the recorder.

### ✨ Added

- 🔎 **Invalid registers** sensor: shows how many registers the device
  currently reports as `-99` and which ones (e.g.
  `room_3.current_temperature`) – the cause behind a steadily growing
  invalid-value count. *Download diagnostics* lists every such register
  with room, manual address, and number of cycles.
- 🔁 **Pump blueprint for several modules:** select the pump indicators of
  all modules a pump supplies (e.g. three floors) – it runs while any of
  them needs heat. Automations created with a single indicator keep
  working.

### 🔄 Changed

- ⚡ Requested read-backs after a change now run within about a second
  (previously throttled to one every 10 seconds).
- 🗄️ The cumulative open time of the actuator statistics changes once per
  open period instead of on every polling cycle – far fewer database rows.

### 🐛 Fixed

- 🎛️ **Instant feedback:** a new target temperature, mode, on/off, preset,
  or power level appeared only after a delay (since 1.2.0), and two quick
  clicks on "+" raised the target by only 0.5 °C. The new value is now
  shown immediately, kept until the device confirms it, and read back
  within about a second.
- 🔢 The open-transition count and cumulative open time restarted at 0
  after every restart instead of continuing from their restored values.

### 📚 Documentation

- 🖼️ **Three example dashboards** with real screenshots from Home
  Assistant 2026.10 and their complete YAML: standard, tiles with built-in
  cards, and a German button-card layout (HACS) based on a real,
  anonymised user dashboard.
- 🪜 Step-by-step guide for the pump automation – one shared pump or one
  pump per module.
- 🗄️ New section *Keeping the database small* with recorder exclude
  examples for English and German installations.
- 🩺 Troubleshooting entry for a growing invalid-value count.
- ✏️ Corrected the WLAN-module serial number entity ID in the dashboard
  example (`sensor.fonterra_wlan_module_serial_number`).

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

[Unreleased]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.3.2...HEAD
[1.3.2]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/releases/tag/v1.0.0
