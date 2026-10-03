"""The reductions of one point's plots table, each one file beside it.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0), called by the simulation stage of :mod:`pyflightstream.post._sim`
for every plots table it writes.

Each applicable reduction of a point's plots table is one file beside it
under ``probes/``, windowed as the record's plan and the matrix row state
it: the time average, the phase-locked table and the per-blade table, one
per rotor where a row names its rotors (FR-68), and the per-revolution table
with the drift of its last revolution (0.31.0), each written by the writers
of :mod:`pyflightstream.post.point_tables`. A reduction the row cannot window
is recorded under ``skipped`` with its reason, and an average a frozen solve
would cover is refused by the stage's one verdict. A names dictionary of the
pproc is applied where the table can honour it and said where it cannot.

A further reduction of the backlog joins this module, its table writer
joining :mod:`pyflightstream.post.point_tables`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import DEFAULT_DRIFT_LIMIT_PCT
from pyflightstream.cases.windows import AZIMUTHAL
from pyflightstream.cases.workflows import PER_ROTOR_REDUCTIONS, REDUCTION_NAMES, ROTORS_KEY
from pyflightstream.post._stage import (
    _MOMENT_POINT_COLUMNS,
    _PER_BLADE,
    _PER_REVOLUTION,
    _PHASE_LOCKED,
    _PLOTS_CLOCK_COLUMNS,
    PROBES_DIR,
    _a_name_a_file_may_carry,
    _judge_average,
    _names_location,
    _window_the_reduction_reads,
)
from pyflightstream.post._tables import (
    ProductError,
    ReferenceValues,
    context_row,
    plots_table_series,
    renamed_columns,
    write_csv_table,
)
from pyflightstream.post.point_tables import (
    DRIFT_SUFFIX,
    PER_REVOLUTION_COLUMNS,
    per_revolution_table,
    revolution_drift_pct,
    write_per_blade_table,
    write_phase_locked_table,
    write_reduction_table,
)
from pyflightstream.post.unsteady import (
    TimestepSeries,
    revolution_drift_warnings,
)
from pyflightstream.results import FrozenSolve


def _dictionary_the_table_can_honour(
    columns: Sequence[str],
    names: Mapping[str, str] | None,
    stem: str,
    skipped: dict[str, str],
) -> Mapping[str, str] | None:
    """Return the pproc dictionary, or None once it is reported as unusable.

    A dictionary the plots table cannot honour is said ONCE for the point, under
    `probes/<point>#names`, and the reductions keep the export's own names
    rather than be lost. This lived inside the lazy load of the history until
    2026-09-22, when loading it earlier for the interpolation support skipped
    the check and handed the writer a dictionary it then refused the product
    for.
    """
    try:
        renamed_columns(columns, names, printed=columns, where=_names_location(PROBES_DIR, stem))
    except ProductError as refused:
        skipped[f"{PROBES_DIR}/{stem}#names"] = str(refused)
        warn(str(refused), PyflightstreamWarning, stacklevel=2)
        return None
    return names


def _point_reductions(
    plots_table: Path,
    plan: Mapping[str, object] | None,
    out: Path,
    *,
    runs: list[str],
    target: Callable[[Path], Path],
    written: list[Path],
    written_names: dict[str, dict[str, object]],
    skipped: dict[str, str],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    rotor_facts: Mapping[str, Mapping[str, object]] | None = None,
    names: Mapping[str, str] | None = None,
    frozen: FrozenSolve | None = None,
    pol: str | int | None = None,
    drift_limit_pct: float | None = None,
) -> None:
    """Write every applicable reduction of one plots table beside it (PFS-2015.04).

    ``pol`` is the point's polar, the first column of every reduction since
    0.27.0 (G16).

    ``names`` is the pproc's dictionary. It renames the columns of the averaged
    reductions; a dictionary the plots table cannot honour is said ONCE for the
    point, under ``probes/<point>#names``, and the reductions keep the export's
    names rather than be lost. The per-blade and azimuthal tables carry columns
    that are no longer the export's own names and are not renamed.

    ``rotor_facts`` is what the sections table takes of each rotor, its blade
    families and its clock; the per-blade reduction is ONE ROW PER BLADE since
    0.24.0 and needs both.

    The plots table is written FIRST and is never touched here: the
    reductions are read off it and land under their own names beside it,
    which is the rule of 2026-08-16 (a reduction ships beside the history
    and never in its place) kept by construction. A reduction the record
    cannot window, or whose window reaches past the table, is a skip
    recorded under the file it would have been, with the reason.
    """
    stem = plots_table.name[: -len("_plots.csv")]
    if plan is None:
        skipped[f"{PROBES_DIR}/{stem}_time_average.csv"] = (
            "the run record carries no reduction windows, so no reduction of the plots "
            "table can say which steps it averaged; the record was written before the "
            "field existed or by hand. Rerun the row, and the record will carry the "
            "windows its row states."
        )
        return
    ctx = _ReductionProducts(
        plots_table=plots_table,
        plan=plan,
        out=out,
        runs=runs,
        target=target,
        written=written,
        written_names=written_names,
        skipped=skipped,
        condition=condition,
        reference=reference,
        rotor_facts=rotor_facts,
        names=names,
        frozen=frozen,
        pol=pol,
        stem=stem,
    )
    reading, per_rotor = _reduction_reading(ctx)
    for name, entry, relative, rotor in reading:
        _write_point_reduction(ctx, name, entry, relative, rotor, per_rotor=per_rotor)
    _write_point_revolutions(ctx, drift_limit_pct)


def _the_rotor_of_a_reduction(
    rotor: str | None,
    plan: Mapping[str, object],
    rotor_facts: Mapping[str, Mapping[str, object]],
) -> tuple[str | None, Mapping[str, object], int]:
    """Return the rotor a passage reduction is about, what is known of it, and its blades.

    A per-rotor file names its rotor. The row-level file of a row that turns ONE
    rotor is that rotor's; with none or several it is nobody's and the facts are
    empty, which the writer refuses by name.
    """
    facts: Mapping[str, object] = {}
    blades: object = plan.get("blades")
    if rotor is not None:
        facts = rotor_facts.get(rotor, {})
        blocks = plan.get(ROTORS_KEY)
        block = blocks.get(rotor) if isinstance(blocks, Mapping) else None
        if isinstance(block, Mapping) and block.get("blades") is not None:
            blades = block.get("blades")
    elif len(rotor_facts) == 1:
        rotor, facts = next(iter(rotor_facts.items()))
        rotor = rotor or None
    count = int(blades) if isinstance(blades, int | float) and not isinstance(blades, bool) else 0
    return rotor, facts, count


def _write_the_per_blade_table(
    destination: Path,
    series: TimestepSeries,
    columns: Sequence[str],
    windows: Sequence[tuple[int, ...]],
    *,
    rotor: str | None,
    plan: Mapping[str, object],
    rotor_facts: Mapping[str, Mapping[str, object]],
    condition: Mapping[str, object] | None,
    reference: ReferenceValues | None,
    pol: str | int | None = None,
) -> Path:
    """Resolve which rotor a per-blade file is about, and write one row per blade.

    A per-rotor file names its rotor. The row-level file of a row that turns ONE
    rotor is that rotor's; with none or several it is nobody's, and the writer
    refuses it by name rather than guess. A record planned before the window was
    shared holds one window per blade: their span is the revolution they cut, and
    it is the window every blade is averaged over now.
    """
    if not windows:
        raise ProductError("the per_blade reduction states no window")
    rotor, facts, count = _the_rotor_of_a_reduction(rotor, plan, rotor_facts)
    return write_per_blade_table(
        destination,
        series,
        columns,
        window=(int(windows[0][0]), int(windows[-1][1])),
        rotor=rotor,
        blades=count,
        facts=facts,
        condition=condition,
        reference=reference,
        pol=pol,
    )


def _drift_limit_pct(pproc: object) -> float:
    """Return the drift limit the pproc declares, in per cent, else the default."""
    declared = getattr(getattr(pproc, "per_revolution", None), "drift_limit_pct", None)
    return float(declared) if isinstance(declared, int | float) else DEFAULT_DRIFT_LIMIT_PCT


def _per_revolution_targets(
    plan: Mapping[str, object], stem: str
) -> list[tuple[str | None, object, str]]:
    """Return (rotor alias or None, steps per revolution, file) for each rotor of the plan."""
    blocks = plan.get(ROTORS_KEY)
    targets: list[tuple[str | None, object, str]] = []
    if isinstance(blocks, Mapping):
        for alias, block in blocks.items():
            stated = block.get("steps_per_revolution") if isinstance(block, Mapping) else None
            safe = _a_name_a_file_may_carry(str(alias))
            targets.append(
                (str(alias), stated, f"{PROBES_DIR}/{stem}_{_PER_REVOLUTION}_{safe}.csv")
            )
    elif isinstance(plan.get("phase_locked"), Mapping):
        targets.append(
            (None, plan.get("steps_per_revolution"), f"{PROBES_DIR}/{stem}_{_PER_REVOLUTION}.csv")
        )
    return targets


def _write_the_per_revolution_products(
    series: TimestepSeries,
    columns: Sequence[str],
    plan: Mapping[str, object],
    out: Path,
    *,
    stem: str,
    runs: list[str],
    target: Callable[[Path], Path],
    written: list[Path],
    written_names: dict[str, dict[str, object]],
    skipped: dict[str, str],
    condition: Mapping[str, object] | None,
    reference: ReferenceValues | None,
    names: Mapping[str, str] | None,
    frozen: FrozenSolve | None,
    pol: str | int | None,
    drift_limit_pct: float,
) -> None:
    """Write `<point>_per_revolution_<ALIAS>.csv` for each rotor the record's plan turns.

    One file per rotor of the plan's ``rotors`` block, each cut on THAT rotor's
    own steps per revolution; a row that names no rotor by alias and states its
    clock flat gets `<point>_per_revolution.csv` with `NA` for the rotor. A point
    whose plan states no rotor at all (a steady or a plain unsteady one) has no
    revolution and no entry: it is not applicable, as `phase_locked` is not.
    A rotor whose clock could not be resolved, a history shorter than one
    revolution and a refused frozen solve are each a named skip.

    THE WARNING NEVER BLOCKS (invariant 12): the last revolution's drift over the
    declared limit is a WARNING line in ``post.log`` and the table is written.
    """
    printed = [name for name in columns if name not in _PLOTS_CLOCK_COLUMNS]
    for rotor, per_revolution, relative in _per_revolution_targets(plan, stem):
        who = f"rotor {rotor!r}" if rotor is not None else "the row's rotor"
        if (
            isinstance(per_revolution, bool)
            or not isinstance(per_revolution, int | float)
            or not per_revolution >= 0.5
        ):
            skipped[relative] = (
                f"the run record states no steps per revolution for {who}, so a revolution "
                "has no length in solver steps and the history cannot be cut into revolutions. "
                "It is stated where the row gives the rotor speed and the solver time step."
            )
            continue
        revolution_steps = int(round(float(per_revolution)))
        read: set[int] = set()
        try:
            windows, means, partial = per_revolution_table(
                series, printed, revolution_steps=revolution_steps, read_steps=read
            )
        except (PyflightstreamError, ValueError) as error:
            skipped[relative] = str(error)
            continue
        if not windows:
            skipped[relative] = (
                f"the plots table of this point holds {len(series.steps)} time steps and "
                f"{who} turns {float(per_revolution):g} solver steps per revolution "
                f"({revolution_steps} used), so not one COMPLETE revolution was written and "
                "there is nothing to average"
            )
            continue
        reason = _judge_average(frozen, read, point=stem, product=relative)
        if reason is not None:
            target(out / relative)  # archive any stale product from an earlier post
            skipped[relative] = reason
            continue
        drifts: list[dict[str, float | None]] = [{name: None for name in printed}]
        for previous, current in zip(means, means[1:], strict=False):
            drifts.append(
                {name: revolution_drift_pct(current[name], previous[name]) for name in printed}
            )
        try:
            heading = renamed_columns(
                (*PER_REVOLUTION_COLUMNS, *printed),
                names,
                printed=printed,
                where=_names_location(PROBES_DIR, relative),
            )
        except ProductError as refused:
            skipped[relative] = str(refused)
            continue
        shown = heading[len(PER_REVOLUTION_COLUMNS) :]
        context = context_row(condition, None if reference is None else reference.as_lengths())
        moment = context_row(
            None if reference is None else reference.as_moment_point(),
            None,
            columns=_MOMENT_POINT_COLUMNS,
        )
        rows: list[tuple[object, ...]] = []
        for index, ((first, last), mean, drift) in enumerate(
            zip(windows, means, drifts, strict=True), start=1
        ):
            rows.append(
                (
                    pol,
                    _PER_REVOLUTION,
                    rotor,
                    index,
                    first,
                    last,
                    revolution_steps,
                    *context,
                    *moment,
                    *(mean[name] for name in printed),
                    *(drift[name] for name in printed),
                )
            )
        destination = target(out / relative)
        written.append(
            write_csv_table(
                destination,
                (*heading, *(f"{name}{DRIFT_SUFFIX}" for name in shown)),
                rows,
            )
        )
        if partial:
            note = (
                f"the plots table holds {len(series.steps)} time steps, {len(windows)} complete "
                f"revolution(s) of {revolution_steps} and {partial} step(s) of a partial one, "
                "which is NOT averaged: a mean of part of a revolution is a mean of another thing"
            )
            skipped[f"{relative}#partial"] = note
            warn(f"point={stem} product={relative}: {note}", PyflightstreamWarning, stacklevel=2)
        before = means[-2] if len(means) >= 2 else {}  # only a second revolution can drift
        for clause in revolution_drift_warnings(
            before, means[-1], dict(zip(printed, shown, strict=True)), limit_pct=drift_limit_pct
        ):
            warn(
                f"point={stem} product={relative}: {who} {clause} between revolution "
                f"{len(windows) - 1} and revolution {len(windows)}, over the drift limit "
                f"of {drift_limit_pct:g} per cent ([per_revolution] drift_limit_pct): "
                "the last revolution is still moving",
                PyflightstreamWarning,
                stacklevel=2,
            )
        record: dict[str, object] = {
            "runs": runs,
            "reduction": _PER_REVOLUTION,
            "windows": [list(window) for window in windows],
            "window_from": (
                f"the plots table cut into complete revolutions of {revolution_steps} solver steps"
            ),
            "steps_per_revolution": float(per_revolution),
        }
        if rotor is not None:
            record["rotor"] = rotor
        written_names[relative] = record


@dataclass
class _ReductionProducts:
    """One point's output sinks and lazily loaded plots history."""

    plots_table: Path
    plan: Mapping[str, object]
    out: Path
    runs: list[str]
    target: Callable[[Path], Path]
    written: list[Path]
    written_names: dict[str, dict[str, object]]
    skipped: dict[str, str]
    condition: Mapping[str, object] | None
    reference: ReferenceValues | None
    rotor_facts: Mapping[str, Mapping[str, object]] | None
    names: Mapping[str, str] | None
    frozen: FrozenSolve | None
    pol: str | int | None
    stem: str
    series: TimestepSeries | None = None
    columns: tuple[str, ...] = ()


