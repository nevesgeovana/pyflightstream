"""Setup operations on a point's surfaces: removing surfaces, and the wake option it emits.

Pipeline role: the cases row, where a row's solver commands are emitted.
It emits the removal of the surfaces a setup names, with the renumbering
of the surface inventory that removal causes, and the slipstream wake
stabilization a setup states.

Two setup keys reach the solver here, each through a short hook in
:mod:`pyflightstream.cases.workflows`:

``delete_surfaces``
    Boundaries named by NAME, alias or family, never by index. Each is
    removed with ``DELETE_SURFACES``. The solver renumbers the surfaces
    after a deleted one, so the inventory the script holds is rewritten
    to the surviving names at their new indices, and every later command
    and the run record's inventory read the new numbering. Licensed
    probe round 1 of 0.32.0 on 26.124 (probe ``D1_delete_surfaces``):
    ``DELETE_SURFACES 3`` on a four-surface mesh (Body, Base, Blade1,
    Blade2) left Body, Base, Blade2, and only Blade2 moved, to index 3.
    A family is removed from its last member so no index shifts under
    the next command.

``slipstream_wake_stabilization``
    A toggle emitted as ``SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION`` for
    each rotor motion the row creates. The same round (probe
    ``W1_wake_stab_disable``) showed DISABLE stored after an ENABLE, in
    the form ``1 DISABLE 1``.

A key that reaches nothing is refused, never dropped: a setup naming
surfaces on a row that opens no geometry, or a wake stabilization on a
row that creates no rotor motion, is a silent no-op otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyflightstream.cases import CampaignConfigError, select_group_members

if TYPE_CHECKING:
    from pyflightstream.cases import SimCase
    from pyflightstream.script import Script

#: The setup key naming the surfaces to remove.
DELETE_SURFACES_KEY = "delete_surfaces"

#: The setup key stating the slipstream wake stabilization.
WAKE_STABILIZATION_KEY = "slipstream_wake_stabilization"

_DELETE = "DELETE_SURFACES"
_STABILIZATION = "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"


def emit_setup_surfaces(script: Script, case: SimCase) -> None:
    """Emit the removal of the surfaces the case's setup names, and renumber the inventory.

    Nothing is emitted, and the script is left as it was, when the setup
    states no ``delete_surfaces``.

    Parameters
    ----------
    script : Script
        The script being built for the point, with the geometry opened
        and its boundary inventory declared.
    case : SimCase
        The point's case; ``case.solver.delete_surfaces`` names the
        surfaces and ``case.aliases`` the row's aliases.

    Raises
    ------
    CampaignConfigError
        If the list is empty, the geometry declares no boundary names,
        a name resolves to no surface of the inventory, or the removal
        would leave no surface.
    """
    stated = case.solver.delete_surfaces
    if stated is None:
        return
    inventory = script.boundary_inventory
    labels = script.entities.labels("boundaries")
    if not stated:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {DELETE_SURFACES_KEY} as an empty list, which names "
            "no surface. Leave the key out to remove nothing, or list the names to remove."
        )
    if not inventory or not labels:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {DELETE_SURFACES_KEY}, and the geometry declares no "
            "boundary names to resolve them against. Open a saved simulation whose mesh "
            "block carries the names, or state them in a boundaries.toml sidecar."
        )
    ordered = [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]
    doomed: set[int] = set()
    for token in stated:
        found = select_group_members([token], ordered, case.aliases)
        if not found:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {DELETE_SURFACES_KEY} with {token!r}, and the "
                f"inventory declares no surface of that name, alias or family; it declares "
                f"{', '.join(repr(name) for name in ordered)}. Write one of those, or a "
                "family name (the label without its trailing number)."
            )
        doomed.update(labels[name] for name in found)
    if len(doomed) >= len(inventory):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {DELETE_SURFACES_KEY} with {', '.join(stated)}, "
            f"which removes every surface of the {len(inventory)} the geometry carries. A "
            "mesh with no surface cannot be solved; keep at least one."
        )
    for index in sorted(doomed, reverse=True):
        script.emit(_DELETE, index)
    survivors = tuple(name for position, name in enumerate(inventory, 1) if position not in doomed)
    script.boundary_inventory = survivors
    renumbered = {
        name: new_index
        for new_index, name in enumerate(survivors, 1)
        if name in labels and survivors.count(name) == 1
    }
    script.entities.renumber_boundaries(renumbered, len(survivors))


def emit_wake_stabilization(
    script: Script, case: SimCase, motion_id: int, blades: int | None
) -> None:
    """Emit the slipstream wake stabilization the setup states, for one rotor motion.

    Parameters
    ----------
    script : Script
        The script being built, with the motion already created.
    case : SimCase
        The point's case; ``case.solver.slipstream_wake_stabilization``
        is the toggle, or None to emit nothing.
    motion_id : int
        The rotor motion the setting applies to.
    blades : int, optional
        The row's blade count. An ENABLE needs it, because the solver
        reads the count per propeller; a DISABLE reads none, so one is
        written when the row states none (the form probe ``W1`` ran).

    Raises
    ------
    CampaignConfigError
        If the setup enables the stabilization, the build's command takes a
        blade count, and the row states none.
    """
    enabled = case.solver.slipstream_wake_stabilization
    if enabled is None:
        return
    takes_count = "num_blades" in {argument.name for argument in script.entry(_STABILIZATION).args}
    if enabled and blades is None and takes_count:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WAKE_STABILIZATION_KEY} as ENABLE, and the solver "
            "reads the blade count per propeller, which the row does not state. Add "
            "'BLADES: <count>' (or the sector's PERIODIC_COPIES) to the row."
        )
    arguments: list[object] = [motion_id, "ENABLE" if enabled else "DISABLE"]
    if takes_count:
        arguments.append(blades if blades is not None else 1)
    script.emit(_STABILIZATION, *arguments)


def refuse_setup_keys_that_reached_nothing(script: Script, case: SimCase) -> None:
    """Refuse a stated surface or wake key the finished script never emitted.

    Called after the workflow's builder, because only then is it known
    whether the row opened a geometry and created a rotor motion.

    Raises
    ------
    CampaignConfigError
        If ``delete_surfaces`` is stated and no removal was emitted, or
        ``slipstream_wake_stabilization`` is stated and no rotor motion
        received it.
    """
    solver = case.solver
    if solver.delete_surfaces is None and solver.slipstream_wake_stabilization is None:
        return
    lines = script.render().splitlines()
    if solver.delete_surfaces is not None and not any(
        line.startswith(_DELETE + " ") for line in lines
    ):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {DELETE_SURFACES_KEY}, and the row opens no "
            "geometry the surfaces could be removed from. Name a geometry in the row, or "
            "remove the key."
        )
    if solver.slipstream_wake_stabilization is not None and not any(
        line.startswith(_STABILIZATION + " ") for line in lines
    ):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WAKE_STABILIZATION_KEY}, and the row creates no "
            "rotor motion for it to apply to. Use it on a rotor row, or remove the key."
        )
