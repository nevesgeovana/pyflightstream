"""0.57.0 PFS-2214 (G10): matrix reach, the MESH_ROUTE column and the geometry row.

Written from the requirement (C2: a row and the API give one identity; C3: a failed row does not
stop the others; C4: a route column, each value reaching its own code path, a mesh row warned and
skipped, a row with no route emitting the script it emitted before; layout: an old header reads
with a warning and migrates, no byte lost) and the design's section D.4 and D.5. The generator
runs for real on a one-component body up to the pure stages; the kernel stages and the strategy
meshers are replaced where a test is about the route, not the geometry.
"""

from __future__ import annotations

import importlib
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import NotApplicableWarning, PyflightstreamDeprecationWarning
from tests.support_helpers import make_library, stage_geometry

BODY_TOML = '[components.FUS]\ntype = "body"\nlength_mm = 2000.0\n'


def test_r27_row_documentation_describes_behavior_without_personal_provenance():
    from pyflightstream.workspace import _geometry_row

    assert "her rule" not in _geometry_row.__doc__
    assert "warned and skipped" in _geometry_row.__doc__


#: The header of 0.56.0, written out, so the frozen layout is held against a literal.
OLD_HEADER = (
    "POL HIDDEN RUN AIRCRAFT CONFIGURATION DESCRIPTION FLIGHT_CONDITION SWEEP_VALUES GEOMETRY "
    "REF SET PPROC SYMMETRY SYMMETRY_LOADS NCPUS WALLTIME FS_BUILD WORKFLOW VAR_NAMES_VALUES"
).split()


def _cells(pol="7001", geometry="wing.fsm", route=None, free="", build="26.120"):
    cells = {
        "POL": pol,
        "HIDDEN": "0",
        "RUN": "1",
        "AIRCRAFT": "Wing",
        "CONFIGURATION": "-",
        "DESCRIPTION": "ROW",
        "FLIGHT_CONDITION": "MACH:0.1, REmi:1.0, ALPHA:sweep",
        "SWEEP_VALUES": "0.0",
        "GEOMETRY": geometry,
        "MESH_ROUTE": route or "NA",
        "REF": "r003",
        "SET": "s002",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "SYMMETRY_LOADS": "-",
        "NCPUS": "-",
        "WALLTIME": "-",
        "FS_BUILD": build,
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": free,
    }
    return cells


def _matrix(tmp_path, rows, *, old=False, name="matrix.fs"):
    """Write a matrix of ``rows`` at the current layout, or at the frozen one."""
    from pyflightstream.cases.matrix import MATRIX_COLUMNS

    columns = [c for c in MATRIX_COLUMNS if not (old and c == "MESH_ROUTE")]
    lines = [" | ".join(columns), "-" * 40]
    lines += [" | ".join(row[c] for c in columns) for row in rows]
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def library(tmp_path):
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing.fsm")
    (workspace.inputs_dir / "geometries" / "demo.geom.toml").write_text(BODY_TOML, encoding="utf-8")
    return workspace


def _resolve(path, workspace):
    from pyflightstream.workspace.matrix import resolve_matrix

    return resolve_matrix(path, workspace, name="m", fs_version="26.120", recipes={})


# --- the layout ----------------------------------------------------------------------------


def test_the_current_layout_adds_mesh_route_right_after_geometry():
    from pyflightstream.cases.matrix import MATRIX_COLUMNS

    assert MATRIX_COLUMNS.index("MESH_ROUTE") == MATRIX_COLUMNS.index("GEOMETRY") + 1
    assert [c for c in MATRIX_COLUMNS if c != "MESH_ROUTE"] == OLD_HEADER


def test_the_frozen_layout_is_the_header_of_0_56_0():
    from pyflightstream.cases.matrix import RECOGNIZED_MATRIX_LAYOUTS

    assert tuple(OLD_HEADER) in RECOGNIZED_MATRIX_LAYOUTS


def test_an_old_header_reads_with_a_warning_and_the_route_unstated(tmp_path):
    from pyflightstream.cases.matrix import read_matrix

    path = _matrix(tmp_path, [_cells()], old=True)
    with pytest.warns(PyflightstreamDeprecationWarning, match="0.60.0") as caught:
        (row,) = read_matrix(path)
    assert "MESH_ROUTE" in str(caught[0].message) and "migrate" in str(caught[0].message)
    assert "MESH_ROUTE" not in row.variables
    assert row.pol == "7001"


def test_the_current_header_reads_with_no_layout_warning(tmp_path):
    from pyflightstream.cases.matrix import read_matrix

    path = _matrix(tmp_path, [_cells(route="native", geometry="demo.geom.toml")])
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamDeprecationWarning)
        (row,) = read_matrix(path)
    assert row.variables["MESH_ROUTE"] == "native"


def test_the_ledger_records_the_layout_promise():
    from pyflightstream._deprecations import DEPRECATIONS, MATRIX_LAYOUT_0_56_0

    assert MATRIX_LAYOUT_0_56_0 in DEPRECATIONS
    assert MATRIX_LAYOUT_0_56_0.removal_version == "0.60.0"
    assert "removed in v0.60.0" in MATRIX_LAYOUT_0_56_0.message()


