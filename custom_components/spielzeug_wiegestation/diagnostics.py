"""Diagnose-Download: Eichung, Rohwerte und Zustand der Waage (nichts Geheimes)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import WiegestationConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WiegestationConfigEntry) -> dict[str, Any]:
    manager = entry.runtime_data
    return {
        "entry": dict(entry.data),
        "options": dict(entry.options),
        "calibration": manager.calibration.to_dict(),
        "cells": {
            entity_id: (state.state if (state := hass.states.get(entity_id)) else None) for entity_id in manager.cells
        },
        "raws": manager.raws,
        "weight": manager.weight,
        "stable": manager.stable,
        "occupied": manager.occupied,
    }
