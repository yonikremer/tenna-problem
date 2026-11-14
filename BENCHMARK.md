# Benchmark: where the recovery breaks

Generated with `python benchmark.py`. Every recording is synthesised from the assignment's signal model, so the truth is known exactly and every run is scored against it: PRNs found, Doppler error, recovered shift, recovered flip set (precision/recall), and residual power against the generator's noise variance (1.000 is perfect cancellation).

Nothing here reads `gnss_observation.nc` or `gnss_observation2.nc`: these are fresh recordings, not the supplied pair. The `seed1`/`seed2` suffix is a noise seed - the same scenario generated twice with different Doppler, delay, carrier phase and flip positions, so the two rows show run-to-run scatter rather than one lucky draw.

The tables for `prns` and `bit_probability` come from a separate run of the same script, made after the PRN range was extended to 210 and the per-PRN data-bit experiment was added; every other table is from the full run. Seeded generators make both runs reproducible.

`verdict` is `pass` only when every PRN was found with no false alarm, the shift is right, and the recovered flip set matches the truth exactly.

## Headline

- **Sensitivity.** Exact recovery down to about **47 dB-Hz** per PRN; below that the failures are flips. 12 PRNs at 55 dB-Hz is the assignment's case and it passes with margin. The 47 dB-Hz rows are two noise seeds, not a rate, so it was measured separately with `python -m analysis.weakest_chip`: 60 known-truth trials at **47.5 dB-Hz** recover the whole 15-chip mask in **57** of them (the other three return 14, 16 and 17), and the weakest truly flipped chip never read below +0.12 of its amplitude. At **55 dB-Hz** the same experiment is 30 of 30 with the weakest chip at +0.64. The 47 dB-Hz edge is real but better than two seeds suggested.
- **How many chips are flipped.** Every count up to **240** recovers exactly (at 200 one run came back 1 chip short). From 400 up, detection is what fails: 4 of 12 PRNs found at 400 chips, 0 of 12 at 500, because a code modified on 2K of its chips keeps (1023 - 2K)/1023 of the nominal correlation: 223/1023 at 400 and 23/1023 at 500.
- **Doppler.** None of the three fears holds. All 12 PRNs at 0 Hz, all within +-2 Hz and all within +-20 Hz recover exactly (zero 2/2, within-2hz 2/2, within-20hz 2/2, random-4000hz 2/2, fixed-5150hz 2/2, fixed-5500hz 2/2, fixed-5600hz 0/2, fixed-5800hz 0/2, fixed-20000hz 0/2): different spreading codes stay orthogonal even at identical Doppler, and cancellation removes what the codes do not. Large Doppler is a search-span question, not an algorithm one: the span is +-5175 Hz from the satellite's line-of-sight speed plus a 200 km/h receiver, the coarse grid reaches +-5000 Hz and the fine search adds +-500 Hz, so signals at +5500 Hz are still found and at +5800 Hz are not. Raise --max-speed-km-h if the receiver assumption is wrong; do not expect the search to guess outside the span it was given.
- **Large Doppler with the search widened to cover it.** Yes, it works: wide-6khz-default: 0/2 (span +-5175 Hz, 1.7 s); wide-6khz-wide: 2/2 (span +-6300 Hz, 2.7 s); wide-10khz-default: 0/2 (span +-5175 Hz, 1.7 s); wide-10khz-wide: 2/2 (span +-10500 Hz, 3.1 s); wide-15khz-default: 0/2 (span +-5175 Hz, 1.8 s); wide-15khz-wide: 2/2 (span +-15750 Hz, 3.4 s); wide-20khz-default: 0/2 (span +-5175 Hz, 1.9 s); wide-20khz-wide: 2/2 (span +-21000 Hz, 4.2 s); wide-30khz-default: 0/2 (span +-5175 Hz, 2.0 s); wide-30khz-wide: 2/2 (span +-31500 Hz, 4.4 s). Paying for the span costs search time and a little sensitivity, because the detection threshold grows with the number of cells searched (2**-t per cell, so four times the span costs about one more unit of peak-to-floor ratio); it does not cost correctness. Without widening, the same signals are invisible.
- **Dense modifications: a soft edge, not a threshold.** Passes per flip count over 6 seeds: {236: '0/6', 240: '4/6', 244: '0/6', 248: '0/6', 252: '2/6', 256: '0/6', 260: '0/6', 264: '1/6'}. The pattern is not monotonic, and that is the finding: which draw wins depends on where the random base lands, not on K alone, so there is no single flip count at which the method stops. What collapses is the shift margin - 0.016 to 0.250 when the shift is right, 0.001 to 0.198 when it is wrong - so the two populations overlap and the outcome turns on which alias fits. The wrong shifts are 343 and 684, about 1023/3 and 2*1023/3, where PRN rolls coincide. The assignment's 15 flips sits nowhere near this.
- **Number of PRNs.** At 52 dB-Hz per PRN: exact at [6, 7, 8, 9, 10, 12, 16, 20, 30], partial at [5, 40, 60], never recovered at [1, 2, 3, 4, 80, 120, 160, 210] (tested [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16, 20, 30, 40, 60, 80, 120, 160, 210]). One PRN cannot define a shift at all - there is nothing to relate it to - and the flip decisions need the sqrt(N) combining gain: 12 PRNs buy 10.8 dB where 4 buy 6 dB.
- **Data bits changing at random per PRN.** Over 16 runs, 76 of 192 PRN-records carried a transition inside the record, drawn with probability = record length / 20 ms, and the sign-pattern detector located 188 of them exactly. Runs that did not recover every chip: ['bitprob-2ms-52db-seed1', 'bitprob-2ms-52db-seed2', 'bitprob-4ms-52db-seed2']. At 2 ms the record holds two code periods, which is too few to fit a phase slope *and* locate a step, so a transition there costs the Doppler estimate (371 Hz error in one run) even though the chips survive.
- **Record length.** 2 ms is not enough (failures: ['periods-2-seed1', 'periods-2-seed2']); 4 ms and longer are exact.
- **Fractional code phase** (non-integer sample delay): flips stay exact and the worst Doppler error is 3.88 Hz, but cancellation leaves 1.137 of the noise level behind at a half-sample chip offset, because the replica uses integer-sample rectangular chips. The flips do not care; a residual-power check does.
- **A navigation data bit flipping mid-record**: worst Doppler error 3.74 Hz over 4 runs. This case used to return ~100 Hz while claiming +-1.5 Hz; the sign change is now modelled, so it costs nothing.
- **Independent random flips per PRN** (no shared rule): the chain reports [0] chips at +0.000 to +0.000 dB held-out gain, so the evidence collapses to nothing and no rule is claimed.
- **No modification at all**: [0] chips reported at +0.000 to +0.000 dB, i.e. the search does not manufacture a rule out of noise.

