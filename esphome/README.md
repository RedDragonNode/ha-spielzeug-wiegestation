# Firmware der Spielzeug Wiegestation (ESPHome)

Die Firmware läuft auf dem **Waveshare ESP32-P4-ETH** (mit PoE-Modul) und liest vier Wägezellen über vier HX711-Module. Sie ist reine ESPHome-Konfiguration, es gibt keinen eigenen Code.

| Datei | Zweck |
|---|---|
| `board.yaml` | Chip (Serienchip ab Revision 3), Ethernet und Diagnose-Werte (Laufzeit, IP, MAC, letzter Neustart) |
| `waage.yaml` | vier HX711-Sensoren „Zelle 1“ bis „Zelle 4“ mit ihren Rohwerten |

## Als Paket einbinden

Die eigene Gerätedatei im ESPHome Device Builder bleibt kurz. Sie enthält nur Namen, Schlüssel und die Pakete. Der API-Schlüssel gehört **nur dorthin**, nie ins Repo.

```yaml
substitutions:
  name: spielzeug-wiegestation

esphome:
  name: ${name}
  friendly_name: Spielzeug Wiegestation

packages:
  wiegestation:
    url: https://github.com/RedDragonNode/ha-spielzeug-wiegestation
    ref: main
    files: [esphome/board.yaml, esphome/waage.yaml]
    refresh: always

api:
  encryption:
    key: "<dein API-Schlüssel>"

ota:
  - platform: esphome
```

Den ersten Flash machst du per USB, danach gehen Updates über das Netzwerk. Für den Betrieb solltest du `ref: main` durch einen festen Stand ersetzen (z. B. `ref: v0.1.0`) und `refresh` weglassen.

## Verdrahtung

Pro Zelle ein HX711-Modul. Das Modul bekommt **3,3 V** (nicht 5 V), Daten und Takt gehen an je einen Pin des Boards:

| Zelle | Daten (DT/DOUT) | Takt (SCK) |
|---|---|---|
| 1 | GPIO20 | GPIO21 |
| 2 | GPIO22 | GPIO23 |
| 3 | GPIO26 | GPIO27 |
| 4 | GPIO47 | GPIO48 |

Die Pins lassen sich in der Gerätedatei unter `substitutions:` ändern (`cell1_dout`, `cell1_clk`, …). Ein Pin, an dem kein Modul hängt, meldet nichts.

> **PoE und USB nie gleichzeitig anschließen.** Waveshare sagt nicht, ob das Board beides verträgt. Zum Flashen das Netzwerkkabel vom PoE-Anschluss abziehen oder das Board am normalen Netzwerk-Port betreiben, im Betrieb nur PoE.
