"""The per-step exports of an unsteady point as a series (PFS-2031.18.01).

A row stating ``EXPORT_UNSTEADY_AFTER_REV`` or ``EXPORT_UNSTEADY_AFTER_ITER``
has the solver export its loads, sectional loads and probe points on every
step from the threshold on, each file stamped ``_iteration=N`` beside the
simulation (RPT-041 finding 3). Those files are what the author's incidence study
reads, one revolution after another, and a folder of forty stamped
spreadsheets is not a series until something tables them: this module
writes, per point, one table per export kind under ``post/<matrix
stem>/series/``, a row per step (and per surface, section or probe where
the export carries several), the step's time and azimuth from the clock the
run record carries, which is the same arithmetic the counter program runs
on the machine (``run/_actions_counter.py``, ``state()``), so the series and
the counter agree by construction.

The Tecplot ``.dat`` and the ``_cp`` files of the window are listed in
``products.json`` by path and not tabled: they are the solver's own
formats, and a table of either would be a second format of one thing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path

from pyflightstream._errors import PyflightstreamError
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.post._tables import (
    SECTION_COLUMNS,
    ProductError,
    ProductExistsError,
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
    "SERIES_DIR",
    "SERIES_KINDS",
    "SERIES_LEAD",
    "stamped_exports",
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
#: The three columns every series table leads with.
SERIES_LEAD: tuple[str, ...] = ("step", "time_s", "azimuth_deg")
#: The stamped kinds that are listed by path and not tabled.
#: The keys carry the package's own kind names (``cases.EXPORT_KINDS``):
#: ``sections`` is the ``_cp`` export and ``tecplot`` the ``.dat`` file.
LISTED_KINDS: tuple[tuple[str, str, str], ...] = (
    ("sections", "_cp", "txt"),
    ("tecplot", "", "dat"),
)

#: The columns of one loads spreadsheet row, in the solver's order.
LOADS_COLUMNS: tuple[str, ...] = ("Cx", "Cy", "Cz", "CL", "CDi", "CDo", "CMx", "CMy", "CMz")


def stamped_exports(sim_dir: Path, stem: str) -> dict[tuple[str, str], dict[int, Path]]:
    """Return the stamped files of ``stem`` in ``sim_dir``, by (suffix, extension) then step.

    The suffix is ``""`` for the loads spreadsheet and the Tecplot file,
    ``_cp``, ``_sloads`` or ``_probes`` otherwise; the extension ``txt`` or
    ``dat``. The pattern is the one the tier-3 actions test reads the same
    folder with.
    """
    pattern = re.compile(rf"{re.escape(stem)}(_cp|_sloads|_probes)?_iteration=(\d+)\.(txt|dat)$")
    found: dict[tuple[str, str], dict[int, Path]] = {}
    for path in sorted(sim_dir.iterdir()) if sim_dir.is_dir() else ():
        matched = pattern.match(path.name)
        if matched is None:
            continue
        suffix, step, extension = matched.group(1) or "", int(matched.group(2)), matched.group(3)
        found.setdefault((suffix, extension), {})[step] = path
    return found


def _clock(record: RunRecord) -> tuple[float | None, float | None]:
    """Return (delta_time_s, step_deg) as the record states them, or what it lets one infer.

    A record written since 0.14.0 carries both in its export window; one
    written before carries neither, and its azimuth step is still known
    from the reductions plan's steps per revolution, while its time step
    is not known at all and the column stays empty rather than guessed.
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
    """Return the three lead cells of one row: the step, its time and its azimuth, or blank."""
    return (
        step,
        "" if delta is None else step * delta,
        "" if step_deg is None else step * step_deg,
    )


def _loads_rows(
    files: Mapping[int, Path], steps: range, delta: float | None, step_deg: float | None
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
        rows.append((*_lead(step, delta, step_deg), *values))
    return (*SERIES_LEAD, *columns), rows


def _names(columns: list[str]) -> list[str]:
    """Return the surface names the wide columns were built from, in their order."""
    names: list[str] = []
    for column in columns:
        name = column.rsplit("_", 1)[0]
        if name not in names:
            names.append(name)
    return names


def _sections_rows(
    files: Mapping[int, Path], steps: range, delta: float | None, step_deg: float | None
) -> tuple[tuple[str, ...], list[tuple[object, ...]]]:
    """One row per step and section, the export's own seven columns."""
    columns = (*SERIES_LEAD, *SECTION_COLUMNS[-7:])
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
        for values in report.values:
            rows.append((*_lead(step, delta, step_deg), *(float(v) for v in values[:7])))
    return columns, rows


def _probes_rows(
    files: Mapping[int, Path], steps: range, delta: float | None, step_deg: float | None
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
        for values in report.values.tolist():
            rows.append((*_lead(step, delta, step_deg), *values))
    return (*SERIES_LEAD, *columns), rows


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
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write the series tables of one point from its stamped exports.

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
        Whether an existing table may be rewritten; refused otherwise
        with :class:`~pyflightstream.post.products.ProductExistsError`,
        the products stage's own rule.

    Returns
    -------
    tuple
        The tables written, and their ``products.json`` entries keyed by
        path relative to ``out``: the runs, the steps tabled, the steps the
        window states, and on the loads entry the sections (``_cp``) and
        Tecplot (``.dat``) files of the window by path, under
        ``sections_files`` and ``tecplot_files``.
    """
    window = record.export_window
    if not window:
        return [], {}
    first, last = int(window["first_step"]), int(window["time_iterations"])
    steps = range(first, last + 1)
    delta, step_deg = _clock(record)
    stamped = stamped_exports(sim_dir, stem)
    written: list[Path] = []
    names: dict[str, dict[str, object]] = {}
    for kind, suffix in SERIES_KINDS:
        files = stamped.get((suffix or "", "txt"), {})
        columns, rows = _ROWS[kind](files, steps, delta, step_deg)
        relative = f"{SERIES_DIR}/{stem}_{kind}_series.csv"
        path = out / relative
        if path.exists() and not overwrite:
            raise ProductExistsError(
                f"the product {path} exists; pass overwrite (CLI: --overwrite) to rewrite "
                "it from the manifest"
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
        names[relative] = entry
    return written, names