def test_old_header_warns_and_migrates_with_no_byte_lost(tmp_path):
    from pyflightstream.cases.matrix import MATRIX_COLUMNS, read_matrix
    from pyflightstream.workspace.migrate import migrate_workspace

    workspace = make_library(tmp_path)
    path = _matrix(workspace.root, [_cells(), _cells(pol="7002")], old=True)
    original = path.read_bytes()
    preview = migrate_workspace(workspace.root)
    assert [c["file"] for c in preview if c.get("kind") == "matrix"] == ["matrix.fs"]
    assert path.read_bytes() == original  # a preview writes nothing
    applied = migrate_workspace(workspace.root, apply=True)
    assert any(c.get("kind") == "matrix" and c["applied"] for c in applied)
    assert (workspace.root / "matrix.fs.bak").read_bytes() == original
    migrated = path.read_bytes()
    header, *_ = migrated.decode().splitlines()
    assert tuple(c.strip() for c in header.split("|")) == MATRIX_COLUMNS
    # dropping the inserted cell of each line gives the original back
    index = MATRIX_COLUMNS.index("MESH_ROUTE")
    for before, after in zip(
        original.decode().splitlines(keepends=True),
        migrated.decode().splitlines(keepends=True),
        strict=True,
    ):
        if "|" in after:
            parts = after.split("|")
            del parts[index]
            after = "|".join(parts)
        assert after == before
    assert [r.pol for r in read_matrix(path)] == ["7001", "7002"]
    assert not any(c.get("kind") == "matrix" for c in migrate_workspace(workspace.root, apply=True))


def test_r27_matrix_backup_conflict_prevents_manifest_migration(tmp_path):
    from pyflightstream.workspace.manifest import WorkspaceError
    from pyflightstream.workspace.migrate import migrate_workspace

    workspace = make_library(tmp_path)
    matrix = _matrix(workspace.root, [_cells()], old=True)
    original = matrix.read_bytes()
    manifest = workspace.root / "runs.json"
    manifest.write_bytes(b"[]\r\n")
    backup = matrix.with_suffix(".fs.bak")
    backup.write_bytes(b"a different preserved matrix")
    with pytest.raises(WorkspaceError, match="different backup"):
        migrate_workspace(workspace.root, apply=True)
    assert manifest.read_bytes() == b"[]\r\n"
    assert not manifest.with_suffix(".json.bak").exists()
    assert matrix.read_bytes() == original
    assert backup.read_bytes() == b"a different preserved matrix"

    backup.write_bytes(original)
    changes = migrate_workspace(workspace.root, apply=True)
    assert {row["file"] for row in changes} == {"runs.json", "matrix.fs"}
    assert manifest.with_suffix(".json.bak").read_bytes() == b"[]\r\n"
    assert matrix.with_suffix(".fs.bak").read_bytes() == original
    assert b"MESH_ROUTE" in matrix.read_bytes()


def test_every_tracked_matrix_file_is_at_the_current_layout():
    from pyflightstream.cases.matrix import MATRIX_COLUMNS

    root = Path(__file__).resolve().parents[2]
    files = [
        *sorted((root / "examples").rglob("*.fs")),
        *sorted((root / "tests" / "tier1_offline" / "fixtures").glob("*.fs")),
        *sorted((root / "tests" / "tier3_licensed").glob("*.fs")),
    ]
    stale = []
    for path in files:
        header = next(
            (ln for ln in path.read_text(encoding="utf-8-sig").splitlines() if "|" in ln), ""
        )
        names = tuple(c.strip() for c in header.split("|"))
        legacy = path.name.startswith("pfs")  # fixtures of earlier layouts, kept as they were
        if "HIDDEN" in names and names != MATRIX_COLUMNS and not legacy:
            stale.append(path.name)
    assert files and not stale, f"not migrated: {stale}"


# --- the row keys and the refuse or warn table ------------------------------------------------


def test_the_geometry_row_keys_are_registered_on_every_run_type():
    from pyflightstream.cases.workflows import GEOMETRY_ROW_KEYS, ROW_KEY_MEANINGS

    assert set(GEOMETRY_ROW_KEYS) == {
        "MESH_ROUTE",
        "GEOM_CONFIGURATION",
        "GEOM_VARIANT",
        "GEOM_PARAMS",
        "MESH_CONTROLS",
    }
    assert set(GEOMETRY_ROW_KEYS) <= set(ROW_KEY_MEANINGS)


def test_an_unknown_route_refuses_that_row_and_the_others_bind(tmp_path, library):
    rows = [
        _cells(pol="7001", geometry="demo.geom.toml", route="warp_drive"),
        _cells(pol="7002"),
    ]
    resolved = _resolve(_matrix(tmp_path, rows), library)
    assert [case.sim_id for case in resolved.campaign.sims] == ["7002"]
    assert "warp_drive" in resolved.geometry_failures["7001"]["message"]
    assert len(resolved.row_builds) == 1


def test_mesh_entries_on_an_fsm_row_are_warned_and_skipped(tmp_path, library):
    rows = [
        _cells(
            route="quad_dominant",
            free="GEOM_VARIANT: cs / MESH_CONTROLS: wing.mesh.toml",
        )
    ]
    with pytest.warns(NotApplicableWarning) as caught:
        resolved = _resolve(_matrix(tmp_path, rows), library)
    said = " ".join(str(w.message) for w in caught)
    assert "MESH_ROUTE" in said and "GEOM_VARIANT" in said and "MESH_CONTROLS" in said
    assert [case.sim_id for case in resolved.campaign.sims] == ["7001"]
    assert not resolved.geometry_failures


def test_a_row_with_no_route_binds_the_case_it_bound_before(tmp_path, library):
    new = _resolve(_matrix(tmp_path, [_cells()], name="new.fs"), library)
    with pytest.warns(PyflightstreamDeprecationWarning):
        old = _resolve(_matrix(tmp_path, [_cells()], old=True, name="old.fs"), library)
    (a,), (b,) = new.campaign.sims, old.campaign.sims
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
    assert a.variables == b.variables


