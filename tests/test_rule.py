"""Tests for the rule module: the Fibonacci structure and the held-out flip-count search."""

import numpy as np
import pytest

from gnss import rule


def test_fibonacci_base_is_the_expected_position_set():
    assert rule.fibonacci_base() == (
        34,
        411,
        644,
        788,
        877,
        932,
        966,
        987,
        1000,
        1008,
        1013,
        1016,
        1018,
        1019,
        1020,
    )


def test_fibonacci_base_wraps_instead_of_going_negative():
    base = rule.fibonacci_base(start_chip=5)
    assert all(0 <= chip < rule.CODE_LENGTH for chip in base)
    assert len(base) == len(rule.FIBONACCI) + 1


def test_rule_flips_shifts_each_prn_in_code_coordinates():
    base = {10, 20, 30}
    assert rule.rule_flips(base, slope=2, prn=1) == {10, 20, 30}
    assert rule.rule_flips(base, slope=2, prn=4) == {4, 14, 24}
    # the first PRN of a search window that does not start at 1 keeps the base unchanged
    assert rule.rule_flips(base, slope=2, prn=7, first_prn=7) == {10, 20, 30}
    assert all(0 <= chip < rule.CODE_LENGTH for chip in rule.rule_flips(base, 700, 3))


def test_explain_base_confirms_a_matching_pattern():
    explanation = rule.explain_base(rule.fibonacci_base())
    assert explanation.matches
    assert explanation.missing == ()
    assert explanation.unexpected == ()
    assert explanation.worst_error_chips == 0
    assert "matches that rule exactly" in explanation.describe()[2]


def test_explain_base_names_missing_and_unexpected_positions():
    base = set(rule.fibonacci_base()) - {987} | {551}
    explanation = rule.explain_base(base)

    assert not explanation.matches
    assert explanation.missing == (987,)
    assert explanation.unexpected == (551,)
    assert explanation.worst_error_chips > 0
    lines = explanation.describe()
    assert any("does not support: 987" in line for line in lines)
    assert any("rule does not contain: 551" in line for line in lines)
    assert explanation.offsets_from_start == tuple(
        sorted((rule.BASE_START_CHIP - chip) % rule.CODE_LENGTH for chip in base)
    )


def test_explain_base_explains_an_unsupported_position_without_contradicting_the_rule():
    explanation = rule.explain_base(set(rule.fibonacci_base()) - {987})
    assert not explanation.matches
    assert explanation.unexpected == ()
    assert any("sensitivity limit" in line for line in explanation.describe())


def test_align_and_sum_lines_the_patterns_up():
    vectors = {prn: np.zeros(rule.CODE_LENGTH) for prn in (1, 2, 3)}
    vectors[1][100] = -1.0
    vectors[2][98] = -1.0
    vectors[3][96] = -1.0

    consensus = rule.align_and_sum(vectors, slope=2)
    assert consensus[100] == pytest.approx(-1.0)
    assert np.count_nonzero(consensus) == 1


def test_aligned_matrix_rolls_every_prn_by_the_slope():
    vectors = {1: np.arange(rule.CODE_LENGTH, dtype=float)}
    _, aligned = rule.aligned_matrix(vectors, slope=3)
    assert aligned.shape == (1, rule.CODE_LENGTH)
    assert np.array_equal(aligned[0], np.arange(rule.CODE_LENGTH, dtype=float))


def test_held_out_gain_rewards_a_rule_that_the_left_out_prn_agrees_with():
    """A chip negative in every PRN must score higher than a chip that is noise in the left-out one."""
    generator = np.random.default_rng(7)
    shared = {0, 400, 900}
    vectors = {}
    for prn in (1, 2, 3, 4):
        # a real soft vector is +1 on every unflipped chip and -1 on the flipped ones
        vector = 1.0 + generator.normal(0.0, 0.02, rule.CODE_LENGTH)
        vector[list(shared)] = -1.0
        vectors[prn] = vector

    good = rule.held_out_gain(vectors, slope=0, count=3)
    bad = rule.held_out_gain(vectors, slope=0, count=9)
    assert good > 0.0
    assert good > bad
    assert rule.choose_count(vectors, slope=0, candidates=range(1, 12))[0] == 3


def test_held_out_gain_skips_a_prn_whose_correlation_is_zero():
    vectors = {1: np.zeros(rule.CODE_LENGTH), 2: np.zeros(rule.CODE_LENGTH)}
    assert rule.held_out_gain(vectors, slope=0, count=1) == 0.0


def test_choose_count_picks_the_supported_number_of_chips():
    generator = np.random.default_rng(11)
    positions = {10, 300, 700}
    vectors = {}
    for prn in (1, 2, 3, 4, 5):
        vector = generator.normal(0.0, 0.02, rule.CODE_LENGTH)
        vector[list(positions)] = -1.0
        vectors[prn] = vector

    count, scores = rule.choose_count(vectors, slope=0, candidates=range(1, 8))
    assert count == 3
    assert scores[3] == max(scores.values())
    assert set(scores) == set(range(1, 8))


def test_rule_helpers_report_shifts_positions_and_the_cutoff():
    consensus = np.zeros(rule.CODE_LENGTH)
    consensus[[5, 200, 600]] = -3.0
    consensus[[10, 11]] = 1.0
    recovered = rule.Rule(
        slope=2,
        score=1.0,
        count=3,
        base=frozenset({5, 200, 600}),
        consensus=consensus,
        flips={1: frozenset({5, 200, 600}), 2: frozenset({3, 198, 598})},
        count_scores={3: 0.2},
    )

    assert recovered.first_prn == 1
    assert recovered.shift_of(2) == 2
    assert recovered.positions(2) == {3, 198, 598}
    assert recovered.table() == [(1, 0, 5), (1, 0, 200), (1, 0, 600), (2, 2, 3), (2, 2, 198), (2, 2, 598)]
    weakest, strongest = recovered.cutoff()
    assert weakest < 0.0
    assert strongest >= 0.0
