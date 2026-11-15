"""The geometry verbs that ``pyfs-matrix`` once carried, driven through their home.

``pyfs-matrix refine``, ``audit-mesh``, ``inventory`` and ``degenerate`` were removed in
0.58.0 (PFS-2237): ``pyfs-workspace geometry refine``, ``audit``, ``inventory`` and
``degenerate`` give the same results with the same arguments. A test that drives one of
those verbs keeps its argument list and calls :func:`main`, which sends the four verbs to
the ``geometry`` group of ``pyfs-workspace`` and every other command to ``pyfs-matrix``.
"""

from __future__ import annotations

from typing import Any

from pyflightstream.run import cli as _matrix_cli

#: The verb as ``pyfs-matrix`` spelled it, to its name in the ``geometry`` group.
VERBS = {
    "refine": "refine",
    "audit-mesh": "audit",
    "inventory": "inventory",
    "degenerate": "degenerate",
}


def main(argv: list[str] | None = None) -> int:
    """Run a geometry verb through ``pyfs-workspace geometry``, else through ``pyfs-matrix``."""
    from pyflightstream.workspace.cli import main as workspace_main

    arguments = list(argv or [])
    # The global flags that stand before the subcommand (``--warning-off``) keep their place.
    at = next((i for i, word in enumerate(arguments) if not word.startswith("-")), None)
    if at is not None and arguments[at] in VERBS:
        head, verb, rest = arguments[:at], arguments[at], arguments[at + 1 :]
        return int(workspace_main([*head, "geometry", VERBS[verb], *rest]))
    return int(_matrix_cli.main(argv))


def __getattr__(name: str) -> Any:
    return getattr(_matrix_cli, name)
