"""The ``pyfs-workspace geometry`` verbs that build one mesh from others (PFS-2186.01 to .04, .06).

Pipeline role: the run layer's parsers and handlers for ``sector-to-wheel``, ``sector-remesh``
and ``power-off-body``. The work is the workspace layer's
(:mod:`pyflightstream.workspace._wheel`, :mod:`pyflightstream.workspace._sector_driver`); this
module only reads the command line, calls it, prints its summary and returns the exit code.
It is registered from
:mod:`pyflightstream.run._cli_geometry` by :func:`add_wheel_verbs` and :data:`WHEEL_HANDLERS`,
so a further verb of the same kind is one parser and one handler added here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

from pyflightstream._errors import PyflightstreamError

__all__ = ["WHEEL_HANDLERS", "WHEEL_VERBS", "add_wheel_verbs"]


def _add_sector_to_wheel(verbs: Any) -> None:
    """Add ``geometry sector-to-wheel``: a sector copied about an axis into a full wheel."""
    wheel = verbs.add_parser(
        "sector-to-wheel",
        help="copy one sector about an axis into a full wheel, an OBJ or a saved simulation",
        description=(
            "SECTOR is an OBJ (with its .obj.boundaries.toml and trailing-edge points files "
            "beside it) or a saved simulation (.fsm). The sector is copied --copies times about "
            "--axis through --center, the nodes of the seams are merged within --tolerance, the "
            "surfaces named in --blades are numbered one per copy and every other surface is "
            "one group. An OBJ gives an OBJ, its boundaries file in the named form, one points "
            "file per rim per blade and <out stem>.wheel.json; a .fsm gives a .fsm, with no "
            "solver, from a layout inferred from saved files. A layout the reader does not "
            "recognize is warned, nothing is written and the exit code is 2 (docs/geometry.md)."
        ),
    )
    wheel.add_argument("sector", metavar="SECTOR", help="the sector OBJ or saved simulation")
    wheel.add_argument("--copies", type=int, required=True, help="the number of copies, 2 or more")
    wheel.add_argument(
        "--blades",
        nargs="+",
        required=True,
        metavar="FAMILY",
        help="the OBJ group(s), or the boundary(ies) of a saved simulation, that are the blade",
    )
    wheel.add_argument(
        "--axis",
        default="x",
        help="x, y, z, a signed one of them written --axis=-x, or three comma-separated numbers "
        "(default x)",
    )
    wheel.add_argument(
        "--center",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="a point of the axis, in the mesh's unit (default the origin)",
    )
    wheel.add_argument(
        "--hub",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="deprecated alias for --center; both may be given only with equal values",
    )
    wheel.add_argument(
        "--tolerance",
        type=float,
        default=1e-4,
        metavar="METRES",
        help="nodes within this distance, in metres, are one node (default 1e-4)",
    )
    wheel.add_argument(
        "--out", metavar="PATH", help="the wheel (default <sector stem>_wheel beside the sector)"
    )
    wheel.add_argument("--overwrite", action="store_true", help="replace an existing wheel")
    wheel.add_argument(
        "--no-wake-terminations",
        dest="wake_terminations",
        action="store_false",
        help="drop the wake terminations an OBJ sector's trailing-edge entries declare; by "
        "default every copy carries them, as the saved route does",
    )


def _cmd_sector_to_wheel(args: argparse.Namespace) -> int:
    """Run ``geometry sector-to-wheel``: print the files and the checks, return the exit code."""
    from pyflightstream.workspace import sector_to_wheel

    try:
        result = sector_to_wheel(
            args.sector,
            copies=args.copies,
            blades=args.blades,
            axis=args.axis,
            hub=args.hub,
            center=args.center,
            tolerance=args.tolerance,
            out=args.out,
            overwrite=args.overwrite,
            wake_terminations=args.wake_terminations,
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for line in result.lines():
        print(line)
    if not result.written:
        print("Nothing was written.", file=sys.stderr)
    return 0 if result.written else 2


def _add_remesh_common(parser: Any) -> None:
    """Add the arguments both remesh verbs share: sector, blade, axis, output, nacelle."""
    parser.add_argument(
        "sector", metavar="SECTOR", help="the saved simulation (.fsm) of one sector"
    )
    parser.add_argument(
        "--blades",
        nargs=1,
        required=True,
        metavar="FAMILY",
        help="the boundary that is the blade (one blade per sector); the spinner and the nacelle "
        "are found from it",
    )
    parser.add_argument("--axis", default="x", choices=("x", "y", "z"), help="default x")
    parser.add_argument("--out", metavar="PATH", help="the output (default beside the sector)")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing output")
    parser.add_argument(
        "--nacelle-theta", type=int, default=6, help="nacelle cells per sector, even (default 6)"
    )
    parser.add_argument(
        "--nacelle-cells", type=int, default=28, help="nacelle rings along its meridian (28)"
    )


def _add_sector_remesh(verbs: Any) -> None:
    """Add ``geometry sector-remesh``: a sector's blade, spinner and nacelle rebuilt as quads."""
    remesh = verbs.add_parser(
        "sector-remesh",
        help="rebuild a saved sector's blade, spinner and nacelle as full-quad surfaces",
        description=(
            "SECTOR is a saved simulation of one sector with a blunt trailing edge: one blade "
            "whose quads end in two rim lines that start on the root loop, a spinner and a "
            "nacelle with a flat base. The blade is rebuilt with the chord clustered at the "
            "leading edge only, constant span cells and every row at one radius from mid blade "
            "outward; the spinner and the nacelle are rebuilt as quads. The layout is inferred "
            "from saved files. Writes the sector and <out stem>.remesh.json with the checks. A "
            "sector of another topology is warned, nothing is written and the exit code is 2 "
            "(docs/geometry.md)."
        ),
    )
    _add_remesh_common(remesh)
    remesh.add_argument(
        "--chord-cells", type=int, required=True, help="chord cells, the side with fewer"
    )
    remesh.add_argument(
        "--le", type=float, required=True, help="first chord cell, fraction of the side arc"
    )
    remesh.add_argument("--span-cell", type=float, required=True, help="constant span cell, metres")
    remesh.add_argument(
        "--tip-ratio", type=float, default=0.6, help="last span cell over the constant one (0.6)"
    )
    remesh.add_argument(
        "--tip-length", type=float, default=0.2, help="length of the finer tip region, metres (0.2)"
    )
    remesh.add_argument(
        "--tip-radius",
        type=float,
        help="tip radius, metres (default the blade's largest radius about the axis, warned)",
    )
    remesh.add_argument(
        "--spinner-theta", type=int, default=12, help="spinner cells per sector, even (12)"
    )
    remesh.add_argument(
        "--spinner-layers", type=int, default=4, help="O-grid layers at the root (4)"
    )
    remesh.add_argument(
        "--spinner-rings", type=int, default=7, help="rings forward to the nose (7)"
    )
    remesh.add_argument(
        "--root-margin-r",
        type=float,
        default=0.038,
        help="spinner margin ahead of the root loop, fraction of the tip radius (0.038)",
    )
    remesh.add_argument(
        "--nose-radius-r",
        type=float,
        default=0.038,
        help="radius of the nose kite, fraction of the tip radius (0.038)",
    )


