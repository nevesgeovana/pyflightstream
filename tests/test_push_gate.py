"""Tier 1 end to end guards for the role-review push gate hook.

The hook is process infrastructure, not library code, but it is the
mechanism that decides whether unreviewed work can ship, so it needs the
same evidence discipline as the package. This file pins the DECISION the
gate makes, because the parsing can be right while the enforcement is
wrong: the range fix that closed the attest-only-the-tip hole opened a
worse one on the release path, and only an adversarial review caught it.

This suite and the hardened gate it exercises were ported inward from
the sister library, which found and reproduced six fail-open holes while
porting an earlier version of the gate the other way (an allowlist of
ref-neutral options replacing a denylist that ``--follow-tag`` slipped
through, refspec resolution on both sides of the colon, per-ref scoping,
the project-name identity, and deny messages that name the command that
clears them). The hook is process infrastructure rather than package
code, so these guards were written after the port rather than before it;
that ordering is a deliberate exception to the repository's TDD rule,
which governs the ``pyflightstream`` package.

Each test builds a throwaway repository with a local bare remote, so
nothing here touches the real checkout, the real attestation, or the
shared incident ledger. The hook is invoked exactly as the harness
invokes it: the PreToolUse payload on stdin, a permission decision on
stdout.

HOW HERMETICITY IS OBTAINED, because the mechanism inverted on
2026-08-02 and the old sentence would now be actively misleading. It
used to be enough to STRIP the incident-ledger variable from every hook
subprocess: unset meant the incident check did not apply, so an absent
variable was the neutral state. Kit 0.2.8 made an absent variable DENY,
for the reason recorded on ``test_an_unconfigured_ledger_now_denies``,
and neutral-by-absence stopped existing. Stripping the variable would
now make every allow case fail for a reason that has nothing to do with
what it tests.

So the neutral state is no longer "no ledger" but "a ledger that is
readable and reports clean", and ``hook_env`` supplies one: a stub
``check_incidents.py`` in a throwaway directory that exits 0 whatever it
is asked. The suite is hermetic in the sense that matters, which is that
it never reads the author's real ledger, and it can still express the
genuinely-absent case by passing ``ledger=UNSET``.

WHY EVERY DENY HERE NAMES ITS SUB-KIND (OPS-2006.08), with the
reproduction that bought the rule rather than an argument for it.

A deny is not one outcome. The gate emits a bracketed sub-kind because
the remedies differ: ``[review]`` means run the reviewers, ``[ledger]``
means repair infrastructure, ``[config]`` means export one variable,
``[gate]`` means the gate itself crashed and fell closed on an error it
could not classify. An assertion that only reads ``== "deny"`` cannot
tell them apart, so the specific protection can be gone while the suite
stays green on the fail-closed path that replaced it.

Measured, not supposed. A copy of the gate was sabotaged with one
statement, ``raise RuntimeError`` as the first line of ``main``'s try
block, so that every recognized push denied through the ``[gate]``
fail-closed arm and NO check in the file was reached: not the scope
resolution, not the ledger, not the attestation, not the CI arm. Against
that mutant, 21 of the 69 cases in the pre-OPS-2006.08 edition of this
file still passed, and 15 of those 21 are cases that exist to assert a
refusal (the other 6 assert an allow, read the hook text, or call
``_strip_heredocs`` directly, and pass honestly). One of the 15 passed
on a substring collision rather than on a bracketless assertion:
``test_a_deletion_deny_does_not_prescribe_pushing_the_ref`` looks for
"author decision" in the reason, and the ``[gate]`` message happens to
carry the words "an author decision, not a workaround".

So ``judge`` now takes ``kind=`` and asserts it: the reason opens with
the gate's own prefix, the bracket that FOLLOWS that prefix is read, and
it must equal ``kind``, and it must not be ``gate`` unless ``[gate]`` is
what the case is about. Both halves are needed. The positive half
catches a refusal that moved to another arm; the negative half catches
the crash-and-fail-closed regression, which no positive assertion about
a DIFFERENT kind would catch on its own. Equality on the opening bracket
rather than a substring search, because the collision above is what a
substring search looks like when it fails.

Naming them all was a sweep, and a sweep does not hold: the next case
here will be written beside one that already passes, and ``== "deny"``
is shorter and reads fine. So the rule is also a RATCHET.
``unpinned_refusal_sites`` measures this file against itself and
``test_every_refusal_this_file_asserts_names_which_check_refused``
fails on a refusal that names no check, with the escape hatch declared
in ``DELEGATES_ITS_SUB_KIND_ASSERTION`` and checked in both directions.

The taxonomy and both gate constants are READ OUT OF THE GATE BODY
rather than mirrored here, for the reason ``LEDGER_ENV`` records below:
a hand-copied literal that stops matching does not fail loudly, it
quietly stops testing what it names.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "role_review_gate.py"
#: The kit's own fake-`gh` builder, imported from the vendored companion that
#: sits beside `ci_state.py`. Loaded by path rather than imported by name
#: because `.claude/hooks` is not a package and must not become one.
_CI_MUTATIONS = HOOK.parent / "ci_state_mutations.py"
_spec = importlib.util.spec_from_file_location("_ci_state_mutations", _CI_MUTATIONS)
assert _spec and _spec.loader, f"cannot load {_CI_MUTATIONS}"
_ci_state_mutations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ci_state_mutations)
_fake_gh = _ci_state_mutations.fake_gh
#: `gh run list --json` answers, in the CLI's own vocabulary. GREEN is the
#: suite's neutral state; the others are used by the release-path cases that
#: exist to show the CI arm refusing.
CI_GREEN = (
    '[{"status":"completed","conclusion":"success",'
    '"workflowName":"tests","databaseId":1,"url":"u1"}]'
)
CI_RUNNING = (
    '[{"status":"in_progress","conclusion":null,"workflowName":"tests","databaseId":1,"url":"u1"}]'
)
CI_RED = (
    '[{"status":"completed","conclusion":"failure",'
    '"workflowName":"tests","databaseId":1,"url":"u1"}]'
)
CI_NONE = "[]"
ATTESTATION = Path(".claude") / ".role_review_attestation.json"


def gate_constant(name: str, source: Path | None = None) -> str:
    """Read a module-level string constant out of the gate body.

    Parameters
    ----------
    name : str
        The constant's name, assigned at module level in the hook.
    source : Path or None, optional
        The gate body to read. Defaults to the vendored hook. A test that
        wants to prove this really reads rather than remembers passes a
        mutated copy.

    Returns
    -------
    str
        The literal the gate assigns, evaluated with ``ast.literal_eval``
        so no code from the hook runs.

    Raises
    ------
    AssertionError
        When the assignment is absent, appears more than once, or is not a
        non-empty string. Loud is the whole point: the failure this
        replaces was silent.

    Notes
    -----
    Reading the file rather than importing it is deliberate. Importing the
    gate would put ``.claude/hooks`` on ``sys.path`` and execute the whole
    module for one string; the hook is a hash-pinned vendored row
    (``tests/test_kit_drift.py``), so the cheapest read that cannot
    perturb it wins.
    """
    lines = source.read_text(encoding="utf-8") if source else HOOK.read_text(encoding="utf-8")
    assignments = [line for line in lines.splitlines() if line.startswith(f"{name} = ")]
    assert len(assignments) == 1, (
        f"expected exactly one module-level `{name} = ...` in {source or HOOK}, "
        f"found {len(assignments)}. The gate is the authority on this value and "
        "this file must not fall back to a literal of its own."
    )
    value = ast.literal_eval(assignments[0].split("=", 1)[1].strip())
    assert isinstance(value, str) and value, f"{name} is not a non-empty string: {value!r}"
    return value


def pinned_kinds() -> set[str]:
    """The deny sub-kinds some case in THIS file names as its expectation.

    Returns
    -------
    set of str
        Every string literal passed as ``kind=`` to ``judge`` or ``decide``,
        plus the sub-kind of any direct ``assert_kind`` call.

    Notes
    -----
    Read with ``ast`` rather than a regular expression because ``attest``
    also takes a ``kind=`` keyword, in an unrelated vocabulary (which
    attestation is being written). A text scan would count ``"release"`` as
    pinned on the strength of an attestation that names it, which is
    exactly the kind of accidental agreement this file is trying to stop
    making.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id in {"judge", "decide"}:
            for keyword in node.keywords:
                if keyword.arg != "kind":
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    found.add(keyword.value.value)
        elif node.func.id == "assert_kind" and len(node.args) >= 3:
            third = node.args[2]
            if isinstance(third, ast.Constant) and isinstance(third.value, str):
                found.add(third.value)
    return found


#: Test functions allowed to reach a refusal WITHOUT naming ``kind=``, each
#: with the reason, because they call ``assert_kind`` by hand instead.
#:
#: Declared rather than merely tolerated. The ``kind=`` rule is what makes a
#: refusal assertion mean something, so the escape hatch from it is the one
#: place the rule can be lost without anything going red, and the guard below
#: checks this set in BOTH directions: an undeclared user fails, and a stale
#: declaration fails too, so the hatch cannot outlive the case that needed it.
DELEGATES_ITS_SUB_KIND_ASSERTION = {
    "test_an_unterminated_heredoc_opener_does_not_swallow_a_real_push": (
        "the shape it was written for is NO DECISION AT ALL, so the fail-open "
        "message has to be the first thing a failure prints; the sub-kind is "
        "asserted afterwards, by hand, on that case's last line"
    ),
}


