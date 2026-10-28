"""Sensoren: Gewicht, Gewicht je Zelle und Stand der Eichung."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WiegestationConfigEntry
from .const import CAL_DONE, CAL_NONE
from .entity import StationEntity
from .manager import StationManager


async def async_setup_entry(
    hass: HomeAssistant, entry: WiegestationConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manager = entry.runtime_data
    async_add_entities(
        [
            WeightSensor(manager),
            CalibrationSensor(manager),
            *(CellWeightSensor(manager, index) for index in range(len(manager.cells))),
        ]
    )


class WeightSensor(StationEntity, SensorEntity):
    """Gewicht auf der Platte nach Tara, `unbekannt` bis zum Eichen."""

    _attr_translation_key = "weight"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, manager: StationManager) -> None:
        super().__init__(manager, "weight")

    @property
    def native_value(self) -> float | None:
        weight = self.manager.weight
        return None if weight is None else round(weight, 1)


class CellWeightSensor(StationEntity, SensorEntity):
    """Gewicht, das eine einzelne Zelle trägt. Hilft, die Eichung und den Aufbau zu prüfen."""

    _attr_translation_key = "cell_weight"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, manager: StationManager, index: int) -> None:
        super().__init__(manager, f"cell_{index + 1}_weight")
        self.index = index
        self._attr_translation_placeholders = {"number": str(index + 1)}

    @property
    def native_value(self) -> float | None:
        weight = self.manager.cell_weight(self.index)
        return None if weight is None else round(weight, 1)


class CalibrationSensor(StationEntity, SensorEntity):
    """Ob die Waage geeicht ist."""

    _attr_translation_key = "calibration"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [CAL_NONE, CAL_DONE]  # noqa: RUF012
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: StationManager) -> None:
        super().__init__(manager, "calibration")

    @property
    def available(self) -> bool:
        return True  # der Stand der Eichung gilt auch, wenn die Zellen gerade nichts melden

    @property
    def native_value(self) -> str:
        return CAL_DONE if self.manager.calibrated else CAL_NONE
