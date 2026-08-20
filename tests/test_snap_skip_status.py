"""Tier 1: what the vendored snapshot tool does when a tree is unconfigured.

Reproduction, which is what this module exists for (OPS-2013.03)::

    $ unset COORD_SHARED_LEDGER_TREE
    $ bash .claude/tools/snap.sh shared
    shared: no _private tree, skipped
    $ echo $?
    0

The skip itself is CORRECT and is the 0.2.5 body's own promise: an
unconfigured tree is skipped rather than snapshotted against an empty work
tree. The status is not. ``snapshot()`` calls ``ensure()``, which refuses an
unconfigured tree with ``return 1``, and then converts that refusal into
``return 0`` after printing the skip; the no-argument loop collects
``snapshot "$r" || rc=1`` and so exits 0 with the shared incident ledger, the
tree both push gates consult, never taken. The message tells the truth and the
status does not, which is one layer out from the defect this file was fixed
for in 2026-07-28 (``PLN-20260728-1615-snap-shared-tree-false-success``,
closed by taking the 0.2.5 body) and the same class as the loop fix already in
it.

The other three actions do NOT have the defect, and the contrast is measured
below rather than described: ``log``, ``diff`` and ``restore`` go through
``g()``, which refuses on stderr with a nonzero status, and the script's exit
status is that refusal.

WHAT IS AND IS NOT ENFORCED HERE, because this is the half of the item that
could land. ``.claude/tools/snap.sh`` is a hash-pinned vendored kit body
(``tests/test_kit_drift.py``): a change to it is promoted at the coordination
kit and re-vendored, never hand-edited here, so the two assertions that
require the fixed body carry ``xfail(strict=True)`` and name the promotion
they wait for. Strict is the point: the day the promoted body is vendored they
turn from expected failures into failures, so the marker cannot outlive the
defect quietly. Everything else here passes on the body as vendored today and
guards behaviour that is already right.

The runs are made against a SANDBOXED COPY of the vendored script, with the
two literal work trees and the snapshot base rewritten to a temporary
directory. Nothing here reads or writes the real ``_private`` trees, the real
snapshot repositories or the real shared ledger, and nothing here depends on
how this machine is configured: the variable under test is cleared from the
child environment rather than assumed absent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SNAP = REPO / ".claude/tools/snap.sh"

#: The three assignments the sandbox rewrites, named by their LEFT-HAND SIDE
#: rather than by their value. The first version of this module spelled each
#: whole line, values included, and `tests/test_house_style.py` refused it:
#: those values are absolute paths into the author's workspace container,
#: which is machine configuration, and this remote is public.
#:
#: Each is still asserted present and UNIQUE before it is replaced, which is
#: the property the literal anchors carried: a pattern that matches twice, or
#: not at all, makes the substitution land somewhere nobody chose, and the run
#: would then measure a script the repository does not ship. Deriving the
#: anchor moves that assertion onto the part that is stable across machines,
#: the assignment, and off the part that is not, the path.
REWRITTEN_ASSIGNMENTS = ("BASE", "[pyflightstream]", "[itaca]")

#: The line under test, left untouched by the sandbox. Asserted present so a
#: re-vendor that renames the variable fails here rather than making every
#: assertion below vacuously true about a tree nothing reads.
SHARED_TREE_LINE = '[shared]="${COORD_SHARED_LEDGER_TREE:-}"'

PENDING_PROMOTION = (
    "the fix is a kit promotion at the coordination level and a re-vendor of "
    "this hash-pinned body (OPS-2013.03); the vendored 0.2.5 body converts "
    "ensure()'s refusal into return 0 and prints the skip on stdout"
)


def _bash_runs() -> bool:
    """Whether bash is present AND works.

    EXISTENCE IS NOT CAPABILITY, and the difference kept CI red. On
    GitHub's windows-latest a file named ``bash`` is on PATH: it is the
    WSL stub, which has no distribution installed, prints a UTF-16
    notice about installing one and exits 1. A guard asking
    ``shutil.which("bash") is None`` sees a bash there, does not skip,
    and every case in this module then fails with that notice as its
    diagnosis, including the strict xfail, which XPASSes because the run
    failed for a reason that has nothing to do with what it expects.
    """
    if shutil.which("bash") is None:
        return False
    try:
        proof = subprocess.run(
            ["bash", "-c", "echo bash-works"],
            capture_output=True,
            text=True,
            timeout=30,
            # THE ENVIRONMENT THE REAL RUNS USE, which is what this probe
            # exists to decide about. The first version passed a minimal
            # five-variable env, so it established that bash works under
            # conditions no case in this module runs under: `_run` below
            # passes `os.environ.copy()` plus the git identity. The tier-1
            # ratchet asks that a spawn NAME its environment, not that it
            # minimise it.
            env=os.environ.copy(),
        )
    except OSError:
        return False
    # A TIMEOUT IS NOT AN ANSWER, so it is not caught. `TimeoutExpired` is
    # a `SubprocessError`, and catching that whole family turned a loaded
    # runner's thirty-second hiccup into "this machine has no bash", which
    # skips the module, which silences the three strict xfails whose whole
    # purpose is to go red the day the kit body is promoted.
    return proof.returncode == 0 and "bash-works" in proof.stdout


pytestmark = pytest.mark.skipif(
    not _bash_runs(),
    reason="the vendored snapshot tool is a bash script and this machine has no WORKING "
    "bash (a WSL stub with no distribution installed counts as none)",
)


def _assignment(text: str, name: str) -> str:
    """Return the one line of the vendored script assigning ``name``.

    The VALUE is read rather than written down here. Every value this
    sandbox rewrites is an absolute path into the author's workspace
    container, and a tracked file on a public remote may not carry one
    (``CLAUDE.md``, machine configuration; ``tests/test_house_style.py``
    is the guard, and it refused the first version of this module).

    Reading it buys a second property the literals did not have: this
    fails when a re-vendor RENAMES or duplicates the assignment, which is
    the change that would make the sandbox rewrite the wrong script, and
    not when its value changes, which is the part that legitimately
    differs per machine.

    Parameters
    ----------
    text : str
        The vendored script, line endings already normalised.
    name : str
        The left-hand side, for example ``BASE`` or ``[itaca]``.

    Returns
    -------
    str
        The whole assignment, ready to be used as a unique anchor.

    Raises
    ------
    AssertionError
        If the script does not carry exactly one such assignment.
    """
    found = [line.strip() for line in text.split("\n") if line.strip().startswith(f"{name}=")]
    assert len(found) == 1, (
        f"the vendored snap.sh carries {len(found)} assignment(s) to {name}, not one. "
        "It was re-vendored and this sandbox would rewrite a script that no longer "
        "exists; re-read the body before trusting any assertion in this module."
    )
    return found[0]


def _msys(path: Path) -> str:
    """Render a path the way the vendored script writes its own.

    The script is bash and its literals are msys paths (``/c/WORK/...``), so a
    Windows temporary directory has to be spelled the same way before it is
    substituted in; on a POSIX machine this is the identity.

    Returns
    -------
    str
        The path with backslashes as forward slashes and a ``C:`` drive letter
        rewritten to a ``/c`` root. No units: this is a filesystem path.
    """
    text = str(path).replace("\\", "/")
    if len(text) > 1 and text[1] == ":":
        text = "/" + text[0].lower() + text[2:]
    return text


@pytest.fixture
def sandbox(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A copy of the vendored script whose real trees point into ``tmp_path``.

    Returns
    -------
    tuple of (pathlib.Path, dict)
        The sandboxed script, and a child environment with
        ``COORD_SHARED_LEDGER_TREE`` REMOVED rather than emptied, so the run
        exercises the unset case on any machine.
    """
    text = SNAP.read_text(encoding="utf-8").replace("\r\n", "\n")
    anchors = {name: _assignment(text, name) for name in REWRITTEN_ASSIGNMENTS}
    assert text.count(SHARED_TREE_LINE) == 1, (
        f"the vendored snap.sh does not carry {SHARED_TREE_LINE!r} exactly once "
        f"(found {text.count(SHARED_TREE_LINE)}). It was re-vendored and this "
        "sandbox is rewriting a script that no longer exists; re-read the "
        "body before trusting any assertion in this module."
    )
    # The snapshot base is a directory the real tool finds already there;
    # `git init --git-dir=<base>/x.git` fails if its parent does not exist,
    # and the body echoes "created" before checking, so an absent base looks
    # like a snapshot repository that was made.
    (tmp_path / "snapshots").mkdir()
    for name in ("pyflightstream", "itaca"):
        tree = tmp_path / name
        tree.mkdir()
        (tree / "notes.md").write_text("sandbox tree\n", encoding="utf-8")
    destinations = {
        "BASE": tmp_path / "snapshots",
        "[pyflightstream]": tmp_path / "pyflightstream",
        "[itaca]": tmp_path / "itaca",
    }
    for name, destination in destinations.items():
        text = text.replace(anchors[name], f'{name}="{_msys(destination)}"')
    assert SHARED_TREE_LINE in text, "the sandbox rewrote the line under test"
    script = tmp_path / "snap_sandbox.sh"
    script.write_text(text, encoding="utf-8", newline="\n")

    env = os.environ.copy()
    env.pop("COORD_SHARED_LEDGER_TREE", None)
    # A snapshot commits, so it needs an identity; the body reads the ambient
    # git configuration, which a CI runner may not have.
    env.setdefault("GIT_AUTHOR_NAME", "sandbox")
    env.setdefault("GIT_AUTHOR_EMAIL", "sandbox@example.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "sandbox")
    env.setdefault("GIT_COMMITTER_EMAIL", "sandbox@example.invalid")
    return script, env


def _run(
    script: Path, env: dict[str, str], *args: str, tree: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the sandboxed script, optionally with a configured shared tree."""
    child = dict(env)
    if tree is not None:
        child["COORD_SHARED_LEDGER_TREE"] = tree
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=child,
        cwd=str(script.parent),
    )


def test_an_unconfigured_shared_tree_is_really_skipped(
    sandbox: tuple[Path, dict[str, str]], tmp_path: Path
) -> None:
    """Nothing is snapshotted and the skip is announced.

    This is the half of the promise the 0.2.5 body keeps, and it is the half
    that was FALSE in 0.2.4: ``ensure()`` took the already-exists shortcut
    before testing the work tree, so a machine that had snapshotted the shared
    tree once ran ``add -A`` with an empty ``--work-tree`` and announced a
    snapshot it had not taken.

    THE SNAPSHOT REPOSITORY IS SEEDED FIRST, and that is part of the test
    rather than setup: on a clone that has never snapshotted, the reordered and
    the correct ``ensure()`` behave identically, so a run against an empty base
    would pass with the ordering reversed and prove nothing. Seeding reproduces
    the state of the machine the defect was found on.

    What the adversarial pass measured, recorded because it is a property of
    the 0.2.5 body rather than of this test: the tree is guarded TWICE, in
    ``ensure()`` and again in ``g()``, so reversing the ``ensure()`` order
    alone no longer produces a false snapshot even on a seeded machine, and
    this assertion stays green under that single mutation. It goes red when
    both guards are removed. Read it as "the skip is real", not as "the
    ``ensure()`` ordering is pinned"; the ordering is pinned by the body hash
    in ``tests/test_kit_drift.py``.
    """
    script, env = sandbox
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "INC-sandbox.md").write_text("status: closed\n", encoding="utf-8")
    seeded = _run(script, env, "shared", tree=_msys(ledger))
    assert "snapshot taken" in seeded.stdout, (
        f"the shared snapshot repository was not seeded, so this run is not the "
        f"already-exists case: {seeded.stdout!r} {seeded.stderr!r}"
    )
    assert (script.parent / "snapshots" / "shared_private.git").is_dir()

    result = _run(script, env, "shared")
    assert "skipped" in (result.stdout + result.stderr), (
        f"the unconfigured shared tree was not announced as skipped: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "snapshot taken" not in result.stdout, (
        "a snapshot was announced for a tree that is not configured, which is "
        f"the 2026-07-28 defect: stdout={result.stdout!r}"
    )


def test_the_sandbox_can_take_a_snapshot_when_the_tree_is_configured(
    sandbox: tuple[Path, dict[str, str]],
    tmp_path: Path,
) -> None:
    """The harness itself is falsifiable, which the test above needs.

    An assertion that NOTHING happened passes just as well when bash never
    ran, when the substitution broke the script, or when git is missing. This
    run configures the tree and requires the snapshot to be taken, so the
    absence measured above is an absence the same machinery could have filled.
    """
    script, env = sandbox
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "INC-sandbox.md").write_text("status: closed\n", encoding="utf-8")
    result = _run(script, env, "shared", tree=_msys(ledger))
    assert result.returncode == 0, (
        f"a configured shared tree failed to snapshot: {result.stdout!r} {result.stderr!r}"
    )
    assert "snapshot taken" in result.stdout, (
        f"expected a snapshot, got stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert (script.parent / "snapshots" / "shared_private.git").is_dir()


def test_log_refuses_an_unconfigured_tree_on_stderr_with_a_nonzero_status(
    sandbox: tuple[Path, dict[str, str]],
) -> None:
    """The contrast case, and it is the shape the snapshot action owes.

    ``log`` reaches the tree through ``g()``, which refuses an unconfigured
    tree on stderr and returns 1, and the script's exit status is that
    refusal. Nothing about the snapshot action makes it a special case; this
    test is here so the two can be compared rather than described.
    """
    script, env = sandbox
    result = _run(script, env, "shared", "log")
    assert result.returncode != 0, (
        f"`snap.sh shared log` reported success on an unconfigured tree: stdout={result.stdout!r}"
    )
    assert "no tree configured" in result.stderr, (
        f"the refusal did not reach stderr: stderr={result.stderr!r}"
    )


@pytest.mark.xfail(strict=True, reason=PENDING_PROMOTION)
def test_a_skipped_snapshot_exits_nonzero(sandbox: tuple[Path, dict[str, str]]) -> None:
    """The status carries the refusal instead of reporting success.

    THE PRECONDITION IS THE POINT, and this case had none until a review
    pass measured what that costs. Asserting only a nonzero status makes
    the marker fire on ANY nonzero cause: on a runner where bash could
    not open the script at all, this XPASSed while its two content
    anchored siblings correctly stayed xfail. A strict xfail that flips
    on an unrelated failure reports the kit promotion arriving when
    nothing arrived.
    """
    script, env = sandbox
    result = _run(script, env, "shared")
    assert "skipped" in (result.stdout + result.stderr).lower(), (
        "the run produced no skip message at all, so its status says nothing about "
        f"the behaviour this case measures. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert result.returncode != 0, (
        "`snap.sh shared` exited 0 having taken no snapshot of the ledger both "
        "push gates consult. A recovery tool whose status says success after "
        "doing nothing is the failure this file exists to prevent."
    )


@pytest.mark.xfail(strict=True, reason=PENDING_PROMOTION)
def test_the_skip_is_printed_on_stderr(sandbox: tuple[Path, dict[str, str]]) -> None:
    """The skip goes where a refusal goes, as ``g()``'s already does."""
    script, env = sandbox
    result = _run(script, env, "shared")
    assert "skipped" in result.stderr and "skipped" not in result.stdout, (
        f"the skip was printed on stdout: stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.xfail(strict=True, reason=PENDING_PROMOTION)
def test_the_no_argument_run_carries_the_refusal(sandbox: tuple[Path, dict[str, str]]) -> None:
    """The documented normal usage is the one that hides the skip.

    The aggregate loop keeps the worst outcome, so a skipped tree has to reach
    it as a nonzero return. The other two sandbox trees exist and snapshot
    normally in the same run, which is what makes the status meaningful: it is
    reporting the one tree that was not taken, not a run that failed wholesale.
    """
    script, env = sandbox
    result = _run(script, env)
    assert "snapshot taken" in result.stdout, (
        f"the two configured sandbox trees did not snapshot, so this run "
        f"measures something else: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.returncode != 0, (
        "the no-argument run exited 0 with the shared ledger skipped, which is "
        "the documented normal usage reporting success after taking nothing."
    )
