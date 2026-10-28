"""Basisklasse der Entities: hängt sich an das Gerät der Zellen und folgt dem Manager."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import StationManager


class StationEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: StationManager, key: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.entry.entry_id}_{key}"
        if device := async_entity_id_to_device(manager.hass, manager.cells[0]):
            self.device_entry = device  # alles liegt auf der Geräteseite der Waage, neben den Rohwerten
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, manager.entry.entry_id)},
                name=manager.entry.title,
                manufacturer="RedDragonNode",
                model="Spielzeug Wiegestation",
            )

    @property
    def available(self) -> bool:
        return self.manager.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, self.manager.signal, self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()
