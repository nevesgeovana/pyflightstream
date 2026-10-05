"""Installed-frame copies of the probes table and the reusable inflow profile (FR-420).

Pipeline role: the post stage, beside the point tables it mirrors. With
``[products] installed_frame`` naming ``probes`` and/or ``inflow``, the post
writes, next to each probes table and each reusable inflow profile, a copy
mirrored through ``y = 0``, the frame of a rotor installed on the other side of
the plane from the one that was simulated.

The classification of the columns is NOT here. It is the one list of
:data:`pyflightstream.post.inflow_tools.FLIPPED_COLUMNS` and
:data:`~pyflightstream.post.inflow_tools.AZIMUTH_COLUMNS`, which
:func:`pyflightstream.post.inflow_tools.to_installed_frame` has always read and
the definitions page states; this module only reads it. The copy is the
isolated-frame table mirrored, blade ``k`` staying blade ``k``; it holds where
the installed configuration is the mirror image of the simulated one and asserts
nothing about a flow that is not.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

import pyflightstream._textio as _textio
from pyflightstream._errors import ProductError, PyflightstreamWarning, warn
from pyflightstream._tokens import CONTEXT_COLUMNS
from pyflightstream.cases import FLUID_PLOT_PARAMETERS
from pyflightstream.post.inflow_tools import _negated, installed_frame_columns, to_installed_frame
from pyflightstream.post.point_tables import PROBE_SPINE

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext

__all__: list[str] = []

#: The suffix of a reusable inflow profile, and of its installed copy.
INFLOW_SUFFIX = ".inflow.dat"
INSTALLED_KIND = "installed_frame"
_INSTALLED_INFLOW_SUFFIX = ".inflow_installed.dat"
#: The six columns of a reusable inflow profile, which has no header line.
_PROFILE_COLUMNS = ("X", "Y", "Z", "VX", "VY", "VZ")
#: The columns of the solver's own probe export beyond those above, which the
#: steady probes table carries in the export's own names.
_EXPORT_COLUMNS = (
    "CP_REF",
    "VTOT",
    "CP",
    "S_LEN",
    "MOMENTUM_THICKNESS",
    "DISP_THICK",
    "THICKNESS",
    "CF",
    "TRANSITION",
)
#: Columns the probes table carries by construction and the mirror leaves as written.
_AS_WRITTEN = frozenset(
    name.upper()
    for name in (*PROBE_SPINE, *CONTEXT_COLUMNS, *FLUID_PLOT_PARAMETERS, *_EXPORT_COLUMNS)
)


def _unplaced(header: list[str]) -> list[str]:
    """Return the columns of ``header`` the classification cannot place."""
    classes = installed_frame_columns(header)
    placed = {*classes.flipped, *classes.mapped}
    return [name for name in header if name not in placed and name.upper() not in _AS_WRITTEN]


def _name_once(ctx: SimContext, columns: list[str], table: Path) -> None:
    """Warn, once per simulation and column, that a column was copied as it stands."""
    fresh = [name for name in columns if name not in ctx.installed_unplaced]
    ctx.installed_unplaced.update(fresh)
    if fresh:
        warn(
            f"{table.relative_to(ctx.out).as_posix()}: the installed-frame copy cannot place "
            f"column(s) {', '.join(fresh)}, so they are copied as written; "
            "add them to the classification on the definitions page if they change under the "
            "mirror through y = 0",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _entry(ctx: SimContext, written: Path, source: Path, point_name: str) -> None:
    ctx.add(
        written,
        {
            "runs": ctx.sources[point_name],
            "kind": INSTALLED_KIND,
            "source": source.relative_to(ctx.out).as_posix(),
        },
    )


def write_installed_probes(ctx: SimContext, table: Path, point_name: str) -> None:
    """Write ``<point>_probes_installed.csv`` beside a probes table, where the pproc asks.

    Parameters
    ----------
    ctx : SimContext
        The simulation's post context.
    table : pathlib.Path
        The probes table just written.
    point_name : str
        The point it belongs to.
    """
    if "probes" not in ctx.pproc.products.installed_frame:
        return
    target = ctx.target(table.with_name(f"{table.stem}_installed.csv"))
    try:
        written = to_installed_frame(table, out=target)
        with table.open(encoding="utf-8", newline="") as stream:
            header = next(csv.reader(stream), [])
    except (ProductError, OSError) as error:
        ctx.skipped[target.relative_to(ctx.out).as_posix()] = str(error)
        return
    _name_once(ctx, _unplaced(header), table)
    _entry(ctx, written, table, point_name)


def write_installed_inflow(ctx: SimContext, profile: Path, point_name: str) -> None:
    """Write ``<stem>.inflow_installed.dat`` beside a reusable inflow profile, where asked.

    The profile has six columns and no header, ``x y z vx vy vz``; they are read as
    ``X Y Z VX VY VZ`` through the one classification of the installed-frame copy, so
    the position and the velocity along y change sign and nothing else does.

    Parameters
    ----------
    ctx : SimContext
        The simulation's post context.
    profile : pathlib.Path
        The ``<stem>.inflow.dat`` just written.
    point_name : str
        The point it belongs to.
    """
    if "inflow" not in ctx.pproc.products.installed_frame:
        return
    stem = profile.name.removesuffix(INFLOW_SUFFIX)
    target = ctx.target(profile.with_name(stem + _INSTALLED_INFLOW_SUFFIX))
    negate = set(installed_frame_columns(_PROFILE_COLUMNS).flipped)
    lines = []
    try:
        for line in profile.read_text(encoding="utf-8").splitlines():
            cells = line.split()
            lines.append(
                " ".join(
                    _negated(cell) if name in negate else cell
                    for name, cell in zip(_PROFILE_COLUMNS, cells, strict=True)
                )
            )
    except (OSError, ValueError) as error:
        ctx.skipped[target.relative_to(ctx.out).as_posix()] = (
            f"the inflow profile {profile.name} is not six columns of numbers: {error}"
        )
        return
    _textio.write_text(target, "".join(f"{line}\n" for line in lines))
    _entry(ctx, target, profile, point_name)
