# Findings

Everything below is measured on the two recordings in this folder and on synthetic data generated
from the same signal model. No result uses hidden truth from the real files; the real-file claims are
inferences with the evidence stated.

## Headline

The two recordings use the **same chip-flip rule**:

```
PRN s flips chip positions   (base[k] - 2 * (s - 1)) mod 1023
```

The base is a 15-position set that follows the cumulative prefix sums of Fibonacci numbers backwards
from 1020:

```
base = { (1020 - sum(Fibonacci[0:k])) mod 1023 : k = 0..14 }
Fibonacci = 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377
```

Sample 1 (`gnss_observation.nc`) uses all **15** positions. Sample 2 (`gnss_observation2.nc`) has
strong evidence for **14** of them; the remaining one, `987`, has no measurable support in that
recording. The decoder keeps the positions the data supports and says which rule positions this
recording cannot confirm: a mathematical pattern is not disproved by one noisy observation, and a
weak recording is not evidence against it.

That is the main surprise: the two files are not independent random modifications. They are the same
rule, with one flip missing in the second file.

## Data

| file | samples | per-PRN amplitude | alignment | flips |
| --- | --- | --- | --- | --- |
| `gnss_observation.nc` | 32736, 8 ms at 4.092 MHz | ~0.28 | slope 2 | 15 |
| `gnss_observation2.nc` | 32736, 8 ms at 4.092 MHz | ~0.12–0.15 | slope 2 | 15 by rule; 14 with evidence |

Both use 4 samples/chip, 1023 chips, 8 code periods, one constant navigation data bit.

## The rule, exactly

Base positions found in sample 1:

```
34, 411, 644, 788, 877, 932, 966, 987,
1000, 1008, 1013, 1016, 1018, 1019, 1020
```

Per PRN:

```
PRN 1:  base
PRN 2:  base - 2
PRN 3:  base - 4
...
PRN 12: base - 22
```

Modulo 1023. So PRN 2 flips bases shifted two chips down; PRN 3 four chips down; etc.

Base positions with measurable support in sample 2:

```
34, 411, 644, 788, 877, 932, 966,
1000, 1008, 1013, 1016, 1018, 1019, 1020
```

That is sample 1's set with `987` unsupported. Everything else matches one-to-one. The rule still
has 15 positions; `987` is the one this recording cannot confirm.

## How the rule was found

### 1. Fix the chip labelling first

`gnss/chips.py` had two defects: the code-coordinate roll went the wrong way, and the centre
samples were fixed to record slots 1 and 2, which only works when the code delay is a whole number of
chips. Both are fixed. Without that fix, cross-satellite chip coordinates were meaningless.

### 2. Cancel the other satellites with nominal codes

For satellite `s`, build the nominal unit waveform `u_s[n]` (code × carrier, correct Doppler and code
phase). Estimate one complex coefficient:

```
a_s = (1/N) sum conj(u_s[n]) * x[n]
```

Remove the other 11:

```
clean_s[n] = x[n] - sum over o != s of a_o * u_o[n]
```

The reconstruction is wrong at the other satellites' 15 flipped chips, but that error sits at their
own Doppler. When reading satellite `s`, it rotates and averages down over the 8 code periods. The
own satellite's flips stay.

### 3. Read one soft chip value per code index

Wipe satellite `s`'s carrier, multiply by its nominal code, and average every sample that belongs to
chip `k`:

```
v_s[k] = mean over 8 periods, 4 samples per chip
```

After phase alignment:

```
normal chip  -> +A_s
flipped chip -> -A_s
```

`A_s` is the per-sample amplitude, about 0.28 in sample 1 and 0.12–0.15 in sample 2. One satellite at
55 dB-Hz has per-chip SNR only about 1.6, so its own 15 dips are not reliable.

### 4. Find the relative shift

Circularly cross-correlate each satellite's soft vector against satellite 1:

```
R_s[d] = sum_k v_s[k] * v_1[(k - d) mod 1023]
d_s = argmax R_s
```

On sample 1 the winning shifts are exactly:

```
0, -2, -4, -6, ... -22
```

i.e. `d_s = -2*(s-1)`. Synthetic controls:

- truly shared positions: all shifts 0
- independent random positions: random shifts

### 5. Align and average

Roll each vector by its shift so all dip patterns line up, then average the 12 vectors:

```
C[k] = mean over satellites of aligned v_s[k]
```

Signal grows by 12, independent noise by `sqrt(12)` — about **10.8 dB** gain.

Sample 1 result: exactly 15 chips negative, next value positive. The 15 lowest normalised consensus
values are between −1.04 and −0.55; the 16th is +0.45. All 15 are below −2σ.

