"""Tests for the signal algebra: replicas, unit waveforms, and the linear fit that removes them."""

import sys
from pathlib import Path

import numpy as np
import pytest

from gnss import signals, vendor


def test_published_code_vectors_match_the_interface_specification():
    assert signals.first_10_chips(1) == 0o1440
    assert signals.first_10_chips(2) == 0o1620


def test_spreading_code_replica_is_a_pm_one_sequence_of_the_requested_length():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    replica = signals.spreading_code_replica(5, grid.samples_per_code_period, grid)
    assert len(replica) == grid.samples_per_code_period
    assert set(np.unique(replica)) == {-1.0, 1.0}
    assert np.array_equal(replica, np.roll(replica, grid.samples_per_code_period))


def test_carrier_is_a_unit_magnitude_ramp():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    ramp = signals.carrier(64, grid, 1000.0)
    assert np.allclose(np.abs(ramp), 1.0)
    phase_step = np.angle(ramp[1] / ramp[0])
    assert phase_step == pytest.approx(2 * np.pi * 1000.0 / grid.sample_rate_hz)


def test_unit_signal_is_code_times_carrier():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    unit = signals.unit_signal(grid.samples_per_code_period, 3, grid, 500.0, 12.0)
    replica = signals.spreading_code_replica(
        3, grid.samples_per_code_period, grid, None, -12.0 * grid.code_phase_increment
    )
    assert np.allclose(unit, replica * signals.carrier(grid.samples_per_code_period, grid, 500.0))


def test_aligned_code_places_chips_on_the_sample_grid():
    chip_array = np.array([1.0, -1.0, 1.0, -1.0])
    aligned = signals.aligned_code(chip_array, shift_samples=0.0, length=8, samples_per_chip=2)
    assert aligned.tolist() == [1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0]


def test_flipped_replica_negates_exactly_the_named_chips():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    length = grid.samples_per_code_period
    nominal = signals.flipped_replica(7, length, grid, 0.0)
    one_flip = signals.flipped_replica(7, length, grid, 0.0, frozenset({100}))

    changed = np.flatnonzero(nominal != one_flip)
    assert len(changed) == grid.samples_per_chip_whole
    assert set((changed // grid.samples_per_chip_whole).tolist()) == {100}


def test_fit_and_remove_recovers_an_injected_amplitude():
    grid = signals.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    generator = np.random.default_rng(5)
    length = grid.samples_per_code_period * 2
    units = {
        1: signals.unit_signal(length, 1, grid, 1200.0, 0.0),
        2: signals.unit_signal(length, 2, grid, -800.0, 40.0),
    }
    samples = 0.3 * units[1] + (-0.2j) * units[2]
    samples = samples + 1e-3 * (
        generator.standard_normal(length) + 1j * generator.standard_normal(length)
    )

    coefficients = signals.fit_amplitudes(samples, units)
    assert abs(coefficients[1]) == pytest.approx(0.3, rel=0.02)
    assert abs(coefficients[2]) == pytest.approx(0.2, rel=0.02)
    assert np.allclose(signals.reconstruct(coefficients, units), samples, atol=1e-2)
    assert signals.noise_variance(signals.residual(samples, coefficients, units)) < 1e-5

    only_first = signals.cleaned(samples, coefficients, units, 1)
    assert np.allclose(only_first, 0.3 * units[1], atol=1e-2)


def test_cleaned_with_only_one_satellite_leaves_the_recording_untouched():
    generator = np.random.default_rng(3)
    samples = generator.standard_normal(16) + 1j * generator.standard_normal(16)
    units = {1: np.ones(16)}
    coefficients = {1: 0.5 + 0j}
    assert np.allclose(signals.cleaned(samples, coefficients, units, 1), samples)


def test_reconstruct_needs_at_least_one_waveform():
    with pytest.raises(ValueError):
        signals.reconstruct({}, {})


def test_vendor_path_is_added_once_and_reported_when_missing(monkeypatch):
    entry = vendor.add_to_import_path()
    already_present = sys.path.count(entry)
    assert vendor.add_to_import_path() == entry
    assert sys.path.count(entry) == already_present
    assert Path(entry) == vendor.VENDOR_PATH

    monkeypatch.setattr(vendor, "VENDOR_PATH", Path("nowhere-at-all"))
    with pytest.raises(ImportError):
        vendor.add_to_import_path()