def _is_gate_call(node: ast.AST) -> bool:
    """True for a call to ``judge`` or ``decide`` by name."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"judge", "decide"}
    )


def _names_a_sub_kind(call: ast.Call) -> bool:
    """True when a call passes ``kind=`` as anything but a literal ``None``.

    A literal ``None`` is excluded deliberately: ``assert_kind`` applies only
    the fail-closed rule to it, so ``kind=None`` names no check and would be
    the cheapest way past the guard below while looking like compliance.
    """
    return any(
        keyword.arg == "kind"
        and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
        for keyword in call.keywords
    )


def unpinned_refusal_sites(source: Path | None = None) -> list[tuple[str, str]]:
    """Gate calls in this file that assert nothing about WHICH check refused.

    Parameters
    ----------
    source : Path or None, optional
        The file to measure. Defaults to this one. A companion test passes a
        deliberately mutated copy, which is the only way to show this
        measures rather than agrees.

    Returns
    -------
    list of tuple of str
        ``(enclosing test name, "line N: <the call>")`` for every ``judge``
        or ``decide`` call that neither names a ``kind=`` nor is asserted to
        ALLOW. A call inside a function named in
        ``DELEGATES_ITS_SUB_KIND_ASSERTION`` is still reported, tagged with
        that function, so the caller can partition it rather than have it
        silently excused here.

    Notes
    -----
    An ALLOW assertion is the third accepted shape and not an oversight: a
    case that requires the gate to let a push through is making a decision
    claim with no sub-kind to name, and forcing ``kind=`` on it would mean
    writing an expectation the case does not hold.
    """
    text = (source or Path(__file__)).read_text(encoding="utf-8")
    tree = ast.parse(text)
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not _is_gate_call(node.left):
            continue
        if any(
            isinstance(other, ast.Constant) and other.value == "allow" for other in node.comparators
        ):
            allowed.add(id(node.left))
    sites: list[tuple[str, str]] = []
    seen: set[int] = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if not _is_gate_call(node):
                continue
            assert isinstance(node, ast.Call)
            seen.add(id(node))
            if _names_a_sub_kind(node) or id(node) in allowed:
                continue
            sites.append((function.name, f"line {node.lineno}: {ast.unparse(node)}"))
    # A gate call outside every function would be invisible to the loop above,
    # and it would run at import time where a failure is an error rather than
    # a case. There are none today; it is scanned for rather than assumed,
    # because "there are none today" is how the bare refusals got in.
    for node in ast.walk(tree):
        if not _is_gate_call(node) or id(node) in seen:
            continue
        assert isinstance(node, ast.Call)
        if _names_a_sub_kind(node) or id(node) in allowed:
            continue
        sites.append(("<module level>", f"line {node.lineno}: {ast.unparse(node)}"))
    return sites


# The variable the GATE reads. Renamed from PYFS_INCIDENT_LEDGER when the
# 0.2.16 body was vendored on 2026-08-02: kit 0.2.8 gave every workspace one
# name under the author decision LEDGER-ENVVAR. This constant must track the
# gate body, and until 2026-08-11 it had to be said that the analyst charter
# was a DIFFERENT artifact on a different kit row still reading the old name.
# The 0.2.11 charter closed that: nothing in this repository reads
# PYFS_INCIDENT_LEDGER any more, and CLAUDE.md dropped it.
#
# It is DERIVED from the gate body rather than mirrored (OPS-2006.08). A
# hand-written literal here fails in the one direction nothing reports:
# pointed at a name the gate no longer reads, `hook_env` strips a variable
# nobody consults, the REAL ledger reaches every hook subprocess, and the
# suite silently starts depending on one author's machine and on whatever
# incidents are open on it that morning. Nothing goes red at the rename;
# the tests keep passing while testing something else.
LEDGER_ENV = gate_constant("LEDGER_ENV")
#: The voice every deny opens with. Derived for the same reason: the sub-kind
#: assertions below are worth nothing if the prefix they anchor on has moved.
GATE_PREFIX = gate_constant("GATE_PREFIX")
# Built by concatenation so this file never contains the literal command
# it tests; the gate scans command text and would flag work on this file.
PUSH = "git" + " push"
#: Sub-kinds the gate carries that NO case in this file reaches, each with the
#: reason it is unreachable from here. Declared rather than omitted, so that a
#: kind arriving in a future kit body is neither silently uncovered nor
#: silently declared fine: the partition test at the end of this file fails
#: on any kind that is in neither set.
UNREACHED_DENY_KINDS = {
    # Needs `ci_state.py` to be absent from every path the gate searches,
    # which would mean deleting half of a vendoring unit this repository
    # asserts is present (tests/test_kit_drift.py). Reachable a second way,
    # as the CONFIG state of the interpolated site, which no fake `gh` can
    # produce either.
    "ci-config",
    # Needs the gate's own 50 second CI budget to run out, which no local
    # fake `gh` can consume. Already named as unreached in the CI section's
    # own note below.
    "ci-budget",
    # The gate's own comment calls this arm UNREACHABLE TODAY and says why:
    # `_push_scope` resolves the same commit-ish first and refuses with
    # [scope], so no push arrives at it. Kept there deliberately; declared
    # here for the same reason rather than quietly excluded.
    "ci-tag",
}
#: The gate spells most sub-kinds out but INTERPOLATES the CI states at one
#: site, `[ci-{state}]`, so a text scan of the gate body cannot see them. The
#: states this file reaches are read off `CI_REFUSAL_CASES` near the end
#: rather than repeated here, which is the same rule as `LEDGER_ENV`: one
#: home per fact.
GATE_INTERPOLATED_KIND_SITE = "{GATE_PREFIX} [ci-{"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stripped stdout."""
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


# Sentinel for "the variable is genuinely absent", which is now a distinct
# state from "not specified by this test" and has the opposite outcome. A
# plain None cannot carry both meanings any more.
UNSET = object()


def _clean_ledger() -> str:
    """A throwaway ledger directory whose checker always reports clean.

    Created once per session and cached. This is the NEUTRAL state for every
    case that is not about incidents: readable, answers 0, names no repository.
    Deliberately not the author's real ledger, whose contents change and whose
    open blocking entries would otherwise fail tests about refspec parsing.
    """
    global _CLEAN_LEDGER
    if _CLEAN_LEDGER is None:
        folder = Path(tempfile.mkdtemp(prefix="pyfs-clean-ledger-"))
        _CLEAN_LEDGER = stub_ledger(folder, 0, "clean")
    return _CLEAN_LEDGER


_CLEAN_LEDGER: str | None = None


def hook_env(ledger: str | object | None = None) -> dict[str, str]:
    """The environment a hook subprocess runs in.

    ``ledger`` is a path to use, ``UNSET`` to remove the variable entirely, or
    ``None`` (the default) for the clean stub above. The author's real ledger
    is never inherited in any of the three: a real open incident would fail
    tests that are not about incidents at all, which is precisely what the
    blocking entry that prompted this vendor would have done to 24 of them.
    """
    env = {k: v for k, v in os.environ.items() if k != LEDGER_ENV}
    if ledger is UNSET:
        return env
    env[LEDGER_ENV] = _clean_ledger() if ledger is None else str(ledger)
    return env


def install_gh(repo: Path, payload: str = CI_GREEN, status: int = 0) -> None:
    """Put a FAKE ``gh`` on this test's PATH, answering ``payload``.

    Reused from the vendored ``ci_state_mutations.fake_gh`` rather than
    rewritten, because the Windows half of it is not obvious and getting it
    wrong is silent: ``CreateProcess`` resolves a bare ``gh`` by appending
    ``.exe`` and nothing else, so a ``gh.bat`` is never found, every case reads
    UNKNOWN because ``gh`` is simply absent, and the case that looks like it
    passes (``gh`` exiting non-zero) passes on the not-found message instead.
    A second implementation of that would be a second place to get it wrong.

    Written INTO the repository directory, which is also the hook's cwd, and
    that is required rather than convenient: the Windows fake is a copy of this
    interpreter, so its script arrives as the first argument (the literal word
    ``run`` from ``gh run list``) and is resolved against the working
    directory. Called from ``judge`` and therefore always after the test's
    commits, so ``add_commit``'s ``git add -A`` never stages it.
    """
    _fake_gh(repo, payload, status)


