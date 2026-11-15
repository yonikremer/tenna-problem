"""Locate where the recovery chain breaks on each axis, by bisection over 100 signals per point.

This is the second half of `BENCHMARK.md`, not a separate document: it renders the `## Break points`
section, either into the report the benchmark writes or into an existing report, replacing only that
section. `python benchmark.py` fills the sweep half and calls in here for the other; `python
breakpoints.py` measures the probes and then rewrites its own section in place, so the back of the
report never goes stale.

Why it exists at all: `benchmark.py` sweeps a fixed grid with two noise seeds per point. Two seeds
can only report 0/2, 1/2 or 2/2, so the grid shows *that* a break exists but not *where* - the
difference between a method that works every time and one that works half the time is one row apart.

So each probe runs `--signals` independent recordings (100 by default) at one value of one axis,
measures the fraction that recover exactly, and the value is bisected until the passing and breaking
ends are one resolution apart. Every probe reuses the same seeds (common random numbers), so adjacent
probes differ in the parameter and not in the noise draw.

Three things make the answer honest:

  - The criterion is a rate, not a single run: the default is that at least 95 of 100 signals
    recover, which is the claim the prose actually wants to make.
  - Binomial noise is quoted, not hidden: the Wilson interval of every probe is printed, and each
    axis's resolution is chosen so the bisection does not pretend to be finer than the sampling
    allows (100 signals cannot resolve a rate better than about +-2 points near 95%).
  - The bracket is checked, not assumed. If the "known good" end does not reach the criterion, or
    the "known bad" end does, the axis says so and stops instead of bisecting on nonsense.

Bisection needs the pass rate to be monotone between the two ends. Where the chain is not monotone
the two edges are searched separately: the PRN count fails both below a minimum (one PRN cannot
define a shared shift, and the combining gain that decides a chip is not there) and above a maximum
(a dense modification leaves too little of the nominal code to detect).

Usage:
    python breakpoints.py                       # every axis, 100 signals per probe
    python breakpoints.py --signals 50          # coarser and quicker
    python breakpoints.py --axes cn0 flip_count # named axes only
"""

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from benchmark import Scenario, score, synthesise

WORK_DIR = Path("data/breakpoints")
CACHE_PATH = Path("data/breakpoints/probes.json")
DURATION_CACHE = Path("data/breakpoints/duration_cn0.json")
DURATION_FIGURE = Path("assets/cn0_vs_duration.svg")
REPORT_PATH = Path("BENCHMARK.md")

# The record lengths the duration experiment compares: each doubling is 1 ms of signal, and about
# 3 dB of chip combining gain, which is exactly the quantity that experiment sets out to measure.
DURATION_PERIODS = (2, 4, 8, 16, 32)

# The headings this module owns in BENCHMARK.md. Everything from the first one down is replaced on a
# rerun, because both sections are always written together and always come last.
SECTION_HEADING = "## Break points"
SECTION_DURATION_HEADING = "## Duration against C/N0"

# A recovered recording counts when every PRN was found with no false alarm, the shift is right and
# the recovered flip set matches the truth exactly - the same `verdict` the benchmark reports.
PASSING_VERDICTS = ("pass",)


@dataclass(frozen=True)
class Axis:
    """One physical axis: a bracket that straddles the break, and how to build a signal on it."""

    name: str
    question: str
    passing: float
    """Value known to recover: the bisection starts here."""
    breaking: float
    """Value known to fail: the other end of the bracket."""
    resolution: float
    """Stop when the two ends are this close; see the module docstring for why not finer."""
    build: Callable[[float, int], Scenario]
    """`build(value, seed) -> Scenario`."""
    unit: str = ""
    integer: bool = False

    def scenario(self, value: float, seed: int) -> Scenario:
        return self.build(self.snap(value), seed)

    def snap(self, value: float):
        return int(round(value)) if self.integer else float(value)

    def text(self, value: float) -> str:
        return f"{value:g} {self.unit}".strip()


