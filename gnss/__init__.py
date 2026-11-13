"""Recover the hidden chip-flip rule of a simulated GPS L1 C/A recording.

The package is split by concern, and each module states its own physics:

  lattice       the sampling grid, taken from the recording's metadata
  signals       spreading-code replicas, carriers, and the linear fit that removes them
  alignment     code phase of one satellite, coarse then sub-sample
  acquisition   which satellites are present, their Doppler and code phase
  chips         one soft value per spreading-code chip
  rule          the common flip pattern and the Fibonacci structure behind it
  verification  quantitative proof that the recovered codes explain the recording
  pipeline      the whole chain as one call
  tables        CSV artifacts

The end-to-end entry point is `solve.py` in the repository root, which chains these modules and
prints the rule, the pattern and the evidence.
"""

from . import (
    acquisition,
    alignment,
    chips,
    lattice,
    pipeline,
    rule,
    signals,
    tables,
    verification,
)
from .lattice import Lattice, load_recording
from .pipeline import Recovery, recover, soft_chip_vectors
from .rule import PatternExplanation, Rule, explain_base, fibonacci_base, recover_rule
from .verification import Verification, verify

__all__ = [
    "Lattice",
    "PatternExplanation",
    "Recovery",
    "Rule",
    "Verification",
    "acquisition",
    "alignment",
    "chips",
    "explain_base",
    "fibonacci_base",
    "lattice",
    "load_recording",
    "pipeline",
    "recover",
    "recover_rule",
    "rule",
    "signals",
    "soft_chip_vectors",
    "tables",
    "verification",
    "verify",
]
