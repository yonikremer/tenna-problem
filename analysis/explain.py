"""Show, in numbers, that the recovered flip pattern explains the received recording.

No truth file is used: the recording and the recovered model are the only inputs, so every number
below holds on the supplied files, not just on synthetic ones.

Four measurements, each with the value it must have if the recovery is right:

 1. Explained power. The recovered model removes `received - residual` of the received power, and the
    noise sets a ceiling `received - noise`: a perfect model explains the signal and nothing more.
 2. Residual against the noise variance. Recovered codes must leave noise; the nominal codes must
    leave the extra power the flips were hiding, and that excess has a closed form:
    `signal * (1 - ((N - 2K)/N)^2)` for K flips in an N-chip code.
 3. Per-PRN correlation gain. A K-flip code correlates with `(N - 2K)/N` of the nominal amplitude,
    so the gain has a ceiling `20*log10(N/(N-2K))`; landing inside it means no chip is wrong.
 4. A permutation null. The same statistic that found the pattern, evaluated on random chip masks of
    the same size, says how often noise could have produced it.
"""

import sys

import numpy as np

from gnss import pipeline, signals, verification
from gnss.acquisition import acquire
from gnss.rule import CODE_LENGTH

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")
PERMUTATIONS = 500
SEED = 20240601


def mask_gain(vectors: dict, base, slope: int, first_prn: int) -> float:
    """Mean per-PRN correlation gain of one fixed chip mask, in dB.

    Flipping a chip changes a replica's correlation with the recording by exactly minus twice that
    chip's contribution, so one projection per PRN gives the gain of any mask without rebuilding
    waveforms. This is the statistic the recovery selects on, which is what makes it a fair target
    for a null distribution.
    """
    gains = []
    for prn, own in sorted(vectors.items()):
        shift = slope * (prn - first_prn)
        flips = [(chip - shift) % CODE_LENGTH for chip in base]
        nominal = own.sum()
        if nominal == 0:
            continue
        flipped = nominal - 2.0 * own[flips].sum()
        gains.append(float(10.0 * np.log10(abs(flipped / nominal) ** 2 + 1e-30)))
    return float(np.mean(gains))


def report(recording: str, check: verification.Verification, vectors: dict, rule, found,
           correlation: float) -> None:
    noise = float(found.noise_variance)
    received = float(found.received_power)
    recovered = check.recovered_residual_power
    nominal = check.nominal_residual_power
    count = rule.count

    explained = received - recovered

    print(f"\n{recording}")
    print(f"  {len(found.detected)} PRNs, {count} flipped chips per PRN")
    print(f"  received power    {received:.4f}   noise variance {noise:.4f}   "
          f"signal {received - noise:.4f}")
    print(f"  model power       {explained:.4f} = {100.0 * explained / received:.1f}% of received "
          f"power, correlation with the recording R^2 = {correlation ** 2:.4f}")
    print(f"  residual          recovered {recovered:.4f}   nominal {nominal:.4f}"
          f"   (nominal leaves {100.0 * (nominal / recovered - 1.0):.1f}% more)")
    print(f"  residual / noise  recovered {recovered / noise:.4f}   nominal {nominal / noise:.4f}"
          f"   (noise estimated during acquisition)")

    expected_excess = explained * (1.0 - ((CODE_LENGTH - 2 * count) / CODE_LENGTH) ** 2)
    print(f"  excess power from {count} wrong chips: predicted {expected_excess:.4f}, "
          f"measured {nominal - recovered:.4f}")

    gains = np.array([check.gains_db[prn] for prn in sorted(check.gains_db)])
    print(f"  per-PRN gain      {gains.min():+.3f} to {gains.max():+.3f} dB, "
          f"mean {gains.mean():+.3f} dB, ceiling {check.ceiling_db:+.3f} dB")

    rng = np.random.default_rng(SEED)
    sizes = {check.flips_per_prn[prn] for prn in check.flips_per_prn}
    null = np.array([
        mask_gain(vectors, set(rng.choice(CODE_LENGTH, max(sizes), replace=False)),
                  rule.slope, rule.first_prn)
        for _ in range(PERMUTATIONS)
    ])
    actual = mask_gain(vectors, rule.base, rule.slope, rule.first_prn)
    p = float(np.count_nonzero(null >= actual) + 1) / (PERMUTATIONS + 1)
    print(f"  permutation null  {PERMUTATIONS} random {max(sizes)}-chip masks: "
          f"{null.min():+.3f} to {null.max():+.3f} dB, mean {null.mean():+.3f} dB")
    print(f"  recovered mask    {actual:+.3f} dB beats "
          f"{np.count_nonzero(null < actual)}/{PERMUTATIONS}, p = {p:.4f}")

    assert recovered < nominal, "nominal codes must leave more power behind"
    assert actual > null.max(), "recovered mask must beat every random mask"


def main(recordings=DEFAULT_RECORDINGS, satellites=None):
    for recording in recordings:
        found = acquire(recording, satellites)
        recovery = pipeline.recover(recording, acquisition=found)
        check = verification.verify(found, recovery.rule.flips)
        vectors = {prn: sat.vector for prn, sat in recovery.satellites.items()}
        units = verification.unit_signals(found, recovery.rule.flips, nominal=False)
        reconstruction = signals.reconstruct(signals.fit_amplitudes(found.samples, units), units)
        samples = found.samples
        correlation = float(
            abs(np.vdot(reconstruction, samples))
            / (np.sqrt(np.vdot(reconstruction, reconstruction).real)
               * np.sqrt(np.vdot(samples, samples).real))
        )
        report(recording, check, vectors, recovery.rule, found, correlation)


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
