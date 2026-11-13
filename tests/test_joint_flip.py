import make_shared_55  # type: ignore
import numpy as np

from analysis import joint_flip


def test_prepared_exposes_vectors_and_noise(shared_55):
    vectors, noise_variance, period_samples, samples_per_chip = joint_flip.prepared(
        shared_55["recording"]
    )
    assert set(vectors) == set(range(1, 13))
    assert noise_variance > 0.0
    assert period_samples == 4092
    assert samples_per_chip == 4
    for vector in vectors.values():
        assert len(vector) == 1023


def test_chip_contributions_use_the_combined_sample_count(shared_55):
    vectors, _, period_samples, samples_per_chip = joint_flip.prepared(shared_55["recording"])
    periods = make_shared_55.base.LENGTH // period_samples
    vector = vectors[1]
    contributions = joint_flip.chip_contributions(vector, samples_per_chip, periods)
    assert np.array_equal(contributions, vector * samples_per_chip * periods)


def test_joint_score_decomposes_over_satellites(shared_55):
    vectors, _, period_samples, samples_per_chip = joint_flip.prepared(shared_55["recording"])
    periods = make_shared_55.base.LENGTH // period_samples
    all_satellites = joint_flip.joint_scores(vectors, samples_per_chip, periods)
    split = joint_flip.joint_scores(
        vectors, samples_per_chip, periods, satellites=[1, 2]
    ) + joint_flip.joint_scores(vectors, samples_per_chip, periods, satellites=[3])
    assert all_satellites.shape == (1023,)
    assert np.all(np.isfinite(all_satellites))
    expected = joint_flip.joint_scores(vectors, samples_per_chip, periods, satellites=[1, 2, 3])
    assert np.allclose(split, expected)


def test_explained_power_prefers_the_true_per_satellite_flips(shared_55):
    vectors, _, period_samples, samples_per_chip = joint_flip.prepared(shared_55["recording"])
    periods = make_shared_55.base.LENGTH // period_samples
    baseline = joint_flip.explained_power(vectors, samples_per_chip, periods, {})
    truth = {satellite: make_shared_55.flips_for(satellite) for satellite in vectors}
    repaired = joint_flip.explained_power(vectors, samples_per_chip, periods, truth)
    assert repaired > baseline
    assert repaired > 0.0


def test_main_prints_the_benchmarks(shared_55, capsys):
    joint_flip.main([shared_55["recording"]])
    output = capsys.readouterr().out
    assert "split-half overlap" in output
    assert "top 15 chips" in output
    assert "same 15 chips in all codes" in output
    assert "independent mask per code" in output
    assert "explained |S|^2" in output
