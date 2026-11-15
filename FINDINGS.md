# Findings

Everything below is measured on the two recordings in this folder and on synthetic data generated
from the same signal model. The real-file claims are inferences with the evidence stated; the only
truth taken from the files is what they declare about themselves in their attributes, quoted in the
first section below.

## Headline

The two recordings use the **same chip-flip rule**:

`prn_index` starts at 1.

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

Sample 1 (`data/gnss_observation.nc`) uses all **15** positions. Sample 2 (`data/gnss_observation2.nc`) has
strong evidence for **14** of them and weak positive evidence for the fifteenth, `987` (Bayes factor
36, a third of the per-chip error bar). The decoder keeps the positions the data supports and says which rule
position this recording cannot confirm: a mathematical pattern is not disproved by one noisy
observation, and a weak recording is not evidence against it.

## What the recordings say about themselves

`python -m analysis.dump_attrs` writes every attribute to JSON; the signal model is stated in the file.

| attribute | recording 1 | recording 2 |
| --- | --- | --- |
| `description` | "12 synthetic GPS L1 C/A signals, 8 ms, **15 recurrent flips per PRN**, complex AWGN" | "One continuous complex baseband recording containing a superposition of GPS L1 C/A signals. Complex samples are i + 1j*q." |
| `signal_model` | "Constant nav bit, rectangular chips, constant carrier phase/Doppler, **integer-sample delay**, independent CN(0,N0*Fs) noise" | "ideal rectangular-chip spreading, constant navigation symbol, stable carrier Doppler with coherent code Doppler, additive white Gaussian noise" |
| `random_seed` | 20261111 | absent |
| `target_cn0_dbhz_per_prn` | 55.0 | absent |
| `noise_complex_variance` | 1.0 | absent |
| `per_prn_signal_power` | 0.077280, i.e. amplitude 0.2780 | absent |
| `synthetic_truth` | "Prior inferred modification positions from original, not externally verified truth" | absent |

Three things follow, and they are the file's own statements rather than my inferences:

1. **Recording 1 declares an integer-sample delay.** That is a testable prediction about the code
   phase, which must then be a whole number of samples. Measured: mean distance to a whole sample is
   **0.049** now, and was **0.247** before the sub-sample refinement was fixed — the fix moved the
   estimates onto the grid the file declares, without being told to. Recording 2 makes no such claim,
   and its own fit is noisier (0.093), which is consistent with it being 8.5 dB weaker.
2. **Recording 1 declares 15 flips per PRN.** That corroborates the recovered count independently of
   the estimator, and it is why `987` is reported as unsupported rather than absent: recording 1's own
   `description` says every PRN carries fifteen. Recording 2 declares no flip count.
3. **The declared model is matched, not fitted.** Declared amplitude 0.2780; measured with the other
   satellites removed it is **0.2784**, a ratio of 1.001. (Projecting one satellite against the
   *uncleaned* composite reads 0.267, 4% low, because the other eleven codes are not perfectly
   orthogonal — that is a measurement bias, not a model error.) Declared noise power 1.0; the seeded
   noise also measures 1.0, and the 0.054 left over by a nominal-code model is the 180 flipped chips,
   not noise, on this noise-free reconstruction. On the shipped noisy recording the same model leaves
   `residual_gain_db` 0.218 dB (recording 1) and 0.035 dB (recording 2), which is why the residual
   check alone cannot see the flips in recording 2 — see "Double-checking the answer against the
   file's own seed" below.

Recording 1 also states that its `synthetic_truth` is a **prior inference, not verified truth**, which
is why this report never treats it as ground truth.

## Double-checking the answer against the file's own seed

This section is not part of the solution. It is a **verification step to run after a solution exists**,
and it is the strongest end-to-end check in this report because it needs nothing but the file: no
truth list, no benchmark, no assumption about which chips are flipped.

Recording 1 declares `random_seed = 20261111`, and its noise is "independent CN(0,N0*Fs)". If a
standard generator produced that noise, the noise is a deterministic function of the integer, so it
can be reconstructed and subtracted. What is left is the signal with no noise at all — and then any
candidate answer can be tested against the recording at effectively infinite signal-to-noise instead
of at 5.4 dB.

