"""Did a navigation data bit change inside the 8 ms recording, for each satellite?

Physical constraint: a navigation data bit lasts 20 ms and the recording is 8 ms, so at most ONE
transition can fall inside it, and it must sit on a code-period boundary.

Segmentation. The record does not start on a code boundary, so equal windows from the first sample
would both lose a candidate boundary and let a transition straddle two windows, diluting the sign
change instead of separating the halves. Segments are therefore cut at the code boundaries implied
by the measured code phase:

    partial segment | full period | ... | full period | partial segment

With 8 periods of data that is 9 segments and 8 candidate boundaries. Segment lengths differ, so
every sum is weighted by its own sample count.

Alignment. The shift comes from a SINGLE code period, not from the whole record: if a data bit does
change mid-record, the whole-record coherent sum partly cancels and its peak collapses, which would
misalign everything and hide the very change being looked for.

Method
  1. Remove carrier and spreading code, leaving the data bit times noise.
  2. Sum each segment.
  3. Match the whole sign pattern: the coherent amplitude is largest exactly at the true boundary
     when the bit changes, and equals the constant-bit amplitude when it does not. Matching the
     pattern also identifies the position, which a plain phase difference cannot, because a split
     placed before the true change leaves both signs inside one half.
  4. Threshold from Monte Carlo at the measured noise level, so "how big from noise alone" is
     answered rather than assumed.
"""

import sys

import numpy as np

from gnss import alignment
from gnss.lattice import load_recording
from gnss.tables import read_detections

FALSE_ALARM = 1e-3
DEFAULT_RECORDINGS = ("gnss_observation.nc", "gnss_observation2.nc")


def coherent_z(amplitudes, counts, sample_noise, boundary=None):
    """Signal-to-noise ratio of the coherent sum under a sign pattern (None means constant bit)."""
    signs = np.ones(len(amplitudes))
    if boundary is not None:
        signs[boundary:] = -1.0
    total = abs((signs * counts * amplitudes).sum())
    # noise on the weighted sum: variance = sum over segments of counts * sample_noise squared
    return float(total / (sample_noise * np.sqrt(counts.sum())))


def boundary_evidence(segments, sample_noise, false_alarm=FALSE_ALARM, trials=5000):
    """Best boundary, the evidence for a change, and the noise-only threshold.

    Evidence is the increase in signal-to-noise of the coherent sum when one sign change is allowed,
    measured against the constant-bit sum: a real change raises it enormously, a constant bit lowers
    it because the sign pattern then mismatches. Both terms are z-scores of the same units, so no
    quantity cancels and no ratio can explode.
    """
    amplitudes = np.array([total / count for count, total in segments])
    counts = np.array([count for count, _ in segments], dtype=float)

    constant_z = coherent_z(amplitudes, counts, sample_noise)
    z_values = [coherent_z(amplitudes, counts, sample_noise, k) for k in range(1, len(amplitudes))]
    best = int(np.argmax(z_values)) + 1
    evidence = z_values[best - 1] - constant_z

    generator = np.random.default_rng(2024)
    level = float(np.mean(np.abs(amplitudes)))
    noise = sample_noise / np.sqrt(counts)
    drawn = np.empty(trials)
    for trial in range(trials):
        noisy = level + noise * (
            generator.standard_normal(len(amplitudes)) + 1j * generator.standard_normal(len(amplitudes))
        ) / np.sqrt(2.0)
        flat = coherent_z(noisy, counts, sample_noise)
        peak = max(coherent_z(noisy, counts, sample_noise, k) for k in range(1, len(noisy)))
        drawn[trial] = peak - flat
    return best, float(evidence), float(np.quantile(drawn, 1.0 - false_alarm)), len(segments)


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        detected = read_detections(recording)
        samples, _, lattice = load_recording(recording)

        measured = {}
        for satellite, doppler_hz in sorted(detected.items()):
            shift = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
            segments = alignment.code_period_segments(samples, satellite, lattice, doppler_hz, shift)
            amplitude = float(np.mean([abs(total) / count for count, total in segments]))
            measured[satellite] = (segments, amplitude)

        noise_variance = float(np.mean(np.abs(samples) ** 2)) - sum(
            amplitude**2 for _, amplitude in measured.values()
        )
        sample_noise = float(np.sqrt(noise_variance))

        print(f"\n{recording}   noise variance {noise_variance:.3f}")
        print(f"{'sat':>4} {'amplitude':>10} {'boundary':>9} {'evidence':>9} {'threshold':>10} {'segments':>9}  verdict")
        for satellite, (segments, amplitude) in measured.items():
            boundary, evidence, threshold, size = boundary_evidence(segments, sample_noise)
            # a change must both beat the noise and actually beat the constant-bit model
            verdict = "CHANGED" if evidence > 0 and evidence >= threshold else "constant"
            # the boundary index only means something when a change was actually called
            shown = boundary if verdict == "CHANGED" else "-"
            print(
                f"{satellite:>4} {amplitude:>10.3f} {shown:>9} {evidence:>9.2f} "
                f"{threshold:>10.3f} {size:>9}  {verdict}"
            )


