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

_HEAD = (
    "FlightStream - PROPELLER POLAR\n320720\n{stamp}\n007 01\nMNOM SREF CREF BREF XMOM YMOM ZMOM\n"
)


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
    """PFS-2014.01.02: a .dat whose line 1 is not a custom polar title keeps its stamp."""
    norm = _load().normalize
    data = _group("Sat Oct 03 05:10:55  2026").replace(b"FlightStream - ", b"Other tool - ")
    assert norm("matrix/polars/P4800-M144_g01.dat", data) == data


def test_pfs2014_a_named_group_file_is_rewritten_too():
    """PFS-2014.01.02: a named group file (``_ROTOR.dat``) has the same line 3 and normalizes."""
    norm = _load().normalize
    name = "matrix/polars/P4903-M144RPM00447_ROTOR.dat"
    one = _group("Sat Oct 03 05:51:56  2026")
    two = _group("Sat Oct 03 05:56:08  2026")
    assert norm(name, one) == norm(name, two)


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


def test_p0390_parity_the_package_version_stamp_of_a_post_is_not_a_difference():
    """P0390-PARITY (release parity): outputs differing only by the version stamp compare equal."""
    norm = _load().normalize
    log = "pyflightstream {v} post\ntime=2026-10-11T01:02:03+00:00\n"
    assert norm("m/post.log", log.format(v="0.38.0").encode()) == norm(
        "m/post.log", log.format(v="0.39.0").encode()
    )
    js = '{{\n  "version": "{v}",\n  "workspace": "w"\n}}'
    assert norm("m/post.log.json", js.format(v="0.38.0").encode()) == norm(
        "m/post.log.json", js.format(v="0.39.0").encode()
    )
    pj = (
        '{{"superfile_report": "reports/superfile-{t}.json", '
        '"sections_report": "reports/sections-{t}.json"}}'
    )
    assert norm("m/products.json", pj.format(t="0380").encode()) == norm(
        "m/products.json", pj.format(t="0390").encode()
    )
    out = norm("m/products.json", pj.format(t="0390").encode())
    assert b'"superfile_report": "reports/superfile-<VERSION>.json"' in out
    assert b'"sections_report": "reports/sections-<VERSION>.json"' in out


def test_p0390_parity_a_number_elsewhere_beside_the_version_stamp_still_differs():
    """P0390-PARITY (release parity): the rule hides the stamp only, not a neighbouring change."""
    norm = _load().normalize
    one = b"pyflightstream 0.38.0 post\n"
    assert norm("m/post.log", one) != norm("m/post.log", b"pyflightstream 0.39.0 post extra\n")
    assert norm("m/post.log", b"pyflightstream 0.39.0 post 1\n") != norm(
        "m/post.log", b"pyflightstream 0.39.0 post 2\n"
    )
    a = b'{"version": "0.38.0", "n": 1}'
    assert norm("m/post.log.json", a) != norm("m/post.log.json", b'{"version": "0.38.0", "n": 2}')
    p = b'"superfile_report": "reports/superfile-0380.json"'
    assert norm("m/products.json", p) != norm(
        "m/products.json", b'"superfile_report": "reports/superfile-0380.json.x"'
    )


def _custom_title_and_error(tmp_path, **kwargs):
    from pyflightstream.post._tables import COEFFICIENT_COLUMNS
    from pyflightstream.post.custom_polar import write_custom_polar_format
    from pyflightstream.post.products import ReferenceValues

    reference = ReferenceValues.from_mapping(
        {"SREF": 1.0, "CREF": 1.0, "BREF": 1.0, "XMOM": 0, "YMOM": 0, "ZMOM": 0}
    )
    given = {"polar": 1, "description": "d", "group": 1, "mach": 0.144, "reference": reference}
    given.update(kwargs)
    return write_custom_polar_format(
        tmp_path / "t.dat", rows=[(1.0,) * len(COEFFICIENT_COLUMNS)], **given
    )


def test_x_f_1192_a_non_ascii_header_value_is_a_product_error_naming_the_line(tmp_path):
    """X-F-1192: a polar id outside ASCII is a ProductError, not a UnicodeEncodeError."""
    import pytest

    from pyflightstream.post._tables import ProductError

    with pytest.raises(ProductError, match="line 2 of the custom polar header holds"):
        _custom_title_and_error(tmp_path, polar="p" + chr(0xE7))
    assert not (tmp_path / "t.dat").exists()


def test_x_f_1641_an_na_configuration_adds_nothing_to_the_title(tmp_path):
    """X-F-1641: the NA token is a placeholder like the dash, never printed in the title."""
    first = _custom_title_and_error(tmp_path, configuration="NA").read_text(encoding="ascii")
    second = _custom_title_and_error(tmp_path, configuration="-").read_text(encoding="ascii")
    assert first.splitlines()[0] == second.splitlines()[0]
    assert "NA" not in first.splitlines()[0]
    kept = _custom_title_and_error(tmp_path, configuration="flap 5").read_text(encoding="ascii")
    assert kept.splitlines()[0].endswith(" - flap 5")
