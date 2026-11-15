# Benchmark: where the recovery breaks

Generated with `python benchmark.py`. Every recording is synthesised from the assignment's signal model, so the truth is known exactly and every run is scored against it: PRNs found, Doppler error, recovered shift, recovered flip set (precision/recall), and residual power against the generator's noise variance (1.000 is perfect cancellation).

Nothing here reads `gnss_observation.nc` or `gnss_observation2.nc`: these are fresh recordings, not the supplied pair. The `seed1`/`seed2` suffix is a noise seed - the same scenario generated twice with different Doppler, delay, carrier phase and flip positions, so the two rows show run-to-run scatter rather than one lucky draw.

`verdict` is `pass` only when every PRN was found with no false alarm, the shift is right, and the recovered flip set matches the truth exactly.

## Headline

- **Sensitivity.** Both seeds passed down to **51 dB-Hz** per PRN. At 49 and at 47, one seed of the pair carried one extra chip (15/16, precision 0.94, recall 1.00), so those points are partial rather than exact. This is a floor for two seeds, not a rate: two seeds can only say 2 of 2. `python breakpoints.py` measures the rate over 100 independent signals per point and finds the 95% edge at **49.4 dB-Hz** - see the Break points section at the end of this report. 12 PRNs at 55 dB-Hz is the assignment's case and it passes with margin.
- **How many chips are flipped.** Every count up to **160** recovers exactly. From 400 up, detection is what fails: 4 of 12 PRNs found at 400 chips, 0 of 12 at 500, because a code modified on 2K of its chips keeps (1023 - 2K)/1023 of the nominal correlation: 223/1023 at 400 and 23/1023 at 500.
- **Doppler.** None of the three fears holds. All 12 PRNs at 0 Hz, all within +-2 Hz and all within +-20 Hz recover exactly (zero 2/2, within-2hz 2/2, within-20hz 2/2, random-4000hz 2/2, fixed-5150hz 2/2, fixed-5500hz 2/2, fixed-5600hz 1/2, fixed-5800hz 0/2, fixed-20000hz 0/2): different spreading codes stay orthogonal even at identical Doppler, and cancellation removes what the codes do not. Large Doppler is a search-span question, not an algorithm one: the span is +-5175 Hz from the satellite's line-of-sight speed plus a 200 km/h receiver, the coarse grid reaches +-5000 Hz and the fine search adds +-500 Hz, so signals at +5500 Hz are still found and at +5800 Hz are not. Raise --max-speed-km-h if the receiver assumption is wrong; do not expect the search to guess outside the span it was given.
- **Large Doppler with the search widened to cover it.** Yes, it works: wide-6khz-default: 0/2 (span +-5175 Hz, 0.3 s); wide-6khz-wide: 2/2 (span +-6300 Hz, 0.6 s); wide-10khz-default: 0/2 (span +-5175 Hz, 0.2 s); wide-10khz-wide: 2/2 (span +-10500 Hz, 0.5 s); wide-15khz-default: 0/2 (span +-5175 Hz, 0.2 s); wide-15khz-wide: 2/2 (span +-15750 Hz, 0.6 s); wide-20khz-default: 0/2 (span +-5175 Hz, 0.2 s); wide-20khz-wide: 2/2 (span +-21000 Hz, 0.6 s); wide-30khz-default: 0/2 (span +-5175 Hz, 0.2 s); wide-30khz-wide: 2/2 (span +-31500 Hz, 0.6 s). Paying for the span costs search time and a little sensitivity, because the detection threshold grows with the number of cells searched (2**-t per cell, so four times the span costs about one more unit of peak-to-floor ratio); it does not cost correctness. Without widening, the same signals are invisible.
- **Dense modifications: a soft edge, not a threshold.** Passes per flip count over 6 seeds: {236: '0/6', 240: '1/6', 244: '0/6', 248: '0/6', 252: '0/6', 256: '0/6', 260: '0/6', 264: '0/6'}. The pattern is not monotonic, and that is the finding: which draw wins depends on where the random base lands, not on K alone, so there is no single flip count at which the method stops. What collapses is the shift margin - 0.030 to 0.030 when the shift is right, 0.000 to 0.121 when it is wrong - so the two populations overlap and the outcome turns on which alias fits. The wrong shifts are 343 and 684, about 1023/3 and 2*1023/3, where PRN rolls coincide. The assignment's 15 flips sits nowhere near this.
- **Number of PRNs.** At 52 dB-Hz per PRN: exact at [4, 5, 6, 7, 8, 9, 10, 12, 16, 20, 30], partial at [40, 60], never recovered at [1, 2, 3, 80, 120, 160, 210] (tested [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 20, 30, 40, 60, 80, 120, 160, 210]). One PRN cannot define a shift at all - there is nothing to relate it to - and the flip decisions need the sqrt(N) combining gain: 12 PRNs buy 10.8 dB where 4 buy 6 dB.
- **Data bits changing at random per PRN.** Over 16 runs, 76 of 192 PRN-records carried a transition inside the record, drawn with probability = record length / 20 ms, and the sign-pattern detector located 188 of them exactly. Runs that did not recover every chip: ['bitprob-2ms-52db-seed2', 'bitprob-4ms-52db-seed2']. At 2 ms the record holds two code periods, which is too few to fit a phase slope *and* locate a step, so a transition there costs the Doppler estimate (371 Hz error in one run) even though the chips survive.
- **Record length.** 2 ms is not enough (failures: ['periods-2-seed1', 'periods-2-seed2']); 4 ms and longer are exact.
- **Fractional code phase** (non-integer sample delay): flips stay exact and the worst Doppler error is 3.88 Hz, but cancellation leaves 1.137 of the noise level behind at a half-sample chip offset, because the replica uses integer-sample rectangular chips. The flips do not care; a residual-power check does.
- **A navigation data bit flipping mid-record**: worst Doppler error 3.74 Hz over 4 runs. This case used to return ~100 Hz while claiming +-1.5 Hz; the sign change is now modelled, so it costs nothing.
- **Independent random flips per PRN** (no shared rule): the chain reports [0] chips at +0.000 to +0.000 dB held-out gain, so the evidence collapses to nothing and no rule is claimed.
- **No modification at all**: [0] chips reported at +0.000 to +0.000 dB, i.e. the search does not manufacture a rule out of noise.

