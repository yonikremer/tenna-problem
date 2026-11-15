"""The correlation kernels, and the promise that the backend only changes where they run.

Two things are pinned here:

 1. The CPU kernel is the definition: `doppler_powers` must agree with a direct whole-record
    correlation, and `coarse_doppler_index` must agree with an argmax over `coarse_search`. This
    runs on any machine, so the fallback is tested even where there is no GPU.
 2. When a CUDA device is present, the device kernel must return the same winning cell as the CPU
    one on the same data. Nothing above the kernel can tell the two apart.
"""

import numpy as np
import pytest

from gnss import correlation, signals

GRID = signals.Lattice(
    sample_rate_hz=4_092_000.0,
    centre_frequency_hz=1_575_420_000.0,
    chip_rate_hz=1_023_000.0,
    code_length_in_chips=1023,
)
PERIOD = GRID.samples_per_code_period
PERIODS = 8
SATELLITES = (3, 7, 11)
DOPPLERS = np.array([-1000.0, -250.0, 0.0, 370.5, 1200.0])


@pytest.fixture(scope="module")
def samples():
    """A record with three satellites and noise, so every cell is a different question."""
    generator = np.random.default_rng(20261114)
    length = PERIOD * PERIODS
    times = np.arange(length) / GRID.sample_rate_hz
    total = np.zeros(length, dtype=np.complex128)
    for satellite, doppler_hz in zip(SATELLITES, (-1000.0, 370.5, 1200.0), strict=False):
        code = signals.spreading_code_replica(satellite, length, GRID)
        total += 0.3 * code * np.exp(2j * np.pi * doppler_hz * times)
    noise = generator.standard_normal(length) + 1j * generator.standard_normal(length)
    return total + noise / np.sqrt(2.0)


@pytest.fixture
def cpu_only(monkeypatch):
    """Force the numpy kernels, and restore whichever backend the machine had afterwards."""
    monkeypatch.setattr(correlation, "cp", None)
    return correlation


def whole_record_power(samples, satellite, doppler_hz):
    """The definition: one transform over the whole record, first code period of its power."""
    length = len(samples)
    code = signals.spreading_code_replica(satellite, length, GRID)
    product = samples * np.conj(signals.carrier(length, GRID, doppler_hz))
    correlated = np.fft.ifft(np.fft.fft(product) * np.conj(np.fft.fft(code)))
    return np.abs(correlated) ** 2


def test_doppler_powers_matches_a_whole_record_correlation(samples, cpu_only):
    """One period of the batched kernel must be one period of the whole-record correlation."""
    powers = cpu_only.doppler_powers(samples, 7, GRID, [370.5])
    assert powers.shape == (1, PERIOD)
    reference = whole_record_power(samples, 7, 370.5)[:PERIOD]
    assert float(np.abs(powers[0] - reference).max() / reference.max()) < 1e-9
    # the whole-record power repeats with the code period, which is why one period is enough
    assert np.allclose(reference, whole_record_power(samples, 7, 370.5)[PERIOD : 2 * PERIOD])


def test_doppler_powers_peaks_at_the_injected_doppler(samples, cpu_only):
    powers = cpu_only.doppler_powers(samples, 7, GRID, DOPPLERS)
    best = DOPPLERS[int(np.argmax(powers.max(axis=1)))]
    assert best == pytest.approx(370.5, abs=500.0)


def test_coarse_doppler_index_is_the_argmax_of_the_full_grid(samples, cpu_only):
    grid = cpu_only.coarse_search(samples, SATELLITES, GRID, DOPPLERS)
    assert grid.shape == (len(DOPPLERS), len(SATELLITES), PERIOD)
    expected = grid.transpose(1, 0, 2).reshape(len(SATELLITES), -1).argmax(axis=1) // PERIOD
    assert np.array_equal(cpu_only.coarse_doppler_index(samples, SATELLITES, GRID, DOPPLERS), expected)


def test_the_coarse_grid_does_not_depend_on_the_chunking(samples, cpu_only):
    """Chunking is a memory decision, so it must not move a single number."""
    whole = cpu_only.coarse_search(samples, SATELLITES, GRID, DOPPLERS)
    chunked = np.concatenate(
        [power for _, power in cpu_only.coarse_chunks(samples, SATELLITES, GRID, DOPPLERS, chunk=2)]
    )
    assert np.allclose(whole, chunked, rtol=0.0, atol=0.0)


@pytest.mark.skipif(correlation.cp is None, reason="no CUDA device available")
def test_the_device_kernel_picks_the_same_cells_as_the_cpu(samples, monkeypatch):
    """The device path must not change a decision: same winning bin, same power to float64 noise."""
    device_library = correlation.cp
    device_powers = correlation.doppler_powers(samples, 7, GRID, DOPPLERS)
    device_indices = correlation.coarse_doppler_index(samples, SATELLITES, GRID, DOPPLERS)

    monkeypatch.setattr(correlation, "cp", None)
    cpu_powers = correlation.doppler_powers(samples, 7, GRID, DOPPLERS)
    cpu_indices = correlation.coarse_doppler_index(samples, SATELLITES, GRID, DOPPLERS)

    assert device_library is not None
    assert np.array_equal(device_powers.argmax(axis=1), cpu_powers.argmax(axis=1))
    assert np.array_equal(device_indices, cpu_indices)
    assert float(np.abs(device_powers - cpu_powers).max() / cpu_powers.max()) < 1e-12


def test_a_requested_device_that_cannot_start_says_so(monkeypatch):
    """Asking for a GPU must never quietly turn into CPU timings."""
    monkeypatch.setattr(correlation, "BACKEND_SETTING", "gpu")
    monkeypatch.setitem(__import__("sys").modules, "cupy", None)
    with pytest.raises(ImportError, match="GNSS_BACKEND=gpu"):
        correlation._load_device_library()


def test_an_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.setattr(correlation, "BACKEND_SETTING", "quantum")
    with pytest.raises(SystemExit):
        correlation._load_device_library()
