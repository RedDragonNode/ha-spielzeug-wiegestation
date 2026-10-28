"""Einrichten, Ändern der Zellen und der Eichen-Assistent."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spielzeug_wiegestation.config_flow import suggest_cells
from custom_components.spielzeug_wiegestation.const import CONF_CELLS, DOMAIN

from .conftest import CELLS, Clock, set_cells, setup_station, station_entry

ZERO = [100000, 200000, 300000, 400000]
TRUE_FACTORS = [0.0023, 0.0021, 0.0025, -0.0022]  # die vierte Zelle ist andersherum angeschlossen
SAME_WAY = [0.0023, 0.0021, 0.0025, 0.0022]
WEIGHT = 500.0


def cell_fields(cells=CELLS) -> dict[str, str]:
    return {f"cell_{number}": entity_id for number, entity_id in enumerate(cells, start=1)}


def raws_with_shares(shares, factors=TRUE_FACTORS) -> list[float]:
    """Rohwerte, die vier Zellen mit diesen Faktoren bei WEIGHT g und diesem Lastanteil melden würden."""
    return [z + share * WEIGHT / f for z, share, f in zip(ZERO, shares, factors, strict=True)]


def register_esphome_cells(hass, names=("Zelle 1", "Zelle 2", "Zelle 3", "Zelle 4")) -> str:
    other = MockConfigEntry(domain="esphome", title="Waage")
    other.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("esphome", "waage")}, name="Waage"
    )
    for number, (name, entity_id) in enumerate(zip(names, CELLS, strict=False), start=1):
        er.async_get(hass).async_get_or_create(
            "sensor",
            "esphome",
            f"w-{number}",
            suggested_object_id=entity_id.split(".")[1],
            config_entry=other,
            device_id=device.id,
            original_name=name,
        )
    return device.id


# --------------------------------------------------------------------------- Einrichten
async def test_user_flow_suggests_the_cells_of_the_esphome_device(hass) -> None:
    register_esphome_cells(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    suggested = {
        str(key): key.description["suggested_value"] for key in result["data_schema"].schema if key.description
    }
    assert suggested == cell_fields()


async def test_user_flow_creates_the_entry(hass) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Waage Spielzimmer", **cell_fields()}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Waage Spielzimmer"
    assert result["data"] == {CONF_CELLS: CELLS}
    assert result["result"].unique_id == "|".join(CELLS)


async def test_user_flow_needs_four_different_sensors(hass) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    fields = cell_fields([CELLS[0], CELLS[1], CELLS[2], CELLS[2]])
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "x", **fields})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "duplicate_cells"}


async def test_user_flow_does_not_add_the_same_cells_twice(hass) -> None:
    station_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "x", **cell_fields()})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_changes_the_cells(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry, ZERO)
    other = [f"sensor.neu_{number}" for number in range(1, 5)]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    duplicate = await hass.config_entries.flow.async_configure(result["flow_id"], cell_fields([other[0]] * 4))
    assert duplicate["errors"] == {"base": "duplicate_cells"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], cell_fields(other))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CELLS] == other


@pytest.mark.parametrize(
    "names",
    [("Zelle 1", "Zelle 2", "Zelle 3"), ("Zelle 1", "Zelle 2", "Zelle 3", "Gewicht")],
)
async def test_no_suggestion_without_all_four_cells(hass, names) -> None:
    register_esphome_cells(hass, names)
    assert suggest_cells(hass) == {}


# --------------------------------------------------------------------------- Eichen-Assistent
async def open_menu(hass, entry) -> str:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"calibrate", "settings", "reset_calibration"}
    return result["flow_id"]


async def pick(hass, flow_id: str, step: str):
    return await hass.config_entries.options.async_configure(flow_id, {"next_step_id": step})


async def submit(hass, flow_id: str, data=None):
    return await hass.config_entries.options.async_configure(flow_id, data or {})


async def put_weight_on(hass, clock: Clock, shares, factors=SAME_WAY) -> None:
    """Gewicht auflegen und lange genug warten, bis die Waage ruhig ist."""
    set_cells(hass, raws_with_shares(shares, factors))
    await hass.async_block_till_done()
    clock.advance(3)


async def start_calibration(hass, clock: Clock):
    entry = station_entry()
    manager = await setup_station(hass, entry, ZERO)
    clock.advance(3)
    flow_id = await open_menu(hass, entry)
    form = await pick(hass, flow_id, "calibrate")
    assert form["type"] is FlowResultType.FORM
    assert form["step_id"] == "calibrate"
    return entry, manager, flow_id


async def test_calibrate_with_only_the_middle(hass, clock: Clock) -> None:
    _entry, manager, flow_id = await start_calibration(hass, clock)
    form = await submit(hass, flow_id)  # leere Platte
    assert form["step_id"] == "calibrate_weight"
    clock.advance(3)
    await put_weight_on(hass, clock, [0.25] * 4)
    menu = await submit(hass, flow_id, {"weight_g": WEIGHT})
    assert menu["type"] is FlowResultType.MENU
    assert menu["step_id"] == "calibrate_more"
    result = await pick(hass, flow_id, "calibrate_done")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "calibration_saved_center"
    assert manager.calibrated
    assert len(set(manager.calibration.factor)) == 1
    clock.advance(3)
    assert manager.weight == pytest.approx(WEIGHT, rel=1e-6)


async def test_calibrate_every_cell_individually(hass, clock: Clock) -> None:
    _entry, manager, flow_id = await start_calibration(hass, clock)
    await submit(hass, flow_id)
    clock.advance(3)
    await put_weight_on(hass, clock, [0.25] * 4)
    await submit(hass, flow_id, {"weight_g": WEIGHT})
    form = await pick(hass, flow_id, "calibrate_corner")
    for corner in range(1, 5):
        assert form["step_id"] == "calibrate_corner"
        assert form["description_placeholders"] == {"corner": str(corner), "weight": "500"}
        shares = [0.1] * 4
        shares[corner - 1] = 0.7
        await put_weight_on(hass, clock, shares)
        form = await submit(hass, flow_id)
    assert form["type"] is FlowResultType.ABORT
    assert form["reason"] == "calibration_saved"
    assert float(form["description_placeholders"]["details"]) < 0.01
    assert manager.calibration.factor == pytest.approx(SAME_WAY, rel=1e-6)
    assert manager.calibration.zero == [float(z) for z in ZERO]
    set_cells(hass, raws_with_shares([0.4, 0.3, 0.2, 0.1], SAME_WAY))
    assert manager.weight == pytest.approx(WEIGHT, rel=1e-6)


async def test_a_reversed_cell_gets_a_negative_factor(hass, clock: Clock) -> None:
    _entry, manager, flow_id = await start_calibration(hass, clock)
    await submit(hass, flow_id)
    clock.advance(3)
    await put_weight_on(hass, clock, [0.25] * 4, TRUE_FACTORS)
    form = await submit(hass, flow_id, {"weight_g": WEIGHT})
    assert form["type"] is FlowResultType.FORM
    assert form["step_id"] == "calibrate_signs"  # nur über jeder Zelle einzeln zu eichen
    form = await submit(hass, flow_id)
    for corner in range(1, 5):
        assert form["step_id"] == "calibrate_corner"
        assert form["description_placeholders"]["corner"] == str(corner)
        shares = [0.1] * 4
        shares[corner - 1] = 0.7
        await put_weight_on(hass, clock, shares, TRUE_FACTORS)
        form = await submit(hass, flow_id)
    assert form["reason"] == "calibration_saved"
    assert manager.calibration.factor == pytest.approx(TRUE_FACTORS, rel=1e-6)
    set_cells(hass, raws_with_shares([0.4, 0.3, 0.2, 0.1], TRUE_FACTORS))
    assert manager.weight == pytest.approx(WEIGHT, rel=1e-6)


async def test_a_wobbling_plate_is_not_saved(hass, clock: Clock) -> None:
    _entry, manager, flow_id = await start_calibration(hass, clock)
    await submit(hass, flow_id)
    clock.advance(3)
    await put_weight_on(hass, clock, [0.25] * 4)
    await submit(hass, flow_id, {"weight_g": WEIGHT})
    form = await pick(hass, flow_id, "calibrate_corner")
    for corner in range(1, 5):
        shares = [0.1] * 4
        shares[corner - 1] = 0.7 if corner != 3 else 1.1  # an der dritten Zelle verrutscht das Gewicht
        await put_weight_on(hass, clock, shares)
        form = await submit(hass, flow_id)
    assert form["type"] is FlowResultType.ABORT
    assert form["reason"] == "calibration_rejected"
    assert not manager.calibrated


async def test_calibration_refuses_when_not_steady(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry, ZERO)  # die Uhr steht still, die Waage ist noch nicht ruhig
    flow_id = await open_menu(hass, entry)
    await pick(hass, flow_id, "calibrate")
    form = await submit(hass, flow_id)
    assert form["type"] is FlowResultType.FORM
    assert form["errors"] == {"base": "not_stable"}


async def test_calibration_refuses_without_cell_values(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry)
    clock.advance(3)
    flow_id = await open_menu(hass, entry)
    await pick(hass, flow_id, "calibrate")
    form = await submit(hass, flow_id)
    assert form["errors"] == {"base": "no_data"}


async def test_calibration_needs_a_load_on_the_plate(hass, clock: Clock) -> None:
    _entry, _manager, flow_id = await start_calibration(hass, clock)
    await submit(hass, flow_id)
    clock.advance(3)
    form = await submit(hass, flow_id, {"weight_g": WEIGHT})  # es liegt nichts auf der Platte
    assert form["type"] is FlowResultType.FORM
    assert form["errors"] == {"base": "no_load"}
    assert form["step_id"] == "calibrate_weight"


async def test_zero_only_is_not_a_calibration(hass, clock: Clock) -> None:
    _entry, manager, flow_id = await start_calibration(hass, clock)
    await submit(hass, flow_id)
    assert not manager.calibrated
    assert manager.calibration.zero == [float(z) for z in ZERO]


async def test_settings_are_saved_and_applied(hass, clock: Clock) -> None:
    entry = station_entry()
    await setup_station(hass, entry, ZERO)
    flow_id = await open_menu(hass, entry)
    form = await pick(hass, flow_id, "settings")
    assert form["step_id"] == "settings"
    result = await submit(hass, flow_id, {"stable_seconds": 4.0, "stable_tolerance_g": 0.5, "occupied_g": 20.0})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert dict(entry.options) == {"stable_seconds": 4.0, "stable_tolerance_g": 0.5, "occupied_g": 20.0}
    assert entry.runtime_data._tracker.seconds == 4.0  # nach dem Neuladen gelten die neuen Werte


async def test_reset_calibration(hass, clock: Clock) -> None:
    entry, manager, flow_id = await start_calibration(hass, clock)
    await manager.async_apply_factors([0.002] * 4)
    flow_id = await open_menu(hass, entry)
    form = await pick(hass, flow_id, "reset_calibration")
    assert form["step_id"] == "reset_calibration"
    result = await submit(hass, flow_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "calibration_reset"
    assert not manager.calibrated