def _reduction_reading(
    ctx: _ReductionProducts,
) -> tuple[list[tuple[str, object, str, str | None]], dict[str, list[str]]]:
    # ONE READING LIST, TWO SHAPES (FR-68). A row turning several rotors
    # has no single blade passage, so its two passage reductions live one
    # per ROTOR under `rotors` and land in files that NAME the rotor; the
    # flat keys carry the skip that says where they went, and the products
    # record it as it records any skip. A row turning one rotor, and every
    # row written before 0.15.0, reads the flat keys alone and its files
    # keep the names they have always had.
    """List flat reductions before per-rotor reductions and their skip pointers."""
    reading: list[tuple[str, object, str, str | None]] = [
        (name, ctx.plan.get(name), f"{PROBES_DIR}/{ctx.stem}_{name}.csv", None)
        for name in REDUCTION_NAMES
    ]
    rotors = ctx.plan.get(ROTORS_KEY)
    if isinstance(rotors, Mapping):
        for alias, block in rotors.items():
            if not isinstance(block, Mapping):
                continue
            safe = _a_name_a_file_may_carry(str(alias))
            for name in PER_ROTOR_REDUCTIONS:
                reading.append(
                    (
                        name,
                        block.get(name),
                        f"{PROBES_DIR}/{ctx.stem}_{name}_{safe}.csv",
                        str(alias),
                    )
                )
    # THE FLAT SKIP NAMES THE FILES, because this layer knows the stem and
    # the cases layer does not. Its own sentence can only describe the
    # SHAPE of the names; read by someone who has just opened the plots
    # folder and not found their per-blade table, that is one inference
    # away from the two files sitting in the folder they are looking at
    # (the interface lens, 2026-09-10).
    per_rotor: dict[str, list[str]] = {}
    for name, _entry, relative, rotor in reading:
        if rotor is not None:
            per_rotor.setdefault(name, []).append(relative)
    return reading, per_rotor


