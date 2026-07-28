"""Tier 1: the vendored kit plan checker stays proven by its mutation test.

``check_plan_kit.py`` is the shared kit plan-ledger validator (Option C: the
strict guards plus the union vocabulary, with the legacy-id grandfather
exemption). A validator is only trustworthy if it can still FAIL the case it
exists to catch, so the kit ships a mutation companion that breaks an entry
each way and confirms the checker rejects it. Founding failure number two of
this whole ledger scheme was a validator that could not fail (a CSV reader
that tolerated malformed rows), so running the mutation test in CI is the
guard on the guard.

The companion resolves the checker as a sibling file (kit 0.2.2 de-hardcoded
the absolute coordination path that previously stopped it running here), so
it exercises the VENDORED copy under .claude/tools, and its fixtures are built
in the OS temp dir, never under _private. Both files are pinned by BODY HASH by
tests/test_kit_drift.py: the provenance header's ``note:`` and
``canonical-source:`` lines sit above the hash boundary and are deliberately
not pinned, which is what lets a vendored copy restamp its own note.

The seven tests below the mutation run pin the EXIT TAXONOMY the `plan` skill
teaches. They are here because the skill's table is prose and a re-vendor
changes behaviour: the table must not be allowed to describe a checker this
repository no longer runs, which is exactly what happened between kit 0.2.2
and 0.2.3.

The mapping is deliberately NOT one test per table row. The config-error row
has two tests, because its two failure arms are different exceptions behind one
exit code; one test pins the read precedence between the empty-directory branch
and the exemption list, which is a behaviour no row describes; and one pins an
outcome the skill's table gained only after these tests were written, the usage
error, which shares exit 2 with the config error and has nothing to do with it.

One of them is a unit test rather than a subprocess run, and the reason is the
whole point of the row it pins. ``load_legacy_ids`` fails two ways, and only
one is reachable portably from a subprocess. Bytes that are not UTF-8 raise
``UnicodeDecodeError``, which is NOT an ``OSError`` subclass; the defect kit
0.2.3 was promoted to fix was in the ``OSError`` arm, where 0.2.2 swallowed a
permission failure into an empty exemption set. A test that provokes only the
decode arm leaves the arm that actually regressed uncovered, and a partial
revert of just that arm passes every subprocess test in this file.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
PLAN_MUTATIONS = REPO / ".claude" / "tools" / "check_plan_kit_mutations.py"
PLAN_CHECKER = REPO / ".claude" / "tools" / "check_plan_kit.py"


def _load_checker_module() -> ModuleType:
    """Import the vendored checker by path; it is not on the import path."""
    spec = importlib.util.spec_from_file_location("_vendored_check_plan_kit", PLAN_CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_plan_checker_can_still_fail() -> None:
    """Every guard in the kit plan checker must reject a broken entry."""
    done = subprocess.run(
        [sys.executable, str(PLAN_MUTATIONS)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, (
        "the kit plan checker failed its mutation test (a guard could not fail "
        f"the case it exists to catch):\n{done.stdout}\n{done.stderr}"
    )


def _run_checker(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PLAN_CHECKER), str(target)],
        capture_output=True,
        text=True,
    )


def test_a_path_that_does_not_resolve_fails_loud(tmp_path: Path) -> None:
    """A missing ledger directory exits non-zero and says so.

    The `plan` skill anchors the ledger path on CLAUDE_PROJECT_DIR precisely
    because a mistyped or stale path must not read as a clean ledger. That
    argument depends on this exit code, and nothing asserted it until the
    2026-07-27 migration moved trees out of `_private/`.
    """
    done = _run_checker(tmp_path / "nowhere")
    assert done.returncode == 1, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    assert "not a directory" in (done.stdout + done.stderr)


def test_an_empty_ledger_directory_exits_zero_and_says_it_checked_nothing(
    tmp_path: Path,
) -> None:
    """An empty directory exits 0. This pins a WEAKNESS, not a guarantee.

    A checker aimed at a directory that exists but holds no entries reports
    success while validating nothing, which is the exact failure mode the
    2026-07-27 migration made reachable: a tree can now move out from under a
    configured path. The sister library registered the same defect
    independently the same day.

    The test asserts the CURRENT contract so a re-vendor cannot change it
    silently. If the kit later decides an empty ledger should exit non-zero,
    this test is the thing that must change with it, deliberately.
    """
    done = _run_checker(tmp_path)
    assert done.returncode == 0, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    assert "no entries" in (done.stdout + done.stderr), (
        "an empty ledger must at least SAY it checked nothing; silence here "
        "would be indistinguishable from a clean ledger"
    )


def test_the_empty_directory_branch_precedes_the_exemption_read(tmp_path: Path) -> None:
    """An empty ledger reports success even when its config is corrupt.

    Split out of the test above rather than appended to it, because it pins a
    different fact and, appended, it would never run on a day the first
    assertion failed.

    The empty-directory branch is reached BEFORE the exemption list is read, so
    a corrupt ``legacy_ids.txt`` on top of an empty ledger exits 0 while the
    same file with one entry present exits 2. That is the 2026-07-27 migration
    scenario (a plan tree moving out from under a configured path) with a
    broken config on top, reported as success.

    Pinned as it is rather than changed: the precedence is kit-body semantics,
    so it is the coordination level's call and is routed there, not edited
    here.
    """
    (tmp_path / "legacy_ids.txt").write_bytes(b"\xff\xfe not utf-8")
    done = _run_checker(tmp_path)
    assert done.returncode == 0, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    assert "CONFIG ERROR" not in (done.stdout + done.stderr)


_LEGACY_ENTRY = """\
---
id: PLN-001-a-legacy-entry
milestone: v0.1
priority: P1
status: open
ref: a ref
---

