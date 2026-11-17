# Synthetic GPS L1 tests

Consolidated findings, including the common rule and the second recording: [`../FINDINGS.md`](../FINDINGS.md).

## What is generated

`tests/make_synthetic.py` builds one recording and two answer-key files:

| file | contents |
| --- | --- |
| `synthetic_l1.nc` | 32736 complex samples, 8 ms at 4.092 MHz (4 samples/chip), 12 satellites |
| `synthetic_l1_truth.csv` | one row per satellite: PRN, Doppler, delay, code-phase chips, carrier phase, amplitude, data bit, C/N0, 15 flipped chips |
| `synthetic_l1_codes.csv` | all 1023 chips of every satellite: nominal, modified, flipped flag |

The generator writes the files into `tests/` itself; the tests do not depend on files being committed.

Deliberate choices:

- **Codes**: PRN 1..12 (twelve different C/A codes).
- **Doppler**: distinct integer values in +-3500 Hz, one per satellite.
- **Code delay**: distinct integer samples in 0..4091, so many delays are NOT a whole number of
  chips. That is what exposed the chip-labelling bug.
- **Modification**: exactly 15 random chip positions per code, saved as truth.
- **Data bit**: one constant `+1` shared by all satellites.
- **Amplitude**: 0.278 per sample, the same per-satellite amplitude as the real 55 dB-Hz files.
- **Noise**: complex variance 0.01 instead of 1.0. That raises C/N0 to 75 dB-Hz while keeping the
  composite signal at real-file amplitude, which makes the 15 chip positions recoverable exactly.
  The reduced noise is only about the sensitivity of the test, not the signal model.

Everything random comes from seed 20261113.

`tests/make_shared_55.py` builds the realistic companion data set:

| file | contents |
| --- | --- |
| `synthetic_shared_55.nc` | 55.0 dB-Hz per PRN, noise variance 1.0, 12 PRNs |
| `synthetic_shared_55_truth.csv` | same parameters plus the common base pattern, the per-PRN shift, and the 15 flips of each PRN |
| `synthetic_shared_55_codes.csv` | nominal and modified chips of every PRN |

The modification follows the rule found in the real recording: one 15-chip base pattern,
`{34, 411, 644, 788, 877, 932, 966, 987, 1000, 1008, 1013, 1016, 1018, 1019, 1020}`, which is
`1020` minus the prefix sums of `1,1,2,3,5,8,13,21,34,55,89,144,233,377` (the Fibonacci numbers in
reverse). PRN `k` uses the base shifted by `2 * (k - 1)` chips.

## Common rule at 55 dB-Hz - the actual solution

At 55 dB-Hz one PRN gives a chip decision signal-to-noise of only about 1.6, so its 15 flips cannot
be read reliably on their own. The assignment's premise is a **common rule**, and that is the lever:
after nominal-code cancellation, the 12 soft vectors align at a slope of **2 chips per PRN**. Summing
the aligned vectors raises the signal by 12 and the independent noise by `sqrt(12)`, a **10.8 dB**
gain. The 15 consensus chips are then separated from the rest by a wide margin.

`gnss/pipeline.py` and `gnss/rule.py` implements this:

1. Cancels the other satellites with their nominal codes.
2. Extracts one soft value per chip for each PRN.
3. Searches the single common slope that makes the aligned sum sharpest.
4. Chooses how many consensus chips to keep by held-out gain (below), then takes that many most
   negative ones as the base pattern.
5. Maps the base back to every PRN with `flip = base - 2*(PRN - 1)`. For these PRNs the result does not wrap, so each PRN still has 15 flips.

Result on `synthetic_shared_55.nc` (55.0 dB-Hz, noise 1.0): **exact 15/15 flips for all 12 PRNs**,
and the recovered modified codes reduce the reconstruction residual to the noise level. The same
script on the real recordings returns the same slope 2 and the same base pattern:

| recording | score | residual with nominal codes | residual with recovered codes |
| --- | --- | --- | --- |
| `data/gnss_observation.nc` | 3.48 | 1.0421 | 0.9911 |
| `data/gnss_observation2.nc` | 2.33 | 1.0052 | 0.9970 |

The earlier note in `docs/notes_chip_extraction.md` that the positions are not shared was measured
with the buggy chip labels described below. With correct labels and the 2-chip alignment, the common
structure is strong and unambiguous.

## Running the tests

```bash
.venv/Scripts/python.exe -m pytest
```

`pytest.ini` enables coverage on every run and fails below 90%:

`gnss/` is covered module by module; `analysis/` scripts keep their own tests but are not part of
the coverage requirement, because they are evidence rather than the shipped path.

