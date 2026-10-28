"""Das Manifest und die Bilder gehören zusammen und müssen zu HACS passen."""

from __future__ import annotations

import json
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


def test_firmware_never_holds_secrets() -> None:
    """API-Schlüssel und Kennwörter gehören nur in die Gerätedatei des Nutzers, nie in die Pakete im Repo."""
    for path in (ROOT / "esphome").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "encryption:" not in text, path.name
        assert "password:" not in text, path.name
