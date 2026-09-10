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


def test_a_record_written_with_tight_slashes_is_told_about_the_spacing(tmp_path):
    """A refusal that argues with the evidence it prints sends the author the wrong way.

    `{FILE: raw/x.txt/BEFORE: init}` is read as ONE pair whose value
    swallowed the rest, so the author used to be told the record states no
    BEFORE while the message quoted back, in the same sentence, the BEFORE
    they had written; and it then listed the phases, which is the one part
    of the cell that was already right (the interface and architecture
    lenses, independently, 2026-09-10).
    """
    with pytest.raises(MatrixError) as refused:
        only_row(tmp_path, f"{BASE} / RAW: {{FILE: raw/x.txt/BEFORE: init}}")
    said = str(refused.value)
    assert "no spaces around it" in said, said
    assert "BEFORE was swallowed" in said, said


def test_a_misspelled_phase_is_refused_where_the_cell_is_read(tmp_path):
    """The phase list is known here, so a misspelling need not wait for the model.

    It used to pass this reader whole and surface at `resolve_matrix` as a
    pydantic error with no POL and no matrix vocabulary, while the MISSING
    phase three lines away got a careful refusal listing the phases (the
    interface lens, 2026-09-10).
    """
    with pytest.raises(MatrixError) as refused:
        only_row(tmp_path, f"{BASE} / RAW: {{COMMAND: PRINT x / BEFORE: inti}}")
    said = str(refused.value)
    assert "'inti'" in said and "not a phase" in said, said
    assert "9001" in said, "the refusal does not name the POL"


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
    # A RUN TYPE, NOT LEGACY. `write_matrix` upgrades a pre-0.8.0 row, whose
    # WORKFLOW becomes LEGACY, and a LEGACY row is refused the RAW key for
    # the reason `test_a_legacy_row_may_not_state_raw_commands` states: its
    # own recipe emits no raw command, so the lines would be recorded as
    # taken and never emitted. This fixture is about the FILE resolution, so
    # it names a run type.
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("| LEGACY ", "| steady ").replace("OUTPUTS: loads_{point}.txt / ", ""),
        encoding="utf-8",
    )
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


def test_a_legacy_row_may_not_state_raw_commands(tmp_path):
    """The guard the preset's own table already had, which the row's list walked past.

    A LEGACY row is built by its own recipe, which emits no raw command, so
    the case would carry the lines and the RUN RECORD would claim them
    while the script never took them. `_not_on_a_legacy_row` refuses the
    PRESET's `[[raw]]` table on such a row for exactly that reason, one
    function away, and the row's own list was appended beside it with no
    guard (the architecture lens, 2026-09-10).
    """
    from tests.tier1_offline.test_matrix_run import write_matrix

    path = write_matrix(tmp_path / "legacy.fs", [RAW_ROW])
    with pytest.raises(MatrixError) as refused:
        read_matrix(path)
    said = str(refused.value)
    assert "LEGACY" in said and "RAW" in said, said
    assert "never emitted" in said or "recorded as taken" in said, said


def test_a_raw_file_needs_a_workspace_and_says_so_where_there_is_none(tmp_path):
    """`to_campaign` reads a matrix and has no inputs to resolve a FILE against.

    It used to drop the whole RAW cell in silence, so a matrix read without
    a workspace, which `to_campaign` and `convert_matrix` both are and both
    public, lost every raw command a row stated: no error, no warning, and
    the row had parsed cleanly (the architecture lens, 2026-09-10).
    """
    from pyflightstream.cases.matrix import to_campaign
    from tests.tier1_offline.test_matrix_run import RECIPES, write_matrix

    path = write_matrix(tmp_path / "nows.fs", [RAW_ROW])
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("| LEGACY ", "| steady ").replace("OUTPUTS: loads_{point}.txt / ", ""),
        encoding="utf-8",
    )
    with pytest.raises(MatrixError) as refused:
        to_campaign(
            path, name="x", fs_version="26.120", fs_exe="C:/fs/FlightStream.exe", recipes=RECIPES
        )
    said = str(refused.value)
    assert "raw/extra.txt" in said and "workspace" in said, said


def test_a_command_record_converts_without_a_workspace(tmp_path):
    """A COMMAND record is already resolved: the line and the phase are in the cell."""
    from pyflightstream.cases.matrix import to_campaign
    from tests.tier1_offline.test_matrix_run import RECIPES, write_matrix

    row = RAW_ROW.replace("{FILE: raw/extra.txt / BEFORE: init}, ", "")
    path = write_matrix(tmp_path / "cellonly.fs", [row])
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("| LEGACY ", "| steady ").replace("OUTPUTS: loads_{point}.txt / ", ""),
        encoding="utf-8",
    )
    campaign = to_campaign(
        path, name="x", fs_version="26.120", fs_exe="C:/fs/FlightStream.exe", recipes=RECIPES
    )
    case = next(sim for sim in campaign.sims if sim.sim_id == "9301")
    assert [entry.command for entry in case.raw_commands] == ["PRINT after_the_file"]
    assert case.raw_commands[0].source == "matrix"


