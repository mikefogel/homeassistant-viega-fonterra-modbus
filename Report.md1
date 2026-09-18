# Review- und Fix-Report — Viega Fonterra Smart Control Integration

Datum: 2026-09-03
Umfang: Vollständiges Code-Review gegen `spec.md`, Behebung aller gefundenen Fehler,
Ergänzung fehlender Spezifikationsteile, Aufbau einer lauffähigen Testsuite.

## 1. Zusammenfassung

Der ursprüngliche Code-Review ergab 16 konkrete Fehler (davon mehrere kritisch, u.a.
eine falsche Register-Adressberechnung, die auf echter Hardware zu ungültigen
Modbus-Zugriffen geführt hätte) sowie mehrere Lücken in `spec.md` selbst. Alle
Punkte wurden behoben bzw. spezifiziert. Zusätzlich wurde auf Nachfrage die fehlende
Anforderung "Geräte müssen löschbar sein" ergänzt und abgesichert, und eine vorher
nicht lauffähige Testsuite in eine ausführbare, deutlich erweiterte Suite überführt.

**Wichtiger Vorbehalt:** In dieser Arbeitsumgebung ist kein Python installiert. Alle
Code- und Testaufrufe wurden manuell durchgerechnet und nachvollzogen, aber **nicht
tatsächlich ausgeführt**. Vor jedem Commit/Merge sollte `pytest` lokal laufen.

## 2. Gefundene und behobene Fehler

| # | Fund | Datei | Schwere |
| --- | --- | --- | --- |
| 1 | `pdu_address()` rechnete PDU-Adressen ~30000–40000 zu hoch (`manual - 1` statt `manual - 40001`/`-30001`) | `registers.py` | Kritisch |
| 2 | `ViegaDiagnosticTextEntity`-Konstruktor branchte auf Argumentanzahl; beide Aufrufer trafen den falschen Zweig | `diagnostic.py`, `sensor.py` | Kritisch |
| 3 | Plattform `diagnostic` war nicht in `PLATFORMS` registriert (toter Code), stattdessen fehlerhaftes Duplikat in `sensor.py` | `const.py` | Hoch |
| 4 | Kein Lock im Modbus-Client → parallele Entity-Updates konnten TX/RX-Frames verschränken | `modbus_handler.py` | Kritisch |
| 5 | `-99`-Fehler-Sentinel bei Holding-Registern unerkennbar (unsigned statt signed dekodiert) | `modbus_handler.py` | Kritisch |
| 6 | Undokumentierte `0xFFFF`-Fehlerprüfung verwarf ganze Antworten ohne Spec-Bezug | `modbus_handler.py` | Mittel |
| 7 | `switch.py`: `unique_id` basierte auf editierbarem Raumnamen statt `room_id` → Umbenennen erzeugte Doppel-Entity | `switch.py` | Hoch |
| 8 | `number.py`: Gefahrlose Rückfalladresse `0` kollidierte mit dem Base-Unit-Operating-Mode-Register | `number.py` | Kritisch |
| 9 | `device_info["name"]` überall hart codiert statt konfigurierbarem `device_name` | alle Entity-Plattformen | Hoch |
| 10 | Räume ohne explizites `room_number` bekamen keine Standardregister (Kernfunktion "Zieltemperatur ändern" fehlte) | `climate.py` | Hoch |
| 11 | `polling_interval` wurde gespeichert, aber nirgends angewendet | `__init__.py` | Hoch |
| 12 | `RoomMappingDiscovery`/"erste Lesezyklus"-Discovery (§3a/§4) existierte nur isoliert, nicht im produktiven Setup-Pfad | — | Dokumentiert, nicht rückgebaut (siehe Abschnitt 5) |
| 13 | Zusätzliche Aktoren in Mehrfach-Aktor-Räumen wurden stillschweigend verworfen | `climate.py`, `sensor.py` | Mittel |
| 14 | Kein `ConfigEntryNotReady` bei Verbindungsfehler beim Setup → kein automatischer Retry | `__init__.py` | Mittel |
| 15 | Kein Fehlerindikator-Entity für Base-Unit-Fehlercode (Akzeptanzkriterium fehlte) | neu: `binary_sensor.py` | Hoch |
| 16 | Geratenes, undokumentiertes Byte-Encoding bei Identitäts-Registern | `sensor.py` | Mittel (jetzt explizit als vorläufig markiert) |
| 17 | *(Nachtrag auf Nutzeranfrage)* Kein robustes Lösch-Verhalten: `hass.data[DOMAIN]`-Zugriff konnte `KeyError` werfen, ein fehlschlagender `disconnect()` konnte das Entfernen eines Moduls blockieren | `__init__.py` | Hoch |

