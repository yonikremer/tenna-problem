"""Code phase of one satellite: coarse from a single period, then refined sub-sample.

Why not align on the whole recording at once? A navigation data bit may change inside the record.
A whole-record coherent sum then partly cancels, its peak collapses, and the alignment it reports is
wrong - the very event being looked for would be hidden. A single code period is short enough to
hold one sign, so its peak stays sharp, and the sub-sample refinement maximises total segment energy,
which is insensitive to a sign change.
"""

import numpy as np

from .lattice import Lattice
from .signals import carrier, spreading_code_replica

SUBSAMPLE_SPAN = 1.0
SUBSAMPLE_STEP = 0.1


def alignment_shift(samples: np.ndarray, satellite: int, lattice: Lattice, doppler_hz: float) -> float:
    """Code-phase shift in samples, from the strongest single code period."""
    per_period = lattice.samples_per_code_period
    windows = len(samples) // per_period
    block = samples[: windows * per_period].reshape(windows, per_period)
    times = np.arange(per_period) / lattice.sample_rate_hz
    spectrum = np.conj(np.fft.fft(spreading_code_replica(satellite, per_period, lattice)))
    power = np.array(
        [
            np.abs(np.fft.ifft(spectrum * np.fft.fft(window * np.exp(-2j * np.pi * doppler_hz * times)))) ** 2
            for window in block
        ]
    )
    row, column = np.unravel_index(int(np.argmax(power)), power.shape)
    below = power[row, (column - 1) % per_period]
    at = power[row, column]
    above = power[row, (column + 1) % per_period]
    curvature = below - 2.0 * at + above
    offset = 0.0 if curvature >= 0 else 0.5 * (below - above) / curvature
    return float((column + offset) % per_period)


def code_period_segments(
    samples: np.ndarray, satellite: int, lattice: Lattice, doppler_hz: float, shift_samples: float
):
    """Cut the carrier- and code-wiped record at code boundaries: (sample count, complex sum)."""
    length = len(samples)
    code = spreading_code_replica(
        satellite, length, lattice, None, -shift_samples * lattice.code_phase_increment
    )
    times = np.arange(length) / lattice.sample_rate_hz
    product = samples * np.exp(-2j * np.pi * doppler_hz * times) * code

    edge = shift_samples
    bounds = [0]
    if edge > 0.5:
        bounds.append(int(round(edge)))
    while edge + lattice.samples_per_code_period < length - 0.5:
        edge += lattice.samples_per_code_period
        bounds.append(int(round(edge)))
    bounds.append(length)

    segments = []
    for start, stop in zip(sorted(set(bounds))[:-1], sorted(set(bounds))[1:], strict=False):
        if stop - start > 0:
            segments.append((stop - start, product[start:stop].sum()))
    return segments


def refine_alignment(
    samples: np.ndarray,
    satellite: int,
    lattice: Lattice,
    doppler_hz: float,
    shift_samples: float,
    span: float = SUBSAMPLE_SPAN,
    step: float = SUBSAMPLE_STEP,
) -> float:
    """Sub-sample alignment that maximises total segment energy."""
    best_shift, best_energy = shift_samples, -1.0
    for offset in np.arange(-span, span + 0.5 * step, step):
        candidate = shift_samples + offset
        segments = code_period_segments(samples, satellite, lattice, doppler_hz, candidate)
        energy = sum(abs(total) ** 2 for _, total in segments)
        if energy > best_energy:
            best_shift, best_energy = candidate, energy
    return best_shift


def aligned_shift(
    samples: np.ndarray, satellite: int, lattice: Lattice, doppler_hz: float
) -> float:
    """Coarse-then-refined code phase: the pair every downstream stage needs."""
    coarse = alignment_shift(samples, satellite, lattice, doppler_hz)
    return refine_alignment(samples, satellite, lattice, doppler_hz, coarse)


__all__ = [
    "alignment_shift",
    "refine_alignment",
    "aligned_shift",
    "code_period_segments",
    "carrier",
]
