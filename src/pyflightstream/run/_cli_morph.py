"""The ``pyfs-workspace geometry`` verbs a morphing control file drives (PFS-2189, PFS-2193).

Pipeline role: the run layer's parsers and handlers for ``repitch``, ``collapse-te``,
``hub-rings`` and ``morph``. The work is the workspace layer's
(:mod:`pyflightstream.workspace.repitch`, :mod:`pyflightstream.workspace.collapse_te`,
:mod:`pyflightstream.workspace.hub_rings`, :mod:`pyflightstream.workspace.morph`); this module
only reads the command line, calls it,
prints the checks it returns and gives the exit code: 0 when the output was written, 2 when the
input is refused, with the refusal on standard error and nothing written. Each parser names its
handler as the ``mesh_command`` default, which :mod:`pyflightstream.run._cli_geometry` calls, so
the group adds every verb of this module through :func:`add_morph_verbs` and lists them by
:data:`MORPH_VERBS`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from pyflightstream._errors import PyflightstreamError

__all__ = ["MORPH_VERBS", "add_morph_verbs"]


def _print_checks(work: Callable[[], dict[str, Any]]) -> int:
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

    return _print_checks(lambda: repitch_mesh(args.mesh, args.morphing, args.out))


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

    return _print_checks(lambda: collapse_trailing_edge(args.mesh, args.morphing, args.out))


def add_hub_rings_parser(subparsers: Any) -> None:
    """Add the verb that rebuilds a hub around blade roots as rings of quads."""
    parser = subparsers.add_parser(
        "hub-rings",
        help="rebuild the named hub around blade roots as rings of quads, on an OBJ",
        description=(
            "MESH is an OBJ. The [hub_rings] table of the morphing file states rings (and "
            "optionally width); blades and hub sit at the top of the file or in the table. Per "
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

    return _print_checks(lambda: hub_rings_mesh(args.mesh, args.morphing, args.out))


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

    return _print_checks(lambda: morph_mesh(args.mesh, args.morphing, args.out))


#: The parser of each verb this module adds, by its name in the group.
_PARSERS: dict[str, Callable[[Any], None]] = {
    "repitch": add_repitch_parser,
    "collapse-te": add_collapse_te_parser,
    "hub-rings": add_hub_rings_parser,
    "morph": add_morph_parser,
}

#: The verbs this module adds to the group.
MORPH_VERBS = tuple(_PARSERS)


def add_morph_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` subparsers."""
    for add in _PARSERS.values():
        add(verbs)