## Time

One row per sweep. `mean` is the cost of scoring one recording, i.e. the whole chain (acquisition, cancellation, chip read-out, rule search, verification), averaged over that sweep's runs. Synthesis and scoring are excluded from `mean` but not from `total`.

Backend: `gpu (NVIDIA GeForce RTX 4050 Laptop GPU, CuPy 14.2.0)`. `GNSS_BACKEND=cpu` or `GNSS_BACKEND=gpu` forces one. The CPU path is the reference the device path is checked against, so the two produce the same numbers; only the time changes.

| sweep | runs | mean seconds | total seconds |
| --- | --- | --- | --- |
| cn0 | 20 | 0.56 | 11.3 |
| flip_count | 36 | 0.56 | 20.0 |
| dense_flips | 48 | 0.59 | 28.1 |
| doppler | 18 | 0.46 | 8.3 |
| wide_doppler | 20 | 0.40 | 8.1 |
| slope | 12 | 0.54 | 6.5 |
| prns | 40 | 2.23 | 89.1 |
| bit_probability | 16 | 0.66 | 10.5 |
| duration | 8 | 0.62 | 5.0 |
| fractional_delay | 8 | 0.56 | 4.5 |
| data_bit | 8 | 0.55 | 4.4 |
| structure | 6 | 0.55 | 3.3 |
| **all** | 240 | 0.86 | 206 |

## cn0

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cn0-70-seed1 | 12/12 | 1.39 Hz | 2 ok | 5.761 | 15/15 | 1.00 | 1.00 | 1.00 | 1.014 | pass |
| cn0-70-seed2 | 12/12 | 1.33 Hz | 2 ok | 5.110 | 15/15 | 1.00 | 1.00 | 1.00 | 1.038 | pass |
| cn0-65-seed1 | 12/12 | 1.76 Hz | 2 ok | 5.620 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-65-seed2 | 12/12 | 1.31 Hz | 2 ok | 4.977 | 15/15 | 1.00 | 1.00 | 1.00 | 1.012 | pass |
| cn0-60-seed1 | 12/12 | 2.52 Hz | 2 ok | 5.265 | 15/15 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| cn0-60-seed2 | 12/12 | 1.41 Hz | 2 ok | 4.602 | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| cn0-57-seed1 | 12/12 | 3.24 Hz | 2 ok | 4.863 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-57-seed2 | 12/12 | 2.00 Hz | 2 ok | 4.196 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-55-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-55-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-53-seed1 | 12/12 | 4.69 Hz | 2 ok | 4.043 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-53-seed2 | 12/12 | 1.93 Hz | 2 ok | 3.406 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-51-seed1 | 12/12 | 5.71 Hz | 2 ok | 3.522 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-51-seed2 | 12/12 | 2.65 Hz | 2 ok | 2.913 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-49-seed1 | 12/12 | 6.99 Hz | 2 ok | 2.958 | 15/16 | 0.94 | 1.00 | 0.97 | 0.996 | partial |
| cn0-49-seed2 | 12/12 | 3.41 Hz | 2 ok | 2.374 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-47-seed1 | 12/12 | 8.49 Hz | 2 ok | 2.373 | 15/16 | 0.94 | 1.00 | 0.97 | 0.996 | partial |
| cn0-47-seed2 | 12/12 | 4.38 Hz | 2 ok | 1.780 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-45-seed1 | 12/12 | 10.26 Hz | 2 ok | 1.591 | 15/16 | 0.94 | 1.00 | 0.97 | 0.996 | partial |
| cn0-45-seed2 | 12/12 | 5.58 Hz | 2 ok | 1.180 | 15/17 | 0.88 | 1.00 | 0.94 | 1.000 | partial |

