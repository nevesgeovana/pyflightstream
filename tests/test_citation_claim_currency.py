"""Tier 1: no shipped page promises a manual page on every database entry.

Since 2026-08-06 an entry rests on ONE of two citations: the manual page
that documents the command, or a committed probe report measuring that
the solver accepts one no edition documents. Sentences saying otherwise
were swept by hand three times, nine sites then three then four, and the
sweep kept missing a surface, which is why this file exists.

REBUILT after round three, which proved the first version did not hold
its class. Four defects, two of them demonstrated by reverting a real
sentence and watching the suite stay green:

* it read a Python file's docstrings and comments, and every shipped
  sentence of ``reference.py`` is a STRING LITERAL. Restoring the
  generated preamble that commit 0b49f80 had just repaired left the
  suite green, so two of the four repaired homes were unguarded while
  ``PAGES`` said they were covered.
* it flattened a markdown file before splitting, and a bullet with no
  terminal period runs into the next one. Putting a stale bullet back
  into ``philosophy.md`` was exempted by the FOLLOWING bullet's mention
  of a probe report. That is the paragraph-scope leak the previous
  version's own docstring claimed to have cured.
* the exemption matched the bare token ``probe``, which also appears in
  "when probed on a licensed machine", a phrase about status promotion
  and not about the kind of citation. The package's own top docstring
  was exempted by it.
* ``PAGES`` was hand-enumerated and omitted the user guide, the package
  docstring and CONTRIBUTING, all of which carried a live instance.

The fixture is pinned against history and every entry is verified
against the commit that still held it, by
``test_every_stale_sentence_really_shipped``. One sentence was found
CLIPPED at the point where the real one went on to name the
alternative, so the pattern was being certified against a truncation
rather than against what shipped.

NINE sentences are pinned, out of the sixteen corrected. The rest are
covered only by the sweep over ``PAGES``, which is a weaker claim, and
saying so here is the point: a reader must not take the fixture for the
complete history. The surface list is the part that actually failed
twice, so ``test_pages_covers_the_tracked_prose_that_describes_the_database``
derives its candidates from the tracked tree rather than trusting the
list, and everything deliberately outside it is named with a reason.

What this still does NOT cover: a page outside ``PAGES``, and prose in a
file type it does not read. ``test_pages_covers_the_tracked_prose``
holds the first of those to the tracked doc set.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where an untracked prose file is admitted into the population below.
#: Everything `PAGES` and `DELIBERATELY_UNLISTED` can rule on lives under
#: one of these.
SOURCE_ROOTS = ("src", "docs", "scripts", "examples", "tools")

_PROSE_SUFFIXES = (".md", ".tex", ".py")


def prose_population(root: Path) -> list[str]:
    """Return the prose files this guard rules on, tracked or about to be.

    TWO CALLS, NOT ONE, and the split is the whole content of this
    function.

    Everything TRACKED is in, wherever it sits. That is the population a
    committed tree has, and it is what CI sees.

    Everything UNTRACKED is in only under ``SOURCE_ROOTS``. Both halves
    of that are corrections of real failures. Asking for tracked files
    alone meant a file this guard would refuse passed until the moment it
    was committed, and the commit was what changed the answer: on
    2026-08-17 a new module was written, the suite was run in three
    chunks and reported green, the commit was made, and the guard went
    red on the file the commit had just added. Asking for every untracked
    file traded that for the opposite asymmetry, and the review pass
    measured it with a scratch note at the repository root: tier 1 goes
    RED on a developer's machine and stays green in CI, which is the
    worse direction, because it teaches that a red suite can be ignored.

    A git pathspec is not a shell glob, incidentally, and the first
    attempt at this scoping assumed it was: ``*`` matches ``/`` in a
    pathspec, so ``*.md`` matches every markdown file at every depth and
    a pattern list cannot narrow ``--others`` at all.
    """
    # `env=` EXPLICITLY, and identical to the inherited default: git
    # needs the ambient environment to find its own configuration, and
    # the rule is that the environment is passed rather than assumed.
    # The ratchet in `test_repository_guards.py` counts the sites that
    # do not.
    environment = os.environ.copy()

    # A FAILED CALL REFUSES, and neither call checked its status until
    # 2026-08-18. If the `--others` call failed for any reason while
    # `--cached` succeeded, this returned the tracked-only population
    # in silence, which is exactly the regression the test below
    # exists to prevent, undetected. Absence read as permission is the
    # shape this repository has an incident about.
    def ls_files(*argv: str) -> list[str]:
        done = subprocess.run(
            ["git", "ls-files", *argv],
            capture_output=True,
            text=True,
            cwd=root,
            env=environment,
        )
        assert done.returncode == 0, (
            f"git ls-files {' '.join(argv)} failed with {done.returncode}, so this "
            f"guard would have walked a population missing whatever that call "
            f"would have listed: {done.stderr.strip()}"
        )
        return done.stdout.split()

    seen = ls_files("--cached", "*.md", "*.tex", "*.py")
    untracked = ls_files("--others", "--exclude-standard", "--", *SOURCE_ROOTS)
    seen += [name for name in untracked if name.endswith(_PROSE_SUFFIXES)]
    return sorted(set(seen))


#: The shipped prose surfaces that describe the database to a reader.
PAGES = (
    "README.md",
    "CONTRIBUTING.md",
    "docs/index.md",
    "docs/mesh-inputs.md",
    "docs/srs/data-model.md",
    "docs/srs/philosophy.md",
    "docs/srs/roadmap.md",
    "docs/srs/scope.md",
    "docs/srs/functional-requirements.md",
    "docs/srs/introduction.md",
    "docs/tutorial-replay.md",
    "guide/pyflightstream_user_guide.tex",
    "src/pyflightstream/__init__.py",
    "src/pyflightstream/commands/__init__.py",
    "src/pyflightstream/reference.py",
    # Joined 2026-08-10 with the `citations` subcommand, whose whole
    # subject is the citation fields and whose module docstring
    # describes them. The guard's own walk is what put both here.
    "src/pyflightstream/utils/cli.py",
    # TWO MAINTENANCE PROCEDURES WERE WATCHED HERE and left the tree on
    # 2026-08-23 with the process tooling that held them: the one a
    # maintainer followed when registering a build, whose silence let ten
    # stale citations ship, and the one stating the evidence rule for a
    # work item. Recorded rather than silently dropped, because this list
    # is the part of this file that has failed twice by omission. The
    # rule itself is not lost: `CONTRIBUTING.md` and the SRS both state
    # it and both are watched below, and a maintenance page that returns
    # will be found by the walk rather than by anyone remembering this.
)

#: The claim shape: a citation OF THE MANUAL offered as an entry's
#: evidence. Deliberately broad, because the sentences below spell it
#: several ways and a pattern tuned to one of them catches one of them.
CLAIM = re.compile(
    r"manual (?:page )?citations?|page citations?|cites its page",
    re.IGNORECASE,
)

#: What makes such a sentence a claim ABOUT ENTRIES rather than a true
#: statement about the field. Without it the pattern flags accurate
#: sentences: the refusal message that carries a citation, the regex
#: comment describing the citation shape, and the ``default_ref``
#: docstring, all of which are manual-only facts and correctly so.
#:
#: "every" and "each" were in this set and are not: they matched a true
#: sentence about "every solver flag with its provenance: a documented
#: default with its MANUAL CITATION", which has no probe alternative
#: because a default is a manual fact. Every sentence in the fixture
#: below contains the word "entry", so narrowing costs nothing and the
#: false positive goes away exactly.
ENTRY_SCOPE = re.compile(r"\bentry\b|\bentries\b", re.IGNORECASE)

#: What makes such a claim HONEST: offering the other kind of citation
#: as an ALTERNATIVE, which in practice means a disjunction.
#:
#: Two looser rules were measured and both failed on the same ambiguity.
#: The bare token "probe" matches "when probed on a licensed machine",
#: which is about how a STATUS is promoted, and it exempted the
#: package's own top docstring. Requiring the words "probe report" is no
#: better: the original README sentence promised a manual citation on
#: every entry and went on to say a status "can only be promoted by
#: citing a committed probe report", so the true half of the sentence
#: exempted the false half.
#:
#: The honest sentences all say OR. That is the difference between
#: naming the alternative and merely mentioning the artifact.
#: ``probe_ref`` and "probe-cited" name the citation KIND and are safe
#: to exempt anywhere in the unit, unlike the bare verb "probed". Not
#: one of the pinned sentences contains either, which the fixture test
#: proves rather than this comment asserting it.
MENTIONS_THE_ALTERNATIVE = re.compile(
    r"\bor\s+(?:a\s+)?(?:committed\s+)?(?:probe[- ]?report|probe_ref|report\b)"
    r"|citation or the other"
    r"|probe_ref"
    r"|probe-cited"
    r"|probe[- ]report citation",
    re.IGNORECASE,
)

#: Prose is split into claim-sized units by BLOCK and then by terminal
#: punctuation. A block is a paragraph, a list item or a table row.
#:
#: Neither simpler rule works, and both were measured. Flattening the
#: whole file first merges a markdown bullet into its neighbours, because
#: a bullet carries no terminal period, and a stale bullet put back into
#: philosophy.md was then exempted by the NEXT bullet's mention of a
#: probe report. Splitting per line instead breaks every wrapped
#: sentence in two, so the claim lands in one unit and the word "entry"
#: in the next, and four real sentences stopped matching.
#: Only a full stop ends a unit. Semicolons and colons were tried and
#: removed: a table cell reading "the citation backing the entry;
#: exclusive with probe_ref" is ONE statement, and splitting it put the
#: claim in one unit and its qualifier in the next, so the guard flagged
#: the accurate wording. Blocks already separate rows and bullets.
SENTENCE_SPLIT = re.compile(r"(?<=\.)\s+")

#: A line that STARTS a new block rather than continuing one: a markdown
#: or LaTeX list item, a table row, a heading, or an indented literal.
BLOCK_START = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s|\\item\b|\||#{1,6}\s|!!!)")

#: The sentences that really shipped and were really removed. Verified
#: verbatim against the commits that held them by the test below, so a
#: paraphrase typed from memory cannot certify coverage the pattern does
#: not have. Each is stored WHOLE: one was previously clipped at the
#: comma where the real sentence went on to name the alternative, which
#: made the pattern look effective against text that never shipped.
SENTENCES_THAT_WENT_STALE = (
    (
        "README.md",
        "Every database entry carries a manual page citation, and its status per\n"
        "version (documented, verified, broken) can only be promoted by citing a\n"
        "committed probe report from a licensed machine.",
    ),
    (
        "README.md",
        "- Command database with per-version evidence and a manual citation on\n  every entry",
    ),
    ("docs/srs/data-model.md", "| manual_ref | The page citation backing the entry |"),
    (
        "docs/srs/philosophy.md",
        "- Every command database entry carries a manual page citation\n"
        "  (`manual_ref`). Manual facts appear only as paraphrases with the\n"
        "  page number; manual text is never reproduced.",
    ),
    (
        "docs/srs/functional-requirements.md",
        "    script commands. Each entry records name, layout grammar, typed\n"
        "    arguments, the version span in which it exists, per-version\n"
        "    argument differences, and a manual page citation.",
    ),
    (
        "docs/index.md",
        "database, with a manual page citation for every entry and empirical probe\n"
        "evidence for every verified status, backs a script builder that refuses to",
    ),
    (
        "docs/mesh-inputs.md",
        "documents (each entry carries its page citation), so a workflow step",
    ),
    (
        "src/pyflightstream/commands/__init__.py",
        "phase, and a manual page citation (``manual_ref``) per entry.",
    ),
    (
        "src/pyflightstream/reference.py",
        'f"{entry_count} commands. Every entry paraphrases the FlightStream manual "\n'
        '        "and cites its page (manual_ref); statuses follow the evidence rules of "',
    ),
)

#: Commits that still held the sentences above, newest last.
COMMITS_BEFORE_THE_SWEEPS = ("da6c1dd", "f4148a5", "bff8678", "02ad14a")


def _prose_of(path: Path) -> str:
    """Return the human prose of a file.

    For Python that is comments, docstrings AND string literals, and the
    third of those is the correction round three forced: every sentence
    ``reference.py`` renders onto a page is a literal assembled in a
    function, so a walk of docstrings alone read 22 percent of that file
    and none of the part a reader sees.
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return text
    pieces = [
        line.lstrip().lstrip("#").strip()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    ]
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            pieces.append(node.value)
    return "\n".join(pieces)


