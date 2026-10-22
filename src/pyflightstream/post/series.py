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
from pyflightstream._tokens import NOT_APPLICABLE, POLAR_ID_COLUMN
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
    DRAG_PAIRS,
    NOT_CARRIED_BY_THE_VTK,
    LoadsReport,
    MalformedOutputError,
    drag_pair,
    labeled_value,
    parse_loads,
    parse_probe_points,
)
from pyflightstream.results.sectional_loads import parse_sectional_loads
from pyflightstream.workspace import AdditionalRecord, RunRecord
from pyflightstream.workspace.storage import pruned_step_refusal

__all__ = [
    "PROBE_COLUMN",
    "SECTIONS_SERIES_LEAD",
    "SERIES_DIR",
    "SERIES_KINDS",
    "SERIES_LEAD",
    "run_clock",
    "stamped_exports",
    "surface_export_metadata",
    "translated_surface",
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
#: The three columns every series table leads with, after `POL` (the polar, first
#: in every table the post writes ). `STEP` the ONE
#: name of the solver step across the package's tables; it was `step` here,
#: `ITERATION` in the sections table and `STEP` in the probe table.
SERIES_LEAD: tuple[str, ...] = ("STEP", "time_s", "azimuth_deg")
#: What a SECTIONS series row leads with after `POL`: the step and its time, then
#: which distribution the row belongs to and where THAT rotor's blade one is.
#: `azimuth_deg`, the row clock's unwrapped angle, is not carried beside an
#: `AZIMUTH` that means something else.
SECTIONS_SERIES_LEAD: tuple[str, ...] = ("STEP", "time_s", "FAMILY", "PLANE", "ROTOR", "AZIMUTH")
#: The column saying WHICH probe a probes series row is, numbered from
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

#: The columns of one loads spreadsheet row, in the solver's order, as the recorded
#: 26.123 and 26.124 print them. 26.125 prints its drag split ``CDp, CDv`` in
#: the places of ``CDi, CDo`` (FR-423; RPT-160, "FlightStream 26.125 registered from
#: its manual and its outputs", 2026-10-05), and a series carries the names its
#: steps printed (:func:`_printed_loads_columns`).
LOADS_COLUMNS: tuple[str, ...] = ("Cx", "Cy", "Cz", "CL", "CDi", "CDo", "CMx", "CMy", "CMz")


def _printed_loads_columns(report: LoadsReport) -> tuple[str, ...]:
    """Return :data:`LOADS_COLUMNS` with the drag split the table printed (FR-423)."""
    printed = dict(zip(DRAG_PAIRS[0], drag_pair(report.total), strict=True))
    return tuple(printed.get(column, column) for column in LOADS_COLUMNS)


def stamped_exports(
    sim_dir: Path, stem: str, *more: Path
) -> dict[tuple[str, str], dict[int, Path]]:
    """Return the stamped files of ``stem`` in ``sim_dir``, by (suffix, extension) then step.

    ``more`` are further folders to look in, a later one winning a step two hold.
    A SUBMITTED point runs in ``datapoints/DP-<tag>/`` and the solver
    stamps its per-step exports into its working directory, which collect does
    not move because they are not declared outputs; scanning the simulation
    folder alone found nothing of such a point.

    The suffix is ``""`` for the loads spreadsheet and the Tecplot file,
    ``_cp``, ``_sloads`` or ``_probes`` otherwise; the extension ``txt`` or
    ``dat``. The pattern is the one the tier-3 actions test reads the same
    folder with.

    Parameters
    ----------
    sim_dir : Path
        The simulation folder.
    stem : str
        The point's file stem.
    *more : Path
        Further folders to look in.

    Returns
    -------
    dict of (str, str) to dict of int to Path
        (suffix, extension) to the file of each step.
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
    """Describe a native surface export from the run's immutable averaging request.

    Parameters
    ----------
    record : RunRecord
        The point's run record.
    step : int, optional
        The step of the export described.

    Returns
    -------
    dict of str to object
        ``{'kind': 'average', 'window': ...}``, ``{'kind': 'instant'}``, or why the export is
        skipped.
    """
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


#: The stamp an unsteady action's export carries before its extension (RPT-041).
_STAMPED = re.compile(r"^(?P<stem>.+)_iteration=(?P<step>\d+)$")
#: A ``DATASETAUXDATA`` record of a Tecplot file: its name and its quoted value.
_AUXDATA = re.compile(r'^DATASETAUXDATA\s+(?P<name>\w+)\s*=\s*"(?P<value>[^"]*)"\s*$')


def _stated_auxdata(path: Path) -> dict[str, str]:
    """Return the DATASETAUXDATA records of a Tecplot header, read to its first row of numbers."""
    stated: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                found = _AUXDATA.match(stripped)
                if found is not None:
                    stated[found.group("name")] = found.group("value")
                elif stripped and stripped[0] in "0123456789+-.":
                    break  # the first row of numbers ends the header, however long
    except OSError:
        return {}
    return stated


def translated_surface(record: RunRecord | AdditionalRecord, path: Path) -> dict[str, object]:
    """Say what a Tecplot surface the package wrote from a VTK is (G45).

    Empty for a ``.dat`` the solver wrote, which is every Tecplot of a record
    written in legacy releases: nothing about it changed. For one the run wrote from
    its VTK, at the end of the run or stamped at a step: ``translated_from``,
    the VTK beside it; ``source_sha256``, that VTK's sha256 as the ``.dat``
    itself states it (``NA`` where the file cannot be read); ``location``
    ``cell-centred``; ``frame`` ``reference``; and ``not_carried``, the solver
    Tecplot's variables the VTK does not hold.

    Parameters
    ----------
    record : RunRecord or AdditionalRecord
        The record whose run wrote the file.
    path : Path
        The Tecplot file.

    Returns
    -------
    dict of str to object
        The translation's metadata; empty for a Tecplot the solver wrote.
    """
    translations = record.surface_translations or []
    stamped = _STAMPED.match(path.stem)
    for translation in translations:
        if not isinstance(translation, Mapping):
            continue
        dat, vtk = Path(str(translation.get("dat"))), Path(str(translation.get("vtk")))
        if path.suffix.lower() != dat.suffix.lower():
            continue
        if path.stem == dat.stem:
            source = vtk.name
        elif stamped is not None and stamped.group("stem") == dat.stem:
            source = f"{vtk.stem}_iteration={stamped.group('step')}{vtk.suffix}"
        else:
            continue
        stated = _stated_auxdata(path)
        metadata: dict[str, object] = {
            "translated_from": source,
            "source_sha256": stated.get("SOURCE_VTK_SHA256", NOT_APPLICABLE),
            "location": "cell-centred",
            "frame": "reference",
            "not_carried": list(NOT_CARRIED_BY_THE_VTK),
        }
        native = stated.get("SOURCE_NATIVE_TECPLOT")
        native_hash = stated.get("SOURCE_NATIVE_TECPLOT_SHA256")
        if native and native_hash:
            metadata.update(
                native_source=native,
                native_source_sha256=native_hash,
                nodal_variables=["Singularity_strength"],
                not_carried=[],
                location="mixed nodal and cell-centred",
            )
        return metadata
    return {}


def run_clock(record: RunRecord) -> tuple[float | None, float | None]:
    """Return (delta_time_s, step_deg) as the record states them, or what it lets one infer.

    Public because the sections table needs the same
    answer. Reaching into a sibling module for an underscore-private name is
    the boundary this package already refuses for a helper, and the honest fix
    is to publish it: two functions computing one clock is how two products of
    the same point come to disagree about when it was sampled.

    A record with a declared clock carries both in its export window; one
    without a declared clock carries neither, and its azimuth step is still known
    from the reductions plan's steps per revolution, while its time step
    is not known at all and the column is left unstated rather than guessed.

    THE AZIMUTH STEP IS UNSIGNED. The recorded ``step_deg`` of an export window and the
    inferred ``360 / steps_per_revolution`` both carry the size of one step and not the
    sense the rotor turns, so a series azimuth is the step times that size, degrees of turn
    counted from step zero, and says nothing of which way the rotor spins (X-F-0355).

    UNSTATED HERE IS `NA` IN THE FILE, the same clause :func:`_lead` carries
    fifteen lines below: this returns a blank and the funnel renders it. The
    correction was applied to `_lead` alone when it was first made, in this
    same module, which is how one of two functions on one path ends up
    describing a product the other one writes.

    Parameters
    ----------
    record : RunRecord
        The point's run record.

    Returns
    -------
    tuple of (float or None, float or None)
        The time step in seconds and the azimuth step in degrees, None where not known.
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
    loads_columns: tuple[str, ...] = ()
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
            loads_columns = _printed_loads_columns(report)
            columns = [f"{name}_{column}" for name in surfaces for column in loads_columns]
        elif _printed_loads_columns(report) != loads_columns:
            raise ProductError(
                f"{path} prints the drag split {', '.join(drag_pair(report.total))} and the "
                "first stamped step of the window another; a series is one column set over "
                "every step, so post the steps of one build together"
            )
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
            for column in loads_columns
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
        elif tuple(report.columns) != columns:
            # The rows are written under the FIRST step's header, so a step printing
            # other columns (another build, another probe export) would put its values
            # under names that are not theirs.
            raise ProductError(
                f"{path} prints the probe columns {', '.join(report.columns)} and the first "
                f"stamped step of the window prints {', '.join(columns)}; a series is one "
                "column set over every step, so post the steps of one build together"
            )
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


def _surface_export_entries(
    surface_exports: dict[str, dict[str, object]],
    stamped: Mapping[tuple[str, str], Mapping[int, Path]],
    steps: range,
    record: RunRecord,
    out: Path,
    *,
    skipped: dict[str, str] | None,
) -> None:
    """Fill the manifest entries of the native Tecplot, VTK and CSV files of the window."""
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
                **(translated_surface(record, path) if kind == "tecplot" else {}),
            }