## flip_count

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flips-3-seed1 | 12/12 | 2.75 Hz | 2 ok | 1.233 | 3/3 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-3-seed2 | 12/12 | 2.06 Hz | 2 ok | 1.014 | 3/3 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-5-seed1 | 12/12 | 3.09 Hz | 2 ok | 1.454 | 5/5 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-5-seed2 | 12/12 | 2.64 Hz | 2 ok | 1.826 | 5/5 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-8-seed1 | 12/12 | 1.84 Hz | 2 ok | 2.582 | 8/8 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-8-seed2 | 12/12 | 3.56 Hz | 2 ok | 2.507 | 8/8 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-12-seed1 | 12/12 | 2.68 Hz | 2 ok | 3.626 | 12/12 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-12-seed2 | 12/12 | 4.25 Hz | 2 ok | 3.143 | 12/12 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-15-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-15-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-20-seed1 | 12/12 | 1.91 Hz | 2 ok | 4.155 | 20/20 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-20-seed2 | 12/12 | 3.24 Hz | 2 ok | 4.347 | 20/20 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-30-seed1 | 12/12 | 2.93 Hz | 2 ok | 2.674 | 30/30 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| flips-30-seed2 | 12/12 | 2.28 Hz | 2 ok | 2.933 | 30/30 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-40-seed1 | 12/12 | 3.02 Hz | 2 ok | 2.973 | 40/40 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-40-seed2 | 12/12 | 3.58 Hz | 2 ok | 3.162 | 40/40 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-60-seed1 | 12/12 | 5.25 Hz | 2 ok | 1.860 | 60/60 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-60-seed2 | 12/12 | 2.91 Hz | 2 ok | 1.853 | 60/60 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-80-seed1 | 12/12 | 2.93 Hz | 2 ok | 1.121 | 80/80 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-80-seed2 | 12/12 | 3.68 Hz | 2 ok | 1.232 | 80/80 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-120-seed1 | 12/12 | 4.95 Hz | 2 ok | 0.690 | 120/120 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-120-seed2 | 12/12 | 4.32 Hz | 2 ok | 0.308 | 120/120 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| flips-160-seed1 | 12/12 | 7.07 Hz | 2 ok | 0.149 | 160/160 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-160-seed2 | 12/12 | 5.54 Hz | 2 ok | 0.083 | 160/160 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| flips-200-seed1 | 12/12 | 4.00 Hz | 684 WRONG | 0.048 | 200/68 | 0.71 | 0.24 | 0.36 | 1.506 | slope |
| flips-200-seed2 | 12/12 | 8.55 Hz | 2 ok | 0.016 | 200/200 | 1.00 | 1.00 | 1.00 | 1.005 | pass |
| flips-230-seed1 | 12/12 | 7.49 Hz | 2 ok | 0.061 | 230/230 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-230-seed2 | 12/12 | 8.02 Hz | 684 WRONG | 0.054 | 230/133 | 0.65 | 0.38 | 0.48 | 1.538 | slope |
| flips-240-seed1 | 12/12 | 7.12 Hz | 2 ok | 0.030 | 240/240 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-240-seed2 | 12/12 | 7.46 Hz | 684 WRONG | 0.038 | 240/119 | 0.69 | 0.34 | 0.46 | 1.545 | slope |
| flips-320-seed1 | 12/12 | 13.30 Hz | 343 WRONG | 0.002 | 320/147 | 0.71 | 0.33 | 0.45 | 1.640 | slope |
| flips-320-seed2 | 12/12 | 17.18 Hz | 343 WRONG | 0.042 | 320/167 | 0.73 | 0.38 | 0.50 | 1.660 | slope |
| flips-400-seed1 | 6/12 | 9.45 Hz | 292 WRONG | 0.017 | 400/35 | 0.31 | 0.03 | 0.05 | 1.923 | detection |
| flips-400-seed2 | 4/12 | 8.00 Hz | 820 WRONG | 0.002 | 400/26 | 0.50 | 0.03 | 0.06 | 1.911 | detection |
| flips-500-seed1 | 0/12 | n/a | n/a | n/a | 500/n/a | n/a | n/a | n/a | n/a | detection |
| flips-500-seed2 | 0/12 | n/a | n/a | n/a | 500/n/a | n/a | n/a | n/a | n/a | detection |

