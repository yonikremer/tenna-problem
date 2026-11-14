"""Tests for the code-phase refinement: what the segment energy can and cannot resolve."""

import numpy as np
import pytest

from gnss import alignment, signals

GRID = signals.Lattice(
    sample_rate_hz=4_092_000.0,
    centre_frequency_hz=1_575_420_000.0,
    chip_rate_hz=1_023_000.0,
    code_length_in_chips=1023,
)


def clean_recording(satellite: int = 4, delay_samples: float = 500.0) -> np.ndarray:
    length = GRID.samples_per_code_period * 8
    return 0.278 * signals.spreading_code_replica(
        satellite, length, GRID, None, -delay_samples * GRID.code_phase_increment
    )


def test_refine_alignment_keeps_a_coarse_estimate_the_energy_cannot_beat():
    """Inside the plateau every shift is equally good, so the coarse sub-sample value must survive.

    Regression: the scan used to return the first grid point of the plateau, which discarded the
    parabolic peak's sub-sample accuracy and made the result depend on where the scan started.
    """
    samples = clean_recording()
    assert alignment.refine_alignment(samples, 4, GRID, 0.0, 499.6) == pytest.approx(499.6, abs=0.05)
    assert alignment.refine_alignment(samples, 4, GRID, 0.0, 500.0) == pytest.approx(500.0, abs=0.05)


def test_refine_alignment_pulls_a_coarse_estimate_outside_the_plateau_back_into_it():
    samples = clean_recording()
    refined = alignment.refine_alignment(samples, 4, GRID, 0.0, 501.0)
    assert refined == pytest.approx(500.0, abs=0.15)


def test_aligned_shift_is_accurate_to_a_few_tenths_of_a_sample():
    """The honest resolution: one sample is 0.25 chip, and this stage cannot resolve far below it."""
    length = GRID.samples_per_code_period * 8
    times = np.arange(length) / GRID.sample_rate_hz
    frequencies = np.fft.fftfreq(length)
    generator = np.random.default_rng(5)
    period = GRID.samples_per_code_period
    errors = []
    for _ in range(6):
        delay = generator.uniform(0.0, period)
        base = 0.278 * signals.spreading_code_replica(9, length, GRID) * np.exp(
            2j * np.pi * 2054.9 * times
        )
        noisy = np.fft.ifft(np.fft.fft(base) * np.exp(-2j * np.pi * frequencies * delay))
        noisy += (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)
        estimate = alignment.aligned_shift(noisy, 9, GRID, 2054.9)
        errors.append((estimate - delay + period / 2) % period - period / 2)
    errors = np.array(errors)
    assert abs(errors.mean()) < 0.5
    assert np.abs(errors).max() < 1.0
