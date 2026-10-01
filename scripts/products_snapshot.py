#!/usr/bin/env python3
"""Compare the post stage's products with the committed byte snapshot (GOAL-038 arm A4).

    python scripts/products_snapshot.py --out <release folder>/wp5_snapshot.json
    python scripts/products_snapshot.py --write --out <release folder>/wp5_snapshot.json

The snapshot and its campaigns are defined in
``tests/tier1_offline/test_products_snapshot.py`` (P0330-PRODUCTS-SNAPSHOT);
this script runs the same regeneration and comparison outside pytest and
writes the receipt the goal arm reads::

    {"release_sha": <git rev-parse HEAD>, "files_checked": n,
     "differing": [], "control": "caught k of k", ...}

``differing`` names every file that is missing, added or changed against the
stored digests and texts; ``control`` counts the planted differences (a
changed byte, a removed and an added product per campaign) the comparison
caught. The receipt also records whether ``src/`` and ``tests/`` were clean
at that SHA, because a comparison of a dirty tree is not one of the SHA.

``--write`` stores the snapshot anew from the current tree: done once before
the first move of WP5, and afterwards only when a release changes a product
on purpose and names the change.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        # Git reads nothing of the environment this script depends on.
        env=os.environ.copy(),
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Write the receipt (or store the snapshot) and return 0 when nothing differs."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="the receipt to write")
    parser.add_argument("--write", action="store_true", help="store the snapshot anew")
    args = parser.parse_args(argv)
    sys.path[:0] = [str(REPO / "src"), str(REPO)]
    from tests.tier1_offline.test_products_snapshot import snapshot_receipt

    receipt = snapshot_receipt(write=args.write)
    receipt = {
        "release_sha": _git("rev-parse", "HEAD"),
        "tree_clean": not _git("status", "--porcelain", "--", "src", "tests"),
        **receipt,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "differing"}))
    print(f"differing: {len(receipt['differing'])}")
    for line in receipt["differing"][:20]:
        print(f"  {line}")
    control = str(receipt["control"]).split()
    ok = not receipt["differing"] and control[1] == control[3] and receipt["files_checked"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
