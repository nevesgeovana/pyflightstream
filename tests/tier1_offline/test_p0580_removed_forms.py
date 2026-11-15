"""P0580-REMOVED-FORMS (PFS-2237): every form that was deprecated is refused by name.

Each old form of the former deprecation ledger no longer works. A person who still writes it
is told what it became, so the migration is one edit and not a search. One test per form: it
runs the real entry point with the old spelling and requires the refusal to name the new one.
"""

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.workspace import sector_to_wheel
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0540_wheel_obj import build_sector
from tests.tier1_offline.test_p0560_morph import build, control, invoke


def test_p0580_hub_rings_width_key_is_refused_naming_band_width(tmp_path, capsys):
    source = build(tmp_path)
    cfg = control(tmp_path, "[hub_rings]\nrings = 4\nwidth = 0.04\n")
    out = tmp_path / "rings.obj"
    assert invoke("hub-rings", source, cfg, out) == 2
    said = capsys.readouterr().err
    assert "width" in said and "band_width" in said and "no longer accepted" in said, said
    assert not out.exists()


def test_p0580_sector_to_wheel_hub_argument_is_refused_naming_center(tmp_path):
    sector = build_sector(tmp_path)
    with pytest.raises(InputValueError, match=r"center \(CLI: --center\)") as refused:
        sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], hub=[0, 0, 0])
    assert "no longer accepted" in str(refused.value)
    # Stating the replacement beside it does not make the old form pass.
    with pytest.raises(InputValueError, match="no longer accepted"):
        sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], center=[0, 0, 0], hub=[0, 0, 0])


def test_p0580_sector_to_wheel_hub_flag_is_refused_naming_center(tmp_path, capsys):
    sector = build_sector(tmp_path)
    out = tmp_path / "wheel.obj"
    code = main(
        [
            "geometry",
            "sector-to-wheel",
            str(sector.obj),
            "--copies",
            "6",
            "--blades",
            "Blade1",
            "--out",
            str(out),
            "--hub",
            "0",
            "0",
            "0",
        ]
    )
    said = capsys.readouterr().err
    assert code == 2 and "--center" in said and "no longer accepted" in said, said
    assert not out.exists()


# --- the keywords, the verbs, the header and the names the ledger held --------------------


@pytest.mark.parametrize("entry_point", ["plan_matrix", "run_matrix"])
def test_p0580_matrix_fs_version_keyword_is_refused_naming_default_fs_version(
    tmp_path, entry_point
):
    from pyflightstream.cases.matrix import MatrixError
    from pyflightstream.run import LoadsAssessor
    from pyflightstream.run import matrix as matrix_module
    from tests.support_helpers import REGISTRY_FIXTURE, make_library

    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    call = getattr(matrix_module, entry_point)
    extra = {"assess": LoadsAssessor()} if entry_point == "run_matrix" else {}
    with pytest.raises(MatrixError, match="default_fs_version") as refused:
        call(
            REGISTRY_FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes={"003": "steady", "004": "steady"},
            **extra,
        )
    assert "no longer accepted" in str(refused.value)
    assert "--fs-version" in str(refused.value), "the command line keeps its spelling"


def test_p0580_analysis_setup_vorticity_argument_is_refused_naming_solver_settings():
    from pyflightstream.script import CommandArgumentError, Script, helpers

    script = Script(version="26.120")
    with pytest.raises(CommandArgumentError, match=r"solver_settings\(") as refused:
        helpers.analysis_setup(script, vorticity_drag_boundaries="all")
    assert "no longer accepted" in str(refused.value)
    assert "SET_VORTICITY_DRAG_BOUNDARIES" not in script.render()


def test_p0580_station_harmonics_is_refused_naming_inflow_station_harmonics():
    from pyflightstream.post import inflow_tools

    with pytest.raises(AttributeError, match="InflowStationHarmonics") as refused:
        _ = inflow_tools.StationHarmonics
    assert "no longer accepted" in str(refused.value)
    assert inflow_tools.InflowStationHarmonics is not None


