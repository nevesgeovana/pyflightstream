"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_setup_bc_is_complete_every_in_scope_command_operational_the_rest_refused(tmp_path):
    """The setup/BC chapters of the 26.124 database are complete at this tree.

    GOAL033:capability_ids:items:G67

    Measured, not listed: the 13 setup/BC chapters hold 155 commands, and
    they divide exactly into 121 in scope and 34 not applicable (151, 121
    and 30 until 0.37.0, whose 26.125 database adds four setup commands no
    26.124 row carries, each refused on 26.124). Every
    in-scope command with a script route is BUILT here, stated and control,
    and the stated script carries the command's block while the control does
    not; the 12 whose operation needs a native replay execute that replay.
    Missing private receipts leave this gate explicitly unproven and skipped,
    rather than passed by a comment tag. Every one of the 33 commands 26.124 lacks is refused
    by the emitter naming it, and the one the owner excluded appears in no
    script any route writes.
    """
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.script import Script
    from tests.tier1_offline import test_goal034_setup_operational_commands as setup

    registry = CommandRegistry.load()
    chapters = {n for n, e in registry.commands.items() if e.chapter in setup.SETUP_CHAPTERS}
    elsewhere = {c for commands in setup.PROVED_ELSEWHERE.values() for c in commands}
    routed = set(setup.ROUTES) | set(setup.SCRIPT_ROUTES) | elsewhere
    refused = set(setup.REFUSED_ON_26124) | set(setup.OWNER_EXCLUDED)
    assert routed | refused == chapters and not routed & refused

    broken, written = [], []
    for index, (command, route) in enumerate(sorted(setup.ROUTES.items())):
        stated_dir, control_dir = tmp_path / f"r{index}s", tmp_path / f"r{index}c"
        stated_dir.mkdir()
        control_dir.mkdir()
        lines, why = setup._render(route.stated(stated_dir))
        if lines is None or not setup._carries(lines, route.block):
            broken.append(f"{command}: stated {why[:120] or 'lacks its block'}")
            continue
        written.extend(lines)
        if route.control is not None:
            control, why = setup._render(route.control(control_dir))
            if control is None or setup._carries(control, route.block):
                broken.append(f"{command}: control {why[:120] or 'carries the block'}")
    for index, (command, route) in enumerate(sorted(setup.SCRIPT_ROUTES.items())):
        stated_dir, control_dir = tmp_path / f"s{index}s", tmp_path / f"s{index}c"
        stated_dir.mkdir()
        control_dir.mkdir()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lines, control = route.stated(stated_dir), route.control(control_dir)
        written.extend(lines)
        if not setup._carries(lines, route.block) or setup._carries(control, route.block):
            broken.append(f"{command}: script route does not discriminate")
    for path, commands in setup.PROVED_ELSEWHERE.items():
        # The replays skip without the private receipts, so CI holds that each tag sits in
        # a test that reads a recorded receipt and asserts on it, not that the replay ran.
        held = setup.tag_holders((ROOT / path).read_text(encoding="utf-8"))
        broken += [f"{c}: {held.get(c)}" for c in commands if held.get(c) != "ok"]
    assert not broken, "in scope and not operational:\n  " + "\n  ".join(broken)

    admitted = []
    for command, error in setup.REFUSED_ON_26124.items():
        script = Script(setup.BUILD)
        with pytest.raises(error) as refusal:
            script.emit(command)
        if command not in str(refusal.value) or command in script.render():
            admitted.append(command)
    assert not admitted, f"not refused by name: {admitted}"
    excluded = [line for line in written if line.split(" ", 1)[0] in setup.OWNER_EXCLUDED]
    assert not excluded, f"an owner-excluded command is written: {excluded[:3]}"
    for path, commands in setup.PROVED_ELSEWHERE.items():
        setup._prove_elsewhere(path, commands)
