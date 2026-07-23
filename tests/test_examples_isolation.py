"""Tier 1: the Sybil example collector stays out of the default suite.

Pipeline role: quality gate on the A2a CI wiring (INB-006 item 1e).
The load-bearing property of the root conftest is that its three
example Sybils are path-scoped, so a plain ``pytest`` (testpaths =
["tests"]) collects zero examples and the Tier 1 suite runs exactly
what it did before. That property is asserted here, so dropping a
``path=`` from any Sybil fails a test instead of silently pulling
source-tree examples into the default run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_root_conftest():
    """Import the repository-root conftest by path (not the tests one)."""
    spec = importlib.util.spec_from_file_location("_root_conftest", REPO_ROOT / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


conftest = _load_root_conftest()
# Skip cleanly where sybil (a dev-only dependency) is absent: the
# conftest registers no collector then, so there is nothing to isolate.
if not getattr(conftest, "_SYBIL", False):  # pragma: no cover - dev extra present in CI
    pytest.skip("sybil not installed; no example collector to isolate", allow_module_level=True)


def test_no_sybil_parses_a_tests_tree_file():
    """A file under tests/ is not an example for any Sybil.

    This is the isolation that matters for the default run: pytest
    walks tests/ there, so if no Sybil parses a tests file, the default
    collection gains nothing.
    """
    tests_file = REPO_ROOT / "tests" / "test_examples_isolation.py"
    assert not any(sybil.should_parse(tests_file) for sybil in conftest.EXAMPLE_SYBILS)


def test_the_collector_does_parse_a_real_example_file():
    """The wiring is live: the root README is parsed by exactly one Sybil.

    Guards against a vacuously green step (a collector that scopes
    everything out would also pass the isolation test above).
    """
    readme = REPO_ROOT / "README.md"
    assert sum(sybil.should_parse(readme) for sybil in conftest.EXAMPLE_SYBILS) == 1


def test_nested_developer_readmes_are_excluded():
    """The ``*/README.md`` exclude spares the root README, drops the rest."""
    nested = REPO_ROOT / "src" / "pyflightstream" / "fsi" / "README.md"
    assert not any(sybil.should_parse(nested) for sybil in conftest.EXAMPLE_SYBILS)
