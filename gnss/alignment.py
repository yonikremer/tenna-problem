"""Code phase of one satellite: coarse from a single period, then refined sub-sample.

Why not align on the whole recording at once? A navigation data bit may change inside the record.
A whole-record coherent sum then partly cancels, its peak collapses, and the alignment it reports is
wrong - the very event being looked for would be hidden. A single code period is short enough to
hold one sign, so its peak stays sharp, and the sub-sample refinement maximises total segment energy,
which is insensitive to a sign change.
"""

import numpy as np

from .lattice import Lattice
from .signals import carrier, sample_times, spreading_code_replica, tiled_code_replica

SUBSAMPLE_SPAN = 1.0
SUBSAMPLE_STEP = 0.1
# Energies within this relative distance of the maximum are the same alignment: the objective is
# quantized to whole samples, so its differences inside one sample are numerical dust (0.1% in energy
# is 0.05% in amplitude, 0.004 dB), not evidence for one shift over another.
SUBSAMPLE_TIE = 1e-3


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
    code = tiled_code_replica(satellite, length, lattice, -shift_samples * lattice.code_phase_increment)
    times = sample_times(length, lattice.sample_rate_hz)
    product = samples * np.exp(-2j * np.pi * doppler_hz * times) * code
    return segment_totals(product, lattice, shift_samples)


def segment_totals(product: np.ndarray, lattice: Lattice, shift_samples: float):
    """The same cuts, on a record that is already carrier- and code-wiped."""
    length = len(product)
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
    """Sub-sample alignment that maximises total segment energy, tied towards the coarse estimate.

    The energy is not a smooth function of the shift: the code replica and the segment cuts both snap
    to the sample grid, so a whole neighbourhood of shifts scores the same and the maximum is a
    plateau about half a sample wide. Returning the first grid point of that plateau throws away the
    sub-sample accuracy of the coarse parabolic fit and makes the result depend on where the scan
    started. The plateau members are all equally consistent with the energy, so the one closest to the
    coarse estimate is returned, and the resolution of the whole stage stays at one sample (0.25
    chip) rather than being quoted to three decimals.
    """
    offsets = np.arange(-span, span + 0.5 * step, step)
    # the carrier is wiped once: only the code replica depends on the shift being scanned
    wiped = samples * np.exp(
        -2j * np.pi * doppler_hz * sample_times(len(samples), lattice.sample_rate_hz)
    )
    length = len(samples)
    energies = np.array([
        sum(
            abs(total) ** 2
            for _, total in segment_totals(
                wiped
                * tiled_code_replica(
                    satellite,
                    length,
                    lattice,
                    -(shift_samples + offset) * lattice.code_phase_increment,
                ),
                lattice,
                shift_samples + offset,
            )
        )
        for offset in offsets
    ])
    best = energies.max()
    if best <= 0.0:
        return shift_samples
    plateau = offsets[energies >= best * (1.0 - SUBSAMPLE_TIE)]
    return float(shift_samples + plateau[np.argmin(np.abs(plateau))])


def aligned_shift(
    samples: np.ndarray, satellite: int, lattice: Lattice, doppler_hz: float
) -> float:
    """Coarse-then-refined code phase: the pair every downstream stage needs."""
    coarse = alignment_shift(samples, satellite, lattice, doppler_hz)
    return refine_alignment(samples, satellite, lattice, doppler_hz, coarse)


# A navigation data bit lasts 20 ms, so at most one change falls inside a short record, and it must
# sit on a code-period boundary. Accept such a change only when it explains the prompt phase far
# better than a straight line: a real change collapses the residual, noise does not.
BIT_CHANGE_RESIDUAL_RATIO = 0.25


def weighted_line(centred: np.ndarray, values: np.ndarray, weights: np.ndarray):
    """Weighted straight-line fit of `values` against `centred`; slope, intercept, residual power."""
    total = float(weights.sum())
    denominator = float(np.sum(weights * centred * centred))
    slope = float(np.sum(weights * centred * values) / denominator)
    intercept = float(np.sum(weights * values) / total)
    residual = values - (intercept + slope * centred)
    return slope, intercept, float(np.sum(weights * residual**2) / total)


def data_bit_sign_pattern(prompts: np.ndarray, code_period_seconds: float) -> np.ndarray:
    """Per-period +-1 navigation data bit signs, from at most one sign change.

    A navigation data bit lasts 20 ms, so a short record holds at most one change and it must sit on
    a code-period boundary: from that period on, the prompt sign is inverted. That inversion is not
    separable from a frequency offset of about one over twice the half-record, so the choice is made
    the way a receiver makes it - take the sign pattern whose de-rotated prompts add up to the
    largest coherent sum. The all-positive pattern is always a candidate, so a record with a
    constant bit keeps it.
    """
    periods = len(prompts)
    ones = np.ones(periods)
    if periods < 4:
        return ones

    times = np.arange(periods) * code_period_seconds
    weights = np.abs(prompts) ** 2
    centred = times - float(np.sum(weights * times) / float(weights.sum()))

    def coherence(pattern):
        corrected = prompts * pattern
        phases = np.unwrap(np.angle(corrected))
        slope, _, _ = weighted_line(centred, phases, weights)
        de_rotated = corrected * np.exp(-1j * slope * times)
        return float(abs(de_rotated.sum()))

    best_pattern, best_coherence = ones, coherence(ones)
    for boundary in range(1, periods):
        for sign in (1.0, -1.0):
            pattern = ones.copy()
            pattern[boundary:] = sign
            candidate = coherence(pattern)
            if candidate > best_coherence:
                best_pattern, best_coherence = pattern, candidate
    return best_pattern


__all__ = [
    "alignment_shift",
    "refine_alignment",
    "aligned_shift",
    "code_period_segments",
    "segment_totals",
    "data_bit_sign_pattern",
    "weighted_line",
    "carrier",
]
