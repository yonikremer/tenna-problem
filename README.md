# GNSS L1 C/A — recovering a hidden chip modification

A take-home assignment gave two 8 ms recordings of a simulated GPS L1 C/A baseband signal: twelve
satellites on one carrier, each satellite's 1023-chip spreading code modified chip-by-chip by an
unknown binary sequence produced by a common rule. This repository finds the satellites, reads the
modified chips out of the noise, recovers the rule, and proves the rule explains the data.

## Answer

The two recordings share one rule. PRN `s` flips the chips

```text
(base[k] - 2 * (s - 1)) mod 1023
```

where the base set is the prefix sums of the Fibonacci numbers counted backwards from chip 1020:

```text
base = { (1020 - sum(Fibonacci[0:k])) mod 1023 : k = 0..14 }
Fibonacci = 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377

base = 34 411 644 788 877 932 966 987 1000 1008 1013 1016 1018 1019 1020
```

Fifteen positions, two chips apart per PRN index. The first recording supports all fifteen; the
second supports fourteen of them and has no measurable evidence for chip `987`, which the report
states instead of hiding. Full reasoning and measured evidence: [`FINDINGS.md`](FINDINGS.md).

## Run it

```text
.venv/Scripts/python.exe solve.py                        # both supplied recordings
.venv/Scripts/python.exe solve.py gnss_observation.nc     # one recording
.venv/Scripts/python.exe solve.py my.nc --satellites 1-32 # narrower, faster search
```

`solve.py` runs the whole chain and writes three files next to each recording:

| file | content |
| --- | --- |
| `<name>_acquisition.csv` | every detected PRN: Doppler, Doppler uncertainty, code phase, C/N0 |
| `<name>_joint_flips.csv` | one row per recovered flipped chip: PRN, shift, chip index |
| `<name>_solution.json`  | the same answer as one machine-readable object |

Exit status is 0 when the recovered base is a subset of the Fibonacci rule, 1 when a recording
supports a position the rule cannot produce. The default satellite search is `1-210`, which removes a
hidden assumption about which PRNs are in use; it costs about 25 s per recording.

## Layout

| path | role |
| --- | --- |
| `solve.py` | end-to-end entry point: acquisition → cancellation → chip readout → rule → evidence |
| `gnss/lattice.py` | sampling grid derived from the recording's own metadata |
| `gnss/signals.py` | spreading-code replicas, carriers, and the per-satellite linear fit |
| `gnss/alignment.py` | code phase of one satellite, coarse then sub-sample |
| `gnss/acquisition.py` | which PRNs are present, their Doppler and code phase |
| `gnss/chips.py` | one soft value per spreading-code chip |
| `gnss/rule.py` | common flip pattern, held-out flip-count search, Fibonacci structure |
| `gnss/verification.py` | quantitative check that the recovered codes explain the recording |
| `gnss/pipeline.py` | the chain as one call, returning plain data objects |
| `gnss/tables.py` | CSV and JSON artifacts |
| `gnss/vendor.py` | locates the vendored third-party code generator |
| `analysis/` | exploratory scripts that measure one thing each (see `analysis/__init__.py`) |
| `tests/` | 127 tests, synthetic generators with known truth, 97% coverage of `gnss/` |
| `vendor/` | third-party MIT code (Peter Monta, GNSS-DSP-tools): the C/A code tables come from here |
| `docs/` | working notes written while solving |

## Tests

```text
.venv/Scripts/python.exe -m pytest
```

The suite builds two synthetic recordings with known truth — one with independent random flips per
PRN, one with the shared shifted rule at 55 dB-Hz — and checks the whole chain against them, plus
known-answer self-checks inside the modules. Coverage of `gnss/` is held at 90% by `pytest.ini`.

A single module runs on its own as well:

```text
.venv/Scripts/python.exe -m gnss.acquisition gnss_observation.nc --satellites 1-12
.venv/Scripts/python.exe -m analysis.chip_extraction gnss_observation.nc
```

## Third-party code, stated plainly

The C/A spreading codes come from someone else's code, not mine.

- **Vendored:** `gnsstools.gps.ca` (code generator and the IS-GPS-200 G2 delay table),
  `gnsstools.nco`, `gnsstools.io` from **Peter Monta's
  [GNSS-DSP-tools](https://github.com/pmonta/GNSS-DSP-tools)**, MIT licence, Copyright (c) 2014
  Peter Monta. Copied unchanged at commit `be93f96f9bf1c31a82ac52b5f8e67bf023977190` and trimmed to
  the files this project uses. Licence text: `vendor/LICENSE`. Provenance and the exact file list:
  `vendor/README.md`.
- **Used as a reference, not copied:** upstream's acquisition, tracking and cancellation scripts.
  Everything in `gnss/` — acquisition, alignment, cancellation, chip readout, rule recovery,
  verification — is written for this task. One exception is stated where it lives:
  `analysis/acquire_nc.py` keeps Peter Monta's FFT acquisition kernel shape as an independent
  cross-check of `gnss/acquisition.py`, and its docstring says so.
- **Mine:** all other code in this repository.