AXES = {
    "cn0": Axis(
        name="cn0",
        question="lowest carrier-to-noise density per PRN that still recovers every chip",
        passing=60.0,
        breaking=40.0,
        resolution=0.25,
        unit="dB-Hz",
        build=lambda value, seed: Scenario(label=f"probe-seed{seed}", cn0_dbhz=value, seed=seed),
    ),
    "flip_count": Axis(
        name="flip_count",
        question="largest number of flipped chips per PRN that still recovers exactly",
        passing=15,
        breaking=500,
        resolution=4,
        integer=True,
        unit="chips",
        build=lambda value, seed: Scenario(
            label=f"probe-seed{seed}", flip_count=int(value), seed=seed
        ),
    ),
    "prns_low": Axis(
        name="prns_low",
        question="fewest PRNs that still recover exactly (below it the combining gain is gone)",
        passing=12,
        breaking=1,
        resolution=1,
        integer=True,
        unit="PRNs",
        build=lambda value, seed: Scenario(
            label=f"probe-seed{seed}",
            prns=tuple(range(1, int(value) + 1)),
            cn0_dbhz=52.0,
            seed=seed,
        ),
    ),
    "prns_high": Axis(
        name="prns_high",
        question="most PRNs that still recover exactly (beyond it the noise floor moves)",
        passing=12,
        breaking=120,
        resolution=4,
        integer=True,
        unit="PRNs",
        build=lambda value, seed: Scenario(
            label=f"probe-seed{seed}",
            prns=tuple(range(1, int(value) + 1)),
            cn0_dbhz=52.0,
            seed=seed,
        ),
    ),
    "doppler": Axis(
        name="doppler",
        question="largest Doppler the widened search still recovers (span widens to cover it)",
        passing=60000.0,
        # 60 kHz passed 100/100 on the first attempt, so the bracket moved outwards: the break on
        # this axis is the detection threshold rising with the number of cells searched, not a
        # correctness cliff at the GPS line-of-sight speed.
        breaking=120000.0,
        resolution=5000.0,
        unit="Hz",
        build=lambda value, seed: Scenario(
            label=f"probe-seed{seed}",
            dopplers=(value, -value),
            max_speed_km_h=_speed_to_cover(value),
            seed=seed,
        ),
    ),
    "duration": Axis(
        name="duration",
        question="shortest record, in code periods, that still recovers exactly",
        passing=8,
        breaking=1,
        resolution=1,
        integer=True,
        unit="code periods",
        build=lambda value, seed: Scenario(
            label=f"probe-seed{seed}", code_periods=int(value), cn0_dbhz=52.0, seed=seed
        ),
    ),
}


def duration_axes() -> dict:
    """One C/N0 bisection per record length: the same question asked at five durations."""
    axes = {}
    for periods in DURATION_PERIODS:
        axes[periods] = Axis(
            name=f"cn0_{periods}periods",
            question=f"lowest C/N0 per PRN that recovers every chip at {periods} code periods",
            # two code periods cannot fit a phase slope and locate a step, so it needs more signal
            passing=70.0 if periods <= 2 else 60.0,
            breaking=40.0,
            resolution=0.25,
            unit="dB-Hz",
            build=lambda value, seed, code_periods=periods: Scenario(
                label=f"probe-seed{seed}",
                code_periods=code_periods,
                cn0_dbhz=value,
                seed=seed,
            ),
        )
    return axes


def _speed_to_cover(doppler_hz: float) -> float:
    """Receiver speed whose search span reaches `doppler_hz`, with the benchmark's 5% headroom."""
    import benchmark

    return benchmark.receiver_speed_to_cover(doppler_hz)


def probe_key(axis: "Axis", value: float) -> str:
    return f"{axis.name}@{value:g}"


