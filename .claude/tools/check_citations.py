# ITACA / pyflightstream shared process kit
# kit-version: 0.2.17
# artifact: check_citations.py
# body-sha256: e295e4781f0f073caa90ea4920b09b597042824ccb534008c85550910672d395
# canonical-source: BUILT for the kit (0.2.16, HUB-12) from ITC-20260802-0340, cite an id with its title so a wrong citation is visible. Lane ITA-11 cited OQ-53 in two places for a question OQ-53 does not ask, and three reviewer lenses caught it independently. The obvious guard, "every cited id must exist", was TESTED AGAINST THAT CASE and would have PASSED, because OQ-53 exists: the error was a wrong-but-existing citation, which is semantic. The coordination level has its own live precedent that moved code: FND-040 was classified here as a defect while REQ-39 chartered the behaviour, and two lanes implemented and reverted a fix before the authority chain stopped it. Records: coordination/DESIGN_HUB-12_kit_batch.md item 7. 0.2.17 writes the en dash and em dash in one strip set as ESCAPES rather than literals. That is not text polish: a literal either character in a committed file is refused by both libraries' house-style walks, and it is what stopped itaca vendoring this row at all. The strip set is unchanged in meaning. The citation FORM, the LaTeX index form and the British spellings are DEFERRED by the author to the next stable version and this file stays ADVISORY; ITC-20260802-1705, ITC-20260802-1710 and ITC-20260802-1720 stay open deliberately. See coordination/DESIGN_HUB-13_kit_0217.md item 8.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Cite an id WITH ITS TITLE, so a wrong citation is visible.

Usage:
    python check_citations.py --authority <path> [--authority <path> ...]
                              --prose <path> [--prose <path> ...]
                              [--mode advisory|mandatory]
                              [--prefix OQ --prefix DD ...]

Exit codes: 0 clean, 1 a violation, 2 configuration error.

THE DEFECT THIS IS ABOUT, and the guard a reader reaches for first does not
catch it. ``ITC-20260802-0340``. A lane cited ``OQ-53`` in two places for a
question ``OQ-53`` does not ask. Three reviewer lenses caught it
independently, which is three expensive reads spent on something mechanical.

"Every cited id must exist in its authority" catches a DANGLING citation: an
id never allocated, or one lost to renumbering. APPLIED TO THE REAL ERROR IT
WOULD HAVE PASSED, because ``OQ-53`` exists. The error was a
wrong-but-EXISTING citation, which is semantic, and a guard proposed for a
defect it cannot catch is what this workspace registers most often.

THE FORM THAT CATCHES IT is to cite the id together with its title and check
that the quoted title matches the title that id carries in its authority. Had
the sentence read "OQ-53, whether the vendored kit is checked for CURRENCY",
the mismatch with the paragraph it sat in, which was about a review-round
ledger, would have been visible while writing it. It catches the dangling
case for free, since an id with no heading has no title to match.

WHAT IT STILL CANNOT CATCH, from the incident's own words: prose that cites
correctly and then concludes something the cited authority does not support.
That is not mechanizable and belongs to review.

THE CITATION FORM, stated exactly, because a checker that guesses is worse
than none::

    <ID>, <title fragment>

The id, a comma, and a fragment running to a sentence stop, an opening
bracket, or a blank line. Anything else is a citation carrying NO title,
which is the case ``--mode`` governs.

A TABLE THAT PAIRS AN ID WITH ITS TITLE IN THE NEXT CELL satisfies the
intent and NOT this form, so it is reported as a citation with no title.
That is deliberate rather than an oversight: a form that accepted "the title
is somewhere nearby" would be the line-window shape this kit has now paid
for three times. It is also why ``advisory`` is the default, since a
document whose ids are tabulated is not wrong, it is written another way.

THE AUTHORITY INDEX is built from three forms and no others:

1. A markdown HEADING whose text begins with the id: ``## OQ-53: <title>``,
   ``### FND-040 <title>``. The title is the rest of the heading.
2. A TABLE ROW whose first cell is exactly the id. The title is the second
   cell.
3. A FILE whose YAML frontmatter carries ``id:``. Its title is the
   frontmatter ``title:`` when present, else THE ID'S OWN TRAILING SLUG with
   hyphens read as spaces, else the first ``#`` heading. A frontmatter id of
   the form ``<PREFIX>-<numbers>-<slug>`` also registers the
   ``<PREFIX>-<numbers>`` part, because that is the form prose cites.

   The slug comes BEFORE the heading, and that order was wrong in the first
   version: a file whose title is IN its id carries no ``# Title`` heading,
   so the first heading found is a SECTION heading. Real entries indexed as
   "Symptom, measured" until this was measured on a real plan directory.

