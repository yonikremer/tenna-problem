"""Are the 1 ms segments of the recorded signal identical? Three separate questions.

1. Are the RAW 1 ms blocks identical copies? No, and no amount of arithmetic can make them so: each
   satellite's carrier advances by Doppler x 1 ms of phase per segment, from -973 to +955 degrees in
   observation 1, i.e. up to 2.7 turns. The sum of twelve of those cannot repeat.

2. Is one satellite's signal, after its carrier and the other satellites are removed, the same
   waveform in every segment? Yes, up to one complex scalar per segment. The test is the normalised
   block-to-block correlation: 1 means proportional, 0 means unrelated, and the shortfall from 1 must
   be explained by noise. Note that this metric is invariant to carrier derotation - multiplying by a
   carrier ramp only scales each block by a constant - so it measures block-to-block proportionality,
   not the derotation itself.

3. Does the chip modification recur unchanged in every segment? This is what question 2 tests as
   well: a per-segment-varying modification would differ by about 2 x 15/1023 in amplitude between
   blocks.
"""

import sys

import numpy as np

from gnss import alignment, signals
from gnss.lattice import load_recording
from gnss.tables import read_detections

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")


def block_correlations(blocks):
    """Complex correlation of every block against the first, normalised by both energies."""
    reference = blocks[0]
    energy = np.vdot(reference, reference).real
    return [np.vdot(reference, block) / np.sqrt(energy * np.vdot(block, block).real) for block in blocks]


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        detected = read_detections(recording)
        samples, _, lattice = load_recording(recording)
        period_samples = lattice.samples_per_code_period
        periods = len(samples) // period_samples
        segment_seconds = period_samples / lattice.sample_rate_hz

        units, coefficients = {}, {}
        for satellite, doppler_hz in sorted(detected.items()):
            shift = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
            units[satellite] = signals.unit_signal(len(samples), satellite, lattice, doppler_hz, shift)
            coefficients[satellite] = np.vdot(units[satellite], samples) / len(samples)
        residual = signals.residual(samples, coefficients, units)

        amplitudes = {s: abs(c) for s, c in coefficients.items()}
        noise_variance = float(np.mean(np.abs(residual) ** 2))
        # two noise-corrupted copies of the same block correlate as |rho|^2 = (S/(S+N))^2, not S/(S+N):
        # the correlation is the product of the two amplitudes, so both get attenuated
        mean_power = float(np.mean([a * a for a in amplitudes.values()]))
        expected_single = (mean_power / (mean_power + noise_variance)) ** 2
        unrelated = float(
            np.mean([abs(rho) ** 2 for rho in block_correlations(residual.reshape(periods, period_samples))[1:]])
        )

        raw = np.array([abs(rho) ** 2 for rho in block_correlations(samples.reshape(periods, period_samples))[1:]])
        print(f"\n{recording}")
        print(f"  noise variance {noise_variance:.3f}, {periods} segments of {period_samples} samples")
        print(f"  raw segments: |rho|^2 = {raw.mean():.5f}  (1.0 = identical copies)")
        print(f"  unrelated blocks give |rho|^2 = {unrelated:.5f} (measured on the noise-only residual)")
        print(f"  one satellite alone would give |rho|^2 = {expected_single:.5f} if its waveform repeats")
        print(f"{'sat':>4} {'|rho|^2':>9} {'expected':>9} {'surplus':>8} {'phase advance per segment deg':>30}")
        for satellite, doppler_hz in sorted(detected.items()):
            clean = signals.cleaned(samples, coefficients, units, satellite)
            rhos = block_correlations(clean.reshape(periods, period_samples))
            measured = float(np.mean([abs(rho) ** 2 for rho in rhos[1:]]))
            print(
                f"{satellite:>4} {measured:>9.5f} {expected_single:>9.5f} {measured - expected_single:>+8.5f} "
                f"{360.0 * doppler_hz * segment_seconds:>30.0f}"
            )


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