def run_gate(
    repo: Path,
    command: str,
    ledger: str | object | None = None,
    gh: tuple[str, int] | None = None,
    cwd: Path | None = None,
    hook: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke one gate body on ``command`` and return the finished process.

    Split out of ``judge`` so the two cases that read something ``judge``
    discards can share the invocation instead of hand-rolling it: the
    observability line on stderr, and the mutation companion, which runs a
    SABOTAGED copy of the gate and must not be routed through the very
    assertions it exists to falsify.

    Parameters
    ----------
    cwd : Path or None, optional
        The working directory the hook runs in. Defaults to ``repo``. A
        directory outside any repository is how the ``[repo]`` arm is
        reached, and a ``git -C`` command is how it is NOT: the gate
        resolves the ``-C`` target, so such a push is judged on the repo it
        names and never reaches that arm.
    hook : Path or None, optional
        The gate body to run. Defaults to the vendored hook.
    """
    payload, status = gh if gh is not None else (CI_GREEN, 0)
    install_gh(repo, payload, status)
    env = hook_env(ledger)
    env["PATH"] = str(repo) + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        [sys.executable, str(hook or HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        cwd=cwd or repo,
        env=env,
    )


def outcome(done: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    """The (decision, reason) a finished hook process reports.

    A silent process is an allow: the gate emits no JSON on the paths that
    stay out of the way, and on the final all-checks-passed path, which
    prints to stderr and deliberately does not return an ``allow``
    permission decision.
    """
    if not done.stdout.strip():
        return "allow", ""
    out = json.loads(done.stdout)["hookSpecificOutput"]
    return str(out["permissionDecision"]), str(out.get("permissionDecisionReason", ""))


def assert_kind(decision: str, reason: str, kind: str | None, command: str) -> None:
    """Check that a refusal is the one the caller named, by sub-kind.

    Parameters
    ----------
    decision : str
        The gate's permission decision.
    reason : str
        The reason text, whose first line carries the bracketed sub-kind.
    kind : str or None
        The sub-kind the case expects, WITHOUT brackets (``"review"``,
        ``"ledger"``, ``"ci-red"``, ...). ``None`` means the caller is not
        asserting a refusal at all, and only the fail-closed rule below is
        applied.
    command : str
        Echoed into the failure text, because the parametrized cases differ
        only by the command they push.

    Notes
    -----
    Two rules, and both are needed (OPS-2006.08).

    The POSITIVE rule pins the arm: a refusal that moves from ``[review]``
    to ``[scope]`` is a different guard with a different remedy, and a
    bracketless ``== "deny"`` reads them as the same event.

    The NEGATIVE rule is the one the item exists for. ``[gate]`` is the
    fail-closed arm the hook takes when it raises an exception it cannot
    classify, so a regression that crashes the gate denies EVERYTHING and
    every bracketless refusal assertion in this file passes while no check
    in the hook has run at all. Measured against a one-line sabotage of the
    gate body: 15 refusal cases stayed green. So ``[gate]`` is refused
    everywhere except in the one case that is about ``[gate]`` itself.

    Both rules read the sub-kind that OPENS the message and compare it for
    equality, rather than searching the whole reason for a substring. A
    substring test would be satisfied by a bracket appearing anywhere in a
    long remedy paragraph, which is the shape of accidental agreement this
    file has already been caught making once, on the words "author
    decision".
    """
    if decision != "deny":
        assert kind is None, (
            f"expected a [{kind}] refusal for {command!r}, got {decision!r}. "
            "A case that names a sub-kind is asserting that the gate REFUSES."
        )
        return
    assert reason.startswith(GATE_PREFIX), (
        f"a refusal of {command!r} does not open with {GATE_PREFIX!r}: {reason!r}"
    )
    opener = re.match(r"\[([^\]\s]+)\]", reason[len(GATE_PREFIX) :].lstrip())
    assert opener, (
        f"a refusal of {command!r} carries no bracketed sub-kind after the gate "
        f"prefix, so no case here can say which check refused it: {reason!r}"
    )
    fired = opener.group(1)
    if kind != "gate":
        assert fired != "gate", (
            f"{command!r} was refused through the FAIL-CLOSED arm, not by the "
            "check this case is about. The gate raised before it could classify "
            f"anything, so nothing here was actually exercised: {reason}"
        )
    if kind is not None:
        assert fired == kind, (
            f"expected the [{kind}] refusal for {command!r}, got [{fired}]: {reason}"
        )


def judge(
    repo: Path,
    command: str,
    ledger: str | object | None = None,
    gh: tuple[str, int] | None = None,
    *,
    cwd: Path | None = None,
    kind: str | None = None,
) -> tuple[str, str]:
    """Run the hook on ``command`` and return (decision, reason).

    ``gh`` defaults to a GREEN fake, which is the neutral state for the same
    reason ``ledger`` defaults to a clean stub: since the 0.2.18 body a
    release-grade push asks the remote what CI concluded, BEFORE it asks for
    the release attestation, and anything but GREEN denies. Without a fake, six
    tests about attestation SCOPE denied at ``[ci-unknown]`` instead, each
    passing its assertion on a message about something else, and the suite took
    137 seconds talking to a network it has no business needing. Measured on
    2026-08-11, on the run that vendored the 0.2.18 gate.

    ``kind`` names the bracketed sub-kind the case expects, and is checked by
    ``assert_kind``; ``cwd`` runs the hook somewhere other than ``repo``.
    """
    decision, reason = outcome(run_gate(repo, command, ledger, gh, cwd=cwd))
    assert_kind(decision, reason, kind, command)
    return decision, reason


def decide(
    repo: Path,
    command: str,
    ledger: str | object | None = None,
    gh: tuple[str, int] | None = None,
    *,
    cwd: Path | None = None,
    kind: str | None = None,
) -> str:
    """Run the hook on ``command`` and return its permission decision."""
    return judge(repo, command, ledger, gh, cwd=cwd, kind=kind)[0]


def stub_ledger(folder: Path, exit_code: int, message: str) -> str:
    """Write a fake check_incidents.py that exits with ``exit_code``.

    The real ledger lives outside the repository, so the only way to
    exercise the branch that matters (a checker that runs and reports a
    blocking incident) is to stand one up here. Without this the gate
    could be disabled entirely and the suite would stay green.
    """
    folder.mkdir(parents=True, exist_ok=True)
    checker = folder / "check_incidents.py"
    checker.write_text(
        f"import sys\nprint({message!r} + ' ' + sys.argv[1])\nsys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return str(folder)


def attest(repo: Path, commits: list[str], kind: str = "review") -> None:
    """Write an attestation covering ``commits`` (bypassing the writer)."""
    path = repo / ATTESTATION
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    existing[kind] = {"head": commits[0] if commits else "", "commits": commits}
    path.write_text(json.dumps(existing), encoding="utf-8")


def add_commit(repo: Path, name: str) -> str:
    """Add one commit and return its sha."""
    (repo / f"{name}.txt").write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


def _pushed(repo: Path) -> list[str]:
    """The commits a push from ``repo`` would make new."""
    listed = git(repo, "rev-list", "HEAD", "--not", "--remotes")
    return [c for c in listed.splitlines() if c]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one pushed commit and a local bare remote."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "T")
    # Pin push.default so the baseline (a bare `push origin` resolves to the
    # current branch) does not depend on the developer's global git config;
    # a machine set to push.default=matching would otherwise flip the
    # unscopable-bare-push tests.
    git(work, "config", "push.default", "simple")
    (work / "a.txt").write_text("a", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    # Name the branch, so a test that pushes "main" by name pushes a ref
    # that exists locally. git init picks master or main depending on the
    # installation, and the gate now resolves the named ref.
    git(work, "branch", "-M", "main")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(work, "fetch", "-q", "origin")
    return work


def test_unattested_push_is_denied(repo: Path) -> None:
    """A new commit with no attestation never ships."""
    add_commit(repo, "one")
    assert decide(repo, f"{PUSH} origin main", kind="review") == "deny"


def test_attested_range_is_allowed(repo: Path) -> None:
    """An attestation covering every new commit clears the gate."""
    first = add_commit(repo, "one")
    second = add_commit(repo, "two")
    attest(repo, [second, first])
    assert decide(repo, f"{PUSH} origin main") == "allow"


def test_attesting_only_the_tip_is_denied(repo: Path) -> None:
    """The sister library's review found this: no free rides for ancestors.

    The fixture forces two unpushed commits rather than letting the case
    skip itself when the repository happens to hold only one, because
    the previous evidence for this gate was a script whose main case
    could skip itself and still report all clear.
    """
    add_commit(repo, "one")
    tip = add_commit(repo, "two")
    attest(repo, [tip])
    assert decide(repo, f"{PUSH} origin main", kind="review") == "deny"


@pytest.mark.parametrize("spec", ["v9.9.9", "HEAD:refs/tags/v9.9.9"])
def test_tag_push_needs_the_release_attestation_when_the_branch_is_pushed(
    repo: Path, spec: str
) -> None:
    """The regression the range fix introduced, and the reason for in_scope.

    Pushing the branch first leaves the tagged commit already on the
    remote, so the range of new commits is empty. Set containment over
    an empty range is vacuously true, which briefly let an unattested
    tag reach the PyPI publish workflow. Both this exact incident
    condition and the ``HEAD:refs/tags/vX`` refspec form (the two shapes
    named in INC-20260724-0839) are exercised together here.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(repo, "fetch", "-q", "origin")
    git(repo, "tag", "v9.9.9")
    assert git(repo, "rev-list", "HEAD", "--not", "--remotes") == ""
    # Review-attested but not release-attested: the release gate holds.
    assert decide(repo, f"{PUSH} origin {spec}", kind="release") == "deny", spec
    attest(repo, [head], kind="release")
    assert decide(repo, f"{PUSH} origin {spec}") == "allow", spec


def test_a_configured_but_unreadable_ledger_blocks(repo: Path, tmp_path: Path) -> None:
    """A ledger that cannot be consulted must not read as all clear."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin main", ledger=str(tmp_path / "nowhere"), kind="ledger") == (
        "deny"
    )


def test_an_unconfigured_ledger_now_denies(repo: Path) -> None:
    """Without the environment variable the push is REFUSED, not waved through.

    This test asserted the opposite until 2026-08-02, and the inversion is the
    substance of the kit 0.2.8 promotion rather than a detail of it. The old
    contract reasoned that the shared ledger is one author's local artifact, so
    a clone that never configured it should still be able to push once its work
    was reviewed. That reasoning is about a FORK, and it was applied to the
    variable being absent, which is a different question with the same symptom.

    What it cost, measured at the coordination level and not hypothesized: the
    repository that WRITES the incidents derived a ledger variable name that
    had never existed, unset read as does-not-apply, and it pushed past a
    blocking incident of its own authorship. Of the three workspaces, the gate
    stopped two and the silence was in the one with the most to lose.

    So the rule is now that a guard may not read its own missing configuration
    as permission. The remedy for a genuine fork is to export the variable at a
    ledger it can read, which is one line and is named in the deny text; the
    remedy for the old behaviour was nothing, because nothing was reported.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=UNSET, kind="config")
    assert decision == "deny"
    assert LEDGER_ENV in reason, reason


