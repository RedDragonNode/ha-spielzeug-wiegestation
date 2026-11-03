"""Spielzeug anlernen: Name, Gewicht und Toleranz, ein Untereintrag je Spielzeug."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import CONF_TOLERANCE, CONF_WEIGHT, DEFAULT_OCCUPIED, OPT_OCCUPIED
from .manager import toys_of
from .recognition import Toy, default_tolerance


def _number(low: float, high: float, step: float) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=low, max=high, step=step, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="g"
        )
    )


class ToyFlow(ConfigSubentryFlow):
    """Das Spielzeug auf die Waage legen, warten, bis sie ruhig ist, und einen Namen geben: das Gewicht ist schon da."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._async_toy_form("user", user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._async_toy_form("reconfigure", user_input)

    async def _async_toy_form(self, step_id: str, user_input: dict[str, Any] | None) -> SubentryFlowResult:
        entry = self._get_entry()
        own = self._get_reconfigure_subentry() if step_id == "reconfigure" else None
        min_g = float(entry.options.get(OPT_OCCUPIED, DEFAULT_OCCUPIED))
        manager = getattr(entry, "runtime_data", None)
        measured = manager.settled_weight if manager else None
        errors: dict[str, str] = {}
        placeholders = {"current": "–" if measured is None else f"{measured:.1f}", "min": f"{min_g:g}", "other": ""}

        if user_input is not None:
            name = str(user_input.get(CONF_NAME, "")).strip()
            weight = float(user_input[CONF_WEIGHT])
            tolerance = float(user_input.get(CONF_TOLERANCE) or default_tolerance(weight))
            others = [toy for toy in toys_of(entry) if own is None or toy.toy_id != own.subentry_id]
            overlapping = next((toy for toy in others if Toy("", name, weight, tolerance).overlaps(toy)), None)
            if not name:
                errors[CONF_NAME] = "name_missing"
            elif any(toy.name.casefold() == name.casefold() for toy in others):
                errors[CONF_NAME] = "name_exists"
            elif weight < min_g:
                errors[CONF_WEIGHT] = "too_light"
            elif overlapping:
                errors["base"] = "overlap"
                placeholders["other"] = overlapping.name
            else:
                data = {CONF_WEIGHT: weight, CONF_TOLERANCE: tolerance}
                if own is None:
                    return self.async_create_entry(title=name, data=data)
                return self.async_update_and_abort(entry, own, title=name, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_WEIGHT): _number(0.5, 20000, 0.1),
                vol.Optional(CONF_TOLERANCE): _number(0.5, 5000, 0.1),
            }
        )
        if user_input is not None:
            suggested: dict[str, Any] = dict(user_input)
        elif own is not None:
            suggested = {CONF_NAME: own.title, **own.data}
        else:
            suggested = {} if measured is None else {CONF_WEIGHT: round(measured, 1)}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )
