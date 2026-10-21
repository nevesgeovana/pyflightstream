#!/usr/bin/env python3
"""Measure the SRS levels against their approved ceilings and check the L3 traceability.

Three layers are read. The method layer (L0 stage goals and central L1 requirements) comes
from the method table of ``docs/srs/numerical-laboratory-method.md``. The instantiation and
quality layers (L1 capabilities and L2 behaviour) come from the authored registers under
``docs/unpublished/requirements``. The L3 layer is ``tests/requirements_l3.csv``: one detail
row per line, each tied to its parent L2 and to the test that verifies it (MOOSE and NQA-1
style), so it is checked by tooling and never read as a page.

Run ``python scripts/srs_levels.py`` for a table against the targets, or ``--json`` for one
JSON object on stdout. The exit status is 0 only when every ceiling holds AND the L3
traceability holds (every L3 row resolves to an existing test under a live L2, and every L2
has an L3 row or a direct test anchor). Standard library and the repository's own scripts
only; no network, no solver.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _requirements_paths import (  # noqa: E402
    L3_REQUIREMENTS,
    read_l3,
    read_requirements,
    roadmap_uids,
)
from gen_requirements_index import anchor_names_a_test  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
METHOD_PAGE = Path("docs/srs/numerical-laboratory-method.md")
QUALITY = "QFSU QPEFF QCOMP QUSA QREL QSEC QMNT QFLX QSAF".split()

#: The approved ceilings (owner decision of 2026-10-20). Quality rows count inside the
#: instantiation budget: inst_L1 + quality_L1 <= inst_L1 ceiling, and the same for L2.
CEILINGS = {
    "method_L0": 12,
    "method_L1": 60,
    "inst_L1": 120,
    "inst_L2": 600,
    "total_L0_L2": 800,
    "max_children": 9,
    "mean_children": 5,
}
#: At most this many quality L1 rows per ISO/IEC 25010:2023 characteristic.
QUALITY_L1_PER_CHARACTERISTIC = 5


def method_rows(root: Path) -> list[dict[str, str]]:
    """Parse the method table by its header names; an older header still reads."""
    path = root / METHOD_PAGE
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    columns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            columns = []
            continue
        cells = [
            c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]
        if cells and cells[0].lower() == "uid":
            columns = [c.lower() for c in cells]
            continue
        if not columns or not re.fullmatch(r"NL-[A-Z]+(?:-\d+)?", cells[0]):
            continue
        record = dict(zip(columns, cells, strict=False))
        uid = cells[0]
        level = record.get("level") or ("L0" if uid.count("-") == 1 else "L1")
        parent = "-" if level == "L0" else uid.rsplit("-", 1)[0]
        verification = record.get("verification") or ("analysis" if level == "L0" else "")
        rows.append(
            {
                "uid": uid,
                "layer": "method",
                "level": level,
                "parent": parent,
                "statement": record.get("statement", ""),
                "verification": verification.lower(),
            }
        )
    return rows


def git_head(root: Path) -> str:
    """Return the HEAD commit, or an empty string outside a git checkout."""
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def measure(root: Path = REPO, release: bool = False) -> dict[str, object]:
    """Return the full measurement as a JSON-ready dict; ``ok`` carries the verdict.

    A pending L3 row whose test does not exist yet, and a pending L2 with neither a test nor an
    L3 row, are work the release still owes: they are listed under ``owed_l3`` and ``owed_l2``
    and do not fail the check, except with ``release=True`` (the tag), where nothing is owed.
    """
    live = read_requirements(root, live_only=True)
    l3 = read_l3(root)
    rows = method_rows(root)
    for row in live:
        if row["level"] == "L3":
            continue
        quality = row["hid"].split("-")[0] in QUALITY
        rows.append(
            {
                "uid": row["uid"],
                "layer": "quality" if quality else "instantiation",
                "level": row["level"],
                "parent": row["parent"],
                "statement": row["statement"],
                "verification": row["verification_method"],
            }
        )
    count = Counter((r["layer"], r["level"]) for r in rows)
    counts = {
        "method_L0": count["method", "L0"],
        "method_L1": count["method", "L1"],
        "inst_L1": count["instantiation", "L1"],
        "inst_L2": count["instantiation", "L2"],
        "quality_L1": count["quality", "L1"],
        "quality_L2": count["quality", "L2"],
        "total_L0_L2": len(rows),
    }
    l1 = [r["uid"] for r in rows if r["layer"] != "method" and r["level"] == "L1"]
    children: dict[str, int] = {uid: 0 for uid in l1}
    for r in rows:
        if r["layer"] != "method" and r["level"] == "L2" and r["parent"] in children:
            children[r["parent"]] += 1
    l2_total = counts["inst_L2"] + counts["quality_L2"]
    mean = round(l2_total / len(l1), 3) if l1 else 0.0
    over = sorted((u for u, n in children.items() if n > CEILINGS["max_children"]), key=_key)
    per_characteristic = Counter(
        r["hid"].split("-")[0]
        for r in live
        if r["level"] == "L1" and r["hid"].split("-")[0] in QUALITY
    )
    l2_rows = {r["uid"]: r for r in live if r["level"] == "L2"}
    l3_parents = {r["parent"] for r in l3}
    missing = [r for r in l3 if not anchor_names_a_test(root, r["test"])]
    owed_l3 = sorted((r["uid"] for r in missing if r.get("status") == "pending"), key=_key)
    unresolved = sorted((r["uid"] for r in missing if r.get("status") != "pending"), key=_key)
    orphans = sorted((r["uid"] for r in l3 if r["parent"] not in l2_rows), key=_key)
    bare = [(u, r) for u, r in l2_rows.items() if r["test"] in ("", "-") and u not in l3_parents]
    owed_l2 = sorted((u for u, r in bare if r["status"] != "implemented"), key=_key)
    uncovered = sorted((u for u, r in bare if r["status"] == "implemented"), key=_key)
    if release:
        unresolved, uncovered = (
            sorted(unresolved + owed_l3, key=_key),
            sorted(uncovered + owed_l2, key=_key),
        )
    owed = sorted((u for u, r in l2_rows.items() if r["status"] != "implemented"), key=_key)
    identities = Counter([r["uid"] for r in live] + [r["uid"] for r in l3])
    identities.update(roadmap_uids(root))
    duplicates = sorted((u for u, n in identities.items() if n > 1), key=_key)
    checks = {
        "method_L0": counts["method_L0"] <= CEILINGS["method_L0"],
        "method_L1": counts["method_L1"] <= CEILINGS["method_L1"],
        "inst_L1": counts["inst_L1"] + counts["quality_L1"] <= CEILINGS["inst_L1"],
        "inst_L2": l2_total <= CEILINGS["inst_L2"],
        "total_L0_L2": counts["total_L0_L2"] <= CEILINGS["total_L0_L2"],
        "max_children": not over,
        "mean_children": mean <= CEILINGS["mean_children"],
        "quality_per_characteristic": all(
            n <= QUALITY_L1_PER_CHARACTERISTIC for n in per_characteristic.values()
        ),
        "l3_resolved": not unresolved and not orphans,
        "l2_covered": not uncovered,
        "unique_uids": not duplicates,
    }
    return {
        "head": git_head(root),
        "rows": rows,
        "counts": counts,
        "ceilings": dict(CEILINGS),
        "children": {"max": max(children.values(), default=0), "mean": mean, "over_9": over},
        "quality_L1_per_characteristic": dict(sorted(per_characteristic.items())),
        "l3": {
            "file": L3_REQUIREMENTS.as_posix(),
            "rows": len(l3),
            "unresolved": unresolved,
            "orphans": orphans,
            "l2_uncovered": uncovered,
            "owed_l3": owed_l3,
            "owed_l2": owed_l2,
        },
        "release": release,
        "l2_not_implemented": owed,
        "duplicates": duplicates,
        "checks": checks,
        "ok": all(checks.values()),
    }


def _key(uid: str) -> tuple[str, int]:
    prefix, _, number = uid.partition("-")
    digits = re.match(r"\d+", number)
    return (prefix, int(digits.group()) if digits else 0)


def report(result: dict[str, object]) -> str:
    """Render the measurement as a short table against the targets."""
    counts = result["counts"]
    children = result["children"]
    l3 = result["l3"]
    assert isinstance(counts, dict) and isinstance(children, dict) and isinstance(l3, dict)
    lines = [
        f"{'measure':<28}{'value':>8}{'target':>10}",
        f"{'method L0':<28}{counts['method_L0']:>8}{'<= 12':>10}",
        f"{'method central L1':<28}{counts['method_L1']:>8}{'<= 60':>10}",
        f"{'instantiation L1 (+quality)':<28}"
        f"{counts['inst_L1'] + counts['quality_L1']:>8}{'<= 120':>10}",
        f"{'instantiation L2 (+quality)':<28}"
        f"{counts['inst_L2'] + counts['quality_L2']:>8}{'<= 600':>10}",
        f"{'total L0 to L2':<28}{counts['total_L0_L2']:>8}{'<= 800':>10}",
        f"{'max L2 per L1':<28}{children['max']:>8}{'<= 9':>10}",
        f"{'mean L2 per L1':<28}{children['mean']:>8}{'<= 5':>10}",
        f"{'L3 rows':<28}{l3['rows']:>8}{'-':>10}",
        f"{'L3 unresolved or orphan':<28}{len(l3['unresolved']) + len(l3['orphans']):>8}{'0':>10}",
        f"{'L2 without L3 or test':<28}{len(l3['l2_uncovered']):>8}{'0':>10}",
        f"{'L2 not yet implemented':<28}{len(result['l2_not_implemented']):>8}{'0 at tag':>10}",
        f"{'owed rows without a test':<28}"
        f"{len(l3['owed_l3']) + len(l3['owed_l2']):>8}{'0 at tag':>10}",
        "",
        "failed: " + (", ".join(k for k, v in result["checks"].items() if not v) or "none"),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the measurement; exit 0 only when every ceiling and traceability check holds."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    parser.add_argument("--root", type=Path, default=REPO, help=argparse.SUPPRESS)
    parser.add_argument(
        "--release", action="store_true", help="the tag check: pending rows without a test fail"
    )
    args = parser.parse_args(argv)
    result = measure(args.root, release=args.release)
    print(json.dumps(result, indent=1) if args.json else report(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
