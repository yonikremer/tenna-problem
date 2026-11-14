# Solution walkthrough

A complete account of how this solves the assignment: what the signal is, what each step does and
why, the arithmetic that sets every threshold, and the numbers the code actually produced. Every
number below comes from running the code in this repository, not from notes.

- Answer and evidence in brief: [`README.md`](README.md)
- Measured evidence and the reasoning behind it: [`FINDINGS.md`](FINDINGS.md)
- Where the method stops working: [`BENCHMARK.md`](BENCHMARK.md)

---

## 1. The problem

Two NetCDF files hold 8 ms of simulated GPS L1 C/A baseband, sampled at 4.092 MHz, containing a
superposition of 12 satellites. Each satellite's 1023-chip spreading code has been modified
chip-by-chip by an unknown binary sequence. All satellites' modifications follow one common rule. The
task: find the satellites, recover the modification, state the rule, and prove it explains the data.

## 2. The answer

PRN `s` flips the chips

```text
base[k] - 2 * (s - 1)   mod 1023
```

where `base` is the prefix sums of the Fibonacci numbers counted backwards from chip 1020:

```text
base = { (1020 - sum(Fibonacci[0:k])) mod 1023 : k = 0..14 }
Fibonacci = 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377

base = 34 411 644 788 877 932 966 987 1000 1008 1013 1016 1018 1019 1020
```

Fifteen positions, shifted **two chips per PRN index**. Recording 1 supports all fifteen; recording 2
supports fourteen of them and is explicit about the one it cannot see (`987`).

## 3. Signal model and vocabulary

The composite recording is

```text
x[n] = sum over satellites s of  a_s * c_s[k(n)] * exp(j(2*pi*f_s*t_n + phi_s)) * b_s[n]  +  noise[n]
```

| symbol | meaning | how it is obtained |
| --- | --- | --- |
| `c_s` | spreading code of satellite `s`, 1023 values, ±1 | published tables (`vendor/gnsstools/gps/ca.py`) |
| `k(n)` | chip index of sample `n` | from the code phase, see step 5 |
| `a_s` | amplitude per sample (complex) | fitted, one number per satellite |
| `f_s` | carrier Doppler | searched, then refined to a fraction of a hertz |
| `phi_s` | carrier phase | absorbed into `a_s` |
| `b_s[n]` | navigation data bit, ±1, 20 ms long | constant here; detected if it flips |
| noise | complex AWGN | measured as received power minus satellites |

Vocabulary used consistently in the code: *spreading code*, *chip*, *code period* (1023 chips = 1 ms),
*code phase* (position inside the period, in chips), *carrier Doppler* (Hz offset of one satellite).

The sampling lattice is read from the file, never assumed:

```text
sample rate 4.092 MHz, chip rate 1.023 MHz  ->  4 samples per chip  ->  4092 samples per code period
8 code periods  ->  32736 samples  ->  8 ms
```

## 4. Step 1 — acquisition: which satellites are there, and where

For each candidate satellite and each candidate Doppler, correlate the recording with a code × carrier
replica. The peak over all code phases is the detection statistic.

**Processing gain.** Coherently combining `N` samples raises the signal by `N` and the noise by
`sqrt(N)`, a gain of `10*log10(N)`:

```text
1 code period at 1 sample/chip     10*log10(1023) = 30.1 dB
1 code period at 4 samples/chip    10*log10(4092) = 36.1 dB
```

That is why 8 ms of a 55 dB-Hz signal, which is invisible in the raw samples, stands 30 dB out of the
noise after correlation.

**Doppler grid, derived not guessed.** The coherent sum loses coherence when the carrier rotates a
half cycle across the integration window, so the coarse step is half a cycle per code period:

```text
coarse step = 1 / (2 * T_period) = 1 / (2 ms) = 500 Hz
fine step   = 1 / (4 * T_total)  = 1 / (32 ms) = 31.25 Hz
```

**Doppler span, from physics.** The largest relative speed a ground receiver can see is the
satellite's line-of-sight speed plus its own. For a circular orbit the radial part of the orbital speed
is `sqrt(mu/a) * (R_earth / a)` = 929 m/s; a receiver at 200 km/h adds 55.6 m/s. Then

```text
span = f_carrier * v_relative / c = 1575.42e6 * 984.6 / 299792458 = +-5175 Hz
```

`--max-speed-km-h` changes that assumption, and section 9 shows what happens when you do.

**Detection threshold, from a false-alarm probability.** Noise-only correlation power is exponentially
distributed, so one cell exceeds `t` times the median with probability `2^-t`. Over `cells` independent
cells the chance that any cell anywhere is that high is `cells * 2^-t`; solving for a per-search
false-alarm probability of `1e-6`:

