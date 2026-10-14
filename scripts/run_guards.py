"""Run the retained structural and product-protection guards.

Use --list to inspect the selection. Historical release-record and prose
currency guards belong to internal release tooling. Exit 0 only when every
selected file ran tests and passed; exit 2 if a selected file is missing.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIER1 = "tests/tier1_offline"

#: The guard files, each judging the whole tree. Kept in one list so the
#: guard test can check that every entry exists.
GUARDS = (
    f"{TIER1}/test_architecture_metrics.py",
    f"{TIER1}/test_extras_isolation.py",
    f"{TIER1}/test_goal028_module_level_layering.py",
    f"{TIER1}/test_p0400_reach_guard.py",
    f"{TIER1}/test_p0380_guards.py",
    f"{TIER1}/test_repository_guards.py",
)


def missing_guards(root: Path | None = None, guards: tuple[str, ...] | None = None) -> list[str]:
    """Return the guard files that do not exist under the root (the module's, by default)."""
    root = ROOT if root is None else root
    return [g for g in (GUARDS if guards is None else guards) if not (root / g).is_file()]


def _outcomes(junit: Path, guards: tuple[str, ...]) -> dict[str, list[str] | None]:
    """Map each guard file to the names of its failed tests; None when none of its tests ran.

    A test case belongs to a guard when its dotted class name is the guard's
    module or starts with it (a test class inside the module). A skipped case
    did not run, so a guard whose every case was skipped maps to None and is
    reported NOT RUN (NFR-44 R1).
    """
    modules = {g: g[: -len(".py")].replace("/", ".") for g in guards}
    result: dict[str, list[str] | None] = dict.fromkeys(guards)
    for case in ET.parse(junit).getroot().iter("testcase"):
        classname = case.get("classname") or ""
        bad = case.find("failure") is not None or case.find("error") is not None
        if case.find("skipped") is not None and not bad:
            continue
        for guard, module in modules.items():
            if classname == module or classname.startswith(module + "."):
                names = result[guard]
                if names is None:
                    names = []
                if bad:
                    names.append(case.get("name") or "")
                result[guard] = names
                break
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the guards and print one line per guard file; return the exit status."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--list", action="store_true", help="print the guard files and exit")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(GUARDS))
        return 0
    absent = missing_guards()
    if absent:
        print("missing guard files: " + ", ".join(absent))
        return 2
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "guards.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-n",
            "4",
            f"--junitxml={junit}",
            *GUARDS,
        ]
        status = subprocess.run(command, cwd=ROOT, env=dict(os.environ), check=False).returncode
        outcomes = _outcomes(junit, GUARDS) if junit.is_file() else dict.fromkeys(GUARDS)
    print()
    for guard in GUARDS:
        names = outcomes[guard]
        state = "PASS" if names == [] else ("FAIL" if names else "NOT RUN")
        detail = f" ({len(names)}: {', '.join(names[:3])})" if names else ""
        print(f"{state:7s} {guard}{detail}")
    green = status == 0 and all(v == [] for v in outcomes.values())
    print(f"guards: {'green' if green else 'RED'} in {time.monotonic() - started:.0f} s")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
