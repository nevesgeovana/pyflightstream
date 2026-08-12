#!/usr/bin/env python3
r"""Mutation proof for the extras-isolation guard, tests/test_extras_isolation.py.

ONE OF THE TWO GUARDS THAT CLOSED INC-20260810-2140-shared, and this file was
named for both until 2026-08-11. The other was the repository-owned CI-green
tag gate, deleted with its test and this battery's BM1..BM16 in the commit that
vendored kit 0.2.18, which carries that rule in the SHARED push gate. Its
replacement evidence lives with the body it proves: `ci_state_mutations.py`
beside the vendored `ci_state.py`, run in tier 1 by `tests/test_ci_state.py`,
with the refusal at the push boundary pinned by `tests/test_push_gate.py`. The
rename came with the deletion rather than after it, because a battery named for
two guards that proves one asserts a property no run of it evaluates.

Committed rather than kept in a scratchpad, which is this workspace's own
practice (`.claude/tools/check_plan_kit_mutations.py` and
`check_side_effect_guard_mutations.py` ship beside the checkers they
prove, and the kit's V and V lens once refused a promotion that shipped a
checker without its mutations). A guard's evidence that nobody else can
re-run is an assertion, not evidence.

    python scripts/prove_extras_isolation.py            # everything
    python scripts/prove_extras_isolation.py M1 M2 N1   # by label prefix

Exit 0 when every mutant died and every negative control survived. The
full run takes upwards of ten minutes, because each mutant re-runs a
suite that walks the whole tree, so the label filter exists to keep one
invocation inside an ordinary command timeout. A partial run is still a
real proof of the mutants it names; it is not a proof of the others.

TWO THINGS THIS FILE GETS RIGHT THAT THE FIRST DRAFT DID NOT, both
learned the expensive way.

It writes BYTES. The first harness used ``write_text`` after ``decode``,
which translates ``\\n`` again on a file that already carries ``\\r\\n``
and leaves ``\\r\\r\\n`` on every line. The mutants still died, for the
wrong reason, and so did the negative control, which is the only reason
the corruption was noticed. A battery that reddens the suite by
corrupting the file measures nothing at all.

And it carries NEGATIVE controls. A guard that refuses a legitimate
idiom is a guard the next contributor weakens instead of obeying, so at
least one case here must SURVIVE, and the run fails if it does not.

It mutates the working tree in place and restores from saved bytes in a
``finally``. Run it on a clean tree and check ``git status`` afterwards;
the run prints the reminder.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)


#: Where an in-flight mutant's ORIGINAL bytes are parked, so a run that
#: is killed can be undone by the next one. Inside `.git/`, which is
#: never tracked and always present.
#:
#: This exists because it happened. A run of this battery hit a ten
#: minute command timeout mid-mutant and left `.claude/settings.json`
#: holding the mutation that UNWIRED the CI gate; had it been committed,
#: the guard would have shipped disabled, which is the exact failure the
#: guard existed to prevent. (That mutant, BM10, went with the bridge on
#: 2026-08-11; the recovery path it justified stays, because the hazard
#: is the harness rather than any one mutant.) A `finally` does not survive SIGKILL, and
#: this workspace already has an incident about a review process dying
#: with mutations in the tree.
#: Resolved through git rather than assumed to be `REPO / ".git"`: in a
#: LINKED WORKTREE `.git` is a FILE, so `mkdir` raised on the first
#: mutant and `recover()` silently found nothing. This workspace parks
#: reviewer agents in worktrees by standing practice, which is exactly
#: where a battery most needs to run.
def _git_dir() -> Path:
    """Return the git directory of this checkout, worktree or not."""
    done = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        # Explicit, and identical to the inherited default: git needs the
        # ambient environment to find its own configuration.
        env=os.environ.copy(),
    )
    resolved = done.stdout.strip()
    return Path(resolved) if resolved else REPO / ".git"


BACKUP = _git_dir() / "mutation-backup"

GUARD_A = "tests/test_extras_isolation.py"
# GUARD_B WAS `tests/test_ci_release_gate.py` AND IS GONE, with its whole
# battery (BM1..BM16), on 2026-08-11. The repository-owned bridge hook it
# proved was deleted in the commit that vendored kit 0.2.18, which carries the
# CI-green tag rule in the SHARED gate. Its replacement evidence is not
# nothing and is not here: `ci_state_mutations.py` ships beside the vendored
# `ci_state.py` and is run by `tests/test_ci_state.py` in tier 1, and the
# refusal at the push boundary is pinned by `tests/test_push_gate.py`. This
# file was renamed from `prove_extras_and_ci_guards.py` in the same commit,
# because a battery named for two guards that proves one is the stale success
# line this project registers most.

#: A backtick fence, built rather than written, so this file carries no
#: fence of its own for the scanner it is proving to trip over.
FENCE = chr(96) * 3


#: A suite that hangs must not become an external kill. The recovery
#: path exists because two runs WERE killed; this is the structural half,
#: turning a hang into a TimeoutExpired the `finally` blocks survive.
SUITE_TIMEOUT = 300.0


def run(target: str) -> tuple[int, str]:
    """Run one test file and return its exit code and summary line."""
    try:
        done = subprocess.run(
            [str(PYTHON), "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=SUITE_TIMEOUT,
            # Explicit, and identical to the inherited default: the child is
            # pytest and needs this interpreter's own environment.
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return 1, f"TIMED OUT after {SUITE_TIMEOUT:.0f}s (INCONCLUSIVE, and look at why)"
    tail = [line for line in done.stdout.splitlines() if "passed" in line or "failed" in line]
    return done.returncode, (tail[-1] if tail else "no summary")


def _slot(path: Path) -> Path:
    """Return the backup file for one repository path."""
    return BACKUP / path.relative_to(REPO).as_posix().replace("/", "%")


def park(path: Path, original: bytes) -> None:
    """Record a file's original bytes before it is mutated."""
    BACKUP.mkdir(parents=True, exist_ok=True)
    _slot(path).write_bytes(original)