```text
t = log2(cells / P_fa)
```

with `cells = satellites * code phases * Doppler bins`. For 210 satellites that is about 40
peak-to-floor. The floor is a **median** over lag, not a mean: other satellites' codes leave
cross-correlation spikes that would bias a mean upward.

**Result on recording 1** (`data/gnss_observation_acquisition.csv`): 12 satellites, all detected with
peak-to-floor 1259–1930 against a threshold of 39.9, C/N0 54.1–54.9 dB-Hz, Doppler ±2704 Hz, code
phase to a thousandth of a chip.

## 5. Step 2 — code phase: where inside the code period

A whole-record coherent sum is the wrong tool here: a navigation data bit may change inside the
record, the two halves then cancel, the peak collapses, and the alignment it reports is wrong. So the
first estimate comes from the **strongest single code period**, refined by a three-point parabolic fit
through the peak, and then by a sub-sample search that maximises total segment energy — insensitive to a
sign change.

Measured on injected band-limited delays at 55 dB-Hz, the finished stage is accurate to **bias −0.12,
standard deviation 0.17, worst 0.42 sample** — 0.11 chip worst case. On the 75 dB-Hz test fixture, whose
true delays are known, it lands within **0.07 sample (0.018 chip)** of every one of them.

The refinement's objective is quantized: the code replica and the segment cuts both snap to the sample
grid, so a whole neighbourhood of shifts scores the same and the maximum is a plateau. The returned
value is the plateau member nearest the parabolic estimate; until this was fixed it was the *first*
grid point of the plateau, which threw the sub-sample estimate away and sat up to **0.97 sample
(0.24 chip)** from the truth — precision printed to three decimals while being off by a quarter chip.

## 6. Step 3 — Doppler to a fraction of a hertz

The grid only locates the peak to roughly `1/(recording length)` divided by the peak SNR. The
carrier phase of one prompt per code period drifts linearly at the residual frequency, and fitting that
line across 8 periods multiplies the lever arm by 8:

```text
phase slope (rad/s) = weighted least squares over prompts
f_refined = f_grid + slope / (2*pi)
uncertainty = max(thermal Cramer-Rao bound, scatter of the fit residuals)
```

The residual-scatter term is what catches multi-access interference: the other satellites' codes and
this code's own flipped chips do not average away like thermal noise.

**One subtlety that cost a real bug.** A navigation data bit lasts 20 ms, so a short record holds at
most one change, and it inverts the prompt sign from that period on. A straight line through that step
returns a frequency 95 Hz wrong *while reporting ±1.4 Hz*. Worse, a π step and a frequency offset of
about `1/(2 * half-record)` are indistinguishable to a correlation peak. The fix is a matched-filter
choice: take the per-period sign pattern whose de-rotated prompts add up to the largest coherent sum,
with the all-positive pattern always a candidate. The same pattern is then removed from the correlation
and from the chip average.

## 7. Step 4 — remove the other satellites

Every detected satellite is a known waveform times one complex amplitude. Because the signals add, the
amplitude is a single projection:

```text
u_s[n] = code_s[n] * exp(j*2*pi*f_s*t_n) * bit_s[n]        (unit amplitude, aligned)
a_s    = (1/N) * sum conj(u_s[n]) * x[n]
clean_s[n] = x[n] - sum over o != s of a_o * u_o[n]
```

The unit waveforms are close to orthogonal over the record, so one projection per satellite is within a
fraction of a percent of the joint least-squares fit. Cancellation matters because the chips of one PRN
sit at a per-chip SNR of 1.57, and another code's cross-correlation would otherwise set the floor.

## 8. Step 5 — read one soft value per chip

A chip reappears at the same place in every code period, so its occurrences average coherently. The chip
index of a sample follows from the measured code phase:

```text
chip of sample n = floor((n - shift_samples) / 4) mod 1023
value of chip k  = mean over 8 periods and the chip's centre samples of  x * conj(carrier) * code
```

The output is 1023 complex numbers per satellite. `chips.align` rotates out the residual carrier phase;
a sign that disagrees with the nominal code is a modified chip.

**Why the chip average needs the 12-fold combining.** At 55 dB-Hz and 4 samples/chip:

```text
per-sample amplitude a = 0.278, complex noise power 1.0
one chip value = mean of 8 periods * 4 samples = 32 samples
noise on it = 1/sqrt(32) = 0.177
per-chip SNR = 0.278 / 0.177 = 1.57
```

