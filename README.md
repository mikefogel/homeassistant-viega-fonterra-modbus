# Viega Fonterra Smart Control Integration für Home Assistant

Diese Integration ermöglicht die Steuerung und Überwachung des Viega Fonterra Smart Control Systems über Home Assistant.

## Inhalt
- [Installation](#installation)
- [Konfiguration](#konfiguration)
- [Verwendung](#verwendung)
- [FAQ](#faq)
- [Unterstützung](#unterstützung)
- [Lizenz](#lizenz)

## Installation

### Voraussetzung
- Home Assistant (mindestens Version 2022.5)
- HACS (Home Assistant Community Store) installiert

### Schritte
1. Öffne HACS in deinem Home Assistant.
2. Klicke auf „Integrationen“ und dann auf das „+“-Symbol.
3. Suche nach „Viega Fonterra Smart Control“.
4. Wähle die Integration aus und klicke auf „Installieren“.
5. Starte Home Assistant neu, um die Integration zu aktivieren.

## Konfiguration

1. Gehe zu den Integrationen in Home Assistant.
2. Klicke auf „Integration hinzufügen“ und wähle „Viega Fonterra Smart Control“ aus.
3. Gib die notwendigen Zugangsdaten für dein Viega Fonterra Smart Control System ein.
4. Klicke auf „Absenden“ und überprüfe, ob die Konfiguration erfolgreich war.

## Verwendung

### Funktionen
- Überwachung der Temperatur in den Räumen
- Steuerung der Heizkreise
- Automatisierte Regelungen basierend auf Home Assistant Automationen

### Beispiel-Automation
```yaml
automation:
  - alias: Heizung anpassen bei Temperaturänderung
    trigger:
      platform: state
      entity_id: sensor.wohnzimmer_temperatur
    action:
      service: climate.set_temperature
      data:
        entity_id: climate.wohnzimmer
        temperature: "{{ states('sensor.wohnzimmer_temperatur') | float + 2 }}"
```

### FAQ
__Wie installiere ich HACS?__
- HACS kann über die offizielle Dokumentation installiert werden.

__Kann ich mehrere Viega Fonterra Smart Control Systeme hinzufügen?__
- Ja, du kannst mehrere Systeme hinzufügen, indem du den Konfigurationsprozess für jedes System wiederholst.

### Unterstützung
Für Hilfe und Unterstützung besuche unser GitHub-Repository oder eröffne ein Issue im Repository.

### Lizenz
Dieses Projekt steht unter der MIT-Lizenz. Siehe die LICENSE-Datei für weitere Details

