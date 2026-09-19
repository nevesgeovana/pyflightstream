"""The per-step exports of an unsteady point as a series (PFS-2031.18.01).

A row stating ``EXPORT_UNSTEADY_AFTER_REV`` or ``EXPORT_UNSTEADY_AFTER_ITER``
has the solver export its loads, sectional loads and probe points on every
step from the threshold on, each file stamped ``_iteration=N`` beside the
simulation (RPT-041 finding 3). Those files are what the reference incidence study
reads, one revolution after another, and a folder of forty stamped
spreadsheets is not a series until something tables them: this module
writes, per point, one table per export kind under ``post/<matrix
stem>/series/``, a row per step (and per surface, section or probe where
the export carries several), the step's time and azimuth from the clock the
run record carries, which is the same arithmetic the counter program runs
on the machine (``run/_actions_counter.py``, ``state()``), so the series and
the counter agree by construction.

Native surface files and the ``_cp`` files remain listed in ``products.json``.
The distribution writer also tables sectional loads and Cp, one file per
pproc distribution, while this module retains the combined sections series.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pyflightstream._errors import PyflightstreamError
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.post._tables import (
    CONTEXT_COLUMNS,
    SECTION_COLUMNS,
    ProductError,
    ProductExistsError,
    context_row,
    section_identity,
    write_csv_table,
)
from pyflightstream.results import (
    MalformedOutputError,
    labeled_value,
    parse_loads,
    parse_probe_points,
)
from pyflightstream.workspace import RunRecord

__all__ = [
    "PROBE_COLUMN",
    "SECTIONS_SERIES_LEAD",
    "SERIES_DIR",
    "SERIES_KINDS",
    "SERIES_LEAD",
    "run_clock",
    "stamped_exports",
    "surface_export_metadata",
    "write_point_series",
]

#: The folder under a matrix's products where the series land.
SERIES_DIR = "series"
#: The kinds tabled, in the order written: the file suffix the solver
#: stamps, ``None`` being the loads spreadsheet's own name.
SERIES_KINDS: tuple[tuple[str, str | None], ...] = (
    ("loads", None),
    ("sections", "_sloads"),
    ("probes", "_probes"),
)
#: The three columns every series table leads with. `STEP` since 0.24.0, the ONE
#: name of the solver step across the package's tables; it was `step` here,
#: `ITERATION` in the sections table and `STEP` in the probe table.
SERIES_LEAD: tuple[str, ...] = ("STEP", "time_s", "azimuth_deg")
#: What a SECTIONS series row leads with (0.24.0): the step and its time, then
#: which distribution the row belongs to and where THAT rotor's blade one is.
#: `azimuth_deg`, the row clock's unwrapped angle, is not carried beside an
#: `AZIMUTH` that means something else.
SECTIONS_SERIES_LEAD: tuple[str, ...] = ("STEP", "time_s", "FAMILY", "PLANE", "ROTOR", "AZIMUTH")
#: The column saying WHICH probe a probes series row is (0.24.0), numbered from
#: one in the export's own order, as the probe table numbers them.
PROBE_COLUMN = "PROBE"
#: Native paths retained in the loads-series entry; Cp is also split by distribution.
#: The keys carry the package's own kind names (``cases.EXPORT_KINDS``):
#: ``sections`` is the ``_cp`` export and ``tecplot`` the ``.dat`` file.
LISTED_KINDS: tuple[tuple[str, str, str], ...] = (
    ("sections", "_cp", "txt"),
    ("tecplot", "", "dat"),
    ("vtk", "", "vtk"),
    ("csv", "", "csv"),
)

#: The columns of one loads spreadsheet row, in the solver's order.
LOADS_COLUMNS: tuple[str, ...] = ("Cx", "Cy", "Cz", "CL", "CDi", "CDo", "CMx", "CMy", "CMz")


def stamped_exports(
    sim_dir: Path, stem: str, *more: Path
) -> dict[tuple[str, str], dict[int, Path]]:
    """Return the stamped files of ``stem`` in ``sim_dir``, by (suffix, extension) then step.

    ``more`` are further folders to look in, a later one winning a step two hold.
    A SUBMITTED point runs in ``datapoints/DP-<tag>/`` since 0.18.1 and the solver
    stamps its per-step exports into its working directory, which collect does
    not move because they are not declared outputs; scanning the simulation
    folder alone found nothing of such a point.

    The suffix is ``""`` for the loads spreadsheet and the Tecplot file,
    ``_cp``, ``_sloads`` or ``_probes`` otherwise; the extension ``txt`` or
    ``dat``. The pattern is the one the tier-3 actions test reads the same
    folder with.
    """
    pattern = re.compile(
        rf"{re.escape(stem)}(_cp|_sloads|_probes)?_iteration=(\d+)\.(txt|dat|vtk|csv)$"
    )
    found: dict[tuple[str, str], dict[int, Path]] = {}
    folders: list[Path] = []
    for folder in (sim_dir, *more):
        if folder not in folders and folder.is_dir():
            folders.append(folder)
    for folder in folders:
        for path in sorted(folder.iterdir()):
            matched = pattern.match(path.name)
            if matched is None:
                continue
            suffix, step = matched.group(1) or "", int(matched.group(2))
            found.setdefault((suffix, matched.group(3)), {})[step] = path
    return found


def surface_export_metadata(record: RunRecord, *, step: int | None = None) -> dict[str, object]:
    """Describe a native surface export from the run's immutable averaging request."""
    stated = record.surface_time_averaging
    if stated is None:
        return {"kind": "instant"}
    window = dict(stated)
    bounds = stated["iterations"]
    first, last = int(bounds[0]), int(bounds[1])
    if step is None and record.stopped_at is not None:
        stopped = record.stopped_at.get("step")
        if isinstance(stopped, int | float) and not isinstance(stopped, bool):
            step = int(stopped)
    if step is not None:
        if step < first:
            return {
                "skipped": f"surface averaging starts at step {first}; export is at step {step}"
            }
        last = min(last, step)
    window["iterations"] = [first, last]
    return {"kind": "average", "window": window}


