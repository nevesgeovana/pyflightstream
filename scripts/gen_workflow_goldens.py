"""Regenerate the per-build workflow renders under ``tests/goldens/workflows/``.

WHY THESE EXIST, stated here because the reason is a measurement rather
than a convention. v0.8.1 claimed that a matrix naming none of its three
new keys renders byte for byte as it always did, and cited the 23 files
in ``tests/goldens/`` and the 18 in ``tests/fixtures/`` as the evidence.
Not one of those 41 files is produced by a workflow builder: they are
hand-written ``script.emit`` sequences and solver-output parser fixtures,
so they could not have changed whatever the builders did. A QA pass
measured the hole by inserting one extra ``script.emit`` into
``_build_steady``; it changed every steady render on every build and the
whole tier 1 suite stayed green.

These goldens are the population the claim was always about: every
workflow crossed with every build that workflow covers, rendered from a
case declaring NONE of ``GEOMETRY``, ``SYMMETRY`` or ``PERIODIC_COPIES``,
which is what every matrix written before v0.8.1 says.

A build a workflow covers but cannot build is goldened too, as its
REFUSAL text. That is not a curiosity: ``covered_builds`` reports
FlightStream 25.000 as covered by ``steady`` because the build's database
carries every command the workflow always emits, while the initialization
helper refuses that edition's grammar outright. Pinning the refusal is
what keeps the over-approximation visible rather than letting it change
silently.

The case definitions are NOT written here. They are ``steady_case`` and
``rotor_case`` in ``tests/test_workflows.py``, which is the single home
the guard reads them from too, so a generator and a test cannot drift
into disagreeing about what "the historical case" is.

Usage
-----
    python scripts/gen_workflow_goldens.py

Writes only where the bytes differ, and prints one line per file it
touched, so a run that changes nothing says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"
GOLDENS = TESTS / "goldens" / "workflows"

# The case builders live in the test module, which is the single home;
# see the module docstring. Importing it runs module-level code only.
sys.path.insert(0, str(TESTS))

from pyflightstream.cases.workflows import (  # noqa: E402
    WORKFLOWS,
    covered_builds,
)


def render_or_refusal(name: str, build: str) -> str:
    """Return one workflow's render on one build, or its refusal text.

    A build inside ``covered_builds`` that the builder cannot express
    raises instead of rendering, and the raised text is what gets pinned.
    The exception TYPE is recorded beside the message, because a refusal
    changing class is a public change even when its wording does not
    move.
    """
    import test_workflows as helpers  # noqa: PLC0415

    case = helpers.steady_case() if name == "steady" else helpers.rotor_case()
    try:
        return helpers.rendered(case, build)
    except Exception as error:  # noqa: BLE001 - the refusal IS the golden
        return f"REFUSED {type(error).__name__}\n{error}\n"


def main() -> int:
    """Write every render that differs from its committed golden."""
    GOLDENS.mkdir(parents=True, exist_ok=True)
    written = 0
    for name in sorted(WORKFLOWS):
        for build in covered_builds(WORKFLOWS[name]):
            text = render_or_refusal(name, build)
            target = GOLDENS / f"{name}@{build}.txt"
            # newline="\n" and never the platform default: the goldens
            # tree carries a tier 1 guard that no golden holds a carriage
            # return, and this repository is Windows-primary.
            new = text.encode("utf-8")
            if target.exists() and target.read_bytes() == new:
                continue
            target.write_bytes(new)
            written += 1
            print(f"wrote {target.relative_to(REPO).as_posix()}")
    print(f"{written} file(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
