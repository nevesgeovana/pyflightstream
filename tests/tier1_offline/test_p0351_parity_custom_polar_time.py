"""Tier 1: the parity checker ignores only the write time of a custom polar group file.

FR-94: line 3 of a custom polar group file (``*_gNN.dat``) is the time it was written, by
definition (``post/custom_polar.py``), so two runs of the same post differ there and only
there. The parity rule rewrites that one line on both sides; any other line, and the same
stamp in any other file, still counts as a difference.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_HEAD = "PROPELLER POLAR\n320720\n{stamp}\n007 01\nMNOM SREF CREF BREF XMOM YMOM ZMOM\n"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_parity_under_test", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _group(stamp: str, line4: str = "007 01") -> bytes:
    return _HEAD.format(stamp=stamp).replace("007 01", line4).encode("utf-8")


def test_fr94_the_write_time_of_a_custom_polar_group_file_is_not_a_difference():
    """FR-94: two group files that differ only by their line-3 write time normalize equal."""
    norm = _load().normalize
    one = _group("Sat Oct 03 05:10:55  2026")
    two = _group("Sat Oct 03 05:15:41  2026")
    assert one != two
    name = "matrix/polars/P4800-M144_g01.dat"
    assert norm(name, one) == norm(name, two)
    assert b"<TIME>" in norm(name, one)


def test_fr94_any_other_line_of_a_group_file_still_differs():
    """FR-94: a change on line 4 survives the rule, so the rule hides the stamp only."""
    norm = _load().normalize
    name = "matrix/polars/P4800-M144_g01.dat"
    stamp = "Sat Oct 03 05:10:55  2026"
    assert norm(name, _group(stamp)) != norm(name, _group(stamp, "007 02"))


def test_fr94_the_stamp_in_another_file_is_not_rewritten():
    """FR-94: the rule matches the group file name only; another .dat keeps its stamp."""
    norm = _load().normalize
    data = _group("Sat Oct 03 05:10:55  2026")
    assert norm("matrix/polars/P4800-M144.dat", data) == data
