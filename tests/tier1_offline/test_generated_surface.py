"""GOAL-020 item 6, PFS-2032.06: one home for the surface and the count, read not transcribed.

THE DEFECT THIS FILE EXISTS ON, measured rather than argued. The subcommands
of the console scripts stood in the README table, the documentation index, the
architecture page and the guide; the tier-3 matrix count stood in the README,
the index twice, the tiers page, the workspace page, the guide and the change
log. Two of them said six where seven existed.

IT PROVED ITSELF AGAIN WHILE 0.18.0 WAS BEING BUILT. Adding ONE subcommand,
`collect`, broke three separate transcriptions in one commit: the command-line
options registry, an assertion in the run-CLI tests whose own comment says
"add a subcommand is exactly the change that quietly" breaks it, and the
recorded module total. And this file's first run found the matrix count stated
as seven on five live pages while the folder held eight.

THE NODE OFFERED TWO SHAPES and this is the second: a generator, or a tier-1
test that reads the REAL surface and the REAL count and holds every page to
them. The test is chosen because a generator writes pages a human then edits
around, while a test refuses the drift wherever the sentence lives, including
in prose nobody would have templated.

WHAT IT DOES NOT COVER, said rather than left: the CHANGELOG, whose entries
are history. A released entry that said seven was true when it was written,
and rewriting it would be editing a record rather than correcting a claim.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TIER3 = REPO / "tests" / "tier3_licensed"

#: The pages a reader takes as CURRENT. The change log is deliberately absent:
#: its entries are history and are corrected beside themselves, never edited.
LIVE_PAGES = (
    *sorted((REPO / "docs").glob("*.md")),
    REPO / "README.md",
    *sorted((REPO / "guide").glob("*.tex")),
)

#: How a count gets written in prose here, in both spellings a page uses.
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _tier3_matrix_count() -> int:
    """The number of tier-3 matrices, read off the FOLDER."""
    return len(list(TIER3.glob("matriz*.fs")))


#: A line that is TALKING ABOUT the tier-3 matrix set at all. Without this the
#: rule fires on every sentence that says "one matrix" about a user's own
#: workspace, which is not a claim about this repository.
_ABOUT_TIER3 = re.compile(r"tier-3|tier 3|tier3_licensed", re.I)

#: How many lines count as "close together" for a page to be ENUMERATING a
#: console script's surface rather than using it. Forty is a table, a bullet
#: list or one section; it is not a whole readme.
_ENUMERATION_WINDOW = 40

#: A count of matrices. The lookbehind is not decoration: the first writing
#: matched "3 matrices" out of the phrase "tier 3 matrices", where the 3 is
#: the TIER and not the count, and reported six pages as wrong that were
#: right. A guard that fires on the wrong thing is worse than none, because
#: it teaches the next reader to widen it rather than to read it.
#: The trailing lookahead is the second false positive this pattern produced
#: and is written here rather than fixed silently: "write one matrix ROW" is a
#: sentence about one ROW of a matrix, not a claim that the repository holds
#: one matrix, and the guard reported a correct tutorial as wrong.
_COUNT_OF_MATRICES = re.compile(
    r"(?<!tier )(?<!tier-)\b(?:("
    + "|".join(NUMBER_WORDS)
    + r")|(\d+))\s+matri(?:ces|x)\b(?!\s+(?:row|cell|column|file|stem))",
    re.I,
)


def _matrix_claims(text: str) -> list[tuple[str, int]]:
    """Every line of ``text`` that states how many tier-3 matrices there are.

    LINE BY LINE, and only where the line is about the tier-3 set. A count of
    matrices in a sentence about somebody's own campaign is not a claim about
    this repository and is not this guard's business.
    """
    found: list[tuple[str, int]] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        # A THREE-LINE WINDOW, because the anchor and the count are often one
        # sentence broken over two lines: the documentation index says "the
        # tier-3 workspace, which IS a campaign workspace: seven matrices over
        # one synthetic library", and a line-only rule read the second half
        # alone and let it pass.
        window = "\n".join(lines[max(0, index - 2) : index + 3])
        if not _ABOUT_TIER3.search(window):
            continue
        for match in _COUNT_OF_MATRICES.finditer(line):
            word, digits = match.group(1), match.group(2)
            value = NUMBER_WORDS[word.lower()] if word else int(digits)
            found.append((match.group(0), value))
    return found


def test_goal020_board_items_the_repository_holds_the_matrices_the_pages_claim():
    """Every live page that states a tier-3 matrix count states the real one.

    THE COUNT IS READ OFF THE FOLDER, which is the whole point: a page and a
    folder cannot disagree if the page is checked against the folder rather
    than against another page.
    """
    actual = _tier3_matrix_count()
    assert actual, f"no tier-3 matrix found under {TIER3}"
    wrong: list[str] = []
    for page in LIVE_PAGES:
        text = page.read_text(encoding="utf-8", errors="replace")
        for sentence, claimed in _matrix_claims(text):
            if claimed != actual:
                wrong.append(f"{page.relative_to(REPO).as_posix()}: {sentence!r} (actual {actual})")
    assert not wrong, (
        "these live pages state a tier-3 matrix count the folder does not hold:\n  "
        + "\n  ".join(wrong)
        + "\nThe folder is the authority. Correct the page, and if a count has to be "
        "written down in prose at all, it is written down HERE being checked."
    )


def _subcommands(module_name: str) -> set[str]:
    """The subcommands one console script actually declares."""
    import importlib

    module = importlib.import_module(module_name)
    parser = module._build_parser()  # noqa: SLF001 -- the surface under test
    for action in parser._actions:  # noqa: SLF001
        if getattr(action, "choices", None) and hasattr(action.choices, "keys"):
            return set(action.choices)
    raise AssertionError(f"{module_name} declares no subparsers")


@pytest.mark.parametrize(
    ("script", "module_name"),
    [("pyfs-matrix", "pyflightstream.run.cli"), ("pyfs-workspace", "pyflightstream.workspace.cli")],
)
def test_goal020_board_items_a_page_listing_the_surface_lists_all_of_it(script, module_name):
    """A page that lists a console script's subcommands lists EVERY one of them.

    THE RULE IS DELIBERATELY NOT "every page names every subcommand", which
    would refuse a page that mentions one in passing, and it is not three
    either. A tutorial walks a reader through plan, run and post and is a
    CORRECT page that happens to name three; demanding it also list `upgrade`
    would be demanding it teach something it is not teaching.

    FIVE is where a page has clearly set out to ENUMERATE the surface rather
    than to use it, and where a missing one is a wrong page rather than a
    narrow one. The threshold carries its reason here because the first
    writing used three and would have refused the getting-started page for
    being a tutorial.
    """
    declared = _subcommands(module_name)
    if len(declared) < 5:
        # SKIPPED AND SAID, never silently passed. A script with three
        # subcommands cannot trip a five-subcommand rule, so a green result
        # here would be a rule that never ran reading as a rule that held.
        pytest.skip(
            f"{script} declares {len(declared)} subcommands ({', '.join(sorted(declared))}), "
            "fewer than the five this rule needs to distinguish an enumeration from a use"
        )
    short: list[str] = []
    for page in LIVE_PAGES:
        lines = page.read_text(encoding="utf-8", errors="replace").splitlines()
        # A WINDOW AND NOT THE WHOLE PAGE. A five-hundred-line readme that
        # uses plan, run, post, upgrade and inventory in five different
        # paragraphs is a page that USES the surface, not one that enumerates
        # it, and the first writing of this rule refused it for that. An
        # enumeration is a BLOCK: five of them close together.
        for start in range(0, max(1, len(lines) - _ENUMERATION_WINDOW + 1)):
            window = "\n".join(lines[start : start + _ENUMERATION_WINDOW])
            named = {name for name in declared if re.search(rf"{script}\s+{name}\b", window)}
            if len(named) >= 5 and named != declared:
                missing = ", ".join(sorted(declared - named))
                short.append(
                    f"{page.relative_to(REPO).as_posix()} near line {start + 1}: missing {missing}"
                )
                break
    assert not short, (
        f"these pages enumerate {script} and leave a subcommand out:\n  "
        + "\n  ".join(short)
        + f"\nThe surface is {', '.join(sorted(declared))}, read from the parser itself."
    )
