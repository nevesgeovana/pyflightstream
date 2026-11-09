"""The ``pyfs-workspace geometry`` verbs that write a new mesh and print its record.

Pipeline role: the run layer's parsers and handlers for the verbs a morphing control file
drives, ``repitch``, ``collapse-te``, ``hub-rings`` and ``morph`` (PFS-2189, PFS-2193), and for
the verbs that read named IGES files, ``iges-grid`` and ``iges-convert`` (PFS-2198, PFS-2199,
on the gmsh kernel). The work is the workspace layer's
(:mod:`pyflightstream.workspace.repitch`, :mod:`pyflightstream.workspace.collapse_te`,
:mod:`pyflightstream.workspace.hub_rings`, :mod:`pyflightstream.workspace.morph`,
:mod:`pyflightstream.workspace.iges_grid`, :mod:`pyflightstream.workspace.iges_convert`); this
module only reads the command line, calls it, prints the checks or the record it returns and
gives the exit code: 0 when the output was written, 2 when the input is refused or the gmsh
library cannot load, with the message on standard error and nothing written. Each parser names its
handler as the ``mesh_command`` default, which :mod:`pyflightstream.run._cli_geometry` calls, so
the group adds every verb of this module through :func:`add_morph_verbs` and lists them by
:data:`MORPH_VERBS`, which also carries ``mesh-generated``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.run._geom_cli_moved import report_of, write_json

__all__ = ["MORPH_VERBS", "add_morph_verbs"]


def print_checks(work: Callable[[], dict[str, Any]]) -> int:
    """Run one verb, print the checks it returns and return the exit code."""
    try:
        report = work()
    except (OSError, PyflightstreamError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, default=str))
    return 0


def add_repitch_parser(subparsers: Any) -> None:
    """Add the rigid-blade repitch verb with its morphing control file."""
    parser = subparsers.add_parser(
        "repitch",
        help="rigidly repitch blades and rebuild the named hub around their roots",
        description=(
            "MESH is an OBJ or a saved simulation (.fsm). The [repitch] table of the morphing "
            "file names the blades, the hub and the angle; each blade turns rigidly about its "
            "pitch axis; [repitch] hub_method chooses how the hub follows: its complete quad "
            "rings move (rings), the band around each turned root is remeshed quad-dominant "
            "(remesh, OBJ only), or auto picks one. The checks are written to "
            "<out>.repitch.json. Quality findings are warned with their numbers and the mesh "
            "is written; a broken input or invariant refuses and nothing is written "
            "(docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj or .fsm, read only")
    parser.add_argument("--morphing", required=True, help="TOML with a [repitch] table")
    parser.add_argument("--out", required=True, help="new mesh of the same kind")
    parser.set_defaults(mesh_command=run_repitch)


def run_repitch(args: argparse.Namespace) -> int:
    """Run repitch and print the checks written beside its output."""
    from pyflightstream.workspace.repitch import repitch_mesh

    return print_checks(lambda: repitch_mesh(args.mesh, args.morphing, args.out))


def add_collapse_te_parser(subparsers: Any) -> None:
    """Add the verb that collapses a blunt trailing edge, with its morphing control file."""
    parser = subparsers.add_parser(
        "collapse-te",
        help="collapse the blunt trailing edge of named blades of an OBJ",
        description=(
            "MESH is an OBJ. The [collapse_te] table of the morphing file names the blades; "
            "each pair of rim nodes across a blade's one-cell base strip merges at its "
            "midpoint and the strip leaves. Every other node and face keeps its place; the "
            "boundaries file gets one trailing-edge line per blade and the checks are written "
            "to <out>.collapse.json. Quality findings (a face the merge turns over) are warned "
            "with their numbers and the mesh is written; a broken input or invariant refuses "
            "and nothing is written (docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj, read only")
    parser.add_argument("--morphing", required=True, help="TOML with a [collapse_te] table")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_collapse_te)


def run_collapse_te(args: argparse.Namespace) -> int:
    """Run collapse-te and print the checks written beside its output."""
    from pyflightstream.workspace.collapse_te import collapse_trailing_edge

    return print_checks(lambda: collapse_trailing_edge(args.mesh, args.morphing, args.out))


def add_hub_rings_parser(subparsers: Any) -> None:
    """Add the verb that rebuilds a hub around blade roots as rings of quads."""
    parser = subparsers.add_parser(
        "hub-rings",
        help="rebuild the named hub around blade roots as rings of quads, on an OBJ",
        description=(
            "MESH is an OBJ. The [hub_rings] table of the morphing file states rings (and "
            "optionally band_width); blades and hub sit at the top or in the table. Per "
            "blade, rings rows of quads are marched outward from the root on the hub, the hub "
            "faces they reach plus one layer leave, and the band between them is remeshed "
            "quad-dominant. Blade nodes, other families and the hub's seams stay to the bit; the "
            "checks are written to <out>.hub_rings.json. Quality findings are warned with their "
            "numbers and the mesh is written; a broken input or invariant refuses and nothing "
            "is written (docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj, read only")
    parser.add_argument("--morphing", required=True, help="TOML with a [hub_rings] table")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_hub_rings)


def run_hub_rings(args: argparse.Namespace) -> int:
    """Run hub-rings and print the checks written beside its output."""
    from pyflightstream.workspace.hub_rings import hub_rings_mesh

    return print_checks(lambda: hub_rings_mesh(args.mesh, args.morphing, args.out))


def add_morph_parser(subparsers: Any) -> None:
    """Add the verb that applies every table of a morphing control file, in its fixed order."""
    parser = subparsers.add_parser(
        "morph",
        help="apply the morphing file's tables in order: hub rings, repitch, collapse, wheel",
        description=(
            "MESH is an OBJ, a sector or a full wheel. The tables the morphing file holds are "
            "applied in one fixed order: [hub_rings], [repitch], [collapse_te], [wheel] (a "
            "sector only), each with its own checks; blades and hub sit at the top of the file. "
            "One OBJ is written with its boundaries file, its points files and "
            "<out>.morph.json. Each step warns of quality with its numbers and goes on; "
            "nothing is written when a step refuses a broken input or invariant "
            "(docs/mesh/how-to.md)."
        ),
    )
    parser.add_argument("mesh", help="source .obj, read only")
    parser.add_argument("--morphing", required=True, help="TOML control file of the chain")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.set_defaults(mesh_command=run_morph)


def run_morph(args: argparse.Namespace) -> int:
    """Run the morphing chain and print the record written beside its output."""
    from pyflightstream.workspace.morph import morph_mesh

    return print_checks(lambda: morph_mesh(args.mesh, args.morphing, args.out))


def _add_name_encoding(parser: Any) -> None:
    parser.add_argument(
        "--name-encoding",
        default="latin-1",
        help=(
            "text encoding of the NAME bytes in the IGES files (default latin-1, one "
            "character per byte; use utf-8 for UTF-8 names). Never guessed: a name invalid "
            "in the encoding is refused"
        ),
    )


def add_iges_grid_parser(subparsers: Any) -> None:
    """Add the verb that grids named IGES components into one OBJ."""
    parser = subparsers.add_parser(
        "iges-grid",
        help="grid the named components of IGES files into one OBJ (uses the gmsh kernel)",
        description=(
            "Each component the IGES files name (the NAME of a level) becomes one family of the "
            "OBJ. Faces are joined so shared edges are conformal; four-sided patches follow the "
            "laws of the grid control file and become quads, other patches are quad-dominant at "
            "the component's size. Writes the OBJ, <out>.boundaries.toml for mark-boundaries, "
            "one points file per trailing edge found and the record <out>.json. Each junction of "
            "two components is measured against the original faces of both. Quality is "
            "warned, never refused (docs/mesh/iges.md)."
        ),
    )
    parser.add_argument("iges", nargs="+", help="IGES files, read only")
    parser.add_argument("--grid", required=True, help="grid control file (TOML)")
    parser.add_argument("--out", required=True, help="new .obj")
    parser.add_argument(
        "--component",
        dest="components",
        action="append",
        metavar="NAME",
        help=(
            "grid only this component, named as the files name it (repeatable); the others "
            "leave the model before the join. An unknown or ambiguous name is refused with the "
            "names found. Default: every component"
        ),
    )
    _add_name_encoding(parser)
    parser.set_defaults(mesh_command=run_iges_grid)


def run_iges_grid(args: argparse.Namespace) -> int:
    """Run iges-grid and print the record written beside its output."""
    from pyflightstream.workspace.iges_grid import grid_iges

    return print_checks(
        lambda: grid_iges(
            args.iges,
            args.grid,
            args.out,
            name_encoding=args.name_encoding,
            components=args.components,
        )
    )


def add_iges_convert_parser(subparsers: Any) -> None:
    """Add the verb that rewrites named IGES files as one IGES of B-spline faces."""
    parser = subparsers.add_parser(
        "iges-convert",
        help="rewrite IGES files as one IGES of B-spline faces, names kept (uses the gmsh kernel)",
        description=(
            "Every face of the IGES files is converted to a B-spline surface and written to one "
            "IGES, each component on its own level with one NAME, so the solver's CAD import "
            "and this package read the same components back. The first file's length unit is "
            "kept. Writes the IGES and the record <out>.json (docs/mesh/iges.md)."
        ),
    )
    parser.add_argument("iges", nargs="+", help="IGES files, read only")
    parser.add_argument("--out", required=True, help="new .igs")
    _add_name_encoding(parser)
    parser.set_defaults(mesh_command=run_iges_convert)


def run_iges_convert(args: argparse.Namespace) -> int:
    """Run iges-convert and print the record written beside its output."""
    from pyflightstream.workspace.iges_convert import convert_iges

    return print_checks(lambda: convert_iges(args.iges, args.out, name_encoding=args.name_encoding))


def add_mesh_generated_parser(subparsers: Any) -> None:
    """Add the verb that meshes a parametric configuration into an all-quad OBJ."""
    parser = subparsers.add_parser(
        "mesh-generated",
        help="mesh a parametric configuration into an all-quad OBJ (uses the gmsh kernel)",
        description=(
            "Resolves the configuration and meshes its patches from their role: constant "
            "spanwise width with a refined tip, chordwise growth from the leading edge, "
            "constant azimuth and axial step on a body, a planar all-quad flat tip cap and, "
            "for a wing on a body, the fairing as one quad-dominant transition ring. The "
            "orientation is outward. The record (counts, the acceptance checks, the spacing "
            "rules) is printed; the OBJ holds one group per component."
        ),
    )
    parser.add_argument("config", metavar="CONFIG", help="the configuration (TOML)")
    parser.add_argument("--obj", required=True, help="new .obj")
    parser.add_argument(
        "--component",
        metavar="NAME",
        help="mesh this body or lifting surface alone, in its own frame (default: the assembly)",
    )
    parser.add_argument(
        "--controls",
        metavar="TOML",
        help="mesh controls overriding the defaults, by table: lifting_surface, body, checks, "
        "assembly",
    )
    parser.add_argument("--out", metavar="JSON", help="also write the record to this file")
    parser.set_defaults(mesh_command=run_mesh_generated)


def run_mesh_generated(args: argparse.Namespace) -> int:
    """Run mesh-generated: write the OBJ and print the record of its checks."""
    from pyflightstream.geometry import load_config
    from pyflightstream.workspace.geometry_pipeline import mesh_generated

    def work() -> dict[str, Any]:
        resolved = load_config(args.config)
        result = mesh_generated(
            resolved, component=args.component, controls=args.controls, obj=args.obj
        )
        record = {"obj": args.obj, **result.record}
        write_json(args.out, record)
        return record

    return report_of(work)


#: The parser of each verb this module adds, by its name in the group.
_PARSERS: dict[str, Callable[[Any], None]] = {
    "repitch": add_repitch_parser,
    "collapse-te": add_collapse_te_parser,
    "hub-rings": add_hub_rings_parser,
    "morph": add_morph_parser,
    "iges-grid": add_iges_grid_parser,
    "iges-convert": add_iges_convert_parser,
    "mesh-generated": add_mesh_generated_parser,
}

#: The verbs this module adds to the group.
MORPH_VERBS = tuple(_PARSERS)


def add_morph_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` group."""
    for add in _PARSERS.values():
        add(verbs)
