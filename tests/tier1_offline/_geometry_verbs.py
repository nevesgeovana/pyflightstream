"""The mesh verbs that ``pyfs-matrix`` once carried, driven through their home, ``pyfs-mesh``.

``pyfs-matrix refine``, ``audit-mesh``, ``inventory`` and ``degenerate`` were removed in
0.58.0 (PFS-2237), and the geometry group that first took them was split the same release
(PFS-2260): ``pyfs-mesh refine``, ``audit``, ``inventory`` and ``degenerate`` give the same
results with the same arguments. A test that drives one of those verbs keeps its argument
list and calls :func:`main`, which sends the four verbs to ``pyfs-mesh`` and every other
command to ``pyfs-matrix``.
"""

from __future__ import annotations

from typing import Any

from pyflightstream.run import cli as _matrix_cli

#: The verb as ``pyfs-matrix`` spelled it, to its name in ``pyfs-mesh``.
VERBS = {
    "refine": "refine",
    "audit-mesh": "audit",
    "inventory": "inventory",
    "degenerate": "degenerate",
}


def main(argv: list[str] | None = None) -> int:
    """Run a command line through the program that holds its verb since 0.58.0.

    A mesh verb goes to ``pyfs-mesh``, a records, storage or query verb (PFS-2261) to
    ``pyfs-workspace``, the flag form of the storage verbs included, and every other
    command to ``pyfs-matrix``.
    """
    from pyflightstream._cli import WORKSPACE_VERBS
    from pyflightstream.run.mesh_cli import main as mesh_main
    from pyflightstream.workspace.cli import main as workspace_main

    arguments = list(argv or [])
    # The global flags that stand before the subcommand (``--warning-off``) keep their place.
    at = next((i for i, word in enumerate(arguments) if not word.startswith("-")), None)
    if at is not None and arguments[at] in VERBS:
        head, verb, rest = arguments[:at], arguments[at], arguments[at + 1 :]
        return int(mesh_main([*head, VERBS[verb], *rest]))
    flags = {f"--{verb}" for verb in ("space-in-use", "free-space", "delete-sims", "sync")}
    flag_form = any(word.split("=", 1)[0] in flags for word in arguments)
    if (at is not None and arguments[at] in WORKSPACE_VERBS) or flag_form:
        return int(workspace_main(argv))
    return int(_matrix_cli.main(argv))


def parser_for(argv: list[str]) -> Any:
    """Return the parser of the program that holds the verb ``argv`` names since 0.58.0.

    ``pyflightstream.run._cli_parsers.records_parser`` for a records, storage or query
    verb (PFS-2261), the ``pyfs-matrix`` parser for every other.
    """
    from pyflightstream._cli import WORKSPACE_VERBS
    from pyflightstream.run._cli_parsers import _build_parser, records_parser

    word = next((w for w in argv if not w.startswith("-")), None)
    return records_parser() if word in WORKSPACE_VERBS else _build_parser()


def mesh_parser() -> Any:
    """Return a parser of the ``pyfs-mesh`` verbs built from their public builders."""
    import argparse

    from pyflightstream.run._cli_geometry import add_geometry_verbs

    parser = argparse.ArgumentParser(prog="pyfs-mesh")
    add_geometry_verbs(parser.add_subparsers(dest="verb", required=True))
    return parser


def __getattr__(name: str) -> Any:
    return getattr(_matrix_cli, name)
