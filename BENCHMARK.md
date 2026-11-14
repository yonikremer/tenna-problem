# Benchmark: where the recovery breaks

Generated with `python benchmark.py`. Every recording is synthesised from the assignment's signal model, so the truth is known exactly and every run is scored against it: PRNs found, Doppler error, recovered shift, recovered flip set (precision/recall), and residual power against the generator's noise variance (1.000 is perfect cancellation).

Nothing here reads `gnss_observation.nc` or `gnss_observation2.nc`: these are fresh recordings, not the supplied pair. The `seed1`/`seed2` suffix is a noise seed - the same scenario generated twice with different Doppler, delay, carrier phase and flip positions, so the two rows show run-to-run scatter rather than one lucky draw.

`verdict` is `pass` only when every PRN was found with no false alarm, the shift is right, and the recovered flip set matches the truth exactly.

## Headline

- **Sensitivity.** Exact recovery down to about **47 dB-Hz** per PRN; below that the failures are flips. 12 PRNs at 55 dB-Hz is the assignment's case and it passes with margin.
- **How many chips are flipped.** Exact up to **K = 240** of 1023. At K = 320 the *shift* search is what fails first: it returns 684 instead of 2. With a third of the chips negative, a wrong shift also stacks flip signs, and the alignment score - an extreme-value statistic over the 15 most negative chips - stops isolating the true shift. At K = 500 only 0 of 12 PRNs are detected: a code modified on 1000 of its chips keeps 23/1023 of the nominal correlation, so a nominal replica barely sees it. Scoring shifts by held-out gain instead of the extreme-value score would push this limit up; it is not done, because the assignment lives at 15 flips.
- **Number of PRNs.** At 52 dB-Hz per PRN the combining gain is what decides: failures at [2, 4] PRNs, exact from 6 up (tested [2, 4, 6, 8, 10, 12]).
- **Record length.** 2 ms is not enough (failures: ['periods-2-seed1', 'periods-2-seed2']); 4 ms and longer are exact.
- **Fractional code phase** (non-integer sample delay): flips stay exact and the worst Doppler error is 3.88 Hz, but cancellation leaves 1.137 of the noise level behind at a half-sample chip offset, because the replica uses integer-sample rectangular chips. The flips do not care; a residual-power check does.
- **A navigation data bit flipping mid-record**: worst Doppler error 3.74 Hz over 4 runs. This case used to return ~100 Hz while claiming +-1.5 Hz; the sign change is now modelled, so it costs nothing.
- **Independent random flips per PRN** (no shared rule): the chain reports [0] chips at +0.000 to +0.000 dB held-out gain, so the evidence collapses to nothing and no rule is claimed.
- **No modification at all**: [0] chips reported at +0.000 to +0.000 dB, i.e. the search does not manufacture a rule out of noise.

## cn0

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cn0-70-seed1 | 12/12 | 1.39 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.014 | pass |
| cn0-70-seed2 | 12/12 | 1.33 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.038 | pass |
| cn0-65-seed1 | 12/12 | 1.76 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-65-seed2 | 12/12 | 1.31 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.012 | pass |
| cn0-60-seed1 | 12/12 | 2.52 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| cn0-60-seed2 | 12/12 | 1.41 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| cn0-57-seed1 | 12/12 | 3.24 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-57-seed2 | 12/12 | 2.00 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-55-seed1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-55-seed2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-53-seed1 | 12/12 | 4.69 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-53-seed2 | 12/12 | 1.93 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-51-seed1 | 12/12 | 5.71 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-51-seed2 | 12/12 | 2.65 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-49-seed1 | 12/12 | 6.99 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| cn0-49-seed2 | 12/12 | 3.41 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-47-seed1 | 12/12 | 8.49 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| cn0-47-seed2 | 12/12 | 4.38 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-45-seed1 | 12/12 | 10.26 Hz | 2 ok | 15/11 | 1.00 | 0.73 | 0.85 | 0.997 | flips |
| cn0-45-seed2 | 12/12 | 5.58 Hz | 2 ok | 15/13 | 0.92 | 0.80 | 0.86 | 1.001 | flips |

## flip_count

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flips-3-seed1 | 12/12 | 2.75 Hz | 2 ok | 3/3 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-3-seed2 | 12/12 | 2.06 Hz | 2 ok | 3/3 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-5-seed1 | 12/12 | 3.09 Hz | 2 ok | 5/5 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-5-seed2 | 12/12 | 2.64 Hz | 2 ok | 5/5 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-8-seed1 | 12/12 | 1.84 Hz | 2 ok | 8/8 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-8-seed2 | 12/12 | 3.56 Hz | 2 ok | 8/8 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-12-seed1 | 12/12 | 2.68 Hz | 2 ok | 12/12 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-12-seed2 | 12/12 | 4.25 Hz | 2 ok | 12/12 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-15-seed1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-15-seed2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-20-seed1 | 12/12 | 1.91 Hz | 2 ok | 20/20 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-20-seed2 | 12/12 | 3.24 Hz | 2 ok | 20/20 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-30-seed1 | 12/12 | 2.93 Hz | 2 ok | 30/30 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| flips-30-seed2 | 12/12 | 2.28 Hz | 2 ok | 30/30 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-40-seed1 | 12/12 | 3.02 Hz | 2 ok | 40/40 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-40-seed2 | 12/12 | 3.58 Hz | 2 ok | 40/40 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-60-seed1 | 12/12 | 5.25 Hz | 2 ok | 60/60 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-60-seed2 | 12/12 | 2.91 Hz | 2 ok | 60/60 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-80-seed1 | 12/12 | 2.93 Hz | 2 ok | 80/80 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-80-seed2 | 12/12 | 3.68 Hz | 2 ok | 80/80 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-120-seed1 | 12/12 | 4.95 Hz | 2 ok | 120/120 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-120-seed2 | 12/12 | 4.32 Hz | 2 ok | 120/120 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| flips-160-seed1 | 12/12 | 7.07 Hz | 2 ok | 160/160 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-160-seed2 | 12/12 | 5.54 Hz | 2 ok | 160/160 | 1.00 | 1.00 | 1.00 | 1.003 | pass |
| flips-240-seed1 | 12/12 | 7.12 Hz | 2 ok | 240/240 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| flips-240-seed2 | 12/12 | 7.46 Hz | 2 ok | 240/240 | 1.00 | 1.00 | 1.00 | 1.006 | pass |
| flips-320-seed1 | 12/12 | 13.30 Hz | 684 WRONG | 320/91 | 0.71 | 0.20 | 0.32 | 1.679 | slope |
| flips-320-seed2 | 12/12 | 17.18 Hz | 343 WRONG | 320/192 | 0.72 | 0.43 | 0.54 | 1.654 | slope |
| flips-400-seed1 | 6/12 | 9.45 Hz | 292 WRONG | 400/35 | 0.31 | 0.03 | 0.05 | 1.923 | detection |
| flips-400-seed2 | 4/12 | 8.00 Hz | 439 WRONG | 400/65 | 0.43 | 0.07 | 0.12 | 1.902 | detection |
| flips-500-seed1 | 0/12 | n/a | n/a | 500/n/a | n/a | n/a | n/a | n/a | detection |
| flips-500-seed2 | 0/12 | n/a | n/a | 500/n/a | n/a | n/a | n/a | n/a | detection |

