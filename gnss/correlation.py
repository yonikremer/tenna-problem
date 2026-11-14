"""The two batched correlation searches, on the CPU or on a CUDA device.

Both kernels compute the same complex128 numbers whichever backend runs them, so the code that
decides what the numbers mean - which Doppler wins, which peak is real, what the flip rule is -
stays in one place, on numpy, above this module.

Why a kernel is worth a backend at all: the record is 32768 samples and a search asks thousands of
correlation questions about it (every satellite x every code phase x every Doppler candidate). Each
question is a 4092-point transform, which is small enough that the CPU spends most of its time in
per-call overhead, and numerous enough that a GPU is kept busy. Measured on an RTX 4050: 72 us per
transform on the CPU versus 7.6 us batched on the device.

Backend choice: `GNSS_BACKEND` = `auto` (default), `cpu` or `gpu`. Asking for `gpu` on a machine
without a usable device raises instead of quietly reporting CPU timings, and `backend()` says which
one ran so a report can state it. The CPU path is not a degraded mode: it is the reference
implementation, and the device path is checked against it.
"""

import os
from typing import Any

import numpy as np

from . import signals

BACKEND_SETTING = os.environ.get("GNSS_BACKEND", "auto").strip().lower()


def _load_device_library() -> Any:
    """CuPy when it is installed and can allocate, else None; a requested GPU must work."""
    if BACKEND_SETTING not in {"auto", "cpu", "gpu"}:
        raise SystemExit(f"GNSS_BACKEND={BACKEND_SETTING!r} is not one of auto, cpu, gpu")
    if BACKEND_SETTING == "cpu":
        return None
    try:
        import cupy

        cupy.zeros(1)  # a device that cannot allocate cannot accelerate anything
        return cupy
    except Exception as error:  # noqa: BLE001 - any failure to start means "no device"
        if BACKEND_SETTING == "gpu":
            raise ImportError(f"GNSS_BACKEND=gpu, but CuPy is not usable: {error}") from error
        return None


cp: Any = _load_device_library()

# One uploaded record, so the hundreds of kernels per recording share one copy of the samples.
# `is` is the test on purpose: the next recording is a different array and replaces it.
_uploaded: tuple[Any, Any] = (None, None)


def backend() -> str:
    """Which backend the kernels run on: `gpu` or `cpu`."""
    return "gpu" if cp is not None else "cpu"


def describe_backend() -> str:
    """The backend plus the device it uses, for a report that must not mislead."""
    if cp is None:
        return "cpu (numpy)"
    properties = cp.cuda.runtime.getDeviceProperties(0)
    name = properties["name"].decode()
    return f"gpu ({name}, CuPy {cp.__version__})"


def device_samples(samples: np.ndarray) -> Any:
    """The record resident on the device, uploaded once per array."""
    global _uploaded
    if _uploaded[0] is not samples:
        _uploaded = (samples, cp.asarray(samples))
    return _uploaded[1]


def doppler_powers(samples: np.ndarray, satellite: int, lattice, dopplers) -> np.ndarray:
    """Correlation power over one code period for each Doppler candidate, `(len(dopplers), period)`.

    The replica repeats every code period, so the whole-record correlation is the sum of the
    per-period correlations and its power repeats with them. Correlating a period at a time keeps
    both transforms short, and the code's own spectrum is cached by `signals.code_period_plan`
    instead of being rebuilt for every candidate.

    The carrier is split into its drift inside one period and the whole-cycle step that period p
    adds, so the only full-length-in-candidates factor is one period wide.

    Where the candidates are batched differs by backend, and the reason is measured rather than
    assumed: on the CPU one candidate at a time is 1.5x faster, because a 35 MB candidate block is
    memory-bound where a 0.5 MB one stays in cache; on the device batching is what keeps the
    transforms off the launch-latency floor. Both produce the same numbers.
    """
    dopplers = np.atleast_1d(np.asarray(dopplers, dtype=float))
    period = lattice.samples_per_code_period
    periods = len(samples) // period
    spectrum = signals.code_period_plan(satellite, lattice, 0.0)[0]
    clock = signals.sample_times(period, lattice.sample_rate_hz)
    step = (np.arange(periods) * period) / lattice.sample_rate_hz

    if cp is None:
        blocks = samples.reshape(periods, period)
        powers = []
        for doppler_hz in dopplers:
            within = np.exp(-2j * np.pi * doppler_hz * clock)
            across = np.exp(-2j * np.pi * doppler_hz * step)
            spectra = np.fft.fft(blocks * within, axis=1) * across[:, None]
            powers.append(np.abs(np.fft.ifft(spectra.sum(axis=0) * spectrum)) ** 2)
        return np.stack(powers)

    blocks = device_samples(samples).reshape(periods, period)
    candidate = cp.asarray(dopplers)
    within = cp.exp(-2j * cp.pi * candidate[:, None] * cp.asarray(clock)[None, :])
    across = cp.exp(-2j * cp.pi * candidate[:, None] * cp.asarray(step)[None, :])
    spectra = cp.fft.fft(blocks[None, :, :] * within[:, None, :], axis=-1) * across[:, :, None]
    correlation_grid = cp.fft.ifft(spectra.sum(axis=1) * cp.asarray(spectrum), axis=-1)
    return cp.asnumpy(cp.abs(correlation_grid) ** 2)


