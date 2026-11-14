"""Audit one chip of one recording: is its weak reading a pipeline defect or noise in the file?

The chain reads each chip by averaging its 32 samples (8 code periods x 4 samples) after cancelling
the other satellites. A single chip reading near zero could come from the data or from the code, so
this script perturbs every input the readout depends on and reports whether the reading moves:

 1. the file itself: sample count, NaN/Inf, per-period power
 2. the navigation-bit sign pattern the readout applies per PRN
 3. the code phase, +- 0.25 and +- 1 sample
 4. the Doppler, +- 2 and +- 5 Hz
 5. the cancellation: residual power, and what the other eleven satellites leak into the chip
 6. the two halves of the record, which have independent noise

A reading that stays put while every input is perturbed, and disagrees between the halves, is noise.
A reading that swings with the code phase or the Doppler is a bug in the readout.
"""

import sys

import numpy as np

from gnss import alignment, chips, signals
from gnss.acquisition import acquire

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")
TEST_CHIPS = (987, 1008)
SLOPE = 2


def prepare(found) -> tuple:
    """Unit waveform, amplitude and code phase of every detected PRN."""
    units, coefficients, shifts = {}, {}, {}
    for prn, detection in found.detected.items():
        shift = alignment.aligned_shift(found.samples, prn, found.lattice, detection.doppler_hz)
        shifts[prn] = shift
        units[prn] = signals.unit_signal(
            len(found.samples), prn, found.lattice, detection.doppler_hz, shift,
            detection.bit_change_period,
        )
        coefficients[prn] = np.vdot(units[prn], found.samples) / len(found.samples)
    return units, coefficients, shifts


def reading(samples, found, units, coefficients, shifts, prn, base_chip,
            shift_delta=0.0, doppler_delta=0.0) -> float:
    """Consensus reading of one base chip through one PRN, in units of that PRN's chip amplitude."""
    detection = found.detected[prn]
    clean = signals.cleaned(samples, coefficients, units, prn)
    values = chips.chip_periods(
        clean, prn, found.lattice, detection.doppler_hz + doppler_delta, shifts[prn] + shift_delta
    )
    vector = np.real(chips.align(values.mean(axis=(0, 2))))
    chip = (base_chip - SLOPE * (prn - min(found.detected))) % found.lattice.code_length_in_chips
    return float(-vector[chip] / np.median(np.abs(vector)))


def consensus(samples, found, units, coefficients, shifts, base_chip, **kwargs) -> tuple:
    values = np.array([
        reading(samples, found, units, coefficients, shifts, prn, base_chip, **kwargs)
        for prn in sorted(found.detected)
    ])
    return float(values.mean()), float(values.std() / np.sqrt(len(values)))


def audit(recording: str, base_chip: int) -> None:
    found = acquire(recording)
    samples, lattice = found.samples, found.lattice
    units, coefficients, shifts = prepare(found)
    periods = len(samples) // lattice.samples_per_code_period

    print(f"\n{recording}  base chip {base_chip}")
    print(f"  file: {len(samples)} samples, dtype {samples.dtype}, "
          f"NaN {bool(np.isnan(samples).any())}, Inf {bool(np.isinf(samples).any())}")
    power = np.abs(samples).reshape(periods, -1).mean(axis=1)
    print(f"  per-period power {power.min():.3f} to {power.max():.3f} "
          f"(flat = no segment defect)")

    signs = {}
    for prn, detection in sorted(found.detected.items()):
        replica = signals.spreading_code_replica(
            prn, len(samples), lattice, None, -shifts[prn] * lattice.code_phase_increment
        )
        times = np.arange(len(samples)) / lattice.sample_rate_hz
        product = (samples * np.exp(-2j * np.pi * detection.doppler_hz * times) * replica)
        blocks = product[: periods * lattice.samples_per_code_period].reshape(
            periods, lattice.samples_per_code_period
        )
        signs[prn] = alignment.data_bit_sign_pattern(
            blocks.sum(axis=1), lattice.code_period_seconds
        ).astype(int)
    print(f"  bit sign patterns: {'all +1' if all((s == 1).all() for s in signs.values()) else signs}")

    residual = samples - signals.reconstruct(coefficients, units)
    print(f"  residual power {signals.noise_variance(residual):.4f} vs received "
          f"{found.received_power:.4f} (model leaves noise)")

    mean, error = consensus(samples, found, units, coefficients, shifts, base_chip)
    print(f"  reading at the fitted code phase and Doppler: {mean:+.2f} +- {error:.2f}")
    for label, kwargs in (
        ("code phase -1.00 sample", {"shift_delta": -1.0}),
        ("code phase -0.25 sample", {"shift_delta": -0.25}),
        ("code phase +0.25 sample", {"shift_delta": 0.25}),
        ("code phase +1.00 sample", {"shift_delta": 1.0}),
        ("Doppler -5 Hz", {"doppler_delta": -5.0}),
        ("Doppler +5 Hz", {"doppler_delta": 5.0}),
    ):
        moved, moved_error = consensus(samples, found, units, coefficients, shifts, base_chip, **kwargs)
        print(f"  {label:<24} {moved:+.2f} +- {moved_error:.2f}")

    half = periods // 2
    for label, part in (("periods 0-3", slice(0, half)), ("periods 4-7", slice(half, periods))):
        values = []
        for prn in sorted(found.detected):
            clean = signals.cleaned(samples, coefficients, units, prn)
            detection = found.detected[prn]
            block = chips.chip_periods(clean, prn, lattice, detection.doppler_hz, shifts[prn])[part]
            vector = np.real(chips.align(block.mean(axis=(0, 2))))
            chip = (base_chip - SLOPE * (prn - min(found.detected))) % lattice.code_length_in_chips
            values.append(-vector[chip] / np.median(np.abs(vector)))
        values = np.array(values)
        print(f"  {label:<24} {values.mean():+.2f} +- "
              f"{values.std() / np.sqrt(len(values)):.2f}")


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        for chip in TEST_CHIPS:
            audit(recording, chip)


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
