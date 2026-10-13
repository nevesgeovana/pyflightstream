"""Reproduce the upgrade with name_field('ALPHA', 10.45) and a two-angle matrix."""

# ruff: noqa: N999 - the release lane requires this filename.

import pytest

from pyflightstream.cases import point_name
from pyflightstream.cases.matrix import MATRIX_COLUMNS, read_matrix
from pyflightstream.cases.naming import name_field


@pytest.mark.requirement("P0400-LITA-NAMING")
@pytest.mark.parametrize(
    ("angle", "recorded"),
    [
        (9.25, "AL+092"),
        (10.25, "AL+102"),
        (-0.05, "AL+000"),
        (0.45, "AL+004"),
        (10.45, "AL+104"),
        (0.65, "AL+006"),
        (9.65, "AL+096"),
        (10.65, "AL+106"),
        (4.85, "AL+048"),
        (5.85, "AL+058"),
    ],
)
def test_p0400_lita_existing_angle_names_survive_upgrade(angle, recorded):
    assert name_field("ALPHA", angle) == recorded


@pytest.mark.requirement("P0400-LITA-NAMING")
def test_p0400_lita_the_two_study_angles_plan_with_their_existing_names(tmp_path):
    row = dict.fromkeys(MATRIX_COLUMNS, "NA")
    row.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        FS_BUILD="MANUAL",
        WORKFLOW="unsteady",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep, BETA:0",
        SWEEP_VALUES="10.45,10.50",
        VAR_NAMES_VALUES="",
    )
    path = tmp_path / "matrix.fs"
    path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
    (case,) = read_matrix(path)
    assert [point_name(case, point) for point in case.sweep.points()] == [
        "M100AL+104BE+000",
        "M100AL+105BE+000",
    ]
