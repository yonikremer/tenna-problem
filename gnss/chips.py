"""One soft value per spreading-code chip, read out of a cleaned recording.

A chip repeats at the same place in every code period, so the 8 occurrences average coherently: the
signal adds, thermal noise and the other satellites' codes do not. A chip whose received sign differs
from the nominal code is a flipped chip.

Two readings are produced on purpose:
  - `centre` uses the middle samples of each chip, so a code run boundary never contributes a
    neighbour chip's value.
  - `whole` averages every sample of the chip, which is the stronger estimator when the chip grid is
    exact.
"""

import numpy as np

from .lattice import Lattice
from .signals import spreading_code_replica


def chip_vector(
    samples: np.ndarray,
    satellite: int,
    lattice: Lattice,
    doppler_hz: float,
    shift_samples: float,
    period_samples: int | None = None,
    samples_per_chip: int | None = None,
):
    """Complex value of every chip, averaged over the code periods in the record.

    The chip index of a sample follows from the measured code phase, so it is already the code
    coordinate: no relabelling roll is needed, and a delay that is not a whole number of chips is
    handled by sampling each chip's midpoint.
    """
    period_samples = lattice.samples_per_code_period if period_samples is None else period_samples
    samples_per_chip = lattice.samples_per_chip_whole if samples_per_chip is None else samples_per_chip
    length = len(samples)
    periods = length // period_samples
    usable = periods * period_samples
    replica = spreading_code_replica(
        satellite, length, lattice, None, -shift_samples * lattice.code_phase_increment
    )
    times = np.arange(length) / lattice.sample_rate_hz
    product = (samples * np.exp(-2j * np.pi * doppler_hz * times) * replica)[:usable]
    blocks = product.reshape(periods, period_samples)

    slots = np.arange(lattice.code_length_in_chips)[:, None] * samples_per_chip + np.arange(
        samples_per_chip
    )[None, :]
    positions = np.floor(shift_samples + slots + 0.5).astype(int) % period_samples
    values = blocks[:, positions]

    low = max(samples_per_chip // 2 - 1, 0)
    high = max(samples_per_chip // 2 + 1, low + 1)
    centre = values[:, :, low:high].mean(axis=2).mean(axis=0)
    whole = values.mean(axis=2).mean(axis=0)
    return centre, whole, periods


def align(vector: np.ndarray) -> np.ndarray:
    """Rotate so the mean lies on the positive real axis: removes the residual carrier phase."""
    reference = vector.sum()
    return vector * (np.conj(reference) / abs(reference)) if reference != 0 else vector


def bits_of(vector: np.ndarray) -> np.ndarray:
    """Chip signs after forcing the majority to +1, since the data-bit sign is unknown."""
    signs = np.sign(np.real(align(vector)))
    if np.count_nonzero(signs < 0) > len(signs) / 2:
        signs = -signs
    return signs


def flipped_chips(vector: np.ndarray) -> set:
    """Chips whose recovered sign is negative, i.e. modified relative to the nominal code."""
    return set(np.flatnonzero(bits_of(vector) < 0).tolist())
