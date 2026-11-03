"""Spielzeug erkennen: Ereignisse, Entities, Nullpunkt-Nachführung und Anlernen."""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER, ConfigSubentry
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.spielzeug_wiegestation.const import (
    CONF_TOLERANCE,
    CONF_WEIGHT,
    DOMAIN,
    EVENT_TOY_PLACED,
    EVENT_TOY_REMOVED,
    EVENT_UNKNOWN_PLACED,
    EVENT_UNKNOWN_REMOVED,
    SUBENTRY_TOY,
)
from custom_components.spielzeug_wiegestation.diagnostics import async_get_config_entry_diagnostics

from .conftest import Clock, entity_id_of, set_cells, setup_station, station_entry, toy_data
from .test_config_flow import register_esphome_cells

ZERO = [100000, 200000, 300000, 400000]
FACTOR = 0.002  # g je Zähler, bei allen Zellen gleich
ON_ONE_CELL = (1.0, 0.0, 0.0, 0.0)  # die ganze Last auf Zelle 1: eine Änderung ist ein einziges Ereignis
TOYS = (toy_data("teddy", "Teddy", 250.0, 12.5), toy_data("auto", "Auto", 80.0, 4.0))


def raws_for(weight: float) -> list[float]:
    return [z + share * weight / FACTOR for z, share in zip(ZERO, ON_ONE_CELL, strict=True)]


async def quiet(hass, clock: Clock, seconds: float = 3) -> None:
    """Lässt Zeit vergehen, bis die Waage ruhig ist und die Erkennung läuft."""
    clock.advance(seconds)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def put(hass, clock: Clock, weight: float, seconds: float = 3) -> None:
    """Legt so viel Gewicht auf die Platte (insgesamt) und wartet, bis die Waage ruhig ist."""
    set_cells(hass, raws_for(weight))
    await hass.async_block_till_done()
    await quiet(hass, clock, seconds)


async def station(hass, clock: Clock, toys=TOYS, **options):
    """Eine geeichte Waage mit leerer Platte, auf der die Erkennung schon läuft."""
    entry = station_entry(toys=toys, **options)
    manager = await setup_station(hass, entry, ZERO)
    await manager.async_set_zero()
    await manager.async_apply_factors([FACTOR] * 4)
    await quiet(hass, clock)  # die erste ruhige leere Platte ist der Anfang
    return entry, manager


def state_of(hass, entry, domain: str, key: str):
    return hass.states.get(entity_id_of(hass, entry, domain, key))


