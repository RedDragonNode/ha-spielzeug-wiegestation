"""Die Waage in Home Assistant: Entities, Gewicht, Ruhe, Belegt, Tara, Speicher."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.spielzeug_wiegestation.const import DOMAIN
from custom_components.spielzeug_wiegestation.manager import calibration_store

from .conftest import CELLS, Clock, entity_id_of, set_cells, setup_station, station_entry

ZERO = [100000, 200000, 300000, 400000]
FACTOR = 0.002  # g je Zähler, bei allen Zellen gleich


def raws_for(weight: float, shares=(0.25, 0.25, 0.25, 0.25)) -> list[float]:
    return [z + share * weight / FACTOR for z, share in zip(ZERO, shares, strict=True)]


async def calibrated_station(hass, clock: Clock, **options):
    """Eine geeichte Waage mit leerer Platte."""
    entry = station_entry(**options)
    manager = await setup_station(hass, entry, ZERO)
    await manager.async_set_zero()
    await manager.async_apply_factors([FACTOR] * 4)
    clock.advance(10)
    return entry, manager


async def test_entities_and_unavailable_without_cells(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry)  # die Zell-Sensoren gibt es noch nicht
    assert entry.state is ConfigEntryState.LOADED
    for domain, key in (
        ("sensor", "weight"),
        ("sensor", "cell_1_weight"),
        ("binary_sensor", "stable"),
        ("binary_sensor", "occupied"),
        ("button", "tare"),
        ("sensor", "calibration"),
    ):
        assert entity_id_of(hass, entry, domain, key)
    assert hass.states.get(entity_id_of(hass, entry, "sensor", "weight")).state == STATE_UNAVAILABLE
    # der Stand der Eichung gilt auch ohne Zellen
    assert hass.states.get(entity_id_of(hass, entry, "sensor", "calibration")).state == "not_calibrated"


async def test_weight_is_unknown_until_calibrated(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry, ZERO)
    assert hass.states.get(entity_id_of(hass, entry, "sensor", "weight")).state == STATE_UNKNOWN


async def test_weight_follows_the_cells_after_calibration(hass, clock: Clock) -> None:
    entry, _manager = await calibrated_station(hass, clock)
    weight = entity_id_of(hass, entry, "sensor", "weight")
    assert hass.states.get(weight).state == "0.0"
    set_cells(hass, raws_for(123.4))
    await hass.async_block_till_done()
    assert float(hass.states.get(weight).state) == pytest.approx(123.4, abs=0.05)
    assert hass.states.get(entity_id_of(hass, entry, "sensor", "calibration")).state == "calibrated"


async def test_one_cell_unavailable_makes_the_scale_unavailable(hass, clock: Clock) -> None:
    entry, _manager = await calibrated_station(hass, clock)
    set_cells(hass, [ZERO[0], ZERO[1], ZERO[2], STATE_UNAVAILABLE])
    await hass.async_block_till_done()
    assert hass.states.get(entity_id_of(hass, entry, "sensor", "weight")).state == STATE_UNAVAILABLE
    assert hass.states.get(entity_id_of(hass, entry, "binary_sensor", "stable")).state == STATE_UNAVAILABLE
    set_cells(hass, ZERO)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id_of(hass, entry, "sensor", "weight")).state == "0.0"


async def test_cell_weights_are_diagnostic_and_off_by_default(hass, clock: Clock) -> None:
    entry, manager = await calibrated_station(hass, clock)
    registry_entry = er.async_get(hass).async_get(entity_id_of(hass, entry, "sensor", "cell_2_weight"))
    assert registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry_entry.entity_category == "diagnostic"
    assert manager.cell_weight(1) == pytest.approx(0.0)
    set_cells(hass, raws_for(400, shares=(0.1, 0.2, 0.3, 0.4)))
    assert manager.cell_weight(1) == pytest.approx(80.0)


async def test_stable_follows_time_and_changes(hass, clock: Clock) -> None:
    entry, _manager = await calibrated_station(hass, clock)
    stable = entity_id_of(hass, entry, "binary_sensor", "stable")
    set_cells(hass, raws_for(250))
    await hass.async_block_till_done()
    assert hass.states.get(stable).state == "off"  # eben erst geändert
    clock.advance(3)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert hass.states.get(stable).state == "on"
    set_cells(hass, raws_for(400))
    await hass.async_block_till_done()
    assert hass.states.get(stable).state == "off"


async def test_small_changes_within_the_tolerance_stay_steady(hass, clock: Clock) -> None:
    _entry, manager = await calibrated_station(hass, clock)
    for weight in (300.0, 300.5, 299.6, 300.3):
        set_cells(hass, raws_for(weight))
        await hass.async_block_till_done()
        clock.advance(1)
    clock.advance(3)
    assert manager.stable


async def test_occupied_has_a_hysteresis(hass, clock: Clock) -> None:
    entry, _manager = await calibrated_station(hass, clock, occupied_g=10.0)
    occupied = entity_id_of(hass, entry, "binary_sensor", "occupied")
    states = []
    for weight in (0, 9, 10, 7, 6.5, 5.9, 0):
        set_cells(hass, raws_for(weight))
        await hass.async_block_till_done()
        states.append(hass.states.get(occupied).state)
    assert states == ["off", "off", "on", "on", "on", "off", "off"]


async def test_occupied_is_off_while_not_calibrated(hass, clock: Clock) -> None:
    entry = station_entry()
    manager = await setup_station(hass, entry, ZERO)
    set_cells(hass, raws_for(500))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id_of(hass, entry, "binary_sensor", "occupied")).state == "off"
    assert manager.weight is None


async def test_tare_sets_the_weight_on_the_plate_to_zero(hass, clock: Clock) -> None:
    entry, _manager = await calibrated_station(hass, clock)
    set_cells(hass, raws_for(80))  # eine Schale
    await hass.async_block_till_done()
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id_of(hass, entry, "button", "tare")}, blocking=True
    )
    weight = entity_id_of(hass, entry, "sensor", "weight")
    assert float(hass.states.get(weight).state) == pytest.approx(0.0, abs=0.05)
    set_cells(hass, raws_for(80 + 55))
    await hass.async_block_till_done()
    assert float(hass.states.get(weight).state) == pytest.approx(55.0, abs=0.05)


async def test_tare_needs_a_calibration_and_values(hass, clock: Clock) -> None:
    entry = station_entry()
    manager = await setup_station(hass, entry, ZERO)
    with pytest.raises(HomeAssistantError):
        await manager.async_tare()  # noch nicht geeicht
    set_cells(hass, [ZERO[0], ZERO[1], ZERO[2], STATE_UNKNOWN])
    with pytest.raises(HomeAssistantError):
        await manager.async_tare()  # keine Werte


async def test_calibration_survives_a_reload_and_goes_with_the_entry(hass, clock: Clock) -> None:
    entry, manager = await calibrated_station(hass, clock)
    await manager.async_apply_factors([0.002, 0.0021, 0.0019, 0.0022])
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    again = entry.runtime_data
    assert again is not manager
    assert again.calibrated
    assert again.calibration.factor == [0.002, 0.0021, 0.0019, 0.0022]
    assert again.calibration.zero == [float(z) for z in ZERO]
    assert await calibration_store(hass, entry.entry_id).async_load() is not None
    assert await hass.config_entries.async_remove(entry.entry_id)
    assert await calibration_store(hass, entry.entry_id).async_load() is None


async def test_entities_join_the_device_of_the_cells(hass, clock: Clock) -> None:
    """Liegen die Zellen an einem Gerät, kommen Gewicht & Co. auf dessen Seite, nicht auf ein zweites."""
    other = MockConfigEntry(domain="esphome", title="Spielzeug Wiegestation")
    other.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("esphome", "waage")}, name="Spielzeug Wiegestation"
    )
    registry = er.async_get(hass)
    for number, entity_id in enumerate(CELLS, start=1):
        registry.async_get_or_create(
            "sensor",
            "esphome",
            f"waage-{number}",
            suggested_object_id=entity_id.split(".")[1],
            config_entry=other,
            device_id=device.id,
            original_name=f"Zelle {number}",
        )
    entry = station_entry()
    await setup_station(hass, entry, ZERO)
    for domain, key in (("sensor", "weight"), ("binary_sensor", "stable"), ("button", "tare")):
        assert registry.async_get(entity_id_of(hass, entry, domain, key)).device_id == device.id


async def test_without_a_device_the_station_makes_its_own(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry, ZERO)
    registry_entry = er.async_get(hass).async_get(entity_id_of(hass, entry, "sensor", "weight"))
    device = dr.async_get(hass).async_get(registry_entry.device_id)
    assert device.identifiers == {(DOMAIN, entry.entry_id)}
    assert device.name == "Spielzeug Wiegestation"