### The check, in four steps

```text
1. noise  = (rng.standard_normal(N) + 1j*rng.standard_normal(N))/sqrt(2), rng = default_rng(20261111)
2. signal = recording - noise                     # now noise-free
3. build the 12-satellite model twice: with the nominal code, and with the candidate flipped code
4. compare each model against the recording
```

Step 3 is where the *answer* enters, so the comparison is a hypothesis test, not a derivation: the
seed comes from the file, the flips come from the solution, and the question is whether the solution
turns the residual into nothing. Both models get identical freedom — per-PRN Doppler and integer delay
refined on the noise-free signal, one complex amplitude each — so the only difference between them is
the fifteen chips.

### What a pass looks like

| model of the signal | leftover power | correlation with the recording |
| --- | --- | --- |
| 12 satellites, **nominal** codes | 5.41e-2 | 0.985761 |
| 12 satellites, **recovered 15-flip codes** | **9.32e-4** | **0.999768** |

- The recovered codes reproduce the file to **0.05% of its power**, correlation **0.9998**.
- The change from nominal is **+0.0140** in correlation and a **58-fold** drop in leftover power
  (−17.6 dB).
- Refining the nominal model's own delay per PRN does not close that gap: it stays at 5.41e-2, so
  the improvement is not extra fitting.
- The two model signals differ only on the 180 flipped chips and correlate with each other at
  **0.97048**, against the analytic `(1023 - 30)/1023 = 0.970674`. The size of the effect matches the
  claim it is testing — that is what makes this a check rather than a fit.
- On the noise-free signal the chip readout returns **exactly the fifteen rule positions for all
  twelve PRNs**, worst chip deviation 0.095 of the amplitude, and the per-PRN amplitude is
  0.2774-0.2780 against the declared 0.2780.

Run it with `python -m analysis.seed_recovery`; it scans for the noise in the seeded stream (offset 0,
`I` then `Q`, scale `1/sqrt(2)`), prints both models side by side, and ends with the chip check. A
correlation near 0.9998 is a pass; near 0.9858 means the flipped chips are missing from the model.

### What it cannot do

- **Only recording 1.** Recording 2 declares no seed, so this check cannot run on it. That is why the
  cross-recording transfer and the held-out `987` analysis carry the argument there.
- **It confirms the signal model, not the rule.** It shows the recovered *positions* explain this file.
  That the positions follow a Fibonacci rule, and that recording 2 shares it, are separate claims with
  separate evidence (`analysis/correctness.py`).
- **The parameter draws are not recovered.** The delays are a designed lattice — sorted, their
  circular gaps are 312-367 samples around 4092/12 = 341, and twelve uniform integers would give
  exponential gaps with all twelve landing within 30 samples of 341 at a probability of about 1e-13.
  The seeded generator supplied the noise, not the geometry. So the check recovers the file, not the
  script that wrote it.

### One false lead, recorded

The 5.4% leftover of the nominal model first looked like a second, chip-rate noise term: its
autocorrelation at lags 1-4 is 0.748, 0.496, 0.243, 0.007, exactly what white noise sampled at the chip
rate and held four samples gives. It was the 180 flipped chips, each four samples wide, which the
nominal replica cannot cancel: `180 * (2*0.278)^2 * 32 / 32736 = 0.0544` predicted against 0.05415
measured. The lesson is worth keeping: a residual with the right *statistics* for noise was the answer
itself, and only modelling the modified code revealed it.

That is the main surprise: the two files are not independent random modifications. They are the same
rule, with one flip not measurable in the second file.

## Data

| file | samples | per-PRN amplitude | alignment | flips |
| --- | --- | --- | --- | --- |
| `data/gnss_observation.nc` | 32736, 8 ms at 4.092 MHz | ~0.28 | slope 2 | 15 |
| `data/gnss_observation2.nc` | 32736, 8 ms at 4.092 MHz | ~0.12–0.15 | slope 2 | 15 by rule; 14 with evidence |

