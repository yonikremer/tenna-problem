import make_synthetic as generator  # type: ignore
import numpy as np
import pytest

from analysis import data_bit_check
from gnss import acquisition, alignment, signals


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


def test_sign_pattern_is_all_positive_without_a_bit_change():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    times = np.arange(8) * grid.code_period_seconds
    prompts = np.exp(2j * np.pi * 17.0 * times + 0.4)
    assert np.all(alignment.data_bit_sign_pattern(prompts, grid.code_period_seconds) == 1.0)


def test_sign_pattern_finds_the_period_where_the_bit_changed():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    times = np.arange(8) * grid.code_period_seconds
    generated = np.random.default_rng(3)
    phases = np.exp(2j * np.pi * 17.0 * times + 0.4)
    phases[4:] *= -1.0
    noisy = phases + 0.05 * (
        generated.standard_normal(8) + 1j * generated.standard_normal(8)
    )
    pattern = alignment.data_bit_sign_pattern(noisy, grid.code_period_seconds)
    assert pattern.tolist() == [1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0]


def test_sharp_doppler_survives_a_data_bit_change():
    """The straight-line fit sees a step of pi here; unhandled it returns ~100 Hz and says +-1 Hz."""
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    length = grid.samples_per_code_period * 8
    times = np.arange(length) / grid.sample_rate_hz
    satellite, injected_hz = 11, -1234.5
    generated = np.random.default_rng(21)

    code = signals.spreading_code_replica(satellite, length, grid)
    bit_signs = np.ones(length)
    bit_signs[4 * grid.samples_per_code_period :] = -1.0
    noisy = 0.278 * code * bit_signs * np.exp(2j * np.pi * injected_hz * times)
    noisy += (generated.standard_normal(length) + 1j * generated.standard_normal(length)) / np.sqrt(2.0)

    shift = alignment.aligned_shift(noisy, satellite, grid, injected_hz)
    estimate, uncertainty = acquisition.sharp_doppler(
        noisy, satellite, grid, injected_hz + 20.0, shift, 1.0
    )
    assert abs(estimate - injected_hz) < 1.0
    assert 0.0 < uncertainty < 5.0


def test_chip_vector_recovers_flips_across_a_data_bit_change():
    from gnss import chips

    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    length = grid.samples_per_code_period * 8
    times = np.arange(length) / grid.sample_rate_hz
    satellite, doppler_hz = 7, 870.0
    flipped = {17, 200, 512, 700, 1022}
    generated = np.random.default_rng(13)

    nominal = signals.spreading_code_replica(satellite, grid.code_length_in_chips, grid, increment=1.0)
    modified = nominal.copy()
    modified[list(flipped)] *= -1.0
    chip_of_sample = (np.arange(length) // grid.samples_per_chip_whole) % grid.code_length_in_chips
    bit_signs = np.ones(length)
    bit_signs[4 * grid.samples_per_code_period :] = -1.0
    samples = 1.0 * modified[chip_of_sample] * bit_signs * np.exp(2j * np.pi * doppler_hz * times)
    samples += (generated.standard_normal(length) + 1j * generated.standard_normal(length)) / np.sqrt(2.0)

    shift = alignment.aligned_shift(samples, satellite, grid, doppler_hz)
    _, whole, _ = chips.chip_vector(samples, satellite, grid, doppler_hz, shift)
    assert chips.flipped_chips(whole) == flipped