## cn0

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cn0-70-seed1 | 12/12 | 1.39 Hz | 2 ok | 5.846 | 15/15 | 1.00 | 1.00 | 1.00 | 1.014 | pass |
| cn0-70-seed2 | 12/12 | 1.33 Hz | 2 ok | 5.347 | 15/15 | 1.00 | 1.00 | 1.00 | 1.038 | pass |
| cn0-65-seed1 | 12/12 | 1.76 Hz | 2 ok | 5.700 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-65-seed2 | 12/12 | 1.31 Hz | 2 ok | 5.057 | 15/15 | 1.00 | 1.00 | 1.00 | 1.012 | pass |
| cn0-60-seed1 | 12/12 | 2.52 Hz | 2 ok | 5.299 | 15/15 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| cn0-60-seed2 | 12/12 | 1.41 Hz | 2 ok | 4.601 | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| cn0-57-seed1 | 12/12 | 3.24 Hz | 2 ok | 4.850 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-57-seed2 | 12/12 | 2.00 Hz | 2 ok | 4.142 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-55-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-55-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-53-seed1 | 12/12 | 4.69 Hz | 2 ok | 4.016 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-53-seed2 | 12/12 | 1.93 Hz | 2 ok | 3.127 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-51-seed1 | 12/12 | 5.71 Hz | 2 ok | 3.416 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-51-seed2 | 12/12 | 2.65 Hz | 2 ok | 2.600 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-49-seed1 | 12/12 | 6.99 Hz | 2 ok | 2.823 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| cn0-49-seed2 | 12/12 | 3.41 Hz | 2 ok | 1.983 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-47-seed1 | 12/12 | 8.49 Hz | 2 ok | 2.117 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| cn0-47-seed2 | 12/12 | 4.38 Hz | 2 ok | 1.395 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-45-seed1 | 12/12 | 10.26 Hz | 2 ok | 1.296 | 15/11 | 1.00 | 0.73 | 0.85 | 0.997 | flips |
| cn0-45-seed2 | 12/12 | 5.58 Hz | 2 ok | 0.825 | 15/13 | 0.92 | 0.80 | 0.86 | 1.001 | flips |

