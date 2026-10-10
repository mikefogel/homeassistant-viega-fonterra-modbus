# Viega Fonterra Smart Control – system specification

This document is binding for the integration: every behaviour described with
"must" is a requirement, and changes to the integration are specified here
before they are implemented. Section numbers are stable references used by
code comments, tests, and commit messages ("spec.md 16c"); a section that is
dropped keeps its number unused (§8, §14) instead of being reassigned.

## 1. Purpose

A Home Assistant custom integration for Viega Fonterra Smart Control
underfloor-heating installations. It talks to one or more Fonterra base units
locally over Modbus TCP, discovers rooms and actuators from the device itself,
and exposes each room as a native thermostat plus linked sensors, controls,
and diagnostics, configured entirely through the Home Assistant UI.

## 2. Core objectives

- Connect to one or more Fonterra Smart Control modules over local Modbus TCP,
  each configured, polled, and removed independently.
- Discover the room/actuator topology and room names from the device's own
  registers; no hand-typed mapping is needed.
- Expose each room as a Climate entity (current/target temperature, operating
  mode, profile mode, current activity) with linked entities for everything
  Climate cannot show.
- Keep the last valid value through invalid readings and outages, recover
  from connection loss on its own, and report problems in the user's language.
- Use only registers documented in the Viega manual or confirmed on real
  hardware.

## 3. Device model

A **module** is one Fonterra Smart Control base unit with its WLAN module, set
up as one config entry and represented by one Home Assistant device (§7). It
is configured by host, port, display name (`device_name`), polling interval,
and Modbus timeout (§6b), and carries the identity values of §3a.

A module has up to 12 **rooms** and up to 12 **actuators** (heating circuits).
A room has a room number (`1`-`12`), a display name read from the device
(§4a), a measured temperature, a target temperature, a power level, an error
register (§3b), and one or more actuators. Each actuator has a position
(open/closed), a return temperature, and a "Raum-ID" register naming the room
it serves.

### 3a. Module and base-unit identity

The integration reads and keeps the identity and status of the WLAN module and
the base unit. These belong to the module's device and are independent of the
user-editable `device_name`:

- WLAN-module serial number
- base-unit serial number
- base-unit designation (name)
- base-unit error code (§3b)

Serial numbers and the designation are exposed as read-only diagnostic sensors
(and as device metadata where Home Assistant supports it). The error code is
exposed as a diagnostic sensor with the raw code and a translated description
(§5d), and drives the base-unit error binary sensor (`on` for any non-zero
code).

Identity values are read at setup and refreshed by the regular polling cycle
(§16i); no diagnostic entity polls on its own. A failed, timed-out, or `-99`
read keeps the last valid value. A missing identity register never prevents
room, sensor, or thermostat entities from being created.

Text fields span several registers and are decoded as two ASCII characters per
register in **big-endian** byte order within each register, with trailing NUL
and space characters stripped (confirmed on hardware; little-endian swaps every
character pair, e.g. "aBd" for "Bad"). The same decoder is used for every text
register and is covered by fixtures with normal text and padding.

### 3b. Base-unit and room error codes

The base-unit error register (manual `30024`) and each room's own error
register (manual `30051`/`30053`/.../`30073`) share one code space (manual
page 94, "Fehlercodes"): `0` means no error; `3`, `4`, `5`, `6`, `7`, `9`, `10`
are base-unit faults/warnings; `21`, `22`, `24` are room-scoped (thermostat
connection/battery). One table, `BASE_UNIT_ERROR_CODES` in `registers.py`, maps
codes to English descriptions; `ERROR_CODE_WARNINGS` (`10`, `22`, `24`) marks the
codes the manual describes as warnings. New codes are added to the table, never
guessed in the entity layer. A room's diagnostic reads that room's own error
register, not the base unit's.

The English descriptions are used only in logs and the diagnostics export (an
unknown code renders as `"Unknown error (code N)"`). Entities expose a stable
key instead, translated per §5d: `no_error` for `0`, `error_<code>` for every
documented code, `unknown_error` for any other code (with the numeric code as
an attribute), and `sensor_invalid` before a valid value has been read.

## 4. Room discovery

On every setup, after connecting and before any room entity is created, the
integration resolves the module's room/actuator topology from the device
(§4a). The topology may be non-1:1: a room can be fed by several actuators.
Every actuator of a room is exposed with its own position and
return-temperature entities; none is dropped. The Climate entity uses the
first actuator for its single-value attributes and all of them for
`hvac_action` (§5a.2).

### 4a. Automatic discovery via the actuator Raum-ID register

The device is the source of truth for the topology:

- Each of the 12 actuators reports the room it serves in its Raum-ID input
  register (manual `30252`/`30255`/.../`30285`, actuator base address `+2`):
  an `int16` in `1`-`12` (manual page 91).
- Each room's display name is a 24-character text field of 12 registers
  (manual `30074`/`30086`/.../`30206`, manual page 90), decoded per §3a.

Discovery reads all 12 actuators' position/return-temperature/Raum-ID
registers (one 3-register read each) and the name of every room that an
actuator reports. A room no actuator reports is omitted; a room whose name
cannot be read gets a generic `room_<n>` name; a failed read for one actuator
or name does not abort discovery.

