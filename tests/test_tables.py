"""Tests for the CSV/JSON artifacts: the answer in a form a spreadsheet can check."""

import csv
import json

import numpy as np
import pytest

from gnss import acquisition, pipeline, tables


def test_artifact_paths_are_named_after_the_recording():
    assert tables.acquisition_path("data/run.nc") == "data/run_acquisition.csv"
    assert tables.flips_path("run.nc") == "run_joint_flips.csv"
    assert tables.summary_path("run.nc") == "run_solution.json"
    assert tables.artifact("run.1.nc", "_x.csv") == "run.1_x.csv"


def test_acquisition_table_round_trips(shared_55):
    recording = shared_55["recording"]
    destination = tables.write_acquisition(recording, shared_55["recovery"].acquisition.detections)

    with open(destination, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == set(tables.ACQUISITION_COLUMNS)
    assert len(rows) == 12
    assert all(row["detected"] == "True" for row in rows)

    detected = tables.read_detections(recording)
    assert set(detected) == set(range(1, 13))
    assert all(isinstance(value, float) for value in detected.values())


def test_acquisition_table_keeps_undetected_rows_for_audit(tmp_path):
    destination = tmp_path / "one_acquisition.csv"
    rows = [
        acquisition.Detection(1, 100.0, 1.0, 10.0, 500.0, 54.0, True),
        acquisition.Detection(2, 200.0, 1.0, 20.0, 5.0, None, False),
    ]
    written = tables._write_rows(str(destination), tables.ACQUISITION_COLUMNS, [r.as_row() for r in rows])
    with open(written, encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    assert [row["satellite"] for row in saved] == ["1", "2"]
    assert [row["detected"] for row in saved] == ["True", "False"]
    assert saved[1]["carrier_to_noise_density_dbhz"] == ""


def test_flip_table_round_trips(shared_55):
    recording = shared_55["recording"]
    destination = tables.write_flips(recording, shared_55["recovery"].rule)

    with open(destination, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == set(tables.FLIPS_COLUMNS)
    assert len(rows) == 12 * 15
    assert {int(row["chip_index"]) for row in rows if row["satellite"] == "1"} == {
        int(chip) for chip in shared_55["recovery"].rule.flips[1]
    }


def test_codes_artifact_carries_every_chip_of_every_prn(shared_55):
    recording = shared_55["recording"]
    rule = shared_55["recovery"].rule
    paths = tables.write_codes(recording, shared_55["lattice"], rule.flips)
    length = shared_55["lattice"].code_length_in_chips

    with open(paths["codes"], encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == set(tables.CODES_COLUMNS)
    assert len(rows) == 12
    assert [int(row["prn"]) for row in rows] == list(range(1, 13))
    for row in rows:
        original = [int(value) for value in row["original_code"].split()]
        transmitted = [int(value) for value in row["transmitted_code"].split()]
        modified = [int(value) for value in row["modified_indexes"].split()]
        assert len(original) == length
        assert len(transmitted) == length
        assert set(original) <= {-1, 1}
        assert set(transmitted) <= {-1, 1}
        assert int(row["chips"]) == length
        assert int(row["modified_count"]) == len(modified)
        assert modified == sorted(rule.flips[int(row["prn"])])
        assert [i for i in range(length) if original[i] != transmitted[i]] == modified

    expected = {(prn, chip) for prn in rule.flips for chip in rule.flips[prn]}
    saved = np.load(paths["codes_matrix"])
    assert saved["transmitted"].shape == (12, length)
    assert saved["nominal"].shape == saved["transmitted"].shape
    assert int((saved["transmitted"] != saved["nominal"]).sum()) == len(expected)
    assert (saved["transmitted"] ** 2 == 1).all()


def test_positions_artifact_is_one_row_per_modified_chip(shared_55):
    recording = shared_55["recording"]
    rule = shared_55["recovery"].rule
    path = tables.write_positions(recording, rule.flips)
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert set(rows[0]) == set(tables.POSITIONS_COLUMNS)
    assert len(rows) == 12 * rule.count


def test_a_bad_destination_is_reported(tmp_path):
    with pytest.raises(SystemExit):
        tables._write_rows(str(tmp_path / "missing" / "out.csv"), tables.FLIPS_COLUMNS, [])
    with pytest.raises(SystemExit):
        tables.write_flips(str(tmp_path / "missing" / "run.nc"), None)


def test_a_missing_acquisition_table_is_reported(tmp_path):
    with pytest.raises(SystemExit):
        tables.read_detections(str(tmp_path / "absent.nc"))


def write_summary(shared_55) -> dict:
    """Run `solve.save` for the fixture and return the JSON it wrote, so no test leans on leftover files."""
    from gnss import verification
    from gnss.rule import explain_base
    from solve import save

    recovery = shared_55["recovery"]
    found = recovery.acquisition
    save(
        shared_55["recording"],
        found,
        recovery,
        explain_base(recovery.rule.base),
        verification.verify(found, recovery.rule.flips),
    )
    with open(tables.summary_path(shared_55["recording"]), encoding="utf-8") as handle:
        return json.load(handle)


def test_summary_path_matches_what_solve_writes(shared_55):
    payload = write_summary(shared_55)
    assert payload["recording"] == shared_55["recording"]
    assert set(payload) == {
        "recording", "sampling", "detected_prns", "acquisition", "codes", "rule", "pattern", "evidence"
    }
    assert payload["rule"]["flipped_chips_per_prn"] == len(payload["rule"]["base_pattern"])
    assert payload["pattern"]["matches"] is True
    # the closed form is written next to the recovered list, so a reader can compare them
    assert set(payload["rule"]["closed_form_flips"]) == set(payload["rule"]["flips"])
    assert all(payload["rule"]["closed_form_matches"].values())


def test_summary_carries_the_whole_code_of_every_prn(shared_55):
    codes = write_summary(shared_55)["codes"]

    length = shared_55["lattice"].code_length_in_chips
    assert [row["prn"] for row in codes] == list(range(1, 13))
    assert set(codes[0]) == {"prn", "transmitted_code", "original_code", "modified_indexes"}
    for row in codes:
        assert len(row["original_code"]) == length
        assert len(row["transmitted_code"]) == length
        assert set(row["original_code"]) <= {-1, 1}
        assert set(row["transmitted_code"]) <= {-1, 1}
        differing = [
            index
            for index, (before, after) in enumerate(
                zip(row["original_code"], row["transmitted_code"], strict=True)
            )
            if before != after
        ]
        assert differing == row["modified_indexes"]
        assert differing == sorted(shared_55["recovery"].rule.flips[row["prn"]])


def test_recovery_reports_a_recording_without_satellites(shared_55):
    empty = pipeline.Recovery(
        acquisition=shared_55["recovery"].acquisition,
        satellites={},
        residual=shared_55["recovery"].residual,
        rule=shared_55["recovery"].rule,
    )
    assert empty.rule.count == 15
    assert empty.residual_power == pytest.approx(shared_55["recovery"].residual_power)
