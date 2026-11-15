"""The unsteady polar: the plots history of each point, time-averaged over its window.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5), written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here.

An unsteady simulation's polar comes from its plots and not from its loads
export: that export states the LAST TIME STEP (RPT-133, "vorticity drag list and
the step exports on 26.124", 2026-10-02), one instant of a cycle, so a
polar read from it is a polar of an instant. the retired ``write_unsteady_polar``
reads the plots tables the stage has already written, so the free-stream
scaling is performed once, and averages each point over the window its row
states, one row per point, under ``polars/`` (:func:`_unsteady_polar_file_name`).
Its axis coefficients (:data:`UNSTEADY_AXIS_COLUMNS`) come from the forces the
run plotted in the global frame (:func:`global_frame_plot_groups`); the
row's setup, the equations and the names dictionary of the pproc artifact
are carried beside them.

A further time-averaged polar of the backlog (an extrapolated or a trimmed
unsteady polar) joins this module beside the writer it extends.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from pyflightstream._deprecations import removed_names_hook
from pyflightstream._tokens import MESH_FACES_COLUMN
from pyflightstream.cases import (
    AXES_PLOT_COMPONENTS,
    AXES_PLOT_GROUP,
    global_frame_plot_declarations,
)
from pyflightstream.post._rotor_plan import _emitted_by_another, _plot_name_can_emit
from pyflightstream.post._tables import (
    COEFFICIENT_COLUMNS,
    ReferenceValues,
)
from pyflightstream.post.axes import _polar_axis_coefficients
from pyflightstream.results import REDUCTION_COLUMN, REDUCTION_WINDOW_COLUMN

if TYPE_CHECKING:
    pass

__all__ = [
    "UNSTEADY_AXIS_COLUMNS",
    "global_frame_plot_groups",
]


#: What opens a row that is an AVERAGE: the window it was taken over, in the three
#: columns the reductions use.
_WINDOW_COLUMNS: tuple[str, ...] = ("FIRST_STEP", "LAST_STEP", "STEPS")

#: What closes every row, after the super content (FR-348): the face count of the
#: point's geometry as its inventory states it, ``NA`` where it states none. Last
#: so a reader that takes the columns of 0.33 by position keeps every one of them.
_LAST_COLUMNS: tuple[str, ...] = (MESH_FACES_COLUMN,)

#: What the provenance cells of a row say (FR-32): the row is the package's
#: time average over the window its first columns state. The super content
#: carries the sweep row's cells, which describe the native export, the last
#: time step (``last_step`` over ``last_time_step``); written unchanged here
#: they said an averaged row was an instant.
_AVERAGED_ROW_PROVENANCE: dict[str, str] = {
    REDUCTION_COLUMN: "time_average",
    REDUCTION_WINDOW_COLUMN: "averaging_window",
}


def _averaged(content: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of a point's super content whose provenance cells name the average."""
    # ALWAYS BOTH CELLS, also where the caller passed no super content: the file promises a
    # `time_average` over an `averaging_window`, and a polar written without `setup` said nothing.
    return {**content, **_AVERAGED_ROW_PROVENANCE}


def _unsteady_polar_file_name(sim_id: str | int, *, name: str) -> str:
    """Return the file name of one unsteady simulation's POLAR, which is per SIMULATION.

    Item 17. It carries no GROUP, and that is the whole difference from
    the retired ``swept_polar_file_name``: the steady polar is one table per pproc group
    because its source, the loads export, states loads PER FAMILY. This one's
    source is the plots history, whose columns are whatever the run defined as
    plots, so there is one table per simulation and one row per point.

    Parameters
    ----------
    sim_id : str or int
        The simulation's identifier, written as it stands after the ``P``.
    name : str
        The name the file carries between the simulation and ``uns_avg``.

    Returns
    -------
    str
        The file name, ``P<sim_id>_<name>_uns_avg.csv``, without a directory.
    """
    # A simulation id is not a group token; do not add the numbered-group
    # prefix. P<sim>_<name>_uns_avg.csv identifies the simulation and names
    # the product as an unsteady-history average.
    return f"P{sim_id}_{name}_uns_avg.csv"


