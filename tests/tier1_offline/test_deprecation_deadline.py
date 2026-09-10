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
    DEPRECATIONS,
    DeprecatedManifestKey,
    DeprecatedModule,
    Deprecation,
    expired_promise,
    parse_version,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _subject(entry: Deprecation) -> str:
    return entry.subject


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
# fixture (tests/tier1_offline/conftest.py), which puts sys.modules back afterwards.
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


@pytest.mark.parametrize("entry", DEPRECATIONS, ids=_subject)
def test_removal_promise_is_well_formed(entry: Deprecation) -> None:
    """Each ledger entry, of every kind, promises removal strictly after deprecation."""
    assert parse_version(entry.deprecated_since) < parse_version(entry.removal_version), (
        f"{entry.subject} records removal_version {entry.removal_version} "
        f"not after deprecated_since {entry.deprecated_since}; a shim must "
        "live for at least one release before it disappears."
    )


@pytest.mark.parametrize("entry", DEPRECATIONS, ids=_subject)
def test_no_promise_of_any_kind_survives_its_removal_version(entry: Deprecation) -> None:
    """The deadline for every kind the ledger holds (PFS-2021.07.01).

    A module shim is additionally imported below, which is a check only
    a module admits; a parameter, a flag, a manifest key and a column
    are judged here, by the same function and against the same version,
    so no kind can outlive its promise because the guard only knew
    modules.
    """
    refusal = expired_promise(entry, _project_version())
    assert refusal is None, refusal


@pytest.mark.parametrize("entry", DEPRECATIONS, ids=_subject)
def test_every_promise_states_its_removal_version_in_its_warning(entry: Deprecation) -> None:
    """The text a shim emits is built from the entry, so it names the deadline."""
    message = entry.message()
    assert f"removed in v{entry.removal_version}" in message and entry.subject in message, message


@pytest.mark.parametrize("entry", DEPRECATED_MODULES, ids=lambda e: e.module)
def test_no_shim_survives_its_removal_version(entry: DeprecatedModule, restored_module) -> None:
    """The deadline itself: an expired shim fails the suite.

    Before the recorded removal version the shim must exist (a ledger
    row for a module already deleted is stale and must be removed with
    it). From the removal version on, the shim must be gone: delete the
    shim module, its tests, and the ledger entry in the same commit
    that bumps the version.
    """
    refusal = expired_promise(entry, _project_version())
    with restored_module(entry.module):
        try:
            _fresh_import(entry.module)
            importable = True
        except ModuleNotFoundError:
            importable = False
    if refusal is not None:
        assert not importable, refusal
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


def test_the_guard_refuses_an_expired_manifest_key(monkeypatch) -> None:
    """The red of PFS-2021.07.01: a kind that is not a module expires too.

    Measured on the base tree before the ledger grew: the guard iterated
    ``DEPRECATED_MODULES`` three times and nothing else, and no class
    could hold a manifest key, so a promise of that kind could not be
    refused because it could not be recorded.
    """
    entry = DeprecatedManifestKey(
        old="broken_commands",
        new="waived_commands",
        deprecated_since="0.13.0",
        removal_version="0.15.0",
    )
    assert expired_promise(entry, "0.14.9") is None, "refused a promise that is still live"
    refusal = expired_promise(entry, "0.15.0")
    assert refusal is not None and "manifest key broken_commands promised removal in v0.15.0" in (
        refusal
    ), refusal
    monkeypatch.setattr(sys.modules[__name__], "_project_version", lambda: "0.15.0")
    with pytest.raises(AssertionError, match="promised removal in v0.15.0"):
        test_no_promise_of_any_kind_survives_its_removal_version(entry)


def test_the_two_promises_made_before_the_ledger_could_hold_them_are_in_it() -> None:
    """PFS-2021.02: a promise that names no release cannot be checked.

    Two shims warned "in a future release" and sat outside the ledger in
    a comment. Measured RED on the base tree: neither subject was among
    the ledger's entries, and the warning text of ``analysis_setup``
    said "a future minor release", which NFR-20's policy forbids from
    1.0 and which no test could hold to a date before it. Both stay
    until 1.0.0, the decision recorded beside the entries.
    """
    subjects = {entry.subject for entry in DEPRECATIONS}
    for subject in (
        "vorticity_drag_boundaries of analysis_setup",
        "fs_version of plan_matrix",
        "fs_version of run_matrix",
    ):
        assert subject in subjects, f"{subject} is not in the ledger; it warns without a deadline"


def test_every_promise_defined_in_the_ledger_is_in_the_tuple() -> None:
    """The QA lens of the rename round, a SURVIVED mutant: deleting one entry
    from ``DEPRECATIONS`` left the suite green while the shim kept warning,
    because the shim reaches its entry by name and the deadline tests iterate
    the tuple. An entry defined at module scope and absent from the tuple is a
    promise with no deadline, which is the defect this module exists to refuse."""
    from pyflightstream import _deprecations
    from pyflightstream._deprecations import (
        DeprecatedColumn,
        DeprecatedFlag,
        DeprecatedParameter,
    )

    kinds = (
        DeprecatedModule,
        DeprecatedParameter,
        DeprecatedFlag,
        DeprecatedManifestKey,
        DeprecatedColumn,
    )
    defined = {
        name: value for name, value in vars(_deprecations).items() if isinstance(value, kinds)
    }
    assert defined, "the ledger defines no entry at module scope, so this proves nothing"
    # TWO HOMES, AND AN ENTRY BELONGS TO EXACTLY ONE. `DEPRECATIONS` holds a
    # live shim with a deadline; `REFUSED_IN_0_15_0` holds an entry whose old
    # spelling this release REFUSES, kept only so the refusal and the ledger
    # print one sentence. What is still forbidden is an entry in neither,
    # which is a promise nothing keeps.
    refused = _deprecations.REFUSED_IN_0_15_0
    listed = {id(entry) for entry in DEPRECATIONS} | {id(entry) for entry in refused}
    missing = sorted(name for name, entry in defined.items() if id(entry) not in listed)
    assert not missing, (
        f"defined in the ledger and in neither DEPRECATIONS nor REFUSED_IN_0_15_0: {missing}"
    )
    both = sorted(
        name
        for name, entry in defined.items()
        if id(entry) in {id(one) for one in DEPRECATIONS}
        and id(entry) in {id(one) for one in refused}
    )
    assert not both, (
        f"{both} are in DEPRECATIONS and in REFUSED_IN_0_15_0 at once, so the same "
        "spelling is promised and refused; the deadline guard would watch a shim "
        "that no longer exists"
    )
    assert refused, (
        "REFUSED_IN_0_15_0 is empty. It holds the batch this release breaks rather "
        "than carries, and an empty tuple makes the disjointness above vacuous."
    )


@pytest.mark.parametrize("entry", DEPRECATIONS, ids=_subject)
def test_no_promise_is_dated_ahead_of_the_version_being_built(entry: Deprecation) -> None:
    """The QA lens of the rename round: the suite checked deprecated_since
    against removal_version and the tree against removal_version, and never
    that deprecated_since is at or before the version being built, so five
    entries said 0.14.0 on a 0.13.2.dev0 tree. A development tree of the next
    release counts as that release (0.14.1.dev0 is after 0.14.0)."""
    assert parse_version(entry.deprecated_since) <= parse_version(_project_version()), (
        f"{entry.subject} says deprecated since {entry.deprecated_since}, and the tree is "
        f"{_project_version()}: the promise names a release that has not been cut"
    )


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