Details zu Ursache/Fix je Punkt stehen als Code-Kommentare an den jeweiligen Stellen
sowie in den neuen "Session lessons"-Einträgen in `spec.md` §14.

## 3. Neue/geänderte Produktivmodule

- **`registers.py`** — korrigierte `pdu_address()`-Formel; neu: `resolve_room_number()`
  (leitet Raumnummer aus `room_id` ab), `BASE_UNIT_ERROR_CODES`/`describe_error_code()`.
- **`modbus_handler.py`** — `asyncio.Lock` für Request-Serialisierung; einheitlich
  signed dekodierte Register; entfernte, nicht spezifizierte `0xFFFF`-Prüfung.
- **`device.py`** *(neu)* — zentrale `build_device_info()`, verwendet überall den
  konfigurierten Gerätenamen.
- **`polling.py`** *(neu)* — `PollingGate`: drosselt tatsächliche Modbus-Reads auf
  den konfigurierten `polling_interval`, unabhängig vom fixen Home-Assistant-Poll-Takt.
- **`binary_sensor.py`** *(neu)* — Base-Unit-Fehlerindikator (`on` bei Code ≠ 0).
- **`sensor.py`** — `ViegaBaseUnitIdentitySensor` (Text-Encoding dokumentiert und
  konsistent gemacht, Fehlercode-Beschreibung ergänzt), neu `ViegaActorLinkedSensor`
  + `_extra_actor_sensors()` für zusätzliche Aktoren in Mehrfach-Aktor-Räumen.
- **`climate.py`, `number.py`, `switch.py`, `diagnostic.py`** — Fixes wie oben
  gelistet, plus `PollingGate`-Integration.
- **`config_flow.py`** — `parse_rooms_input()` als reine, testbare Funktion
  herausgezogen (Verhalten unverändert); totes `async_step_rooms` entfernt.
- **`__init__.py`** — `ConfigEntryNotReady` bei Verbindungsfehlern; robustes,
  fehlertolerantes `async_unload_entry` (Modul muss immer löschbar sein, auch offline).
- **`const.py`** — `PLATFORMS` um `binary_sensor` und `diagnostic` ergänzt;
  `MIN_SCAN_INTERVAL` für das Polling-Modell.

## 4. Änderungen an `spec.md`

- §3a: Byte-Encoding für Text-/Seriennummer-Register normativ (und als vorläufig
  gekennzeichnet) festgelegt.
- §3b *(neu)*: Fehlercode-Tabelle und Beschreibungs-Konvention.
- §4: Verhalten bei Mehrfach-Aktor-Räumen präzisiert (zusätzliche Aktoren als
  eigene Linked-Sensoren, nicht verwerfen).
- §5a/§5b: PDU-Adress-Formel normativ festgeschrieben (`manual - 40001` /
  `manual - 30001`); `room_number`-Fallback-Regel dokumentiert; Basisunit-
  Fehlerindikator vs. Fehlercode-Sensor als zwei getrennte Entities klargestellt;
  Betriebs-/Profilmodus-Werte als vorläufig markiert.
- §6a *(neu, auf Nutzeranfrage)*: Abschnitt "Removing a module" — Module müssen über
  die Standard-HA-UI löschbar sein, auch offline, ohne andere Module zu beeinflussen.
- §6c *(neu)*: Polling-Modell (Throttle statt festem Scan-Intervall) dokumentiert.
- §11: Signed-Dekodierung aller Register normativ festgelegt.
- §11b *(neu)*: Anforderung zur Serialisierung gleichzeitiger Requests auf einer
  Verbindung.
- §13: Neue Akzeptanzkriterien (Löschbarkeit, Polling-Modell, Concurrency,
  unique-ID-Stabilität für alle Plattformen, Device-Name-Konsistenz).
- §14: Zwei neue "Session lessons"-Einträge (PDU-Adress-Offset,
  Konstruktor-Überladung anhand Argumentanzahl) zur Vermeidung der gleichen Fehler
  in Zukunft.

## 5. Bewusst nicht behobene/offene Punkte

- **`diagnostic.py`-Entities bleiben statisch** — sie zeigen nach Erstellung nie
  einen aktualisierten Fehlerstatus (kein `async_update`). Der Konstruktor-Bug
  wurde behoben, die Live-Aktualisierung war nicht Teil der ursprünglich
  gemeldeten 16 Punkte und wurde bewusst nicht zusätzlich umgebaut, um den
  Änderungsumfang nicht weiter aufzublähen.