def _dependency_order(equations: Mapping[str, object]) -> list[str]:
    """Return the equations ordered so each follows every equation it names.

    The order :meth:`pyflightstream.cases.PprocSpec.equation_order` gives, derived
    here from the equations alone when the caller states none; ties keep
    declaration order. A circular set is returned in declaration order, which
    the evaluation then refuses by name.
    """
    names = list(equations)
    depends = {
        name: [
            token
            for token in getattr(equations[name], "symbols", lambda: [])()
            if token in equations
        ]
        for name in names
    }
    order: list[str] = []
    while len(order) < len(names):
        ready = [
            name
            for name in names
            if name not in order and all(dep in order for dep in depends[name])
        ]
        if not ready:
            return names
        order.extend(ready)
    return order


def global_frame_plot_groups(
    pproc: object,
    *,
    inventory: Sequence[str] = (),
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, ...]:
    """Return the names of the plot groups whose six components are in the GLOBAL frame.

    Read off the pproc artifact, which is the only place a plot's frame is stated.
    A group counts when its frame is `MRP` and the artifact plots all of
    ``FX, FY, FZ, MX, MY, MZ``. Where the artifact declares none, the run adds one of
    its own over every boundary (:data:`pyflightstream.cases.AXES_PLOT_GROUP`), so
    that name is what is looked for; a run without that group has no such columns
    and its polar says so. A template also suppresses that automatic group, but
    its unresolved names cannot supply an axes block; that block is a named skip.

    Parameters
    ----------
    pproc : object
        The pproc artifact, read for its ``plots`` declarations and its
        ``is_blade`` test.
    inventory : sequence of str, optional
        The surface names of the run, used to decide which groups the
        automatic plot can emit.
    aliases : mapping of str to sequence of str, optional
        The family aliases of the run.

    Returns
    -------
    tuple of str
        The names of the plot groups whose six components are in the global
        frame; empty when the artifact's own groups shadow the automatic one.
    """
    plots = getattr(pproc, "plots", None)
    parameters = set(getattr(plots, "parameters", ()) or ())
    every_group = getattr(plots, "groups", ()) or ()
    global_groups = global_frame_plot_declarations(pproc)
    declared = [
        str(group.name)
        for group in global_groups
        if "{" not in str(group.name)
        # A NAME ANOTHER DECLARATION COULD EMIT IS AMBIGUOUS and is never read as
        # global: its history may be that other group's, in another frame.
        and not _emitted_by_another(str(group.name), every_group, group, outside_frame="MRP")
    ]
    if global_groups:
        # Templates also suppress the automatic group at run. Without resolved
        # emitted names, skip their axes rather than claim an automatic source.
        return tuple(declared)
    # Automatic plots never overwrite an already emitted name. A group with
    # this name in another frame therefore cannot supply global components.
    if parameters.intersection(_SIX_COMPONENTS) and any(
        _plot_name_can_emit(
            str(group.name),
            AXES_PLOT_GROUP,
            group.families,
            inventory=inventory,
            is_blade=getattr(pproc, "is_blade", lambda _name: False),
            aliases=aliases,
            frame=str(getattr(group, "frame", "")).strip().upper(),
        )
        and str(getattr(group, "frame", "")).strip().upper() != "MRP"
        for group in (getattr(plots, "groups", ()) or ())
    ):
        return ()
    return (AXES_PLOT_GROUP,)


#: The eighteen axis columns of an unsteady polar, wind axes first as the draft of
#: the product lists them, and where each sits in what
#: :func:`pyflightstream.post.axes._polar_axis_coefficients` returns (body,
#: stability, wind).
#: They ARE the steady polar's eighteen names, read off its one tuple, `25`
#: included: one construction about one moment point has one name in `polars/`.
_STEADY_AXIS_COLUMNS: tuple[str, ...] = COEFFICIENT_COLUMNS[4:22]


UNSTEADY_AXIS_COLUMNS: tuple[str, ...] = (
    *_STEADY_AXIS_COLUMNS[12:18],
    *_STEADY_AXIS_COLUMNS[6:12],
    *_STEADY_AXIS_COLUMNS[0:6],
)


_SIX_COMPONENTS = AXES_PLOT_COMPONENTS


def _store_turned(
    values: dict[str, float],
    group: str,
    turned: Sequence[float],
    stored: list[tuple[dict[str, float], str]],
    added: list[str],
) -> None:
    """Write a group's turned axis coefficients into a row, noting each column once."""
    for column in UNSTEADY_AXIS_COLUMNS:
        name = f"{column}_{group}"
        values[name] = turned[_STEADY_AXIS_COLUMNS.index(column)]
        stored.append((values, name))
        if name not in added:
            added.append(name)


def _positive_reference(reference: ReferenceValues) -> bool:
    """Whether the reference area, chord and span are all positive."""
    return reference.sref_m2 > 0.0 and reference.cref_m > 0.0 and reference.bref_m > 0.0


