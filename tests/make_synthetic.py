"""Build a synthetic GPS L1 C/A recording with a saved, exact answer key.

The recording mirrors the real files' geometry (4 samples per chip, 8 code periods, one constant
navigation data bit) so every work script can be pointed at it. Everything random is drawn from one
seed and written to disk, because a test is only worth running if the truth it is checked against can
be read back later:

  synthetic_l1.nc         complex i/q, same variables and metadata names as gnss_observation.nc
  synthetic_l1_truth.csv  one row per satellite: Doppler, delay, carrier phase, amplitude, bit,
                          and the 15 modified chip positions
  synthetic_l1_codes.csv  all 1023 chips of every satellite: nominal, modified, and whether flipped

Signal model (deliberately the same as the real recording states about itself):
  constant navigation data bit, rectangular chips, constant carrier phase and Doppler,
  integer-sample code delay, independent complex Gaussian noise per sample.
"""

import csv
import os
import sys

import netCDF4
import numpy as np

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, os.path.join(ROOT, "vendor"))
import gnsstools.gps.ca as ca  # type: ignore  # noqa: E402

SATELLITE_NUMBERS = tuple(range(1, 13))  # twelve codes: PRN 1..12
SAMPLE_RATE_HZ = 4_092_000.0
CENTRE_FREQUENCY_HZ = 1_575_420_000.0
CHIP_RATE_HZ = 1_023_000.0
CODE_LENGTH_IN_CHIPS = 1023
CODE_PERIODS = 8
SAMPLES_PER_CHIP = int(round(SAMPLE_RATE_HZ / CHIP_RATE_HZ))
SAMPLES_PER_CODE_PERIOD = SAMPLES_PER_CHIP * CODE_LENGTH_IN_CHIPS
LENGTH = SAMPLES_PER_CODE_PERIOD * CODE_PERIODS

FLIPS_PER_CODE = 15
PER_PRN_AMPLITUDE = 0.278  # same per-satellite amplitude as the real 55 dB-Hz recordings
NOISE_COMPLEX_VARIANCE = 0.01  # lower than the real files, so the 15 chip positions are recoverable exactly
# Carrier-to-noise density implied by the two constants above: A^2 * Fs / N0.
CARRIER_TO_NOISE_DENSITY_DBHZ = round(
    10.0 * np.log10(PER_PRN_AMPLITUDE**2 * SAMPLE_RATE_HZ / NOISE_COMPLEX_VARIANCE), 3
)
DOPPLER_LIMIT_HZ = 3_500.0
DATA_BIT = 1.0
SEED = 20261113


def nominal_code(prn):
    """Published +-1 C/A code of one satellite, one full code period."""
    return 1.0 - 2.0 * ca.ca_code(prn).astype(np.float64)


def draw_parameters(generator):
    """One dictionary per satellite: every random quantity, drawn independently."""
    satellites = []
    # Dopplers and delays drawn without replacement, so no two satellites share either value.
    dopplers = generator.choice(
        np.arange(-DOPPLER_LIMIT_HZ, DOPPLER_LIMIT_HZ + 1.0, 1.0), len(SATELLITE_NUMBERS), replace=False
    )
    delays = generator.choice(np.arange(SAMPLES_PER_CODE_PERIOD), len(SATELLITE_NUMBERS), replace=False)
    for prn, doppler_hz, delay_samples in zip(SATELLITE_NUMBERS, dopplers, delays, strict=True):
        flipped = np.sort(
            generator.choice(CODE_LENGTH_IN_CHIPS, FLIPS_PER_CODE, replace=False)
        )
        satellites.append(
            {
                "satellite": prn,
                "prn": prn,
                "doppler_hz": float(doppler_hz),
                "delay_samples": int(delay_samples),
                "carrier_phase_rad": float(generator.uniform(0.0, 2.0 * np.pi)),
                "flipped_chips": flipped,
            }
        )
    return satellites


def modified_code(prn, flipped_chips):
    code = nominal_code(prn).copy()
    code[flipped_chips] *= -1.0
    return code


