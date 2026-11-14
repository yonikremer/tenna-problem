"""Tests for the mask statistic the explanation's permutation test is built on."""

import numpy as np
import pytest

from analysis.explain import mask_gain
from gnss import rule


def test_correct_mask_gain_equals_the_ceiling():
    count, length = 15, rule.CODE_LENGTH
    base = set(rule.fibonacci_base())
    vector = np.ones(length)
    vector[sorted(base)] = -1.0
    gain = mask_gain({1: vector}, base, slope=0, first_prn=1)
    assert gain == pytest.approx(20.0 * np.log10(length / (length - 2 * count)), abs=1e-9)


def test_wrong_mask_gain_is_negative():
    count, length = 15, rule.CODE_LENGTH
    base = set(rule.fibonacci_base())
    wrong = set(range(length)) - base
    wrong = set(sorted(wrong)[:count])
    vector = np.ones(length)
    vector[sorted(base)] = -1.0
    gain = mask_gain({1: vector}, wrong, slope=0, first_prn=1)
    assert gain == pytest.approx(
        20.0 * np.log10((length - 4 * count) / (length - 2 * count)), abs=1e-9
    )


def test_mask_is_shifted_by_the_slope_like_the_rule():
    length = rule.CODE_LENGTH
    base = {10, 20, 30}
    vector = np.ones(length)
    vector[sorted(rule.rule_flips(base, slope=2, prn=4))] = -1.0
    shifted = mask_gain({4: vector}, base, slope=2, first_prn=1)
    assert shifted > 0.0
