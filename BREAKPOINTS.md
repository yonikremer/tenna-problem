# Where the chain breaks, measured over independent signals

Generated with `python breakpoints.py --signals 100`. Each probe runs **100 independent recordings** (one per seed) at one value of one axis and counts how many recover exactly, then the value is bisected until the passing and breaking ends are one resolution apart. `benchmark.py` uses two seeds per point, which can only say 0/2, 1/2 or 2/2; this can say 91 of 100.

A signal counts as recovered when the verdict is `pass`: every PRN found with no false alarm, the shift right and the flip set exactly right. The criterion is **95 of 100** signals. Every probe reuses the same seeds, so adjacent probes differ in the parameter and not in the noise draw.

## Located edges

| axis | question | edge | rate at the edge | 95% interval | next value fails at |
| --- | --- | --- | --- | --- | --- |
| cn0 | lowest carrier-to-noise density per PRN that still recovers every chip | 49.375 dB-Hz | 95/100 = 95% | 89% to 98% | 49.2188 dB-Hz |
| flip_count | largest number of flipped chips per PRN that still recovers exactly | 140 chips | 97/100 = 97% | 92% to 99% | 144 chips |
| prns_low | fewest PRNs that still recover exactly (below it the combining gain is gone) | 7 PRNs | 99/100 = 99% | 95% to 100% | 6 PRNs |
| prns_high | most PRNs that still recover exactly (beyond it the noise floor moves) | 32 PRNs | 100/100 = 100% | 96% to 100% | 36 PRNs |
| doppler | largest Doppler the widened search still recovers (span widens to cover it) | **bracket wrong** | the declared bad end 120000 Hz still reached 100/100; the break is outside the bracket | | |
| duration | shortest record, in code periods, that still recovers exactly | 5 code periods | 98/100 = 98% | 93% to 99% | 4 code periods |

## cn0

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

**Edge between 49.375 and 49.2188 dB-Hz** (resolution 0.25, criterion 95%). Probes on this axis: 9, 912 s.

## flip_count

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

**Edge between 140 and 144 chips** (resolution 4, criterion 95%). Probes on this axis: 9, 957 s.

## prns_low

fewest PRNs that still recover exactly (below it the combining gain is gone)

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 12 PRNs (declared good) | 100/100 | 100% | 96% to 100% |
| 6 PRNs | 94/100 | 94% | 88% to 97% |
| 7 PRNs | 99/100 | 99% | 95% to 100% |
| 8 PRNs | 98/100 | 98% | 93% to 99% |
| 9 PRNs | 100/100 | 100% | 96% to 100% |
| 1 PRNs (declared bad) | 0/100 | 0% | 0% to 4% |

**Edge between 7 and 6 PRNs** (resolution 1, criterion 95%). Probes on this axis: 6, 425 s.

## prns_high

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

**Edge between 32 and 36 PRNs** (resolution 4, criterion 95%). Probes on this axis: 7, 2786 s.

## doppler

largest Doppler the widened search still recovers (span widens to cover it)

**Bracket wrong.** the declared bad end 120000 Hz still reached 100/100; the break is outside the bracket

## duration

shortest record, in code periods, that still recovers exactly

| value | recovered | rate | 95% interval |
| --- | --- | --- | --- |
| 8 code periods (declared good) | 100/100 | 100% | 96% to 100% |
| 4 code periods | 94/100 | 94% | 88% to 97% |
| 5 code periods | 98/100 | 98% | 93% to 99% |
| 6 code periods | 100/100 | 100% | 96% to 100% |
| 1 code periods (declared bad) | 0/100 | 0% | 0% to 4% |

**Edge between 5 and 4 code periods** (resolution 1, criterion 95%). Probes on this axis: 5, 340 s.

## Cost

6 axes, 38 probes, 100 signals per probe: 3800 recordings scored in 94.3 min (1.49 s per recording). This is the measured cost of the probes, including any reused from the cache; this run took 0.0 min of wall clock.