def test_the_presets_line_comes_before_the_rows_at_a_shared_seam(tmp_path):
    """THE REQUIREMENT'S HEADLINE, which no test asserted until this round.

    "after the preset's at the same seam" is in FR-67's own title, in the
    CHANGELOG and in a code comment naming her row 9210, and it was
    measured NOWHERE: the ordering case resolved a row against a setup
    that states no raw line at all, so it asserted only the order INSIDE
    the row (the technical-writing lens and the architecture lens,
    independently, 2026-09-10).

    This is her row 9210 as a test: a preset line, then the row's file,
    then the row's own cell line.
    """
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

    workspace = make_library(tmp_path)
    setup = workspace.inputs_dir / "setups" / "s002.toml"
    setup.write_text(
        setup.read_text(encoding="utf-8")
        + '\n[[raw]]\ncommand = "PRINT from_the_preset"\nbefore = "init"\n',
        encoding="utf-8",
    )
    raw_dir = workspace.inputs_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / "extra.txt").write_text(FILE_TEXT, encoding="utf-8")

    path = write_matrix(tmp_path / "seam.fs", [RAW_ROW])
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("| LEGACY ", "| steady ").replace("OUTPUTS: loads_{point}.txt / ", ""),
        encoding="utf-8",
    )
    resolved = resolve_matrix(
        path,
        workspace,
        name="seam",
        fs_version="26.120",
        recipes=RECIPES,
        fs_exe="C:/fs/FlightStream.exe",
    )
    case = next(sim for sim in resolved.campaign.sims if sim.sim_id == "9301")
    assert [entry.source for entry in case.raw_commands] == [
        "s002",
        "raw/extra.txt:5",
        "raw/extra.txt:6",
        "matrix",
    ], [entry.source for entry in case.raw_commands]
    assert case.raw_commands[0].command == "PRINT from_the_preset", (
        "the preset's line is not first: the shared ground comes before the specific"
    )


def test_the_documented_generator_example_writes_a_cell_this_reader_accepts(tmp_path):
    """The example on `docs/workspace-and-workflows.md`, RUN.

    It is the argument `SWEEP_WORD` already makes on the conditions page: a
    generator that spells the key by importing the name writes a row this
    reader accepts, and the two cannot drift apart. Executing it here is
    what keeps the page from rotting into a lie, and it is what the docs
    arm of GOAL-014 asks for.
    """
    from pyflightstream.cases.workflows import (
        RAW_BEFORE_KEY,
        RAW_COMMAND_KEY,
        RAW_FILE_KEY,
        RAW_VARIABLE,
    )

    record = {RAW_COMMAND_KEY: "SOLVER_SET_ITERATIONS 350", RAW_BEFORE_KEY: "init"}
    cell = f"{RAW_VARIABLE}: {{" + " / ".join(f"{k}: {v}" for k, v in record.items()) + "}"
    assert cell == "RAW: {COMMAND: SOLVER_SET_ITERATIONS 350 / BEFORE: init}"

    by_file = {RAW_FILE_KEY: "raw/extra.txt", RAW_BEFORE_KEY: "init"}
    other = f"{RAW_VARIABLE}: {{" + " / ".join(f"{k}: {v}" for k, v in by_file.items()) + "}"
    assert other == "RAW: {FILE: raw/extra.txt / BEFORE: init}"

    # THE READER ACCEPTS WHAT THE GENERATOR WROTE, which is the whole claim.
    assert only_row(tmp_path, f"{BASE} / {cell}").raw == [record]
    assert only_row(tmp_path, f"{BASE} / {other}").raw == [by_file]

    # And the page's closing note: a generator writing the BARE separator
    # produces a row this reader refuses.
    tight = f"{RAW_VARIABLE}: {{" + "/".join(f"{k}: {v}" for k, v in by_file.items()) + "}"
    with pytest.raises(MatrixError):
        only_row(tmp_path, f"{BASE} / {tight}")


# --- the round of 2026-09-10: four arms no case reached ----------------------


