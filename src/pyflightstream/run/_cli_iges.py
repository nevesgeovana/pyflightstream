"""The ``pyfs-workspace geometry`` verbs that read named IGES files (PFS-2198, PFS-2199).

Pipeline role: the run layer's parsers and handlers for ``iges-grid`` and ``iges-convert``. The
work is the workspace layer's (:mod:`pyflightstream.workspace.iges_grid`,
:mod:`pyflightstream.workspace.iges_convert`), built on the optional ``gmsh`` extra; this module
only reads the command line, calls it, prints the record it returns and gives the exit code: 0
when the output was written, 2 when an input is refused or gmsh is not installed, with the
message on standard error and nothing written. Each parser names its handler as the
``mesh_command`` default, which :mod:`pyflightstream.run._cli_geometry` calls.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from pyflightstream.run._cli_morph import _print_checks

__all__ = ["IGES_VERBS", "add_iges_verbs"]


def add_iges_grid_parser(subparsers: Any) -> None:
    """Add the verb that grids named IGES components into one OBJ."""
    parser = subparsers.add_parser(
        "iges-grid",
        help="grid the named components of IGES files into one OBJ (needs the gmsh extra)",
        description=(
            "Each component the IGES files name (the NAME of a level) becomes one family of the "
            "OBJ. Faces are joined so shared edges are conformal; four-sided patches follow the "
            "laws of the grid control file and become quads, other patches are quad-dominant at "
            "the component's size. Writes the OBJ, <out>.boundaries.toml for mark-boundaries, "
            "one points file per trailing edge found and the record <out>.json. Quality is "
            "warned, never refused (docs/mesh/iges.md)."
        ),
    )
    parser.add_argument("iges", nargs="+", help="IGES files, read only")
    parser.add_argument("--grid", required=True, help="grid control file (TOML)")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_iges_grid)


def run_iges_grid(args: argparse.Namespace) -> int:
    """Run iges-grid and print the record written beside its output."""
    from pyflightstream.workspace.iges_grid import grid_iges

    return _print_checks(lambda: grid_iges(args.iges, args.grid, args.out))


def add_iges_convert_parser(subparsers: Any) -> None:
    """Add the verb that rewrites named IGES files as one IGES of B-spline faces."""
    parser = subparsers.add_parser(
        "iges-convert",
        help="rewrite IGES files as one IGES of B-spline faces, names kept (needs the gmsh extra)",
        description=(
            "Every face of the IGES files is converted to a B-spline surface and written to one "
            "IGES, each component on its own level with one NAME, so the solver's CAD import "
            "and this package read the same components back. The first file's length unit is "
            "kept. Writes the IGES and the record <out>.json (docs/mesh/iges.md)."
        ),
    )
    parser.add_argument("iges", nargs="+", help="IGES files, read only")
    parser.add_argument("--out", required=True, help="new .igs")
    parser.set_defaults(mesh_command=run_iges_convert)


def run_iges_convert(args: argparse.Namespace) -> int:
    """Run iges-convert and print the record written beside its output."""
    from pyflightstream.workspace.iges_convert import convert_iges

    return _print_checks(lambda: convert_iges(args.iges, args.out))


#: The parser of each verb this module adds, by its name in the group.
_PARSERS: dict[str, Callable[[Any], None]] = {
    "iges-grid": add_iges_grid_parser,
    "iges-convert": add_iges_convert_parser,
}

#: The verbs this module adds to the group.
IGES_VERBS = tuple(_PARSERS)


def add_iges_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` subparsers."""
    for add in _PARSERS.values():
        add(verbs)
