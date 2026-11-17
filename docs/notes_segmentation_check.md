# Checked and disproved: "the code-period segments are the same for every satellite"

## The claim

When cutting an 8 ms recording into code-period segments for the data-bit test, one could assume a
single segmentation can be shared by all satellites, because they are received through one channel.

## Why it cannot be true

Each satellite arrives with its own code phase. The correlation peak of satellite *p* sits at its own
delay, so its code-period boundaries fall at

```text
boundary(k) = ceil(phase_p) + k * samples_per_code_period
```

with `phase_p` different for every satellite. Measured on `gnss_observation.nc`, the twelve code
phases are 31.24, 109.24, 188.25, 274.25, 351.26, 438.00, 522.00, 604.00, 687.00, 771.00, 854.25 and
946.01 chips — twelve different boundary sets, starting 125, 437, 753 ... 3784 samples into the
record.

## The measurement that settles it

Segment amplitude is a direct indicator of correct alignment: cut at the right boundaries and each
segment sums coherently to the full per-sample amplitude (about 0.27); cut at the wrong ones and the
sum straddles two code periods and collapses.

| satellite | boundaries used | mean segment amplitude |
| --- | --- | --- |
| 1 | its own | 0.281 |
| 2 | its own | 0.258 |
| 2 | satellite 1's | 0.051 |
| 3 | its own | 0.263 |
| 3 | satellite 1's | 0.038 |
| 6 | its own | 0.282 |
| 6 | satellite 1's | 0.041 |
| 12 | its own | 0.271 |
| 12 | satellite 1's | 0.037 |

Using one satellite's boundaries for the others costs a factor of about six in amplitude, so a shared
segmentation would have destroyed the sensitivity of the data-bit test. Per-satellite segmentation is
therefore required, and is what the code does.

## Second finding: the number of segments is not always nine

A record that starts mid-period yields

```text
partial | full | full | full | full | full | full | full | partial   -> 9 segments, 8 boundaries
```

but a record that starts on a code boundary has no leading partial segment:

```text
full | full | full | full | full | full | full | full              -> 8 segments, 7 boundaries
```

Verified by injection with measured amplitudes 0.275-0.281 in every case:

| injected code phase (samples) | segments | boundaries |
| --- | --- | --- |
| 0 | 8 | 7 |
| 1 | 8 | 7 |
| 512 | 9 | 8 |
| 2046 | 9 | 8 |
| 4091 | 9 | 8 |

Both files happen to contain only code phases of 124 samples or more, so both give 9 segments and 8
boundaries. The 8/7 path exists, is handled, and is now covered by the script's self-check rather than
assumed.

## Consequence for the data-bit result

The "no data-bit change" verdict for all 24 satellite-checks stands: each was computed on that
satellite's own segmentation. What changed is that the per-satellite requirement is now demonstrated
with numbers instead of merely implemented.

## Where this is implemented

- `gnss/alignment.py`, functions `alignment_shift`, `refine_alignment`,
  `code_period_segments`
- self-check covers code phases 0, 1, 512, 2046, 4091 and injected data-bit changes at boundaries 2, 5
  and 8
