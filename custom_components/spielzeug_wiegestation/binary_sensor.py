"""Binärsensoren: Waage ruhig und Platte belegt."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WiegestationConfigEntry
from .entity import StationEntity
from .manager import StationManager


async def async_setup_entry(
    hass: HomeAssistant, entry: WiegestationConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager = entry.runtime_data
    async_add_entities([StableSensor(manager), OccupiedSensor(manager)])


class StableSensor(StationEntity, BinarySensorEntity):
    """Das Gewicht hat sich lange genug nicht mehr geändert."""

    _attr_translation_key = "stable"

    def __init__(self, manager: StationManager) -> None:
        super().__init__(manager, "stable")

    @property
    def is_on(self) -> bool:
        return self.manager.stable


class OccupiedSensor(StationEntity, BinarySensorEntity):
    """Etwas liegt auf der Platte (Gewicht über der Schwelle)."""

    _attr_translation_key = "occupied"

    def __init__(self, manager: StationManager) -> None:
        super().__init__(manager, "occupied")

    @property
    def is_on(self) -> bool:
        return self.manager.occupied
