# Firmware der Spielzeug Wiegestation (ESPHome)

Die Firmware läuft auf dem **Waveshare ESP32-P4-ETH** (mit PoE-Modul) und liest vier Wägezellen über vier HX711-Module. Sie ist reine ESPHome-Konfiguration, es gibt keinen eigenen Code.

| Datei | Zweck |
|---|---|
| `board-test.yaml` | Etappe 0: nur Ethernet, Anbindung an Home Assistant und Diagnose-Werte, noch ohne Waage |

## Als Paket einbinden

Die eigene Gerätedatei im ESPHome Device Builder bleibt kurz. Sie enthält nur Namen, Schlüssel und das Paket. Der API-Schlüssel und das Update-Kennwort gehören **nur dorthin**, nie ins Repo.

```yaml
substitutions:
  name: spielzeug-wiegestation

esphome:
  name: ${name}
  friendly_name: Spielzeug Wiegestation

packages:
  board:
    url: https://github.com/RedDragonNode/ha-spielzeug-wiegestation
    ref: main
    files: [esphome/board-test.yaml]
    refresh: always

api:
  encryption:
    key: "<dein API-Schlüssel>"

ota:
  - platform: esphome
    password: "<dein Update-Kennwort>"
```

Den ersten Flash machst du per USB, danach gehen Updates über das Netzwerk.

> **PoE und USB nie gleichzeitig anschließen.** Waveshare sagt nicht, ob das Board beides verträgt. Zum Flashen das Netzwerkkabel vom PoE-Anschluss abziehen oder das Board am normalen Netzwerk-Port betreiben, im Betrieb nur PoE.