def synthetic_samples(satellites, seed, noise_variance=None):
    """Composite signal plus independent complex Gaussian noise."""
    if noise_variance is None:
        noise_variance = NOISE_COMPLEX_VARIANCE
    amplitude = PER_PRN_AMPLITUDE
    sample_index = np.arange(LENGTH)
    composite = np.zeros(LENGTH, dtype=np.complex128)
    for satellite in satellites:
        code = modified_code(satellite["prn"], satellite["flipped_chips"])
        # Record sample n holds the code chip that sits (n - delay) samples into the code.
        chips = ((sample_index - satellite["delay_samples"]) // SAMPLES_PER_CHIP) % CODE_LENGTH_IN_CHIPS
        carrier = np.exp(
            2j * np.pi * satellite["doppler_hz"] * sample_index / SAMPLE_RATE_HZ
            + 1j * satellite["carrier_phase_rad"]
        )
        satellite["amplitude_per_sample"] = float(amplitude)
        composite += amplitude * code[chips] * carrier

    noise_generator = np.random.default_rng(seed + 1)
    noise = (
        noise_generator.standard_normal(LENGTH) + 1j * noise_generator.standard_normal(LENGTH)
    ) * np.sqrt(noise_variance / 2.0)
    return composite + noise


def write_recording(path, samples):
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.createDimension("sample", LENGTH)
        real = dataset.createVariable("i", "f4", ("sample",))
        imaginary = dataset.createVariable("q", "f4", ("sample",))
        real[:] = samples.real.astype(np.float32)
        imaginary[:] = samples.imag.astype(np.float32)

        dataset.title = "Synthetic composite GPS L1 C/A, truth saved beside the file"
        dataset.description = (
            f"{len(SATELLITE_NUMBERS)} synthetic GPS L1 C/A signals, {CODE_PERIODS} ms, "
            f"{FLIPS_PER_CODE} modified chips per code, complex AWGN"
        )
        dataset.sample_rate_hz = SAMPLE_RATE_HZ
        dataset.center_frequency_hz = CENTRE_FREQUENCY_HZ
        dataset.nominal_chip_rate_hz = CHIP_RATE_HZ
        dataset.nominal_code_length_chips = CODE_LENGTH_IN_CHIPS
        dataset.observation_duration_seconds = LENGTH / SAMPLE_RATE_HZ
        dataset.target_cn0_dbhz_per_prn = CARRIER_TO_NOISE_DENSITY_DBHZ
        dataset.per_prn_amplitude_per_sample = PER_PRN_AMPLITUDE
        dataset.noise_complex_variance = NOISE_COMPLEX_VARIANCE
        dataset.noise_sigma_per_real_dimension = float(np.sqrt(NOISE_COMPLEX_VARIANCE / 2.0))
        dataset.random_seed = SEED
        dataset.synthetic_truth = "Exact generator parameters in synthetic_l1_truth.csv and synthetic_l1_codes.csv"
        dataset.signal_model = (
            "Constant nav bit, rectangular chips, constant carrier phase/Doppler, "
            "integer-sample delay, independent CN(0,N0) noise"
        )


def write_truth(truth_path, codes_path, satellites):
    columns = [
        "satellite",
        "prn",
        "doppler_hz",
        "delay_samples",
        "code_phase_chips",
        "carrier_phase_rad",
        "amplitude_per_sample",
        "data_bit",
        "cn0_dbhz",
        "flipped_chips",
    ]
    with open(truth_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for satellite in satellites:
            writer.writerow(
                [
                    satellite["satellite"],
                    satellite["prn"],
                    round(satellite["doppler_hz"], 3),
                    satellite["delay_samples"],
                    round(satellite["delay_samples"] * CODE_LENGTH_IN_CHIPS / SAMPLES_PER_CODE_PERIOD, 3),
                    round(satellite["carrier_phase_rad"], 6),
                    round(satellite["amplitude_per_sample"], 6),
                    DATA_BIT,
                    CARRIER_TO_NOISE_DENSITY_DBHZ,
                    " ".join(str(int(chip)) for chip in satellite["flipped_chips"]),
                ]
            )

    with open(codes_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["satellite", "chip_index", "nominal_chip", "modified_chip", "flipped"])
        for satellite in satellites:
            nominal = nominal_code(satellite["prn"])
            modified = modified_code(satellite["prn"], satellite["flipped_chips"])
            flipped = {int(chip) for chip in satellite["flipped_chips"]}
            for index in range(CODE_LENGTH_IN_CHIPS):
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

    recording = os.path.join(TESTS_DIR, "synthetic_l1.nc")
    truth = os.path.join(TESTS_DIR, "synthetic_l1_truth.csv")
    codes = os.path.join(TESTS_DIR, "synthetic_l1_codes.csv")
    write_recording(recording, samples)
    write_truth(truth, codes, satellites)

    print(f"{recording}: {LENGTH} samples at {SAMPLE_RATE_HZ:g} Hz, {CODE_PERIODS} code periods")
    print(f"  {len(satellites)} satellites, {FLIPS_PER_CODE} modified chips each, one constant data bit")
    print(f"{'sat':>4} {'doppler Hz':>11} {'delay samples':>14} {'code chips':>11}  flipped chips")
    for satellite in satellites:
        print(
            f"{satellite['satellite']:>4} {satellite['doppler_hz']:>11.1f} {satellite['delay_samples']:>14d} "
            f"{satellite['delay_samples'] * CODE_LENGTH_IN_CHIPS / SAMPLES_PER_CODE_PERIOD:>11.2f}  "
            f"{' '.join(str(int(chip)) for chip in satellite['flipped_chips'])}"
        )
    print(f"-> {truth}")
    print(f"-> {codes}")


def self_check():
    """The generator must reproduce its own truth, and the truth files must round-trip."""
    generator = np.random.default_rng(SEED)
    satellites = draw_parameters(generator)
    if len({satellite["doppler_hz"] for satellite in satellites}) != len(satellites):
        raise SystemExit("generator drew duplicate Doppler frequencies")
    if len({satellite["delay_samples"] for satellite in satellites}) != len(satellites):
        raise SystemExit("generator drew duplicate code delays")
    for satellite in satellites:
        nominal = nominal_code(satellite["prn"])
        modified = modified_code(satellite["prn"], satellite["flipped_chips"])
        changed = np.flatnonzero(nominal != modified)
        if not np.array_equal(changed, np.sort(satellite["flipped_chips"])):
            raise SystemExit(f"satellite {satellite['satellite']} modified chips do not match the truth list")
        if len(changed) != FLIPS_PER_CODE:
            raise SystemExit(f"satellite {satellite['satellite']} has {len(changed)} flips, expected {FLIPS_PER_CODE}")


if __name__ == "__main__":
    self_check()
    try:
        requested_seed = int(sys.argv[1]) if len(sys.argv) > 1 else SEED
    except ValueError as error:
        raise SystemExit(f"bad seed {sys.argv[1]!r}: {error}") from error
    main(requested_seed)
