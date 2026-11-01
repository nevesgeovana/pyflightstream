"""visual-inspect: the design of experiments of a workspace's run matrices as a pair plot (FR-3440).

``pyfs-matrix visual-inspect --matrices A B --params ADVANCE_RATIO ALPHA elev_RH`` expands every
active row of the named matrices into its points and draws, on one PDF page, a scatter of every
pair of parameters and the histogram of each parameter on the diagonal, one colour and marker per
matrix. It reads the matrices only: no executable, no seat, no manifest.

A parameter is a FLIGHT_CONDITION key (ALPHA, ADVANCE_RATIO, MACH, ...), a scalar
VAR_NAMES_VALUES key (REVOLUTIONS, ...) or a ROTATE alias, whose value is the ANGLE. An alias
turned about more than one axis across the matrices is named ``alias:AXIS``. A row that does not
state a ROTATE alias leaves it not turned, so its angle is 0; any other parameter a row does not
state leaves the point out of that panel. Rows are read by
:func:`pyflightstream.cases.matrix.read_matrix`, so ROTATE, MOTIONS and the other keys mean
here what they mean to ``plan``.
"""

from __future__ import annotations

import argparse
import itertools
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import EmptySelectionWarning, NotApplicableWarning
from pyflightstream.cases.matrix import MatrixRow, read_matrix
from pyflightstream.workspace import matrix_files
from pyflightstream.workspace._matrix_homes import every_matrix, matrix_path, matrix_stem
from pyflightstream.workspace.cli import add_console_arguments

__all__ = [
    "ALL_MATRICES",
    "OUTPUT_PATTERN",
    "add_visual_inspect_parser",
    "cmd_visual_inspect",
    "design_table",
    "is_power_off",
    "output_path",
    "row_points",
    "visual_inspect",
]

#: The word of ``--matrices`` that names every matrix the workspace holds.
ALL_MATRICES = "all"

#: PROVISIONAL name and place of the figure, pending the owner: defined once, here. ``{matrices}``
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


def is_power_off(row: MatrixRow) -> bool:
    """Whether a row's rotor turns no blades (PROVISIONAL rule, pending the owner's answer).

    Today: the CONFIGURATION says POWEROFF, or no MOTIONS record of the row states a
    MOVING_BC_ALIAS. Such a row's ADVANCE_RATIO only sets the time step and the spinner's speed,
    so it is no design variable. The rule lives here alone, so it changes in one place.
    """
    configuration = str(row.variables.get("CONFIGURATION", "")).upper().replace("-", "")
    moves = any("MOVING_BC_ALIAS" in record for record in row.motions)
    return "POWEROFF" in configuration or not moves


def _number(value: Any) -> float | None:
    """Return ``value`` as a float, or None when it is not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def row_points(row: MatrixRow) -> list[_Point]:
    """Expand one row into its points: (scalar parameters, ROTATE angles by (alias, axis)).

    The swept FLIGHT_CONDITION key takes each SWEEP_VALUES value. A power-off row (see
    :func:`is_power_off`) states no ADVANCE_RATIO design value unless it is the swept key.
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
    if "ADVANCE_RATIO" not in swept and is_power_off(row):
        base.pop("ADVANCE_RATIO", None)
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
    out = output_path(root, list(names))
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
