"""Solve the assignment end to end: recover the hidden chip modification of a GNSS recording.

One command, one answer:

    python solve.py                              # both supplied recordings
    python solve.py data/gnss_observation.nc      # one recording
    python solve.py my.nc --satellites 1-32      # narrower search, faster

For each recording it runs the full chain, using the package modules for every step:

  1. `gnss.acquisition`   find the PRNs, their Doppler and their code phase.
  2. `gnss.pipeline`      cancel the other PRNs, read one soft value per chip, align the PRNs by a
                          common slope, and sum them to recover the flip pattern.
  3. `gnss.rule`          check that the recovered base is the backward cumulative-Fibonacci set.
  4. `gnss.verification`  measure how much of the received power the recovered codes explain.

Outputs land next to the recording:

  <name>_acquisition.csv   every detected PRN with its measured parameters
  <name>_joint_flips.csv   one row per recovered flipped chip
  <name>_solution.json     the same answer as one machine-readable object

Exit status is 0 when every recording's recovered base is a subset of the Fibonacci rule, and 1
when a recording supports a position the rule cannot produce, so the script can be used as a check.
"""

import argparse
import json
import sys

from gnss import pipeline, tables, verification
from gnss.acquisition import (
    DEFAULT_SATELLITES,
    FALSE_ALARM_PROBABILITY,
    GROUND_RECEIVER_MAX_SPEED_KM_H,
    acquire,
    parse_satellite_spec,
    report,
)
from gnss.rule import explain_base


def solve(recording: str, satellites=None, max_speed_km_h=None, false_alarm_probability=None):
    """Run the whole chain on one recording and return everything the report and the files need."""
    settings = {}
    if max_speed_km_h is not None:
        settings["max_speed_km_h"] = max_speed_km_h
    if false_alarm_probability is not None:
        settings["false_alarm_probability"] = false_alarm_probability

    found = acquire(recording, satellites, **settings)
    recovery = pipeline.recover(recording, acquisition=found)
    pattern = explain_base(recovery.rule.base)
    check = verification.verify(found, recovery.rule.flips)
    return found, recovery, pattern, check


def print_report(recording: str, found, recovery, pattern, check) -> list:
    """Print the report of one recording and return the lines it printed, for logging."""
    lines = []
    lines.append("")
    lines.append("=" * 78)
    lines.append(recording)
    lines.append("=" * 78)
    lines.extend(report(found))
    lines.append("")
    lines.append(f"recovered from {len(recovery.satellites)} PRNs, "
                 f"{found.lattice.code_length_in_chips} chips each")
    lines.extend(recovery.describe_rule())
    lines.extend(recovery.describe_warnings())
    lines.append("")
    lines.append("the mathematical structure behind the base pattern")
    lines.extend(f"  {line}" for line in pattern.describe())
    lines.append("")
    lines.append("recovered flip positions, one line per PRN")
    lines.extend(f"  {line}" for line in recovery.describe_flips())
    lines.append("")
    lines.append("quantitative evidence that the recovered codes explain the recording")
    lines.extend(f"  {line}" for line in check.describe(found.noise_variance))
    for line in lines:
        print(line)
    return lines


def save(recording: str, found, recovery, pattern, check) -> dict:
    """Write the three artifacts and return their paths."""
    paths = {
        "acquisition": tables.write_acquisition(recording, found.detections),
        "flips": tables.write_flips(recording, recovery.rule),
    }
    payload = {
        "recording": recording,
        "sampling": {
            "sample_rate_hz": found.lattice.sample_rate_hz,
            "centre_frequency_hz": found.lattice.centre_frequency_hz,
            "chip_rate_hz": found.lattice.chip_rate_hz,
            "code_length_in_chips": found.lattice.code_length_in_chips,
            "samples_per_code_period": found.lattice.samples_per_code_period,
            "code_periods": found.code_periods,
        },
        "detected_prns": sorted(found.detected),
        "acquisition": [detection.as_row() for detection in found.detections if detection.detected],
        "rule": {
            "slope_chips_per_prn": recovery.rule.slope,
            "alignment_score": round(recovery.rule.score, 4),
            "flipped_chips_per_prn": recovery.rule.count,
            "held_out_gain_db": round(recovery.rule.count_scores[recovery.rule.count], 4),
            "base_pattern": sorted(recovery.rule.base),
            "flips": {
                str(prn): sorted(recovery.rule.flips[prn]) for prn in sorted(recovery.rule.flips)
            },
        },
        "pattern": {
            "name": pattern.name,
            "formula": pattern.formula,
            "matches": pattern.matches,
            "increments": list(pattern.increments),
            "offsets_from_start": list(pattern.offsets_from_start),
            "positions_missing_here": list(pattern.missing),
            "positions_not_in_the_rule": list(pattern.unexpected),
        },
        "evidence": {
            "noise_variance": round(found.noise_variance, 6),
            "nominal_residual_power": round(check.nominal_residual_power, 6),
            "recovered_residual_power": round(check.recovered_residual_power, 6),
            "residual_gain_db": round(check.residual_gain_db, 4),
            "explained_fraction": round(check.explained_fraction, 6),
            "per_prn_gain_db": {str(prn): round(gain, 4) for prn, gain in sorted(check.gains_db.items())},
        },
    }
    paths["summary"] = tables.summary_path(recording)
    try:
        with open(paths["summary"], "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    except OSError as error:
        raise SystemExit(f"cannot write {paths['summary']}: {error}") from error
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python solve.py",
        description="Recover the hidden chip modification of GPS L1 C/A recordings, end to end.",
    )
    parser.add_argument(
        "recordings",
        nargs="*",
        default=["data/gnss_observation.nc", "data/gnss_observation2.nc"],
        help="NetCDF recordings to solve (default: the two supplied files)",
    )
    parser.add_argument(
        "--satellites",
        default=DEFAULT_SATELLITES,
        help=f"satellite numbers to search, e.g. 1-32 (default {DEFAULT_SATELLITES})",
    )
    parser.add_argument(
        "--max-speed-km-h",
        type=float,
        default=GROUND_RECEIVER_MAX_SPEED_KM_H,
        help="largest expected receiver speed; sets the Doppler span",
    )
    parser.add_argument(
        "--false-alarm-probability",
        type=float,
        default=FALSE_ALARM_PROBABILITY,
        help="per-satellite false-alarm probability for detection",
    )
    arguments = parser.parse_args(argv)

    satellites = parse_satellite_spec(arguments.satellites)
    failures = 0
    for recording in arguments.recordings:
        found, recovery, pattern, check = solve(
            recording,
            satellites,
            max_speed_km_h=arguments.max_speed_km_h,
            false_alarm_probability=arguments.false_alarm_probability,
        )
        print_report(recording, found, recovery, pattern, check)
        paths = save(recording, found, recovery, pattern, check)
        for label, path in paths.items():
            print(f"  -> {label:<12} {path}")
        if not pattern.matches:
            print(f"  note: {recording} supports {len(pattern.offsets_from_start)} of "
                  f"{len(pattern.cumulative_chips)} rule positions; see the pattern section above")
        # A recording that supports fewer rule positions is a sensitivity limit, not a different
        # rule. Only a position the rule cannot produce is a real contradiction.
        if pattern.unexpected:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
