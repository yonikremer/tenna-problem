# Attempts that did not work

Methods tried on the way to the rule, kept because a failed attempt that is not written down gets
tried again. Each entry says what was attempted, why it looked promising, what the data did instead,
and where the code or measurement lives.

## Pairwise circular cross-correlation of the PRN soft vectors

**What was tried.** Read one soft chip value per PRN (the existing first three steps of `FINDINGS.md`),
then for every unordered pair of PRNs circularly cross-correlate the two 1023-chip vectors over all
1023 lags and read the winning lag. That gives 66 measured offsets for 12 PRNs. Require the offsets to
compose - the lag from PRN 1 to PRN 3 must equal 1 to 2 plus 2 to 3, and the same for every one of the
220 triples - and require the step per PRN to be constant, which is the rule's linear shift. Refuse a
pair that cannot name one lag: two local maxima within 5% of each other (with lags within two chips of
the winner counted as the same main peak), or a curve that never falls 10% below its peak. Code:
`analysis/pairwise_offsets.py`.

**Why it looked promising.** It measures the offsets directly instead of inferring one parameter from
an alignment score, and 66 independent measurements plus a composition check look stronger than one
fit. On `data/gnss_observation.nc` it did exactly that: every pair's peak was decisive, the offsets
composed, and the recovered step was 2 chips per PRN.

**What happened.** It fails on `data/gnss_observation2.nc` (44.1-48.0 dB-Hz). A pair is decided by
one PRN's 15 dips alone, and on that file the per-chip dip is only about twice the chip noise, so many
pairs have a second peak nearly as tall as the winning one. The solver stopped at the first such pair:

```text
PRN 1 vs PRN 2: two peaks are too close to name one offset - lag 374 at 1.816 vs lag 41 at 1.742,
a margin of 0.074 where at least 0.091 is needed; refusing to pick one
```

```text
python -m analysis.pairwise_offsets
```

Accepting every pair's global maximum instead does not rescue it, because the offsets then contradict
each other:

```text
PRN 1->2 is 374 chips and 2->3 is 934, but 1->3 is 585, not 285: the pairwise offsets do not compose
```

**Why the old route survives the same file.** The one-slope search fits a single parameter across all
12 vectors. The weak patterns combine before the choice is made, so the signal grows by about the
number of PRNs while independent noise grows by its square root. Pairwise uses one pair at a time and
gets none of that combining gain.

**Verdict.** Reverted. `gnss.rule.recover_rule` is back to the slope search, and no pairwise code is
left in `gnss/`. The attempt is kept as `analysis/pairwise_offsets.py`, which reproduces the counts
and both failure messages above. The strict checks were right about the measurement being unclear -
the mistake was using a per-pair measurement where the answer needs all 12 PRNs at once.

## Flip one chip at a time, one PRN at a time

**What was tried.** For each PRN, flip chip `m` in its replica for every `m` from 0 to 1022 and keep
the chips whose flip raises that PRN's own correlation power. The score change is analytic: flipping a
chip removes its contribution twice, so `|S_m|^2 - |S|^2` needs one correlation, not 1023. The
shortcut is checked against a direct correlation before use. Code: `analysis/greedy_flip.py`.

**Why it looked promising.** It needs no rule at all, and each accepted chip is justified by its own
measured power change.

**What happened.** One PRN is too weak to rank its own chips. On `data/gnss_observation.nc` the
per-chip signal-to-noise is about 1.6, and the scan flags 21-38 chips per PRN where the truth has 15.
The known-answer synthetic test shows what that mix costs: most true chips are found, but about a
fifth of the flags are noise chips that also happen to improve the score, and no threshold on the
score separates the two groups.

```text
python -m analysis.greedy_flip
python -m pytest tests/test_greedy_flip.py
```

On `data/gnss_observation2.nc` the per-chip signal-to-noise is below 1 and the scan flags 157-259
chips per PRN, so the ranking there is noise.

**Verdict.** Useful as a per-PRN diagnostic and as a check of the analytic shortcut, not as a way to
read the flips. The shared rule is what raises the evidence above the noise.

## Same flip pattern in every PRN: flip chip i in all 12 PRNs together

**What was tried.** Assume every code flips the same chip indexes, with no per-PRN shift. Then chip
`i` contributes to all 12 correlations at once, and the total power change from flipping chip `i` in
every replica is one number per chip. Rank all 1023 chips by it and keep the best 15. Two versions:
the exact scan in `tests/global_flip.py` (with `tests/test_global_mask_scan.py`), and the joint-score
version with split-half validation in `analysis/joint_flip.py`.

**Why it looked promising.** The 12 PRNs' evidence adds coherently where one PRN's does not, so the
combined scan is about `sqrt(12)` more sensitive than the per-PRN scan.

**What happened.** The method is correct only when the assumption is true. On a synthetic recording
whose 12 codes really do flip the same 15 positions, the scan returns exactly those 15 positions for
every noise seed:

```text
python -m pytest tests/test_global_mask_scan.py
```

The supplied recordings violate the assumption: the rule shifts the pattern two chips per PRN. The
split-half check says so - ranking the chips from PRNs 1-6 and again from PRNs 7-12 shares 1 of 15
chips on `data/gnss_observation.nc` and 0 of 15 on `data/gnss_observation2.nc`, against 0.22 expected
from chance. Applying the same 15 chips to all codes also *lowers* the explained power compared with
no modification, while a separate mask per code raises it only by fitting 12 x 15 free chips.

```text
python -m analysis.joint_flip
```

**Verdict.** The scan itself works; the assumption is what fails. It is the baseline that shows why
the per-PRN shift has to be searched instead of assumed.

## What replaced them

`gnss.rule.recover_rule` searches one slope - the number of chips each PRN's pattern moves relative to
the first - and aligns all 12 vectors before summing them. That combining gain is what makes the weak
recording readable, and it is why the answer for `data/gnss_observation2.nc` keeps 14 of the 15
positions instead of stopping.

The per-PRN scan and the same-mask scan remain as checks and as records of the paths that did not
pay off; neither chooses the rule. The pairwise route lives on only as
`analysis/pairwise_offsets.py`, outside the solver.