- **`RoomMappingDiscovery`/"erster Lesezyklus"-Discovery aus dem Gerät selbst**
  (spec.md §3a/§4) ist weiterhin nicht in den produktiven Setup-Pfad verdrahtet;
  Räume kommen unverändert aus der vom Nutzer eingegebenen Konfiguration. Das war
  ursprünglich als Gap gemeldet, aber kein "Fehler" im engeren Sinn und wurde nicht
  nachgerüstet.
- **Volle `ConfigFlow`/`OptionsFlow`-Integrationstests** fehlen weiterhin — dafür
  wäre der offizielle `pytest-homeassistant-custom-component`-Testharness mit
  echter `hass`-Fixture nötig, den dieses Repo nicht einsetzt. Nur die reine Logik
  (`parse_rooms_input`, `_rooms_from_input`) ist getestet.

## 6. Testsuite

### Infrastruktur (neu)
- `pytest.ini` — setzt `pythonpath = .`, ohne das lief `pytest` zuvor je nach
  Aufrufkontext mit `ModuleNotFoundError: No module named 'custom_components'`.
- `requirements-test.txt` — `pytest`, `homeassistant`, `voluptuous`.

### Umfang
133 Testfunktionen in 16 Dateien (davon 6 vorher schon vorhanden, 10 neu):

| Datei | Tests | Neu? |
| --- | ---: | --- |
| `test_modbus_handler.py` | 30 | erweitert (war 12) |
| `test_sensor_entities.py` | 13 | neu |
| `test_climate.py` | 13 | neu |
| `test_registers.py` | 11 | erweitert (war 1) |
| `test_config_flow.py` | 9 | neu |
| `test_entity_fixes.py` | 8 | neu |
| `test_specification.py` | 7 | unverändert |
| `test_room_mapping.py` | 6 | neu |
| `test_diagnostic.py` | 6 | erweitert (war 1) |
| `test_switch.py` | 5 | neu |
| `test_polling.py` | 5 | neu |
| `test_number.py` | 5 | neu |
| `test_binary_sensor.py` | 5 | neu |
| `test_device.py` | 4 | neu |
| `test_init.py` | 3 | neu |
| `test_device_registry.py` | 3 | neu |

Abgedeckt sind u.a.: Modbus-Frame-Aufbau/-Dekodierung inkl. Fehlerpfaden,
Verbindungsaufbau/-abbruch (gemockt), Request-Serialisierung unter Nebenläufigkeit,
korrekte PDU-Adressen gegen die in spec.md 5b vorgerechneten Werte, Sentinel-/
Fehlerbehandlung auf jeder Entity-Plattform, Polling-Drosselung, Device-Name-
Konsistenz, stabile unique-IDs, sowie die Löschbarkeits-Fixes aus `__init__.py`.

## 7. Geänderte/neue Dateien

```
Geändert:
  custom_components/viega_fonterra_modbus/__init__.py
  custom_components/viega_fonterra_modbus/climate.py
  custom_components/viega_fonterra_modbus/config_flow.py
  custom_components/viega_fonterra_modbus/const.py
  custom_components/viega_fonterra_modbus/diagnostic.py
  custom_components/viega_fonterra_modbus/modbus_handler.py
  custom_components/viega_fonterra_modbus/number.py
  custom_components/viega_fonterra_modbus/registers.py
  custom_components/viega_fonterra_modbus/sensor.py
  custom_components/viega_fonterra_modbus/switch.py
  spec.md
  tests/test_diagnostic.py
  tests/test_modbus_handler.py
  tests/test_registers.py

Neu:
  custom_components/viega_fonterra_modbus/binary_sensor.py
  custom_components/viega_fonterra_modbus/device.py
  custom_components/viega_fonterra_modbus/polling.py
  pytest.ini
  requirements-test.txt
  tests/test_binary_sensor.py
  tests/test_climate.py
  tests/test_config_flow.py
  tests/test_device.py
  tests/test_device_registry.py
  tests/test_entity_fixes.py
  tests/test_init.py
  tests/test_number.py
  tests/test_polling.py
  tests/test_room_mapping.py
  tests/test_sensor_entities.py
  tests/test_switch.py
```

## 8. Empfohlene nächste Schritte

1. `pip install -r requirements-test.txt && pytest` lokal ausführen und Ergebnis
   verifizieren (in dieser Umgebung nicht möglich).
2. Bei Bedarf `pytest-homeassistant-custom-component` einrichten, um die
   vollständigen Config-/Options-Flow-Schritte zu testen.
3. Entscheiden, ob `diagnostic.py`-Entities live aktualisiert werden sollen
   (Abschnitt 5).
4. Vor einem Release: Manifest-Version und Git-Tag konsistent halten
   (siehe spec.md §14, "Version and tag drift").

Nichts aus dieser Session wurde committet oder gepusht.
