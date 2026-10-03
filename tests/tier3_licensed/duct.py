"""Reproduce the measured eight-vertex, six-quad synthetic duct locally."""

from __future__ import annotations

from pathlib import Path

from tests.support_tier3 import (
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
