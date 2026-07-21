"""Tier 1: legacy matrix reader and convert-matrix (FR-10, FR-11).

The fixture mirrors the verified 15-column layout of the predecessor
run matrix (first data row shaped like the real POL 9001 case);
names and values are synthetic.
"""

from pathlib import Path

import pytest

from pyflightstream.cases import load_campaign
from pyflightstream.cases.matrix_legacy import (
    LegacyMatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
)

FIXTURE = Path(__file__).parent / "fixtures" / "matrix_legacy.fs"
RECIPES = {"003": "recipes.steady_polar:build", "004": "recipes.beta_sweep:build"}


def test_read_matrix_parses_the_verified_layout():
    rows = read_matrix(FIXTURE)
    assert [row.pol for row in rows] == ["9001", "9002"]
    first = rows[0]
    assert first.aircraft == "TestWing"
    assert first.re_millions == 4.38
    assert first.mach == 0.1441
    assert first.script_code == "003"
    assert first.fs_build == "MANUAL"
    assert first.hidden is False
    assert rows[1].hidden is True


def test_run_filtering_follows_the_legacy_flag():
    assert len(read_matrix(FIXTURE)) == 2
    everything = read_matrix(FIXTURE, active_only=False)
    assert [row.run for row in everything] == [1, 1, 0]


def test_sweeps_convert_to_native_axes():
    rows = read_matrix(FIXTURE)
    assert rows[0].sweep.type == "alpha_beta"
    assert list(rows[0].sweep.points()) == [
        {"alpha": -4.0, "beta": 0.0},
        {"alpha": 0.0, "beta": 0.0},
        {"alpha": 4.0, "beta": 0.0},
    ]
    assert rows[1].sweep.type == "beta"
    assert rows[1].sweep.values == [-6.0, 0.0, 6.0]


def test_variables_parse_spaced_values_and_lowercase_keys():
    variables = read_matrix(FIXTURE)[0].variables
    assert variables["SYMMETRY_TYPE"] == "PERIODIC 6"
    assert variables["ADVANCE_RATIO"] == "1.7"
    assert variables["unsteady_delta_theta_deg"] == "10.0"


def test_unverified_sweep_code_is_refused_with_evidence_language(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8").replace("| AL/BE ", "| J     ")
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(LegacyMatrixError, match="verified legacy\\s+codes"):
        read_matrix(bad)


def test_header_deviation_is_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("A | B | C\n1 | 2 | 3\n", encoding="utf-8")
    with pytest.raises(LegacyMatrixError, match="verified 15-column layout"):
        read_matrix(bad)


def test_to_campaign_maps_codes_and_preserves_them():
    campaign = to_campaign(
        FIXTURE, name="legacy", fs_version="26.12", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    case = campaign.sims[0]
    assert case.sim_id == "9001"
    assert case.reynolds == 4.38e6
    assert case.recipe == "recipes.steady_polar:build"
    assert case.variables["legacy_ref"] == "003"
    assert case.variables["legacy_fs_build"] == "MANUAL"
    assert case.variables["legacy_hidden"] is False
    assert case.variables["SYMMETRY_TYPE"] == "PERIODIC 6"


def test_unmapped_script_code_is_refused():
    with pytest.raises(LegacyMatrixError, match="no recipe\\s+mapping"):
        to_campaign(FIXTURE, name="legacy", fs_version="26.12", fs_exe="C:/fs.exe", recipes={})


def test_convert_matrix_round_trips_through_load_campaign(tmp_path):
    text = convert_matrix(
        FIXTURE, name="legacy", fs_version="26.12", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    path = tmp_path / "campaign.toml"
    path.write_text(text, encoding="utf-8")
    campaign = load_campaign(path)
    direct = to_campaign(
        FIXTURE, name="legacy", fs_version="26.12", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    assert campaign == direct
