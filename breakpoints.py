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
# The figure is written once per theme, so the SVG carries its own background instead of relying on
# the page behind it: assets/cn0_vs_duration_light.svg and _dark.svg.
DURATION_FIGURE = Path("assets/cn0_vs_duration")

# One palette per theme. The data colours (green, amber, red) are darkened for white and lightened for
# the dark sheet, so both sheets clear the same contrast bar against their own background.
SCATTER_PALETTES = {
    "light": {
        "bg": "#ffffff",
        "ink": "#1f2328",
        "muted": "#57606a",
        "annotation": "#414a53",
        "grid": "#f2f4f7",
        "axis": "#d0d7de",
        "edge": "#0969da",
        "dots": {"#": "#1a7f37", "o": "#9a6700", ".": "#d1242f"},
        "bands": (("#b8dcd2", "#0f766e"), ("#dbccf8", "#6d28d9")),
    },
    "dark": {
        "bg": "#16181c",
        "ink": "#e6e8eb",
        "muted": "#a3aab2",
        "annotation": "#c2c8d0",
        "grid": "#2a2f35",
        "axis": "#3a4048",
        "edge": "#539bf5",
        "dots": {"#": "#4ac26b", "o": "#d4a72c", ".": "#ff7b72"},
        "bands": (("#1f4038", "#34b3a0"), ("#3a2f57", "#a371f7")),
    },
}
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

# The C/N0 each supplied recording actually spans over its twelve PRNs, measured with
#   python -m gnss.acquisition data/gnss_observation.nc --satellites 1-32   (and ...2.nc)
# They are drawn as horizontal bands so the figure answers the question a reader actually has: are
# our signals above the edge at our record length?
OBSERVATIONS = (
    ("recording 1", 54.1, 54.9),
    ("recording 2", 44.1, 48.0),
)


def _probes_of(record: dict) -> list:
    """Every (C/N0, rate) this axis actually probed, bracket ends included."""
    points = [(record["passing"], record["good_probe"][0])]
    points += [(value, passes) for value, passes, _ in record["trace"]]
    points.append((record["breaking"], record["bad_probe"][0]))
    return points


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


def _svg_legend(
    parts: list,
    left: float,
    height: float,
    colours: dict,
    criterion: float,
    signals: int,
    edge_colour: str,
    annotation: str,
    muted: str,
    observations=(),
    bands=(),
) -> None:
    """Two rows underneath the plot: what a mark means, then the annotations.

    The counts are spelled out rather than described as "half" and "above", so a reader does not
    have to hold the criterion in their head: with 100 recordings per point and the 95% criterion
    the rows read 95-100, 50-94 and 0-49 fully recovered. The edge marker gets its own entry: it is
    not a probe, and a reader who cannot find a mark in the legend has to guess what it means.
    """
    at_criterion = round(criterion * signals)
    half = signals // 2
    rows = [
        [
            ("dot", colours["#"], f"{at_criterion}-{signals} of {signals} fully recovered"),
            ("dot", colours["o"], f"{half}-{at_criterion - 1} of {signals} fully recovered"),
            ("dot", colours["."], f"0-{half - 1} of {signals} fully recovered"),
        ],
        [
            ("rule", annotation, "our record length"),
            ("dash", edge_colour, "located edge"),
            ("bracket", edge_colour, "edge marker"),
        ],
    ]
    if observations:
        rows.append(
            [
                ("swatch", bands[index % len(bands)][0], f"{label}: {low:g} to {high:g} dB-Hz")
                for index, (label, low, high) in enumerate(observations)
            ]
        )
    for row, entries in enumerate(rows):
        y = height - 62 + row * 24
        x = left
        for kind, colour, label in entries:
            if kind == "dot":
                parts.append(f'<circle cx="{x + 5:.1f}" cy="{y - 4}" r="3.4" fill="{colour}"/>')
            elif kind == "ring":
                parts.append(
                    f'<circle cx="{x + 5:.1f}" cy="{y - 4}" r="3.4" fill="none" '
                    f'stroke="{colour}" stroke-width="1.6"/>'
                )
            elif kind == "bound":
                parts.append(
                    f'<circle cx="{x + 5:.1f}" cy="{y - 4}" r="3.0" fill="none" '
                    f'stroke="{colour}" stroke-width="1.2"/>'
                )
            elif kind == "swatch":
                parts.append(
                    f'<rect x="{x:.1f}" y="{y - 8}" width="10" height="8" fill="{colour}"/>'
                )
            elif kind == "bracket":
                parts.append(
                    f'<line x1="{x:.1f}" y1="{y - 4}" x2="{x + 4.5:.1f}" y2="{y - 4}" '
                    f'stroke="{colour}" stroke-width="2"/>'
                )
                parts.append(
                    f'<line x1="{x + 9.5:.1f}" y1="{y - 4}" x2="{x + 14:.1f}" y2="{y - 4}" '
                    f'stroke="{colour}" stroke-width="2"/>'
                )
            else:
                parts.append(
                    f'<line x1="{x:.1f}" y1="{y - 4}" x2="{x + 14:.1f}" y2="{y - 4}" '
                    f'stroke="{colour}" stroke-width="2.5" stroke-dasharray="7 5"/>'
                )
            parts.append(
                f'<text x="{x + 22:.1f}" y="{y}" font-size="13" fill="{muted}">{label}</text>'
            )
            x += 26 + 7.5 * len(label)


