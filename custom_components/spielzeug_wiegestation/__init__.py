"""Spielzeug Wiegestation: Waage für Spielzeug mit ESP32-P4 und vier Wägezellen."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .manager import StationManager, calibration_store

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type WiegestationConfigEntry = ConfigEntry[StationManager]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WiegestationConfigEntry) -> bool:
    manager = StationManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    manager.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WiegestationConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Beim Löschen der Integration auch die gespeicherte Eichung entfernen."""
    await calibration_store(hass, entry.entry_id).async_remove()
