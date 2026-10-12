"""Reproduce the measured eight-vertex, six-quad synthetic duct locally.

Run it as ``python tests/tier3_licensed/duct.py <output.obj>`` from anywhere: the
repository root is put on the import path from this file's own location
(``python -m tests.tier3_licensed.duct <output.obj>`` from the root works as well).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support_tier3 import (  # noqa: E402
    _CAPTURE_HEADER as _CAPTURE_HEADER,
)
from tests.support_tier3 import (
    write_duct_obj as write_duct_obj,
)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write_duct_obj(parser.parse_args().output)
