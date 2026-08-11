#!/usr/bin/env python3
r"""Mutation proof for the two guards that close INC-20260810-2140-shared.

Committed rather than kept in a scratchpad, which is this workspace's own
practice (`.claude/tools/check_plan_kit_mutations.py` and
`check_side_effect_guard_mutations.py` ship beside the checkers they
prove, and the kit's V and V lens once refused a promotion that shipped a
checker without its mutations). A guard's evidence that nobody else can
re-run is an assertion, not evidence.

    python scripts/prove_extras_and_ci_guards.py            # everything
    python scripts/prove_extras_and_ci_guards.py M1 M2 N1   # by label prefix

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
#: holding the mutation that UNWIRES the CI gate; had it been committed,
#: the guard would have shipped disabled, which is the exact failure the
#: guard exists to prevent. A `finally` does not survive SIGKILL, and
#: this workspace already has an incident about a review process dying
#: with mutations in the tree.
BACKUP = REPO / ".git" / "mutation-backup"

GUARD_A = "tests/test_extras_isolation.py"
GUARD_B = "tests/test_ci_release_gate.py"

#: A backtick fence, built rather than written, so this file carries no
#: fence of its own for the scanner it is proving to trip over.
FENCE = chr(96) * 3


def run(target: str) -> tuple[int, str]:
    """Run one test file and return its exit code and summary line."""
    done = subprocess.run(
        [str(PYTHON), "-m", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
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
        target = REPO / slot.name.replace("%", "/")
        target.write_bytes(slot.read_bytes())
        slot.unlink()
        restored.append(target.relative_to(REPO).as_posix())
    return restored


#: Label prefixes to run, from the command line. Empty means all.
WANTED: list[str] = []


def selected(label: str) -> bool:
    """Whether a mutant's label was asked for."""
    return not WANTED or any(label.startswith(prefix) for prefix in WANTED)


class Battery:
    """Apply mutants one at a time, restoring bytes after each."""

    def __init__(self, target: str) -> None:
        self.target = target
        self.failures: list[str] = []

    def _verdict(self, label: str, code: int, summary: str, expect: str) -> None:
        got = "KILLED" if code else "SURVIVED"
        flag = ""
        if got != expect:
            flag = f"  <-- EXPECTED {expect}"
            self.failures.append(label)
        print(f"  {label:52} {got:9}{summary}{flag}")

    def patch(self, path: Path, old: str, new: str, label: str, expect: str = "KILLED") -> None:
        """Replace one unique substring, run, restore."""
        if not selected(label):
            return
        original = path.read_bytes()
        try:
            text = original.decode("utf-8")
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
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
            self._verdict(label, *run(self.target), expect=expect)
        finally:
            path.unlink(missing_ok=True)


def prove_guard_a() -> list[str]:
    """Run the battery against the extras-isolation scanner."""
    if WANTED and not any(prefix.startswith(("M", "N")) for prefix in WANTED):
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


def prove_guard_b() -> list[str]:
    """Run the battery against the CI-green release gate."""
    if WANTED and not any(prefix.startswith("BM") for prefix in WANTED):
        return []
    print(f"\n{GUARD_B}")
    code, summary = run(GUARD_B)
    print(f"  {'CONTROL (unmutated hook)':52} {'GREEN':9}{summary}")
    if code:
        return ["guard B control is not green"]

    battery = Battery(GUARD_B)
    hook = REPO / ".claude" / "hooks" / "ci_release_gate.py"
    settings = REPO / ".claude" / "settings.json"

    battery.patch(
        hook,
        'GOOD = frozenset({"success", "neutral", "skipped"})',
        'GOOD = frozenset({"success", "neutral", "skipped", "failure", "cancelled"})',
        "BM1 accepted conclusions widened to failure",
    )
    battery.patch(
        hook,
        '    if bad:\n        return "red", _summarise(bad)',
        '    if False:\n        return "red", _summarise(bad)',
        "BM2 the red branch disabled",
    )
    battery.patch(
        hook,
        '    if not runs:\n        return "absent"',
        '    if not runs:\n        return "green"',
        "BM3 an empty payload reads as green",
    )
    battery.patch(
        hook,
        '    return "unreachable", last or "no answer"',
        '    return "ok", []',
        "BM4 unreachable downgraded to an empty ok",
    )
    battery.patch(
        hook,
        '    if pending:\n        return "pending", _summarise(pending)',
        '    if False:\n        return "pending", _summarise(pending)',
        "BM5 pending downgraded to green",
    )
    battery.patch(
        hook,
        '        if at and (status != "completed" or not completed or completed > at):',
        "        if False:",
        "BM6 the historical instant ignored",
    )
    battery.patch(
        hook,
        "            if any(marker in last for marker in _NO_SUCH_COMMIT):",
        "            if False:",
        "BM7 a 422 reported as unreachable",
    )
    battery.patch(
        hook,
        "        if isinstance(total, int) and total > len(runs):",
        "        if False:",
        "BM8 a truncated page read as complete",
    )
    battery.patch(
        hook,
        '        return token.strip("' + chr(92) + '"' + chr(39) + '")',
        "        break",
        "BM9 the named remote ignored, always origin",
    )
    battery.patch(
        settings,
        '"command": "python \\"$CLAUDE_PROJECT_DIR/.claude/hooks/ci_release_gate.py\\""',
        '"command": "python \\"$CLAUDE_PROJECT_DIR/.claude/hooks/role_review_gate.py\\""',
        "BM10 the hook silently unwired from settings",
    )

    battery.patch(
        hook,
        '        url = _git(root, "config", "--get", f"remote.{remote}.pushurl") or _git(\n'
        '            root, "config", "--get", f"remote.{remote}.url"\n'
        "        )",
        '        url = _git(root, "config", "--get", f"remote.{remote}.url")',
        "BM12 pushurl ignored, fetch url used",
    )
    battery.patch(
        hook,
        "        if is_push and deletes_a_ref(after):",
        "        if False:",
        "BM13 a tag deletion gated as a publish",
    )
    battery.patch(
        hook,
        "        if is_push and not after:",
        "        if False:",
        "BM14 the kit fail-closed sentinel read as an allow",
    )
    battery.patch(
        hook,
        "        targets = tag_targets(after, tags)",
        "        targets = {tag: tag for tag in tags}",
        "BM15 a refspec resolved from its destination",
    )

    if selected("BM16"):
        original = hook.read_bytes()
        try:
            park(hook, original)
            hook.unlink()
            battery._verdict("BM16 the hook file deleted entirely", *run(GUARD_B), expect="KILLED")
        finally:
            hook.write_bytes(original)
            unpark(hook)
    return battery.failures


def main() -> int:
    """Run both batteries and report."""
    WANTED.extend(sys.argv[1:])
    stranded = recover()
    if stranded:
        print("RECOVERED mutations a previous run was killed in the middle of:")
        for name in stranded:
            print(f"  {name}")
        print("Re-run from a clean tree.\n")
        return 1

    failures = prove_guard_a() + prove_guard_b()
    print()
    if failures:
        print(f"UNEXPECTED VERDICTS ({len(failures)}):")
        for item in failures:
            print(f"  {item}")
        print("\nA mutant that survives is a hole; a control that dies is a false positive.")
        return 1
    print("every mutant died and every control survived")
    print("check `git status` before trusting this: the battery edits the working tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
