"""What a campaign plan reports per point, and the lines its summary prints.

Private to :mod:`pyflightstream.run`, whose plan module re-exports every
public name of it. :func:`point_facts` reads a point's rotors, quasi-steady
wheel, wake, streamlines, far field and default angles from its case; the
``*_line`` functions turn those records into the words the plan summary prints.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pyflightstream._errors import EmptySelectionWarning, InputValueError, NotApplicableWarning
from pyflightstream.cases import SimCase
from pyflightstream.cases.matrix import MatrixRow, read_matrix
from pyflightstream.cases.qsteady import summarise as summarise_validity
from pyflightstream.cases.qsteady import summarise_inflow_harmonics
from pyflightstream.cases.workflows import (
    WakeTermination,
    angles_not_stated,
    planned_run_wake,
    planned_wake,
    qsteady_validity,
    rotor_machs,
    streamline_count,
)
from pyflightstream.cases.workflows import plan_record as farfield_plan_record
from pyflightstream.workspace import matrix_files
from pyflightstream.workspace._matrix_homes import every_matrix, matrix_path, matrix_stem
from pyflightstream.workspace.cli import add_console_arguments
from pyflightstream.workspace.naming import sweep_file_stem

PointPlan = Any  # the PointPlan of run._plan, which imports this module


def _point_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the per-point lines of the plan's summary in display order."""
    lines = boundaries_lines(points)
    lines += _mach_lines(points)
    lines += _validity_lines(points)
    lines += _wake_lines(points)
    lines += _angle_lines(points)
    return lines + _streamline_lines(points) + _farfield_lines(points)


def boundaries_lines(points: Sequence[PointPlan]) -> list[str]:
    """Name the selected boundaries file once per planned row."""
    return list(
        dict.fromkeys(
            f"  POL {point.sim_id}: boundaries read from {point.boundaries_file}"
            for point in points
            if point.boundaries_file
        )
    )


def _mach_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the line of each rotor of each point: tip and helical Mach numbers (M1)."""
    return [
        f"  {entry.run_id}: {rotor_mach_line(alias, mach)}"
        for entry in points
        for alias, mach in entry.rotor_mach.items()
    ]


def _validity_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the lines of every quasi-steady wheel point.

    Each states the four values of its blade's 1P reduced frequency, or why the
    chord is not known.
    """
    lines: list[str] = []
    for entry in points:
        if entry.qsteady_validity:
            lines.append(f"  {entry.run_id}: {qsteady_validity_line(entry.qsteady_validity)}")
            harmonics = entry.qsteady_validity.get("inflow_fft")
            if isinstance(harmonics, Mapping):
                lines.append(f"  {entry.run_id}: {inflow_harmonics_line(harmonics)}")
    return lines


def _wake_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the wake termination line of each rotor point (FR-584), then the run length lines.

    A run length stated as a wake length states its count (FR-906).
    """
    lines = [
        f"  {entry.run_id}: {wake_termination_line(entry.wake_termination)}"
        for entry in points
        if entry.wake_termination
    ]
    lines += [
        f"  {entry.run_id}: {run_wake_length_line(entry.run_wake_length)}"
        for entry in points
        if entry.run_wake_length
    ]
    return lines


def _angle_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the line of each point whose flow angles take the default 0.0 degrees (FR-69)."""
    lines: list[str] = []
    for entry in points:
        if entry.angles_not_stated:
            shown = ", ".join(f"{name} = 0.0 (default)" for name in entry.angles_not_stated)
            lines.append(f"  {entry.run_id}: {shown}; the row states no such angle")
    return lines


def _streamline_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the plan's line per point that seeds off-body streamlines (FR-1079)."""
    return [
        f"  {entry.run_id}: {entry.streamlines} off-body streamlines traced "
        "(the [streamlines] lines and tubes of its pproc)"
        for entry in points
        if entry.streamlines
    ]


