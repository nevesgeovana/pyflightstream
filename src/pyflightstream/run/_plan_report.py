"""What a campaign plan reports per point, and the lines its summary prints.

Private to :mod:`pyflightstream.run`, whose plan module re-exports every
public name of it. :func:`point_facts` reads a point's rotors, quasi-steady
wheel, wake, streamlines, far field and default angles from its case; the
``*_line`` functions turn those records into the words the plan summary prints.
"""

from __future__ import annotations

import argparse
import itertools
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from pyflightstream._errors import EmptySelectionWarning, NotApplicableWarning
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
    "OUTPUT_PATTERN",
    "add_visual_inspect_parser",
    "cmd_visual_inspect",
    "design_table",
    "output_path",
    "row_points",
    "visual_inspect",
]


#: The word of ``--matrices`` that names every matrix the workspace holds.
ALL_MATRICES = "all"


#: Name and place of the figure under the workspace, defined once, here. ``{matrices}``
#: is the matrix stems joined by an underscore, ``all`` for ``--matrices all``.
OUTPUT_PATTERN = "post/visual-inspect/doe_{matrices}.pdf"


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


def output_path(root: str | Path, names: Sequence[str]) -> Path:
    """Return where the figure of ``names`` is written (:data:`OUTPUT_PATTERN`)."""
    label = ALL_MATRICES if ALL_MATRICES in names else "_".join(names)
    return Path(root) / OUTPUT_PATTERN.format(matrices=label)


def _levels(table: Mapping[str, list[dict[str, float]]], key: str) -> list[float]:
    return sorted({p[key] for points in table.values() for p in points if key in p})


def _draw(table: Mapping[str, list[dict[str, float]]], params: Sequence[str], out: Path) -> None:
    """Draw the pair plot of ``params`` to the PDF ``out``."""
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
            for k, points in enumerate(table.values()):
                kept = [r for r in points if px in r and py in r]
                if not kept:
                    continue
                color = colors[k % len(colors)]
                if i == j:
                    ax.hist([r[px] for r in kept], bins=bins[px], alpha=0.5, color=color)
                else:
                    ax.scatter(
                        [r[px] for r in kept], [r[py] for r in kept], s=14, alpha=0.75,
                        marker=_MARKERS[k % len(_MARKERS)], color=color,
                    )  # fmt: skip
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
        fig.legend(handles=handles, loc="upper center", ncol=min(len(handles), 3), fontsize=9)
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
    root: str | Path, names: Sequence[str], params: Sequence[str] | None = None
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
    paths = _named_matrices(Path(root), names)
    table = design_table({stem: read_matrix(path) for stem, path in paths.items()})
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
    # The stems drawn name the file: a name typed with .fs or a path, or one skipped, is not.
    out = output_path(root, [ALL_MATRICES] if ALL_MATRICES in names else list(paths))
    _draw(table, chosen, out)
    print("points per matrix:", {m: len(p) for m, p in table.items()})
    print("varying parameters:", ", ".join(varying))
    return out


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
            f"{OUTPUT_PATTERN} under the workspace."
        ),
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
        "--workspace", default=".", help="workspace root (default: the current directory)"
    )
    add_console_arguments(inspect, "print more detail")


def cmd_visual_inspect(args: argparse.Namespace) -> int:
    """Run ``pyfs-matrix visual-inspect``; prints the path of the figure and returns 0."""
    out = visual_inspect(args.workspace, args.matrices, args.params)
    if out is not None:
        print(out)
    return 0
