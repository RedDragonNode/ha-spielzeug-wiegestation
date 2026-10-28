<p align="center">
  <img src="docs/banner.png" alt="Toy weighing station" width="520">
</p>

# Toy weighing station for Home Assistant

[![Tests](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/tests.yaml/badge.svg)](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/tests.yaml)
[![Hassfest](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hassfest.yaml)
[![HACS](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hacs.yaml/badge.svg)](https://github.com/RedDragonNode/ha-spielzeug-wiegestation/actions/workflows/hacs.yaml)

*[Deutsche Version](README.md)*

**A scale for toys.** An ESP32-P4 with Ethernet and PoE reads four load cells under one plate (one HX711 module each). Home Assistant calculates the weight, shows whether the scale is steady and whether something is on it, and calibrates itself through a wizard in the UI, without you having to flash the firmware again.

The project has two parts in one repo:

| Part | Where | What |
|---|---|---|
| **Firmware** (ESPHome) | [`esphome/`](esphome/README.md) | runs on the board and reports four raw values |
| **Integration** | `custom_components/spielzeug_wiegestation` | calculates tare, calibration, weight, "steady" and "occupied" |

> **Version 0.1.0:** The scale measures, calibrates and reports weight, steadiness and occupancy. Recognising individual toys by weight comes in 0.2.0.

| You want to … | Use |
|---|---|
| see the weight on the plate | `Weight` (in grams) |
| know whether the scale is steady | `Scale steady` |
| know whether something is on the plate | `Occupied` |
| subtract a tray or pad | the `Tare` button |
| calibrate the scale | *Configure → Calibrate the scale* |
| check whether a cell misbehaves | the disabled sensors `Weight cell 1` to `4` |

## Hardware

- **Board:** Waveshare ESP32-P4-ETH (with PoE module). The board has Ethernet only, no Wi-Fi.
- **Load cells:** four bar cells (5 kg each), each on its own **HX711** module. Together they carry up to about 20 kg.
- **Power:** PoE (IEEE 802.3af capable switch or injector) or USB-C.

> **Never connect PoE and USB at the same time.** Waveshare does not say whether the board tolerates both. To flash, unplug the network cable from the PoE port or plug the board into a normal network port.

### Wiring

Each HX711 module gets **3.3 V** (not 5 V). Data (`DT`) and clock (`SCK`) go to one pin of the board each:

| Cell | `DT` on the module to | `SCK` on the module to |
|---|---|---|
| 1 | `GPIO20` | `GPIO21` |
| 2 | `GPIO22` | `GPIO23` |
| 3 | `GPIO26` | `GPIO27` |
| 4 | `GPIO47` | `GPIO48` |

`VCC` of all modules goes to `3V3`, `GND` to `GND` of the board. The pins are on the right-hand header of the board, counted from the USB-C end: `VBUS`, `VSYS`, `GND`, `EN`, **`3V3`**, **`GPIO20`**, **`GPIO21`**, **`GND`**, `GPIO22`, `GPIO23`, `RUN`, `GPIO26`, `GND`, `GPIO27`, `GPIO32`, `GPIO33`, `GPIO46`, `GND`, `GPIO47`, `GPIO48`.

> **Mind the order:** On the HX711 module the row is usually `GND, DT, SCK, VCC`, on the board `3V3, GPIO20, GPIO21, GND` lie one below the other. A ribbon cable that simply connects both rows swaps 3V3 and GND and destroys the module. Connect each wire on its own, by name.

The cell connects to the module with four wires:

| Cell wire | Pin on the module |
|---|---|
| red | `E+` |
| black | `E−` |
| white | `A−` |
| green | `A+` |

That is the usual colour code. If a cell points the other way when you put a weight on it, `A+` and `A−` are swapped. That is not an error: the calibration wizard notices it and calculates a negative factor for that cell.

### Building the plate

- Each cell has a **fixed end** (with the two threaded holes, where the cable comes out) on the base and a **free end** that carries the plate. The free end needs **air** underneath, otherwise the cell cannot bend. Use spacers under the fixed end and above the free end.
- The arrow on the cell shows the direction in which the load should act.
- The four cells sit in the corners, all oriented the same way. The plate must be **stiff** and must not touch anything else.
- Never load a cell above 5 kg. Route the cables loosely and relieve the strain at the board.

## Installation

1. **HACS:** *HACS → ⋮ → Custom repositories*, add `https://github.com/RedDragonNode/ha-spielzeug-wiegestation` as **Integration**, install **Spielzeug Wiegestation** and restart Home Assistant.
2. **Firmware:** Set the board up with the firmware from [`esphome/`](esphome/README.md) (ESPHome Device Builder). The device file is only a few lines.
3. **Integration:** *Settings → Devices & services → Add integration → Spielzeug Wiegestation*. The four cells are suggested when the firmware from this project is running. All entities appear on the device page of the scale, next to the raw values.

## Calibrating

*Settings → Devices & services → Spielzeug Wiegestation → Configure → Calibrate the scale.* You need a weight whose mass you know exactly: 500 g to 1 kg is good (for example a pack of sugar or flour, a calibration weight or many coins). Below 100 g the calibration gets inaccurate.

1. **Empty plate:** take everything off, wait until the scale is steady and confirm. The scale remembers the zero point of each cell.
2. **Weight in the middle:** put the weight in the middle of the plate and enter its weight in grams. The scale is now calibrated, all four cells have the same factor.
3. **More accurate (optional):** put the same weight directly over each of the four cells in turn. From that the integration calculates (least squares over all five measurements) the factor of each cell separately. It reports the largest deviation. If it is above 3 %, nothing is saved, which points to a wobbling plate or a weight that slipped.

A cell that is wired the other way round is noticed by the wizard itself. Then only the measurement over each cell works.

You set the **tare** with the `Tare` button: put a tray on, press the button, the weight reads 0. Calibrating resets the tare.

## Entities

| Entity | Meaning |
|---|---|
| `sensor … Weight` | weight in grams after tare, `unknown` until calibrated |
| `binary_sensor … Scale steady` | the weight changed by no more than the tolerance within the set seconds |
| `binary_sensor … Occupied` | weight above the threshold (drops out only at 60 % of it, so it does not flicker) |
| `button … Tare` | sets the weight to zero |
| `sensor … Calibration` (diagnostic) | `Calibrated` or `Not calibrated` |
| `sensor … Weight cell 1` to `4` (diagnostic, off) | weight each cell carries |

The raw values of the firmware appear on the device page as "Zelle 1" to "Zelle 4".

### Settings

*Configure → Set thresholds:*

| Setting | Default | Meaning |
|---|---|---|
| Steady after | 2 s | the weight may change by no more than the tolerance for this long |
| Tolerance for "steady" | 2 g | largest swing that still counts as steady |
| Occupied from | 5 g | from this weight the plate counts as occupied |

## Notes

- The raw values arrive about once a second when something changes, otherwise every 15 seconds. The integration keeps calculating with the last value. For the recorder it is worth excluding the four raw-value sensors and the cell weights from recording.
- Without calibration the scale only calculates with a rough estimate, so "steady" already works during calibration. It shows the weight only afterwards.
- The calibration is stored in Home Assistant (not in the repo) and survives reloads and restarts. Deleting the integration removes it as well.

## Planned

- **0.2.0:** Teach toys (name and weight), recognise what is on the plate, with events for automations.
- **0.3.0:** Examples for Discord messages with a camera snapshot through [Discord Hub](https://github.com/RedDragonNode/ha-discord-hub).

## License

MIT, see [LICENSE](LICENSE).