def _judged_reduction_windows(
    ctx: _ReductionProducts,
    name: str,
    entry: Mapping[str, object],
    relative: str,
    rotor: str | None,
) -> (
    tuple[list[tuple[int, ...]], list[tuple[tuple[int, ...], str]], Mapping[str, object], int]
    | None
):
    """Read the history once and judge the samples of each planned window."""
    stated = cast(Iterable[Iterable[int | str]], entry.get("windows", ()))
    windows = [tuple(int(v) for v in window) for window in stated]
    try:
        if ctx.series is None:
            ctx.columns, ctx.series = plots_table_series(ctx.plots_table)
            ctx.names = _dictionary_the_table_can_honour(
                ctx.columns, ctx.names, ctx.stem, ctx.skipped
            )
        _, facts, count = _the_rotor_of_a_reduction(rotor, ctx.plan, ctx.rotor_facts or {})
        combined_reads = (
            _window_the_reduction_reads(
                name, entry, (windows[0][0], windows[-1][1]), ctx.series, ctx.columns, count, facts
            )
            if name == _PER_BLADE and windows
            else None
        )
        reached = [
            (window, why)
            for window in windows
            if (
                why := _judge_average(
                    ctx.frozen,
                    {step for step in combined_reads if window[0] <= step <= window[-1]}
                    if combined_reads is not None
                    else _window_the_reduction_reads(
                        name, entry, window, ctx.series, ctx.columns, count, facts
                    ),
                    point=ctx.stem,
                    product=relative,
                )
            )
            is not None
        ]
    except (PyflightstreamError, OSError, ValueError) as error:
        ctx.skipped[relative] = str(error)
        return None
    return windows, reached, facts, count


