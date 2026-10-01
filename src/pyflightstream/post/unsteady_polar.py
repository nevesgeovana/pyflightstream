"""The unsteady polar: the plots history of each point, time-averaged over its window.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5 of 0.33.0), written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here.

An unsteady simulation's polar comes from its plots and not from its loads
export: that export states the LAST TIME STEP, one instant of a cycle, so a
polar read from it is a polar of an instant. :func:`write_unsteady_polar`
reads the plots tables the stage has already written, so the free-stream
scaling is performed once, and averages each point over the window its row
states, one row per point, under ``polars/`` (:func:`unsteady_polar_file_name`).
Its axis coefficients (:data:`UNSTEADY_AXIS_COLUMNS`) come from the forces the
run plotted in the global frame (:func:`global_frame_plot_groups`); the
row's setup, the equations and the names dictionary of the pproc artifact
are carried beside them.

A further time-averaged polar of the backlog (an extrapolated or a trimmed
unsteady polar) joins this module beside the writer it extends.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream._tokens import POLAR_ID_COLUMN
from pyflightstream.cases import (
    AXES_PLOT_COMPONENTS,
    AXES_PLOT_GROUP,
    global_frame_plot_declarations,
)
from pyflightstream.post._rotor_plan import _emitted_by_another, _plot_name_can_emit
from pyflightstream.post._stage import (
    _MOMENT_POINT_COLUMNS,
    _PLOTS_CLOCK_COLUMNS,
    POLARS_DIR,
    _judge_average,
    _names_location,
)
from pyflightstream.post._tables import (
    COEFFICIENT_COLUMNS,
    CONTEXT_COLUMNS,
    ProductError,
    ReferenceValues,
    context_row,
    plots_table_series,
    renamed_columns,
    write_csv_table,
)
from pyflightstream.post.axes import polar_axis_coefficients
from pyflightstream.post.equations import apply_equations
from pyflightstream.post.unsteady import blade_passage_average
from pyflightstream.results import FrozenSolve

if TYPE_CHECKING:
    pass

__all__ = [
    "UNSTEADY_AXIS_COLUMNS",
    "global_frame_plot_groups",
    "unsteady_polar_file_name",
    "write_unsteady_polar",
]


#: What opens a row that is an AVERAGE: the window it was taken over, in the three
#: columns the reductions use.
_WINDOW_COLUMNS: tuple[str, ...] = ("FIRST_STEP", "LAST_STEP", "STEPS")


def unsteady_polar_file_name(sim_id: str | int, *, name: str) -> str:
    """Return the file name of one unsteady simulation's POLAR, which is per SIMULATION.

    Item 17. It carries no GROUP, and that is the whole difference from
    :func:`swept_polar_file_name`: the steady polar is one table per pproc group
    because its source, the loads export, states loads PER FAMILY. This one's
    source is the plots history, whose columns are whatever the run defined as
    plots, so there is one table per simulation and one row per point.
    """
    # NOT `group_token`, which is the GROUP rule: it prefixes a bare number with
    # `g` so a named group can never be told from the numbered era's suffix. A
    # simulation id is not a group and carries no such history, and prefixing it
    # would rename every file of every existing workspace.
    # `P<sim>_<name>_uns_avg.csv` SINCE 0.24.0. Every file under
    # `post/` comes from a sweep, so a sweep token in the middle of the name told a
    # reader nothing; `uns_avg` says what the file IS, the average of the unsteady
    # history, and the `P` is the prefix every per-point product already carries.
    # It was `<sim>_<name>_unsteady.csv`.
    return f"P{sim_id}_{name}_uns_avg.csv"


def write_unsteady_polar(
    path: str | Path,
    *,
    points: Sequence[object],
    plots: Mapping[str, Path],
    window: tuple[int, int],
    conditions: Sequence[Mapping[str, object]],
    reference: ReferenceValues | None,
    left_out: list[str] | None = None,
    windows: Mapping[str, tuple[int, int]] | None = None,
    setup: Mapping[str, Mapping[str, object]] | None = None,
    notes: list[str] | None = None,
    axes_groups: Sequence[str] | None = None,
    names: Mapping[str, str] | None = None,
    name_notes: list[str] | None = None,
    equations: Mapping[str, object] | None = None,
    equation_order: Sequence[str] | None = None,
    equation_notes: list[str] | None = None,
    frozen: Mapping[str, FrozenSolve] | None = None,
    contributor_path: Callable[[Sequence[str]], Path] | None = None,
    pol: str | int | None = None,
) -> Path | None:
    """Write the POLAR of one unsteady simulation from the PLOTS history (item 17).

    ``pol`` is the simulation's polar, the matrix row's POL, the FIRST column of
    every row since 0.27.0 (G16); `NA` where the caller states none. The super
    content's own `POL` cell is that same polar and is not written a second time.

    THE PPROC'S ``[equations]`` ARE EVALUATED HERE (0.24.0), into columns named
    ``<NAME>_<alias>`` that follow the axis block and precede the super content.
    An expression reads the columns THAT ROW already holds, the window, the
    condition block, the moment point, the averaged plots, the axis coefficients
    and whatever of the super content is a number; how a symbol finds its column
    is :func:`pyflightstream.post.equations.resolve_symbol`. ``equation_order`` is
    :meth:`pyflightstream.cases.PprocSpec.equation_order`. A symbol that is no
    equation and no column refuses the BLOCK, whole, and ``equation_notes``
    receives the refusal; the polar is written without it, never with a column
    of `NA`.

    THE NATIVE COEFFICIENT EXPORT IS NOT THE SOURCE: it states the LAST TIME
    STEP, which on an oscillating rotor is one instant of a cycle. The unsteady
    polar always comes from the unsteady plots export, and carries the time
    average as well.

    THE COLUMNS ARE THE EXPORT'S OWN NAMES, and this is the decision that made
    the item buildable: the table is detached from the steady polar's names and
    writes each variable under the name the unsteady plots export gave it. So
    this table does NOT carry the steady polar's twenty-four fixed coefficients;
    it carries the plots the run defined, under the names the export prints them.

    Nothing in this package knows which plot label carries which coefficient, and
    a label invented here would not fail loudly -- it would write `NA` down a
    whole column. Taking the names from the file removes that possibility
    entirely rather than guarding against it.

    THE WINDOW IS THE ROW'S, the one `last_revs_avg` or `last_iters_avg` states,
    and it is the same window `per_blade` and the time average use (item 16).

    THE FILE SAYS IT IS AN AVERAGE, AND OVER WHAT (0.24.0). Each row opens with
    `FIRST_STEP, LAST_STEP, STEPS`, the three columns the reductions beside it
    already use; the window used to be in `products.json` alone. The moment point
    follows the reference lengths, because the plots carry `MX_/MY_/MZ_` columns
    and a moment states nothing without the point it is about.

    ``setup`` is the SUPER CONTENT of each point by name: what the polar does NOT
    have, the matrix cells, the record's scalars, each rotor's speed, the solver
    flags. It is ADDED to this table rather than written as a second file; a key
    already stated by an earlier block is not repeated, and a point that lacks a
    key reads `NA` under it.

    ``windows`` gives a point ITS OWN window by name where the points of one row
    do not share a clock; a point it does not name takes ``window``.
    ``frozen`` carries native-log freeze evidence by point name. An affected
    averaging window is left out with its reason, including on a recorded success.

    THE AXIS COEFFICIENTS FOLLOW THE PLOTS (0.24.0), from the plot variables of the
    GLOBAL MRP frame: the six components ``FX .. MZ`` of each plot group
    ``axes_groups`` names, which the caller reads off the pproc artifact (a plot's
    column states its group's NAME and never its frame, so the frame cannot be
    read here), in Newtons and Newton metres, averaged over the window like every
    other column, made coefficients by the row's own ``RHO``, ``VINF``, ``SREF``
    and ``CREF`` and turned by the chain the steady polar uses. Never a rotor's
    own frame, whose axes are not the geometry's. The columns are the steady
    polar's eighteen names, each suffixed with its plot group's whole name
    (``CLW_MRP_TOTAL``), one group or several.
    Where the block cannot be written, no MRP group with the six or a row stating
    no density, it is NOT written as a column of `NA`: ``notes`` receives the
    reason.

    ONE ROW PER POINT, in the order given. A point whose plots export is missing
    or unreadable is LEFT OUT rather than written as a row of `NA`: the sweep is
    a table of what ran, and an absent point is absent.

    Returns None when no point yields a row, which is an ordinary campaign -- an
    unsteady simulation whose points exported no plots -- and never a refusal
    that would cost the simulation its other products.

    ``contributor_path``, when supplied, chooses the destination from the names
    of the points that actually yield rows, before the table is written.
    """
    path = Path(path)
    columns: list[str] = []
    rows: list[
        tuple[Mapping[str, object], dict[str, float], tuple[int, int], dict[str, object]]
    ] = []
    # WHY EACH ABSENT POINT IS ABSENT, collected rather than discarded. A sweep
    # dropping rows in silence hands a reader a table shorter than the matrix
    # with nothing saying which points went or why -- which is a blank cell one
    # level up, and `_tokens.py` argues against exactly that: indistinguishable
    # from a value that went missing, from a column that never applied, and from
    # a writer that crashed halfway. The QA lens of the closing round found the
    # round had fixed the two readers disagreeing about the RULE and left them
    # disagreeing about the REPORT.
    left_out = [] if left_out is None else left_out
    contributors: list[str] = []
    for point, condition in zip(points, conditions, strict=True):
        name = str(getattr(point, "name", ""))
        name_of_point = name  # `name` is reused for the plot columns below
        source = plots.get(name)
        if source is None or not source.is_file():
            left_out.append(f"{name}: no plots table")
            continue
        point_window = (windows or {}).get(name, window)
        try:
            printed_names, series = plots_table_series(source)
            # A PARTIAL COVER IS NOT A COVER, and this dropped only the point
            # whose history missed the window ENTIRELY. `blade_passage_average`
            # refuses when NO frame falls inside, so a point that stopped
            # part-way through averaged the part and returned normally -- and
            # its row sat beside a full one, in one file, with no frame count
            # and a manifest claiming the whole window. A reader comparing the
            # two is comparing a ten-step mean with a four-step one.
            #
            # THE SIBLING READER OF THIS SAME FILE ALREADY REFUSES IT:
            # `write_reduction_table` says "a shorter history averaged as a
            # whole one would be an average of a run that did not finish
            # writing". Two readers of one plots table with opposite rules, and
            # the PUBLISHED one was the permissive one. The QA lens found it.
            steps = np.asarray(series.steps, dtype=int)
            if (
                not len(steps)
                or int(steps[0]) > point_window[0]
                or int(steps[-1]) < point_window[1]
            ):
                held = f"steps {int(steps[0])} to {int(steps[-1])}" if len(steps) else "no step"
                left_out.append(
                    f"{name}: the row states steps {point_window[0]} to {point_window[1]} and the "
                    f"history holds {held}"
                )
                continue
            read_steps: set[int] = set()
            averaged = blade_passage_average(series, window=point_window, read_steps=read_steps)
        except (PyflightstreamError, ValueError) as error:
            # A history that does not cover the row's window is a run that
            # stopped early, not a fault: it costs this point its row.
            left_out.append(f"{name}: its plots table could not be read: {error}")
            continue
        refusal = _judge_average(
            (frozen or {}).get(name), read_steps, point=name, product=str(path)
        )
        if refusal is not None:
            left_out.append(f"{name}: {refusal}")
            continue
        values: dict[str, float] = {}
        for name in printed_names:
            # THE CLOCK IS NOT A COEFFICIENT, and averaging it publishes a number
            # with no physical meaning under the same contract as `CL`. Over
            # steps 5 to 8 the mean of the step column is 6.5, which is not a
            # measurement of anything. `plots_table_series` carries the step
            # column as a FIELD as well as using it as the axis -- its own
            # docstring says so -- and a writer that takes "every name it
            # returns" therefore takes the clock with them.
            #
            # The V&V lens of the release round found this. My test asserted
            # `"CL" in columns` and the ABSENCE of the steady polar's names; it
            # never asserted the column SET, so an extra column was invisible to
            # it. Measure the carrier, not the mention.
            if name in _PLOTS_CLOCK_COLUMNS:
                continue
            column = averaged.fields.get(name)
            if column is not None and len(column):
                values[name] = float(column[0])
        if not values:
            left_out.append(f"{name_of_point}: its plots table states no numeric plot column")
            continue
        for name in values:
            if name not in columns:
                columns.append(name)
        rows.append((condition, values, point_window, dict((setup or {}).get(name_of_point, {}))))
        contributors.append(name_of_point)
    if not rows:
        return None
    if contributor_path is not None:
        path = contributor_path(contributors)
    plot_columns = list(columns)
    axis_columns = _the_axes_of_the_unsteady_rows(rows, reference, notes, axes_groups or ())
    # ITEM 5 REACHES THIS PRODUCT TOO: a coefficient states nothing without the
    # condition it was taken at and the lengths it was normalised by.
    lengths = None if reference is None else reference.as_lengths()
    moment = None if reference is None else reference.as_moment_point()
    columns = [*columns, *axis_columns]
    stated = {
        POLAR_ID_COLUMN,
        *_WINDOW_COLUMNS,
        *CONTEXT_COLUMNS,
        *_MOMENT_POINT_COLUMNS,
        *columns,
    }
    extra: list[str] = []
    for _condition, _values, _window, content in rows:
        for key in content:
            if key not in stated and key not in extra:
                extra.append(key)
    header = (
        POLAR_ID_COLUMN,
        *_WINDOW_COLUMNS,
        *CONTEXT_COLUMNS,
        *_MOMENT_POINT_COLUMNS,
        *columns,
        *extra,
    )
    table = [
        (
            pol,
            span[0],
            span[1],
            span[1] - span[0] + 1,
            *context_row(condition, lengths),
            *context_row(moment, None, columns=_MOMENT_POINT_COLUMNS),
            *(values.get(name) for name in columns),
            *(content.get(key) for key in extra),
        )
        for condition, values, span, content in rows
    ]
    derived_columns: list[str] = []
    derived: list[dict[str, float | None]] = [{} for _row in table]
    if equations:
        # THE ROW AS THE FILE WILL STATE IT is what an expression reads, so a
        # symbol means the column a reader of the file sees under that name.
        try:
            derived_columns, derived = apply_equations(
                [dict(zip(header, cells, strict=True)) for cells in table],
                equations,
                list(equation_order if equation_order is not None else equations),
                columns=header,
                where=f"{POLARS_DIR}/{path.name}",
                notes=equation_notes,
            )
        except ProductError as refused:
            if equation_notes is None:
                raise
            equation_notes.append(str(refused))
    at = len(header) - len(extra)
    # THE DICTIONARY IS APPLIED LAST, to the heading alone: the axes and the
    # equations above read the names the export prints, and a reader's tool reads
    # the names the pproc gives them.
    final = (*header[:at], *derived_columns, *header[at:])
    try:
        final = renamed_columns(
            final, names, printed=plot_columns, where=_names_location(POLARS_DIR, path)
        )
    except ProductError as refused:
        if name_notes is None:
            raise
        name_notes.append(str(refused))
    return write_csv_table(
        path,
        final,
        [
            (*cells[:at], *(values.get(name) for name in derived_columns), *cells[at:])
            for cells, values in zip(table, derived, strict=True)
        ],
    )


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
    that name is what is looked for; a run made before 0.24.0 has no such columns
    and its polar says so. A template also suppresses that automatic group, but
    its unresolved names cannot supply an axes block; that block is a named skip.
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
#: :func:`pyflightstream.post.axes.polar_axis_coefficients` returns (body,
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
    if reference is None or reference.sref_m2 <= 0.0 or reference.cref_m <= 0.0:
        notes.append("the axis coefficients are not written: no reference area and chord")
        return []
    added: list[str] = []
    for condition, values, _window, _content in rows:
        stated = {str(key).upper(): value for key, value in condition.items()}
        rho, speed = stated.get("RHO"), stated.get("VINF")
        alpha, beta = stated.get("ALPHA"), stated.get("BETA")
        lacking = [
            key
            for key, value in (("RHO", rho), ("VINF", speed), ("ALPHA", alpha), ("BETA", beta))
            if not isinstance(value, int | float) or isinstance(value, bool)
        ]
        if not lacking and not (float(rho) > 0.0 and float(speed) > 0.0):  # type: ignore[arg-type]
            lacking = ["a positive RHO and VINF"]
        if lacking:
            notes.append(
                f"the axis coefficients of steps {_window[0]} to {_window[1]} are not written: "
                f"the row states no {', '.join(lacking)}, and a force in Newtons is no "
                "coefficient without the dynamic pressure it is divided by"
            )
            continue
        unit = 0.5 * float(rho) * float(speed) ** 2 * reference.sref_m2  # type: ignore[arg-type]
        for group in groups:
            six = [values.get(f"{part}_{group}") for part in _SIX_COMPONENTS]
            if any(value is None for value in six):
                continue
            turned = polar_axis_coefficients(
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
            for column in UNSTEADY_AXIS_COLUMNS:
                at = _STEADY_AXIS_COLUMNS.index(column)
                name = f"{column}_{group}"
                values[name] = turned[at]
                if name not in added:
                    added.append(name)
    return added