The discovered topology is stored in the config entry's options. A previously
stored or manually edited mapping (§6a) is used **only** when live discovery
returns nothing for this setup (e.g. actuators unreachable); it never
overrides a successful discovery, because a stored mapping can drift from the
physical installation unnoticed. Persisting the discovered topology must not
trigger a reload of the entry it was written by (§12a).

## 5. Room thermostat

Each room is represented by one Climate entity – the room's primary control
surface – plus linked entities on the same device for values Climate cannot
show. Unique IDs are built from the config entry ID and the `room_id`, never
from display names, so renaming a module or room never creates duplicate
entities; this applies to every platform. All of a module's entities belong to
that module's device (§7).

### 5a. Room capability matrix

| Requirement | Home Assistant representation | Behaviour |
| --- | --- | --- |
| Current room temperature | Climate `current_temperature` | Read from the room's measured-value register |
| Target temperature | Climate `target_temperature` | Read from the target holding register |
| Change target temperature | `climate.set_temperature` | Write the target holding register |
| Operating mode (heat/cool/standby) | Climate `hvac_mode` (§5a.1) | Shared base-unit holding register `40001` |
| On/off | `climate.turn_on`/`turn_off` (§5a.1b) | Writes the operating mode |
| Profile mode (manual/profile/setback) | Climate `preset_mode` (§5a.1a) | Shared base-unit holding register `40002` |
| What the room is doing now | Climate `hvac_action` (§5a.2) | Derived, read-only |
| Power level (Leistungsstufe, `0`-`10`) | Number entity, also a Climate attribute | Room holding register |
| Flow temperature | One sensor per module, also a Climate attribute | Base-unit input register `30025` |
| Actuator return temperature | One sensor per actuator | Actuator input register |
| Actuator position | One binary sensor per actuator, device class `opening` | `0` = closed, `1` = open (not a percentage) |
| Base-unit error active | Diagnostic binary sensor, device class `problem` | `on` for a non-zero code |
| Which base-unit error | Diagnostic sensor: raw code + translated description | §3b |
| Room error/warning | Room diagnostic enum sensor (§5d) | Room's own error register |
| Room number | Climate attribute `room_id` | From the topology |

The Climate entity:

- sets `°C`, a `0.5` °C step, and a range of `5`-`30` °C in `heat`/`off` or
  `16`-`30` °C in `cool` mode (manual page 91). These are fixed, mode-dependent
  properties of the entity, not per-room registers;
- advertises `TARGET_TEMPERATURE` only when a writable target register exists.
  A room without one still shows its current and target values, but no
  control;
- validates a requested temperature against that range before writing (an
  invalid one raises a translated `ServiceValidationError`, §10a), writes the
  value ×10, and updates `target_temperature` only after the write is
  acknowledged; the next cycle reconciles it with the device (§16c);
- never replaces `current_temperature` with the requested target;
- advertises a feature only when its register is configured and writable; a
  value that is readable but not writable is shown without a control;
- exposes as attributes: `room_id`, `power_level`, `flow_temperature`,
  `return_temperature` and `actuator_position` (first actuator),
  `actuator_positions` (all actuators), `base_unit_error_code`, and
  `last_active_hvac_mode` (§5a.1b).

The flow temperature is measured once per base unit and has exactly one sensor
per module, even though every Climate entity mirrors it as an attribute.

### 5a.1. Heating and cooling operation

Holding register `40001` (manual page 91) has exactly three values:

| Climate mode | Raw value | Meaning |
| --- | --- | --- |
| `off` | `0` | Standby; frost protection stays active |
| `heat` | `1` | Regulation in heating mode |
| `cool` | `2` | Regulation in cooling mode |

`heat_cool`/automatic changeover is not advertised: the manual describes it
only as an external relay-box function (Change-over contact, manual pages 11
and 21), not as a Modbus value. An unknown raw value is reported
diagnostically and never mapped to another mode.

`hvac_mode` reflects the device value. `set_hvac_mode` validates the mode,
writes the documented value, and updates the state after the acknowledged
write; it never changes `current_temperature` or `target_temperature`. The
target control stays available in every mode with a writable setpoint.

Operating mode (`40001`) and profile mode (`40002`) exist once per **base
unit**, not per room (manual page 92). Every room's Climate entity reads and
writes the same registers, so changing the mode or preset from any room
changes it for all rooms of that module – this matches the device.

Profile mode values are `0` = `manual` ("Manuell"), `1` = `profile`
("Profil"), `2` = `setback` ("Absenkbetrieb"). The `preset_mode` identifiers
are stable and untranslated; their labels come from
`entity.climate.room.state_attributes.preset_mode.state` in
`translations/*.json`.

### 5a.1a. Profile mode only in heating mode

Profile mode exists only in heating mode (manual page 91). `PRESET_MODE` is
therefore advertised only while `hvac_mode` is `heat` (and the profile-mode
register is configured); in `cool` and `off` the preset control is hidden.
`set_preset_mode` outside heating mode raises a translated
`ServiceValidationError` (§10a) without writing. The last profile mode read
from the device is kept while hidden and shown again in heating mode;
changing the operating mode never writes the profile-mode register.