def unpark(path: Path) -> None:
    """Forget a recorded original, the mutation having been undone."""
    _slot(path).unlink(missing_ok=True)


def recover() -> list[str]:
    """Undo any mutation a previous run was killed in the middle of."""
    if not BACKUP.is_dir():
        return []
    restored: list[str] = []
    for slot in sorted(BACKUP.iterdir()):
        target = (REPO / slot.name.replace("%", "/")).resolve()
        if REPO.resolve() not in target.parents:
            # A recovery tool that can write outside the tree it is
            # recovering is a worse problem than the one it solves.
            # Reported AND counted, so main() refuses to continue. A
            # poisoned slot that is merely printed persists across every
            # later run while the tool reports a clean start.
            restored.append(f"{slot.name} (REFUSED: resolves outside the repository)")
            continue
        parked = slot.read_bytes()
        if parked:
            target.write_bytes(parked)
            restored.append(target.relative_to(REPO).as_posix())
        else:
            # An empty slot is the tombstone `create` leaves: the path
            # did not exist before the mutation, so recovery is deletion.
            target.unlink(missing_ok=True)
            restored.append(f"{target.relative_to(REPO).as_posix()} (deleted)")
        slot.unlink()
    return restored


#: Label prefixes to run, from the command line. Empty means all.
WANTED: list[str] = []

#: Every label the run offered, and every label it actually ran. The
#: second exists because the first version of this script printed
#: "every mutant died and every control survived" and exited 0 for a
#: mistyped filter, having run nothing. That is the shape of the very
#: defect both guards exist to prevent, inside the artifact that is
#: supposed to be their evidence.
OFFERED: list[str] = []
RAN: list[str] = []

#: Guards the filter skipped whole. Tracked because a guard that never
#: ran contributes no labels to OFFERED, so a denominator built from
#: OFFERED alone would read "14 of 14" for a run that touched half the
#: battery.
SKIPPED_GUARDS: list[str] = []


def selected(label: str) -> bool:
    """Whether a mutant's label was asked for."""
    OFFERED.append(label)
    if WANTED and not any(label.startswith(prefix) for prefix in WANTED):
        return False
    RAN.append(label)
    return True


