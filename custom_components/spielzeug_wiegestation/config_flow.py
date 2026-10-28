"""Config-Flow (die vier Zellen wählen) und Optionen (Eichen, Tara, Schwellen)."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from . import scale
from .const import (
    CELL_COUNT,
    CONF_CELLS,
    CONF_NAME,
    DEFAULT_OCCUPIED,
    DEFAULT_STABLE_SECONDS,
    DEFAULT_STABLE_TOLERANCE,
    DOMAIN,
    FIELD_CELL,
    MAX_FIT_ERROR_PERCENT,
    MINOR_VERSION,
    OPT_OCCUPIED,
    OPT_STABLE_SECONDS,
    OPT_STABLE_TOLERANCE,
)
from .manager import StationManager

DEFAULT_TITLE = "Spielzeug Wiegestation"
FIELD_WEIGHT = "weight_g"

_CELL_NAME = re.compile(r"Zelle (\d)")


def suggest_cells(hass: HomeAssistant) -> dict[str, str]:
    """Findet die vier Rohwert-Sensoren „Zelle 1“ bis „Zelle 4“ eines ESPHome-Geräts und schlägt sie vor."""
    by_device: dict[str | None, dict[int, str]] = {}
    for entry in er.async_get(hass).entities.values():
        if entry.platform != "esphome" or entry.domain != "sensor" or entry.disabled:
            continue
        match = _CELL_NAME.fullmatch((entry.name or entry.original_name or "").strip())
        if match:
            by_device.setdefault(entry.device_id, {})[int(match.group(1))] = entry.entity_id
    for cells in by_device.values():
        if all(number in cells for number in range(1, CELL_COUNT + 1)):
            return {f"{FIELD_CELL}{number}": cells[number] for number in range(1, CELL_COUNT + 1)}
    return {}


def _cells_schema(with_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=DEFAULT_TITLE)] = selector.TextSelector()
    for number in range(1, CELL_COUNT + 1):
        fields[vol.Required(f"{FIELD_CELL}{number}")] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )
    return vol.Schema(fields)


def _cells_of(user_input: dict[str, Any]) -> list[str]:
    return [user_input[f"{FIELD_CELL}{number}"] for number in range(1, CELL_COUNT + 1)]


class WiegestationConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = MINOR_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cells = _cells_of(user_input)
            if len(set(cells)) != CELL_COUNT:
                errors["base"] = "duplicate_cells"
            else:
                await self.async_set_unique_id("|".join(cells))
                self._abort_if_unique_id_configured()
                title = (user_input.get(CONF_NAME) or "").strip() or DEFAULT_TITLE
                return self.async_create_entry(title=title, data={CONF_CELLS: cells})
        suggested = user_input or suggest_cells(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_cells_schema(with_name=True), suggested),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            cells = _cells_of(user_input)
            if len(set(cells)) != CELL_COUNT:
                errors["base"] = "duplicate_cells"
            else:
                return self.async_update_reload_and_abort(
                    entry, unique_id="|".join(cells), data_updates={CONF_CELLS: cells}
                )
        suggested = user_input or {
            f"{FIELD_CELL}{number}": entity_id for number, entity_id in enumerate(entry.data[CONF_CELLS], start=1)
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(_cells_schema(with_name=False), suggested),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WiegestationOptionsFlow:
        return WiegestationOptionsFlow()


def _number(low: float, high: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low, max=high, step=step, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit
        )
    )


class WiegestationOptionsFlow(OptionsFlowWithReload):
    """Menü: Eichen, Schwellen, Eichung zurücksetzen.

    Beim Eichen kommt zuerst die leere Platte (Nullpunkt), dann ein bekanntes Gewicht in der Mitte. Das reicht für einen
    gemeinsamen Faktor. Wer es genauer will, legt dasselbe Gewicht danach über jede der vier Zellen, daraus berechnet
    die Integration den Faktor jeder Zelle einzeln.
    """

    def __init__(self) -> None:
        self._observations: list[tuple[list[float], float]] = []
        self._weight = 0.0

    @property
    def manager(self) -> StationManager | None:
        return getattr(self.config_entry, "runtime_data", None)

    def _not_ready(self) -> str | None:
        """Schlüssel des Fehlers, wenn gerade nicht gemessen werden kann."""
        manager = self.manager
        if manager is None or not manager.available:
            return "no_data"
        if not manager.stable:
            return "not_stable"
        return None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        return self.async_show_menu(step_id="init", menu_options=["calibrate", "settings", "reset_calibration"])

    # ------------------------------------------------------------- Schwellen
    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(OPT_STABLE_SECONDS): _number(0.5, 30, 0.5, "s"),
                vol.Required(OPT_STABLE_TOLERANCE): _number(0.1, 100, 0.1, "g"),
                vol.Required(OPT_OCCUPIED): _number(0.5, 5000, 0.5, "g"),
            }
        )
        suggested = {
            OPT_STABLE_SECONDS: options.get(OPT_STABLE_SECONDS, DEFAULT_STABLE_SECONDS),
            OPT_STABLE_TOLERANCE: options.get(OPT_STABLE_TOLERANCE, DEFAULT_STABLE_TOLERANCE),
            OPT_OCCUPIED: options.get(OPT_OCCUPIED, DEFAULT_OCCUPIED),
        }
        return self.async_show_form(
            step_id="settings", data_schema=self.add_suggested_values_to_schema(schema, suggested)
        )

    # ------------------------------------------------------------- Zurücksetzen
    async def async_step_reset_calibration(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            if self.manager:
                await self.manager.async_reset_calibration()
            return self.async_abort(reason="calibration_reset")
        return self.async_show_form(step_id="reset_calibration", data_schema=vol.Schema({}))

    # ------------------------------------------------------------- Eichen
    async def async_step_calibrate(self, user_input: dict[str, Any] | None = None) -> Any:
        """Schritt 1: leere Platte, merkt sich den Nullpunkt."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := self._not_ready():
                errors["base"] = error
            else:
                assert self.manager is not None
                await self.manager.async_set_zero()
                self._observations = []
                return await self.async_step_calibrate_weight()
        return self.async_show_form(step_id="calibrate", data_schema=vol.Schema({}), errors=errors)

    async def async_step_calibrate_weight(self, user_input: dict[str, Any] | None = None) -> Any:
        """Schritt 2: ein bekanntes Gewicht in der Mitte der Platte."""
        errors: dict[str, str] = {}
        if user_input is not None:
            weight = float(user_input[FIELD_WEIGHT])
            if error := self._not_ready():
                errors["base"] = error
            else:
                assert self.manager is not None
                delta = self.manager.observe()
                try:
                    scale.common_factor(delta, weight)
                except scale.CalibrationError as err:
                    if err.key != "mixed_signs":
                        errors["base"] = err.key
                    else:  # eine Zelle ist andersherum angeschlossen: nur mit der Messung über jeder Zelle zu eichen
                        self._weight = weight
                        self._observations = [(delta, weight)]
                        return await self.async_step_calibrate_signs()
                else:
                    self._weight = weight
                    self._observations = [(delta, weight)]
                    return await self.async_step_calibrate_more()
        schema = vol.Schema({vol.Required(FIELD_WEIGHT): _number(1, 20000, 0.1, "g")})
        return self.async_show_form(
            step_id="calibrate_weight",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {FIELD_WEIGHT: self._weight or 500}),
            errors=errors,
        )

    async def async_step_calibrate_signs(self, user_input: dict[str, Any] | None = None) -> Any:
        """Eine Zelle zeigt in die andere Richtung. Das ist kein Fehler, verlangt aber die Messung über jeder Zelle."""
        if user_input is not None:
            return await self.async_step_calibrate_corner()
        return self.async_show_form(step_id="calibrate_signs", data_schema=vol.Schema({}))

    async def async_step_calibrate_more(self, user_input: dict[str, Any] | None = None) -> Any:
        return self.async_show_menu(step_id="calibrate_more", menu_options=["calibrate_corner", "calibrate_done"])

    async def async_step_calibrate_done(self, user_input: dict[str, Any] | None = None) -> Any:
        """Nur die Mitte gemessen: ein Faktor für alle Zellen."""
        assert self.manager is not None
        delta, weight = self._observations[0]
        factor = scale.common_factor(delta, weight)
        await self.manager.async_apply_factors([factor] * CELL_COUNT)
        return self.async_abort(reason="calibration_saved_center")

    async def async_step_calibrate_corner(self, user_input: dict[str, Any] | None = None) -> Any:
        """Je Zelle ein Gewicht direkt darüber. Nach der vierten Zelle wird gerechnet."""
        corner = len(self._observations)  # 1 bis 4, die Mitte war die Messung davor
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := self._not_ready():
                errors["base"] = error
            else:
                assert self.manager is not None
                self._observations.append((self.manager.observe(), self._weight))
                if len(self._observations) > CELL_COUNT:
                    return await self._finish_fit()
                corner = len(self._observations)
        return self.async_show_form(
            step_id="calibrate_corner",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"corner": str(corner), "weight": f"{self._weight:g}"},
        )

    async def _finish_fit(self) -> Any:
        assert self.manager is not None
        try:
            factors = scale.fit_factors(self._observations)
        except scale.CalibrationError as err:
            return self.async_abort(reason=err.key)
        error = scale.fit_error_percent(factors, self._observations)
        if error > MAX_FIT_ERROR_PERCENT:
            return self.async_abort(reason="calibration_rejected", description_placeholders={"details": f"{error:.1f}"})
        await self.manager.async_apply_factors(factors)
        return self.async_abort(reason="calibration_saved", description_placeholders={"details": f"{error:.2f}"})
