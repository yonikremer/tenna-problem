"""Greedy per-chip flip test: does flipping chip m increase one PRN's correlation score?

Score for one satellite is the coherent correlation over the whole record,

    S = sum over samples of x * exp(-j*2*pi*f*t) * nominal_code

Flipping nominal chip m removes that chip's contribution twice (once because the replica changes sign,
once because the received contribution then adds instead of cancels), so

    S_m = S - 2 * (contribution of chip m)

and the flip is accepted when |S_m|^2 > |S|^2. That is an analytic shortcut: it needs one correlation,
not 1023. The script verifies the shortcut against a brute-force correlation before using it, then
measures how many chips the rule flags, and - by simulation at the measured signal-to-noise - how
often the true chips would be among the flagged.

This is the "one PRN at a time" baseline. At 55 dB-Hz it is not enough on its own; the point of the
shared rule is that 12 PRNs add coherently where one cannot decide.
"""

import sys

import numpy as np

from gnss import alignment, chips, signals
from gnss.lattice import load_recording
from gnss.tables import read_detections

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")


def prepare(recording):
    """Per-satellite chip vectors after removing the other satellites, plus noise level."""
    detected = read_detections(recording)
    samples, _, lattice = load_recording(recording)
    period_samples = lattice.samples_per_code_period
    samples_per_chip = lattice.samples_per_chip_whole

    units, coefficients, shifts = {}, {}, {}
    for satellite, doppler_hz in sorted(detected.items()):
        shifts[satellite] = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
        units[satellite] = signals.unit_signal(
            len(samples), satellite, lattice, doppler_hz, shifts[satellite]
        )
        coefficients[satellite] = np.vdot(units[satellite], samples) / len(samples)
    residual = signals.residual(samples, coefficients, units)
    noise_variance = float(np.mean(np.abs(residual) ** 2))

    vectors = {}
    for satellite, doppler_hz in detected.items():
        clean = signals.cleaned(samples, coefficients, units, satellite)
        _, whole, _ = chips.chip_vector(
            clean, satellite, lattice, doppler_hz, shifts[satellite], period_samples, samples_per_chip
        )
        vectors[satellite] = chips.align(whole)
    return vectors, noise_variance, period_samples, samples_per_chip


def score_changes(vector, samples_per_chip, periods):
    """Change in |S|^2 for flipping each chip, using the analytic shortcut."""
    total = vector.sum() * samples_per_chip * periods
    contribution = vector * samples_per_chip * periods
    return np.abs(total - 2.0 * contribution) ** 2 - abs(total) ** 2


def brute_force(recording, satellite, doppler_hz, chip_index, prepared):
    """Direct correlation with a replica whose chip is flipped, for verification only."""
    samples, _, lattice = load_recording(recording)
    _, _, _, samples_per_chip = prepared
    periods = len(samples) // lattice.samples_per_code_period
    shift = alignment.aligned_shift(samples, satellite, lattice, doppler_hz)
    replica = signals.spreading_code_replica(
        satellite, len(samples), lattice, None, -shift * lattice.code_phase_increment
    )
    times = np.arange(len(samples)) / lattice.sample_rate_hz
    carrier = np.exp(-2j * np.pi * doppler_hz * times)
    offsets = np.arange(samples_per_chip)
    modified = replica.copy()
    for period in range(periods):
        base = period * lattice.samples_per_code_period + chip_index * samples_per_chip
        modified[base + offsets] *= -1.0
    score = abs(np.sum(modified * carrier * samples)) ** 2
    nominal = abs(np.sum(replica * carrier * samples)) ** 2
    return score - nominal


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        vectors, noise_variance, period_samples, samples_per_chip = prepare(recording)
        samples, _, lattice = load_recording(recording)
        periods = len(samples) // period_samples
        # 32 samples are combined into one chip: 8 code periods x 4 samples per chip
        chip_noise = float(np.sqrt(noise_variance / (periods * samples_per_chip)))

        print(f"\n{recording}   per-chip noise {chip_noise:.4f}")
        print(f"{'sat':>4} {'flagged':>8} {'improve>0':>10} {'amplitude':>10} {'snr':>6}")
        for satellite, vector in sorted(vectors.items()):
            changes = score_changes(vector, samples_per_chip, periods)
            flagged = int(np.count_nonzero(changes > 0))
            amplitude = float(np.mean(np.abs(np.real(vector))))
            print(
                f"{satellite:>4} {flagged:>8} {np.count_nonzero(changes > 0):>10} "
                f"{amplitude:>10.4f} {amplitude / chip_noise:>6.2f}"
            )

        shortcut_check()


def shortcut_check():
    """Verify on a synthetic signal that the analytic score change equals a real correlation."""
    from gnss.lattice import Lattice

    print("  verifying the analytic score change against a direct correlation:")
    lattice = Lattice(4092000.0, 1575420000.0, 1023000.0, 1023)
    length = lattice.samples_per_code_period * 8
    period_samples = lattice.samples_per_code_period
    samples_per_chip = lattice.samples_per_chip_whole
    periods = 8
    generator = np.random.default_rng(3)
    satellite = 5
    code = signals.spreading_code_replica(satellite, length, lattice)
    times = np.arange(length) / lattice.sample_rate_hz
    signal = 0.278 * code * np.exp(2j * np.pi * 400.0 * times)
    signal += (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)
    carrier = np.exp(-2j * np.pi * 400.0 * times)
    product = signal * carrier * code
    whole = product.reshape(periods, -1, samples_per_chip).mean(axis=2).mean(axis=0)
    changes = score_changes(whole, samples_per_chip, periods)
    worst = 0.0
    for chip_index in (0, 137, 512, 900, 1022):
        modified = code.copy()
        offsets = np.arange(samples_per_chip)
        for period in range(periods):
            base = period * period_samples + chip_index * samples_per_chip
            modified[base + offsets] *= -1.0
        # plain sum, not np.vdot: vdot conjugates its first argument and would flip the carrier
        direct = abs(np.sum(modified * carrier * signal)) ** 2 - abs(np.sum(code * carrier * signal)) ** 2
        scale = max(abs(direct), 1.0)
        worst = max(worst, abs(float(changes[chip_index]) - direct) / scale)
    print(f"    worst relative difference {worst:.2e}")
    if worst > 1e-3:
        raise SystemExit("analytic score change does not match a direct correlation")


def vector_doppler(recording, satellite):
    detected = read_detections(recording)
    if satellite not in detected:
        raise SystemExit(f"satellite {satellite} is not detected in {recording}")
    return detected[satellite]


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