### 5a.1b. Turning the installation on and off

The Climate entity advertises `TURN_ON` and `TURN_OFF`:

- `turn_off` writes operating mode `0` (standby, frost protection stays
  active), like `set_hvac_mode(off)`.
- `turn_on` restores the last non-off mode read from or written to the device
  (`heat` or `cool`, default `heat`). This mode is kept as the
  `last_active_hvac_mode` attribute and survives a restart (§15).
- Neither writes anything when the module is already in the requested state.

Like the operating mode itself, this affects every room of the module.

### 5a.2. Current HVAC action

`hvac_mode` says what the module is *set* to; `hvac_action` says what the room
is *doing*. Home Assistant's built-in thermostat and tile cards show it as text
and colour ("Heizt"/"Kühlt"/"Leerlauf"/"Aus"), and the Climate entity's history
graph shows coloured bands while the room actually heats or cools. Labels and
colours come from Home Assistant itself.

There is no per-room heating register, so the value is derived:

| Operating mode | Actuators of the room | `hvac_action` |
| --- | --- | --- |
| `0` (standby) | any | `off` |
| `1` (heating) | at least one open | `heating` |
| `1` (heating) | all closed | `idle` |
| `2` (cooling) | at least one open | `cooling` |
| `2` (cooling) | all closed | `idle` |
| unknown | any | `None` |
| `1` or `2` | no position read yet | `None` |

- **All** actuators of the room count; the position register of every
  actuator assigned to the room is read.
- A failed or `-99` position read keeps that actuator's last position (§10).
- The value follows the device on every cycle and is not debounced (the pump
  debounce of §5c does not apply). Whether to smooth it is an open item (§17).
- It is read-only and adds no register, write, or feature flag.
- After a restart it is derived from the restored mode and positions (§15).

### 5a.3. Dashboard presentation without frontend add-ons

Everything the integration exposes must be usable with Home Assistant's
built-in cards (`thermostat`, `tile` with its built-in features, `entities`,
`glance`, `history-graph`, `statistics-graph`, `heading`, `area`,
`markdown`, ...). No feature may depend on a HACS or other custom frontend
card.

The README offers three example dashboards, each as a screenshot plus its
complete YAML (kept in `docs/dashboards/`, identical to the README blocks):

1. **Standard** – thermostat, entities, glance, and history-graph cards;
   works on the minimum Home Assistant version.
2. **Tiles** – a sections view with one column per room (tile cards with the
   target-temperature feature, actuator, return-temperature, and diagnostic
   tiles), labelled module-status badges, and a full-width history graph;
   built-in cards only.
3. **Tiles with button-card** – the same content in a denser layout. This is
   the only example that uses a HACS card and must say so clearly: it is
   optional, names the card and the version it was tested with, and nothing
   else in the README depends on it. Its texts come from Home Assistant's own
   formatting (`hass.formatEntityState` etc.), so they follow the user's
   language.

The screenshots must show what the YAML actually produces: they are taken
from a real Home Assistant instance running this integration against a
simulated, anonymous module (generic room names, no real serial numbers or
addresses), with `tools/dashboard-screenshots/render.sh`, never drawn by hand.

### 5b. Register addressing and writes

Register addresses and scaling come from `registers.py`, never from the
entity layer. A room mapping can be minimal (`name`, `actor`, `sensor`); room
numbers resolve from the `room_id`'s trailing digits (`"room_1"` → `1`) when
no `room_number` is given, and the default registers follow from it. Optional
per-room overrides exist for the target-temperature, power-level,
actuator-position, flow-temperature, return-temperature, operating-mode,
profile-mode, and error-code registers. Room and actuator numbers `1`-`12`
are supported.

Manual addresses convert to Modbus PDU addresses as
`pdu = manual - 40000` for holding registers (`4xxxx`) and
`pdu = manual - 30000` for input registers (`3xxxx`): the last four digits
*are* the PDU address. This is confirmed by the manual's wire examples
(pages 94-95: manual `40001` → PDU `0x0001`, `40053` → `0x0035`, `30250` →
`0x00FA`) and real hardware. The common Modicon convention
(`manual - 40001`) is off by one for this device and must never be used.

Default layout per room *n* and actuator *m* (manual addresses):

| Register | Address |
| --- | --- |
| Room power level / target temperature (holding) | `40048+2n` / `40049+2n` (room 1: `40050`/`40051`) |
| Room measured value / error (input) | `30048+2n` / `30049+2n` (room 1: `30050`/`30051`) |
| Room name (input, 12 registers) | `30074+12(n-1)` |
| Actuator position / return temperature / Raum-ID (input) | `30250+3(m-1)` / `+1` / `+2` |
| Operating mode / profile mode (holding, base unit) | `40001` / `40002` |
| Error code / flow temperature (input, base unit) | `30024` / `30025` |
| WLAN-module serial / base-unit serial / base-unit name (input, text) | `30001` (5 registers) / `30006` (5) / `30011` (12) |

