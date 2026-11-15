"""End-to-end recovery of the hidden chip flip rule from one recording.

Order of operations, and why each step exists:

 1. `acquisition.acquire`     find every PRN, its Doppler and its code phase.
 2. cancel the others         each detected satellite has a known unit waveform, so the recording
                              can be rebuilt without the eleven others, leaving that satellite plus
                              noise. Without this, another code's cross-correlation sets the floor.
 3. read one soft value per chip
                              a chip reappears in every code period; averaging its occurrences
                              lifts it above the noise. One PRN alone is still not enough at 55 dB-Hz.
 4. align and sum the PRNs    the patterns share one shape, shifted by a constant number of chips per
                              PRN. Summing them raises the signal by the PRN count and the noise by
                              its square root: the gain that makes the flips readable.
 5. state the rule            the base pattern is the backward cumulative-Fibonacci set; that is
                              checked, not asserted.

The result is a plain data object, so the CLI, the tests and the verification all read the same
numbers.
"""

from dataclasses import dataclass

import numpy as np

from . import acquisition as acquisition_module
from . import chips, signals
from . import rule as rule_module
from .acquisition import Acquisition
from .lattice import Lattice

# Below this many PRNs the combining gain that makes a single chip decidable is not there: the
# benchmark's PRN sweep recovers every flip from 6 PRNs at 52 dB-Hz and misses 7-13% at 2 and 4.
MINIMUM_PRNS = 6


@dataclass(frozen=True)
class Satellite:
    """One detected PRN after cancellation: its geometry and its soft chip vector."""

    prn: int
    doppler_hz: float
    shift_samples: float
    unit: np.ndarray
    amplitude: complex
    vector: np.ndarray

@dataclass(frozen=True)
class Recovery:
    """Everything recovered from one recording."""

    acquisition: Acquisition
    satellites: dict
    residual: np.ndarray
    rule: rule_module.Rule
    warnings: tuple = ()

    @property
    def lattice(self) -> Lattice:
        return self.acquisition.lattice

    @property
    def samples(self) -> np.ndarray:
        return self.acquisition.samples

    @property
    def residual_power(self) -> float:
        return signals.noise_variance(self.residual)

    def describe_rule(self) -> list:
        """The recovered rule as printable lines, including how the count was chosen."""
        held_out = self.rule.count_scores[self.rule.count]
        neighbours = [
            f"{count}: {gain:+.3f} dB"
            for count, gain in sorted(self.rule.count_scores.items())
            if abs(count - self.rule.count) <= 2
        ]
        weakest, strongest = self.rule.cutoff()
        return [
            f"common shift per PRN: {self.rule.slope} chips, alignment score {self.rule.score:.2f}",
            f"flipped chips per PRN: {self.rule.count} "
            f"(chosen by held-out correlation, {held_out:+.3f} dB; nearby counts: "
            f"{', '.join(neighbours)})",
            f"cutoff: weakest accepted chip {weakest:+.2f} sigma, "
            f"strongest rejected chip {strongest:+.2f} sigma",
            f"base pattern: {' '.join(str(chip) for chip in sorted(self.rule.base))}",
        ]

    def describe_warnings(self) -> list:
        """Anything a reader must know before trusting the rule above."""
        return [f"warning: {message}" for message in self.warnings]

    def describe_flips(self) -> list:
        return [
            f"PRN {prn:>2}: {' '.join(str(chip) for chip in sorted(self.rule.flips[prn]))}"
            for prn in sorted(self.rule.flips)
        ]


def soft_chip_vectors(acquisition) -> tuple:
    """Per-PRN soft chip vector after cancelling the other PRNs, and the noise-only residual."""
    samples = acquisition.samples
    lattice = acquisition.lattice
    length = len(samples)

    units, coefficients, shifts = {}, {}, {}
    for prn, detection in acquisition.detected.items():
        shift = acquisition.aligned_shift(prn)
        shifts[prn] = shift
        units[prn] = signals.unit_signal(
            length, prn, lattice, detection.doppler_hz, shift, detection.bit_change_period
        )
        coefficients[prn] = np.vdot(units[prn], samples) / length
    if not units:
        # Nothing to cancel, nothing to read. Say so, instead of failing inside the arithmetic: a
        # dense modification can push the nominal-code correlation under the detection threshold.
        raise SystemExit(
            f"{acquisition.recording}: no satellites detected, nothing to recover "
            f"(threshold {acquisition.threshold:.1f})"
        )

    residual = signals.residual(samples, coefficients, units)
    satellites = {}
    for prn, detection in acquisition.detected.items():
        clean = signals.cleaned(samples, coefficients, units, prn)
        _, whole, _ = chips.chip_vector(
            clean, prn, lattice, detection.doppler_hz, shifts[prn]
        )
        satellites[prn] = Satellite(
            prn=prn,
            doppler_hz=detection.doppler_hz,
            shift_samples=shifts[prn],
            unit=units[prn],
            amplitude=coefficients[prn],
            vector=np.real(chips.align(whole)),
        )
    return satellites, residual


def recover(recording: str, satellites=None, acquisition=None) -> Recovery:
    """Recover the common chip-flip rule of one recording, end to end."""
    if acquisition is None:
        acquisition = acquisition_module.acquire(recording, satellites)
    per_satellite, residual = soft_chip_vectors(acquisition)
    vectors = {prn: satellite.vector for prn, satellite in per_satellite.items()}
    rule = rule_module.recover_rule(vectors)
    warnings = []
    if len(per_satellite) < MINIMUM_PRNS:
        warnings.append(
            f"only {len(per_satellite)} PRNs detected; fewer than {MINIMUM_PRNS} does not decide every "
            f"chip (see the PRN sweep in BENCHMARK.md), so treat the rule as provisional"
        )
    return Recovery(
        acquisition=acquisition,
        satellites=per_satellite,
        residual=residual,
        rule=rule,
        warnings=tuple(warnings),
    )