## Correlation gain and chip repair

Code level: the truth-modified code and the nominal code agree on 1008 of 1023 chips and
disagree on 15. The inner product counts each disagreement as -1 instead of +1, so
`1008 - 15 = 993`. Their normalised cross-correlation is `993/1023 = 0.97067`, i.e. **2.93% lower**. In power that is
`0.97067^2 = 0.9422`, a **0.259 dB** loss.

Signal level, using the truth-modified replica on the composite recording:

| quantity | measured |
| --- | --- |
| correlation-power gain over nominal replica | +0.214 to +0.370 dB, mean **+0.277 dB** |
| same on a noise-only-plus-one-satellite signal | exactly **+0.259 dB** |

Chip-by-chip repair (`tests/chip_fixing.py`) flips the chips whose current soft value is negative,
then re-reads. Results:

| input | true flips found | false flips | rounds | correlation gain |
| --- | --- | --- | --- | --- |
| truth-exact cancellation | 180/180 | 0 | 1 | +0.25 to +0.26 dB |
| other satellites cancelled with nominal code | 179/180 | 33 (0-10 per satellite) | 1-6 | +0.249 to +0.299 dB |
| raw composite, no cancellation | 164/180 | 737 | 1-6 | can look larger, but it fits interference |

The greedy analytic rule in `analysis/greedy_flip.py` (`score_changes`) flags 15-25 chips per satellite.
Those flags contain **178/180 true flips**, miss **2**, and add **32 false** ones. Keeping only the
15 strongest after nominal cancellation gives **173/180 true and 7 false**.

Conclusion: chip-by-chip repair finds almost all flips once the other satellites are cancelled, but
doing it on the raw composite is misleading - the correlation can rise by fitting another code's
cross-correlation rather than the true flipped signal.

## Bugs found and fixed

### 1. Chip labels and chip-centre sampling were wrong (`gnss/chips.py`)

**Symptom.** The module's own self-check failed: it injected known flips and recovered the same
count shifted by 31 chips. On the generated data every satellite with a delay not divisible by four
was labelled one chip off (e.g. delay 66 samples = 16.5 chips).

**Root cause.** Two mistakes in `chip_vector`:

- The relabelling roll had the wrong sign. Record position `m` holds code chip
  `(m - shift/4) mod 1023`, so the array must be rolled by `-shift/4`, not `+shift/4`.
- The centre samples were hard-coded to slots 1 and 2 of each four-sample cell. That only works
  when the code delay is a whole number of chips (a multiple of four samples). With any other
  integer-sample delay the two "middle" samples straddle a chip boundary.

**Fix.** Chip values are now read at the midpoint of every chip window relative to the measured
code phase (`floor(shift + k*samples_per_chip + j + 0.5)`). The result is already in code
coordinates, so the roll was removed. The self-check now injects flips in code coordinates and
adds a 124-sample (31-chip) integer delay, so it exercises the same path.

**Evidence.** With truth-exact cancellation, all 12 satellites recover exactly the 15 saved flip
positions, and only those.

### 2. Control-noise prediction used 512x too much averaging (`analysis/interference_cancellation.py`)

**Symptom.** The script printed "pure noise would be about 0.0129" while the measured control code
was 0.335. The prediction was 2.8x (in amplitude) too small.

**Root cause.** `periods_samples()` multiplied samples per code period by samples per chip
(4092 x 4 = 16368) instead of multiplying code periods by samples per chip (8 x 4 = 32). One chip
combines 32 samples, not 16368.

**Fix.** Use `periods * samples_per_chip`; the unused helper was deleted. The test now parses the
printed prediction and checks it equals `sqrt(residual_power / 32)`.

### 3. Doppler refinement ignored multi-access interference (`gnss/acquisition.py`)

**Symptom.** On the 12-satellite file, `sharp_doppler` reported uncertainty around 0.4 Hz while the
error against truth was up to 4.1 Hz (about 10 sigma). The estimate was also no better than the fine
grid, because the acceptance test rejected the improved value.

**Root cause.** The phase-slope fit reads one satellite, but its prompt still contains the other 11
satellites' codes. Their cross-correlation does not average away over eight code periods, so it adds
a phase wobble that biases the slope. The acceptance test compared peak powers on that same dirty
signal, where interference jitter is larger than the difference caused by a sub-hertz correction, so
it usually kept the worse grid frequency.

**Fix.** `gps_acquire.main` now reconstructs every detected satellite, subtracts all the others, and
runs the phase-slope fit on the cleaned signal. A detected satellite accepts the cleaned fit when it
stays within half a fine step of the grid value; undetected satellites still use the peak-power
guard. The reported uncertainty is the larger of the thermal Cramer-Rao bound and the measured
fit-residual scatter.

