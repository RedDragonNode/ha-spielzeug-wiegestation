"""Spielzeug Wiegestation: Waage für Spielzeug mit ESP32-P4 und vier Wägezellen."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .manager import StationManager, calibration_store, toys_of

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
    entry.async_on_unload(entry.add_update_listener(_async_entry_changed))
    return True


async def _async_entry_changed(hass: HomeAssistant, entry: WiegestationConfigEntry) -> None:
    """Schwellen oder Spielzeuge wurden geändert: neu laden, damit Erkennung und Entities dazu passen."""
    manager = getattr(entry, "runtime_data", None)
    if manager is not None and (toys_of(entry) != manager.toys or dict(entry.options) != manager.options):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WiegestationConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Beim Löschen der Integration auch die gespeicherte Eichung entfernen."""
    await calibration_store(hass, entry.entry_id).async_remove()
