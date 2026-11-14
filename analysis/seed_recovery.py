"""Recover the generator of recording 1 from its declared `random_seed`.

The file says `random_seed = 20261111` and that the noise is "independent CN(0,N0*Fs)". If that seed
drives a standard generator, the noise in the file is a deterministic function of it, and finding where
that function starts settles the whole recording: the noise can be subtracted, leaving the signal at
infinite signal-to-noise, and every parameter can then be measured instead of estimated.

The scan tries the two layouts a NumPy generator is usually used in, and reports the offset that
matches. Correlation is enough: white noise at the right offset correlates with the recording at ~1.0,
anything else at ~1/sqrt(samples).

Usage:
    python -m analysis.seed_recovery
"""

import sys

import netCDF4
import numpy as np

from gnss import alignment, chips, signals
from gnss.acquisition import acquire, parse_satellite_spec
from gnss.rule import fibonacci_base, rule_flips

DEFAULT_RECORDINGS = ("data/gnss_observation.nc",)
OFFSETS = 4096


def load(path: str) -> tuple:
    with netCDF4.Dataset(path) as dataset:
        samples = np.array(dataset["i"][:], dtype=np.float64) + 1j * np.array(
            dataset["q"][:], dtype=np.float64
        )
        seed = getattr(dataset, "random_seed", None)
    return samples, (int(seed) if seed is not None else None)


def fitted_model(samples: np.ndarray, path: str) -> np.ndarray:
    """The 12-satellite model of the recording, from the package's own estimates."""
    found = acquire(path, parse_satellite_spec("1-12"))
    units, coefficients = {}, {}
    for prn, detection in found.detected.items():
        shift = alignment.aligned_shift(samples, prn, found.lattice, detection.doppler_hz)
        units[prn] = signals.unit_signal(
            len(samples), prn, found.lattice, detection.doppler_hz, shift,
            detection.bit_change_period,
        )
        coefficients[prn] = np.vdot(units[prn], samples) / len(samples)
    return signals.reconstruct(coefficients, units)


def correlation(a: np.ndarray, b: np.ndarray) -> float:
    left = a - a.mean()
    right = b - b.mean()
    return float(abs(np.vdot(left, right)) / (np.linalg.norm(left) * np.linalg.norm(right)))


def scan(recording: str, offsets: int = OFFSETS) -> dict:
    samples, seed = load(recording)
    if seed is None:
        raise SystemExit(f"{recording} declares no random_seed")
    length = len(samples)
    residual = samples - fitted_model(samples, recording)
    generator = np.random.default_rng(seed)
    stream = generator.standard_normal(2 * length + 2 * offsets)

    window = 1024
    target = residual[:window]
    best = {}
    for layout in ("interleaved", "block"):
        scores = []
        for offset in range(offsets):
            if layout == "interleaved":
                candidate = (
                    stream[2 * offset: 2 * offset + 2 * window: 2]
                    + 1j * stream[2 * offset + 1: 2 * offset + 2 * window: 2]
                ) / np.sqrt(2.0)
            else:
                candidate = (
                    stream[offset: offset + window] + 1j * stream[length + offset: length + offset + window]
                ) / np.sqrt(2.0)
            scores.append(correlation(candidate, target))
        scores = np.array(scores)
        best[layout] = (int(np.argmax(scores)), float(scores.max()))
    return {"recording": recording, "seed": seed, "best": best, "residual": residual, "length": length}


def verify(recording: str, offset: int, length: int) -> None:
    """Rebuild the noise at the winning offset, then score the signal models against the recording.

    Two models are compared on the noise-free signal: the nominal spreading code, and the recovered
    code with each PRN's fifteen flipped chips. The second is the answer; the first is what a reader
    who ignores the flips would fit.
    """
    samples, seed = load(recording)
    stream = np.random.default_rng(seed).standard_normal(2 * length + offset)
    noise = (stream[offset: offset + length] + 1j * stream[length + offset: length + offset + length]
             ) / np.sqrt(2.0)
    signal = samples - noise
    found = acquire(recording, parse_satellite_spec("1-12"))
    lattice = found.lattice
    dopplers = {prn: detection.doppler_hz for prn, detection in found.detected.items()}
    shifts = {
        prn: float(round(alignment.aligned_shift(samples, prn, lattice, doppler)))
        for prn, doppler in dopplers.items()
    }
    base = frozenset(fibonacci_base())
    flips = {prn: frozenset(rule_flips(base, 2, prn)) for prn in dopplers}

    def build(modified: bool) -> dict:
        if not modified:
            return {prn: signals.unit_signal(length, prn, lattice, dopplers[prn], shifts[prn])
                    for prn in dopplers}
        return {
            prn: signals.flipped_replica(prn, length, lattice, shifts[prn], flips[prn])
            * signals.carrier(length, lattice, dopplers[prn])
            for prn in dopplers
        }

    def score(label: str, modified: bool) -> float:
        units = build(modified)
        coefficients = {prn: np.vdot(unit, signal) / length for prn, unit in units.items()}
        leftover = signal - signals.reconstruct(coefficients, units)
        model = signals.reconstruct(coefficients, units)
        print(f"  {label}: leftover {np.mean(np.abs(leftover)**2):.2e} of received "
              f"{np.mean(np.abs(samples)**2):.4f}, correlation with the recording "
              f"{correlation(samples, model + noise):.6f}")
        return np.mean(np.abs(leftover) ** 2)

    print(f"  noise stream offset {offset}: I = draws 0..N, Q = draws N..2N, scale 1/sqrt(2)")
    score("nominal spreading code", modified=False)
    score("recovered 15-flip code", modified=True)

    units = build(modified=True)
    coefficients = {prn: np.vdot(unit, signal) / length for prn, unit in units.items()}
    with netCDF4.Dataset(recording) as dataset:
        declared = float(np.sqrt(getattr(dataset, "per_prn_signal_power", np.nan)))
    amplitudes = np.array([
        abs(np.vdot(units[prn], signals.cleaned(signal, coefficients, units, prn))) / length
        for prn in units
    ])
    print(f"  amplitude with the other eleven removed: {amplitudes.min():.4f} to "
          f"{amplitudes.max():.4f}, declared {declared:.4f}, mean ratio "
          f"{amplitudes.mean() / declared:.4f}")
    exact = 0
    worst = 0.0
    for prn in sorted(units):
        clean = signals.cleaned(signal, coefficients, units, prn)
        values = np.real(
            chips.align(chips.chip_periods(clean, prn, lattice, dopplers[prn], shifts[prn])
                        .mean(axis=(0, 2)))
        )
        amplitude = np.median(np.abs(values))
        negative = set(np.flatnonzero(values < 0).tolist())
        exact += int(negative == set(flips[prn]))
        worst = max(worst, float(np.max(np.abs(np.abs(values) - amplitude)) / amplitude))
    print(f"  chip readout on the noise-free signal: {exact} of {len(units)} PRNs read exactly the "
          f"fifteen rule positions, worst chip deviation {worst:.3f} of the amplitude")


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        result = scan(recording)
        print(f"\n{recording}: seed {result['seed']}, {result['length']} samples")
        for layout, (offset, score) in result["best"].items():
            print(f"  {layout:>12} layout: best |correlation| {score:.4f} at offset {offset}")
        offset, score = result["best"]["block"]
        if score > 0.5:
            verify(recording, offset, result["length"])
        else:
            print("  no offset matches the recording; the declared seed does not drive this noise")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
