"""PFS-2010.01.05: no string a user reads names a released version as a future fix.

THE DEFECT. A refusal shipped in 0.18.0 told its user to submit one point at a
time "until 0.18.0 gives a submitted point its own working directory". The
user was running 0.18.0; the reasonable reading is that their installation is
wrong. A sentence that dates its own removal goes false the day that release
ships, and nothing re-reads it on that day.

THE SAME SCAN FOUND TWO MORE, and that is why it is a guard rather than a
reword: a deprecation's extra text said a form "is exempt until 0.17.0, when"
the key becomes required, and a refusal said "0.15.0 has not shipped". All
three were live in 0.18.0.

WHAT IT READS. Every string literal under ``src/``, f-strings included,
DOCSTRINGS EXCLUDED, and the exclusion is a measurement rather than a
preference. Run over docstrings too, the rule flagged nine sentences on
2026-09-14 and all nine were narrated history ("the folder was called
``raw/`` until 0.16.0, FR-84, and ..."): this package's docstrings record
what changed and when, densely, and a phrase rule cannot tell reported past
speech from a promise. Over the strings a user is shown in a refusal, a
warning or a deprecation, it flagged exactly the three defects.

What it flags is a PRESENT OR FUTURE claim about a version that has already
been released: ``until X`` followed by a present-tense clause, ``X has not
shipped``, ``lands in X``. A past-tense sentence naming the same version is
history and is left alone; the fixtures below are real sentences of both kinds,
copied from the tree, so the rule is scored against what it will meet.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pyflightstream"

_VERSION = r"v?(\d+\.\d+\.\d+)"
_PRESENT = (
    "gives|lands|ships|adds|makes|removes|brings|fixes|builds|arrives|replaces|"
    "lets|allows|supports|turns|becomes|changes|moves|is released|is out"
)
#: Each pattern captures the version in group 1.
FUTURE_CLAIMS = (
    re.compile(rf"\buntil\s+{_VERSION}(?=,\s*when\b|\s+(?:{_PRESENT})\b)", re.I),
    re.compile(
        rf"\b{_VERSION}\s+(?:has not|hasn't|is not yet|is yet to be|will be)"
        r"\s+(?:shipped|released|out)\b",
        re.I,
    ),
    re.compile(rf"\b(?:lands|arrives|ships|comes|is fixed|will be \w+)\s+in\s+{_VERSION}", re.I),
)


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def last_released() -> tuple[int, ...]:
    """The newest version this tree may call released.

    A development tree (``0.18.1.dev0``) has not released its own base, so a
    sentence about 0.18.1 may still be a promise there; one about 0.18.0 may
    not. A release tree has released exactly what it declares.
    """
    declared = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    match = re.match(r"(\d+)\.(\d+)\.(\d+)(.*)", declared)
    assert match, declared
    base = tuple(int(match.group(i)) for i in (1, 2, 3))
    if match.group(4):
        major, minor, patch = base
        if patch:
            return (major, minor, patch - 1)
        return (major, minor - 1, 999) if minor else (major - 1, 999, 999)
    return base


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _strings(tree: ast.AST):
    skip = _docstrings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            skip.update(id(part) for part in node.values)
            yield (
                node.lineno,
                "".join(
                    part.value if isinstance(part, ast.Constant) else "{}" for part in node.values
                ),
            )
        elif (
            isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
        ):
            yield node.lineno, node.value


def future_claims(text: str, released: tuple[int, ...]) -> list[str]:
    """Every claim in ``text`` that a released version is still to come."""
    flat = re.sub(r"\s+", " ", text)
    found = []
    for pattern in FUTURE_CLAIMS:
        for match in pattern.finditer(flat):
            if _key(match.group(1)) <= released:
                found.append(flat[max(0, match.start() - 40) : match.end() + 30])
    return found


def scan(root: Path, released: tuple[int, ...]) -> list[str]:
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, text in _strings(tree):
            offenders += [
                f"{path.relative_to(root).as_posix()}:{lineno}: ...{claim}..."
                for claim in future_claims(text, released)
            ]
    return offenders


#: Real sentences, as they stood in v0.18.0, that the guard must flag.
SHIPPED_DEFECTS = (
    "Submit one point of a row at a time until 0.18.0 gives a submitted point its own "
    "working directory, or collect the queued point first.",
    "The flat form has nothing to choose between and is exempt until 0.17.0, when which "
    "rotor bounds the time step becomes a decision every row states.",
    "the promise that the flat form was exempt until 0.17.0 was written in 0.15.0 and "
    "0.15.0 has not shipped, so no workspace was ever told it held.",
)

#: Real sentences from the tree naming released versions IN THE PAST, which
#: the guard must leave alone. A rule that flagged these would be deleted by
#: the first person it annoyed.
HISTORY = (
    "Until v0.8.0 it also accepted the campaign root as a path.",
    "which the reference artifact carried until 0.11.0 and no builder read.",
    "A point submitted before 0.18.0 carries no such list and is completed by hand,",
    "was removed in v0.16.0; write {} instead. It was renamed in v0.14.0, warned through v0.15.0",
    "no plan for this matrix, and since v0.17.0 a run needs one.",
)


@pytest.mark.parametrize("sentence", SHIPPED_DEFECTS)
def test_goal021_future_version_the_guard_flags_each_sentence_that_shipped(sentence):
    assert future_claims(sentence, (0, 18, 0)), (
        f"the guard does not flag a sentence that shipped in 0.18.0 promising a released "
        f"version as future: {sentence!r}"
    )


@pytest.mark.parametrize("sentence", HISTORY)
def test_goal021_future_version_the_guard_leaves_history_alone(sentence):
    assert future_claims(sentence, (0, 18, 0)) == [], sentence


def test_goal021_future_version_an_unreleased_version_may_still_be_promised():
    """The control: the same sentence about a version NOT yet out is legitimate."""
    assert future_claims(SHIPPED_DEFECTS[0].replace("0.18.0", "0.19.0"), (0, 18, 0)) == []


def test_goal021_future_version_no_string_in_the_package_promises_a_released_version():
    released = last_released()
    offenders = scan(SRC, released)
    assert offenders == [], (
        f"these strings name a version at or below {'.'.join(map(str, released))} as still "
        "to come. State the limitation without dating its removal:\n  " + "\n  ".join(offenders)
    )


def test_goal021_future_version_the_scan_reads_the_package():
    """The scan over the tree is not vacuous: it reads files and strings."""
    count = sum(
        1
        for path in SRC.rglob("*.py")
        for _ in _strings(ast.parse(path.read_text(encoding="utf-8")))
    )
    assert count > 500, f"the scan read only {count} string literal(s) under {SRC}"
