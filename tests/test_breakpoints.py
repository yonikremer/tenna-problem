"""The search itself: the part of breakpoints.py that decides where an edge is.

No recordings are synthesised here - the bisection and the interval are pure functions, and the
bracket check is exercised with a stubbed probe, so these tests say nothing about the physics and
everything about whether a located edge can be trusted.
"""

import breakpoints


def step_at_five(value):
    return 1.0 if value >= 5.0 else 0.0


def test_bisect_finds_the_edge_of_a_step():
    passing, breaking, trace = breakpoints.bisect(10.0, 0.0, step_at_five, 0.95, 1.0)
    assert passing >= 5.0 > breaking
    assert passing - breaking <= 1.0
    assert trace, "the search must actually probe"


def test_bisect_on_integers_stops_at_adjacent_values():
    """An integer bracket cannot split below one step, so it must stop instead of looping."""
    passing, breaking, _ = breakpoints.bisect(
        10, 0, lambda value: 1.0 if value >= 4 else 0.0, 0.95, 1
    )
    assert (passing, breaking) == (4, 3)


def test_bisect_finds_a_lower_edge():
    """A breaking side above the passing side is the same interval halving in the other direction."""
    passing, breaking, _ = breakpoints.bisect(
        40.0, 70.0, lambda value: 1.0 if value <= 46.5 else 0.0, 0.95, 0.25
    )
    assert passing <= 46.5 < breaking
    assert breaking - passing <= 0.25


def test_a_wrong_bracket_is_reported_instead_of_bisected(monkeypatch):
    """If the declared good end does not reach the criterion, bisecting would locate noise."""
    axis = breakpoints.AXES["duration"]
    monkeypatch.setattr(breakpoints, "measure", lambda axis, value, signals, cache: (0, 0.0))
    record = breakpoints.locate(axis, 10, 0.95, {})
    assert record["located"] is None
    assert record["error"] and "declared good end" in record["error"]
    assert record["trace"] == []


def test_an_unreachable_break_end_is_reported(monkeypatch):
    axis = breakpoints.AXES["duration"]
    monkeypatch.setattr(breakpoints, "measure", lambda axis, value, signals, cache: (10, 0.0))
    record = breakpoints.locate(axis, 10, 0.95, {})
    assert record["located"] is None
    assert record["error"] and "break is outside the bracket" in record["error"]


def test_wilson_interval_quotes_the_sampling_error():
    low, high = breakpoints.wilson_interval(95, 100)
    assert low < 0.95 < high
    assert 0.88 < low < 0.90 and 0.97 < high < 0.99
    low, high = breakpoints.wilson_interval(100, 100)
    assert high > 0.999 and 0.95 < low < 0.98
    assert breakpoints.wilson_interval(0, 0) == (0.0, 1.0)
