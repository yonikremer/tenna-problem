"""The common rule: one flip pattern, shifted by a constant number of chips per PRN.

The recording's PRNs are not independent. The same flip pattern appears in every code, shifted in
code coordinates. One PRN alone gives each chip only about 1.6 amplitude signal-to-noise at 55 dB-Hz,
so its own flips cannot be read reliably. Aligning the PRN soft vectors by the common shift and
summing raises the signal by the number of PRNs while independent noise grows as its square root:
about 10.8 dB for 12 PRNs, enough to read every position.

The shift is a linear function of the PRN index (`slope * (prn - first)` chips), so it is found by
searching one slope instead of pairwise image registration. The same search works for any constant
slope, and returns zero when the patterns are genuinely unrelated.

How many positions to keep is decided from the data, not assumed. For every candidate count K and
every left-out PRN, the pattern is built from the other PRNs and applied to the one that was left
out; a genuinely flipped chip raises that PRN's correlation, a wrong chip lowers it. The count with
the best average held-out correlation is kept. This is what separates the 15 positions of the first
recording from the 14 that the second recording can actually support.

The recovered base pattern is not an arbitrary set. Its positions are the prefix sums of the
Fibonacci numbers counted backwards from chip 1020; `explain_base` states whether that holds, and
which positions disagree, instead of asserting it.
"""

from dataclasses import dataclass

import numpy as np

CODE_LENGTH = 1023
FLIP_COUNT = 15

# Candidate numbers of flipped chips, from zero to half the code. Zero belongs in the set: if no chip
# is flipped, or nothing is shared between the PRNs, that is the honest answer. The search stops at
# half the code because a pattern of more than 512 flipped chips describes a code closer to its own
# negation than to itself, which is the same ambiguity as a navigation data bit's sign and cannot be
# separated from it.
MAX_FLIP_COUNT = CODE_LENGTH // 2
CANDIDATE_COUNTS = tuple(range(MAX_FLIP_COUNT + 1))

# The fourteen increments of the inferred generator, in chips.
FIBONACCI = (1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377)
BASE_START_CHIP = 1020


def fibonacci_base(start_chip: int = BASE_START_CHIP, increments=FIBONACCI) -> tuple:
    """The inferred base pattern: `start_chip` minus the running sum of the Fibonacci increments."""
    running = 0
    positions = [start_chip % CODE_LENGTH]
    for increment in increments:
        running += increment
        positions.append((start_chip - running) % CODE_LENGTH)
    return tuple(sorted(positions))


def rule_flips(base, slope: int, prn: int, first_prn: int = 1) -> set:
    """Flip positions of one PRN under the rule: the base, shifted by `slope * (prn - first)`."""
    shift = slope * (prn - first_prn)
    return {(chip - shift) % CODE_LENGTH for chip in base}


def fibonacci(n: int) -> int:
    """The n-th Fibonacci number; fibonacci(1) = 1 and fibonacci(2) = 1."""
    a, b = 1, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return a


def closed_form_flips(prn_index: int) -> list:
    """Chip indexes PRN `prn_index` flips, straight from the rule. `prn_index` starts at 1.

    Start at `1022 - 2 * prn_index` and step back by successive Fibonacci numbers, keeping each
    landing only while it stays inside the code. The walk stops before the step that would go
    negative: for PRN 1 the next step is 610, and 34 - 610 = -576 is not a chip. Subtracting
    modulo 1023 there would invent chip 447, which is not flipped.
    """
    x = 1022 - 2 * prn_index
    chips = [x]
    i = 1
    while x - fibonacci(i) >= 0:
        x = x - fibonacci(i)
        chips.append(x)
        i += 1
    return chips


@dataclass(frozen=True)
class PatternExplanation:
    """What the recovered base pattern is, as a formula plus a per-position match against it."""

    name: str
    formula: str
    matches: bool
    increments: tuple
    cumulative_chips: tuple
    offsets_from_start: tuple
    worst_error_chips: int
    missing: tuple
    unexpected: tuple

    def describe(self) -> list:
        found = len(self.offsets_from_start)
        lines = [
            f"{self.name}:",
            f"  chips = 1020 - prefix sum of {list(self.increments)}",
        ]
        if self.matches:
            lines.append(f"  the recovered pattern matches that rule exactly ({found}/{found} positions)")
            return lines
        expected = len(self.cumulative_chips)
        lines.append(
            f"  the recovered pattern matches that rule on {found - len(self.unexpected)} of "
            f"{expected} rule positions"
        )
        if self.missing:
            lines.append(
                f"  positions the rule expects but this recording does not support: "
                f"{' '.join(str(chip) for chip in self.missing)}"
            )
        if self.unexpected:
            lines.append(
                f"  positions the recording supports but the rule does not contain: "
                f"{' '.join(str(chip) for chip in self.unexpected)}"
            )
        if self.missing and not self.unexpected:
            lines.append(
                "  the rule itself is not contradicted: a position with no measurable evidence in "
                "one recording is a sensitivity limit, not a different pattern"
            )
        return lines