def test_a_trailing_command_does_not_defeat_the_gate(repo: Path) -> None:
    """``push; echo done`` reaches the remote, so it must be recognized.

    ``shlex(posix=False)`` leaves ``push;`` as a single token, and the
    v1 comparison against ``"push"`` missed it. That failed open on the
    most natural way to type a push followed by anything else.

    The sub-kind here is [scope] and NOT [review], which is worth stating
    because it is not what the name of this case suggests. The gate reads
    the trailing ``echo`` as a ref, cannot resolve it, and refuses on scope
    before it ever asks about attestation. That is still the right answer
    (a push whose refs the gate cannot enumerate is refused), and the
    property this case is named for holds: the push was RECOGNIZED rather
    than passed over. Measured, and pinned so a body that started ignoring
    everything after the separator would show up as a changed sub-kind
    instead of an unchanged "deny".
    """
    add_commit(repo, "one")
    assert decide(repo, f"{PUSH} origin main; echo done", kind="scope") == "deny"


def test_a_quoted_mention_of_the_command_is_not_a_push(repo: Path) -> None:
    """A commit message naming the command must not trip the gate."""
    add_commit(repo, "one")
    assert decide(repo, f'git commit -m "explain the {PUSH} gate"') == "allow"


def test_a_heredoc_commit_that_mentions_the_push_is_not_a_push(repo: Path) -> None:
    """A commit message written as a heredoc body that names the push must allow.

    ``_strip_heredocs`` removes the heredoc body before tokenizing, so a
    commit that documents a push is not misread as one. The regex that
    finds the heredoc opener carried a stray control byte that made it
    match nothing, so the stripper was dead and every heredoc commit
    naming the push was falsely denied (INC-20260724-0912). All three
    delimiter forms are exercised.
    """
    add_commit(repo, "one")
    for opener, closer in (("<<'MSG'", "MSG"), ("<<MSG", "MSG"), ('<<"MSG"', "MSG")):
        cmd = f"git commit -F- {opener}\ndocument the {PUSH} gate\n{closer}"
        assert decide(repo, cmd) == "allow", opener


# INC-20260802-1450-shared. Kept as a table rather than three separate
# functions because the point is the CLASS: every one of these is two lines of
# ordinary shell with no heredoc in it anywhere, and the label is what a
# failure prints.
UNTERMINATED_OPENER_CASES = [
    (
        "a message naming <<EOF, then a real push on the next line",
        f'git commit -m "see the <<EOF form"\n{PUSH} origin main',
    ),
    (
        "the same with the opener inside a -m and a trailing &&",
        f'git commit -m "about <<HEREDOC" && \\\n{PUSH} origin main',
    ),
    (
        "a << that is not a heredoc at all, then a real push",
        f'git commit -m "a << b"\n{PUSH} origin main',
    ),
]


@pytest.mark.parametrize("label,command", UNTERMINATED_OPENER_CASES, ids=lambda v: v[:40])
def test_an_unterminated_heredoc_opener_does_not_swallow_a_real_push(
    repo: Path, label: str, command: str
) -> None:
    """A heredoc opener that never terminates must strip NOTHING.

    INC-20260802-1450-shared, and it is the worst shape this mechanism has: a
    FAIL-OPEN. ``_strip_heredocs`` removes heredoc bodies before tokenizing so
    that a commit message merely describing a push does not read as one. Its
    opener pattern matched anywhere in a line, including inside a quoted commit
    message, and when no matching delimiter line ever arrived it dropped every
    remaining line. The real push on the next line went with them, and the gate
    returned without requiring an attestation, reading the ledger, or checking
    for a release tag. Not a weaker refusal: no refusal.

    Measured here against the deployed 0.2.4 body before it was replaced, all
    three cases returned NO DECISION AT ALL while the control below denied.

    The structural rule the fix encodes, and the reason this test asserts on
    every branch rather than sampling one: stripping can only ever REMOVE
    tokens from what is scanned, so for an input the stripper does not
    understand there is exactly one safe direction, and it is to strip nothing.
    Do not weaken this to "the parse fails and the raw-text fallback catches
    it". That fallback is not a net. ``shlex.split(posix=False)`` does not
    raise on every unbalanced quote (given ``git commit -m @'`` it returns
    ``@'`` as an ordinary token and parses on), so a stripping bug produces a
    CLEAN parse with the push missing from it and nothing downstream notices.
    """
    decision, reason = judge(repo, command)
    assert decision == "deny", (
        f"{label}: the gate returned {decision!r} on a command containing a "
        "real push. An empty decision here is the fail-open, not an allow."
    )
    assert reason, f"{label}: denied with no reason text"
    # The sub-kind is checked SECOND here, and only here, so the fail-open
    # message above stays the first thing a failure prints: no-decision is
    # the shape this case was written for, and a caller that reads the
    # bracket first would report it as a missing [review] instead.
    assert_kind(decision, reason, "review", command)


def test_the_control_for_the_unterminated_opener_cases_denies(repo: Path) -> None:
    """A bare unattested push denies, so the cases above can see a deny at all.

    Without this the three above are unfalsifiable: a harness that could never
    produce a deny would pass them for the wrong reason. This is the same
    control that was measured alongside the red run.
    """
    add_commit(repo, "one")
    assert decide(repo, f"{PUSH} origin main", kind="review") == "deny"


def test_a_terminated_heredoc_does_not_hide_a_push_after_it(repo: Path) -> None:
    """Stripping stops at the delimiter, so a push AFTER the body is still seen.

    The companion pin to the allow case above. Together they bound the fix from
    both sides: an unterminated opener must strip nothing, and a terminated one
    must strip exactly its own body and no more. A fix that satisfied only the
    fail-open could have been written by disabling the stripper entirely, and
    this is the assertion that would have caught it.
    """
    add_commit(repo, "one")
    cmd = f"git commit -F- <<MSG\na message\nMSG\n{PUSH} origin main"
    assert decide(repo, cmd, kind="review") == "deny"


def test_a_dash_c_push_from_outside_the_repo_is_recognized(repo: Path, tmp_path: Path) -> None:
    """`git -C <repo> push` run from a non-repo cwd must still be gated.

    The gate resolves the repository from the -C global option, not only
    from the working directory, so a push issued from elsewhere cannot
    slip past it.

    THE SUB-KIND IS THE ASSERTION HERE, and it is [review] rather than
    [repo], which is the opposite of what the cwd suggests. That is the
    whole content of the case: ``_find_git_push`` returns the ``-C``
    target, the gate resolves the toplevel from THAT and not from its own
    working directory, so the "no repository resolves" arm is never
    reached and the push is judged on the repo it named, where one
    unattested commit is waiting. A case that only asserted "deny" would
    pass identically if the gate had ignored ``-C`` and refused because it
    could not find a repository, which is the bug this test is named for
    read backwards.
    """
    add_commit(repo, "one")
    outside = tmp_path / "outside"
    outside.mkdir()
    cmd = f"git -C {repo.as_posix()} " + "push origin main"
    assert decide(repo, cmd, cwd=outside, kind="review") == "deny"


def test_an_unbalanced_quote_naming_git_and_push_fails_closed(repo: Path) -> None:
    """A command shlex cannot parse must fail closed when it looks like a push.

    On unbalanced quotes the tokenizer gives up; if the raw text still
    carries both ``git`` and ``push`` as words, the gate treats it as a
    push it could not confirm safe rather than allowing it through.
    """
    add_commit(repo, "one")
    cmd = "git " + 'push origin "main'  # unterminated quote
    # [review], not [scope]: the raw-text fallback recognizes the push but
    # hands the scope resolver no parsed refs, so the gate scopes HEAD and
    # refuses on the unattested commit. Measured, not assumed.
    assert decide(repo, cmd, kind="review") == "deny"


def test_a_named_branch_is_scoped_by_that_branch_not_by_head(repo: Path) -> None:
    """Pushing a ref that is not HEAD must be judged on that ref.

    Scoping from HEAD let a branch carrying unattested commits ship
    whenever HEAD happened to be attested, which is the same free ride
    for unreviewed work that the range check exists to stop.
    """
    head = add_commit(repo, "one")
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    add_commit(repo, "unreviewed")
    git(repo, "checkout", "-q", "main")
    attest(repo, [head])
    assert git(repo, "rev-parse", "HEAD") == head
    assert decide(repo, f"{PUSH} origin side", kind="review") == "deny"
    assert decide(repo, f"{PUSH} origin side:main", kind="review") == "deny"


def test_a_push_the_gate_cannot_scope_is_denied(repo: Path) -> None:
    """--all, --mirror and --tags send refs the gate cannot enumerate.

    Offline there is no way to tell which tags the remote already has, so
    the honest answer is to refuse and ask for the ref by name. Allowing
    would be a guard discharging its assertion by not making one:
    --follow-tags is the ordinary release command, and it published an
    unattested tag while the suite stayed green.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    attest(repo, [head], kind="release")
    for form in ("--all", "--mirror", "--tags", "--follow-tags"):
        decision, reason = judge(repo, f"{PUSH} {form} origin", kind="scope")
        assert decision == "deny", form
        assert "cannot determine" in reason, form


def test_a_deletion_refspec_is_denied(repo: Path) -> None:
    """A push that removes a remote ref is not something the gate can bless.

    v0.2.2 reframes it as a policy stop: a deletion's scope IS resolvable, so
    it no longer shares the "cannot determine scope" wrapper. It is tagged
    [policy], with the honest reason.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin :main", kind="policy")
    assert decision == "deny"
    assert "deletes a published remote ref" in reason
    assert "guesses at its own scope" not in reason


