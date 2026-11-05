"""The ``pyfs-workspace geometry`` verbs a morphing control file drives (PFS-2189, PFS-2193).

Pipeline role: the run layer's parsers and handlers for ``repitch`` and ``collapse-te``. The work
is the workspace layer's (:mod:`pyflightstream.workspace.repitch`,
:mod:`pyflightstream.workspace.collapse_te`); this module only reads the command line, calls it,
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
    print(json.dumps(report, indent=2))
    return 0


def add_repitch_parser(subparsers: Any) -> None:
    """Add the rigid-blade repitch verb with its morphing control file."""
    parser = subparsers.add_parser(
        "repitch",
        help="rigidly repitch blades and rebuild the named hub's source rings",
        description=(
            "MESH is an OBJ or a saved simulation (.fsm). The [repitch] table of the morphing "
            "file names the blades, the hub and the angle; each blade turns rigidly about its "
            "pitch axis and the hub's quad rings around its root follow. The output keeps the "
            "source's kind, its face order and its markings; the checks are written to "
            "<out>.repitch.json. Nothing is written when a check fails (docs/mesh/how-to.md)."
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
            "to <out>.collapse.json. Nothing is written when a check fails (docs/mesh/how-to.md)."
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


#: The parser of each verb this module adds, by its name in the group.
_PARSERS: dict[str, Callable[[Any], None]] = {
    "repitch": add_repitch_parser,
    "collapse-te": add_collapse_te_parser,
}

#: The verbs this module adds to the group.
MORPH_VERBS = tuple(_PARSERS)


def add_morph_verbs(verbs: Any) -> None:
    """Add this module's verbs to the ``geometry`` subparsers."""
    for add in _PARSERS.values():
        add(verbs)
