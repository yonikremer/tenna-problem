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
Step-by-step derivation of the whole method, with the arithmetic behind every threshold:
[`SOLUTION.md`](SOLUTION.md).

## Run it

```text
.venv/Scripts/python.exe solve.py                        # both supplied recordings
.venv/Scripts/python.exe solve.py data/gnss_observation.nc  # one recording
.venv/Scripts/python.exe solve.py my.nc --satellites 1-32 # narrower, faster search
```

`solve.py` runs the whole chain and writes three files next to each recording, i.e. into `data/`:

| file | content |
| --- | --- |
| `data/<name>_acquisition.csv` | every searched PRN: Doppler, Doppler uncertainty, code phase, C/N0 |
| `data/<name>_joint_flips.csv` | one row per recovered flipped chip: PRN, shift, chip index |
| `data/<name>_solution.json` | the same answer as one machine-readable object |

Exit status is 0 when the recovered base is a subset of the Fibonacci rule, 1 when a recording
supports a position the rule cannot produce. The default satellite search is `1-210`, which removes a
hidden assumption about which PRNs are in use; it costs about 11 s per recording.

### Checking the answer afterwards

Recording 1 declares a `random_seed`, so its noise can be rebuilt from the file and subtracted, leaving
the signal with no noise at all. That turns the answer into something testable to the last digit:

```text
.venv/Scripts/python.exe -m analysis.seed_recovery
```

The recovered codes then reproduce the recording at correlation **0.9998** and leave **7.2e-4** of its
power, against **0.9858** and **5.4e-2** for the nominal codes — same Doppler, offset and amplitude
freedom for both. Recording 2 declares no seed, so this check applies to recording 1 only. Procedure
and limits: `FINDINGS.md`, "Double-checking the answer against the file's own seed".

## Layout

| path | role |
| --- | --- |
| `SOLUTION.md` | the whole method, step by step, with the arithmetic and the measured numbers |
| `solve.py` | end-to-end entry point: acquisition → cancellation → chip readout → rule → evidence |
| `data/` | the recordings, plus every artifact made from them (`data/tests/`, `data/benchmark/` are generated) |
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
.venv/Scripts/python.exe -m gnss.acquisition data/gnss_observation.nc --satellites 1-12
.venv/Scripts/python.exe -m analysis.chip_extraction data/gnss_observation.nc
```

## Where it works and where it breaks

`python benchmark.py` synthesises recordings across one axis at a time — C/N0, number of flipped
chips, PRN count, record length, shift per PRN, fractional code phase, a data bit flipping mid-record,
and the no-shared-rule cases — and scores every run against truth. Full tables: [`BENCHMARK.md`](BENCHMARK.md).

| axis | result with 12 PRNs at 55 dB-Hz |
| --- | --- |
| C/N0 per PRN | exact down to **47 dB-Hz**; at 45 dB-Hz 73-80% of the flips come back |
| flipped chips per PRN | exact for **3 to 240** of 1023 (one run at 200 came back a chip short); shift search fails at 320, detection at 400, nothing at 500 |
| PRNs at 52 dB-Hz | exact from **6 to 30**; 1 PRN cannot define a shift at all, 2–5 miss a chip or two, and from 40 up a few PRNs stop being *detected* (78/80 at 80 PRNs, 197–202/210 at 210) |
| record length | **4 ms and longer** exact; 2 ms loses 13-40% of the flips |
| shift per PRN | exact for **0, 1, 2, 3, 7, 25** chips |
| fractional code phase | flips exact at 0.25/0.5/0.75 sample offsets; residual power rises to 1.14x noise |
| data bit flipping mid-record | exact; worst Doppler error 3.7 Hz |
| data bits changing at random per PRN (P = record/20 ms) | exact at **8 and 16 ms**; at 2 ms a transition costs the Doppler fit (371 Hz) though the chips survive |
| Doppler absent or clustered | exact with all 12 PRNs at **0 Hz**, within ±2 Hz, and within ±20 Hz |
| Doppler far from zero | found to about **±5.5 kHz** with the default span; nothing at ±5.8 kHz — but raising `--max-speed-km-h` recovers **±6, ±10, ±15, ±20 and ±30 kHz exactly**, at the cost of search time and a slightly higher detection threshold |
| no shared rule / no modification | reports **0 chips at 0.000 dB** — no rule invented |

The assignment's own case (12 PRNs, 55 dB-Hz, 15 chips) passes with margin. Below 6 detected PRNs `solve.py` prints a warning: the combining gain is not there, and the benchmark shows 2-4 PRNs leave 7-13% of the chips missing.

`benchmark.py` uses two noise seeds per grid point, which can only report 0/2, 1/2 or 2/2. To turn
those edges into a rate, `python breakpoints.py` runs **100 independent recordings per probe** and
bisects each axis for the value where exact recovery stops, quoting the binomial interval of every
probe (100 signals resolve a 95% rate to about ±4 points). It also checks its own bracket before
trusting a bisection. It is the `## Break points` section at the end of [`BENCHMARK.md`](BENCHMARK.md).

`python breakpoints.py --duration` asks the same question in two dimensions instead of one: what is
the lowest C/N0 that still recovers all 15 chips at each record length? The floor falls **13.4 dB
between 2 and 32 code periods - 3.36 dB per doubling** of the record, which is what one more
coherent chip measurement per period should buy. Scatter and numbers: the `## Duration against C/N0`
section of the same report, or [`assets/cn0_vs_duration.svg`](assets/cn0_vs_duration.svg).

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