**Evidence.** On a truth-exact cleaned signal the estimator recovers every Doppler within 0.2 Hz.
On the composite file the worst error drops from 4.1 Hz to about 1.1 Hz.

### 4. Direct-correlation check conjugated the carrier twice (`analysis/greedy_flip.py`)

**Symptom.** `brute_force` was meant to verify the analytic score-change shortcut, but it did not
agree with a direct correlation on the aligned synthetic signal.

**Root cause.** It used `np.vdot(modified * carrier, samples)`. `vdot` conjugates its first argument,
which turns the wipe-off carrier `exp(-j2*pi*f*t)` into `exp(+j2*pi*f*t)`; combined with the signal's
own carrier the correlation runs at twice the Doppler. It was also never called from `main`, so the
bad check was invisible.

**Fix.** Use a plain `np.sum(modified * carrier * samples)`, matching `shortcut_check` and
`chip_bits`. The test now compares the shortcut against a real correlation on an aligned synthetic
signal (worst relative difference below 1e-6), and `main` accepts a recording argument so the same
code can run on the synthetic file.

## Deliberately not "fixed"

- **Per-chip signs on the raw composite.** Eleven other codes leak about 0.3 per chip, so one
  satellite's chips cannot be read exactly without cancelling the others. That is still true, and it
  is why the common-rule joint sum is needed. The exact single-PRN chip test uses truth-exact
  cancellation; this matches the limitation recorded in `docs/notes_chip_extraction.md`.
- **Reported C/N0 is 67.6 dB-Hz against a true 75 dB-Hz.** The nominal-code correlation misses the
  15 flipped chips (about 2.9% of amplitude), and that unmodelled power is counted as noise. At the
  real files' 55 dB-Hz / noise 1.0 the same bias is about 0.2 dB. Recovering the flip fraction is
  the assignment itself, so the estimator is left as-is.
- **`acquire_nc.py` code phase is the complement of the delay.** Peter Monta's kernel correlates in
  the opposite direction; the test asserts the complement rather than changing the kernel.
- **The greedy score change is a sampled approximation when the chip grid is fractional.**
  `score_changes` uses the midpoint samples from `chip_vector`, while a real correlation assigns each
  boundary sample to one of the two neighbouring chips. On a signal whose chip boundaries line up
  with the sample grid the two agree exactly (worst relative difference 1e-13); on a fractional
  delay they can differ by a sizable fraction of the score change. The flags still found 178/180 true
  flips on this data, but the per-chip score is not exact there. The iterative repair in
  `chip_fixing.py` re-correlates the whole signal each round and does not have this approximation.

## Noise robustness of nominal-code cancellation

The table cancels the other 11 satellites with their NOMINAL codes, then repairs this satellite's
chips. Three noise realisations per row, same signal and truth. `C/N0` follows from the fixed
amplitude 0.278; `N0=1.0` is the real files' noise level.

| C/N0 dB-Hz | N0 | repair, all negatives: hits/180 | false | exact codes | top-15 only: hits/180 | false | exact codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 75 | 0.01 | 177-179 | 31-33 | 5/12 | 172-173 | 7-8 | 7/12 |
| 68 | 0.05 | 176-179 | 30-38 | 3-5/12 | 171-173 | 7-9 | 7/12 |
| 65 | 0.10 | 176-179 | 34-39 | 3-4/12 | 170-173 | 7-10 | 6-7/12 |
| 62 | 0.20 | 175-179 | 39-44 | 1-3/12 | 169-174 | 6-11 | 4-8/12 |
| 58 | 0.50 | 168-176 | 57-67 | 0/12 | 157-160 | 20-22 | 1-4/12 |
| 55 | 1.00 | 161-164 | 193-221 | 0/12 | 123-149 | 31-57 | 0-1/12 |

Reading: for **one PRN alone**, nominal-code cancellation is not the limiting factor; its leftover
other-satellite terms rotate at their own Doppler and average down over eight code periods. The
limit is thermal noise on one chip. With a little noise (65-68 dB-Hz) one PRN finds about 96% of its
true flips, with 7-10 false ones when capped at the known 15. At the real files' 55 dB-Hz one PRN
finds only about 70-80%. This is exactly why the joint common-rule method above is required: summing
the 12 aligned PRNs recovers all 15 exactly at 55 dB-Hz.

## Shared-mask scan at 55 dB-Hz

New scenario in `tests/test_global_mask_scan.py`:

