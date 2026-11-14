"""Generate the realistic 55 dB-Hz recording: one common flip pattern, shifted 2 chips per PRN.

This is the model the real assignment describes: the PRN sequences are modified by a common rule,
not by independent random bits. The base pattern is the Fibonacci prefix-sum rule observed in
`gnss_observation.nc`, and PRN k uses it shifted by `2 * (PRN - 1)` chips.
"""

import csv
import os
import sys

import netCDF4
import numpy as np

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
DATA_DIR = os.path.join(ROOT, "data", "tests")
sys.path.insert(0, os.path.join(ROOT, "vendor"))
sys.path.insert(0, TESTS_DIR)
import make_synthetic as base  # type: ignore  # noqa: E402

FIBONACCI = (1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377)
BASE_START = 1020
BASE_PATTERN = tuple(
    sorted({(BASE_START - sum(FIBONACCI[:step])) % base.CODE_LENGTH_IN_CHIPS for step in range(15)})
)
SHIFT_PER_PRN = 2
PER_PRN_AMPLITUDE = 0.278
NOISE_COMPLEX_VARIANCE = 1.0
CARRIER_TO_NOISE_DENSITY_DBHZ = round(
    10.0 * np.log10(PER_PRN_AMPLITUDE**2 * base.SAMPLE_RATE_HZ / NOISE_COMPLEX_VARIANCE), 3
)
SEED = 20261113
DATA_BIT = 1.0


def flips_for(prn):
    return np.array(
        sorted({(chip - SHIFT_PER_PRN * (prn - 1)) % base.CODE_LENGTH_IN_CHIPS for chip in BASE_PATTERN})
    )


def draw_parameters(generator):
    satellites = base.draw_parameters(generator)
    for satellite in satellites:
        satellite["flipped_chips"] = flips_for(satellite["prn"])
    return satellites


def synthetic_samples(satellites, seed):
    sample_index = np.arange(base.LENGTH)
    composite = np.zeros(base.LENGTH, dtype=np.complex128)
    for satellite in satellites:
        code = base.modified_code(satellite["prn"], satellite["flipped_chips"])
        chips = ((sample_index - satellite["delay_samples"]) // base.SAMPLES_PER_CHIP) % base.CODE_LENGTH_IN_CHIPS
        carrier = np.exp(
            2j * np.pi * satellite["doppler_hz"] * sample_index / base.SAMPLE_RATE_HZ
            + 1j * satellite["carrier_phase_rad"]
        )
        satellite["amplitude_per_sample"] = PER_PRN_AMPLITUDE
        composite += PER_PRN_AMPLITUDE * code[chips] * carrier
    noise_generator = np.random.default_rng(seed + 1)
    noise = (
        noise_generator.standard_normal(base.LENGTH)
        + 1j * noise_generator.standard_normal(base.LENGTH)
    ) * np.sqrt(NOISE_COMPLEX_VARIANCE / 2.0)
    return composite + noise


def write_recording(path, samples):
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("sample", base.LENGTH)
        real = dataset.createVariable("i", "f4", ("sample",))
        imaginary = dataset.createVariable("q", "f4", ("sample",))
        real[:] = samples.real.astype(np.float32)
        imaginary[:] = samples.imag.astype(np.float32)
        dataset.title = "Synthetic common-rule GPS L1 C/A at 55 dB-Hz per PRN"
        dataset.description = (
            f"{len(base.SATELLITE_NUMBERS)} GPS L1 C/A signals, one common {len(BASE_PATTERN)}-chip "
            f"pattern, shifted {SHIFT_PER_PRN} chips per PRN, one constant data bit"
        )
        dataset.sample_rate_hz = base.SAMPLE_RATE_HZ
        dataset.center_frequency_hz = base.CENTRE_FREQUENCY_HZ
        dataset.nominal_chip_rate_hz = base.CHIP_RATE_HZ
        dataset.nominal_code_length_chips = base.CODE_LENGTH_IN_CHIPS
        dataset.observation_duration_seconds = base.LENGTH / base.SAMPLE_RATE_HZ
        dataset.target_cn0_dbhz_per_prn = CARRIER_TO_NOISE_DENSITY_DBHZ
        dataset.per_prn_amplitude_per_sample = PER_PRN_AMPLITUDE
        dataset.noise_complex_variance = NOISE_COMPLEX_VARIANCE
        dataset.noise_sigma_per_real_dimension = float(np.sqrt(NOISE_COMPLEX_VARIANCE / 2.0))
        dataset.common_shift_chips_per_prn = SHIFT_PER_PRN
        dataset.base_pattern = " ".join(str(chip) for chip in BASE_PATTERN)
        dataset.random_seed = SEED


def write_truth(truth_path, codes_path, satellites):
    with open(truth_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "satellite",
                "prn",
                "doppler_hz",
                "delay_samples",
                "code_phase_chips",
                "carrier_phase_rad",
                "amplitude_per_sample",
                "data_bit",
                "cn0_dbhz",
                "base_pattern",
                "shift_chips",
                "flipped_chips",
            ]
        )
        for satellite in satellites:
            writer.writerow(
                [
                    satellite["satellite"],
                    satellite["prn"],
                    round(satellite["doppler_hz"], 3),
                    satellite["delay_samples"],
                    round(satellite["delay_samples"] * base.CODE_LENGTH_IN_CHIPS / base.SAMPLES_PER_CODE_PERIOD, 3),
                    round(satellite["carrier_phase_rad"], 6),
                    round(satellite["amplitude_per_sample"], 6),
                    DATA_BIT,
                    CARRIER_TO_NOISE_DENSITY_DBHZ,
                    " ".join(str(chip) for chip in BASE_PATTERN),
                    SHIFT_PER_PRN * (satellite["prn"] - 1),
                    " ".join(str(int(chip)) for chip in satellite["flipped_chips"]),
                ]
            )

    with open(codes_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["satellite", "chip_index", "nominal_chip", "modified_chip", "flipped"])
        for satellite in satellites:
            nominal = base.nominal_code(satellite["prn"])
            modified = base.modified_code(satellite["prn"], satellite["flipped_chips"])
            flipped = {int(chip) for chip in satellite["flipped_chips"]}
            for index in range(base.CODE_LENGTH_IN_CHIPS):
                writer.writerow(
                    [
                        satellite["satellite"],
                        index,
                        int(nominal[index]),
                        int(modified[index]),
                        index in flipped,
                    ]
                )


