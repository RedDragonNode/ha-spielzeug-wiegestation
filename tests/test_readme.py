"""Die READMEs sagen dasselbe wie die Firmware, und beide Sprachen haben dieselbe Gliederung."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _pins_of_waage_yaml() -> dict[str, tuple[str, str]]:
    text = (ROOT / "esphome" / "waage.yaml").read_text(encoding="utf-8")
    return {
        number: (dout, clk)
        for number, dout, clk in zip(
            "1234",
            re.findall(r"^  cell\d_dout: (GPIO\d+)$", text, flags=re.MULTILINE),
            re.findall(r"^  cell\d_clk: (GPIO\d+)$", text, flags=re.MULTILINE),
            strict=True,
        )
    }


@pytest.mark.parametrize("name", ["README.md", "README.en.md"])
def test_wiring_table_matches_the_firmware(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\d) \| `(GPIO\d+)` \| `(GPIO\d+)` \|$", text, flags=re.MULTILINE)
    assert {number: (dout, clk) for number, dout, clk in rows} == _pins_of_waage_yaml()


def test_both_languages_have_the_same_structure() -> None:
    de = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^## ", de, flags=re.MULTILINE)) == len(re.findall(r"^## ", en, flags=re.MULTILINE))
    assert len(re.findall(r"^### ", de, flags=re.MULTILINE)) == len(re.findall(r"^### ", en, flags=re.MULTILINE))
    assert de.count("|---|") == en.count("|---|")
    for text in (de, en):
        assert "docs/banner.png" in text
        assert "esphome/README.md" in text
    assert "README.en.md" in de
    assert "README.md" in en
