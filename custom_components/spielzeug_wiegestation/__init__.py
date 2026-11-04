"""Spielzeug Wiegestation: Waage für Spielzeug mit ESP32-P4 und vier Wägezellen."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_THREAD, DOMAIN, SERVICE_SET_TOY_THREAD, SUBENTRY_TOY
from .manager import StationManager, calibration_store

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type WiegestationConfigEntry = ConfigEntry[StationManager]


SET_TOY_THREAD_SCHEMA = vol.Schema({vol.Required("toy_id"): cv.string, vol.Required(CONF_THREAD): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def set_toy_thread(call: ServiceCall) -> None:
        """Verknüpft ein Spielzeug mit seinem Thread. Eine leere Kennung löst die Verknüpfung."""
        toy_id = call.data["toy_id"]
        for entry in hass.config_entries.async_entries(DOMAIN):
            subentry = entry.subentries.get(toy_id)
            if subentry is not None and subentry.subentry_type == SUBENTRY_TOY:
                hass.config_entries.async_update_subentry(
                    entry, subentry, data={**subentry.data, CONF_THREAD: call.data[CONF_THREAD].strip()}
                )
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="unknown_toy", translation_placeholders={"toy_id": toy_id}
        )

    hass.services.async_register(DOMAIN, SERVICE_SET_TOY_THREAD, set_toy_thread, schema=SET_TOY_THREAD_SCHEMA)
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
    if manager is None:
        return
    toys_changed = manager.async_update_toys()  # meldet Anlernen, Ändern und Löschen
    if toys_changed or dict(entry.options) != manager.options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WiegestationConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Beim Löschen der Integration auch die gespeicherte Eichung entfernen."""
    await calibration_store(hass, entry.entry_id).async_remove()
