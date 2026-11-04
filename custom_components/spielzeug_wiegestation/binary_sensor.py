"""Binärsensoren: Waage ruhig und Platte belegt."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WiegestationConfigEntry
from .const import DOMAIN, SUBENTRY_TOY
from .entity import StationEntity
from .manager import StationManager


async def async_setup_entry(
    hass: HomeAssistant, entry: WiegestationConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager = entry.runtime_data
    async_add_entities([StableSensor(manager), OccupiedSensor(manager)])
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_TOY:
            async_add_entities([ToySensor(manager, subentry)], config_subentry_id=subentry.subentry_id)


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


class ToySensor(StationEntity, BinarySensorEntity):
    """Ein angelerntes Spielzeug liegt auf der Platte."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, manager: StationManager, subentry: ConfigSubentry) -> None:
        super().__init__(manager, f"toy_{subentry.subentry_id}")
        self.toy_id = subentry.subentry_id
        if self.device_entry is None:
            # Es gibt keine ESPHome-Geräteseite: Ein Gerät gehört zu genau einem Untereintrag, also bekommt jedes
            # Spielzeug sein eigenes und der Sensor heißt wie das Spielzeug.
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, subentry.subentry_id)},
                name=subentry.title,
                manufacturer="RedDragonNode",
                model="Spielzeug",
            )
            self._attr_name = None
        else:
            self._attr_name = subentry.title

    @property
    def available(self) -> bool:
        return self.manager.available and self.manager.calibrated

    @property
    def is_on(self) -> bool:
        return self.toy_id in self.manager.present_toy_ids

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Der Steckbrief des Spielzeugs."""
        card = self.manager.cards.get(self.toy_id, {})
        return {
            "weight_g": card.get("weight"),
            "tolerance_g": card.get("tolerance"),
            "description": card.get("description"),
            "taught_at": card.get("taught_at"),
            "thread_id": card.get("thread_id"),
        }
