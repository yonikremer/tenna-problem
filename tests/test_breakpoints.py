"""The search itself: the part of breakpoints.py that decides where an edge is.

No recordings are synthesised here - the bisection and the interval are pure functions, and the
bracket check is exercised with a stubbed probe, so these tests say nothing about the physics and
everything about whether a located edge can be trusted.
"""

import json

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
    monkeypatch.setattr(
        breakpoints, "measure", lambda axis, value, signals, criterion, cache: (0, 0.0)
    )
    record = breakpoints.locate(axis, 10, 0.95, {})
    assert record["located"] is None
    assert record["error"] and "declared good end" in record["error"]
    assert record["trace"] == []


def test_an_unreachable_break_end_is_reported(monkeypatch):
    axis = breakpoints.AXES["duration"]
    monkeypatch.setattr(
        breakpoints, "measure", lambda axis, value, signals, criterion, cache: (10, 0.0)
    )
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


def test_cached_section_says_so_when_nothing_is_measured(tmp_path):
    """The section is part of BENCHMARK.md, so it must appear even with no probes behind it."""
    section = breakpoints.cached_section(tmp_path / "missing.json")
    assert section[0] == breakpoints.SECTION_HEADING
    assert "No probes measured yet" in " ".join(section)


def test_cached_section_refuses_a_cache_that_mixes_experiments(tmp_path):
    path = tmp_path / "probes.json"
    path.write_text(
        json.dumps(
            {
                "cn0@50": {"passes": 100, "signals": 100, "criterion": 0.95, "seconds": 1.0},
                "cn0@49": {"passes": 10, "signals": 50, "criterion": 0.95, "seconds": 1.0},
            }
        ),
        encoding="utf-8",
    )
    assert "no single rate can be quoted" in " ".join(breakpoints.cached_section(path))


def test_cached_section_survives_a_half_measured_cache(tmp_path):
    """A missing probe must not take the report down, and must not start 100 recordings."""
    path = tmp_path / "probes.json"
    path.write_text(
        json.dumps({"cn0@60": {"passes": 100, "signals": 100, "criterion": 0.95, "seconds": 1.0}}),
        encoding="utf-8",
    )
    section = " ".join(breakpoints.cached_section(path))
    assert "probes for this axis are incomplete" in section
    assert "not in" in section


def test_write_into_replaces_only_its_own_section(tmp_path):
    path = tmp_path / "BENCHMARK.md"
    path.write_text(
        "# Report\n\n## cn0\n\n| a |\n\n## Break points, old\n\nstale\n", encoding="utf-8"
    )
    breakpoints.write_into(path, [breakpoints.SECTION_HEADING, "", "fresh"])
    text = path.read_text(encoding="utf-8")
    assert "## cn0" in text and "| a |" in text
    assert "fresh" in text and "stale" not in text
    assert text.count(breakpoints.SECTION_HEADING) == 1