Both use 4 samples/chip, 1023 chips, 8 code periods, one constant navigation data bit.

## The rule, exactly

Base positions found in sample 1:

```text
34, 411, 644, 788, 877, 932, 966, 987,
1000, 1008, 1013, 1016, 1018, 1019, 1020
```

Per PRN:

```text
PRN 1:  base
PRN 2:  base - 2
PRN 3:  base - 4
...
PRN 12: base - 22
```

Modulo 1023. So PRN 2 flips bases shifted two chips down; PRN 3 four chips down; etc.

Base positions with measurable support in sample 2:

```text
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

```text
a_s = (1/N) sum conj(u_s[n]) * x[n]
```

Remove the other 11:

```text
clean_s[n] = x[n] - sum over o != s of a_o * u_o[n]
```

The reconstruction is wrong at the other satellites' 15 flipped chips, but that error sits at their
own Doppler. When reading satellite `s`, it rotates and averages down over the 8 code periods. The
own satellite's flips stay.

### 3. Read one soft chip value per code index

Wipe satellite `s`'s carrier, multiply by its nominal code, and average every sample that belongs to
chip `k`:

```text
v_s[k] = mean over 8 periods, 4 samples per chip
```

After phase alignment:

```text
normal chip  -> +A_s
flipped chip -> -A_s
```

`A_s` is the per-sample amplitude, about 0.28 in sample 1 and 0.12–0.15 in sample 2. One satellite at
55 dB-Hz has per-chip SNR only about 1.6, so its own 15 dips are not reliable.

### 4. Find the relative shift

Circularly cross-correlate each satellite's soft vector against satellite 1 (this pairwise route is
shown on recording 1 only: recording 2 is too weak to align pairwise, and the slope search is used
there; see *Known uncertainties*):

```text
R_s[d] = sum_k v_s[k] * v_1[(k - d) mod 1023]
d_s = argmax R_s
```

On sample 1 the winning shifts are exactly:

```text
0, -2, -4, -6, ... -22
```

i.e. `d_s = -2*(s-1)`. Synthetic controls:

- truly shared positions: all shifts 0
- independent random positions: random shifts

### 5. Align and average

Roll each vector by its shift so all dip patterns line up, then average the 12 vectors:

```text
C[k] = mean over satellites of aligned v_s[k]
```

Signal grows by 12, independent noise by `sqrt(12)` — about **10.8 dB** gain.

Sample 1 result: exactly 15 chips negative, next value positive. The 15 lowest normalised consensus
values are between −2.63 and −4.73 sigma; the 16th is **+2.00**. All 15 are the rule's positions.

Sample 2 result: the 15 lowest are **exactly the rule's 15 positions**, but the last of them is barely
negative — chip 987 at −0.42 sigma, with the 16th at +0.05. That is the whole of the 14-versus-15
question: one chip whose measurement is a third of the per-chip error bar.

## Sample 2: 14 strong positions, 987 not measurable

At the 15 base positions of sample 1, sample 2 gives:

| chip | consensus | satellites negative |
| --- | --- | --- |
| 987 | **−0.42σ** | **6/12** |
| 1008 | −0.92σ | 9/12 |
| all other 13 | −1.38 to −3.69σ | 7/12 to 12/12 |

`987` is the one position this recording cannot settle: its best estimate is a third of the per-chip
error bar, and six of twelve PRNs read it negative. `1008` is weak but on the right side. The shipped count
criterion (held-out gain below) stops at 14 and names `987` as the rule position it cannot confirm,
while the likelihood on the rule's own chips prefers 15 over 14 by 36:1 — the difference between
those two criteria is the honest width of the answer here.

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
| `data/gnss_observation.nc` | **15** | +0.244 dB | +0.231 dB (14) | +0.225 dB (16) |
| `data/gnss_observation2.nc` | **14** | +0.235 dB | +0.225 dB (13) | +0.226 dB (15) |

Sample 1 peaks at 15 with a clear margin on both sides. Sample 2 peaks at 14, with 15 only 0.009 dB
behind: the count is decided, and the single position it cannot confirm is `987`.

Nearby counts for sample 2:

| K | mean held-out gain |
| --- | --- |
| 12 | +0.202 dB |
| 13 | +0.225 dB |
| **14** | **+0.235 dB** |
| 15 | +0.226 dB |
| 16 | +0.215 dB |

Adding `1008` to the 13-chip core raises the held-out gain by 0.010 dB. Adding `987` lowers it by
0.009 dB. So this recording puts `1008` in and leaves `987` out, and that is exactly what the flip
table reports: fourteen positions, with `987` named as the rule position it cannot confirm.

### Why the rule still has 15 positions

The base pattern is a single mathematical object: fifteen cumulative-Fibonacci positions. One weak
observation does not justify deleting one term from that pattern. The decoder separates the two
claims instead of merging them:

- the flip table contains only the positions this recording supports;
- `gnss.rule.explain_base` compares that set against the Fibonacci rule and prints, for sample 2:

```text
the recovered pattern matches that rule on 14 of 15 rule positions
positions the rule expects but this recording does not support: 987
the rule itself is not contradicted: a position with no measurable evidence in one
recording is a sensitivity limit, not a different pattern
```

Dropping the term from the explanation would hide the mismatch. Emitting it in the flip table without
evidence would hide the low confidence. Splitting the two states both facts, and the JSON artifact
carries `positions_missing_here` next to the flips.

### Is the `987` deficit a defect or the noise floor?

`python -m analysis.chip_anomaly` perturbs every input the readout of one chip depends on, on the real
file. Sample 2, chip `987`, reading in units of the local amplitude where a clean flip reads +1:

| input perturbed | reading |
| --- | --- |
| as fitted | +0.14 ± 0.31 |
| code phase −0.25 / +0.25 sample | +0.14 ± 0.31 / +0.18 ± 0.37 |
| code phase −1.00 / +1.00 sample | −0.04 ± 0.28 / +0.27 ± 0.25 |
| Doppler −5 / +5 Hz | +0.16 ± 0.32 / +0.12 ± 0.31 |
| periods 0-3 | −0.09 ± 0.38 |
| periods 4-7 | +0.36 ± 0.26 |

Nothing moves it: the file is clean (no NaN, power flat to 3% across periods, no segment defect), no
PRN carries a spurious navigation-bit step, the cancellation residual sits at the noise floor, and
the two halves disagree with each other in the way independent noise does — not in the way a stable
attenuation would.

`python -m analysis.weakest_chip` then asks how often a *truly* flipped chip reads this low. A rerun
of 100 synthetic recordings at sample 2's own amplitude (47.5 dB-Hz per PRN) and its Dopplers, through
the real chain: the weakest of the fifteen true chips has median **+0.44**, 5th percentile +0.17,
minimum **+0.10**, and in **0 of 100 trials does a true chip read below +0.04**. Reported counts: 15 in
89 trials, 14 in 2, 16 in 7, 17 in 2. Sample 2's +0.14 at chip `987` is inside that spread, near the
low end.

Those numbers are after the code-phase fix described below. Before it the same experiment, 60 trials at
the same strength, gave a median weakest chip of +0.20, a minimum of −0.27, some chip below +0.04 in
**14 of 60** trials, and the right count in only **28 of 60**. The alignment bug was costing real
signal-to-noise, not just printed decimals: sample 2's own reading at `987` rose from −0.04 to +0.14
and its recovered count from 13 to 14 when the fix landed.

### 13, 14 or 15: fixed-mask likelihood

The ranking-based count search answers "how many chips does a ranking support", which is not the same
question as "is this named chip flipped". The per-chip log-likelihood ratio is tabulated once, further
down in "Second recording: 14 strong flips, 987 weak but kept" (the table with the `reading` column).
In short: sample 2 prefers the full 15-chip set over the 13-chip set by about **4e4:1**, and prefers 15
over 14 by 36:1. The ranking search still reports P(14) = 0.9996, P(15) = 0.0003, because it has to
*rediscover* which 1023 positions are in play and `987` ranks fifteenth there. Both statements are
true and they answer different questions: the count this file can establish on its own is 14, the mask
it fits best among the rule's chips is 15, and the 15-chip rule is not contradicted by any measurement
in the file.

## Evidence that the aligned mask is real

For sample 1, derive the mask from 11 satellites and test the 12th:

- per-PRN amplitude-ratio gain (in-sample: all twelve PRNs fitted at once, so not a held-out number):
  **+0.188 to +0.338 dB**, mean +0.249 dB (`evidence.per_prn_gain_db`)
- chip-domain mask gain, the held-out number: **+0.244 dB** (`rule.held_out_gain_db`) against a
  random-mask null of about -0.3 to -0.2 dB

A wrong mask flips wrong chips and loses correlation. The held-out gain means the mask explains
satellites it was not fitted on.

For sample 2 with K=14, the per-PRN waveform gains are **+0.078 to +0.439 dB**, mean +0.255 dB.

## Correlation gain from using the correct modified code

Code level: nominal and 15-flip code agree on 1008/1023 chips and disagree on 15. The inner product is not that count: each disagreement contributes -1 instead of +1, so 1008 - 15 = 993.

```text
normalised correlation = 993/1023 = 0.97067
power ratio             = 0.9422  = -0.259 dB
```

Signal level on the composite: measured **+0.214 to +0.370 dB** with the truth-modified replica, mean
+0.277 dB (`analysis/explain.py`, a different estimator from the per-PRN fit above; its mean sits
just above the 0.259 dB ceiling because the replica is scored against the same record it was fitted
to). On a clean single satellite: exactly +0.259 dB.

`python -m analysis.explain` puts the whole explanation in one table per recording, with no truth
file: explained power and its correlation with the recording, residual against the noise variance,
the closed-form excess the nominal codes must leave, per-PRN gain against the ceiling, and a
permutation null over random chip masks.

## Is the recovered mask an artefact of the search?

`python -m analysis.correctness` answers that three ways, all measured on the two supplied files.

**Split-half.** Recover the mask from code periods 0-3 only, score it on periods 4-7, and reverse.
On recording 1 both halves independently return slope 2 and **exactly the same 15 positions**; the
transfer gain is **+0.243 dB** and **+0.245 dB** against a random-mask null of −0.30 to −0.18 dB (a
second draw from the same null experiment as above; the two draws overlap), and
the out-of-sample count is 15 in both directions with 14 and 16 both 0.02 dB behind.
On recording 2 the halves are much weaker (half the periods is 3 dB less): periods 0-3 return 13 chips
and periods 4-7 return 8, with transfer gains of +0.149 and +0.161 dB and out-of-sample counts of 14
and 12. That recording is genuinely close to the edge of what 8 ms supports.

**Evidence per chip.** A Gaussian log-likelihood ratio between "flipped at this satellite's own
amplitude" and "unflipped", summed over the twelve PRNs, gives a Bayes factor per chip. Recording 1:
all fifteen between **1.7e35 and 1.4e63**, each with 11 or 12 of 12 PRNs reading it negative, and the
two Fibonacci positions just outside the set (447, 483) at 1.3e−56 and 3.0e−49 with 0 of 12 negative.
Recording 2, fixed chips: thirteen between **9.2e4 and 7.9e12**, chip `1008` at **1.1e3**, chip `987`
at **36** (weak; 6 of 12 PRNs read it negative).

The ranking search reports a posterior for recording 2 of P(14) = 0.9996, P(15) = 0.0003, but that
answers a different question. It scans all 1023 positions and asks how many chips the file can
establish *without being told which*; the per-chip rows ask whether a *named* chip is flipped. Scored
on the rule's own chips, recording 2 prefers:

| mask | log-likelihood ratio | reading |
| --- | --- | --- |
| 13 chips (rule minus 987, 1008) | +273.7 | baseline |
| 14 chips (+1008) | +280.7 | **1075:1** over 13 |
| 15 chips (+987) | +284.3 | **36:1 for** 15 over 14, **4e4:1** for 15 over 13 |

So the honest reading is: the mask has fifteen positions, recording 1 proves all of them, recording 2
establishes fourteen on its own and mildly prefers the fifteenth.

**Transfer between recordings.** A mask recovered from one file, applied to the other with nothing
fitted on the target, gains **+0.237 dB** (recording 1's 15 chips on recording 2) and **+0.227 dB**
(recording 2's 14 chips on recording 1). Recording 2's entire answer is a subset of recording 1's 15.

## How much of the 14/15 answer is noise? Known-truth comparison

The 14th and 15th positions are the low-confidence ones for a measurable reason: at recording 2's
strength each chip gets only about **3.2 sigma** of combined evidence, where recording 1 gets 5.4.
`python -m analysis.weakest_chip` turns that into a rate by generating recordings with known truth
and running the real chain on them.

| case | strength | truth | weakest true chip (units of amplitude) | count recovered |
| --- | --- | --- | --- | --- |
| recording 1 | 55 dB-Hz | 15 positions | +0.98 (chip 987) | 15 |
| recording 2 | 47.5 dB-Hz | 15 positions assumed | **+0.14** (chip 987) | 14 |
| 100 known-truth trials | 47.5 dB-Hz | 15 | median +0.44, 5th pct +0.17, worst +0.10 | 15 in 89, 14 in 2, 16 in 7, 17 in 2 |
| 1000 known-truth trials | 47.5 dB-Hz | 15 | exact set 839/1000; 75 drop one chip, 9 drop two, 76 add extras, 1 swap | supersedes the 100-trial row above |
| 100 known-truth trials | 55 dB-Hz | 15 | median +0.77, worst +0.61 | 15 in 100 |
| 12-PRN test fixture | 75 dB-Hz | 15 per PRN, independent | greedy test finds 179 of 180, 43 false | no shared rule to recover |

What the table says:

- A truly flipped chip at 47.5 dB-Hz never read below **+0.10** in 100 trials. Recording 2's +0.14 at
  chip `987` is inside that spread, near the low end, and still positive.
- A later exact-set check, 1000 trials at 47.5 dB-Hz, returned the planted 15 chips in 839 trials.
  75 dropped one true chip and added nothing. 9 dropped two. 76 kept all 15 and added extras.
  One reported 15 chips but swapped one. Recording 2's single drop is that 7.5% case, not a rare fluke.
  The trials ran at one level only: 47.5 dB-Hz is near the loud end of recording 2's 44.1–48.0
  dB-Hz range (mean 46.5), so the fainter PRNs in that file are not represented.
- At 55 dB-Hz the weakest true chip never fell below +0.61 and the count was right in 100 of 100, which
  is why recording 1 settles all fifteen positions and recording 2 needs the rule to settle the last
  one.
- The 75 dB-Hz fixture shows the ceiling: with **10x the amplitude per chip** (75 dB-Hz against 55) the
  per-PRN greedy test alone finds 179 of 180 true flips, and the shared rule is not needed to decide
  them.

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

(The 179-of-180, 43-false row above and the 172–173, 7–8 row here are the same fixture scored by two
different selectors: keep every positive analytic score, versus keep only the 15 strongest chips. The
second is the one that matches what the pipeline does.)
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
.venv/Scripts/python.exe -m pytest      # create the venv first: see README, Setup
```