class Battery:
    """Apply mutants one at a time, restoring bytes after each."""

    def __init__(self, target: str) -> None:
        self.target = target
        self.failures: list[str] = []

    def _verdict(self, label: str, code: int, summary: str, expect: str) -> None:
        # A non-zero exit is not the same as an assertion catching the
        # mutant: pytest exits non-zero on a collection error too, so a
        # mutant that merely breaks the file would read as KILLED and
        # inflate the count. Require the suite to say a test FAILED.
        if code and "failed" in summary:
            got = "KILLED"
        elif code:
            got = "INCONCLUSIVE"
        else:
            got = "SURVIVED"
        flag = ""
        if got != expect:
            flag = f"  <-- EXPECTED {expect}"
            self.failures.append(f"{label} ({got})")
        print(f"  {label:52} {got:13}{summary}{flag}")

    def patch(self, path: Path, old: str, new: str, label: str, expect: str = "KILLED") -> None:
        """Replace one unique substring, run, restore."""
        if not selected(label):
            return
        original = path.read_bytes()
        try:
            text = original.decode("utf-8")
            # Normalise the ANCHOR to the file's own line endings. Every
            # anchor here is written with bare \n while these files are
            # CRLF on a checkout with core.autocrlf, so five multi-line
            # anchors matched nothing and reported SKIPPED. Three of the
            # five were BM2, BM3 and BM5, the mutants that reproduce this
            # incident, and a commit message asserted them as killed on
            # the strength of a run taken while the files happened to be
            # LF. `append` and `create` already did this; `patch` did not.
            if "\r\n" in text:
                old = old.replace("\r\n", "\n").replace("\n", "\r\n")
                new = new.replace("\r\n", "\n").replace("\n", "\r\n")
            if text.count(old) != 1:
                print(f"  {label:52} SKIPPED (anchor appears {text.count(old)} times)")
                self.failures.append(f"{label} (anchor missing)")
                return
            park(path, original)
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            self._verdict(label, *run(self.target), expect=expect)
        finally:
            path.write_bytes(original)
            unpark(path)

    def append(self, path: Path, extra: str, label: str, expect: str = "KILLED") -> None:
        """Append text to an existing file, run, restore."""
        if not selected(label):
            return
        original = path.read_bytes()
        try:
            park(path, original)
            path.write_bytes(original + extra.replace("\n", "\r\n").encode("utf-8"))
            self._verdict(label, *run(self.target), expect=expect)
        finally:
            path.write_bytes(original)
            unpark(path)

    def create(self, path: Path, content: str, label: str, expect: str = "KILLED") -> None:
        """Create a file that should be refused, run, delete."""
        if not selected(label):
            return
        if path.exists():
            # Never write over a real file. `finally` unlinks
            # unconditionally, so a name collision would destroy it with
            # no backup to restore from.
            print(f"  {label:52} SKIPPED ({path.name} already exists)")
            self.failures.append(f"{label} (target exists)")
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # A tombstone: an empty slot means "this path did not exist,
            # delete it on recovery". Without it a kill mid-create leaves
            # an untracked file holding a deliberately unguarded import,
            # and `recover()` has nothing to find.
            park(path, b"")
            path.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
            self._verdict(label, *run(self.target), expect=expect)
        finally:
            path.unlink(missing_ok=True)
            unpark(path)


