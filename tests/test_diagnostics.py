"""Diagnose-Download."""

from __future__ import annotations

from custom_components.spielzeug_wiegestation.diagnostics import async_get_config_entry_diagnostics

from .conftest import CELLS, Clock, setup_station, station_entry


async def test_diagnostics_show_calibration_and_values(hass, clock: Clock) -> None:
    entry = station_entry(occupied_g=8.0)
    manager = await setup_station(hass, entry, [100000, 200000, 300000, 400000])
    await manager.async_set_zero()
    await manager.async_apply_factors([0.002] * 4)
    clock.advance(5)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["entry"] == {"cells": CELLS}
    assert data["options"] == {"occupied_g": 8.0}
    assert data["calibration"]["calibrated"] is True
    assert data["calibration"]["factor"] == [0.002] * 4
    assert data["cells"] == dict(zip(CELLS, ["100000", "200000", "300000", "400000"], strict=True))
    assert data["raws"] == [100000.0, 200000.0, 300000.0, 400000.0]
    assert data["weight"] == 0.0
    assert data["stable"] is True
    assert data["occupied"] is False
