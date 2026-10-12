"""Tier 1: a point name rounds a tie away from zero, on the decimal written (0.40.0)."""

import pytest

from pyflightstream.cases.matrix import MATRIX_COLUMNS, read_matrix
from pyflightstream.cases.naming import name_field


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("ALPHA", 0.15, "AL+002"),
        ("ALPHA", 0.25, "AL+003"),
        ("ALPHA", 0.35, "AL+004"),
        ("ALPHA", -0.25, "AL-003"),
        ("ADVANCE_RATIO", 0.115, "J+012"),
        ("ADVANCE_RATIO", 0.125, "J+013"),
    ],
)
def test_p0400_name_field_rounds_a_tie_away_from_zero(key, value, expected):
    """P0400-NAME-ROUNDING (PFS-2095.038): values a name resolution apart get two names."""
    assert name_field(key, value) == expected


def test_p0400_sweep_values_a_tenth_apart_are_not_refused(tmp_path):
    """P0400-NAME-ROUNDING (PFS-2095.038): 0.05, 0.15, 0.25, 0.35 degrees are four points."""
    row = dict.fromkeys(MATRIX_COLUMNS, "NA")
    row.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
        SWEEP_VALUES="0.05,0.15,0.25,0.35",
        FS_BUILD="MANUAL",
        WORKFLOW="unsteady",
        VAR_NAMES_VALUES="",
    )
    path = tmp_path / "matrix.fs"
    path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
    (read,) = read_matrix(path)
    assert read.sweep.values == [0.05, 0.15, 0.25, 0.35]
