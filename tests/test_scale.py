"""Die Rechnung hinter der Waage: Gewicht, Eichen, Ruhe."""

from __future__ import annotations

import pytest

from custom_components.spielzeug_wiegestation import scale
from custom_components.spielzeug_wiegestation.scale import Calibration, CalibrationError, StabilityTracker

TRUE_FACTORS = [0.0023, 0.0021, 0.0025, -0.0022]  # g je Zähler, die vierte Zelle ist andersherum angeschlossen
SHARES = [  # Anteil des Gewichts, den jede Zelle trägt: Mitte, dann je ein Gewicht über jeder Zelle
    [0.25, 0.25, 0.25, 0.25],
    [0.7, 0.1, 0.1, 0.1],
    [0.1, 0.7, 0.1, 0.1],
    [0.1, 0.1, 0.7, 0.1],
    [0.1, 0.1, 0.1, 0.7],
]


def observations(weight: float = 500.0) -> list[tuple[list[float], float]]:
    """Messwerte, wie sie eine Waage mit den echten Faktoren liefern würde."""
    return [([share * weight / f for share, f in zip(row, TRUE_FACTORS, strict=True)], weight) for row in SHARES]


def test_calibration_roundtrip() -> None:
    cal = Calibration(zero=[1.0, 2.0, 3.0, 4.0], factor=[0.1, 0.2, 0.3, 0.4], tare_g=12.5, calibrated=True)
    assert Calibration.from_dict(cal.to_dict()) == cal


@pytest.mark.parametrize(
    "stored",
    [
        None,
        {},
        {"zero": [1, 2], "factor": [1, 2]},
        {"zero": "x", "factor": "y"},
        {"zero": [1] * 4, "factor": [None] * 4},
    ],
)
def test_broken_storage_means_not_calibrated(stored) -> None:
    cal = Calibration.from_dict(stored)
    assert not cal.calibrated
    assert cal.tare_g == 0.0


def test_weights_use_zero_factor_and_tare() -> None:
    cal = Calibration(zero=[100, 200, 300, 400], factor=[0.5, 1.0, 2.0, -1.0], tare_g=10.0, calibrated=True)
    raws = [110, 230, 305, 380]
    assert scale.cell_weights(cal, raws) == [5.0, 30.0, 10.0, 20.0]
    assert scale.gross_weight(cal, raws) == 65.0
    assert scale.net_weight(cal, raws) == 55.0
    assert scale.deltas(cal, raws) == [10, 30, 5, -20]


def test_common_factor() -> None:
    assert scale.common_factor([1000, 1000, 1000, 1000], 100.0) == pytest.approx(0.025)


@pytest.mark.parametrize("delta", [[0, 0, 0, 0], [10, 10, 10, 10], [500, -500, 0, 0]])
def test_common_factor_needs_a_load(delta) -> None:
    with pytest.raises(CalibrationError) as err:
        scale.common_factor(delta, 500.0)
    assert err.value.key == "no_load"


def test_common_factor_refuses_a_cell_that_points_the_other_way() -> None:
    with pytest.raises(CalibrationError) as err:
        scale.common_factor([100000, 98000, 101000, -99000], 500.0)
    assert err.value.key == "mixed_signs"


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ([1000, 1100, 900, 1050], True),
        ([-1000, -1100, -900, -1050], True),
        ([1000, 1100, 900, -1050], False),
        ([1000, 1100, 900, 20], True),  # eine Zelle ohne Last zählt nicht
        ([1000, 1100, 900, -20], True),
    ],
)
def test_same_direction(delta, expected) -> None:
    assert scale.same_direction(delta) is expected


def test_fit_recovers_the_factors_of_every_cell_including_a_reversed_one() -> None:
    factors = scale.fit_factors(observations())
    assert factors == pytest.approx(TRUE_FACTORS, rel=1e-6)
    assert scale.fit_error_percent(factors, observations()) < 1e-6


def test_fit_with_noise_stays_close() -> None:
    noisy = [
        ([v * (1 + 0.004 * ((i + j) % 3 - 1)) for j, v in enumerate(delta)], w)
        for i, (delta, w) in enumerate(observations())
    ]
    factors = scale.fit_factors(noisy)
    assert factors == pytest.approx(TRUE_FACTORS, rel=0.05)
    assert scale.fit_error_percent(factors, noisy) < 1.0


def test_fit_needs_four_positions() -> None:
    with pytest.raises(CalibrationError) as err:
        scale.fit_factors(observations()[:3])
    assert err.value.key == "not_enough_positions"


def test_fit_rejects_identical_positions() -> None:
    same = [observations()[0]] * 5
    with pytest.raises(CalibrationError) as err:
        scale.fit_factors(same)
    assert err.value.key == "not_enough_positions"


def test_fit_error_shows_an_inconsistent_measurement() -> None:
    bad = observations()
    bad[2] = ([v * 1.5 for v in bad[2][0]], bad[2][1])
    factors = scale.fit_factors(bad)
    assert scale.fit_error_percent(factors, bad) > 3.0


class TestStability:
    def test_not_stable_before_it_was_watched_long_enough(self) -> None:
        tracker = StabilityTracker(2.0, 1.0)
        assert not tracker.stable(0.0)
        tracker.add(0.0, 100.0)
        assert not tracker.stable(1.9)
        assert tracker.stable(2.0)

    def test_the_last_value_holds_until_a_new_one_comes(self) -> None:
        tracker = StabilityTracker(2.0, 1.0)
        tracker.add(0.0, 100.0)
        assert tracker.stable(600.0)

    def test_a_jump_is_unsteady_until_the_old_value_leaves_the_window(self) -> None:
        tracker = StabilityTracker(2.0, 1.0)
        tracker.add(0.0, 0.0)
        tracker.add(10.0, 100.0)
        assert not tracker.stable(10.5)
        assert not tracker.stable(11.9)
        assert tracker.stable(12.1)

    def test_small_wobble_within_the_tolerance_is_steady(self) -> None:
        tracker = StabilityTracker(2.0, 1.0)
        for t, value in enumerate([100.0, 100.4, 99.8, 100.3, 100.1, 99.9]):
            tracker.add(float(t), value)
        assert tracker.stable(5.0)

    def test_drift_over_the_tolerance_is_unsteady(self) -> None:
        tracker = StabilityTracker(3.0, 1.0)
        for t, value in enumerate([100.0, 100.6, 101.2, 101.8, 102.4]):
            tracker.add(float(t), value)
        assert not tracker.stable(4.0)

    def test_reset_starts_the_observation_again(self) -> None:
        tracker = StabilityTracker(2.0, 1.0)
        tracker.add(0.0, 100.0)
        tracker.reset()
        assert not tracker.stable(10.0)
        tracker.add(10.0, 100.0)
        assert tracker.stable(12.0)