def _coarse_chunk(periods: int, satellites: int, period: int) -> int:
    """How many Doppler candidates to put on the device at once, from the product array's size."""
    target = 2**24  # complex128 elements per (candidate, period, satellite) product, ~256 MB
    return max(1, target // max(periods * satellites * period, 1))


def coarse_chunks(samples: np.ndarray, satellites, lattice, dopplers, chunk: int | None = None):
    """Yield `(first index, powers)` with powers of shape `(chunk, satellites, period)`.

    Non-coherent integration: every code period's power is summed, so a data bit that changes
    inside the record costs one period rather than the whole correlation. The sum is divided by the
    number of periods, so the reported quantity is a mean power per period.

    The CPU path is the pre-device implementation, one Doppler candidate at a time, because that
    measured faster on numpy - the batched block is a quarter of a gigabyte where one candidate's
    is a few megabytes. The same numbers come out either way.
    """
    satellites = list(satellites)
    period = lattice.samples_per_code_period
    periods = len(samples) // period
    dopplers = np.asarray(dopplers, dtype=float)
    if cp is None:
        split = samples.reshape(periods, period)
        clock = signals.sample_times(period, lattice.sample_rate_hz)
        spectra = np.conj(
            np.fft.fft(
                np.stack([signals.spreading_code_replica(s, period, lattice) for s in satellites]), axis=1
            )
        )
        for index, doppler_hz in enumerate(dopplers):
            rotation = np.exp(-2j * np.pi * doppler_hz * clock)
            accumulated = np.zeros((len(satellites), period))
            for one_period in range(periods):
                signal_spectrum = np.fft.fft(split[one_period] * rotation)
                accumulated += np.abs(np.fft.ifft(spectra * signal_spectrum, axis=1)) ** 2
            yield index, (accumulated / periods)[None, :, :]
        return

    split = device_samples(samples).reshape(periods, period)
    clock = cp.asarray(signals.sample_times(period, lattice.sample_rate_hz))
    spectra = cp.asarray(
        np.conj(
            np.fft.fft(
                np.stack([signals.spreading_code_replica(s, period, lattice) for s in satellites]), axis=1
            )
        )
    )
    size = chunk or _coarse_chunk(periods, len(satellites), period)
    for start in range(0, len(dopplers), size):
        block = cp.asarray(dopplers[start : start + size])
        rotation = cp.exp(-2j * cp.pi * block[:, None] * clock[None, :])
        signal_spectra = cp.fft.fft(split[None, :, :] * rotation[:, None, :], axis=-1)
        products = signal_spectra[:, :, None, :] * spectra[None, None, :, :]
        correlation_grid = cp.fft.ifft(products, axis=-1)
        power = (cp.abs(correlation_grid) ** 2).sum(axis=1) / periods
        yield start, cp.asnumpy(power)


def coarse_search(samples: np.ndarray, satellites, lattice, doppler_grid_hz) -> np.ndarray:
    """Power for every satellite, every code phase and every Doppler candidate: `(doppler, sat, code)`."""
    satellites = list(satellites)
    period = lattice.samples_per_code_period
    grid = np.empty((len(doppler_grid_hz), len(satellites), period))
    for start, power in coarse_chunks(samples, satellites, lattice, doppler_grid_hz):
        grid[start : start + len(power)] = power
    return grid


def coarse_doppler_index(samples: np.ndarray, satellites, lattice, doppler_grid_hz) -> np.ndarray:
    """For each satellite, the Doppler candidate with the highest power: what acquisition asks.

    The whole grid is never materialised on the host, which is the difference between moving a few
    integers and moving a quarter of a gigabyte when a search covers two hundred satellites.
    """
    satellites = list(satellites)
    period = lattice.samples_per_code_period
    if cp is None:
        grid = coarse_search(samples, satellites, lattice, doppler_grid_hz)
        flat = grid.transpose(1, 0, 2).reshape(len(satellites), -1)
        return flat.argmax(axis=1) // period

    # Reduce on the device: only the winning index per satellite comes back.
    dopplers = np.asarray(doppler_grid_hz, dtype=float)
    periods = len(samples) // period
    split = device_samples(samples).reshape(periods, period)
    clock = cp.asarray(signals.sample_times(period, lattice.sample_rate_hz))
    spectra = cp.asarray(
        np.conj(
            np.fft.fft(
                np.stack([signals.spreading_code_replica(s, period, lattice) for s in satellites]), axis=1
            )
        )
    )
    best = cp.zeros(len(satellites), dtype=cp.int64)
    best_power = cp.full(len(satellites), -cp.inf)
    size = _coarse_chunk(periods, len(satellites), period)
    for start in range(0, len(dopplers), size):
        block = cp.asarray(dopplers[start : start + size])
        rotation = cp.exp(-2j * cp.pi * block[:, None] * clock[None, :])
        signal_spectra = cp.fft.fft(split[None, :, :] * rotation[:, None, :], axis=-1)
        products = signal_spectra[:, :, None, :] * spectra[None, None, :, :]
        correlation_grid = cp.fft.ifft(products, axis=-1)
        power = (cp.abs(correlation_grid) ** 2).sum(axis=1) / periods
        power = power.max(axis=2)
        for offset in range(len(block)):
            better = power[offset] > best_power
            best_power = cp.where(better, power[offset], best_power)
            best = cp.where(better, start + offset, best)
    return cp.asnumpy(best)
