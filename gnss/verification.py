"""Quantitative check that the recovered flips explain the recording.

Two measurements, both against the same noise level:

 1. Per satellite, correlate the recording with the nominal code and with the recovered modified
    code. The recovered code must correlate better. `+0.26 dB` is the ceiling for this data: the
    recovered code differs from the nominal one on 15 of 1023 chips, so 993/1023 of the signal
    survives, and 20*log10(993/1023) = -0.26 dB. A gain near that number means every recovered chip
    is right; a gain well below it means some are wrong.

 2. Rebuild every satellite from the recovered code and subtract. What is left must be noise alone,
    i.e. its power must equal the noise variance estimated from the recording's own received power.
    A model with wrong chips cannot remove the signal it got wrong.

Nothing here uses a truth file: the recording is the only input, so the numbers hold on the real
files as well as on synthetic ones.
"""

from dataclasses import dataclass

import numpy as np

from . import alignment, signals
from .acquisition import Acquisition


@dataclass(frozen=True)
class Verification:
    """What the recovered model explains, in power and in decibels."""

    nominal_residual_power: float
    recovered_residual_power: float
    received_power: float
    gains_db: dict
    flips_per_prn: dict
    code_length: int

    @property
    def residual_gain_db(self) -> float:
        return float(10.0 * np.log10(self.nominal_residual_power / self.recovered_residual_power))

    @property
    def explained_fraction(self) -> float:
        return 1.0 - self.recovered_residual_power / self.received_power

    @property
    def ceiling_db(self) -> float:
        """Best gain one satellite can show: a flipped chip correlates against the nominal code.

        With K flipped chips the nominal code matches on N-K chips and disagrees on K, so the
        recovered code correlates with amplitude (N-2K)/N of the nominal one.
        """
        flipped = max(self.flips_per_prn.values(), default=0)
        remaining = self.code_length - 2 * flipped
        return float(20.0 * np.log10(self.code_length / remaining)) if remaining > 0 else np.inf

    def describe(self, noise_variance: float) -> list:
        gains = [self.gains_db[prn] for prn in sorted(self.gains_db)]
        return [
            f"residual power with nominal codes   {self.nominal_residual_power:.4f}",
            f"residual power with recovered codes {self.recovered_residual_power:.4f}",
            f"noise variance measured from the recording {noise_variance:.4f}",
            f"recovered codes remove {100.0 * self.explained_fraction:.1f}% of received power "
            f"({self.residual_gain_db:+.3f} dB less residual power)",
            f"per-PRN correlation gain: {min(gains):+.3f} to {max(gains):+.3f} dB, "
            f"mean {np.mean(gains):+.3f} dB, ceiling {self.ceiling_db:+.3f} dB",
        ]


def unit_signals(
    acquisition: Acquisition, flips: dict, nominal: bool
) -> dict:
    """Unit waveform of every detected PRN, built from the nominal or the recovered code."""
    samples = acquisition.samples
    lattice = acquisition.lattice
    length = len(samples)
    units = {}
    for prn, detection in acquisition.detected.items():
        shift = alignment.aligned_shift(samples, prn, lattice, detection.doppler_hz)
        if nominal:
            units[prn] = signals.unit_signal(length, prn, lattice, detection.doppler_hz, shift)
        else:
            units[prn] = signals.flipped_replica(
                prn, length, lattice, shift, frozenset(flips.get(prn, ()))
            ) * signals.carrier(length, lattice, detection.doppler_hz)
    return units


def residual_power(samples: np.ndarray, units: dict) -> float:
    coefficients = signals.fit_amplitudes(samples, units)
    return signals.noise_variance(signals.residual(samples, coefficients, units))


def verify(acquisition: Acquisition, flips: dict) -> Verification:
    """Compare the nominal-code model against the recovered-code model on the same recording."""
    samples = acquisition.samples
    nominal = unit_signals(acquisition, flips, nominal=True)
    recovered = unit_signals(acquisition, flips, nominal=False)

    nominal_coefficients = signals.fit_amplitudes(samples, nominal)
    recovered_coefficients = signals.fit_amplitudes(samples, recovered)

    # Power of each satellite's component under either model: the fitted coefficient is the
    # amplitude of a unit waveform, so |coefficient|^2 is its power per sample.
    gains_db, flips_per_prn = {}, {}
    for prn in recovered:
        gains_db[prn] = float(
            10.0
            * np.log10(abs(recovered_coefficients[prn]) ** 2 / abs(nominal_coefficients[prn]) ** 2)
        )
        flips_per_prn[prn] = len(flips.get(prn, ()))

    return Verification(
        nominal_residual_power=residual_power(samples, nominal),
        recovered_residual_power=residual_power(samples, recovered),
        received_power=acquisition.received_power,
        gains_db=gains_db,
        flips_per_prn=flips_per_prn,
        code_length=acquisition.lattice.code_length_in_chips,
    )