def run_clock(record: RunRecord) -> tuple[float | None, float | None]:
    """Return (delta_time_s, step_deg) as the record states them, or what it lets one infer.

    PUBLIC SINCE 0.23.0 ITEM 13, because the sections table needs the same
    answer. Reaching into a sibling module for an underscore-private name is
    the boundary this package already refuses for a helper, and the honest fix
    is to publish it: two functions computing one clock is how two products of
    the same point come to disagree about when it was sampled.

    A record written since 0.14.0 carries both in its export window; one
    written before carries neither, and its azimuth step is still known
    from the reductions plan's steps per revolution, while its time step
    is not known at all and the column is left unstated rather than guessed.

    UNSTATED HERE IS `NA` IN THE FILE, the same clause :func:`_lead` carries
    fifteen lines below: this returns a blank and the funnel renders it. The
    correction was applied to `_lead` alone when it was first made, in this
    same module, which is how one of two functions on one path ends up
    describing a product the other one writes.
    """
    window = record.export_window or {}
    delta = window.get("delta_time_s")
    step_deg = window.get("step_deg")
    if step_deg is None and isinstance(record.reductions, Mapping):
        per_revolution = record.reductions.get("steps_per_revolution")
        if isinstance(per_revolution, (int, float)) and per_revolution > 0:
            step_deg = 360.0 / float(per_revolution)
    return (
        float(delta) if isinstance(delta, (int, float)) else None,
        float(step_deg) if isinstance(step_deg, (int, float)) else None,
    )


def _lead(step: int, delta: float | None, step_deg: float | None) -> tuple[object, ...]:
    """Return the three lead cells of one row: the step, its time and its azimuth.

    THE BLANK RETURNED HERE IS NOT WHAT THE USER OPENS. A cell this leaves
    empty is rendered `NA` by the funnel in :mod:`pyflightstream.post._tables`,
    which every row of this table passes through, so the file says `NA` where
    this function says ``""``. The clause is here because the docstring said
    "or blank" and was true of the return value and false of the product, which
    is the half a reader of the file actually sees.
    """
    return (
        step,
        "" if delta is None else step * delta,
        "" if step_deg is None else step * step_deg,
    )


def _loads_rows(
    files: Mapping[int, Path],
    steps: range,
    delta: float | None,
    step_deg: float | None,
    context: tuple[object, ...],
    **_: object,
) -> tuple[tuple[str, ...], list[tuple[object, ...]]]:
    """One row per step, the coefficients of every surface and the Total, wide."""
    columns: list[str] = []
    rows: list[tuple[object, ...]] = []
    for step in steps:
        path = files.get(step)
        if path is None:
            continue
        try:
            report = parse_loads(path.read_text(encoding="utf-8", errors="replace"))
        except PyflightstreamError as error:
            raise ProductError(f"{path} is not a loads table: {error}") from error
        surfaces = {**report.surfaces, "Total": report.total}
        if not columns:
            columns = [f"{name}_{column}" for name in surfaces for column in LOADS_COLUMNS]
        elif list(surfaces) != _names(columns):
            # The wide table has one column set; a step whose surfaces differ
            # from the first would lose a surface or read as a missing
            # measurement, silently (the QA lens of REL-0140).
            first = ", ".join(repr(n) for n in _names(columns))
            raise ProductError(
                f"{path} lists the surfaces {', '.join(repr(n) for n in surfaces)} and the "
                f"first stamped step of the window lists {first}; a series is one column set "
                "over every step, so the window cannot be tabled as written"
            )
        values = [
            surfaces.get(name, {}).get(column, "")
            for name in _names(columns)
            for column in LOADS_COLUMNS
        ]
        rows.append((*_lead(step, delta, step_deg), *context, *values))
    return (*SERIES_LEAD, *CONTEXT_COLUMNS, *columns), rows


