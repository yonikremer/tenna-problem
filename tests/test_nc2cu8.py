import re
from pathlib import Path

from analysis import nc2cu8
import numpy as np
import pytest


def test_load_nc_matches_the_recording(synthetic):
    samples, sample_rate = nc2cu8.load_nc(synthetic.recording)
    assert sample_rate == synthetic.lattice.sample_rate_hz
    assert np.allclose(samples, synthetic.samples, atol=1e-5)


def test_main_writes_interleaved_int8(synthetic, capsys):
    destination = Path(synthetic.recording).with_name("nc2cu8_test.cu8")
    nc2cu8.main(synthetic.recording, str(destination))
    output = capsys.readouterr().out
    assert destination.exists()
    assert destination.stat().st_size == 2 * len(synthetic.samples)

    clipped_match = re.search(r"clipped samples: (\d+)", output)
    assert clipped_match is not None
    clipped = int(clipped_match.group(1))
    raw = np.fromfile(destination, dtype=np.int8)
    reconstructed = raw[0::2] / nc2cu8.SCALE + 1j * raw[1::2] / nc2cu8.SCALE
    error = np.max(
        np.abs(np.concatenate([reconstructed.real - synthetic.samples.real, reconstructed.imag - synthetic.samples.imag]))
    )
    if clipped == 0:
        assert error <= 0.5 / nc2cu8.SCALE + 1e-12
    else:
        assert error < 1.0
    destination.unlink()


def test_main_reports_the_conversion(synthetic, capsys):
    destination = Path(synthetic.recording).with_name("nc2cu8_test2.cu8")
    nc2cu8.main(synthetic.recording, str(destination))
    output = capsys.readouterr().out
    assert synthetic.recording in output
    assert "scale 20" in output
    destination.unlink()


def test_scaling_keeps_the_signal_inside_int8(synthetic):
    peak = np.max(np.abs(np.concatenate([synthetic.samples.real, synthetic.samples.imag])))
    assert peak * nc2cu8.SCALE < 127.0


def test_main_rejects_a_missing_file(tmp_path):
    with pytest.raises(OSError):
        nc2cu8.main(str(tmp_path / "absent.nc"), str(tmp_path / "out.cu8"))
