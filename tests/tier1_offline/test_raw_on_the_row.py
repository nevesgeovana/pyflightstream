"""Tier 1: a row states raw solver commands, in the cell or in a file (FR-67).

Her decision of 2026-09-10, PFS-2035.10, "a linha ganha um jeito de passar
comando bruto, mantendo a feature original preservada". It EXTENDS the
preset-level `[[raw]]` table of FR-31 to the row and replaces nothing.

THE SPECIFICATION IS THREE ROWS SHE WROTE, 9208, 9209 and 9210 of
`pfs0150/matriz_work.fs`, hidden and not run, each spelling out one shape:
the line in the cell, the line in a file, and both together over a preset
that states one of its own. Row 9210 is the one that fixes the ORDER at a
shared seam, and its answer is the preset's line, then the row's file, then
the row's cell line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import RawCommand
from pyflightstream.cases.matrix import MatrixError, read_matrix

HEADER = (
    "POL  | AIRCRAFT | DESCRIPTION | FLIGHT_CONDITION | SWEEP_VALUES | REF  | SET  | "
    "PPROC | FS_BUILD | HIDDEN | RUN | WORKFLOW | VAR_NAMES_VALUES\n" + "-" * 200 + "\n"
)


def matrix_with(tmp_path: Path, cell: str, pol: str = "9001") -> Path:
    """One active row whose VAR_NAMES_VALUES cell is ``cell``."""
    row = (
        f"{pol} | WORK | RAW_case | MACH:0.14, REmi:5.6, ALPHA:sweep, BETA:0 | 0,2 | "
        f"r011 | s010 | p011 | 26.123 | 0 | 1 | unsteady_rotor | {cell}"
    )
    path = tmp_path / "m.fs"
    path.write_text(HEADER + row + "\n", encoding="utf-8")
    return path


def only_row(tmp_path: Path, cell: str):
    return read_matrix(matrix_with(tmp_path, cell))[0]


BASE = "GEOMETRY: 90_WORK.fsm / SYMMETRY: NONE / DELTA_TIME: 0.0001 / TIME_ITERATIONS: 720"


def test_a_cell_states_a_raw_command_and_the_phase_it_goes_before(tmp_path):
    """Her row 9208's first shape, read off the cell."""
    row = only_row(
        tmp_path,
        f"{BASE} / RAW: {{COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}}",
    )
    assert row.raw == [{"COMMAND": "SOLVER_SET_ITERATIONS 350", "BEFORE": "init"}]


def test_a_cell_states_several_raw_commands_in_cell_order(tmp_path):
    """Her row 9208 whole: two records, and control is a phase like any other."""
    row = only_row(
        tmp_path,
        f"{BASE} / RAW: {{COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}}, "
        "{COMMAND: PRINT starting_the_pusher_case / BEFORE: control}",
    )
    assert [record["BEFORE"] for record in row.raw] == ["init", "control"]
    assert row.raw[1]["COMMAND"] == "PRINT starting_the_pusher_case"


def test_a_file_path_survives_the_record_separator(tmp_path):
    """HER OWN ROW 9209 DID NOT PARSE, and the reason is the grammar.

    A record's pairs are separated by a slash and a path carries slashes,
    so `FILE: raw/pusher_extra.txt / BEFORE: init` was cut at the path's
    own separator and refused as not a KEY: value pair. A raw record
    splits on a SPACED separator, because its two values are a path and a
    command line and both carry punctuation of their own.
    """
    row = only_row(tmp_path, f"{BASE} / RAW: {{FILE: raw/pusher_extra.txt / BEFORE: init}}")
    assert row.raw == [{"FILE": "raw/pusher_extra.txt", "BEFORE": "init"}]


def test_a_record_stating_both_forms_is_refused(tmp_path):
    """The line and the file are the same statement made twice, with no order between."""
    with pytest.raises(MatrixError) as refused:
        only_row(
            tmp_path,
            f"{BASE} / RAW: {{COMMAND: PRINT x / FILE: raw/x.txt / BEFORE: init}}",
        )
    said = str(refused.value)
    assert "COMMAND" in said and "FILE" in said, said
    assert "ONE of the two" in said


def test_a_record_stating_neither_form_is_refused(tmp_path):
    with pytest.raises(MatrixError) as refused:
        only_row(tmp_path, f"{BASE} / RAW: {{BEFORE: init}}")
    assert "neither" in str(refused.value)


def test_a_record_stating_no_phase_is_refused_naming_the_phases(tmp_path):
    with pytest.raises(MatrixError) as refused:
        only_row(tmp_path, f"{BASE} / RAW: {{COMMAND: PRINT x}}")
    said = str(refused.value)
    assert "BEFORE" in said and "init" in said, said