def _names(columns: list[str]) -> list[str]:
    """Return the surface names the wide columns were built from, in their order."""
    names: list[str] = []
    for column in columns:
        name = column.rsplit("_", 1)[0]
        if name not in names:
            names.append(name)
    return names


def _sections_rows(
    files: Mapping[int, Path],
    steps: range,
    delta: float | None,
    step_deg: float | None,
    context: tuple[object, ...],
    *,
    layout: Sequence[Mapping[str, object]] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
    **_: object,
) -> tuple[tuple[str, ...], list[tuple[object, ...]]]:
    """One row per step and section: its block's identity, the condition, the export's seven.

    The identity is the sections table's own (RI-04), from the same function: a
    series that named its blocks another way would be a second reading of one
    export.
    """
    columns = (*SECTIONS_SERIES_LEAD, *CONTEXT_COLUMNS, *SECTION_COLUMNS[-7:])
    rows: list[tuple[object, ...]] = []
    for step in steps:
        path = files.get(step)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            declared = int(float(labeled_value(text, "Number of Surface Sections:")))
        except (MalformedOutputError, ValueError):
            declared = -1
        if declared == 0:
            continue
        try:
            report = parse_sectional_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{path} is not a sectional loads export: {error}") from error
        identity = section_identity(len(report.values), layout, rotors, step, None)
        lead = _lead(step, delta, step_deg)[:2]
        for at, values in enumerate(report.values):
            rows.append((*lead, *identity[at], *context, *(float(v) for v in values[:7])))
    return columns, rows


def _probes_rows(
    files: Mapping[int, Path],
    steps: range,
    delta: float | None,
    step_deg: float | None,
    context: tuple[object, ...],
    **_: object,
) -> tuple[tuple[str, ...], list[tuple[object, ...]]]:
    """One row per step and probe, the export's own columns; a run with no probe has none."""
    columns: tuple[str, ...] = ()
    rows: list[tuple[object, ...]] = []
    for step in steps:
        path = files.get(step)
        if path is None:
            continue
        try:
            report = parse_probe_points(path.read_text(encoding="utf-8", errors="replace"))
        except PyflightstreamError as error:
            raise ProductError(f"{path} is not a probe points export: {error}") from error
        if not columns:
            columns = tuple(report.columns)
        # WHICH PROBE (RI-06). Twelve rows of one step were told apart by their
        # order, which is not a table.
        for number, values in enumerate(report.values.tolist(), start=1):
            rows.append((*_lead(step, delta, step_deg), number, *context, *values))
    return (*SERIES_LEAD, PROBE_COLUMN, *CONTEXT_COLUMNS, *columns), rows


_ROWS: dict[str, Callable[..., tuple[tuple[str, ...], list[tuple[object, ...]]]]] = {
    "loads": _loads_rows,
    "sections": _sections_rows,
    "probes": _probes_rows,
}


