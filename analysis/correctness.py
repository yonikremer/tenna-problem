"""Independent tests that the recovered chip set is right, not a lucky fit.

The recovery chooses its 15 positions from the same recording it is scored on, so a correlation gain
measured on that recording can flatter it. These tests remove that freedom three ways.

 1. Split-half. The eight code periods are independent measurements of the same chips. Recover the
    whole answer from periods 0-3 only, then score it on periods 4-7, and the other way round. The
    mask never sees the data it is scored on.
 2. Evidence per position. A Gaussian log-likelihood ratio between "flipped by this satellite's own
    amplitude" and "not flipped", summed over the twelve PRNs, turns every candidate chip into a
    Bayes factor. For the count, the positions are ranked leave-one-PRN-out, so the position tested
    was never chosen with that PRN's data, and the per-rank factors give a posterior over the count.
 3. Transfer between recordings. The two files are independent noise realisations of one rule, so a
    mask recovered from one can be applied to the other with no freedom left at all.
"""

import math
import sys

import numpy as np

from analysis.explain import mask_gain
from gnss import alignment, chips, signals
from gnss.acquisition import acquire
from gnss.rule import (
    CODE_LENGTH,
    FIBONACCI,
    align_and_sum,
    aligned_matrix,
    fibonacci_base,
    recover_rule,
)

DEFAULT_RECORDINGS = ("data/gnss_observation.nc", "data/gnss_observation2.nc")
PERMUTATIONS = 500
RANKS = 20
SEED = 20240601


def prepared(found) -> dict:
    """Every code period's reading of every chip, with the other PRNs cancelled."""
    samples, lattice = found.samples, found.lattice
    units, coefficients, shifts = {}, {}, {}
    for prn, detection in found.detected.items():
        shift = alignment.aligned_shift(samples, prn, lattice, detection.doppler_hz)
        shifts[prn] = shift
        units[prn] = signals.unit_signal(
            len(samples), prn, lattice, detection.doppler_hz, shift, detection.bit_change_period
        )
        coefficients[prn] = np.vdot(units[prn], samples) / len(samples)
    return {
        prn: chips.chip_periods(
            signals.cleaned(samples, coefficients, units, prn),
            prn,
            lattice,
            detection.doppler_hz,
            shifts[prn],
        )
        for prn, detection in found.detected.items()
    }


def vector_of(period_values: np.ndarray) -> np.ndarray:
    """One soft value per chip, real part, carrier phase removed."""
    return np.real(chips.align(period_values.mean(axis=(0, 2))))


def vectors_of(period_values: dict) -> dict:
    return {prn: vector_of(values) for prn, values in period_values.items()}


def scale_of(found, periods: int) -> float:
    """Chip amplitude per PRN (later) and the noise standard deviation of one real chip value.

    A chip value averages `periods * samples_per_chip` independent white-noise samples, so its real
    part has variance `noise_power / (2 * periods * samples_per_chip)`.
    """
    variance = found.noise_variance / (2.0 * periods * found.lattice.samples_per_chip_whole)
    return math.sqrt(variance)


def position_evidence(vectors: dict, amplitude: dict, sigma: float, slope: int, positions) -> dict:
    """Evidence for each named chip, summed over all PRNs, in log-likelihood ratio units.

    Chip `c` sits at `(c - slope * (prn - first)) mod 1023` in PRN `prn`'s own coordinates. For a
    chip value `v`, the log-likelihood ratio between "flipped, depth a" and "unflipped" is
    `-2 * a * v / sigma^2`, so a negative `v` supports a flip.
    """
    first = min(vectors)
    evidence = {}
    for chip in positions:
        ratio, negatives = 0.0, 0
        for prn, vector in vectors.items():
            value = float(vector[(chip - slope * (prn - first)) % CODE_LENGTH])
            ratio += -2.0 * amplitude[prn] * value / sigma**2
            negatives += value < 0
        evidence[chip] = (ratio, negatives)
    return evidence


