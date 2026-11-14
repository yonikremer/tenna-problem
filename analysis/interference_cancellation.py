"""Subtract the other satellites' signals and measure whether it helps.

Each detected satellite is fully described by its Doppler, code phase, and one complex amplitude
(constant data bit). Those parameters are estimated far better than one chip: the amplitude comes
from a correlation over 32,736 samples, not 32. So every satellite except the one being read can be
reconstructed and subtracted, leaving that satellite plus noise.

Measured, not assumed:
  - spread of the chip values before and after cancellation
  - the control code, which must fall to pure noise after cancellation
  - the resulting per-chip signal-to-noise and what it implies for deciding a single chip
"""

import sys

import numpy as np

from gnss import alignment, chips, signals
from gnss.lattice import load_recording
from gnss.tables import read_detections

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        detected = read_detections(recording)
        samples, _, lattice = load_recording(recording)
        period_samples = lattice.samples_per_code_period
        samples_per_chip = lattice.samples_per_chip_whole
        periods = len(samples) // period_samples

        units, coefficients = {}, {}
        for satellite, doppler_hz in sorted(detected.items()):
            shift = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
            units[satellite] = signals.unit_signal(
                len(samples), satellite, lattice, doppler_hz, shift
            )
            coefficients[satellite] = np.vdot(units[satellite], samples) / len(samples)

        residual = signals.residual(samples, coefficients, units)
        received_power = float(np.mean(np.abs(samples) ** 2))
        residual_power = float(np.mean(np.abs(residual) ** 2))

        print(f"\n{recording}")
        print(f"  received power {received_power:.4f}, after subtracting all satellites {residual_power:.4f}")
        print(
            f"  cancellation removed {100 * (1 - residual_power / received_power):.1f}% of the power "
        )

        print(f"{'sat':>4} {'spread before':>14} {'spread after':>13} {'snr before':>11} {'snr after':>10}")
        before_all, after_all = [], []
        for satellite, doppler_hz in sorted(detected.items()):
            shift = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
            clean = signals.cleaned(samples, coefficients, units, satellite)
            _, whole, _ = chips.chip_vector(
                samples, satellite, lattice, doppler_hz, shift, period_samples, samples_per_chip
            )
            _, clean_whole, _ = chips.chip_vector(
                clean, satellite, lattice, doppler_hz, shift, period_samples, samples_per_chip
            )
            original = chips.align(whole)
            cleaned = chips.align(clean_whole)
            bits = chips.bits_of(whole)
            spread_before = float(np.std(np.real(original)[bits > 0]))
            spread_after = float(np.std(np.real(cleaned)[bits > 0]))
            amplitude = float(np.mean(np.abs(np.real(cleaned))))
            before_all.append(spread_before)
            after_all.append(spread_after)
            print(
                f"{satellite:>4} {spread_before:>14.4f} {spread_after:>13.4f} "
                f"{amplitude / spread_before:>11.2f} {amplitude / spread_after:>10.2f}"
            )

        control, _, _ = chips.chip_vector(
            residual, max(detected) + 5, lattice, 0.0, 0.0, period_samples, samples_per_chip
        )
        control = chips.align(control)
        print(
            f"  control code on the cleaned signal: mean |value| {np.mean(np.abs(control)):.4f} "
            f"(pure noise would be about {np.sqrt(residual_power / (periods * samples_per_chip)):.4f})"
        )
        print(
            f"  mean per-chip spread {np.mean(before_all):.4f} -> {np.mean(after_all):.4f} "
            f"({np.mean(before_all) / np.mean(after_all):.2f}x smaller)"
        )


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
