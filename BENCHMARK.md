# Benchmark: where the recovery breaks

Generated with `python benchmark.py`. Every recording is synthesised from the assignment's signal model, so the truth is known exactly and every run is scored against it: PRNs found, Doppler error, recovered shift, recovered flip set (precision/recall), and the ratio of residual power to noise power (1.000 is perfect cancellation).

`verdict` is `pass` only when every PRN was found with no false alarm, the shift is right, and the recovered flip set matches the truth exactly.

## Headline

- **Sensitivity.** Exact recovery down to about **47 dB-Hz** per PRN; below that the failures are flips. 12 PRNs at 55 dB-Hz is the assignment's case and it passes with margin.
- **How many chips are flipped** is recovered exactly for every count tested, 3 to 40 chips out of 1023.
- **Number of PRNs.** At 52 dB-Hz per PRN the combining gain is what decides: failures at [2, 4] PRNs, exact from 6 up (tested [2, 4, 6, 8, 10, 12]).
- **Record length.** 2 ms is not enough (failures: ['periods-2-s1', 'periods-2-s2']); 4 ms and longer are exact.
- **Fractional code phase** (non-integer sample delay): flips stay exact and the worst Doppler error is 3.88 Hz, but cancellation leaves 1.137 of the noise level behind at a half-sample chip offset, because the replica uses integer-sample rectangular chips. The flips do not care; a residual-power check does.
- **A navigation data bit flipping mid-record**: worst Doppler error 3.74 Hz over 4 runs. This case used to return ~100 Hz while claiming +-1.5 Hz; the sign change is now modelled, so it costs nothing.
- **Independent random flips per PRN** (no shared rule): the chain reports [0] chips at +0.000 to +0.000 dB held-out gain, so the evidence collapses to nothing and no rule is claimed.
- **No modification at all**: [0] chips reported at +0.000 to +0.000 dB, i.e. the search does not manufacture a rule out of noise.

## cn0

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cn0-70-s1 | 12/12 | 1.39 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.014 | pass |
| cn0-70-s2 | 12/12 | 1.33 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.038 | pass |
| cn0-65-s1 | 12/12 | 1.76 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-65-s2 | 12/12 | 1.31 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.012 | pass |
| cn0-60-s1 | 12/12 | 2.52 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| cn0-60-s2 | 12/12 | 1.41 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.004 | pass |
| cn0-57-s1 | 12/12 | 3.24 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-57-s2 | 12/12 | 2.00 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-55-s1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-55-s2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| cn0-53-s1 | 12/12 | 4.69 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-53-s2 | 12/12 | 1.93 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-51-s1 | 12/12 | 5.71 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| cn0-51-s2 | 12/12 | 2.65 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-49-s1 | 12/12 | 6.99 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| cn0-49-s2 | 12/12 | 3.41 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-47-s1 | 12/12 | 8.49 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| cn0-47-s2 | 12/12 | 4.38 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| cn0-45-s1 | 12/12 | 10.26 Hz | 2 ok | 15/11 | 1.00 | 0.73 | 0.85 | 0.997 | flips |
| cn0-45-s2 | 12/12 | 5.58 Hz | 2 ok | 15/13 | 0.92 | 0.80 | 0.86 | 1.001 | flips |

## flip_count

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flips-3-s1 | 12/12 | 2.75 Hz | 2 ok | 3/3 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-3-s2 | 12/12 | 2.06 Hz | 2 ok | 3/3 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-5-s1 | 12/12 | 3.09 Hz | 2 ok | 5/5 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-5-s2 | 12/12 | 2.64 Hz | 2 ok | 5/5 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-8-s1 | 12/12 | 1.84 Hz | 2 ok | 8/8 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-8-s2 | 12/12 | 3.56 Hz | 2 ok | 8/8 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| flips-12-s1 | 12/12 | 2.68 Hz | 2 ok | 12/12 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-12-s2 | 12/12 | 4.25 Hz | 2 ok | 12/12 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-15-s1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-15-s2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-20-s1 | 12/12 | 1.91 Hz | 2 ok | 20/20 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| flips-20-s2 | 12/12 | 3.24 Hz | 2 ok | 20/20 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-30-s1 | 12/12 | 2.93 Hz | 2 ok | 30/30 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| flips-30-s2 | 12/12 | 2.28 Hz | 2 ok | 30/30 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| flips-40-s1 | 12/12 | 3.02 Hz | 2 ok | 40/40 | 1.00 | 1.00 | 1.00 | 0.998 | pass |
| flips-40-s2 | 12/12 | 3.58 Hz | 2 ok | 40/40 | 1.00 | 1.00 | 1.00 | 1.002 | pass |

