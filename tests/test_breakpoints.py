"""The search itself: the part of breakpoints.py that decides where an edge is.

No recordings are synthesised here - the bisection and the interval are pure functions, and the
bracket check is exercised with a stubbed probe, so these tests say nothing about the physics and
everything about whether a located edge can be trusted.
"""

import json

import pytest

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


def a_record(passing, breaking, good, trace, located, seconds=1.0):
    """The shape `locate` returns, so the renderers can be exercised without measuring."""
    return {
        "axis": "cn0",
        "question": "a question",
        "passing": passing,
        "breaking": breaking,
        "resolution": 0.25,
        "unit": "dB-Hz",
        "good_probe": (good, 100),
        "bad_probe": (0, 100),
        "trace": trace,
        "located": located,
        "error": None,
        "seconds": seconds,
    }


def test_duration_axes_each_ask_about_their_own_record_length():
    """The build closure must capture its own duration, not the last one the loop made."""
    axes = breakpoints.duration_axes()
    assert list(axes) == [2, 4, 8, 16, 32]
    assert {periods: axis.scenario(55.0, 3).code_periods for periods, axis in axes.items()} == {
        2: 2,
        4: 4,
        8: 8,
        16: 16,
        32: 32,
    }
    # a longer record carries more energy, so the floor it is bracketed against must not be higher
    assert axes[2].passing >= axes[8].passing


def test_duration_section_says_so_before_anything_is_measured(tmp_path):
    figure = tmp_path / "figure.svg"
    section = breakpoints.duration_section(tmp_path / "missing.json", figure)
    assert section[0] == breakpoints.SECTION_DURATION_HEADING
    assert "No probes measured yet" in " ".join(section)
    assert not figure.exists(), "no figure can be drawn from no probes"


def test_the_text_scatter_marks_every_probe_by_rate():
    record = a_record(60.0, 40.0, 100, [(50.0, 98, 0.98), (46.0, 40, 0.40)], (50.0, 49.0))
    lines = breakpoints._text_scatter([record], [8], 100, 0.95)
    by_value = {line.split()[0]: line for line in lines if line.strip() and line[0].isdigit()}
    assert "#" in by_value["60"] and "#" in by_value["50"]
    assert "." in by_value["46"] and "." in by_value["40"]
    assert "46" in by_value and "40" in by_value


def test_the_svg_has_one_circle_per_probe_and_closes():
    record = a_record(60.0, 40.0, 100, [(50.0, 98, 0.98), (46.0, 40, 0.40)], (50.0, 49.0))
    svg = breakpoints._scatter_svg([record], [8], 100, 0.95)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    # good end + two trace points + bad end + the edge marker + three legend swatches
    assert svg.count("<circle") == 8
    assert svg.count("<polyline") == 0, "one duration cannot draw an edge line"


def test_the_svg_draws_the_edge_line_and_survives_a_broken_axis():
    good = a_record(60.0, 40.0, 100, [(50.0, 98, 0.98)], (50.0, 49.0))
    broken = {"axis": "cn0", "question": "q", "error": "bracket wrong", "trace": [], "seconds": 0.0}
    svg = breakpoints._scatter_svg([good, broken], [8, 16], 100, 0.95)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")


def test_the_duration_section_reports_the_gain_per_doubling(monkeypatch, tmp_path):
    """Two located edges 4 dB apart over two doublings must be reported as 4 dB per doubling."""
    near = a_record(60.0, 40.0, 100, [(50.0, 98, 0.98)], (50.0, 49.5))
    far = a_record(60.0, 40.0, 100, [(42.0, 98, 0.98)], (42.0, 41.5))
    monkeypatch.setattr(
        breakpoints,
        "_located",
        lambda axes, cache_path: ([near, far], [8, 32], 100, 0.95, None),
    )
    figure = tmp_path / "figure.svg"
    section = breakpoints.duration_section(tmp_path / "probes.json", figure)
    text = " ".join(section)
    assert section[0] == breakpoints.SECTION_DURATION_HEADING
    assert "4.00 dB per doubling" in text
    assert figure.as_posix() in text
    assert figure.exists() and figure.read_text(encoding="utf-8").startswith("<svg")


def test_each_probe_is_paid_for_once(monkeypatch):
    """The reported cost must be the sum of the probes, not twice it.

    Regression: the bisection measured each value, then the trace loop measured it again to recover
    the pass count, so every stored cost was counted twice and the report claimed 1.8x the truth.
    """
    probed = []

    def fake_probe(axis, value, signals, criterion, cache):
        probed.append(value)
        return (100 if value >= 50.0 else 0), 10.0

    monkeypatch.setattr(breakpoints, "measure", fake_probe)
    record = breakpoints.locate(breakpoints.AXES["cn0"], 100, 0.95, {})
    assert len(probed) == len(set(probed)), f"a value was probed twice: {sorted(probed)}"
    assert record["seconds"] == 10.0 * len(probed)
    assert all(passes in (0, 100) for _, passes, _ in record["trace"])


def test_the_half_rate_crossing_is_interpolated_between_its_probes():
    """0 of 100 at 40 dB-Hz and 83 of 100 at 47.5 puts half 0.5/0.83 of the way between them."""
    half = breakpoints._half_rate_cn0([(40.0, 0), (47.5, 83), (50.0, 98)], 100)
    assert half == pytest.approx(40.0 + (0.5 / 0.83) * 7.5, abs=1e-9)


def test_the_half_rate_is_none_when_no_probe_brackets_half():
    assert breakpoints._half_rate_cn0([(50.0, 98), (60.0, 100)], 100) is None
    assert breakpoints._half_rate_cn0([(40.0, 0), (41.0, 2)], 100) is None
    assert breakpoints._half_rate_cn0([(40.0, 0)], 100) is None


def test_the_figure_marks_the_assignment_length_and_draws_one_band_per_duration():
    good = a_record(60.0, 40.0, 100, [(50.0, 98, 0.98), (44.0, 20, 0.20)], (50.0, 49.0))
    svg = breakpoints._scatter_svg([good, good], [8, 32], 100, 0.95)
    assert breakpoints.ASSIGNMENT_PERIODS == 8
    assert svg.count("<rect x=") == 1, "the 8 ms marker is exactly one shaded band"
    assert "8 ms = our signal" in svg
    assert svg.count('stroke-width="11"') == 3, "one range bar per duration plus the legend sample"


def test_the_figure_marks_nothing_when_eight_milliseconds_is_not_plotted():
    good = a_record(60.0, 40.0, 100, [(50.0, 98, 0.98), (44.0, 20, 0.20)], (50.0, 49.0))
    svg = breakpoints._scatter_svg([good], [16], 100, 0.95)
    assert "<rect x=" not in svg
    assert "our signal" not in svg
