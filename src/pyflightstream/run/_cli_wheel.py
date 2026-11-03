"""The ``pyfs-workspace geometry`` verbs that build one mesh from others (PFS-2186.01 to .04).

Pipeline role: the run layer's parsers and handlers for ``sector-to-wheel``. The work is the
workspace layer's (:mod:`pyflightstream.workspace._wheel`); this module only reads the command
line, calls it, prints its summary and returns the exit code. It is registered from
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
            "--axis through --hub, the nodes of the seams are merged within --tolerance, the "
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
        help="x, y, z, a signed one of them, or three comma-separated numbers (default x)",
    )
    wheel.add_argument(
        "--hub",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="a point of the axis, in the mesh's unit (default the origin)",
    )
    wheel.add_argument(
        "--tolerance",
        type=float,
        default=1e-4,
        metavar="METRES",
        help="nodes closer than this, in metres, are one node (default 1e-4)",
    )
    wheel.add_argument(
        "--out", metavar="PATH", help="the wheel (default <sector stem>_wheel beside the sector)"
    )
    wheel.add_argument("--overwrite", action="store_true", help="replace an existing wheel")


def _cmd_sector_to_wheel(args: argparse.Namespace) -> int:
    """Run ``geometry sector-to-wheel``: print the files and the checks, return the exit code."""
    from pyflightstream.workspace import sector_to_wheel

    try:
        result = sector_to_wheel(
            args.sector,
            copies=args.copies,
            blades=args.blades,
            axis=args.axis,
            hub=args.hub or (0.0, 0.0, 0.0),
            tolerance=args.tolerance,
            out=args.out,
            overwrite=args.overwrite,
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for line in result.lines():
        print(line)
    if not result.written:
        print("Nothing was written.", file=sys.stderr)
    return 0 if result.written else 2


#: The handler of each verb this module adds, by its name in the group.
WHEEL_HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "sector-to-wheel": _cmd_sector_to_wheel,
}

#: The verbs this module adds to the group.
WHEEL_VERBS = tuple(WHEEL_HANDLERS)


def add_wheel_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` subparsers."""
    _add_sector_to_wheel(verbs)
