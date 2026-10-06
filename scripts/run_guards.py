"""Run the cross-cutting guards alone, in one process, and say which failed (NFR-44).

Usage:
    python scripts/run_guards.py            run every guard, one line per guard file
    python scripts/run_guards.py --list     print the guard files and exit

The guards are the tier-1 tests that judge the whole tree rather than one
feature: architecture metrics, private-name coupling, the requirements index,
the repository and house-style guards, the documented rows and invocations,
claim currency, the release-ready record and the SRS consistency. A change that
breaks one of them breaks it whatever file it touched, so they run after every
fix commit and at every lane close, and the full suite runs once per wave.
Exit status: 0 when every guard passed, 1 when any failed, 2 when a guard file
is missing.
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
    f"{TIER1}/test_citation_claim_currency.py",
    f"{TIER1}/test_claim_currency.py",
    f"{TIER1}/test_documented_invocations.py",
    f"{TIER1}/test_documented_rows.py",
    f"{TIER1}/test_house_style.py",
    f"{TIER1}/test_no_estate_headers.py",
    f"{TIER1}/test_p0320_k1_srs_coverage.py",
    f"{TIER1}/test_p0340_release_ready.py",
    f"{TIER1}/test_p0380_guards.py",
    f"{TIER1}/test_repository_guards.py",
    f"{TIER1}/test_requirements_index.py",
    f"{TIER1}/test_srs_changelog.py",
    f"{TIER1}/test_srs_consistency.py",
    f"{TIER1}/test_traceability.py",
)


def missing_guards(root: Path | None = None, guards: tuple[str, ...] | None = None) -> list[str]:
    """Return the guard files that do not exist under the root (the module's, by default)."""
    root = ROOT if root is None else root
    return [g for g in (GUARDS if guards is None else guards) if not (root / g).is_file()]


def _outcomes(junit: Path) -> dict[str, list[str]]:
    failed: dict[str, list[str]] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = (case.get("classname") or "").replace(".", "/") + ".py"
        bad = case.find("failure") is not None or case.find("error") is not None
        failed.setdefault(name, [])
        if bad:
            failed[name].append(case.get("name") or "")
    return failed


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
            "auto",
            f"--junitxml={junit}",
            *GUARDS,
        ]
        status = subprocess.run(command, cwd=ROOT, env=dict(os.environ), check=False).returncode
        outcomes = _outcomes(junit) if junit.is_file() else {}
    print()
    for guard in GUARDS:
        names = next(
            (v for k, v in outcomes.items() if guard.endswith(k.split("tests/", 1)[-1])), None
        )
        state = "PASS" if names == [] else ("FAIL" if names else "NOT RUN")
        detail = f" ({len(names)}: {', '.join(names[:3])})" if names else ""
        print(f"{state:7s} {guard}{detail}")
    print(f"guards: {'green' if status == 0 else 'RED'} in {time.monotonic() - started:.0f} s")
    return 0 if status == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