def _farfield_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return one line per far-field input a plan adds or cannot serve (FR-1047)."""
    lines: list[str] = []
    for entry in points:
        inputs = entry.farfield.get("inputs", ()) if entry.farfield else ()
        for item in cast(Sequence[Mapping[str, object]], inputs):
            if item.get("state") in ("added", "not_applicable", "refused"):
                lines.append(f"  {entry.run_id}: far field {farfield_line(item)}")
    return lines


def farfield_line(item: Mapping[str, object]) -> str:
    """Return one far-field input of the plan as its console line (FR-1047)."""
    what = item.get("source") or item.get("reason") or ""
    return (
        f"entry {item.get('entry')!r} ({item.get('variant')}) "
        f"{item.get('input')} {item.get('state')}: {what}"
    ).rstrip(": ")


def run_wake_length_line(run: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's run length from a wake length (FR-422).

    ``run`` is one :attr:`PointPlan.run_wake_length`: the length asked, the
    resolved step count and the revolutions it turns, and the V_ax with the
    rule that gave it. The length is nominal (FR-908), so the revolutions are
    what a user checks near hover.
    """
    return (
        f"run length RUN_WAKE_LENGTH_R = {run.get('length_r'):g} R: "
        f"{run.get('time_iterations')} steps, {run.get('revolutions'):.4g} revolution(s), "
        f"V_ax {run.get('v_ax_m_s'):.4g} m/s ({run.get('rule')}); "
        "nominal helical travel, not a measured wake length"
    )


def wake_termination_line(wake: Mapping[str, object]) -> str:
    """Return the words the plan prints for one rotor point's wake termination (FR-584).

    ``wake`` is one :attr:`PointPlan.wake_termination`: the L asked, the V_ax
    used with the rule that gave it, and the steps emitted; a count states
    itself, its steps and the length it keeps over the run (FR-601).
    """
    steps, length, speed = wake.get("steps"), wake.get("length_r"), wake.get("v_ax_m_s")
    if not isinstance(length, int | float):
        kept = WakeTermination(**cast(dict[str, Any], wake)).count_kept_r()
        keeps = "an unknown length" if kept is None else f"about {kept:.3g} R"
        return f"wake termination {wake.get('stated_as')}: {steps} steps, keeping {keeps} of wake"
    if steps is None:
        return (
            f"wake termination L = {length:g} R ({wake.get('stated_as')}) not converted: "
            "no rotor radius is known, so no termination line is written"
        )
    used = f"{speed:.4g} m/s" if isinstance(speed, int | float) else "none"
    return (
        f"wake termination L = {length:g} R ({wake.get('stated_as')}), V_ax {used} "
        f"({wake.get('rule')}), {steps} steps"
    )


def qsteady_validity_line(validity: Mapping[str, object]) -> str:
    """Return the words the plan prints for one quasi-steady wheel point.

    ``validity`` is one :attr:`PointPlan.qsteady_validity`.
    """
    note = validity.get("note")
    if note:
        root, tip = validity.get("k_per_chord_m_root"), validity.get("k_per_chord_m_tip")
        known = (
            f"; k per metre of chord {root:.4f} at the root, {tip:.4f} at the tip"
            if isinstance(root, int | float) and isinstance(tip, int | float)
            else ""
        )
        return f"quasi-steady validity not computed: {note}{known}"
    return f"quasi-steady validity (1P reduced frequency): {summarise_validity(validity)}"


