"""Tier 1: the parity checker ignores only the write time of a custom polar group file.

PFS-2014.01.02: line 3 of a custom polar group file (``*_gNN.dat``) is the time it was written, by
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


def test_pfs2014_the_write_time_of_a_custom_polar_group_file_is_not_a_difference():
    """PFS-2014.01.02: group files differing only by their line-3 write time normalize equal."""
    norm = _load().normalize
    one = _group("Sat Oct 03 05:10:55  2026")
    two = _group("Sat Oct 03 05:15:41  2026")
    assert one != two
    name = "matrix/polars/P4800-M144_g01.dat"
    assert norm(name, one) == norm(name, two)
    assert b"<TIME>" in norm(name, one)


def test_pfs2014_any_other_line_of_a_group_file_still_differs():
    """PFS-2014.01.02: a change on line 4 survives the rule, so the rule hides the stamp only."""
    norm = _load().normalize
    name = "matrix/polars/P4800-M144_g01.dat"
    stamp = "Sat Oct 03 05:10:55  2026"
    assert norm(name, _group(stamp)) != norm(name, _group(stamp, "007 02"))


def test_pfs2014_the_stamp_in_another_file_is_not_rewritten():
    """PFS-2014.01.02: the rule matches the group file name only; another .dat keeps its stamp."""
    norm = _load().normalize
    data = _group("Sat Oct 03 05:10:55  2026")
    assert norm("matrix/polars/P4800-M144.dat", data) == data


def test_pfs2014_a_line_3_that_is_not_a_stamp_still_differs():
    """PFS-2014.01.02: only the stamp shape is rewritten; other line-3 text keeps its bytes."""
    norm = _load().normalize
    name = "matrix/polars/P4800-M144_g01.dat"
    assert norm(name, _group("not a date")) != norm(name, _group("other text"))


def test_pfs2014_a_stamp_on_another_line_is_kept():
    """PFS-2014.01.02: the rule reaches line 3 only; the same stamp on line 4 is not rewritten."""
    norm = _load().normalize
    name = "matrix/polars/P4800-M144_g01.dat"
    stamp = "Sat Oct 03 05:10:55  2026"
    data = _group("not a date", stamp)
    assert norm(name, data) == data


def test_pfs2014_the_writer_format_with_crlf_is_rewritten():
    """PFS-2014.01.02: a stamp in the writer's own format, with CRLF line ends, normalizes equal."""
    import datetime as dt

    from pyflightstream.post.custom_polar import CUSTOM_DATE_FORMAT

    norm = _load().normalize
    name = "matrix/polars/P4800-M144_g01.dat"
    one = dt.datetime(2026, 10, 3, 5, 10, 55).strftime(CUSTOM_DATE_FORMAT)
    two = dt.datetime(2026, 10, 3, 5, 15, 41).strftime(CUSTOM_DATE_FORMAT)
    crlf = [_group(s).replace(b"\n", b"\r\n") for s in (one, two)]
    assert crlf[0] != crlf[1]
    assert norm(name, crlf[0]) == norm(name, crlf[1])
