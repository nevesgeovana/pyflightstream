"""Solver actions saved in a geometry: named by inventory, removed by --clean (FR-308).

The fixture reproduces the shape measured on 2026-09-30 in a 26.1 save:
the SOLVER block ends with a count and, per action, a name line, a command
line padded with spaces, and ``<length of the command>,<1 COMMAND_LINE or
0 SCRIPT>, F``. The lines before the count include ``0`` and ``1,1, F``,
which a walk that overran the count would read as one more record.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

import pyflightstream._fsm as fsm_module
from pyflightstream._fsm import (
    MESH_MARKER,
    MeshReadError,
    saved_solver_actions,
    without_saved_solver_actions,
)
from pyflightstream.run.cli import main

CLOCK = '"C:/Program Files/Python313/python.exe" "actions/pfs_walltime_clock.py"'
STOP = "actions/pfs_walltime_stop.txt"
ACTIONS = [("pfs_walltime_clock", CLOCK, 1), ("pfs_walltime_stop", STOP, 0)]
TIER3 = Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries"


def _saved_simulation(path, actions, *, count=None, names=("Spinner", "Nacelle")):
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$", "$SOLVER_START$", " F", "0", "0", "1,1, F"]
    body.append(str(len(actions) if count is None else count))
    for name, command, kind in actions:
        body += [name.ljust(70), command.ljust(70), f"{len(command)},{kind}, F"]
    body += ["$SOLVER_END$", "$POST_START$", "0", "$POST_END$"]
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


def test_reader_names_each_saved_action_fr_308(tmp_path):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "01_ROTOR.fsm", ACTIONS)
    assert saved_solver_actions(geometry) == (
        ("pfs_walltime_clock", CLOCK, "COMMAND_LINE"),
        ("pfs_walltime_stop", STOP, "SCRIPT"),
    )


def test_reader_reads_no_action_and_no_block_fr_308(tmp_path):
    # Verifies FR-308.
    assert saved_solver_actions(_saved_simulation(tmp_path / "a.fsm", [])) == ()
    bare = tmp_path / "b.fsm"
    bare.write_text(f"{MESH_MARKER}\r\n9999\r\n99\r\n0\r\n$MESH_END$\r\n", encoding="utf-8")
    assert saved_solver_actions(bare) is None


def test_reader_refuses_a_count_that_disagrees_fr_308(tmp_path):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "c.fsm", ACTIONS, count=3)
    with pytest.raises(MeshReadError, match="count '3' before 2 action record"):
        saved_solver_actions(geometry)


@pytest.mark.skipif(not TIER3.is_dir(), reason="tier-3 geometries not in this checkout")
def test_every_tier3_geometry_carries_no_saved_action_fr_308():
    # Verifies FR-308.
    files = sorted(TIER3.glob("*.fsm"))
    assert files
    assert {path.name: saved_solver_actions(path) for path in files} == {
        path.name: () for path in files
    }


def test_inventory_warns_and_names_clean_by_default_fr_308(tmp_path, capsys):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "01_ROTOR.fsm", ACTIONS)
    before = geometry.read_bytes()
    assert main(["inventory", str(geometry)]) == 0
    captured = capsys.readouterr()
    assert "warning: 01_ROTOR.fsm carries 2 unsteady solver action(s)" in captured.err
    assert "pfs_walltime_clock [COMMAND_LINE]" in captured.err and CLOCK in captured.err
    assert f"pyfs-matrix inventory {geometry} --clean" in captured.err
    assert captured.out.strip() == str(tmp_path / "01_ROTOR.boundaries.toml")
    assert geometry.read_bytes() == before, "the warning changed the file"


def test_inventory_is_silent_on_a_clean_geometry_fr_308(tmp_path, capsys):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "02_ROTOR.fsm", [])
    assert main(["inventory", str(geometry)]) == 0
    assert "warning" not in capsys.readouterr().err


def test_clean_removes_only_the_actions_and_keeps_a_copy_fr_308(tmp_path, capsys):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "01_ROTOR.fsm", ACTIONS)
    original = geometry.read_bytes()
    expected = _saved_simulation(tmp_path / "expected.fsm", []).read_bytes()
    sidecar = tmp_path / "01_ROTOR.boundaries.toml"
    sidecar.write_text('boundaries = ["kept"]\n', encoding="utf-8")
    assert main(["inventory", str(geometry), "--clean"]) == 0
    err = capsys.readouterr().err
    assert "removed saved action pfs_walltime_clock [COMMAND_LINE]" in err
    assert "removed saved action pfs_walltime_stop [SCRIPT]" in err
    assert geometry.read_bytes() == expected
    backups = list(tmp_path.glob("01_ROTOR.fsm.bak-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert sidecar.read_text(encoding="utf-8") == 'boundaries = ["kept"]\n'
    assert main(["inventory", str(geometry), "--overwrite"]) == 0
    assert "warning" not in capsys.readouterr().err


def test_clean_of_a_clean_geometry_writes_nothing_fr_308(tmp_path, capsys):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "02_ROTOR.fsm", [])
    before = geometry.read_bytes()
    assert main(["inventory", str(geometry), "--clean"]) == 0
    assert "carries no saved unsteady solver action" in capsys.readouterr().err
    assert geometry.read_bytes() == before
    assert not list(tmp_path.glob("*.bak-*"))


def test_clean_refuses_a_shape_it_cannot_read_fr_308(tmp_path, capsys):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "c.fsm", ACTIONS, count=3)
    before = geometry.read_bytes()
    assert main(["inventory", str(geometry), "--clean"]) == 2
    assert "count '3' before 2 action record" in capsys.readouterr().err
    assert geometry.read_bytes() == before
    assert not list(tmp_path.glob("*.bak-*"))


def test_mutant_keeping_the_count_turns_the_check_red_fr_308(tmp_path):
    # Verifies FR-308.
    source = Path(fsm_module.__file__).read_text(encoding="utf-8")
    old = '    kept = head[: len(head) - len(head.lstrip())] + "0"\n'
    assert source.count(old) == 1
    mutant = source.replace(old, "    kept = head\n")
    assert mutant != source
    spec = importlib.util.spec_from_loader("fsm_mutant_count", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pyflightstream"
    sys.modules["fsm_mutant_count"] = module
    try:
        exec(compile(mutant, "fsm_mutant_count.py", "exec"), module.__dict__)
        text = _saved_simulation(tmp_path / "m.fsm", ACTIONS).read_bytes().decode("latin-1")
        broken, _ = module.without_saved_solver_actions(text, "m.fsm")
        (tmp_path / "broken.fsm").write_bytes(broken.encode("latin-1"))
        with pytest.raises(MeshReadError):
            saved_solver_actions(tmp_path / "broken.fsm")
        fixed, _ = without_saved_solver_actions(text, "m.fsm")
        (tmp_path / "fixed.fsm").write_bytes(fixed.encode("latin-1"))
        assert saved_solver_actions(tmp_path / "fixed.fsm") == ()
    finally:
        sys.modules.pop("fsm_mutant_count", None)


def test_reader_refuses_an_action_whose_command_length_disagrees_fr_308(tmp_path):
    # Verifies FR-308.
    geometry = _saved_simulation(tmp_path / "d.fsm", ACTIONS[:1])
    stated = f"{len(CLOCK)},1, F".encode()
    assert stated in geometry.read_bytes()
    geometry.write_bytes(geometry.read_bytes().replace(stated, f"{len(CLOCK) + 1},1, F".encode()))
    with pytest.raises(MeshReadError):
        saved_solver_actions(geometry)
