# GNSS L1 C/A — recovering a hidden chip modification

A take-home assignment gave two 8 ms recordings of a simulated GPS L1 C/A baseband signal: twelve
satellites on one carrier, each satellite's 1023-chip spreading code modified chip-by-chip by an
unknown binary sequence produced by a common rule. This repository finds the satellites, reads the
modified chips out of the noise, recovers the rule, and proves the rule explains the data.

## Start here, if you are reviewing this

Two ways to read the solution, both self-contained:

- **[The walkthrough](solution-workthrough.html)**: one page, six steps, from the raw samples
  to the rule, with the measured numbers and the two figures. Open it in a browser.
- **[The same page as a PDF](solution-workthrough.pdf)**: light theme, 12 pages, for reading
  or printing offline.

The short version is below; the evidence is in [`FINDINGS.md`](FINDINGS.md) and the limits in
[`BENCHMARK.md`](BENCHMARK.md). The walkthrough is the answer to "how did you get there": every step
from the raw samples to the rule, with the arithmetic that sets each threshold, and every number in it
is one you can regenerate with the commands in this file.

## The two recordings, and what each was for

The two files are the same signal model at different strength, which is what makes them useful as a
development set and a check:

- **`data/gnss_observation.nc` is the development reference.** 12 PRNs at 54.1–54.9 dB-Hz, and it
declares a `random_seed`. Rebuilding that noise and subtracting it turns the file into a noise-free
recording, so the answer can be checked to the last digit (correlation 0.9998, 0.05% leftover power)
rather than argued about. This is the file the thresholds were derived and confirmed on.
- **`data/gnss_observation2.nc` is the robustness check.** Same 12 PRNs, the same rule and the same
slope, but 8 dB weaker on average (44.1–48.0 dB-Hz) and with no seed, so the noise-free check is not
available and the file has to stand on its own. The chain that runs on it is unchanged — nothing in
`gnss/` knows either filename beyond a command-line default — and it recovers 14 of the 15 positions,
missing `987`, which is what the noise-floor measurements say a file this weak should do (7.5% of
1000 known-truth trials drop exactly one chip). Neither file redefines the rule: the same fifteen
positions, shifted two chips per PRN, explain both.

## Answer

The two recordings share one rule. `prn_index` starts at 1.

```python
def flipped_chips(prn_index: int) -> list[int]:
    x = 1022 - 2 * prn_index
    chips = [x]
    i = 1
    while x - fibonacci(i) >= 0:
        x = x - fibonacci(i)
        chips.append(x)
        i += 1
    return chips
```

`sorted(flipped_chips(1))` is

```text
34 411 644 788 877 932 966 987 1000 1008 1013 1016 1018 1019 1020
```

Fifteen positions, two chips apart per PRN index. The first recording supports all fifteen; the
second supports fourteen of them and has no measurable evidence for chip `987`, which the report
states instead of hiding.

The same function is in the package as `gnss.rule.closed_form_flips`, and `solve.py` checks it against
the recovered list for every PRN. The result goes into `<name>_solution.json` as
`rule.closed_form_matches`: true for all twelve PRNs on recording 1, false for all twelve on
recording 2. That looks like twelve failures and is one: every PRN's list lacks the same base
position, `987` in PRN 1's coordinates and `965` in PRN 12's, because each PRN's list is that base
shifted by two chips. Compare `rule.closed_form_flips` with `rule.flips` in that file to see it.

Full reasoning and measured evidence: [`FINDINGS.md`](FINDINGS.md). The method step by step, with the
arithmetic behind every threshold and the charts: [`solution-workthrough.html`](solution-workthrough.html).

## Setup

