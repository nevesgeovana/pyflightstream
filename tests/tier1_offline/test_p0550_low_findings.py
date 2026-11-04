"""P0550-LOW: the small defects of the 0.54.0 review that carry no decision.

Pipeline role: tier-1 oracle of PFS-2187.07. Each test runs the verb or the command line a user
runs and reads what the user reads: the message, the exit code and the files.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.qa import apply_compat
from tests.tier1_offline.test_command_db import QUOTED_PHRASE
from tests.tier1_offline.test_p0540_sector_remesh import ARGS, build_blunt_sector
from tests.tier1_offline.test_qa_compat import write_chapter_fixture, write_dated_report


def _messages(call: Callable[[], object]) -> list[str]:
    """Return the text of every warning the call raised."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    return [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]


@pytest.mark.requirement("FR-3520")
def test_p0550_the_sector_angle_warning_states_the_angle_the_copies_need(tmp_path: Path) -> None:
    from pyflightstream.workspace import power_off_body

    source = build_blunt_sector(tmp_path)
    text = " ".join(
        _messages(
            lambda: power_off_body(source, blades=["Blade1"], copies=2, out=tmp_path / "a.fsm")
        )
    )
    assert "2 copies (N = 2 was asked) need 360/2 = 180.0000 deg each" in text
    assert "rotation check below" not in text
    assert "for a whole number N" not in text


def test_p0550_the_body_verb_does_not_speak_of_the_rows_of_a_remesh(tmp_path: Path) -> None:
    from pyflightstream.workspace import power_off_body, sector_remesh

    source = build_blunt_sector(tmp_path)
    body = " ".join(
        _messages(
            lambda: power_off_body(
                source, blades=["Blade1"], copies=5, tip_radius=5.0, out=tmp_path / "b.fsm"
            )
        )
    )
    assert "tip-radius" in body and "largest radius about the axis" in body
    assert "rows of a remesh" not in body
    assert "span rows" not in " ".join(
        _messages(
            lambda: power_off_body(source, blades=["Blade1"], copies=5, out=tmp_path / "c.fsm")
        )
    )
    remesh = " ".join(
        _messages(
            lambda: sector_remesh(
                source, blades=["Blade1"], tip_radius=5.0, out=tmp_path / "r.fsm", **ARGS
            )
        )
    )
    assert "the rows of a remesh stop short" in remesh


@pytest.mark.requirement("FR-3521")
def test_p0550_an_overwritten_wheel_of_fewer_copies_leaves_no_points_file_of_the_old_one(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace._wheel import sector_to_wheel
    from tests.tier1_offline.test_p0540_wheel import build_sector

    sector = build_sector(tmp_path)
    out = tmp_path / "out" / "wheel.obj"
    out.parent.mkdir()
    sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], out=out)
    assert out.with_name("wheel.TE_a_6.te.txt").is_file()
    stranger = out.with_name("wheel.mine.te.txt")
    stranger.write_text("METER\n", encoding="utf-8")
    again = sector_to_wheel(sector.obj, copies=3, blades=["Blade1"], out=out, overwrite=True)
    names = sorted(p.name for p in out.parent.glob("*.te.txt"))
    assert not any(f"_{k}.te.txt" in n for n in names for k in (4, 5, 6)), names
    assert {"wheel.TE_a_3.te.txt", "wheel.TE_b_1.te.txt", "wheel.N.te.txt"} <= set(names)
    assert stranger.is_file()
    written = {p.name for p in again.files if p.name.endswith(".te.txt")}
    assert written == set(names) - {stranger.name}


def test_p0550_the_cad_create_notes_end_in_a_complete_clause() -> None:
    from pyflightstream.commands import CommandRegistry

    commands = CommandRegistry.load().commands
    for name in ("CAD_CREATE_IMPORT_CURVE_TXT", "CAD_CREATE_AUTO_CROSS_SECTIONS"):
        for build, row in commands[name].versions.items():
            assert "[...]" not in (row.note or ""), (name, build)
    for build in ("26.126", "26.127"):
        note = commands["CAD_CREATE_AUTO_CROSS_SECTIONS"].versions[build].note
        assert note.endswith("before=0, after=15, control=0; expected 0,9,0"), build
        assert "The 26.125 note: FSM-26.125 p.301" not in note, build
    sentinel = commands["CAD_CREATE_IMPORT_CURVE_TXT"].versions["26.125"].note
    assert sentinel.endswith("(END sentinel missing)")