def _request(library, *, free=None, route=None):
    from pyflightstream.workspace import _geometry_row as row_module

    variables = {"GEOMETRY": "demo.geom.toml", **(free or {})}
    if route:
        variables["MESH_ROUTE"] = route
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return row_module.plan_row_geometry(
            variables, "7001", library.resolve_geometry, fs_build="26.120"
        )


def test_a_configuration_file_with_several_configurations_names_one(tmp_path, library):
    from pyflightstream.workspace import _geometry_row as row_module

    (library.inputs_dir / "geometries" / "demo.geom.toml").write_text(
        BODY_TOML
        + '[configurations.a]\nmembers = ["FUS"]\n[configurations.b]\nmembers = ["FUS"]\n',
        encoding="utf-8",
    )
    request = _request(library)
    assert request.route == "native"  # unstated: read as native
    with pytest.raises(row_module.GeometryRowError, match="a, b"):
        row_module.prepare_row_geometry(request, library.inputs_dir / "geometries")


# --- identity, reuse and failure --------------------------------------------------------------


def _fake_generation(calls, *, status="accepted"):
    """Return a runner that writes what a generation writes and records each call."""

    def fake(config, *, out, configuration=None, variant="clean", overrides=None, until="S13", **_):
        calls.append({"overrides": dict(overrides or {}), "until": until})
        folder = Path(out)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "demo.igs").write_text("iges", encoding="utf-8")
        report = {
            "status": status,
            "parameter_id": "p" * 64,
            "stage": "S4" if status == "failed" else None,
            "check": "law.monotonic" if status == "failed" else None,
            "message": "planted",
            "outputs": {"iges": str(folder / "demo.igs"), "members": ["FUS"]},
        }
        (folder / "report.json").write_text(json.dumps(report), encoding="utf-8")
        return report

    return fake


def test_row_and_api_give_the_same_identity(tmp_path, library):
    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geom_run import run_geometry

    request = _request(library, free={"GEOM_PARAMS": "{FUS.length_mm=2500.0}"})
    assert request.overrides == {"FUS.length_mm": 2500.0}
    api = run_geometry(
        library.inputs_dir / "geometries" / "demo.geom.toml",
        out=tmp_path / "api",
        overrides={"FUS.length_mm": 2500.0},
        until="S9",
    )
    parameter, _ = row_module.row_identity(request)
    other, _ = row_module.row_identity(_request(library))
    assert parameter == api["parameter_id"] != other


def test_equal_parameters_reuse_the_folder_and_other_parameters_do_not(tmp_path, library):
    from pyflightstream.workspace import _geometry_row as row_module

    calls: list = []
    fake = _fake_generation(calls)
    geometries = library.inputs_dir / "geometries"
    prepare = row_module.prepare_row_geometry
    first = prepare(_request(library), geometries, generate=fake)
    again = prepare(_request(library), geometries, generate=fake)
    other = prepare(
        _request(library, free={"GEOM_PARAMS": "{FUS.length_mm=2600.0}"}), geometries, generate=fake
    )
    assert (first.reused, again.reused, other.reused) == (False, True, False)
    assert first.folder == again.folder != other.folder
    assert len(calls) == 2 and first.folder.parent == geometries
    assert (first.folder / f"{first.name}.geometry.toml").is_file()
    assert not [p for p in geometries.iterdir() if p.name.endswith(".part")]


def test_a_failed_generation_loses_its_row_and_names_stage_check_and_report(tmp_path, library):
    from pyflightstream.workspace import _geometry_row as row_module

    fake = _fake_generation([], status="failed")
    with pytest.raises(row_module.GeometryRowError, match="S4.*law.monotonic") as caught:
        row_module.prepare_row_geometry(
            _request(library), library.inputs_dir / "geometries", generate=fake
        )
    assert caught.value.report_path is not None and caught.value.report_path.is_file()


def test_a_refused_row_does_not_stop_the_others_and_is_recorded(tmp_path, library):
    from pyflightstream.workspace import RunStatus
    from pyflightstream.workspace._geometry_row import record_geometry_failures

    rows = [
        _cells(
            pol="7001",
            geometry="demo.geom.toml",
            route="native",
            free="GEOM_PARAMS: {NOPE.length_mm=1.0}",
        ),
        _cells(pol="7002"),
    ]
    resolved = _resolve(_matrix(tmp_path, rows), library)
    assert [case.sim_id for case in resolved.campaign.sims] == ["7002"]
    assert "NOPE" in resolved.geometry_failures["7001"]["message"]
    record_geometry_failures(resolved.geometry_failures, library, resolved.campaign, "26.120")
    (record,) = library.read_manifest()
    assert record.status is RunStatus.GEOMETRY_FAILED and record.sim_id == "7001"
    assert not record.status.value.startswith("FAILED")


def test_a_generated_row_waits_for_the_geometry_stage_and_then_opens_its_fsm(tmp_path, library):
    from tests.tier1_offline._kernel_support import kernel_or_skip

    kernel_or_skip()
    rows = [_cells(geometry="demo.geom.toml", route="native"), _cells(pol="7002")]
    matrix = _matrix(tmp_path, rows)
    waiting = _resolve(matrix, library)
    message = waiting.geometry_failures["7001"]["message"]
    assert "geometry build gen-demo-" in message
    assert [case.sim_id for case in waiting.campaign.sims] == ["7002"]
    folder = next((library.inputs_dir / "geometries").glob("gen-demo-*"))
    (folder / f"{folder.name}.fsm").write_bytes(b"fake simulation")
    built = _resolve(matrix, library)
    case = built.campaign.sims[0]
    assert Path(case.geometry) == folder / f"{folder.name}.fsm"
    assert not built.geometry_failures


