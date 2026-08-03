#!/usr/bin/env python3
"""Generate the machine-readable index of the requirement set.

Pipeline role: evidence generator. The SRS pages under ``docs/srs`` are
the single source; this script renders them into one JSON document that
an external dashboard can consume without parsing Markdown, plus the
traceability counts that say how much of the set a test reaches.

Run it with no argument to write ``reports/requirements-index.json``, or
with ``--check`` to fail when the committed file is stale. The Tier 1
suite runs the second form, so the index cannot drift from the SRS the
way a hand-maintained list does: the dashboard it feeds carried 32
hand-assembled entries against a set that had grown well past that
before this generator existed.

Field names are fixed by the consumer. This list is the emitted set,
and it is checked against the generator's output by a Tier 1 test
rather than maintained by hand: it described three fields while six
were being written, and a zero traceability count while eight
requirements carried falsifying markers (REV010-017).

``id``
    The requirement identifier, for example ``FR-37`` or ``NFR-13``.
``text``
    The statement, as one paragraph of plain text.
``priority``
    ``"M"`` for mandatory, ``"D"`` for deferred. Deferred means the
    requirement is agreed and its implementation waits on something
    outside this repository, which for this project is almost always
    licensed-solver evidence.
``status``
    The badge the SRS page carries: ``implemented``, ``pending`` or
    ``deferred``. What ``priority`` cannot say, because a pending
    requirement is still mandatory.
``verification``
    How the requirement is to be shown satisfied.
``evidence``
    What currently shows it, when anything does.

The top level carries ``source``, ``generated_by``, ``traceability``
and ``requirements``. ``traceability`` counts how many requirement ids
are MENTIONED anywhere under ``tests/``, which is an upper bound rather
than a measure; the marker ratchet is a separate and smaller number,
held in ``tests/test_traceability.py``. See :func:`traceability` for
why the looser count is reported at all.

What the index does NOT carry, and why. Only ``requirement`` boxes are
published. Architecture decisions (AD-xx) and non-requirements
(NREQ-xx) live in the same pages and are excluded, because a field
named ``priority`` has no value that means "this is a rule rather than
an obligation" or "this is a refusal": the first version of this
generator published NREQ-01, "No graphical interface is planned or
accepted", as a mandatory requirement. Requirements badged
``deprecated`` are excluded for the same reason. A requirement badged
``pending`` IS published as mandatory, because it is owed; what a
consumer cannot learn from this artifact is whether it has shipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRS = REPO / "docs" / "srs"
OUT = REPO / "reports" / "requirements-index.json"
TESTS = REPO / "tests"

#: Requirement box headers look like: !!! requirement "FR-37 Title <span ...
BOX = re.compile(
    r"^!!! (?P<kind>requirement|decision|nonrequirement) "
    r'"(?P<id>[A-Za-z]+-[0-9]+[a-z]?) (?P<title>[^"]*)"[^\n]*\n',
    re.MULTILINE,
)

#: The status badge, read out of the header line rather than the body.
STATUS = re.compile(r"srs-(?P<status>\w+)")


def _plain(text: str) -> str:
    """Strip the inline Markdown a JSON consumer has no use for."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links keep their words
    text = text.replace("**", "").replace("``", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def _statement(body: str) -> str:
    """Return the requirement's statement: its first real paragraph."""
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    for para in paragraphs:
        stripped = para.strip()
        if stripped.startswith("*Origin") or (
            stripped.startswith("*") and stripped.endswith("*") and "**" not in stripped
        ):
            continue  # the italic origin and evidence tag
        return _plain(" ".join(line.strip() for line in stripped.splitlines()))
    return ""


def _evidence(body: str) -> str:
    """Return the requirement's origin and evidence tag, as written.

    The italic first paragraph of a box carries both. Empty where a box
    has none, which is itself a fact worth publishing: a requirement
    with no evidence line is one nobody can check.
    """
    for para in re.split(r"\n\s*\n", body):
        stripped = para.strip()
        if stripped.startswith("*Origin"):
            return _plain(" ".join(line.strip() for line in stripped.splitlines()))
    return ""


def _verification(body: str, status: str) -> str:
    """Classify HOW a requirement is verified, from its evidence line.

    Four values, and the distinction NFR-13 needs is between the first
    two. ``test`` means something fails when the requirement stops
    holding. ``review`` means a human checks it and nothing fails. A
    requirement badged implemented and verified by review is not wrong,
    but a reader is entitled to know which it is rather than to assume.
    """
    if status in {"pending", "draft"}:
        return "none"
    evidence = _evidence(body).lower()
    if "tests/" in evidence or "test_" in evidence:
        return "test"
    if "milestone" in evidence or "report" in evidence:
        return "evidence"
    return "review"


def collect() -> list[dict[str, str]]:
    """Parse the live requirement set out of the SRS.

    Three kinds of box are parsed and only one is published. A
    ``decision`` (AD-xx) is an architecture rule, a ``nonrequirement``
    (NREQ-xx) states what the package will NOT do, and publishing
    either into a field named ``priority`` with the value ``M`` for
    mandatory inverts what it says: the first release of this index did
    exactly that, and shipped "No graphical interface is planned or
    accepted" to a dashboard as a mandatory requirement. A requirement
    badged ``deprecated`` is dropped for the same reason, since it is
    superseded rather than owed.
    """
    entries: list[dict[str, str]] = []
    for page in sorted(SRS.glob("*.md")):
        text = page.read_text(encoding="utf-8")
        matches = list(BOX.finditer(text))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.end() : end]
            badge = STATUS.search(m.group("title"))
            status = badge.group("status") if badge else "implemented"
            if m.group("kind") != "requirement" or status == "deprecated":
                continue
            entries.append(
                {
                    "id": m.group("id"),
                    "text": _statement(body),
                    "priority": "D" if status == "deferred" else "M",
                    # NFR-13 asks the index to carry status, evidence and a
                    # verification method, and the first edition published id,
                    # text and priority alone: a consumer could not tell an
                    # implemented requirement from a pending one, nor find what
                    # backs it (review finding PYFS-020).
                    "status": status,
                    "evidence": _evidence(body),
                    "verification": _verification(body, status),
                }
            )
    entries.sort(key=_sort_key)
    return entries


