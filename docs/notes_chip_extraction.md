# Chip extraction and the 15-flip question

## Pipeline (`gnss/chips.py`)

For each detected satellite:

1. Sharpened Doppler from the phase slope across code periods (uncertainty 1.4-2 Hz in observation 1).
2. Wipe the carrier, then wipe that satellite's NOMINAL spreading code, leaving `+amplitude` where the
   received chip matches the nominal code and `-amplitude` where it was modified.
3. Average the 8 occurrences of each chip coherently, sampling the chip centre (the two middle of the
   four samples per chip). Whole-chip averaging is also computed and agrees.
4. Rotate out the residual phase, then take the sign.
5. Relabel from record position to code coordinate: position `m` inside a period holds code chip
   `(m - phase/4) mod 1023`, because the replica starts at that satellite's own code phase.

Output: `gnss_observation_chips.csv` and `gnss_observation2_chips.csv`, 12 satellites x 1023 chips.

## Per-chip signal-to-noise, measured not assumed

    signal per chip  = amplitude x 32 samples
    noise per chip   = sqrt(1.051 / 32) = 0.181   (observation 1)
    interference from the other 11 codes, per chip = 0.28 measured with a control code

Control experiment: run the same processing with code 17, which is not in the recording. If the other
codes cancelled properly it should give noise only, predicted 0.181. Measured mean |chip| = 0.337,
i.e. excess power 0.28. So the other codes are NOT cancelled below the noise level: dividing by 32
samples reduces them by sqrt(32) only, since spreading codes are orthogonal over a full 1023-chip
period, not over 32 samples.

Consequence: per-chip signal-to-noise is 0.278 / sqrt(0.181^2 + 0.28^2) = 0.83, so a single chip's
sign is decided correctly only about 70-75% of the time. Individual flipped chips cannot be located
in one satellite.

## The 15-flip claim, tested without locating positions

A flipped chip contributes `-amplitude` instead of `+amplitude`, so N flipped chips lower the mean chip
value by `2N/1023`. Measured per satellite and calibrated by Monte Carlo at the measured amplitude and
noise:

| quantity | observation 1 |
| --- | --- |
| measured amplitude per chip | 0.267 |
| measured spread of positive chips | 0.185 |
| Monte Carlo, true flips = 0 | -0.0 +- 5.9 flips |
| Monte Carlo, true flips = 15 | 14.8 +- 5.8 flips |
| measured, 12-satellite mean | **18.0 +- 3.0 flips** |

So observation 1 is consistent with about 15 modified chips per code (1.9 standard deviations high)
and inconsistent with no modification at all (10.6 standard deviations). The count is supported; the
positions are not recoverable at this signal-to-noise.

Observation 2 cannot answer the question with this test: its per-chip amplitude is 0.110 against
0.177 noise, so the estimator is biased upward regardless of the truth.

## Cross-satellite structure: not common positions

If the same chip positions were flipped in every satellite, summed vectors would show 15 entries near
-12 x amplitude against a spread of sqrt(12) x 0.18 = 0.63, i.e. unmistakable.

- Consensus over all 12 satellites: 0 chips negative, at every one of the 1023 circular shifts.
- Best pairwise alignment between any two satellites: 80-86% sign agreement, which is what two
  independent noise-dominated patterns give by chance, at arbitrary shifts.

Conclusion: the modified positions are not shared across satellites in code coordinates. Any rule must
therefore be tested as a hypothesis on the 1023 soft chip values, not discovered by averaging.

## Interference cancellation (`analysis/interference_cancellation.py`)

Every detected satellite is described by its Doppler, code phase and one complex amplitude, all
estimated over 32,736 samples rather than 32. Reconstruct all of them, subtract, and the residual is
noise:

| | observation 1 | observation 2 |
| --- | --- | --- |
| received power | 1.9135 | 1.1419 |
| after subtracting all satellites | 1.0422 | 1.0052 |
| noise variance | 1.051 | 1.006 |
| power removed | 45.5% | 12.0% |

The residual equals the noise variance to within 1%, so all twelve satellites are reconstructed to
about 1% - independent confirmation of every estimated Doppler, code phase and amplitude.

Per-chip effect: spread 0.188 -> 0.124 in observation 1, and 0.124 is exactly the thermal limit
sqrt(1.05/32). Per-chip signal-to-noise rises from about 1.5 to 2.2, so a single chip's sign is decided
correctly 98.5% of the time instead of 92%.

Effect on the 15-flip count:

| measurement | before cancellation | after cancellation |
| --- | --- | --- |
| per-satellite estimate | 18.0 +- 5.9 | 14.8 +- 4.0 |
| 12-satellite mean | 18.0 +- 3.0 | **14.8 +- 1.0** |
| Monte Carlo, truth 15 | 14.8 +- 5.8 | 14.9 +- 4.0 |

So cancellation tightens the count by a factor of three and the answer is 15 modified chips per code.

Control after cancellation: reading an absent code on the cleaned signal gives mean |value| 0.227,
against 0.226 predicted for pure complex Gaussian noise. The other satellites' contributions, measured
at 0.28 per chip before cancellation, are gone.

Consensus after cancellation: spread 0.480 against 0.443 expected from noise alone, and **zero chips
below two standard deviations** in either file. Had the 15 modified positions been shared by the
twelve satellites they would sit at -12 x amplitude, about -7 standard deviations, and be impossible
to miss. They are therefore not shared: the common element is the rule, not the positions.

## Correction after the synthetic test pass

`chip_vector` had two defects: the chip relabelling roll went the wrong way, and the two centre
samples were hard-coded to record slots 1 and 2, which only works when the code delay is a whole
number of chips. Both are fixed in `gnss/chips.py`: values are now read at each chip's midpoint
relative to the measured code phase, and the result is already in code coordinates.

Numbers in this note that depend on per-chip values were measured before that fix. Re-running on
`gnss_observation.nc` now gives amplitude about 0.295 per chip (was 0.267), spread about 0.18
(predicted 0.181), and a control-code mean of 0.337. The count-based conclusions (about 15 modified
chips, not shared across satellites) are unchanged. The exact-position test now recovers all 15 saved
positions after truth-exact cancellation; see `tests/README.md`.

## Corrections after implementing the greedy flip test (`analysis/greedy_flip.py`)

1. Per-chip signal-to-noise after cancellation is **1.55**, not 2.2. The 2.2 came from the spread of
   positive chips only, which is biased low by truncation. Correct figures: noise per chip before
   cancellation sqrt(0.18^2 + 0.28^2) = 0.33, after 0.181, amplitude 0.28, so SNR 0.84 -> 1.55.
2. The 15-flip count uncertainty is therefore +-1.7 for the 12-satellite mean, not +-1.0. The count
   itself stands: 14.8 +- 1.7.
3. "Positions are not recoverable" was too strong. They are not recoverable *without a sparsity prior*,
   but with the prior "exactly 15 chips changed" and ranking by the increase in coherent score, a
   simulation at the measured SNR recovers 13.7 +- 0.9 of the 15 per satellite.
4. The score-change test is algebraically the same as deciding each chip's sign against the global
   coherent sum: flipping chip m changes the score by -4 Re(2 C_m S*) + ... So without the prior it
   flags 21-38 chips per satellite in observation 1 (15 true plus about as many from noise), and
   165-258 in observation 2.
5. Cross-file agreement confirms the recovery: at observation 1's top-15 chip positions, observation 2's
   chips are negative 67% of the time against a 20% baseline, implying about 13 of the 15 are correct.
   The two files therefore carry the same modification per satellite, even though the positions are not
   shared between different satellites.

## Correction: the pattern IS shared, shifted 2 chips per PRN

The "not common positions" conclusion above was measured with the pre-fix chip labels (`chip_vector`
rolled the wrong way and sampled fixed centre slots). After the label and sampling fix, and after
cancelling the other satellites with their nominal codes, the 12 soft chip vectors align at a single
slope: **PRN k is PRN 1 shifted by 2*(k-1) chips**. Summing the aligned vectors gives 15 consensus
chips far below the rest, and the base pattern is

    34 411 644 788 877 932 966 987 1000 1008 1013 1016 1018 1019 1020

which is `1020` minus the prefix sums of `1,1,2,3,5,8,13,21,34,55,89,144,233,377` - the Fibonacci
numbers in reverse. Per PRN: `flip = (base - 2*(PRN-1)) mod 1023`.

The joint sum raises the signal by 12 while the independent noise rises by sqrt(12), about 10.8 dB.
At 55 dB-Hz that is enough to read all 15 positions exactly, which one PRN alone cannot do. The
recovered modified codes drop the real recording's reconstruction residual from 1.0421 to 0.9911
(observation 1) and from 1.0052 to 0.9970 (observation 2); the noise variance is 1.0. See
`gnss/pipeline.py` (`gnss/rule.py`) and the tests in `tests/test_pipeline.py`.