Temperatures are `int16` in tenths of a degree. Every write – target
temperature, power level, operating mode, profile mode – uses function `0x10`
(Write Multiple Registers, quantity `1`, byte count `2`), as in the manual's
own example ("Beispiel 2", page 95: `... 01 10 00 35 00 01 02 00 D2`); `0x06`
is never used. Each writable register has a defined range (target temperature
§5a, power level `0`-`10`, modes §5a.1), and the entity state changes only
after the write is acknowledged.

### 5c. Circulation pump indicator

The device has no pump register. One binary sensor per module (device class
`running`) is derived from the position registers of the module's **used**
actuators (those assigned to a room by discovery):

- `on` while at least one used actuator is confirmed open, `off` once all are
  confirmed closed, `None` (unknown) until at least one actuator has settled.
- Each actuator's reading is debounced: its contribution changes only after the
  same raw value has been read in **3 consecutive polling cycles**
  (`PUMP_DEBOUNCE_READS`); a different value restarts that actuator's count at
  `1`; a failed or `-99` read neither advances nor resets it. Debouncing is per
  actuator; the aggregate turns `on` as soon as any actuator is confirmed open.
  Each polling cycle counts once, even if the entity is updated more often.
- It is read-only, writes nothing, and controls nothing on the device. It is
  meant to drive the user's own automation for a separately wired pump
  (§16k); it must not be modelled as a switch.

### 5d. Translated states, units, names, and icons

Everything an entity shows follows Home Assistant's language setting
(`translations/de.json` and `translations/en.json`, always with the same keys):

- **Names:** every entity name comes from `translation_key` (with
  `translation_placeholders` such as room and actuator), never from a
  hardcoded `_attr_name`.
- **States and attribute values** that are text are stable keys: the room
  diagnostic is an `enum` sensor whose state is one of the keys of §3b
  (`entity.sensor.room_diagnostic.state.<key>`, raw code as `error_code`
  attribute), and the base-unit error-code sensor's `description` attribute
  uses the same keys
  (`entity.sensor.base_unit_error_code.state_attributes.description.state.<key>`).
  States restored from versions that stored the English text are mapped to the
  matching key.
- **Units** that are words are translated
  (`entity.<platform>.<key>.unit_of_measurement`): the power level's unit is
  "Stufe"/"level".
- **Icons** are defined per entity and state in `icons.json`: the actuator
  position shows a valve (`mdi:valve-open`/`mdi:valve-closed`), the pump
  indicator a pump (`mdi:pump`/`mdi:pump-off`), the room diagnostic a check
  mark for `no_error` and a warning symbol otherwise; services have icons too.
  Device classes stay unchanged, so state labels ("Geöffnet"/"Geschlossen",
  "Läuft"/"Aus") keep coming from Home Assistant.
- Preset labels follow §5a.1, action errors §10a, repairs §16j, and
  configuration-dialog texts §6a.

## 6. Multiple modules

Any number of modules can be configured in one Home Assistant installation.
Each has its own config entry, device, connection, polling cycle, entities,
and repairs; a failure, reload, or removal of one never affects another.

### 6a. Home Assistant UI configuration

Modules are set up, edited, and removed entirely in the Home Assistant UI; no
YAML or JSON editing is needed or supported (the integration declares
`CONFIG_SCHEMA = cv.config_entry_only_config_schema`).

**Adding a module.** The setup form asks for the parameters of §6b – and
nothing else; in particular no room mapping, since rooms are discovered from
the device (§4a). `host` accepts IPv4 addresses and resolvable hostnames. The
connection is tested before the entry is created; invalid values and a failed
connection are shown in the form as translated messages. Form error texts
live under `config.error` and `options.error` in the translation files (not
per step), as Home Assistant requires. `host:port` is the entry's unique ID: a
second entry for the same device is rejected (`already_configured`).

**Editing a module.** The options flow edits display name, host, port,
polling interval, Modbus timeout, and, for every room already reported by the
device, its name, actuator(s), sensor, and target-temperature register. A room
with several actuators keeps all of them when the form is saved. The
connection is tested before saving; afterwards the module reloads with the new
settings (which re-runs discovery, §4a). The options flow obtains
`config_entry` from Home Assistant's `OptionsFlow` base class, not through its
own constructor (deprecated since Home Assistant 2024.12).

**Removing a module.** Deleting the integration entry – or the module's
device from its own device page (`async_remove_config_entry_device`) – removes
the module's connection, entities, device, and repairs. Removal always
succeeds, also when the device is offline or its socket is broken: every
blocking step of the disconnect is bounded by the Modbus timeout (a hung close
never raises, so a `try`/`except` alone is not enough), and a failure is
logged, never blocking.

**Setup failures.** If the module cannot be reached at setup, the integration
raises `ConfigEntryNotReady` (any connection error, including a refused
connection), so Home Assistant retries with back-off instead of leaving the
entry broken.

### 6b. Configuration parameters