def test_a_record_stating_a_key_a_raw_command_does_not_read_is_refused(tmp_path):
    with pytest.raises(MatrixError) as refused:
        only_row(tmp_path, f"{BASE} / RAW: {{COMMAND: PRINT x / BEFORE: init / AFTER: exec}}")
    assert "AFTER" in str(refused.value)


def test_a_row_stating_no_raw_carries_none(tmp_path):
    """Every row written before this release, and every row that wants none."""
    assert only_row(tmp_path, BASE).raw == []


def test_a_line_knows_where_it_came_from(tmp_path):
    """The model carries the source, which is what a refusal names (FR-67)."""
    assert RawCommand(command="PRINT x", before="init", source="matrix").source == "matrix"
    assert (
        RawCommand(command="PRINT x", before="init", source="raw/a.txt:14").source == "raw/a.txt:14"
    )
    # A line stating no source is what a preset's `[[raw]]` table builds,
    # and it is read exactly as it was at 0.14.0.
    assert RawCommand(command="PRINT x", before="init").source is None


# --- the workspace half: a FILE becomes one command per line -----------------


RAW_ROW = (
    "9301 | TestWing | RAW_ROW | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 |          | 0 | 1 | OUTPUTS: loads_{point}.txt / RAW: "
    "{FILE: raw/extra.txt / BEFORE: init}, {COMMAND: PRINT after_the_file / BEFORE: init}"
)


def resolved_row(tmp_path, file_text=None, row=RAW_ROW):
    """Resolve one row against a synthetic library, writing a raw file if asked."""
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

    workspace = make_library(tmp_path)
    if file_text is not None:
        raw_dir = workspace.inputs_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / "extra.txt").write_text(file_text, encoding="utf-8")
    path = write_matrix(tmp_path / "raw.fs", [row])
    resolved = resolve_matrix(
        path,
        workspace,
        name="raw",
        fs_version="26.120",
        recipes=RECIPES,
        fs_exe="C:/fs/FlightStream.exe",
    )
    return next(sim for sim in resolved.campaign.sims if sim.sim_id == "9301")


FILE_TEXT = """# extra.txt, which explains itself.
#
# A blank line and a line opening with # are skipped.

SOLVER_SET_ITERATIONS 400
SET_SIGNIFICANT_DIGITS 7
"""


def test_a_raw_file_becomes_one_command_per_line_in_order(tmp_path):
    """Her row 9209's shape: the file's lines, verbatim, in order."""
    case = resolved_row(tmp_path, FILE_TEXT)
    from_file = [entry for entry in case.raw_commands if entry.source != "matrix"]
    assert [entry.command for entry in from_file] == [
        "SOLVER_SET_ITERATIONS 400",
        "SET_SIGNIFICANT_DIGITS 7",
    ], from_file


def test_a_blank_line_and_a_comment_are_skipped_so_a_file_may_explain_itself(tmp_path):
    """Four of the six lines of the fixture are prose, and none is emitted."""
    case = resolved_row(tmp_path, FILE_TEXT)
    assert not any("#" in entry.command for entry in case.raw_commands)
    assert not any(not entry.command.strip() for entry in case.raw_commands)


def test_each_line_carries_the_file_and_its_line_number(tmp_path):
    """THE POINT OF THE SOURCE FIELD: the cell holds a path and the mistake is
    thirty lines away, so a refusal must name the FILE and the LINE."""
    case = resolved_row(tmp_path, FILE_TEXT)
    sources = [entry.source for entry in case.raw_commands if entry.source != "matrix"]
    assert sources == ["raw/extra.txt:5", "raw/extra.txt:6"], sources


def test_the_rows_cell_line_comes_after_the_rows_file(tmp_path):
    """Her row 9210 fixes the order, and this is the half of it inside the row."""
    case = resolved_row(tmp_path, FILE_TEXT)
    assert [entry.source for entry in case.raw_commands][-1] == "matrix"
    assert case.raw_commands[-1].command == "PRINT after_the_file"


def test_a_file_the_workspace_does_not_carry_is_refused_naming_it(tmp_path):
    with pytest.raises(MatrixError) as refused:
        resolved_row(tmp_path, None)
    said = str(refused.value)
    assert "raw/extra.txt" in said and "not a file" in said, said


def test_a_file_outside_the_inputs_is_refused(tmp_path):
    """A raw file is a file of the workspace, so a second machine has it."""
    escaping = RAW_ROW.replace("raw/extra.txt", "../../../etc/passwd")
    with pytest.raises(MatrixError) as refused:
        resolved_row(tmp_path, FILE_TEXT, row=escaping)
    assert "outside the workspace" in str(refused.value)
