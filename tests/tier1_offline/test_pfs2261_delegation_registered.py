"""PFS-2261: the delegated verbs of pyfs-workspace are registered once, and only once.

A second, different registration would silently keep the first; it is refused naming both.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from pyflightstream import _cli


def test_pfs2261_a_fresh_workspace_parser_lists_every_delegated_verb():
    code = (
        "import argparse\n"
        "from pyflightstream import _cli\n"
        "from pyflightstream.workspace.cli import _build_parser\n"
        "parser = _build_parser()\n"
        "(verbs,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]\n"
        "missing = [v for v in _cli.WORKSPACE_VERBS if v not in verbs.choices]\n"
        "print('MISSING', missing)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "MISSING []" in done.stdout, done.stdout


def test_pfs2261_a_second_different_registration_is_refused():
    import pyflightstream.run._cli_geometry  # noqa: F401  (registers the runner)

    first = list(_cli._DELEGATED)
    assert first, "nothing registered"
    build, entry = first[0]
    _cli.register_delegated_commands(build, entry)  # the same registration is harmless
    with pytest.raises(RuntimeError) as refused:
        _cli.register_delegated_commands("other.mod:build", "other.mod:entry")
    assert build in str(refused.value) and "other.mod:build" in str(refused.value)
    assert _cli._DELEGATED == first
