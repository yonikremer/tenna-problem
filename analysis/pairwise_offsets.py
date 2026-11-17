"""Pairwise circular cross-correlation of the PRN soft vectors: the route that did not work.

For every unordered pair of PRNs, correlate the two 1023-chip soft vectors circularly over all 1023
lags, with the mean removed, and read the winning lag. A pair "names" a lag only when the win is
decisive: the runner-up local maximum (outside the main peak's +/-2 chip window) must be at least 5%
lower, and the curve must fall at least 10% below its peak somewhere. The measured offsets are then
required to compose - the lag from PRN i to PRN k must be the lag from i to j plus the lag from j to k.

This is kept because it is the check that answers the obvious objection to the one-slope search: why
not measure every relative shift directly? The script prints why. On `data/gnss_observation.nc` all 66
pairs name a lag and the offsets compose to 2 chips per PRN. On `data/gnss_observation2.nc` many pairs
cannot name one, and even taking every pair's global maximum makes the offsets contradict each other.
The one-slope search combines all 12 vectors before choosing, which is the gain pairwise cannot get.

The solver does not use any of this. `gnss.rule.recover_rule` searches one slope; see `didnt_work.md`.

Usage:
    python -m analysis.pairwise_offsets                       # the two supplied recordings
    python -m analysis.pairwise_offsets data/file.nc          # one recording
"""

import dataclasses
import itertools
import statistics
import sys

import numpy as np

from gnss import acquisition, pipeline
from gnss.acquisition import parse_satellite_spec

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")
DEFAULT_SATELLITES = "1-12"

CODE_LENGTH = 1023
PEAK_LEAD_FRACTION = 0.05
CURVE_DIP_FRACTION = 0.10
PEAK_GUARD_CHIPS = 2


@dataclasses.dataclass(frozen=True)
class Measurement:
    """What one pair's correlation says: a lag when it can name one, else the reason it cannot."""

    lag: int | None
    lead: float | None
    reason: str | None

    @property
    def clear(self) -> bool:
        return self.reason is None