def _trim_reduction_windows(
    ctx: _ReductionProducts,
    name: str,
    entry: Mapping[str, object],
    relative: str,
    *,
    windows: list[tuple[int, ...]],
    reached: list[tuple[tuple[int, ...], str]],
    facts: Mapping[str, object],
    count: int,
) -> list[tuple[int, ...]] | None:
    """Trim refused windows and judge the final per-blade span without bridging."""
    assert ctx.series is not None  # The first sample judgment loaded the history.
    frozen_windows = [window for window, _ in reached]
    kept = [window for window in windows if window not in frozen_windows]
    # THE PER-BLADE TABLE HAS ONE WINDOW, collapsed from its passages, so
    # dropping a refused passage IN THE MIDDLE and collapsing the rest
    # BRIDGES it: passages [55,56] and [59,60] became [55,60], averaging the
    # very step the refusal had just removed and recording that span in the
    # manifest (the V&V lens at the push review, 2026-09-22). Losing
    # passages from an END is not bridging and keeps its product, which is
    # what the definitions page asks and what the independent review of
    # 0.25.0 restored. So the test is CONTIGUITY, not "any refusal".
    bridged = (
        name == _PER_BLADE and kept != windows[windows.index(kept[0]) : windows.index(kept[-1]) + 1]
        if kept
        else False
    )
    if reached and (not kept or bridged):
        ctx.target(ctx.out / relative)  # archive any stale product from an earlier post
        ctx.skipped[relative] = (
            reached[0][1]
            if not kept
            else f"{reached[0][1]}; this table states ONE window over its passages and the "
            "refused one lies between passages that were kept, so the window it would state "
            "would span the refused steps"
        )
        return None
    if reached:
        windows = kept
    if name == _PER_BLADE and windows:
        # End trimming changes the span. Ask the reducer again for exactly
        # what the final table reads, including samples between passages.
        # UNDER THE SAME HANDLING AS THE FIRST ASK: a trimmed span that
        # holds no plotted frame is a named skip of this table, as the
        # definitions page asks of every no-data impossibility, and not an
        # exception out of the post (the QA read of the closing-round
        # fixes, 2026-09-23: passages [58,58], [59,59], [60,61], plotted
        # 60 and 61, unread 61 opt-in, aborted every later product).
        try:
            final_reads = _window_the_reduction_reads(
                name, entry, (windows[0][0], windows[-1][1]), ctx.series, ctx.columns, count, facts
            )
            final_reason = _judge_average(ctx.frozen, final_reads, point=ctx.stem, product=relative)
        except (PyflightstreamError, OSError, ValueError) as error:
            ctx.target(ctx.out / relative)
            ctx.skipped[relative] = str(error)
            return None
        if final_reason is not None:
            ctx.target(ctx.out / relative)
            ctx.skipped[relative] = final_reason
            return None
    return windows


