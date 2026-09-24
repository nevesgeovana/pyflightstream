"""Regenerate the extraction scripts under ``tests/tier1_offline/goldens/additional/``.

WHAT THESE PIN (G12 of 0.27.0). The additional post reopens a point's saved
simulation and runs one pproc's extractions over it, with no solve. What it
emits is a promise made to a licensed seat: ``OPEN`` and the blank line after
the path, the new distributions in the frames the run created, the update and
the computation of the sectional loads, the exports, the close, and nothing
else. One golden per kind of additional pproc: sections only; sections and the
surface in VTK and CSV; and an unsteady rotor's last instant.

ONE BUILD, 26.124, because RPT-062 measured what a reopened simulation gives
back there and on no other build, and the builder refuses the rest.

The kinds are NOT written here. They are ``ADDITIONAL_KINDS`` in
``tests/tier1_offline/test_additional_post.py``, which is the single home the
guard reads them from too, so the generator and the test cannot drift into
disagreeing about what a kind is. The goldens are NOT under
``goldens/workflows/``, whose population is exactly the run types' renders.

Usage
-----
    python scripts/gen_additional_goldens.py
    python scripts/gen_additional_goldens.py --check

``--check`` writes nothing and exits non-zero if any golden is missing, stale
or orphaned; the tier 1 guard in the test module is the real check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The test module imports its siblings as `tests.tier1_offline.*`, so the
# repository root is what goes on the path.
sys.path.insert(0, str(REPO))

from tests.tier1_offline.test_additional_post import (  # noqa: E402
    ADDITIONAL_KINDS,
    GOLDENS,
    golden_of,
    render_additional,
)


def build() -> dict[Path, bytes]:
    """Render every kind and return the bytes each golden should hold."""
    return {golden_of(kind): render_additional(kind).encode("utf-8") for kind in ADDITIONAL_KINDS}


def main(argv: list[str] | None = None) -> int:
    """Write every render that differs from its committed golden."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit non-zero if any golden is missing, stale or orphaned",
    )
    args = parser.parse_args(argv)

    GOLDENS.mkdir(parents=True, exist_ok=True)
    rendered = build()
    stale = [
        target
        for target, new in sorted(rendered.items())
        if not target.exists() or target.read_bytes() != new
    ]
    orphans = sorted(set(GOLDENS.glob("*.txt")) - set(rendered))

    if args.check:
        for target in stale:
            print(f"stale or missing: {target.relative_to(REPO).as_posix()}")
        for target in orphans:
            print(f"not produced by any kind: {target.relative_to(REPO).as_posix()}")
        print(f"{len(stale)} stale, {len(orphans)} orphaned")
        return 1 if stale or orphans else 0

    for target in stale:
        # BYTES, so no newline translation happens anywhere: the goldens tree
        # is LF only, which a tier 1 guard asserts.
        target.write_bytes(rendered[target])
        print(f"wrote {target.relative_to(REPO).as_posix()}")
    for target in orphans:
        print(f"orphaned, not produced by any kind: {target.relative_to(REPO).as_posix()}")
    print(f"{len(stale)} file(s) changed, {len(orphans)} orphaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
