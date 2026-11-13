"""Convert a NetCDF recording (float32 i/q) into int8 interleaved IQ for GNSS-DSP-tools.

GNSS-DSP-tools' `gnsstools/io.py` only reads signed 8-bit interleaved IQ. Data is rms ~1 per
dimension; scale 20 keeps peaks inside +-127 and puts quantisation noise ~33 dB below the thermal
noise, so the SNR loss is about 0.001 dB.

Usage: python -m analysis.nc2cu8 gnss_observation.nc obs1.cu8
"""

import sys

import netCDF4
import numpy as np

SCALE = 20.0


def load_nc(path):
    with netCDF4.Dataset(path) as dataset:
        samples = np.asarray(dataset["i"][:], dtype=np.float64) + 1j * np.asarray(
            dataset["q"][:], dtype=np.float64
        )
        sample_rate_hz = float(dataset.sample_rate_hz)
    return samples, sample_rate_hz


def main(src, dst):
    samples, sample_rate_hz = load_nc(src)
    iq = np.empty(2 * len(samples), dtype=np.int8)
    iq[0::2] = np.clip(np.round(samples.real * SCALE), -127, 127)
    iq[1::2] = np.clip(np.round(samples.imag * SCALE), -127, 127)
    iq.tofile(dst)
    print(f"{src}: {len(samples)} samples @ {sample_rate_hz:g} Hz -> {dst} ({iq.nbytes} bytes, scale {SCALE:g})")
    print(f"  clipped samples: {int(np.count_nonzero(np.abs(iq) >= 127))}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
