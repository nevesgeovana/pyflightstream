"""Regenerate the per-build workflow renders under ``tests/goldens/workflows/``.

WHY THESE EXIST, stated here because the reason is a measurement rather
than a convention. v0.8.1 claimed that a matrix naming none of its three
new keys renders byte for byte as it always did, and cited the 23 files
in ``tests/goldens/`` and the 18 in ``tests/fixtures/`` as the evidence.
Not one of those 41 files is produced by a workflow builder, so they
could not have changed whatever the builders did. A QA pass measured the
hole by inserting one extra ``script.emit`` into ``_build_steady``; it
changed every steady render on every build and the whole tier 1 suite
stayed green.

These goldens are the population the claim was always about: every
workflow crossed with every build that workflow covers, rendered from
cases declaring NONE of ``GEOMETRY``, ``SYMMETRY`` or
``PERIODIC_COPIES``, which is what every matrix written before v0.8.1
says.

A build a workflow COVERS but cannot BUILD is pinned as its REFUSAL text
rather than as a script. That is deliberate and it is also the dangerous
part, so it is bounded: only the pairs in
``tests.test_workflows.EXPECTED_REFUSALS`` may be written as refusals,
and any other failure aborts this script instead of being frozen as
evidence. Without that bound, a defect that made a builder raise
everywhere would be laundered into "expected" by one run of this
generator, and the suite would agree.

The case definitions are NOT written here. They are ``GOLDEN_CASES`` in
``tests/test_workflows.py``, which is the single home the guard reads
them from too, so a generator and a test cannot drift into disagreeing
about what "the historical case" is.

MEASURED AGAINST THE RELEASED v0.8.0, once, on 2026-08-21: the same
case shapes rendered against a worktree at the ``v0.8.0`` tag produce
these bytes exactly. That is what licenses the retrospective half of the
claim ("renders what it rendered BEFORE 0.8.1"); the goldens themselves
can only pin the forward half. The measurement is committed beside them
as ``RECEIPT-v0.8.0.md``, which carries the method in full: note that
the v0.8.0 tree has neither ``GOLDEN_CASES`` nor ``render_or_refusal``,
both being new here, so a redo restates the case shapes in its render
script rather than importing them.

Usage
-----
    python scripts/gen_workflow_goldens.py
    python scripts/gen_workflow_goldens.py --check

``--check`` writes nothing and exits non-zero if any golden is missing
or stale, which is what CI would run if it ran this at all; the tier 1
guard in ``tests/test_workflows.py`` is the real check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
GOLDENS = TESTS / "goldens" / "workflows"

# The case table and the expected-refusal set live in the test module,
# which is the single home; see the module docstring.
sys.path.insert(0, str(TESTS))

from test_workflows import (  # noqa: E402
    EXPECTED_REFUSALS,
    GOLDEN_RENDERS,
    golden_name,
    render_or_refusal,
)


def build() -> dict[Path, bytes]:
    """Render every pair and return the bytes each golden should hold.

    Raises
    ------
    SystemExit
        When a pair outside :data:`EXPECTED_REFUSALS` refuses. That is
        the guard against laundering a regression into committed
        evidence: a builder that starts raising everywhere must fail
        here rather than produce a tree full of refusal goldens that the
        suite then accepts.
    """
    rendered: dict[Path, bytes] = {}
    for name, label, build_id in GOLDEN_RENDERS:
        text = render_or_refusal(name, label, build_id)
        if text.startswith("REFUSED") and (name, build_id) not in EXPECTED_REFUSALS:
            raise SystemExit(
                f"{name} refused on {build_id}, which is not a declared refusal.\n"
                f"{text}\n"
                "Refusing to write that as a golden: an unexpected refusal is a defect "
                "in the builder, and pinning it here would record the defect as the "
                "expected behaviour. Fix the builder, or add the pair to "
                "EXPECTED_REFUSALS in tests/test_workflows.py and say why."
            )
        rendered[GOLDENS / golden_name(name, label, build_id)] = text.encode("utf-8")
    return rendered


def main(argv: list[str] | None = None) -> int:
    """Write every render that differs from its committed golden."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit non-zero if any golden is missing or stale",
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
            print(f"not produced by any pair: {target.relative_to(REPO).as_posix()}")
        print(f"{len(stale)} stale, {len(orphans)} orphaned")
        return 1 if stale or orphans else 0

    for target in stale:
        # Written as BYTES, so no newline translation is possible at any
        # point. The goldens tree is pinned to LF by .gitattributes and a
        # tier 1 guard asserts no golden carries a carriage return.
        target.write_bytes(rendered[target])
        print(f"wrote {target.relative_to(REPO).as_posix()}")
    for target in orphans:
        print(f"orphaned, not produced by any pair: {target.relative_to(REPO).as_posix()}")
    print(f"{len(stale)} file(s) changed, {len(orphans)} orphaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