## slope

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| slope-0-seed1 | 12/12 | 2.62 Hz | 0 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-0-seed2 | 12/12 | 1.60 Hz | 0 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-1-seed1 | 12/12 | 3.66 Hz | 1 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-1-seed2 | 12/12 | 1.74 Hz | 1 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-2-seed1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-2-seed2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-3-seed1 | 12/12 | 2.78 Hz | 3 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-3-seed2 | 12/12 | 1.87 Hz | 3 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-7-seed1 | 12/12 | 3.63 Hz | 7 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-7-seed2 | 12/12 | 2.29 Hz | 7 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-25-seed1 | 12/12 | 4.97 Hz | 25 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-25-seed2 | 12/12 | 2.31 Hz | 25 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |

## prns

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prns-2-seed1 | 2/2 | 2.10 Hz | 2 ok | 15/13 | 1.00 | 0.87 | 0.93 | 0.997 | partial |
| prns-2-seed2 | 2/2 | 1.49 Hz | 2 ok | 15/14 | 1.00 | 0.93 | 0.97 | 1.001 | partial |
| prns-4-seed1 | 4/4 | 4.44 Hz | 2 ok | 15/14 | 1.00 | 0.93 | 0.97 | 0.997 | partial |
| prns-4-seed2 | 4/4 | 2.39 Hz | 2 ok | 15/16 | 0.94 | 1.00 | 0.97 | 1.001 | partial |
| prns-6-seed1 | 6/6 | 3.06 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-6-seed2 | 6/6 | 2.41 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-8-seed1 | 8/8 | 1.40 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-8-seed2 | 8/8 | 2.49 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-10-seed1 | 10/10 | 7.00 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-10-seed2 | 10/10 | 1.64 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-12-seed1 | 12/12 | 5.17 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-12-seed2 | 12/12 | 2.32 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |

## duration

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| periods-2-seed1 | 12/12 | 32.34 Hz | 2 ok | 15/9 | 1.00 | 0.60 | 0.75 | 0.995 | flips |
| periods-2-seed2 | 12/12 | 20.55 Hz | 2 ok | 15/14 | 0.93 | 0.87 | 0.90 | 0.988 | flips |
| periods-4-seed1 | 12/12 | 4.31 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.986 | pass |
| periods-4-seed2 | 12/12 | 10.35 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| periods-8-seed1 | 12/12 | 5.17 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| periods-8-seed2 | 12/12 | 2.32 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| periods-16-seed1 | 12/12 | 1.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| periods-16-seed2 | 12/12 | 1.27 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |

## fractional_delay

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delay-0.0-seed1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| delay-0.0-seed2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| delay-0.25-seed1 | 12/12 | 3.55 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.034 | pass |
| delay-0.25-seed2 | 12/12 | 2.95 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.037 | pass |
| delay-0.5-seed1 | 12/12 | 3.03 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.136 | pass |
| delay-0.5-seed2 | 12/12 | 2.46 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.137 | pass |
| delay-0.75-seed1 | 12/12 | 2.58 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.036 | pass |
| delay-0.75-seed2 | 12/12 | 2.06 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.043 | pass |

## data_bit

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bit-None-55-seed1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-55-seed2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-None-52-seed1 | 12/12 | 5.17 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-52-seed2 | 12/12 | 2.32 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| bit-4-55-seed1 | 12/12 | 2.85 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-55-seed2 | 12/12 | 3.74 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-4-52-seed1 | 12/12 | 2.68 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-52-seed2 | 12/12 | 3.51 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |

## structure

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared-15-seed1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| shared-15-seed2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| independent-15-seed1 | 12/12 | 3.65 Hz | n/a | 15/0 | n/a | n/a | n/a | 1.053 | no-rule |
| independent-15-seed2 | 12/12 | 2.98 Hz | n/a | 15/0 | n/a | n/a | n/a | 1.057 | no-rule |
| none-0-seed1 | 12/12 | 1.60 Hz | n/a | 0/0 | n/a | n/a | n/a | 0.997 | no-rule |
| none-0-seed2 | 12/12 | 3.26 Hz | n/a | 0/0 | n/a | n/a | n/a | 1.002 | no-rule |

