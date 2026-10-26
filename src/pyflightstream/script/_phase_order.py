"""Phase-order validation without mutating the Script emission state."""

from __future__ import annotations

from typing import cast

from pyflightstream.commands import CommandEntry, Phase
from pyflightstream.script import _ORDERED_PHASES, Script, ScriptOrderError
from pyflightstream.script._ledger_tables import _INITIALIZATION_COMMAND


def check_phase(self: Script, entry: CommandEntry) -> tuple[int, tuple[str, int]] | None:
    """Refuse a command whose phase has passed; return the phase it reaches.

    Returns the new phase index and its setter when the command moves the
    phase forward, or None when it does not. Nothing is moved here:
    :meth:`emit` commits the move once the block is accepted, so a command
    refused by a later check does not leave the script in a phase it never
    reached (PFS-2104.019).
    """
    if getattr(self, "_marking_only", False):
        if entry.phase in (Phase.INIT, Phase.EXEC):
            raise ScriptOrderError(
                f"{entry.name}: a marking script cannot initialize or run the solver"
            )
        if entry.name in {
            "SELECT_MESH_NODE",
            "MARK_WAKE_TERMINATION_NODES",
            "AUTO_DETECT_WAKE_TERMINATION_NODES",
            "SURFACE_COMBINE",
            "SURFACE_RENAME",
        } and (self._phase_index is None or self._phase_index <= 1):
            return None
    if entry.phase is Phase.CONTROL:
        return None
    if self._through_the_door:
        # emit_after_initialization judged this emission, and it moves no
        # phase: the next command still meets the init phase.
        return None
    index = _ORDERED_PHASES.index(entry.phase)
    if self._reinitialization_owed is not None and index > _ORDERED_PHASES.index(Phase.INIT):
        waiting, line = self._reinitialization_owed
        raise ScriptOrderError(
            f"{entry.name} belongs to the {entry.phase} phase, and {waiting} at line {line} "
            "was emitted on an initialised solver, which uses what it marked only "
            f"once it initialises again. Emit {_INITIALIZATION_COMMAND} after it, "
            "with the settings of the first, before the solver starts"
        )
    if self._phase_index is not None and index < self._phase_index:
        setter_name, setter_line = cast(tuple[str, int], self._phase_setter)
        current = _ORDERED_PHASES[self._phase_index]
        raise ScriptOrderError(
            f"{entry.name} is a {entry.phase} command, but the script already "
            f"reached the {current} phase ({setter_name} at line {setter_line}). "
            "Auxiliary definitions such as coordinate systems, actuators, and "
            "motions must precede solver initialization; the phase order is "
            "geometry, setup, init, exec, analysis, export."
        )
    if self._phase_index is None or index > self._phase_index:
        return index, (entry.name, len(self._lines) + 1)
    return None


def check_after_initialization(self: Script, name: str) -> None:
    """Validate the narrow setup-command door without changing phase or state."""
    entry = self._view[name]
    if entry.phase is not Phase.SETUP:
        raise ScriptOrderError(
            f"{name} belongs to the {entry.phase} phase, and emit_after_initialization carries "
            "a setup command past an initialised solver and nothing else. Emit it "
            "with emit(), which holds it to the phase order"
        )
    if self._initialized_at is None:
        raise ScriptOrderError(
            f"{name}: no {_INITIALIZATION_COMMAND} precedes it, so there is no "
            "initialised solver for it to act on. Emit it with emit(), before the "
            "init phase, where a setup command belongs"
        )
    init = _ORDERED_PHASES.index(Phase.INIT)
    if self._phase_index is not None and self._phase_index > init:
        setter_name, setter_line = self._phase_setter or ("", 0)
        raise ScriptOrderError(
            f"{name}: the script already reached the "
            f"{_ORDERED_PHASES[self._phase_index]} phase ({setter_name} at line "
            f"{setter_line}), so the solver ran on the initialisation at line "
            f"{self._initialized_at}. A setup command after an initialisation acts "
            f"only through a second {_INITIALIZATION_COMMAND}, emitted before the "
            "solver starts"
        )
