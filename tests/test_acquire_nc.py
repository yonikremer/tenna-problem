import re

from analysis import acquire_nc
import make_synthetic as generator  # type: ignore
import numpy as np
import pytest


def test_load_resamples_to_the_kernel_rate(cu8_recording):
    samples = acquire_nc.load(cu8_recording, acquire_nc.MS)
    assert len(samples) == acquire_nc.MS * 4096 + 5 * 4096
    assert samples.dtype == np.complex128
    assert np.all(np.isfinite(samples))


def test_search_finds_a_known_satellite(cu8_recording, synthetic):
    samples = acquire_nc.load(cu8_recording, acquire_nc.MS)
    satellite = 1
    truth = synthetic.truth[satellite]
    doppler_search = (truth["doppler_hz"] - 400.0, truth["doppler_hz"] + 400.0, 200.0)
    metric, code_phase, doppler_hz = acquire_nc.search(
        samples, satellite, doppler_search, acquire_nc.MS
    )
    assert metric > 3.0
    assert abs(doppler_hz - truth["doppler_hz"]) <= 200.0
    # The kernel correlates in the opposite direction, so its code phase is the complement.
    expected = (-truth["code_phase_chips"]) % generator.CODE_LENGTH_IN_CHIPS
    error = (code_phase - expected + 1023 / 2) % 1023 - 1023 / 2
    assert abs(error) < 3.0


def test_main_prints_a_row_per_satellite(cu8_recording, capsys):
    acquire_nc.main(cu8_recording, range(1, 4))
    output = capsys.readouterr().out
    rows = re.findall(r"^\s+(\d+)\s+([0-9.]+)\s+([+-]?[0-9.]+)\s+([0-9.]+)\s*$", output, re.MULTILINE)
    assert len(rows) == 3
    for row in rows:
        assert 1 <= int(row[0]) <= 3
        assert 0.0 <= float(row[3]) < generator.CODE_LENGTH_IN_CHIPS
    assert "doppler grid" in output


def test_load_rejects_a_short_file(tmp_path):
    short = tmp_path / "short.cu8"
    short.write_bytes(b"\x00" * 16)
    with pytest.raises(RuntimeError):
        acquire_nc.load(str(short), acquire_nc.MS)
