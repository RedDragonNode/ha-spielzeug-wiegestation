"""Die Rechnung hinter der Waage, ohne Home Assistant: Eichen, Gewicht, Ruhe.

Jede Zelle liefert einen Rohwert (Zähler des HX711). Das Gewicht der Zelle ist
`faktor * (rohwert - nullpunkt)` in Gramm, das Gewicht der Platte die Summe der vier Zellen
abzüglich der Tara. Der Faktor kann negativ sein, wenn eine Zelle andersherum angeschlossen ist.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .const import CELL_COUNT, MIN_LOAD_COUNTS


class CalibrationError(Exception):
    """Aus den Messungen lässt sich keine Eichung berechnen. `key` ist der Schlüssel des Fehlertexts."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


@dataclass(slots=True)
class Calibration:
    """Nullpunkt und Faktor je Zelle, dazu die Tara in Gramm."""

    zero: list[float] = field(default_factory=lambda: [0.0] * CELL_COUNT)
    factor: list[float] = field(default_factory=lambda: [1.0] * CELL_COUNT)
    tare_g: float = 0.0
    calibrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"zero": self.zero, "factor": self.factor, "tare_g": self.tare_g, "calibrated": self.calibrated}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Calibration:
        """Liest gespeicherte Werte, ein kaputter oder fremder Stand ergibt eine ungeeichte Waage."""
        try:
            zero = [float(v) for v in data["zero"]]  # type: ignore[index]
            factor = [float(v) for v in data["factor"]]  # type: ignore[index]
            if len(zero) != CELL_COUNT or len(factor) != CELL_COUNT:
                raise ValueError
            return cls(zero, factor, float(data.get("tare_g", 0.0)), bool(data.get("calibrated")))  # type: ignore[union-attr]
        except (KeyError, TypeError, ValueError):
            return cls()


def cell_weights(cal: Calibration, raws: Sequence[float]) -> list[float]:
    """Gewicht jeder Zelle in Gramm, ohne Tara."""
    return [f * (r - z) for f, r, z in zip(cal.factor, raws, cal.zero, strict=True)]


def gross_weight(cal: Calibration, raws: Sequence[float]) -> float:
    """Gewicht auf der Platte in Gramm, ohne Tara."""
    return sum(cell_weights(cal, raws))


def net_weight(cal: Calibration, raws: Sequence[float]) -> float:
    """Gewicht in Gramm nach Abzug der Tara."""
    return gross_weight(cal, raws) - cal.tare_g


def deltas(cal: Calibration, raws: Sequence[float]) -> list[float]:
    """Änderung der Rohwerte gegenüber dem Nullpunkt, je Zelle."""
    return [r - z for r, z in zip(raws, cal.zero, strict=True)]


def same_direction(delta: Sequence[float]) -> bool:
    """Reagieren alle belasteten Zellen in dieselbe Richtung? Sonst ist eine Zelle andersherum angeschlossen."""
    largest = max(abs(v) for v in delta)
    big = [d for d in delta if abs(d) >= 0.1 * largest]
    return all(d >= 0 for d in big) or all(d <= 0 for d in big)


def common_factor(delta: Sequence[float], weight_g: float) -> float:
    """Ein Faktor für alle vier Zellen aus einem Gewicht, das in der Mitte der Platte liegt."""
    total = sum(delta)
    if abs(total) < MIN_LOAD_COUNTS or weight_g <= 0:
        raise CalibrationError("no_load")
    if not same_direction(delta):
        raise CalibrationError("mixed_signs")
    return weight_g / total


def fit_factors(observations: Sequence[tuple[Sequence[float], float]]) -> list[float]:
    """Faktor je Zelle aus mehreren Messungen (Änderung der Rohwerte je Zelle, aufgelegtes Gewicht).

    Kleinste Quadrate über `sum(faktor_i * delta_i) = gewicht`. Die Messungen müssen die Last verschieden auf die Zellen
    verteilen, zum Beispiel Mitte und je ein Gewicht über jeder Zelle.
    """
    if len(observations) < CELL_COUNT:
        raise CalibrationError("not_enough_positions")
    # Normalgleichungen: (D^T D) f = D^T w, dazu auf eine ähnliche Größe skaliert, damit der Pivot vergleichbar bleibt
    scale = max(abs(v) for delta, _ in observations for v in delta) or 1.0
    matrix = [[0.0] * CELL_COUNT for _ in range(CELL_COUNT)]
    vector = [0.0] * CELL_COUNT
    for delta, weight in observations:
        scaled = [v / scale for v in delta]
        for i in range(CELL_COUNT):
            vector[i] += scaled[i] * weight
            for j in range(CELL_COUNT):
                matrix[i][j] += scaled[i] * scaled[j]
    solved = _solve(matrix, vector)
    return [value / scale for value in solved]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gauß-Verfahren mit Spaltenpivot für ein kleines Gleichungssystem."""
    size = len(vector)
    rows = [[*matrix[i], vector[i]] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-9:
            raise CalibrationError("not_enough_positions")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(col + 1, size):
            ratio = rows[r][col] / rows[col][col]
            for c in range(col, size + 1):
                rows[r][c] -= ratio * rows[col][c]
    result = [0.0] * size
    for r in range(size - 1, -1, -1):
        result[r] = (rows[r][size] - sum(rows[r][c] * result[c] for c in range(r + 1, size))) / rows[r][r]
    return result


def fit_error_percent(factors: Sequence[float], observations: Sequence[tuple[Sequence[float], float]]) -> float:
    """Größte Abweichung der Eichung von den aufgelegten Gewichten, in Prozent des jeweiligen Gewichts."""
    worst = 0.0
    for delta, weight in observations:
        predicted = sum(f * d for f, d in zip(factors, delta, strict=True))
        worst = max(worst, abs(predicted - weight) / weight * 100)
    return worst


class StabilityTracker:
    """Sagt, ob das Gewicht ruhig ist: In den letzten `seconds` Sekunden schwankte es höchstens um `tolerance`.

    Die Zellen melden nur, wenn sich etwas ändert. Der letzte Wert gilt darum weiter, bis ein neuer kommt.
    """

    def __init__(self, seconds: float, tolerance: float) -> None:
        self.seconds = seconds
        self.tolerance = tolerance
        self._samples: deque[tuple[float, float]] = deque()

    def reset(self) -> None:
        self._samples.clear()

    def add(self, now: float, value: float) -> None:
        self._samples.append((now, value))
        self._prune(now)

    def _prune(self, now: float) -> None:
        """Alles vor dem letzten Wert, der das Fenster eröffnet, wird nicht mehr gebraucht."""
        start = now - self.seconds
        while len(self._samples) >= 2 and self._samples[1][0] <= start:
            self._samples.popleft()

    def stable(self, now: float) -> bool:
        if not self._samples:
            return False
        self._prune(now)
        start = now - self.seconds
        if self._samples[0][0] > start:
            return False  # wir beobachten noch nicht lange genug
        values = [value for _, value in self._samples]
        return max(values) - min(values) <= self.tolerance