A statement of the work.
"""


def _seed_legacy_entry(target: Path) -> None:
    (target / "PLN-001-a-legacy-entry.md").write_text(_LEGACY_ENTRY, encoding="utf-8")


def test_an_undecodable_legacy_ids_file_is_a_named_config_error(tmp_path: Path) -> None:
    """A ``legacy_ids.txt`` that is not UTF-8 exits 2 and says why.

    This is the row kit 0.2.3 added. Before it, an unreadable exemption list
    could be swallowed into an empty set, so all 88 grandfathered ids failed
    the timestamp-shape guard at once, each message telling the reader their id
    "would reintroduce the central counter". That is loud in a way that points
    at the wrong fix: it reads as 88 real defects and invites renumbering,
    which the plan rules forbid outright and which is how a wrong citation once
    leaked into a committed file.

    Covers the DECODE arm only, which is the one a subprocess can provoke
    portably. The permission arm, which is the one 0.2.2 actually got wrong,
    is covered by the unit test below; neither test alone is enough and the
    module docstring says why.
    """
    _seed_legacy_entry(tmp_path)
    (tmp_path / "legacy_ids.txt").write_bytes(b"\xff\xfe not utf-8")
    done = _run_checker(tmp_path)
    assert done.returncode == 2, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    assert "CONFIG ERROR" in done.stderr, (
        "the config error must be labelled as one, on stderr: the skill teaches "
        f"a reader to look for it there. stdout={done.stdout!r}"
    )
    assert "legacy_ids.txt" in done.stderr, "it must name the file the reader has to fix"
    assert "could not be read" in done.stderr, (
        "the plan skill quotes this message in its exit table; a kit reword "
        "keeping the label but dropping the cause would leave that quotation "
        "stale and this test green"
    )
    assert "reintroduce the central counter" not in (done.stdout + done.stderr), (
        "a config error must not be reported as a ledger defect: that message "
        "is what sends a reader to renumbering instead of to the file"
    )


def test_an_unreadable_legacy_ids_file_raises_rather_than_yielding_no_exemptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The permission arm raises ``LegacyIdsUnreadable``, it does not swallow.

    This is the arm kit 0.2.2 got wrong, and it cannot be provoked from a
    subprocess on this repository's primary platform: a file the current user
    cannot read is not portably creatable on Windows. So the vendored module is
    imported by path and ``read_text`` is made to raise ``PermissionError``,
    which is an ``OSError`` and is therefore the exact failure 0.2.2 turned into
    an empty exemption set.

    Without this test a partial revert, restoring ``except OSError: return
    frozenset()`` while leaving the decode arm loud, reproduces the original
    defect and passes every other test in this file.
    """
    checker = _load_checker_module()
    for name in ("load_legacy_ids", "LegacyIdsUnreadable"):
        assert hasattr(checker, name), (
            f"the vendored checker has no {name!r}. A kit re-vendor renamed or "
            "removed the exemption reader, so this test must move with it "
            "rather than fail as a bare AttributeError."
        )
    (tmp_path / "legacy_ids.txt").write_text("PLN-001-a-legacy-entry\n", encoding="utf-8")

    def _refuse(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", _refuse)
    with pytest.raises(checker.LegacyIdsUnreadable) as caught:
        checker.load_legacy_ids(tmp_path)
    assert "legacy_ids.txt" in str(caught.value), (
        "the raised error must name the file, because its whole purpose is to "
        "send the reader to the configuration instead of to the ledger"
    )


def test_an_absent_legacy_ids_file_stays_silent_and_fails_every_legacy_id(
    tmp_path: Path,
) -> None:
    """An ABSENT exemption list is still silent. This pins a WEAKNESS.

    Stated separately from the tests above because the two halves of that row
    did NOT move together, and both the routing brief and this repository's own
    plan entry read as though the whole row became loud at 0.2.3. It did not.
    Absent remains a deliberate silent no-exemptions path, so that a repository
    which never had counter ids (the sister's case) is unaffected; only
    present-but-unreadable became a config error. A ledger whose exemption list
    is deleted therefore still fails every legacy id at once with no cause
    named.

    The fixture is deliberately three entries rather than one, because the
    signature the skill teaches a reader to recognize is the COUNT: every
    legacy id failing at once means the exemption list is gone, while one or a
    few failures is a real ledger defect. A one-entry fixture cannot tell those
    two apart and so cannot pin what the skill claims.
    """
    _seed_legacy_entry(tmp_path)
    (tmp_path / "PLN-002-another-legacy-entry.md").write_text(
        _LEGACY_ENTRY.replace("PLN-001-a-legacy-entry", "PLN-002-another-legacy-entry"),
        encoding="utf-8",
    )
    (tmp_path / "PLN-20260101-0000-a-modern-entry.md").write_text(
        _LEGACY_ENTRY.replace("PLN-001-a-legacy-entry", "PLN-20260101-0000-a-modern-entry"),
        encoding="utf-8",
    )

    done = _run_checker(tmp_path)
    assert done.returncode == 1, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    output = done.stdout + done.stderr
    assert "CONFIG ERROR" not in output, (
        "absent is not a config error; if the kit ever makes it one, this test "
        "is the thing that must change with it, deliberately"
    )
    assert output.count("reintroduce the central counter") == 2, (
        "both counter ids must fail, and only they: that all-at-once count is "
        f"the signature the plan skill teaches. output={output!r}"
    )
    failing = [line for line in output.splitlines() if line.startswith("FAIL")]
    assert not any("PLN-20260101-0000-a-modern-entry" in line for line in failing), (
        "a timestamp id must pass while the exemption list is absent. Scoped to "
        "the FAIL lines rather than the whole output, so a future kit that "
        f"echoed passing entries would not trip a correct behaviour: {failing}"
    )

    (tmp_path / "legacy_ids.txt").write_text(
        "PLN-001-a-legacy-entry\nPLN-002-another-legacy-entry\n", encoding="utf-8"
    )
    listed = _run_checker(tmp_path)
    assert listed.returncode == 0, f"stdout={listed.stdout!r} stderr={listed.stderr!r}"


def test_a_usage_error_shares_exit_2_with_the_config_error(tmp_path: Path) -> None:
    """Exit 2 is overloaded, so the OUTPUT is what distinguishes the two.

    The checker returns 2 both for a corrupt exemption list and for a wrong
    argument count. In this environment's primary shell an unquoted path
    containing a space splits into two arguments, which is a live way to reach
    the usage branch by accident. A reader who keys on the exit code alone
    concludes their exemption list is corrupt and goes to fix a file that is
    fine, so the `plan` skill's table keys row five on the CONFIG ERROR line
    and this test pins that the two stay textually distinguishable.
    """
    done = subprocess.run(
        [sys.executable, str(PLAN_CHECKER), str(tmp_path), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    output = done.stdout + done.stderr
    assert "usage" in output.lower()
    assert "CONFIG ERROR" not in output, (
        "a usage error must not carry the config-error label, or the two exit-2 "
        "causes become indistinguishable to a reader following the skill table"
    )
