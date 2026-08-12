# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: check_spawn_env.py
# body-sha256: b5db024d0e110f379bc9c019ed2ef117e14a952b95895593d81a2e394a3c7619
# canonical-source: BUILT for the kit (0.2.16, HUB-12) from ITC-20260802-0200, the spawn guard reads a line window not the call. A repository's own guard decided whether a spawn site passed an explicit environment by reading a fixed window of lines after each `subprocess.run(`, and lane ITA-11 round two met BOTH of its failure directions in one commit: a helper's `env=child_env()` sixteen lines below a DIFFERENT function's call excused two real offenders, and a correct call whose argv was written one element per line was reported as an offender seventeen lines from its own opening. The shared thing is not that test, it is the checker SHAPE: a needle that is a text window over source rather than the construct it claims to measure. Records: coordination/DESIGN_HUB-12_kit_batch.md item 6.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Every subprocess spawn must pass an explicit environment, judged per CALL.

Usage:
    python check_spawn_env.py <directory> [<directory> ...]

Exit codes: 0 clean, 1 an offender, 2 configuration error.

WHY THIS EXISTS, and the defect is in the GUARD rather than in the code it
guards. A repository wrote a test that decided whether a spawn site passed an
explicit environment by searching a fixed window of lines after each
``subprocess.run(``. That is a text window over source, not a reading of the
call, and lane ITA-11 round two met both of its failure directions in ONE
commit:

- a helper spread three git spawns over a loop and put ``env=child_env()``
  SIXTEEN lines below the ``subprocess.run(`` of a DIFFERENT function, so a
  neighbour's keyword excused calls that passed no environment at all;
- ``_ask`` DID pass ``env=child_env()``, seventeen lines after its own
  opening line because its argv was written one element per line, and it was
  reported as an offender.

The pressure a window-based guard creates is the dangerous half: the obvious
repair is to WIDEN the window until the false red goes away, and a widened
window is exactly how a real offender becomes invisible. The repository in
question has already paid for the underlying failure once, ``COV_CORE_*``
leaking into a spawned child and aborting CI after every test passed, which
is why the guard exists at all.

WHAT THIS DOES INSTEAD. It parses each module with ``ast`` and looks at the
CALL. A keyword named ``env`` must be on the ``Call`` node itself. A
neighbour's keyword is a different node and is invisible here, which is the
whole point, and a keyword written a hundred lines from its opening
parenthesis is still on its own call.

WHAT COUNTS AS A SPAWN. ``subprocess.run``, ``subprocess.Popen``,
``subprocess.call``, ``subprocess.check_call`` and
``subprocess.check_output``, called through the module or through a bare name
that the SAME module imported from ``subprocess``. A bare ``run(...)`` in a
module that never imported it from ``subprocess`` is somebody's own function
and is not this guard's business.

A ``**kwargs`` SPLAT SATISFIES THE CHECK AND IS REPORTED. The checker cannot
see inside a dict it did not build, so refusing there would be a false red
and passing silently would be a lie about coverage. It is counted and named
in the output as UNVERIFIABLE, so a reader knows what the clean verdict did
and did not cover.

EVERY MODULE UNDER THE DIRECTORY, not ``test_*.py``. That is the incident's
second, smaller item, recorded by a QA lens as new ground: a shared helper
sitting outside the naming convention spawns nothing today, and the next one
that does would be unguarded silently. A guard whose scope is a filename
convention is a guard with a door in it.

A FILE THAT DOES NOT PARSE IS A REFUSAL, exit 2, naming the file. A checker
that passes silently over what it could not read is the failure this kit
registers most often.

WHAT IT DOES NOT COVER, stated rather than implied: ``os.system``,
``os.spawn*``, ``os.execv*``, ``multiprocessing`` and any spawn made through
a wrapper this checker cannot see through, for example a call whose callee is
an attribute of a variable. The incident is about ``subprocess``, and a
checker that claimed the whole class while measuring one library would be the
defect it was written to fix, one level up.

Standalone, stdlib only, no third-party deps, like every kit checker.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

MODULE = "subprocess"
FUNCTIONS = ("run", "Popen", "call", "check_call", "check_output")
REQUIRED = "env"


class ConfigError(Exception):
    """The check could not run. Never reported as a clean tree."""


def _bare_names(tree: ast.AST) -> set[str]:
    """The spawn functions THIS module imported from subprocess by name.

    A bare ``run(...)`` is only a spawn when the module said so, which is
    what keeps somebody's own ``run`` helper out of the offender list.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == MODULE:
            for alias in node.names:
                if alias.name in FUNCTIONS:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == MODULE and alias.asname:
                    # `import subprocess as sp` -> `sp.run` is still a spawn.
                    names.add(f"{alias.asname}.")
    return names


def _callee(node: ast.Call, bare: set[str]) -> str | None:
    """The spawn this call makes, or None if it is not a spawn.

    Only names resolvable STATICALLY are reported. A call through a
    variable is invisible here and the docstring says so; guessing would
    produce the false reds this checker exists to remove.
    """
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in FUNCTIONS:
        owner = func.value
        if isinstance(owner, ast.Name):
            if owner.id == MODULE or f"{owner.id}." in bare:
                return f"{owner.id}.{func.attr}"
        return None
    if isinstance(func, ast.Name) and func.id in bare:
        return func.id
    return None


def audit(path: Path) -> tuple[list[str], list[str], int]:
    """Audit one module. Returns (offenders, unverifiable, spawns seen)."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ConfigError(
            f"{path} does not parse: {exc}. A module this checker cannot "
            "read is refused rather than skipped; a guard that passes over "
            "what it could not parse reports a clean tree over less than it "
            "was given.") from exc
    bare = _bare_names(tree)
    offenders: list[str] = []
    unverifiable: list[str] = []
    seen = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee(node, bare)
        if name is None:
            continue
        seen += 1
        keywords = {kw.arg for kw in node.keywords}
        if REQUIRED in keywords:
            continue
        if None in keywords:
            # A `**kwargs` splat. Accepted, and NAMED: the checker cannot
            # see inside a dict it did not build, and silence here would
            # be a claim about coverage that this file cannot support.
            unverifiable.append(
                f"{path}:{node.lineno}: {name} passes **kwargs, so whether "
                f"it sets {REQUIRED}= cannot be read from the call")
            continue
        offenders.append(
            f"{path}:{node.lineno}: {name} passes no {REQUIRED}=. The child "
            "inherits this process's whole environment, including anything "
            "the test runner injected. Pass the environment explicitly on "
            "THIS call.")
    return offenders, unverifiable, seen


def walk(roots: list[Path]) -> tuple[list[str], list[str], int, int]:
    offenders: list[str] = []
    unverifiable: list[str] = []
    modules = 0
    spawns = 0
    for root in roots:
        if not root.is_dir():
            raise ConfigError(
                f"{root} is not a directory. Pass the directory whose "
                "modules should be checked, for example tests.")
        for module in sorted(root.rglob("*.py")):
            modules += 1
            found, unsure, seen = audit(module)
            offenders += found
            unverifiable += unsure
            spawns += seen
    return offenders, unverifiable, modules, spawns


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv[1:]]
    if not roots:
        print("usage: check_spawn_env.py <directory> [<directory> ...]",
              file=sys.stderr)
        return 2
    try:
        offenders, unverifiable, modules, spawns = walk(roots)
    except ConfigError as exc:
        print(f"CONFIG: {exc}", file=sys.stderr)
        return 2
    if modules == 0:
        # An audit that examined nothing is a misconfiguration wearing a
        # green verdict, which is the shape this kit refuses everywhere
        # else it counts something.
        print(f"CONFIG: no *.py module under {', '.join(str(r) for r in roots)}"
              ". An audit that examined nothing is a configuration error, "
              "not a clean tree.", file=sys.stderr)
        return 2
    for line in offenders:
        print(f"UNGUARDED {line}")
    for line in unverifiable:
        print(f"UNVERIFIABLE {line}")
    # Always printed, so a passing run is never indistinguishable from one
    # that examined nothing, and so the clean verdict states its own scope.
    print(f"checked {modules} module(s), {spawns} spawn call(s), "
          f"{len(offenders)} unguarded, {len(unverifiable)} unverifiable")
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
