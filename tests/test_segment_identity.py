import re

import numpy as np
import pytest

from analysis import segment_identity


def test_block_correlations_detects_proportional_blocks():
    generator = np.random.default_rng(3)
    first = generator.standard_normal(4092) + 1j * generator.standard_normal(4092)
    blocks = [first, 2.0 * first, 1j * first]
    correlations = segment_identity.block_correlations(blocks)
    assert correlations[0] == pytest.approx(1.0)
    for correlation in correlations[1:]:
        assert abs(correlation) == pytest.approx(1.0)


def test_block_correlations_rejects_unrelated_blocks():
    generator = np.random.default_rng(4)
    blocks = [
        generator.standard_normal(4092) + 1j * generator.standard_normal(4092) for _ in range(4)
    ]
    correlations = segment_identity.block_correlations(blocks)
    assert all(abs(correlation) < 0.1 for correlation in correlations[1:])


def test_main_measures_every_satellite(synthetic, capsys):
    segment_identity.main([synthetic.recording])
    output = capsys.readouterr().out
    assert "raw segments" in output
    assert "one satellite alone would give" in output
    rows = re.findall(
        r"^\s+(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+([+-][0-9.]+)\s+([+-]?\d+)\s*$",
        output,
        re.MULTILINE,
    )
    assert len(rows) == 12
    for row in rows:
        measured, expected, surplus, advance = row[1], row[2], row[3], row[4]
        assert 0.0 <= float(measured) <= 1.0
        assert 0.0 <= float(expected) <= 1.0
        assert abs(float(surplus)) < 0.5
        assert abs(int(advance)) < 2000
