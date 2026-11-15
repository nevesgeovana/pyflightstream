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
    """Run a mesh verb through ``pyfs-mesh``, else the command through ``pyfs-matrix``."""
    from pyflightstream.run.mesh_cli import main as mesh_main

    arguments = list(argv or [])
    # The global flags that stand before the subcommand (``--warning-off``) keep their place.
    at = next((i for i, word in enumerate(arguments) if not word.startswith("-")), None)
    if at is not None and arguments[at] in VERBS:
        head, verb, rest = arguments[:at], arguments[at], arguments[at + 1 :]
        return int(mesh_main([*head, VERBS[verb], *rest]))
    return int(_matrix_cli.main(argv))


def mesh_parser() -> Any:
    """Return a parser of the ``pyfs-mesh`` verbs built from their public builders."""
    import argparse

    from pyflightstream.run._cli_geometry import add_geometry_verbs

    parser = argparse.ArgumentParser(prog="pyfs-mesh")
    add_geometry_verbs(parser.add_subparsers(dest="verb", required=True))
    return parser


def __getattr__(name: str) -> Any:
    return getattr(_matrix_cli, name)