## flip_count

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flips-3-seed1 | 12/12 | 2.75 Hz | 2 ok | 1.222 | 3/3 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-3-seed2 | 12/12 | 2.06 Hz | 2 ok | 1.110 | 3/3 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-5-seed1 | 12/12 | 3.09 Hz | 2 ok | 1.791 | 5/5 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-5-seed2 | 12/12 | 2.64 Hz | 2 ok | 2.111 | 5/5 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-8-seed1 | 12/12 | 1.84 Hz | 2 ok | 2.595 | 8/8 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-8-seed2 | 12/12 | 3.56 Hz | 2 ok | 2.702 | 8/8 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-12-seed1 | 12/12 | 2.68 Hz | 2 ok | 3.571 | 12/12 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-12-seed2 | 12/12 | 4.25 Hz | 2 ok | 3.342 | 12/12 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-15-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-15-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-20-seed1 | 12/12 | 1.91 Hz | 2 ok | 4.027 | 20/20 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-20-seed2 | 12/12 | 3.24 Hz | 2 ok | 4.296 | 20/20 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-30-seed1 | 12/12 | 2.93 Hz | 2 ok | 2.465 | 30/30 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| flips-30-seed2 | 12/12 | 2.28 Hz | 2 ok | 2.912 | 30/30 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-40-seed1 | 12/12 | 3.02 Hz | 2 ok | 2.959 | 40/40 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-40-seed2 | 12/12 | 3.58 Hz | 2 ok | 3.142 | 40/40 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-60-seed1 | 12/12 | 5.25 Hz | 2 ok | 1.851 | 60/60 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-60-seed2 | 12/12 | 2.91 Hz | 2 ok | 1.903 | 60/60 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-80-seed1 | 12/12 | 2.93 Hz | 2 ok | 1.232 | 80/80 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-80-seed2 | 12/12 | 3.68 Hz | 2 ok | 1.355 | 80/80 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-120-seed1 | 12/12 | 4.95 Hz | 2 ok | 0.864 | 120/120 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-120-seed2 | 12/12 | 4.32 Hz | 2 ok | 0.533 | 120/120 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| flips-160-seed1 | 12/12 | 7.07 Hz | 2 ok | 0.422 | 160/160 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-160-seed2 | 12/12 | 5.54 Hz | 2 ok | 0.227 | 160/160 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| flips-200-seed1 | 12/12 | 4.00 Hz | 2 ok | 0.245 | 200/199 | 1.00 | 0.99 | 1.00 | 1.001 | partial |
| flips-200-seed2 | 12/12 | 8.55 Hz | 2 ok | 0.191 | 200/200 | 1.00 | 1.00 | 1.00 | 1.005 | pass |
| flips-230-seed1 | 12/12 | 7.49 Hz | 2 ok | 0.211 | 230/230 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-230-seed2 | 12/12 | 8.02 Hz | 2 ok | 0.103 | 230/230 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| flips-240-seed1 | 12/12 | 7.12 Hz | 2 ok | 0.250 | 240/240 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-240-seed2 | 12/12 | 7.46 Hz | 2 ok | 0.037 | 240/240 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| flips-320-seed1 | 12/12 | 13.30 Hz | 684 WRONG | 0.024 | 320/91 | 0.71 | 0.20 | 0.32 | 1.679 | slope |
| flips-320-seed2 | 12/12 | 17.18 Hz | 343 WRONG | 0.053 | 320/192 | 0.72 | 0.43 | 0.54 | 1.654 | slope |
| flips-400-seed1 | 6/12 | 9.45 Hz | 292 WRONG | 0.017 | 400/35 | 0.31 | 0.03 | 0.05 | 1.923 | detection |
| flips-400-seed2 | 4/12 | 8.00 Hz | 439 WRONG | 0.010 | 400/65 | 0.43 | 0.07 | 0.12 | 1.902 | detection |
| flips-500-seed1 | 0/12 | n/a | n/a | n/a | 500/n/a | n/a | n/a | n/a | n/a | detection |
| flips-500-seed2 | 0/12 | n/a | n/a | n/a | 500/n/a | n/a | n/a | n/a | n/a | detection |

