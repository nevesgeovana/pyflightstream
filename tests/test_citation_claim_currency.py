"""Tier 1: no shipped page promises a manual page on every database entry.

Since 2026-08-06 an entry rests on ONE of two citations: the manual page
that documents the command, or a committed probe report measuring that
the solver accepts one no edition documents. Twelve shipped sentences
said otherwise, and they were found in two passes rather than one, nine
in the first review round and three more in the second, one of those
inside the module that owns the field.

That is the argument for a guard rather than a third sweep. The class is
"a page promises a manual citation for EVERY entry", and it recurs
because the sentence is natural to write and nothing reads it.

The pattern is pinned against history rather than against the current
tree, following ``tests/test_guide_currency.py``: a pattern asserted only
over today's files is satisfied by today's files.
``SENTENCES_THAT_WENT_STALE`` holds the real ones, verbatim, and the
pattern must match every one.

What this does NOT cover, stated so the wording above is not read as
more: it reads the shipped prose surfaces listed in ``PAGES``, and one
real sentence shape escapes it, recorded below as
``SENTENCE_THE_PATTERN_MISSES``. The residual is real and the rule for a
person is unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The shipped prose surfaces that describe the database to a reader.
PAGES = (
    "README.md",
    "docs/index.md",
    "docs/mesh-inputs.md",
    "docs/srs/data-model.md",
    "docs/srs/philosophy.md",
    "docs/srs/functional-requirements.md",
    "src/pyflightstream/commands/__init__.py",
    "src/pyflightstream/reference.py",
)

#: The claim shape: a citation OF THE MANUAL offered as an entry's
#: evidence. Deliberately broad, because the sentences below spell it
#: several ways and a pattern tuned to one of them catches one of them.
CLAIM = re.compile(
    r"manual (?:page )?citations?|page citations?|cites its page",
    re.IGNORECASE,
)

#: What makes such a sentence a claim ABOUT ENTRIES rather than a true
#: statement about the field. Without it the pattern flags seven
#: accurate sentences: the refusal message that carries a citation, the
#: regex comment describing the citation shape, and the ``default_ref``
#: docstring, all of which are manual-only facts and correctly so.
ENTRY_SCOPE = re.compile(r"\bentry\b|\bentries\b|\bevery\b|\beach\b", re.IGNORECASE)

#: What makes such a claim HONEST: naming the other kind of evidence.
#: This is the second discriminator and it took a wrong pattern to find
#: it. Distinguishing by the claim's own wording failed in both
#: directions at once, missing six of the ten real sentences while
#: flagging the accurate replacements, because a stale sentence and an
#: honest one say the same thing about the manual. They differ in
#: whether they go on to mention the alternative.
MENTIONS_THE_ALTERNATIVE = re.compile(r"probe", re.IGNORECASE)

#: A sentence boundary in flattened prose: a period, semicolon or
#: table-cell bar, then a capital or the end. The qualifying words are
#: looked for inside the claim's OWN sentence and no further.
#:
#: A character window was tried first and was measured useless: with 160
#: characters either side, all three mutations restoring a real stale
#: sentence stayed green, because the paragraph around each of them goes
#: on to mention probe evidence for a different reason. A claim is
#: honest when IT names the alternative, not when something near it does.
SENTENCE_SPLIT = re.compile(r"(?<=[.;|])\s+(?=[A-Z|-])|(?<=\|)\s*")

#: The sentences that really shipped and were really removed, verbatim,
#: across the two review rounds of 2026-08-06. A pattern that misses any
#: of them is not guarding the class that occurred: each one could be
#: restored today without turning anything red.
SENTENCES_THAT_WENT_STALE = (
    "Every database entry carries a manual page citation, and its status per",
    "- Command database with per-version evidence and a manual citation on\n  every entry",
    "| manual_ref | The page citation backing the entry |",
    "- Every command database entry carries a manual page citation",
    "Each entry records name, layout grammar, typed arguments, the version span "
    "in which it exists, per-version argument differences, and a manual page citation.",
    "A per-version command database, with a manual page citation for every entry",
    "documents (each entry carries its page citation), so a workflow step",
    "phase, and a manual page citation (``manual_ref``) per entry.",
    "commands. Every entry paraphrases the FlightStream manual and cites its page (manual_ref)",
)

#: The one real sentence this pattern does NOT catch, kept rather than
#: dropped so the gap is a recorded fact instead of a silence. It claims
#: manual citations for the database as a whole and never says entry, so
#: catching it means adding "database" to ENTRY_SCOPE, which immediately
#: flags the true sentence describing what shape a citation takes. A
#: narrower pattern with a stated gap beats a wider one with an
#: allowlist.
SENTENCE_THE_PATTERN_MISSES = (
    "The command database: what exists in which FlightStream version, with manual page citations"
)


def _prose_of(path: Path) -> str:
    """Return the human prose of a file, and for Python only the prose.

    Sentence splitting a whole .py file runs statements together into
    pseudo-sentences hundreds of characters long, and those pick up an
    "entry" from one line and a "citation" from another that were never
    in one sentence. Four false positives came from exactly that. The
    prose of a Python file is its docstrings and its comments, so those
    are what this reads.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return text
    import ast

    pieces = [
        line.lstrip().lstrip("#").strip()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    ]
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node)
            if doc:
                pieces.append(doc)
    return "\n\n".join(pieces)


