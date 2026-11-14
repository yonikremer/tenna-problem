"""Per-PRN chip readout: one soft value per spreading-code chip, plus a control code.

Each satellite transmits its own 1023-chip code once per code period, so a chip value reappears at
the same place in every period. Averaging those occurrences coherently suppresses both thermal
noise and the other satellites' codes, which are unrelated sequences and therefore add incoherently.

Pipeline per satellite
  1. Use the sharpened Doppler estimate for that satellite; a wrong frequency would rotate the phase
     across the record and cancel the average.
  2. Wipe the carrier and wipe the NOMINAL spreading code. What remains is +amplitude where the
     received chip matches the nominal code and -amplitude where the chip was modified.
  3. Average the occurrences of each chip. Chips are sampled at their centre, so runs and edges of
     the code do not disturb the value.
  4. Rotate out the residual phase, then read the sign. A sign that disagrees with the nominal code
     is a modified chip.

Cross-check used throughout: the same processing with a code that is NOT in the recording. It must
produce noise only, which is what "the other codes cancelled" has to mean quantitatively.
"""

import csv
import sys

import numpy as np

from gnss import acquisition, alignment, chips
from gnss.lattice import load_recording
from gnss.tables import artifact, read_detections

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        detected = read_detections(recording)
        samples, _, lattice = load_recording(recording)
        period_samples = lattice.samples_per_code_period
        samples_per_chip = lattice.samples_per_chip_whole
        if not lattice.chip_grid_is_exact:
            raise SystemExit("code period is not a whole number of chips at this sample rate")

        vectors, centre_vectors = {}, {}
        periods = 0
        for satellite, doppler_hz in sorted(detected.items()):
            shift = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
            centre, whole, periods = chips.chip_vector(
                samples, satellite, lattice, doppler_hz, shift, period_samples, samples_per_chip
            )
            vectors[satellite] = whole
            centre_vectors[satellite] = centre

        received_power = float(np.mean(np.abs(samples) ** 2))
        # amplitude from the coherent correlation peak, not from mean|chip|: averaging magnitudes
        # folds noise and the other satellites' codes into the estimate and biases it high
        satellites_power = sum(
            acquisition.coherent_correlation(samples, satellite, lattice, doppler_hz)[3] ** 2
            for satellite, doppler_hz in detected.items()
        )
        noise_variance = received_power - satellites_power
        if noise_variance <= 0:
            raise SystemExit("detected satellites explain all received power, noise would be zero")
        sample_noise = float(np.sqrt(noise_variance))
        combined_samples = periods * samples_per_chip
        predicted_noise = sample_noise / np.sqrt(combined_samples)
        centre_noise = sample_noise / np.sqrt(periods * max(samples_per_chip // 2, 1))

        print("")
        print(recording)
        print(f"  noise variance {noise_variance:.3f}, {periods} periods, {samples_per_chip} samples/chip")
        print(f"  predicted noise on one chip {predicted_noise:.4f} (whole chip), {centre_noise:.4f} (centre only)")

        # the chips share code coordinates, so the satellites' patterns can be summed
        consensus = np.zeros(lattice.code_length_in_chips, dtype=complex)
        for vector in vectors.values():
            consensus += chips.align(vector)
        consensus_bits = chips.bits_of(consensus)
        print(f"  consensus modified chips: {np.count_nonzero(consensus_bits < 0)} of {lattice.code_length_in_chips}")

        print(f"{'sat':>4} {'flips':>6} {'centre':>7} {'agree':>7} {'amplitude':>10} {'spread':>8} {'predicted':>10}")
        for satellite, vector in vectors.items():
            aligned = chips.align(vector)
            bits = chips.bits_of(vector)
            centre_bits = chips.bits_of(centre_vectors[satellite])
            agreement = np.mean(bits == consensus_bits) * 100.0
            spread = float(np.std(np.real(aligned)[bits > 0]))
            print(
                f"{satellite:>4} {np.count_nonzero(bits < 0):>6} {np.count_nonzero(centre_bits < 0):>7} "
                f"{agreement:>6.1f}% {np.mean(np.abs(np.real(aligned))):>10.4f} {spread:>8.4f} {predicted_noise:>10.4f}"
            )

        # control: a code that is not in the recording must produce noise, not chips
        absent = max(detected) + 5
        control, _, _ = chips.chip_vector(
            samples, absent, lattice, 0.0, 0.0, period_samples, samples_per_chip
        )
        control = chips.align(control)
        print(
            f"  control code {absent}: mean |value| {np.mean(np.abs(control)):.4f}, "
            f"std {np.std(np.real(control)):.4f} (predicted noise {predicted_noise:.4f})"
        )

        destination = artifact(recording, "_chips.csv")
        try:
            with open(destination, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["satellite", "chip_index", "real", "imag", "magnitude", "flipped", "consensus_flipped"]
                )
                for satellite, vector in vectors.items():
                    aligned = chips.align(vector)
                    bits = chips.bits_of(vector)
                    for index in range(lattice.code_length_in_chips):
                        writer.writerow(
                            [
                                satellite,
                                index,
                                round(float(np.real(aligned)[index]), 5),
                                round(float(np.imag(aligned)[index]), 5),
                                round(float(abs(aligned[index])), 5),
                                bool(bits[index] < 0),
                                bool(consensus_bits[index] < 0),
                            ]
                        )
        except OSError as error:
            raise SystemExit(f"cannot write {destination}: {error}") from error
        print(f"  -> {destination}")


def self_check():
    """Injected known pattern: the pipeline must recover exactly the chips that were flipped."""
    from gnss.lattice import Lattice
    from gnss.signals import spreading_code_replica

    lattice = Lattice(4092000.0, 1575420000.0, 1023000.0, 1023)
    length = lattice.samples_per_code_period * 8
    times = np.arange(length) / lattice.sample_rate_hz
    generator = np.random.default_rng(13)
    satellite, doppler_hz = 7, 870.0
    flipped = np.array([17, 200, 201, 512, 700, 1022])

    code = spreading_code_replica(satellite, length, lattice, None, 0.0)
    modified = code.copy()
    chips_per_period = lattice.code_length_in_chips
    samples_per_chip = lattice.samples_per_code_period // chips_per_period
    # flip every sample of the chosen chips, in every code period, not just one sample per chip
    offsets = np.arange(samples_per_chip)
    for chip in flipped:
        for period in range(length // lattice.samples_per_code_period):
            base = period * lattice.samples_per_code_period + chip * samples_per_chip
            modified[base + offsets] *= -1.0
    # amplitude chosen so one chip is many standard deviations from zero: this test checks the
    # mechanics (alignment, per-chip averaging, chip-centre sampling), not the sensitivity limit
    signal = 3.0 * modified * np.exp(2j * np.pi * doppler_hz * times)
    # the record starts 124 samples (31 chips) into the code, so the known answer stays in code
    # coordinates while the alignment still has to find a non-zero shift
    signal = np.roll(signal, 124)
    signal += (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)

    shift = alignment.aligned_shift(signal, satellite, lattice, doppler_hz)
    _, whole, _ = chips.chip_vector(
        signal, satellite, lattice, doppler_hz, shift, lattice.samples_per_code_period, samples_per_chip
    )
    recovered = chips.flipped_chips(whole)
    if recovered != set(flipped.tolist()):
        raise SystemExit(f"recovered flipped chips {sorted(recovered)}, injected {flipped.tolist()}")


if __name__ == "__main__":
    self_check()
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