def main(seed=SEED):
    generator = np.random.default_rng(seed)
    satellites = draw_parameters(generator)
    samples = synthetic_samples(satellites, seed)
    os.makedirs(DATA_DIR, exist_ok=True)
    recording = os.path.join(DATA_DIR, "synthetic_shared_55.nc")
    truth = os.path.join(DATA_DIR, "synthetic_shared_55_truth.csv")
    codes = os.path.join(DATA_DIR, "synthetic_shared_55_codes.csv")
    write_recording(recording, samples)
    write_truth(truth, codes, satellites)
    print(f"{recording}: {base.LENGTH} samples, 12 PRNs, common rule, {CARRIER_TO_NOISE_DENSITY_DBHZ:.1f} dB-Hz")
    print(f"  base pattern: {' '.join(str(chip) for chip in BASE_PATTERN)}")
    print(f"  shift per PRN: {SHIFT_PER_PRN} chips")
    print(f"-> {truth}")


def self_check():
    if len(BASE_PATTERN) != 15:
        raise SystemExit("base pattern does not have 15 distinct positions")
    if len(set(BASE_PATTERN)) != 15:
        raise SystemExit("base pattern has duplicate positions")
    for prn in base.SATELLITE_NUMBERS:
        flips = flips_for(prn)
        if len(flips) != 15:
            raise SystemExit(f"PRN {prn} has {len(flips)} flips, expected 15")
        expected = {(chip - SHIFT_PER_PRN * (prn - 1)) % base.CODE_LENGTH_IN_CHIPS for chip in BASE_PATTERN}
        if set(flips.tolist()) != expected:
            raise SystemExit(f"PRN {prn} does not follow the shifted-base rule")


if __name__ == "__main__":
    self_check()
    try:
        requested_seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    except ValueError as error:
        raise SystemExit(f"bad seed {sys.argv[1]!r}: {error}") from error
    main(requested_seed)
