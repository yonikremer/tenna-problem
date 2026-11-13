# Vendored code

Everything in this folder is **third-party code, not mine**. It is copied here unchanged so the
solution can generate GPS L1 C/A spreading codes from the published tables instead of from a
transcription of them.

| | |
| --- | --- |
| upstream | <https://github.com/pmonta/GNSS-DSP-tools> |
| author | Peter Monta |
| licence | MIT, Copyright (c) 2014 Peter Monta (see `LICENSE` in this folder) |
| commit copied | `be93f96f9bf1c31a82ac52b5f8e67bf023977190` (2025-08-17) |
| copied on | 2026-11-14 |

## What was kept, and why

| file | what it does here |
| --- | --- |
| `gnsstools/gps/ca.py` | GPS C/A code generator: `code()`, `first_10_chips()`, `code_length`, and the IS-GPS-200 G2 delay table. Used by `gnss/signals.py`. |
| `gnsstools/nco.py` | Numerically controlled oscillator. Used only by `analysis/acquire_nc.py`, the independent acquisition cross-check. |
| `gnsstools/io.py` | reader for int8 interleaved IQ files. Used only by `analysis/acquire_nc.py`. |
| `gnsstools/__init__.py`, `gnsstools/gps/__init__.py` | empty package markers |

The upstream repository also ships acquisition and tracking scripts for every GNSS signal, and code
generators for BeiDou, Galileo, GLONASS and Xona. **None of that is here**, because none of it is
used: the acquisition, tracking, cancellation and chip-reading logic in `gnss/` is written for this
task, and the upstream scripts were read as a reference, not copied. Upstream's own generator was
used only as a trusted source of the code tables.

Deleted from the copy: `.git`, `.gitignore`, `Makefile`, `README`, every `acquire-*.py` and
`track-*.py`, `cn0.py`, `spectrum.py`, `squaring.py`, `gnsstools/{beidou,galileo,glonass,xona}`,
`gnsstools/{discriminator,squaring,util}.py`, and the non-C/A GPS generator modules
(`gnsstools/gps/{l1cd,l1cp,l2cl,l2cm,l5i,l5q,p}.py`).

## Licence obligation

MIT requires the copyright notice and permission notice to travel with the code. They are in
`vendor/LICENSE`, and `README.md` at the repository root says in plain words which parts are
third-party. If you redistribute this repository, keep both.