# --------------------------------------------------------------------------- Ereignisse
async def test_placing_a_known_toy_fires_an_event_and_switches_its_sensor(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    placed = async_capture_events(hass, EVENT_TOY_PLACED)
    await put(hass, clock, 250.0)
    assert len(placed) == 1
    data = placed[0].data
    assert (data["toy"], data["toy_id"], data["entry_id"], data["station"]) == (
        "Teddy",
        "teddy",
        entry.entry_id,
        "Spielzeug Wiegestation",
    )
    assert data["weight"] == pytest.approx(250.0, abs=0.1)
    assert data["total"] == pytest.approx(250.0, abs=0.1)
    assert state_of(hass, entry, "binary_sensor", "toy_teddy").state == "on"
    assert state_of(hass, entry, "binary_sensor", "toy_auto").state == "off"
    plate = state_of(hass, entry, "sensor", "plate_items")
    assert plate.state == "1"
    assert plate.attributes["toys"] == ["Teddy"]
    assert plate.attributes["unknown_g"] == []


async def test_removing_the_toy_fires_removed_and_switches_the_sensor_off(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    await put(hass, clock, 250.0)
    removed = async_capture_events(hass, EVENT_TOY_REMOVED)
    await put(hass, clock, 0.0)
    assert [event.data["toy"] for event in removed] == ["Teddy"]
    assert removed[0].data["weight"] == pytest.approx(250.0, abs=0.1)
    assert state_of(hass, entry, "binary_sensor", "toy_teddy").state == "off"
    assert state_of(hass, entry, "sensor", "plate_items").state == "0"


async def test_an_unknown_thing_fires_the_unknown_events(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    placed = async_capture_events(hass, EVENT_UNKNOWN_PLACED)
    removed = async_capture_events(hass, EVENT_UNKNOWN_REMOVED)
    toy_events = async_capture_events(hass, EVENT_TOY_PLACED)
    await put(hass, clock, 150.0)
    assert len(placed) == 1
    assert placed[0].data["weight"] == pytest.approx(150.0, abs=0.1)
    assert "toy" not in placed[0].data
    plate = state_of(hass, entry, "sensor", "plate_items")
    assert (plate.state, plate.attributes["toys"]) == ("1", [])
    assert plate.attributes["unknown_g"] == [pytest.approx(150.0, abs=0.1)]
    await put(hass, clock, 0.0)
    assert len(removed) == 1
    assert removed[0].data["weight"] == pytest.approx(150.0, abs=0.1)
    assert toy_events == []


async def test_two_toys_one_after_the_other(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    placed = async_capture_events(hass, EVENT_TOY_PLACED)
    await put(hass, clock, 250.0)
    await put(hass, clock, 330.0)
    assert [event.data["toy"] for event in placed] == ["Teddy", "Auto"]
    assert state_of(hass, entry, "sensor", "plate_items").attributes["toys"] == ["Teddy", "Auto"]
    removed = async_capture_events(hass, EVENT_TOY_REMOVED)
    await put(hass, clock, 250.0)
    assert [event.data["toy"] for event in removed] == ["Auto"]
    assert state_of(hass, entry, "binary_sensor", "toy_teddy").state == "on"
    assert state_of(hass, entry, "binary_sensor", "toy_auto").state == "off"


async def test_noise_and_wobble_do_not_fire_events(hass, clock: Clock) -> None:
    _entry, _manager = await station(hass, clock)
    events = [
        async_capture_events(hass, event)
        for event in (EVENT_TOY_PLACED, EVENT_TOY_REMOVED, EVENT_UNKNOWN_PLACED, EVENT_UNKNOWN_REMOVED)
    ]
    for weight in (0.4, -0.8, 1.1, -1.5, 0.2):
        await put(hass, clock, weight)
    assert all(not captured for captured in events)


async def test_nothing_is_recognised_before_the_scale_is_calibrated(hass, clock: Clock) -> None:
    entry = station_entry(toys=TOYS)
    await setup_station(hass, entry, ZERO)
    events = async_capture_events(hass, EVENT_UNKNOWN_PLACED)
    await put(hass, clock, 250.0)
    assert events == []
    assert state_of(hass, entry, "binary_sensor", "toy_teddy").state == "unavailable"
    assert state_of(hass, entry, "sensor", "plate_items").state == "unavailable"


async def test_tare_with_a_toy_on_the_plate_starts_the_recognition_afresh(hass, clock: Clock) -> None:
    entry, manager = await station(hass, clock)
    await put(hass, clock, 250.0)  # eine Schale, die der Nutzer jetzt auf null setzt
    placed = async_capture_events(hass, EVENT_UNKNOWN_PLACED)
    await manager.async_tare()
    await quiet(hass, clock)
    assert placed == []
    assert state_of(hass, entry, "binary_sensor", "toy_teddy").state == "off"
    assert state_of(hass, entry, "sensor", "plate_items").state == "0"


# --------------------------------------------------------------------------- Nullpunkt nachführen
async def test_a_drifting_empty_plate_is_zeroed_without_events(hass, clock: Clock) -> None:
    entry, manager = await station(hass, clock)
    events = async_capture_events(hass, EVENT_UNKNOWN_PLACED)
    weight = entity_id_of(hass, entry, "sensor", "weight")
    for gross in (2.0, 4.0, 6.0, 8.0):  # die leere Platte kriecht ruhig, jeder Schritt unter der Mindestgröße
        await put(hass, clock, gross, seconds=12)
        assert float(hass.states.get(weight).state) == pytest.approx(0.0, abs=0.05)
    assert events == []
    assert manager.calibration.tare_g == pytest.approx(8.0)
    assert state_of(hass, entry, "binary_sensor", "occupied").state == "off"


async def test_the_zero_is_not_moved_while_a_toy_lies_on_the_plate(hass, clock: Clock) -> None:
    entry, manager = await station(hass, clock)
    await put(hass, clock, 250.0)
    await put(hass, clock, 252.0)
    assert manager.calibration.tare_g == 0.0
    assert float(state_of(hass, entry, "sensor", "weight").state) == pytest.approx(252.0, abs=2.1)


async def test_a_small_unknown_thing_is_not_swallowed_by_the_zero(hass, clock: Clock) -> None:
    entry, manager = await station(hass, clock)
    events = async_capture_events(hass, EVENT_UNKNOWN_PLACED)
    await put(hass, clock, 8.0)
    assert len(events) == 1
    assert manager.calibration.tare_g == 0.0
    assert float(state_of(hass, entry, "sensor", "weight").state) == pytest.approx(8.0, abs=0.1)


async def test_a_zero_drift_with_nothing_on_the_plate_at_the_start_is_zeroed(hass, clock: Clock) -> None:
    entry = station_entry(toys=TOYS)
    manager = await setup_station(hass, entry, ZERO)
    await manager.async_set_zero()
    await manager.async_apply_factors([FACTOR] * 4)
    set_cells(hass, raws_for(6.0))  # beim Start steht die leere Platte schon 6 g daneben
    await hass.async_block_till_done()
    await quiet(hass, clock, 12)
    assert manager.calibration.tare_g == pytest.approx(6.0)
    assert manager.plate_items == []
    assert state_of(hass, entry, "binary_sensor", "occupied").state == "off"


# --------------------------------------------------------------------------- Spielzeuge ändern
async def test_adding_a_toy_reloads_the_station_and_adds_its_sensor(hass, clock: Clock) -> None:
    entry, manager = await station(hass, clock)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType({CONF_WEIGHT: 30.0, CONF_TOLERANCE: 3.0}),
            subentry_type=SUBENTRY_TOY,
            title="Ball",
            unique_id=None,
        ),
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is not manager
    assert [toy.name for toy in entry.runtime_data.toys] == ["Teddy", "Auto", "Ball"]
    ball = next(sub for sub in entry.subentries.values() if sub.title == "Ball")
    assert entity_id_of(hass, entry, "binary_sensor", f"toy_{ball.subentry_id}")


async def test_removing_a_toy_removes_its_sensor(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    unique_id = f"{entry.entry_id}_toy_auto"
    assert er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, unique_id)
    hass.config_entries.async_remove_subentry(entry, "auto")
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, unique_id) is None
    assert [toy.name for toy in entry.runtime_data.toys] == ["Teddy"]


async def test_a_toy_renamed_reloads_with_the_new_name(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    hass.config_entries.async_update_subentry(entry, entry.subentries["teddy"], title="Bär")
    await hass.async_block_till_done()
    assert [toy.name for toy in entry.runtime_data.toys] == ["Bär", "Auto"]


async def test_diagnostics_list_the_toys_and_what_is_on_the_plate(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    await put(hass, clock, 250.0)
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["toys"] == [
        {"name": "Teddy", "weight_g": 250.0, "tolerance_g": 12.5},
        {"name": "Auto", "weight_g": 80.0, "tolerance_g": 4.0},
    ]
    assert [item["name"] for item in data["on_plate"]] == ["Teddy"]
    assert data["on_plate"][0]["weight_g"] == pytest.approx(250.0, abs=0.1)


# --------------------------------------------------------------------------- Anlernen
async def open_flow(hass, entry, source=SOURCE_USER, subentry_id=None):
    context = {"source": source}
    if subentry_id:
        context["subentry_id"] = subentry_id
    return await hass.config_entries.subentries.async_init((entry.entry_id, SUBENTRY_TOY), context=context)


def suggested(result) -> dict:
    return {str(key): key.description["suggested_value"] for key in result["data_schema"].schema if key.description}


async def test_teaching_a_toy_fills_in_the_measured_weight(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock, toys=())
    await put(hass, clock, 120.4)
    result = await open_flow(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert suggested(result) == {"weight_g": pytest.approx(120.4, abs=0.1)}
    assert result["description_placeholders"]["current"] == "120.4"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Bagger", "weight_g": 120.4}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    (subentry,) = entry.subentries.values()
    assert subentry.title == "Bagger"
    assert dict(subentry.data) == {"weight_g": 120.4, "tolerance_g": 6.0}  # 5 % des Gewichts
    await hass.async_block_till_done()
    assert [toy.name for toy in entry.runtime_data.toys] == ["Bagger"]


async def test_teaching_keeps_an_explicit_tolerance(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock, toys=())
    result = await open_flow(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Ball", "weight_g": 30.0, "tolerance_g": 7.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(next(iter(entry.subentries.values())).data) == {"weight_g": 30.0, "tolerance_g": 7.0}


async def test_teaching_without_a_steady_scale_leaves_the_weight_empty(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock, toys=())
    set_cells(hass, raws_for(120.0))  # eben aufgelegt, noch nicht ruhig
    await hass.async_block_till_done()
    result = await open_flow(hass, entry)
    assert suggested(result) == {}
    assert result["description_placeholders"]["current"] == "–"


@pytest.mark.parametrize(
    ("fields", "errors"),
    [
        ({"name": "   ", "weight_g": 100.0}, {"name": "name_missing"}),
        ({"name": "teddy", "weight_g": 100.0}, {"name": "name_exists"}),
        ({"name": "Feder", "weight_g": 3.0}, {"weight_g": "too_light"}),
        ({"name": "Bär", "weight_g": 255.0}, {"base": "overlap"}),
        ({"name": "Bär", "weight_g": 100.0, "tolerance_g": 200.0}, {"base": "overlap"}),
    ],
)
async def test_teaching_checks_name_weight_and_overlap(hass, clock: Clock, fields, errors) -> None:
    entry, _manager = await station(hass, clock)
    result = await open_flow(hass, entry)
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], fields)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors
    if "base" in errors:
        assert result["description_placeholders"]["other"] in ("Teddy", "Auto")
    assert len(entry.subentries) == 2  # nichts wurde angelegt


async def test_reconfiguring_a_toy_changes_name_weight_and_tolerance(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    result = await open_flow(hass, entry, SOURCE_RECONFIGURE, "teddy")
    assert result["type"] is FlowResultType.FORM
    assert suggested(result) == {"name": "Teddy", "weight_g": 250.0, "tolerance_g": 12.5}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Teddy neu", "weight_g": 255.0, "tolerance_g": 10.0},  # der Teddy selbst zählt nicht
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    teddy = entry.subentries["teddy"]
    assert teddy.title == "Teddy neu"
    assert dict(teddy.data) == {"weight_g": 255.0, "tolerance_g": 10.0}


# --------------------------------------------------------------------------- Geräte
async def test_toy_sensors_join_the_device_of_the_cells(hass, clock: Clock) -> None:
    device_id = register_esphome_cells(hass)
    entry, _manager = await station(hass, clock)
    registry = er.async_get(hass)
    for domain, key in (("binary_sensor", "toy_teddy"), ("binary_sensor", "toy_auto"), ("sensor", "weight")):
        assert registry.async_get(entity_id_of(hass, entry, domain, key)).device_id == device_id, key
    assert len(dr.async_get(hass).devices) == 1  # nur die Geräteseite der Zellen


async def test_without_a_device_every_toy_gets_its_own(hass, clock: Clock) -> None:
    entry, _manager = await station(hass, clock)
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    station_device = registry.async_get(entity_id_of(hass, entry, "sensor", "weight")).device_id
    teddy = devices.async_get(registry.async_get(entity_id_of(hass, entry, "binary_sensor", "toy_teddy")).device_id)
    assert teddy.id != station_device
    assert (teddy.name, teddy.identifiers) == ("Teddy", {(DOMAIN, "teddy")})
    assert entity_id_of(hass, entry, "binary_sensor", "toy_teddy") == "binary_sensor.teddy"
