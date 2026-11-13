import csv
from pathlib import Path

import make_synthetic as generator  # type: ignore
import numpy as np
import pytest

from analysis import chip_extraction
from gnss import chips


def test_self_check():
    chip_extraction.self_check()


def test_align_puts_the_mean_on_the_positive_real_axis():
    vector = np.array([1 + 2j, -1 + 1j, 0.5 - 3j])
    aligned = chips.align(vector)
    assert aligned.sum().imag == pytest.approx(0.0, abs=1e-12)
    assert aligned.sum().real > 0.0
    assert chips.align(np.zeros(3)).tolist() == [0.0, 0.0, 0.0]


def test_bits_of_forces_a_positive_majority():
    signs = chips.bits_of(np.array([-1.0, -1.0, 1.0]))
    assert np.count_nonzero(signs < 0) < len(signs) / 2


def test_flipped_chips_reads_negative_signs():
    vector = np.ones(generator.CODE_LENGTH_IN_CHIPS)
    vector[[7, 900]] = -1.0
    assert chips.flipped_chips(vector) == {7, 900}


def test_chip_vector_recovers_exactly_the_known_flips(synthetic, truth_clean):
    lattice = synthetic.lattice
    samples_per_chip = generator.SAMPLES_PER_CODE_PERIOD // generator.CODE_LENGTH_IN_CHIPS
    for satellite, row in synthetic.truth.items():
        centre, whole, periods = chips.chip_vector(
            truth_clean.cleaned[satellite],
            satellite,
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
            generator.SAMPLES_PER_CODE_PERIOD,
            samples_per_chip,
        )
        assert periods == generator.CODE_PERIODS
        assert len(centre) == generator.CODE_LENGTH_IN_CHIPS
        recovered = chips.flipped_chips(whole)
        assert recovered == set(row["flipped_chips"])
        assert np.all(np.isfinite(whole))
        assert np.all(np.abs(whole) > 0)


def test_main_writes_one_row_per_chip(synthetic, capsys):
    chip_extraction.main([synthetic.recording])
    capsys.readouterr()
    destination = Path(synthetic.recording).with_name("synthetic_l1_chips.csv")
    with open(destination, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12 * 1023
    assert set(rows[0]) == {
        "satellite",
        "chip_index",
        "real",
        "imag",
        "magnitude",
        "flipped",
        "consensus_flipped",
    }
    assert {int(row["satellite"]) for row in rows} == set(range(1, 13))
    consensus = {row["consensus_flipped"] for row in rows}
    assert consensus <= {"True", "False"}
    assert sum(row["consensus_flipped"] == "True" for row in rows) <= 2
    for satellite in range(1, 13):
        flips = sum(row["flipped"] == "True" for row in rows if int(row["satellite"]) == satellite)
        assert 0 <= flips <= 400