- 12 satellites, 55 dB-Hz per PRN (`noise_variance = 1.0`), same 15-chip mask in every code.
- For every chip `i` from 0 to 1022, flip chip `i` in **all twelve** nominal replicas and measure the
  total correlation power `sum over satellites of |S_s|^2`.
- Keep `i` when the total power goes up.

Result: exactly **15 chips have a positive change**, and those 15 are the true mask, for every one of
5 noise seeds. The analytic score and a full recomputation of all twelve correlations agree to
`1e-14`. This works at 55 dB-Hz because the 12 satellites' evidence adds: per-chip SNR 1.57 each
becomes about `1.57 * sqrt(12) = 5.4` for the common mask.

Code: `tests/global_flip.py` (`prepare`, `score_changes`, `brute_force_change`).

## How the -2 chip-per-PRN shift was found

1. Fixed `chip_bits.chip_vector` first. Before that, cross-satellite chip coordinates were mislabelled
   and any comparison was meaningless.
2. For each satellite in `data/gnss_observation.nc`, cancelled the other eleven with nominal codes, then
   read one complex soft value per chip. Each vector is mostly +amplitude with about 15 negative dips.
3. Circularly cross-correlated every satellite's vector against satellite 1 over all 1023 shifts. On
   the strong file the winning shifts came out as `0, -2, -4, -6, ... -22`, i.e. exactly
   `-2 * (PRN - 1)`. Synthetic controls behaved as expected: truly shared flips gave shift 0 for all
   satellites; independent flips gave random shifts.
4. Shifted every vector by its winning shift and averaged. Fifteen chips then stood out negative
   (-1.04 to -0.55 in normalised units) with a clean gap to the sixteenth (+0.45).
5. Held-out check: derive the 15-chip mask from eleven satellites, apply it to the twelfth, and measure
   correlation gain. All twelve held-out gains were **+0.19 to +0.34 dB** (mean +0.25 dB, theory
   +0.26 dB). Random 15-chip masks gave **-0.23 to -0.27 dB**.

`data/gnss_observation2.nc` recovers the same slope, 2 chips per PRN, and keeps 14 of the 15 rule
positions. Its signals are 8 dB weaker, so the weakest position, base chip 987, falls under the
count's cutoff; the recording is a sensitivity limit, not a different pattern.

## Second recording: 14 strong flips, 987 dropped but named

The same seven-step process on `data/gnss_observation2.nc` gives the same slope 2, but the fixed-15
consensus has a hole. At the 15 base positions of `data/gnss_observation.nc`:

| base chip | consensus (normalised) | satellites negative |
| --- | --- | --- |
| 987 | -0.42 sigma | 6/12 |
| 1008 | -0.92 sigma | 9/12 |
| all other 13 | -1.38 to -3.69 sigma | 7/12 to 12/12 |

So 987 is present but weak: it reads a third of a full flip and six of twelve satellites put it
below zero, so the count search drops it. 1008 is the other uncertain one, and it survives the
count. Neither is a second rule: the dropped position stays in the rule, and the JSON records it
under `pattern.positions_missing_here`.

The count is chosen without assuming a value. Search every `K` from 1 upward, and for each `K`
derive the base from 11 satellites, apply it to the left-out satellite, and measure correlation gain.
Average over all 12 left-out choices. The maximum is the data-driven count.

| recording | best K | mean held-out gain at best K |
| --- | --- | --- |
| `data/gnss_observation.nc` | **15** | +0.244 dB |
| `data/gnss_observation2.nc` | **14** | +0.235 dB |

The earlier list `5,10,12,15,...` was only a diagnostic sweep; the choice below does not depend on it.

For the second file, the nearby values are:

| assumed flips | mean held-out gain |
| --- | --- |
| 13 (without 1008) | +0.225 dB |
| **14 (with 1008, without 987)** | **+0.235 dB** |
| 15 (with 987 and 1008) | +0.226 dB |

Adding 1008 raises the held-out gain; adding 987 lowers it. The data-driven count
is **14**. The base with measurable support is the 15-position Fibonacci set without 987:

`[34, 411, 644, 788, 877, 932, 966, 1000, 1008, 1013, 1016, 1018, 1019, 1020]`

Per PRN: `flip = base - 2*(PRN-1)`. The subtraction does not wrap.

The count is not certain: 1008 is only about 3 sigma from both models, so 13 is possible. 987 stays
in the rule but not in this recording's flip table: the JSON records it in
`pattern.positions_missing_here`, and 987 is the position the rule expects that this file cannot
confirm. Hiding the mismatch or silently emitting the chip are both worse than stating the split.
