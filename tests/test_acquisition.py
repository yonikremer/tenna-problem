import csv
from pathlib import Path

import make_synthetic as generator  # type: ignore
import netCDF4
import numpy as np
import pytest

from gnss import acquisition, lattice as lattice_module


def test_parse_satellite_spec():
    assert acquisition.parse_satellite_spec("1-3,7,10-11") == [1, 2, 3, 7, 10, 11]
    with pytest.raises(SystemExit):
        acquisition.parse_satellite_spec("1-x")


def test_a_satellite_outside_the_code_table_is_reported(tmp_path):
    path = tmp_path / "empty.nc"
    import netCDF4

    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("sample", 4092)
        real = dataset.createVariable("i", "f4", ("sample",))
        imaginary = dataset.createVariable("q", "f4", ("sample",))
        real[:] = 0.0
        imaginary[:] = 0.0
        dataset.sample_rate_hz = 4_092_000.0
        dataset.center_frequency_hz = 1_575_420_000.0
    with pytest.raises(SystemExit):
        acquisition.acquire(str(path), [1, 9999])


def test_speed_model():
    satellite_speed = acquisition.satellite_line_of_sight_speed_m_s()
    assert 900.0 < satellite_speed < 1000.0
    assert acquisition.maximum_relative_speed_m_s(200.0) > satellite_speed


def test_lattice_and_recording(synthetic):
    with netCDF4.Dataset(synthetic.recording) as dataset:
        lattice = lattice_module.lattice_from_metadata(dataset)
    assert lattice.sample_rate_hz == generator.SAMPLE_RATE_HZ
    assert lattice.samples_per_chip == 4.0
    assert lattice.samples_per_code_period == generator.SAMPLES_PER_CODE_PERIOD
    assert lattice.code_phase_increment == pytest.approx(0.25)
    assert synthetic.periods == generator.CODE_PERIODS
    assert len(synthetic.samples) == generator.LENGTH