def _sort_key(entry: dict[str, str]) -> tuple[str, int, str]:
    prefix, _, rest = entry["id"].partition("-")
    number = re.match(r"(\d+)([a-z]?)", rest)
    return (prefix, int(number.group(1)), number.group(2))


def traceability(ids: list[str]) -> dict[str, object]:
    """Count how many requirement ids are mentioned under ``tests/``.

    This is a GENEROUS measurement and the payload says so in its own
    ``method`` field, because the number travels to a dashboard where
    the docstring does not. It counts a bare mention anywhere in a test
    module, which includes a mention in a module docstring or a
    comment; a mention is not a falsifying test. Under the marker
    convention NFR-13 asks for, eight requirements carry a falsifying
    marker today (the ratchet is `MARKED_FLOOR` in
    tests/test_traceability.py), and this number counts far more than
    that because it counts mentions. It read "today's honest count
    would be zero" until 2026-08-03, which was true when the markers
    did not exist and stayed in place after they landed.

    So the number is an upper bound on traceability, not a measure of
    it. Reporting it flatters the gap, which is the direction that
    matters to know: the real gap is at least this wide. ``conftest.py``
    is excluded because it holds fixtures rather than tests, and two of
    the ids counted by the first version of this function came from
    there.
    """
    sources = [p for p in TESTS.rglob("*.py") if p.name != "conftest.py"]
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in sources)
    cited = {rid for rid in ids if re.search(rf"\b{re.escape(rid)}\b", corpus)}
    return {
        "cited_by_a_test": len(cited),
        "total": len(ids),
        "method": (
            "upper bound: an id mentioned anywhere in tests/**/*.py excluding "
            "conftest.py, which is not the marked falsifying test NFR-13 asks for"
        ),
    }


def build() -> dict[str, object]:
    """Assemble the published payload: the set plus its traceability."""
    entries = collect()
    return {
        "source": "docs/srs",
        "generated_by": "scripts/gen_requirements_index.py",
        "traceability": traceability([e["id"] for e in entries]),
        "requirements": entries,
    }


def main() -> int:
    """Write the index, or check the committed one against the SRS."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed index differs from the SRS",
    )
    args = parser.parse_args()
    data = build()
    payload = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != payload:
            print(
                "reports/requirements-index.json is stale. Regenerate it with:\n"
                "    python scripts/gen_requirements_index.py",
                file=sys.stderr,
            )
            return 1
        print(f"index current: {len(data['requirements'])} requirements")
        return 0
    OUT.write_text(payload, encoding="utf-8", newline="\n")
    trace = data["traceability"]
    print(
        f"wrote {OUT.relative_to(REPO)}: {len(data['requirements'])} requirements, "
        f"{trace['cited_by_a_test']}/{trace['total']} cited by a test"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
