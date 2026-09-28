# Register-Adressplan — Viega Fonterra Smart Control

Datum: 2026-09-18
Quelle: `Fonterra Smart Control-de-DE.pdf`, Abschnitt „Modbus Registerdefinition"
(S. 89–93, „Input-Register" und „Holding-Register"), abgeglichen mit
`custom_components/viega_fonterra_modbus/registers.py`.

Alle Manual-Adressen (Modicon-Schreibweise, `3xxxx`/`4xxxx`) werden gemäß
`registers.py::pdu_address()` in die PDU-Adresse umgerechnet:
`pdu = manual_address - 30000` (Input, Funktion `0x04`) bzw.
`pdu = manual_address - 40000` (Holding, Lesen `0x03` / Schreiben `0x10` —
**nicht** `0x06`, siehe `spec.md` §14 „The write command used the wrong
function code"). Es gibt
**keinen** zusätzlichen `-1`-Offset (siehe `spec.md` §14 „PDU address offset,
take two" — das war ein früherer, durch die Handbuch-Beispiele widerlegter
Fehler).

Diese Datei ist der von dir angeforderte Plan: welche Adresse durch welche
Home-Assistant-Entity abgedeckt wird, und welche Adressen im dokumentierten
Bereich **nicht** vorkommen (Lücken/reserviert) bzw. außerhalb des
dokumentierten Bereichs liegen (unbekannt, nicht zu raten). Kapitel 5 fasst
eine gezielte Websuche nach weiteren, außerhalb dieses Handbuchs
dokumentierten Registern zusammen.

## 1. Input-Register (Funktion `0x04`, Bereich `30001`–`30285`)

| Manual-Adresse(n) | PDU | Länge | Bereich | Beschreibung | Home-Assistant-Entity | Datei/Klasse |
| --- | --- | --- | --- | --- | --- | --- |
| 30001–30005 | 1–5 | 5 | Basiseinheit | WLAN-Modul Seriennummer (string10) | `sensor.wlan_module_serial_number` | `sensor.py::ViegaBaseUnitIdentitySensor` |
| 30006–30010 | 6–10 | 5 | Basiseinheit | Basiseinheit Seriennummer (string10) | `sensor.base_unit_serial_number` | `sensor.py::ViegaBaseUnitIdentitySensor` |
| 30011–30022 | 11–22 | 12 | Basiseinheit | Bezeichnung (string24) | `sensor.base_unit_name` | `sensor.py::ViegaBaseUnitIdentitySensor` |
| **30023** | **23** | 1 | — | **nicht dokumentiert** | — | *(Lücke, siehe §3)* |
| 30024 | 24 | 1 | Basiseinheit | Fehlercode | `binary_sensor.base_unit_error` (Schwelle) + `sensor.base_unit_error_code` (Rohwert+Text) | `binary_sensor.py::ViegaBaseUnitErrorBinarySensor`, `sensor.py::ViegaBaseUnitIdentitySensor` |
| 30025 | 25 | 1 | Basiseinheit | Vorlauftemperatur °C (×10) | `sensor.flow_temperature` (einmal je Gerät) | `sensor.py::ViegaBaseUnitTemperatureSensor` |
| **30026–30049** | **26–49** | 24 | — | **nicht dokumentiert** | — | *(Lücke, siehe §3)* |
| 30050 | 50 | 1 | Raum 1 | Ist-Temperatur °C (×10) | `climate` (Raum 1) `current_temperature` | `climate.py::ViegaRoomClimateEntity` |
| 30051 | 51 | 1 | Raum 1 | Fehlercode | `sensor.<raum1>_diagnostic` (Text) | `diagnostic.py::ViegaDiagnosticTextEntity` |
| 30052 | 52 | 1 | Raum 2 | Ist-Temperatur °C (×10) | `climate` (Raum 2) | `climate.py` |
| 30053 | 53 | 1 | Raum 2 | Fehlercode | `sensor.<raum2>_diagnostic` | `diagnostic.py` |
| 30054 | 54 | 1 | Raum 3 | Ist-Temperatur °C (×10) | `climate` (Raum 3) | `climate.py` |
| 30055 | 55 | 1 | Raum 3 | Fehlercode | `sensor.<raum3>_diagnostic` | `diagnostic.py` |
| 30056 | 56 | 1 | Raum 4 | Ist-Temperatur °C (×10) | `climate` (Raum 4) | `climate.py` |
| 30057 | 57 | 1 | Raum 4 | Fehlercode | `sensor.<raum4>_diagnostic` | `diagnostic.py` |
| 30058 | 58 | 1 | Raum 5 | Ist-Temperatur °C (×10) | `climate` (Raum 5) | `climate.py` |
| 30059 | 59 | 1 | Raum 5 | Fehlercode | `sensor.<raum5>_diagnostic` | `diagnostic.py` |
| 30060 | 60 | 1 | Raum 6 | Ist-Temperatur °C (×10) | `climate` (Raum 6) | `climate.py` |
| 30061 | 61 | 1 | Raum 6 | Fehlercode | `sensor.<raum6>_diagnostic` | `diagnostic.py` |
| 30062 | 62 | 1 | Raum 7 | Ist-Temperatur °C (×10) | `climate` (Raum 7) | `climate.py` |
| 30063 | 63 | 1 | Raum 7 | Fehlercode | `sensor.<raum7>_diagnostic` | `diagnostic.py` |
| 30064 | 64 | 1 | Raum 8 | Ist-Temperatur °C (×10) | `climate` (Raum 8) | `climate.py` |
| 30065 | 65 | 1 | Raum 8 | Fehlercode | `sensor.<raum8>_diagnostic` | `diagnostic.py` |
| 30066 | 66 | 1 | Raum 9 | Ist-Temperatur °C (×10) | `climate` (Raum 9) | `climate.py` |
| 30067 | 67 | 1 | Raum 9 | Fehlercode | `sensor.<raum9>_diagnostic` | `diagnostic.py` |
| 30068 | 68 | 1 | Raum 10 | Ist-Temperatur °C (×10) | `climate` (Raum 10) | `climate.py` |
| 30069 | 69 | 1 | Raum 10 | Fehlercode | `sensor.<raum10>_diagnostic` | `diagnostic.py` |
| 30070 | 70 | 1 | Raum 11 | Ist-Temperatur °C (×10) | `climate` (Raum 11) | `climate.py` |
| 30071 | 71 | 1 | Raum 11 | Fehlercode | `sensor.<raum11>_diagnostic` | `diagnostic.py` |
| 30072 | 72 | 1 | Raum 12 | Ist-Temperatur °C (×10) | `climate` (Raum 12) | `climate.py` |
| 30073 | 73 | 1 | Raum 12 | Fehlercode | `sensor.<raum12>_diagnostic` | `diagnostic.py` |
| 30074–30085 | 74–85 | 12 | Raum 1 | Name (string24) | Anzeigename Raum 1 (Discovery) | `room_mapping.py::RoomMappingDiscovery.discover_from_device` |
| 30086–30097 | 86–97 | 12 | Raum 2 | Name (string24) | Anzeigename Raum 2 | `room_mapping.py` |
| 30098–30109 | 98–109 | 12 | Raum 3 | Name (string24) | Anzeigename Raum 3 | `room_mapping.py` |
| 30110–30121 | 110–121 | 12 | Raum 4 | Name (string24) | Anzeigename Raum 4 | `room_mapping.py` |
| 30122–30133 | 122–133 | 12 | Raum 5 | Name (string24) | Anzeigename Raum 5 | `room_mapping.py` |
| 30134–30145 | 134–145 | 12 | Raum 6 | Name (string24) | Anzeigename Raum 6 | `room_mapping.py` |
| 30146–30157 | 146–157 | 12 | Raum 7 | Name (string24) | Anzeigename Raum 7 | `room_mapping.py` |
| 30158–30169 | 158–169 | 12 | Raum 8 | Name (string24) | Anzeigename Raum 8 | `room_mapping.py` |
| 30170–30181 | 170–181 | 12 | Raum 9 | Name (string24) | Anzeigename Raum 9 | `room_mapping.py` |
| 30182–30193 | 182–193 | 12 | Raum 10 | Name (string24) | Anzeigename Raum 10 | `room_mapping.py` |
| 30194–30205 | 194–205 | 12 | Raum 11 | Name (string24) | Anzeigename Raum 11 | `room_mapping.py` |
| 30206–30217 | 206–217 | 12 | Raum 12 | Name (string24) | Anzeigename Raum 12 | `room_mapping.py` |
| **30218–30249** | **218–249** | 32 | — | **nicht dokumentiert** | — | *(Lücke, siehe §3)* |
| 30250 | 250 | 1 | Aktor 1 | Stellung (0=geschlossen, 1=offen) | `binary_sensor.<raum>_actuator_1_position` | `binary_sensor.py::ViegaActuatorPositionBinarySensor` |
| 30251 | 251 | 1 | Aktor 1 | Rücklauftemperatur °C (×10) | `sensor.<raum>_actuator_1_return_temperature` | `sensor.py::ViegaActorLinkedSensor` |
| 30252 | 252 | 1 | Aktor 1 | Raum-ID (1–12) | Raumzuordnung (Discovery, nicht als eigene Entity) | `room_mapping.py`, `registers.py::actor_registers` |
| 30253 | 253 | 1 | Aktor 2 | Stellung | `binary_sensor…actuator_2_position` | `binary_sensor.py` |
| 30254 | 254 | 1 | Aktor 2 | Rücklauftemperatur °C (×10) | `sensor…actuator_2_return_temperature` | `sensor.py` |
| 30255 | 255 | 1 | Aktor 2 | Raum-ID | Discovery | `room_mapping.py` |
| 30256 | 256 | 1 | Aktor 3 | Stellung | `binary_sensor…actuator_3_position` | `binary_sensor.py` |
| 30257 | 257 | 1 | Aktor 3 | Rücklauftemperatur °C (×10) | `sensor…actuator_3_return_temperature` | `sensor.py` |
| 30258 | 258 | 1 | Aktor 3 | Raum-ID | Discovery | `room_mapping.py` |
| 30259 | 259 | 1 | Aktor 4 | Stellung | `binary_sensor…actuator_4_position` | `binary_sensor.py` |
| 30260 | 260 | 1 | Aktor 4 | Rücklauftemperatur °C (×10) | `sensor…actuator_4_return_temperature` | `sensor.py` |
| 30261 | 261 | 1 | Aktor 4 | Raum-ID | Discovery | `room_mapping.py` |
| 30262 | 262 | 1 | Aktor 5 | Stellung | `binary_sensor…actuator_5_position` | `binary_sensor.py` |
| 30263 | 263 | 1 | Aktor 5 | Rücklauftemperatur °C (×10) | `sensor…actuator_5_return_temperature` | `sensor.py` |
| 30264 | 264 | 1 | Aktor 5 | Raum-ID | Discovery | `room_mapping.py` |
| 30265 | 265 | 1 | Aktor 6 | Stellung | `binary_sensor…actuator_6_position` | `binary_sensor.py` |
| 30266 | 266 | 1 | Aktor 6 | Rücklauftemperatur °C (×10) | `sensor…actuator_6_return_temperature` | `sensor.py` |
| 30267 | 267 | 1 | Aktor 6 | Raum-ID | Discovery | `room_mapping.py` |
| 30268 | 268 | 1 | Aktor 7 | Stellung | `binary_sensor…actuator_7_position` | `binary_sensor.py` |
| 30269 | 269 | 1 | Aktor 7 | Rücklauftemperatur °C (×10) | `sensor…actuator_7_return_temperature` | `sensor.py` |
| 30270 | 270 | 1 | Aktor 7 | Raum-ID | Discovery | `room_mapping.py` |
| 30271 | 271 | 1 | Aktor 8 | Stellung | `binary_sensor…actuator_8_position` | `binary_sensor.py` |
| 30272 | 272 | 1 | Aktor 8 | Rücklauftemperatur °C (×10) | `sensor…actuator_8_return_temperature` | `sensor.py` |
| 30273 | 273 | 1 | Aktor 8 | Raum-ID | Discovery | `room_mapping.py` |
| 30274 | 274 | 1 | Aktor 9 | Stellung | `binary_sensor…actuator_9_position` | `binary_sensor.py` |
| 30275 | 275 | 1 | Aktor 9 | Rücklauftemperatur °C (×10) | `sensor…actuator_9_return_temperature` | `sensor.py` |
| 30276 | 276 | 1 | Aktor 9 | Raum-ID | Discovery | `room_mapping.py` |
| 30277 | 277 | 1 | Aktor 10 | Stellung | `binary_sensor…actuator_10_position` | `binary_sensor.py` |
| 30278 | 278 | 1 | Aktor 10 | Rücklauftemperatur °C (×10) | `sensor…actuator_10_return_temperature` | `sensor.py` |
| 30279 | 279 | 1 | Aktor 10 | Raum-ID | Discovery | `room_mapping.py` |
| 30280 | 280 | 1 | Aktor 11 | Stellung | `binary_sensor…actuator_11_position` | `binary_sensor.py` |
| 30281 | 281 | 1 | Aktor 11 | Rücklauftemperatur °C (×10) | `sensor…actuator_11_return_temperature` | `sensor.py` |
| 30282 | 282 | 1 | Aktor 11 | Raum-ID | Discovery | `room_mapping.py` |
| 30283 | 283 | 1 | Aktor 12 | Stellung | `binary_sensor…actuator_12_position` | `binary_sensor.py` |
| 30284 | 284 | 1 | Aktor 12 | Rücklauftemperatur °C (×10) | `sensor…actuator_12_return_temperature` | `sensor.py` |
| 30285 | 285 | 1 | Aktor 12 | Raum-ID | Discovery | `room_mapping.py` |
| **30286+** | **286+** | — | — | **außerhalb des dokumentierten Bereichs** | — | *(unbekannt, siehe §3 — nicht raten)* |

Hinweis zu den Aktor-Entities: `binary_sensor…` / `sensor…` werden nur für
Aktoren erzeugt, die tatsächlich einem konfigurierten Raum zugeordnet sind
(`room_config["actor"]`, per Discovery aus Register `+2` aufgelöst, §4a der
Spec). Ein physisch nicht vorhandener oder keinem Raum zugeordneter Aktor
erzeugt keine Entity.

## 2. Holding-Register (Lesen `0x03`, Schreiben `0x10`, Bereich `40001`–`40073`)

| Manual-Adresse | PDU | Bereich | Beschreibung | Home-Assistant-Entity | Datei/Klasse |
| --- | --- | --- | --- | --- | --- |
| 40001 | 1 | Basiseinheit | Betriebsmodus (0=Standby, 1=Heizen, 2=Kühlen) | `climate.hvac_mode` (**gemeinsam für alle Räume**, §5a.1) | `climate.py::ViegaRoomClimateEntity` |
| 40002 | 2 | Basiseinheit | Profilmodus (0=Manuell, 1=Profil, 2=Absenkbetrieb) | `climate.preset_mode` (**gemeinsam für alle Räume**) | `climate.py::ViegaRoomClimateEntity` |
| **40003–40049** | **3–49** | — | **nicht dokumentiert** | — | *(Lücke, siehe §3)* |
| 40050 | 50 | Raum 1 | Leistungsstufe (0/1–10) | `number.<raum1>_power_level` | `number.py::ViegaPowerLevelNumber` |
| 40051 | 51 | Raum 1 | Soll-Temperatur °C (×10) | `climate` (Raum 1) `target_temperature` | `climate.py` |
| 40052 | 52 | Raum 2 | Leistungsstufe | `number.<raum2>_power_level` | `number.py` |
| 40053 | 53 | Raum 2 | Soll-Temperatur °C (×10) | `climate` (Raum 2) | `climate.py` |
| 40054 | 54 | Raum 3 | Leistungsstufe | `number.<raum3>_power_level` | `number.py` |
| 40055 | 55 | Raum 3 | Soll-Temperatur °C (×10) | `climate` (Raum 3) | `climate.py` |
| 40056 | 56 | Raum 4 | Leistungsstufe | `number.<raum4>_power_level` | `number.py` |
| 40057 | 57 | Raum 4 | Soll-Temperatur °C (×10) | `climate` (Raum 4) | `climate.py` |
| 40058 | 58 | Raum 5 | Leistungsstufe | `number.<raum5>_power_level` | `number.py` |
| 40059 | 59 | Raum 5 | Soll-Temperatur °C (×10) | `climate` (Raum 5) | `climate.py` |
| 40060 | 60 | Raum 6 | Leistungsstufe | `number.<raum6>_power_level` | `number.py` |
| 40061 | 61 | Raum 6 | Soll-Temperatur °C (×10) | `climate` (Raum 6) | `climate.py` |
| 40062 | 62 | Raum 7 | Leistungsstufe | `number.<raum7>_power_level` | `number.py` |
| 40063 | 63 | Raum 7 | Soll-Temperatur °C (×10) | `climate` (Raum 7) | `climate.py` |
| 40064 | 64 | Raum 8 | Leistungsstufe | `number.<raum8>_power_level` | `number.py` |
| 40065 | 65 | Raum 8 | Soll-Temperatur °C (×10) | `climate` (Raum 8) | `climate.py` |
| 40066 | 66 | Raum 9 | Leistungsstufe | `number.<raum9>_power_level` | `number.py` |
| 40067 | 67 | Raum 9 | Soll-Temperatur °C (×10) | `climate` (Raum 9) | `climate.py` |
| 40068 | 68 | Raum 10 | Leistungsstufe | `number.<raum10>_power_level` | `number.py` |
| 40069 | 69 | Raum 10 | Soll-Temperatur °C (×10) | `climate` (Raum 10) | `climate.py` |
| 40070 | 70 | Raum 11 | Leistungsstufe | `number.<raum11>_power_level` | `number.py` |
| 40071 | 71 | Raum 11 | Soll-Temperatur °C (×10) | `climate` (Raum 11) | `climate.py` |
| 40072 | 72 | Raum 12 | Leistungsstufe | `number.<raum12>_power_level` | `number.py` |
| 40073 | 73 | Raum 12 | Soll-Temperatur °C (×10) | `climate` (Raum 12) | `climate.py` |
| **40074+** | **74+** | — | **außerhalb des dokumentierten Bereichs** | — | *(unbekannt, siehe §3 — nicht raten)* |

## 3. Nicht belegte / unbekannte Adressen

Diese Bereiche stehen im Handbuch entweder als Lücke zwischen zwei
dokumentierten Blöcken (wahrscheinlich reserviert für zukünftige
Erweiterungen) oder liegen ganz außerhalb des dokumentierten Tabellenbereichs.
In beiden Fällen: **nicht raten** — kein Code liest oder schreibt hier etwas
(`spec.md` §9 verbietet ausdrücklich, `REGISTER_DEFINITIONS`-Platzhalter wie
reale Adressen zu behandeln; dasselbe Prinzip gilt hier).

| Bereich (Manual) | Anzahl Register | Lage |
| --- | --- | --- |
| 30023 | 1 | zwischen Basiseinheit-Bezeichnung und Fehlercode |
| 30026–30049 | 24 | zwischen Vorlauftemperatur und Raum-1-Ist-Temperatur |
| 30218–30249 | 32 | zwischen Raum-12-Name und Aktor-1-Stellung |
| 30286+ | unbekannt | nach dem letzten dokumentierten Aktor-Register (Aktor 12 Raum-ID) |
| 40003–40049 | 47 | zwischen Profilmodus und Raum-1-Leistungsstufe |
| 40074+ | unbekannt | nach dem letzten dokumentierten Raum-Register (Raum 12 Soll-Temperatur) |

## 4. Auffälligkeiten für die weitere Arbeit

- **40001/40002 sind Basiseinheit-weit, nicht pro Raum.** Jede Raum-Climate-Entity
  liest/schreibt dasselbe Register; eine Änderung von Modus oder Profil in
  einem Raum wirkt sich auf alle Räume aus. Das entspricht dem Handbuch
  (Spalte „Bereich: Basiseinheit"), ist aber ein Punkt, der Nutzer:innen
  überraschen kann — jetzt in `spec.md` §5a.1 dokumentiert.
- **Aktor „Stellung" ist binär (0/1), keine Prozentangabe.** War in `spec.md`
  §5a als „percentage sensor" spezifiziert; korrigiert auf `binary_sensor`
  (device_class `opening`).
- Es gibt **kein** dokumentiertes, schreibbares Register für ein einfaches
  Ein/Aus pro Raum — der bisherige `switch`-Entity-Typ hatte deshalb keine
  Entsprechung im Registerplan und wurde entfernt (siehe `spec.md` §14 „A
  switch that never touched the device").
- **Schreibbefehl nutzte den falschen Funktionscode.** Alle Schreibzugriffe
  (Solltemperatur, Leistungsstufe, Betriebs-/Profilmodus) liefen über
  Funktion `0x06` (Write Single Register) statt über die im Handbuch
  einzige belegte Schreib-Funktion `0x10` (Write Multiple Registers,
  S. 95, „Beispiel 2"). Behoben — Details in `spec.md` §14 „The write
  command used the wrong function code".
- Alle in diesem Dokument aufgeführten Adressen sind gegen die
  Handbuch-Tabellen (S. 89–93) und die eigenen Wire-Beispiele des Handbuchs
  (S. 94–95: Betriebsmodus lesen, Soll-Temperatur Raum 2 setzen, Aktor 1
  lesen) geprüft und stimmen mit der aktuellen `registers.py`-Implementierung
  überein.

## 5. Web-Recherche: weitere Quellen (2026-09-18)

Auftrag: prüfen, ob es außerhalb des mitgelieferten Handbuchs
(`Fonterra Smart Control-de-DE.pdf`) weitere, bisher nicht erfasste
Registerdefinitionen gibt (andere Handbuchausgaben, Foren, Reverse-Engineering
durch Dritte).

### Ergebnis in Kürze

**Keine zusätzlichen, bisher unbekannten Register gefunden.** Alle
technischen Quellen, die konkrete Registeradressen nennen, decken sich mit
Abschnitt 1/2 dieses Dokuments (Basiseinheit `30001`–`30025`/`40001`–`40002`,
Räume `30050`–`30073`/`30074`–`30217`/`40050`–`40073`, Aktoren
`30250`–`30285`). Kein Fund deutet auf Register für Luftfeuchtigkeit,
Taupunkt, Zeitprogramm/Urlaubsmodus, Außentemperatur oder Ähnliches hin.

### Geprüfte Quellen

| Quelle | Ergebnis |
| --- | --- |
| [Home Assistant Community: „Viega Floorheating Fonterra Smart Control"](https://community.home-assistant.io/t/viega-floorheating-fonterra-smart-control/284753) | Mehrere Nutzer:innen mit eigenen YAML-Modbus-Configs. Verwendete PDU-Adressen (`address: 50`/`51` für Raum 1, `54`/`55` für Raum 3) **bestätigen unabhängig** die in `registers.py::pdu_address()` verwendete Formel (`manual − 30000`/`−40000`, kein zusätzlicher `-1`-Offset). Keine neuen Register. |
| [simon42 Community: „Modbus-Problem nach Update Fonterra Smart Control (Viega)"](https://community.simon42.com/t/modbus-problem-nach-update-fonterra-smart-control-viega/29014) | Bereits als Quelle in `spec.md` §9a zitiert (HA-Modbus-`count`-Parameter-Regression bei `int16`). Keine neuen Register, keine weiteren technischen Details. |
| [ManualsLib: Viega Fonterra Smart Control Gebrauchsanleitung (Dok.-ID 722311)](https://www.manualslib.de/manual/722311/Viega-Fonterra-Smart-Control.html) | Andere Paginierung als die lokale PDF (Registerkapitel dort ab S. 105ff.), aber **inhaltlich identische** Input-/Holding-Register- und Fehlercode-Tabellen (stichprobenartig auf S. 108 und S. 111 geprüft). Keine zusätzlichen Register. |
| [ManualsLib: ältere Ausgabe (Dok.-ID 779473, Stand 04.3/2016)](https://www.manualslib.de/manual/779473/Viega-Fonterra-Smart-Control.html) | Enthält **noch gar kein** Modbus-Kapitel — Modbus-Unterstützung (und ihre Dokumentation) wurde erst mit einer späteren Ausgabe ergänzt (die mitgelieferte PDF ist als „Fonterra Smart Control 2.0" gekennzeichnet). Kein Hinweis auf ein noch umfangreicheres, älteres Registerset. |
| [ManualsLib: englische „Instructions For Use" (Dok.-ID 2097230)](https://www.manualslib.com/manual/2097230/Viega-Fonterra-Smart-Control.html) | Nur über Suchergebnis-Schnipsel geprüft (03 Read Holding-Registers ab `40001`, 04 Read Input-Registers `30011`–`30023`) — deckungsgleich mit dem vorliegenden Handbuch, keine Abweichung gefunden. |
| [Viega: Fonterra Heat Control-Basiseinheit](https://www.viega.de/de/produkte/Katalog/Flaechentemperierung/Fonterra/Regelungen/Fonterra-Heat-Control/Fonterra-Heat-Control-Basiseinheit-1251-1.html) | **Anderes Produkt**, nicht Smart Control: einfachere Regelung (bis 6 Raumthermostate/12 Aktoren, USB statt WLAN), in der Produktbeschreibung kein Hinweis auf Modbus/Netzwerkanbindung. Nicht relevant für diesen Registerplan; das zugehörige Handbuch-PDF war beim Abruf nicht erreichbar (404/403). |
| [ise.de: SMART CONNECT KNX viega (Gateway)](https://www.ise.de/en/products/smart-connect-series/viega) | KNX-Gateway für bis zu 5 Basisstationen; Produktseite nennt keine einzelnen Datenpunkte/Register, verlinkt nur auf (hier nicht abgerufene) Datenblätter. Kein Fund. |
| [fonterra-smart-control.viega.com/de/register/](https://fonterra-smart-control.viega.com/de/register/) | Trotz des Pfadnamens **keine Registerdokumentation** — reine Benutzer-Registrierungsseite (Konto anlegen) für die Fonterra-App/-Cloud. |

### Sachdienlicher Nebenfund (kein Register, aber relevant für den Betrieb)

Mehrere Beiträge im Home-Assistant-Forum beschreiben einen **Firmware-Bug**:
Version **4.1-5.02** lieferte über Modbus zeitweise Fehler-/Leerwerte statt
echter Messwerte zurück; behoben in **4.1-5.03**. Das ist kein
Registerdefinitions-Fehler, aber relevant für die Fehlerdiagnose bei
Nutzer:innen mit älterer Basiseinheit-Firmware — sollte bei Support-Anfragen
zu unplausiblen `-99`-Werten als möglicher Grund mit abgefragt werden
(Firmwarestand der Basiseinheit, nicht der Integration).

### Nicht übernommen

Eine erste, automatisiert zusammengefasste Fundstelle nannte einen
abweichenden Default-Endpunkt „192.168.8.20:1502" für das WLAN-Modul. Eine
gezielte Nachprüfung derselben Quelle konnte das nicht reproduzieren (dort
fand sich stattdessen nur ein Nutzer-Beispiel mit eigener statischer IP,
Port 502) — dieser Wert wird daher als nicht verifiziert **nicht** in
`spec.md`/`const.py` übernommen.

## 6. Weitere externe Quelle: `matrover/viega-fonterra` (geprüft 2026-09-25)

Auftrag: das Repository [github.com/matrover/viega-fonterra](https://github.com/matrover/viega-fonterra)
(eine unabhängige, andere Home-Assistant-Integration für dasselbe Gerät) nach
weiteren Registerzuordnungen durchsuchen, die diesem Dokument noch fehlen.

### Bestätigung bestehender Register

`custom_components/viega_fonterra/const.py` dieses Repos definiert
`REGISTER_CURRENT_TEMP_BASE = 50` (Input) und `REGISTER_SETPOINT_BASE = 51`
(Holding), je Raum mit Stride `2` - deckt sich exakt mit den hier in
Abschnitt 1/2 dokumentierten Adressen `30050`/`40051` (Raum 1),
`30052`/`40053` (Raum 2) usw. Eine weitere unabhängige Bestätigung der
bereits erfassten Adressen, keine neue Information.

### Zwei zusätzliche Register - nicht übernommen, unbestätigt

Dieselbe `const.py` definiert außerdem:

- `REGISTER_OUTDOOR_TEMP = 100` (Input, x0,1 °C) - "Außentemperatur"
- `REGISTER_PUMP_STATUS_BASE = 200` (Input, Stride `1` je Zone) - "Pumpenstatus"

Als Input-Register wären das `30100` und `30200`+(Zonennummer-1) in
Manual-Schreibweise - beide liegen in den nach Abschnitt 3 bislang als nicht
dokumentiert markierten Lücken (`30026-30049` reicht nicht bis `30100`,
d.h. `30100` läge sogar noch hinter dem hier dokumentierten Bereich `30001-30285`;
`30200`+x liegt in der Lücke `30218-30249` nur teilweise - für höhere
Zonennummern bereits darüber hinaus). Sie widersprechen den bislang
dokumentierten Adressen also nicht direkt, sind aber durch nichts belegt,
das diesem Projekt vorliegt:

- Das lokale Handbuch (`Fonterra Smart Control-de-DE.pdf`, S. 89-96, siehe
  Kopf dieses Dokuments) wurde erneut vollständig geprüft (S. 89-98,
  einschließlich der Wire-Beispiele und der Fehlercode-Tabelle): keine
  Außentemperatur- oder Pumpenstatus-Register enthalten. Das
  Modbus-Kapitel endet nach dem letzten Holding-Register `40073`.
- Der in `matrover/viega-fonterra`s README verlinkte, angeblich neuere
  Handbuch-Stand ("Seite 105ff.") war beim Abruf nicht erreichbar (HTTP 404).
- Das bereits in Abschnitt 5 geprüfte Home-Assistant-Forum
  ("Viega Floorheating Fonterra Smart Control") wurde erneut gezielt nach
  "Außentemperatur"/"pump" durchsucht: keine Registeradresse für eines von
  beidem wird dort von irgendjemandem genannt oder bestätigt.
- Im Quellcode von `matrover/viega-fonterra` selbst gibt es - anders als bei
  jedem bestätigten Register in `registers.py` dieses Projekts - keine
  Handbuch-Seitenangabe oder sonstige Quellenangabe zu diesen beiden
  Adressen.
- Das Repository selbst weist in seiner README ausdrücklich darauf hin:
  "This integration has **not yet been tested on live hardware**."

Bewertung: `REGISTER_OUTDOOR_TEMP`/`REGISTER_PUMP_STATUS_BASE` sind
plausible, aber unbestätigte Vermutungen des anderen Repos - nicht Ergebnisse
einer bestätigten Handbuch- oder Hardware-Prüfung. Nach dem in Abschnitt 3
festgelegten Grundsatz dieses Projekts ("nicht raten") werden sie nicht in
`registers.py`/`spec.md` als reale Register übernommen. Sollte künftig echte
Hardware verfügbar sein, wären `30100` (Außentemperatur, Input, Funktion
`0x04`) und `30200`+(Zonennummer-1) (Pumpenstatus je Zone, Input) die ersten
Kandidaten für einen gezielten Testlese-Versuch.

## 7. Weitere Web-Recherche: Übertragungsmodus und Datentypen (2026-09-25)

Die Suche nach unabhängigen Quellen zu den Registern selbst ergab weiterhin
keine bestätigten Adressen außerhalb der Tabellen in Abschnitt 1 und 2. Die
folgende Zusatzinformation stammt aus der veröffentlichten Anleitung und aus
mehreren praktischen Beiträgen im Home-Assistant-Forum. Sie ändert den
Registerplan nicht, ist aber für einen direkten Modbus-Test und die
Fehlerdiagnose nützlich.

### Verbindungsparameter laut Anleitung

- Die Schnittstelle ist **Modbus TCP** über Ethernet oder WLAN. Eine
  asynchrone serielle Übertragung (**Modbus RTU**) wird laut Anleitung nicht
  unterstützt.
- Der TCP-Port ist `502`.
- Im Punkt-zu-Punkt-Modus nennt die Anleitung `192.168.1.1` als IP-Adresse;
  in allen anderen Betriebsarten wird eine dynamische IP-Adresse per DHCP
  verwendet. Für Home Assistant ist deshalb eine im Router reservierte bzw.
  statische IP-Adresse des WLAN-Moduls sinnvoll.
- Die Basiseinheit akzeptiert laut Anleitung eine beliebige Modbus-Geräte-ID
  im Nachrichtenkopf. Die Forum-Beispiele verwenden `slave: 1`; das ist ein
  erprobtes Beispiel, aber keine zusätzliche Registerdefinition.
- Die Anleitung nennt als unterstützte Ausnahme-Codes `01` (Illegal
  Function), `02` (Illegal Data Address), `03` (Illegal Data Value) und `04`
  (Slave Device Failure). Ein Fehler beim Lesen darf daher nicht automatisch
  als unbekannte oder reservierte Registeradresse interpretiert werden.

### Datentypen und Genauigkeit

- Zahlen werden als Modbus-Register mit 16 Bit übertragen; der dokumentierte
  numerische Datentyp ist `int16` (signed, Wertebereich `-32768` bis `32767`).
- Für die Namen der Basiseinheit und Räume gibt es zusätzlich den erweiterten
  Datentyp `String`. Die in den Tabellen angegebenen Längen bleiben dabei
  maßgeblich: Seriennummern `string10`, Namen `string24`.
- Die Anleitung beschreibt Raumtemperaturen als auf `0,5 °C` genau. Vorlauf-
  und Rücklauftemperatur sind davon ausgenommen und werden mit `0,1 °C`
  Genauigkeit angegeben. Das ist eine Aussage über die Gerätegenauigkeit,
  nicht über eine neue Skalierung oder einen neuen Registerbereich; die
  dokumentierte Übertragung der Temperaturwerte mit Faktor `0,1` bleibt in
  den Tabellen dieses Dokuments erhalten.

### Praktische Bestätigungen aus dem Forum

- Ein 2021 veröffentlichter Beitrag zeigt eine funktionierende Home-
  Assistant-Modbus-TCP-Konfiguration mit Port `502`, `slave: 1`, Input-
  Register `50` für die aktuelle Raumtemperatur und Holding-Register `51`
  für die Solltemperatur. Weitere Beiträge bestätigen das Muster `52/53`,
  `54/55` usw. und die notwendige Trennung von Input- und Holding-Register.
- Die Modbus-Funktion muss in der Viega-Weboberfläche oder in der iPad-App
  aktiviert werden; laut Forum funktioniert diese Einstellung nicht in der
  iPhone-App. Das ist eine Gerätevoraussetzung, kein zusätzliches Register.
- Der Forenverlauf dokumentiert einen Firmwarefehler in `4.1-5.02`: Raum-
  namen, Fehlerstatus, aktuelle Raumtemperaturen und Solltemperaturen waren
  leer bzw. lieferten `-99`, während Seriennummer, Vorlauftemperatur und
  Rücklauftemperaturen weiterhin gelesen werden konnten. Mit `4.1-5.03`
  wurde das Problem laut Rückmeldung behoben. Bei selektiv fehlenden Werten
  sollte daher zuerst der Firmwarestand geprüft werden.

### Quellen dieser Ergänzung

| Quelle | Neue bzw. bestätigte Information |
| --- | --- |
| [ManualsLib, S. 104 - Übertragungsmodus](https://www.manualslib.de/manual/722311/Viega-Fonterra-Smart-Control.html?page=104) | Modbus TCP, Port 502, Punkt-zu-Punkt-IP `192.168.1.1`, DHCP in anderen Modi, kein Modbus RTU, beliebige Unit-ID |
| [ManualsLib, S. 105 - Registeradressen und Datentypen](https://www.manualslib.de/manual/722311/Viega-Fonterra-Smart-Control.html?page=105) | Input ab `30001`, Holding ab `40001`, `int16`, `String`, Modbus-Fehlercodes 01-04 |
| [ManualsLib, S. 106 - Hinweise zur Registerdefinition](https://www.manualslib.de/manual/722311/Viega-Fonterra-Smart-Control.html?page=106) | Raumtemperaturen mit 0,5 °C Genauigkeit; Vorlauf/Rücklauf mit 0,1 °C |
| [Home Assistant Community, Beiträge 4-7](https://community.home-assistant.io/t/viega-floorheating-fonterra-smart-control/284753) | Aktivierung, statische IP, Port 502 sowie die getrennte Verwendung von Input `50` und Holding `51` |
| [Home Assistant Community, Beiträge 8-13](https://community.home-assistant.io/t/viega-floorheating-fonterra-smart-control/284753) | Firmwarefehler `4.1-5.02` und Rückmeldung zur Korrektur in `4.1-5.03` |
| [matrover/viega-fonterra, README](https://github.com/matrover/viega-fonterra/blob/main/README.md) | Unabhängige aktuelle Bestätigung von Port 502, statischer IP, Unit-ID 1 und der bekannten Raumregister; das Repository weist selbst auf fehlende Live-Hardwaretests hin |

Die in `matrover/viega-fonterra` zusätzlich genannten Register für
Außentemperatur (`100`) und Pumpenstatus (`200+x`) bleiben deshalb weiterhin
unbestätigte Kandidaten aus Abschnitt 6 und werden nicht als reale
Registerdefinitionen übernommen.

## 8. Firmware-/Software-Recherche (2026-09-25)

### Offizielle Update-Information von Viega

Die aktuelle Viega-Service-Seite [Fonterra Smart Control - Umstellung auf neue
Bediensoftware](https://www.viega.de/de/service/Kundendienst/smartcontrol.html)
ist eine neue, relevante Quelle für die Gerätekompatibilität:

- Viega stellt auf eine neue Bediensoftware bzw. einen neuen Server um.
- Vor dem Umzug muss die bisherige Software schrittweise aktualisiert werden,
  mindestens bis `xx-5.08`, laut Viega besser bis `xx-6.10`.
- Die Updates sollen spätestens bis **31.10.2026** durchgeführt werden.
- Ohne dieses Update bleibt laut Viega nur der Punkt-zu-Punkt-Betrieb über das
  WLAN-Modul mit der bisherigen Bediensoftware möglich; der Serverumzug ist
  dann nicht möglich.
- Viega verlinkt dort eine offizielle [Update-Anleitung (PDF)](https://www.viega.de/content/dam/viega-assets/viega-worldwide-assets/products/surface-tempering/fonterra-smart-control/technical-documents/instructions-for-use/Fonterra%20Smart%20Control%20v1.0.pdf)
  und eine [Anleitung zur Umstellung der Bediensoftware (PDF)](https://www.viega.de/content/dam/viega-assets/viega-worldwide-assets/products/surface-tempering/fonterra-smart-control/technical-documents/instructions-for-use/Smart%20Control%20-%20Umstellung%20Bediensoftware_DE.pdf).

Das ist ein offizieller Hinweis auf mehrere Software-/Firmware-Stände, aber
kein öffentliches Firmware-Abbild. Die Angaben belegen auch keine zusätzlichen
Modbus-Register und ändern daher den Registerplan nicht.

### Gefundene App, aber kein Firmware-Leak

Bei [APKPure: Fonterra Smart Control](https://apkpure.com/de/fonterra-smart-control/de.viega.fonterra_smart_control)
ist eine alte Android-Bediensoftware öffentlich gelistet:

- Paketname: `de.viega.fonterra_smart_control`
- Version: `1.0`, Versioncode `2`
- Aktualisierung: `29.11.2018`
- Größe: ca. `16,7 MB`
- Architektur: `armeabi-v7a`
- Anbieterangabe: Viega Holding GmbH & Co. KG

Diese APK ist eine mobile Bedienoberfläche und nicht die Firmware des
WLAN-Moduls oder der Basiseinheit. Sie enthält nach der öffentlich sichtbaren
Beschreibung keine Registermap, kein Firmware-Updatepaket und keinen
verifizierten Firmware-Dump. Eine Installation aus einer Drittquelle sollte
zudem nur mit vorheriger Signatur-/Hash-Prüfung erfolgen.

### Ergebnis der Leak-/Reverse-Engineering-Suche

Bis zum Recherchedatum wurde kein öffentlich zugängliches `.bin`-, `.hex`-,
OTA- oder sonstiges Firmware-Abbild für das WLAN-Modul Modell `1250.16` oder
die Fonterra-Smart-Control-Basiseinheit gefunden. Auch die öffentlichen
GitHub-Suchen ergaben kein Firmware-Repository und keinen veröffentlichten
Firmware-Dump. Die bisher stärksten technischen Quellen bleiben daher:

1. Viega-Handbücher und die offizielle Service-Seite,
2. reproduzierbare Modbus-Konfigurationen und Fehlerberichte im
   Home-Assistant-Forum,
3. die unabhängige Integration `matrover/viega-fonterra`.

Firmware-Reverse-Engineering wäre nur mit einem eigenen Updatepaket, einem
Geräteabbild oder Mitschnitten des Updatevorgangs sinnvoll möglich. Die
öffentlich sichtbaren Versionsnummern allein erlauben keine seriöse Ableitung
weiterer Register.
