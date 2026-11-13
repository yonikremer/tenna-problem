import global_flip
import make_synthetic as generator  # type: ignore
import numpy as np
import pytest

from gnss import acquisition


def shared_scenario(seed):
    """55 dB-Hz composite where all 12 codes flip the same 15 chips."""
    lattice = acquisition.Lattice(4_092_000.0, 1_575_420_000.0, 1_023_000.0, 1023)
    satellites = generator.draw_parameters(np.random.default_rng(generator.SEED))
    mask = np.sort(np.random.default_rng(777).choice(generator.CODE_LENGTH_IN_CHIPS, 15, replace=False))
    for satellite in satellites:
        satellite["flipped_chips"] = mask.copy()
    samples = generator.synthetic_samples(satellites, seed, noise_variance=1.0)
    prepared = global_flip.prepare(samples, satellites, lattice)
    changes = global_flip.score_changes(prepared)
    return lattice, satellites, mask, prepared, changes


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_scanning_every_chip_finds_the_shared_mask_at_55dbhz(seed):
    _, _, mask, _, changes = shared_scenario(seed)
    flagged = set(np.flatnonzero(changes > 0).tolist())
    assert flagged == set(mask.tolist())
    assert len(flagged) == 15


def test_the_score_is_the_real_total_correlation_change():
    lattice, satellites, mask, prepared, changes = shared_scenario(0)
    used = set(mask.tolist())
    probe = next(index for index in range(generator.CODE_LENGTH_IN_CHIPS) if index not in used)
    for chip_index in (int(mask[0]), probe):
        direct = global_flip.brute_force_change(satellites, lattice, prepared, chip_index)
        assert direct == pytest.approx(float(changes[chip_index]), rel=1e-9)


def test_shared_mask_survives_a_different_noise_seed():
    _, _, mask, _, changes = shared_scenario(11)
    assert set(np.flatnonzero(changes > 0).tolist()) == set(mask.tolist())
