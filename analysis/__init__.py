"""Exploratory and evidence scripts.

These are not part of the pipeline that `solve.py` runs. Each one answers a single quantitative
question that the main report summarises, and each prints its measurement rather than asserting it:

  chip_extraction            one soft value per chip, per PRN, plus a control code that must be noise
  data_bit_check             did a navigation data bit change inside the recording
  interference_cancellation  what removing the other PRNs actually buys, measured on chip spread
  greedy_flip                the analytic per-chip flip score, verified against a direct correlation
  joint_flip                 benchmarks of a shared mask against independent per-PRN flips
  code_phase_accuracy        bias and spread of the code-phase estimator against injected truth
  segment_identity           are the code periods copies, and how far from identical
  acquire_nc                 acquisition with the vendored Peter Monta kernel, as a cross-check
  nc2cu8                     NetCDF recording to the int8 interleaved form that kernel reads
  dump_attrs                 every NetCDF attribute of a recording, as JSON

Run one with `python -m analysis.<name> [recording ...]` from the repository root.
"""
