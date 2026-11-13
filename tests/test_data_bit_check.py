import make_synthetic as generator  # type: ignore
import numpy as np
import pytest

from analysis import data_bit_check
from gnss import alignment


def circular_error(measured, expected, period):
    return (measured - expected + period / 2) % period - period / 2


def test_self_check():
    data_bit_check.self_check()


def test_alignment_shift_matches_every_injected_delay(synthetic):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        shift = alignment.aligned_shift(synthetic.samples, satellite, lattice, row["doppler_hz"])
        assert abs(circular_error(shift, row["delay_samples"], generator.SAMPLES_PER_CODE_PERIOD)) < 1.0


def test_code_period_segments_cover_the_record(synthetic):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        shift = alignment.aligned_shift(synthetic.samples, satellite, lattice, row["doppler_hz"])
        segments = alignment.code_period_segments(
            synthetic.samples, satellite, lattice, row["doppler_hz"], shift
        )
        assert len(segments) in (8, 9)
        assert sum(count for count, _ in segments) == generator.LENGTH
        assert all(count > 0 for count, _ in segments)


def test_coherent_z_prefers_the_matching_sign_pattern():
    amplitudes = np.array([1.0, 1.0, 1.0, 1.0])
    counts = np.ones(4)
    constant = data_bit_check.coherent_z(amplitudes, counts, 1.0)
    change = data_bit_check.coherent_z(amplitudes, counts, 1.0, boundary=2)
    assert constant == pytest.approx(4.0 / np.sqrt(4.0))
    assert change == pytest.approx(0.0)


def test_boundary_evidence_finds_no_change_in_constant_bit_data(synthetic):
    lattice = synthetic.lattice
    sample_noise = np.sqrt(generator.NOISE_COMPLEX_VARIANCE)
    for satellite, row in synthetic.truth.items():
        shift = alignment.aligned_shift(synthetic.samples, satellite, lattice, row["doppler_hz"])
        segments = alignment.code_period_segments(
            synthetic.samples, satellite, lattice, row["doppler_hz"], shift
        )
        _, evidence, threshold, size = data_bit_check.boundary_evidence(segments, sample_noise, trials=200)
        assert size in (8, 9)
        assert not (evidence > 0 and evidence >= threshold)


def test_main_reports_a_constant_bit_for_every_satellite(synthetic, capsys):
    data_bit_check.main([synthetic.recording])
    output = capsys.readouterr().out
    assert output.count("constant") == 12
    assert "CHANGED" not in output
    assert " segments" in output
