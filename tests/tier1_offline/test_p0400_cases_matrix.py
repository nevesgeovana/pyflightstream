"""Tier 1: the run-matrix reader and converter refuse by name and convert losslessly (0.40.0)."""

import warnings

import pytest

from pyflightstream.cases import load_campaign
from pyflightstream.cases.matrix import (
    _LAYOUT_0_15_0,
    MATRIX_COLUMNS,
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
)

CAMPAIGN = {"name": "polar", "fs_version": "26.124", "fs_exe": "FlightStream.exe", "recipes": {}}


def _matrix(tmp_path, **cells):
    """Write a one-row matrix at the current layout, overriding the named cells."""
    row = dict.fromkeys(MATRIX_COLUMNS, "NA")
    row.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        AIRCRAFT="Wing",
        DESCRIPTION="POLAR",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
        SWEEP_VALUES="0.0,2.0",
        FS_BUILD="MANUAL",
        WORKFLOW="unsteady",
        VAR_NAMES_VALUES="",
    )
    row.update(cells)
    path = tmp_path / "matrix.fs"
    path.write_text(" | ".join(row) + "\n" + " | ".join(row.values()) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(("column", "value"), [("RUN", "NA"), ("RUN", "1.0"), ("HIDDEN", "yes")])
def test_p0400_run_and_hidden_cells_are_refused_naming_row_and_pol(tmp_path, column, value):
    """P0400-RUN-HIDDEN (PFS-2095.003): a RUN or HIDDEN value outside its form names row and POL."""
    with pytest.raises(MatrixError) as caught:
        read_matrix(_matrix(tmp_path, **{column: value}), active_only=False)
    text = str(caught.value)
    assert "data row 1" in text and "POL 9001" in text and column in text and repr(value) in text


def test_p0400_layout_0_15_0_is_recognised_naming_its_converter(tmp_path):
    """P0400-LAYOUT-0150 (PFS-2095.037): the 13-column layout is not told to restore a backup."""
    path = tmp_path / "m016.fs"
    path.write_text(" | ".join(_LAYOUT_0_15_0) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(path)
    text = str(caught.value)
    assert "v0.15.0 to v0.16.0" in text and "pyfs-matrix upgrade" in text
    assert "CONFIGURATION" in text and "WALLTIME" in text
    assert "restore the original" not in text


@pytest.mark.parametrize("token", ["abc", "inf", "nan"])
def test_p0400_sweep_value_that_is_not_a_finite_number_names_the_pol(tmp_path, token):
    """P0400-SWEEP-TOKEN (PFS-2095.002): a SWEEP_VALUES token is refused as a matrix error."""
    with pytest.raises(MatrixError) as caught:
        read_matrix(_matrix(tmp_path, SWEEP_VALUES=f"0.0,{token}"))
    text = str(caught.value)
    assert "POL 9001" in text and "SWEEP_VALUES" in text and repr(token) in text
    assert "comma-separated numbers" in text


def test_p0400_no_active_row_and_no_default_build_is_a_matrix_error(tmp_path):
    """P0400-NO-ACTIVE-ROW (PFS-2095.004): no StopIteration when every row is switched off."""
    path = _matrix(tmp_path, RUN="0")
    with pytest.raises(MatrixError, match=r"no active row.*--fs-version"):
        to_campaign(path, **{**CAMPAIGN, "fs_version": ""})


def test_p0400_convert_matrix_keeps_every_record_list(tmp_path):
    """P0400-CONVERT-LOSSLESS (PFS-2096.002): read -> convert -> load gives the same SimCase."""
    path = _matrix(
        tmp_path,
        VAR_NAMES_VALUES=(
            "MOTIONS: {MOVING_BOUNDARIES: S / RPM_SIGN: 1 / ROTOR_AXIS: X}"
            " / ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: S}"
            " / TRANSLATE: {DISTANCE: 0.5 / AXIS: MRP-X / ALIAS: S}"
            " / RAW: {COMMAND: PRINT hello / BEFORE: init}"
        ),
    )
    case = to_campaign(path, **CAMPAIGN).sims[0]
    assert case.motions and case.rotations and case.translations and case.raw_commands
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        text = convert_matrix(path, **CAMPAIGN)
    converted = tmp_path / "campaign.toml"
    converted.write_text(text, encoding="utf-8")
    assert load_campaign(converted).sims[0].model_dump() == case.model_dump()