def test_an_open_blocking_incident_denies(repo: Path, tmp_path: Path) -> None:
    """The branch the incident gate exists for, driven by a real checker.

    Only the unreachable-ledger path was covered before, so the whole
    incident gate could be deleted with the suite green.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    ledger = stub_ledger(tmp_path / "ledger", 1, "INC-1 open and blocking for")
    # v0.2.0 folded the three divergent prefixes ("INCIDENT GATE:",
    # "RELEASE GATE:", "ROLE-REVIEW GATE:") into one "role-review gate:"
    # voice with a bracketed sub-kind, which `kind=` now pins from the
    # gate's own constant rather than from a literal written out here.
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=ledger, kind="incident")
    assert decision == "deny"
    assert "INC-1 open and blocking for" in reason
    # The two failure classes have opposite remedies and must not share
    # a message: this one is a real incident, not an unreadable ledger.
    assert "incident-analyst" in reason
    assert "could not be consulted" not in reason


def test_a_clean_ledger_allows(repo: Path, tmp_path: Path) -> None:
    """A checker that reports no blocking incident must not block."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    ledger = stub_ledger(tmp_path / "ledger", 0, "clean for")
    assert decide(repo, f"{PUSH} origin main", ledger=ledger) == "allow"


def test_the_incident_query_uses_the_project_name(repo: Path, tmp_path: Path) -> None:
    """The queried identity must survive a clone into a renamed directory.

    Taking it from the folder name meant a clone named anything else
    queried an unknown repository, got a clean answer, and shipped.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    (repo / "pyproject.toml").write_text('[project]\nname = "pyflightstream"\n', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pyproject")
    attest(repo, _pushed(repo))
    ledger = stub_ledger(tmp_path / "ledger", 1, "queried")
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=ledger, kind="incident")
    assert decision == "deny"
    assert "queried pyflightstream" in reason, reason


def test_the_deny_names_the_range_to_review(repo: Path) -> None:
    """The reason must carry the command that clears it, not just a complaint.

    A reader who follows the role-review skill default reviews the last
    commit, which is the wrong scope for this denial and re-arms the gate.
    """
    add_commit(repo, "one")
    tip = add_commit(repo, "two")
    decision, reason = judge(repo, f"{PUSH} origin main", kind="review")
    assert decision == "deny"
    assert f"{tip} --not --remotes" in reason, reason


def test_the_fail_closed_reason_does_not_offer_to_disable_the_gate() -> None:
    """A confused gate must not hand over its own bypass as a remedy.

    The fail-closed message is read by an agent under time pressure. It
    once offered turning the hook off through /hooks as a co-equal
    option, next to actually fixing the problem.
    """
    text = HOOK.read_text(encoding="utf-8")
    assert "via /hooks" not in text
    assert "disable the hook" not in text


def test_settings_json_wires_the_hook() -> None:
    """A hook nobody invokes is not a guard.

    Every other test here runs the script by path, so the suite passed
    identically with the registration deleted, the matcher narrowed, or
    the path drifted.
    """
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    wired = [
        hook
        for entry in entries
        for hook in entry.get("hooks", [])
        if "role_review_gate.py" in hook.get("command", "")
    ]
    assert wired, "no PreToolUse hook invokes role_review_gate.py"
    matchers = [
        entry["matcher"]
        for entry in entries
        if any("role_review_gate.py" in h.get("command", "") for h in entry["hooks"])
    ]
    assert any("Bash" in m and "PowerShell" in m for m in matchers), matchers


@pytest.mark.parametrize(
    "form",
    ["--follow-tag", "--tag", "--mirro", "--al", "--delet", "--prune"],
)
def test_an_abbreviated_blanket_option_is_still_refused(repo: Path, form: str) -> None:
    """Git accepts any unambiguous prefix of a long option.

    A refusal keyed on exact spellings moved the hole rather than
    closing it: `--follow-tag` runs, and it published an unattested tag
    four keystrokes short of the spelling the gate knew.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    attest(repo, [head], kind="release")
    decision, reason = judge(repo, f"{PUSH} {form} origin main", kind="scope")
    assert decision == "deny", form
    assert "cannot determine" in reason, form


@pytest.mark.parametrize(
    "option",
    ["-u", "--force-with-lease", "-q", "--atomic", "--dry-run", "-o ci.skip"],
)
def test_an_ordinary_option_does_not_block_an_attested_push(repo: Path, option: str) -> None:
    """The positive control the refusal needs.

    Widening the refusal is the natural fix for the abbreviation hole,
    and without this the suite cannot tell a correct widening from a
    gate that blocks every real push.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} {option} origin main") == "allow", option


@pytest.mark.parametrize(
    "spec",
    ["v9.9.9:v9.9.9", "refs/tags/v9.9.9:refs/tags/v9.9.9", "HEAD:refs/tags/v9.9.9"],
)
def test_a_tag_written_as_a_refspec_is_still_release_grade(repo: Path, spec: str) -> None:
    """The form a blocked operator reaches for next.

    Release classification matched the whole token, so a colon refspec
    scoped correctly, passed the review gate, and skipped the release
    attestation for a syntax git treats as equivalent.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "tag", "v9.9.9")
    assert decide(repo, f"{PUSH} origin {spec}", kind="release") == "deny", spec
    attest(repo, [head], kind="release")
    assert decide(repo, f"{PUSH} origin {spec}") == "allow", spec


def test_a_configured_push_refspec_makes_a_bare_push_unscopable(repo: Path) -> None:
    """`git push origin` does not always mean the current branch.

    Under push.default=matching, or with remote.<name>.push configured,
    a bare push sends every matching branch while the gate scoped HEAD
    alone, so unattested commits on any other branch shipped.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin") == "allow"
    git(repo, "config", "push.default", "matching")
    decision, reason = judge(repo, f"{PUSH} origin", kind="scope")
    assert decision == "deny"
    assert "cannot determine" in reason
    git(repo, "config", "push.default", "simple")
    git(repo, "config", "remote.origin.push", "refs/heads/*:refs/heads/*")
    assert decide(repo, f"{PUSH} origin", kind="scope") == "deny"


def test_a_multi_ref_push_scopes_every_ref(repo: Path) -> None:
    """The release-day form: branch and tag in one command."""
    head = add_commit(repo, "one")
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    unattested = add_commit(repo, "unreviewed")
    git(repo, "checkout", "-q", "main")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin main side", kind="review")
    assert decision == "deny"
    assert unattested[:12] in reason


def test_a_deletion_deny_does_not_prescribe_pushing_the_ref(repo: Path) -> None:
    """A fix that cannot reach the goal is not a fix.

    Telling a user who wants to remove a remote ref to push one by name
    is unactionable, and every unscopable case shared that one sentence.

    ``kind="policy"`` is load-bearing rather than decorative here, and this
    case is the reason the negative half of ``assert_kind`` exists. Under a
    sabotaged gate that denied everything through the fail-closed arm, this
    test still PASSED: the ``[gate]`` message ends "turning the gate off to
    ship is an author decision, not a workaround", so its one substring
    assertion matched a message about something else entirely.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    _, reason = judge(repo, f"{PUSH} origin :main", kind="policy")
    assert "author decision" in reason
    assert "Push the branch or tag by name" not in reason


def test_the_deny_range_command_is_one_git_can_run(repo: Path) -> None:
    """A synthesized `<oldest>^..<tip>` dies on a root commit.

    The reason must print the expression the gate itself computed, not
    a range reconstructed from list positions.
    """
    add_commit(repo, "one")
    _, reason = judge(repo, f"{PUSH} origin main", kind="review")
    assert "--not --remotes" in reason
    assert "^.." not in reason


def test_an_unreadable_incident_file_gets_the_repair_remedy(repo: Path, tmp_path: Path) -> None:
    """The two incident classes must stay separable from checker output."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    ledger = stub_ledger(tmp_path / "ledger", 1, "UNREADABLE header in INC-2 for")
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=ledger, kind="ledger")
    assert decision == "deny"
    assert "could not be consulted" in reason
    assert "incident-analyst" not in reason


def test_the_identity_ignores_other_tables_and_inline_comments(repo: Path, tmp_path: Path) -> None:
    """A prefix match on a raw line is not a TOML parser."""
    head = add_commit(repo, "one")
    (repo / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "wrong"\n\n[project]\nname = "pyflightstream"  # published\n',
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pyproject")
    attest(repo, [*_pushed(repo), head])
    ledger = stub_ledger(tmp_path / "ledger", 1, "queried")
    _, reason = judge(repo, f"{PUSH} origin main", ledger=ledger, kind="incident")
    assert "queried pyflightstream\n" in reason or "queried pyflightstream " in reason, reason


def test_a_bare_push_resolves_the_remote_it_would_actually_use(repo: Path) -> None:
    """`git push` with no remote does not always mean origin.

    Git resolves branch.<current>.pushRemote, then remote.pushDefault,
    then branch.<current>.remote, then origin. Reading the config for
    `origin` alone closed the push.default half of this hole and left
    the remote-selection half open.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "remote", "add", "upstream", str(repo.parent / "remote.git"))
    git(repo, "config", "branch.main.remote", "upstream")
    git(repo, "config", "remote.upstream.push", "refs/heads/*:refs/heads/*")
    decision, reason = judge(repo, PUSH, kind="scope")
    assert decision == "deny"
    assert "cannot determine" in reason


def test_the_review_deny_tells_a_non_head_push_to_pass_the_ref(repo: Path) -> None:
    """The review check runs first, so it is where the loop happens.

    The release deny carries the "pass the ref" instruction, but a
    review denial on a ref behind HEAD is reached first, and the skill's
    documented invocation stamps HEAD again: push, deny, re-attest,
    deny.
    """
    add_commit(repo, "one")
    _, reason = judge(repo, f"{PUSH} origin main", kind="review")
    assert "write_attestation.py review" in reason
    assert "stamps HEAD by default" in reason


