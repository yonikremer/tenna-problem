"""Bold assumption: the SAME flipped chips appear in all twelve codes, shifted per PRN.

Test procedure, using each satellite's known Doppler and code offset:

  - Joint score. For satellite p the coherent sum over the record is S_p, and chip m contributes
    C_p[m] to it, so flipping chip m in every code changes the score by
        delta(m) = sum over p of ( |S_p - 2 C_p[m]|^2 - |S_p|^2 )
    The twelve satellites' contributions add coherently (the same chip index, the same modification)
    while the noise on them adds in quadrature, so this is sqrt(12) times more sensitive than testing
    one satellite. Rank by delta and keep the best ones.

  - Split-half consistency, the decisive check. Rank using satellites 1-6 and again using 7-12. If the
    assumption holds, both halves must pick nearly the same chips. Two chance sets would share
    K*K/1023 chips.

  - Benchmarks, as requested: no modification at all, one shared mask, a random mask, and
    per-satellite independent masks, each scored by the power left after refitting the amplitudes.

This is the "no shift" version of the rule: it assumes every PRN flips the same chip indices. The
real rule shifts the mask per PRN, which is what `gnss.rule` searches for; this script is the
baseline that shows why the shift has to be searched.
"""

import sys

import numpy as np

from analysis import greedy_flip as greedy
from gnss.lattice import load_recording
from gnss.rule import FLIP_COUNT

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")


def prepared(recording):
    vectors, noise_variance, period_samples, samples_per_chip = greedy.prepare(recording)
    return vectors, noise_variance, period_samples, samples_per_chip


def chip_contributions(vector, samples_per_chip, periods):
    """Contribution of each chip to the coherent sum (already in code coordinates)."""
    return vector * samples_per_chip * periods


def joint_scores(vectors, samples_per_chip, periods, satellites=None):
    satellites = list(vectors) if satellites is None else satellites
    total = np.zeros(1023)
    for satellite in satellites:
        vector = vectors[satellite]
        coherent = vector.sum() * samples_per_chip * periods
        contributions = chip_contributions(vector, samples_per_chip, periods)
        total += np.abs(coherent - 2.0 * contributions) ** 2 - abs(coherent) ** 2
    return total


def explained_power(vectors, samples_per_chip, periods, flips_by_satellite):
    """Signal power explained when each satellite's model has the given chips flipped."""
    explained = 0.0
    for satellite, vector in vectors.items():
        coherent = vector.sum() * samples_per_chip * periods
        for chip in flips_by_satellite.get(satellite, ()):
            coherent -= 2.0 * vector[chip] * samples_per_chip * periods
        explained += abs(coherent) ** 2
    return float(explained) / (samples_per_chip * periods * 1023)


def main(recordings=DEFAULT_RECORDINGS):
    for recording in recordings:
        vectors, noise_variance, period_samples, samples_per_chip = prepared(recording)
        samples, _, _ = load_recording(recording)
        periods = len(samples) // period_samples
        length = len(samples)
        received_power = float(np.mean(np.abs(samples) ** 2))

        scores = joint_scores(vectors, samples_per_chip, periods)
        ranking = np.argsort(scores)[::-1]
        joint_top = list(ranking[:FLIP_COUNT])
        noise_level = float(np.std(scores))

        first_half = [s for s in sorted(vectors) if s <= 6]
        second_half = [s for s in sorted(vectors) if s > 6]
        half_one = list(np.argsort(joint_scores(vectors, samples_per_chip, periods, first_half))[::-1][:FLIP_COUNT])
        half_two = list(np.argsort(joint_scores(vectors, samples_per_chip, periods, second_half))[::-1][:FLIP_COUNT])
        overlap = len(set(half_one) & set(half_two))
        chance = FLIP_COUNT * FLIP_COUNT / 1023

        print(f"\n{recording}")
        print(f"  received power {received_power:.4f}, noise variance {noise_variance:.4f}")
        # scores are negative for a correctly modelled chip, so the largest value is the best candidate
        print(
            f"  score distribution: mean {scores.mean():.3g}, spread {noise_level:.3g}, "
            f"best {scores[ranking[0]]:.3g} ({(scores[ranking[0]] - scores.mean()) / noise_level:+.1f} sigma)"
        )
        print(
            f"  split-half overlap: satellites 1-6 vs 7-12 share {overlap} of {FLIP_COUNT} chips "
            f"(chance {chance:.2f})"
        )
        print(f"  top {FLIP_COUNT} chips: {sorted(int(c) for c in joint_top)}")

        baseline = explained_power(vectors, samples_per_chip, periods, {})
        shared = explained_power(vectors, samples_per_chip, periods, dict.fromkeys(vectors, joint_top))
        independent = explained_power(
            vectors,
            samples_per_chip,
            periods,
            {
                s: list(np.argsort(joint_scores(vectors, samples_per_chip, periods, [s]))[::-1][:FLIP_COUNT])
                for s in vectors
            },
        )
        generator = np.random.default_rng(0)
        random_scores = [
            explained_power(
                vectors,
                samples_per_chip,
                periods,
                dict.fromkeys(vectors, list(generator.choice(1023, FLIP_COUNT, replace=False))),
            )
            for _ in range(200)
        ]

        print(f"{'model':>26} {'explained |S|^2':>16} {'gain vs none':>13} {'residual/Hz':>12}")
        for label, value in (
            ("no modification at all", baseline),
            (f"same {FLIP_COUNT} chips in all codes", shared),
            ("random chips in all codes", float(np.mean(random_scores))),
            ("independent mask per code", independent),
        ):
            gain = value - baseline
            residual = (received_power * length - value) / length
            print(f"{label:>26} {value:>16.4g} {gain:>+13.4g} {residual:>12.4f}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