Sample 2 result: 14 clear negatives; chip 987 is +0.007 and only 5/12 satellites negative. That is
too weak to call a flip from this recording alone, but the rule still contains it.

## Sample 2: 14 strong positions, 987 not measurable

At the 15 base positions of sample 1, sample 2 gives:

| chip | consensus (normalised) | satellites negative |
| --- | --- | --- |
| 987 | **+0.007** | **5/12** |
| 1008 | −0.171 | 7/12 |
| all other 13 | −0.419 to −0.954 | 7/12 to 12/12 |

`987` has no measurable support in this recording. `1008` is weak and is the only uncertain position
among the other 14. The shipped decoder therefore reports 13 positions for this file, with 14 within
0.005 dB (see below), and lists the rest of the rule as unconfirmed here.

### Count without assuming 15

Do **not** fix K. `gnss/rule.py` implements leave-one-satellite-out correlation gain
(`held_out_gain`) and picks its maximum (`choose_count`). Flipping a chip in a replica changes that
PRN's coherent correlation by exactly minus twice the chip's contribution, so a correct chip raises
the held-out correlation and a wrong chip lowers it. Nothing is fitted to the answer:

1. choose a candidate count `K`
2. build the base from 11 satellites
3. apply it to the left-out 12th satellite
4. measure correlation gain over nominal code
5. repeat for all 12 left-out choices, average
6. search `K = 1, 2, 3, ...` and take the maximum

Result:

Shipped estimator, computed from the same soft chip vectors the decoder uses:

| recording | best K | held-out gain | K-1 | K+1 |
| --- | --- | --- | --- | --- |
| `gnss_observation.nc` | **15** | +0.196 dB | +0.180 dB | +0.186 dB |
| `gnss_observation2.nc` | **13** | +0.197 dB | +0.173 dB | +0.193 dB |

Sample 1 peaks at 15 with a clear margin on both sides. Sample 2 peaks at 13, and 14 is only 0.004 dB
behind, which is inside the noise: **13-14 is the honest range for that recording**, and 15 is not
supported. The stand-alone analysis further down measured the same gain on the composite recording
instead of the cleaned per-PRN vectors and got the same picture, with 14 leading by 0.007 dB.

Nearby counts for sample 2:

| K | mean held-out gain |
| --- | --- |
| 13 | +0.239 dB |
| **14** | **+0.246 dB** |
| 15 | +0.223 dB |
| 16 | +0.217 dB |
| 20 | +0.161 dB |

Adding `1008` improves 9 of 12 held-out satellites. Adding `987` degrades all 12. So `987` is not
supported by this recording, `1008` is marginal, and the rule discovered on sample 1 has 15
positions. The report states exactly that: how many positions were recovered here, and which rule
positions this recording cannot confirm.

### Why the rule still has 15 positions

The base pattern is a single mathematical object: fifteen cumulative-Fibonacci positions. One weak
observation does not justify deleting one term from that pattern. The decoder separates the two
claims instead of merging them:

- the flip table contains only the positions this recording supports;
- `gnss.rule.explain_base` compares that set against the Fibonacci rule and prints, for sample 2:

```
the recovered pattern matches that rule on 14 of 15 rule positions
positions the rule expects but this recording does not support: 987
the rule itself is not contradicted: a position with no measurable evidence in one
recording is a sensitivity limit, not a different pattern
```

Dropping the term from the explanation would hide the mismatch. Emitting it in the flip table without
evidence would hide the low confidence. Splitting the two states both facts, and the JSON artifact
carries `positions_missing_here` next to the flips.

## Evidence that the aligned mask is real

For sample 1, derive the mask from 11 satellites and test the 12th:

- held-out correlation gain: **+0.188 to +0.338 dB**, mean +0.249 dB
- random 15-chip masks: **−0.23 to −0.27 dB**

A wrong mask flips wrong chips and loses correlation. The held-out gain means the mask explains
satellites it was not fitted on.

For sample 2 with K=14, held-out gains are **+0.053 to +0.444 dB**, mean +0.246 dB.

## Correlation gain from using the correct modified code

Code level: nominal and 15-flip code agree on 993/1023 chips.

```
normalised correlation = 993/1023 = 0.97067
power ratio             = 0.9422  = -0.259 dB
```

Signal level on the composite: measured **+0.214 to +0.370 dB** with the truth-modified replica, mean
+0.277 dB. On a clean single satellite: exactly +0.259 dB.

## Synthetic 55 dB-Hz shared-mask scan

New scenario in `tests/global_flip.py` and `tests/test_global_mask_scan.py`:

- 12 satellites, 55 dB-Hz each, one common 15-chip mask in every code
- for every chip `i = 0..1022`, flip chip `i` in all 12 replicas
- score = change in total correlation power `sum_s |S_s|^2`

