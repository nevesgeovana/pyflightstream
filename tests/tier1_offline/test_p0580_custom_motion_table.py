"""Tier 1, 0.58.0 PFS-2254: a MOTIONS record drives a custom motion by a table file.

Written from the approved design page (design-motion-table.md, sections 3 and 6)
and the command database's SET_MOTION_CUSTOM_TABLE entry (FSM-26.127 p.246 for
the table's columns, p.345 for the command). The unsteady fixture runs 480 steps
of 0.00025 s, so the run ends at 0.12 s.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows._custom_motion import (
    custom_motion_record_refusal,
    read_motion_table,
    resolve_motion_tables,
)
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import unsteady_case

TABLE = "0.0, 0, 0, 0, 0, 0, 0\n0.06 0 0 0.01 0 2.5 0\n0.12,0,0,0,0,0,0\n"


def _flap(tmp_path: Path, text: str = TABLE, **variables):
    """An unsteady row moving the alias FLAP by the table, bound as the workspace binds it."""
    table = tmp_path / "flap.txt"
    table.write_bytes(text.encode("utf-8"))
    record = {
        "ALIAS": "FLAP",
        "TABLE": "flap.txt",
        "TABLE_TYPE": "POSITION-TIME",
        "TABLE_PATH": str(table),
        "TABLE_SHA256": hashlib.sha256(table.read_bytes()).hexdigest(),
    }
    case = unsteady_case(**{"CLOCK_MOTION": "FLAP", **variables})
    return case.model_copy(
        update={
            "custom_motions": [record],
            "inventory": ("Wing", "Flap"),
            "aliases": {"FLAP": ["Flap"]},
        }
    ), table


def _script(case) -> str:
    from pyflightstream.cases.workflows import workflow_registry

    script = Script("26.127")
    script.entities.declare_boundaries({"Wing": 1, "Flap": 2})
    workflow_registry()["unsteady"](case, script)
    return script, script.render()


def test_p0580_cm_a_table_motion_emits_its_three_commands_in_order(tmp_path):
    """Design test 1: CREATE_NEW_MOTION CUSTOM, the table with the id second and the copy on
    its own line, then the alias's boundaries, all before the solver is initialised."""
    case, _ = _flap(tmp_path)
    script, text = _script(case)
    lines = [line for line in text.splitlines() if line]
    start = lines.index("CREATE_NEW_MOTION CUSTOM")
    assert lines[start : start + 5] == [
        "CREATE_NEW_MOTION CUSTOM",
        "SET_MOTION_CUSTOM_TABLE POSITION-TIME 1",
        "flap.motion_table.txt",
        "SET_MOTION_BOUNDARIES 1 1",
        "2",
    ]
    assert start < lines.index("INITIALIZE_SOLVER")
    assert script.pending_input_files["flap.motion_table.txt"] == TABLE.encode("utf-8")


def test_p0580_cm_the_run_record_hashes_the_tables_exact_bytes(tmp_path):
    """Design test 4, first half: the parked copy is the file's bytes, hashed into the record."""
    from pyflightstream.run._pending import _write_pending_files

    case, table = _flap(tmp_path)
    script, _ = _script(case)
    out = tmp_path / "point"
    out.mkdir()
    digests = _write_pending_files(script, out, case=case, recorded={})
    assert digests["flap.motion_table.txt"] == hashlib.sha256(table.read_bytes()).hexdigest()
    assert (out / "flap.motion_table.txt").read_bytes() == table.read_bytes()


def test_p0580_cm_a_table_changed_after_the_plan_is_refused_at_build(tmp_path):
    """Design test 4, second half."""
    case, table = _flap(tmp_path)
    table.write_bytes(TABLE.replace("2.5", "3.0").encode("utf-8"))
    with pytest.raises(CampaignConfigError, match="changed after the row was planned"):
        _script(case)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("0 0 0 0 0 0 0\n0.12 0 0 0 0 0\n", "line 2 .* 7 numbers"),
        ("t,x,y,z,a,b,c\n0 0 0 0 0 0 0\n", "line 1 .* no header line"),
        ("0 0 0 0 0 0 0\n0.12 0 0 nan 0 0 0\n", "line 2 .* not finite"),
        ("0 0 0 0 0 0 0\n0.1 0 0 0 0 0 0\n0.05 0 0 0 0 0 0\n", "line 3: the time 0.05 s"),
    ],
)
def test_p0580_cm_a_table_not_in_its_form_is_refused_naming_the_line(tmp_path, text, match):
    """Design test 3: seven numbers a row, finite, the time strictly increasing."""
    with pytest.raises(CampaignConfigError, match=match):
        read_motion_table(text, source="the table")
    case, _ = _flap(tmp_path, text)
    with pytest.raises(CampaignConfigError, match=match):
        _script(case)


def test_p0580_cm_a_run_that_outlasts_its_table_is_refused_naming_both_times(tmp_path):
    """Design test 3: the table's last time is at or beyond the run's end."""
    case, _ = _flap(tmp_path, "0 0 0 0 0 0 0\n0.1 0 0 0 0 0 0\n")
    with pytest.raises(CampaignConfigError, match=r"ends at 0\.1 s and the run at 0\.12 s"):
        _script(case)