def self_check():
    """Injected known answers: a real change must be found at the right boundary, noise must not lie."""
    from gnss.lattice import Lattice
    from gnss.signals import spreading_code_replica

    lattice = Lattice(4092000.0, 1575420000.0, 1023000.0, 1023)
    length = lattice.samples_per_code_period * 8
    times = np.arange(length) / lattice.sample_rate_hz
    satellite, doppler_hz = 4, 620.0
    per_period = lattice.samples_per_code_period
    first_boundary = 125  # record starts mid-chip, as the real files do

    # segmentation must follow each satellite's own code phase, and the segment COUNT changes with
    # it: a code phase near zero leaves no leading partial segment, giving 8 segments not 9
    for phase_samples, expected_segments in ((0, 8), (1, 8), (512, 9), (2046, 9), (4091, 9)):
        generator = np.random.default_rng(9)
        code = spreading_code_replica(9, length, lattice, None, -phase_samples / 4)
        signal = 0.278 * code * np.exp(2j * np.pi * doppler_hz * times)
        signal += (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)
        shift = alignment.aligned_shift(signal, 9, lattice, doppler_hz)
        segments = alignment.code_period_segments(signal, 9, lattice, doppler_hz, shift)
        if len(segments) != expected_segments:
            raise SystemExit(
                f"code phase {phase_samples} samples gave {len(segments)} segments, expected {expected_segments}"
            )
        amplitude = float(np.mean([abs(total) / count for count, total in segments]))
        if amplitude < 0.25:
            raise SystemExit(f"code phase {phase_samples} samples gave amplitude {amplitude:.3f}, badly aligned")

    for flip_at in (None, 5, 2, 8):
        generator = np.random.default_rng(5)
        code = spreading_code_replica(satellite, length, lattice, None, -first_boundary / 4)
        base = np.sqrt(0.0773) * code * np.exp(2j * np.pi * doppler_hz * times)
        boundaries = [first_boundary] + [first_boundary + n * per_period for n in range(1, 8)]
        if flip_at is not None:
            base[boundaries[flip_at - 1] :] *= -1.0
        noisy = base + (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)

        shift = alignment.aligned_shift(noisy, satellite, lattice, doppler_hz)
        segments = alignment.code_period_segments(noisy, satellite, lattice, doppler_hz, shift)
        if len(segments) != 9:
            raise SystemExit(f"expected 9 segments, got {len(segments)}")
        boundary, evidence, threshold, _ = boundary_evidence(segments, 1.0, trials=1000)
        if flip_at is None:
            if evidence >= threshold:
                raise SystemExit(f"constant data bit reported a change: {evidence:.2f} >= {threshold:.2f}")
        else:
            if evidence < threshold:
                raise SystemExit(f"change at boundary {flip_at} missed: {evidence:.2f} < {threshold:.2f}")
            if boundary != flip_at:
                raise SystemExit(f"change at boundary {flip_at} located at {boundary}")


if __name__ == "__main__":
    self_check()
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
