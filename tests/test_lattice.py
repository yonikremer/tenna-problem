"""Tests for the sampling grid: metadata reading, derived quantities, and error paths."""

import netCDF4
import numpy as np
import pytest

from gnss import lattice as lattice_module


def test_derived_quantities_follow_from_the_four_metadata_values():
    grid = lattice_module.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    assert grid.samples_per_chip == 4.0
    assert grid.samples_per_code_period == 4092
    assert grid.samples_per_chip_whole == 4
    assert grid.code_phase_increment == pytest.approx(0.25)
    assert grid.code_period_seconds == pytest.approx(1023 / 1_023_000.0)
    assert grid.chip_grid_is_exact


def test_chip_grid_is_not_exact_for_a_rate_that_is_not_a_whole_multiple():
    grid = lattice_module.Lattice(4_092_500.0, 1_575_420_000.0, 1_023_000.0, 1023)
    assert not grid.chip_grid_is_exact


def write_recording(path, length=4092, attributes=None, with_variables=True):
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("sample", length)
        if with_variables:
            real = dataset.createVariable("i", "f4", ("sample",))
            imaginary = dataset.createVariable("q", "f4", ("sample",))
            real[:] = np.zeros(length, dtype=np.float32)
            imaginary[:] = np.zeros(length, dtype=np.float32)
        for name, value in (attributes or {}).items():
            dataset.setncattr(name, value)


def test_metadata_is_read_and_published_values_are_fallbacks(tmp_path):
    path = tmp_path / "full.nc"
    write_recording(
        path,
        attributes={
            "sample_rate_hz": 4092000.0,
            "center_frequency_hz": 1575420000.0,
            "nominal_chip_rate_hz": 1023000.0,
            "nominal_code_length_chips": 1023,
        },
    )
    _, periods, grid = lattice_module.load_recording(str(path))
    assert periods == 1
    assert grid == lattice_module.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)


def test_missing_chip_rate_and_code_length_use_the_published_values(tmp_path):
    path = tmp_path / "partial.nc"
    write_recording(path, attributes={"sample_rate_hz": 4092000.0, "center_frequency_hz": 1575420000.0})
    _, _, grid = lattice_module.load_recording(str(path))
    assert grid.chip_rate_hz == lattice_module.PUBLISHED_GPS_L1["chip_rate_hz"]
    assert grid.code_length_in_chips == lattice_module.PUBLISHED_GPS_L1["code_length_in_chips"]


def test_a_missing_sample_rate_is_reported(tmp_path):
    path = tmp_path / "no_rate.nc"
    write_recording(path, attributes={"center_frequency_hz": 1575420000.0})
    with pytest.raises(SystemExit):
        lattice_module.load_recording(str(path))


def test_non_numeric_metadata_is_reported(tmp_path):
    path = tmp_path / "bad.nc"
    write_recording(
        path,
        attributes={
            "sample_rate_hz": "fast",
            "center_frequency_hz": 1575420000.0,
        },
    )
    with pytest.raises(SystemExit):
        lattice_module.load_recording(str(path))


def test_a_rate_that_is_not_a_whole_multiple_of_the_chip_rate_is_reported(tmp_path):
    path = tmp_path / "odd.nc"
    write_recording(
        path,
        attributes={"sample_rate_hz": 4092500.0, "center_frequency_hz": 1575420000.0},
    )
    with pytest.raises(SystemExit):
        lattice_module.load_recording(str(path))


def test_trailing_partial_period_is_dropped(tmp_path):
    path = tmp_path / "long.nc"
    write_recording(
        path,
        length=5000,
        attributes={"sample_rate_hz": 4092000.0, "center_frequency_hz": 1575420000.0},
    )
    samples, periods, _ = lattice_module.load_recording(str(path))
    assert periods == 1
    assert len(samples) == 4092


def test_an_unreadable_recording_is_reported(tmp_path):
    with pytest.raises(SystemExit):
        lattice_module.load_recording(str(tmp_path / "absent.nc"))


def test_reading_reports_an_unreadable_recording(tmp_path):
    with pytest.raises(SystemExit):
        lattice_module.reading(str(tmp_path / "absent.nc"))


def test_reading_exposes_every_attribute(tmp_path):
    path = tmp_path / "attrs.nc"
    write_recording(path, attributes={"sample_rate_hz": 4092000.0, "title": "a recording"})
    attributes = lattice_module.reading(str(path))
    assert attributes["sample_rate_hz"] == 4092000.0
    assert attributes["title"] == "a recording"
