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
* the file is never handed to a surface kind (``_vsec`` is claimed first);
* an unsteady or rotor row naming the table is refused before any emission;
* the file is collected into the point's folder and hashed in the record;
* the table's metres reach the solver in the simulation's length unit.

Nothing here runs a solver. What the delete-then-create sequence does on a
seat is not measured: DELETE_VOLUME_SECTION is verified alone.
"""

from __future__ import annotations

import re

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
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
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

RECTANGLE = {"shape": "rectangle", "plane": "XZ", "corners_m": [-1, -1, 1, 1]}
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
    """The table is accepted, and the point declares the file its format names."""
    vtk = _pproc(**RECTANGLE)
    assert "{name}_vsec.vtk" in vtk.outputs(unsteady=False)
    assert "{name}_vsec.dat" not in vtk.outputs(unsteady=False)
    tecplot = _pproc(**{**RECTANGLE, "format": "tecplot"})
    assert "{name}_vsec.dat" in tecplot.outputs(unsteady=False)
    assert "{name}_vsec.vtk" not in tecplot.outputs(unsteady=False)
    for pproc in (vtk, tecplot):
        assert not [name for name in pproc.outputs(unsteady=True) if "_vsec" in name], (
            "an unsteady row declares a volume file, and nothing on that run type makes one"
        )
    # THE CONTROL: without the table nothing is declared, which is every pproc
    # written before 0.27.0 and what keeps every existing golden where it was.
    assert not [name for name in PprocSpec().outputs(unsteady=False) if "_vsec" in name]


@pytest.mark.parametrize(
    ("table", "words"),
    [
        ({**RECTANGLE, "radii_m": [0.1, 0.5]}, "shape = 'rectangle' states radii_m"),
        ({**RECTANGLE, "points": [4, 4]}, "shape = 'rectangle' states points"),
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
    """Rectangle and circle, on the build the commands were last verified on."""
    lines = _lines(_steady(_pproc(**RECTANGLE)))
    solve = lines.index("START_SOLVER")
    create = lines.index(
        "CREATE_NEW_RECTANGLE_VOLUME_SECTION 2 XZ 0.0 1 -1.0 -1.0 1.0 1.0 NONE 0.1 1 1.2"
    )
    export = lines.index("EXPORT_VOLUME_SECTION_VTK 1")
    assert solve < create < export, (
        f"START_SOLVER at {solve}, the section created at {create} and exported at {export}; "
        "a section cut before the solve cuts a field that does not exist"
    )
    assert lines[export + 1] == "P_vsec.vtk", lines[export : export + 2]
    assert not [line for line in lines if line.startswith("DELETE_VOLUME_SECTION")], (
        "a single point deleted a section nothing had created"
    )

    circle = _lines(_steady(_pproc(**CIRCLE)))
    assert "CREATE_NEW_CIRCLE_VOLUME_SECTION 2 YZ 1.5 10 12 0.2 1.0 NONE 0.1 1 1.2" in circle
    at = circle.index("EXPORT_VOLUME_SECTION_TECPLOT 1")
    assert circle[at + 1] == "P_vsec.dat"
    assert circle.index("START_SOLVER") < at


def test_g05_a_frame_the_run_did_not_create_is_refused():
    """The pproc names the frame; a row whose run made no such frame is told which it made."""
    with pytest.raises(CampaignConfigError, match=r"'HUB' for the volume section.*created: MRP"):
        _lines(_steady(_pproc(**{**RECTANGLE, "frame": "HUB"})))


def test_g05_each_point_of_a_warm_sweep_exports_its_own_section():
    """One create per point, the previous one deleted first, every export citing 1."""
    pproc = _pproc(**RECTANGLE)
    points = [
        case_at_point(_steady(pproc, stem=f"P-A{int(alpha):+d}", alpha=alpha), {"alpha": alpha})
        for alpha in (-2.0, 0.0, 2.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script)
    lines = script.render().splitlines()
    solves = [index for index, line in enumerate(lines) if line == "START_SOLVER"]
    creates = [
        index
        for index, line in enumerate(lines)
        if line.startswith("CREATE_NEW_RECTANGLE_VOLUME_SECTION ")
    ]
    deletes = [index for index, line in enumerate(lines) if line == "DELETE_VOLUME_SECTION 1"]
    exports = [
        index for index, line in enumerate(lines) if line.startswith("EXPORT_VOLUME_SECTION")
    ]
    assert len(solves) == len(creates) == len(exports) == 3, (solves, creates, exports)
    assert len(deletes) == 2, f"two later points and {len(deletes)} deletes"
    for point, (solve, create, export) in enumerate(zip(solves, creates, exports, strict=True)):
        assert solve < create < export
        assert lines[export] == "EXPORT_VOLUME_SECTION_VTK 1"
        assert lines[export + 1] == classify_outputs(points[point].outputs)["volume_section_vtk"]
        if point:
            assert solve < deletes[point - 1] < create, (
                f"point {point + 1} created its section before deleting the previous one, "
                "so its export at index 1 would write the previous point's plane"
            )


def test_g05_the_export_cites_the_pproc_s_own_section_after_a_raw_one():
    """A raw circle cut first takes index 1, so the pproc's rectangle is 2, and 2 is exported."""
    case = _steady(_pproc(**RECTANGLE)).model_copy(update={"raw_commands": [RAW_CIRCLE]})
    lines = _lines(case)
    raw = lines.index(RAW_CIRCLE.command)
    own = next(i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_RECTANGLE"))
    export = next(i for i, line in enumerate(lines) if line.startswith("EXPORT_VOLUME_SECTION"))
    assert raw < own < export, "the fixture does not cut the raw circle before the pproc's plane"
    assert (lines[export], lines[export + 1]) == ("EXPORT_VOLUME_SECTION_VTK 2", "P_vsec.vtk"), (
        f"the pproc's rectangle is the second section the script cut, and the file its pproc "
        f"declares, P_vsec.vtk, is exported by {lines[export]!r}: the raw circle's plane under "
        "the rectangle's name"
    )


def test_g05_a_sweep_deletes_and_exports_the_pproc_s_own_section_beside_raw_ones():
    """Per point the raw circle is cut again; the pproc deletes and exports its own by index.

    Point 1: circle 1, rectangle 2, export 2. Point 2: circle 3, then the
    rectangle of point 1 (2) is deleted, which moves circle 3 to 2, and point
    2's rectangle is cut as 3 and exported as 3.
    """
    pproc = _pproc(**RECTANGLE)
    points = [
        case_at_point(
            _steady(pproc, stem=f"P-A{int(alpha):+d}", alpha=alpha).model_copy(
                update={"raw_commands": [RAW_CIRCLE]}
            ),
            {"alpha": alpha},
        )
        for alpha in (0.0, 2.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script)
    lines = script.render().splitlines()
    volume = [
        line
        for line in lines
        if line.startswith(("CREATE_NEW_", "DELETE_VOLUME", "EXPORT_VOLUME"))
        and "ACTUATOR" not in line
        and "COORDINATE" not in line
    ]
    assert volume == [
        RAW_CIRCLE.command,
        next(line for line in volume if line.startswith("CREATE_NEW_RECTANGLE")),
        "EXPORT_VOLUME_SECTION_VTK 2",
        RAW_CIRCLE.command,
        "DELETE_VOLUME_SECTION 2",
        next(line for line in volume if line.startswith("CREATE_NEW_RECTANGLE")),
        "EXPORT_VOLUME_SECTION_VTK 3",
    ], volume


def test_g05_a_volume_file_with_no_section_of_its_pproc_to_export_is_refused():
    """No table, or a raw line deleting the pproc's section before its export: refused, named."""
    declared = _steady(_pproc(**RECTANGLE))
    bare = declared.model_copy(update={"pproc": PprocSpec(), "pproc_id": "p001"})
    with pytest.raises(CampaignConfigError, match=r"'P_vsec\.vtk'.*cuts no volume section"):
        _lines(bare)
    deleted = declared.model_copy(
        update={"raw_commands": [RawCommand(command="DELETE_VOLUME_SECTION 1", before="export")]}
    )
    with pytest.raises(CampaignConfigError, match=r"'P_vsec\.vtk'.*raw line deleted the one"):
        _lines(deleted)
    # THE CONTROL: the same row without the raw delete exports its own section.
    assert "EXPORT_VOLUME_SECTION_VTK 1" in _lines(declared)


def test_g05_a_raw_delete_below_the_pproc_s_section_moves_its_index_down():
    """Raw circle 1, the pproc's rectangle 2, a raw delete of 1: the rectangle is now 1."""
    delete_first = RawCommand(command="DELETE_VOLUME_SECTION 1", before="export")
    case = _steady(_pproc(**RECTANGLE)).model_copy(
        update={"raw_commands": [RAW_CIRCLE, delete_first]}
    )
    lines = _lines(case)
    export = next(i for i, line in enumerate(lines) if line.startswith("EXPORT_VOLUME_SECTION"))
    assert lines.index("DELETE_VOLUME_SECTION 1") < export, "the fixture deletes after the export"
    assert lines[export] == "EXPORT_VOLUME_SECTION_VTK 1", (
        f"the raw circle below the pproc's rectangle was deleted, so the rectangle is the first "
        f"section left, and its file is exported by {lines[export]!r}"
    )
    # A SECTION ABOVE IT moves nothing: a raw circle cut after the rectangle (2) and
    # deleted leaves the rectangle 1.
    above = [
        RawCommand(command=RAW_CIRCLE.command, before="export"),
        RawCommand(command="DELETE_VOLUME_SECTION 2", before="export"),
    ]
    lines = _lines(_steady(_pproc(**RECTANGLE)).model_copy(update={"raw_commands": above}))
    export = next(i for i, line in enumerate(lines) if line.startswith("EXPORT_VOLUME_SECTION"))
    assert lines[export] == "EXPORT_VOLUME_SECTION_VTK 1", lines[export]


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


@pytest.mark.parametrize(
    ("make", "run_type"), [(unsteady_case, "unsteady"), (rotor_case, "unsteady_rotor")]
)
def test_g05_an_unsteady_row_naming_a_volume_section_is_refused(make, run_type):
    """The step exports fire during the march, before a section cut after it exists."""
    case = make().model_copy(update={"pproc": _pproc(**RECTANGLE), "pproc_id": "p005"})
    with pytest.raises(CampaignConfigError, match=rf"\[volume_section\].*'{run_type}'"):
        build_script(case, Script("26.124"))


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
    volume = [name for name in records[0].outputs if str(name).endswith("_vsec.vtk")]
    assert len(volume) == 1, records[0].outputs
    assert re.fullmatch(r"datapoints/DP-(?P<tag>[^/]+)/P3207-(?P=tag)_vsec\.vtk", volume[0])
    on_disk = workspace.sim_dir("3207") / volume[0]
    assert records[0].outputs_sha256[volume[0]] == file_sha256(on_disk)


# --- the section's metres reach the solver in the simulation's unit ----------


def test_g05_a_millimetre_simulation_takes_the_section_in_millimetres():
    """Both create commands read their lengths in the simulation's unit: every one times 1000."""
    rectangle = _lines(
        _steady(_pproc(**{**RECTANGLE, "offset_m": 0.5})).model_copy(
            update={"raw_commands": [MILLIMETRES]}
        )
    )
    assert "SET_SIMULATION_LENGTH_UNITS MILLIMETER" in rectangle, "the fixture sets no unit"
    created = next(line for line in rectangle if line.startswith("CREATE_NEW_RECTANGLE"))
    assert created == (
        "CREATE_NEW_RECTANGLE_VOLUME_SECTION 2 XZ 500.0 1 -1000.0 -1000.0 1000.0 1000.0 "
        "NONE 0.1 1 1.2"
    ), f"a 2 m square 0.5 m off its plane was cut as {created!r} in a simulation in millimetres"
    circle = _lines(_steady(_pproc(**CIRCLE)).model_copy(update={"raw_commands": [MILLIMETRES]}))
    cut = next(line for line in circle if line.startswith("CREATE_NEW_CIRCLE"))
    assert (
        cut == "CREATE_NEW_CIRCLE_VOLUME_SECTION 2 YZ 1500.0 10 12 200.0 1000.0 NONE 0.1 1 1.2"
    ), f"an annulus of 0.2 m to 1 m, 1.5 m off its plane, was cut as {cut!r} in millimetres"


def test_g05_a_saved_simulation_whose_unit_is_not_read_is_refused_naming_the_keys(tmp_path):
    """The section is refused on a save whose global block the package has not read in metres."""
    head = _saved_block("GLOBAL")
    other = _saved_copy(tmp_path / "wing_other.fsm", "GLOBAL", [head[0], "1", *head[2:]])
    case = _steady(_pproc(**CIRCLE)).model_copy(update={"geometry": str(other)})
    with pytest.raises(CampaignConfigError, match=r"offset_m and radii_m.*in metres"):
        _lines(case)
    # THE CONTROL: the committed geometry, saved in metres, cuts the numbers as written.
    control = _lines(_steady(_pproc(**CIRCLE)).model_copy(update={"geometry": str(WING_PHY)}))
    assert "CREATE_NEW_CIRCLE_VOLUME_SECTION 2 YZ 1.5 10 12 0.2 1.0 NONE 0.1 1 1.2" in control