1.57 is not enough to decide a chip reliably, which is exactly why the assignment's common structure is
the key and not a detail.

**Control.** The same processing with a code that is not in the recording must produce noise. It does,
and `analysis/chip_extraction.py` prints the comparison: measured spread against the predicted
`sample_noise / sqrt(periods * samples_per_chip)`.

## 9. Step 6 — recover the common rule

The 12 soft vectors are shifted copies of one pattern. Aligning and summing them raises the signal by
12 and the noise by `sqrt(12)`:

```text
consensus[k] = mean over s of  soft_s[k + slope * (s - first)]
```

**Shift search.** The shift is linear in the PRN index, so one integer slope is searched rather than
pairwise registration. Each slope is scored by how sharp its 15 most negative consensus values are.
Measured: slope 2 wins on both recordings.

**How many chips, decided by the data.** For every candidate count `K` and every left-out PRN, build the
pattern from the other 11 and apply it to the 12th. Flipping a chip in a replica changes that PRN's
coherent correlation by exactly minus twice the chip's contribution, so

```text
S = sum of chip contributions            S_mod = S - 2 * sum of the chosen chips' contributions
held-out gain = 10 * log10(|S_mod / S|^2)      averaged over all 12 left-out choices
```

A correct chip raises the held-out correlation; a wrong chip lowers it. The count with the best average
is kept, and zero is a candidate — if no chip is flipped, or nothing is shared, the honest answer is no
rule at all.

Measured on recording 1: 15 chips at +0.244 dB, with 14 at +0.231 and 16 at +0.225, so the peak is
narrow and unambiguous. On recording 2: 14 at +0.235, with 13 at +0.225 and 15 at +0.226 — the count
is decided, and the one position that recording cannot confirm is `987` (see section 11).

## 10. Step 7 — the rule behind the positions

The recovered base pattern is not arbitrary. Take the Fibonacci numbers, accumulate them, and walk
backwards from chip 1020:

| k | Fibonacci | cumulative | chip = (1020 - cumulative) mod 1023 |
| --- | --- | --- | --- |
| 0 | – | 0 | 1020 |
| 1 | 1 | 1 | 1019 |
| 2 | 1 | 2 | 1018 |
| 3 | 2 | 4 | 1016 |
| 4 | 3 | 7 | 1013 |
| 5 | 5 | 12 | 1008 |
| 6 | 8 | 20 | 1000 |
| 7 | 13 | 33 | 987 |
| 8 | 21 | 54 | 966 |
| 9 | 34 | 88 | 932 |
| 10 | 55 | 143 | 877 |
| 11 | 89 | 232 | 788 |
| 12 | 144 | 376 | 644 |
| 13 | 233 | 609 | 411 |
| 14 | 377 | 986 | 34 |

That is the recovered set exactly, and `gnss/rule.py` checks it rather than asserting it: on recording
1 it reports *matches that rule exactly (15/15 positions)*; on recording 2 it reports *13 of 15*
and names `987` and `1008` as positions this recording cannot confirm, adding that an unsupported
position is a sensitivity limit, not a different pattern.

The generator's structure is therefore: a 15-position sparse mask, the mask shifted by two chips per
PRN index. Equivalently, chip `i` of PRN `s` is flipped when
`(i + 2(s-1)) mod 1023` is a backward cumulative Fibonacci sum. The Fibonacci interpretation is an
observation about the recovered positions; it is not proof of the generator's intent, and
`FINDINGS.md` says so.

## 11. Step 8 — prove the recovered codes explain the data

Two measurements, both against the recording itself, so they hold on the real files and not only on
synthetic ones.

**Residual power.** Rebuild every satellite from its recovered modified code, subtract, and compare what
is left with the noise power:

| recording | residual, nominal codes | residual, recovered codes | noise variance |
| --- | --- | --- | --- |
| 1 | 1.0421 | **0.9911** | 1.0511 |
| 2 | 1.0053 | **0.9973** | 1.0065 |

The recovered model leaves noise and nothing else. The nominal model leaves extra power, and that extra
power is exactly the part of the signal the flips were hiding.

**Correlation gain, with a known ceiling.** Fifteen flipped chips change a code at 15 of 1023 places,
so the recovered code correlates with amplitude `(1023 - 2*15)/1023 = 993/1023` of the nominal one:

```text
20 * log10(993/1023) = -0.259 dB      i.e. a ceiling of +0.259 dB of gain over the nominal code
```

Measured gain per satellite: **+0.188 to +0.338 dB, mean +0.249** on recording 1 — every satellite
inside the ceiling band, so no recovered chip is wrong. On recording 2: +0.078 to +0.439, mean +0.255,
ceiling +0.241: a wider spread because that recording is weaker, and it is the honest picture of a
14-position recovery.

