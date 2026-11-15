"""CSV artifacts of one solution: the acquisition table, the recovered flip table, and the codes.

The tables are the answer in plain form: a spreadsheet reader can check every number without
running the code. File names are derived from the recording name so a run never overwrites a
different recording's result.
"""

import csv

import numpy as np

from .signals import spreading_code_replica

ACQUISITION_COLUMNS = (
    "satellite",
    "doppler_hz",
    "doppler_uncertainty_hz",
    "code_phase_in_chips",
    "peak_to_floor_ratio",
    "carrier_to_noise_density_dbhz",
    "detected",
)

FLIPS_COLUMNS = ("satellite", "shift_chips", "chip_index", "base_chip")

POSITIONS_COLUMNS = ("prn", "chip_index")

CODES_COLUMNS = (
    "prn",
    "chips",
    "modified_count",
    "modified_indexes",
    "original_code",
    "transmitted_code",
)


def artifact(recording: str, suffix: str) -> str:
    """Path of one artifact for a recording: `name.nc` -> `name<suffix>`."""
    return recording.rsplit(".", 1)[0] + suffix


def acquisition_path(recording: str) -> str:
    return artifact(recording, "_acquisition.csv")


def flips_path(recording: str) -> str:
    return artifact(recording, "_joint_flips.csv")


def summary_path(recording: str) -> str:
    return artifact(recording, "_solution.json")


def positions_path(recording: str) -> str:
    return artifact(recording, "_modified_positions.csv")


def codes_path(recording: str) -> str:
    return artifact(recording, "_transmitted_codes.csv")


def codes_matrix_path(recording: str) -> str:
    return artifact(recording, "_transmitted_codes.npz")


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
            for satellite, shift_chips, chip_index, base_chip in rule.table():
                writer.writerow([satellite, shift_chips, chip_index, base_chip])
    except OSError as error:
        raise SystemExit(f"cannot write {destination}: {error}") from error
    return destination


def write_positions(recording: str, flips) -> str:
    """One row per modified chip: the positions alone, with no shift column."""
    rows = [
        {"prn": prn, "chip_index": chip}
        for prn in sorted(flips)
        for chip in sorted(flips[prn])
    ]
    return _write_rows(positions_path(recording), POSITIONS_COLUMNS, rows)


def transmitted_codes(lattice, flips) -> tuple:
    """Nominal and transmitted 1023-chip code of every PRN, as two `(PRNs, chips)` arrays.

    The transmitted code is the published code with the recovered chips negated. A chip that is not
    exactly +-1, or a changed chip that is not in the recovered set, is a bug, so both are checked
    here rather than trusted.
    """
    prns = sorted(flips)
    length = lattice.code_length_in_chips
    nominal = np.zeros((len(prns), length), dtype=np.int8)
    transmitted = np.zeros((len(prns), length), dtype=np.int8)
    for row, prn in enumerate(prns):
        code = np.real(spreading_code_replica(prn, length, lattice, increment=1.0))
        nominal[row] = np.sign(code)
        changed = code.copy()
        changed[sorted(flips[prn])] *= -1.0
        transmitted[row] = np.sign(changed)
        if not np.all(np.abs(code) == 1.0):
            raise SystemExit(f"PRN {prn}: nominal code is not +-1")
        if set(np.flatnonzero(transmitted[row] != nominal[row]).tolist()) != set(flips[prn]):
            raise SystemExit(f"PRN {prn}: changed chips do not match the recovered flips")
    return np.array(prns, dtype=int), nominal, transmitted


def write_codes(recording: str, lattice, flips) -> dict:
    """Write the 1023-chip codes of every PRN as CSV and as arrays, plus the positions alone.

    The CSV is one row per PRN, so a reader sees a whole code at a glance: the codes are space
    separated, and the modified indexes sit next to them for comparison.
    """
    prns, nominal, transmitted = transmitted_codes(lattice, flips)
    flipped = {int(prn): sorted(int(chip) for chip in flips[prn]) for prn in prns}
    rows = [
        {
            "prn": int(prn),
            "chips": int(nominal.shape[1]),
            "modified_count": len(flipped[int(prn)]),
            "modified_indexes": " ".join(str(chip) for chip in flipped[int(prn)]),
            "original_code": " ".join(str(int(value)) for value in nominal[row]),
            "transmitted_code": " ".join(str(int(value)) for value in transmitted[row]),
        }
        for row, prn in enumerate(prns)
    ]
    paths = {
        "positions": write_positions(recording, flips),
        "codes": _write_rows(codes_path(recording), CODES_COLUMNS, rows),
        "codes_matrix": codes_matrix_path(recording),
    }
    try:
        np.savez_compressed(
            paths["codes_matrix"], prns=prns, nominal=nominal, transmitted=transmitted
        )
    except OSError as error:
        raise SystemExit(f"cannot write {paths['codes_matrix']}: {error}") from error
    return paths


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