def test_spreading_code_replica_matches_the_published_code(synthetic):
    length = generator.SAMPLES_PER_CODE_PERIOD
    replica = acquisition.spreading_code_replica(3, length, synthetic.lattice)
    expected = generator.nominal_code(3)[np.arange(length) // 4 % 1023]
    assert np.array_equal(replica, expected)
    assert set(np.unique(replica)) == {-1.0, 1.0}


def test_detection_threshold():
    assert acquisition.detection_threshold(1000, 1e-6) == pytest.approx(np.log2(1e9))
    assert acquisition.detection_threshold(10_000, 1e-6) > acquisition.detection_threshold(
        1_000, 1e-6
    )


def test_self_check(synthetic):
    acquisition.self_check(synthetic.lattice)


def test_coherent_correlation_recovers_each_satellite(synthetic):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        peak, floor, shift, amplitude = acquisition.coherent_correlation(
            synthetic.samples, satellite, lattice, row["doppler_hz"]
        )
        assert peak / floor > 200.0
        circular_error = (shift - row["delay_samples"] + generator.SAMPLES_PER_CODE_PERIOD / 2) % (
            generator.SAMPLES_PER_CODE_PERIOD
        ) - generator.SAMPLES_PER_CODE_PERIOD / 2
        assert abs(circular_error) < 0.5
        assert amplitude == pytest.approx(generator.PER_PRN_AMPLITUDE * 1008 / 1023, rel=0.05)


def test_coarse_search_finds_every_satellite(synthetic):
    lattice = synthetic.lattice
    coarse_step = 500.0
    grid = coarse_step * np.arange(-10, 11)
    power = acquisition.coarse_search(synthetic.samples, list(synthetic.truth), lattice, grid)
    for position, row in enumerate(synthetic.truth.values()):
        doppler_index, code_index = np.unravel_index(
            int(np.argmax(power[:, position, :])), (len(grid), lattice.samples_per_code_period)
        )
        assert abs(grid[doppler_index] - row["doppler_hz"]) <= coarse_step
        expected = row["delay_samples"]
        error = (code_index - expected + generator.SAMPLES_PER_CODE_PERIOD / 2) % (
            generator.SAMPLES_PER_CODE_PERIOD
        ) - generator.SAMPLES_PER_CODE_PERIOD / 2
        assert abs(error) <= 1.0


def test_period_prompts(synthetic):
    lattice = synthetic.lattice
    row = synthetic.truth[4]
    prompts = acquisition.period_prompts(synthetic.samples, 4, lattice, row["doppler_hz"], row["delay_samples"])
    assert len(prompts) == generator.CODE_PERIODS
    assert np.all(np.abs(prompts) > 0)
    phase_steps = np.angle(prompts[1:] / prompts[:-1])
    assert np.all(np.abs(phase_steps) < 0.2)


def test_sharp_doppler_on_a_clean_satellite(synthetic, truth_clean):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        estimate, uncertainty = acquisition.sharp_doppler(
            truth_clean.cleaned[satellite],
            satellite,
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
            generator.NOISE_COMPLEX_VARIANCE,
        )
        assert abs(estimate - row["doppler_hz"]) < 0.5
        assert 0.0 < uncertainty < 1.0


def test_fine_search(synthetic):
    lattice = synthetic.lattice
    row = synthetic.truth[6]
    doppler_hz, peak, floor, shift, amplitude = acquisition.fine_search(
        synthetic.samples, 6, lattice, row["doppler_hz"], 500.0, 31.25
    )
    assert abs(doppler_hz - row["doppler_hz"]) < 10.0
    assert peak / floor > 100.0
    circular_error = (shift - row["delay_samples"] + generator.SAMPLES_PER_CODE_PERIOD / 2) % (
        generator.SAMPLES_PER_CODE_PERIOD
    ) - generator.SAMPLES_PER_CODE_PERIOD / 2
    assert abs(circular_error) < 0.5
    assert amplitude > 0


def test_main_detects_every_satellite_with_accurate_parameters(synthetic, acquisition_rows):
    rows = acquisition_rows
    assert len(rows) == 12
    for satellite, row in synthetic.truth.items():
        result = rows[satellite]
        assert result["detected"]
        assert abs(result["doppler_hz"] - row["doppler_hz"]) < 2.0
        assert abs(result["code_phase_in_chips"] - row["code_phase_chips"]) < 0.1
        assert result["peak_to_floor_ratio"] > 100.0
        assert 60.0 < result["carrier_to_noise_density_dbhz"] < 80.0


def test_main_writes_the_acquisition_table(synthetic, acquisition_rows):
    summary = Path(synthetic.recording).with_name("synthetic_l1_acquisition.csv")
    with open(summary, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    assert set(rows[0]) == {
        "satellite",
        "doppler_hz",
        "doppler_uncertainty_hz",
        "code_phase_in_chips",
        "peak_to_floor_ratio",
        "carrier_to_noise_density_dbhz",
        "detected",
    }


def whole_record_power(samples, satellite, lattice, doppler_hz):
    """Correlation power of the first code period, from one transform over the whole record."""
    from gnss import signals

    length = len(samples)
    code = signals.spreading_code_replica(satellite, length, lattice)
    product = samples * np.conj(signals.carrier(length, lattice, doppler_hz))
    correlation = np.fft.ifft(np.fft.fft(product) * np.conj(np.fft.fft(code)))
    return np.abs(correlation) ** 2


def test_correlating_per_code_period_matches_one_whole_record_transform(synthetic):
    """The period-wise shortcut must return the correlation one whole-record transform returns.

    It is only valid while the replica repeats every code period, so the noiseless case is used:
    there the parabolic sub-sample fit lands exactly on the peak sample, which makes peak and floor
    directly comparable with the whole-record array.
    """
    lattice = synthetic.lattice
    length = lattice.samples_per_code_period * 8
    times = np.arange(length) / lattice.sample_rate_hz
    for satellite, doppler_hz in ((7, 1234.0), (19, -3100.0)):
        samples = acquisition.spreading_code_replica(satellite, length, lattice) * np.exp(
            2j * np.pi * doppler_hz * times
        )
        power = whole_record_power(samples, satellite, lattice, doppler_hz)
        distinct = power[: lattice.samples_per_code_period]
        peak, floor, shift, _ = acquisition.coherent_correlation(
            samples, satellite, lattice, doppler_hz
        )
        assert peak == pytest.approx(float(distinct.max()), rel=1e-6)
        assert floor == pytest.approx(
            float(np.median(np.delete(distinct, int(np.argmax(distinct))))), rel=1e-9
        )
        assert abs((shift + lattice.samples_per_code_period / 2) % lattice.samples_per_code_period
                   - lattice.samples_per_code_period / 2) < 0.5


def test_correlation_falls_back_when_the_record_is_not_whole_code_periods(synthetic):
    """A record the period-wise path cannot describe still correlates correctly."""
    lattice = synthetic.lattice
    length = lattice.samples_per_code_period * 8 - 500
    row = synthetic.truth[6]
    peak, floor, shift, _ = acquisition.coherent_correlation(
        synthetic.samples[:length], 6, lattice, row["doppler_hz"]
    )
    assert peak / floor > 100.0
    circular_error = (shift - row["delay_samples"] + lattice.samples_per_code_period / 2) % (
        lattice.samples_per_code_period
    ) - lattice.samples_per_code_period / 2
    assert abs(circular_error) < 0.5
