"""Tier 1: point names keep the historical binary half-even rounding (0.40.0)."""

import pytest

from pyflightstream.cases.matrix import MATRIX_COLUMNS, read_matrix
from pyflightstream.cases.naming import name_field


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("ALPHA", 0.15, "AL+002"),
        ("ALPHA", 0.25, "AL+002"),
        ("ALPHA", 0.35, "AL+004"),
        ("ALPHA", -0.25, "AL-002"),
        ("ADVANCE_RATIO", 0.115, "J+012"),
        ("ADVANCE_RATIO", 0.125, "J+012"),
    ],
)
def test_p0400_name_field_keeps_historical_rounding(key, value, expected):
    """P0400-NAME-ROUNDING (PFS-2081.48): historical point names do not change."""
    assert name_field(key, value) == expected


def test_p0400_sweep_values_with_distinct_historical_names_are_not_refused(tmp_path):
    """P0400-NAME-ROUNDING (PFS-2081.48): distinct historical names remain accepted."""
    row = dict.fromkeys(MATRIX_COLUMNS, "NA")
    row.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
        SWEEP_VALUES="0.0,0.1,0.2,0.3",
        FS_BUILD="MANUAL",
        WORKFLOW="unsteady",
        VAR_NAMES_VALUES="",
    )
    path = tmp_path / "matrix.fs"
    path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
    (read,) = read_matrix(path)
    assert read.sweep.values == [0.0, 0.1, 0.2, 0.3]
