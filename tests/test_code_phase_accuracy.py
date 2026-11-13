import re

import numpy as np
import pytest

from analysis import code_phase_accuracy as accuracy
from gnss import acquisition


def test_upsampled_shift_recovers_a_known_delay():
    lattice = acquisition.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    length = lattice.samples_per_code_period * 8
    generator = np.random.default_rng(2)
    code = acquisition.spreading_code_replica(9, length, lattice)
    noisy = np.roll(code, 37) + 0.01 * (
        generator.standard_normal(length) + 1j * generator.standard_normal(length)
    )
    shift = accuracy.upsampled_shift(noisy, 9, lattice, 0.0, 16)
    period = lattice.samples_per_code_period
    circular = (shift - 37 + period / 2) % period - period / 2
    assert abs(circular) < 0.2


def test_main_compares_the_two_estimators(capsys):
    accuracy.main(trials=8)
    output = capsys.readouterr().out
    assert "current    bias" in output
    assert "upsampled  bias" in output
    match = re.search(r"current\s+bias ([+-][0-9.]+) chips\s+std ([0-9.]+) chips", output)
    assert match is not None
    assert abs(float(match.group(1))) < 0.1
    assert float(match.group(2)) < 0.1
    assert "1 chip =" in output


def test_upsampled_shift_is_finer_than_one_sample():
    lattice = acquisition.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    length = lattice.samples_per_code_period * 8
    code = acquisition.spreading_code_replica(4, length, lattice)
    shift = accuracy.upsampled_shift(code, 4, lattice, 0.0, 16)
    assert shift == pytest.approx(0.0, abs=1e-9)
