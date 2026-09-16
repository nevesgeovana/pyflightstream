"""Tier 1: a point is named by its flight condition (0.21.0, GOAL-024 arm 2).

The name writes every variable the row's FLIGHT_CONDITION cell declares, in the
order the cell declares them, each as the code and the digits of the approved
table. ONE name does three jobs: it ends the ``run_id``, it names the datapoint
folder ``DP-<name>``, and it is the stem of every file of the point,
``P<POL>-<name>``.

The tests drive the matrix path from the cell to the planned script and the run
record, so what is asserted is what a campaign writes rather than what the
naming function returns in isolation. This module is the evidence of FR-102.

The test names carry ``goal024_point_name``
so the goal's checker can select them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import (
    POINT_NAME_FIELDS,
    CampaignConfigError,
    name_field,
)
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.workspace import (
    CampaignWorkspace,
    NamingTemplateError,
    PointName,
    RunStatus,
)
from pyflightstream.workspace.naming import (
    MATRIX_POINT_NAME,
    NamingTemplate,
    datapoint_dir_name,
    point_file_stem,
)
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
    make_library,
    stage_geometry,
)

#: Every key of the approved table, so a key dropped from it fails here and not
#: only where a matrix happens to declare it.
EVERY_KEY = (
    "MACH",
    "TASmps",
    "REmi",
    "ALTFT",
    "dISA",
    "RHOkgm3",
    "MUPas",
    "ASMPS",
    "TK",
    "PPA",
    "ALPHA",
    "BETA",
    "ADVANCE_RATIO",
    "RPM",
    "roll_rate",
    "pitch_rate",
    "yaw_rate",
)


def _matrix(
    tmp_path,
    *,
    condition,
    values,
    pol="3207",
    workflow="steady",
    stem="wing_clean.fsm",
    cell="",
):
    """A workspace and a one-row matrix whose FLIGHT_CONDITION cell is ``condition``."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, stem)
    # The matrix path names its files as the command line does,
    # ``P<POL>-<name>`` (MATRIX_POINT_NAME); the library's own default is the
    # bare name, and the last test of this file measures that difference.
    workspace = CampaignWorkspace(
        workspace.root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )
    header = " | ".join(matrix_mod._COLUMNS)
    row = " | ".join(
        {
            "POL": pol,
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Wing",
            "DESCRIPTION": "NAMED_BY_ITS_FLIGHT_CONDITION",
            "FLIGHT_CONDITION": condition,
            "SWEEP_VALUES": values,
            "GEOMETRY": stem,
            "REF": "r003",
            "SET": "s002",
            "PPROC": "p001",
            "SYMMETRY": "NONE",
            "FS_BUILD": "26.120",
            "WORKFLOW": workflow,
            "VAR_NAMES_VALUES": cell,
        }.get(name, "-")
        for name in matrix_mod._COLUMNS
    )
    path = tmp_path / "named.fs"
    path.write_text(header + "\n" + "-" * 40 + "\n" + row + "\n", encoding="utf-8")
    return workspace, path


def _plan(workspace, matrix):
    return plan_matrix(
        matrix,
        workspace,
        name="named",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


def test_goal024_point_name_every_declared_variable_is_written_in_the_cell_s_order(tmp_path):
    """The cell declares five variables and the name carries all five, in that order.

    THE ORDER IS THE CELL'S and not a canonical one: the same five keys
    written in another order give another name, which is asserted by the
    second half of this test rather than described.
    """
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:0.0, BETA:0.0, ADVANCE_RATIO:sweep",
        values="0.8",
    )
    plan = _plan(workspace, matrix)
    names = [point.run_id.rsplit("/", 1)[-1] for point in plan.points]
    assert names == ["M144RE438AL+000BE+000J+080"], plan.summary()

    workspace, matrix = _matrix(
        tmp_path / "other",
        condition="ALPHA:0.0, MACH:0.144, BETA:0.0, REmi:4.38, ADVANCE_RATIO:sweep",
        values="0.8",
    )
    reordered = [point.run_id.rsplit("/", 1)[-1] for point in _plan(workspace, matrix).points]
    assert reordered == ["AL+000M144BE+000RE438J+080"], "the cell's order is the name's order"


