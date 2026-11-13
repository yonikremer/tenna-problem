"""CSV artifacts of one solution: the acquisition table and the recovered flip table.

The tables are the answer in plain form: a spreadsheet reader can check every number without
running the code. File names are derived from the recording name so a run never overwrites a
different recording's result.
"""

import csv

ACQUISITION_COLUMNS = (
    "satellite",
    "doppler_hz",
    "doppler_uncertainty_hz",
    "code_phase_in_chips",
    "peak_to_floor_ratio",
    "carrier_to_noise_density_dbhz",
    "detected",
)

FLIPS_COLUMNS = ("satellite", "shift_chips", "chip_index")


def artifact(recording: str, suffix: str) -> str:
    """Path of one artifact for a recording: `name.nc` -> `name<suffix>`."""
    return recording.rsplit(".", 1)[0] + suffix


def acquisition_path(recording: str) -> str:
    return artifact(recording, "_acquisition.csv")


def flips_path(recording: str) -> str:
    return artifact(recording, "_joint_flips.csv")


def summary_path(recording: str) -> str:
    return artifact(recording, "_solution.json")


def _write_rows(destination: str, columns, rows) -> str:
    try:
        with open(destination, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise SystemExit(f"cannot write {destination}: {error}") from error
    return destination


def write_acquisition(recording: str, detections) -> str:
    """One row per searched satellite, best peak-to-floor first, with the detection verdict.

    Undetected satellites are kept so the table documents the whole search, not just its successes.
    """
    return _write_rows(
        acquisition_path(recording), ACQUISITION_COLUMNS, [d.as_row() for d in detections]
    )


def write_flips(recording: str, rule) -> str:
    """One row per recovered flipped chip, so the answer is a plain table."""
    destination = flips_path(recording)
    try:
        with open(destination, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(FLIPS_COLUMNS)
            for satellite, shift_chips, chip_index in rule.table():
                writer.writerow([satellite, shift_chips, chip_index])
    except OSError as error:
        raise SystemExit(f"cannot write {destination}: {error}") from error
    return destination


def read_detections(recording: str) -> dict:
    """{satellite: doppler_hz} for the detected rows of a previously written acquisition table."""
    path = acquisition_path(recording)
    try:
        with open(path, encoding="utf-8") as handle:
            return {
                int(row["satellite"]): float(row["doppler_hz"])
                for row in csv.DictReader(handle)
                if row["detected"] == "True"
            }
    except OSError as error:
        raise SystemExit(f"cannot read {path}: {error}") from error
