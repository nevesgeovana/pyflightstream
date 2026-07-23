"""Tier 1: run-matrix reader and convert-matrix (FR-10, FR-11).

The fixture mirrors the verified 15-column layout of the run matrix
(first data row shaped like the real POL 9001 case); names and
values are synthetic.
"""

import importlib
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import load_campaign
from pyflightstream.cases.matrix import (
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
)

FIXTURE = Path(__file__).parent / "fixtures" / "matrix.fs"
RECIPES = {"003": "recipes.steady_polar:build", "004": "recipes.beta_sweep:build"}


def test_read_matrix_parses_the_verified_layout():
    rows = read_matrix(FIXTURE)
    assert [row.pol for row in rows] == ["9001", "9002", "9004", "9005", "9006", "9008"]
    first = rows[0]
    assert first.aircraft == "TestWing"
    assert first.re_millions == 4.38
    assert first.mach == 0.1441
    assert first.script_code == "003"
    assert first.fs_build == "MANUAL"
    assert first.hidden is False
    assert rows[1].hidden is True


def test_run_filtering_follows_the_run_flag():
    assert len(read_matrix(FIXTURE)) == 6
    everything = read_matrix(FIXTURE, active_only=False)
    assert [row.run for row in everything] == [1, 1, 0, 1, 1, 1, 0, 1]
    assert [row.pol for row in everything if row.run == 0] == ["9003", "9007"]


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


def test_single_beta_broadcasts_over_the_alpha_sweep():
    # POL 9001: three alphas against one beta value.
    sweep = read_matrix(FIXTURE)[0].sweep
    assert sweep.type == "alpha_beta"
    assert [point["beta"] for point in sweep.points()] == [0.0, 0.0, 0.0]


def test_single_alpha_broadcasts_over_the_beta_sweep():
    # POL 9004: one alpha against five beta values.
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9004").sweep
    assert sweep.type == "alpha_beta"
    points = list(sweep.points())
    assert [point["alpha"] for point in points] == [2.0] * 5
    assert [point["beta"] for point in points] == [-6.0, -3.0, 0.0, 3.0, 6.0]


def test_alpha_only_sweep_reads_every_value():
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9005").sweep
    assert sweep.type == "alpha"
    assert sweep.values == [-2.0, 0.0, 2.0, 4.0, 6.0]


def test_equal_length_al_be_lists_pair_up():
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9008").sweep
    assert sweep.type == "alpha_beta"
    assert list(sweep.points()) == [
        {"alpha": -4.0, "beta": -2.0},
        {"alpha": 0.0, "beta": 0.0},
        {"alpha": 4.0, "beta": 2.0},
    ]


def test_variables_parse_spaced_values_and_lowercase_keys():
    variables = read_matrix(FIXTURE)[0].variables
    assert variables["SYMMETRY_TYPE"] == "PERIODIC 6"
    assert variables["ADVANCE_RATIO"] == "1.7"
    assert variables["unsteady_delta_theta_deg"] == "10.0"


def test_full_variables_cell_keeps_every_pair_verbatim():
    # POL 9006 carries the fullest VAR_NAMES_VALUES cell of the fixture,
    # including an escaped newline (a literal backslash-n sequence) that
    # must survive verbatim: the reader never interprets values.
    variables = next(row for row in read_matrix(FIXTURE) if row.pol == "9006").variables
    assert variables == {
        "CONFIG": "NSX",
        "FSM_FILE": "wing_flapped",
        "NOTE": "first line\\nsecond line",
        "SYMMETRY_TYPE": "PERIODIC 6",
        "RESTART": "DISABLE",
        "TRIM_TARGET": "CL 0.45",
        "scale_inv": "1.0",
    }
    assert "\n" not in variables["NOTE"]


