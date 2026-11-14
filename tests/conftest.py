import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
DATA_TESTS = ROOT / "data" / "tests"
for path in (ROOT, TESTS, ROOT / "vendor"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from gnss import acquisition, alignment  # noqa: E402

import make_synthetic  # type: ignore  # noqa: E402


def read_truth(path):
    import csv

    with open(path, encoding="utf-8") as handle:
        return {
            int(row["satellite"]): {
                **row,
                "doppler_hz": float(row["doppler_hz"]),
                "delay_samples": int(row["delay_samples"]),
                "code_phase_chips": float(row["code_phase_chips"]),
                "carrier_phase_rad": float(row["carrier_phase_rad"]),
                "amplitude_per_sample": float(row["amplitude_per_sample"]),
                "data_bit": float(row["data_bit"]),
                "flipped_chips": [int(value) for value in row["flipped_chips"].split()],
            }
            for row in csv.DictReader(handle)
        }


def read_codes(path):
    import csv

    rows = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            satellite = int(row["satellite"])
            entry = rows.setdefault(
                satellite,
                {
                    "nominal": np.zeros(make_synthetic.CODE_LENGTH_IN_CHIPS),
                    "modified": np.zeros(make_synthetic.CODE_LENGTH_IN_CHIPS),
                    "flipped": np.zeros(make_synthetic.CODE_LENGTH_IN_CHIPS, dtype=bool),
                },
            )
            index = int(row["chip_index"])
            entry["nominal"][index] = int(row["nominal_chip"])
            entry["modified"][index] = int(row["modified_chip"])
            entry["flipped"][index] = row["flipped"] == "True"
    return rows


@pytest.fixture(scope="session")
def synthetic():
    make_synthetic.self_check()
    make_synthetic.main(make_synthetic.SEED)
    recording = DATA_TESTS / "synthetic_l1.nc"
    truth = read_truth(DATA_TESTS / "synthetic_l1_truth.csv")
    codes = read_codes(DATA_TESTS / "synthetic_l1_codes.csv")
    samples, periods, lattice = acquisition.load_recording(str(recording))
    return SimpleNamespace(
        recording=str(recording),
        truth=truth,
        codes=codes,
        samples=samples,
        periods=periods,
        lattice=lattice,
    )


@pytest.fixture(scope="session")
def acquisition_rows(synthetic):
    import csv

    acquisition.main([synthetic.recording, "--satellites", "1-12"])
    summary = synthetic.recording.replace(".nc", "_acquisition.csv")
    with open(summary, encoding="utf-8") as handle:
        return {
            int(row["satellite"]): {
                **row,
                "doppler_hz": float(row["doppler_hz"]),
                "doppler_uncertainty_hz": float(row["doppler_uncertainty_hz"]),
                "code_phase_in_chips": float(row["code_phase_in_chips"]),
                "peak_to_floor_ratio": float(row["peak_to_floor_ratio"]),
                "carrier_to_noise_density_dbhz": float(row["carrier_to_noise_density_dbhz"]),
                "detected": row["detected"] == "True",
            }
            for row in csv.DictReader(handle)
        }


@pytest.fixture(scope="session")
def truth_clean(synthetic):
    """Truth-exact per-satellite signals, residual, and the cleaned signal for each satellite.

    The generator knows every chip it flipped, so this fixture can subtract every other satellite
    exactly. It is the known-answer probe for chip extraction and for the phase-slope estimator.
    """
    samples = synthetic.samples
    length = len(samples)
    times = np.arange(length) / synthetic.lattice.sample_rate_hz
    units, coefficients, shifts = {}, {}, {}
    for satellite, row in synthetic.truth.items():
        doppler_hz = row["doppler_hz"]
        shifts[satellite] = alignment.aligned_shift(samples, satellite, synthetic.lattice, doppler_hz)
        modified = synthetic.codes[satellite]["modified"]
        chip_index = (
            (np.arange(length) - row["delay_samples"]) // make_synthetic.SAMPLES_PER_CHIP
        ) % make_synthetic.CODE_LENGTH_IN_CHIPS
        unit = modified[chip_index] * np.exp(2j * np.pi * doppler_hz * times)
        units[satellite] = unit
        coefficients[satellite] = np.vdot(unit, samples) / length
    residual = samples - sum(coefficients[satellite] * units[satellite] for satellite in units)
    cleaned = {
        satellite: residual + coefficients[satellite] * units[satellite] for satellite in units
    }
    return SimpleNamespace(
        units=units,
        coefficients=coefficients,
        residual=residual,
        cleaned=cleaned,
        shifts=shifts,
    )


@pytest.fixture(scope="session")
def cu8_recording(synthetic):
    from analysis import nc2cu8

    destination = DATA_TESTS / "synthetic_l1.cu8"
    nc2cu8.main(synthetic.recording, str(destination))
    return str(destination)


@pytest.fixture(scope="session")
def shared_55():
    """The 55 dB-Hz recording that follows the real rule, recovered end to end."""
    import csv

    import make_shared_55  # type: ignore

    from gnss import pipeline, tables

    make_shared_55.self_check()
    make_shared_55.main()
    recording = str(DATA_TESTS / "synthetic_shared_55.nc")
    with open(DATA_TESTS / "synthetic_shared_55_truth.csv", encoding="utf-8") as handle:
        truth = {
            int(row["satellite"]): {
                **row,
                "doppler_hz": float(row["doppler_hz"]),
                "delay_samples": int(row["delay_samples"]),
                "base_pattern": {int(chip) for chip in row["base_pattern"].split()},
                "shift_chips": int(row["shift_chips"]),
                "flipped_chips": {int(chip) for chip in row["flipped_chips"].split()},
                "data_bit": float(row["data_bit"]),
                "cn0_dbhz": float(row["cn0_dbhz"]),
            }
            for row in csv.DictReader(handle)
        }
    recovery = pipeline.recover(recording, satellites=range(1, 13))
    # the analysis scripts read the acquisition table by convention, so the fixture must produce it
    # rather than rely on one left behind by an earlier session
    tables.write_acquisition(recording, recovery.acquisition.detections)
    return {
        "recording": recording,
        "truth": truth,
        "recovery": recovery,
        "samples": recovery.samples,
        "lattice": recovery.lattice,
    }
