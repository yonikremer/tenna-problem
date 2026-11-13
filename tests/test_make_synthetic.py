import csv
from pathlib import Path

import make_synthetic as generator  # type: ignore
import netCDF4
import numpy as np


def truth_path(synthetic):
    return Path(synthetic.recording).with_name("synthetic_l1_truth.csv")


def codes_path(synthetic):
    return Path(synthetic.recording).with_name("synthetic_l1_codes.csv")


def test_self_check():
    generator.self_check()


def test_draw_parameters_are_distinct():
    satellites = generator.draw_parameters(np.random.default_rng(generator.SEED))
    assert len(satellites) == 12
    assert len({satellite["doppler_hz"] for satellite in satellites}) == 12
    assert len({satellite["delay_samples"] for satellite in satellites}) == 12
    assert [satellite["satellite"] for satellite in satellites] == list(range(1, 13))


def test_nominal_and_modified_codes():
    nominal = generator.nominal_code(7)
    flipped = np.array([3, 100, 1022])
    modified = generator.modified_code(7, flipped)
    assert len(nominal) == 1023
    assert set(np.unique(nominal)) == {-1.0, 1.0}
    assert np.array_equal(np.flatnonzero(nominal != modified), flipped)


def test_truth_file_has_every_parameter(synthetic):
    with open(truth_path(synthetic), encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    for row in rows:
        assert len(row["flipped_chips"].split()) == 15
        assert float(row["data_bit"]) == 1.0  # one constant bit across all satellites
        assert float(row["amplitude_per_sample"]) == generator.PER_PRN_AMPLITUDE
    assert len({row["doppler_hz"] for row in rows}) == 12
    assert len({row["delay_samples"] for row in rows}) == 12


def test_code_file_holds_the_modified_codes(synthetic):
    with open(codes_path(synthetic), encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12 * 1023
    for satellite in range(1, 13):
        nominal = synthetic.codes[satellite]["nominal"]
        modified = synthetic.codes[satellite]["modified"]
        flipped = synthetic.codes[satellite]["flipped"]
        truth = synthetic.truth[satellite]
        assert np.count_nonzero(flipped) == 15
        assert set(np.unique(nominal)) == {-1.0, 1.0}
        assert np.array_equal(nominal[flipped], -modified[flipped])
        assert np.array_equal(nominal[~flipped], modified[~flipped])
        assert set(np.flatnonzero(flipped)) == set(truth["flipped_chips"])


def test_recording_metadata_and_samples(synthetic):
    with netCDF4.Dataset(synthetic.recording) as dataset:
        assert dataset.sample_rate_hz == generator.SAMPLE_RATE_HZ
        assert dataset.center_frequency_hz == generator.CENTRE_FREQUENCY_HZ
        assert dataset.nominal_chip_rate_hz == generator.CHIP_RATE_HZ
        assert dataset.nominal_code_length_chips == generator.CODE_LENGTH_IN_CHIPS
        assert dataset.noise_complex_variance == generator.NOISE_COMPLEX_VARIANCE
        assert dataset.per_prn_amplitude_per_sample == generator.PER_PRN_AMPLITUDE
        assert len(dataset["i"]) == generator.LENGTH
        assert len(dataset["q"]) == generator.LENGTH
        recorded = np.asarray(dataset["i"][:]) + 1j * np.asarray(dataset["q"][:])
    assert synthetic.samples.shape == recorded.shape
    assert synthetic.periods == generator.CODE_PERIODS
    assert np.allclose(synthetic.samples, recorded, atol=1e-5)


def test_composite_power_matches_the_signal_model(synthetic):
    expected = (
        12 * generator.PER_PRN_AMPLITUDE**2 + generator.NOISE_COMPLEX_VARIANCE
    )
    measured = float(np.mean(np.abs(synthetic.samples) ** 2))
    assert abs(measured - expected) / expected < 0.05