## dense_flips

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dense-236-seed1 | 12/12 | 9.71 Hz | 343 WRONG | 0.042 | 236/137 | 0.69 | 0.40 | 0.51 | 1.528 | slope |
| dense-236-seed2 | 12/12 | 11.25 Hz | 343 WRONG | 0.026 | 236/145 | 0.66 | 0.41 | 0.50 | 1.517 | slope |
| dense-236-seed3 | 12/12 | 8.01 Hz | 2 ok | 0.198 | 236/235 | 1.00 | 1.00 | 1.00 | 1.014 | partial |
| dense-236-seed4 | 12/12 | 9.06 Hz | 343 WRONG | 0.057 | 236/97 | 0.75 | 0.31 | 0.44 | 1.539 | slope |
| dense-236-seed5 | 12/12 | 4.48 Hz | 684 WRONG | 0.003 | 236/102 | 0.67 | 0.29 | 0.40 | 1.550 | slope |
| dense-236-seed6 | 12/12 | 6.98 Hz | 343 WRONG | 0.124 | 236/104 | 0.63 | 0.28 | 0.39 | 1.559 | slope |
| dense-240-seed1 | 12/12 | 7.12 Hz | 2 ok | 0.250 | 240/240 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| dense-240-seed2 | 12/12 | 7.46 Hz | 2 ok | 0.037 | 240/240 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| dense-240-seed3 | 12/12 | 6.17 Hz | 2 ok | 0.016 | 240/240 | 1.00 | 1.00 | 1.00 | 1.009 | pass |
| dense-240-seed4 | 12/12 | 6.40 Hz | 343 WRONG | 0.006 | 240/103 | 0.71 | 0.30 | 0.43 | 1.546 | slope |
| dense-240-seed5 | 12/12 | 8.39 Hz | 2 ok | 0.022 | 240/240 | 1.00 | 1.00 | 1.00 | 0.995 | pass |
| dense-240-seed6 | 12/12 | 10.49 Hz | 684 WRONG | 0.080 | 240/50 | 0.70 | 0.15 | 0.24 | 1.579 | slope |
| dense-244-seed1 | 12/12 | 5.71 Hz | 343 WRONG | 0.035 | 244/134 | 0.71 | 0.39 | 0.50 | 1.536 | slope |
| dense-244-seed2 | 12/12 | 6.49 Hz | 343 WRONG | 0.071 | 244/108 | 0.72 | 0.32 | 0.44 | 1.549 | slope |
| dense-244-seed3 | 12/12 | 6.25 Hz | 343 WRONG | 0.065 | 244/149 | 0.68 | 0.41 | 0.51 | 1.555 | slope |
| dense-244-seed4 | 12/12 | 9.58 Hz | 343 WRONG | 0.004 | 244/107 | 0.71 | 0.31 | 0.43 | 1.550 | slope |
| dense-244-seed5 | 12/12 | 5.93 Hz | 684 WRONG | 0.082 | 244/15 | 0.93 | 0.06 | 0.11 | 1.631 | slope |
| dense-244-seed6 | 12/12 | 8.11 Hz | 343 WRONG | 0.023 | 244/135 | 0.67 | 0.37 | 0.47 | 1.551 | slope |
| dense-248-seed1 | 12/12 | 7.41 Hz | 343 WRONG | 0.055 | 248/109 | 0.76 | 0.33 | 0.46 | 1.555 | slope |
| dense-248-seed2 | 12/12 | 8.23 Hz | 684 WRONG | 0.020 | 248/116 | 0.74 | 0.35 | 0.47 | 1.564 | slope |
| dense-248-seed3 | 12/12 | 13.25 Hz | 343 WRONG | 0.103 | 248/17 | 1.00 | 0.07 | 0.13 | 1.660 | slope |
| dense-248-seed4 | 12/12 | 5.66 Hz | 343 WRONG | 0.020 | 248/86 | 0.77 | 0.27 | 0.40 | 1.581 | slope |
| dense-248-seed5 | 12/12 | 5.53 Hz | 343 WRONG | 0.004 | 248/131 | 0.65 | 0.34 | 0.45 | 1.544 | slope |
| dense-248-seed6 | 12/12 +1 | 7.36 Hz | 2 ok | 0.087 | 248/248 | 1.00 | 1.00 | 1.00 | 1.002 | detection |
| dense-252-seed1 | 12/12 | 11.15 Hz | 343 WRONG | 0.004 | 252/71 | 0.70 | 0.20 | 0.31 | 1.602 | slope |
| dense-252-seed2 | 12/12 | 7.79 Hz | 567 WRONG | 0.014 | 252/11 | 0.73 | 0.03 | 0.06 | 1.658 | slope |
| dense-252-seed3 | 12/12 | 6.50 Hz | 684 WRONG | 0.030 | 252/35 | 0.83 | 0.12 | 0.20 | 1.643 | slope |
| dense-252-seed4 | 12/12 | 8.16 Hz | 2 ok | 0.156 | 252/252 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| dense-252-seed5 | 12/12 | 5.06 Hz | 343 WRONG | 0.025 | 252/167 | 0.60 | 0.40 | 0.48 | 1.569 | slope |
| dense-252-seed6 | 12/12 | 8.69 Hz | 2 ok | 0.039 | 252/252 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| dense-256-seed1 | 12/12 | 6.19 Hz | 343 WRONG | 0.003 | 256/164 | 0.71 | 0.46 | 0.56 | 1.541 | slope |
| dense-256-seed2 | 12/12 | 7.61 Hz | 684 WRONG | 0.012 | 256/92 | 0.66 | 0.24 | 0.35 | 1.574 | slope |
| dense-256-seed3 | 12/12 | 7.56 Hz | 343 WRONG | 0.137 | 256/209 | 0.64 | 0.52 | 0.58 | 1.541 | slope |
| dense-256-seed4 | 12/12 | 10.35 Hz | 698 WRONG | 0.019 | 256/12 | 0.58 | 0.03 | 0.05 | 1.686 | slope |
| dense-256-seed5 | 12/12 | 9.64 Hz | 684 WRONG | 0.037 | 256/87 | 0.74 | 0.25 | 0.37 | 1.581 | slope |
| dense-256-seed6 | 12/12 | 6.38 Hz | 684 WRONG | 0.028 | 256/114 | 0.74 | 0.33 | 0.45 | 1.559 | slope |
| dense-260-seed1 | 12/12 | 10.89 Hz | 684 WRONG | 0.014 | 260/98 | 0.69 | 0.26 | 0.38 | 1.594 | slope |
| dense-260-seed2 | 12/12 | 9.59 Hz | 343 WRONG | 0.021 | 260/15 | 0.93 | 0.05 | 0.10 | 1.683 | slope |
| dense-260-seed3 | 12/12 | 7.31 Hz | 343 WRONG | 0.010 | 260/80 | 0.62 | 0.19 | 0.29 | 1.598 | slope |
| dense-260-seed4 | 12/12 | 7.01 Hz | 684 WRONG | 0.012 | 260/116 | 0.74 | 0.33 | 0.46 | 1.579 | slope |
| dense-260-seed5 | 12/12 | 6.16 Hz | 343 WRONG | 0.001 | 260/157 | 0.66 | 0.40 | 0.49 | 1.549 | slope |
| dense-260-seed6 | 12/12 | 7.28 Hz | 343 WRONG | 0.003 | 260/140 | 0.70 | 0.38 | 0.49 | 1.555 | slope |
| dense-264-seed1 | 12/12 | 5.73 Hz | 684 WRONG | 0.027 | 264/156 | 0.68 | 0.40 | 0.50 | 1.588 | slope |
| dense-264-seed2 | 12/12 | 7.72 Hz | 684 WRONG | 0.058 | 264/70 | 0.66 | 0.17 | 0.28 | 1.611 | slope |
| dense-264-seed3 | 12/12 | 6.31 Hz | 684 WRONG | 0.002 | 264/136 | 0.71 | 0.37 | 0.49 | 1.572 | slope |
| dense-264-seed4 | 12/12 | 7.93 Hz | 684 WRONG | 0.035 | 264/139 | 0.71 | 0.37 | 0.49 | 1.593 | slope |
| dense-264-seed5 | 12/12 | 8.14 Hz | 2 ok | 0.041 | 264/264 | 1.00 | 1.00 | 1.00 | 0.993 | pass |
| dense-264-seed6 | 12/12 | 4.42 Hz | 343 WRONG | 0.029 | 264/84 | 0.76 | 0.24 | 0.37 | 1.621 | slope |

