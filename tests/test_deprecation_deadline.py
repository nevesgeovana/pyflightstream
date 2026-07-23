"""Guard against deprecation shims outliving their removal promise.

Pipeline role: Tier 1 quality gate (D10 adoption of the 2026-07-23
library review). A deprecation is a versioned promise recorded in
:mod:`pyflightstream._deprecations`; this module fails the suite the
moment ``pyproject.toml`` reaches a shim's recorded removal version
with the shim still importable, so an expired promise can never ship
unnoticed. It also keeps the ledger honest in the other direction:
every entry must describe a shim that still exists and warns, and the
warning text must state the exact recorded removal version.
"""

from __future__ import annotations

import importlib
import sys
import tomllib
import warnings
from pathlib import Path

import pytest

from pyflightstream._deprecations import (
    DEPRECATED_MODULES,
    DeprecatedModule,
    parse_version,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _project_version() -> str:
    """Read the version being built from pyproject.toml.

    The file is the version authority of the release commit; installed
    metadata can lag it in an editable checkout, so the guard reads
    the file directly.
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _fresh_import(module: str):
    """Import the shim as a user would, DeprecationWarning silenced."""
    sys.modules.pop(module, None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return importlib.import_module(module)


@pytest.mark.parametrize("entry", DEPRECATED_MODULES, ids=lambda e: e.module)
def test_removal_promise_is_well_formed(entry: DeprecatedModule) -> None:
    """Each ledger entry promises removal strictly after deprecation."""
    assert parse_version(entry.deprecated_since) < parse_version(entry.removal_version), (
        f"{entry.module} records removal_version {entry.removal_version} "
        f"not after deprecated_since {entry.deprecated_since}; a shim must "
        "live for at least one release before it disappears."
    )


@pytest.mark.parametrize("entry", DEPRECATED_MODULES, ids=lambda e: e.module)
def test_no_shim_survives_its_removal_version(entry: DeprecatedModule) -> None:
    """The deadline itself: an expired shim fails the suite.

    Before the recorded removal version the shim must exist (a ledger
    row for a module already deleted is stale and must be removed with
    it). From the removal version on, the shim must be gone: delete the
    shim module, its tests, and the ledger entry in the same commit
    that bumps the version.
    """
    current = parse_version(_project_version())
    expired = current >= parse_version(entry.removal_version)
    try:
        _fresh_import(entry.module)
        importable = True
    except ModuleNotFoundError:
        importable = False
    if expired:
        assert not importable, (
            f"{entry.module} promised removal in v{entry.removal_version} "
            f"and the project version is now {_project_version()}; delete "
            "the shim (and this ledger entry) before releasing, or move "
            "the promise deliberately and document the extension in the "
            "changelog."
        )
    else:
        assert importable, (
            f"{entry.module} has a ledger entry but does not import; if the "
            "shim was deleted early, delete its ledger entry in the same "
            "commit."
        )


@pytest.mark.parametrize("entry", DEPRECATED_MODULES, ids=lambda e: e.module)
def test_shim_warning_states_the_recorded_removal_version(entry: DeprecatedModule) -> None:
    """The warning users see cites the exact version the ledger enforces.

    Release skill pause point 1 checks the same fact by eye; here it is
    mechanical: the shim's import-time DeprecationWarning must name the
    replacement module and the recorded removal version.
    """
    if parse_version(_project_version()) >= parse_version(entry.removal_version):
        pytest.skip("expired shim; the deadline test above already fails the suite")
    sys.modules.pop(entry.module, None)
    with pytest.warns(DeprecationWarning) as caught:
        importlib.import_module(entry.module)
    messages = [str(w.message) for w in caught]
    assert any(
        f"removed in v{entry.removal_version}" in m and entry.replacement in m for m in messages
    ), (
        f"{entry.module} warns without naming its recorded removal version "
        f"v{entry.removal_version} and replacement {entry.replacement}; the "
        "message must come from the ledger entry (single home, NFR-11). "
        f"Warnings seen: {messages}"
    )