def _unqualified_claims(text: str) -> list[str]:
    """Return each entry-scoped manual-citation claim that omits the alternative."""
    found = []
    for sentence in SENTENCE_SPLIT.split(" ".join(text.split())):
        match = CLAIM.search(sentence)
        if match is None:
            continue
        if not ENTRY_SCOPE.search(sentence):
            continue
        if MENTIONS_THE_ALTERNATIVE.search(sentence):
            continue
        found.append(match.group(0))
    return found


@pytest.mark.parametrize("sentence", SENTENCES_THAT_WENT_STALE)
def test_the_pattern_matches_what_actually_went_stale(sentence):
    """Guard the guard, against history rather than against itself."""
    assert _unqualified_claims(sentence), (
        f"the pattern does not match {sentence!r}, a sentence this repository "
        "shipped and removed for promising a manual page on every entry. It "
        "could be restored today without turning anything red"
    )


def test_the_pattern_does_not_match_the_honest_replacements():
    """The control: saying the true thing must not trip the guard.

    Without this the test above passes just as well under a pattern that
    flagged every sentence containing the word manual, which would make
    the accurate wording unwritable and the guard something to route
    around rather than satisfy.
    """
    honest = (
        "Every database entry carries exactly one piece of evidence: the manual "
        "page that documents the command, or a committed probe report.",
        "each entry carries one citation or the other",
        "a manual page or probe-report citation on every entry",
        "| manual_ref | The manual page citation backing the entry; exclusive with probe_ref |",
    )
    tripped = [text for text in honest if _unqualified_claims(text)]
    assert not tripped, (
        "the pattern flags wording that is TRUE, so it would push an author "
        "away from the accurate sentence: " + "; ".join(tripped)
    )


def test_the_known_gap_stays_a_known_gap():
    """A recorded miss, so widening the pattern updates the record.

    If someone makes the pattern catch this sentence, this test fails and
    they delete it, which is the point: the gap does not get to become
    folklore.
    """
    assert not _unqualified_claims(SENTENCE_THE_PATTERN_MISSES), (
        "the pattern now catches the sentence recorded as its gap; delete "
        "SENTENCE_THE_PATTERN_MISSES and this test, and move the sentence into "
        "SENTENCES_THAT_WENT_STALE"
    )


def test_no_shipped_page_promises_a_manual_citation_on_every_entry():
    offenders = []
    for relative in PAGES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is listed here and does not exist"
        for claim in _unqualified_claims(_prose_of(path)):
            offenders.append(f"{relative}: {claim}")
    assert not offenders, (
        "these pages promise a manual page citation on every database entry, "
        "which stopped being true when probe_ref landed: an entry rests on a "
        "manual page OR a committed probe report. Say which, or say that both "
        "are possible: " + "; ".join(offenders)
    )