## dense_flips

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dense-236-seed1 | 12/12 | 9.71 Hz | 343 WRONG | 0.050 | 236/142 | 0.71 | 0.43 | 0.53 | 1.521 | slope |
| dense-236-seed2 | 12/12 | 11.25 Hz | 343 WRONG | 0.015 | 236/139 | 0.68 | 0.40 | 0.51 | 1.516 | slope |
| dense-236-seed3 | 12/12 | 8.01 Hz | 969 WRONG | 0.027 | 236/23 | 0.52 | 0.05 | 0.09 | 1.637 | slope |
| dense-236-seed4 | 12/12 | 9.06 Hz | 343 WRONG | 0.020 | 236/141 | 0.69 | 0.41 | 0.51 | 1.512 | slope |
| dense-236-seed5 | 12/12 | 4.48 Hz | 684 WRONG | 0.081 | 236/114 | 0.68 | 0.33 | 0.44 | 1.540 | slope |
| dense-236-seed6 | 12/12 | 6.98 Hz | 343 WRONG | 0.071 | 236/100 | 0.68 | 0.29 | 0.40 | 1.558 | slope |
| dense-240-seed1 | 12/12 | 7.12 Hz | 2 ok | 0.030 | 240/240 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| dense-240-seed2 | 12/12 | 7.46 Hz | 684 WRONG | 0.038 | 240/119 | 0.69 | 0.34 | 0.46 | 1.545 | slope |
| dense-240-seed3 | 12/12 | 6.17 Hz | 684 WRONG | 0.003 | 240/159 | 0.65 | 0.43 | 0.52 | 1.549 | slope |
| dense-240-seed4 | 12/12 | 6.40 Hz | 684 WRONG | 0.004 | 240/127 | 0.68 | 0.36 | 0.47 | 1.542 | slope |
| dense-240-seed5 | 12/12 | 8.39 Hz | 343 WRONG | 0.004 | 240/132 | 0.65 | 0.36 | 0.46 | 1.545 | slope |
| dense-240-seed6 | 12/12 | 10.49 Hz | 684 WRONG | 0.019 | 240/102 | 0.70 | 0.30 | 0.42 | 1.544 | slope |
| dense-244-seed1 | 12/12 | 5.71 Hz | 684 WRONG | 0.030 | 244/125 | 0.70 | 0.36 | 0.47 | 1.535 | slope |
| dense-244-seed2 | 12/12 | 6.49 Hz | 343 WRONG | 0.023 | 244/114 | 0.72 | 0.34 | 0.46 | 1.545 | slope |
| dense-244-seed3 | 12/12 | 6.25 Hz | 343 WRONG | 0.039 | 244/149 | 0.68 | 0.41 | 0.51 | 1.551 | slope |
| dense-244-seed4 | 12/12 | 9.58 Hz | 343 WRONG | 0.014 | 244/114 | 0.73 | 0.34 | 0.46 | 1.544 | slope |
| dense-244-seed5 | 12/12 | 5.93 Hz | 684 WRONG | 0.067 | 244/116 | 0.68 | 0.32 | 0.44 | 1.544 | slope |
| dense-244-seed6 | 12/12 | 8.11 Hz | 343 WRONG | 0.043 | 244/124 | 0.67 | 0.34 | 0.45 | 1.547 | slope |
| dense-248-seed1 | 12/12 | 7.41 Hz | 343 WRONG | 0.063 | 248/148 | 0.70 | 0.42 | 0.53 | 1.533 | slope |
| dense-248-seed2 | 12/12 | 8.23 Hz | 684 WRONG | 0.011 | 248/119 | 0.69 | 0.33 | 0.45 | 1.557 | slope |
| dense-248-seed3 | 12/12 | 13.25 Hz | 343 WRONG | 0.114 | 248/127 | 0.69 | 0.35 | 0.46 | 1.577 | slope |
| dense-248-seed4 | 12/12 | 5.66 Hz | 343 WRONG | 0.044 | 248/117 | 0.69 | 0.33 | 0.44 | 1.566 | slope |
| dense-248-seed5 | 12/12 | 5.53 Hz | 684 WRONG | 0.045 | 248/154 | 0.71 | 0.44 | 0.54 | 1.532 | slope |
| dense-248-seed6 | 12/12 +1 | 7.36 Hz | 2 ok | 0.002 | 248/248 | 1.00 | 1.00 | 1.00 | 1.002 | detection |
| dense-252-seed1 | 12/12 | 11.15 Hz | 343 WRONG | 0.015 | 252/126 | 0.70 | 0.35 | 0.47 | 1.567 | slope |
| dense-252-seed2 | 12/12 | 7.79 Hz | 567 WRONG | 0.010 | 252/19 | 0.68 | 0.05 | 0.10 | 1.651 | slope |
| dense-252-seed3 | 12/12 | 6.50 Hz | 343 WRONG | 0.003 | 252/128 | 0.69 | 0.35 | 0.46 | 1.580 | slope |
| dense-252-seed4 | 12/12 | 8.16 Hz | 343 WRONG | 0.015 | 252/170 | 0.66 | 0.45 | 0.54 | 1.538 | slope |
| dense-252-seed5 | 12/12 | 5.06 Hz | 343 WRONG | 0.028 | 252/134 | 0.66 | 0.35 | 0.46 | 1.570 | slope |
| dense-252-seed6 | 12/12 | 8.69 Hz | 343 WRONG | 0.021 | 252/139 | 0.68 | 0.38 | 0.49 | 1.564 | slope |
| dense-256-seed1 | 12/12 | 6.19 Hz | 684 WRONG | 0.015 | 256/174 | 0.70 | 0.47 | 0.56 | 1.536 | slope |
| dense-256-seed2 | 12/12 | 7.61 Hz | 684 WRONG | 0.039 | 256/141 | 0.67 | 0.37 | 0.47 | 1.550 | slope |
| dense-256-seed3 | 12/12 | 7.56 Hz | 343 WRONG | 0.121 | 256/186 | 0.69 | 0.50 | 0.58 | 1.535 | slope |
| dense-256-seed4 | 12/12 | 10.35 Hz | 55 WRONG | 0.067 | 256/9 | 0.56 | 0.02 | 0.04 | 1.686 | slope |
| dense-256-seed5 | 12/12 | 9.64 Hz | 835 WRONG | 0.068 | 256/4 | 0.75 | 0.01 | 0.02 | 1.671 | slope |
| dense-256-seed6 | 12/12 | 6.38 Hz | 684 WRONG | 0.027 | 256/114 | 0.75 | 0.34 | 0.46 | 1.559 | slope |
| dense-260-seed1 | 12/12 | 10.89 Hz | 343 WRONG | 0.045 | 260/114 | 0.70 | 0.31 | 0.43 | 1.579 | slope |
| dense-260-seed2 | 12/12 | 9.59 Hz | 684 WRONG | 0.012 | 260/156 | 0.67 | 0.40 | 0.50 | 1.577 | slope |
| dense-260-seed3 | 12/12 | 7.31 Hz | 684 WRONG | 0.023 | 260/166 | 0.67 | 0.43 | 0.53 | 1.552 | slope |
| dense-260-seed4 | 12/12 | 7.01 Hz | 684 WRONG | 0.011 | 260/168 | 0.68 | 0.44 | 0.53 | 1.547 | slope |
| dense-260-seed5 | 12/12 | 6.16 Hz | 343 WRONG | 0.011 | 260/138 | 0.70 | 0.37 | 0.48 | 1.550 | slope |
| dense-260-seed6 | 12/12 | 7.28 Hz | 684 WRONG | 0.008 | 260/154 | 0.71 | 0.42 | 0.53 | 1.546 | slope |
| dense-264-seed1 | 12/12 | 5.73 Hz | 684 WRONG | 0.002 | 264/157 | 0.70 | 0.42 | 0.52 | 1.583 | slope |
| dense-264-seed2 | 12/12 | 7.72 Hz | 684 WRONG | 0.046 | 264/157 | 0.70 | 0.42 | 0.52 | 1.560 | slope |
| dense-264-seed3 | 12/12 | 6.31 Hz | 684 WRONG | 0.020 | 264/145 | 0.70 | 0.39 | 0.50 | 1.562 | slope |
| dense-264-seed4 | 12/12 | 7.93 Hz | 684 WRONG | 0.000 | 264/147 | 0.69 | 0.38 | 0.49 | 1.589 | slope |
| dense-264-seed5 | 12/12 | 8.14 Hz | 343 WRONG | 0.020 | 264/117 | 0.69 | 0.31 | 0.43 | 1.581 | slope |
| dense-264-seed6 | 12/12 | 4.42 Hz | 684 WRONG | 0.014 | 264/124 | 0.72 | 0.34 | 0.46 | 1.594 | slope |