| Parameter | Meaning | Default | Range |
| --- | --- | --- | --- |
| `host` | IP address or hostname of the module | `192.168.0.188` | – |
| `port` | Modbus TCP port | `502` | `1`-`65535` |
| `device_name` | Display name of the module and its device | – | – |
| `polling_interval` | Seconds between two polling cycles (§16i) | `30` | `5`-`300` |
| `modbus_timeout` | Seconds to wait for a Modbus response | `5` | `1`-`30` |

Port `502` is the manual's port for normal/DHCP networks; `192.168.1.1` is the
device's address only in point-to-point mode.

A room mapping is never a setup parameter. The stored mapping (discovered or
edited in the options flow) has this shape and serves only as the fallback of
§4a; each room's `name` is the display name of its entities:

```python
rooms = {
    "room_1": {"name": "Wohnzimmer", "room_number": 1, "actor": 1, "sensor": 1},
    "room_2": {"name": "Bad", "room_number": 2, "actor": [2, 3], "sensor": 2},
}
```

### 6c. Polling model

Each module has one polling cycle (§16i) per `polling_interval` that reads all
of its registers and then updates all of its entities. Entities are not polled
by Home Assistant individually and never read the device themselves.

## 7. Distinguishable devices

Each module's device is identified by its own config entry and named with its
own `device_name` – never a fixed string – so several modules are always
distinguishable in the device registry, entity picker, and dashboards.

## 8. (Not used)

## 9. Register map

`registers.py` is the single source of register addresses, scaling, and the
topology helpers (`room_registers`, `actor_registers`,
`known_addresses_for_topology`, ...). Only addresses documented in the manual
or confirmed with logged frames on real hardware may be used (§16h); the real
map spans roughly PDU `0`-`285`. `REGISTER_DEFINITIONS` in `registers.py`
illustrates the schema with placeholder addresses (`1000`+) that are not
Viega registers; it must not be instantiated as live entities.

All register values are decoded as signed 16-bit integers (§10). The
integration uses its own Modbus TCP client, not Home Assistant's YAML Modbus
platform, so that platform's `count` problem with `int16` on some firmware
(see the reported
[Fonterra Smart Control update issue](https://community.simon42.com/t/modbus-problem-nach-update-fonterra-smart-control-viega/29014))
does not apply; the protocol quantity field is always sent (`1` for a single
register). A YAML Modbus alternative, if ever offered, must omit `count` for
`int16`.

## 10. Data validity

The device reports `-99` for a value it considers invalid (e.g. no thermostat
paired). `-99`, a failed read, and a value missing from a polling cycle are all
treated the same way:

- the entity keeps its last valid value – for every register-backed value,
  including Climate attributes, modes, and presets, and across any number of
  consecutive failures;
- the sentinel is detected on the raw value **before** scaling (a raw `-99`
  temperature must never become `-9.9` °C);
- no exception escapes the update;
- the room's diagnostic sensor shows the room's state (§5d), and the entity
  keeps its latest internal error text in `last_error_message` for logs.

Holding and input registers are both decoded as signed `int16`, so `-99`
(`0xFF9D`) is recognisable on every read path; writes are unsigned 16-bit
values on the wire. Ordinary values (temperatures, levels, modes) are far below
`32768`.

### 10a. User-facing errors for actions

Background polling never raises (§10). Actions a user triggers – target
temperature, operating mode, preset, power level, on/off, rediscovery – report
failures as translated messages, never as a raw Python exception with a
traceback:

| Failure | Exception | Examples |
| --- | --- | --- |
| The request itself is invalid | `ServiceValidationError` | temperature outside the mode's range; power level outside `0`-`10`; unsupported mode or preset; preset outside heating mode; register not configured for this room; unknown device; module not loaded |
| A valid request could not be carried out | `HomeAssistantError` | module unreachable or reconnecting; timeout; Modbus exception response; rediscovery failed |

- Every exception carries `translation_domain`, `translation_key`, and
  `translation_placeholders`; every key has a message in the `exceptions`
  section of every translation file.
- Transport errors are chained (`raise ... from err`) and logged at DEBUG, not
  as an ERROR traceback.
- Validation happens before anything is sent; an invalid request never causes
  a write.
- A failed write leaves the displayed value unchanged.

## 11. Modbus transaction validation

Every response must pass all of these checks before its values are used:

- the transaction ID matches the request (a mismatch raises `ValueError`);
- the function code echoes the request's; a code with the high bit set (e.g.
  `0x83`) is a Modbus exception response and is reported with the device's
  exception code, never passed to the decoder;
- a read returns exactly as many registers as requested.

TCP is a byte stream: the client first reads the 6-byte MBAP header and then
exactly as many bytes as its length field states, reassembling a response
split across several TCP segments, instead of assuming one read returns the
whole frame.

### 11a. Frame-level logging

With the integration's logger at DEBUG (Home Assistant's `logger.logs`), every
TX and RX frame is logged with direction, host, port, length, transaction ID,
unit ID, function code, and the complete frame in hex. This is the only switch
(no separate option), it is off by default, and it never changes protocol
behaviour. Logs contain no credentials or unrelated Home Assistant state; a
malformed or truncated frame is logged safely. Response validation (§11) runs
after the RX frame is logged.

