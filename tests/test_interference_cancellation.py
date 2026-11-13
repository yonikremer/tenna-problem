import re

import make_synthetic as generator  # type: ignore
import numpy as np
import pytest

from analysis import interference_cancellation as cancellation
from gnss import acquisition, signals


def test_unit_signal_is_the_aligned_code_times_carrier(synthetic, truth_clean):
    lattice = synthetic.lattice
    times = np.arange(len(synthetic.samples)) / lattice.sample_rate_hz
    for satellite, row in synthetic.truth.items():
        shift = truth_clean.shifts[satellite]
        unit = signals.unit_signal(len(synthetic.samples), satellite, lattice, row["doppler_hz"], shift)
        replica = acquisition.spreading_code_replica(
            satellite,
            len(synthetic.samples),
            lattice,
            None,
            -shift * lattice.code_phase_increment,
        )
        expected = replica * np.exp(2j * np.pi * row["doppler_hz"] * times)
        assert np.allclose(unit, expected)


def test_truth_exact_cancellation_leaves_noise_only(synthetic, truth_clean):
    residual_power = float(np.mean(np.abs(truth_clean.residual) ** 2))
    assert residual_power == pytest.approx(generator.NOISE_COMPLEX_VARIANCE, rel=0.15)
    for coefficient in truth_clean.coefficients.values():
        assert abs(coefficient) == pytest.approx(generator.PER_PRN_AMPLITUDE, rel=0.15)
    mean_coefficient = np.mean([abs(coefficient) for coefficient in truth_clean.coefficients.values()])
    assert mean_coefficient == pytest.approx(generator.PER_PRN_AMPLITUDE, rel=0.05)


def test_main_cancels_most_power_and_predicts_the_control_scale(synthetic, capsys):
    cancellation.main([synthetic.recording])
    output = capsys.readouterr().out

    residual = re.search(r"after subtracting all satellites ([0-9.]+)", output)
    predicted = re.search(r"pure noise would be about ([0-9.]+)", output)
    assert residual is not None
    assert predicted is not None

    residual_power = float(residual.group(1))
    # One chip combines every sample of the chip over every code period: periods x samples/chip.
    expected = np.sqrt(residual_power / (generator.CODE_PERIODS * generator.SAMPLES_PER_CHIP))
    assert float(predicted.group(1)) == pytest.approx(expected, rel=0.02)
    # The old formula divided by samples_per_code_period too, making the prediction 8x too small.
    assert float(predicted.group(1)) > 2.0 * np.sqrt(
        residual_power / (generator.CODE_PERIODS * generator.SAMPLES_PER_CODE_PERIOD)
    )
    assert "cancellation removed" in output
    assert output.count("spread before") == 1