def nested_evidence(vectors: dict, amplitude: dict, sigma: float, slope: int, ranks: int) -> tuple:
    """Leave-one-PRN-out log-likelihood ratio for each rank of the candidate pattern.

    For each held-out PRN the positions are ranked by the other eleven, so the position tested at
    rank `k` was never chosen with that PRN's own data. Also returned is which chip each fold put at
    each rank, because past the supported count the ranking starts to disagree between folds.
    """
    satellites, aligned = aligned_matrix(vectors, slope)
    total = aligned.sum(axis=0)
    llr = np.zeros(ranks)
    chosen = np.zeros((len(satellites), ranks), dtype=int)
    for index, prn in enumerate(satellites):
        others = (total - aligned[index]) / max(len(satellites) - 1, 1)
        order = np.argsort(others)[:ranks]
        chosen[index] = order
        llr += -2.0 * amplitude[prn] * aligned[index][order] / sigma**2
    return llr, chosen


def posterior(llr: np.ndarray, k_max: int) -> np.ndarray:
    """Probability of each flipped-chip count under a flat prior, from the nested evidence."""
    cumulative = np.concatenate(([0.0], np.cumsum(llr[:k_max])))
    weights = np.exp(cumulative - cumulative.max())
    return weights / weights.sum()


def bayes_factor(line: str, ratio: float) -> float:
    return math.exp(min(ratio, 700.0))


def fibonacci_coincidence() -> list:
    """How surprising it is that the recovered set has the Fibonacci gap sequence.

    This is a statement about the answer's structure, not about the flips: the positions were chosen
    from the data, and the Fibonacci reading came after seeing them. It says the recovered mask is a
    short description rather than fifteen arbitrary numbers, which is what a noise fit would be.
    """
    subsets = math.comb(CODE_LENGTH, 15)
    with_gaps = CODE_LENGTH * math.factorial(14) // 2
    return [
        f"listing 15 positions out of {CODE_LENGTH} costs log2(C(1023,15)) = "
        f"{math.log2(subsets):.1f} bits",
        "the recovered set instead costs one start chip plus the stated Fibonacci increments",
        f"chance a random 15-subset has that gap multiset, allowing any order: {with_gaps / subsets:.1e}",
        "that describes the answer's shape, not the flips: the positions came from the data",
    ]


