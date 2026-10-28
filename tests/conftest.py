"""Gemeinsame Fixtures: ein Eintrag mit vier Zell-Sensoren und eine Uhr, die der Test selbst vorstellt."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spielzeug_wiegestation import manager as manager_module
from custom_components.spielzeug_wiegestation.const import CONF_CELLS, DOMAIN

CELLS = [f"sensor.zelle_{number}" for number in range(1, 5)]
TITLE = "Spielzeug Wiegestation"


class Clock:
    """Ersatz für `time.monotonic`: steht still, bis der Test sie weiterstellt."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Lässt Home Assistant die Integration aus `custom_components` laden."""


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(manager_module, "_now", fake)
    return fake


def station_entry(**options: float) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=TITLE,
        unique_id="|".join(CELLS),
        data={CONF_CELLS: list(CELLS)},
        options=options,
        minor_version=1,
    )


def set_cells(hass: HomeAssistant, values: Sequence[float | str]) -> None:
    """Die vier Rohwert-Sensoren melden diese Werte (Texte wie `unavailable` gehen auch)."""
    for entity_id, value in zip(CELLS, values, strict=True):
        hass.states.async_set(entity_id, str(value))


async def setup_station(hass: HomeAssistant, entry: MockConfigEntry, values: Sequence[float | str] | None = None):
    """Setzt die Zellen, legt den Eintrag an und gibt den Manager zurück."""
    if values is not None:
        set_cells(hass, values)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


def entity_id_of(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, f"{domain}.{key}"
    return entity_id