def write_point_series(
    root: Path,
    *,
    sim_dir: Path,
    record: RunRecord,
    stem: str,
    out: Path,
    overwrite: bool = False,
    target: Callable[[Path], Path] | None = None,
    condition: Mapping[str, object] | None = None,
    reference: Mapping[str, object] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
    skipped: dict[str, str] | None = None,
    surface_exports: dict[str, dict[str, object]] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write the series tables of one point from its stamped exports.

    ``condition`` and ``reference`` are the point's, as every other product of it
    states them (0.24.0); without them the cells read `NA`. ``rotors`` is what
    the sections identity needs of each rotor, as
    :func:`~pyflightstream.post.products.write_sections_table` takes it.

    ``surface_exports``, when given, receives manifest entries for native
    Tecplot, VTK and CSV files. Those files are listed, not rewritten, and
    are separate from the returned tables and their entries.

    A KIND WITH NO STAMPED FILE IS NOT WRITTEN (0.24.0). It used to be a table of
    a header and no row, recorded in the manifest as written; ``skipped``, when
    given, receives the reason under the table's own name.

    Parameters
    ----------
    root : Path
        The workspace root, which the listed files are named relative to.
    sim_dir : Path
        The simulation folder, where the solver left the stamped files.
    record : RunRecord
        The point's run record; its ``export_window`` says which steps
        exist and, since 0.14.0, the clock they were stepped with.
    stem : str
        The point's name, the loads spreadsheet's name without ``.txt``.
    out : Path
        The matrix's products folder; the tables land under ``series/``.
    overwrite : bool
        Consulted only when ``target`` is None: whether an existing table
        may be rewritten, refused otherwise with
        :class:`~pyflightstream.post.products.ProductExistsError`.
    target : callable, optional
        Called with each table's path before that table is written, and the
        table is written to the path it returns, and its entry is keyed by
        that path: the same seam
        :func:`~pyflightstream.post.superfile.write_superfiles` takes. When
        it is given, IT ALONE decides what becomes of an existing table and
        ``overwrite`` is not consulted, which is the rule every other product
        of the stage follows. The products stage passes its archiver, which
        moves an existing table into ``series/archive/<day and hour>/``, or,
        called with ``archive=False``, leaves it to be overwritten.

    Returns
    -------
    tuple
        The tables written, and their ``products.json`` entries keyed by the
        path each was written to, relative to ``out`` (absolute when a
        target wrote it outside ``out``): the runs, the steps tabled, the steps the
        window states, and on the loads entry the sections (``_cp``) and
        Tecplot (``.dat``) files of the window by path, under
        ``sections_files`` and ``tecplot_files``.
    """
    window = record.export_window
    if not window:
        return [], {}
    first, last = int(window["first_step"]), int(window["time_iterations"])
    steps = range(first, last + 1)
    delta, step_deg = run_clock(record)
    # WHERE THE POINT RAN, as its own outputs state it: the simulation folder for a
    # local run, its datapoint folder for a submitted one (MT-06).
    ran_in = [sim_dir / Path(output).parent for output in record.outputs]
    stamped = stamped_exports(sim_dir, stem, *ran_in)
    context = context_row(condition, reference)
    written: list[Path] = []
    names: dict[str, dict[str, object]] = {}
    if surface_exports is not None:
        for kind, listed_suffix, extension in LISTED_KINDS:
            if kind == "sections":
                continue
            for step, path in stamped.get((listed_suffix, extension), {}).items():
                if step not in steps:
                    continue
                relative = Path(os.path.relpath(path, out)).as_posix()
                metadata = surface_export_metadata(record, step=step)
                if "skipped" in metadata:
                    if skipped is not None:
                        skipped[relative] = str(metadata["skipped"])
                    continue
                surface_exports[relative] = {
                    "runs": [record.run_id],
                    "format": kind,
                    "step": step,
                    **metadata,
                }
    for kind, suffix in SERIES_KINDS:
        files = stamped.get((suffix or "", "txt"), {})
        relative = f"{SERIES_DIR}/{stem}_{kind}_series.csv"
        if not any(step in files for step in steps):
            if skipped is not None:
                looked = ", ".join(str(folder) for folder in dict.fromkeys([sim_dir, *ran_in]))
                skipped[relative] = (
                    f"no {stem}{suffix or ''}_iteration=<step>.txt of steps {first} to {last} "
                    f"is in {looked}, so there is no row to table"
                )
            continue
        columns, rows = _ROWS[kind](
            files, steps, delta, step_deg, context, layout=record.sections_layout, rotors=rotors
        )
        path = out / relative
        # THE TARGET DECIDES, AND DECIDES ALONE. Until 2026-09-14 the products
        # stage accepted `archive` and never passed it here, so a rebuild
        # archived every product but these, which it rewrote in place:
        # measured on a rotor campaign rebuilt twice, four folders gained
        # archive/ and series/ did not. The overwrite gate is skipped when a
        # target is given, because running both split one rebuild in two
        # (the API, QA and architecture lenses): archive=False with
        # overwrite=False rewrote every other product and then refused these.
        if target is not None:
            path = target(path)
        elif path.exists() and not overwrite:
            raise ProductExistsError(
                f"the product {path} exists; pass overwrite=True to rewrite it from the "
                "manifest, or a target that decides what becomes of it (the products stage "
                "passes one that archives it first)"
            )
        done = write_csv_table(path, columns, rows)
        written.append(done)
        tabled = sorted(step for step in steps if step in files)
        entry: dict[str, object] = {
            "runs": [record.run_id],
            "steps": [first, last],
            "steps_tabled": tabled,
            "clock": {"delta_time_s": delta, "step_deg": step_deg},
        }
        if kind == "loads":
            for listed, listed_suffix, extension in LISTED_KINDS:
                found = stamped.get((listed_suffix, extension), {})
                entry[f"{listed}_files"] = [
                    found[step].relative_to(root).as_posix() for step in steps if step in found
                ]
        # KEYED BY WHERE THE TABLE WENT, as write_superfiles keys its entries
        # (the API lens, round two): keyed by the path asked for, a target that
        # redirected left products.json naming a file that does not exist.
        key = done.relative_to(out) if done.is_relative_to(out) else done
        names[key.as_posix()] = entry
    return written, names