def main(recordings=DEFAULT_RECORDINGS):
    recovered = {}
    for recording in recordings:
        found = acquire(recording)
        period_values = prepared(found)
        periods = next(iter(period_values.values())).shape[0]
        half = periods // 2
        full = vectors_of(period_values)
        rule = recover_rule(full)
        sigma = scale_of(found, periods)
        amplitude = {prn: float(np.median(np.abs(vector))) for prn, vector in full.items()}

        print(f"\n{recording}  ({len(found.detected)} PRNs, {periods} code periods)")
        print(f"  full-data answer: slope {rule.slope}, {rule.count} chips, margin {rule.margin:.2f}")

        print("\n 1. recover on half the periods, score on the other half")
        for source_label, held_label in (("periods 0-3", "periods 4-7"),
                                        ("periods 4-7", "periods 0-3")):
            if source_label == "periods 0-3":
                parts = ({prn: v[:half] for prn, v in period_values.items()},
                         {prn: v[half:] for prn, v in period_values.items()})
            else:
                parts = ({prn: v[half:] for prn, v in period_values.items()},
                         {prn: v[:half] for prn, v in period_values.items()})
            source_vectors = vectors_of(parts[0])
            held_out = vectors_of(parts[1])
            half_rule = recover_rule(source_vectors)
            first = min(source_vectors)
            rng = np.random.default_rng(SEED)
            null = np.array([
                mask_gain(held_out, set(rng.choice(CODE_LENGTH, max(half_rule.count, 1), replace=False)),
                          half_rule.slope, first)
                for _ in range(PERMUTATIONS)
            ])
            gain = mask_gain(held_out, half_rule.base, half_rule.slope, first)
            p = float(np.count_nonzero(null >= gain) + 1) / (PERMUTATIONS + 1)
            ranking = np.argsort(align_and_sum(source_vectors, half_rule.slope))
            by_count = {k: mask_gain(held_out, set(ranking[:k]), half_rule.slope, first)
                        for k in range(10, RANKS + 1)}
            best = max(by_count, key=lambda key: by_count[key])
            print(f"  from {source_label}: slope {half_rule.slope}, {half_rule.count} chips "
                  f"({'same as' if set(half_rule.base) == set(rule.base) else 'differs from'} "
                  f"the full-data set)")
            print(f"    gain on {held_label} {gain:+.3f} dB; null "
                  f"{null.min():+.3f} to {null.max():+.3f} dB, so p = {p:.4f}")
            print(f"    count best supported by {held_label}: {best} "
                  f"({', '.join(f'{k}: {by_count[k]:+.3f}' for k in sorted(by_count))})")
            assert gain > null.max(), "a mask chosen on the other half must beat every random mask"

        print("\n 2a. is this named chip flipped? Evidence for the rule's chips, all 12 PRNs")
        print("     this is the question the answer needs; 2b answers a different one")
        print("     the last two rows are the next Fibonacci positions, outside the claimed set")
        claimed = set(fibonacci_base())
        positions = fibonacci_base(increments=FIBONACCI + (610, 987))
        evidence = position_evidence(full, amplitude, sigma, rule.slope, positions)
        print("     chip   LLR    Bayes factor  P(flip)   PRNs negative  in the rule")
        for chip, (ratio, negatives) in sorted(evidence.items()):
            factor = bayes_factor("", ratio)
            print(f"     {chip:>4}  {ratio:>+7.2f}  {factor:>12.1e}  "
                  f"{factor / (1.0 + factor):>7.4f}   {negatives:>2}/12          "
                  f"{'yes' if chip in claimed else 'no'}")

        core = [chip for chip in claimed if chip not in (987, 1008)]
        totals = {len(core): sum(evidence[chip][0] for chip in core)}
        totals[len(core) + 1] = totals[len(core)] + evidence[1008][0]
        totals[len(core) + 2] = totals[len(core) + 1] + evidence[987][0]
        print(f"     whole-mask log-likelihood ratio: {len(core)} chips {totals[len(core)]:+.1f}, "
              f"+1008 {totals[len(core) + 1]:+.1f}, +987 {totals[len(core) + 2]:+.1f}")
        print(f"     so this file prefers {len(core) + 1} over {len(core)} by "
              f"{bayes_factor('', totals[len(core) + 1] - totals[len(core)]):.0f}:1, and "
              f"{len(core) + 2} over {len(core) + 1} by "
              f"{bayes_factor('', totals[len(core) + 2] - totals[len(core) + 1]):.2f}:1")

        print("\n 2b. how many chips can be found without being told which? Leave-one-PRN-out.")
        print("     it scans all 1023 positions, so it reports the count this file establishes on its")
        print("     own; it is not a verdict on the rule's chips, which is what 2a measures")
        llr, chosen = nested_evidence(full, amplitude, sigma, rule.slope, RANKS)
        probability = posterior(llr, RANKS)
        print("     rank  chip  folds  LLR     P(K = rank)  P(K > rank)")
        for rank in range(1, RANKS + 1):
            labels, counts = np.unique(chosen[:, rank - 1], return_counts=True)
            modal = int(labels[int(np.argmax(counts))])
            print(f"     {rank:>4}  {modal:>4}  {int(counts.max()):>2}/12  {llr[rank - 1]:>+7.2f}  "
                  f"{probability[rank]:>10.4f}  {probability[rank + 1:].sum():>10.4f}")
        print(f"     posterior mode {int(np.argmax(probability))} chips: "
              f"P(13) {probability[13]:.4f}, P(14) {probability[14]:.4f}, P(15) {probability[15]:.4f}")
        print("     read this next to 2a, not instead of it: the two disagree when the file can find")
        print("     the right count but not the right positions (or the reverse)")

        recovered[recording] = (rule, full)

    print("\n 3. transfer between recordings: the two files are independent noise realisations")
    names = list(recovered)
    for source in names:
        source_rule, _ = recovered[source]
        for target in names:
            if target == source:
                continue
            _, target_vectors = recovered[target]
            first = min(target_vectors)
            gain = mask_gain(target_vectors, source_rule.base, source_rule.slope, first)
            shared = len(source_rule.base & recovered[target][0].base)
            print(f"  mask from {source} applied to {target}: {gain:+.3f} dB over nominal "
                  f"({len(source_rule.base)} chips, nothing fitted on the target)")
            print(f"    {shared} of the target's {len(recovered[target][0].base)} own chips are in that "
                  f"mask; the extra {len(source_rule.base) - shared} chips cost it nothing")

    print("\n 4. how short the answer is")
    for line in fibonacci_coincidence():
        print(f"    {line}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_RECORDINGS)