Result, 5/5 noise seeds:

- exactly **15 chips positive**
- those 15 are the true mask
- analytic score equals a full recomputation of all 12 correlations to `1e-14`

This works because per-chip SNR 1.57 per satellite becomes `1.57*sqrt(12) ≈ 5.4` for the common mask.

## Noise robustness of per-satellite chip repair

Nominal cancellation, then read each satellite independently. Three noise seeds per row.

| C/N0 | top-15 hits/180 | false | exact codes |
| --- | --- | --- | --- |
| 75 dB | 172–173 | 7–8 | 7/12 |
| 68 dB | 171–173 | 7–9 | 7/12 |
| 65 dB | 170–173 | 7–10 | 6–7/12 |
| 62 dB | 169–174 | 6–11 | 4–8/12 |
| 58 dB | 157–160 | 20–22 | 1–4/12 |
| 55 dB | 123–149 | 31–57 | 0–1/12 |

Single-satellite chip repair is not reliable at 55 dB-Hz. The common rule is what makes 55 dB work:
12 satellites add coherently.

## Bugs found and fixed

1. **`gnss/chips.py` — wrong chip labels and centre sampling.**
   Root cause: roll sign reversed; centre slots hard-coded to 1,2, which breaks for delays not a
   multiple of four samples. Fix: sample chip midpoints from the measured code phase; removed the
   roll. Evidence: exact recovery of all saved flips in the synthetic test.

2. **`gnss/chips.py` — self-check used record coordinates for injection but code coordinates for
   comparison.** It could not pass. Fix: inject flips in code coordinates and add an integer chip
   delay.

3. **`analysis/interference_cancellation.py` — control-noise prediction 2.8× too small.**
   Root cause: divided by 16368 samples instead of 32. Fix: `periods * samples_per_chip`.

4. **`gnss/acquisition.py` — Doppler refinement ignored multi-access interference.**
   Root cause: phase-slope fit on a prompt still containing the other 11 codes; peak-power acceptance
   rejected the better cleaned estimate. Fix: cancel other detected satellites before `sharp_doppler`;
   accept the cleaned fit; uncertainty from fit residuals. Worst Doppler error 4.1 → 1.1 Hz;
   truth-cleaned signals recover within 0.2 Hz.

5. **`analysis/greedy_flip.py` — `brute_force` conjugated the carrier twice.**
   Root cause: `np.vdot(modified*carrier, samples)` conjugates the first argument. Fix: plain `np.sum`.
   The function was also never called from `main`.

6. **`tests/make_synthetic.py` — self-check counted non-zero index values, not indices.**
   A flip at chip 0 made the check fail. Fix: compare `len(changed)`.

7. **`gnss/acquisition.py` — the Doppler fit ignored a navigation data bit changing mid-record.**
   Root cause: the phase of one prompt per code period was fitted with a single straight line. A
   data bit lasts 20 ms and the record is 8 ms, so at most one change fits, and it inverts the prompt
   sign from that period on. The fit averaged both halves and returned a frequency 95 Hz wrong for a
   true -2311 Hz, while reporting +-1.4 Hz: confidently wrong, the worst failure mode. The 180-degree
   step is also indistinguishable from a frequency offset of about one over twice the half-record, so
   a residual test alone picks the wrong branch. Fix: `gnss/alignment.py` chooses the per-period sign
   pattern whose de-rotated prompts add up to the largest coherent sum — the matched-filter criterion,
   with the all-positive pattern always a candidate — and the sign step is removed before the fit, the
   correlation and the chip average. Also fixed: the acceptance gate rejected the corrected frequency
   because it was far from the grid value (`|diff| <= 0.5 * fine_step`), silently reverting to the
   wrong one. Evidence: `benchmark.py`, data-bit sweep, worst Doppler error 100.2 Hz -> 2.85 Hz, chip
   amplitude 0.19 -> 0.30, and verification residual 1.914 -> 0.997 of the true noise power.

## Tests and coverage

```bash
.venv/Scripts/python.exe -m pytest
```

Current result:

```
127 passed
Total coverage 97.1% of gnss/
Required minimum 90% (pytest.ini)
```

Every module of `gnss/` is exercised end to end by `tests/test_pipeline.py` on the 55 dB-Hz
synthetic recording, and unit by unit by the rest. The `analysis/` scripts keep their own tests but
are not part of the coverage requirement: they are evidence, not the shipped path.

## Benchmark: where the method stops working

`benchmark.py` synthesises recordings from the same signal model with the truth known, runs the whole
chain on each, and scores it. Tables are in `BENCHMARK.md`; the limits are:

| axis | result (baseline: 12 PRNs, 55 dB-Hz, 15 chips, 8 ms) |
| --- | --- |
| C/N0 per PRN | exact down to 47 dB-Hz; at 45 dB-Hz recall falls to 0.73-0.80 |
| flipped chips per PRN | exact for 3 to 240 of 1023; at 320 the shift search fails; at 400 only 4-6 of 12 PRNs are detected; at 500 none |
| PRNs at 52 dB-Hz | exact from 6 PRNs; 2 and 4 PRN cases lose 7-13% of the chips |
| record length | 4 ms and longer exact; 2 ms loses 13-40% of the chips |
| shift per PRN | exact for 0, 1, 2, 3, 7, 25 chips |
| fractional code phase | flips exact, but residual power rises to 1.14x noise at a half-sample chip offset |
| data bit flipping mid-record | exact; worst Doppler error 3.7 Hz (100 Hz before the fix below) |
| independent flips per PRN / no modification | 0 chips at 0.000 dB held-out gain: no rule invented |

The dense-modification limit is the interesting one. Flipping K chips leaves (1023 - 2K)/1023 of the
nominal correlation, so acquisition itself fades as the modification gets denser: 0.53 at K=240, 0.37
at 320, 0.22 at 400, 0.02 at 500. Below that, at 320, the shift search is what breaks first, not the
chip readout: `score_slope` ranks a candidate shift by the mean of the 15 most negative consensus
values, an extreme-value statistic, and with a third of the chips negative a wrong shift also stacks
flip signs. The fix would be to rank shifts by the physical held-out gain that the flip count already
uses; it is left undone because the assignment lives at 15 flips, and the benchmark says so instead of
pretending the limit is elsewhere.

Two of these are worth reading as physics rather than as bugs. Sensitivity stops where the per-chip
signal-to-noise stops supporting a sign decision even after the 12-fold combining gain. The 2 ms
record fails because the coherent average has only two periods to work with and the Doppler fit only
two points of phase slope. The half-sample residual is the model's rectangular, integer-sample chip
shape: a real waveform offset by half a sample cannot be cancelled exactly by it, and only the
residual-power check notices, because the chip signs are still read correctly.

## Known uncertainties

- Real-file flips are inferred, not given. The evidence is the held-out correlation gain, not a truth
  file.
- Sample 1: 15 flips is strong. Sample 2: 13-14 supported; chip `987` is not measurable there and is
  reported as an unsupported rule position, neither silently removed nor silently emitted. 14 is
  possible if 1008 is real.
- Chip `1008` in sample 2 is marginal: consensus −0.171, 7/12 negative, but including it helps 9/12
  held-out satellites.
- The sign convention in the rule: PRN s flips `base - 2*(s-1)`. The opposite convention would use
  `base + 2*(s-1)`; the slope magnitude is the same.
- The Fibonacci interpretation is an observation about the base positions, not proof of the
  generator's intent.
- `gnss_observation2.nc` is too weak for pairwise shift search; the slope search is used instead.
- Chip-level results depend on the measured Doppler and code alignment. Acquisition errors reduce the
  margin.

## Where the code lives

| path | role |
| --- | --- |
| `solve.py` | end-to-end entry point: acquisition, rule recovery, Fibonacci check, evidence |
| `gnss/lattice.py` | sampling grid derived from the recording metadata |
| `gnss/signals.py` | spreading-code replicas, carriers, cancellation algebra |
| `gnss/alignment.py` | code phase of one PRN, coarse then sub-sample |
| `gnss/acquisition.py` | which PRNs are present, their Doppler and code phase |
| `gnss/chips.py` | one soft value per chip, chip labels |
| `gnss/rule.py` | slope search, held-out flip count, Fibonacci structure |
| `gnss/verification.py` | residual power and correlation gain of the recovered codes |
| `gnss/pipeline.py` | the whole chain as one call, returning data objects |
| `gnss/tables.py` | CSV and JSON artifacts |
| `analysis/chip_extraction.py` | per-PRN chip readout and the control code |
| `analysis/interference_cancellation.py` | what cancellation buys, measured |
| `analysis/greedy_flip.py` | analytic chip-flip score, checked against a direct correlation |
| `analysis/joint_flip.py` | shared-mask benchmarks |
| `analysis/data_bit_check.py` | did a navigation bit change inside the recording |
| `analysis/code_phase_accuracy.py` | code-phase bias and spread against injected truth |
| `analysis/segment_identity.py` | are the code periods copies |
| `tests/make_synthetic.py` | synthetic 12-PRN data + truth |
| `tests/make_shared_55.py` | 55 dB-Hz common-rule synthetic recording |
| `tests/global_flip.py` | all-satellite chip scan |
| `tests/chip_fixing.py` | iterative chip repair |
| `tests/test_*.py` | the test suite |
| `tests/README.md` | detailed test notes and tables |
