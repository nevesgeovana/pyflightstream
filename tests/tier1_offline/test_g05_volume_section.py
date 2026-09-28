# GEOVERSE_HEADER
# file_version: "1.0.1"
# last_modified_at: 2026-09-28T00:24:35.366Z
# last_modified_by: OpenAI / Codex / GPT-6 / vv-engineer-pyflightstream
# dependencies: [pyflightstream.cases.workflows, test_workflows.py]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Preserve missing-frame refusal and prove unsteady REFERENCE volume sampling.
# revision_source: git
"""Tier 1: a volume section declared in the pproc, created and exported per steady point (G05).

Pipeline role: quality gate on FR-110 of 0.27.0.

The GUI draws a flow-field plane through the solution and saves it to VTK or
Tecplot; before 0.27.0 no row could, because none of the ten volume-section
commands was emitted by anything but the licensed probes. The pproc's
``[volume_section]`` table now declares ONE plane, and each point of a steady
row creates it after its solve and exports it under the point's own name:

* the table is validated where the artifact is read, each shape with its own
  keys, and ``[exports]`` cannot name the volume kinds;
* the section is created in the analysis phase, after ``START_SOLVER``, where
  the verified probes created it, and exported with the index it takes: 1,
  unless a raw line of the row cut a section before it;
* each later point of a warm sweep deletes the previous section first, by its
  own index, so the export names that point's file with that point's plane;
* every point computes its section with ``UPDATE_ALL_VOLUME_SECTIONS`` between
  the cut and the export (RPT-070: exported without it, every cell was 0.0);
* the file is never handed to a surface kind (``_vsec`` is claimed first),
  while a run recorded before 0.27.0 keeps its ``_vsec`` files the surface
  exports they were when written;
* an unsteady or rotor row naming the table is refused before any emission;
* the file is collected into the point's folder and hashed in the record;
* the table's metres reach the solver in the simulation's length unit.

Nothing here runs a solver. What the delete-then-create sequence does on a
seat is not measured: DELETE_VOLUME_SECTION is verified alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream._digest import file_sha256
from pyflightstream.cases import (
    CampaignConfigError,
    PprocSpec,
    RawCommand,
    ReferenceData,
    SimCase,
    SweepAxis,
    case_at_point,
    classify_outputs,
)
from pyflightstream.cases.workflows import (
    WORKFLOW_KEY,
    build_script,
    build_steady_sweep,
    workflow_registry,
)
from pyflightstream.post.products import _prov_document, write_campaign_products
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_g06_actuator_disc import (
    MILLIMETRES,
    WING_PHY,
    _saved_block,
    _saved_copy,
)
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case

RECTANGLE = {"shape": "rectangle", "plane": "XZ", "corners_m": [-1, -1, 1, 1], "points": [2, 2]}
CIRCLE = {
    "shape": "circle",
    "plane": "YZ",
    "offset_m": 1.5,
    "radii_m": [0.2, 1.0],
    "points": [10, 12],
    "format": "tecplot",
}

#: A circle the row's raw line cuts at the analysis seam, BEFORE the pproc's own
#: section: the raw entry is accepted there, and it is emitted once per point.
RAW_CIRCLE = RawCommand(
    command="CREATE_NEW_CIRCLE_VOLUME_SECTION 1 YZ 0.5 10 12 0.2 1.0 NONE 0.1 1 1.2",
    before="analysis",
)


def _pproc(**table: object) -> PprocSpec:
    return PprocSpec.model_validate({"volume_section": table})


def _steady(pproc: PprocSpec, *, stem: str = "P", alpha: float = 0.0) -> SimCase:
    """A steady row as the matrix path builds it: a reference, so MRP exists, and
    the outputs the pproc declares rendered for one point."""
    return SimCase(
        sim_id="9005",
        aircraft="Wing",
        sweep=SweepAxis(type="alpha", values=[alpha]),
        recipe="steady",
        outputs=[name.replace("{name}", stem) for name in pproc.outputs(unsteady=False)],
        variables={WORKFLOW_KEY: "steady", "VELOCITY": "30.0"},
        point={"alpha": alpha},
        reference=ReferenceData(area=1.0, length=1.0, moment_point_m=(0.25, 0.0, 0.0)),
        pproc=pproc,
        pproc_id="p005",
    )


def _lines(case: SimCase, build: str = "26.124") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def test_g05_a_pproc_declares_one_volume_section():
    """Sample sources are native exports; the requested field is written at post."""
    for format_name in ("vtk", "tecplot"):
        pproc = _pproc(**{**RECTANGLE, "format": format_name})
        assert "{name}_probes.txt" in pproc.outputs(unsteady=False)
        assert "{name}_plots.txt" in pproc.outputs(unsteady=True)
        assert not any("_vsec" in name for name in pproc.outputs(unsteady=False))
        assert pproc.volume_section.format == format_name


@pytest.mark.parametrize(
    ("table", "words"),
    [
        ({**RECTANGLE, "radii_m": [0.1, 0.5]}, "shape = 'rectangle' states radii_m"),
        ({**RECTANGLE, "points": [1, 4]}, "at least 2 samples"),
        ({"shape": "rectangle", "plane": "XZ"}, "shape = 'rectangle' needs corners_m"),
        ({**CIRCLE, "corners_m": [-1, -1, 1, 1]}, "shape = 'circle' states corners_m"),
        ({**CIRCLE, "refinement_layers": 2}, "shape = 'circle' states refinement_layers"),
        (
            {key: value for key, value in CIRCLE.items() if key != "points"},
            "shape = 'circle' needs points; a circle takes radii_m",
        ),
        ({**CIRCLE, "radii_m": [1.0, 0.2]}, "inner radius"),
        ({**RECTANGLE, "corners_m": [-1, 0, 1, 0]}, "enclose no area"),
        ({**RECTANGLE, "plane": "XX"}, r"volume_section\.plane"),
        ({**RECTANGLE, "prisms_type": "PRISMS"}, r"volume_section\.prisms_type"),
        # The lengths carry their unit in the key; the bare word is not a key.
        ({**CIRCLE, "offset": 1.5}, r"volume_section\.offset\b"),
    ],
)
def test_g05_a_malformed_volume_section_is_refused_naming_the_key(table, words):
    """Each shape takes its own keys, and the refusal says which key is wrong.

    The prism arguments are not the table's: the package writes the filler the
    verified probes sent, so a table stating one is refused as a key it does not
    have rather than read.
    """
    with pytest.raises(ValidationError, match=words):
        _pproc(**table)


def test_g05_the_exports_table_cannot_name_the_volume_kinds():
    """The format lives on the section; [exports] saying it too would be two homes."""
    with pytest.raises(ValidationError, match=r"\[volume_section\] format"):
        PprocSpec.model_validate({"exports": {"volume_section_vtk": True}})


def test_g05_the_section_is_created_after_the_solve_and_exported_to_its_point():
    """Steady planes sample the solved field and export its probe values."""
    for table in (RECTANGLE, CIRCLE):
        lines = _lines(_steady(_pproc(**table)))
        solve = lines.index("START_SOLVER")
        clear = lines.index("DELETE_PROBE_POINTS")
        create = next(i for i, line in enumerate(lines) if line.startswith("NEW_PROBE_POINT"))
        export = lines.index("EXPORT_PROBE_POINTS")
        assert solve < clear < create < export
        assert lines[export + 1] == "P_probes.txt"
        assert not any("VOLUME_SECTION" in line for line in lines)


def test_g05_a_frame_the_run_did_not_create_is_refused():
    """The pproc names the frame; a row whose run made no such frame is told which it made."""
    with pytest.raises(CampaignConfigError, match=r"'HUB' for the volume section.*created: MRP"):
        _lines(_steady(_pproc(**{**RECTANGLE, "frame": "HUB"})))


def test_g05_each_point_of_a_warm_sweep_exports_its_own_section():
    """Every point rebuilds its survey so previous or saved probes cannot shift IDs."""
    pproc = _pproc(**RECTANGLE)
    points = [
        case_at_point(_steady(pproc, stem=f"P-A{int(a):+d}", alpha=a), {"alpha": a})
        for a in (-2.0, 0.0, 2.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script)
    lines = script.render().splitlines()
    assert lines.count("START_SOLVER") == lines.count("DELETE_PROBE_POINTS") == 3
    assert lines.count("EXPORT_PROBE_POINTS") == 3
    assert len(script.probe_field_layout) == 1
    assert len(script.probe_points) == 4
    assert not any("VOLUME_SECTION" in line for line in lines)


def test_g05_the_export_cites_the_pproc_s_own_section_after_a_raw_one():
    """A preexisting native section cannot select the sampled plane's data."""
    case = _steady(_pproc(**RECTANGLE)).model_copy(update={"raw_commands": [RAW_CIRCLE]})
    lines = _lines(case)
    assert RAW_CIRCLE.command in lines
    assert "EXPORT_PROBE_POINTS" in lines
    assert not any(line.startswith("EXPORT_VOLUME_SECTION") for line in lines)