def prove_guard_a() -> list[str]:
    """Run the battery against the extras-isolation scanner."""
    if WANTED and not any(prefix.startswith(("M", "N")) for prefix in WANTED):
        SKIPPED_GUARDS.append(GUARD_A)
        return []
    print(f"\n{GUARD_A}")
    code, summary = run(GUARD_A)
    print(f"  {'CONTROL (unmutated tree)':52} {'GREEN':9}{summary}")
    if code:
        return ["guard A control is not green"]

    battery = Battery(GUARD_A)
    tests = REPO / "tests" / "test_utils_manual.py"
    guard = REPO / "tests" / "test_extras_isolation.py"
    original = 'pypdf = pytest.importorskip("pypdf")'

    battery.patch(tests, original, "import pypdf", "M1  the original defect, restored")
    battery.patch(tests, original, "from pypdf import PdfReader", "M2  the from-import form")
    battery.patch(
        tests,
        original,
        "import importlib; pypdf = importlib.import_module('pypdf')",
        "M3  the dynamic import_module form",
    )
    battery.create(
        REPO / "tests" / "deep" / "nest" / "test_zz_mutant.py",
        "import pypdf\n",
        "M4  a new file nested two levels down",
    )
    battery.create(
        REPO / "examples" / "zz_mutant_plot.py",
        "import matplotlib.pyplot as plt\n",
        "M5  the other extra, matplotlib",
    )
    battery.create(
        REPO / "docs" / "zz_mutant.md",
        f"# m\n\n{FENCE}python\nimport pypdf\n{FENCE}\n",
        "M6  a fenced block in a docs page",
    )
    battery.patch(
        guard,
        'for path in sorted((REPO / root).rglob("*.py")):',
        'for path in sorted((REPO / root).glob("*.py")):',
        "M7  rglob degraded to a flat glob",
    )
    battery.patch(
        guard,
        "    return at_risk - always",
        "    return set()",
        "M8  forbidden set emptied",
    )
    battery.patch(
        guard,
        "    return set.intersection(*sets)",
        "    return set.union(*sets)",
        "M9  intersection widened to union",
    )
    battery.append(
        REPO / "conftest.py", "\nimport pypdf\n", "M10 an unguarded import in the ROOT conftest"
    )
    battery.create(
        REPO / "docs" / "zz_mutant_doctest.md",
        f"# m\n\n{FENCE}python\n>>> import pypdf\n>>> pypdf\n{FENCE}\n",
        "M11 a DOCTEST fence in a docs page",
    )
    battery.append(
        REPO / "src" / "pyflightstream" / "options.py",
        '\n\ndef _zz():\n    """Doc.\n\n    >>> import pypdf\n    """\n',
        "M12 a doctest inside a src docstring",
    )
    battery.create(
        REPO / ".claude" / "hooks" / "zz_mutant_hook.py",
        "import pypdf\n",
        "M13 an unguarded import in .claude/hooks",
    )
    battery.patch(
        REPO / ".github" / "workflows" / "ci.yml",
        "        run: pip install -e .[dev,fsi,geom,manual,plot]",
        "        run: pip install -e .[dev,fsi,geom]",
        "M14 the all-extras leg reduced to the lean set",
    )
    battery.create(
        REPO / "docs" / "zz_mutant_prose.md",
        f"# m\n\n{FENCE}python\nthis is prose, not python, and holds no doctest\n{FENCE}\n",
        "M15 a fence that is neither python nor a doctest",
    )
    battery.patch(
        guard,
        'SCAN_ROOTS = ("src", "tests", "examples", "scripts", ".claude/hooks", ".claude/tools")',
        'SCAN_ROOTS = ("src",)',
        "M16 the scan narrowed to one tree",
    )
    battery.patch(
        guard,
        "dist/[^" + chr(92) + '"' + chr(39) + r"\[\]]*?(?:\.whl|\}\})",
        r"dist/\S*?(?:\.whl|\}\})",
        "M17 the install matcher unable to cross whitespace",
    )

    battery.patch(
        guard,
        '    return "".join(\n'
        "        example.source for example in doctest.DocTestParser()"
        ".get_examples(text, name=label)\n"
        "    )",
        "    try:\n"
        '        return "".join(\n'
        "            example.source for example in doctest.DocTestParser()"
        ".get_examples(text, name=label)\n"
        "        )\n"
        "    except ValueError:\n"
        '        return ""',
        "M18 doctest_source swallows a malformed doctest",
    )

    # NEGATIVE CONTROLS. These must SURVIVE: refusing a legitimate idiom
    # is how a guard gets weakened rather than obeyed.
    battery.append(
        REPO / "src" / "pyflightstream" / "options.py",
        "\nfrom typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import pypdf\n",
        "N1  an import under if TYPE_CHECKING",
        expect="SURVIVED",
    )
    battery.append(
        REPO / "src" / "pyflightstream" / "options.py",
        "\ntry:\n    import pypdf\nexcept ImportError:\n    pypdf = None\n",
        "N2  a try/except ImportError fallback",
        expect="SURVIVED",
    )
    return battery.failures


def main() -> int:
    """Run the battery and report.

    Said in the singular since 2026-08-12. It read "run both batteries" for a
    day after the second battery was deleted, inside the file renamed for
    exactly that class of stale sentence.
    """
    WANTED.extend(sys.argv[1:])
    stranded = recover()
    if stranded:
        print("RECOVERED mutations a previous run was killed in the middle of:")
        for name in stranded:
            print(f"  {name}")
        print("Re-run from a clean tree.\n")
        return 1

    failures = prove_guard_a()

    print()
    print("check `git status` before trusting this: the battery edits the working tree")
    if failures:
        print(f"\nUNEXPECTED VERDICTS ({len(failures)}):")
        for item in failures:
            print(f"  {item}")
        print("\nA mutant that survives is a hole; a control that dies is a false positive.")
        return 1

    # A run that selected nothing is not a clean run. Refusing here is
    # the whole reason OFFERED and RAN exist: `--help`, or a mistyped
    # label, used to print the success sentence having proved nothing.
    if not RAN:
        print(f"\nNOTHING RAN. The filter {WANTED} matched none of the {len(OFFERED)} labels:")
        for label in OFFERED:
            print(f"  {label}")
        return 1

    if WANTED:
        skipped = f", and {', '.join(SKIPPED_GUARDS)} entirely" if SKIPPED_GUARDS else ""
        print(
            f"\nPARTIAL RUN: {len(RAN)} of the {len(OFFERED)} mutants this filter "
            f"reached{skipped}, selected by {WANTED}."
            "\nThe others were NOT run and this is not a proof of them."
        )
    else:
        print(f"\nevery one of the {len(RAN)} mutants died and every control survived")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