def explain_base(base) -> PatternExplanation:
    """Check whether a base pattern is the backward cumulative-Fibonacci set, and how it differs."""
    recovered = set(base)
    reference = set(fibonacci_base())
    offsets = tuple(sorted((BASE_START_CHIP - chip) % CODE_LENGTH for chip in base))

    running = 0
    cumulative = [0]
    for increment in FIBONACCI:
        running += increment
        cumulative.append(running)

    errors = [
        min(abs((BASE_START_CHIP - chip) % CODE_LENGTH - step) for step in cumulative)
        for chip in recovered
    ]
    return PatternExplanation(
        name="backward cumulative Fibonacci prefix sums",
        formula="1020 - sum(Fibonacci[0:k]) for k = 0..14",
        matches=recovered == reference,
        increments=FIBONACCI,
        cumulative_chips=tuple(cumulative),
        offsets_from_start=offsets,
        worst_error_chips=max(errors) if errors else 0,
        missing=tuple(sorted(reference - recovered)),
        unexpected=tuple(sorted(recovered - reference)),
    )


def aligned_matrix(vectors: dict, slope: int) -> tuple:
    """Every PRN's soft vector rolled into the base pattern's coordinates."""
    satellites = sorted(vectors)
    aligned = np.array(
        [np.roll(vectors[prn], slope * (prn - satellites[0])) for prn in satellites]
    )
    return satellites, aligned


def align_and_sum(vectors: dict, slope: int) -> np.ndarray:
    """Consensus soft vector after shifting PRN k by `slope * (PRN - first PRN)` chips."""
    _, aligned = aligned_matrix(vectors, slope)
    return aligned.mean(axis=0)


def score_slope(vectors: dict, slope: int, flip_count: int = FLIP_COUNT) -> float:
    """How sharp the `flip_count` negative chips are after alignment; larger is better.

    shortcut: this is an extreme-value statistic, so a wrong shift that happens to stack flip signs
    can outrank the true one once a large fraction of the chips are negative. Measured onset: 3 of 4
    runs still exact at 240 flipped chips of 1023, none of 4 at 244, and the wrong answer is 343 or
    684 - about 1023/3 and 2*1023/3, where the PRN rolls coincide and a dense random mask's own
    autocorrelation competes with the true shift of 2. Upgrade to ranking shifts by held-out gain
    (`count_scores`) if dense modifications ever matter; see BENCHMARK.md.
    """
    consensus = align_and_sum(vectors, slope)
    # only the flip_count smallest values are used, so partitioning beats sorting the whole code
    ordered = (
        np.sort(consensus)
        if flip_count >= len(consensus)
        else np.partition(consensus, flip_count - 1)[:flip_count]
    )
    return float(-np.mean(ordered) / (np.std(consensus) + 1e-12))


def held_out_gain(vectors: dict, slope: int, count: int) -> float:
    """Average correlation gain when a `count`-chip pattern from 11 PRNs is applied to the 12th.

    The gain is physical, not a score to be gamed: flipping a chip in a replica changes that PRN's
    coherent correlation by exactly minus twice that chip's contribution, so a correct chip raises
    the correlation and a wrong chip lowers it. Averaging over all left-out PRNs therefore peaks at
    the number of chips the recording really supports.
    """
    satellites, aligned = aligned_matrix(vectors, slope)
    total = np.sum(aligned, axis=0)
    folds = 0
    gain = 0.0
    for index, prn in enumerate(satellites):
        others = (total - aligned[index]) / max(len(satellites) - 1, 1)
        base = np.argsort(others)[:count]
        contributions = vectors[prn]
        shift = slope * (prn - satellites[0])
        flips = [(chip - shift) % CODE_LENGTH for chip in base]
        nominal = contributions.sum()
        flipped = nominal - 2.0 * contributions[flips].sum()
        if nominal == 0:
            continue
        gain += float(10.0 * np.log10(abs(flipped / nominal) ** 2 + 1e-30))
        folds += 1
    return gain / max(folds, 1)


