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

from gnss import alignment, signals
from gnss.acquisition import acquire, parse_satellite_spec

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
    """Rebuild the noise at the winning offset and check the signal that is left against the metadata."""
    samples, seed = load(recording)
    stream = np.random.default_rng(seed).standard_normal(2 * length + offset)
    noise = (stream[offset: offset + length] + 1j * stream[length + offset: length + offset + length]
             ) / np.sqrt(2.0)
    signal = samples - noise
    found = acquire(recording, parse_satellite_spec("1-12"))
    units, coefficients = {}, {}
    for prn, detection in found.detected.items():
        shift = alignment.aligned_shift(samples, prn, found.lattice, detection.doppler_hz)
        units[prn] = signals.unit_signal(
            length, prn, found.lattice, detection.doppler_hz, shift, detection.bit_change_period
        )
        coefficients[prn] = np.vdot(units[prn], signal) / length
    leftover = signal - signals.reconstruct(coefficients, units)
    with netCDF4.Dataset(recording) as dataset:
        declared = float(np.sqrt(getattr(dataset, "per_prn_signal_power", np.nan)))
    # the amplitude of a satellite must be measured with the other eleven removed: projecting one
    # satellite against the uncleaned composite picks up the others' cross-correlation and reads
    # about 4% low
    amplitudes = np.array([
        abs(np.vdot(units[prn], signals.cleaned(signal, coefficients, units, prn))) / length
        for prn in units
    ])
    print(f"  noise stream offset {offset}, I = draws 0..N, Q = draws N..2N, scale 1/sqrt(2)")
    print(f"  amplitudes from the noise-free signal {amplitudes.min():.4f} to {amplitudes.max():.4f}, "
          f"declared {declared:.4f}, mean ratio {amplitudes.mean() / declared:.4f}")
    print(f"  leftover after the 12-satellite model: {np.mean(np.abs(leftover)**2):.5f} "
          f"of {np.mean(np.abs(signal)**2):.4f} signal power")

    # the leftover is a second noise term; identify it by its correlation structure
    lags = [abs(np.vdot(leftover[:-k], leftover[k:])) / np.vdot(leftover, leftover) for k in range(1, 5)]
    simulated = np.repeat(np.random.default_rng(1).standard_normal(length // 4 + 1), 4)[:length]
    hold = [abs(np.vdot(simulated[:-k], simulated[k:])) / np.vdot(simulated, simulated)
            for k in range(1, 5)]
    print(f"  leftover autocorrelation at lags 1-4: {np.round(lags, 3)}")
    print(f"  a chip-rate hold held 4x would give:  {np.round(hold, 3)}")
    print(f"  leftover period-folded power {np.mean(np.abs(leftover.reshape(-1, 4092).mean(axis=0))**2):.5f}"
          f" (a satellite signal folds coherently, noise does not)")

    # is that second term the next draws of the same stream?
    held = leftover.reshape(-1, 4).mean(axis=1)
    tail = np.random.default_rng(seed).standard_normal(2 * length + 4 * len(held))[2 * length:]
    candidate = (tail[: len(held)] + 1j * tail[len(held): 2 * len(held)]) / np.sqrt(2.0)
    print(f"  correlation of that term with the next draws of the same stream: "
          f"{correlation(candidate, held):.4f} (0 = not from this stream)")


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
