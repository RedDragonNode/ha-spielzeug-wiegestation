"""Übersetzungen: gleiche Schlüssel in beiden Sprachen, nur bekannte Platzhalter, nichts fehlt, was der Code braucht."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "spielzeug_wiegestation"
TRANSLATIONS = COMPONENT / "translations"
# Das Frontend liest jede geschweifte Klammer als Platzhalter und meldet einen Fehler, wenn der Wert fehlt.
ALLOWED_PLACEHOLDERS = {"corner", "details", "number", "weight"}


def _flatten(node: object, prefix: str = "") -> dict[str, str]:
    if isinstance(node, dict):
        out: dict[str, str] = {}
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else key))
        return out
    return {prefix: str(node)}


def _code(name: str) -> str:
    return (COMPONENT / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def texts() -> dict[str, dict[str, str]]:
    return {
        lang: _flatten(json.loads((TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))) for lang in ("de", "en")
    }


def test_both_languages_have_the_same_keys(texts: dict[str, dict[str, str]]) -> None:
    assert set(texts["de"]) == set(texts["en"])


@pytest.mark.parametrize("lang", ["de", "en"])
def test_only_known_placeholders(texts: dict[str, dict[str, str]], lang: str) -> None:
    for key, text in texts[lang].items():
        assert set(re.findall(r"\{([^{}]*)\}", text)) <= ALLOWED_PLACEHOLDERS, f"{lang}: {key}"
        assert text.count("{") == text.count("}"), f"{lang}: {key}"


def test_placeholders_match_between_languages(texts: dict[str, dict[str, str]]) -> None:
    for key, de_text in texts["de"].items():
        assert set(re.findall(r"\{(\w+)\}", de_text)) == set(re.findall(r"\{(\w+)\}", texts["en"][key])), key


@pytest.mark.parametrize("lang", ["de", "en"])
def test_no_text_is_empty(texts: dict[str, dict[str, str]], lang: str) -> None:
    assert all(text.strip() for text in texts[lang].values())


@pytest.mark.parametrize("lang", ["de", "en"])
def test_no_urls_in_texts(texts: dict[str, dict[str, str]], lang: str) -> None:
    """Hassfest lehnt Adressen in Übersetzungen ab."""
    for key, text in texts[lang].items():
        assert "http" not in text, f"{lang}: {key}"


@pytest.mark.parametrize("lang", ["de", "en"])
def test_every_step_of_the_flows_has_a_title(texts: dict[str, dict[str, str]], lang: str) -> None:
    steps = set(re.findall(r'step_id="(\w+)"', _code("config_flow.py")))
    assert {"user", "reconfigure", "init", "settings", "calibrate", "calibrate_weight", "calibrate_corner"} <= steps
    for step in steps:
        assert any(texts[lang].get(f"{flow}.step.{step}.title") for flow in ("config", "options")), f"{lang}: {step}"


@pytest.mark.parametrize("lang", ["de", "en"])
def test_every_menu_option_has_a_text(texts: dict[str, dict[str, str]], lang: str) -> None:
    menus = re.findall(r'step_id="(\w+)", menu_options=\[([^\]]*)\]', _code("config_flow.py"))
    assert len(menus) == 2
    for step, options in menus:
        for option in re.findall(r'"(\w+)"', options):
            assert f"options.step.{step}.menu_options.{option}" in texts[lang], f"{lang}: {step}.{option}"


@pytest.mark.parametrize("lang", ["de", "en"])
def test_every_error_and_abort_reason_used_in_the_code_has_a_text(texts: dict[str, dict[str, str]], lang: str) -> None:
    flow = _code("config_flow.py")
    errors = set(re.findall(r'errors\["base"\] = "(\w+)"', flow)) | set(re.findall(r'return "(\w+)"', flow))
    # Fehler der Rechnung gehen als Fehlertext ans Formular, außer der Eichung selbst: die bricht mit einem Grund ab
    # und `mixed_signs` hat eine eigene Seite
    calculation = set(re.findall(r'CalibrationError\("(\w+)"\)', _code("scale.py"))) - {"mixed_signs"}
    aborts = set(re.findall(r'reason="(\w+)"', flow)) | {"not_enough_positions"}
    errors |= calculation - aborts
    assert {"not_stable", "no_data", "no_load", "duplicate_cells"} <= errors
    assert {"calibration_saved", "calibration_rejected", "calibration_reset", "not_enough_positions"} <= aborts
    for key in errors:
        assert any(f"{flow_name}.error.{key}" in texts[lang] for flow_name in ("config", "options")), f"{lang}: {key}"
    for key in aborts | {"already_configured", "reconfigure_successful"}:
        assert any(f"{flow_name}.abort.{key}" in texts[lang] for flow_name in ("config", "options")), f"{lang}: {key}"


def test_every_exception_key_used_in_the_code_has_a_text(texts: dict[str, dict[str, str]]) -> None:
    used = set(re.findall(r'translation_key="(\w+)"', _code("manager.py")))
    assert used == {"no_data", "not_calibrated"}
    for lang, entries in texts.items():
        for key in used:
            assert f"exceptions.{key}.message" in entries, f"{lang}: {key}"


def test_every_entity_is_named_in_both_languages(texts: dict[str, dict[str, str]]) -> None:
    for domain in ("sensor", "binary_sensor", "button"):
        keys = set(re.findall(r'_attr_translation_key = "(\w+)"', _code(f"{domain}.py")))
        assert keys, domain
        for lang, entries in texts.items():
            for key in keys:
                assert f"entity.{domain}.{key}.name" in entries, f"{lang}: {domain}.{key}"
    for lang, entries in texts.items():
        for state in ("not_calibrated", "calibrated"):
            assert f"entity.sensor.calibration.state.{state}" in entries, f"{lang}: {state}"
