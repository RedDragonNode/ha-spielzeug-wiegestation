"""Der Zustand einer Wiegestation: liest die vier Zellen, rechnet das Gewicht und merkt sich die Eichung."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from time import monotonic as _now

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store

from . import scale
from .const import (
    CONF_CELLS,
    CONF_DESCRIPTION,
    CONF_TAUGHT,
    CONF_THREAD,
    CONF_TOLERANCE,
    CONF_WEIGHT,
    DEFAULT_OCCUPIED,
    DEFAULT_STABLE_SECONDS,
    DEFAULT_STABLE_TOLERANCE,
    DOMAIN,
    EVENT_TOY_CHANGED,
    EVENT_TOY_DELETED,
    EVENT_TOY_PLACED,
    EVENT_TOY_REMOVED,
    EVENT_TOY_TAUGHT,
    EVENT_UNKNOWN_PLACED,
    EVENT_UNKNOWN_REMOVED,
    OCCUPIED_RELEASE,
    OPT_OCCUPIED,
    OPT_STABLE_SECONDS,
    OPT_STABLE_TOLERANCE,
    SETTLE_INTERVAL,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_TOY,
    ZERO_TRACK_MAX_G,
    ZERO_TRACK_MIN_G,
    ZERO_TRACK_SAVE_DELAY,
)
from .recognition import KIND_PLACED, Detection, PlateItem, PlateTracker, Toy

_LOGGER = logging.getLogger(__name__)

# Solange nicht geeicht ist, rechnet die Waage mit einem Richtwert (etwa 430 Zähler je Gramm bei einer 5-kg-Zelle an
# 3,3 V), damit „ruhig“ schon beim Eichen taugt. Das Gewicht selbst zeigt sie erst nach dem Eichen.
PROVISIONAL_FACTOR = 1 / 430


def calibration_store(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")


def toys_of(entry: ConfigEntry) -> list[Toy]:
    """Die angelernten Spielzeuge: ein Untereintrag je Spielzeug."""
    return [
        Toy(sub.subentry_id, sub.title, float(sub.data[CONF_WEIGHT]), float(sub.data[CONF_TOLERANCE]))
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TOY
    ]


def toy_card(entry: ConfigEntry, subentry: ConfigSubentry) -> dict[str, object]:
    """Der Steckbrief eines Spielzeugs: so steht er in den Ereignissen zum Anlernen, Ändern und Löschen."""
    data = subentry.data
    return {
        "entry_id": entry.entry_id,
        "station": entry.title,
        "toy": subentry.title,
        "toy_id": subentry.subentry_id,
        "weight": float(data[CONF_WEIGHT]),
        "tolerance": float(data[CONF_TOLERANCE]),
        "description": str(data.get(CONF_DESCRIPTION, "")),
        "taught_at": str(data.get(CONF_TAUGHT, "")),
        "thread_id": str(data.get(CONF_THREAD, "")),
    }


def cards_of(entry: ConfigEntry) -> dict[str, dict[str, object]]:
    return {
        sub.subentry_id: toy_card(entry, sub) for sub in entry.subentries.values() if sub.subentry_type == SUBENTRY_TOY
    }


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
        self._shown: float | None = None
        self._settled = False  # die Anzeige steht schon auf dem Mittelwert der ruhigen Zeit
        self.toys = toys_of(entry)
        self.cards = cards_of(entry)  # Steckbriefe, so wie sie zuletzt gemeldet wurden
        self.options = dict(entry.options)  # so war die Waage eingestellt, als sie geladen wurde
        self._plate = PlateTracker()
        self._was_stable = False
        self._last_settle = 0.0
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

    @property
    def display_weight(self) -> float | None:
        """Das Gewicht, das der Sensor zeigt: bleibt stehen, solange es nur um das Rauschen schwankt."""
        return self._shown

    @property
    def settled_weight(self) -> float | None:
        """Das Gewicht, wenn die Waage ruhig und geeicht ist (Mittel der ruhigen Zeit), sonst `None`."""
        if not self.calibrated or not self.stable:
            return None
        return self._tracker.mean(_now())

    @property
    def plate_items(self) -> list[PlateItem]:
        """Was nach der Erkennung auf der Platte liegt."""
        return list(self._plate.items)

    @property
    def present_toy_ids(self) -> set[str]:
        return {item.toy.toy_id for item in self._plate.items if item.toy}

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
            self._check_settled()
            self._update_occupied()
            self._schedule_recheck()
        self._update_shown()
        self._notify()

    def _check_settled(self) -> None:
        """Ist die Waage eben ruhig geworden? Dann ist es Zeit zu erkennen, was sich auf der Platte geändert hat.

        Bleibt sie ruhig, wird trotzdem alle paar Sekunden nachgesehen: Die leere Platte kriecht langsam und bleibt
        dabei ruhig, der Nullpunkt muss aber mitwandern.
        """
        stable = self.stable
        now = _now()
        if stable and (not self._was_stable or now - self._last_settle >= SETTLE_INTERVAL):
            self._last_settle = now
            self._settle()
        self._was_stable = stable

    def _settle(self) -> None:
        if not self.calibrated:
            return
        weight = self._tracker.mean(_now())
        for detection in self._plate.settle(weight, self.toys, self._occupied_g):
            self._fire(detection, weight)
        if not self._plate.items and ZERO_TRACK_MIN_G <= abs(weight) <= ZERO_TRACK_MAX_G:
            self._track_zero(weight)

    def _track_zero(self, weight: float) -> None:
        """Die Platte ist leer und zeigt trotzdem ein paar Gramm (Kriechen, Feuchte): der Nullpunkt wandert mit."""
        self.calibration.tare_g += weight
        self._store.async_delay_save(self.calibration.to_dict, ZERO_TRACK_SAVE_DELAY)
        self._tracker.reset()
        self._reset_shown()
        self._plate.rebase(0.0)
        self._was_stable = False

    def _fire(self, detection: Detection, total: float) -> None:
        placed = detection.kind == KIND_PLACED
        if detection.toy:
            event = EVENT_TOY_PLACED if placed else EVENT_TOY_REMOVED
        else:
            event = EVENT_UNKNOWN_PLACED if placed else EVENT_UNKNOWN_REMOVED
        data: dict[str, object] = {
            "entry_id": self.entry.entry_id,
            "station": self.entry.title,
            "weight": round(detection.weight_g, 1),
            "total": round(total, 1),
        }
        if detection.toy:
            data["toy"] = detection.toy.name
            data["toy_id"] = detection.toy.toy_id
            data["thread_id"] = self.cards.get(detection.toy.toy_id, {}).get("thread_id", "")
        self.hass.bus.async_fire(event, data)

    @callback
    def async_update_toys(self) -> bool:
        """Spielzeuge wurden angelernt, geändert oder gelöscht: meldet es und sagt, ob die Erkennung neu laden muss.

        Eine Änderung der Beschreibung oder des Threads ändert nur den Steckbrief, die Erkennung läuft weiter.
        """
        new = cards_of(self.entry)
        for toy_id, card in new.items():
            old = self.cards.get(toy_id)
            if old is None:
                self.hass.bus.async_fire(EVENT_TOY_TAUGHT, card)
            elif {key: value for key, value in old.items() if key != "thread_id"} != {
                key: value for key, value in card.items() if key != "thread_id"
            }:
                self.hass.bus.async_fire(EVENT_TOY_CHANGED, card)
        for toy_id, card in self.cards.items():
            if toy_id not in new:
                self.hass.bus.async_fire(EVENT_TOY_DELETED, card)
        self.cards = new
        self._notify()
        return toys_of(self.entry) != self.toys

    def _update_shown(self) -> None:
        """Das gezeigte Gewicht folgt erst, wenn es sich um mehr als die Toleranz bewegt hat.

        Ohne das schriebe der Sensor bei jedem Rauschen des HX711 (etwa ein Gramm) einen neuen Wert in die Datenbank.
        Die Zellen melden einzeln, das Gewicht läuft also über Teilsummen. Wird die Waage ruhig, setzt sich die Anzeige
        darum einmal auf den Mittelwert der ruhigen Zeit.
        """
        weight = self.weight
        if weight is None:
            self._reset_shown()
        elif self._shown is None or abs(weight - self._shown) >= self._tracker.tolerance:
            self._shown = weight
            self._settled = False
        elif not self.stable:
            self._settled = False
        elif not self._settled:
            self._shown = self._tracker.mean(_now())
            self._settled = True

    def _reset_shown(self) -> None:
        self._shown = None
        self._settled = False

    def _reset_plate(self) -> None:
        self._plate.reset()
        self._was_stable = False

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
        self._check_settled()
        self._update_occupied()
        self._update_shown()
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
        self._reset_shown()  # nach der Tara zeigt der Sensor sofort null
        self._reset_plate()
        self._refresh()

    async def async_set_zero(self) -> None:
        """Leere Platte: merkt sich die Rohwerte als Nullpunkt. Die Eichung gilt danach als neu zu machen."""
        raws = self._require_raws()
        self.calibration = scale.Calibration(zero=list(raws), factor=list(self.calibration.factor), calibrated=False)
        await self._save()
        self._tracker.reset()
        self._reset_shown()
        self._reset_plate()
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
        self._reset_shown()
        self._reset_plate()
        self._refresh()

    async def async_reset_calibration(self) -> None:
        self.calibration = scale.Calibration()
        await self._save()
        self._tracker.reset()
        self._reset_shown()
        self._reset_plate()
        self._refresh()
