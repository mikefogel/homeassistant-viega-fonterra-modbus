# Viega Fonterra Smart Control Integration für Home Assistant

Eine lokale Home Assistant Custom Integration für die Steuerung und Überwachung des Viega Fonterra Smart Control Systems über Modbus TCP.

## Inhaltsverzeichnis
- [Funktionen](#funktionen)
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Verwendung](#verwendung)
- [Fehlerbehebung](#fehlerbehebung)
- [FAQ](#faq)
- [Lizenz](#lizenz)

## Funktionen

✅ **Multi-Device-Support**: Mehrere Fonterra-Geräte unabhängig konfigurierbar  
✅ **Raumthermostate**: Climate-Entitäten pro Raum mit Ziel- und Ist-Temperatur  
✅ **Sensoren**: Register-basierte Werte (Vorlauf-, Rücklauf-, Raumtemperatur, Druck, Pumpenzustand)  
✅ **Schalter**: Ein/Aus-Steuerung für Aktuatoren  
✅ **Diagnose-Entitäten**: Textuelle Fehlerzustände  
✅ **Konfigurierbar**: Polling-Intervall, Modbus-Timeout, Raumbezeichnungen  
✅ **Fehlertoleranz**: Letzten Wert bei Kommunikationsfehlern beibehalten  
✅ **Sicher**: Modbus/TCP-Transaktions-ID-Validierung  

## Installation

### Voraussetzungen
- Home Assistant 2022.5+
- HACS installiert
- Viega Fonterra Smart Control mit Modbus TCP Zugang

### Schritt-für-Schritt

1. **HACS öffnen**
   - Gehe zu `Einstellungen > Geräte & Services > Integrationen > +`
   - Suche nach "Viega Fonterra Smart Control"
   - Klicke auf "Installieren"

2. **Home Assistant neu starten**
   - `Einstellungen > System > Neu starten`

3. **Integration hinzufügen**
   - `Einstellungen > Geräte & Services > + Integration erstellen`
   - Wähle "Viega Fonterra Smart Control"

## Konfiguration

### Konfigurationsschritte

**Schritt 1: Geräteverbindung**
- **Host**: IP-Adresse des Fonterra Smart Control (z.B. `192.168.1.50`)
- **Port**: Modbus TCP Port (Standard: `502`)
- **Gerätename**: Lesbar z.B. "Heizung Wohnzimmer"
- **Polling-Intervall**: Updateintervall in Sekunden (5–300, Standard: 30)
- **Modbus-Timeout**: Wartezeit auf Antwort in Sekunden (1–30, Standard: 5)

**Schritt 2: Räume konfigurieren**

JSON-Format mit Rauminformationen:
```json
{
  "room_1": {
    "name": "Wohnzimmer",
    "actor": 1,
    "sensor": 10
  },
  "room_2": {
    "name": "Schlafzimmer",
    "actor": 2,
    "sensor": 11
  }
}
```

Jeder Raum erzeugt:
- **Climate-Entity**: Thermostat mit Name aus Konfiguration
- **Switch-Entity**: Aktuator-Steuerung
- **Diagnostic-Entity**: Fehlerstatus

## Verwendung

### Entitäten in Home Assistant

Nach der Konfiguration erscheinen automatisch:

- `climate.wohnzimmer` - Raumthermostat
- `switch.wohnzimmer` - Aktuator
- `sensor.viega_fonterra_*` - Register-Sensoren
- `sensor.*_diagnostic` - Fehlerzustände

### Beispiel-Automation

```yaml
automation:
  - alias: Heizung bei Temperaturabfall erhöhen
    trigger:
      platform: state
      entity_id: climate.wohnzimmer
      attribute: current_temperature
      to: "19.0"
    action:
      service: climate.set_temperature
      target:
        entity_id: climate.wohnzimmer
      data:
        temperature: 22
```

## Fehlerbehebung

### Verbindungsfehler
- **Problem**: "Verbindung konnte nicht hergestellt werden"
- **Lösung**: 
  - Überprüfe IP-Adresse und Port des Fonterra-Geräts
  - Teste die Verbindung: `telnet 192.168.1.50 502`
  - Erhöhe Modbus-Timeout auf 10 Sekunden

### Sensoren zeigen `unavailable`
- **Problem**: Sensoren sind nicht verfügbar
- **Lösung**:
  - Überprüfe die Register-Adressen in der Konfiguration
  - Kontrolliere die Gerätelogs: `Einstellungen > System > Protokolle > Viega Fonterra`
  - Erhöhe Polling-Intervall auf 60 Sekunden

### Diagnostic-Entitäten zeigen Fehler
- Normale Funktion bei Kommunikationsfehlern
- Sensor behält letzten gültigen Wert
- Fehler wird in Diagnostic-Entity angezeigt

## FAQ

**F: Kann ich mehrere Fonterra-Geräte hinzufügen?**  
A: Ja! Wiederhole den Konfigurationsprozess für jedes Gerät.

**F: Wie erhöhe ich das Polling-Intervall?**  
A: In der Config-Flow unter "Polling-Intervall" oder später in den Optionen.

**F: Welche Register sind unterstützt?**  
A: Siehe `spec.md` im Repository oder `registers.py`.

**F: Kann ich den Fehler `-99` selbst behandeln?**  
A: Nein, die Integration verarbeitet `-99` automatisch und behält den letzten Wert.

## Lizenz

MIT License - siehe [LICENSE](LICENSE) für Details