def _write_reduction_table(
    ctx: _ReductionProducts,
    name: str,
    entry: Mapping[str, object],
    relative: str,
    rotor: str | None,
    *,
    windows: list[tuple[int, ...]],
) -> tuple[Path, list[tuple[int, ...]]] | None:
    """Dispatch the table writer and return the windows its file actually holds."""
    assert ctx.series is not None  # The caller loaded and judged this history.
    destination = ctx.target(ctx.out / relative)
    try:
        if name == _PER_BLADE:
            done = _write_the_per_blade_table(
                destination,
                ctx.series,
                ctx.columns,
                windows,
                rotor=rotor,
                plan=ctx.plan,
                rotor_facts=ctx.rotor_facts or {},
                condition=ctx.condition,
                reference=ctx.reference,
                pol=ctx.pol,
            )
            # ONE WINDOW, and the manifest says the one the file holds.
            windows = [(windows[0][0], windows[-1][1])]
        elif name == _PHASE_LOCKED and entry.get("shape") == AZIMUTHAL:
            # THE PPROC DECLARES [phase_locked]: the mean at each azimuth.
            rotor_of, facts, count = _the_rotor_of_a_reduction(
                rotor, ctx.plan, ctx.rotor_facts or {}
            )
            done = write_phase_locked_table(
                destination,
                ctx.series,
                ctx.columns,
                window=windows[0],
                revolutions=float(entry.get("revolutions") or 0.0),  # type: ignore[arg-type]
                steps_per_revolution=float(entry.get("steps_per_revolution") or 0.0),  # type: ignore[arg-type]
                rotor=rotor_of,
                blades=count,
                facts=facts,
                condition=ctx.condition,
                reference=ctx.reference,
                pol=ctx.pol,
            )
        else:
            done = write_reduction_table(
                destination,
                ctx.series,
                ctx.columns,
                reduction=name,
                windows=windows,
                names=ctx.names,
                # ITEM 5. A reduction is an AVERAGE over a window, and an
                # average of coefficients states nothing without the condition
                # they were taken at and the lengths they were normalised by.
                # Both are threaded in from the caller: this function reaches no
                # record, and inventing them here is how two products of one
                # point come to disagree about what point it was.
                condition=ctx.condition,
                reference=ctx.reference,
                rotor=rotor,
                pol=ctx.pol,
            )
    except ProductError as error:
        ctx.skipped[relative] = str(error)
        return None
    return done, windows


