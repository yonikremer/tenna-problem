"""How low can a truly flipped chip read? A Monte Carlo at one recording's signal-to-noise ratio.

Recording 2 does not show chip `987` at all: its twelve-PRN reading is -0.04 of the expected flip
depth, where a clean flip would read -1.0. That could be a defect in the chain or the ordinary tail of
a weak recording. This answers it by generating recordings whose truth is known and running the real
chain on them.

Each trial: 8 ms, 12 PRNs, the assignment's model, the shared 15-chip mask, 47.5 dB-Hz per PRN (the
amplitude recording 2 actually has) and recording 2's own Dopplers. Acquisition, cancellation, chip
readout and rule recovery are the package's, not a shortcut. Scored: the weakest of the 15 truly
flipped chips, and how many chips the chain thinks are flipped.

Usage:
    python -m analysis.weakest_chip              # 60 trials, about 12 minutes
    python -m analysis.weakest_chip 20           # fewer trials
"""

import sys
from pathlib import Path

import numpy as np

from analysis.correctness import prepared, vector_of
from benchmark import Scenario, synthesise
from gnss import pipeline
from gnss.acquisition import acquire, parse_satellite_spec
from gnss.rule import aligned_matrix

DEFAULT_TRIALS = 60
CN0_DBHZ = 47.5
# recording 2's own measured Dopplers, so the carrier beat between satellites is the same
DOPPLERS = (1441.54, 2653.12, 1115.35, -346.40, 876.27, -1530.54,
            -2698.26, -932.22, 2049.55, 266.42, -2112.79, -1103.70)
THRESHOLD = 0.04


def trial(seed: int, cn0_dbhz: float = CN0_DBHZ) -> tuple:
    """Weakest true-flip reading, number of chips the chain reports, chips below the threshold."""
    scenario = Scenario(
        label=f"weakest-{seed:03d}", seed=seed, prns=tuple(range(1, 13)), cn0_dbhz=cn0_dbhz,
        mode="shared", flip_count=15, slope=2, code_periods=8, dopplers=DOPPLERS,
    )
    path, truth = synthesise(scenario, Path("data/benchmark/weakest"))
    found = acquire(str(path), parse_satellite_spec("1-12"))
    recovery = pipeline.recover(str(path), acquisition=found)
    full = {prn: vector_of(values) for prn, values in prepared(found).items()}
    amplitude = {prn: float(np.median(np.abs(vector))) for prn, vector in full.items()}
    satellites, aligned = aligned_matrix(full, 2)
    readings = np.array([
        np.mean([-aligned[i][chip] / amplitude[satellites[i]] for i in range(len(satellites))])
        for chip in sorted(truth.base)
    ])
    return float(readings.min()), recovery.rule.count, int(np.sum(readings < THRESHOLD))


def main(trials: int = DEFAULT_TRIALS, cn0_dbhz: float = CN0_DBHZ):
    weakest, counts, weak_chips = [], [], []
    for seed in range(trials):
        reading, count, below = trial(seed, cn0_dbhz)
        weakest.append(reading)
        counts.append(count)
        weak_chips.append(below)
        print(f"seed {seed:>3}  count {count:>2}  weakest true chip {reading:+.2f}  "
              f"chips below {THRESHOLD}: {below}", flush=True)

    weakest = np.array(weakest)
    with_chip = sum(1 for below in weak_chips if below)
    print(f"\nsummary over {trials} trials at {cn0_dbhz} dB-Hz")
    print(f"  weakest true chip: min {weakest.min():+.2f}, 5th percentile "
          f"{np.percentile(weakest, 5):+.2f}, median {np.median(weakest):+.2f}")
    print(f"  trials where some true chip reads below {THRESHOLD}: {with_chip} of {trials} "
          f"({100.0 * with_chip / trials:.0f}%)")
    per_chip = 1.0 - (1.0 - with_chip / trials) ** (1.0 / 15.0)
    print(f"  equivalent chance for one named chip: {100.0 * per_chip:.1f}%")
    labels, frequencies = np.unique(np.array(counts), return_counts=True)
    print(f"  reported chip count: "
          f"{', '.join(f'{k}x{f}' for k, f in zip(labels.tolist(), frequencies.tolist(), strict=True))}")


if __name__ == "__main__":
    main(
        int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRIALS,
        float(sys.argv[2]) if len(sys.argv) > 2 else CN0_DBHZ,
    )
