"""The ``pyfs-mesh`` command line: every mesh operation of pyflightstream (FR-477).

Pipeline role: the run row, because ``build --apply``, ``mark-boundaries --apply`` and
``export-surface-mesh --apply`` run the solver and the executor is the run layer's; every
other verb reads and writes mesh files with no solver. The verbs' parsers and handlers are
those of :mod:`pyflightstream.run._cli_geometry`, :mod:`pyflightstream.run._cli_morph`,
:mod:`pyflightstream.run._cli_wheel` and :mod:`pyflightstream.run._cli_merge`, and the four
mesh parsers of :mod:`pyflightstream.run._cli_mesh` copied as parents (refine, audit,
inventory, degenerate); this module builds the program around them and gives each command
the console contract of ``pyfs-workspace``: the titled opening, ``--warning-refusals``,
``--verbose`` and ``--log-level``, the warnings at the end.

The verbs are the mesh half of the geometry tooling, the CAD half being ``pyfs-geom``
(:mod:`pyflightstream.run.geom_cli`) and the FSI beam cut ``pyfs-fsi beam``.
"""

from __future__ import annotations

import argparse
import sys

from pyflightstream._cli import cli_entrypoint
from pyflightstream._console import add_warning_option, command_help
from pyflightstream._errors import PyflightstreamError
from pyflightstream._progress import command_console
from pyflightstream.options import get_option, option_context
from pyflightstream.run._cli_geometry import HANDLERS, add_geometry_verbs
from pyflightstream.run._cli_mesh import (
    add_degenerate_parser,
    add_inventory_parser,
    add_mesh_parsers,
)
from pyflightstream.run._cli_morph import MORPH_VERBS
from pyflightstream.workspace import cli as _workspace_cli

__all__ = ["MESH_VERBS", "PYFS_MATRIX_ALIASES", "main", "matrix_parsers", "run_mesh_verb"]

#: The four mesh parsers ``pyfs-matrix`` once carried, by their name in ``pyfs-mesh``.
PYFS_MATRIX_ALIASES = {
    "refine": "refine",
    "audit": "audit-mesh",
    "inventory": "inventory",
    "degenerate": "degenerate",
}

#: Every verb of ``pyfs-mesh``, in the order its help lists them.
MESH_VERBS = (
    "mark-boundaries",
    "export-surface-mesh",
    "trailing-edge",
    "convert2midnodes",
    "identify-te",
    "prepare-to-refine",
    "visual-inspect",
    "merge",
    "sector-to-wheel",
    "sector-remesh",
    "power-off-body",
    *MORPH_VERBS,
    "build",
    "accept",
    "from-sidecar",
    *PYFS_MATRIX_ALIASES,
)


def _copied() -> argparse._SubParsersAction:
    holder = argparse.ArgumentParser(add_help=False)
    sub = holder.add_subparsers(dest="subcommand")
    add_mesh_parsers(sub)
    add_inventory_parser(sub)
    add_degenerate_parser(sub)
    return sub


def matrix_parsers() -> dict[str, argparse.ArgumentParser]:
    """Return the four copied mesh parsers, built afresh, by their ``pyfs-matrix`` name.

    Returns
    -------
    dict of str to argparse.ArgumentParser
        ``refine``, ``audit-mesh``, ``inventory`` and ``degenerate``.
    """
    return dict(_copied().choices)


def _build_parser() -> argparse.ArgumentParser:
    """Build the ``pyfs-mesh`` parser without parsing anything."""
    parser = argparse.ArgumentParser(
        prog="pyfs-mesh",
        description=(
            "Mesh operations of pyflightstream: refine, audit, inventory and derive panel "
            "meshes, find and collapse trailing edges, morph, repitch, scale, merge and copy "
            "sectors into wheels, grid IGES files and parametric configurations, and build, "
            "mark and export a workspace geometry with the solver (docs/mesh/reference.md)."
        ),
    )
    parser.add_argument(
        "--warning-refusals",
        action="store_true",
        default=get_option("warning_refusals"),
        help="restore refusals for inputs otherwise skipped with typed warnings",
    )
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")
    add_geometry_verbs(verbs)
    helps = {choice.dest: choice.help for choice in _copied()._choices_actions}
    sources = matrix_parsers()
    for name, matrix in PYFS_MATRIX_ALIASES.items():
        source = sources[matrix]
        verbs.add_parser(
            name,
            parents=[source],
            add_help=False,
            help=helps.get(matrix),
            description=source.description,
        )
    for leaf in dict.fromkeys(verbs.choices.values()):
        # A verb whose parser names its own handler (``mesh_command``: the copied parsers and
        # the morph verbs) keeps exactly its own options.
        mirrors = "mesh_command" in leaf._defaults
        if not mirrors and not any(action.dest == "log_level" for action in leaf._actions):
            _workspace_cli.add_console_arguments(
                leaf, "print every value taken from the settings files and more detail"
            )
    add_warning_option(parser)
    return parser


def run_mesh_verb(args: argparse.Namespace) -> int:
    """Run the ``pyfs-mesh`` verb ``args.verb`` names and return its exit code.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line of one verb.

    Returns
    -------
    int
        The verb's exit code.
    """
    if args.verb in HANDLERS:
        return int(HANDLERS[args.verb](args))
    # THE COPIED HANDLER ITSELF, named by its parser (FR-477); a copied mesh parser reads the
    # name it had under pyfs-matrix.
    args.subcommand = PYFS_MATRIX_ALIASES.get(args.verb, args.verb)
    try:
        return int(args.mesh_command(args))
    except PyflightstreamError as error:
        print(str(error), file=sys.stderr)
        return 2


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Run ``pyfs-mesh``; returns the process exit code.

    Parameters
    ----------
    argv : list of str, optional
        The command line without the program name; None reads ``sys.argv``.

    Returns
    -------
    int
        The exit code of the verb that ran: 0 on success, 2 for a refused input, and the
        verb's own codes otherwise (``build``: 1 a failed audit gate, 3 the solver failed).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    _workspace_cli._take_the_console_level(args)
    with (
        option_context("warning_refusals", args.warning_refusals),
        command_console(
            "pyfs-mesh",
            args.verb,
            what=command_help(parser, [args.verb]),
            workspace=getattr(args, "workspace", None) or getattr(args, "root", None),
        ),
    ):
        return run_mesh_verb(args)


if __name__ == "__main__":
    raise SystemExit(main())