### 11b. Request serialization

All of a module's traffic shares one connection. At most one request is in
flight; its response is read before the next request is sent, so frames can
never interleave or be attributed to the wrong request.

### 11c. Connection loss and automatic reconnection

A connection that breaks during operation (base unit or WLAN module restart,
Wi-Fi or router outage, peer closing the connection) must never require a
manual reload; the integration resumes on its own once the module is reachable.

- **Discarding:** a socket error/EOF, a response timeout, or any integrity
  failure of §11 (transaction ID, function code, register count, malformed
  frame) discards the connection – closing the socket (bounded by the
  timeout) and dropping all buffered bytes – because the byte stream can no
  longer be trusted to line up with the requests. A well-formed Modbus
  exception response does **not** discard the connection.
- **Reconnecting:** the next request reconnects lazily, inside the
  serialization lock (§11b). After a failed attempt, further attempts back off
  from `5` s, doubling up to the module's `polling_interval`; requests during
  the back-off fail immediately. A successful connection resets the back-off.
- **Retrying:** a read that hit a broken connection is retried at most once on
  the new connection; a write is never retried automatically.
- **During an outage** entities keep their last valid values (§10); nothing
  raises out of an entity update, blocks the event loop beyond the timeout, or
  affects another module.
- **Logging:** the loss is logged once at WARNING, the restoration once at
  INFO. The number of reconnections and the time of the last one are
  connection-health metrics (§16b).
- **Unload:** after `disconnect()` the client never reconnects, even for a
  request that was already queued.

## 12. Implementation, packaging, and release

- Type-annotated Python; tested on Python 3.12 (pinned test environment) and
  the Python version of the newest Home Assistant (§12a). The minimum Home
  Assistant version is the one in `hacs.json`.
- Clear separation of register map (`registers.py`), transport
  (`modbus_handler.py`), polling (`coordinator.py`), and entity platforms; no
  placeholder-only code paths.
- `manifest.json` declares `config_flow: true` and `@mikefogel` as code owner;
  `hacs.json` keeps `content_in_root: false` and contains only keys the
  current HACS schema accepts (domain and IoT class come from
  `manifest.json`).
- Development-only files (`tests/`, `tools/`, `requirements-test.txt`,
  `pytest.ini`, `.github/`, `.gitattributes`, `.gitignore`) are versioned but marked
  `export-ignore` in `.gitattributes`, so release archives do not contain
  them; HACS installs only `custom_components/viega_fonterra_modbus/`.
  Personal tooling (`.claude/`, private scripts) is not versioned at all
  (`.gitignore`). Files are never deleted to keep them out of a release.
- `CHANGELOG.md` (Keep a Changelog, emoji headings: ⚠️ for anything users
  must check after updating, ✨ Added, 🔄 Changed, 🐛 Fixed) lists every
  user-visible change under `[Unreleased]` as it is committed.
- A release: renames `[Unreleased]` to the new version and date; sets the same
  version in `manifest.json` (`1.2.0`) and the tag (`v1.2.0`); is tagged only
  from a commit whose CI passed (§12a); checks the tagged manifest and
  `git archive <tag>` for development files; never replaces an existing remote
  tag; uses the changelog section as GitHub release notes; and is complete only
  once branch and tag are on the remote.

### 12a. Tests, continuous integration, and diagnostics export

**Tests** use `pytest-homeassistant-custom-component` (pinned in
`requirements-test.txt`) with a real Home Assistant instance for everything a
stand-in cannot verify: config and options flows (success, cannot-connect,
duplicate host/port, multi-actuator round trip), the setup lifecycle (setup,
reload with stable unique IDs, connection retry, removal also when
`disconnect()` fails, one module's reload leaving another untouched, entities
fed by the polling cycle), repairs, and the blueprint. Unit tests cover
protocol framing, registers, discovery, and entity behaviour.

The update listener reloads an entry only for a change that differs from the
configuration its running setup applied; persisting the discovered topology
during setup (§4a) must not cause a second setup, discovery, and connection.

**Continuous integration** (GitHub Actions, `.github/workflows/`) runs on
every push to `main` and every pull request: the test suite with the pinned
environment (`tests.yml`), and hassfest plus the HACS validation
(`validate.yml`, also weekly). A weekly run (`latest-home-assistant.yml`, also
on demand) tests against the newest test harness and thus the newest Home
Assistant; a failure there means "update the pinned version", not a release
blocker.

**Diagnostics export.** "Download diagnostics" returns, without any extra
Modbus read: the module's configuration (`host` redacted) and identity; every
room with its number, name, and resolved register addresses; every actuator
of every room with its registers; and a bounded extended snapshot (§16e).

## 13. Acceptance criteria

### Setup and modules

- Modules are added, edited, and removed in the UI only, with host or
  hostname, port, display name, polling interval, and timeout; no room mapping
  is typed at setup.
- A duplicate host/port is rejected; every form error is a translated message.
- Several modules stay fully independent; each device carries its own
  `device_name`.
- A module can be removed also while offline; an unreachable module at setup
  is retried by Home Assistant.
- Setup connects and discovers once; it does not reload itself.

