import chip_fixing
import make_synthetic as generator  # type: ignore
import numpy as np
import pytest


@pytest.fixture(scope="session")
def nominal_cleaned(synthetic, truth_clean):
    """The composite signal with every other satellite subtracted using its NOMINAL code."""
    lattice = synthetic.lattice
    length = len(synthetic.samples)
    times = np.arange(length) / lattice.sample_rate_hz
    units, coefficients = {}, {}
    for satellite, row in synthetic.truth.items():
        unit = chip_fixing.aligned_code(
            generator.nominal_code(satellite),
            truth_clean.shifts[satellite],
            length,
            generator.SAMPLES_PER_CHIP,
        ) * np.exp(2j * np.pi * row["doppler_hz"] * times)
        units[satellite] = unit
        coefficients[satellite] = np.vdot(unit, synthetic.samples) / length
    return {
        satellite: synthetic.samples
        - sum(
            coefficients[other] * units[other]
            for other in units
            if other != satellite
        )
        for satellite in units
    }


def theoretical_energy_factor():
    """Power left when 15 of 1023 chips disagree: ((1023 - 2*15) / 1023)^2."""
    return ((1023 - 2 * generator.FLIPS_PER_CODE) / 1023) ** 2


def test_modified_code_loses_the_expected_cross_correlation(synthetic):
    for rows in synthetic.codes.values():
        nominal = rows["nominal"]
        modified = rows["modified"]
        correlation = float(np.dot(nominal, modified) / len(nominal))
        assert correlation == pytest.approx(
            (1023 - 2 * generator.FLIPS_PER_CODE) / 1023, abs=1e-12
        )
        assert correlation < 1.0
        assert np.count_nonzero(nominal != modified) == generator.FLIPS_PER_CODE


def test_modified_replica_gains_the_theoretical_peak_on_a_clean_signal(
    synthetic, truth_clean
):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        nominal = chip_fixing.correlation_peak(
            truth_clean.cleaned[satellite],
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        modified = chip_fixing.correlation_peak(
            truth_clean.cleaned[satellite],
            synthetic.codes[satellite]["modified"],
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        assert modified / nominal == pytest.approx(1.0 / theoretical_energy_factor(), rel=0.01)
        assert 10 * np.log10(modified / nominal) == pytest.approx(
            -10 * np.log10(theoretical_energy_factor()), abs=0.02
        )


def test_modified_replica_gain_on_the_composite_signal(synthetic):
    lattice = synthetic.lattice
    gains = []
    for satellite, row in synthetic.truth.items():
        nominal = chip_fixing.correlation_peak(
            synthetic.samples,
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            row["delay_samples"],
        )
        modified = chip_fixing.correlation_peak(
            synthetic.samples,
            synthetic.codes[satellite]["modified"],
            lattice,
            row["doppler_hz"],
            row["delay_samples"],
        )
        gains.append(10 * np.log10(modified / nominal))
    assert all(0.10 < gain < 0.45 for gain in gains)
    assert 0.20 < float(np.mean(gains)) < 0.35


def test_chip_repair_recovers_every_flip_on_a_clean_signal(synthetic, truth_clean):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        repaired, history = chip_fixing.repair_code(
            truth_clean.cleaned[satellite],
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        flipped = set(np.flatnonzero(repaired != generator.nominal_code(satellite)).tolist())
        assert flipped == set(row["flipped_chips"])
        assert len(history) == 2  # one repair round, then a confirming empty round


def test_chip_repair_after_nominal_cancellation_finds_all_true_flips(synthetic, nominal_cleaned, truth_clean):
    lattice = synthetic.lattice
    for satellite, row in synthetic.truth.items():
        repaired, _ = chip_fixing.repair_code(
            nominal_cleaned[satellite],
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        flipped = set(np.flatnonzero(repaired != generator.nominal_code(satellite)).tolist())
        truth = set(row["flipped_chips"])
        assert len(truth & flipped) >= generator.FLIPS_PER_CODE - 1
        assert len(flipped - truth) <= 12

        nominal_peak = chip_fixing.correlation_peak(
            nominal_cleaned[satellite],
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        repaired_peak = chip_fixing.correlation_peak(
            nominal_cleaned[satellite],
            repaired,
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        gain = 10 * np.log10(repaired_peak / nominal_peak)
        assert 0.10 < gain < 0.55


def test_best_fifteen_chips_after_nominal_cancellation(synthetic, nominal_cleaned, truth_clean):
    lattice = synthetic.lattice
    hits, false = 0, 0
    for satellite, row in synthetic.truth.items():
        repaired, _ = chip_fixing.repair_code(
            nominal_cleaned[satellite],
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
            rounds=1,
            max_flips=generator.FLIPS_PER_CODE,
        )
        flipped = set(np.flatnonzero(repaired != generator.nominal_code(satellite)).tolist())
        truth = set(row["flipped_chips"])
        assert len(flipped) == generator.FLIPS_PER_CODE
        hits += len(flipped & truth)
        false += len(flipped - truth)
    assert hits >= 160
    assert false <= 12


def test_chip_repair_on_the_raw_signal_is_not_trustworthy(synthetic, truth_clean):
    lattice = synthetic.lattice
    missed, false = 0, 0
    for satellite, row in synthetic.truth.items():
        repaired, _ = chip_fixing.repair_code(
            synthetic.samples,
            generator.nominal_code(satellite),
            lattice,
            row["doppler_hz"],
            truth_clean.shifts[satellite],
        )
        flipped = set(np.flatnonzero(repaired != generator.nominal_code(satellite)).tolist())
        truth = set(row["flipped_chips"])
        missed += len(truth - flipped)
        false += len(flipped - truth)
    assert missed > 0 or false > 50