def test_unverified_sweep_code_is_refused_with_evidence_language(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8").replace("| AL/BE ", "| J     ")
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(MatrixError, match="verified\\s+codes"):
        read_matrix(bad)


def test_header_deviation_is_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("A | B | C\n1 | 2 | 3\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="verified 15-column layout"):
        read_matrix(bad)


def test_empty_matrix_file_is_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("\n-----\n\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="no matrix content"):
        read_matrix(bad)


def test_truncated_row_is_refused_naming_the_row(tmp_path):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    # Drop the last cell of the first data row (POL 9001, file line 3).
    lines[2] = lines[2].rsplit("|", 1)[0].rstrip()
    bad = tmp_path / "matrix.fs"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError, match=r"data row 1 of .* holds 14 cells"):
        read_matrix(bad)


def test_to_campaign_maps_codes_and_preserves_them():
    campaign = to_campaign(
        FIXTURE, name="matrix", fs_version="26.12", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    case = campaign.sims[0]
    assert case.sim_id == "9001"
    assert case.reynolds == 4.38e6
    assert case.recipe == "recipes.steady_polar:build"
    assert case.variables["matrix_ref"] == "003"
    assert case.variables["matrix_fs_build"] == "MANUAL"
    assert case.variables["matrix_hidden"] is False
    assert case.variables["SYMMETRY_TYPE"] == "PERIODIC 6"


def test_unmapped_script_code_is_refused():
    with pytest.raises(MatrixError, match="no recipe\\s+mapping"):
        to_campaign(FIXTURE, name="matrix", fs_version="26.12", fs_exe="C:/fs.exe", recipes={})


def test_convert_matrix_round_trips_through_load_campaign(tmp_path):
    text = convert_matrix(
        FIXTURE, name="matrix", fs_version="26.12", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    path = tmp_path / "campaign.toml"
    path.write_text(text, encoding="utf-8")
    campaign = load_campaign(path)
    direct = to_campaign(
        FIXTURE, name="matrix", fs_version="26.12", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    assert campaign == direct
    # The escaped newline survives the TOML round trip verbatim.
    full = next(sim for sim in campaign.sims if sim.sim_id == "9006")
    assert full.variables["NOTE"] == "first line\\nsecond line"


def test_earlier_conversions_with_legacy_keys_stay_loadable(tmp_path):
    # The changelog promise: campaign.toml files converted before the
    # matrix_* rename keep their legacy_* variable keys and load
    # verbatim; variables are free-keyed by design.
    path = tmp_path / "campaign.toml"
    path.write_text(
        '[campaign]\nname = "old"\nfs_version = "26.12"\nfs_exe = "C:/fs.exe"\n\n'
        '[[sim]]\nsim_id = "9001"\naircraft = "TestWing"\n'
        'sweep = {type = "alpha", values = [0.0]}\n'
        'recipe = "recipes.steady_polar:build"\n'
        "[sim.variables]\n"
        'legacy_ref = "003"\nlegacy_hidden = false\n',
        encoding="utf-8",
    )
    campaign = load_campaign(path)
    assert campaign.sims[0].variables["legacy_ref"] == "003"
    assert campaign.sims[0].variables["legacy_hidden"] is False


# --- the deprecated pyflightstream.cases.matrix_legacy shim -----------------


def test_matrix_legacy_shim_reexports_and_warns():
    sys.modules.pop("pyflightstream.cases.matrix_legacy", None)
    with pytest.warns(DeprecationWarning, match="pyflightstream.cases.matrix"):
        shim = importlib.import_module("pyflightstream.cases.matrix_legacy")
    import pyflightstream.cases.matrix as canonical

    # The whole canonical surface, name by name: a name later dropped
    # from matrix.__all__ must fail here, not vanish silently.
    assert set(shim.__all__) == set(canonical.__all__) | {"LegacyMatrixError", "LegacyRow"}
    for name in canonical.__all__:
        assert getattr(shim, name) is getattr(canonical, name)
    # Same objects, so old except/isinstance code keeps working.
    assert shim.LegacyMatrixError is canonical.MatrixError
    assert shim.LegacyRow is canonical.MatrixRow


def test_matrix_legacy_shim_names_the_removal_horizon():
    sys.modules.pop("pyflightstream.cases.matrix_legacy", None)
    with pytest.warns(DeprecationWarning, match="future minor release"):
        importlib.import_module("pyflightstream.cases.matrix_legacy")