def _lacking_condition(rho: object, speed: object, alpha: object, beta: object) -> list[str]:
    """Return what a row's condition lacks to divide a force by its dynamic pressure."""
    lacking = [
        key
        for key, value in (("RHO", rho), ("VINF", speed), ("ALPHA", alpha), ("BETA", beta))
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value)
    ]
    if not lacking and not (float(rho) > 0.0 and float(speed) > 0.0):  # type: ignore[arg-type]
        lacking = ["a positive RHO and VINF"]
    return lacking


def _the_axes_of_the_unsteady_rows(
    rows: Sequence[
        tuple[Mapping[str, object], dict[str, float], tuple[int, int], dict[str, object]]
    ],
    reference: ReferenceValues | None,
    notes: list[str] | None,
    declared: Sequence[str],
) -> list[str]:
    """Add the axis coefficients to each row's values, and return the columns added.

    The values of a row are the window's average of every plotted column, so the
    six components are already averaged; what is done here is the division by the
    dynamic pressure of THAT row and the turn.
    """
    notes = [] if notes is None else notes
    groups = [
        group
        for group in dict.fromkeys(str(name) for name in declared)
        if any(
            all(f"{part}_{group}" in values for part in _SIX_COMPONENTS)
            for _condition, values, _window, _content in rows
        )
    ]
    if not groups:
        notes.append(
            "the axis coefficients are not written: the plots hold FX, FY, FZ, MX, MY and MZ "
            f"of no plot group in the global MRP frame (looked for: {list(declared) or 'none'}; "
            "a rotor's own frame is not the geometry's "
            'axes). Declare a [[plots.groups]] entry with frame = "MRP" and those six '
            "parameters; it takes a new run, the script defines what the solver plots."
        )
        return []
    # The span too: the roll and yaw moments are made dimensionless by it, and a
    # zero BREF was a bare ZeroDivisionError out of the whole polar.
    if reference is None or not _positive_reference(reference):
        notes.append(
            "the axis coefficients are not written: no positive reference area, chord "
            "and span (the roll and yaw moments need a span)"
        )
        return []
    added: list[str] = []
    stored: list[tuple[dict[str, float], str]] = []
    for condition, values, _window, _content in rows:
        stated = {str(key).upper(): value for key, value in condition.items()}
        rho, speed = stated.get("RHO"), stated.get("VINF")
        alpha, beta = stated.get("ALPHA"), stated.get("BETA")
        lacking = _lacking_condition(rho, speed, alpha, beta)
        if lacking:
            notes.append(
                f"the axis coefficients of steps {_window[0]} to {_window[1]} are not written: "
                f"the row states no {', '.join(lacking)}, and a force in Newtons is no "
                "coefficient without the dynamic pressure it is divided by"
            )
            continue
        try:
            unit = 0.5 * float(rho) * float(speed) ** 2 * reference.sref_m2  # type: ignore[arg-type]
            for group in groups:
                six = [values.get(f"{part}_{group}") for part in _SIX_COMPONENTS]
                if any(value is None for value in six):
                    continue
                turned = _polar_axis_coefficients(
                    [float(value) / unit for value in six[:3]],  # type: ignore[arg-type]
                    [float(value) / (unit * reference.cref_m) for value in six[3:]],  # type: ignore[arg-type]
                    float(alpha),  # type: ignore[arg-type]
                    float(beta),  # type: ignore[arg-type]
                    cref_m=reference.cref_m,
                    bref_m=reference.bref_m,
                )
                # ALWAYS the group's whole name, as every plotted column of this file
                # carries it (`CL_MRP_TOTAL`, so `CLW_MRP_TOTAL`): a column that changed
                # its name when the pproc gained a second group broke every reader keyed
                # to it, and a shortened name let two groups write one column.
                _store_turned(values, group, turned, stored, added)
        except (OverflowError, ZeroDivisionError) as error:
            # AN OVERFLOW IN THE NORMALISATION OMITS THE BLOCK, as every other reason
            # does: it aborted the whole polar, and the point lost its row.
            for stored_values, stored_name in stored:
                del stored_values[stored_name]
            notes.append(
                f"the axis coefficients are not written: the normalisation of steps "
                f"{_window[0]} to {_window[1]} failed ({error}), so no row carries the block"
            )
            return []
    return added


# The names retired with their products answer by name (FR-457).
__getattr__ = removed_names_hook(__name__)
