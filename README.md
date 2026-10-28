<p align="center">
  <img src="docs/banner.png" alt="Spielzeug Wiegestation" width="520">
</p>

# Spielzeug Wiegestation für Home Assistant

[![Tests](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/tests.yaml/badge.svg)](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/tests.yaml)
[![Hassfest](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hassfest.yaml)
[![HACS](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hacs.yaml/badge.svg)](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hacs.yaml)

*[English version](README.en.md)*

**Eine Waage für Spielzeug.** Ein ESP32-P4 mit Ethernet und PoE liest vier Wägezellen unter einer Platte (je ein HX711-Modul). Home Assistant rechnet daraus das Gewicht, zeigt, ob die Waage ruhig ist und ob etwas darauf liegt, und eicht sich über einen Assistenten in der Oberfläche, ohne dass du die Firmware neu aufspielen musst.

Das Projekt hat zwei Teile in einem Repo:

| Teil | Wo | Was |
|---|---|---|
| **Firmware** (ESPHome) | [`esphome/`](esphome/README.md) | läuft auf dem Board und meldet vier Rohwerte |
| **Integration** | `custom_components/spielzeug_wiegestation` | rechnet Tara, Eichung, Gewicht, „ruhig“ und „belegt“ |

> **Stand 0.1.0:** Die Waage misst, eicht und meldet Gewicht, Ruhe und Belegung. Das Erkennen einzelner Spielzeuge am Gewicht kommt in 0.2.0.

| Du willst … | Dafür |
|---|---|
| das Gewicht auf der Platte sehen | `Gewicht` (in Gramm) |
| wissen, ob die Waage ruhig ist | `Waage ruhig` |
| wissen, ob etwas auf der Platte liegt | `Belegt` |
| eine Schale oder Unterlage abziehen | Taste `Tara` |
| die Waage eichen | *Konfigurieren → Waage eichen* |
| prüfen, ob eine Zelle spinnt | die deaktivierten Sensoren `Gewicht Zelle 1` bis `4` |

## Hardware

- **Board:** Waveshare ESP32-P4-ETH (mit PoE-Modul). Das Board hat nur Ethernet, kein WLAN.
- **Wägezellen:** vier Balkenzellen (je 5 kg), jede an einem eigenen **HX711**-Modul. Zusammen tragen sie bis etwa 20 kg.
- **Strom:** PoE (IEEE 802.3af-fähiger Switch oder Injektor) oder USB-C.

> **PoE und USB nie gleichzeitig anschließen.** Waveshare sagt nicht, ob das Board beides verträgt. Zum Flashen das Netzwerkkabel vom PoE-Anschluss abziehen oder das Board an einen normalen Netzwerk-Port stecken.

### Verdrahtung

Jedes HX711-Modul bekommt **3,3 V** (nicht 5 V). Daten (`DT`) und Takt (`SCK`) gehen an je einen Pin des Boards:

| Zelle | `DT` am Modul an | `SCK` am Modul an |
|---|---|---|
| 1 | `GPIO20` | `GPIO21` |
| 2 | `GPIO22` | `GPIO23` |
| 3 | `GPIO26` | `GPIO27` |
| 4 | `GPIO47` | `GPIO48` |

`VCC` aller Module geht an `3V3`, `GND` an `GND` des Boards. Die Pins liegen an der rechten Stiftleiste des Boards, von der USB-C-Seite gezählt: `VBUS`, `VSYS`, `GND`, `EN`, **`3V3`**, **`GPIO20`**, **`GPIO21`**, **`GND`**, `GPIO22`, `GPIO23`, `RUN`, `GPIO26`, `GND`, `GPIO27`, `GPIO32`, `GPIO33`, `GPIO46`, `GND`, `GPIO47`, `GPIO48`.

> **Reihenfolge beachten:** Auf dem HX711-Modul steht die Reihe meist `GND, DT, SCK, VCC`, am Board liegen `3V3, GPIO20, GPIO21, GND` untereinander. Ein Flachbandkabel, das beide Reihen einfach verbindet, vertauscht 3V3 und GND und zerstört das Modul. Jeden Draht einzeln nach dem Namen stecken.

Die Zelle kommt mit vier Kabeln an das Modul:

| Kabel der Zelle | Pin am Modul |
|---|---|
| rot | `E+` |
| schwarz | `E−` |
| weiß | `A−` |
| grün | `A+` |

Das ist die übliche Farbbelegung. Zeigt eine Zelle beim Auflegen in die andere Richtung, sind `A+` und `A−` vertauscht. Das ist kein Fehler: Der Eichen-Assistent erkennt es und rechnet für diese Zelle einen negativen Faktor.

### Aufbau der Platte

- Pro Zelle ein **festes Ende** (mit den zwei Gewindelöchern, aus dem die Kabel kommen) am Boden und ein **freies Ende**, auf dem die Platte liegt. Das freie Ende muss unten **Luft** haben, sonst kann sich die Zelle nicht biegen. Dafür gehören Abstandshalter unter das feste Ende und über das freie.
- Der Pfeil auf der Zelle zeigt die Richtung, in der die Last wirken soll.
- Die vier Zellen sitzen in den Ecken, alle gleich ausgerichtet. Die Platte muss **steif** sein und darf nichts anderes berühren.
- Keine Zelle über 5 kg belasten. Kabel locker verlegen und an der Platine entlasten.

## Installation

1. **HACS:** *HACS → ⋮ → Benutzerdefinierte Repositories* `https://github.com/RedDragonNode/ha-spielzeug-wiegestation` als **Integration** hinzufügen, **Spielzeug Wiegestation** installieren und Home Assistant neu starten.
2. **Firmware:** Das Board mit der Firmware aus [`esphome/`](esphome/README.md) einrichten (ESPHome Device Builder). Die Gerätedatei dafür hat nur ein paar Zeilen.
3. **Integration:** *Einstellungen → Geräte & Dienste → Integration hinzufügen → Spielzeug Wiegestation*. Die vier Zellen werden vorgeschlagen, wenn die Firmware aus diesem Projekt läuft. Alle Entities erscheinen auf der Geräteseite der Waage, neben den Rohwerten.

## Eichen

*Einstellungen → Geräte & Dienste → Spielzeug Wiegestation → Konfigurieren → Waage eichen.* Du brauchst ein Gewicht, dessen Masse du genau kennst: 500 g bis 1 kg sind gut (zum Beispiel ein Päckchen Zucker oder Mehl, ein Eichgewicht oder viele Münzen). Unter 100 g wird die Eichung ungenau.

1. **Leere Platte:** alles herunternehmen, kurz warten, bis die Waage ruhig ist, und bestätigen. Die Waage merkt sich den Nullpunkt jeder Zelle.
2. **Gewicht in der Mitte:** das Gewicht in die Mitte der Platte legen und das Gewicht in Gramm eintragen. Damit ist die Waage schon geeicht, alle vier Zellen haben denselben Faktor.
3. **Genauer (optional):** dasselbe Gewicht nacheinander direkt über jede der vier Zellen legen. Daraus rechnet die Integration (Kleinste Quadrate über alle fünf Messungen) den Faktor jeder Zelle einzeln. Sie meldet die größte Abweichung. Liegt sie über 3 %, wird nichts gespeichert, das spricht für eine wackelnde Platte oder ein verrutschtes Gewicht.

Eine Zelle, die andersherum angeschlossen ist, erkennt der Assistent selbst. Dann geht es nur mit der Messung über jeder Zelle.

Die **Tara** setzt du mit der Taste `Tara`: Schale auflegen, Taste drücken, das Gewicht steht auf 0. Eichen setzt die Tara zurück.

## Entities

| Entity | Bedeutung |
|---|---|
| `sensor … Gewicht` | Gewicht in Gramm nach Tara, `unbekannt` bis zur Eichung |
| `binary_sensor … Waage ruhig` | das Gewicht hat sich in den eingestellten Sekunden höchstens um die Toleranz geändert |
| `binary_sensor … Belegt` | Gewicht über der Schwelle (fällt erst bei 60 % davon wieder aus, damit es nicht flackert) |
| `button … Tara` | setzt das Gewicht auf null |
| `sensor … Eichung` (Diagnose) | `Geeicht` oder `Nicht geeicht` |
| `sensor … Gewicht Zelle 1` bis `4` (Diagnose, aus) | Gewicht, das jede Zelle trägt |

Die Rohwerte der Firmware sind auf der Geräteseite als „Zelle 1“ bis „Zelle 4“ zu sehen.

### Einstellungen

*Konfigurieren → Schwellen einstellen:*

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Ruhig nach | 2 s | so lange darf sich das Gewicht höchstens um die Toleranz ändern |
| Toleranz für „ruhig“ | 2 g | größte Schwankung, die noch als ruhig gilt |
| Belegt ab | 5 g | ab diesem Gewicht gilt die Platte als belegt |

## Hinweise

- Die Rohwerte kommen etwa einmal pro Sekunde, wenn sich etwas ändert, sonst alle 15 Sekunden. Die Integration rechnet mit dem letzten Wert weiter. Für den Rekorder lohnt sich, die vier Rohwert-Sensoren und die Zellen-Gewichte vom Aufzeichnen auszunehmen.
- Ohne Eichung rechnet die Waage nur mit einem Richtwert, damit „ruhig“ schon beim Eichen funktioniert. Das Gewicht zeigt sie erst danach.
- Die Eichung liegt im Speicher von Home Assistant (nicht im Repo) und bleibt beim Neuladen und Neustarten erhalten. Beim Löschen der Integration wird sie mit entfernt.

## Geplant

- **0.2.0:** Spielzeuge anlernen (Name und Gewicht), erkennen, was aufliegt, mit Ereignissen für Automationen.
- **0.3.0:** Beispiele für Discord-Meldungen mit Kamera-Schnappschuss über [Discord Hub](https://github.com/RedDragonNode/ha-discord-hub).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
