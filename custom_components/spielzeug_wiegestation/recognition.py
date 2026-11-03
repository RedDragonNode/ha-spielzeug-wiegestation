"""Erkennung, ohne Home Assistant: Welches Spielzeug wurde aufgelegt oder weggenommen?

Ist die Waage ruhig geworden, vergleicht sie ihr Gewicht mit dem der letzten ruhigen Zeit. Der Unterschied ist das, was
dazugekommen oder weggegangen ist. Passt er auf ein angelerntes Spielzeug (Gewicht plus oder minus Toleranz), ist es
dieses. Es zählt nur das Gewicht, nicht die Lage auf der Platte.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .const import MIN_TOLERANCE_G, TOLERANCE_PERCENT, ZERO_TRACK_MAX_G

KIND_PLACED = "placed"
KIND_REMOVED = "removed"


def default_tolerance(weight_g: float) -> float:
    """Toleranz, wenn keine eingetragen ist: 5 % des Gewichts, mindestens 3 g (das Rauschen der Zellen)."""
    return round(max(MIN_TOLERANCE_G, weight_g * TOLERANCE_PERCENT / 100), 1)


@dataclass(frozen=True, slots=True)
class Toy:
    toy_id: str
    name: str
    weight_g: float
    tolerance_g: float

    def matches(self, weight_g: float) -> bool:
        return abs(weight_g - self.weight_g) <= self.tolerance_g

    def overlaps(self, other: Toy) -> bool:
        """Gibt es Gewichte, die zu beiden passen?"""
        return abs(self.weight_g - other.weight_g) <= self.tolerance_g + other.tolerance_g


def match_toy(weight_g: float, toys: Sequence[Toy]) -> Toy | None:
    """Das Spielzeug, dessen Gewicht am nächsten liegt und dessen Toleranz noch passt."""
    fitting = (toy for toy in toys if toy.matches(weight_g))
    return min(fitting, key=lambda toy: abs(weight_g - toy.weight_g), default=None)


@dataclass(slots=True)
class PlateItem:
    """Etwas, das auf der Platte liegt: ein angelerntes Spielzeug (`toy`) oder etwas Unbekanntes."""

    weight_g: float  # so schwer wurde es beim Auflegen gemessen
    toy: Toy | None

    @property
    def tolerance_g(self) -> float:
        return self.toy.tolerance_g if self.toy else default_tolerance(self.weight_g)


@dataclass(frozen=True, slots=True)
class Detection:
    kind: str  # KIND_PLACED oder KIND_REMOVED
    weight_g: float  # gemessene Änderung, immer positiv
    toy: Toy | None  # None: kein angelerntes Spielzeug


class PlateTracker:
    """Merkt sich, was auf der Platte liegt, und meldet jede Änderung, wenn die Waage ruhig geworden ist."""

    def __init__(self) -> None:
        self.reference: float | None = None
        self.items: list[PlateItem] = []

    def reset(self) -> None:
        self.reference = None
        self.items = []

    def rebase(self, weight_g: float) -> None:
        """Der Nullpunkt wurde nachgeführt, das ruhige Gewicht von eben gilt jetzt als `weight_g`."""
        self.reference = weight_g

    def settle(self, weight_g: float, toys: Sequence[Toy], min_g: float) -> list[Detection]:
        """`weight_g` ist das ruhige Gewicht, `min_g` die kleinste Änderung, die als Auflegen oder Wegnehmen zählt."""
        if self.reference is None:
            self.reference = weight_g
            self.items = self._found_on_start(weight_g, toys, min_g)
            return []
        delta = weight_g - self.reference
        detections: list[Detection] = []
        if weight_g < min_g and self.items:  # die Platte ist leer, was noch als aufliegend galt, ist weg
            detections = [Detection(KIND_REMOVED, item.weight_g, item.toy) for item in self.items]
            self.items = []
        elif delta >= min_g:
            toy = match_toy(delta, toys)
            self.items.append(PlateItem(delta, toy))
            detections.append(Detection(KIND_PLACED, delta, toy))
        elif delta <= -min_g:
            item = self._take(-delta)
            toy = item.toy if item else match_toy(-delta, toys)
            detections.append(Detection(KIND_REMOVED, -delta, toy))
        self.reference = weight_g
        return detections

    @staticmethod
    def _found_on_start(weight_g: float, toys: Sequence[Toy], min_g: float) -> list[PlateItem]:
        """Liegt schon etwas auf der Platte, wenn die Erkennung anfängt: ohne Meldung merken, was es sein könnte."""
        if weight_g < min_g:
            return []
        toy = match_toy(weight_g, toys)
        if toy is None and weight_g < ZERO_TRACK_MAX_G:
            return []  # so wenig kann auch ein gewanderter Nullpunkt sein
        return [PlateItem(weight_g, toy)]

    def _take(self, weight_g: float) -> PlateItem | None:
        """Nimmt das aufliegende Teil heraus, das zum weggenommenen Gewicht passt."""
        fitting = [item for item in self.items if abs(item.weight_g - weight_g) <= item.tolerance_g]
        if not fitting:
            return None
        item = min(fitting, key=lambda item: abs(item.weight_g - weight_g))
        self.items.remove(item)
        return item