# --- the routes -------------------------------------------------------------------------------


def test_native_writes_a_cad_instruction_over_the_generated_iges(tmp_path, library):
    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

    calls: list = []
    built = row_module.prepare_row_geometry(
        _request(library, route="native"),
        library.inputs_dir / "geometries",
        generate=_fake_generation(calls),
    )
    instruction = read_geometry_instruction(built.folder / f"{built.name}.geometry.toml")
    assert instruction.kind == "cad" and instruction.cad.file == "demo.igs"
    assert instruction.fs_build == "26.120" and calls[0]["until"] == "S12.C"
    # The importer names the one body it converts "Model 0"; the instruction renames it to the
    # one word its boundaries state (record tests/tier3_licensed/data/g13-native-import.json).
    assert instruction.boundaries == ("demo",)
    assert [(o.op, o.surface, o.to) for o in instruction.operations] == [
        ("rename", "Model 0", "demo")
    ]


def test_quad_dominant_meshes_with_strategy_1_and_hands_the_mesh_over(
    tmp_path, library, monkeypatch
):
    from functools import partial

    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

    calls: list = []
    seen: dict = {}

    class Result:
        record = {"members": ["FUS"], "accepted": True}
        written: dict = {}

    def strategy_1(config, controls, *, out, descriptor, **_):
        seen.update(controls=controls, descriptor=descriptor)
        (Path(out) / f"{descriptor}.obj").write_text("o FUS\n", encoding="utf-8")
        return Result()

    monkeypatch.setitem(
        row_module.MESH_STRATEGIES,
        "quad_dominant",
        partial(row_module.mesh_with_strategy_1, mesh_configuration=strategy_1),
    )
    (library.inputs_dir / "geometries" / "demo.mesh.toml").write_text("[mesh]\n", encoding="utf-8")
    built = row_module.prepare_row_geometry(
        _request(library, route="quad_dominant"),
        library.inputs_dir / "geometries",
        generate=_fake_generation(calls),
    )
    instruction = read_geometry_instruction(built.folder / f"{built.name}.geometry.toml")
    assert instruction.kind == "mesh" and instruction.mesh.file == f"{built.name}.obj"
    assert seen["controls"]["mesh"] == {"strategy": 1, "variant": "clean"}
    assert seen["descriptor"] == built.name
    assert calls[0]["until"] == "S11"


def test_quad_dominant_with_no_controls_file_is_refused_by_name(tmp_path, library):
    from functools import partial

    from pyflightstream.workspace import _geometry_row as row_module

    mesher = partial(row_module.mesh_with_strategy_1, mesh_configuration=lambda *a, **k: None)
    with pytest.raises(row_module.GeometryRowError, match="demo.mesh.toml"):
        mesher(_request(library, route="quad_dominant"), tmp_path, "x", {})


def test_full_grid_is_refused_by_name_before_anything_is_generated(tmp_path, library, monkeypatch):
    """A route whose mesher entry is None (a tree without strategy 2) is refused by name."""
    from pyflightstream.workspace import _geometry_row as row_module

    monkeypatch.setitem(row_module.MESH_STRATEGIES, "full_grid", None)
    calls: list = []
    with pytest.raises(row_module.GeometryRowError, match="strategy 2"):
        row_module.prepare_row_geometry(
            _request(library, route="full_grid"),
            library.inputs_dir / "geometries",
            generate=_fake_generation(calls),
        )
    assert not calls


def test_a_mesher_set_for_full_grid_is_the_one_called(tmp_path, library, monkeypatch):
    """The lane of strategy 2 sets its entry; the route reaches exactly that function."""
    from pyflightstream.workspace import _geometry_row as row_module

    reached: list = []
    (library.inputs_dir / "geometries" / "demo.mesh.toml").write_text(
        "[mesh]\nstrategy = 2\n", encoding="utf-8"
    )
    monkeypatch.setitem(
        row_module.MESH_STRATEGIES, "full_grid", lambda *args: reached.append("full_grid")
    )
    row_module.prepare_row_geometry(
        _request(library, route="full_grid"),
        library.inputs_dir / "geometries",
        generate=_fake_generation([]),
    )
    assert reached == ["full_grid"]


def test_an_iges_row_with_a_route_builds_through_cad_and_without_one_is_refused_as_before(
    tmp_path, library
):
    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

    (library.inputs_dir / "geometries" / "wing.igs").write_text("iges", encoding="utf-8")
    variables = {"GEOMETRY": "wing.igs"}
    assert row_module.plan_row_geometry(variables, "7001", library.resolve_geometry) is None
    request = row_module.plan_row_geometry(
        {**variables, "MESH_ROUTE": "native"}, "7001", library.resolve_geometry, fs_build="26.120"
    )
    built = row_module.prepare_row_geometry(request, library.inputs_dir / "geometries")
    instruction = read_geometry_instruction(built.folder / f"{built.name}.geometry.toml")
    assert instruction.kind == "cad" and instruction.cad.file == "wing.igs"
    mesh = row_module.plan_row_geometry(
        {**variables, "MESH_ROUTE": "quad_dominant"}, "7001", library.resolve_geometry
    )
    with pytest.raises(row_module.GeometryRowError, match="IGES"):
        row_module.prepare_row_geometry(mesh, library.inputs_dir / "geometries")


