"""GPS L1 C/A acquisition with the vendored GNSS-DSP-tools kernels, as an independent cross-check.

Reuses (unmodified, imported from the vendored copy in `vendor/`):
  - gnsstools.gps.ca.code  : fractional-chip C/A replica
  - gnsstools.nco.mix      : carrier wipeoff NCO
  - gnsstools.io           : int8 interleaved reader

The search kernel below is Peter Monta's, copied from acquire-gps-l1.py, with the
multiprocessing.Pool removed: that script has no `if __name__ == "__main__"` guard,
which is fine under Linux fork but dies under Windows spawn.

The point of running a second, independent implementation is to confirm that the acquisition in
`gnss.acquisition` is not agreeing with itself. Results agree to the coarse grid this kernel uses.

Usage: python -m analysis.acquire_nc obs1.cu8 [first-prn last-prn]
"""

import sys

import numpy as np
import scipy.fftpack as fft
import scipy.signal

from gnss.vendor import add_to_import_path

add_to_import_path()

import gnsstools.gps.ca as ca  # type: ignore  # noqa: E402
import gnsstools.io as io  # type: ignore  # noqa: E402
import gnsstools.nco as nco  # type: ignore  # noqa: E402

MS = 3             # coherent/incoherent integration in ms
DOPPLER = (-7000.0, 7000.0, 200.0)
FS_R = 4096000.0   # internal rate expected by the kernel


def load(path, ms):
    """Load int8 IQ and resample to 4.096 MHz exactly as acquire-gps-l1.py does."""
    fs = 4092000.0
    ms_pad = ms + 5
    try:
        with open(path, "rb") as handle:
            x = io.get_samples_complex(handle, int(fs * 0.001 * ms_pad))
    except OSError as error:
        raise RuntimeError(f"cannot read {path}: {error}") from error
    if x is None:
        raise RuntimeError(f"{path}: shorter than {ms_pad} ms")
    fsr = FS_R / fs
    h = scipy.signal.firwin(161, 1.5e6 / (fs / 2), window="hann")
    x = scipy.signal.filtfilt(h, [1], x)
    idx = (1 / fsr) * np.arange(ms_pad * 4096)
    return np.interp(idx, np.arange(len(x)), np.real(x)) + 1j * np.interp(idx, np.arange(len(x)), np.imag(x))


def search(x, prn, doppler_search, ms):
    """Peter Monta's acquisition kernel (FFT parallel code-phase search)."""
    fs = FS_R
    n = 4096
    doppler_min, doppler_max, doppler_incr = doppler_search
    incr = float(ca.code_length) / n
    c = fft.fft(ca.code(prn, 0, 0, incr, n))
    m_metric, m_code, m_doppler = 0, 0, 0
    for doppler in np.arange(doppler_min, doppler_max, doppler_incr):
        q = np.zeros(n)
        w = nco.nco(-doppler / fs, 0, n)
        for block in range(ms):
            b = x[(block * n) : ((block + 1) * n)]
            b = b * w
            r = fft.ifft(c * np.conj(fft.fft(b)))
            q = q + np.absolute(r)
        idx = np.argmax(q)
        metric = q[idx] / np.mean(q)
        if metric > m_metric:
            m_metric = metric
            m_code = ca.code_length * (float(idx) / n)
            m_doppler = doppler
    return m_metric, m_code, m_doppler


def main(path, prns):
    x = load(path, MS)
    print(f"{path}: {len(x)} samples @ {FS_R:g} Hz, {MS} ms integration, doppler grid {DOPPLER}")
    print(f"{'prn':>4} {'metric':>7} {'doppler Hz':>11} {'code phase (chips)':>19}")
    rows = []
    for prn in prns:
        metric, code, doppler = search(x, prn, DOPPLER, MS)
        rows.append((metric, prn, doppler, code))
    for metric, prn, doppler, code in sorted(rows, reverse=True):
        print(f"{prn:>4} {metric:>7.2f} {doppler:>11.1f} {code:>19.2f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        main(sys.argv[1], range(1, 33))
    else:
        main(sys.argv[1], range(int(sys.argv[2]), int(sys.argv[3]) + 1))
