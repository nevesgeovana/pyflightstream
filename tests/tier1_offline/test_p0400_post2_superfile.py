"""P0400-LEGACYWIDTH: every field of the legacy polar super file is separated.

At the 0.40.0 base each field was right-justified to 16 characters with no
separator, so a name of 16 characters or more ran into its neighbour and a
description holding spaces split into several tokens.
"""

from __future__ import annotations

from pyflightstream.post.superfile import _write_legacy_polar

COLUMNS = ["POL", "SET_SOLVER_VISCOUS_COUPLING", "DESCRIPTION", "flight_condition_defaults_from"]


def test_p0400_legacywidth_every_line_splits_into_one_field_per_column(tmp_path):
    """P0400-LEGACYWIDTH: the header and every row split into len(columns) fields."""
    rows = [
        ["3207", 1, "wing at cruise", "the matrix row"],
        ["3208", 0, "a description longer than sixteen", 0.5],
    ]
    path = _write_legacy_polar(tmp_path / "SUPER.dat", COLUMNS, rows)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split() == COLUMNS
    for line in lines[1:]:
        assert len(line.split()) == len(COLUMNS), line
    assert lines[1].split()[2] == "wing_at_cruise"


def test_p0400_legacywidth_short_fields_keep_the_width_of_sixteen(tmp_path):
    """P0400-LEGACYWIDTH control: names and cells under 16 characters keep the 16 width."""
    path = _write_legacy_polar(tmp_path / "SUPER.dat", ["POL", "CL"], [["3207", 0.5]])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["POL".rjust(16) + "CL".rjust(16), "3207".rjust(16) + "0.50000".rjust(16)]
