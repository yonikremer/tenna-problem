"""Locate where the recovery chain breaks on each axis, by bisection over 100 signals per point.

`benchmark.py` sweeps a fixed grid with two noise seeds per point. Two seeds can only report 0/2,
1/2 or 2/2, so the grid shows *that* a break exists but not *where*: the difference between a
method that works 100% of the time and one that works half the time is one row apart.

This script asks the sharper question. At one value of one axis it runs `--signals` independent
signals (100 by default) and measures the fraction that recovers exactly, then bisects on the value
until the passing end and the breaking end of the bracket are `resolution` apart. Every probe runs
the same seeds (common random numbers), so adjacent probes differ in the parameter and not in the
noise draw, and the located edge is a property of that seed set rather than of a lucky draw.

Three things make the answer honest:

  - The criterion is a rate, not a single run: the default is that at least 95 of 100 signals
    recover, which is the claim the benchmark's prose actually wants to make.
  - Binomial noise is quoted, not hidden: the Wilson interval of every probe is printed, and the
    resolution of each axis is chosen so the bisection does not pretend to be finer than the
    sampling allows (100 signals cannot resolve a rate better than about +-2 points near 95%).
  - The bracket is checked, not assumed. If the "known good" end does not reach the criterion, or
    the "known bad" end does, the run says so and stops instead of bisecting on nonsense.

Bisection needs the pass rate to be monotone between the two ends. Where the chain is not monotone
the two edges are searched separately: the PRN count fails both below a minimum (one PRN cannot
define a shared shift, and the combining gain that decides a chip is not there) and above a maximum
(a dense modification leaves too little of the nominal code to detect). Both edges are listed.

Usage:
    python breakpoints.py                       # every axis, 100 signals per probe
    python breakpoints.py --signals 50          # coarser and quicker
    python breakpoints.py --axes cn0 flip_count  # named axes only
    python breakpoints.py --out BREAKPOINTS.md
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
        build=lambda value, seed: Scenario(
            label=f"probe-seed{seed}", cn0_dbhz=value, seed=seed
        ),
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


def _speed_to_cover(doppler_hz: float) -> float:
    """Receiver speed whose search span reaches `doppler_hz`, with the benchmark's 5% headroom."""
    import benchmark

    return benchmark.receiver_speed_to_cover(doppler_hz)


def wilson_interval(passes: int, signals: int, z: float = 1.96) -> tuple:
    """95% interval of a binomial rate, which is the only honest error bar for a 100-signal probe."""
    if signals <= 0:
        return 0.0, 1.0
    rate = passes / signals
    denominator = 1.0 + z * z / signals
    centre = (rate + z * z / (2 * signals)) / denominator
    half = z * np.sqrt(rate * (1 - rate) / signals + z * z / (4 * signals * signals)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def measure(axis: Axis, value: float, signals: int, cache: dict) -> tuple:
    """Run `signals` independent recordings at one value; return (passes, seconds measured).

    A cached probe still reports the time it took when it was measured: the cost of the evidence
    does not disappear because a rerun is free.
    """
    key = f"{axis.name}@{value:g}"
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
    cache[key] = {"passes": passes, "signals": signals, "seconds": round(elapsed, 3)}
    return passes, elapsed


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


def locate(axis: Axis, signals: int, criterion: float, cache: dict) -> dict:
    """Bisect one axis, and check that both ends of the bracket behave as declared."""
    passes_good, seconds_good = measure(axis, axis.snap(axis.passing), signals, cache)
    passes_bad, seconds_bad = measure(axis, axis.snap(axis.breaking), signals, cache)
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
        def rate_of(value):
            passes, seconds = measure(axis, axis.snap(value), signals, cache)
            spent.append(seconds)
            return passes / signals

        passing, breaking, trace = bisect(
            axis.snap(axis.passing), axis.snap(axis.breaking), rate_of, criterion, axis.resolution
        )
        record["located"] = (passing, breaking)
        for value, rate in trace:
            passes, seconds = measure(axis, axis.snap(value), signals, cache)
            spent.append(seconds)
            record["trace"].append((axis.snap(value), passes, rate))
    # the cost of the probes, not the wall clock of this run: a cached probe still cost something
    record["seconds"] = sum(spent)
    return record


def report(records: list, signals: int, criterion: float, wall_seconds: float) -> list:
    """The located edge per axis, then the probes that located it."""
    lines = [
        "# Where the chain breaks, measured over independent signals",
        "",
        f"Generated with `python breakpoints.py --signals {signals}`. Each probe runs **{signals} "
        "independent recordings** (one per seed) at one value of one axis and counts how many "
        "recover exactly, then the value is bisected until the passing and breaking ends are one "
        "resolution apart. `benchmark.py` uses two seeds per point, which can only say 0/2, 1/2 or "
        "2/2; this can say 91 of 100.",
        "",
        f"A signal counts as recovered when the verdict is `pass`: every PRN found with no false "
        f"alarm, the shift right and the flip set exactly right. The criterion is "
        f"**{round(criterion * signals)} of {signals}** signals. Every probe reuses the same seeds, "
        "so adjacent probes differ in the parameter and not in the noise draw.",
        "",
        "## Located edges",
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
        lines.extend(["", f"## {record['axis']}", "", record["question"], ""])
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
            "## Cost",
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


def _interval_text(passes: int, signals: int) -> str:
    low, high = wilson_interval(passes, signals)
    return f"{100 * low:.0f}% to {100 * high:.0f}%"


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
    parser.add_argument("--out", default="BREAKPOINTS.md", help="markdown report to write")
    parser.add_argument("--cache", default=str(CACHE_PATH), help="probe cache, so a rerun is cheap")
    arguments = parser.parse_args(argv)

    selected = {name: AXES[name] for name in (arguments.axes or AXES)}
    cache_path = Path(arguments.cache)
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"cache {cache_path} is not usable ({error}); starting from scratch", flush=True)
            cache = {}
    if any(entry.get("signals") != arguments.signals for entry in cache.values()):
        # a different signal count is a different experiment: never mix the two
        cache = {}

    started = time.perf_counter()
    records = []
    for name, axis in selected.items():
        print(f"\n## {name}: {axis.question}", flush=True)
        record = locate(axis, arguments.signals, arguments.criterion, cache)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
        if record["error"]:
            print(f"  {record['error']}", flush=True)
        else:
            passing, breaking = record["located"]
            for value, passes, _ in sorted(record["trace"]):
                print(f"  {value:>8g} {axis.unit:<12} {passes:>3}/{arguments.signals}", flush=True)
            print(
                f"  edge between {passing:g} and {breaking:g} {axis.unit} ({record['seconds']:.0f} s)",
                flush=True,
            )
        records.append(record)

    total = time.perf_counter() - started
    lines = report(records, arguments.signals, arguments.criterion, total)
    Path(arguments.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n-> {arguments.out}")
    print(json.dumps({"axes": len(records), "recordings": sum(
        len(r["trace"]) + 2 for r in records) * arguments.signals, "seconds": round(total)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