def inflow_harmonics_line(harmonics: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's ``--inflow-fft`` record.

    nP is counted on ONE BLADE (how many times it meets the perturbation per
    revolution), not the blade-passing N P of a fixed surface nor the rotor
    total (:mod:`pyflightstream.cases.qsteady`).
    """
    note = harmonics.get("note")
    if harmonics.get("n_max") is None:
        return f"inflow harmonics not computed: {note}"
    words = summarise_inflow_harmonics(harmonics)
    return f"{words}; {note}" if note else words


def rotor_mach_line(alias: str, mach: Mapping[str, object]) -> str:
    """Return the words the plan prints for one rotor of one point (M1).

    ``mach`` is one entry of :attr:`PointPlan.rotor_mach`.
    """
    tip, helical = mach.get("mach_tip"), mach.get("mach_helical")
    kind = mach.get("kind") or "rotor"
    if isinstance(tip, int | float) and isinstance(helical, int | float):
        line = f"{kind} {alias} M_tip {tip:.3f}, M_hel {helical:.3f}"
        advancing = mach.get("mach_advancing")
        if isinstance(advancing, int | float):
            line += f", M_adv {advancing:.3f}"
            if mach.get("mach_advancing_bound") == "edgewise":
                line += " (rotor axis not resolved: the edgewise bound)"
        return line
    return f"{kind} {alias} M_tip and M_hel not computed: {mach.get('note')}"


def point_facts(
    point_case: SimCase, *, inflow_fft: bool, fs_version: str | None = None
) -> dict[str, Any]:
    """Return what a point's plan states about its rotors, wheel and wake, READY or not.

    The rotors' tip and helical Mach numbers (M1), a quasi-steady
    wheel's 1P reduced frequency and, on a rotor point, the wake its
    termination keeps (FR-584).
    """
    wake = planned_wake(point_case)
    run = planned_run_wake(point_case)
    return {
        "boundaries_file": point_case.boundaries_file,
        "rotor_mach": {mach.alias: mach.record() for mach in rotor_machs(point_case)},
        "qsteady_validity": qsteady_validity(point_case, inflow_fft=inflow_fft) or {},
        "wake_termination": {} if wake is None else wake.record(),
        "run_wake_length": {} if run is None else run.record(),
        "streamlines": streamline_count(point_case),
        "farfield": {} if fs_version is None else farfield_plan_record(point_case, fs_version),
        "angles_not_stated": angles_not_stated(point_case),
    }


# _visual_inspect.py merged here
__all__ = [
    "ALL_MATRICES",
    "OUTPUT_DIR",
    "add_visual_inspect_parser",
    "cmd_visual_inspect",
    "design_table",
    "figure_name",
    "figure_path",
    "row_points",
    "visual_inspect",
]


#: The word of ``--matrices`` that names every matrix the workspace holds.
ALL_MATRICES = "all"


#: The place of the figure under the workspace, defined once, here; its file name is the user's
#: ``--name``.
OUTPUT_DIR = "post/visual-inspect"


#: Beyond this many levels a diagonal histogram uses ``_FREE_BINS`` bins, not one bar per level.
_MAX_LEVEL_BARS = 25


_FREE_BINS = 16


#: The margin of each axis around the levels, as a fraction of their span.
_MARGIN = 0.06


_MARKERS = "osD^vP*X"


#: Columns the reader folds into the variables; they are not design parameters.
_COLUMN_KEYS = frozenset(
    {"GEOMETRY", "SYMMETRY", "SYMMETRY_LOADS", "NCPUS", "WALLTIME", "CONFIGURATION"}
)


_Point = tuple[dict[str, float], dict[tuple[str, str], float]]


def _number(value: Any) -> float | None:
    """Return ``value`` as a float, or None when it is not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def row_points(row: MatrixRow) -> list[_Point]:
    """Expand one row into its points: (scalar parameters, ROTATE angles by (alias, axis)).

    The swept FLIGHT_CONDITION key takes each SWEEP_VALUES value. Every parameter is read as the
    row states it: a row that declares no ADVANCE_RATIO has none, and an RPM inside a MOTIONS
     record is no parameter.
    """
    base: dict[str, float] = {k: float(v) for k, v in row.flight_condition.items()}
    for key, value in row.variables.items():
        number = _number(value)
        if key not in _COLUMN_KEYS and number is not None:
            base[key] = number
    rotation = {
        (record["ALIAS"], record["AXIS"]): float(record["ANGLE"])
        for record in row.rotations
        if "ALIAS" in record
    }
    swept = [
        key
        for key in row.condition_order
        if key not in row.flight_condition and key not in row.variables
    ]
    values = row.sweep.values
    if not values:
        return [(base, rotation)]
    points: list[_Point] = []
    for level in values:
        if isinstance(level, (tuple, list)):
            points.append(({**base, "ALPHA": float(level[0]), "BETA": float(level[1])}, rotation))
        elif len(swept) == 1:
            points.append(({**base, swept[0]: float(level)}, rotation))
    return points


#: The folder of a post's polar tables under ``post/<matrix stem>/``. It is
#: ``pyflightstream.post._stage.POLARS_DIR``, restated: the run layer does not import the post.
_POLARS_DIR = "polars"

#: The point axes a polar table row is matched on, by the column the table writes them under
#: (``ADVANCE_RATIO`` is the ``J`` column).
_MATCH_COLUMNS = {"ALPHA": "ALPHA", "BETA": "BETA", "MACH": "MACH", "ADVANCE_RATIO": "J"}

#: The other swept axes a polar table states, by its column, in the same unit (the post's
#: ``CONDITION_KEY_ALIASES``, restated: the run layer does not import the post). Matched only
#: where a row sweeps them, which is what tells its points apart (REL-R3-001).
_SWEPT_COLUMNS = {
    **_MATCH_COLUMNS,
    "TASmps": "VINF",
    "ALTFT": "ALT",
    "REmi": "RE",
    "RHOkgm3": "RHO",
    "MUPas": "MU",
    "TK": "TEMP",
}


def _polar_table_rows(folder: Path, pol: str) -> list[dict[str, str]]:
    """Return the rows of the tables ``P<pol>-*.csv`` of simulation ``pol`` in ``folder``."""
    rows: list[dict[str, str]] = []
    if not folder.is_dir():
        return rows
    for path in sorted(folder.glob(f"{sweep_file_stem(pol, '')}*.csv")):
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return rows


def _in_table(
    point: Mapping[str, float], rows: Sequence[Mapping[str, str]], swept: Sequence[str] = ()
) -> bool:
    """Whether a table row states every axis of ``point`` the tables carry, to print precision.

    ``swept`` are the axes the point's row sweeps; each is matched on its column too.
    """
    axes = [
        (_SWEPT_COLUMNS[k], v)
        for k, v in point.items()
        if k in _MATCH_COLUMNS or (k in swept and k in _SWEPT_COLUMNS)
    ]
    for row in rows:
        if axes and all(
            (cell := _number(row.get(column))) is not None
            and math.isclose(cell, value, rel_tol=1e-4, abs_tol=1e-6)
            for column, value in axes
        ):
            return True
    return False


#: The command-line flag that picks the criterion of "finished"; its values are
#: :data:`FINISHED_BY_CHOICES`. One constant so a rename is one line.
FINISHED_BY_OPTION = "--finished-by"
FINISHED_BY_CHOICES = ("products", "sims")

#: Recorded statuses of a point that ran to an end with its numbers (not failed, not stopped by the
#: clock, not submitted): the points the ``sims`` criterion counts as finished.
_FINISHED_STATUSES = frozenset(
    {"CONVERGED", "COMPLETED_MAX_ITER", "MAX_ITER_REACHED", "RAN_MISSING_LOG"}
)


@dataclass(frozen=True)
class _RowAsCase:
    """The attributes :func:`~pyflightstream.cases.naming.point_name` reads from a matrix row."""

    row: MatrixRow

    @property
    def sim_id(self) -> str:
        return self.row.pol

    @property
    def mach(self) -> float | None:
        return self.row.flight_condition.get("MACH")

    @property
    def sweep(self) -> Any:
        return self.row.sweep

    @property
    def flight_condition(self) -> Mapping[str, float]:
        return self.row.flight_condition

    @property
    def condition_order(self) -> Sequence[str]:
        return self.row.condition_order

    @property
    def variables(self) -> Mapping[str, Any]:
        return self.row.variables


def finished_by_sims(root: str | Path, stem: str, rows: Sequence[MatrixRow]) -> list[bool]:
    """Return, per point of ``rows``, whether the run records hold it finished successfully.

    The point is matched to its record by the identity the ledger uses, the simulation (POL) and
    the point name (:func:`~pyflightstream.cases.naming.point_name`). A workspace without
    ``runs.json``, a point without a record or one with another status is not finished.
    """
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.cases.naming import point_name
    from pyflightstream.workspace.ledger import read_ledger

    try:
        recorded = {
            (str(r["sim"]), str(r["point"])): str(r["status"])
            for r in read_ledger(root).points(matrix=stem)
        }
    except (PyflightstreamError, ValueError, OSError):
        recorded = {}
    flags: list[bool] = []
    for row in rows:
        names: list[str | None] = []
        try:
            names = [point_name(_RowAsCase(row), p) for p in row.sweep.points()]  # type: ignore[arg-type]
        except PyflightstreamError:
            names = []
        expected = len(row_points(row))
        if len(names) != expected:
            names = [None] * expected
        flags.extend(recorded.get((row.pol, n or ""), "") in _FINISHED_STATUSES for n in names)
    return flags


def finished_points(
    root: str | Path, stem: str, rows: Sequence[MatrixRow], finished_by: str = "products"
) -> list[bool]:
    """Return, per point of ``rows`` in :func:`design_table` order, whether it is finished.

    ``finished_by`` ``"sims"`` reads the run records (:func:`finished_by_sims`); ``"products"``
    reads the polar tables of the post: finished when ``post/<stem>/polars/`` holds a table of its
    simulation (``P<POL>-*.csv``) with a row at the point's swept values. No folder, no table or
    no such row is not finished, never an error.
    """
    if finished_by == "sims":
        return finished_by_sims(root, stem, rows)
    folder = Path(root) / "post" / stem / _POLARS_DIR
    flags: list[bool] = []
    untold: set[str] = set()
    for row in rows:
        table = _polar_table_rows(folder, row.pol)
        points = [point for point, _ in row_points(row)]
        swept = sorted({k for p in points for k in p if len({q.get(k) for q in points}) > 1})
        if any(k not in _SWEPT_COLUMNS for k in swept):
            # NO COLUMN TELLS THE POINTS APART: matched on its other axes, every point of the
            # row would read finished once one is posted (REL-R3-001); drawn not finished, warned.
            untold.update(k for k in swept if k not in _SWEPT_COLUMNS)
            flags.extend(False for _ in points)
            continue
        flags.extend(_in_table(point, table, swept) for point in points)
    if untold:
        warnings.warn(
            f"visual-inspect: matrix {stem} sweeps {', '.join(sorted(untold))}, which no polar "
            f"table states, so {FINISHED_BY_OPTION} products cannot tell those points apart and "
            f"draws them not finished; {FINISHED_BY_OPTION} sims reads the run records.",
            NotApplicableWarning,
            stacklevel=2,
        )
    return flags


def design_table(
    rows_by_matrix: Mapping[str, Sequence[MatrixRow]],
) -> dict[str, list[dict[str, float]]]:
    """Return, per matrix, one flat dict of parameter to value per point.

    ROTATE aliases are flattened to their name, or ``alias:AXIS`` when the matrices turn the alias
    about more than one axis; an alias a point does not state is 0.
    """
    expanded = {
        name: [p for row in rows for p in row_points(row)] for name, rows in rows_by_matrix.items()
    }
    axes_of: dict[str, set[str]] = {}
    for points in expanded.values():
        for _, rotation in points:
            for alias, axis in rotation:
                axes_of.setdefault(alias, set()).add(axis)

    def flat(base: dict[str, float], rotation: dict[tuple[str, str], float]) -> dict[str, float]:
        out = dict(base)
        for alias, axes in axes_of.items():
            for axis in axes:
                out[alias if len(axes) == 1 else f"{alias}:{axis}"] = rotation.get(
                    (alias, axis), 0.0
                )
        return out

    return {name: [flat(b, r) for b, r in points] for name, points in expanded.items()}


def figure_name(name: str) -> str:
    """Return the file stem of ``--name``: ``.pdf`` is accepted and not doubled.

    Raises
    ------
    ValueError
        When the name is empty or holds a path separator: the place is fixed, only the name is free.
    """
    stem = name[:-4] if name.lower().endswith(".pdf") else name
    if not stem.strip() or any(c in stem for c in "/\\") or stem in (".", ".."):
        raise InputValueError(
            f"name (CLI: --name) {name!r} must be a file name without a folder: "
            f"the figure is always written to {OUTPUT_DIR}/<name>.pdf under the workspace"
        )
    return stem


def figure_path(root: str | Path, name: str) -> Path:
    """Return where the figure called ``name`` is written: ``post/visual-inspect/<name>.pdf``."""
    return Path(root) / OUTPUT_DIR / f"{figure_name(name)}.pdf"


#: Marker areas: the open marker of a point not finished is 1.8 times the filled one.
_DONE_SIZE = 14
_OPEN_SIZE = 25


def _levels(table: Mapping[str, list[dict[str, float]]], key: str) -> list[float]:
    return sorted({p[key] for points in table.values() for p in points if key in p})


def _plot_matrix(
    ax: Any,
    kept: Sequence[tuple[dict[str, float], bool]],
    axes: tuple[str, str],
    style: tuple[str, str],
    bins: Any,
) -> None:
    """Draw one matrix's points on ``ax``: a histogram when ``bins`` is given, else a scatter.

    A finished point keeps the filled marker; one not finished is drawn larger, white-faced, with
    the matrix's colour as its edge, and on top so it stays visible.
    """
    if not kept:
        return
    px, py = axes
    color, marker = style
    if bins is not None:
        ax.hist([r[px] for r, _ in kept], bins=bins, alpha=0.5, color=color)
        return
    for done, size in ((True, _DONE_SIZE), (False, _OPEN_SIZE)):
        chosen = [r for r, ok in kept if ok is done]
        if not chosen:
            continue
        look: dict[str, Any] = (
            {"alpha": 0.75, "color": color}
            if done
            else {"facecolors": "white", "edgecolors": color, "linewidths": 1.2, "zorder": 3}
        )
        ax.scatter([r[px] for r in chosen], [r[py] for r in chosen], s=size, marker=marker, **look)


def _draw(
    table: Mapping[str, list[dict[str, float]]],
    params: Sequence[str],
    out: Path,
    finished: Mapping[str, Sequence[bool]] | None = None,
) -> None:
    """Draw the pair plot of ``params`` to the PDF ``out``.

    ``finished`` flags each point of a matrix (its polar table holds it); a point not flagged is
    drawn larger, white-faced and on top. None flags nothing.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    n = len(params)
    limits: dict[str, tuple[float, float]] = {}
    bins: dict[str, Any] = {}
    for p in params:
        levels = _levels(table, p)
        lo, hi = levels[0], levels[-1]
        pad = _MARGIN * (hi - lo) if hi > lo else 0.5
        limits[p] = (lo - pad, hi + pad)
        if len(levels) <= _MAX_LEVEL_BARS:
            gap = min((b - a for a, b in zip(levels, levels[1:], strict=False)), default=1.0)
            mids = [(a + b) / 2 for a, b in zip(levels, levels[1:], strict=False)]
            bins[p] = [levels[0] - gap / 2, *mids, levels[-1] + gap / 2]
        else:
            bins[p] = _FREE_BINS
    out.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out) as pdf:
        fig, grid = plt.subplots(n, n, figsize=(2.6 * n + 1, 2.6 * n + 1), squeeze=False)
        for (i, py), (j, px) in itertools.product(enumerate(params), enumerate(params)):
            ax = grid[i][j]
            for k, (name, points) in enumerate(table.items()):
                flags = (finished or {}).get(name) or [False] * len(points)
                kept = [
                    (r, ok) for r, ok in zip(points, flags, strict=False) if px in r and py in r
                ]
                color, marker = colors[k % len(colors)], _MARKERS[k % len(_MARKERS)]
                _plot_matrix(ax, kept, (px, py), (color, marker), bins[px] if i == j else None)
            ax.set_xlim(*limits[px])
            if i != j:
                ax.set_ylim(*limits[py])
            if i == n - 1:
                ax.set_xlabel(px)
            if j == 0:
                ax.set_ylabel(py)
            ax.grid(alpha=0.3)
        handles = [
            plt.Line2D(
                [], [], marker=_MARKERS[k % len(_MARKERS)], ls="", color=colors[k % len(colors)],
                label=f"{name} ({len(points)} points)",
            )
            for k, (name, points) in enumerate(table.items())
        ]  # fmt: skip
        handles += [
            plt.Line2D([], [], marker="o", ls="", color="0.4", label="finished"),
            plt.Line2D(
                [], [], marker="o", ls="", markerfacecolor="white", markeredgecolor="0.4",
                markersize=9, label="not finished",
            ),
        ]  # fmt: skip
        fig.legend(handles=handles, loc="upper center", ncol=min(len(handles), 4), fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        pdf.savefig(fig)
        plt.close(fig)


def _named_matrices(root: Path, names: Sequence[str]) -> dict[str, Path]:
    """Return the matrix files the names select, by stem; a name with no file is warned, skipped."""
    if ALL_MATRICES in names:
        return {path.stem: path for path in every_matrix(root)}
    found: dict[str, Path] = {}
    for name in names:
        path = matrix_path(root, name)
        if not path.is_file():
            held = ", ".join(sorted(p.stem for p in matrix_files(root))) or "none"
            warnings.warn(
                f"visual-inspect: the matrix {name!r} was not found and was skipped; "
                f"the workspace holds: {held}.",
                NotApplicableWarning,
                stacklevel=3,
            )
            continue
        found[matrix_stem(path)] = path
    return found


def visual_inspect(
    root: str | Path,
    names: Sequence[str],
    params: Sequence[str] | None = None,
    finished_by: str = "products",
    *,
    name: str,
    overwrite: bool = False,
) -> Path | None:
    """Draw the design of experiments of the matrices ``names`` of the workspace ``root``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    names : sequence of str
        Matrix file names or stems, with or without ``.fs``, or ``"all"``.
    params : sequence of str, optional
        The parameters to draw; None draws every parameter that varies.
    name : str
        The figure's file name, required; it is written to ``post/visual-inspect/<name>.pdf``
        (a ``.pdf`` ending is not doubled).
    overwrite : bool, optional
        Replace ``post/visual-inspect/<name>.pdf`` when it exists; otherwise the file is kept,
        warned and nothing is drawn.
    finished_by : {"products", "sims"}, optional
        What makes a point finished (drawn filled): a row in its simulation's polar table under
        ``post/<matrix>/polars/`` (``"products"``), or a run record that finished successfully
        (``"sims"``). The other points are drawn larger, white-faced and on top.

    Returns
    -------
    Path or None
        The PDF written, or None when no matrix or no parameter is left (nothing is written).

    Warns
    -----
    NotApplicableWarning
        A matrix or a parameter that is not found is skipped, naming what the matrices state.
    EmptySelectionWarning
        Nothing is left to draw.
    """
    if finished_by not in FINISHED_BY_CHOICES:
        raise InputValueError(
            f"visual-inspect: finished_by {finished_by!r} is not valid; give 'products' (the polar "
            f"tables of the post) or 'sims' (the run records), as {FINISHED_BY_OPTION} takes them"
        )
    out = figure_path(root, name)
    if out.exists() and not overwrite:
        warnings.warn(
            f"visual-inspect: {out} exists and was kept, nothing was drawn; "
            f"pass {OVERWRITE_OPTION} to replace it, or give another --name.",
            NotApplicableWarning,
            stacklevel=2,
        )
        return None
    paths = _named_matrices(Path(root), names)
    read = {stem: read_matrix(path) for stem, path in paths.items()}
    table = design_table(read)
    every = sorted({k for points in table.values() for p in points for k in p})
    varying = [k for k in every if len(set(_levels(table, k))) > 1]
    if params:
        unknown = [p for p in params if p not in every]
        if unknown:
            warnings.warn(
                f"visual-inspect: unknown parameters {unknown} were skipped; the matrices state: "
                f"{', '.join(every) or 'nothing'}.",
                NotApplicableWarning,
                stacklevel=2,
            )
        chosen = [p for p in params if p in every]
    else:
        chosen = varying
    if not table or not chosen:
        warnings.warn(
            "visual-inspect: no matrix or no parameter is left to draw; nothing was written.",
            EmptySelectionWarning,
            stacklevel=2,
        )
        return None
    finished = {stem: finished_points(root, stem, rows, finished_by) for stem, rows in read.items()}
    _draw(table, chosen, out, finished)
    print("points per matrix:", {m: len(p) for m, p in table.items()})
    print(
        "finished/total per matrix:",
        {m: f"{sum(finished[m])}/{len(p)}" for m, p in table.items()},
    )
    print("varying parameters:", ", ".join(varying))
    return out


#: The flag that names the figure; one constant so a rename is one line.
NAME_OPTION = "--name"
OVERWRITE_OPTION = "--overwrite"


def _figure_name_argument(text: str) -> str:
    """Parse ``--name``: the name as typed, refused naming the flag when it holds a folder."""
    try:
        figure_name(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None
    return text


def add_visual_inspect_parser(subparsers: Any) -> None:
    """Register ``visual-inspect``, appended last as every later command is."""
    inspect = subparsers.add_parser(
        "visual-inspect",
        help="draw the design of experiments of run matrices as a pair plot of their parameters",
        description=(
            "Expands the active rows of the named matrices into points and draws every pair of "
            "the parameters asked, with the histogram of each on the diagonal and one colour and "
            "marker per matrix. A parameter is a FLIGHT_CONDITION key, a scalar VAR_NAMES_VALUES "
            "key or a ROTATE alias (alias:AXIS when the matrices turn it about several axes). "
            "Reads the matrices only; needs no executable. The figure is written to "
            f"{OUTPUT_DIR}/<name>.pdf under the workspace, <name> being the required --name."
        ),
    )
    inspect.add_argument(
        NAME_OPTION,
        required=True,
        type=_figure_name_argument,
        metavar="NAME",
        help="the figure's file name, required; the figure is written to "
        "post/visual-inspect/<name>.pdf under the workspace (a .pdf ending is not doubled; "
        "a folder in the name is refused)",
    )
    inspect.add_argument(
        OVERWRITE_OPTION,
        action="store_true",
        help="replace the figure when post/visual-inspect/<name>.pdf exists; without it the "
        "file is kept, a warning names it and nothing is drawn",
    )
    inspect.add_argument(
        "--matrices",
        nargs="+",
        required=True,
        metavar="MATRIX",
        help="matrix file names of the workspace, with or without .fs, or 'all' for every matrix "
        "the workspace holds",
    )
    inspect.add_argument(
        "--params",
        nargs="*",
        default=None,
        metavar="PARAM",
        help="the parameters to draw; every parameter that varies when omitted. An unknown one is "
        "warned and skipped, listing the parameters the matrices state",
    )
    inspect.add_argument(
        FINISHED_BY_OPTION,
        choices=FINISHED_BY_CHOICES,
        default="products",
        help="what makes a point finished, drawn filled: 'products' (default) a row in its "
        "simulation's polar table under post/<matrix>/polars/, or 'sims' a run record that "
        "finished successfully; every other point is drawn larger, white-faced and on top",
    )
    inspect.add_argument(
        "--workspace", default=".", help="workspace root (default: the current directory)"
    )
    add_console_arguments(inspect, "print more detail")


def cmd_visual_inspect(args: argparse.Namespace) -> int:
    """Run ``pyfs-matrix visual-inspect``; prints the path of the figure and returns 0."""
    out = visual_inspect(
        args.workspace,
        args.matrices,
        args.params,
        args.finished_by,
        name=args.name,
        overwrite=args.overwrite,
    )
    if out is not None:
        print(out)
    return 0