## 12. Step 9 — where it stops working

Generated recordings with known truth, one axis at a time (`python benchmark.py`, tables in
`BENCHMARK.md`):

| axis | result |
| --- | --- |
| C/N0 per PRN | exact in 57 of 60 known-truth runs at 47.5 dB-Hz, 30 of 30 at 55; at 45 dB-Hz 73–80% of chips |
| flipped chips per PRN | exact to ~240 of 1023; soft edge above, detection fails from 400 |
| PRNs at 52 dB-Hz | exact from 6; 2–4 PRNs miss 7–13% |
| record length | 4 ms and longer exact; 2 ms misses 13–40% |
| Doppler | exact at 0 Hz, ±2 Hz, ±20 Hz; ±5.5 kHz with the default span; **±6 to ±30 kHz when the span is widened** |
| data bit flipping mid-record | exact, worst Doppler error 3.7 Hz |
| no shared rule / no modification | 0 chips at 0.000 dB — no rule invented |

Three limits are worth understanding rather than just knowing:

1. **Sensitivity.** A chip is decidable only when the consensus clears the noise. 12 PRNs buy
   `sqrt(12)` = 10.8 dB; 4 PRNs buy 6 dB, which is why the count matters.
2. **Density.** Flipping `K` chips leaves `(1023 - 2K)/1023` of the nominal correlation, so acquisition
   itself fades: 0.37 at K=320, 0.02 at K=500. And above ~240 chips the shift score (an extreme-value
   statistic over the 15 most negative values) starts losing to aliases at `1023/3` and `2*1023/3`.
3. **Doppler span.** Not an algorithm limit: the search covers what it is told to cover. Widening to
   ±30 kHz works with unchanged accuracy, at the cost of search time and `log2` of the cell count in
   detection threshold.

## 13. Run it

```text
python solve.py                              # both recordings in data/, full report
python solve.py data/gnss_observation.nc      # one
python solve.py data/gnss_observation.nc --satellites 1-12    # faster, known constellation
python benchmark.py                          # regenerate BENCHMARK.md
python -m pytest                             # 134 tests, 96% coverage of gnss/
```

`data/` holds the recordings and every artifact produced from them:
`<name>_acquisition.csv` (parameters per PRN), `<name>_joint_flips.csv` (the answer, one row per flipped
chip), `<name>_solution.json` (the same answer plus the pattern check and the evidence). Generated test
fixtures live in `data/tests/` and benchmark recordings in `data/benchmark/`.

## 14. Module map

| module | responsibility |
| --- | --- |
| `gnss/lattice.py` | sampling grid from the recording's metadata |
| `gnss/acquisition.py` | search grid, correlation, detection threshold, phased Doppler |
| `gnss/alignment.py` | code phase, code-period segments, data-bit sign pattern |
| `gnss/signals.py` | replicas, carriers, cancellation algebra |
| `gnss/chips.py` | per-chip soft values |
| `gnss/rule.py` | slope search, held-out flip count, Fibonacci structure |
| `gnss/verification.py` | residual power and correlation gain |
| `gnss/pipeline.py` | the chain as one call; warnings when the evidence is thin |
| `gnss/tables.py` | CSV and JSON artifacts |
| `analysis/` | one quantitative question per script, measured and printed |
| `benchmark.py` | sweeps with known truth, and where the method breaks |

## 15. Claims and their evidence

| claim | evidence |
| --- | --- |
| the satellites are what we say | detection 39.9x over threshold, C/N0 54–55 dB-Hz matches the file's own attribute |
| the Doppler is right | phase-slope uncertainty 1.4–2.0 Hz, consistent with the residual scatter |
| the chips are read in the right coordinates | synthetic known-answer tests recover injected flips exactly, including at non-integer-sample delays |
| the pattern is shared, not per-PRN noise | held-out gain: fitted on 11 PRNs, improves the 12th by +0.19 to +0.34 dB |
| the recovered codes explain the recording | residual falls to the noise variance; per-PRN gain reaches the theoretical ceiling |
| the rule is Fibonacci, not a curve fit | the 15 recovered positions equal the cumulative-Fibonacci set exactly, verified in code |
| the count is not assumed | chosen by held-out correlation; recording 2 returns 13 with 14 inside the noise, and says so |

Where the evidence is weak, the output says so: a low PRN count raises a warning, an unsupported rule
position is listed rather than emitted, and a weak held-out gain returns a pattern of length zero.