def _write_point_reduction(
    ctx: _ReductionProducts,
    name: str,
    entry: object,
    relative: str,
    rotor: str | None,
    *,
    per_rotor: Mapping[str, list[str]],
) -> None:
    """Judge, write and index one reduction while preserving named omissions."""
    if not isinstance(entry, Mapping):
        return  # not applicable to this run type
    if "skipped" in entry:
        reason = str(entry["skipped"])
        if rotor is None and per_rotor.get(name):
            # THE POINTER REPLACES THE GENERIC TAIL AND ADDS NOTHING ELSE.
            # The head up to the last colon already says the row names its
            # rotors; appending that again made one fact print twice and
            # buried the file names at the end of the repetition, on six
            # lines of every rotor sweep (PFS-2015.05).
            reason = (
                f"{reason.rsplit(':', 1)[0]}: the per-rotor files are "
                f"{' and '.join(per_rotor[name])}."
            )
        ctx.skipped[relative] = reason
        return
    judged = _judged_reduction_windows(ctx, name, entry, relative, rotor)
    if judged is None:
        return
    windows, reached, facts, count = judged
    trimmed = _trim_reduction_windows(
        ctx,
        name,
        entry,
        relative,
        windows=windows,
        reached=reached,
        facts=facts,
        count=count,
    )
    if trimmed is None:
        return
    windows = trimmed
    if ctx.series is None:
        ctx.columns, ctx.series = plots_table_series(ctx.plots_table)
        ctx.names = _dictionary_the_table_can_honour(ctx.columns, ctx.names, ctx.stem, ctx.skipped)
    result = _write_reduction_table(ctx, name, entry, relative, rotor, windows=windows)
    if result is None:
        return
    done, windows = result
    ctx.written.append(done)
    # A FILE WRITTEN WITHOUT SOME OF ITS WINDOWS SAYS SO, under its own name
    # with a marker, the idiom this module uses for a block that was asked for
    # and not applied. Without it the kept passages would look like the whole
    # reduction and the frozen one would have vanished unnamed.
    if reached:
        note = "; ".join(why for _, why in reached)
        ctx.skipped[f"{relative}#windows"] = note
        warn(f"{relative}: {note}", PyflightstreamWarning, stacklevel=3)
    _record_reduction_product(ctx, name, entry, relative, rotor, windows=windows)


