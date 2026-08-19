"""Tier 1: requirement markers resolve, and the covered set only grows.

REV-002 finding PYFS-020, which is NFR-13 itself. The published
requirement index carried ``id``, ``text`` and ``priority`` and nothing
about status, evidence or how each requirement is verified; and
traceability was measured by searching for an identifier ANYWHERE under
``tests/``, a number the generator's own ``method`` field called an
upper bound rather than a measure.

Two halves land here. The index now publishes ``status``, ``evidence``
and ``verification`` (that half is in the generator). This module is
the other: a ``requirement`` marker declares that a test FALSIFIES a
requirement, every marker must resolve to a live identifier, and the
covered set is a ratchet.

Read as a RATCHET rather than as closure, because it is not closure. 96
requirements exist and the marked set is a fraction of them. Naming a
requirement on a test that does not actually falsify it would be worse
than leaving it unmarked, so the set grows as each one is verified by
hand, and this module makes sure it never shrinks silently.

The markers are read with ``ast`` rather than through a pytest plugin:
a static read cannot be fooled by a test that is skipped, deselected or
never collected on this platform, and "the marker exists" is a fact
about the source.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
INDEX = REPO / "reports" / "requirements-index.json"

#: The covered set may only GROW. This is the floor, raised in the same
#: commit that marks a new requirement, exactly like the coverage floor
#: in pyproject: the measurement is the fact and this is the promise.
MARKED_FLOOR = 8


def _marked() -> dict[str, list[str]]:
    """Return {requirement id: [test names]} from the marker decorators."""
    found: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.ClassDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                target = decorator.func
                parts = []
                while isinstance(target, ast.Attribute):
                    parts.append(target.attr)
                    target = target.value
                if parts[:1] != ["requirement"] or "mark" not in parts:
                    continue
                for argument in decorator.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        found.setdefault(argument.value, []).append(
                            f"{path.relative_to(REPO).as_posix()}::{node.name}"
                        )
    return found


def _live_identifiers() -> set[str]:
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    return {entry["id"] for entry in payload["requirements"]}


def test_every_marker_resolves_to_a_live_requirement():
    """A marker naming a withdrawn or misspelled identifier traces nothing.

    This is the half of NFR-13 that is closed rather than ratcheted: it
    holds completely today and cannot silently stop holding.
    """
    live = _live_identifiers()
    marked = _marked()
    assert marked, "no requirement markers found at all; the AST scan is broken"
    dangling = sorted(set(marked) - live)
    assert not dangling, (
        f"these markers name identifiers the SRS does not publish: {dangling}. A "
        "marker that resolves to nothing is worse than no marker, because the "
        "index counts it"
    )


def test_the_marked_set_only_grows():
    """The ratchet. 96 requirements exist and the marked set is a fraction.

    Marking a requirement on a test that does not actually falsify it
    would be worse than leaving it unmarked, so the set grows by hand,
    one verified pair at a time, and this stops it shrinking by accident
    when a test is renamed or deleted.
    """
    marked = _marked()
    assert len(marked) == MARKED_FLOOR, (
        f"{len(marked)} requirements carry a falsifying test and the recorded "
        f"floor is {MARKED_FLOOR}.\n\n"
        "EQUALITY, not a minimum, and that is the point: with `>=` the next "
        "commit that marks a requirement without raising the floor silently "
        "reintroduces the slack the ratchet exists to remove. Marking one more "
        "means raising this number in the same commit; removing one means "
        "lowering it and saying why."
    )


def test_the_published_index_carries_status_evidence_and_verification():
    """NFR-13 asks for these three, and the first edition published none.

    A consumer of the index could not tell an implemented requirement
    from a pending one, nor find what backs either.
    """
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    entries = payload["requirements"]
    assert entries, "the published index is empty"
    for entry in entries:
        assert set(entry) >= {"id", "text", "status", "evidence", "verification"}, entry
        assert entry["status"] in {"implemented", "pending", "deferred", "draft"}, entry
        assert entry["verification"] in {"test", "evidence", "review", "none"}, entry
    # A pending requirement is verified by nothing, by definition; an
    # implemented one must claim SOMETHING. Without this the field could
    # be a constant and still satisfy the membership check above.
    for entry in entries:
        if entry["status"] == "pending":
            assert entry["verification"] == "none", entry["id"]
        if entry["status"] == "implemented":
            assert entry["verification"] != "none", entry["id"]
    kinds = {entry["verification"] for entry in entries}
    assert len(kinds) >= 3, f"verification collapsed to {kinds}; it is not classifying"


def test_the_traceability_number_still_says_what_it_measures():
    """The generous count must keep declaring itself generous.

    The published number counts a bare mention anywhere under tests/,
    which is not a falsifying test. It travels to a dashboard where the
    docstring does not, so the payload carries its own caveat; dropping
    the caveat would turn an upper bound into a claim.
    """
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    method = payload["traceability"]["method"]
    assert "upper bound" in method, method
    assert payload["traceability"]["total"] == len(payload["requirements"])


def test_the_marker_is_registered_so_a_typo_is_not_silent():
    """An unregistered pytest mark is a warning, not an error, by default.

    The marker is declared in pyproject, and this asserts the
    declaration, because a renamed marker would otherwise make every
    marked test lose its trace while the suite stayed green.
    """
    config = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"requirement\(identifier\):', config), (
        "the requirement marker is not registered in pyproject's markers list"
    )


# --- the type-check ratchet, pinned so it can only shrink -------------------
#
# `[tool.mypy]` exempts the modules that were not clean on 2026-08-03 and its
# comment says "an exemption is removed as its module is typed, never added".
# By this repository's own structural-fix rule, documentation is not a guard.


#: The exemptions as first measured on 2026-08-03, then 21 of 53 modules.
#: Re-counted at 0.8.0.dev0 and the SET did not move, only its surroundings:
#: mypy recount 2026-08-18: 275 errors in 21 of 64 modules (reports/RPT-029).
#: Removing one means deleting its override AND its line here, in the same
#: commit.
MYPY_EXEMPTIONS = frozenset(
    {
        "pyflightstream.cases",
        "pyflightstream.cases.matrix",
        "pyflightstream.commands",
        "pyflightstream.farfield",
        "pyflightstream.fsi.driver",
        "pyflightstream.fsi.nodes",
        "pyflightstream.post.writers",
        "pyflightstream.probes.geometry",
        "pyflightstream.probes.planar",
        "pyflightstream.qa.cli",
        "pyflightstream.qa.physics",
        "pyflightstream.qa.probes",
        "pyflightstream.qa.specs",
        "pyflightstream.results.tables",
        "pyflightstream.run",
        "pyflightstream.script",
        "pyflightstream.script.entities",
        "pyflightstream.script.helpers",
        "pyflightstream.script.solver_setup",
        "pyflightstream.workspace.inputs",
        "pyflightstream.workspace.naming",
    }
)


def test_the_type_check_exemption_list_only_shrinks():
    """A new exemption is a decision, not a config edit.

    The ratchet's whole value is that the list is the debt. Appending to
    it silently would turn the check into permission to leave new code
    unchecked, which is what a blanket setting would have been.
    """
    import tomllib

    with open(REPO / "pyproject.toml", "rb") as handle:
        config = tomllib.load(handle)
    declared = {
        override["module"]
        for override in config["tool"]["mypy"].get("overrides", [])
        if override.get("ignore_errors")
    }
    added = sorted(declared - MYPY_EXEMPTIONS)
    assert not added, (
        f"these modules were newly exempted from the type check: {added}. The "
        "exemption list is the debt recorded on 2026-08-03 and it only shrinks; "
        "type the module instead, or record the addition here with its reason"
    )
    removed = sorted(MYPY_EXEMPTIONS - declared)
    assert not removed, (
        f"these modules are typed now and their entries are still listed here: "
        f"{removed}. Delete them from MYPY_EXEMPTIONS in the same commit that "
        "removes the override, so the two cannot drift"
    )


# --- the re-count, and the records that have to agree with it ---------------
#
# REPRODUCTION (OPS-2006.11.01). Before this section existed, four records
# stated the same measurement and every one of them was three releases old:
# pyproject's `[tool.mypy]` header comment, the MYPY_EXEMPTIONS comment above,
# the debt table in PLN-20260803-1830 and the NFR-27 paragraph in the SRS all
# said "223 errors in 21 of 53 modules", taken on 2026-08-03. Reading any one
# of them told a planner the grind was 223 errors over 53 modules. Re-measured
# on 2026-08-18 with every `ignore_errors` override off, the package reports
# 275 errors in 21 of 64 modules. Nothing detected the drift, because nothing
# compared a record against the tree; documentation is not a guard.
#
# What is guarded here, and what deliberately is not. The MODULE TOTAL is
# re-counted from the tracked tree on every run, so a record that says 63 when
# the package holds 64 fails. The ERROR TOTAL is not: it moves with every
# commit and with the versions of numpy's and xarray's own stubs, so it is a
# DATED measurement, reproducible by the command the report records, and what
# is guarded is that no record states a different one.

#: The sentence every record of the re-count carries. Parsed rather than
#: compared verbatim, so a record may set it in its own paragraph as long as
#: the four numbers agree.
RECOUNT_SENTENCE = re.compile(
    r"mypy recount (?P<date>\d{4}-\d{2}-\d{2}): "
    r"(?P<errors>\d+) errors in (?P<dirty>\d+) of (?P<modules>\d+) modules"
)

#: Every committed home of that sentence. The plan ledger under `_private/`
#: carries it too and is deliberately absent: it is local-only, so a test that
#: required it would fail in CI and pass here, which is the worst of both.
RECOUNT_RECORDS = (
    "reports/RPT-029_mypy-exemption-recount_2026-08-18.md",
    "pyproject.toml",
    "tests/test_traceability.py",
)

#: The two modules OPS-2006.11.01 asserted were excused without being
#: recorded. They are recorded, in both places, which is what makes the item's
#: own premise false.
CLAIMED_UNLISTED = ("pyflightstream.workspace.inputs", "pyflightstream.workspace.naming")


def _declared_exemptions() -> set[str]:
    """Return the module names `[tool.mypy]` exempts with `ignore_errors`."""
    import tomllib

    with open(REPO / "pyproject.toml", "rb") as handle:
        config = tomllib.load(handle)
    return {
        override["module"]
        for override in config["tool"]["mypy"].get("overrides", [])
        if override.get("ignore_errors")
    }


def _recount_claims() -> dict[str, tuple[str, ...] | None]:
    """Return {record path: the four numbers it states, or None}.

    A record that does not exist and a record that exists without the
    sentence are both reported as `None`, so a missing file surfaces as
    an assertion rather than as an error inside the test.

    EVERY occurrence in a file is read, not the first. Reading the first
    would let a record carry a current sentence and a contradicting one
    further down and still pass, which is the exact failure mode this
    section exists for; a file that states the re-count twice with
    different numbers reports `None` and is named as silent.
    """
    claims: dict[str, tuple[str, ...] | None] = {}
    for name in RECOUNT_RECORDS:
        path = REPO / name
        if not path.is_file():
            claims[name] = None
            continue
        found = {
            match.group("date", "errors", "dirty", "modules")
            for match in RECOUNT_SENTENCE.finditer(path.read_text(encoding="utf-8"))
        }
        claims[name] = found.pop() if len(found) == 1 else None
    return claims


def _tracked_package_modules() -> list[str]:
    """Return the tracked `.py` files under `src/pyflightstream`.

    The population is the INDEX rather than the working tree on purpose:
    an untracked scratch file beside a module is not part of the package
    and must not inflate the count. The residual is the mirror of that,
    and is stated rather than hidden: a module that has been written but
    not yet staged is invisible here until it is committed, at which
    point this test asks for the re-count.
    """
    import subprocess

    listing = subprocess.run(
        ["git", "ls-files", "src/pyflightstream"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        # Explicit, and identical to the inherited default: git needs the
        # ambient environment to find its own configuration.
        env=os.environ.copy(),
    ).stdout.split()
    return [name for name in listing if name.endswith(".py")]


def test_every_record_of_the_mypy_recount_states_the_same_measurement():
    """Four records said 223 in 21 of 53 and the package said otherwise.

    The failure this catches is not a wrong number, it is two records
    that disagree, because a planner reads one of them and never learns
    that another says something else.
    """
    claims = _recount_claims()
    silent = sorted(name for name, claim in claims.items() if claim is None)
    assert not silent, (
        f"these records state no single mypy re-count: {silent}. Each must "
        "carry the sentence 'mypy recount <date>: <n> errors in <d> of <m> "
        "modules' exactly once, or carry it several times with the same four "
        "numbers, so the measurement cannot drift apart unnoticed. A record "
        "missing the sentence and a record stating it twice with different "
        "numbers both land here"
    )
    distinct = sorted({claim for claim in claims.values() if claim is not None})
    assert len(distinct) == 1, (
        f"the records state different measurements: {claims}. One measurement "
        "has one set of numbers; correct every record in the commit that "
        "re-measures, never one of them"
    )


def test_the_recorded_module_total_is_the_one_the_package_actually_has():
    """The 53 went stale silently because nothing re-counted the tree.

    This is the guard that makes that impossible: the module total the
    records state is compared against the tracked package on every run.
    """
    claims = _recount_claims()
    stated = {claim[3] for claim in claims.values() if claim is not None}
    assert stated, "no record states a module total; the re-count sentence is missing"
    actual = len(_tracked_package_modules())
    assert stated == {str(actual)}, (
        f"the records state {sorted(stated)} modules and the tracked package "
        f"holds {actual}. Re-run the re-count in reports/RPT-029 and correct "
        "every record named in RECOUNT_RECORDS, plus the local plan ledger "
        "item PLN-20260803-1830 and the NFR-27 paragraph in the SRS"
    )


def test_the_recorded_dirty_count_is_the_number_of_overrides_that_exist():
    """The inventory has to be checkable against the config, not believed.

    OPS-2006.11.01 was opened on the belief that the config excused more
    modules than the records named. It does not, and this asserts the
    equality rather than restating the conclusion.
    """
    declared = _declared_exemptions()
    assert declared == set(MYPY_EXEMPTIONS), (
        "the config's exempted set and MYPY_EXEMPTIONS differ; the ratchet "
        "test above says which way"
    )
    claims = _recount_claims()
    stated = {claim[2] for claim in claims.values() if claim is not None}
    assert stated == {str(len(declared))}, (
        f"the records state {sorted(stated)} unclean modules and the config "
        f"carries {len(declared)} ignore_errors overrides. The re-count found "
        "an error in every exempted module, so the two numbers are the same "
        "number until an override is removed"
    )


def test_the_two_modules_called_unlisted_are_listed_in_both_homes():
    """The item's own premise, asserted rather than argued.

    OPS-2006.11.01 says the packaging file excuses twenty-one blocks
    against nineteen recorded names, the workspace input and naming
    modules being unrecorded. Both are recorded, in the config and in
    MYPY_EXEMPTIONS, and the report says so with the lines.
    """
    declared = _declared_exemptions()
    missing_from_config = sorted(set(CLAIMED_UNLISTED) - declared)
    assert not missing_from_config, (
        f"{missing_from_config} are not exempted in pyproject at all, which "
        "would make RPT-029's disproof wrong"
    )
    missing_from_record = sorted(set(CLAIMED_UNLISTED) - set(MYPY_EXEMPTIONS))
    assert not missing_from_record, (
        f"{missing_from_record} are exempted in pyproject and absent from "
        "MYPY_EXEMPTIONS, which is exactly what the item claimed and this "
        "test denies"
    )
    report = REPO / RECOUNT_RECORDS[0]
    text = report.read_text(encoding="utf-8") if report.is_file() else ""
    unnamed = sorted(name for name in CLAIMED_UNLISTED if name not in text)
    assert not unnamed, (
        f"RPT-029 does not name {unnamed}, so the false claim is contradicted "
        f"nowhere a reader can check ({RECOUNT_RECORDS[0]})"
    )
    # The two clauses above are satisfied by the module appearing ANYWHERE in
    # the report, its per-module table included, so on their own they do not
    # assert that the report draws the conclusion. This one pins the verdict.
    # It is a mention-level check over prose and is not pretended to be more:
    # what it makes impossible is the report losing the finding while keeping
    # the numbers, which is how a disproof quietly stops being written down.
    assert "nothing is unlisted" in text, (
        f"{RECOUNT_RECORDS[0]} no longer states the verdict. The item's own "
        "premise is that two excused modules are unrecorded; the report is "
        "where that is written down as false, and a report that lists the "
        "modules without saying so leaves the next reader hunting for a "
        "discrepancy that does not exist"
    )