def test_the_deny_range_covers_every_ref_it_refused(repo: Path) -> None:
    """Naming targets[0] understated the scope on a multi-ref push."""
    head = add_commit(repo, "one")
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    add_commit(repo, "unreviewed")
    git(repo, "checkout", "-q", "main")
    attest(repo, [head])
    _, reason = judge(repo, f"{PUSH} origin main side", kind="review")
    side = git(repo, "rev-parse", "side")
    assert side in reason


def test_the_review_deny_names_the_ref_that_is_behind_head(repo: Path) -> None:
    """The loop only happens when the pushed ref is not HEAD.

    An earlier test pushed `main` while main was HEAD, so the deny could
    name HEAD unconditionally and still pass: the scenario in its own
    name was never exercised.
    """
    behind = add_commit(repo, "one")
    git(repo, "tag", "v0.1.0")
    add_commit(repo, "two")
    assert git(repo, "rev-parse", "v0.1.0") == behind
    assert git(repo, "rev-parse", "HEAD") != behind
    _, reason = judge(repo, f"{PUSH} origin v0.1.0", kind="review")
    assert "write_attestation.py review" in reason
    # Naming HEAD here is the loop: the writer would stamp HEAD, which
    # does not cover the tag, and the same denial repeats.
    assert "<passes,that,ran> v0.1.0" in reason, reason


# ---------------------------------------------------------------------------
# v0.2.0/0.2.1 gate, vendored from the shared process kit. These encode the
# NEW contract, so they would fail on the pre-vendor gate: they are written
# failing-test-first per the structural-fix rule, alongside the gate they
# exercise.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("force", ["-f", "--force"])
def test_bare_force_is_denied_as_author_only(repo: Path, force: str) -> None:
    """Unconditional force rewrites published history, which no attestation
    covers (author call, 2026-07-24).

    It denies even when the range is fully attested: the refusal is on
    policy, not scope, so review cannot license it.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} {force} origin main", kind="policy")
    assert decision == "deny", force
    assert "rewrites published history" in reason, reason
    assert "--force-with-lease" in reason, reason


@pytest.mark.parametrize("safe", ["--force-with-lease", "--force-if-includes"])
def test_safe_force_variants_ride_the_attestation_path(repo: Path, safe: str) -> None:
    """The safe force variants refuse on their own when the remote moved, so
    they stay on the normal attestation path rather than being refused as
    author-only. An attested push with one must clear the gate.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} {safe} origin main") == "allow", safe


def test_a_shell_wrapped_push_is_detected(repo: Path) -> None:
    """``bash -c "git push"`` runs a real push inside a quoted token whose
    basename is the shell, not git.

    The pre-v0.2.0 gate looked only for a git executable and failed OPEN on
    this; v0.2.0 recognizes the wrapper by shell family and recurses on the
    inner command.
    """
    add_commit(repo, "one")
    assert decide(repo, f'bash -c "{PUSH} origin main"', kind="review") == "deny"


def test_a_nested_shell_wrapped_push_is_detected(repo: Path) -> None:
    """A single nesting must not defeat the gate: recursion is bounded but
    deeper than one level.
    """
    add_commit(repo, "one")
    cmd = 'bash -c "bash -c ' + "'" + f"{PUSH} origin main" + "'" + '"'
    assert decide(repo, cmd, kind="review") == "deny"


def test_the_heredoc_stripper_removes_the_body() -> None:
    """Independent liveness guard for INC-20260724-0912, re-forked by the
    0.2.0 kit body and fixed in 0.2.1.

    A stray control byte inside the heredoc-opener regex made the stripper
    match nothing. The neighbouring
    test_a_heredoc_commit_that_mentions_the_push_is_not_a_push pins the
    end-to-end DECISION; this one asserts the underlying property directly on
    `_strip_heredocs`, so a dead stripper fails even if some other path
    happened to reach the same allow. It imports the vendored hook module by
    path.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gate_under_test", HOOK)
    gate = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(gate)
    cmd = f"git commit -F- <<'MSG'\ndocument the {PUSH} gate\nMSG"
    stripped = gate._strip_heredocs(cmd)
    assert stripped != cmd, "the stripper did nothing: the opener regex is dead"
    assert "document the" not in stripped, "the heredoc body survived stripping"
    assert gate._find_git_push(cmd)[0] is False, "a stripped heredoc must not read as a push"


def test_a_commit_only_on_another_remote_is_still_in_scope_for_origin(
    repo: Path, tmp_path: Path
) -> None:
    """v0.2.0 scopes the pushed range to the TARGET remote.

    The pushed range is `<tip> --not --remotes=<remote>` for a known remote,
    not the bare `--not --remotes`. So an ancestor already on a DIFFERENT
    remote is no longer treated as already-shipped to origin: it stays in
    scope and must be attested. Bare `--remotes` would exclude it and let it
    reach origin unreviewed.
    """
    other = tmp_path / "other.git"
    subprocess.run(["git", "init", "--bare", "-q", str(other)], check=True)
    git(repo, "remote", "add", "other", str(other))
    ancestor = add_commit(repo, "ancestor")
    tip = add_commit(repo, "tip")
    # Publish only the ancestor to the OTHER remote, never to origin.
    git(repo, "push", "-q", "other", f"{ancestor}:refs/heads/main")
    git(repo, "fetch", "-q", "other")
    # Attest only the tip; the ancestor is covered by no attestation.
    attest(repo, [tip])
    decision, reason = judge(repo, f"{PUSH} origin main", kind="review")
    assert decision == "deny"
    assert ancestor[:12] in reason, (
        "an ancestor present only on another remote must count as in-scope for a push to origin"
    )


def test_a_multi_tag_release_deny_names_every_tag(repo: Path) -> None:
    """The release deny must name ALL version tags being pushed.

    A multi-tag push that reported only the first tag left the writer command
    short, so a second tag stayed uncovered and the same denial repeated. The
    review gate is satisfied here (the commit is review-attested) so control
    reaches the release check, which must list both tags.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])  # review only, no release attestation
    git(repo, "tag", "v9.9.8")
    git(repo, "tag", "v9.9.9")
    decision, reason = judge(repo, f"{PUSH} origin v9.9.8 v9.9.9", kind="release")
    assert decision == "deny"
    assert "v9.9.8" in reason and "v9.9.9" in reason, reason


def test_the_final_allow_writes_one_observability_line(repo: Path) -> None:
    """A passing gate must not be indistinguishable from an absent one.

    The final all-checks-passed allow prints one stderr line naming the repo
    and the in-scope count, while staying a silent (non-``allow``) permission
    outcome so it does not auto-approve and bypass the normal permission flow.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    # One of the two cases that stays off `judge`: it reads the stderr line
    # and the empty stdout, both of which `judge` discards.
    done = run_gate(repo, f"{PUSH} origin main")
    assert done.stdout.strip() == "", "the final allow must stay a silent permission outcome"
    assert f"{GATE_PREFIX} evaluated and ALLOWED" in done.stderr, done.stderr


def test_the_deny_bracket_taxonomy_matches_the_remedy_class(repo: Path, tmp_path: Path) -> None:
    """v0.2.2 gave every deny path a bracketed sub-kind matching its remedy.

    The two POLICY stops whose scope is fully resolvable (unconditional force,
    ref deletion) are [policy], no longer sharing the scope wrapper that
    stated a cause the code knew was false. A genuinely unresolvable option is
    [scope]. A misconfigured/unreadable ledger is [ledger] (fix config/infra),
    distinct from a real open incident's [incident] (run the analyst). No
    allow/deny decision changed; only the message taxonomy.

    Since OPS-2006.08 this is no longer the only case that reads a bracket:
    every refusal in the file now names its own. What survives here, and is
    why it is not folded away, is that the remedy classes are asserted
    DISTINCT from ONE repository state, so a body that collapsed two of them
    into a single message fails here even though each individual case would
    still find its own substring somewhere.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])

    judge(repo, f"{PUSH} --force origin main", kind="policy")
    judge(repo, f"{PUSH} origin :main", kind="policy")
    judge(repo, f"{PUSH} --frobnicate origin main", kind="scope")
    judge(repo, f"{PUSH} origin main", ledger=str(tmp_path / "nowhere"), kind="ledger")

    # A non-repo working directory: the "looks like a push but no repo" stop,
    # and the ONE case in this file that reaches [repo]. The `git -C` case
    # earlier does NOT, which is measured rather than assumed: the gate
    # resolves the -C target and judges the repository that path names.
    outside = tmp_path / "outside"
    outside.mkdir()
    judge(repo, f"{PUSH} origin main", cwd=outside, kind="repo")


# ---------------------------------------------------------------------------
# The CI-green release arm (kit 0.2.18).
#
# These cases exist because this repository DELETED its own bridge hook
# (.claude/hooks/ci_release_gate.py) in the commit that vendored the 0.2.18
# body. The deletion is only defensible if the replacement is proven HERE, on
# this repository's own tree, rather than trusted because the kit says so. Each
# case below drives the real hook end to end with a fake `gh` answering in the
# CLI's own vocabulary.
#
# WHAT THESE DO NOT COVER, printed rather than implied: the gate has three arms
# no case here reaches (OSError, TimeoutExpired, and CI budget exhaustion).
# They are named in the kit's own companion as unreached and are not counted as
# covered by anything in this file.
# ---------------------------------------------------------------------------


def _release_ready(repo: Path) -> str:
    """A repository whose only remaining obstacle to a tag push is CI."""
    head = add_commit(repo, "one")
    git(repo, "tag", "v9.9.9")
    attest(repo, [head])
    attest(repo, [head], kind="release")
    return head