def _units(text: str) -> list[str]:
    """Split prose into claim-sized units: blocks, then sentences."""
    blocks: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            blocks.append([])
        elif not blocks or BLOCK_START.match(line):
            blocks.append([line.strip()])
        else:
            blocks[-1].append(line.strip())
    units = []
    for block in blocks:
        joined = " ".join(block).strip()
        if joined:
            units.extend(part for part in SENTENCE_SPLIT.split(joined) if part)
    return units


def _unqualified_claims(text: str) -> list[str]:
    """Return each entry-scoped manual-citation claim that omits the alternative."""
    found = []
    for unit in _units(text):
        match = CLAIM.search(unit)
        if match is None:
            continue
        if not ENTRY_SCOPE.search(unit):
            continue
        if MENTIONS_THE_ALTERNATIVE.search(unit):
            continue
        found.append(match.group(0))
    return found


@pytest.mark.parametrize(
    ("origin", "sentence"), SENTENCES_THAT_WENT_STALE, ids=lambda v: Path(str(v)).name
)
def test_the_pattern_matches_what_actually_went_stale(origin, sentence):
    """Guard the guard, against history rather than against itself."""
    assert _unqualified_claims(sentence), (
        f"the pattern does not match the sentence removed from {origin}, which this "
        "repository shipped. It could be restored today without turning anything red"
    )