## doppler

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| doppler-zero-seed1 | 12/12 | 2.25 Hz | 2 ok | 3.762 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| doppler-zero-seed2 | 12/12 | 3.27 Hz | 2 ok | 3.154 | 15/15 | 1.00 | 1.00 | 1.00 | 1.007 | pass |
| doppler-within-2hz-seed1 | 12/12 | 1.90 Hz | 2 ok | 3.610 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-within-2hz-seed2 | 12/12 | 2.59 Hz | 2 ok | 3.431 | 15/15 | 1.00 | 1.00 | 1.00 | 1.007 | pass |
| doppler-within-20hz-seed1 | 12/12 | 2.24 Hz | 2 ok | 3.610 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-within-20hz-seed2 | 12/12 | 2.32 Hz | 2 ok | 3.458 | 15/15 | 1.00 | 1.00 | 1.00 | 1.008 | pass |
| doppler-random-4000hz-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| doppler-random-4000hz-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-fixed-5150hz-seed1 | 12/12 | 1.85 Hz | 2 ok | 4.237 | 15/15 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| doppler-fixed-5150hz-seed2 | 12/12 | 2.60 Hz | 2 ok | 3.703 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| doppler-fixed-5500hz-seed1 | 12/12 | 2.51 Hz | 2 ok | 3.800 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| doppler-fixed-5500hz-seed2 | 12/12 | 1.93 Hz | 2 ok | 3.272 | 15/15 | 1.00 | 1.00 | 1.00 | 1.005 | pass |
| doppler-fixed-5600hz-seed1 | 11/12 | 3.35 Hz | 2 ok | 3.367 | 15/15 | 1.00 | 1.00 | 1.00 | 1.075 | detection |
| doppler-fixed-5600hz-seed2 | 12/12 | 105.59 Hz | 2 ok | 2.862 | 15/14 | 1.00 | 0.93 | 0.97 | 1.039 | partial |
| doppler-fixed-5800hz-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| doppler-fixed-5800hz-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| doppler-fixed-20000hz-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| doppler-fixed-20000hz-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |

## wide_doppler

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| wide-6khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-6khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-6khz-wide-seed1 | 12/12 | 2.25 Hz | 2 ok | 3.633 | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| wide-6khz-wide-seed2 | 12/12 | 2.81 Hz | 2 ok | 3.200 | 15/15 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| wide-10khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-10khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-10khz-wide-seed1 | 12/12 | 1.88 Hz | 2 ok | 3.720 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| wide-10khz-wide-seed2 | 12/12 | 3.07 Hz | 2 ok | 3.049 | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| wide-15khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-15khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-15khz-wide-seed1 | 12/12 | 2.31 Hz | 2 ok | 3.636 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| wide-15khz-wide-seed2 | 12/12 | 3.39 Hz | 2 ok | 2.860 | 15/15 | 1.00 | 1.00 | 1.00 | 1.007 | pass |
| wide-20khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-20khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-20khz-wide-seed1 | 12/12 | 1.37 Hz | 2 ok | 3.626 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| wide-20khz-wide-seed2 | 12/12 | 2.16 Hz | 2 ok | 3.225 | 15/15 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| wide-30khz-default-seed1 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-30khz-default-seed2 | 0/12 | n/a | n/a | n/a | 15/n/a | n/a | n/a | n/a | n/a | detection |
| wide-30khz-wide-seed1 | 12/12 | 3.06 Hz | 2 ok | 3.449 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| wide-30khz-wide-seed2 | 12/12 | 1.73 Hz | 2 ok | 2.887 | 15/15 | 1.00 | 1.00 | 1.00 | 1.005 | pass |

## slope

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| slope-0-seed1 | 12/12 | 2.62 Hz | 0 ok | 4.450 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-0-seed2 | 12/12 | 1.60 Hz | 0 ok | 3.814 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-1-seed1 | 12/12 | 3.66 Hz | 1 ok | 4.183 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-1-seed2 | 12/12 | 1.74 Hz | 1 ok | 3.641 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-2-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-2-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-3-seed1 | 12/12 | 2.78 Hz | 3 ok | 4.465 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-3-seed2 | 12/12 | 1.87 Hz | 3 ok | 3.993 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-7-seed1 | 12/12 | 3.63 Hz | 7 ok | 4.112 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-7-seed2 | 12/12 | 2.29 Hz | 7 ok | 3.827 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-25-seed1 | 12/12 | 4.97 Hz | 25 ok | 4.090 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-25-seed2 | 12/12 | 2.31 Hz | 25 ok | 4.010 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |

## prns

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prns-1-seed1 | 1/1 | 0.02 Hz | 0 WRONG | 0.000 | 15/0 | 0.00 | 0.00 | 0.00 | 0.999 | slope |
| prns-1-seed2 | 1/1 | 1.04 Hz | 0 WRONG | 0.000 | 15/0 | 0.00 | 0.00 | 0.00 | 1.004 | slope |
| prns-2-seed1 | 2/2 | 2.10 Hz | 2 ok | 0.534 | 15/13 | 1.00 | 0.87 | 0.93 | 0.997 | partial |
| prns-2-seed2 | 2/2 | 1.49 Hz | 2 ok | 0.610 | 15/14 | 1.00 | 0.93 | 0.97 | 1.001 | partial |
| prns-3-seed1 | 3/3 | 2.45 Hz | 2 ok | 0.869 | 15/12 | 1.00 | 0.80 | 0.89 | 0.997 | flips |
| prns-3-seed2 | 3/3 | 5.78 Hz | 2 ok | 1.149 | 15/14 | 1.00 | 0.93 | 0.97 | 1.001 | partial |
| prns-4-seed1 | 4/4 | 4.44 Hz | 2 ok | 1.575 | 15/14 | 1.00 | 0.93 | 0.97 | 0.997 | partial |
| prns-4-seed2 | 4/4 | 2.39 Hz | 2 ok | 1.510 | 15/16 | 0.94 | 1.00 | 0.97 | 1.001 | partial |
| prns-5-seed1 | 5/5 | 2.46 Hz | 2 ok | 2.235 | 15/14 | 1.00 | 0.93 | 0.97 | 0.997 | partial |
| prns-5-seed2 | 5/5 | 1.77 Hz | 2 ok | 2.167 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-6-seed1 | 6/6 | 3.06 Hz | 2 ok | 2.803 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-6-seed2 | 6/6 | 2.41 Hz | 2 ok | 2.326 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-7-seed1 | 7/7 | 3.66 Hz | 2 ok | 2.810 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-7-seed2 | 7/7 | 1.61 Hz | 2 ok | 2.500 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-8-seed1 | 8/8 | 1.40 Hz | 2 ok | 3.114 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-8-seed2 | 8/8 | 2.49 Hz | 2 ok | 2.315 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-9-seed1 | 9/9 | 2.98 Hz | 2 ok | 3.082 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-9-seed2 | 9/9 | 3.08 Hz | 2 ok | 2.946 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-10-seed1 | 10/10 | 7.00 Hz | 2 ok | 2.924 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-10-seed2 | 10/10 | 1.64 Hz | 2 ok | 3.034 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-12-seed1 | 12/12 | 5.17 Hz | 2 ok | 3.699 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-12-seed2 | 12/12 | 2.32 Hz | 2 ok | 2.869 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-16-seed1 | 16/16 | 5.14 Hz | 2 ok | 4.024 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-16-seed2 | 16/16 | 3.75 Hz | 2 ok | 3.673 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| prns-20-seed1 | 20/20 | 6.13 Hz | 2 ok | 4.220 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-20-seed2 | 20/20 | 3.29 Hz | 2 ok | 3.685 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| prns-30-seed1 | 30/30 | 5.20 Hz | 2 ok | 4.622 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-30-seed2 | 30/30 | 2.96 Hz | 2 ok | 3.939 | 15/15 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| prns-40-seed1 | 40/40 | 6586.25 Hz | 2 ok | 4.766 | 15/15 | 1.00 | 1.00 | 1.00 | 1.072 | pass |
| prns-40-seed2 | 38/40 | 3.40 Hz | 2 ok | 4.056 | 15/15 | 1.00 | 1.00 | 1.00 | 1.081 | detection |
| prns-60-seed1 | 60/60 | 6586.59 Hz | 2 ok | 5.021 | 15/15 | 1.00 | 1.00 | 1.00 | 1.080 | pass |
| prns-60-seed2 | 58/60 | 4.63 Hz | 2 ok | 4.403 | 15/15 | 1.00 | 1.00 | 1.00 | 1.087 | detection |
| prns-80-seed1 | 78/80 | 4.03 Hz | 2 ok | 5.256 | 15/15 | 1.00 | 1.00 | 1.00 | 1.091 | detection |
| prns-80-seed2 | 78/80 | 6.21 Hz | 2 ok | 4.497 | 15/15 | 1.00 | 1.00 | 1.00 | 1.094 | detection |
| prns-120-seed1 | 118/120 | 10.64 Hz | 2 ok | 5.303 | 15/12 | 1.00 | 0.80 | 0.89 | 1.245 | detection |
| prns-120-seed2 | 118/120 | 11.16 Hz | 2 ok | 4.867 | 15/15 | 1.00 | 1.00 | 1.00 | 1.161 | detection |
| prns-160-seed1 | 158/160 | 10.80 Hz | 2 ok | 5.185 | 15/15 | 1.00 | 1.00 | 1.00 | 1.466 | detection |
| prns-160-seed2 | 158/160 | 12.39 Hz | 2 ok | 4.447 | 15/15 | 1.00 | 1.00 | 1.00 | 1.617 | detection |
| prns-210-seed1 | 197/210 | 11.60 Hz | 2 ok | 4.383 | 15/7 | 1.00 | 0.47 | 0.64 | 3.176 | detection |
| prns-210-seed2 | 202/210 | 11.56 Hz | 2 ok | 3.796 | 15/3 | 1.00 | 0.20 | 0.33 | 3.073 | detection |
## bit_probability

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bitprob-2ms-55db-seed1 | 12/12 | 19.82 Hz | 2 ok | 2.541 | 15/15 | 1.00 | 1.00 | 1.00 | 0.991 | pass |
| bitprob-2ms-55db-seed2 | 12/12 | 371.73 Hz | 2 ok | 1.965 | 15/15 | 1.00 | 1.00 | 1.00 | 1.064 | pass |
| bitprob-2ms-52db-seed1 | 12/12 | 23.10 Hz | 2 ok | 1.442 | 15/17 | 0.88 | 1.00 | 0.94 | 0.990 | partial |
| bitprob-2ms-52db-seed2 | 12/12 | 369.21 Hz | 2 ok | 1.140 | 15/14 | 0.93 | 0.87 | 0.90 | 1.026 | flips |
| bitprob-4ms-55db-seed1 | 12/12 | 8.51 Hz | 2 ok | 3.356 | 15/15 | 1.00 | 1.00 | 1.00 | 0.987 | pass |
| bitprob-4ms-55db-seed2 | 12/12 | 13.50 Hz | 2 ok | 2.963 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bitprob-4ms-52db-seed1 | 12/12 | 9.75 Hz | 2 ok | 2.510 | 15/15 | 1.00 | 1.00 | 1.00 | 0.986 | pass |
| bitprob-4ms-52db-seed2 | 12/12 | 17.90 Hz | 2 ok | 2.264 | 15/14 | 1.00 | 0.93 | 0.97 | 1.003 | partial |
| bitprob-8ms-55db-seed1 | 12/12 | 2.52 Hz | 2 ok | 4.513 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bitprob-8ms-55db-seed2 | 12/12 | 3.83 Hz | 2 ok | 3.727 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bitprob-8ms-52db-seed1 | 12/12 | 3.26 Hz | 2 ok | 3.700 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| bitprob-8ms-52db-seed2 | 12/12 | 4.68 Hz | 2 ok | 3.016 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| bitprob-16ms-55db-seed1 | 12/12 | 0.91 Hz | 2 ok | 5.121 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| bitprob-16ms-55db-seed2 | 12/12 | 0.95 Hz | 2 ok | 4.255 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bitprob-16ms-52db-seed1 | 12/12 | 1.13 Hz | 2 ok | 4.418 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| bitprob-16ms-52db-seed2 | 12/12 | 1.11 Hz | 2 ok | 3.665 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |


