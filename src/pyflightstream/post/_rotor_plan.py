"""Where each rotor table's rows come from: the plan of one simulation's rotor tables.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0), between the simulation stage of :mod:`pyflightstream.post._sim` and
the writer of :mod:`pyflightstream.post.rotor_table`. For each rotor the
reference the matrix row names declares, :func:`_rotor_tables` plans one
table: its destination, the rows of the points that can supply one, and the
points that cannot, each with its reason.

An unsteady row reads the rotor's history from a plot group of the plots
export, time-averaged over the row's window; :func:`rotor_plot_source` names
that group (the one the solver adds itself, or one the pproc declares over
exactly the rotor's families in the rotor's own frame), and the unsteady
polar's axes ask the same question of a frame through
:func:`_plot_name_can_emit` and :func:`_emitted_by_another`. A steady row and
a quasi-steady wheel read their loads export.
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import (
    AXES_PLOT_COMPONENTS,
    ROTOR_PLOT_GROUP_PREFIX,
    select_families,
    select_group_members,
)
from pyflightstream.cases.qsteady import QsteadyRecord, QsteadyRecordError, read_qsteady_record
from pyflightstream.cases.workflows import FLAT_RPM_KEY, ORIGINAL_FRAME_SUFFIX, QSTEADY_ROTOR
from pyflightstream.post import qsteady as _qsteady
from pyflightstream.post._condition import (
    _free_stream_and_sound,
    clock_rotor_facts,
    point_condition,
)
from pyflightstream.post._stage import POLARS_DIR, _a_name_a_file_may_carry, _judge_average
from pyflightstream.post._tables import ROTOR_TABLE_SUFFIX, ReferenceValues, plots_table_series
from pyflightstream.post.polar import PolarPoint
from pyflightstream.post.unsteady import blade_passage_average
from pyflightstream.results import FrozenSolve
from pyflightstream.workspace.inputs import resolve_reference
from pyflightstream.workspace.naming import sweep_file_stem

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


# `unsteady_window` WAS HERE AND IS DELETED, with item 16 landing through
# `cases.workflows._averaging_window` and `_stated_window` below instead.
#
# IT NEVER HAD A CALLER. It was written to give a caller to a window function of
# `post.unsteady` that had none (deleted in 0.24.0, CR-05: its rule discarded the
# FIRST revolutions, the opposite of the shipped one) and reproduced that defect
# exactly one level up; a closing round caught
# the false docstring, a change-log entry was written saying it was NOT WIRED,
# and then item 16 was built somewhere else entirely -- leaving a public-looking
# function nothing reached and two contradictory entries in one release's Added
# list. The architect lens of the release round found both.
#
# THE RULE IT HELD IS NOT LOST. The window is still the LAST revolutions or
# iterations the row states and never the whole history; the derivation is
# `cases.windows.averaging_span`, which `_matrix_window` below and the plan both
# call, so a stage reaches it.


def _plot_name_can_emit(
    template: str,
    name: str,
    families: str | Sequence[str],
    *,
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    aliases: Mapping[str, Sequence[str]] | None = None,
    frame: str = "",
) -> bool:
    """Whether a declared plot name CAN occupy an automatic group's name.

    CONSERVATIVE BY DECISION (release 0.24.0). The label a ``{family}`` group puts
    in its name is chosen by the script builder from the run's case and frames
    (`cases.workflows.pproc_emissions`), which the post stage does not hold. Three
    attempts to re-derive it here each let a rotor-frame or custom-frame history
    pass as global loads. So any template that COULD produce the automatic name
    counts as producing it: a history that might be the wrong one is never read,
    and its table is skipped with the reason. New runs record the emitted names,
    frames and families; rotor tables read that record directly. This matcher
    remains the conservative fallback for older records.
    """
    del families, inventory, is_blade, aliases, frame
    # The builder appends the original frame's suffix to a group plotted in a
    # retained ORIGINAL frame, so a declaration emits its name AND that name
    # suffixed; both can occupy an automatic name.
    # EVERY replacement field is a wildcard, whatever its format spec: the builder
    # applies `str.format`, so `{family}`, `{family:.0}` (empty) or `{family!r}`
    # can each put any text, or none, where they stand.
    # Parsed with Python's own format parser, which handles nested specs; each
    # top-level field becomes a wildcard. The pproc refuses anything but a bare
    # `{family}` when it is read, so this is the second line of defence.
    pattern = "".join(
        re.escape(literal) + (".*" if field is not None else "")
        for literal, field, _spec, _conversion in string.Formatter().parse(template)
    )
    suffix = re.escape(ORIGINAL_FRAME_SUFFIX)
    # Case-insensitive: whether the solver keeps a plot name's case is not measured,
    # so two names equal but for case are taken as able to collide.
    return re.fullmatch(f"{pattern}(?:{suffix})?", name, flags=re.IGNORECASE) is not None


def _emitted_by_another(
    name: str, groups: Sequence[object], own: object, *, outside_frame: str | None = None
) -> bool:
    """Whether a group OTHER than ``own`` could emit plot group ``name``.

    A history column states a group's name and nothing else, so a name two
    declarations could produce is ambiguous: its history may be the other one's.
    An ambiguous name is never read as a source. With ``outside_frame``, only a
    group in ANOTHER frame counts: for the global axes, a second group in the same
    global frame still yields a global history.
    """
    return any(
        group is not own
        and (
            outside_frame is None
            or str(getattr(group, "frame", "")).strip().upper() != outside_frame
        )
        and _plot_name_can_emit(
            str(getattr(group, "name", "")),
            name,
            (),
            inventory=(),
            is_blade=lambda _family: False,
        )
        for group in groups
    )


def rotor_plot_source(
    pproc: object | None,
    alias: str,
    *,
    rotor_families: Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[str], str | None]:
    """Return the plot groups a rotor's six components may be read from, and why not.

    A force plot is named ``<parameter>_<group name>``, the group being an entry of
    the pproc's ``[[plots.groups]]``. So a rotor's history is found THROUGH THE
    PPROC, never by guessing a name:

    1. a group in the global ``MRP`` frame whose families are exactly the rotor's
       own, as the artifact declares it (``HUB_PUSHER`` is as good a name as any);
    2. the group the run adds since 0.24.0, ``ROTOR_<ALIAS>``, also in ``MRP``.

    A GROUP THAT MERELY SHARES THE ALIAS'S NAME IS NOT ONE: an artifact may call a
    group ``PROP`` over the blades alone while the rotor ``PROP`` owns a spinner
    too, and the table would then average another set of surfaces than the one it
    integrates on a steady run.

    A GROUP IN A ROTOR'S OWN FRAME IS NEVER A SOURCE. Its force is stated in axes
    that turn with the rotor and its moment is already about the hub, while the
    rotor table turns a geometry-frame force and transfers the moment from the
    moment point. An expanding frame names its emissions by ``{family}``, which is
    the one way a bare ``FX_<alias>`` arises, so that spelling is refused when the
    artifact declares it there.

    Returns the candidate group names, best first, and what was ruled out and
    why. Without a pproc, a caller holding a plots table and nothing else, the
    alias itself is the only candidate.
    """
    if pproc is None:
        return [alias], None
    wanted = {str(family) for family in rotor_families}
    candidates: list[str] = []
    refused: str | None = None
    generated = f"{ROTOR_PLOT_GROUP_PREFIX}{alias}"
    generated_is_declared = False
    #: The group that takes the generated name, and the frame it takes it in.
    taken_by: tuple[str, str] | None = None
    plots = getattr(pproc, "plots", None)
    components_declared = set(getattr(plots, "parameters", ()) or ()) & set(AXES_PLOT_COMPONENTS)
    is_blade = getattr(pproc, "is_blade", lambda _name: False)
    for group in getattr(getattr(pproc, "plots", None), "groups", ()) or ():
        frame = str(getattr(group, "frame", "")).strip().upper()
        name = str(getattr(group, "name", ""))
        named = group.families if isinstance(group.families, list) else [group.families]
        # Expanding rotor frames label their emissions with the cited rotor.
        took = _plot_name_can_emit(
            name,
            generated,
            group.families if frame in {"SMRP", "RMRP"} else (),
            inventory=inventory,
            is_blade=is_blade,
            aliases=aliases,
            frame=frame,
        )
        generated_is_declared |= took
        if took and taken_by is None:
            taken_by = (name, frame)
        try:
            resolved = select_families(group.families, list(inventory), is_blade, aliases)
        except PyflightstreamError:
            continue
        if frame not in {"SMRP", "RMRP"}:
            took = _plot_name_can_emit(
                name,
                generated,
                [family for selected in resolved for family in selected],
                inventory=inventory,
                is_blade=is_blade,
            )
            generated_is_declared |= took
            if took and taken_by is None:
                taken_by = (name, frame)
        if frame != "MRP":
            if "{family}" in name and alias in {str(member) for member in named}:
                refused = (
                    f"the pproc plots {name.replace('{family}', alias)!r} in the frame {frame}, "
                    "which is the rotor's own: a force there is not in the geometry's axes and "
                    "its moment is already about the hub, so it is not what a rotor table is "
                    "built from. Declare a plot group over the rotor's families with "
                    'frame = "MRP"'
                )
            continue
        if "{family}" in name:
            continue
        if any(wanted and set(families) == wanted for families in resolved):
            if _emitted_by_another(name, getattr(plots, "groups", ()) or (), group):
                continue
            candidates.append(name)
    # A declared name keeps its declared frame and families. The run skips
    # already emitted names when adding its automatic plots.
    if not (generated_is_declared and components_declared):
        candidates.append(generated)
    elif not candidates and refused is None and taken_by is not None:
        # THE NAME IS TAKEN AND NOTHING ELSE CAN SERVE, which left the caller
        # with no candidate at all and a message that named none. Measured on a
        # real pproc declaring `ROTOR_{family}` in `SMRP`: the run wrote
        # `FX_ROTOR_PUSHER` in the rotor's own frame, the automatic global-MRP
        # plot of that name was therefore not added, and eight rotor tables were
        # refused without a word a reader could act on (2026-09-22).
        declared, declared_frame = taken_by
        # WHICH COLLISION IT IS. A group in the rotor's own frame and a global
        # group over the wrong families both take the name and both leave no
        # source, but they are different mistakes and calling MRP "the rotor's
        # own" misnames the second (the V&V lens at the push review).
        # A ROTOR'S OWN FRAME IS NAMED FOR IT. The pproc writes the radical
        # (`SMRP`, `RMRP`) and the run builds `<ALIAS>_SMRP`, `<ALIAS>_RMRP<k>`;
        # both spellings reach here, and calling `PROP_SMRP` a family mismatch
        # named the wrong cause (the closing round, 2026-09-22).
        radical = declared_frame.rsplit("_", 1)[-1].rstrip("0123456789")
        why = (
            f"in the frame {declared_frame}, which is the rotor's own"
            if radical in {"SMRP", "RMRP"}
            else f"in the frame {declared_frame}, over families that are not exactly the rotor's"
        )
        refused = (
            f"the pproc's plot group {declared!r} already emits {generated!r} {why}, so the run "
            f"did not add its automatic {generated!r} in the global MRP frame over exactly the "
            f"rotor's families, and this run has no such history of rotor {alias!r} at all. No "
            f"post-processing can recover it. Rename that group to a name that is not "
            f"{generated!r} (for example 'SHAFT_{{family}}'), or declare a plot group over "
            f'exactly the rotor\'s families with frame = "MRP"; either way the rotor table '
            "returns on the next run"
        )
    return candidates, refused


def _recorded_rotor_plot_groups(emitted: object, families: Sequence[str]) -> list[str]:
    """Select a disjoint, exact cover of the rotor from recorded global-frame plots.

    Each selected group must carry all six components. Duplicate emitted names
    are ambiguous and cannot establish a frame or a surface selection.
    """
    if not isinstance(emitted, list):
        return []
    entries = [entry for entry in emitted if isinstance(entry, Mapping)]
    names = [str(entry.get("name", "")).casefold() for entry in entries]
    wanted = {family.casefold() for family in families}
    candidates: list[tuple[str, set[str]]] = []
    for entry in entries:
        name = str(entry.get("name", ""))
        owned = entry.get("families")
        parameters = entry.get("parameters")
        if (
            not name
            or names.count(name.casefold()) != 1
            or str(entry.get("frame", "")).upper() != "MRP"
            or not isinstance(owned, list)
            or not isinstance(parameters, list)
            or not set(AXES_PLOT_COMPONENTS) <= set(parameters)
        ):
            continue
        selected = {str(family).casefold() for family in owned}
        if selected and selected <= wanted:
            candidates.append((name, selected))

    def cover(remaining: set[str], start: int) -> list[str] | None:
        if not remaining:
            return []
        for index in range(start, len(candidates)):
            name, selected = candidates[index]
            if selected <= remaining:
                tail = cover(remaining - selected, index + 1)
                if tail is not None:
                    return [name, *tail]
        return None

    return cover(wanted, 0) or []


def _rotor_surfaces_carried(
    rotor: object,
    surfaces: Mapping[str, object],
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[str]:
    """Return the surfaces of this point that belong to ``rotor``, as the export names them.

    RESOLVED AS THE ROTOR'S LOADS ARE (:func:`rotor_shaft_loads`): through the
    package's group resolver, an alias, a family or an exact name, and compared
    without case. A plain membership test kept `Spinner` and lost `blade1` against
    an export naming `Blade1`, so a spinner-only plot group read as the rotor's
    whole history (the independent review of GitHub main, GH-1).
    """
    stated = [
        str(family)
        for family in [
            *(getattr(rotor, "families_general", None) or []),
            *(getattr(rotor, "families_blades", None) or []),
        ]
    ]
    owned = {name.casefold() for name in select_group_members(stated, list(surfaces), aliases)}
    return [str(name) for name in surfaces if str(name).casefold() in owned]


def _rotor_tables(
    workspace: CampaignWorkspace,
    sim_id: str,
    points: Sequence[PolarPoint],
    records: Sequence[RunRecord],
    sources: Mapping[str, Sequence[str]],
    reference: ReferenceValues,
    matrix_row: MatrixRow | None,
    out: Path,
    plots: Mapping[str, Path] | None = None,
    window: tuple[int, int] | None = None,
    pproc: object | None = None,
    windows: Mapping[str, tuple[int, int]] | None = None,
    aliases: Mapping[str, Sequence[str]] | None = None,
    frozen: Mapping[str, FrozenSolve] | None = None,
    skipped: dict[str, str] | None = None,
) -> list[tuple[Path, str, dict[str, object]]]:
    """Assemble one rotor table per rotor the ROW's reference declares (item 6).

    Returns the destination, the alias and everything `write_rotor_table` needs.
    A missing matrix row or unresolved reference is named in ``skipped``.
    Empty where the row names no reference, the reference declares no rotor, or
    no point states a speed -- each of which is an ordinary campaign rather
    than a fault, so none of them refuses the simulation's other products.

    EVERY ROW IS DIMENSIONALISED FROM ITS OWN POINT'S RECORD, and until the
    independent review of 2026-09-18 not one of them was. The rotor speed, the
    density, the velocity and the Mach were all read once off `records[0]` and
    the SPEED WAS HOISTED OUT OF THE POINT LOOP, so every row of a sweep was
    normalised by the FIRST point's state. On a J sweep from 0.5 to 1.0 -- the
    one shape this table exists for -- the second point's `CT` came out 0.03125
    where it is 0.125, a factor of four, and `J` came out 0.5 where it is 1.0.

    IT IS THE WORST FORM OF WRONG because the row still LOOKS right:
    `point_condition` is per point, so `ALPHA` and `MACH` in the same row are
    that point's own and correct, sitting beside coefficients computed from a
    different point entirely.

    THE PACKAGE ALREADY KNEW. The superfile writer sixty lines below resolves
    each point through `by_run` and carries a comment, dated 2026-09-11, saying
    in these words that a borrowed value is worse than a missing one because a
    reader sees a missing cell and cannot see a wrong one. That is the rule; it
    had one consumer and needed two.
    """
    skip_name = f"{POLARS_DIR}/{sim_id}#rotor_tables"
    if matrix_row is None:
        # An authored campaign never had a matrix row; only a matrix-derived
        # record can have lost the row needed to recover its rotor reference.
        if skipped is not None and any(record.matrix_stem for record in records):
            skipped[skip_name] = "no matrix row for this simulation; rotor tables cannot be planned"
        return []
    try:
        artifact = resolve_reference(workspace.inputs_dir, matrix_row.ref_code)
    except PyflightstreamError as error:
        if skipped is not None:
            skipped[skip_name] = (
                f"reference {matrix_row.ref_code!r} cannot be resolved; "
                f"rotor tables cannot be planned: {error}"
            )
        return []

    rotors = getattr(artifact, "rotors", None) or {}
    if not rotors:
        return []

    by_run = {record.run_id: record for record in records}
    #: Which plot group each rotor's history was read from, for the manifest.
    sources_read: dict[str, str] = {}

    def _state(point: PolarPoint) -> RunRecord | None:
        """Return the record of THIS point, or None -- never another point's.

        No fallback to `records[0]`, for the reason the superfile writer states
        at its own `by_run.get`: a borrowed value is worse than a missing one,
        because a reader sees a missing cell and cannot see a wrong one. Here it
        would not even be a cell -- it would be the divisor of every coefficient
        in the row.
        """
        run_id = (sources.get(point.name) or [""])[0]
        return by_run.get(run_id)

    #: The six components a plots table states for one group, in NEWTONS, and
    #: the order `rotor_shaft_loads` reads them back in as coefficients.
    _PLOT_COMPONENTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")

    def _averaged_newtons(
        point: PolarPoint, alias: str, families: Sequence[str]
    ) -> tuple[dict[str, float] | None, str, str | None]:
        """Return the rotor's six components averaged over the point's window, or why not.

        ITEM 16 SAYS ONE WINDOW FOR EVERY UNSTEADY PRODUCT OF THE POINT, and the
        rotor table was the product it did not reach: it was built from
        `point.loads`, the native export, which states THE LAST TIME STEP. So an
        unsteady rotor table published one instant of a cycle beside a polar that
        averaged correctly, and nothing in either file said which was which.

        IT LOOKED FOR `FX_<alias>` AND NO RUN PRINTED THAT NAME (L6-04). A force
        plot is named for its pproc GROUP, so the columns read `FX_HUB_PUSHER`;
        the lookup missed on every campaign and the fallback was silent. The
        columns are found through :func:`rotor_plot_source` now.

        The second value is the reason, for the caller to record; the third is the
        group the history was read from, which the manifest states.
        """
        span = (windows or {}).get(point.name, window)
        if plots is None or span is None:
            return None, "the row states no averaging window", None
        where = f"over steps {span[0]} to {span[1]}"
        source = plots.get(point.name)
        if source is None or not source.is_file():
            return None, f"it has no plots table to average {where}", None
        try:
            columns, series = plots_table_series(source)
        except (PyflightstreamError, OSError, ValueError) as error:
            return None, f"its plots table could not be read: {error}", None
        inventory = list(point.loads.surfaces) if point.loads is not None else []
        candidates, refused = rotor_plot_source(
            pproc, alias, rotor_families=families, inventory=inventory, aliases=aliases
        )
        group = next(
            (
                name
                for name in candidates
                if all(f"{part}_{name}" in columns for part in _PLOT_COMPONENTS)
            ),
            None,
        )
        groups = [group] if group is not None else []
        record = _state(point)
        recorded_plan = None if record is None else record.reductions
        if isinstance(recorded_plan, Mapping) and "plot_groups" in recorded_plan:
            groups = _recorded_rotor_plot_groups(recorded_plan["plot_groups"], families)
            if not groups or not all(
                f"{part}_{name}" in columns for name in groups for part in _PLOT_COMPONENTS
            ):
                # THE EXPLANATION TRAVELS WITH THIS REFUSAL TOO. A run that
                # records its emitted plot groups reached here BEFORE the
                # collision was explained, so a pproc taking the ROTOR_<ALIAS>
                # name in the rotor's own frame got a generic sentence naming
                # neither the group nor the remedy -- the very repair this
                # release made, bypassed on the path a 0.24.0 run takes (the
                # third independent reading, 2026-09-22).
                said = (
                    f"recorded plot groups do not provide an exact, unambiguous MRP history "
                    f"of rotor {alias!r} with all six components {where}"
                )
                return None, said if refused is None else f"{said}; {refused}", None
        if not groups:
            looked = ", ".join(f"FX_{name}" for name in candidates) or "none"
            reason = (
                f"its plots table holds the six components of no plot group of rotor {alias!r} "
                f"in the global MRP frame (looked for {looked} and their five siblings) to "
                f"average {where}"
            )
            return None, reason if refused is None else f"{reason}; {refused}", None
        steps = series.steps
        if not len(steps) or int(steps[0]) > span[0] or int(steps[-1]) < span[1]:
            held = f"steps {int(steps[0])} to {int(steps[-1])}" if len(steps) else "no step"
            return (
                None,
                f"the row states steps {span[0]} to {span[1]} and its history holds {held}",
                None,
            )
        try:
            read_steps: set[int] = set()
            averaged = blade_passage_average(series, window=span, read_steps=read_steps)
        except (PyflightstreamError, ValueError) as error:
            return None, f"its history could not be averaged {where}: {error}", None
        refusal = _judge_average(
            (frozen or {}).get(point.name),
            read_steps,
            point=point.name,
            product=f"polars/P{sim_id}-{alias}_rotor.csv",
        )
        if refusal is not None:
            return None, refusal, None
        return (
            {
                part: sum(float(averaged.fields[f"{part}_{name}"][0]) for name in groups)
                for part in _PLOT_COMPONENTS
            },
            "",
            ", ".join(groups),
        )

    def _as_coefficients(newtons: Mapping[str, float], *, density: float, speed: float) -> dict:
        """Turn the averaged Newtons back into the export's own coefficients.

        WHY THIS ROUND TRIP RATHER THAN A SECOND FORCE PATH. `rotor_shaft_loads`
        holds the family selection, the moment transfer to the hub, the shaft
        projection, the analysis-frame refusal and the wind-axis rotation --
        every one of them tested. A second entry point taking Newtons would be
        a second implementation of all of it, which is how two published numbers
        come to disagree. Dividing by the same dynamic pressure the export
        divided by is exact, not an approximation.
        """
        pressure = 0.5 * float(density) * float(speed) ** 2
        # `sref_m2` AND `cref_m`, WITH THEIR UNITS IN THE NAME. This read
        # `reference.sref` and `reference.cref`, which do not exist on this
        # class: an AttributeError the moment the averaging path ran, and NO
        # TEST REACHED IT because reaching it needs a plots table carrying
        # `FX_<alias>`. The type checker is what caught it, which is the whole
        # argument for running that gate rather than trusting a green suite.
        area = reference.sref_m2 or 0.0
        length = reference.cref_m or 0.0
        if pressure <= 0.0 or area <= 0.0 or length <= 0.0:
            return {}
        force = pressure * area
        moment = force * length
        return {
            "Cx": newtons["FX"] / force,
            "Cy": newtons["FY"] / force,
            "Cz": newtons["FZ"] / force,
            "CMx": newtons["MX"] / moment,
            "CMy": newtons["MY"] / moment,
            "CMz": newtons["MZ"] / moment,
        }

    tables: list[tuple[Path, str, dict[str, object]]] = []
    for alias, rotor in rotors.items():
        rows: list[dict[str, object]] = []
        # EVERY POINT THAT IS NOT A ROW, WITH ITS REASON AND ITS RUN ID. The
        # first writing of this function dropped three kinds of point on a bare
        # `continue`, leaving a table quietly shorter than the matrix while the
        # manifest's `runs` list still named every point -- so the provenance
        # said the row was there. The independent lens counted the sites. It is
        # the same defect this release had already fixed for the unsteady polar,
        # reintroduced three hours later by the fix for a different one.
        left_out: list[tuple[str, str]] = []
        for point in points:
            record = _state(point)
            run_id = (sources.get(point.name) or [""])[0]
            if record is None:
                left_out.append((run_id, f"{point.name}: no run record resolves for this point"))
                continue
            reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
            stated = reductions.get("rotors")
            rpm: float | None = None
            if isinstance(stated, Mapping):
                block = stated.get(str(alias))
                if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float):
                    rpm = float(block["rpm"])
            flat = reductions.get(FLAT_RPM_KEY)
            if (
                rpm is None
                and not (isinstance(stated, Mapping) and stated)
                and len(rotors) == 1
                and isinstance(flat, int | float)
                and not isinstance(flat, bool)
            ):
                # A ROW THAT STATES ITS ROTOR WITH FLAT KEYS plans no per-rotor
                # block and records its speed at the top of the plan. With ONE
                # rotor in the reference that speed can only be this rotor's;
                # with several nothing says whose it is, and the skip stays.
                rpm = float(flat)
            # A QUASI-STEADY ROTOR'S SPEED IS IN ITS OWN RECORD (L1 of 0.30.0,
            # RPT-090 and RPT-091). The run is steady and plans no reductions, so
            # neither source above states it; the builder wrote the row's speed,
            # the one the free stream turns at, in the record beside the loads
            # export, and the table reads it there as an unsteady rotor's reads
            # its plan's. The loads (docs/post-processing-definitions.md, the
            # quasi-steady rotor): a sector's one solve, read as it stands, the
            # package never multiplying by the copies; a WHEEL's mean over its
            # clockings (0.31.0, P0310-ROTOR-MEAN), below.
            quasi: QsteadyRecord | None = None
            if getattr(record, "recipe", None) == QSTEADY_ROTOR:
                # A RECORD THAT CANNOT BE READ costs this point its row, named
                # (0.31.0: one reader, one refusal, the caller decides).
                try:
                    quasi = read_qsteady_record(point.loads_path)
                except QsteadyRecordError as error:
                    left_out.append((run_id, f"{point.name}: {error}"))
                    continue
                if rpm is None:
                    rpm = _qsteady.rotor_speed(quasi, str(alias))
            own = getattr(point, "state", None)
            density = (
                own.density_kg_m3
                if own is not None and own.density_kg_m3 is not None
                else record.density_kg_m3
            )
            # THE VELOCITY THE EXPORT REPORTS, NOT THE ONE THE MATRIX ASKED FOR.
            #
            # The export's surface
            # coefficients are normalised by its REFERENCE velocity. So that is
            # the number this dimensionalisation must divide by, and the loads
            # header states it on its own line.
            #
            # IT READ `record.velocity_requested_m_s`, which is what the MATRIX
            # asked for -- disobeying the rule this package states in
            # `point_condition`'s own docstring, that the REPORTED condition
            # wins over the requested one, because the two differ exactly when
            # something went wrong. A fixture in this suite already carries a
            # run whose free stream is 50 and whose reference velocity is 100,
            # in Unsteady mode: a factor of four in dynamic pressure.
            #
            # When the two velocities agree, existing numbers do not change.
            # The published sentence about a static point stays
            # TRUE: with the two equal, hover really is divided by zero.
            reported = getattr(point.loads, "reference_velocity_m_s", None) if point.loads else None
            speed = reported if isinstance(reported, int | float) else None
            if rpm is None:
                left_out.append((run_id, f"{point.name}: its record states no speed for {alias!r}"))
                continue
            if not isinstance(density, int | float):
                left_out.append((run_id, f"{point.name}: its record states no air density"))
                continue
            if speed is None:
                left_out.append(
                    (
                        run_id,
                        f"{point.name}: its loads export states no reference velocity, "
                        "which is what its coefficients are normalised by",
                    )
                )
                continue
            # BOTH ADVANCE RATIOS ARE IN THE ROW, and the stage says when they part
            # (0.24.0, NL-09). `J` is what the row REQUESTED; `J_<alias>` is what this
            # rotor RAN at, from its own speed and diameter, and it is the one every
            # coefficient of the table uses. On the rotor the row sweeps the two
            # should agree; on a second rotor of the row they are not expected to,
            # so nothing is said about it.
            requested = (point.point or {}).get("advance_ratio")
            flight = point.loads.freestream_velocity_m_s if point.loads is not None else None
            span = float(getattr(rotor, "diameter_m", 0.0) or 0.0)
            clock = str(getattr(matrix_row, "variables", {}).get("CLOCK_MOTION", "") or "")
            if (
                isinstance(requested, int | float)
                and isinstance(flight, int | float)
                and span > 0.0
                and rpm
                and (len(rotors) == 1 or clock == str(alias))
            ):
                ran = float(flight) / (abs(rpm) / 60.0 * span)
                if abs(ran - float(requested)) > 5e-4 * max(1.0, abs(float(requested))):
                    warn(
                        f"{point.name}: the row asks for J = {float(requested):g} and rotor "
                        f"{alias} ran at J_{alias} = {ran:.5g} ({float(flight):g} m/s, "
                        f"{abs(rpm):g} rev/min, D {span:g} m). The coefficients of its rotor "
                        f"table use J_{alias}.",
                        PyflightstreamWarning,
                        stacklevel=2,
                    )
            # THE WINDOW AVERAGE WHERE THE HISTORY HAS IT, the last time step
            # where it does not -- and the file says which, every time.
            surfaces: Mapping[str, Mapping[str, float]] = (
                point.loads.surfaces if point.loads is not None else {}
            )
            carried = _rotor_surfaces_carried(rotor, surfaces, aliases)
            newtons, why_not, read_from = _averaged_newtons(point, str(alias), carried)
            if newtons is None and (windows or {}).get(point.name, window) is not None:
                # A ROW THAT STATES A WINDOW NEVER GETS AN INSTANT (RI-01). The table
                # used to fall back to the native export, the last time step, and
                # write it beside averaged rows under one header. The unsteady polar
                # beside it leaves such a point out and names it; so does this.
                left_out.append((run_id, f"{point.name}: {why_not}"))
                continue
            instant = True
            if newtons is not None:
                sources_read[str(alias)] = str(read_from)
                averaged_surfaces = _as_coefficients(
                    newtons, density=float(density), speed=float(speed)
                )
                families = list(getattr(rotor, "families_blades", None) or [])
                if averaged_surfaces and families:
                    # ONE SYNTHETIC SURFACE CARRYING THE WHOLE GROUP, UNDER THE
                    # ROTOR'S FIRST FAMILY NAME. The plots table states the
                    # group's RESULTANT, already summed over every family, so it
                    # must enter under exactly ONE name the rotor's own family
                    # selection will pick -- putting it under all of them would
                    # sum the whole rotor once per blade.
                    surfaces = {str(families[0]): averaged_surfaces}
                    instant = False
            # A QUASI-STEADY WHEEL'S ROW IS THE MEAN OF ITS k CLOCKINGS (0.31.0,
            # P0310-ROTOR-MEAN), not clocking 0 alone:
            # each surface's loads averaged over the clockings' own exports, so
            # the statics below take every coefficient of the MEAN loads, never
            # a mean of per-clocking ETA. A clocking that cannot be read costs
            # the point its row, named: a mean of the rest is not its mean.
            clockings: int | None = None
            if quasi is not None and quasi.case == "wheel":
                meaned = _qsteady.mean_clocking_surfaces(
                    quasi, point.loads_path.parent, speed_m_s=float(speed)
                )
                if isinstance(meaned, str):
                    left_out.append(
                        (
                            run_id,
                            f"{point.name}: {meaned}; the row of a wheel is the mean of all "
                            "its clockings, never of the others",
                        )
                    )
                    continue
                surfaces = meaned.surfaces
                clockings = meaned.clockings
            rows.append(
                {
                    "run_id": run_id,
                    "surfaces": surfaces,
                    "aliases": aliases,
                    "instant": instant,
                    # 0.31.0: k, where the row is the mean of a wheel's clockings.
                    "clockings": clockings,
                    "condition": point_condition(
                        point,
                        mach=record.mach or 0.0,
                        clock=clock_rotor_facts(record, matrix_row, artifact),
                    ),
                    "rpm": rpm,
                    "density": float(density),
                    "speed": float(speed),
                    "free_stream": (
                        point.loads.freestream_velocity_m_s if point.loads is not None else None
                    ),
                    # 0.30.0 (M1): the free-stream speed and the speed of sound
                    # the point resolved to, for its tip and helical Mach numbers.
                    "air": _free_stream_and_sound(record),
                    # THE EXPORT'S OWN STATEMENT OF WHICH FRAME ITS FORCES ARE
                    # IN. Carried from the point to the coefficient rather than
                    # assumed, because `ETAW` rotates that force into wind axes
                    # and the rotation is only valid from the geometry frame.
                    "frame": (point.loads.frame if point.loads is not None else None),
                }
            )
        # THE ALIAS REACHES A FILE NAME SANITISED (NL-04), by the function the
        # passage reductions of this same rotor already use. Raw, a slash wrote
        # the table into a subfolder the manifest then keyed with a slash, and a
        # colon on Windows wrote a stream nobody can see. The rotor's own
        # spelling is the file's first line and the manifest's `rotor` field.
        name = (
            f"{sweep_file_stem(sim_id, _a_name_a_file_may_carry(str(alias)))}{ROTOR_TABLE_SUFFIX}"
        )
        if not rows:
            # EVERY ROW REJECTED IS STILL A REPORT. Returning nothing here made
            # the whole product vanish with no explanation, which is the same
            # silence one level up. The caller writes no file for a plan whose
            # rows are empty and records the reasons instead.
            tables.append(
                (
                    out / POLARS_DIR / name,
                    str(alias),
                    {"rotor": rotor, "rows": [], "left_out": left_out},
                )
            )
            continue
        tables.append(
            (
                out / POLARS_DIR / name,
                str(alias),
                {
                    "rotor": rotor,
                    "rows": rows,
                    "left_out": left_out,
                    # WHAT THE TABLE IS (RI-01), for the manifest: the group its
                    # history was read from, or None where it is the native export
                    # of a steady run.
                    "read_from": sources_read.get(str(alias)),
                },
            )
        )
    return tables