def test_configuration_entries_on_an_iges_row_are_warned_and_skipped(library):
    """API-005: GEOM_CONFIGURATION, GEOM_VARIANT and GEOM_PARAMS on an IGES row are skipped."""
    from pyflightstream.workspace import _geometry_row as row_module

    (library.inputs_dir / "geometries" / "wing.igs").write_text("iges", encoding="utf-8")
    variables = {
        "GEOMETRY": "wing.igs",
        "MESH_ROUTE": "native",
        "GEOM_CONFIGURATION": "clean",
        "GEOM_VARIANT": "cs",
        "GEOM_PARAMS": "{main.planform.span=12}",
    }
    with pytest.warns(NotApplicableWarning) as caught:
        request = row_module.plan_row_geometry(variables, "7001", library.resolve_geometry)
    said = [str(w.message) for w in caught if issubclass(w.category, NotApplicableWarning)]
    for key in ("GEOM_CONFIGURATION", "GEOM_VARIANT", "GEOM_PARAMS"):
        assert any(key in text and "wing.igs" in text for text in said), key
    assert request.kind == "iges" and not request.overrides and request.configuration is None


def test_migrate_help_names_the_mesh_route_column_and_apply(capsys):
    """API-006: pyfs-workspace migrate --help says what it migrates and what --apply does."""
    from pyflightstream.workspace.cli import main

    with pytest.raises(SystemExit):
        main(["migrate", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "MESH_ROUTE" in text
    assert "--apply write the .bak backups" in text


def test_a_matrix_whose_every_row_failed_is_refused_naming_each(tmp_path, library):
    from pyflightstream.cases.matrix import MatrixError

    rows = [
        _cells(pol="7001", geometry="demo.geom.toml", route="warp"),
        _cells(pol="7002", geometry="demo.geom.toml", route="drive"),
    ]
    with pytest.raises(MatrixError, match="7001.*warp.*7002.*drive"):
        _resolve(_matrix(tmp_path, rows), library)


class _Item:
    def __init__(self, passed, gates=()):
        self.passed = passed
        self.failed_gates = gates


def _native_matrix(tmp_path, geometry="demo.geom.toml", route="native"):
    return _matrix(tmp_path, [_cells(geometry=geometry, route=route)])


def test_a_run_builds_the_native_geometry_that_is_missing_with_the_solver(tmp_path, library):
    build_native_rows = importlib.import_module(
        "pyflightstream.workspace._native_rows"
    ).build_native_rows

    asked: list = []

    def solver(folder, build, fs_exe):
        asked.append((folder.name, build))
        return (_Item(True),)

    calls: list = []
    names = build_native_rows(
        _native_matrix(tmp_path),
        library,
        default_build="26.120",
        build=solver,
        generate=_fake_generation(calls),
    )
    assert len(names) == 1 and names[0].startswith("gen-demo-")
    assert asked == [(names[0], "26.120")]


def test_a_native_geometry_already_built_is_not_built_again(tmp_path, library):
    build_native_rows = importlib.import_module(
        "pyflightstream.workspace._native_rows"
    ).build_native_rows

    calls: list = []
    matrix = _native_matrix(tmp_path)
    build_native_rows(
        matrix,
        library,
        default_build="26.120",
        build=lambda *a: (_Item(True),),
        generate=_fake_generation(calls),
    )
    folder = next((library.inputs_dir / "geometries").glob("gen-demo-*"))
    (folder / f"{folder.name}.fsm").write_bytes(b"fake simulation")

    def solver(*_):
        pytest.fail("a seat was spent on a geometry that is built")

    assert (
        build_native_rows(
            matrix, library, default_build="26.120", build=solver, generate=_fake_generation(calls)
        )
        == []
    )


def test_a_native_build_that_fails_its_audit_warns_and_lists_nothing(tmp_path, library):
    from pyflightstream.exceptions import PyflightstreamWarning

    build_native_rows = importlib.import_module(
        "pyflightstream.workspace._native_rows"
    ).build_native_rows

    calls: list = []
    with pytest.warns(PyflightstreamWarning, match="G1 on"):
        names = build_native_rows(
            _native_matrix(tmp_path),
            library,
            default_build="26.120",
            build=lambda *a: (_Item(False, ("G1 on (whole mesh)",)),),
            generate=_fake_generation(calls),
        )
    assert names == []


def test_a_row_that_is_not_native_is_not_built_by_the_solver(tmp_path, library):
    build_native_rows = importlib.import_module(
        "pyflightstream.workspace._native_rows"
    ).build_native_rows

    def solver(*_):
        pytest.fail("a seat was spent")

    matrix = _native_matrix(tmp_path, geometry="wing.fsm", route="NA")
    assert build_native_rows(matrix, library, default_build="26.120", build=solver) == []


class _StopError(Exception):
    pass


def test_run_matrix_passes_selected_rows_to_native_builder(monkeypatch):
    module = importlib.import_module("pyflightstream.run.matrix")
    rows = [SimpleNamespace(pol="7001", variables={})]
    monkeypatch.setattr(module, "_selected", lambda *a, **kw: (rows, ["7001"]))
    monkeypatch.setattr(module, "settle_the_matrix_default", lambda *a, **kw: ("26.120", rows))

    def build(*args, **kwargs):
        assert kwargs["rows"] is rows
        raise _StopError

    monkeypatch.setattr(module, "build_native_geometries", build)
    with pytest.raises(_StopError):
        module.run_matrix(
            "unused", object(), name="test", recipes={}, assess=object(), sims=["7001"]
        )


def test_grouped_run_passes_receipt_selection_to_native_builder(monkeypatch):
    module = importlib.import_module("pyflightstream.run._batch_run")
    rows = [SimpleNamespace(pol="7001", variables={})]
    monkeypatch.setattr(module, "read_matrix", lambda path: rows)
    monkeypatch.setattr(module, "refuse_silent_rows_without_default", lambda *args: None)
    monkeypatch.setattr(module, "_selected", lambda *a, **kw: (rows, ["7001"]), raising=False)
    monkeypatch.setattr(module, "preflight_before_native_build", lambda *a, **kw: None)

    def build(*args, **kwargs):
        assert kwargs["rows"] is rows
        raise _StopError

    monkeypatch.setattr(module, "build_native_geometries", build)
    receipt = SimpleNamespace(jobs=[SimpleNamespace(sims=["7001"])])
    with pytest.raises(_StopError):
        module._bound_matrix("unused", object(), receipt, {"name": "test", "fs_version": "26.120"})


def test_run_matrix_passes_its_executor_to_native_builder(monkeypatch):
    """R28-007: the executor a caller gives run_matrix also runs the native build."""
    module = importlib.import_module("pyflightstream.run.matrix")
    rows, supplied = [SimpleNamespace(pol="7001", variables={})], object()
    monkeypatch.setattr(module, "_selected", lambda *a, **kw: (rows, ["7001"]))
    monkeypatch.setattr(module, "settle_the_matrix_default", lambda *a, **kw: ("26.120", rows))

    def build(*args, **kwargs):
        assert kwargs["executor"] is supplied
        raise _StopError

    monkeypatch.setattr(module, "build_native_geometries", build)
    with pytest.raises(_StopError):
        module.run_matrix(
            "unused", object(), name="test", recipes={}, assess=object(), executor=supplied
        )


def test_grouped_run_passes_its_executor_to_native_builder(monkeypatch):
    module = importlib.import_module("pyflightstream.run._batch_run")
    rows, supplied = [SimpleNamespace(pol="7001", variables={})], object()
    monkeypatch.setattr(module, "read_matrix", lambda path: rows)
    monkeypatch.setattr(module, "refuse_silent_rows_without_default", lambda *args: None)
    monkeypatch.setattr(module, "_selected", lambda *a, **kw: (rows, ["7001"]), raising=False)
    monkeypatch.setattr(module, "preflight_before_native_build", lambda *a, **kw: None)

    def build(*args, **kwargs):
        assert kwargs["executor"] is supplied
        raise _StopError

    monkeypatch.setattr(module, "build_native_geometries", build)
    receipt = SimpleNamespace(jobs=[SimpleNamespace(sims=["7001"])])
    kw = {"name": "test", "fs_version": "26.120", "executor": supplied}
    with pytest.raises(_StopError):
        module._bound_matrix("unused", object(), receipt, kw)


def test_missing_plan_receipt_is_refused_before_native_build(monkeypatch, library):
    """R28-008: with require_plan, a missing receipt is refused before any build call."""
    from pyflightstream.cases.matrix import MatrixError

    module = importlib.import_module("pyflightstream.run.matrix")
    rows, built = [SimpleNamespace(pol="7001", variables={})], []
    monkeypatch.setattr(module, "_selected", lambda *a, **kw: (rows, ["7001"]))
    monkeypatch.setattr(module, "settle_the_matrix_default", lambda *a, **kw: ("26.120", rows))
    monkeypatch.setattr(module, "build_native_geometries", lambda *a, **kw: built.append(True))
    monkeypatch.setattr(module, "resolve_matrix", lambda *a, **kw: built.append("bound"))
    with pytest.raises(MatrixError, match="no plan for this matrix"):
        module.run_matrix(
            library.root / "matrix.txt",
            library,
            name="test",
            recipes={},
            assess=object(),
            require_plan=True,
        )
    assert built == []


def test_grouped_run_refuses_a_missing_plan_receipt_before_native_build(monkeypatch, library):
    from pyflightstream.cases.matrix import MatrixError

    module = importlib.import_module("pyflightstream.run._batch_run")
    rows, built = [SimpleNamespace(pol="7001", variables={})], []
    monkeypatch.setattr(module, "read_matrix", lambda path: rows)
    monkeypatch.setattr(module, "refuse_silent_rows_without_default", lambda *args: None)
    monkeypatch.setattr(module, "_selected", lambda *a, **kw: (rows, ["7001"]), raising=False)
    monkeypatch.setattr(module, "build_native_geometries", lambda *a, **kw: built.append(True))
    receipt = SimpleNamespace(jobs=[SimpleNamespace(sims=["7001"])])
    with pytest.raises(MatrixError, match="no plan for this matrix"):
        module._bound_matrix(
            library.root / "matrix.txt", library, receipt, {"name": "test", "fs_version": "26.120"}
        )
    assert built == []


def _one_pending_build(monkeypatch, tmp_path):
    """Make the real row loop ask the solver for one build of the folder ``wing``."""
    native = importlib.import_module("pyflightstream.workspace._native_rows")
    folder = tmp_path / "geometries" / "wing"

    def one(row, workspace, build, exe, *, solver, generate):
        solver(folder, build, exe)
        return "wing"

    monkeypatch.setattr(native, "_build_one", one)
    return [SimpleNamespace(pol="7001", fs_build="26.127", variables={"GEOMETRY": "wing"})]


def test_native_builder_runs_a_supplied_synchronous_executor(monkeypatch, tmp_path):
    identity = importlib.import_module("pyflightstream.run._identity")
    verbs = importlib.import_module("pyflightstream.run._cli_geometry")
    rows, ran = _one_pending_build(monkeypatch, tmp_path), []

    class Synchronous:
        submits = False

        def run_script(self, script, working_dir, timeout_s=None):
            ran.append(script)
            return SimpleNamespace(
                log_text="", stdout="", stderr="", failed=False, return_code=0, wall_time_s=1.0
            )

    def never(*args, **kwargs):
        raise AssertionError("a local executor or a local executable was asked for")

    plan = SimpleNamespace(root=tmp_path, build_id="26.127")
    monkeypatch.setattr(verbs, "plan_geometry_build", lambda folder, build: plan)
    monkeypatch.setattr(verbs, "refuse_before_running", lambda plan, overwrite: None)
    monkeypatch.setattr(verbs, "resolve_build", never)
    monkeypatch.setattr(verbs, "LocalExecutor", never)

    def apply(plan, runner, package_version):
        runner(tmp_path / "build.txt", tmp_path)
        return (SimpleNamespace(passed=True),)

    monkeypatch.setattr(verbs, "apply_geometry_build", apply)
    names = identity.build_native_geometries(
        "unused", object(), default_build="26.127", rows=rows, executor=Synchronous()
    )
    assert names == ["wing"] and ran == [tmp_path / "build.txt"]


def test_native_builder_refuses_a_submitting_executor_by_name(monkeypatch, tmp_path):
    from pyflightstream.run import ExecutorConfigurationError

    identity = importlib.import_module("pyflightstream.run._identity")
    verbs = importlib.import_module("pyflightstream.run._cli_geometry")
    rows = _one_pending_build(monkeypatch, tmp_path)

    def never(*args, **kwargs):
        raise AssertionError("a submitting executor reached the geometry build")

    monkeypatch.setattr(verbs, "apply_geometry_build", never)
    monkeypatch.setattr(verbs, "plan_geometry_build", never)

    class Cluster:
        submits = True

    with pytest.raises(ExecutorConfigurationError) as raised:
        identity.build_native_geometries(
            "unused", object(), default_build="26.127", rows=rows, executor=Cluster()
        )
    message = str(raised.value)
    assert "native geometry needs a synchronous build first" in message
    assert "Cluster submits jobs" in message
    assert "pyfs-workspace geometry build" in message and "--apply --build 26.127" in message


def test_native_boundary_keeps_dots_in_configuration_stem(tmp_path, library):
    from dataclasses import replace

    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

    request = _request(library, route="native")
    source = request.source.with_name("demo.extra.geom.toml")
    source.write_text(request.source.read_text(encoding="utf-8"), encoding="utf-8")
    built = row_module.prepare_row_geometry(
        replace(request, source=source),
        library.inputs_dir / "geometries",
        generate=_fake_generation([]),
    )
    instruction = read_geometry_instruction(built.folder / f"{built.name}.geometry.toml")
    assert instruction.boundaries == ("demo.extra",)
    assert instruction.operations[0].to == "demo.extra"


def test_native_boundary_keeps_dots_in_iges_stem(tmp_path, library):
    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

    source = library.inputs_dir / "geometries" / "wing.extra.igs"
    source.write_text("iges", encoding="utf-8")
    request = row_module.plan_row_geometry(
        {"GEOMETRY": source.name, "MESH_ROUTE": "native"},
        "7001",
        library.resolve_geometry,
        fs_build="26.120",
    )
    built = row_module.prepare_row_geometry(request, library.inputs_dir / "geometries")
    instruction = read_geometry_instruction(built.folder / f"{built.name}.geometry.toml")
    assert instruction.boundaries == ("wing.extra",)


@pytest.mark.parametrize("route", ["quad_dominant", "full_grid"])
def test_r27_rejected_mesh_never_gets_a_build_instruction(tmp_path, library, monkeypatch, route):
    from functools import partial
    from types import SimpleNamespace

    from pyflightstream.workspace import _geometry_row as row_module

    def rejected(config, controls, *, out, descriptor):
        obj = Path(out) / f"{descriptor}.obj"
        obj.write_text("o FUS\n", encoding="utf-8")
        return SimpleNamespace(
            record={
                "members": ["FUS"],
                "accepted": False,
                "checks": [{"id": "mesh.inverted", "status": "failed"}],
            },
            written={"obj": str(obj)},
        )

    writer = (
        partial(row_module.mesh_with_strategy_1, mesh_configuration=rejected)
        if route == "quad_dominant"
        else partial(row_module.mesh_with_strategy_2, mesh_full_grid=rejected)
    )
    monkeypatch.setitem(row_module.MESH_STRATEGIES, route, writer)
    geometries = library.inputs_dir / "geometries"
    (geometries / "demo.mesh.toml").write_text("[mesh]\n", encoding="utf-8")
    with pytest.raises(row_module.GeometryRowError, match="mesh.inverted"):
        row_module.prepare_row_geometry(
            _request(library, route=route), geometries, generate=_fake_generation([])
        )
    assert not list(geometries.glob("gen-*/*.geometry.toml"))


@pytest.mark.parametrize("kind", ["configuration", "iges"])
def test_r27_build_specific_instructions_do_not_share_a_cache(library, kind):
    from dataclasses import replace

    from pyflightstream.workspace import _geometry_row as row_module
    from pyflightstream.workspace._geometry_instruction import read_geometry_instruction

    request = _request(library, route="native")
    geometries = library.inputs_dir / "geometries"
    if kind == "iges":
        source = geometries / "blade.igs"
        source.write_text("iges", encoding="utf-8")
        request = replace(request, kind="iges", source=source)
    first = row_module.prepare_row_geometry(request, geometries, generate=_fake_generation([]))
    second = row_module.prepare_row_geometry(
        replace(request, fs_build="26.121"), geometries, generate=_fake_generation([])
    )
    assert first.folder != second.folder
    assert (
        read_geometry_instruction(second.folder / f"{second.name}.geometry.toml").fs_build
        == "26.121"
    )


@pytest.mark.parametrize("explicit", [False, True])
def test_r27_mesh_control_bytes_are_part_of_the_row_cache_key(library, explicit):
    from pyflightstream.workspace import _geometry_row as row_module

    geometries = library.inputs_dir / "geometries"
    controls = geometries / ("custom.mesh.toml" if explicit else "demo.mesh.toml")
    controls.write_text("[mesh]\nstrategy = 1\n", encoding="utf-8")
    free = {"MESH_CONTROLS": controls.name} if explicit else {}
    request = _request(library, route="quad_dominant", free=free)
    before = row_module.row_identity(request)
    controls.write_text("[mesh]\nstrategy = 1\n[defaults.body]\nx_cells = 100\n", encoding="utf-8")
    after = row_module.row_identity(request)
    assert before[0] == after[0]  # geometric parameters are unchanged
    assert before[1] != after[1]  # the realized mesh must not be reused


@pytest.mark.parametrize("bad", ["missing", "malformed"])
def test_r27_bad_geometry_input_does_not_abort_healthy_rows(tmp_path, library, bad):
    source = library.inputs_dir / "geometries" / "demo.geom.toml"
    if bad == "malformed":
        source.write_text("[components.FUS\n", encoding="utf-8")
    geometry = "missing.geom.toml" if bad == "missing" else source.name
    rows = [_cells(geometry=geometry, route="native"), _cells(pol="7002")]
    resolved = _resolve(_matrix(tmp_path, rows), library)
    assert [case.sim_id for case in resolved.campaign.sims] == ["7002"]
    assert "7001" in resolved.geometry_failures
    assert resolved.geometry_failures["7001"]["message"]


@pytest.mark.parametrize("route,strategy", [("quad_dominant", 1), ("full_grid", 2)])
def test_r27_row_selection_reaches_mesh_controls(library, tmp_path, route, strategy):
    from types import SimpleNamespace

    from pyflightstream.workspace import _geometry_row as row_module

    geometries = library.inputs_dir / "geometries"
    (geometries / "demo.geom.toml").write_text(
        BODY_TOML + '[configurations.chosen]\nmembers = ["FUS"]\n', encoding="utf-8"
    )
    controls_path = geometries / "demo.mesh.toml"
    original = '[mesh]\nstrategy = 2\nconfiguration = "other"\n'
    controls_path.write_text(original, encoding="utf-8")
    seen = {}

    def mesher(config, controls, *, out, descriptor):
        import tomllib

        raw = tomllib.loads(Path(controls).read_text()) if isinstance(controls, Path) else controls
        seen.update(raw["mesh"])
        (Path(out) / f"{descriptor}.obj").write_text("o FUS\n", encoding="utf-8")
        return SimpleNamespace(record={"accepted": True, "members": ["FUS"]}, written={})

    request = _request(library, route=route, free={"GEOM_CONFIGURATION": "chosen"})
    if strategy == 1:
        row_module.mesh_with_strategy_1(request, tmp_path, "mesh", {}, mesh_configuration=mesher)
    else:
        row_module.mesh_with_strategy_2(request, tmp_path, "mesh", {}, mesh_full_grid=mesher)
    assert seen["configuration"] == "chosen"
    assert seen["strategy"] == strategy
    assert seen["variant"] == "clean"
    assert controls_path.read_text(encoding="utf-8") == original


def _generation_with_records(source_path):
    """A runner that writes the report, a stage record and the run log, all naming its outputs
    by absolute path inside the folder it is given, as the geometry runner does."""

    def fake(config, *, out, configuration=None, variant="clean", overrides=None, until="S13", **_):
        folder = Path(out)
        folder.mkdir(parents=True, exist_ok=True)
        iges = folder / "demo.igs"
        iges.write_text("iges", encoding="utf-8")
        outputs = {
            "iges": str(iges),
            "files": [str(iges)],
            "source": str(source_path),
            "iges_sha256": "a" * 64,
        }
        record = {"stage": "S12", "name": "export", "status": "passed", "outputs": outputs}
        (folder / "S12.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        report = {
            "status": "accepted",
            "parameter_id": "p" * 64,
            "outputs": {**outputs, "members": ["FUS"]},
        }
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (folder / "geom-run.log").write_text(
            f"configuration file: {source_path}\n  file or output iges: {json.dumps(str(iges))}\n",
            encoding="utf-8",
        )
        return report

    return fake


def test_r27_013_published_row_records_name_the_published_folder(library):
    """After the rename, every output reference of the report, the stage records and the run
    log points into the published folder; the input path and the hash are kept as they were,
    on the first publication and when the folder is reused."""
    from pyflightstream.workspace import _geometry_row as row_module

    geometries = library.inputs_dir / "geometries"
    request = _request(library, route="native")
    fake = _generation_with_records(request.source)
    for expected_reuse in (False, True):
        built = row_module.prepare_row_geometry(request, geometries, generate=fake)
        assert built.reused is expected_reuse
        published = built.folder / "demo.igs"
        stage = json.loads((built.folder / "S12.json").read_text(encoding="utf-8"))
        persisted = json.loads((built.folder / "report.json").read_text(encoding="utf-8"))
        for outputs in (built.report["outputs"], persisted["outputs"], stage["outputs"]):
            assert Path(outputs["iges"]) == published and Path(outputs["iges"]).is_file()
            assert [Path(p) for p in outputs["files"]] == [published]
            assert outputs["source"] == str(request.source)
            assert outputs["iges_sha256"] == "a" * 64
        log = (built.folder / "geom-run.log").read_text(encoding="utf-8")
        assert ".part" not in log
        assert json.dumps(str(published)) in log
        assert f"configuration file: {request.source}" in log
