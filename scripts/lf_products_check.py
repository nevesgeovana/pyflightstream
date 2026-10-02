#!/usr/bin/env python3
"""Post recorded offline campaigns here and count the CR bytes of what the package wrote.

    python scripts/lf_products_check.py --out <release folder>/lf_products.txt
    python scripts/lf_products_check.py --out F --campaign unsteady_rotor --campaign additional

The receipt of the LF arm of 0.34.0 (NFR-32, marker P0340-LF-PRODUCTS), read by the
goal checker as ``lf_products.txt``. Each recorded offline campaign of the products
snapshot (``tests/tier1_offline/test_products_snapshot.py``) is built and posted on
THIS platform with the text mode the platform has: on Windows the post is not forced
to anything, so a writer that bypasses the LF route leaves CRLF here and is counted;
on any other platform the post is run with text mode forced to write CRLF as Windows
does (``--force-crlf`` forces it on Windows too). Then every file the package wrote
(:func:`tests.tier1_offline.test_p0340_lf_products.package_written`: the products
under ``post/``, the emitted solver scripts, the run records and logs) is read as
bytes and counted. The guard that walks ``src/`` is run with its ten planted
bypasses. The lines written::

    SHA: <git rev-parse HEAD>
    PLATFORM: win32
    CAMPAIGN: <n> recorded offline campaigns: <names>
    FILES_CHECKED: <files the package wrote, over every campaign>
    SCRIPTS_CHECKED: <of them, emitted solver scripts>
    CR_FILES: <files holding a CR byte>
    GUARD_CONTROL: caught <k> of <k>
    TREE_CLEAN: yes
    LF PRODUCTS: PASS

The last line is PASS only when ``CR_FILES`` is 0, files and scripts were checked, the
guard caught every planted bypass, the guard finds no bypass in ``src/`` and the tree
of ``src/``, ``tests/`` and ``scripts/`` is clean at that SHA (a receipt of a dirty tree
names a SHA it does not describe; ``--allow-dirty`` is for a rehearsal and writes
``TREE_CLEAN: no``, which is never PASS). The exit status is 0 on PASS.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True, env=os.environ.copy()
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Write the receipt and return 0 when it ends in PASS."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="the receipt to write")
    parser.add_argument(
        "--campaign", action="append", help="a campaign of the snapshot (default: all)"
    )
    parser.add_argument(
        "--force-crlf", action="store_true", help="force CRLF text mode on Windows too"
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", help="rehearse on a tree with changes"
    )
    args = parser.parse_args(argv)
    sys.path[:0] = [str(REPO / "src"), str(REPO)]
    from tests.tier1_offline import test_p0340_lf_products as guard
    from tests.tier1_offline import test_products_snapshot as snapshot

    from pyflightstream import _textio

    names = args.campaign or sorted(snapshot.CAMPAIGNS)
    unknown = [n for n in names if n not in snapshot.CAMPAIGNS]
    if unknown:
        parser.error(f"not a campaign of the snapshot: {unknown}")
    # Windows writes CRLF in text mode by itself: leave it there, so the count is its own.
    snapshot.FORCE_CRLF_IN_POST = args.force_crlf or sys.platform != "win32"
    checked = scripts = crs = 0
    for name in names:
        with tempfile.TemporaryDirectory(prefix="pfs-lf-") as scratch:
            with pytest.MonkeyPatch.context() as patch:
                snapshot.pin_environment(patch)
                root = snapshot.CAMPAIGNS[name](Path(scratch) / "w", patch)
                for path in guard.package_written(root):
                    checked += 1
                    scripts += "scripts" in path.parts and path.suffix == ".txt"
                    crs += _textio.file_cr_count(path) > 0
    caught, planted = guard.guard_control()
    sources = {
        p.relative_to(REPO / "src").as_posix(): p.read_text(encoding="utf-8")
        for p in sorted((REPO / "src" / "pyflightstream").rglob("*.py"))
    }
    bypasses = guard.text_write_bypasses(sources)
    clean = not _git("status", "--porcelain", "--", "src", "tests", "scripts")
    ok = crs == 0 and checked > 0 and scripts > 0 and caught == planted and not bypasses and clean
    if not clean and not args.allow_dirty:
        print(
            "the tree has changes: the receipt would name a SHA it does not describe",
            file=sys.stderr,
        )
    lines = [
        f"SHA: {_git('rev-parse', 'HEAD')}",
        f"PLATFORM: {sys.platform}",
        f"CAMPAIGN: {len(names)} recorded offline campaigns: {', '.join(names)}",
        f"FILES_CHECKED: {checked}",
        f"SCRIPTS_CHECKED: {scripts}",
        f"CR_FILES: {crs}",
        f"GUARD_CONTROL: caught {caught} of {planted}",
        f"GUARD_BYPASSES_IN_SRC: {len(bypasses)}",
        f"TREE_CLEAN: {'yes' if clean else 'no'}",
        f"LF PRODUCTS: {'PASS' if ok else 'FAIL'}",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_lines(args.out, lines)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