def _series_destination(path: Path, target: Callable[[Path], Path] | None, overwrite: bool) -> Path:
    """Return where a series table is written, refusing an unowned existing one.

    An explicit ``target`` owns the archive and overwrite policy, so the series
    follows the same rebuild policy as the other products; without one an
    existing table is refused unless ``overwrite`` is set.
    """
    if target is not None:
        return target(path)
    if path.exists() and not overwrite:
        raise ProductExistsError(
            f"the product {path} exists; pass overwrite=True to rewrite it from the "
            "manifest, or a target that decides what becomes of it (the products stage "
            "passes one that archives it first)"
        )
    return path


def _listed_files(
    stamped: Mapping[tuple[str, str], Mapping[int, Path]], steps: range, out: Path
) -> dict[str, list[str]]:
    """Return the listed native files of the window by step, relative to ``out``."""
    listed_files: dict[str, list[str]] = {}
    for listed, listed_suffix, extension in LISTED_KINDS:
        found = stamped.get((listed_suffix, extension), {})
        listed_files[f"{listed}_files"] = [
            Path(os.path.relpath(found[step], out)).as_posix() for step in steps if step in found
        ]
    return listed_files


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
    failed: dict[str, str] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write the series tables of one point from its stamped exports.

    ``condition`` and ``reference`` are the point's, as every other product of it
    states them; without them the cells read `NA`. ``rotors`` is what
    the sections identity needs of each rotor, as
    :func:`~pyflightstream.post.products.write_sections_table` takes it.

    ``surface_exports``, when given, receives manifest entries for native
    Tecplot, VTK and CSV files. Those files are listed, not rewritten, and
    are separate from the returned tables and their entries.

    A KIND WITH NO STAMPED FILE IS NOT WRITTEN. ``skipped``, when
    given, receives the reason under the table's own name.

    A STEP OF THE WINDOW THAT ``free-space`` DELETED (``prune_step_exports``) refuses that
    kind's table, naming the step and the storage call,
    under the same name in ``skipped``, or as a
    :class:`~pyflightstream._errors.ProductError` when no ``skipped`` is given.

    Parameters
    ----------
    root : Path
        The workspace root. Listed files, like product keys, are named
        relative to ``out``, the matrix's products folder.
    sim_dir : Path
        The simulation folder, where the solver left the stamped files.
    record : RunRecord
        The point's run record; its ``export_window`` says which steps
        exist and the clock they were stepped with.
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
    condition : mapping of str to object, optional
        The point's condition, as every product of it states it.
    reference : mapping of str to object, optional
        The point's reference dimensions.
    rotors : mapping of str to mapping, optional
        What the sections identity needs of each rotor.
    skipped : dict of str to str, optional
        Receives the reason a kind is not written, under the table's name.
    surface_exports : dict of str to dict, optional
        Receives the manifest entries of the native Tecplot, VTK and CSV files.
    failed : dict of str to str, optional
        Receives, under the table's name, the refusal of a kind whose stamped
        files cannot be read, and the other kinds are still written. Without it
        that refusal is raised and no table of the point is returned.

    Returns
    -------
    tuple
        The tables written, and their ``products.json`` entries keyed by the
        path each was written to, relative to ``out`` (absolute when a
        target wrote it outside ``out``): the runs, the steps tabled, the steps the
        window states, and on the loads entry the sections (``_cp``) and
        Tecplot (``.dat``) files of the window by path, under
        ``sections_files`` and ``tecplot_files``.

    Raises
    ------
    ProductError
        If a step of the window was deleted by ``free-space`` and no ``skipped`` is given.
    ProductExistsError
        If a table exists, no ``target`` is given and ``overwrite`` is not set.
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
        _surface_export_entries(surface_exports, stamped, steps, record, out, skipped=skipped)
    for kind, suffix in SERIES_KINDS:
        files = stamped.get((suffix or "", "txt"), {})
        relative = f"{SERIES_DIR}/{stem}_{kind}_series.csv"
        # A STEP FREE-SPACE DELETED IS A REFUSAL, NAMED, never the
        # silent gap a series of the steps that remain would be. A step that
        # was never exported keeps the rule it always had.
        pruned = pruned_step_refusal(
            sim_dir,
            record.run_id,
            {
                step: [folder / f"{stem}{suffix or ''}_iteration={step}.txt" for folder in ran_in]
                + [sim_dir / f"{stem}{suffix or ''}_iteration={step}.txt"]
                for step in steps
                if step not in files
            },
            product=relative,
            window=(first, last),
        )
        if pruned is not None:
            if skipped is None:
                raise ProductError(pruned)
            skipped[relative] = pruned
            continue
        if not any(step in files for step in steps):
            if skipped is not None:
                looked = ", ".join(str(folder) for folder in dict.fromkeys([sim_dir, *ran_in]))
                skipped[relative] = (
                    f"no {stem}{suffix or ''}_iteration=<step>.txt of steps {first} to {last} "
                    f"is in {looked}, so there is no row to table"
                )
            continue
        try:
            columns, rows = _ROWS[kind](
                files, steps, delta, step_deg, context, layout=record.sections_layout, rotors=rotors
            )
        except ProductExistsError:
            raise
        except ProductError as error:
            # ONE KIND'S UNREADABLE FILE costs that kind, not the kinds read
            # from other files, when the caller collects the refusals.
            if failed is None:
                raise
            failed[relative] = str(error)
            continue
        path = _series_destination(out / relative, target, overwrite)
        # THE POLAR FIRST (G16), the run record's own: every row of a
        # series is a step of this one point.
        done = write_csv_table(
            path, (POLAR_ID_COLUMN, *columns), [(record.sim_id, *row) for row in rows]
        )
        written.append(done)
        # THE STEPS THE ROWS HOLD, every series leading with its STEP: a step
        # whose export declared no section has a file and no row (PFS-2105.038).
        tabled = sorted({int(str(row[0])) for row in rows})
        entry: dict[str, object] = {
            "runs": [record.run_id],
            "steps": [first, last],
            "steps_tabled": tabled,
            "clock": {"delta_time_s": delta, "step_deg": step_deg},
            **(_listed_files(stamped, steps, out) if kind == "loads" else {}),
        }
        # KEYED BY WHERE THE TABLE WENT, as write_superfiles keys its entries
        # (the API lens, round two): keyed by the path asked for, a target that
        # redirected left products.json naming a file that does not exist.
        key = done.relative_to(out) if done.is_relative_to(out) else done
        names[key.as_posix()] = entry
    return written, names