def test_goal024_point_name_the_run_id_the_folder_and_the_file_stem_are_the_one_name(tmp_path):
    """One name, three jobs: the identity, the folder and the stem of every file."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="-2.0,0.0",
    )
    records = run_matrix(
        matrix,
        workspace,
        name="named",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    (record,) = records
    assert record.status is RunStatus.CONVERGED, record.error
    ran = [entry["tag"] for entry in record.points_ran]
    assert ran == ["M200RE230AL-020", "M200RE230AL+000"]

    # The folder of the first point, and the stem of the files inside it.
    name = PointName(ran[0])
    assert datapoint_dir_name(name) == "DP-M200RE230AL-020"
    assert point_file_stem("3207", name) == "P3207-M200RE230AL-020"
    datapoints = workspace.sim_dir("3207") / "datapoints"
    assert sorted(p.name for p in datapoints.iterdir()) == [
        "DP-M200RE230AL+000",
        "DP-M200RE230AL-020",
    ]
    collected = sorted(p.name for p in (datapoints / "DP-M200RE230AL-020").iterdir())
    assert collected, "the point's folder holds the files it collected"
    assert all(p.startswith("P3207-M200RE230AL-020") for p in collected), collected

    # A steady row is ONE job for its points, so its id ends in the `sweep`
    # token of 0.17.0 rather than in a point's name, and the NAME of that
    # sweep is recorded beside it: each field written but the swept one,
    # which is `AL+sweep`. The points it ran carry the point names, above,
    # and the job's own script is named by the sweep name.
    assert record.run_id == "named/sim_3207/sweep"
    assert record.sweep_name == "M200RE230AL+sweep"
    assert record.point_name == "M200RE230AL+sweep"
    assert Path(record.script_path).name == "P3207-M200RE230AL+sweep.txt", record.script_path


def test_goal024_point_name_two_points_that_differ_in_a_declared_variable_get_two_names(tmp_path):
    """J 0.80 and J 0.84 are two points, and the 0.20 tag gave them one folder.

    The tag wrote one decimal per axis, so `a+00.0_b+00.0_j+00.8` named
    both and the second run collected into the first one's folder. The
    name writes J x 100, so the two are told apart.
    """
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, ALPHA:0.0, ADVANCE_RATIO:sweep",
        values="0.80,0.84",
        workflow="unsteady",
    )
    names = [point.run_id.rsplit("/", 1)[-1] for point in _plan(workspace, matrix).points]
    assert names == ["M144AL+000J+080", "M144AL+000J+084"], names
    assert len(set(names)) == 2, "two points, two names"
    assert len({datapoint_dir_name(PointName(name)) for name in names}) == 2


def test_goal024_point_name_the_collision_guard_reads_every_axis_it_names(tmp_path):
    """The guard is on the NAME, so it fires on any axis whose field two values share.

    It was measured on three axes of seventeen (the qa lens, 2026-09-16): a
    Mach sweep over 0.1441 and 0.1444 writes `M144` twice, and so does any
    other variable whose digits round together.
    """
    # Pydantic wraps the refusal of a field validator, so the message is read
    # off the ValidationError rather than off a CampaignConfigError.
    from pydantic import ValidationError

    from pyflightstream.cases import SweepAxis

    for axis, values, field in (
        ("MACH", [0.1441, 0.1444], "M144"),
        ("REmi", [4.381, 4.384], "RE438"),
        # 800.4 and 800.6 round APART, which is the guard working; 800.2 and
        # 800.4 round together, which is what it refuses.
        ("RPM", [800.2, 800.4], None),
        ("pitch_rate", [2.01, 2.04], "Q+020"),
    ):
        if field is None:
            # RPM is written to the rev/min, so those two are one name too.
            field = "RPM+0800"
        with pytest.raises(ValidationError) as caught:
            SweepAxis(type=axis, values=values)
        assert "both write" in str(caught.value), (axis, str(caught.value))
        assert field in str(caught.value), (axis, field, str(caught.value))


def test_goal024_point_name_two_points_that_write_one_name_are_refused_by_name(tmp_path):
    """Two values that round to one field cannot share a folder, so the plan refuses.

    J 0.8007 and 0.8049 both write `J+080`. The refusal is at plan time,
    before a script is written, and it names both the points and what
    they write, because a reader's next move is to change one of them.
    """
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, ALPHA:0.0, ADVANCE_RATIO:sweep",
        values="0.8007,0.8049",
        workflow="unsteady",
    )
    with pytest.raises(Exception) as caught:
        _plan(workspace, matrix)
    message = str(caught.value)
    assert "both write" in message, message
    assert "J+080" in message, message


def test_goal024_point_name_every_key_of_the_table_writes_its_code_and_its_digits():
    """The seventeen keys, each measured against the value the approved table fixes.

    A code or a width changed in the table changes a name that is already
    in a folder somewhere, so the table is asserted key by key rather than
    through whichever keys a matrix fixture happens to declare.
    """
    assert set(POINT_NAME_FIELDS) == set(EVERY_KEY), sorted(POINT_NAME_FIELDS)
    assert [name_field(key, value) for key, value in EXPECTED] == [
        written for _, _, written in CASES
    ]


#: One measurement per key: the value, and what the approved table writes for it.
CASES = (
    ("MACH", 0.144, "M144"),
    ("TASmps", 34.0, "V0340"),
    ("REmi", 4.38, "RE438"),
    ("ALTFT", 5000.0, "ALT05000"),
    ("dISA", 10.0, "DT+100"),
    ("RHOkgm3", 1.225, "RHO12250"),
    ("MUPas", 1.8e-5, "MU18000"),
    ("ASMPS", 340.0, "A3400"),
    ("TK", 290.0, "T2900"),
    ("PPA", 100000.0, "PS100000"),
    ("ALPHA", -2.0, "AL-020"),
    ("BETA", 4.0, "BE+040"),
    ("ADVANCE_RATIO", 0.8, "J+080"),
    ("RPM", -1860.0, "RPM-1860"),
    ("roll_rate", 2.5, "P+025"),
    ("pitch_rate", -2.5, "Q-025"),
    ("yaw_rate", 0.0, "R+000"),
)
EXPECTED = tuple((key, value) for key, value, _ in CASES)


def test_goal024_point_name_a_negative_value_of_an_unsigned_field_is_refused_by_name():
    """A Mach number below zero has no name under the table, and silence would give it one."""
    with pytest.raises(CampaignConfigError, match="MACH"):
        name_field("MACH", -0.1)


def test_goal024_point_name_the_folder_namer_takes_a_checked_name_and_nothing_else():
    """The mapping the 0.20 namer took is the collapsing step, so it is not taken."""
    with pytest.raises(NamingTemplateError, match="takes a PointName"):
        datapoint_dir_name({"alpha": 0.0})  # type: ignore[arg-type]
    with pytest.raises(NamingTemplateError, match="takes a PointName"):
        datapoint_dir_name("M144AL+000")  # type: ignore[arg-type]
    with pytest.raises(NamingTemplateError, match="folder prefix"):
        PointName("DP-M144AL+000")


def test_goal024_point_name_a_point_run_id_ends_in_the_name_on_a_per_point_row(tmp_path):
    """An unsteady row is one job PER POINT, so each record's id ends in that point's name."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, ALPHA:0.0, ADVANCE_RATIO:sweep",
        values="0.80,0.84",
        workflow="unsteady",
    )
    ids = [point.run_id for point in _plan(workspace, matrix).points]
    assert ids == [
        "named/sim_3207/M144AL+000J+080",
        "named/sim_3207/M144AL+000J+084",
    ], ids