```text
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

`requirements.txt` lists numpy and netCDF4 plus pytest and pytest-cov; CuPy is optional and used only
when present. The commands below use the `.venv` interpreter on Windows; any Python with those
packages works.

## Run it

```text
.venv/Scripts/python.exe solve.py                        # both supplied recordings
.venv/Scripts/python.exe solve.py data/gnss_observation.nc  # one recording
.venv/Scripts/python.exe solve.py my.nc --satellites 1-32 # narrower, faster search
```

`solve.py` is the whole solution in one command: acquisition, isolation, chip readout, the shift
search, the rule, and the evidence. It writes six files next to each recording, i.e. into `data/`:

| file | content |
| --- | --- |
| `data/<name>_acquisition.csv` | every searched PRN: Doppler, Doppler uncertainty, code phase, C/N0 |
| `data/<name>_joint_flips.csv` | one row per flipped chip: PRN, shift, chip index, and the same chip in PRN 1's coordinates |
| `data/<name>_solution.json` | the whole answer, including every PRN's 1023-chip original and transmitted code with its modified indexes, and the closed form per PRN |
| `data/<name>_modified_positions.csv` | one row per modified chip: PRN and chip index |
| `data/<name>_transmitted_codes.csv` | one row per PRN: chip count, modified indexes, and both 1023-chip codes space separated |
| `data/<name>_transmitted_codes.npz` | the same codes as two `(PRNs, chips)` arrays |

Exit status is 0 when the recovered base is a subset of the Fibonacci rule, 1 when a recording
supports a position the rule cannot produce. The default satellite search is `1-210`, which removes a
hidden assumption about which PRNs are in use.

`codes` in `data/<name>_solution.json` is one row per PRN: `prn`, `transmitted_code`, `original_code`
and `modified_indexes`. Both codes are the full 1023 chips. `modified_indexes` is exactly the set of
indexes where the two differ, so the answer can be checked without running the pipeline.

`data/<name>_acquisition.csv` keeps the undetected PRNs on purpose, so the search itself is auditable.
They sort last, so the first twelve rows are the answer. `data/<name>_joint_flips.csv` adds
`base_chip`, the same flip in PRN 1's coordinates: `12,22,12,34` reads as "PRN 12, shift 22, chip 12,
which is base chip 34".

### Checking the answer afterwards

Recording 1 declares a `random_seed`, so its noise can be rebuilt from the file and subtracted, leaving
the signal with no noise at all. That turns the answer into something testable to the last digit:

```text
.venv/Scripts/python.exe -m analysis.seed_recovery
```

The recovered codes then reproduce the recording at correlation **0.9998** and leave **9.3e-4** of its
power, against **0.9858** and **5.4e-2** for the nominal codes — same Doppler, offset and amplitude
freedom for both. Recording 2 declares no seed, so this check applies to recording 1 only. Procedure
and limits: `FINDINGS.md`, "Double-checking the answer against the file's own seed".

## Layout

| path | role |
| --- | --- |
| `solution-workthrough.html` | the walkthrough, step by step, with the arithmetic and the measured numbers |
| `solve.py` | the whole solution in one command: acquisition → cancellation → chip readout → shift → rule → evidence → files |
| `data/` | the recordings, plus every artifact made from them (`data/tests/`, `data/benchmark/` are generated) |
| `gnss/lattice.py` | sampling grid derived from the recording's own metadata |
| `gnss/signals.py` | spreading-code replicas, carriers, and the per-satellite linear fit |
| `gnss/alignment.py` | code phase of one satellite, coarse then sub-sample |
| `gnss/acquisition.py` | which PRNs are present, their Doppler and code phase |
| `gnss/chips.py` | one soft value per spreading-code chip |
| `gnss/rule.py` | common flip pattern, held-out flip-count search, and the closed form `closed_form_flips` |
| `gnss/verification.py` | quantitative check that the recovered codes explain the recording |
| `gnss/pipeline.py` | the chain as one call, returning plain data objects |
| `gnss/tables.py` | CSV, JSON and array artifacts, including the 12 x 1023 transmitted codes |
| `gnss/vendor.py` | locates the vendored third-party code generator |
| `analysis/` | exploratory scripts that measure one thing each (see `analysis/__init__.py`) |
| `tests/` | 181 tests, synthetic generators with known truth, 95% coverage of `gnss/` |
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

The 90% coverage gate applies to a full run. Running one test module alone reports lower coverage and
exits non-zero for that reason, not because a test failed.

## Where it works and where it breaks

`python benchmark.py` synthesises recordings across one axis at a time — C/N0, number of flipped
chips, PRN count, record length, shift per PRN, fractional code phase, a data bit flipping mid-record,
and the no-shared-rule cases — and scores every run against truth. Full tables: [`BENCHMARK.md`](BENCHMARK.md).

| axis | result with 12 PRNs at 55 dB-Hz |
| --- | --- |
| C/N0 per PRN | exact in both seeds down to **51 dB-Hz**; 95% edge **49.4 dB-Hz** over 100 signals per point; at 45 dB-Hz 26 of 100 runs recover every chip |
| flipped chips per PRN | exact in both seeds to **160** of 1023; 95% edge **140 chips** over 100 signals; the shift search fails at 320, detection at 400, nothing at 500 |
| PRNs at 52 dB-Hz | exact in both seeds from **4 to 30**; 95% edge at **7 PRNs** (6 gives 94 of 100); 1 PRN cannot define a shift at all, 2–3 miss a chip, and from 40 up a few PRNs stop being *detected* (78/80 at 80 PRNs, 197–202/210 at 210) |
| record length | exact in both seeds from **4 ms**; 95% edge **5 code periods** (4 ms gives 94 of 100); 2 ms loses 13-40% of the flips |
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
section of the same report, or the figure in two page themes,
[`assets/cn0_vs_duration_light.svg`](assets/cn0_vs_duration_light.svg) and
[`assets/cn0_vs_duration_dark.svg`](assets/cn0_vs_duration_dark.svg).

## How this was built

The assignment allows AI-assisted development tools, and this used one: an AI coding assistant wrote
most of the code and most of the prose in this repository, including the walkthrough.

What that does and does not buy the reader:

- **Every number is checkable.** Each figure and table in these documents comes from a command in this
  repo — `solve.py`, `benchmark.py`, `breakpoints.py`, or a script in `analysis/`. Nothing is quoted
  from a summary; if a claim here is wrong, re-running the command says so.
- **The reasoning is arithmetic, not assertion.** The walkthrough derives each threshold — the 36.1 dB
  processing gain, the 500 Hz Doppler step, the ±5175 Hz span, the detection threshold, the 10.8 dB
  combining gain — from constants you can check by hand.
- **The mistakes are in the record.** The commit history is the working log, including the rounds that
  exist only because a claim did not survive checking: a chip-labelling bug, a Doppler fit that was
  95 Hz wrong while claiming ±1.4 Hz, figures redrawn after review, and two numbers corrected because
  the command they cited no longer printed them. `FINDINGS.md`, "Bugs found and fixed", lists them.

I directed the work, reviewed each result and can defend it line by line; the assistant did the typing,
ran the experiments and produced the numbers.

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
- **Written for this task:** all other code in this repository.
