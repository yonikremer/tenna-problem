"""Locate the vendored gnsstools reference library and put it on the import path.

Only one function is used from it, `gnsstools.gps.ca.code`, which builds a fractional-chip
GPS L1 C/A replica. It is vendored rather than reimplemented so the spreading codes used here
are the published tables of a third-party library, not our own transcription.
"""

import sys
from pathlib import Path

VENDOR_PATH = Path(__file__).resolve().parents[1] / "vendor"


def add_to_import_path():
    """Make `import gnsstools` work without relying on the current directory."""
    if not VENDOR_PATH.is_dir():
        raise ImportError(f"vendored gnsstools not found at {VENDOR_PATH}")
    entry = str(VENDOR_PATH)
    if entry not in sys.path:
        sys.path.append(entry)
    return entry