## doppler

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| doppler-zero-seed1 | 12/12 | 2.25 Hz | 2 ok | 3.902 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| doppler-zero-seed2 | 12/12 | 3.27 Hz | 2 ok | 3.304 | 15/15 | 1.00 | 1.00 | 1.00 | 1.007 | pass |
| doppler-within-2hz-seed1 | 12/12 | 1.90 Hz | 2 ok | 3.652 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-within-2hz-seed2 | 12/12 | 2.59 Hz | 2 ok | 3.641 | 15/15 | 1.00 | 1.00 | 1.00 | 1.007 | pass |
| doppler-within-20hz-seed1 | 12/12 | 2.24 Hz | 2 ok | 3.716 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-within-20hz-seed2 | 12/12 | 2.32 Hz | 2 ok | 3.622 | 15/15 | 1.00 | 1.00 | 1.00 | 1.008 | pass |
| doppler-random-4000hz-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| doppler-random-4000hz-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-fixed-5150hz-seed1 | 12/12 | 1.85 Hz | 2 ok | 4.352 | 15/15 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| doppler-fixed-5150hz-seed2 | 12/12 | 2.60 Hz | 2 ok | 3.794 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-fixed-5500hz-seed1 | 12/12 | 2.51 Hz | 2 ok | 3.948 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| doppler-fixed-5500hz-seed2 | 12/12 | 1.93 Hz | 2 ok | 3.291 | 15/15 | 1.00 | 1.00 | 1.00 | 1.005 | pass |
| doppler-fixed-5600hz-seed1 | 11/12 | 3.35 Hz | 2 ok | 3.411 | 15/15 | 1.00 | 1.00 | 1.00 | 1.075 | detection |
| doppler-fixed-5600hz-seed2 | 12/12 | 105.59 Hz | 2 ok | 3.176 | 15/15 | 1.00 | 1.00 | 1.00 | 1.037 | pass |
| doppler-fixed-5800hz-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| doppler-fixed-5800hz-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| doppler-fixed-20000hz-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| doppler-fixed-20000hz-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |

## wide_doppler

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| wide-6khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-6khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-6khz-wide-seed1 | 12/12 | 2.25 Hz | 2 ok | 3.786 | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| wide-6khz-wide-seed2 | 12/12 | 2.81 Hz | 2 ok | 3.384 | 15/15 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| wide-10khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-10khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-10khz-wide-seed1 | 12/12 | 1.88 Hz | 2 ok | 3.796 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| wide-10khz-wide-seed2 | 12/12 | 3.07 Hz | 2 ok | 3.290 | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| wide-15khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-15khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-15khz-wide-seed1 | 12/12 | 2.31 Hz | 2 ok | 3.617 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| wide-15khz-wide-seed2 | 12/12 | 3.39 Hz | 2 ok | 3.104 | 15/15 | 1.00 | 1.00 | 1.00 | 1.007 | pass |
| wide-20khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-20khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-20khz-wide-seed1 | 12/12 | 1.37 Hz | 2 ok | 3.704 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| wide-20khz-wide-seed2 | 12/12 | 2.16 Hz | 2 ok | 3.296 | 15/15 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| wide-30khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-30khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-30khz-wide-seed1 | 12/12 | 3.06 Hz | 2 ok | 3.732 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| wide-30khz-wide-seed2 | 12/12 | 1.73 Hz | 2 ok | 3.368 | 15/15 | 1.00 | 1.00 | 1.00 | 1.005 | pass |

## slope

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| slope-0-seed1 | 12/12 | 2.62 Hz | 0 ok | 4.717 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-0-seed2 | 12/12 | 1.60 Hz | 0 ok | 3.913 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-1-seed1 | 12/12 | 3.66 Hz | 1 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-1-seed2 | 12/12 | 1.74 Hz | 1 ok | 3.887 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-2-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-2-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-3-seed1 | 12/12 | 2.78 Hz | 3 ok | 4.587 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-3-seed2 | 12/12 | 1.87 Hz | 3 ok | 4.064 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-7-seed1 | 12/12 | 3.63 Hz | 7 ok | 4.488 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-7-seed2 | 12/12 | 2.29 Hz | 7 ok | 3.911 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-25-seed1 | 12/12 | 4.97 Hz | 25 ok | 4.276 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-25-seed2 | 12/12 | 2.31 Hz | 25 ok | 4.104 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |

## prns

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prns-1-seed1 | 1/1 | 0.02 Hz | 0 WRONG | 0.000 | 15/0 | 0.00 | 0.00 | 0.00 | 0.999 | slope |
| prns-1-seed2 | 1/1 | 1.04 Hz | 0 WRONG | 0.000 | 15/0 | 0.00 | 0.00 | 0.00 | 1.004 | slope |
| prns-2-seed1 | 2/2 | 2.10 Hz | 2 ok | 0.855 | 15/13 | 1.00 | 0.87 | 0.93 | 0.997 | partial |
| prns-2-seed2 | 2/2 | 1.49 Hz | 2 ok | 0.739 | 15/14 | 1.00 | 0.93 | 0.97 | 1.001 | partial |
| prns-3-seed1 | 3/3 | 2.45 Hz | 2 ok | 1.418 | 15/14 | 1.00 | 0.93 | 0.97 | 0.997 | partial |
| prns-3-seed2 | 3/3 | 5.78 Hz | 2 ok | 1.579 | 15/15 | 0.93 | 0.93 | 0.93 | 1.001 | partial |
| prns-4-seed1 | 4/4 | 4.44 Hz | 2 ok | 1.982 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-4-seed2 | 4/4 | 2.39 Hz | 2 ok | 1.885 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-5-seed1 | 5/5 | 2.46 Hz | 2 ok | 2.772 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-5-seed2 | 5/5 | 1.77 Hz | 2 ok | 2.312 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-6-seed1 | 6/6 | 3.06 Hz | 2 ok | 3.186 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-6-seed2 | 6/6 | 2.41 Hz | 2 ok | 2.614 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-7-seed1 | 7/7 | 3.66 Hz | 2 ok | 2.930 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-7-seed2 | 7/7 | 1.61 Hz | 2 ok | 2.654 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-8-seed1 | 8/8 | 1.40 Hz | 2 ok | 3.147 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-8-seed2 | 8/8 | 2.49 Hz | 2 ok | 2.903 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-9-seed1 | 9/9 | 2.98 Hz | 2 ok | 3.259 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-9-seed2 | 9/9 | 3.08 Hz | 2 ok | 3.244 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-10-seed1 | 10/10 | 7.00 Hz | 2 ok | 3.250 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-10-seed2 | 10/10 | 1.64 Hz | 2 ok | 3.264 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-12-seed1 | 12/12 | 5.17 Hz | 2 ok | 3.790 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-12-seed2 | 12/12 | 2.32 Hz | 2 ok | 3.167 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-16-seed1 | 16/16 | 5.14 Hz | 2 ok | 4.132 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-16-seed2 | 16/16 | 3.75 Hz | 2 ok | 3.735 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| prns-20-seed1 | 20/20 | 6.13 Hz | 2 ok | 4.415 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-20-seed2 | 20/20 | 3.29 Hz | 2 ok | 3.740 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| prns-30-seed1 | 30/30 | 5.20 Hz | 2 ok | 4.691 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-30-seed2 | 30/30 | 2.96 Hz | 2 ok | 4.033 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| prns-40-seed1 | 40/40 | 6586.25 Hz | 2 ok | 4.834 | 15/15 | 1.00 | 1.00 | 1.00 | 1.072 | pass |
| prns-40-seed2 | 38/40 | 3.40 Hz | 2 ok | 4.023 | 15/15 | 1.00 | 1.00 | 1.00 | 1.081 | detection |
| prns-60-seed1 | 60/60 | 6586.59 Hz | 2 ok | 5.013 | 15/15 | 1.00 | 1.00 | 1.00 | 1.080 | pass |
| prns-60-seed2 | 58/60 | 4.63 Hz | 2 ok | 4.313 | 15/15 | 1.00 | 1.00 | 1.00 | 1.087 | detection |
| prns-80-seed1 | 78/80 | 4.03 Hz | 2 ok | 5.248 | 15/15 | 1.00 | 1.00 | 1.00 | 1.091 | detection |
| prns-80-seed2 | 78/80 | 6.21 Hz | 2 ok | 4.462 | 15/15 | 1.00 | 1.00 | 1.00 | 1.094 | detection |
| prns-120-seed1 | 118/120 | 10.64 Hz | 2 ok | 5.338 | 15/13 | 1.00 | 0.87 | 0.93 | 1.228 | detection |
| prns-120-seed2 | 118/120 | 11.16 Hz | 2 ok | 4.781 | 15/15 | 1.00 | 1.00 | 1.00 | 1.161 | detection |
| prns-160-seed1 | 158/160 | 10.80 Hz | 2 ok | 5.185 | 15/15 | 1.00 | 1.00 | 1.00 | 1.466 | detection |
| prns-160-seed2 | 158/160 | 12.39 Hz | 2 ok | 4.371 | 15/15 | 1.00 | 1.00 | 1.00 | 1.617 | detection |
| prns-210-seed1 | 197/210 | 11.60 Hz | 2 ok | 4.416 | 15/11 | 1.00 | 0.73 | 0.85 | 3.088 | detection |
| prns-210-seed2 | 202/210 | 11.56 Hz | 2 ok | 3.839 | 15/4 | 1.00 | 0.27 | 0.42 | 3.047 | detection |

## bit_probability

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bitprob-2ms-55db-seed1 | 12/12 | 19.82 Hz | 2 ok | 3.106 | 15/15 | 1.00 | 1.00 | 1.00 | 0.991 | pass |
| bitprob-2ms-55db-seed2 | 12/12 | 371.73 Hz | 2 ok | 2.132 | 15/15 | 1.00 | 1.00 | 1.00 | 1.064 | pass |
| bitprob-2ms-52db-seed1 | 12/12 | 23.10 Hz | 2 ok | 1.890 | 15/15 | 1.00 | 1.00 | 1.00 | 0.989 | pass |
| bitprob-2ms-52db-seed2 | 12/12 | 369.21 Hz | 2 ok | 1.458 | 15/13 | 1.00 | 0.87 | 0.93 | 1.027 | partial |
| bitprob-4ms-55db-seed1 | 12/12 | 8.51 Hz | 2 ok | 3.694 | 15/15 | 1.00 | 1.00 | 1.00 | 0.987 | pass |
| bitprob-4ms-55db-seed2 | 12/12 | 13.50 Hz | 2 ok | 3.367 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bitprob-4ms-52db-seed1 | 12/12 | 9.75 Hz | 2 ok | 2.803 | 15/15 | 1.00 | 1.00 | 1.00 | 0.986 | pass |
| bitprob-4ms-52db-seed2 | 12/12 | 17.90 Hz | 2 ok | 2.612 | 15/16 | 0.94 | 1.00 | 0.97 | 1.002 | partial |
| bitprob-8ms-55db-seed1 | 12/12 | 2.52 Hz | 2 ok | 4.659 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bitprob-8ms-55db-seed2 | 12/12 | 3.83 Hz | 2 ok | 3.864 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bitprob-8ms-52db-seed1 | 12/12 | 3.26 Hz | 2 ok | 3.926 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| bitprob-8ms-52db-seed2 | 12/12 | 4.68 Hz | 2 ok | 3.189 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| bitprob-16ms-55db-seed1 | 12/12 | 0.91 Hz | 2 ok | 5.309 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| bitprob-16ms-55db-seed2 | 12/12 | 0.95 Hz | 2 ok | 4.312 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bitprob-16ms-52db-seed1 | 12/12 | 1.13 Hz | 2 ok | 4.710 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| bitprob-16ms-52db-seed2 | 12/12 | 1.11 Hz | 2 ok | 3.798 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |

## duration

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| periods-2-seed1 | 12/12 | 32.34 Hz | 2 ok | 1.281 | 15/14 | 1.00 | 0.93 | 0.97 | 0.990 | partial |
| periods-2-seed2 | 12/12 | 20.55 Hz | 2 ok | 1.638 | 15/15 | 0.93 | 0.93 | 0.93 | 0.988 | partial |
| periods-4-seed1 | 12/12 | 4.31 Hz | 2 ok | 2.696 | 15/15 | 1.00 | 1.00 | 1.00 | 0.986 | pass |
| periods-4-seed2 | 12/12 | 10.35 Hz | 2 ok | 2.817 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| periods-8-seed1 | 12/12 | 5.17 Hz | 2 ok | 3.790 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| periods-8-seed2 | 12/12 | 2.32 Hz | 2 ok | 3.167 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| periods-16-seed1 | 12/12 | 1.54 Hz | 2 ok | 4.506 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| periods-16-seed2 | 12/12 | 1.27 Hz | 2 ok | 4.090 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |

## fractional_delay

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delay-0.0-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| delay-0.0-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| delay-0.25-seed1 | 12/12 | 3.55 Hz | 2 ok | 4.435 | 15/15 | 1.00 | 1.00 | 1.00 | 1.034 | pass |
| delay-0.25-seed2 | 12/12 | 2.95 Hz | 2 ok | 3.829 | 15/15 | 1.00 | 1.00 | 1.00 | 1.037 | pass |
| delay-0.5-seed1 | 12/12 | 3.03 Hz | 2 ok | 4.251 | 15/15 | 1.00 | 1.00 | 1.00 | 1.136 | pass |
| delay-0.5-seed2 | 12/12 | 2.46 Hz | 2 ok | 3.664 | 15/15 | 1.00 | 1.00 | 1.00 | 1.137 | pass |
| delay-0.75-seed1 | 12/12 | 2.58 Hz | 2 ok | 4.443 | 15/15 | 1.00 | 1.00 | 1.00 | 1.036 | pass |
| delay-0.75-seed2 | 12/12 | 2.06 Hz | 2 ok | 3.748 | 15/15 | 1.00 | 1.00 | 1.00 | 1.043 | pass |

## data_bit

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bit-None-55-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-55-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-None-52-seed1 | 12/12 | 5.17 Hz | 2 ok | 3.790 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-52-seed2 | 12/12 | 2.32 Hz | 2 ok | 3.167 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| bit-4-55-seed1 | 12/12 | 2.85 Hz | 2 ok | 4.535 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-55-seed2 | 12/12 | 3.74 Hz | 2 ok | 3.947 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-4-52-seed1 | 12/12 | 2.68 Hz | 2 ok | 3.819 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-52-seed2 | 12/12 | 3.51 Hz | 2 ok | 3.345 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |

## structure

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared-15-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.490 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| shared-15-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.838 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| independent-15-seed1 | 12/12 | 3.65 Hz | n/a | 0.039 | 15/0 | n/a | n/a | n/a | 1.053 | no-rule |
| independent-15-seed2 | 12/12 | 2.98 Hz | n/a | 0.090 | 15/0 | n/a | n/a | n/a | 1.057 | no-rule |
| none-0-seed1 | 12/12 | 1.60 Hz | n/a | 0.007 | 0/0 | n/a | n/a | n/a | 0.997 | no-rule |
| none-0-seed2 | 12/12 | 3.26 Hz | n/a | 0.046 | 0/0 | n/a | n/a | n/a | 1.002 | no-rule |

## Break points, measured over independent signals

Generated with `python breakpoints.py --signals 100`. Each probe runs **100 independent recordings** (one per seed) at one value of one axis and counts how many recover exactly, then the value is bisected until the passing and breaking ends are one resolution apart. The sweeps above use two seeds per point, which can only say 0/2, 1/2 or 2/2; this can say 91 of 100.

A signal counts as recovered when the verdict is `pass`: every PRN found with no false alarm, the shift right and the flip set exactly right. The criterion is **95 of 100** signals. Every probe reuses the same seeds, so adjacent probes differ in the parameter and not in the noise draw.

### Located edges

| axis | question | edge | rate at the edge | 95% interval | next value fails at |
| --- | --- | --- | --- | --- | --- |
| cn0 | lowest carrier-to-noise density per PRN that still recovers every chip | 49.375 dB-Hz | 95/100 = 95% | 89% to 98% | 49.2188 dB-Hz |
| flip_count | largest number of flipped chips per PRN that still recovers exactly | 140 chips | 97/100 = 97% | 92% to 99% | 144 chips |
| prns_low | fewest PRNs that still recover exactly (below it the combining gain is gone) | 7 PRNs | 99/100 = 99% | 95% to 100% | 6 PRNs |
| prns_high | most PRNs that still recover exactly (beyond it the noise floor moves) | 32 PRNs | 100/100 = 100% | 96% to 100% | 36 PRNs |
| doppler | largest Doppler the widened search still recovers (span widens to cover it) | **bracket wrong** | the declared bad end 120000 Hz still reached 100/100; the break is outside the bracket | | |
| duration | shortest record, in code periods, that still recovers exactly | 5 code periods | 98/100 = 98% | 93% to 99% | 4 code periods |

### cn0

lowest carrier-to-noise density per PRN that still recovers every chip

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 60 dB-Hz (declared good) | 100/100 | 100% | 96% to 100% |
| 45 dB-Hz | 26/100 | 26% | 18% to 35% |
| 47.5 dB-Hz | 83/100 | 83% | 74% to 89% |
| 48.75 dB-Hz | 92/100 | 92% | 85% to 96% |
| 49.0625 dB-Hz | 92/100 | 92% | 85% to 96% |
| 49.2188 dB-Hz | 94/100 | 94% | 88% to 97% |
| 49.375 dB-Hz | 95/100 | 95% | 89% to 98% |
| 50 dB-Hz | 98/100 | 98% | 93% to 99% |
| 40 dB-Hz (declared bad) | 0/100 | 0% | 0% to 4% |

**Edge between 49.375 and 49.2188 dB-Hz** (resolution 0.25, criterion 95%). Probes on this axis: 9, 513 s.

### flip_count

