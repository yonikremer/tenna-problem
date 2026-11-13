"""Replica comparison and chip-by-chip repair used by the synthetic-signal tests."""

import numpy as np


def aligned_code(code, shift_samples, length, samples_per_chip):
    """Sample one 1023-chip code at the record grid, delayed by `shift_samples`."""
    index = np.floor((np.arange(length) - shift_samples) / samples_per_chip).astype(int) % len(code)
    return code[index]


def correlation_peak(samples, code, lattice, doppler_hz, shift_samples):
    """Coherent correlation power of one arbitrary code, after carrier wipe-off."""
    length = len(samples)
    times = np.arange(length) / lattice.sample_rate_hz
    replica = aligned_code(
        code, shift_samples, length, lattice.samples_per_code_period // len(code)
    ) * np.exp(2j * np.pi * doppler_hz * times)
    correlation = np.fft.ifft(np.fft.fft(samples) * np.conj(np.fft.fft(replica)))
    return float(np.max(np.abs(correlation[: lattice.samples_per_code_period]) ** 2))


def chip_soft_values(samples, code, lattice, doppler_hz, shift_samples):
    """One complex value per chip, using the current code as the replica."""
    length = len(samples)
    period = lattice.samples_per_code_period
    samples_per_chip = period // len(code)
    periods = length // period
    times = np.arange(length) / lattice.sample_rate_hz
    replica = aligned_code(code, shift_samples, length, samples_per_chip)
    product = (samples * np.exp(-2j * np.pi * doppler_hz * times) * replica)[
        : periods * period
    ].reshape(periods, period)

    slots = np.arange(len(code))[:, None] * samples_per_chip + np.arange(samples_per_chip)[None, :]
    positions = np.floor(shift_samples + slots + 0.5).astype(int) % period
    values = product[:, positions].mean(axis=2).mean(axis=0)
    reference = values.sum()
    return values * (np.conj(reference) / abs(reference)) if reference != 0 else values


def repair_code(samples, nominal_code, lattice, doppler_hz, shift_samples, rounds=6, max_flips=None):
    """Flip chips whose current soft value is negative, one round at a time.

    Returns the repaired code and a list of the flip sets applied in each round.
    """
    current = np.asarray(nominal_code, dtype=np.float64).copy()
    history = []
    for _ in range(rounds):
        values = chip_soft_values(samples, current, lattice, doppler_hz, shift_samples)
        flips = np.flatnonzero(values.real < 0)
        if max_flips is not None and len(flips) > max_flips:
            flips = flips[np.argsort(values.real[flips])[:max_flips]]
        history.append(set(flips.tolist()))
        if len(flips) == 0:
            break
        current[flips] *= -1.0
    return current, history
