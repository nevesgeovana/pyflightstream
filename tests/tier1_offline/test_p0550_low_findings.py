"""P0550-LOW: the small defects of the 0.54.0 review that carry no decision.

Pipeline role: tier-1 oracle of PFS-2187.07. Each test runs the verb or the command line a user
runs and reads what the user reads: the message, the exit code and the files.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from tests.tier1_offline.test_p0540_sector_remesh import ARGS, build_blunt_sector


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
    note = commands["CAD_CREATE_AUTO_CROSS_SECTIONS"].versions["26.126"].note
    assert note.endswith("not their geometric accuracy")
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