largest number of flipped chips per PRN that still recovers exactly

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 15 chips (declared good) | 100/100 | 100% | 96% to 100% |
| 136 chips | 98/100 | 98% | 93% to 99% |
| 140 chips | 97/100 | 97% | 92% to 99% |
| 144 chips | 94/100 | 94% | 88% to 97% |
| 151 chips | 92/100 | 92% | 85% to 96% |
| 166 chips | 78/100 | 78% | 69% to 85% |
| 197 chips | 44/100 | 44% | 35% to 54% |
| 258 chips | 0/100 | 0% | 0% to 4% |
| 500 chips (declared bad) | 0/100 | 0% | 0% to 4% |

**Edge between 140 and 144 chips** (resolution 4, criterion 95%). Probes on this axis: 9, 519 s.

### prns_low

fewest PRNs that still recover exactly (below it the combining gain is gone)

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 12 PRNs (declared good) | 100/100 | 100% | 96% to 100% |
| 6 PRNs | 94/100 | 94% | 88% to 97% |
| 7 PRNs | 99/100 | 99% | 95% to 100% |
| 8 PRNs | 98/100 | 98% | 93% to 99% |
| 9 PRNs | 100/100 | 100% | 96% to 100% |
| 1 PRNs (declared bad) | 0/100 | 0% | 0% to 4% |

**Edge between 7 and 6 PRNs** (resolution 1, criterion 95%). Probes on this axis: 6, 256 s.

### prns_high

most PRNs that still recover exactly (beyond it the noise floor moves)

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 12 PRNs (declared good) | 100/100 | 100% | 96% to 100% |
| 26 PRNs | 100/100 | 100% | 96% to 100% |
| 32 PRNs | 100/100 | 100% | 96% to 100% |
| 36 PRNs | 0/100 | 0% | 0% to 4% |
| 39 PRNs | 34/100 | 34% | 25% to 44% |
| 66 PRNs | 39/100 | 39% | 30% to 49% |
| 120 PRNs (declared bad) | 21/100 | 21% | 14% to 30% |

**Edge between 32 and 36 PRNs** (resolution 4, criterion 95%). Probes on this axis: 7, 1782 s.

### doppler

largest Doppler the widened search still recovers (span widens to cover it)

**Bracket wrong.** the declared bad end 120000 Hz still reached 100/100; the break is outside the bracket

### duration

shortest record, in code periods, that still recovers exactly

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 8 code periods (declared good) | 100/100 | 100% | 96% to 100% |
| 4 code periods | 94/100 | 94% | 88% to 97% |
| 5 code periods | 98/100 | 98% | 93% to 99% |
| 6 code periods | 100/100 | 100% | 96% to 100% |
| 1 code periods (declared bad) | 0/100 | 0% | 0% to 4% |

**Edge between 5 and 4 code periods** (resolution 1, criterion 95%). Probes on this axis: 5, 213 s.

### Cost

6 axes, 38 probes, 100 signals per probe: 3800 recordings scored in 58.6 min (0.93 s per recording). This is the measured cost of the probes, including any reused from the cache; this run took 0.0 min of wall clock.

## Duration against C/N0

Does a longer record buy a lower C/N0 floor for the full 15-chip recovery? A chip is measured once per code period, so every doubling of the record adds 3 dB of combining gain - in principle. This section measures where the floor actually is, one C/N0 bisection per record length, at the same 12 PRNs and 15 flipped chips as the assignment.

### Minimal C/N0 per duration

`minimal C/N0` is the lowest value at which the criterion still holds; `first failure` is the next probe down, so the edge is bracketed between the two. The supplied recordings are 8 ms, marked on the figure.

| code periods | duration | minimal C/N0 | rate there | 95% interval | first failure |
| --- | --- | --- | --- | --- | --- |
| 2 | 2 ms | **55.9375 dB-Hz** | 95/100 = 95% | 89% to 98% | 55.7031 dB-Hz |
| 4 | 4 ms | **52.1875 dB-Hz** | 96/100 = 96% | 90% to 98% | 52.0312 dB-Hz |
| **8** | 8 ms | **49.375 dB-Hz** | 95/100 = 95% | 89% to 98% | 49.2188 dB-Hz |
| 16 | 16 ms | **45 dB-Hz** | 95/100 = 95% | 89% to 98% | 44.8438 dB-Hz |
| 32 | 32 ms | **42.5 dB-Hz** | 95/100 = 95% | 89% to 98% | 42.3438 dB-Hz |

From 2 to 32 code periods the floor moves 13.44 dB, which is **3.36 dB per doubling** of the record (3 dB is what perfect coherent combining of one more chip measurement per period would give).

### Scatter, C/N0 against duration

            2    4    8  * 16   32  
         dB-Hz                 code periods (1 ms each)
     70     #                      
   62.5     #                      
     60          #    #    #    #  
  58.75     #                      
 56.875     #                      
55.9375     #                      
55.7031     o                      
55.4688     o                      
     55     o    #                 
   52.5          #                 
52.1875          #                 
52.0312          o                 
 51.875          o                 
  51.25          o                 
     50          o    #    #    #  
 49.375               #            
49.2188               o            
49.0625               o            
  48.75               o            
   47.5               o            
     45               .    #    #  
44.8438                    o       
44.6875                    o       
 44.375                    o       
  43.75                    o       
   42.5                    .    #  
42.3438                         o  
42.1875                         o  
 41.875                         o  
  41.25                         o  
     40     .    .    .    .    .  

`#` at least 95 of 100 recover, `o` half to that, `.` below half, blank not probed.
`*` the supplied recordings: 8 ms, 8 code periods.

The same scatter as a picture, drawn once per page theme: [light](assets/cn0_vs_duration_light.svg), [dark](assets/cn0_vs_duration_dark.svg). The two horizontal bands on it are the C/N0 each supplied recording spans over its twelve PRNs (recording 1 54.1-54.9, recording 2 44.1-48 dB-Hz), measured with `python -m gnss.acquisition`.

### Cost

5 durations, 45 probes, 100 signals per probe: 4500 recordings scored in 81.1 min (1.08 s per recording).

