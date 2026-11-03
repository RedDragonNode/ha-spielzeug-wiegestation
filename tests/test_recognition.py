"""Erkennung ohne Home Assistant: aufgelegt, weggenommen, unbekannt, Drift."""

from __future__ import annotations

import pytest

from custom_components.spielzeug_wiegestation.recognition import (
    KIND_PLACED,
    KIND_REMOVED,
    PlateTracker,
    Toy,
    default_tolerance,
    match_toy,
)

TEDDY = Toy("t1", "Teddy", 250.0, 12.5)
AUTO = Toy("t2", "Auto", 80.0, 4.0)
BALL = Toy("t3", "Ball", 30.0, 3.0)
TOYS = [TEDDY, AUTO, BALL]
MIN_G = 5.0


def settle(tracker: PlateTracker, weight: float, toys=TOYS):
    return tracker.settle(weight, toys, MIN_G)


@pytest.fixture
def tracker() -> PlateTracker:
    plate = PlateTracker()
    assert settle(plate, 0.0) == []  # die erste ruhige Platte ist der Anfang, kein Ereignis
    return plate


# ---------------------------------------------------------------- Zuordnung
@pytest.mark.parametrize(
    ("weight", "expected"),
    [(250.0, TEDDY), (238.0, TEDDY), (262.5, TEDDY), (80.0, AUTO), (76.0, AUTO), (84.0, AUTO), (31.5, BALL)],
)
def test_a_weight_within_the_tolerance_is_that_toy(weight: float, expected: Toy) -> None:
    assert match_toy(weight, TOYS) is expected


@pytest.mark.parametrize("weight", [0.0, 20.0, 55.0, 100.0, 237.0, 263.0, 500.0])
def test_a_weight_outside_every_tolerance_is_unknown(weight: float) -> None:
    assert match_toy(weight, TOYS) is None


def test_the_nearest_toy_wins_when_two_fit() -> None:
    low, high = Toy("a", "Niedrig", 100.0, 10.0), Toy("b", "Hoch", 108.0, 10.0)
    assert match_toy(103.0, [low, high]) is low
    assert match_toy(105.0, [low, high]) is high
    assert low.overlaps(high)
    assert not low.overlaps(Toy("c", "Weit", 200.0, 10.0))


@pytest.mark.parametrize(("weight", "expected"), [(10, 3.0), (60, 3.0), (100, 5.0), (250, 12.5), (500, 25.0)])
def test_default_tolerance_is_five_percent_but_at_least_three_grams(weight: float, expected: float) -> None:
    assert default_tolerance(weight) == expected


# ---------------------------------------------------------------- Auflegen und Wegnehmen
def test_placing_a_known_toy(tracker: PlateTracker) -> None:
    (found,) = settle(tracker, 251.0)
    assert (found.kind, found.toy, found.weight_g) == (KIND_PLACED, TEDDY, 251.0)
    assert [item.toy for item in tracker.items] == [TEDDY]


def test_placing_an_unknown_thing(tracker: PlateTracker) -> None:
    (found,) = settle(tracker, 150.0)
    assert (found.kind, found.toy, found.weight_g) == (KIND_PLACED, None, 150.0)
    assert [(item.toy, item.weight_g) for item in tracker.items] == [(None, 150.0)]


def test_removing_the_toy_again(tracker: PlateTracker) -> None:
    settle(tracker, 250.0)
    (found,) = settle(tracker, 0.0)
    assert (found.kind, found.toy) == (KIND_REMOVED, TEDDY)
    assert tracker.items == []


def test_removing_an_unknown_thing_again(tracker: PlateTracker) -> None:
    settle(tracker, 150.0)
    (found,) = settle(tracker, 0.0)
    assert (found.kind, found.toy, found.weight_g) == (KIND_REMOVED, None, 150.0)


def test_two_toys_one_after_the_other(tracker: PlateTracker) -> None:
    assert [d.toy for d in settle(tracker, 250.0)] == [TEDDY]
    assert [d.toy for d in settle(tracker, 330.0)] == [AUTO]
    assert [item.toy for item in tracker.items] == [TEDDY, AUTO]
    # das Auto wird weggenommen, der Teddy bleibt
    (found,) = settle(tracker, 250.0)
    assert (found.kind, found.toy) == (KIND_REMOVED, AUTO)
    assert [item.toy for item in tracker.items] == [TEDDY]