Current result:

```text
181 passed
Total coverage 95.4% of gnss/
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
| C/N0 per PRN | exact in both seeds down to 51 dB-Hz (at 49 and 47 one seed carried one extra chip: precision 0.94, recall 1.00); 95% edge 49.4 dB-Hz over 100 independent signals per point; at 45 dB-Hz 26 of 100 runs recover every chip |
| flipped chips per PRN | exact in both seeds to 160; 95% edge 140 chips; the shift search fails at 320; at 400 only 4-6 of 12 PRNs are detected; at 500 none |
| PRNs at 52 dB-Hz | exact in both seeds from 4 to 30; 95% edge at 7 PRNs; exact recovery stops at 36 PRNs (32 of 100 then 0 of 100); 1 PRN cannot define a shift, 2-3 miss 1-3 chips |
| record length | exact in both seeds from 4 ms; 95% edge 5 code periods (4 ms gives 94 of 100); at 2 ms one chip is lost at most, but the Doppler fit degrades |
| shift per PRN | exact for 0, 1, 2, 3, 7, 25 chips |
| fractional code phase | flips exact, but residual power rises to 1.14x noise at a half-sample chip offset |
| Doppler | exact at 0 Hz, within +-2 Hz and within +-20 Hz; found to about +-5.5 kHz, nothing at +-5.8 kHz |
| data bit flipping mid-record | exact; worst Doppler error 3.7 Hz across the bit sweeps (2.85 Hz in the bit-change sweep alone; 100 Hz before the fix in bug 7 above) |
| data bits changing at random per PRN | exact at 8 and 16 ms; at 2 ms the Doppler fit degrades (371 Hz worst) |
| independent flips per PRN / no modification | 0 chips at 0.000 dB held-out gain: no rule invented |

**How many PRNs.** Below six the combining gain is thin: one PRN cannot define a shift at all
(there is nothing to relate it to, and the recovered pattern is empty), two keep 13-14 of the 15 chips,
and three keeps 14 in one seed and all 15 in the other. Four to thirty recover every chip in both
seeds; over 100 signals per point the 95% edge is seven PRNs, with six at 94 of 100. From forty upwards the
limit is not the flip search but **detection**: 38/40 and 58/60 PRNs found at 40 and 60, 78/80 at 80,
118/120 at 120, 158/160 at 160 and 197-202 out of 210. The cause is multi-access: at 52 dB-Hz a weak
PRN's correlation peak can lose to the cross-correlation spikes of forty others, and the single-pass
cancellation cannot repair it because it is built from those same parameters. The measured consequence
is visible in the residual: 1.07x noise at 40 PRNs, 1.25 at 120, 1.6 at 160 and 3.05-3.09 at 210, so the
consensus weakens and only 4 and 11 of the 15 chips survive at 210 (one seed each). One 40-PRN run also accepted a Doppler
6.6 kHz away from the truth for one PRN, which the verdict survived because the other 39 were clean.
Fixing that needs an iterative cancel-and-reacquire pass; it is not done, because the assignment has 12
PRNs and the honest statement is that the method is built for that regime.

**Data bits that really change.** A navigation bit lasts 20 ms, so a recording of N ms that starts at a
random point in the bit carries one transition with probability N/20. Drawing that per PRN gives 76
transitions across 192 PRN-records in the sweep, and the sign-pattern detector located 188 of those 192
PRN-records correctly. Recovery is exact at 8 ms (the assignment's length, P=0.4) and at 16 ms (P=0.8),
one 4 ms run comes back a chip short, and at 2 ms the Doppler fit suffers: two code periods are too few
to fit a phase slope *and* locate a step, so one run accepted a 371 Hz error while still recovering all
15 chips. The chips survive because the chip average uses the per-period sign pattern, which works from
four periods up.

The Doppler questions are all answered by measurement, and two of the three fears are unfounded.
With every PRN at 0 Hz, or all twelve within +-2 Hz, or within +-20 Hz, recovery is exact: different
spreading codes stay orthogonal at identical Doppler, and cancellation removes what they do not share.
Large Doppler is not an algorithmic limit but a search-span one. The span is +-5175 Hz, derived from
the satellite's line-of-sight speed plus a 200 km/h receiver; the coarse grid covers +-5000 Hz and the
fine search adds +-500 Hz, so signals at +-5150 Hz and even +-5500 Hz are found (12/12) while +-5600 Hz
is 11/12 and +-5800 Hz is 0/12. Beyond the span the method does not fail gracefully, it fails cleanly:
nothing is detected, and `--max-speed-km-h` is the knob that widens the span.

Widening it works. With the span asserted wide enough, offsets of +-6, +-10, +-15, +-20 and +-30 kHz
all come back 12/12 detected, 15/15 chips, shift 2, Doppler error 1.4-3.1 Hz - the same accuracy as
the nominal case. The price is search time (0.2 s to 0.6 s per 12-PRN recording, since the coarse grid
grows with the span) and a slightly higher detection threshold: four times the span costs about one
unit of peak-to-floor ratio, as the false-alarm design predicts. What a wide span means physically is worth
saying: a ground receiver cannot see +-30 kHz of satellite Doppler, so a real recording with that much
offset is showing a receiver clock error or a non-terrestrial platform. The search does not care which;
it only has to be told how far to look.

The dense-modification limit is the interesting one, and it is a soft edge rather than a threshold.
Over 6 seeds per count, passes are 0/6 at 236 chips, 1/6 at 240, 0/6 at 244, 0/6 at 248, 0/6 at 252,
0/6 at 256, 0/6 at 260 and 0/6 at 264: non-monotonic, because which draw wins depends on where the
random base lands, not on K alone. What collapses is the shift margin - 0.002 to 0.030 when the shift
is right, 0.000 to 0.121 when it is wrong, overlapping populations. The wrong answers are 343 and 684, about 1023/3 and
2*1023/3, where PRN rolls coincide, so the true shift of 2 stops being the unique winner. Above that,
detection fades too: flipping K chips leaves (1023 - 2K)/1023 of the nominal correlation, 0.37 at
K=320 and 0.02 at K=500, so a nominal replica barely sees the code. Ranking shifts by the physical
held-out gain that the flip count already uses would push the edge up; it is left undone because the
assignment lives at 15 flips, and the benchmark says so instead of pretending the limit is elsewhere.

Two of these are worth reading as physics rather than as bugs. Sensitivity stops where the per-chip
signal-to-noise stops supporting a sign decision even after the 12-fold combining gain. The 2 ms
record fails because the coherent average has only two periods to work with and the Doppler fit only
two points of phase slope. The half-sample residual is the model's rectangular, integer-sample chip
shape: a real waveform offset by half a sample cannot be cancelled exactly by it, and only the
residual-power check notices, because the chip signs are still read correctly.

## Known uncertainties

- Real-file flips are inferred, not given. The evidence is the held-out correlation gain, not a truth
  file.
- Sample 1: 15 flips is strong — every chip is negative in 11 or 12 of the 12 PRNs, Bayes factors
  1.7e35 to 1.4e63. Sample 2: 14 positions supported and emitted; chip `987` is the one rule position
  it cannot confirm (Bayes factor 36 for flipped, 6 of 12 PRNs negative) and is reported as an
  unsupported rule position, neither silently removed nor silently emitted.
- Chip `1008` in sample 2 is weak but positive: 9 of 12 PRNs negative, Bayes factor 1.1e3, and adding
  it raises the held-out gain by 0.010 dB.
- The sign convention in the rule: PRN s flips `base - 2*(s-1)`. The opposite convention would use
  `base + 2*(s-1)`; the slope magnitude is the same.
- The Fibonacci interpretation is an observation about the base positions, not proof of the
  generator's intent.
- `data/gnss_observation2.nc` is too weak for pairwise shift search; the slope search is used instead.
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
| `analysis/explain.py` | explained power, residual/noise, excess prediction, permutation p-value |
| `analysis/correctness.py` | split-half transfer, per-chip Bayes factors, count posterior, cross-file transfer |
| `analysis/chip_anomaly.py` | one chip's reading under code-phase, Doppler and half-record perturbations |
| `analysis/weakest_chip.py` | Monte Carlo: how low a truly flipped chip reads at a given SNR |
| `analysis/seed_recovery.py` | find a recording's noise in the stream of its declared `random_seed` |
| `analysis/data_bit_check.py` | did a navigation bit change inside the recording |
| `analysis/code_phase_accuracy.py` | code-phase bias and spread against injected truth |
| `analysis/segment_identity.py` | are the code periods copies |
| `tests/make_synthetic.py` | synthetic 12-PRN data + truth |
| `tests/make_shared_55.py` | 55 dB-Hz common-rule synthetic recording |
| `tests/global_flip.py` | all-satellite chip scan |
| `tests/chip_fixing.py` | iterative chip repair |
| `tests/test_*.py` | the test suite |
| `tests/README.md` | detailed test notes and tables |