def count_scores(vectors: dict, slope: int, candidates=CANDIDATE_COUNTS) -> dict:
    """Held-out correlation gain for every candidate flip count.

    One sort per left-out PRN is enough for every count at once: the chips are already ordered by the
    other PRNs' consensus, so a count just takes that many from the front. That keeps a 513-count
    search as cheap as a 41-count one.
    """
    satellites, aligned = aligned_matrix(vectors, slope)
    total = np.sum(aligned, axis=0)
    folds = []
    for index, prn in enumerate(satellites):
        others = (total - aligned[index]) / max(len(satellites) - 1, 1)
        order = np.argsort(others)
        shift = slope * (prn - satellites[0])
        own = vectors[prn]
        nominal = float(own.sum())
        if nominal == 0:
            continue
        flipped_contribution = np.cumsum(2.0 * own[(order - shift) % CODE_LENGTH])
        folds.append((nominal, flipped_contribution))
    if not folds:
        return dict.fromkeys(candidates, 0.0)

    scores = {}
    for count in candidates:
        gains = []
        for nominal, flipped_contribution in folds:
            flipped = nominal - (flipped_contribution[count - 1] if count else 0.0)
            gains.append(10.0 * np.log10(abs(flipped / nominal) ** 2 + 1e-30))
        scores[count] = float(np.mean(gains))
    return scores


def choose_count(vectors: dict, slope: int, candidates=CANDIDATE_COUNTS) -> tuple:
    """Best supported number of flipped chips, and the score of every candidate."""
    scores = count_scores(vectors, slope, candidates)
    best = max(scores, key=lambda count: scores[count])
    return best, scores


@dataclass(frozen=True)
class Rule:
    """Recovered common rule: the slope, the base pattern, and every PRN's flip positions."""

    slope: int
    score: float
    count: int
    base: frozenset
    consensus: np.ndarray
    flips: dict
    count_scores: dict
    # how far the winning shift score is ahead of the best rival, in the same units; the recovery is
    # only trustworthy while this stays well above zero
    margin: float = 0.0

    @property
    def first_prn(self) -> int:
        return min(self.flips)

    def shift_of(self, prn: int) -> int:
        return self.slope * (prn - self.first_prn)

    def positions(self, prn: int) -> set:
        return self.flips[prn]

    def table(self) -> list:
        """One row per flipped chip: (satellite, shift_chips, chip_index, base_chip).

        `base_chip` is where that chip sits in the first PRN's coordinates, so the reader can see
        that the shift is the only difference between the PRNs.
        """
        return [
            (prn, self.shift_of(prn), chip, chip + self.shift_of(prn))
            for prn in sorted(self.flips)
            for chip in sorted(self.flips[prn])
        ]

    def cutoff(self) -> tuple:
        """Consensus of the weakest accepted chip and the strongest rejected one, in sigmas.

        The gap between the two is what justifies the chosen count: a real flip sits clearly below
        zero, a chip that was not flipped sits at or above it.
        """
        ordered = np.sort(self.consensus)
        scale = float(np.std(self.consensus)) or 1.0
        if self.count == 0:
            # no chip was accepted, so the boundary is the most negative chip of all
            return float("nan"), float(ordered[0]) / scale
        weakest_accepted = float(ordered[self.count - 1]) / scale
        strongest_rejected = float(ordered[self.count]) / scale if self.count < len(ordered) else np.nan
        return weakest_accepted, strongest_rejected


def recover_rule(vectors: dict) -> Rule:
    """Best slope, best supported flip count, and each PRN's flip positions."""
    satellites = sorted(vectors)
    slope_scores = np.array([score_slope(vectors, slope) for slope in range(CODE_LENGTH)])
    best_slope = int(np.argmax(slope_scores))
    best_score = float(slope_scores[best_slope])
    runner_up = float(np.max(np.delete(slope_scores, best_slope)))

    count, scores = choose_count(vectors, best_slope)
    consensus = align_and_sum(vectors, best_slope)
    base = frozenset(np.argsort(consensus)[:count].tolist())
    flips = {
        prn: frozenset((chip - best_slope * (prn - satellites[0])) % CODE_LENGTH for chip in base)
        for prn in satellites
    }
    return Rule(
        slope=best_slope,
        score=float(best_score),
        count=count,
        base=base,
        consensus=consensus,
        flips=flips,
        count_scores=scores,
        margin=best_score - runner_up,
    )
