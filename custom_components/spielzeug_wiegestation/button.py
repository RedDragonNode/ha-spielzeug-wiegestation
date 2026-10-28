"""Taste: Tara."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WiegestationConfigEntry
from .entity import StationEntity
from .manager import StationManager


async def async_setup_entry(
    hass: HomeAssistant, entry: WiegestationConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([TareButton(entry.runtime_data)])


class TareButton(StationEntity, ButtonEntity):
    """Setzt das Gewicht auf der Platte auf null, zum Beispiel mit einer Schale darauf."""

    _attr_translation_key = "tare"

    def __init__(self, manager: StationManager) -> None:
        super().__init__(manager, "tare")

    async def async_press(self) -> None:
        await self.manager.async_tare()