#: The CI refusals, as a named table rather than an inline list, because the
#: taxonomy-coverage test at the end of this file reads the sub-kinds off it.
#: The gate interpolates these three into `[ci-<state>]` at a single site, so
#: a scan of the gate body cannot enumerate them and this table is the only
#: place that knows which ones a case here actually drives.
CI_REFUSAL_CASES = [
    ("CI still running", CI_RUNNING, 0, "ci-running"),
    ("CI failed", CI_RED, 0, "ci-red"),
    ("no run at all for the sha", CI_NONE, 0, "ci-unknown"),
    ("gh itself failing", "HTTP 401: Bad credentials", 1, "ci-unknown"),
]


@pytest.mark.parametrize(("label", "payload", "status", "kind"), CI_REFUSAL_CASES)
def test_a_release_grade_push_is_refused_unless_ci_concluded_successfully(
    repo: Path, label: str, payload: str, status: int, kind: str
) -> None:
    """Unconcluded, red, absent and unreadable CI all DENY a version tag.

    This is the rule the v0.7.0 tag was published past: it went out fifteen
    seconds after its branch, with CI still running and then red. Both
    attestations are in place in every case here, so nothing but the CI answer
    can be doing the refusing.

    ABSENT and UNREADABLE deny on the same reasoning as the incident ledger: a
    guard that reads its own missing information as permission is not a guard.
    """
    _release_ready(repo)
    decision, reason = judge(repo, f"{PUSH} origin v9.9.9", gh=(payload, status), kind=kind)
    assert decision == "deny", f"{label}: {reason}"
    assert "v9.9.9" in reason, reason


def test_a_release_grade_push_goes_through_when_ci_is_green(repo: Path) -> None:
    """The negative control. Without it the four refusals above prove only
    that this gate denies release-grade pushes, which any broken gate does.
    """
    _release_ready(repo)
    assert decide(repo, f"{PUSH} origin v9.9.9", gh=(CI_GREEN, 0)) == "allow"


def test_an_ordinary_branch_push_never_asks_ci(repo: Path) -> None:
    """The CI arm fires on a VERSION TAG and on nothing else.

    A gate that asked on every push would spend a rate limit and a network
    round trip on the ninety-nine pushes out of a hundred that publish
    nothing. Driven with `gh` answering RED: an ordinary push must still be
    allowed, which it can only be if the arm was never entered.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin main", gh=(CI_RED, 0)) == "allow"


def test_the_configured_hook_timeout_exceeds_the_gates_own_ci_budget() -> None:
    """A hook the harness kills emits no decision, and no decision is an ALLOW.

    Rescued from the deleted bridge test, which asserted exactly this about
    itself, and it is the one assertion of that file that did not become
    redundant: the kit body carries its own CI_BUDGET_SECONDS and its own
    comment saying a consumer whose hook timeout sits below it "has a gate that
    can fail open on a slow network", while the number that decides it lives in
    THIS repository's settings and cannot be asserted from the kit.

    Measured on arrival: the settings said 30 and the vendored 0.2.18 body
    budgets 50, so taking the gate without touching the wiring would have
    shipped exactly that hole.
    """
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    configured = [
        hook.get("timeout")
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry.get("hooks", [])
        if "role_review_gate.py" in hook.get("command", "")
    ]
    assert configured and all(t is not None for t in configured), (
        "the gate is wired with no explicit timeout, so it inherits the "
        "harness default and this assertion cannot be made at all"
    )
    source = HOOK.read_text(encoding="utf-8")
    budget = next(
        float(line.split("=", 1)[1].strip())
        for line in source.splitlines()
        if line.startswith("CI_BUDGET_SECONDS")
    )
    for timeout in configured:
        assert budget < float(timeout), (
            f"the gate budgets {budget}s of CI work under a {timeout}s harness "
            "timeout. If the harness kills it first there is no deny, only "
            "silence, and silence is permission."
        )


# ---------------------------------------------------------------------------
# OPS-2006.08. The two soft spots: a refusal that says only "deny", and a
# hand-mirrored environment variable name.
#
# Everything above now names its sub-kind. These cases guard the mechanism
# that makes those names worth anything: that the fail-closed arm exists and
# is distinguishable, that the assertions actually catch a gate which took
# it, that no sub-kind the gate can emit is left unpinned by accident, and
# that the ledger variable is READ from the gate rather than remembered.
# ---------------------------------------------------------------------------


def test_the_fail_closed_arm_is_reachable_and_names_itself(repo: Path) -> None:
    """[gate] is a real outcome, so refusing it everywhere else means something.

    The negative half of ``assert_kind`` says no case may be refused through
    ``[gate]``. That rule is worth nothing if ``[gate]`` were unreachable:
    an assertion no input can violate proves nothing about any input.

    Reached WITHOUT touching the hook, which is a hash-pinned vendored row
    (``tests/test_kit_drift.py``). ``_repo_identity`` reads pyproject.toml
    with ``encoding="utf-8"`` and catches only ``OSError``, so a pyproject
    holding bytes that are not UTF-8 raises ``UnicodeDecodeError`` out of
    it, into ``main``'s blanket ``except Exception``, which is the
    fail-closed arm. That is also a real failure mode rather than a
    contrivance: a file mangled by an editor writing another codepage.

    The control matters as much as the case. The same push ALLOWS one line
    earlier, so the refusal is attributable to the crash and to nothing
    else, and the sabotage cannot be mistaken for the ordinary review stop.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin main") == "allow"

    (repo / "pyproject.toml").write_bytes(b'[project]\nname = "\xff\xfe not utf 8"\n')
    decision, reason = judge(repo, f"{PUSH} origin main", kind="gate")
    assert decision == "deny"
    assert "UnicodeDecodeError" in reason, reason
    # The remedy class is its own: the gate says it could not evaluate, and
    # does not tell the reader to go and review anything.
    assert "could not be evaluated" in reason, reason
    assert "[review]" not in reason, reason


def _sabotaged_gate(tmp_path: Path) -> Path:
    """A copy of the gate that crashes before it classifies anything.

    The mutation is one statement at the top of ``main``'s try block, so
    every recognized push is refused through the fail-closed arm and NO
    check in the body runs: not the scope resolution, not the ledger, not
    the attestation, not the CI arm. It is the shape of the regression this
    item exists for, applied deliberately.

    The anchor is asserted PRESENT and UNIQUE before it is applied. A
    mutation battery whose anchor silently missed reports the original body
    as surviving, which reads as evidence and is its absence.

    The whole hooks directory is copied rather than the one file, so a
    sibling the gate looks for is where it expects it; the vendored
    original is never written to.
    """
    hooks = tmp_path / "sabotaged-hooks"
    shutil.copytree(HOOK.parent, hooks, ignore=shutil.ignore_patterns("__pycache__"))
    mutant = hooks / HOOK.name
    text = mutant.read_text(encoding="utf-8")
    anchor = "    try:\n        base = Path(git_c_path) if git_c_path else Path.cwd()\n"
    assert text.count(anchor) == 1, (
        f"the sabotage anchor occurs {text.count(anchor)} times in {mutant}; a "
        "battery that cannot find its anchor proves nothing about the body it "
        "did not change"
    )
    crash = '        raise RuntimeError("sabotage: the deny classifier is gone")\n'
    mutant.write_text(
        text.replace(anchor, "    try:\n" + crash + anchor[len("    try:\n") :]),
        encoding="utf-8",
    )
    assert mutant.read_text(encoding="utf-8") != text
    return mutant


def test_a_gate_that_crashes_is_caught_by_the_sub_kind_assertions(
    repo: Path, tmp_path: Path
) -> None:
    """The mutation companion for OPS-2006.08, and its whole justification.

    A guard is not proven by a suite that passes. This one is proven by
    restoring the defect it was written against and watching it deny.

    Measured against the sabotaged body on 2026-08-18, before this item:
    21 of the file's 69 cases still passed, 15 of them cases whose entire
    subject is that the gate REFUSES something. They passed because
    ``== "deny"`` is true of a gate that refuses everything for the wrong
    reason, including a gate that ran no check at all.

    Both halves of ``assert_kind`` are exercised here, and the second is
    the one that generalizes: a caller naming NO kind is still protected,
    because ``[gate]`` is refused for every kind but ``"gate"``. That is
    what makes the rule hold across the whole file rather than only where
    someone remembered to name an expectation.
    """
    add_commit(repo, "one")
    mutant = _sabotaged_gate(tmp_path)
    decision, reason = outcome(run_gate(repo, f"{PUSH} origin main", hook=mutant))

    # What the file used to assert, and what it still reports under sabotage.
    assert decision == "deny"
    assert "sabotage: the deny classifier is gone" in reason, reason

    # What the file asserts now. Named kind: caught.
    with pytest.raises(AssertionError, match="FAIL-CLOSED"):
        assert_kind(decision, reason, "review", f"{PUSH} origin main")
    # Unnamed kind: caught as well, so every judge call in this file is
    # covered and not only the ones that name an expectation.
    with pytest.raises(AssertionError, match="FAIL-CLOSED"):
        assert_kind(decision, reason, None, f"{PUSH} origin main")
    # And the case that is genuinely about the fail-closed arm still passes,
    # so the rule refuses a misrouted refusal rather than the arm itself.
    assert_kind(decision, reason, "gate", f"{PUSH} origin main")