@pytest.mark.parametrize(
    ("origin", "sentence"), SENTENCES_THAT_WENT_STALE, ids=lambda v: Path(str(v)).name
)
def test_every_stale_sentence_really_shipped(origin, sentence):
    """The fixture is taken from git, never from memory.

    A history fixture typed from recollection has certified coverage
    this repository did not have before, and the first version of this
    file did it again: one entry was clipped at the comma where the real
    sentence went on to name the alternative, so the pattern was proven
    against a truncation that never shipped and the whole sentence would
    have been exempt.
    """
    needle = " ".join(sentence.split())
    for commit in COMMITS_BEFORE_THE_SWEEPS:
        blob = subprocess.run(
            ["git", "show", f"{commit}:{origin}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if blob.returncode == 0 and needle in " ".join(blob.stdout.split()):
            return
    pytest.fail(
        f"this sentence is pinned as removed from {origin} and appears in none of "
        f"{list(COMMITS_BEFORE_THE_SWEEPS)}. Take the fixture out of git: a "
        "paraphrase proves whatever it happens to trigger"
    )


def test_the_pattern_does_not_match_the_honest_replacements():
    """The control: saying the true thing must not trip the guard.

    Without this the tests above pass just as well under a pattern that
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


def test_a_status_promotion_phrase_is_not_an_evidence_alternative():
    """ "Probed on a licensed machine" says nothing about what an entry CITES.

    The exemption matched the bare token ``probe`` until round three,
    and this sentence, the package's own top docstring, was exempted by
    it while making exactly the claim the guard forbids.
    """
    assert _unqualified_claims(
        "each entry carries a manual page citation and, when probed on a licensed "
        "machine, empirical evidence of its status"
    ), "a status-promotion phrase must not exempt a citation claim"


def test_pages_covers_the_tracked_prose_that_describes_the_database():
    """The surface list is the guard's weakest part, so it is measured.

    Three shipped surfaces were missing from it after round two and each
    held a live instance. This does not derive PAGES, which would sweep
    hundreds of files; it asserts that any tracked prose file mentioning
    the database's citation fields is either listed or deliberately not.
    """
    # TRACKED **AND ABOUT TO BE**, which is the correction of 2026-08-17.
    # `git ls-files` alone means a file this guard would refuse passes
    # until the moment it is committed, and the commit is what changes the
    # answer. That is not hypothetical: `src/pyflightstream/utils/database.py`
    # was written, the suite was run in three chunks and reported green,
    # the commit was made, and the guard went red on the file the commit
    # had just added. The green was measured on a population that did not
    # include it.
    #
    tracked = prose_population(REPO_ROOT)
    assert tracked, "git ls-files returned nothing; this guard is walking nothing"

    describes = re.compile(r"manual_ref|manual page citation|manual citation")
    candidates = {
        name
        for name in tracked
        if not name.startswith(("tests/", "reports/", "_private/"))
        and describes.search((REPO_ROOT / name).read_text(encoding="utf-8", errors="ignore"))
    }
    missing = sorted(candidates - set(PAGES) - set(DELIBERATELY_UNLISTED))
    assert not missing, (
        "these tracked files describe the database's citation fields and are neither "
        "in PAGES nor recorded as deliberately unlisted, which is how three live "
        "instances survived round two: " + "; ".join(missing)
    )


#: Files that mention the citation fields and are deliberately outside
#: PAGES, each for a stated reason rather than by omission. This set is
#: the guard's honest residual: everything in it can carry a stale claim
#: without turning anything red.
DELIBERATELY_UNLISTED = {
    # HISTORY: these record what the pages used to say, so a stale
    # sentence quoted inside them is the subject rather than a claim.
    "CHANGELOG.md",
    "docs/srs/index.md",
    # The field named AS A FIELD, in error messages, schema prose and
    # drafting output, which says nothing about what every entry carries.
    "src/pyflightstream/utils/manual.py",
    # Its sibling, and for the identical reason: `database.py` names the
    # field AS A FIELD, in a refusal explaining that a manifest row with
    # no citation id would write "None" as a row's provenance. It makes
    # no claim about what every entry carries.
    "src/pyflightstream/utils/database.py",
    "src/pyflightstream/script/__init__.py",
    "src/pyflightstream/qa/compat.py",
    "scripts/gen_docs_pages.py",
    "examples/steady_polar.py",
    # A converter, not a page. It names manual_ref only to explain why a
    # page citation against a compiled help archive would be a number
    # nobody wrote, which is the reason the script exists; it makes no
    # claim about what an entry carries.
    "scripts/chm_to_pdf.py",
    # CONTRIBUTING.md's invariant 3 states the evidence rule and is the
    # author's charter. Its wording is hers to change, not this guard's
    # to force, and it is raised to her rather than edited here.
    "CONTRIBUTING.md",
}


def test_no_shipped_page_promises_a_manual_citation_on_every_entry():
    offenders = []
    for relative in PAGES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is listed here and does not exist"
        prose = _prose_of(path)
        assert prose.strip(), (
            f"{relative} yielded no prose at all, so it is listed and unread, which "
            "is the shape that let reference.py go unguarded"
        )
        for claim in _unqualified_claims(prose):
            offenders.append(f"{relative}: {claim}")
    assert not offenders, (
        "these pages promise a manual page citation on every database entry, "
        "which stopped being true when probe_ref landed: an entry rests on a "
        "manual page OR a committed probe report. Say which, or say that both "
        "are possible: " + "; ".join(offenders)
    )


def test_the_population_walk_sees_a_new_source_file_before_it_is_committed(tmp_path):
    """The property the walk exists for, driven against a throwaway tree.

    This guard's population changed twice and neither change was
    asserted by anything: removing the untracked half again left the
    whole suite green, so the repair could be undone by a formatter, a
    merge, or a reviewer who thought it looked odd.

    Three cases, in a real git repository built here:

    * a TRACKED file under `src/` is in, which is the ordinary case;
    * an UNTRACKED file under `src/` is in, which is the failure of
      2026-08-17, where a new module was invisible until the commit that
      added it turned the suite red;
    * an UNTRACKED file at the ROOT is out, which is the failure the
      first repair introduced, where a developer's scratch note made
      tier 1 red locally and green in CI.
    """
    import subprocess as sp

    def git(*argv):
        sp.run(
            ["git", *argv],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            env=os.environ.copy(),
        )

    git("init", "-q")
    git("config", "user.email", "guard@example.invalid")
    git("config", "user.name", "guard")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "committed.py").write_text("# manual_ref\n", encoding="utf-8")
    git("add", "src/committed.py")
    git("commit", "-qm", "one")

    (tmp_path / "src" / "brand_new.py").write_text("# manual_ref\n", encoding="utf-8")
    (tmp_path / "scratch_note.md").write_text("# manual_ref\n", encoding="utf-8")

    population = prose_population(tmp_path)

    assert "src/committed.py" in population
    assert "src/brand_new.py" in population, (
        "an untracked file under a source root is invisible, so this guard answers "
        "differently before and after the commit that adds it, which is exactly how a "
        "tier-1 green was reported on a population the commit then changed"
    )
    assert "scratch_note.md" not in population, (
        "an untracked file outside the source roots is in the population, so a scratch "
        "note in a developer's tree can turn tier 1 red locally while CI stays green"
    )