def _scatter_svg(
    records: list, periods: list, signals: int, criterion: float, palette: dict | None = None
) -> str:
    """The same scatter as an SVG, so it can be looked at rather than read.

    Hand-written, because the figure has to be produced by an environment that has nothing but
    numpy. Layout decisions that are not obvious:

    - The plotted range is 38 to 72 dB-Hz, wider than the 40 to 70 the axis is labelled with, so a
      probe at either end is drawn whole instead of being cut in half by the frame.
    - Grid lines go down first and the two recording bands over them, so a band never looks like a
      doubled rule where a grid line falls inside it.
    - The bands run the full width. A band is a C/N0 level, and C/N0 does not depend on how long
      the record is, so the level holds at every duration on the axis; the vertical rule, not the
      band's extent, marks the 8 ms of the supplied files. Reading where the dashed edge crosses a
      band therefore means something real: at 2 code periods that level is under the floor.
    - The located edge is a bracket with a gap, not a circle around the point: near the edge the
      probes are closer together than a marker is wide, so a ring would swallow three or four of
      them, including ones of another class.
    - Every probe is drawn the same way, including the two ends of the bracket: each is 100 real
      recordings, so the only thing that differs is its pass rate, carried by colour. Each dot has
      a halo in the sheet's own background colour, because neighbouring probes are closer together
      than a marker is wide and would otherwise over-paint each other.
    """
    low, high = 38.0, 72.0
    width, height = 900, 544
    left, right, top, bottom = 84, 28, 112, 140  # room for the axis title and three legend rows
    plot_width = width - left - right
    plot_height = height - top - bottom
    colours_theme = palette or SCATTER_PALETTES["light"]
    edge_colour = colours_theme["edge"]
    annotation = colours_theme["annotation"]
    grid_colour = colours_theme["grid"]
    ink, muted = colours_theme["ink"], colours_theme["muted"]

    spans = np.log2(periods)
    span = float(spans.max() - spans.min())

    def x_of(count: int) -> float:
        if span == 0.0:  # a single duration has no axis to spread over
            return float(left + plot_width / 2)
        return float(left + (np.log2(count) - spans.min()) / span * plot_width)

    def y_of(cn0: float) -> float:
        return float(top + (high - cn0) / (high - low) * plot_height)

    bottom_of_plot = top + plot_height
    description = (
        "C/N0 per PRN needed for exact recovery of a 15-chip mask, against record length in code "
        f"periods from {periods[0]} to {periods[-1]}. Each dot is {signals} independent recordings "
        "at that point. The top and bottom dot of each column are the ends of the searched range."
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="duration-figure-title" '
        f'font-family="system-ui, -apple-system, Segoe UI, sans-serif">',
        '<title id="duration-figure-title">Longer records read weaker signals</title>',
        f"<desc>{description}</desc>",
        f'<rect width="{width}" height="{height}" fill="{colours_theme["bg"]}"/>',
        f'<text x="28" y="36" font-size="17" font-weight="600" fill="{ink}">'
        f"Longer records read weaker signals</text>",
        f'<text x="28" y="58" font-size="14" fill="{muted}">'
        f"{signals} recordings per point, all 15 chips exact, 12 PRNs</text>",
        f'<text x="28" y="76" font-size="14" fill="{muted}">'
        f"C/N0 needed for full recovery, by record length &#183; our two recordings shaded</text>",
    ]

    # grid first: the bands are washes and must not be cut by a grid line
    cn0_tick = 40.0
    while cn0_tick <= 70.0 + 1e-9:
        y = y_of(cn0_tick)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
            f'stroke="{grid_colour}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-size="13" '
            f'fill="{muted}">{cn0_tick:g}</text>'
        )
        cn0_tick += 5.0

    band_start = left
    band_width = plot_width
    observation_colours = colours_theme["bands"]
    for index, (_, observation_low, observation_high) in enumerate(OBSERVATIONS):
        tint, band_ink = observation_colours[index % len(observation_colours)]
        y_top, y_bottom = y_of(observation_high), y_of(observation_low)
        parts.append(
            f'<rect x="{band_start:.1f}" y="{y_top:.1f}" width="{band_width:.1f}" '
            f'height="{y_bottom - y_top:.1f}" fill="{tint}"/>'
        )
        for edge in (y_top, y_bottom):
            parts.append(
                f'<line x1="{band_start:.1f}" y1="{edge:.1f}" x2="{left + plot_width}" '
                f'y2="{edge:.1f}" stroke="{band_ink}" stroke-opacity="0.6" stroke-width="1"/>'
            )

    parts += [
        f'<line x1="{left}" y1="{bottom_of_plot}" x2="{left + plot_width}" y2="{bottom_of_plot}" '
        f'stroke="{colours_theme["axis"]}"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom_of_plot}" '
        f'stroke="{colours_theme["axis"]}"/>',
    ]
    for count in periods:
        x = x_of(count)
        ours = count == ASSIGNMENT_PERIODS
        parts.append(
            f'<text x="{x:.1f}" y="{bottom_of_plot + 22}" text-anchor="middle" font-size="13" '
            f'font-weight="{"600" if ours else "400"}" '
            f'fill="{annotation if ours else muted}">{count}</text>'
        )
    parts += [
        f'<text x="{left + plot_width / 2:.0f}" y="{bottom_of_plot + 44}" text-anchor="middle" '
        f'font-size="13" fill="{muted}">record length in code periods (log scale) &#183; '
        f"1 period = 1 ms</text>",
        f'<text transform="translate(26 {top + plot_height / 2:.0f}) rotate(-90)" '
        f'text-anchor="middle" font-size="13" fill="{muted}">'
        f"C/N0 needed for exact recovery (dB-Hz)</text>",
    ]

    if ASSIGNMENT_PERIODS in periods:
        column = x_of(ASSIGNMENT_PERIODS)
        parts.append(
            f'<line x1="{column:.1f}" y1="{top}" x2="{column:.1f}" y2="{bottom_of_plot}" '
            f'stroke="{annotation}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{column:.1f}" y="{top - 10}" text-anchor="middle" font-size="13" '
            f'font-weight="600" fill="{annotation}">our recordings: {ASSIGNMENT_PERIODS} ms</text>'
        )

    colours = colours_theme["dots"]
    edges = [
        (x_of(periods[index]), y_of(record["located"][0]))
        for index, record in enumerate(records)
        if record.get("located")
    ]
    # the trend goes under the marks, so it never cuts a dot in half
    if len(edges) > 1:
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in edges)
        parts.append(
            f'<polyline points="{path}" fill="none" stroke="{edge_colour}" stroke-width="2.5" '
            f'stroke-dasharray="7 5" stroke-linecap="round"/>'
        )

    background = colours_theme["bg"]
    for index, record in enumerate(records):
        if record["error"]:
            continue
        x = x_of(periods[index])
        located = record["located"][0] if record.get("located") else None
        probes = _probes_of(record)
        # Probes converge on a tenth of a decibel, which is a fraction of a marker: without a
        # background halo a column near the edge is one smear of over-painted dots. The nearest
        # probe to the edge is painted last, so the mark the column is about stays on top.
        order = sorted(
            probes,
            key=lambda item: -abs(item[0] - located) if located is not None else 0.0,
        )
        for cn0, passes in order:
            y = y_of(cn0)
            glyph = _glyph(passes, signals, criterion)
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{colours[glyph]}" '
                f'stroke="{background}" stroke-width="1.2"/>'
            )
        if record.get("located"):
            y = y_of(record["located"][0])
            for offset in (-9.0, 4.0):
                parts.append(
                    f'<line x1="{x + offset:.1f}" y1="{y:.1f}" x2="{x + offset + 5:.1f}" '
                    f'y2="{y:.1f}" stroke="{edge_colour}" stroke-width="2.5"/>'
                )

    _svg_legend(
        parts,
        left,
        height,
        colours,
        criterion,
        signals,
        edge_colour,
        annotation,
        muted,
        observations=OBSERVATIONS,
        bands=observation_colours,
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
            "`minimal C/N0` is the lowest value at which the criterion still holds; `first failure` "
            "is the next probe down, so the edge is bracketed between the two. The supplied "
            "recordings are 8 ms, marked on the figure.",
            "",
            "| code periods | duration | minimal C/N0 | rate there | 95% interval | first failure |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for index, record in enumerate(records):
        periods_count = periods[index]
        marked = f"**{periods_count}**" if periods_count == ASSIGNMENT_PERIODS else f"{periods_count}"
        if record["error"]:
            lines.append(
                f"| {marked} | {periods_count} ms | **bracket wrong** | {record['error']} | | |"
            )
            continue
        passing, breaking = record["located"]
        passes = next((p for value, p, _ in record["trace"] if value == passing), None)
        if passes is None:
            passes = record["good_probe"][0]
        low, high = wilson_interval(passes, signals)
        lines.append(
            f"| {marked} | {periods_count} ms | **{passing:g} dB-Hz** | "
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
        drawn = []
        for theme, palette in SCATTER_PALETTES.items():
            path = figure.with_name(f"{figure.name}_{theme}.svg")
            path.write_text(
                _scatter_svg(records, periods, signals, criterion, palette), encoding="utf-8"
            )
            drawn.append((theme, path))
        bands = ", ".join(f"{label} {low:g}-{high:g}" for label, low, high in OBSERVATIONS)
        links = ", ".join(
            f"[{theme}]({path.as_posix()})" for theme, path in drawn
        )
        lines.extend(
            [
                f"The same scatter as a picture, drawn once per page theme: {links}. The "
                f"two horizontal bands on it are the C/N0 each supplied recording spans over its "
                f"twelve PRNs ({bands} dB-Hz), measured with `python -m gnss.acquisition`.",
                "",
            ]
        )
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