def test_every_deny_sub_kind_the_gate_can_emit_is_pinned_or_declared_unreached() -> None:
    """No sub-kind arrives in a future kit body unnoticed.

    The gate is vendored and re-vendored; a new refusal arm arrives with a
    new bracket and nothing here would ask for a case covering it. So the
    kinds are read off the gate body and partitioned: either some case in
    this file names one, or ``UNREACHED_DENY_KINDS`` declares it
    unreachable from here WITH the reason. A kind in neither set fails,
    which is a request for one of the two rather than a defect claim.

    Written as a partition rather than a subset check on purpose. A subset
    check would also pass if this file stopped pinning half of them.
    """
    # Deliberately NOT restricted to lowercase words: a scan that only knows
    # today's spelling would step over a new kind spelled any other way and
    # report a complete partition, which is this test's own failure mode.
    written = re.findall(r"\{GATE_PREFIX\} \[([^\]\n]+)\]", HOOK.read_text(encoding="utf-8"))
    kinds_in_gate = {kind for kind in written if "{" not in kind}
    assert len(kinds_in_gate) > 5, kinds_in_gate
    # The sites the scan cannot resolve, because the gate builds the bracket
    # from a variable. Asserted to be exactly one, and to be the CI one:
    # a second would hide a whole family of sub-kinds from this partition.
    interpolated = [kind for kind in written if "{" in kind]
    assert len(interpolated) == 1 and interpolated[0].startswith("ci-"), (
        f"interpolated sub-kind sites in the gate: {interpolated}. This test can "
        "only account for the CI one it knows about"
    )
    assert GATE_INTERPOLATED_KIND_SITE in HOOK.read_text(encoding="utf-8")
    pinned = pinned_kinds() | {case[3] for case in CI_REFUSAL_CASES}
    emitted = kinds_in_gate | {case[3] for case in CI_REFUSAL_CASES}
    unaccounted = emitted - pinned - UNREACHED_DENY_KINDS
    assert not unaccounted, (
        f"the gate can refuse with {sorted(unaccounted)} and nothing in this file "
        "pins it. Add a case that drives the arm, or declare it in "
        "UNREACHED_DENY_KINDS with the reason it cannot be reached from here."
    )
    stale = UNREACHED_DENY_KINDS - emitted
    assert not stale, (
        f"{sorted(stale)} is declared unreachable but the gate no longer emits it "
        "at all; delete the declaration rather than carrying it"
    )
    covered = UNREACHED_DENY_KINDS & pinned
    assert not covered, (
        f"{sorted(covered)} is declared unreachable and a case reaches it; the "
        "declaration is false and would excuse a real gap next to it"
    )


def test_every_refusal_this_file_asserts_names_which_check_refused() -> None:
    """The RATCHET, as distinct from the sweep that preceded it.

    Naming a sub-kind in all 79 cases was a one-time act, and a one-time
    act does not hold: the next case written here will be written by
    someone reading the case above it, and ``== "deny"`` is shorter,
    reads fine, and passes. That is exactly how the 15 bare refusals this
    item removed were written in the first place, one at a time, each
    beside a neighbour that looked the same.

    So the property is measured rather than remembered. Every ``judge``
    or ``decide`` call in this file must either name the sub-kind it
    expects, or assert an ALLOW, or sit in a case declared in
    ``DELEGATES_ITS_SUB_KIND_ASSERTION`` because it asserts the sub-kind
    by hand. Both directions of that declaration are checked, so the
    hatch cannot be widened quietly and cannot outlive its case.

    What this does NOT check, stated so the guard is not read as more
    than it is: that the kind a case names is the RIGHT one. Nothing here
    can know that. The gate itself answers it, by refusing through a
    different arm and failing the case.
    """
    sites = unpinned_refusal_sites()
    undeclared = [site for name, site in sites if name not in DELEGATES_ITS_SUB_KIND_ASSERTION]
    assert not undeclared, (
        "a push-gate case reaches a refusal without saying WHICH check refused it:\n  "
        + "\n  ".join(undeclared)
        + "\nPass kind=<sub-kind> so the case fails when the gate refuses through "
        "another arm, or through the fail-closed [gate] arm having run no check at "
        "all. A bare == 'deny' passes on a gate that denies everything."
    )
    used = {name for name, _ in sites}
    stale = set(DELEGATES_ITS_SUB_KIND_ASSERTION) - used
    assert not stale, (
        f"{sorted(stale)} is declared as asserting its sub-kind by hand and no "
        "longer does; delete the declaration rather than leaving an unused "
        "exemption sitting next to the rule it exempts."
    )
    # The population, printed rather than assumed. A scan that matched nothing
    # would satisfy every assertion above and measure no case at all.
    measured = ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
    calls = [node for node in measured if _is_gate_call(node)]
    assert len(calls) > 50, f"only {len(calls)} gate calls found; the scan is not reaching them"


def test_the_unpinned_scan_catches_a_bare_deny_that_is_added_later(tmp_path: Path) -> None:
    """The mutation companion for the ratchet above.

    A guard is proven by restoring the defect and watching it deny, never
    by a suite that passes. Two shapes are restored here because they are
    the two ways the rule is actually lost: a ``kind=`` deleted from a
    case that had one, and a brand new case written without one.

    The control runs first and on the SAME code path, so a scanner that
    reported everything, or nothing, could not pass all three.
    """
    body = Path(__file__).read_text(encoding="utf-8")
    clean = tmp_path / "clean.py"
    clean.write_text(body, encoding="utf-8")
    assert [site for name, site in unpinned_refusal_sites(clean)] == [
        site for name, site in unpinned_refusal_sites()
    ], "reading a copy must measure the same file"

    # Split so this line is not itself a second occurrence of its own anchor,
    # which is the same reason `PUSH` is built by concatenation at the top of
    # this file. Measured: written whole, the uniqueness check below fails at 2.
    anchor = 'assert decide(repo, f"{PUSH} origin main; echo done", kind=' + '"scope") == "deny"'
    assert body.count(anchor) == 1, (
        f"the mutation anchor occurs {body.count(anchor)} times; a battery that "
        "cannot find its anchor proves nothing about the body it did not change"
    )
    stripped = tmp_path / "stripped.py"
    without_kind = anchor.replace(', kind="scope"', "")
    stripped.write_text(body.replace(anchor, without_kind), encoding="utf-8")
    caught = [site for _, site in unpinned_refusal_sites(stripped)]
    assert any("echo done" in site for site in caught), (
        f"a kind= deleted from an existing case went unreported: {caught}"
    )

    added = tmp_path / "added.py"
    written_later = (
        '\n\ndef test_written_later(repo: Path) -> None:\n    assert decide(repo, "x") == "deny"\n'
    )
    added.write_text(body + written_later, encoding="utf-8")
    assert any(name == "test_written_later" for name, _ in unpinned_refusal_sites(added)), (
        "a new case written with a bare == 'deny' went unreported, which is the "
        "shape this ratchet exists for"
    )

    # The third shape, and the one that would otherwise leave a dead branch in
    # the scan: a gate call outside every function. It is exercised on a COPY
    # rather than as a battery mutant on this file, because a module-level call
    # would run at import and report as a collection error instead of a verdict.
    at_module_level = tmp_path / "module_level.py"
    at_module_level.write_text(
        body + '\n\nWHATEVER = decide(REPO_FIXTURE, "x") == "deny"\n', encoding="utf-8"
    )
    assert any(name == "<module level>" for name, _ in unpinned_refusal_sites(at_module_level)), (
        "a gate call outside every function was invisible to the scan"
    )


def test_the_ledger_variable_name_is_read_from_the_gate_and_not_remembered(
    tmp_path: Path,
) -> None:
    """The second soft spot, and the one that fails silently in both directions.

    ``hook_env`` strips this variable to keep the suite off the author's
    real ledger. Mirrored by hand, a rename in the gate leaves this file
    stripping a name nobody reads: the real ledger reaches every hook
    subprocess, and the suite starts passing or failing on whichever
    incidents are open on one machine that morning. Nothing goes red at the
    rename, which is what makes it worth a guard.

    The derivation is proven by MUTATION rather than by agreement: this
    reads a renamed copy and must report the new name. Comparing the
    derived value against a literal here would only prove that two copies
    of today's name agree, which is the property that was already true.
    """
    assert LEDGER_ENV == gate_constant("LEDGER_ENV")
    body = HOOK.read_text(encoding="utf-8")
    # The gate must actually CONSULT the variable it names, or the rest of
    # this is agreement about an unused string.
    assert "os.environ.get(LEDGER_ENV" in body

    renamed = tmp_path / HOOK.name
    anchor = f'LEDGER_ENV = "{LEDGER_ENV}"\n'
    assert body.count(anchor) == 1, f"{body.count(anchor)} assignments of LEDGER_ENV"
    renamed.write_text(
        body.replace(anchor, 'LEDGER_ENV = "COORD_LEDGER_RENAMED_FOR_THIS_TEST"\n'),
        encoding="utf-8",
    )
    assert gate_constant("LEDGER_ENV", renamed) == "COORD_LEDGER_RENAMED_FOR_THIS_TEST", (
        "the ledger variable name is not being read from the gate body: a rename "
        "there would leave this file stripping a variable nothing reads"
    )
    assert GATE_PREFIX == gate_constant("GATE_PREFIX")
    assert gate_constant("GATE_PREFIX", renamed) == GATE_PREFIX, (
        "reading a mutated copy must change only what was mutated"
    )


def test_a_gate_constant_that_is_absent_or_doubled_fails_loudly(tmp_path: Path) -> None:
    """The reader refuses rather than falling back to a literal.

    A derivation that quietly returned a default on a missing assignment
    would reintroduce the mirrored constant with an extra step, and it
    would do it invisibly.
    """
    body = HOOK.read_text(encoding="utf-8")
    folder = tmp_path
    anchor = f'LEDGER_ENV = "{LEDGER_ENV}"\n'

    missing = folder / "missing.py"
    missing.write_text(body.replace(anchor, "", 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="exactly one"):
        gate_constant("LEDGER_ENV", missing)

    doubled = folder / "doubled.py"
    doubled.write_text(body.replace(anchor, anchor + anchor, 1), encoding="utf-8")
    with pytest.raises(AssertionError, match="exactly one"):
        gate_constant("LEDGER_ENV", doubled)