@pytest.mark.parametrize(
    ("dropped", "named"),
    [
        (("CLOCK_MOTION", "DELTA_TIME"), "no CLOCK_MOTION and no DELTA_TIME"),
        (("CLOCK_MOTION",), "and no CLOCK_MOTION\\."),
    ],
)
def test_p0580_cm_a_table_motion_row_names_its_clock_and_step(tmp_path, dropped, named):
    """Design test 5: without CLOCK_MOTION and DELTA_TIME the row is refused naming both."""
    case, _ = _flap(tmp_path, **dict.fromkeys(dropped))
    with pytest.raises(CampaignConfigError, match=named):
        _script(case)
    other, _ = _flap(tmp_path, CLOCK_MOTION="SLAT")
    with pytest.raises(
        CampaignConfigError, match="not a table motion of the row; name one of FLAP"
    ):
        _script(other)


@pytest.mark.parametrize(
    ("record", "match"),
    [
        ("{ALIAS: FLAP / TABLE: flap.txt}", "states no TABLE_TYPE"),
        ("{ALIAS: FLAP / TABLE: flap.txt / TABLE_TYPE: position}", "POSITION-TIME or VELOCITY"),
        ("{TABLE: flap.txt / TABLE_TYPE: VELOCITY-TIME}", "states no ALIAS"),
    ],
)
def test_p0580_cm_a_record_not_in_its_form_is_refused_naming_it(record, match):
    """Design test 2, the record's own form, refused when the matrix is read."""
    from pyflightstream.cases.matrix import _parse_motions

    with pytest.raises(MatrixError, match=match):
        _parse_motions({"MOTIONS": record}, "9001")


def test_p0580_cm_a_table_named_with_a_folder_part_is_refused():
    for name in ("sub" + chr(92) + "flap.txt", ".."):
        record = {"ALIAS": "FLAP", "TABLE": name, "TABLE_TYPE": "POSITION-TIME"}
        assert "not a bare file name" in str(custom_motion_record_refusal(record))


def test_p0580_cm_the_matrix_reads_a_table_record_apart_from_the_rotors():
    from pyflightstream.cases.matrix import _parse_motions

    records = _parse_motions(
        {"MOTIONS": "{ALIAS: FLAP / TABLE: flap.txt / TABLE_TYPE: VELOCITY-TIME}", "RPM": "900"},
        "9001",
    )
    assert records == [{"ALIAS": "FLAP", "TABLE": "flap.txt", "TABLE_TYPE": "VELOCITY-TIME"}]


@pytest.mark.parametrize("name", ["missing.txt", "empty.txt", "..", "outside.txt"])
def test_p0580_cm_a_table_missing_empty_or_outside_is_refused_at_bind(tmp_path, name):
    """Design test 2: the file of inputs/motions/ is bound when the row is planned."""
    motions = tmp_path / "inputs" / "motions"
    motions.mkdir(parents=True)
    (motions / "empty.txt").write_bytes(b"")
    (tmp_path / "inputs" / "outside.txt").write_bytes(TABLE.encode("utf-8"))
    table = name if name != "outside.txt" else "../outside.txt"
    record = {"ALIAS": "FLAP", "TABLE": table, "TABLE_TYPE": "POSITION-TIME"}
    with pytest.raises(InputArtifactError, match=r"POL 9001: MOTIONS record \{ALIAS: FLAP"):
        resolve_motion_tables(tmp_path / "inputs", [record], pol="9001", workflow="unsteady")


def test_p0580_cm_the_bind_records_the_tables_path_and_digest(tmp_path):
    motions = tmp_path / "inputs" / "motions"
    motions.mkdir(parents=True)
    (motions / "flap.txt").write_bytes(TABLE.encode("utf-8"))
    record = {"ALIAS": "FLAP", "TABLE": "flap.txt", "TABLE_TYPE": "POSITION-TIME"}
    (bound,) = resolve_motion_tables(tmp_path / "inputs", [record], pol="9001", workflow="unsteady")
    assert bound["TABLE_PATH"] == str((motions / "flap.txt").resolve())
    assert bound["TABLE_SHA256"] == hashlib.sha256(TABLE.encode("utf-8")).hexdigest()
    with pytest.raises(InputArtifactError, match="emitted on the unsteady run type"):
        resolve_motion_tables(tmp_path / "inputs", [record], pol="9001", workflow="unsteady_rotor")


def test_p0580_cm_a_matrix_row_binds_its_table_onto_the_case(tmp_path):
    """The route end to end: the cell's record reaches the case bound to inputs/motions/."""
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix

    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.144, REmi:4.38, ALPHA:sweep",
        values="0.0",
        workflow="unsteady",
        cell=(
            "MOTIONS: {ALIAS: FLAP / TABLE: flap.txt / TABLE_TYPE: VELOCITY-TIME} / "
            "CLOCK_MOTION: FLAP / DELTA_TIME: 0.01 / TIME_ITERATIONS: 8 / LAST_ITERS_AVG: 8"
        ),
    )
    motions = workspace.inputs_dir / "motions"
    motions.mkdir()
    (motions / "flap.txt").write_bytes(TABLE.encode("utf-8"))
    resolved = resolve_matrix(matrix, workspace, name="cm", fs_version="26.120", recipes=RECIPES)
    (case,) = resolved.campaign.sims
    assert case.motions == []
    (record,) = case.custom_motions
    assert record["TABLE_TYPE"] == "VELOCITY-TIME"
    assert record["TABLE_PATH"] == str((motions / "flap.txt").resolve())
    assert record["TABLE_SHA256"] == hashlib.sha256(TABLE.encode("utf-8")).hexdigest()
