"""Das Manifest und die Bilder gehören zusammen und müssen zu HACS passen."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "spielzeug_wiegestation"


def test_manifest_domain_and_documentation() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "spielzeug_wiegestation"
    assert manifest["documentation"] == "https://github.com/RedDragonNode/ha-spielzeug-wiegestation"


def test_brand_images_exist() -> None:
    for name in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
        assert (COMPONENT / "brand" / name).is_file(), name
    assert (ROOT / "docs" / "banner.png").is_file()


def test_firmware_targets_production_silicon() -> None:
    """Das Board hat einen Chip ab Revision 3. Das Board-Profil für Vorserienchips lässt ihn endlos neu starten."""
    for path in (ROOT / "esphome").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        if "esp32:" not in text:
            continue
        assert "board: esp32-p4-evboard" not in text, path.name
        assert "engineering_sample: false" in text, path.name


def test_scale_pins_are_distinct_and_clear_of_board_pins() -> None:
    """Vier Zellen, acht verschiedene Pins, keiner davon an Ethernet, I2C, Audio, SD-Karte oder USB."""
    text = (ROOT / "esphome" / "waage.yaml").read_text(encoding="utf-8")
    assert text.count("platform: hx711") == 4
    pins = re.findall(r"^  cell\d_(?:dout|clk): GPIO(\d+)$", text, flags=re.MULTILINE)
    assert len(pins) == 8
    assert len(set(pins)) == 8
    used_by_board = {7, 8, 9, 10, 11, 12, 13, 24, 25, 31, 39, 40, 41, 42, 43, 44, 50, 51, 52, 53}
    assert not {int(p) for p in pins} & used_by_board


def test_firmware_never_holds_secrets() -> None:
    """API-Schlüssel und Kennwörter gehören nur in die Gerätedatei des Nutzers, nie in die Pakete im Repo."""
    for path in (ROOT / "esphome").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "encryption:" not in text, path.name
        assert "password:" not in text, path.name
