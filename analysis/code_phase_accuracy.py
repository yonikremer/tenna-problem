"""How accurate is the recovered code phase, and how accurate could it be?

Injects a known sub-sample code delay plus noise at a stated carrier-to-noise density, then
compares two estimators:
  current  - parabolic fit through the 4-samples-per-chip correlation peak
  upsampled- zero-padded spectrum, so the correlation is evaluated 16x denser before the fit
Truth is known, so bias and spread are measured, not assumed.
"""

import sys

import numpy as np

from gnss.acquisition import coherent_correlation
from gnss.lattice import Lattice
from gnss.signals import spreading_code_replica

SPEED_OF_LIGHT_M_S = 299_792_458.0


def upsampled_shift(samples, satellite, lattice, doppler_hz, factor):
    """Peak position in samples, from a correlation evaluated `factor` times denser."""
    length = len(samples)
    code = spreading_code_replica(satellite, length, lattice)
    times = np.arange(length) / lattice.sample_rate_hz
    product = samples * np.exp(-2j * np.pi * doppler_hz * times)
    spectrum = np.fft.fft(product) * np.conj(np.fft.fft(code))
    fine = np.fft.ifft(spectrum, n=length * factor)
    power = np.abs(fine) ** 2
    distinct = power[: lattice.samples_per_code_period * factor]
    index = int(np.argmax(distinct))
    below, at, above = distinct[(index - 1) % len(distinct)], distinct[index], distinct[(index + 1) % len(distinct)]
    curvature = below - 2.0 * at + above
    offset = 0.0 if curvature >= 0 else 0.5 * (below - above) / curvature
    return (index + offset) / factor


def main(trials=40):
    lattice = Lattice(
        sample_rate_hz=4092000.0,
        centre_frequency_hz=1575420000.0,
        chip_rate_hz=1023000.0,
        code_length_in_chips=1023,
    )
    length = lattice.samples_per_code_period * 8
    times = np.arange(length) / lattice.sample_rate_hz
    generator = np.random.default_rng(11)
    satellite, doppler_hz = 9, 2054.9
    amplitude = np.sqrt(0.0773)  # per-PRN amplitude implied by the file's 55 dB-Hz
    current, upsampled, truth = [], [], []

    frequencies = np.fft.fftfreq(length)
    for _ in range(trials):
        # true fractional delay in samples, applied as a band-limited delay (phase ramp), because
        # the code generator itself snaps its fractional offset to the sample grid and would make
        # the injected truth quantised rather than continuous
        delay_samples = generator.uniform(0.0, length)
        base = amplitude * spreading_code_replica(satellite, length, lattice) * np.exp(
            2j * np.pi * doppler_hz * times
        )
        noisy = np.fft.ifft(np.fft.fft(base) * np.exp(-2j * np.pi * frequencies * delay_samples))
        noisy += (generator.standard_normal(length) + 1j * generator.standard_normal(length)) / np.sqrt(2.0)
        delay_chips = (delay_samples * lattice.code_phase_increment) % lattice.code_length_in_chips

        _, _, shift, _ = coherent_correlation(noisy, satellite, lattice, doppler_hz)
        current.append((shift * lattice.code_phase_increment) % lattice.code_length_in_chips)
        upsampled.append(
            (upsampled_shift(noisy, satellite, lattice, doppler_hz, 16) * lattice.code_phase_increment)
            % lattice.code_length_in_chips
        )
        truth.append(delay_chips)

    def wrap(values):
        return (np.array(values) + lattice.code_length_in_chips / 2) % lattice.code_length_in_chips - (
            lattice.code_length_in_chips / 2
        )

    error_current = wrap(np.array(current) - np.array(truth))
    error_upsampled = wrap(np.array(upsampled) - np.array(truth))
    metres_per_chip = SPEED_OF_LIGHT_M_S / lattice.chip_rate_hz
    print(f"trials {trials}, satellite {satellite}, {doppler_hz} Hz, 55 dB-Hz, 8 code periods")
    print(f"  current    bias {error_current.mean():+.4f} chips  std {error_current.std():.4f} chips")
    print(f"  upsampled  bias {error_upsampled.mean():+.4f} chips  std {error_upsampled.std():.4f} chips")
    print(f"  1 chip = {1e9 / lattice.chip_rate_hz:.1f} ns = {metres_per_chip:.1f} m of range")
    for name, error in (("current", error_current), ("upsampled", error_upsampled)):
        print(f"  {name:9s} worst {np.abs(error).max():.4f} chips = {np.abs(error).max() * metres_per_chip:.2f} m")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