AMBIGUOUS IDS, and this paragraph exists because the checker's FIRST RUN
against a real corpus refused it and was wrong to. Form 3's derived
``<PREFIX>-<numbers>`` part is NOT unique in every workspace: in one real
plan directory the numeric part is a BATCH STAMP and 28 entries share
``ITC-20260723-2042``, with six such stamps in one directory. Prose there
still cites the numeric form, so dropping the derived registration would
report every one of those citations as dangling, and refusing the collision
would refuse the workspace's own convention.

So a DERIVED id may carry many titles, and a citation is checked against ALL
of them and refused only when it matches NONE. That still catches a citation
naming something else entirely, which is the defect class, and it reports how
many entries share the stamp so the reader knows what was compared.

An EXPLICIT id, from a heading or a table row, carries exactly one title. Two
different ones there is a contradiction inside the authority, and a citation
checked against whichever was read first would be worse than one not checked
at all, so that is a CONFIG error.

THE MATCH RULE, and its threshold is deliberately generous. The fragment's
SIGNIFICANT words (four characters or more, minus a small stopword set) are
compared with the title's words. Fewer than a third of them present is a
MISMATCH. Generous because the failure directions are not symmetric: a
missed wrong citation costs one reviewer read, and a FALSE refusal in a gate
teaches a repository to switch the gate off. The overlap is always printed,
so a reader can judge a borderline case rather than trust the threshold.

THE MODE, and the reason it exists rather than being decided here. The
incident is explicit that the convention decision comes FIRST, because a
check that only validates citations which happen to carry a title is
advisory rather than a positive assertion. That decision belongs to each
consumer's charter, so both branches ship and the default is declared:

- ``--mode advisory`` (DEFAULT): a citation with no title fragment is a NOTE
  and exits 0 on notes alone.
- ``--mode mandatory``: it is a violation.

A MISMATCH IS A VIOLATION IN BOTH MODES. The mode governs only the
no-title case, so a repository that stays advisory still gets the check that
catches the defect this file is about.

Standalone, stdlib only, no third-party deps, like every kit checker.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_PREFIXES = ("OQ", "DD", "REQ", "FND", "ITC", "INC", "BRF", "ARCH",
                    "PLN", "REV")
STOPWORDS = frozenset({
    "that", "this", "with", "from", "into", "when", "what", "which", "whose",
    "they", "them", "their", "than", "then", "have", "been", "being", "does",
    "were", "will", "would", "shall", "about", "there", "here", "only",
    "also", "such", "some", "each", "every", "must", "does",
    # `whether` leads a large share of the open questions this checker is
    # aimed at, so it agrees between almost any two of them and inflates
    # the overlap. Measured on the real ITC-20260802-0340 case: with it
    # counted, a wrong citation scored one of two words and passed.
    "whether",
})
# Fewer than this share of a fragment's significant words present in the
# title is a MISMATCH. See THE MATCH RULE in the docstring: generous on
# purpose, because a false refusal in a gate is more expensive than a missed
# wrong citation.
THRESHOLD = 1 / 3
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
FRONT_ID = re.compile(r"^id:\s*(\S+)\s*$")
FRONT_TITLE = re.compile(r"^title:\s*(.+?)\s*$")
SPLIT_ID = re.compile(r"^([A-Z]+-[0-9][0-9-]*[0-9])-(.+)$")


class ConfigError(Exception):
    """The check could not run. Never reported as a clean tree."""


def words(text: str) -> list[str]:
    """Significant words, for comparison only. Never shown to a reader."""
    raw = re.split(r"[^A-Za-z0-9]+", text.lower())
    return [w for w in raw if len(w) >= 4 and w not in STOPWORDS]


def id_pattern(prefixes: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"\b((?:" + "|".join(prefixes) + r")-[0-9][0-9-]*)\b")