def test_g05_a_sweep_deletes_and_exports_the_pproc_s_own_section_beside_raw_ones():
    """Native section indices do not participate in either sampled point."""
    pproc = _pproc(**RECTANGLE)
    points = [
        case_at_point(
            _steady(pproc, stem=f"P{a}", alpha=a).model_copy(update={"raw_commands": [RAW_CIRCLE]}),
            {"alpha": a},
        )
        for a in (0.0, 2.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script)
    lines = script.render().splitlines()
    assert lines.count(RAW_CIRCLE.command) == 2
    assert lines.count("DELETE_PROBE_POINTS") == lines.count("EXPORT_PROBE_POINTS") == 2
    assert not any(
        line.startswith(("DELETE_VOLUME_SECTION", "EXPORT_VOLUME_SECTION")) for line in lines
    )


def test_g05_a_volume_file_with_no_section_of_its_pproc_to_export_is_refused():
    """An explicitly requested old native export is never silently reassigned."""
    bare = _steady(PprocSpec()).model_copy(update={"outputs": ["P.txt", "P_vsec.vtk"]})
    with pytest.raises(CampaignConfigError, match=r"'P_vsec\.vtk'.*cuts no volume section"):
        _lines(bare)


def test_g05_a_raw_delete_before_an_explicit_native_volume_export_is_refused():
    """GEO-060 M1 / Q4 RAISE-04: the refusal workflows.py still makes keeps its test.

    A row that explicitly names the native volume file while a raw line deletes a
    section before the export is refused naming the raw delete, never exported
    from whatever section index happens to remain. The pproc's own plane is
    sampled through probes (G61), so no native section of the pproc survives.
    """
    declared = _steady(_pproc(**RECTANGLE)).model_copy(update={"outputs": ["P.txt", "P_vsec.vtk"]})
    deleted = declared.model_copy(
        update={"raw_commands": [RawCommand(command="DELETE_VOLUME_SECTION 1", before="export")]}
    )
    with pytest.raises(CampaignConfigError, match=r"'P_vsec\.vtk'.*raw line deleted the one"):
        _lines(deleted)
    # THE CONTROL: the same pproc without the explicit native file samples its plane.
    assert "EXPORT_PROBE_POINTS" in _lines(_steady(_pproc(**RECTANGLE)))


def test_g05_a_raw_delete_below_the_pproc_s_section_moves_its_index_down():
    """Deleting a native section cannot move the sampled survey's IDs."""
    case = _steady(_pproc(**RECTANGLE)).model_copy(
        update={
            "raw_commands": [
                RAW_CIRCLE,
                RawCommand(command="DELETE_VOLUME_SECTION 1", before="export"),
            ]
        }
    )
    script = Script("26.124")
    build_script(case, script)
    assert "DELETE_VOLUME_SECTION 1" in script.render()
    assert "EXPORT_PROBE_POINTS" in script.render()
    assert "EXPORT_VOLUME_SECTION" not in script.render()
    assert script.probe_field_layout[0]["probe_ids"] == [1, 2, 3, 4]


# --- the section is computed before it is exported ---------------------------
#
# The licensed run of 2026-09-24 (RPT-070) exported the two points of a steady
# one-job sweep that cut a section after START_SOLVER and exported it straight
# away: both files were byte-identical, and every cell value in them was 0.0.
# The manual computes the flow on a volume section with "Update all", after the
# solution has converged, which the script command UPDATE_ALL_VOLUME_SECTIONS is.


def _volume_lines(lines: list[str]) -> list[str]:
    """The solves, the volume-section commands and the volume exports, in order."""
    return [
        line
        for line in lines
        if line == "START_SOLVER"
        or ("VOLUME_SECTION" in line and not line.startswith("VOLUME_SECTION_"))
    ]


@pytest.mark.parametrize(
    ("table", "export"),
    [(RECTANGLE, "EXPORT_VOLUME_SECTION_VTK 1"), (CIRCLE, "EXPORT_VOLUME_SECTION_TECPLOT 1")],
    ids=["rectangle-vtk", "circle-tecplot"],
)
def test_g05_the_section_is_updated_after_the_solve_and_before_its_export(table, export):
    """The field uses the probe computation path after the solve."""
    lines = _lines(_steady(_pproc(**table)))
    assert lines.index("START_SOLVER") < lines.index("EXPORT_PROBE_POINTS")
    assert "UPDATE_ALL_VOLUME_SECTIONS" not in lines
    assert export not in lines
    assert any(line.startswith("NEW_PROBE_POINT") for line in lines)


def test_g05_every_point_of_a_one_job_sweep_updates_its_own_section():
    """Each point clears prior samples before exporting the current field."""
    pproc = _pproc(**RECTANGLE)
    points = [
        case_at_point(_steady(pproc, stem=f"P{a}", alpha=a), {"alpha": a}) for a in (0.0, 4.0, 8.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script)
    events = [
        line
        for line in script.render().splitlines()
        if line in ("START_SOLVER", "DELETE_PROBE_POINTS", "EXPORT_PROBE_POINTS")
    ]
    assert events == ["START_SOLVER", "DELETE_PROBE_POINTS", "EXPORT_PROBE_POINTS"] * 3


def test_g05_classify_never_hands_a_volume_file_to_a_surface_kind():
    """``_vsec`` is claimed before ``.vtk`` and ``.dat``, whatever order the names come in."""
    assert classify_outputs(["P_vsec.vtk", "P.txt", "P.vtk"]) == {
        "volume_section_vtk": "P_vsec.vtk",
        "loads": "P.txt",
        "vtk": "P.vtk",
    }
    assert classify_outputs(["P.dat", "P_vsec.dat", "P.txt"]) == {
        "tecplot": "P.dat",
        "volume_section_tecplot": "P_vsec.dat",
        "loads": "P.txt",
    }


def _recorded(tmp_path: Path, version: str) -> tuple[CampaignWorkspace, RunRecord]:
    """A converged point whose record, written by ``version``, names two ``_vsec`` files."""
    workspace = CampaignWorkspace(tmp_path / f"camp-{version}")
    record = RunRecord(
        run_id="camp/sim_7003/AL+000",
        sim_id="7003",
        point_name="AL+000",
        fs_version_requested="26.124",
        status=RunStatus.CONVERGED,
        outputs=["P_vsec.vtk", "P_vsec.dat"],
        package_version=version,
        script_sha256="",
        raw_flag=False,
    )
    sim = workspace.sim_dir("7003")
    sim.mkdir(parents=True, exist_ok=True)
    for name in record.outputs:
        (sim / name).write_text("native surface", encoding="utf-8")
    workspace.append_record(record)
    return workspace, record


def _surface_meaning(
    workspace: CampaignWorkspace, record: RunRecord
) -> tuple[dict[str, object], dict[str, object]]:
    """What the post makes of the record's files: products.json formats, PROV-JSON kinds."""
    write_campaign_products(workspace, overwrite=True)
    manifest = json.loads(
        (workspace.products_dir(None) / "products.json").read_text(encoding="utf-8")
    )
    formats = {
        Path(path).name: entry["format"]
        for path, entry in manifest["products"].items()
        if entry.get("format") in ("tecplot", "vtk", "csv")
    }
    document = _prov_document(record, workspace.sim_dir(record.sim_id))
    kinds = {
        node["pyfs:name"]: node.get("pyfs:kind")
        for node in document["entity"].values()
        if node.get("prov:type") == "pyfs:Output"
    }
    return formats, kinds


def test_g05_a_record_from_before_0_27_0_keeps_its_vsec_files_surface_exports(tmp_path):
    """A 0.26.0 record's ``P_vsec.vtk`` was a surface export when written, and stays one.

    The suffix names a volume section since 0.27.0; a record written before
    that release named a surface file, and upgrading the reader does not
    rewrite what the record says.
    """
    formats, kinds = _surface_meaning(*_recorded(tmp_path, "0.26.0"))
    assert formats == {"P_vsec.vtk": "vtk", "P_vsec.dat": "tecplot"}, (
        f"products.json holds {formats} for the surface exports of a 0.26.0 record: the "
        "reader's new suffix took them out of the native-surface entries"
    )
    assert kinds == {"P_vsec.vtk": "instant", "P_vsec.dat": "instant"}, (
        f"PROV-JSON gives the 0.26.0 surface exports the kinds {kinds}"
    )
    # THE CONTROL: the same files in a 0.27.0 record are volume sections.
    formats, kinds = _surface_meaning(*_recorded(tmp_path, "0.27.0.dev6"))
    assert formats == {} and kinds == {"P_vsec.vtk": None, "P_vsec.dat": None}, (formats, kinds)
    # AND THE CLASSIFIER BOTH READ THROUGH, by the record's version.
    names = ["P_vsec.vtk", "P_vsec.dat", "P.txt"]
    assert classify_outputs(names, package_version="0.26.0") == {
        "vtk": "P_vsec.vtk",
        "tecplot": "P_vsec.dat",
        "loads": "P.txt",
    }
    assert classify_outputs(names, package_version="0.27.0") == classify_outputs(names)


@pytest.mark.parametrize(
    ("make", "run_type"), [(unsteady_case, "unsteady"), (rotor_case, "unsteady_rotor")]
)
def test_g05_unsteady_volume_requires_an_existing_named_frame(make, run_type):
    """Missing MRP is refused; an explicit REFERENCE survey works in either workflow."""
    case = make().model_copy(update={"pproc": _pproc(**RECTANGLE), "pproc_id": "p005"})
    assert case.recipe == run_type and case.reference is None
    with pytest.raises(
        CampaignConfigError,
        match=r"'p005'.*frame 'MRP'.*volume section sampled through probes.*created no such frame",
    ):
        build_script(case, Script("26.124"))

    reference_case = case.model_copy(
        update={"pproc": _pproc(**{**RECTANGLE, "frame": "REFERENCE"})}
    )
    script = Script("26.124")
    build_script(reference_case, script)
    assert len(script.probe_points) == 4
    assert {point[1:4] for point in script.probe_points} == {
        (-1.0, 0.0, -1.0),
        (-1.0, 0.0, 1.0),
        (1.0, 0.0, -1.0),
        (1.0, 0.0, 1.0),
    }
    layout = script.probe_field_layout[0]
    assert layout["kind"] == "volume-section"
    assert layout["frame"] == "REFERENCE"
    assert layout["probe_ids"] == [1, 2, 3, 4]
    assert layout["export_kind"] == "unsteady-fluid-plot"
    text = script.render()
    for component in ("VX", "VY", "VZ"):
        assert f"NAME {component}4\n" in text
    assert "VOLUME_SECTION" not in text


def test_g05_the_volume_file_is_collected_and_hashed(tmp_path):
    """The stub writes every export, and the volume file reaches the point's folder."""
    workspace, matrix = _matrix(tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="0.0")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n\n'
        '[volume_section]\nshape = "rectangle"\nplane = "XZ"\ncorners_m = [-1.0, -1.0, 1.0, 1.0]\n',
        encoding="utf-8",
    )
    records = run_matrix(
        matrix,
        workspace,
        name="vsec",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert [record.status for record in records] == [RunStatus.CONVERGED], [
        record.error for record in records
    ]
    volume = [name for name in records[0].outputs if str(name).endswith("_probes.txt")]
    assert len(volume) == 1, records[0].outputs
    assert re.fullmatch(r"datapoints/DP-(?P<tag>[^/]+)/P3207-(?P=tag)_probes\.txt", volume[0])
    on_disk = workspace.sim_dir("3207") / volume[0]
    assert records[0].outputs_sha256[volume[0]] == file_sha256(on_disk)


# --- the section's metres reach the solver in the simulation's unit ----------


def test_g05_a_millimetre_simulation_takes_the_section_in_millimetres():
    """Physical plane coordinates and MRP origin reach native millimeters once."""
    import math

    rectangle = Script("26.124")
    build_script(
        _steady(_pproc(**{**RECTANGLE, "offset_m": 0.5})).model_copy(
            update={"raw_commands": [MILLIMETRES]}
        ),
        rectangle,
    )
    positions = [row[1:4] for row in rectangle.probe_points]
    assert set(positions) == {
        (-750.0, 500.0, -1000.0),
        (-750.0, 500.0, 1000.0),
        (1250.0, 500.0, -1000.0),
        (1250.0, 500.0, 1000.0),
    }
    assert rectangle.probe_field_layout[0]["native_to_m"] == 0.001
    circle = Script("26.124")
    build_script(
        _steady(_pproc(**CIRCLE)).model_copy(update={"raw_commands": [MILLIMETRES]}), circle
    )
    assert {row[1] for row in circle.probe_points} == {1750.0}
    radii = [math.hypot(row[2], row[3]) for row in circle.probe_points]
    assert min(radii) == pytest.approx(200.0)
    assert max(radii) == pytest.approx(1000.0)


def test_g05_a_saved_simulation_whose_unit_is_not_read_is_refused_naming_the_keys(tmp_path):
    """The section is refused on a save whose global block the package has not read in metres."""
    head = _saved_block("GLOBAL")
    other = _saved_copy(tmp_path / "wing_other.fsm", "GLOBAL", [head[0], "1", *head[2:]])
    case = _steady(_pproc(**CIRCLE)).model_copy(update={"geometry": str(other)})
    # G34 now rejects the earlier physical moment point before section emission.
    with pytest.raises(CampaignConfigError, match=r"moment_point_m.*in metres"):
        _lines(case)
    # THE CONTROL: the committed geometry, saved in metres, cuts the numbers as written.
    control = _lines(_steady(_pproc(**CIRCLE)).model_copy(update={"geometry": str(WING_PHY)}))
    assert sum(line.startswith("NEW_PROBE_POINT") for line in control) == 120
