"""P0400-CW-FREESTREAM: the custom field's coverage, in the unit the field is known in.

0.40.0 item PFS-2104.006: a field that declares no unit was read as metres in
every simulation but MILLIMETER, so an INCH grid was compared with the body as
if it were metres.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows import _freestream
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import steady_case

FIELD = b"2 2\n0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n"


def _with_field(tmp_path, unit: str) -> Script:
    source = tmp_path / "field.txt"
    source.write_bytes(FIELD)
    custom = _freestream._RowFreestream(
        path=str(source), form="STRUCTURED", source_units=None, extent=(-3.0, 3.0, -1.0, 1.0)
    )
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    _freestream._free_stream(steady_case(), script, {}, custom)
    return script


@pytest.mark.parametrize("unit", ["INCH", "FEET", "CENTIMETER", "MILLIMETER"])
def test_p0400_cw_freestream_an_undeclared_field_is_unknown_outside_metres(tmp_path, unit):
    """P0400-CW-FREESTREAM (PFS-2104.006): the coverage record says unknown, and why."""
    requirement = "P0400-CW-FREESTREAM"
    with pytest.warns(UserWarning, match="coverage is not checked"):
        script = _with_field(tmp_path, unit)
    assert script.custom_field_extent_m is None, requirement
    assert script.custom_field_coverage is not None
    assert script.custom_field_coverage["state"] == "unknown"
    assert unit in script.custom_field_coverage["reason"]


def test_p0400_cw_freestream_an_undeclared_field_in_metres_is_checked(tmp_path):
    """P0400-CW-FREESTREAM (PFS-2104.006), control: a METER simulation keeps the check."""
    requirement = "P0400-CW-FREESTREAM"
    script = _with_field(tmp_path, "METER")
    assert script.custom_field_extent_m == (-3.0, 3.0, -1.0, 1.0), requirement
    assert script.custom_field_coverage is None
