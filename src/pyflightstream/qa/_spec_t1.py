"""The probe catalog, fourth part: the commands the workflow goldens emit and no spec covered.

Pipeline role: the entries of ``PROBE_SPECS`` for the commands the package's
committed workflow goldens render (``tests/tier1_offline/goldens/workflows``)
and for which ``pyfs-qa probe`` had no probe specification (FR-342, the T1
item of PFS-2073.06): ``ROTATE_SURFACE`` and ``SURFACE_ROTATE`` (the rotation
command by build) and ``SET_NEW_UNSTEADY_SOLVER_ACTION``. A build whose database
does not hold a command never runs its entry: ``ROTATE_SURFACE`` and
``SET_NEW_UNSTEADY_SOLVER_ACTION`` exist on 26.124, the build the native run
measures. Three more commands the goldens of the older builds render
(``SONIC_VELOCITY``, ``SET_MOTION_ANGULAR_VELOCITY``, ``SET_MOTION_IS_ROTOR``)
are in no database view of 26.120 or later, so no authorised run could judge
them and they carry no entry.

The module is imported by ``pyflightstream.qa.specs`` and registers into the
shared registry of ``pyflightstream.qa._spec_kit``. Where no instrument reads
the stored value, the assertion returns None and the command stays unprobed.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream.qa._spec_kit import _emit, _seq, _spec
from pyflightstream.qa.probes import (
    ProbeArtifacts,
    Requires,
    emit_solver_setup,
    fsm_changed,
    printed_line,
)
from pyflightstream.script import Script
from pyflightstream.script.helpers import initialize_solver

__all__: list[str] = []

_ACTION_SCRIPT = "action.txt"
_ACTION_MARKER = "PYFS_EFFECT_ACTION"

# --- the rotation command, one spelling by build ----------------------------

_spec(
    command="ROTATE_SURFACE",
    build_target=_emit(
        "ROTATE_SURFACE", frame=1, axis="Z", angle=17.5, surfaces=-1, detach_vertices="DISABLE"
    ),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note="rotating every surface about the global frame changes the saved mesh",
)
_spec(
    command="SURFACE_ROTATE",
    build_target=_emit(
        "SURFACE_ROTATE",
        frame=1,
        axis="Z",
        angle=17.5,
        surfaces=-1,
        split_vertices="DISABLE",
        adaptive_mesh="DISABLE",
        detach_normal_to_axis="DISABLE",
    ),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note="rotating every surface about the global frame changes the saved mesh",
)


# --- the unsteady action ---------------------------------------------------------


def _action_unsteady_setup(script: Script, workdir: Path) -> None:
    """Emit the steady setup with the unsteady mode over it, and the action's script."""
    emit_solver_setup(script)
    script.emit("SET_SOLVER_UNSTEADY", time_iterations=3, delta_time=0.0123)
    (workdir / _ACTION_SCRIPT).write_text(f"PRINT {_ACTION_MARKER}\n", encoding="utf-8")


def _register_action(script: Script, workdir: Path) -> None:
    script.emit("SET_NEW_UNSTEADY_SOLVER_ACTION", "SCRIPT", "PYFS_ACTION", workdir / _ACTION_SCRIPT)


def _solve(script: Script, workdir: Path) -> None:
    initialize_solver(script)
    script.emit("START_SOLVER")


def _action_ran(artifacts: ProbeArtifacts) -> bool | None:
    """Judge whether the action's message reached the log after the unsteady solve."""
    final = artifacts.log_final()
    if final is None:
        return None
    return True if printed_line(final, _ACTION_MARKER) else None


_spec(
    command="SET_NEW_UNSTEADY_SOLVER_ACTION",
    build_target=_register_action,
    requires=Requires.SIM,
    prelude=_action_unsteady_setup,
    epilogue=_seq(_solve),
    assert_effect=_action_ran,
    effect_note=(
        "the message the registered script prints appears in the log after the unsteady "
        "solve, so the solver ran the action; silence records unprobed"
    ),
    timeout_s=240.0,
)