def circular_correlation(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """`curve[d] = sum_k left[k] * right[(k - d) mod N]`, with each vector's mean removed."""
    left = left - left.mean()
    right = right - right.mean()
    return np.real(np.fft.ifft(np.fft.fft(left) * np.conj(np.fft.fft(right))))


def local_maxima(curve: np.ndarray) -> list:
    """(lag, value) of every strict local maximum, on the circular lag axis."""
    left = np.roll(curve, 1)
    right = np.roll(curve, -1)
    peaks = (curve > left) & (curve >= right)
    return [(int(lag), float(curve[lag])) for lag in np.flatnonzero(peaks)]


def measure_curve(curve: np.ndarray, label: str) -> Measurement:
    """The one lag the curve names, or the measurement that stops it naming one."""
    peaks = local_maxima(curve)
    if not peaks:
        return Measurement(None, None, f"{label}: the cross-correlation has no peak anywhere")
    lag, peak = max(peaks, key=lambda peak: peak[1])
    if peak <= 0.0:
        return Measurement(
            lag,
            None,
            f"{label}: the cross-correlation has no positive peak anywhere (best {peak:.3f} at lag {lag})",
        )
    rivals = [
        (other_lag, value)
        for other_lag, value in peaks
        if min(abs(other_lag - lag), CODE_LENGTH - abs(other_lag - lag)) > PEAK_GUARD_CHIPS
    ]
    rival_lag, rival = max(rivals, key=lambda peak: peak[1]) if rivals else (None, None)
    lead = (peak - rival) / peak if rival is not None else None

    floor = float(curve.min())
    if floor > peak * (1.0 - CURVE_DIP_FRACTION):
        return Measurement(
            lag,
            lead,
            f"{label}: the cross-correlation has no minimum anywhere - it never falls more than "
            f"{CURVE_DIP_FRACTION:.0%} below its peak (peak {peak:.3f} at lag {lag}, floor "
            f"{floor:.3f}); the two patterns look alike at every lag, so the peak names no offset",
        )
    required = PEAK_LEAD_FRACTION * peak
    if rival is not None and peak - rival < required:
        return Measurement(
            lag,
            lead,
            f"{label}: two peaks are too close to name one offset - lag {lag} at {peak:.3f} vs "
            f"lag {rival_lag} at {rival:.3f}, a margin of {peak - rival:.3f} where at least "
            f"{required:.3f} is needed; refusing to pick one",
        )
    return Measurement(lag, lead, None)


def offset_between(offsets: dict, first: int, second: int) -> int:
    """Signed lag from `first` to `second`, from the unordered measurements."""
    if first == second:
        return 0
    lag = offsets[(first, second) if first < second else (second, first)]
    return lag if first < second else (-lag) % CODE_LENGTH


def composition_error(offsets: dict) -> str | None:
    """The first triple whose offsets do not add up, or None when every triple composes."""
    satellites = sorted({prn for pair in offsets for prn in pair})
    for first, middle, last in itertools.combinations(satellites, 3):
        if any(
            (low, high) not in offsets
            for low, high in ((first, middle), (middle, last), (first, last))
        ):
            continue
        stepped = (
            offset_between(offsets, first, middle) + offset_between(offsets, middle, last)
        ) % CODE_LENGTH
        direct = offset_between(offsets, first, last)
        if stepped != direct:
            return (
                f"PRN {first}->{middle} is {offset_between(offsets, first, middle)} chips and "
                f"{middle}->{last} is {offset_between(offsets, middle, last)}, but {first}->{last} "
                f"is {direct}, not {stepped}: the pairwise offsets do not compose"
            )
    return None


def common_step(offsets: dict) -> tuple:
    """(step per PRN, None) when one constant step fits, else (None, reason)."""
    satellites = sorted({prn for pair in offsets for prn in pair})
    steps = {
        offset_between(offsets, low, high) for low, high in itertools.pairwise(satellites)
    }
    if len(steps) > 1:
        return None, (
            f"the pairwise offsets do not share one step per PRN: consecutive steps "
            f"{sorted(steps)} chips"
        )
    return steps.pop() if steps else 0, None


def main(recordings=DEFAULT_RECORDINGS, satellites=DEFAULT_SATELLITES):
    search = parse_satellite_spec(satellites)
    for recording in recordings:
        found = acquisition.acquire(recording, search)
        per_satellite, _ = pipeline.soft_chip_vectors(found)
        vectors = {prn: satellite.vector for prn, satellite in per_satellite.items()}
        curves = {
            pair: circular_correlation(vectors[pair[0]], vectors[pair[1]])
            for pair in itertools.combinations(sorted(vectors), 2)
        }
        measured = {
            pair: measure_curve(curve, f"PRN {pair[0]} vs PRN {pair[1]}")
            for pair, curve in curves.items()
        }

        print(f"\n{recording}")
        print(f"  {len(vectors)} PRNs, {len(curves)} unordered pairs")
        clear = {pair: measurement.lag for pair, measurement in measured.items() if measurement.clear}
        print(f"  pairs that name one lag: {len(clear)}/{len(curves)}")
        leads = [m.lead for m in measured.values() if m.lead is not None]
        if leads:
            print(
                f"  peak lead over the runner-up: {min(leads):.3f} worst, "
                f"{statistics.median(leads):.3f} median"
            )

        failed = [m for m in measured.values() if not m.clear]
        if failed:
            print("  first pair that cannot name a lag:")
            print(f"    {failed[0].reason}")
        else:
            error = composition_error(clear)
            if error:
                print("  the clear offsets do not compose:")
                print(f"    {error}")
            else:
                step, error = common_step(clear)
                print(f"  offsets compose on every triple; common step {step} chips per PRN")

        # What happens if the clarity check is skipped and every pair simply takes its global maximum
        global_offsets = {
            pair: int(np.argmax(curve)) for pair, curve in curves.items()
        }
        error = composition_error(global_offsets)
        if error:
            print("  taking every pair's global maximum instead:")
            print(f"    {error}")
        else:
            step, _ = common_step(global_offsets)
            print(f"  taking every pair's global maximum gives the same step, {step} chips per PRN")


def self_check():
    """Synthetic slopes and the three refusals, so the script's own arithmetic is not taken on trust."""
    base = (34, 411, 644)
    vectors = {}
    for prn in (1, 2, 3):
        vector = np.ones(CODE_LENGTH)
        vector[[(chip - 2 * (prn - 1)) % CODE_LENGTH for chip in base]] = -1.0
        vectors[prn] = vector

    offsets = {
        pair: measure_curve(
            circular_correlation(vectors[pair[0]], vectors[pair[1]]),
            f"PRN {pair[0]} vs PRN {pair[1]}",
        ).lag
        for pair in itertools.combinations(sorted(vectors), 2)
    }
    if offsets != {(1, 2): 2, (1, 3): 4, (2, 3): 2}:
        raise SystemExit(f"pairwise offsets {offsets}, expected the 2-chip synthetic")
    if composition_error(offsets) is not None or common_step(offsets)[0] != 2:
        raise SystemExit("a known 2-chip synthetic slope did not compose")

    shoulder = np.zeros(CODE_LENGTH)
    shoulder[10] = 4.0
    shoulder[12] = 3.9
    if measure_curve(shoulder, "self-check").lag != 10:
        raise SystemExit("a shoulder inside the +/-2 chip window was treated as a rival")

    ambiguous = np.zeros(CODE_LENGTH)
    ambiguous[10] = 4.0
    ambiguous[40] = 3.95
    reason = measure_curve(ambiguous, "self-check").reason
    if reason is None or "two peaks are too close" not in reason:
        raise SystemExit(f"equal peaks were not refused: {reason}")

    flat = np.full(CODE_LENGTH, 1.0)
    flat[20] = 1.05
    reason = measure_curve(flat, "self-check").reason
    if reason is None or "no minimum anywhere" not in reason:
        raise SystemExit(f"a flat curve was not refused: {reason}")


if __name__ == "__main__":
    self_check()
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
