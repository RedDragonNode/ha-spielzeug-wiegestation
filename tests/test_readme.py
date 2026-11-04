"""Die READMEs sagen dasselbe wie die Firmware, und beide Sprachen haben dieselbe Gliederung."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

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


@pytest.mark.parametrize("name", ["README.md", "README.en.md"])
def test_readme_documents_every_event_the_code_fires(name: str) -> None:
    constants = (ROOT / "custom_components" / "spielzeug_wiegestation" / "const.py").read_text(encoding="utf-8")
    events = {
        f"spielzeug_wiegestation_{kind}" for kind in re.findall(r'^EVENT_\w+ = f"\{DOMAIN\}_(\w+)"', constants, re.M)
    }
    assert len(events) == 7
    text = (ROOT / name).read_text(encoding="utf-8")
    for event in events:
        assert f"`{event}`" in text, event


EVENT_FIELDS = {
    "toy",
    "toy_id",
    "weight",
    "tolerance",
    "total",
    "station",
    "entry_id",
    "description",
    "taught_at",
    "thread_id",
}


@pytest.mark.parametrize("name", ["README.md", "README.en.md"])
def test_discord_examples_use_real_events_and_fields(name: str) -> None:
    """Die Beispiele für Discord Hub dürfen nur Ereignisse und Felder nennen, die der Code wirklich schickt."""
    constants = (ROOT / "custom_components" / "spielzeug_wiegestation" / "const.py").read_text(encoding="utf-8")
    real = {
        f"spielzeug_wiegestation_{kind}" for kind in re.findall(r'^EVENT_\w+ = f"\{DOMAIN\}_(\w+)"', constants, re.M)
    }
    text = (ROOT / name).read_text(encoding="utf-8")
    section = text[text.index("### ", text.index("`spielzeug_wiegestation_unknown_removed`")) :].split("\n## ")[0]
    assert "discord_hub.send_message" in section
    assert set(re.findall(r"event_type: (\w+)", section)) <= real
    assert set(re.findall(r"`(spielzeug_wiegestation_\w+)`", section)) <= real
    used = set(re.findall(r"trigger\.(?:event\.data\.)?(\w+)", section)) - {"event"}
    assert used and used <= EVENT_FIELDS, used - EVENT_FIELDS
    # alle Automationen sind gültiges YAML mit echten Ereignissen und bekannten Aktionen
    actions_known = {
        "discord_hub.send_message",
        "discord_hub.forum_post",
        "discord_hub.update_thread",
        "spielzeug_wiegestation.set_toy_thread",
    }
    blocks = re.findall(r"```yaml\n(.*?)```", section, re.S)
    assert blocks
    for block in blocks:
        automation = yaml.safe_load(block)
        assert all(trigger["event_type"] in real for trigger in automation["triggers"])
        assert all(action["action"] in actions_known for action in automation["actions"])