@pytest.mark.parametrize(
    "spelling",
    ["RAW/EXTRA.TXT", "raw\\extra.txt", "raw/../raw/extra.txt", "raw/extra.txt."],
)
def test_a_spelling_the_file_system_forgives_is_recorded_canonically(tmp_path, spelling):
    """The run record names a path a second machine has, which is why containment exists.

    All four of these resolve INSIDE the inputs on this platform, so the
    containment check passes them, and all four were written into the
    record verbatim: an upper-cased name no Linux machine resolves, a
    Windows separator, a non-canonical path, and a trailing dot the file
    system strips and the record did not. Each satisfies the check and
    defeats the reason for it (the QA lens, 2026-09-10).
    """
    row = RAW_ROW.replace("raw/extra.txt", spelling)
    case = resolved_row(tmp_path, FILE_TEXT, row=row)
    sources = [entry.source for entry in case.raw_commands if entry.source != "matrix"]
    assert sources == ["raw/extra.txt:5", "raw/extra.txt:6"], sources


def test_a_raw_file_that_is_not_utf8_is_refused_naming_the_pol(tmp_path):
    """Every other refusal on this path names the POL and the file; this one named neither.

    It reached the user as a bare `UnicodeDecodeError`. A UTF-16 file saved
    from a Windows editor is an ordinary artifact (the QA lens,
    2026-09-10).
    """
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

    workspace = make_library(tmp_path)
    raw_dir = workspace.inputs_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / "extra.txt").write_bytes(b"\xff\xfe\x00A")
    path = write_matrix(tmp_path / "utf16.fs", [RAW_ROW])
    body = path.read_text(encoding="utf-8")
    path.write_text(
        body.replace("| LEGACY ", "| steady ").replace("OUTPUTS: loads_{point}.txt / ", ""),
        encoding="utf-8",
    )
    with pytest.raises(MatrixError) as refused:
        resolve_matrix(
            path,
            workspace,
            name="utf16",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    said = str(refused.value)
    assert "9301" in said and "raw/extra.txt" in said, said
    assert "UTF-8" in said, said


def test_a_byte_order_mark_does_not_ride_into_the_first_command(tmp_path):
    """A mark from a Windows editor became part of the first command's NAME.

    The emitter then refused a command the author can see is spelled
    correctly, which is the worst shape a refusal takes.
    """
    marked = "\ufeff" + FILE_TEXT
    case = resolved_row(tmp_path, marked)
    from_file = [entry for entry in case.raw_commands if entry.source != "matrix"]
    assert from_file[0].command == "SOLVER_SET_ITERATIONS 400", from_file[0].command


def test_a_link_inside_the_inputs_pointing_out_is_refused(tmp_path):
    """The containment check is sound BECAUSE `.resolve()` precedes the comparison.

    `.resolve()` normalises `..` AND follows a link, so a junction placed
    inside the inputs and pointing out is caught. A lexical comparison
    defeats `..` and lets the junction through, and the QA lens measured
    that such a mutant survived the whole suite because no case reached a
    link (2026-09-10). This is that case.
    """
    import os
    import subprocess

    from tests.tier1_offline.test_matrix_run import make_library

    workspace = make_library(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "extra.txt").write_text("PRINT i_am_outside\n", encoding="utf-8")
    link = workspace.inputs_dir / "raw"
    done = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        text=True,
        # EXPLICIT, and identical to the inherited default. The estate's
        # rule is that the call SAYS so rather than letting a
        # runner-injected variable arrive unnoticed, and a guard under
        # tests/ counts the spawns that do not.
        env=os.environ.copy(),
    )
    if done.returncode != 0 or not link.exists():
        pytest.skip(f"this host cannot create a junction: {done.stdout}{done.stderr}")

    from pyflightstream.cases.matrix import read_matrix
    from pyflightstream.workspace.matrix import _the_rows_raw_commands

    path = tmp_path / "linked.fs"
    path.write_text(
        HEADER
        + "9001 | WORK | LINK | MACH:0.14, REmi:5.6, ALPHA:sweep, BETA:0 | 0,2 | r011 | s010 "
        + "| p011 | 26.123 | 0 | 1 | unsteady_rotor | "
        + f"{BASE} / RAW: {{FILE: raw/extra.txt / BEFORE: init}}\n",
        encoding="utf-8",
    )
    row = read_matrix(path)[0]
    with pytest.raises(MatrixError) as refused:
        _the_rows_raw_commands(row, workspace.inputs_dir)
    assert "outside the workspace" in str(refused.value)


def test_a_records_pairs_still_split_on_the_bare_slash_for_every_other_key(tmp_path):
    """The default separator is the one MOTIONS and ROTATE have always used.

    A mutant changing that default to the spaced form survived the whole
    suite, because no case anywhere writes an UNSPACED record (the QA
    lens, 2026-09-10). The tolerance the default provides was exercised by
    nothing, so a later tidy of the raw reader could take it away and no
    test would notice.
    """
    row = only_row(
        tmp_path,
        f"{BASE} / MOTIONS: {{MOVING_BC_ALIAS: PUSHER/RPM: 900}}",
    )
    assert row.motions == [{"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"}], row.motions
