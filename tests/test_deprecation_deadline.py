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
import re
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
    """Read the RELEASE the version being built belongs to.

    The file is the version authority of the release commit; installed
    metadata can lag it in an editable checkout, so the guard reads
    the file directly.

    A development or pre-release suffix is stripped, and that is the
    whole point of this function rather than an incidental tidy-up.
    ``parse_version`` accepts only three dot-separated integers,
    deliberately, because a removal promise is recorded against a plain
    release. When the project moved to ``0.4.0.dev0`` for REV010-015
    this reader began handing it a four-part string, so every deadline
    check would have raised ValueError. It was invisible because
    ``DEPRECATED_MODULES`` is currently empty, which parametrizes those
    tests over nothing: the guard would have surfaced as an unexplained
    crash in the commit that registers the next shim, which is the
    worst moment to discover it (architect pass, 2026-08-03).

    ``0.4.0.dev0`` is treated as ``0.4.0`` because a promise recorded
    for removal at 0.4.0 comes due in the development series that
    becomes 0.4.0; treating the dev version as still-0.3.x would let a
    shim outlive its horizon for the whole cycle in which it is meant
    to be removed.
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["version"]
    return re.split(r"[-+]|\.dev|[abr]c?\d", declared)[0]


# Every deliberate re-import below is wrapped in the restored_module
# fixture (tests/conftest.py), which puts sys.modules back afterwards.
# These tests are where the damage was measured: pyflightstream.versions
# was used here as an "importable stand-in", so the session went on with
# two FsVersion classes and the failure surfaced three test modules away
# from its cause.


def _fresh_import(module: str):
    """Import the shim as a user would, DeprecationWarning silenced.

    The caller owns the restore; see the ``restored_module`` fixture.
    """
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
def test_no_shim_survives_its_removal_version(entry: DeprecatedModule, restored_module) -> None:
    """The deadline itself: an expired shim fails the suite.

    Before the recorded removal version the shim must exist (a ledger
    row for a module already deleted is stale and must be removed with
    it). From the removal version on, the shim must be gone: delete the
    shim module, its tests, and the ledger entry in the same commit
    that bumps the version.
    """
    current = parse_version(_project_version())
    expired = current >= parse_version(entry.removal_version)
    with restored_module(entry.module):
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


def test_the_guard_itself_fires_on_an_expired_shim(monkeypatch, restored_module) -> None:
    """Prove the deadline branch, which stays dormant until v0.4.0.

    A synthetic ledger entry for a real importable module expires
    immediately under a monkeypatched project version; the guard must
    fail exactly then, or a bug in the version sourcing or comparison
    would let an expired shim ship silently (the one defect D10 was
    adopted to prevent).
    """
    entry = DeprecatedModule(
        module="pyflightstream.versions",  # real, importable stand-in
        replacement="pyflightstream.versions",
        deprecated_since="0.0.1",
        removal_version="0.0.2",
    )
    monkeypatch.setattr(sys.modules[__name__], "_project_version", lambda: "0.0.2")
    with pytest.raises(AssertionError, match="promised removal in v0.0.2"):
        test_no_shim_survives_its_removal_version(entry, restored_module)


def test_parse_version_refuses_non_semver_strings() -> None:
    with pytest.raises(ValueError, match=r"plain MAJOR\.MINOR\.PATCH"):
        parse_version("0.4")
    with pytest.raises(ValueError, match="recorded against plain SemVer"):
        parse_version("0.4.0rc1")


@pytest.mark.parametrize("entry", DEPRECATED_MODULES, ids=lambda e: e.module)
def test_shim_warning_states_the_recorded_removal_version(
    entry: DeprecatedModule, restored_module
) -> None:
    """The warning users see cites the exact version the ledger enforces.

    Release skill pause point 1 checks the same fact by eye; here it is
    mechanical: the shim's import-time DeprecationWarning must name the
    replacement module and the recorded removal version.
    """
    if parse_version(_project_version()) >= parse_version(entry.removal_version):
        pytest.skip("expired shim; the deadline test above already fails the suite")
    with restored_module(entry.module):
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


# --- the guard's own input contract ----------------------------------------
#
# Found by the architect pass on 2026-08-03. DEPRECATED_MODULES is empty, so
# every deadline test above is parametrized over nothing and the machinery
# is exercised by no case at all. Moving pyproject to 0.4.0.dev0 for
# REV010-015 therefore broke the deadline check invisibly: parse_version
# accepts three dot-separated integers only, and would have raised on the
# four-part string in the next commit that registered a shim.


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("0.4.0", (0, 4, 0)),
        ("0.4.0.dev0", (0, 4, 0)),
        ("0.4.0rc1", (0, 4, 0)),
        ("0.4.0a1", (0, 4, 0)),
        ("1.0.0+local", (1, 0, 0)),
    ],
)
def test_the_deadline_guard_reads_a_development_version(monkeypatch, declared, expected):
    """A dev version belongs to the release it becomes, for deadline
    purposes: a promise recorded for removal at 0.4.0 comes due in the
    series that becomes 0.4.0, not one cycle later."""
    monkeypatch.setattr(tomllib, "loads", lambda _text: {"project": {"version": declared}})
    assert parse_version(_project_version()) == expected


def test_the_real_project_version_is_still_parseable():
    """The live case, so a future version scheme that this stripper cannot
    handle fails here rather than in the commit that adds the next shim."""
    assert parse_version(_project_version()) >= (0, 4, 0)