def wilson_interval(passes: int, signals: int, z: float = 1.96) -> tuple:
    """95% interval of a binomial rate, which is the only honest error bar for a probe."""
    if signals <= 0:
        return 0.0, 1.0
    rate = passes / signals
    denominator = 1.0 + z * z / signals
    centre = (rate + z * z / (2 * signals)) / denominator
    half = z * np.sqrt(rate * (1 - rate) / signals + z * z / (4 * signals * signals)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def measure(axis: Axis, value: float, signals: int, criterion: float, cache: dict) -> tuple:
    """Run `signals` independent recordings at one value; return (passes, seconds measured).

    A cached probe still reports the time it took when it was measured: the cost of the evidence
    does not disappear because a rerun is free.
    """
    key = probe_key(axis, value)
    if key in cache:
        return cache[key]["passes"], cache[key].get("seconds", 0.0)
    started = time.perf_counter()
    passes = 0
    for seed in range(1, signals + 1):
        scenario = axis.scenario(value, seed)
        path, truth = synthesise(scenario, WORK_DIR)
        result = score(scenario, truth, path)
        passes += result["verdict"] in PASSING_VERDICTS
    elapsed = time.perf_counter() - started
    cache[key] = {
        "passes": passes,
        "signals": signals,
        "criterion": criterion,
        "seconds": round(elapsed, 3),
    }
    return passes, elapsed


def cache_only(axis: Axis, value: float, signals: int, criterion: float, cache: dict) -> tuple:
    """A probe that refuses to run: rendering a report must never start 100 recordings."""
    key = probe_key(axis, value)
    if key not in cache:
        raise KeyError(
            f"{key} is not in {CACHE_PATH}; run `python breakpoints.py` to measure it before "
            f"rendering the report"
        )
    return cache[key]["passes"], cache[key].get("seconds", 0.0)


def bisect(passing, breaking, rate_of, criterion: float, resolution: float, max_probes: int = 14):
    """Halve the bracket while keeping the passing and breaking ends; return the trace.

    Pure, so the search can be exercised without running a single signal. `rate_of` must be
    monotone between the two ends: that is what makes the located edge meaningful.
    """
    trace = []
    for _ in range(max_probes):
        if abs(passing - breaking) <= resolution:
            break
        middle = (passing + breaking) / 2.0
        if isinstance(passing, int) and isinstance(breaking, int):
            middle = int(round(middle))
            if middle in (passing, breaking):  # cannot split an integer bracket any further
                break
        rate = rate_of(middle)
        trace.append((middle, rate))
        if rate >= criterion:
            passing = middle
        else:
            breaking = middle
    return passing, breaking, trace


def locate(
    axis: Axis,
    signals: int,
    criterion: float,
    cache: dict,
    probe: Callable | None = None,
) -> dict:
    """Bisect one axis, and check that both ends of the bracket behave as declared."""
    probe = probe or measure
    passes_good, seconds_good = probe(axis, axis.snap(axis.passing), signals, criterion, cache)
    passes_bad, seconds_bad = probe(axis, axis.snap(axis.breaking), signals, criterion, cache)
    spent = [seconds_good, seconds_bad]
    record = {
        "axis": axis.name,
        "question": axis.question,
        "passing": axis.passing,
        "breaking": axis.breaking,
        "resolution": axis.resolution,
        "unit": axis.unit,
        "good_probe": (passes_good, signals),
        "bad_probe": (passes_bad, signals),
        "trace": [],
        "located": None,
        "error": None,
        "seconds": 0.0,
    }
    if passes_good / signals < criterion:
        record["error"] = (
            f"the declared good end {axis.text(axis.passing)} only reached {passes_good}/{signals}; "
            f"move the bracket before trusting a bisection"
        )
    elif passes_bad / signals >= criterion:
        record["error"] = (
            f"the declared bad end {axis.text(axis.breaking)} still reached {passes_bad}/{signals}; "
            f"the break is outside the bracket"
        )
    else:
        seen = {}

        def rate_of(value):
            snapped = axis.snap(value)
            passes, seconds = probe(axis, snapped, signals, criterion, cache)
            spent.append(seconds)
            seen[snapped] = passes
            return passes / signals

        passing, breaking, trace = bisect(
            axis.snap(axis.passing), axis.snap(axis.breaking), rate_of, criterion, axis.resolution
        )
        record["located"] = (passing, breaking)
        for value, rate in trace:
            # reusing what the bisection already measured: probing again would double the reported
            # cost and, on a live run, the wall clock
            snapped = axis.snap(value)
            record["trace"].append((snapped, seen[snapped], rate))
    # the cost of the probes, not the wall clock of this run: a cached probe still cost something
    record["seconds"] = sum(spent)
    return record


def _interval_text(passes: int, signals: int) -> str:
    low, high = wilson_interval(passes, signals)
    return f"{100 * low:.0f}% to {100 * high:.0f}%"


def report(records: list, signals: int, criterion: float, wall_seconds: float) -> list:
    """The `## Break points` section: the located edge per axis, then the probes that located it."""
    h = "##"
    lines = [
        f"{h} Break points, measured over independent signals",
        "",
        f"Generated with `python breakpoints.py --signals {signals}`. Each probe runs **{signals} "
        "independent recordings** (one per seed) at one value of one axis and counts how many "
        "recover exactly, then the value is bisected until the passing and breaking ends are one "
        "resolution apart. The sweeps above use two seeds per point, which can only say 0/2, 1/2 or "
        "2/2; this can say 91 of 100.",
        "",
        f"A signal counts as recovered when the verdict is `pass`: every PRN found with no false "
        f"alarm, the shift right and the flip set exactly right. The criterion is "
        f"**{round(criterion * signals)} of {signals}** signals. Every probe reuses the same seeds, "
        "so adjacent probes differ in the parameter and not in the noise draw.",
        "",
        f"{h}# Located edges",
        "",
        "| axis | question | edge | rate at the edge | 95% interval | next value fails at |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        if record["error"]:
            lines.append(
                f"| {record['axis']} | {record['question']} | **bracket wrong** | "
                f"{record['error']} | | |"
            )
            continue
        passing, breaking = record["located"]
        passes = next((p for value, p, _ in record["trace"] if value == passing), None)
        if passes is None:
            passes = record["good_probe"][0]
        low, high = wilson_interval(passes, signals)
        lines.append(
            f"| {record['axis']} | {record['question']} | {passing:g} {record['unit']} | "
            f"{passes}/{signals} = {100 * passes / signals:.0f}% | "
            f"{100 * low:.0f}% to {100 * high:.0f}% | {breaking:g} {record['unit']} |"
        )

    for record in records:
        lines.extend(["", f"{h}# {record['axis']}", "", record["question"], ""])
        if record["error"]:
            lines.append(f"**Bracket wrong.** {record['error']}")
            continue
        lines.extend(
            [
                "| value | recovered | rate | 95% interval |",
                "| --- | --- | --- | --- |",
                f"| {record['passing']:g} {record['unit']} (declared good) | "
                f"{record['good_probe'][0]}/{signals} | "
                f"{100 * record['good_probe'][0] / signals:.0f}% | "
                f"{_interval_text(record['good_probe'][0], signals)} |",
            ]
        )
        for value, passes, _ in sorted(record["trace"]):
            lines.append(
                f"| {value:g} {record['unit']} | {passes}/{signals} | {100 * passes / signals:.0f}% | "
                f"{_interval_text(passes, signals)} |"
            )
        lines.append(
            f"| {record['breaking']:g} {record['unit']} (declared bad) | "
            f"{record['bad_probe'][0]}/{signals} | {100 * record['bad_probe'][0] / signals:.0f}% | "
            f"{_interval_text(record['bad_probe'][0], signals)} |"
        )
        passing, breaking = record["located"]
        lines.extend(
            [
                "",
                f"**Edge between {passing:g} and {breaking:g} {record['unit']}** "
                f"(resolution {record['resolution']:g}, criterion {criterion * 100:.0f}%). "
                f"Probes on this axis: {len(record['trace']) + 2}, "
                f"{record['seconds']:.0f} s.",
            ]
        )

    probes = sum(len(record["trace"]) + 2 for record in records)
    measured = sum(record["seconds"] for record in records)
    lines.extend(
        [
            "",
            f"{h}# Cost",
            "",
            f"{len(records)} axes, {probes} probes, {signals} signals per probe: "
            f"{probes * signals} recordings scored in {measured / 60:.1f} min "
            f"({measured / max(probes * signals, 1):.2f} s per recording). This is the measured "
            f"cost of the probes, including any reused from the cache; this run took "
            f"{wall_seconds / 60:.1f} min of wall clock.",
            "",
        ]
    )
    return lines


def load_cache(path: Path = CACHE_PATH) -> dict:
    """The probe cache, or an empty one if it is missing or unreadable."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict, path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")


def _located(axes: dict, cache_path: Path):
    """(records, periods, signals, criterion, problem) located from the cache alone.

    Never measures: a report run must not start thousands of recordings because a probe is missing.
    A cache that is empty, or that mixes signal counts or criteria, comes back as a `problem` line
    saying so - the section can then never silently disappear and never quietly quote a different
    experiment's numbers.
    """
    cache = load_cache(cache_path)
    if not cache:
        return [], [], 0, 0.0, (
            "No probes measured yet. Each sweep above uses two noise seeds per point, which cannot "
            "say where a break is. Run `python breakpoints.py` to measure it over 100 independent "
            "signals per point."
        )
    counts = {entry.get("signals") for entry in cache.values()}
    criteria = {entry.get("criterion") for entry in cache.values()}
    if None in counts or None in criteria or len(counts) != 1 or len(criteria) != 1:
        return [], [], 0, 0.0, (
            f"The probe cache at `{cache_path}` does not record one signal count and one criterion "
            f"for every probe (found {sorted(map(str, counts))} signals and "
            f"{sorted(map(str, criteria))} criteria), so no single rate can be quoted for it. "
            f"Delete it and run `python breakpoints.py` again."
        )
    signals = counts.pop()
    criterion = criteria.pop()
    periods = list(axes)
    records = []
    for axis in axes.values():
        try:
            records.append(locate(axis, signals, criterion, cache, probe=cache_only))
        except KeyError as error:
            # a half-measured cache must not take the report down with it
            records.append(
                {
                    "axis": axis.name,
                    "question": axis.question,
                    "error": f"the probes for this axis are incomplete: {error}",
                    "trace": [],
                    "seconds": 0.0,
                }
            )
    return records, periods, signals, criterion, None


def cached_section(cache_path: Path = CACHE_PATH) -> list:
    """The `## Break points` section, rendered from the cache alone."""
    records, _periods, signals, criterion, problem = _located(AXES, cache_path)
    if problem:
        return [SECTION_HEADING, "", problem, ""]
    return report(records, signals, criterion, 0.0)


# The record length of the supplied recordings: 8 ms, i.e. 8 code periods. Marked on the scatter
# because it is the length the rest of the repository is about.
ASSIGNMENT_PERIODS = 8


def _probes_of(record: dict) -> list:
    """Every (C/N0, rate) this axis actually probed, bracket ends included."""
    points = [(record["passing"], record["good_probe"][0])]
    points += [(value, passes) for value, passes, _ in record["trace"]]
    points.append((record["breaking"], record["bad_probe"][0]))
    return points


def _half_rate_cn0(points: list, signals: int) -> float | None:
    """The C/N0 where the recovery rate crosses half, interpolated between the bracketing probes.

    This is the bottom of the useful range: below it a recording more often fails than recovers, so
    the chain is gambling. The located edge is the top of the same range, where it is reliable.
    """
    ordered = sorted(points)
    for (low_cn0, low_passes), (high_cn0, high_passes) in zip(ordered, ordered[1:], strict=False):
        low_rate = low_passes / signals
        high_rate = high_passes / signals
        if low_rate < 0.5 <= high_rate:
            if high_rate == low_rate:
                return float(high_cn0)
            return float(low_cn0 + (0.5 - low_rate) / (high_rate - low_rate) * (high_cn0 - low_cn0))
    return None


def _glyph(rate: float | None, signals: int, criterion: float) -> str:
    if rate is None:
        return " "
    fraction = rate / signals
    if fraction >= criterion:
        return "#"
    return "o" if fraction >= 0.5 else "."


def _text_scatter(records: list, periods: list, signals: int, criterion: float) -> list:
    """C/N0 down the page against duration across it, one glyph per probe actually run."""
    measured = {periods[index]: dict(_probes_of(record)) for index, record in enumerate(records)}
    rows = sorted({value for record in records for value, _ in _probes_of(record)}, reverse=True)
    label_width = max(len(f"{value:g}") for value in rows)

    def header_cell(periods_count: int) -> str:
        return f"{periods_count:^4d}{'*' if periods_count == ASSIGNMENT_PERIODS else ' '}"

    lines = [
        " " * (label_width + 4) + "".join(header_cell(periods_count) for periods_count in periods),
        " " * (label_width + 2)
        + "dB-Hz"
        + " " * (5 * len(periods) - 5 - len("dB-Hz") + 2)
        + "code periods (1 ms each)",
    ]
    for value in rows:
        cells = "".join(
            f"{_glyph(measured[periods_count].get(value), signals, criterion):^5}"
            for periods_count in periods
        )
        lines.append(f"{value:>{label_width}g}   {cells}")
    lines += [
        "",
        f"`#` at least {round(criterion * signals)} of {signals} recover, `o` half to that, `.` below "
        "half, blank not probed.",
    ]
    if ASSIGNMENT_PERIODS in periods:
        lines.append(
            f"`*` the supplied recordings: {ASSIGNMENT_PERIODS} ms, {ASSIGNMENT_PERIODS} code periods."
        )
    return lines


def _scatter_svg(records: list, periods: list, signals: int, criterion: float) -> str:
    """The same scatter as an SVG, so it can be looked at rather than read.

    Hand-written because the alternative was a fifty-megabyte plotting dependency for one figure;
    the sheet is axis lines, one circle per probe and a dashed line through the located edges.
    """
    low, high = 40.0, 70.0
    width, height, left, right, top, bottom = 780, 470, 86, 26, 46, 70
    plot_width, plot_height = width - left - right, height - top - bottom
    spans = np.log2(periods)
    span = float(spans.max() - spans.min())

    def x_of(count: int) -> float:
        if span == 0.0:  # a single duration has no axis to spread over
            return float(left + plot_width / 2)
        return float(left + (np.log2(count) - spans.min()) / span * plot_width)

    def y_of(cn0: float) -> float:
        return float(top + (high - cn0) / (high - low) * plot_height)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif" font-size="13">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="26" font-size="15" font-weight="600">Minimal C/N0 for full 15-chip '
        f'recovery against record length</text>',
        f'<text x="{left}" y="42" fill="#57606a">{signals} independent signals per probe, '
        f'criterion {round(criterion * signals)} of {signals}; 12 PRNs, 15 flipped chips</text>',
    ]
    cn0_tick = low
    while cn0_tick <= high + 1e-9:
        y = y_of(cn0_tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" stroke="#eaeef2"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" fill="#57606a">{cn0_tick:g}</text>')
        cn0_tick += 5.0
    for count in periods:
        x = x_of(count)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" stroke="#eaeef2"/>')
        parts.append(f'<text x="{x:.1f}" y="{top + plot_height + 20}" text-anchor="middle">{count}</text>')
        parts.append(f'<text x="{x:.1f}" y="{top + plot_height + 36}" text-anchor="middle" fill="#57606a">{count} ms</text>')
    parts += [
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#8c959f"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#8c959f"/>',
        f'<text x="{left + plot_width / 2:.0f}" y="{height - 14}" text-anchor="middle" fill="#57606a">'
        f'record length, code periods (log scale)</text>',
        f'<text transform="translate(20 {top + plot_height / 2:.0f}) rotate(-90)" text-anchor="middle" '
        f'fill="#57606a">C/N0 per PRN, dB-Hz</text>',
    ]
    # The supplied recordings are 8 ms: marked first so it sits behind the data, not on top of it.
    if ASSIGNMENT_PERIODS in periods:
        callout = x_of(ASSIGNMENT_PERIODS)
        parts.append(
            f'<rect x="{callout - 17:.1f}" y="{top}" width="34" height="{plot_height}" '
            f'fill="#0969da" fill-opacity="0.08"/>'
        )
        parts.append(
            f'<text x="{callout:.1f}" y="{top + plot_height + 52}" text-anchor="middle" '
            f'fill="#0969da" font-weight="600">{ASSIGNMENT_PERIODS} ms = our signal</text>'
        )

    # The useful range of each length: from the C/N0 where recovery is a coin flip to where it is
    # reliable. Drawn before the probes so the bars sit behind the points.
    for index, record in enumerate(records):
        if record["error"] or not record.get("located"):
            continue
        half = _half_rate_cn0(_probes_of(record), signals)
        if half is None:
            continue
        x = x_of(periods[index])
        edge = record["located"][0]
        parts.append(
            f'<line x1="{x:.1f}" y1="{y_of(half):.1f}" x2="{x:.1f}" y2="{y_of(edge):.1f}" '
            f'stroke="#0969da" stroke-width="11" stroke-opacity="0.22" stroke-linecap="round"/>'
        )

    colours = {"#": "#1a7f37", "o": "#bf8700", ".": "#d1242f"}
    for index, record in enumerate(records):
        if record["error"]:
            continue
        x = x_of(periods[index])
        for cn0, passes in _probes_of(record):
            glyph = _glyph(passes, signals, criterion)
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y_of(cn0):.1f}" r="5" fill="{colours[glyph]}" '
                f'fill-opacity="0.85"/>'
            )
        if record.get("located"):
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y_of(record["located"][0]):.1f}" r="9" fill="none" '
                f'stroke="#0969da" stroke-width="2"/>'
            )
    edges = [
        (x_of(periods[index]), y_of(record["located"][0]))
        for index, record in enumerate(records)
        if record.get("located")
    ]
    if len(edges) > 1:
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in edges)
        parts.append(f'<polyline points="{path}" fill="none" stroke="#0969da" stroke-width="2" stroke-dasharray="6 4"/>')
    legend = [("#", "at or above the criterion"), ("o", "half to the criterion"), (".", "below half")]
    for row, (glyph, text) in enumerate(legend):
        y = top + 16 + row * 20
        parts.append(f'<circle cx="{left + plot_width - 210}" cy="{y - 4}" r="5" fill="{colours[glyph]}" fill-opacity="0.85"/>')
        parts.append(f'<text x="{left + plot_width - 198}" y="{y}" fill="#57606a">{text}</text>')
    parts.append(
        f'<line x1="{left + plot_width - 210}" y1="{top + 96}" x2="{left + plot_width - 194}" '
        f'y2="{top + 96}" stroke="#0969da" stroke-width="11" stroke-opacity="0.22" stroke-linecap="round"/>'
    )
    parts.append(
        f'<text x="{left + plot_width - 188}" y="{top + 100}" fill="#57606a">'
        f'half to reliable band</text>'
    )
    parts.append(
        f'<text x="{left + plot_width - 210}" y="{top + 120}" fill="#0969da">'
        f'dashed: located edge</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def duration_section(cache_path: Path = DURATION_CACHE, figure: Path = DURATION_FIGURE) -> list:
    """The `## Duration against C/N0` section: the minimal C/N0 at each record length."""
    axes = duration_axes()
    records, periods, signals, criterion, problem = _located(axes, cache_path)
    lines = [
        SECTION_DURATION_HEADING,
        "",
        "Does a longer record buy a lower C/N0 floor for the full 15-chip recovery? A chip is measured "
        "once per code period, so every doubling of the record adds 3 dB of combining gain - in "
        "principle. This section measures where the floor actually is, one C/N0 bisection per record "
        "length, at the same 12 PRNs and 15 flipped chips as the assignment.",
        "",
    ]
    if problem:
        lines.extend([problem, ""])
        return lines
    lines.extend(
        [
            "### Minimal C/N0 per duration",
            "",
            "`half` is the C/N0 where recovery stops being a coin flip (the 50% crossing, "
            "interpolated between the probes that bracket it); `reliable` is the located edge at the "
            "criterion; `band` is the C/N0 range between them. The supplied recordings are 8 ms "
            "(marked on the scatter). Read `half` with the scatter beside it: it is a linear "
            "interpolation, so it is only as precise as the gap between the two probes either side of "
            "it - at 2 ms that gap is the widest, so its band is the least certain end of the table.",
            "",
            "| code periods | duration | half at | reliable at | band | rate there | 95% interval "
            "| first failure |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for index, record in enumerate(records):
        periods_count = periods[index]
        marked = f"**{periods_count}**" if periods_count == ASSIGNMENT_PERIODS else f"{periods_count}"
        if record["error"]:
            lines.append(
                f"| {marked} | {periods_count} ms | **bracket wrong** | {record['error']} | | | | |"
            )
            continue
        passing, breaking = record["located"]
        passes = next((p for value, p, _ in record["trace"] if value == passing), None)
        if passes is None:
            passes = record["good_probe"][0]
        low, high = wilson_interval(passes, signals)
        half = _half_rate_cn0(_probes_of(record), signals)
        half_cell = f"{half:g} dB-Hz" if half is not None else "below the probes"
        band_cell = f"{passing - half:.2f} dB" if half is not None else "n/a"
        lines.append(
            f"| {marked} | {periods_count} ms | {half_cell} | **{passing:g} dB-Hz** | {band_cell} | "
            f"{passes}/{signals} = {100 * passes / signals:.0f}% | "
            f"{100 * low:.0f}% to {100 * high:.0f}% | {breaking:g} dB-Hz |"
        )
    located = [
        (periods[index], record["located"][0])
        for index, record in enumerate(records)
        if record["located"]
    ]
    if len(located) > 1:
        first, last = located[0], located[-1]
        per_doubling = (first[1] - last[1]) / (np.log2(last[0]) - np.log2(first[0]))
        lines.extend(
            [
                "",
                f"From {first[0]} to {last[0]} code periods the floor moves {first[1] - last[1]:.2f} dB, "
                f"which is **{per_doubling:.2f} dB per doubling** of the record (3 dB is what perfect "
                f"coherent combining of one more chip measurement per period would give).",
            ]
        )
    lines.extend(
        [
            "",
            "### Scatter, C/N0 against duration",
            "",
            *(_text_scatter(records, periods, signals, criterion)),
            "",
        ]
    )
    try:
        figure.parent.mkdir(parents=True, exist_ok=True)
        figure.write_text(_scatter_svg(records, periods, signals, criterion), encoding="utf-8")
        lines.extend([f"The same scatter as a picture: [`{figure.as_posix()}`]({figure.as_posix()}).", ""])
    except OSError as error:
        lines.extend([f"The SVG could not be written ({error}); the text scatter above is the data.", ""])
    probes = sum(len(record["trace"]) + 2 for record in records)
    measured = sum(record["seconds"] for record in records)
    lines.extend(
        [
            "### Cost",
            "",
            f"{len(records)} durations, {probes} probes, {signals} signals per probe: "
            f"{probes * signals} recordings scored in {measured / 60:.1f} min "
            f"({measured / max(probes * signals, 1):.2f} s per recording).",
            "",
        ]
    )
    return lines


def report_sections() -> list:
    """Both measured sections, in report order, rendered from the caches alone."""
    return cached_section() + duration_section()


def write_into(path: Path, sections: list) -> None:
    """Replace every measured section in `path`, keeping all the sweeps above them untouched."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    above = text.split(SECTION_HEADING)[0].rstrip()
    body = "\n".join(sections)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((above + "\n\n" if above else "") + body + "\n", encoding="utf-8")


def measure_axes(axes: dict, signals: int, criterion: float, cache_path: Path) -> tuple:
    """Bisect every axis, printing each probe, saving the cache after each one; return (records, s)."""
    cache = load_cache(cache_path)
    if any(
        entry.get("signals") != signals or entry.get("criterion") != criterion
        for entry in cache.values()
    ):
        # a different signal count or criterion is a different experiment: never mix the two
        cache = {}
    started = time.perf_counter()
    records = []
    for name, axis in axes.items():
        print(f"\n## {name}: {axis.question}", flush=True)
        record = locate(axis, signals, criterion, cache)
        save_cache(cache, cache_path)
        if record["error"]:
            print(f"  {record['error']}", flush=True)
        else:
            for value, passes, _ in sorted(record["trace"]):
                print(f"  {value:>8g} {axis.unit:<12} {passes:>3}/{signals}", flush=True)
            passing, breaking = record["located"]
            print(
                f"  edge between {passing:g} and {breaking:g} {axis.unit} ({record['seconds']:.0f} s)",
                flush=True,
            )
        records.append(record)
    return records, time.perf_counter() - started


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bisect each axis for the value where exact recovery stops, over many signals."
    )
    parser.add_argument("--signals", type=int, default=100, help="independent recordings per probe")
    parser.add_argument(
        "--criterion",
        type=float,
        default=0.95,
        help="fraction of signals that must recover for a value to count as still working",
    )
    parser.add_argument("--axes", nargs="*", default=None, help=f"axes to probe: {sorted(AXES)}")
    parser.add_argument("--cache", default=str(CACHE_PATH), help="probe cache, so a rerun is cheap")
    parser.add_argument(
        "--duration",
        action="store_true",
        help="measure the duration-against-C/N0 experiment instead of the break-point axes",
    )
    parser.add_argument(
        "--duration-cache",
        default=str(DURATION_CACHE),
        help="probe cache for the duration experiment",
    )
    parser.add_argument("--report", default=str(REPORT_PATH), help="report whose sections are replaced")
    arguments = parser.parse_args(argv)

    if arguments.duration:
        records, total = measure_axes(
            duration_axes(), arguments.signals, arguments.criterion, Path(arguments.duration_cache)
        )
    else:
        records, total = measure_axes(
            {name: AXES[name] for name in (arguments.axes or AXES)},
            arguments.signals,
            arguments.criterion,
            Path(arguments.cache),
        )

    # both measured sections are rewritten together: they are the last thing in the report and one
    # command must never leave the other one stale or duplicated
    report_path = Path(arguments.report)
    write_into(report_path, report_sections())
    print(f"\n-> {report_path} (measured sections rewritten)")
    print(
        json.dumps(
            {
                "axes": len(records),
                "recordings": sum(len(record["trace"]) + 2 for record in records)* arguments.signals,
                "seconds": round(total),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
