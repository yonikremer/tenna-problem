"""Global shared-mask search: flip chip i in every satellite and measure total correlation.

If all satellites use the same 15 flipped chip positions, the change in the summed correlation power
when chip i is flipped in every replica is a single number per chip. That is exactly the quantity the
simulation scans over i = 0..1022.
"""

import chip_fixing
import make_synthetic as generator  # type: ignore
import numpy as np

from gnss import alignment


def exact_chip_contributions(samples, code, lattice, doppler_hz, shift_samples):
    """Complex contribution of every chip to the coherent correlation.

    Each record sample is assigned to exactly one code chip, so summing the returned values gives the
    full correlation and flipping chip i changes that sum by -2 * contribution[i].
    """
    length = len(samples)
    period = lattice.samples_per_code_period
    samples_per_chip = period // len(code)
    times = np.arange(length) / lattice.sample_rate_hz
    replica = chip_fixing.aligned_code(code, shift_samples, length, samples_per_chip)
    product = samples * np.exp(-2j * np.pi * doppler_hz * times) * replica
    index = np.floor((np.arange(length) - shift_samples) / samples_per_chip).astype(int) % len(code)
    real = np.bincount(index, weights=product.real, minlength=len(code))
    imaginary = np.bincount(index, weights=product.imag, minlength=len(code))
    return real + 1j * imaginary


def prepare(samples, satellites, lattice):
    """Per-satellite chip contributions after cancelling the other satellites with nominal codes."""
    length = len(samples)
    times = np.arange(length) / lattice.sample_rate_hz
    units, coefficients, shifts = {}, {}, {}
    for satellite in satellites:
        number = satellite["satellite"]
        doppler_hz = satellite["doppler_hz"]
        shift = shift = alignment.aligned_shift(samples, number, lattice, doppler_hz)
        shifts[number] = shift
        unit = chip_fixing.aligned_code(
            generator.nominal_code(number), shift, length, generator.SAMPLES_PER_CHIP
        ) * np.exp(2j * np.pi * doppler_hz * times)
        units[number] = unit
        coefficients[number] = np.vdot(unit, samples) / length

    residual = samples - sum(coefficients[number] * units[number] for number in units)
    contributions, cleans = {}, {}
    for satellite in satellites:
        number = satellite["satellite"]
        clean = residual + coefficients[number] * units[number]
        cleans[number] = clean
        contributions[number] = exact_chip_contributions(
            clean,
            generator.nominal_code(number),
            lattice,
            satellite["doppler_hz"],
            shifts[number],
        )
    numbers = [satellite["satellite"] for satellite in satellites]
    return {
        "contributions": np.array([contributions[number] for number in numbers]),
        "totals": np.array([contributions[number].sum() for number in numbers]),
        "cleans": cleans,
        "shifts": shifts,
        "coefficients": coefficients,
        "numbers": numbers,
    }


def score_changes(prepared):
    """Improvement in summed correlation power when chip i is flipped in every satellite."""
    contributions = prepared["contributions"]
    totals = prepared["totals"]
    flipped = totals[:, None] - 2.0 * contributions
    return np.sum(np.abs(flipped) ** 2 - np.abs(totals[:, None]) ** 2, axis=0)


def brute_force_change(satellites, lattice, prepared, chip_index):
    """Direct summed correlation-power change for flipping one chip in every replica."""
    numbers = set(prepared["numbers"])
    total = 0.0
    for satellite in satellites:
        if satellite["satellite"] not in numbers:
            continue
        number = satellite["satellite"]
        code = generator.nominal_code(number).copy()
        code[chip_index] *= -1.0
        peak = chip_fixing.correlation_peak(
            prepared["cleans"][number],
            code,
            lattice,
            satellite["doppler_hz"],
            prepared["shifts"][number],
        )
        total += peak
    nominal = 0.0
    for satellite in satellites:
        if satellite["satellite"] not in numbers:
            continue
        number = satellite["satellite"]
        nominal += chip_fixing.correlation_peak(
            prepared["cleans"][number],
            generator.nominal_code(number),
            lattice,
            satellite["doppler_hz"],
            prepared["shifts"][number],
        )
    return total - nominal