### Discovery

- Rooms, names, and actuator assignments (including several actuators per
  room) come from the device; a stored mapping is only a fallback.
- Every actuator of a room has its own position and return-temperature
  entities.
- Rediscovery updates entities in place with stable unique IDs (§16a).

### Climate

- One Climate entity per room with current and target temperature, correct
  range and step per mode, and a target control only when writable.
- Heat, cool, and off map to the documented operating-mode values; no
  automatic mode; mode changes never touch the temperatures.
- Presets only in heating mode; on/off restores the last active mode, also
  after a restart.
- `hvac_action` reflects all of the room's actuators and is usable by the
  built-in cards and history graph.

### Other entities

- Flow temperature (one per module), return temperature and position (per
  actuator), power level (Number), base-unit identity and error sensors, room
  diagnostics, circulation-pump indicator with per-actuator 3-cycle debounce,
  connection-health and actuator-statistics sensors.
- Every name, text state, text attribute, and word unit is translated; icons
  per §5d.
- Every entity restores its last value after a restart (§15).

### Data, transport, and polling

- `-99`, failed reads, and outages keep the last valid value; nothing is
  scaled before the sentinel check.
- Transaction ID, function code, and register count are validated; split TCP
  frames are reassembled; requests never interleave; frame logging is
  DEBUG-only.
- One polling cycle per module reads adjacent registers in blocks without
  bridging gaps and updates all entities; writes trigger an early cycle and
  are verified.
- After a connection loss the integration reconnects on its own with
  back-off; a late or misaligned response is never accepted; writes are never
  retried; no reconnect after unload.

### Errors and diagnostics

- Invalid requests raise translated `ServiceValidationError`s, failed actions
  translated `HomeAssistantError`s; no raw exception reaches the user.
- An unreachable module and base-unit errors appear under Settings → Repairs
  and clear themselves.
- The diagnostics export contains configuration, identity, topology, and
  register addresses with the host redacted.

### Project

- Everything is usable with built-in dashboard cards; the pump blueprint and
  the heating-time guide work with built-in features.
- Tests pass on the pinned and the newest Home Assistant; hassfest and HACS
  validation pass; release archives contain no development files.

## 14. (Not used)

## 15. State restoration after a restart

After a restart of Home Assistant or a reload, every entity on every platform
shows its last valid state immediately (`RestoreEntity`) – never a default,
`unknown`, or `unavailable` while waiting for the first polling cycle. This
covers an entity's entire displayed state; for the Climate entity that is
`hvac_mode`, `preset_mode`, current and target temperature, and every
attribute of §5a (including `actuator_positions` and `last_active_hvac_mode`,
so `hvac_action` and `turn_on` work right away). Exceptions, by design: the
connection-health sensors (they describe the new connection) and the
open-actuator count of §16f (only meaningful after a fresh debounce).

## 16. Operational features

Each feature below must not introduce undocumented registers or change the
register map (§9).

### 16a. Explicit rediscovery

