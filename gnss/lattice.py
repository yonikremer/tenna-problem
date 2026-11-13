"""Sampling grid of a recording, derived from the recording's own metadata.

Every downstream number - samples per chip, samples per code period, code-phase increment,
Doppler step - is a consequence of the four values in `Lattice`. Published GPS L1 constants are
used only for the two values a file may omit, and only as a stated fallback.
"""

from dataclasses import dataclass

import netCDF4
import numpy as np

# Published GPS L1 values, from the GPS interface specification (IS-GPS-200). Used only when a
# recording does not state them in its metadata.
PUBLISHED_GPS_L1 = {
    "chip_rate_hz": 1_023_000.0,
    "code_length_in_chips": 1023,
}


@dataclass(frozen=True)
class Lattice:
    """Sampling grid of a recording, plus the quantities every search derives from it."""

    sample_rate_hz: float
    centre_frequency_hz: float
    chip_rate_hz: float
    code_length_in_chips: int

    @property
    def samples_per_chip(self) -> float:
        return self.sample_rate_hz / self.chip_rate_hz

    @property
    def samples_per_code_period(self) -> int:
        return int(round(self.samples_per_chip * self.code_length_in_chips))

    @property
    def code_period_seconds(self) -> float:
        return self.code_length_in_chips / self.chip_rate_hz

    @property
    def code_phase_increment(self) -> float:
        """Chips advanced per sample at the nominal chip rate."""
        return self.code_length_in_chips / self.samples_per_code_period

    @property
    def samples_per_chip_whole(self) -> int:
        """Samples per chip as a whole number; the chip grid only exists when this is exact."""
        return self.samples_per_code_period // self.code_length_in_chips

    @property
    def chip_grid_is_exact(self) -> bool:
        return self.samples_per_chip_whole * self.code_length_in_chips == self.samples_per_code_period


def lattice_from_metadata(dataset) -> Lattice:
    """Read the grid from a NetCDF dataset, falling back to published GPS L1 values."""

    def value(name, fallback):
        if name in dataset.ncattrs():
            return getattr(dataset, name)
        if fallback is None:
            raise SystemExit(f"recording does not state {name} and no published value applies")
        return fallback

    try:
        lattice = Lattice(
            sample_rate_hz=float(value("sample_rate_hz", None)),
            centre_frequency_hz=float(value("center_frequency_hz", None)),
            chip_rate_hz=float(value("nominal_chip_rate_hz", PUBLISHED_GPS_L1["chip_rate_hz"])),
            code_length_in_chips=int(
                value("nominal_code_length_chips", PUBLISHED_GPS_L1["code_length_in_chips"])
            ),
        )
    except (TypeError, ValueError) as error:
        raise SystemExit(f"recording metadata is not numeric: {error}") from error

    if abs(lattice.samples_per_chip - round(lattice.samples_per_chip)) > 1e-6:
        raise SystemExit(
            f"sample rate {lattice.sample_rate_hz:g} Hz is not a whole multiple of the "
            f"chip rate {lattice.chip_rate_hz:g} Hz ({lattice.samples_per_chip:.6f} samples/chip)"
        )
    return lattice


def load_recording(path: str):
    """Complex baseband samples, the number of whole code periods, and the sampling grid.

    A trailing partial code period is dropped: every stage of the pipeline assumes whole periods.
    """
    try:
        with netCDF4.Dataset(path) as dataset:
            lattice = lattice_from_metadata(dataset)
            real = np.asarray(dataset["i"][:], dtype=np.float64)
            imaginary = np.asarray(dataset["q"][:], dtype=np.float64)
    except OSError as error:
        raise SystemExit(f"cannot read {path}: {error}") from error
    samples = real + 1j * imaginary
    code_periods = len(samples) // lattice.samples_per_code_period
    return samples[: code_periods * lattice.samples_per_code_period], code_periods, lattice


def reading(path: str) -> dict:
    """Every NetCDF attribute of a recording, for a report that states its inputs."""
    try:
        with netCDF4.Dataset(path) as dataset:
            return {name: getattr(dataset, name) for name in dataset.ncattrs()}
    except OSError as error:
        raise SystemExit(f"cannot read {path}: {error}") from error