class Index:
    """id -> the titles it carries, and which ids are legitimately many.

    AN EXPLICIT id carries exactly one title: a heading or a table row that
    names it twice with two different titles is a contradiction in the
    authority itself, and a citation checked against whichever was read
    first would be worse than one not checked at all. That is a CONFIG
    error.

    A DERIVED id may carry many, and this is not a defect. See AMBIGUOUS
    IDS in the module docstring: the numeric part of a plan-entry id is a
    BATCH STAMP in at least one real workspace, where 28 entries share one.
    """

    def __init__(self) -> None:
        self.titles: dict[str, list[tuple[str, str]]] = {}
        self.derived: set[str] = set()

    def add(self, ident: str, title: str, where: str,
            derived: bool = False) -> None:
        title = title.strip().strip("`*_ ").strip()
        if not title:
            return
        known = self.titles.setdefault(ident, [])
        if any(words(t) == words(title) for t, _ in known):
            return
        if derived:
            self.derived.add(ident)
        elif known and ident not in self.derived:
            raise ConfigError(
                f"{ident} carries two different titles: {known[0][0]!r} in "
                f"{known[0][1]} and {title!r} in {where}. A checker cannot "
                "choose between them, and a citation checked against the "
                "wrong one would be worse than one not checked at all.")
        known.append((title, where))

    def get(self, ident: str) -> list[tuple[str, str]]:
        return self.titles.get(ident, [])

    def __len__(self) -> int:
        return len(self.titles)


def build_index(paths: list[Path], pattern: re.Pattern[str]) -> Index:
    """The authority index. See THE AUTHORITY INDEX and AMBIGUOUS IDS."""
    index = Index()
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files += sorted(path.rglob("*.md"))
        elif path.is_file():
            files.append(path)
        else:
            raise ConfigError(f"{path} is neither a file nor a directory. "
                              "Pass --authority the document or folder that "
                              "ALLOCATES the ids cited in the prose.")
    if not files:
        raise ConfigError(
            "no authority document found. An index built from nothing would "
            "report every citation as dangling, which is a configuration "
            "error wearing a verdict.")
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        where = str(path)
        # Form 3: frontmatter.
        if lines and lines[0].strip() == "---":
            ident = title = ""
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                m = FRONT_ID.match(line.strip())
                if m:
                    ident = m.group(1)
                m = FRONT_TITLE.match(line.strip())
                if m:
                    title = m.group(1)
            if ident:
                head = next((HEADING.match(ln).group(1) for ln in lines
                             if HEADING.match(ln)), "")
                split = SPLIT_ID.match(ident)
                slug = split.group(2).replace("-", " ") if split else ""
                # THE SLUG BEATS THE FIRST HEADING, and the order was wrong
                # in the first version. A plan entry that carries its title
                # in its own id has no `# Title` heading, so the first
                # heading found is a SECTION heading: real files indexed as
                # "Symptom, measured" and "Why there is no mechanism today".
                # Measured on a real plan directory, not predicted.
                index.add(ident, title or slug or head, where)
                if split:
                    index.add(split.group(1), title or slug or head,
                              where, derived=True)
        for line in lines:
            stripped = line.strip()
            # Form 1: a heading beginning with an id.
            m = HEADING.match(stripped)
            if m:
                text = m.group(1).strip().strip("`")
                found = pattern.match(text)
                if found:
                    index.add(found.group(1),
                              # The en dash and em dash are written as
                              # ESCAPES, not as literals. This file is
                              # vendored into repositories whose house-style
                              # walk refuses either character anywhere in a
                              # committed file, and a literal here is what
                              # stopped itaca vendoring this row at all. The
                              # strip set is unchanged in meaning.
                              text[found.end():].lstrip(" :-.\u2013\u2014"),
                              where)
                continue
            # Form 2: a table row whose FIRST cell is exactly an id.
            if stripped.startswith("|"):
                cells = [c.strip().strip("`") for c in stripped.split("|")]
                cells = [c for c in cells[1:]] if len(cells) > 2 else []
                if len(cells) >= 2 and pattern.fullmatch(cells[0]):
                    index.add(cells[0], cells[1], where)
    return index


def citations(text: str, pattern: re.Pattern[str]
              ) -> list[tuple[str, str, int]]:
    """Every (id, title fragment or "", line number) in one document.

    A FRAGMENT SPANS LINE BREAKS, and it has to. This function's first
    version read one line at a time, and the real ITC-20260802-0340 case
    escaped it: the wrapped citation gave up a two-word fragment whose
    first word happened to appear in the right title, so a wrong citation
    scored 50 percent and passed. Prose wraps; a sentence is the unit.

    The fragment ends at a sentence stop, an opening bracket, or a BLANK
    LINE, which is where a paragraph ends and no title continues.
    """
    out: list[tuple[str, str, int]] = []
    flat = text.replace("\r\n", "\n").replace("\r", "\n")
    starts = [0]
    for line in flat.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    for m in pattern.finditer(flat):
        number = sum(1 for s in starts if s <= m.start())
        rest = flat[m.end():]
        fragment = ""
        if rest.startswith(","):
            fragment = re.split(r"[.;(\[]|\n\s*\n", rest[1:], maxsplit=1)[0]
        out.append((m.group(1),
                    " ".join(fragment.split()).strip("`*_ "), number))
    return out