The `viega_fonterra_modbus.rediscover` service (target: the module's device)
re-reads the Raum-ID and room-name registers, compares the result with the
current topology, and adds, removes, or rebuilds only the affected entities –
without reloading the entry, keeping unique IDs stable – and rebuilds the pump
indicator if the set of used actuators changed. Changes are logged and fired
as a `viega_fonterra_modbus_rediscovery` event. It runs on the existing
connection without interleaving with a polling cycle, never replaces the
topology with an empty result, requests an early polling cycle after a change,
and reports an unknown device, an unloaded module, or a failed read as a
translated error (§10a).

### 16b. Connection health metrics

Diagnostic sensors per module, derived from the client's own bookkeeping
without extra requests: last successful response, last failed request,
consecutive failures, invalid-value count (including `-99`), last Modbus
exception code, duration of the last successful request, number of
reconnections, and time of the last reconnection. They never overwrite device
values and expose no network-identifying data.

### 16c. Read-after-write verification

After an acknowledged write the integration requests an early polling cycle
(§16i) and compares the device's next valid value from a **newer** cycle than
the write with the written value. The device value is authoritative: on a
mismatch the entity shows the device value and a warning is logged. A failed
write is never treated as a state change.

### 16d. Contiguous register-block reads

Within a polling cycle, adjacent registers are read with one request (at most
`125` registers). Input and holding registers are never combined, undocumented
gaps are never bridged, and values are only assigned to their declared
addresses. A failed block only drops its own registers from that cycle.

### 16e. Extended downloadable diagnostics

The diagnostics export additionally contains a bounded snapshot: the
connection-health metrics, a fixed-size history of recent Modbus exception
codes, the documented addresses a polling cycle reads for the topology, and the
last rediscovery's changes. No frames, no unbounded data, no firmware version
(the device documents no such register), no network identifiers.

### 16f. Derived actuator statistics

Diagnostic sensors derived from the pump indicator's debounced actuator values
(no extra reads): number of open actuators, open-transition count, time of the
last transition, and cumulative open time. The open count stays unavailable
until a debounced value exists and is not restored; the other three are
restored. They are not presented as device registers.

### 16g. Multi-module overview

The `viega_fonterra_modbus.overview` service returns, per module and without
extra reads: reachability, active base-unit error, stale/failed communication,
and room/actuator counts. Same-named rooms of different modules are never
merged; every value keeps its config entry ID; one module's failure never
affects another's entry.

### 16h. Explicitly excluded capabilities

Excluded until Viega documents them or hardware tests confirm them: manual room
mapping as a replacement for discovery; outdoor-temperature or pump-status
registers; time schedules, holiday programs, humidity, dew point, and
firmware-version registers; probing or writing unknown or reserved addresses.

### 16i. Central update coordinator

One `DataUpdateCoordinator` per module (`ViegaDataCoordinator` in
`coordinator.py`, stored as the entry's `polling` object) runs the polling
cycle:

- Once per `polling_interval` it reads every register of the topology
  (`known_addresses_for_topology`) plus any other register an entity asked for
  in the last `REQUEST_TTL_CYCLES` cycles, in blocks (§16d), and then notifies
  all of the module's entities.
- Entities (`ViegaCoordinatedEntity` in `entity.py`) set `should_poll = False`
  and, after each cycle, run their own value handling on that cycle's data via
  the coordinator's `read()`, which never touches the device; a register
  missing from the cycle behaves like a failed read. They deliberately do not
  use `CoordinatorEntity`, whose availability follows the cycle's success:
  entities must stay available on their last values during an outage.
- A cycle never raises `UpdateFailed`; a failed block only drops its own
  registers.
- A successful write and a topology-changing rediscovery request an early
  cycle. The cycle counter (`generation`) drives write verification (§16c) and
  the once-per-cycle pump debounce (§5c).
- Reconnection stays in the transport (§11c); rediscovery runs through
  `run_exclusive()` so it never interleaves with a cycle.

### 16j. Repair issues

Problems that need attention and do not fix themselves are raised under
**Settings → Repairs**, so they are noticed without watching a dashboard or
having access to the installation:

- **Module unreachable:** no successful response for `30` minutes (from the
  last success, or from setup if there was none), checked every minute.
  Severity `error`; placeholders: module name and time of the last success.
- **Base-unit error:** the base-unit error code is non-zero. Severity
  `warning` for `ERROR_CODE_WARNINGS`, `error` otherwise. Each documented code
  has its own translation key (fully translated text); unknown codes share a
  generic key with the code as placeholder. A new code replaces the issue.

Rules: one issue per module and type (issue ID from the config entry ID); not
fixable through a flow – each clears itself (next successful response; code
back to `0`); titles and descriptions come from the `issues` section of every
translation file; unload and removal delete a module's issues; only values the
integration already reads are used, and a failed or `-99` error-code read
neither raises nor clears the issue. A module that cannot be reached at setup
is already shown by Home Assistant as "retrying setup" and gets no issue.

### 16k. Circulation-pump blueprint

The repository ships an automation blueprint
(`blueprints/automation/viega_fonterra_modbus/circulation_pump.yaml`) that
switches a separately wired pump from the pump indicator(s) of §5c:

- Inputs: one or more pump indicators (one per module that the pump supplies
  – e.g. all three floors for one shared pump, or one floor for its own pump),
  the pump switch (`switch`, `light`, or `input_boolean`), and a run-on time
  (default `5` minutes, `0` allowed). Automations created with a single
  indicator keep working.
- The pump turns on as soon as any indicator turns `on`, and off only when all
  indicators are `off` and the last one has stayed `off` for the run-on time;
  an indicator turning `on` during the run-on time keeps the pump running.
  After a Home Assistant start with an indicator `on`, the pump is switched on.
- While any indicator is `unavailable`/`unknown`, the pump is not switched off.
- Only automation syntax supported by the minimum Home Assistant version is
  used; the blueprint is part of release archives.
- The README has a one-click import button (pointing to `main`) and a
  step-by-step guide for one shared pump and for one pump per module.
- Tests validate the blueprint against Home Assistant's schema and run real
  automations from it, including the three-floor case.

### 16l. Heating time per room (documentation)

The README shows how to get each room's daily heating time from `hvac_action`
with built-in helpers (UI and YAML): a template binary sensor ("room is
heating"), because the History stats helper counts states, not attributes,
then a History stats sensor on it, and a `statistics-graph` bar chart of the
daily totals. No integration code is involved; the snippet must keep working
on the Home Assistant versions CI tests.

## 17. Open items (not yet scheduled)

Approved ideas, deliberately postponed. Each must be specified in its own
section before it is implemented.

- **Submit the brand icons** in `brands/custom_integrations/viega_fonterra_modbus/`
  to `home-assistant/brands`, so Home Assistant shows the integration's icon
  under Settings → Devices & services. First check whether Home Assistant's
  current handling of custom-integration brands still requires that route.
- **Decide whether to smooth `hvac_action`** (§5a.2). The actuators toggle
  every few minutes, so the heating bands look striped (confirmed on the real
  installation with v1.1.0). Decide whether to keep the unsmoothed device state
  or require e.g. a minimum continuous duration before reporting heating or
  cooling.
