"""Der Zustand einer Wiegestation: liest die vier Zellen, rechnet das Gewicht und merkt sich die Eichung."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from time import monotonic as _now

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store

from . import scale
from .const import (
    CONF_CELLS,
    DEFAULT_OCCUPIED,
    DEFAULT_STABLE_SECONDS,
    DEFAULT_STABLE_TOLERANCE,
    DOMAIN,
    OCCUPIED_RELEASE,
    OPT_OCCUPIED,
    OPT_STABLE_SECONDS,
    OPT_STABLE_TOLERANCE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

# Solange nicht geeicht ist, rechnet die Waage mit einem Richtwert (etwa 430 Zähler je Gramm bei einer 5-kg-Zelle an
# 3,3 V), damit „ruhig“ schon beim Eichen taugt. Das Gewicht selbst zeigt sie erst nach dem Eichen.
PROVISIONAL_FACTOR = 1 / 430


def calibration_store(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")


class StationManager:
    """Hält Eichung und aktuelle Werte und meldet Änderungen an die Entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.cells: list[str] = list(entry.data[CONF_CELLS])
        self.signal = f"{DOMAIN}_{entry.entry_id}_update"
        self.calibration = scale.Calibration()
        self.raws: list[float] | None = None
        self._store = calibration_store(hass, entry.entry_id)
        self._tracker = scale.StabilityTracker(
            float(entry.options.get(OPT_STABLE_SECONDS, DEFAULT_STABLE_SECONDS)),
            float(entry.options.get(OPT_STABLE_TOLERANCE, DEFAULT_STABLE_TOLERANCE)),
        )
        self._occupied_g = float(entry.options.get(OPT_OCCUPIED, DEFAULT_OCCUPIED))
        self._occupied = False
        self._cancel_recheck: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------- Laden, Starten, Stoppen
    async def async_load(self) -> None:
        self.calibration = scale.Calibration.from_dict(await self._store.async_load())

    @callback
    def async_start(self) -> None:
        self.entry.async_on_unload(async_track_state_change_event(self.hass, self.cells, self._on_cell_change))
        self.entry.async_on_unload(self._stop)
        self._refresh()

    @callback
    def _stop(self) -> None:
        if self._cancel_recheck:
            self._cancel_recheck()
            self._cancel_recheck = None

    async def _save(self) -> None:
        await self._store.async_save(self.calibration.to_dict())

    async def async_remove_storage(self) -> None:
        await self._store.async_remove()

    # ------------------------------------------------------------- Werte
    @property
    def available(self) -> bool:
        return self.raws is not None

    @property
    def calibrated(self) -> bool:
        return self.calibration.calibrated

    def _provisional(self) -> scale.Calibration:
        """Die Eichung, mit der gerechnet wird: die echte oder, solange es keine gibt, der Richtwert."""
        if self.calibration.calibrated:
            return self.calibration
        return scale.Calibration(
            zero=self.calibration.zero, factor=[PROVISIONAL_FACTOR] * len(self.cells), tare_g=self.calibration.tare_g
        )

    @property
    def weight(self) -> float | None:
        """Gewicht in Gramm nach Tara, `None` bis zum Eichen."""
        if self.raws is None or not self.calibrated:
            return None
        return scale.net_weight(self.calibration, self.raws)

    def cell_weight(self, index: int) -> float | None:
        if self.raws is None or not self.calibrated:
            return None
        return scale.cell_weights(self.calibration, self.raws)[index]

    @property
    def stable(self) -> bool:
        return self.raws is not None and self._tracker.stable(_now())

    @property
    def occupied(self) -> bool:
        return self._occupied

    def _read_raws(self) -> list[float] | None:
        values: list[float] = []
        for entity_id in self.cells:
            state = self.hass.states.get(entity_id)
            try:
                values.append(float(state.state))  # type: ignore[union-attr]
            except (AttributeError, TypeError, ValueError):
                return None  # fehlt, nicht verfügbar oder unbekannt
        return values

    @callback
    def _on_cell_change(self, event: Event[EventStateChangedData]) -> None:
        self._refresh()

    @callback
    def _refresh(self) -> None:
        self.raws = self._read_raws()
        if self.raws is None:
            self._tracker.reset()
        else:
            self._tracker.add(_now(), scale.net_weight(self._provisional(), self.raws))
            self._update_occupied()
            self._schedule_recheck()
        self._notify()

    def _update_occupied(self) -> None:
        weight = self.weight
        if weight is None:
            self._occupied = False
        elif self._occupied:
            self._occupied = weight > self._occupied_g * OCCUPIED_RELEASE
        else:
            self._occupied = weight >= self._occupied_g

    def _schedule_recheck(self) -> None:
        """„Ruhig“ ändert sich mit der Zeit, auch wenn keine Zelle etwas meldet, darum folgt später eine Prüfung."""
        if self._cancel_recheck:
            self._cancel_recheck()
        self._cancel_recheck = async_call_later(self.hass, self._tracker.seconds + 0.1, self._recheck)

    @callback
    def _recheck(self, _now_utc: object) -> None:
        self._cancel_recheck = None
        self._notify()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal)

    # ------------------------------------------------------------- Tara und Eichen
    def _require_raws(self) -> list[float]:
        if self.raws is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_data")
        return self.raws

    async def async_tare(self) -> None:
        """Setzt das Gewicht auf der Platte jetzt auf null."""
        raws = self._require_raws()
        if not self.calibrated:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_calibrated")
        self.calibration.tare_g = scale.gross_weight(self.calibration, raws)
        await self._save()
        self._refresh()

    async def async_set_zero(self) -> None:
        """Leere Platte: merkt sich die Rohwerte als Nullpunkt. Die Eichung gilt danach als neu zu machen."""
        raws = self._require_raws()
        self.calibration = scale.Calibration(zero=list(raws), factor=list(self.calibration.factor), calibrated=False)
        await self._save()
        self._tracker.reset()
        self._refresh()

    def observe(self) -> list[float]:
        """Änderung der Rohwerte seit dem Nullpunkt je Zelle, für eine Eichmessung."""
        return scale.deltas(self.calibration, self._require_raws())

    async def async_apply_factors(self, factors: Sequence[float]) -> None:
        """Speichert die Faktoren, die Waage gilt danach als geeicht, die Tara ist null."""
        self.calibration.factor = list(factors)
        self.calibration.calibrated = True
        self.calibration.tare_g = 0.0
        await self._save()
        self._tracker.reset()
        self._refresh()

    async def async_reset_calibration(self) -> None:
        self.calibration = scale.Calibration()
        await self._save()
        self._tracker.reset()
        self._refresh()