def overlap(fragment: str, title: str) -> tuple[int, int]:
    """(matched, total) significant words of the fragment found in title."""
    have = set(words(title))
    want = words(fragment)
    return sum(1 for w in want if w in have), len(want)


def check(prose: list[Path], index: Index, pattern: re.Pattern[str],
          mandatory: bool) -> tuple[list[str], list[str], int]:
    violations: list[str] = []
    notes: list[str] = []
    files: list[Path] = []
    for path in prose:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*.md"))
        elif path.is_file():
            files.append(path)
        else:
            raise ConfigError(f"{path} is neither a file nor a directory. "
                              "Pass --prose the document to check.")
    if not files:
        raise ConfigError(
            "no prose document found. An audit that examined nothing is a "
            "configuration error, not a clean tree.")
    seen = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for ident, fragment, number in citations(text, pattern):
            seen += 1
            known = index.get(ident)
            if not known:
                violations.append(
                    f"{path}:{number}: {ident} is cited and is allocated "
                    "nowhere in the authority. Either the id is wrong, or it "
                    "was renumbered and this citation was left behind.")
                continue
            title, where = known[0]
            if not fragment:
                message = (f"{path}:{number}: {ident} is cited with no title. "
                           f"It is titled {title!r} in {where}; write "
                           f"`{ident}, <its title>` so a wrong citation is "
                           "visible on sight.")
                (violations if mandatory else notes).append(message)
                continue
            # AGAINST EVERY CANDIDATE, and it is refused only when it matches
            # NONE. An id with one title is the ordinary case and this is the
            # same comparison; an AMBIGUOUS id (see the class above) is
            # checked as "does the quoted title name any entry carrying this
            # stamp", which still catches a citation naming something else
            # entirely and does not refuse a workspace's own naming.
            best = (-1.0, 0, 0, title, where)
            for candidate, candidate_where in known:
                matched, total = overlap(fragment, candidate)
                share = (matched / total) if total else 1.0
                if share > best[0]:
                    best = (share, matched, total, candidate, candidate_where)
            share, matched, total, title, where = best
            if total and share < THRESHOLD:
                many = (f" ({len(known)} entries carry this id; this is the "
                        "closest)") if len(known) > 1 else ""
                violations.append(
                    f"{path}:{number}: {ident} is cited as {fragment!r}, but "
                    f"{ident} is titled {title!r} in {where}{many}. Only "
                    f"{matched} of {total} significant words agree. Either "
                    "the citation names the wrong id, or the quoted title is "
                    "wrong; check which before changing either.")
    return violations, notes, seen


def main(argv: list[str]) -> int:
    args = argv[1:]

    def values(flag: str) -> list[str]:
        return [args[i + 1] for i, a in enumerate(args)
                if a == flag and i + 1 < len(args)]

    mode = (values("--mode") or ["advisory"])[-1]
    prefixes = tuple(values("--prefix")) or DEFAULT_PREFIXES
    authority = [Path(p) for p in values("--authority")]
    prose = [Path(p) for p in values("--prose")]
    if mode not in ("advisory", "mandatory"):
        print(f"CONFIG: --mode {mode!r} is not advisory or mandatory",
              file=sys.stderr)
        return 2
    if not authority or not prose:
        print("usage: check_citations.py --authority <path> --prose <path> "
              "[--mode advisory|mandatory] [--prefix OQ ...]", file=sys.stderr)
        return 2
    pattern = id_pattern(prefixes)
    try:
        index = build_index(authority, pattern)
        violations, notes, seen = check(prose, index, pattern,
                                        mode == "mandatory")
    except ConfigError as exc:
        print(f"CONFIG: {exc}", file=sys.stderr)
        return 2
    for line in notes:
        print(f"NOTE (advisory mode) {line}")
    for line in violations:
        print(f"REFUSED {line}")
    print(f"{len(index)} id(s) indexed, {seen} citation(s) read, "
          f"{len(violations)} refused, {len(notes)} note(s), mode {mode}")
    if seen == 0:
        print("no citation found in the prose given. That is a real answer "
              "and not a clean one: check the --prefix set matches the ids "
              "this workspace allocates.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