## slope

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| slope-0-s1 | 12/12 | 2.62 Hz | 0 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-0-s2 | 12/12 | 1.60 Hz | 0 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-1-s1 | 12/12 | 3.66 Hz | 1 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-1-s2 | 12/12 | 1.74 Hz | 1 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-2-s1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-2-s2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-3-s1 | 12/12 | 2.78 Hz | 3 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-3-s2 | 12/12 | 1.87 Hz | 3 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-7-s1 | 12/12 | 3.63 Hz | 7 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-7-s2 | 12/12 | 2.29 Hz | 7 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| slope-25-s1 | 12/12 | 4.97 Hz | 25 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| slope-25-s2 | 12/12 | 2.31 Hz | 25 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |

## prns

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prns-2-s1 | 2/2 | 2.10 Hz | 2 ok | 15/13 | 1.00 | 0.87 | 0.93 | 0.997 | partial |
| prns-2-s2 | 2/2 | 1.49 Hz | 2 ok | 15/14 | 1.00 | 0.93 | 0.97 | 1.001 | partial |
| prns-4-s1 | 4/4 | 4.44 Hz | 2 ok | 15/14 | 1.00 | 0.93 | 0.97 | 0.997 | partial |
| prns-4-s2 | 4/4 | 2.39 Hz | 2 ok | 15/16 | 0.94 | 1.00 | 0.97 | 1.001 | partial |
| prns-6-s1 | 6/6 | 3.06 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-6-s2 | 6/6 | 2.41 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-8-s1 | 8/8 | 1.40 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |
| prns-8-s2 | 8/8 | 2.49 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-10-s1 | 10/10 | 7.00 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-10-s2 | 10/10 | 1.64 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| prns-12-s1 | 12/12 | 5.17 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| prns-12-s2 | 12/12 | 2.32 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |

## duration

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| periods-2-s1 | 12/12 | 32.34 Hz | 2 ok | 15/9 | 1.00 | 0.60 | 0.75 | 0.995 | flips |
| periods-2-s2 | 12/12 | 20.55 Hz | 2 ok | 15/14 | 0.93 | 0.87 | 0.90 | 0.988 | flips |
| periods-4-s1 | 12/12 | 4.31 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.986 | pass |
| periods-4-s2 | 12/12 | 10.35 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| periods-8-s1 | 12/12 | 5.17 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| periods-8-s2 | 12/12 | 2.32 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| periods-16-s1 | 12/12 | 1.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.999 | pass |
| periods-16-s2 | 12/12 | 1.27 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.996 | pass |

## fractional_delay

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delay-0.0-s1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| delay-0.0-s2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| delay-0.25-s1 | 12/12 | 3.55 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.034 | pass |
| delay-0.25-s2 | 12/12 | 2.95 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.037 | pass |
| delay-0.5-s1 | 12/12 | 3.03 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.136 | pass |
| delay-0.5-s2 | 12/12 | 2.46 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.137 | pass |
| delay-0.75-s1 | 12/12 | 2.58 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.036 | pass |
| delay-0.75-s2 | 12/12 | 2.06 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.043 | pass |

## data_bit

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bit-None-55-s1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-55-s2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-None-52-s1 | 12/12 | 5.17 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-None-52-s2 | 12/12 | 2.32 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |
| bit-4-55-s1 | 12/12 | 2.85 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-55-s2 | 12/12 | 3.74 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| bit-4-52-s1 | 12/12 | 2.68 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| bit-4-52-s2 | 12/12 | 3.51 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.001 | pass |

## structure

| scenario | detected | max doppler err | slope | K true/rec | precision | recall | f1 | residual/true noise | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shared-15-s1 | 12/12 | 3.88 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 0.997 | pass |
| shared-15-s2 | 12/12 | 2.54 Hz | 2 ok | 15/15 | 1.00 | 1.00 | 1.00 | 1.002 | pass |
| independent-15-s1 | 12/12 | 3.65 Hz | n/a | 15/0 | n/a | n/a | n/a | 1.053 | no-rule |
| independent-15-s2 | 12/12 | 2.98 Hz | n/a | 15/0 | n/a | n/a | n/a | 1.057 | no-rule |
| none-0-s1 | 12/12 | 1.60 Hz | n/a | 0/0 | n/a | n/a | n/a | 0.997 | no-rule |
| none-0-s2 | 12/12 | 3.26 Hz | n/a | 0/0 | n/a | n/a | n/a | 1.002 | no-rule |