def test_taking_everything_away_at_once_reports_each_toy(tracker: PlateTracker) -> None:
    settle(tracker, 250.0)
    settle(tracker, 330.0)
    found = settle(tracker, 0.0)
    assert sorted(d.toy.name for d in found if d.toy) == ["Auto", "Teddy"]
    assert {d.kind for d in found} == {KIND_REMOVED}
    assert tracker.items == []


def test_two_toys_placed_together_are_one_unknown_thing(tracker: PlateTracker) -> None:
    (found,) = settle(tracker, 330.0)  # Teddy und Auto zusammen
    assert (found.kind, found.toy) == (KIND_PLACED, None)


def test_removing_something_that_was_not_tracked_still_matches_a_toy(tracker: PlateTracker) -> None:
    settle(tracker, 400.0)  # unbekannt
    (found,) = settle(tracker, 320.0)  # 80 g weg: passt auf das Auto, das nie aufgelegt wurde
    assert (found.kind, found.toy) == (KIND_REMOVED, AUTO)
    assert [(item.toy, item.weight_g) for item in tracker.items] == [(None, 400.0)]


def test_creep_after_the_removal_still_matches_the_toy(tracker: PlateTracker) -> None:
    """Die Platte kriecht nach der Last um etwa ein Prozent: 250 g weg, aber 3 g bleiben stehen."""
    settle(tracker, 250.0)
    (found,) = settle(tracker, 3.0)
    assert (found.kind, found.toy) == (KIND_REMOVED, TEDDY)


# ---------------------------------------------------------------- kleine Änderungen und Drift
def test_changes_below_the_minimum_are_ignored(tracker: PlateTracker) -> None:
    for weight in (2.0, 4.0, 1.0, 4.9):
        assert settle(tracker, weight) == []
    assert tracker.items == []


def test_slow_drift_does_not_add_up_to_a_toy(tracker: PlateTracker) -> None:
    """Jeder Schritt unter 5 g, zusammen 12 g: die Bezugsgröße läuft mit, es gibt kein Ereignis."""
    for weight in (3.0, 6.0, 9.0, 12.0):
        assert settle(tracker, weight) == []
    (found,) = settle(tracker, 12.0 + 250.0)
    assert found.toy is TEDDY and found.weight_g == 250.0


def test_an_empty_plate_with_drift_still_counts_as_empty(tracker: PlateTracker) -> None:
    settle(tracker, 80.0)
    (found,) = settle(tracker, 4.0)  # Auto weg, 4 g Kriechen übrig, unter der Mindestgröße
    assert (found.kind, found.toy) == (KIND_REMOVED, AUTO)
    assert tracker.items == []


# ---------------------------------------------------------------- Anfang, Zurücksetzen
def test_a_toy_already_on_the_plate_at_the_start_is_remembered_silently() -> None:
    plate = PlateTracker()
    assert settle(plate, 80.0) == []
    assert [item.toy for item in plate.items] == [AUTO]
    (found,) = settle(plate, 0.0)
    assert (found.kind, found.toy) == (KIND_REMOVED, AUTO)


def test_an_unknown_weight_at_the_start_is_remembered_as_unknown() -> None:
    plate = PlateTracker()
    assert settle(plate, 150.0) == []
    assert [(item.toy, item.weight_g) for item in plate.items] == [(None, 150.0)]


@pytest.mark.parametrize("weight", [0.0, 3.0, 6.5, 9.9])
def test_a_few_grams_at_the_start_are_a_drifted_zero_not_a_thing(weight: float) -> None:
    plate = PlateTracker()
    assert settle(plate, weight) == []
    assert plate.items == []


def test_a_light_toy_at_the_start_is_found_by_its_weight() -> None:
    plate = PlateTracker()
    settle(plate, 30.0, toys=[BALL])
    assert [item.toy for item in plate.items] == [BALL]


def test_reset_forgets_everything(tracker: PlateTracker) -> None:
    settle(tracker, 250.0)
    tracker.reset()
    assert tracker.reference is None
    assert tracker.items == []
    assert settle(tracker, 250.0) == []  # nach dem Zurücksetzen ist die Platte wieder der Anfang


def test_rebase_moves_the_reference(tracker: PlateTracker) -> None:
    assert settle(tracker, 4.0) == []  # die Platte driftet, die Bezugsgröße läuft mit
    tracker.rebase(0.0)  # der Nullpunkt wurde nachgeführt, die 4 g sind jetzt null
    assert settle(tracker, 80.0)[0].toy is AUTO
