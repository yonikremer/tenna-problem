"""End-to-end recovery on the 55 dB-Hz synthetic recording that follows the real rule."""

import csv
from pathlib import Path

import make_shared_55  # type: ignore
import numpy as np
import pytest

import solve
from gnss import pipeline, rule, tables, verification


def test_generator_follows_the_shifted_base_rule(shared_55):
    truth = shared_55["truth"]
    assert len(truth) == 12
    base = make_shared_55.BASE_PATTERN
    assert len(base) == 15
    for satellite, row in truth.items():
        assert len(row["flipped_chips"]) == 15
        expected = {(chip - make_shared_55.SHIFT_PER_PRN * (satellite - 1)) % 1023 for chip in base}
        assert row["flipped_chips"] == expected
        assert row["base_pattern"] == set(base)
        assert row["shift_chips"] == make_shared_55.SHIFT_PER_PRN * (satellite - 1)
        assert row["data_bit"] == 1.0
        assert row["cn0_dbhz"] == pytest.approx(55.0, abs=0.2)
    assert len({row["doppler_hz"] for row in truth.values()}) == 12
    assert len({row["delay_samples"] for row in truth.values()}) == 12


def test_soft_vectors_have_one_value_per_chip(shared_55):
    satellites = shared_55["recovery"].satellites
    assert set(satellites) == set(range(1, 13))
    for satellite in satellites.values():
        assert len(satellite.vector) == 1023
        assert np.all(np.isfinite(satellite.vector))
        assert np.all(np.abs(satellite.vector) > 0)


def test_recover_finds_the_common_rule_exactly(shared_55):
    recovered = shared_55["recovery"].rule
    truth = shared_55["truth"]
    assert recovered.slope == make_shared_55.SHIFT_PER_PRN
    assert recovered.base == set(make_shared_55.BASE_PATTERN)
    assert recovered.count == 15
    assert recovered.flips == {
        satellite: frozenset(row["flipped_chips"]) for satellite, row in truth.items()
    }
    assert recovered.score > 2.0


def test_the_recovered_rule_explains_the_recording(shared_55):
    """The recovered codes must leave noise alone, and earn the theoretical correlation gain."""
    recovery = shared_55["recovery"]
    check = verification.verify(recovery.acquisition, recovery.rule.flips)

    assert check.recovered_residual_power < check.nominal_residual_power
    assert check.recovered_residual_power == pytest.approx(make_shared_55.NOISE_COMPLEX_VARIANCE, rel=0.1)
    # 15 flipped chips leave (1023 - 2*15)/1023 of the nominal correlation: a ceiling of 0.259 dB
    assert check.ceiling_db == pytest.approx(0.259, abs=0.005)
    for gain in check.gains_db.values():
        assert 0.0 < gain < check.ceiling_db + 0.15
    # what the model removes must be exactly the twelve satellites' power, not more
    removed = check.received_power - check.recovered_residual_power
    assert removed == pytest.approx(12 * make_shared_55.PER_PRN_AMPLITUDE**2, rel=0.1)


def test_the_recovered_base_is_the_fibonacci_rule(shared_55):
    pattern = rule.explain_base(shared_55["recovery"].rule.base)
    assert pattern.matches
    assert pattern.missing == ()
    assert pattern.unexpected == ()
    assert "prefix sum" in pattern.describe()[1]


def test_recovery_survives_extra_noise(shared_55):
    vectors = {prn: s.vector for prn, s in shared_55["recovery"].satellites.items()}
    generator = np.random.default_rng(4)
    for _ in range(3):
        noisy = {prn: vector + generator.normal(0.0, 0.2, len(vector)) for prn, vector in vectors.items()}
        recovered = rule.recover_rule(noisy)
        assert recovered.slope == make_shared_55.SHIFT_PER_PRN
        assert recovered.base == set(make_shared_55.BASE_PATTERN)


def test_write_flips_saves_every_recovered_chip(shared_55):
    destination = tables.write_flips(shared_55["recording"], shared_55["recovery"].rule)
    with open(destination, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12 * 15
    saved = {}
    for row in rows:
        saved.setdefault(int(row["satellite"]), set()).add(int(row["chip_index"]))
        assert int(row["shift_chips"]) == 2 * (int(row["satellite"]) - 1)
    assert saved == shared_55["recovery"].rule.flips


def test_solve_runs_end_to_end_and_writes_every_artifact(shared_55, capsys):
    recording = shared_55["recording"]
    exit_code = solve.main([recording, "--satellites", "1-12"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "common shift per PRN: 2 chips" in output
    assert (
        "base pattern: 34 411 644 788 877 932 966 987 1000 1008 1013 1016 1018 1019 1020" in output
    )
    assert "the recovered pattern matches that rule exactly" in output
    assert "residual power with recovered codes" in output
    for suffix in ("_acquisition.csv", "_joint_flips.csv", "_solution.json"):
        assert Path(recording.replace(".nc", suffix)).exists()


def test_recover_reports_a_missing_recording(tmp_path):
    with pytest.raises(SystemExit):
        pipeline.recover(str(tmp_path / "absent.nc"))


def test_main_reports_a_missing_recording(tmp_path):
    with pytest.raises(SystemExit):
        solve.main([str(tmp_path / "absent.nc"), "--satellites", "1-12"])
