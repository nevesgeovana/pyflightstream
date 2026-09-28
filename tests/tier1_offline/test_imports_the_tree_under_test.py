"""Tier 1, 0.29.0 (GOAL-034 Q8 QA-2): the suite imports the tree it sits in.

A review worktree whose pytest imported whatever ``pyflightstream`` happened
to be installed measured ANOTHER tree: the editable install of the main
checkout. A regression only the candidate carried came back green, and a fix
was credited against code that was not in the candidate. ``pythonpath =
["src"]`` in ``[tool.pytest.ini_options]`` puts this checkout's ``src`` first;
this test fails loudly the day a run imports a foreign install anyway.

The one run that must NOT import the checkout is the release workflow's
``test-artifact`` job, which installs the built wheel and clears the ini
path with ``-o pythonpath=``. It sets ``PYFLIGHTSTREAM_TEST_INSTALLED=1``,
and there the assertion turns around: the package must come from the
installed distribution, never from this checkout's ``src``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pyflightstream

_SRC = Path(__file__).resolve().parents[2] / "src"


def test_the_package_under_test_is_the_one_this_suite_ships_with():
    origin = Path(pyflightstream.__file__).resolve()
    if os.environ.get("PYFLIGHTSTREAM_TEST_INSTALLED") == "1":
        assert not origin.is_relative_to(_SRC), (
            f"the installed-artifact run imported the checkout's source {origin}, "
            "so it tests what ci.yml already tests rather than the built wheel"
        )
        assert "site-packages" in origin.parts, f"not an installed distribution: {origin}"
        return
    assert origin.is_relative_to(_SRC), (
        f"this suite imported pyflightstream from {origin}, not from {_SRC}; every "
        "result of this run measures that other tree, not the one under test"
    )