def _add_power_off_body(verbs: Any) -> None:
    """Add ``geometry power-off-body``: the whole turn of spinner and nacelle, no blades."""
    body = verbs.add_parser(
        "power-off-body",
        help="write the power-off body of a saved sector: a closed spinner and the remesh nacelle",
        description=(
            "SECTOR is the saved simulation sector-remesh reads. The body is --copies sectors of "
            "a closed spinner and the nacelle, merged across the seams, full quad, with no blade "
            "surface; its nacelle has the nodes of the remeshed wheel's. Writes the body and "
            "<out stem>.body.json. A sector of another topology is warned, nothing is written "
            "and the exit code is 2."
        ),
    )
    _add_remesh_common(body)
    body.add_argument("--copies", type=int, required=True, help="sectors in a turn, 2 or more")
    body.add_argument("--spinner-theta", type=int, default=6, help="spinner cells per sector (6)")
    body.add_argument(
        "--spinner-rings", type=int, default=12, help="spinner rings to the nose (12)"
    )
    body.add_argument(
        "--nose-radius-r",
        type=float,
        default=0.038,
        help="radius of the nose kite, fraction of the tip radius (0.038)",
    )
    body.add_argument(
        "--tip-radius", type=float, help="tip radius, metres (default the blade's largest radius)"
    )


def _finish(result: Any) -> int:
    """Print a remesh result and return its exit code."""
    for line in result.lines():
        print(line)
    if not result.written:
        print("Nothing was written.", file=sys.stderr)
    return 0 if result.written else 2


def _cmd_sector_remesh(args: argparse.Namespace) -> int:
    """Run ``geometry sector-remesh``."""
    from pyflightstream.workspace import sector_remesh

    keys = (
        "chord_cells le span_cell axis tip_ratio tip_length tip_radius spinner_theta "
        "spinner_layers spinner_rings nacelle_theta nacelle_cells root_margin_r nose_radius_r "
        "out overwrite"
    ).split()
    try:
        result = sector_remesh(
            args.sector, blades=args.blades, **{k: getattr(args, k) for k in keys}
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return _finish(result)


def _cmd_power_off_body(args: argparse.Namespace) -> int:
    """Run ``geometry power-off-body``."""
    from pyflightstream.workspace import power_off_body

    keys = (
        "copies axis spinner_theta spinner_rings nacelle_theta nacelle_cells nose_radius_r "
        "tip_radius out overwrite"
    ).split()
    try:
        result = power_off_body(
            args.sector, blades=args.blades, **{k: getattr(args, k) for k in keys}
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return _finish(result)


#: The handler of each verb this module adds, by its name in the group.
WHEEL_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "sector-to-wheel": _cmd_sector_to_wheel,
    "sector-remesh": _cmd_sector_remesh,
    "power-off-body": _cmd_power_off_body,
}

#: The verbs this module adds to the group.
WHEEL_VERBS = tuple(WHEEL_HANDLERS)


def add_wheel_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` subparsers."""
    _add_sector_to_wheel(verbs)
    _add_sector_remesh(verbs)
    _add_power_off_body(verbs)