def _write_point_revolutions(
    ctx: _ReductionProducts,
    drift_limit_pct: float | None,
) -> None:
    # THE PER-REVOLUTION PRODUCT (0.31.0, P0310-G2-PER-REV) is read off the same
    # WRITTEN table and is not one of `REDUCTION_NAMES`: it has no window of the
    # row's, it cuts the whole history into revolutions.
    """Write per-revolution products using the point's shared history reading."""
    if not (
        isinstance(ctx.plan.get(ROTORS_KEY), Mapping)
        or isinstance(ctx.plan.get("phase_locked"), Mapping)
    ):
        return  # no rotor turns in this point: the product is not applicable
    if ctx.series is None:
        try:
            ctx.columns, ctx.series = plots_table_series(ctx.plots_table)
        except (PyflightstreamError, OSError, ValueError) as error:
            ctx.skipped[f"{PROBES_DIR}/{ctx.stem}_{_PER_REVOLUTION}.csv"] = str(error)
            return
        ctx.names = _dictionary_the_table_can_honour(ctx.columns, ctx.names, ctx.stem, ctx.skipped)
    _write_the_per_revolution_products(
        ctx.series,
        ctx.columns,
        ctx.plan,
        ctx.out,
        stem=ctx.stem,
        runs=ctx.runs,
        target=ctx.target,
        written=ctx.written,
        written_names=ctx.written_names,
        skipped=ctx.skipped,
        condition=ctx.condition,
        reference=ctx.reference,
        names=ctx.names,
        frozen=ctx.frozen,
        pol=ctx.pol,
        drift_limit_pct=DEFAULT_DRIFT_LIMIT_PCT if drift_limit_pct is None else drift_limit_pct,
    )


def _record_reduction_product(
    ctx: _ReductionProducts,
    name: str,
    entry: Mapping[str, object],
    relative: str,
    rotor: str | None,
    *,
    windows: list[tuple[int, ...]],
) -> None:
    """Index the written reduction's exact windows and rotor provenance."""
    record: dict[str, object] = {
        "runs": ctx.runs,
        "reduction": name,
        "windows": [list(window) for window in windows],
        "window_from": entry.get("window_from"),
    }
    if "period_steps" in entry:
        record["period_steps"] = entry["period_steps"]
    for key in ("shape", "revolutions", "steps_per_revolution"):
        if key in entry:
            record[key] = entry[key]
    if rotor is not None:
        # THE ROTOR AS A FIELD, not only as a piece of a file name. The
        # name is `{stem}_{reduction}_{alias}` and both the reduction
        # and the alias carry underscores, so it does not decompose: a
        # reader holding `a-02.0_per_blade_LIFT_L1.csv` could not say
        # which rotor it is without already knowing the alias set (the
        # interface lens, 2026-09-10).
        record["rotor"] = rotor
    ctx.written_names[relative] = record