def test_p0550_mark_boundaries_refuses_a_broken_command_without_python_advice(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import argparse

    from pyflightstream.run._cli_geometry import run_geometry
    from pyflightstream.script import BrokenCommandError

    error = BrokenCommandError("FOO is broken on 26.126. Script.allow_broken waives it.")
    error.finding = "FOO is broken on 26.126."

    class Poisoned:
        """A mesh argument whose reading raises what a script with a broken command raises."""

        def __fspath__(self) -> str:
            raise error

    args = argparse.Namespace(geometry_command="mark-boundaries", mesh=Poisoned(), apply=False)
    code = run_geometry(args)
    err = capsys.readouterr().err
    assert code == 2
    assert "FOO is broken on 26.126." in err
    assert "allow_broken" not in err


@pytest.mark.requirement("FR-3522")
def test_p0550_a_span_cell_that_asks_for_millions_of_quads_is_refused_before_building(
    tmp_path: Path,
) -> None:
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace import sector_remesh
    from pyflightstream.workspace._sector_remesh import MAX_SPAN_ROWS

    source = build_blunt_sector(tmp_path)
    out = tmp_path / "huge.fsm"
    args = {**ARGS, "span_cell": 1e-5}
    with pytest.raises(
        InputValueError, match=rf"span rows.*most this verb builds is {MAX_SPAN_ROWS}"
    ):
        sector_remesh(source, blades=["Blade1"], tip_radius=1.218, out=out, **args)
    assert not out.exists()


def test_p0550_the_row_bound_is_checked_where_the_rows_are_made() -> None:
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace._sector_remesh import Plan, span_rows

    def plan(cell: float) -> Plan:
        return Plan(12, 0.03, cell, 0.5, 0.3, 1.2)

    assert len(span_rows(0.4, plan(0.1))) < 100
    with pytest.raises(InputValueError, match="span rows"):
        span_rows(0.4, plan(1e-5))


def test_p0550_an_overwritten_wheel_removes_only_the_points_files_a_wheel_wrote(
    tmp_path: Path,
) -> None:
    from pyflightstream.workspace._wheel import sector_to_wheel
    from pyflightstream.workspace.sidecars import inventory_sidecar
    from tests.tier1_offline.test_p0540_wheel import build_sector

    sector = build_sector(tmp_path)
    folder = tmp_path / "out"
    folder.mkdir()
    mesh = folder / "hers.obj"
    mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng W\nf 1 2 3\n", encoding="utf-8")
    hers = folder / "hers.W.te.txt"
    hers.write_text("METER\n1 0 0\n", encoding="utf-8")
    inventory_sidecar(mesh, "obj").write_text(
        'boundaries = ["W"]\n[trailing_edges.W]\nfile = "hers.W.te.txt"\n', encoding="utf-8"
    )
    sector_to_wheel(sector.obj, copies=3, blades=["Blade1"], out=mesh, overwrite=True)
    assert hers.is_file()
    out = folder / "wheel.obj"
    sector_to_wheel(sector.obj, copies=6, blades=["Blade1"], out=out)
    mine = folder / "wheel.nodes.te.txt"
    mine.write_text("METER\n1 0 0\n", encoding="utf-8")
    side = inventory_sidecar(out, "obj")
    side.write_text(
        side.read_text(encoding="utf-8") + '\n[extra]\nfile = "wheel.nodes.te.txt"\n',
        encoding="utf-8",
    )
    sector_to_wheel(sector.obj, copies=3, blades=["Blade1"], out=out, overwrite=True)
    assert mine.is_file()
    assert not (folder / "wheel.TE_a_6.te.txt").exists()


def test_p0550_mark_boundaries_names_no_flag_it_does_not_have(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import argparse

    from pyflightstream.run._cli_geometry import run_geometry
    from pyflightstream.script import BrokenCommandError

    error = BrokenCommandError("FOO is broken on 26.126. Script.allow_broken waives it.")
    error.finding = "FOO is broken on 26.126."

    class Poisoned:
        def __fspath__(self) -> str:
            raise error

    run_geometry(
        argparse.Namespace(geometry_command="mark-boundaries", mesh=Poisoned(), apply=False)
    )
    err = capsys.readouterr().err
    assert "--build" not in err
    assert "fs_build" in err


def test_p0550_a_span_cell_too_small_for_a_number_is_refused_not_a_traceback() -> None:
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace._sector_remesh import Plan, span_rows

    with pytest.raises(InputValueError, match="most this verb builds is 10000"):
        span_rows(0.4, Plan(12, 0.03, 1e-320, 0.5, 0.3, 1.2))


def test_p0550_the_row_bound_is_ten_thousand_rows_exactly() -> None:
    from pyflightstream._errors import InputValueError
    from pyflightstream.workspace._sector_remesh import Plan, span_rows

    assert len(span_rows(0.0, Plan(12, 0.03, 1e-3, 0.5, 5.0, 8.332))) == 10000
    with pytest.raises(InputValueError, match="10001 span rows.*in the mesh's unit"):
        span_rows(0.0, Plan(12, 0.03, 1e-3, 0.5, 5.0, 8.333))


@pytest.mark.requirement("FR-3520")
@pytest.mark.parametrize(
    ("span", "copies", "words"),
    [
        (47.0, 8, "but the 8 copies it is read as need 360/8 = 45.0000 deg each"),
        (300.0, 1, "which is not 360/N for any N of 2 or more;"),
    ],
)
def test_p0550_the_sector_angle_warning_of_a_sector_with_no_copies_asked(
    span: float, copies: int, words: str
) -> None:
    import math
    from types import SimpleNamespace

    from pyflightstream.workspace._sector_driver import span_check

    sector = SimpleNamespace(span=math.radians(span), copies=copies)
    assert words in " ".join(_messages(lambda: span_check(sector, None)))


@pytest.mark.requirement("FR-3530")
def test_p0550_no_command_note_ends_in_a_placeholder() -> None:
    from pyflightstream.commands import CommandRegistry

    bad = [
        f"{name} {build}"
        for name, command in CommandRegistry.load().commands.items()
        for build, row in command.versions.items()
        if "[...]" in (row.note or "")
    ]
    assert bad == []


_DIAGNOSIS = "the command ran (script processing continued past it) but its effect was not observed"
_LONG_CLAUSE = (
    "the line was refused at the position the package emits it with no output and a kill at "
    "240.5 seconds on the first run and no end sentinel in the log of the second"
)
_SOLVER_WORDS = (
    "the line just before the solver start was refused as Unrecognized command in script ... at "
    "line 379, and the script stopped there with return code 0 and no export written"
)


@pytest.mark.requirement("FR-3551")
@pytest.mark.parametrize("build", ["26.120", "26.121"], ids=["row_rewritten", "row_added"])
@pytest.mark.parametrize(
    ("detail", "kept", "named"),
    [
        pytest.param(
            f"{_DIAGNOSIS}; expected: the settings dump reports the 5000 m standard atmosphere "
            "density at every point of the sweep, which the run did not print",
            _DIAGNOSIS,
            True,
            id="last_clause_inside_the_cap",
        ),
        pytest.param(
            f"{_LONG_CLAUSE}. An earlier run with the line moved hung.",
            _LONG_CLAUSE,
            True,
            id="first_clause_past_the_cap",
        ),
        pytest.param(_LONG_CLAUSE, _LONG_CLAUSE, False, id="one_clause_written_whole"),
        pytest.param(
            _SOLVER_WORDS.replace("Unrecognized", "'Unrecognized").replace("379,", "379',")
            + ". A later run hung.",
            _SOLVER_WORDS,
            True,
            id="solver_words_lose_their_quotes",
        ),
    ],
)
def test_p0550_a_promoted_long_detail_keeps_a_complete_note_naming_its_report(
    tmp_path: Path, build: str, detail: str, kept: str, named: bool
) -> None:
    commands = tmp_path / "commands"
    write_chapter_fixture(commands)
    report = write_dated_report(
        tmp_path,
        {"PRINT": {"outcome": "broken", "detail": detail}},
        date="2026-08-11",
        version=build,
    )
    apply_compat(report, repo_root=tmp_path, commands_dir=commands)
    chapter = yaml.safe_load((commands / "script_controls.yaml").read_text(encoding="utf-8"))
    row = chapter["PRINT"]["versions"][build]
    assert row["report"] == f"reports/compat/{report.name}"
    pointer = f". The full text is in {row['report']}."
    assert row["note"] == (f"{kept}{pointer}" if named else kept)
    # What the database's own guards refuse, on the row this promotion wrote.
    assert "[...]" not in row["note"]
    assert QUOTED_PHRASE.search(row["note"]) is None


@pytest.mark.requirement("FR-3530")
@pytest.mark.parametrize(
    ("command", "build", "needle"),
    [
        ("NEW_OFF_BODY_STREAMLINE", "26.126", "line 24, NEW_OFF_BODY_STREAMLINE"),
        ("NEW_OFF_BODY_STREAMLINE", "26.127", "Probe on 26.127"),
        ("NEW_STREAMLINE_DISTRIBUTION", "26.126", "line 24, NEW_STREAMLINE_DISTRIBUTION"),
        ("NEW_OFF_BODY_STREAMTUBE", "26.124", "line 33, PRINT PYFS_PROBE_END"),
        ("NEW_OFF_BODY_STREAMTUBE", "26.125", "line 36, PRINT PYFS_PROBE_END"),
        ("CREATE_NEW_6DOF_EXTERNAL_FORCE", "26.124", "line 48, CREATE_NEW_6DOF_EXTERNAL_FORCE"),
        ("CREATE_NEW_6DOF_EXTERNAL_FORCE", "26.126", "The 26.126 record (CMP-26126"),
        ("CREATE_NEW_6DOF_EXTERNAL_FORCE", "26.127", "The 26.127 record (CMP-26127"),
        ("CREATE_FREE_SURFACE_TFI_MESH", "26.126", "line 12, CREATE_FREE_SURFACE_TFI_MESH"),
        ("CREATE_FREE_SURFACE_TFI_MESH", "26.127", "Probe on 26.127"),
        ("CREATE_BULK_SEPARATION", "26.120", "line 12, CREATE_BULK_SEPARATION PYFS_BULK"),
    ],
)
def test_p0550_a_note_carries_the_measurement_its_report_recorded(
    command: str, build: str, needle: str
) -> None:
    from pyflightstream.commands import CommandRegistry

    assert needle in (CommandRegistry.load().commands[command].versions[build].note or "")


@pytest.mark.requirement("FR-3530")
def test_p0550_no_command_note_carries_an_empty_instrument_head() -> None:
    from pyflightstream.commands import CommandRegistry

    bad = [
        f"{name} {build}"
        for name, command in CommandRegistry.load().commands.items()
        for build, row in command.versions.items()
        if "head:  |" in (row.note or "")
    ]
    assert bad == []


# The QA and tech-writer lenses on the promoted note.
_LONG_NOTE_NL = chr(10)
LONG = "the command ran (script processing continued past it) but its effect was not observed; expected: the settings dump reports the 5000 m standard atmosphere density at every point of the sweep"  # noqa: E501
NL = chr(10)
CR = chr(13) + NL
Q = chr(39)
TAIL = " with no export written to the folder and the log held nothing about the command at all in any line of it and the run went on past it"  # noqa: E501


@pytest.mark.requirement("FR-3551")
def test_p0550_a_repeated_promotion_of_one_long_detail_keeps_one_note_naming_the_latest_report(
    tmp_path,
):
    import yaml

    from pyflightstream.qa import apply_compat
    from tests.tier1_offline.test_qa_compat import write_chapter_fixture, write_dated_report

    commands = tmp_path / "commands"
    write_chapter_fixture(commands)
    for date in ("2026-08-11", "2026-08-12"):
        report = write_dated_report(
            tmp_path, {"PRINT": {"outcome": "broken", "detail": LONG}}, date=date, version="26.120"
        )
        apply_compat(report, repo_root=tmp_path, commands_dir=commands)
    row = yaml.safe_load((commands / "script_controls.yaml").read_text(encoding="utf-8"))["PRINT"][
        "versions"
    ]["26.120"]
    assert row["note"] == (
        "the command ran (script processing continued past it) but its effect was not observed. "
        "The full text is in " + row["report"] + "."
    )


@pytest.mark.requirement("FR-3551")
@pytest.mark.parametrize(
    ("detail", "kept"),
    [
        (
            "the run stopped at approx. 240 seconds" + TAIL + ". More.",
            "the run stopped at approx. 240 seconds" + TAIL,
        ),
        ("Fig. 3 shows the row" + TAIL + ". More.", "Fig. 3 shows the row" + TAIL),
        (
            "the run (stopped; the log held nothing) went on" + TAIL + ". More.",
            "the run (stopped; the log held nothing) went on" + TAIL,
        ),
        (
            "the log said " + Q + "alpha; beta gamma" + Q + " and went on" + TAIL + ". More.",
            "the log said alpha; beta gamma and went on" + TAIL,
        ),
    ],
)
def test_p0550_a_clause_never_ends_on_an_abbreviation_or_inside_a_bracket_or_a_quote(detail, kept):
    from pyflightstream.qa.compat import _one_line_note

    assert _one_line_note(detail, "r.yaml") == f"{kept}. The full text is in r.yaml."


@pytest.mark.requirement("FR-3551")
def test_p0550_a_short_detail_loses_a_multi_word_quote() -> None:
    from pyflightstream.qa.compat import _one_line_note

    assert _one_line_note("refused as 'Unrecognized command' at line 3", "r.yaml") == (
        "refused as Unrecognized command at line 3"
    )


@pytest.mark.requirement("FR-3551")
def test_p0550_the_note_keeps_the_last_clause_inside_the_limit_and_no_abbreviation_ends_one() -> (
    None
):
    from pyflightstream.qa.compat import _one_line_note

    first, second = "a" * 60, "b" * 60
    rest = "c" * 100
    assert _one_line_note(f"{first}; {second}; {rest}", "r.yaml") == (
        f"{first}; {second}. The full text is in r.yaml."
    )
    lead = "see e.g. The manual on this " + "d" * 130
    assert _one_line_note(f"{lead}. More.", "r.yaml") == f"{lead}. The full text is in r.yaml."
