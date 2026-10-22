"""The mesh-rotation command and the boundary selection of ``rotate_surfaces``."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import CommandArgumentError, Script, ScriptReferenceError
from pyflightstream.script._arg_checks import _is_all
from pyflightstream.script._settings import _reject_empty_selection, _toggle

#: The mesh rotation, in the two names it goes by, newest first.
#:
#: THE ORDER CARRIES NOTHING TODAY, and saying so is the correction the
#: adversarial pass forced: this comment claimed the order was the search
#: order, and reversing the tuple broke no test, because EXACTLY ONE of
#: the two resolves on every registered build. That is the load-bearing
#: property, and it is what
#: `test_exactly_one_rotation_command_resolves_on_every_registered_build`
#: measures. The order would start mattering the day a build documented
#: both, which is why the loop takes the first that resolves rather than
#: asserting there is only one.
#:
#: They are NOT one command renamed, which the database records as its
#: own reading: SURFACE_ROTATE is a keyword block of eight arguments and
#: ROTATE_SURFACE is a payload-lines command of six, with no equivalent
#: of SPLIT_VERTICES or ADAPTIVE_MESH.
ROTATION_COMMANDS: tuple[str, ...] = ("ROTATE_SURFACE", "SURFACE_ROTATE")

#: Trailing index of a boundary label, which is what a component name is
#: the label without. ``Blade_1``, ``Blade 2`` and ``Blade3`` all carry
#: the component ``blade``.
_COMPONENT_INDEX = re.compile(r"[\s_.-]*\d+$")


def _component_of(label: str) -> str:
    """Return the component a boundary label belongs to, case-folded."""
    return _COMPONENT_INDEX.sub("", label).casefold()


def _rotation_command(script: Script) -> str:
    """Return the mesh-rotation command this script's build documents."""
    for name in ROTATION_COMMANDS:
        try:
            script._view[name]
        except CommandNotInVersionError:
            continue
        return name
    raise CommandArgumentError(
        f"rotate_surfaces: FlightStream {script.version.canonical} documents neither "
        f"{ROTATION_COMMANDS[0]} nor {ROTATION_COMMANDS[1]}, so this build has no "
        "recorded way to rotate an existing mesh. The capability is one command on "
        "every build up to 26.121 and the other from 26.122; a build carrying neither "
        "has no row for either command in this database rather than no capability"
    )


def _surface_selection(
    script: Script, component: str | None, boundaries: Sequence[int | str] | str
) -> list[int | str]:
    """Return the boundary indices ``rotate_surfaces`` rotates (empty for all of them)."""
    if component is not None:
        declared = script.entities.labels("boundaries")
        wanted = component.casefold()
        selection: list[int | str] = [
            index for label, index in sorted(declared.items()) if _component_of(label) == wanted
        ]
        if not selection:
            known = ", ".join(f"{label!r}" for label in sorted(declared)) or "none"
            raise ScriptReferenceError(
                f"rotate_surfaces: component {component!r} matches no declared boundary "
                f"label; declared labels are {known}. A component is a label with its "
                "trailing index removed, so 'Blade' selects Blade_1 and Blade2 alike. "
                "Declare the geometry's boundary names with declare_existing("
                "boundaries={...}) before rotating by component"
            )
    elif _is_all(boundaries):
        selection = []
    else:
        selection = list(boundaries)
        _reject_empty_selection("rotate_surfaces", "boundaries", list(selection))
    return selection


def _refuse_options_without_equivalent(
    script: Script, command: str, split_on: bool, adaptive_on: bool
) -> None:
    """Refuse the SURFACE_ROTATE-only options on a build that documents ROTATE_SURFACE."""
    if command == "ROTATE_SURFACE":
        for argument, requested in (
            ("split_vertices", split_on),
            ("adaptive_mesh", adaptive_on),
        ):
            if requested:
                raise CommandArgumentError(
                    f"rotate_surfaces: {argument} was asked for, and "
                    f"{command}, which is what FlightStream "
                    f"{script.version.canonical} documents, has no equivalent of it. "
                    "The option belongs to SURFACE_ROTATE, which that build stops "
                    "printing. Emitting the rotation without it would give you a "
                    "different mesh under an argument the call still carried, so it is "
                    "refused instead. Run this rotation on a build up to 26.121, or "
                    "drop the option deliberately"
                )


def _rotation_emission(
    script: Script,
    command: str,
    *,
    frame: int | str,
    axis: str,
    angle_deg: float,
    selection: list[int | str],
    whole: bool,
    toggles: tuple[bool, bool, bool],
    after_initialization: bool,
) -> None:
    """Emit the rotation command with the arguments its layout takes."""
    detach_on, split_on, adaptive_on = toggles
    count = -1 if whole else len(selection)
    arguments: dict[str, Any] = {
        "frame": frame,
        "axis": axis,
        "angle": angle_deg,
        "surfaces": count,
    }
    if count != -1:
        arguments["surface_indices"] = selection
    if command == "ROTATE_SURFACE":
        arguments["detach_vertices"] = _toggle(detach_on)
    else:
        arguments["split_vertices"] = _toggle(split_on)
        arguments["adaptive_mesh"] = _toggle(adaptive_on)
        arguments["detach_normal_to_axis"] = _toggle(detach_on)
    if after_initialization:
        script.emit_after_initialization(command, **arguments)
    else:
        script.emit(command, **arguments)
