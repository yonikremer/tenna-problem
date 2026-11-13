"""Tests for the CSV/JSON artifacts: the answer in a form a spreadsheet can check."""

import csv
import json

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


def test_a_bad_destination_is_reported(tmp_path):
    with pytest.raises(SystemExit):
        tables._write_rows(str(tmp_path / "missing" / "out.csv"), tables.FLIPS_COLUMNS, [])
    with pytest.raises(SystemExit):
        tables.write_flips(str(tmp_path / "missing" / "run.nc"), None)


def test_a_missing_acquisition_table_is_reported(tmp_path):
    with pytest.raises(SystemExit):
        tables.read_detections(str(tmp_path / "absent.nc"))


def test_summary_path_matches_what_solve_writes(shared_55):
    recording = shared_55["recording"]
    with open(tables.summary_path(recording), encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["recording"] == recording
    assert set(payload) == {"recording", "sampling", "detected_prns", "acquisition", "rule", "pattern", "evidence"}
    assert payload["rule"]["flipped_chips_per_prn"] == len(payload["rule"]["base_pattern"])
    assert payload["pattern"]["matches"] is True


def test_recovery_reports_a_recording_without_satellites(shared_55):
    empty = pipeline.Recovery(
        acquisition=shared_55["recovery"].acquisition,
        satellites={},
        residual=shared_55["recovery"].residual,
        rule=shared_55["recovery"].rule,
    )
    assert empty.rule.count == 15
    assert empty.residual_power == pytest.approx(shared_55["recovery"].residual_power)