@pytest.mark.parametrize(
    ("verb", "home"),
    [
        ("refine", "refine"),
        ("audit-mesh", "audit"),
        ("inventory", "inventory"),
        ("degenerate", "degenerate"),
    ],
)
def test_p0580_pyfs_matrix_geometry_verb_is_refused_naming_its_home(verb, home, capsys):
    from pyflightstream.run import cli

    assert cli.main([verb, "mesh.obj"]) == 2
    said = capsys.readouterr().err
    assert f"pyfs-workspace geometry {home}" in said and "no longer accepted" in said, said


def test_p0580_matrix_header_of_0_56_0_is_refused_naming_migrate(tmp_path):
    from pyflightstream.cases.matrix import MATRIX_COLUMNS, MatrixError, read_matrix

    columns = [c for c in MATRIX_COLUMNS if c != "MESH_ROUTE"]
    path = tmp_path / "old.fs"
    path.write_text(" | ".join(columns) + "\n" + "-" * 40 + "\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="MESH_ROUTE") as refused:
        read_matrix(path)
    assert "pyfs-workspace migrate --apply" in str(refused.value)
    assert "no longer accepted" in str(refused.value)


@pytest.mark.parametrize(
    ("key", "new"),
    [
        ("motions.MOVING_BOUNDARIES", "MOVING_BC_ALIAS"),
        ("rotation.FAMILIES", "ALIAS"),
        ("pproc.each_blade", "LOCAL_AXIS"),
        ("families.airframe", "alias"),
        ("families.blades", "alias"),
    ],
)
def test_p0580_the_rotor_row_refusals_keep_naming_the_new_spelling(key, new):
    from pyflightstream._retired_names import REMOVED_FORMS

    message = REMOVED_FORMS[key].message()
    assert new in message and "no longer accepted" in message


def test_p0580_the_deprecation_ledger_holds_no_entry_and_no_form_is_promised():
    from pyflightstream import _deprecations

    assert _deprecations.DEPRECATIONS == ()
    assert _deprecations.DEPRECATED_MODULES == ()
    for gone in (
        "ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES",
        "PLAN_MATRIX_FS_VERSION",
        "RUN_MATRIX_FS_VERSION",
        "ROW_MOVING_BOUNDARIES",
        "ROW_ROTATE_FAMILIES",
        "ROW_EACH_BLADE",
        "ROW_AIRFRAME_SELECTOR",
        "ROW_BLADES_SELECTOR",
        "INFLOW_STATION_HARMONICS",
        "MATRIX_REFINE",
        "MATRIX_AUDIT_MESH",
        "MATRIX_INVENTORY",
        "MATRIX_DEGENERATE",
        "MATRIX_LAYOUT_0_56_0",
    ):
        assert not hasattr(_deprecations, gone), gone


def _refine_source(tmp_path):
    from tests.p0380_mesh_fixtures import sheet_with_strips, write_source

    return write_source(
        tmp_path / "src", "wing", sheet_with_strips((("T", "tri", (0.03, 0.04, 0.05)),))
    )


@pytest.mark.parametrize(
    ("flag", "value", "successor"),
    [
        ("--chordwise", "1.5", "--normal"),
        ("--spanwise", "1.5", "--parallel"),
        ("--keep-first-row", "A", "--families"),
        ("--out-dir", None, "--out"),
    ],
)
def test_p0580_refine_flag_is_refused_naming_its_successor(
    tmp_path, capsys, flag, value, successor
):
    from tests.tier1_offline import _geometry_verbs as cli

    src = _refine_source(tmp_path)
    given = value if value is not None else str(tmp_path / "levels")
    capsys.readouterr()
    code = cli.main(["refine", str(src), "2", flag, given])
    said = capsys.readouterr().err
    assert code == 2, said
    assert flag in said and successor in said and "no longer accepted" in said, said
    assert "Nothing was written." in said
    assert not (tmp_path / "levels").exists()


def test_p0580_audit_csv_flag_is_refused_naming_out(tmp_path, capsys):
    from tests.tier1_offline import _geometry_verbs as cli

    src = _refine_source(tmp_path)
    csv = tmp_path / "figures.csv"
    capsys.readouterr()
    code = cli.main(["audit-mesh", str(src), "--csv", str(csv)])
    said = capsys.readouterr().err
    assert code == 2, said
    assert "--csv" in said and "--out" in said and "no longer accepted" in said, said
    assert "Nothing was written." in said
    assert not csv.exists()
