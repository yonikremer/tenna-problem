"""Signal shapes: spreading-code replicas, carriers, and the linear algebra that removes them.

A detected satellite is fully described by its Doppler, its code phase in samples, and one complex
amplitude. Those three numbers build a unit waveform `u_s[n]`: that satellite at amplitude one.
Because the signals add, the recording is a sum of scaled unit waveforms plus noise, so estimating
one complex coefficient per satellite by least squares is exact. That is what makes cancellation
(removing every other satellite) and verification (measuring what is left) cheap.

Two replicas exist on purpose:
  - `spreading_code_replica` keeps the code phase fractional, so a delay need not be a whole number
    of samples. It is used wherever a chip value is read.
  - `aligned_code` samples a plain +-1 chip array on the record grid. It is used wherever a whole
    code vector must be compared or flipped.
"""

import numpy as np

from .vendor import add_to_import_path

add_to_import_path()
import gnsstools.gps.ca as ca  # type: ignore  # noqa: E402

from .lattice import Lattice  # noqa: E402


def spreading_code_replica(
    satellite: int,
    length: int,
    lattice: Lattice,
    increment: float | None = None,
    chip_offset: float = 0.0,
) -> np.ndarray:
    """+-1 spreading code of one satellite, sampled at the recording rate."""
    return ca.code(
        satellite,
        0,
        chip_offset,
        lattice.code_phase_increment if increment is None else increment,
        length,
    )


def carrier(length: int, lattice: Lattice, doppler_hz: float, phase_rad: float = 0.0) -> np.ndarray:
    times = np.arange(length) / lattice.sample_rate_hz
    return np.exp(2j * np.pi * doppler_hz * times + 1j * phase_rad)


def first_10_chips(satellite: int) -> int:
    """First ten chips of a satellite's code, as the published octal vector."""
    return ca.first_10_chips(satellite)


def unit_signal(
    length: int,
    satellite: int,
    lattice: Lattice,
    doppler_hz: float,
    shift_samples: float,
) -> np.ndarray:
    """Received-signal shape of one satellite: aligned spreading code times its carrier."""
    replica = spreading_code_replica(
        satellite, length, lattice, None, -shift_samples * lattice.code_phase_increment
    )
    return replica * carrier(length, lattice, doppler_hz)


def aligned_code(
    code: np.ndarray, shift_samples: float, length: int, samples_per_chip: int
) -> np.ndarray:
    """Sample one chip array at the record grid, delayed by `shift_samples`."""
    index = (
        np.floor((np.arange(length) - shift_samples) / samples_per_chip).astype(int) % len(code)
    )
    return code[index]


def flipped_replica(
    satellite: int,
    length: int,
    lattice: Lattice,
    shift_samples: float,
    flipped_chips=frozenset(),
) -> np.ndarray:
    """Nominal spreading code with the given chips negated, sampled at the record grid.

    The chip array is sampled at one value per chip (increment 1), not at the record rate: this
    function must flip whole chips, and `aligned_code` then places them on the sample grid.
    """
    code = spreading_code_replica(
        satellite, lattice.code_length_in_chips, lattice, increment=1.0
    )
    if flipped_chips:
        code = code.copy()
        code[list(flipped_chips)] *= -1.0
    return aligned_code(code, shift_samples, length, lattice.samples_per_chip_whole)


def fit_amplitudes(samples: np.ndarray, units: dict) -> dict:
    """Complex amplitude of every unit waveform, one least-squares coefficient each.

    The unit waveforms are close to orthogonal over the record (different codes, different
    carriers), so one pass of independent projections is within a fraction of a percent of the
    joint fit, and it keeps the estimate independent of how many satellites were found.
    """
    return {key: np.vdot(unit, samples) / len(samples) for key, unit in units.items()}


def reconstruct(coefficients: dict, units: dict) -> np.ndarray:
    """Sum of every modelled satellite at its fitted amplitude."""
    total = np.zeros(len(next(iter(units.values()))), dtype=np.complex128)
    for key, unit in units.items():
        total += coefficients[key] * unit
    return total


def residual(samples: np.ndarray, coefficients: dict, units: dict) -> np.ndarray:
    """What is left after removing every modelled satellite: noise plus whatever was not modelled."""
    return samples - reconstruct(coefficients, units)


def cleaned(samples: np.ndarray, coefficients: dict, units: dict, key) -> np.ndarray:
    """The recording with every satellite except `key` removed."""
    others = reconstruct(
        {other: coefficient for other, coefficient in coefficients.items() if other != key},
        {other: unit for other, unit in units.items() if other != key},
    )
    return samples - others


def noise_variance(residual_samples: np.ndarray) -> float:
    return float(np.mean(np.abs(residual_samples) ** 2))