def test_goal024_point_name_the_library_default_writes_the_bare_name_and_the_matrix_the_stem():
    """Two templates, one name: `{point}` is the name and `{polar}` is `P<POL>-<name>`.

    The command line and the matrix path name files `P<POL>-<name>`
    (MATRIX_POINT_NAME); a campaign built in Python keeps the library
    default, which is the name alone. Both are the SAME name, which is
    what this asserts: the prefix is the only difference between them.
    """
    name = PointName("M200RE230AL-020")
    assert NamingTemplate().point_name == "{point}"
    assert MATRIX_POINT_NAME == "{polar}"
    assert point_file_stem("3207", name) == f"P3207-{name}"


def test_goal024_point_name_the_code_table_reads_the_same_in_all_three_homes():
    """The table lives in the code, in the workspace page and in FR-102: one table.

    The migration page tells a user to read the DOCUMENTED table before renaming,
    "because the names it gives are the ones your folders will carry", which
    makes a drifted table a wrong instruction on a destructive operation. The
    three agree today and nothing generated another, so this compares them (the
    technical-writing lens, 2026-09-16).
    """
    import re

    docs = (Path(__file__).resolve().parents[2] / "docs" / "workspace-and-workflows.md").read_text(
        encoding="utf-8"
    )
    table = docs.split("### How a point is named", 1)[1].split("###", 1)[0]
    documented = {}
    for line in table.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].startswith("`"):
            continue
        names = re.findall(r"`([^`]+)`", cells[0])
        codes = re.findall(r"`([^`]+)`", cells[1])
        if len(names) != len(codes):
            continue
        documented.update(dict(zip(names, codes, strict=True)))
    assert documented, table[:400]
    from pyflightstream.cases import POINT_NAME_FIELDS

    assert set(documented) == set(POINT_NAME_FIELDS), sorted(
        set(documented) ^ set(POINT_NAME_FIELDS)
    )
    for key, code in documented.items():
        assert POINT_NAME_FIELDS[key].code == code, (key, code, POINT_NAME_FIELDS[key].code)