## duration

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| periods-2-seed1 | 12/12 | 32.34 Hz | 2 ok | 1.104 | 15/9 | 1.00 | 0.60 | 0.75 | 0.995 | flips |
| periods-2-seed2 | 12/12 | 20.55 Hz | 2 ok | 0.897 | 15/14 | 0.93 | 0.87 | 0.90 | 0.988 | flips |
| periods-4-seed1 | 12/12 | 4.31 Hz | 2 ok | 2.486 | 15/15 | 1.00 | 1.00 | 1.00 | 0.986 | pass |
| periods-4-seed2 | 12/12 | 10.35 Hz | 2 ok | 2.545 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| periods-8-seed1 | 12/12 | 5.17 Hz | 2 ok | 3.699 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| periods-8-seed2 | 12/12 | 2.32 Hz | 2 ok | 2.869 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| periods-16-seed1 | 12/12 | 1.54 Hz | 2 ok | 4.229 | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| periods-16-seed2 | 12/12 | 1.27 Hz | 2 ok | 3.919 | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |

## fractional_delay

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delay-0.0-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| delay-0.0-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| delay-0.25-seed1 | 12/12 | 3.55 Hz | 2 ok | 4.295 | 15/15 | 1.00 | 1.00 | 1.00 | 1.034 | pass |
| delay-0.25-seed2 | 12/12 | 2.95 Hz | 2 ok | 3.741 | 15/15 | 1.00 | 1.00 | 1.00 | 1.037 | pass |
| delay-0.5-seed1 | 12/12 | 3.03 Hz | 2 ok | 3.940 | 15/15 | 1.00 | 1.00 | 1.00 | 1.136 | pass |
| delay-0.5-seed2 | 12/12 | 2.46 Hz | 2 ok | 3.551 | 15/15 | 1.00 | 1.00 | 1.00 | 1.137 | pass |
| delay-0.75-seed1 | 12/12 | 2.58 Hz | 2 ok | 4.370 | 15/15 | 1.00 | 1.00 | 1.00 | 1.036 | pass |
| delay-0.75-seed2 | 12/12 | 2.06 Hz | 2 ok | 3.664 | 15/15 | 1.00 | 1.00 | 1.00 | 1.043 | pass |

## data_bit

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bit-None-55-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-55-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-None-52-seed1 | 12/12 | 5.17 Hz | 2 ok | 3.699 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-52-seed2 | 12/12 | 2.32 Hz | 2 ok | 2.869 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| bit-4-55-seed1 | 12/12 | 2.85 Hz | 2 ok | 4.374 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-55-seed2 | 12/12 | 3.74 Hz | 2 ok | 3.882 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-4-52-seed1 | 12/12 | 2.68 Hz | 2 ok | 3.596 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-52-seed2 | 12/12 | 3.51 Hz | 2 ok | 3.115 | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |

## structure

| scenario | detected | max doppler err | slope | margin | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared-15-seed1 | 12/12 | 3.88 Hz | 2 ok | 4.404 | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| shared-15-seed2 | 12/12 | 2.54 Hz | 2 ok | 3.616 | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| independent-15-seed1 | 12/12 | 3.65 Hz | n/a | 0.016 | 15/0 | n/a | n/a | n/a | 1.053 | no-rule |
| independent-15-seed2 | 12/12 | 2.98 Hz | n/a | 0.134 | 15/0 | n/a | n/a | n/a | 1.057 | no-rule |
| none-0-seed1 | 12/12 | 1.60 Hz | n/a | 0.189 | 0/0 | n/a | n/a | n/a | 0.997 | no-rule |
| none-0-seed2 | 12/12 | 3.26 Hz | n/a | 0.054 | 0/0 | n/a | n/a | n/a | 1.002 | no-rule |

