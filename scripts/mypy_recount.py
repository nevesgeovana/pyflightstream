"""Re-measure the type-checker exemption debt, and emit every figure RPT-029 states.

    python scripts/mypy_recount.py [--out <dir>]

WHY THIS IS A SCRIPT AND NOT A PROCEDURE IN A REPORT. `RPT-029` carries one
measurement in six shapes: a dated sentence, two quoted tool lines, a
per-module table, a per-code table, a concentration list and a delta table.
On 2026-08-19 it held THREE MUTUALLY CONTRADICTORY statements of that one
measurement, because the sentence had been retyped to follow a new module
total and the tool output beside it had not.
`tests/test_traceability.py` now guards two of the six against each other,
which is what caught it. This script closes the rest of the gap from the other
side: every figure comes out of one run, so retyping one of them cannot be
done at all.

WHAT IT MEASURES. Two invocations of mypy over `src/pyflightstream`:

* with the `[tool.mypy]` overrides OFF, supplied as a separate config file so
  the measurement never requires the shipped configuration to be in a state
  this repository does not ship. Its final line is the debt.
* with the shipped configuration, overrides and all, which must be green.

THE COUNT DEPENDS ON THE ENVIRONMENT and the report says so at length:
`[tool.mypy]` deliberately does not pin `python_version`, and a large share of
the findings are `arg-type` against numpy, xarray and pandas stubs rather than
against anything this package declares. So the environment is printed with the
numbers rather than left to be reconstructed.

MYPY WALKS THE FILESYSTEM rather than the git index, so a tree carrying
uncommitted work does not reproduce a committed measurement, and the
difference does not announce itself. This script prints `git status --short`
alongside, so the reader of its output can see whether the tree was settled.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The shipped `[tool.mypy]` minus its override blocks. Written to a temporary
#: file rather than by editing `pyproject.toml`, which is the whole point: the
#: repository is never left in a configuration it does not ship.
BARE_CONFIG = """[mypy]
files = src/pyflightstream
ignore_missing_imports = True
disallow_untyped_defs = False
warn_return_any = False
"""

#: A mypy finding: path, line, then the message, then the code in brackets at
#: the END of the line. Reading the FIRST bracket is wrong in a way that looks
#: right, and the report records why: a message about `list[str]` offers
#: `[str]` before it offers its real code, and a tally built that way reported
#: four codes this checker does not emit.
FINDING = re.compile(r"^(?P<path>.+?):(?P<line>\d+): error: .*\[(?P<code>[a-z-]+)\]\s*$")
FINAL = re.compile(r"^Found (\d+) errors? in (\d+) files? \(checked (\d+) source files?\)$")


def _run_mypy(config: Path | None) -> tuple[list[str], str]:
    """Run mypy over the package and return its lines and its final line.

    Parameters
    ----------
    config : Path or None
        Config file to use, or None for the shipped `pyproject.toml`.

    Returns
    -------
    tuple of list of str and str
        Every output line, and the final line alone.
    """
    argv = [sys.executable, "-m", "mypy", "--no-color-output"]
    if config is not None:
        argv += ["--config-file", str(config)]
    else:
        argv += ["src/pyflightstream"]
    # THE ENVIRONMENT IS PASSED EXPLICITLY, which is `check_spawn_env.py`'s
    # rule and which this script broke on its first run. `os.environ.copy()`
    # is EXACTLY what an omitted `env=` gives, so nothing about the child
    # changes; what changes is that the inheritance is a decision at the call
    # site. It matters here more than most: this measurement depends on the
    # interpreter and on the installed stubs, so the environment the child
    # gets is part of the number.
    completed = subprocess.run(
        argv, capture_output=True, text=True, cwd=REPO, env=os.environ.copy()
    )
    lines = [line.rstrip() for line in completed.stdout.splitlines() if line.strip()]
    return lines, lines[-1] if lines else ""


def _module_name(path: str) -> str:
    """Turn a reported source path into its dotted module name."""
    relative = Path(path.replace("\\", "/")).as_posix()
    marker = "src/pyflightstream/"
    if marker in relative:
        relative = relative.split(marker, 1)[1]
    stem = relative[: -len(".py")] if relative.endswith(".py") else relative
    parts = [part for part in stem.split("/") if part]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(["pyflightstream", *parts])


def _environment() -> list[str]:
    """Return the version lines the count depends on."""
    rows = [f"python   {sys.version.split()[0]} ({sys.platform})"]
    for name in ("mypy", "numpy", "xarray", "pandas", "pydantic"):
        try:
            module = __import__(name)
            rows.append(f"{name:8} {getattr(module, '__version__', 'unknown')}")
        except ImportError:
            rows.append(f"{name:8} NOT INSTALLED")
    return rows


def main() -> int:
    """Run both invocations and print every figure the report states."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    out = Path(args.out).resolve() if args.out else None

    tracked = subprocess.run(
        ["git", "ls-tree", "-r", "HEAD", "--name-only", "src/pyflightstream"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=os.environ.copy(),
    ).stdout
    modules = [name for name in tracked.splitlines() if name.endswith(".py")]

    dirty = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=os.environ.copy(),
    ).stdout.strip()

    # THE CONFIG NEVER LANDS IN THE REPOSITORY unless the caller asks for it
    # with --out. Writing it to the tree by default would leave an untracked
    # file behind after a measurement whose whole point is that the tree is
    # settled, and the next run would then report the tree as dirty because of
    # the previous run.
    with tempfile.TemporaryDirectory() as scratch:
        config = (out or Path(scratch)) / "recount_mypy.ini"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(BARE_CONFIG, encoding="utf-8")
        bare_lines, bare_final = _run_mypy(config)
    _, shipped_final = _run_mypy(None)

    findings = [match.groupdict() for line in bare_lines if (match := FINDING.match(line))]
    per_module_errors: collections.Counter[str] = collections.Counter()
    per_module_lines: dict[str, set[str]] = collections.defaultdict(set)
    per_code: collections.Counter[str] = collections.Counter()
    per_site: collections.Counter[str] = collections.Counter()
    for finding in findings:
        module = _module_name(finding["path"])
        per_module_errors[module] += 1
        per_module_lines[module].add(finding["line"])
        per_code[finding["code"]] += 1
        site = Path(finding["path"].replace("\\", "/")).as_posix()
        per_site[f"{site}:{finding['line']}"] += 1

    print("=" * 72)
    print("TREE")
    print("=" * 72)
    print(f"tracked modules under src/pyflightstream: {len(modules)}")
    if dirty:
        print("THE TREE IS NOT SETTLED. mypy walks the filesystem, so these numbers")
        print("do not reproduce from the committed tree. Uncommitted paths:")
        for line in dirty.splitlines():
            print("   ", line)
    else:
        print("the tree is clean, so these numbers reproduce from HEAD")

    print()
    for row in _environment():
        print("   ", row)

    print()
    print("=" * 72)
    print("THE TWO INVOCATIONS")
    print("=" * 72)
    print("    " + bare_final)
    print("    " + shipped_final)

    final = FINAL.match(bare_final)
    if final is None:
        print("\nthe overrides-off run did not end in a countable line; nothing is stated")
        return 1
    errors, dirty_files, checked = final.groups()
    if int(checked) != len(modules):
        print(
            f"\nmypy checked {checked} source files and git tracks {len(modules)}. "
            "One of the two is not the package; do not state either number until "
            "that is explained (an untracked .py under src/ is the usual cause)."
        )
    print()
    print(
        f"**mypy recount {date.today().isoformat()}: {errors} errors in "
        f"{dirty_files} of {checked} modules.**"
    )

    print()
    print("=" * 72)
    print("THE DEBT, PER MODULE")
    print("=" * 72)
    print("    errors   lines   module")
    for module, count in sorted(per_module_errors.items(), key=lambda item: (-item[1], item[0])):
        print(f"    {count:6}  {len(per_module_lines[module]):6}   {module}")
    print("       ---     ---")
    total_lines = sum(len(v) for v in per_module_lines.values())
    print(
        f"    {sum(per_module_errors.values()):6}  {total_lines:6}   "
        f"{len(per_module_errors)} modules of {checked}"
    )

    print()
    print("BY ERROR CODE:")
    for code, count in per_code.most_common():
        print(f"    {count:4}  {code}")

    print()
    print("CONCENTRATION, the sites reporting more than once:")
    heavy = [(site, n) for site, n in per_site.most_common() if n > 1]
    for site, count in heavy[:12]:
        print(f"    {count:3}  {site}")
    print(
        f"    {sum(n for _, n in heavy[:6])} errors sit on the top six sites, of "
        f"{sum(per_module_errors.values())}"
    )
    print(
        f"    {sum(per_module_errors.values())} errors sit on {total_lines} distinct source lines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
