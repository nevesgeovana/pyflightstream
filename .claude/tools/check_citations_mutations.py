# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: check_citations_mutations.py
# body-sha256: 97a46d08ea2b39fe13403048f22d96f9f4189af768ac2483f037bcafbf0d32aa
# canonical-source: BUILT for the kit (0.2.16, HUB-12) as the guard evidence for check_citations.py. Its load-bearing case is the REAL miscitation of ITC-20260802-0340, reproduced verbatim in shape: OQ-53 cited for a question OQ-53 does not ask, wrapped across two lines exactly as prose wraps. That case caught a defect in the checker's own first version, recorded below rather than quietly fixed.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Guard evidence for check_citations.py, on real documents on disk.

Run:  python check_citations_mutations.py

THE LOAD-BEARING CASE IS THE REAL ONE. ``ITC-20260802-0340`` records that
lane ITA-11 cited ``OQ-53`` for a question ``OQ-53`` does not ask, and that
three reviewer lenses caught it independently. That citation, wrapped across
two lines the way prose wraps, is ``the_real_miscitation_is_refused`` below,
and the correct form of the same sentence is the case beside it.

A FINDING THIS FILE MADE AGAINST ITS OWN CHECKER, recorded because a guard
that never fires on its author is a guard nobody tested. The checker's first
version read citations ONE LINE AT A TIME, and on the real case the fragment
was truncated at the line break to two words, one of which was ``whether``,
which appears in the right title. Two of two words agreed, the wrong
citation scored 100 percent and PASSED. The first run of this file said so.

Two things moved, and the SECOND finding is the one worth reading: a
fragment now spans line breaks, and ``whether`` became a stopword because it
leads a large share of the open questions this is aimed at and therefore
agrees between almost any two of them. Each fix ALONE is enough to refuse
the real case, so the mutant for the line-spanning half survived on it,
denied only by a changed message. A mutant denied by a message rather than a
verdict is the weaker evidence this kit names elsewhere, so the case
``a_wrapped_citation_is_read_whole_not_to_the_line_break`` was written for
it instead: its first line agrees with the title and its rest does not, so
truncation scores two of two and the whole fragment scores two of eight.
Both halves now have a mutant denied by a verdict.

Exit 0 when every case holds and every mutant is denied, 1 otherwise.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

MODULE = Path(__file__).resolve().parent / "check_citations.py"

AUTHORITY = """\
# Open questions

| id | question |
|---|---|
| OQ-53 | whether the vendored kit is checked for CURRENCY and by what locator |
| OQ-54 | should the two-round cap be MECHANICAL, and at which moment |

## REQ-39 the reviewer may hold Bash and must not mutate git state
"""

# The real error, wrapped across two lines exactly as prose wraps.
MISCITED = """\
The round ledger has no locator today, which is OQ-53, whether the round
ledger is checked at a gate. That is registered rather than taken.
"""

CORRECT = """\
This is OQ-53, whether the vendored kit is checked for CURRENCY, and it is
adjacent to but not the same as the ledger question.
"""

# A wrapped citation whose FIRST LINE agrees with the title and whose rest
# does not. This is what separates the line-spanning fix from the stopword
# one: truncated at the break it scores two of two and passes; read whole it
# scores two of eight and is refused.
WRAPPED_FIRST_LINE_LOOKS_RIGHT = """\
The mechanisation question is OQ-54, should the two-round cap be
enforced by the release gate, the tag path, the caller workflow and the
publish job.
"""

NO_TITLE = "See OQ-54 for the mechanisation question.\n"
DANGLING = "See OQ-99, a question nobody allocated.\n"
HEADING_FORM = ("A lens may hold Bash: REQ-39, the reviewer may hold Bash "
                "and must not mutate git state.\n")
HEADING_FORM_WRONG = ("A lens may not hold Bash at all: REQ-39, no reviewer "
                      "agent is given a shell under any circumstances.\n")

# The frontmatter form, which is how the workspaces name plan entries: the
# id carries its own slug and prose cites the numeric part alone.
PLAN_ENTRY = """\
---
id: ITC-20260802-0340-cite-an-id-with-its-title-so-a-wrong-citation-is-visible
status: open
---

Some prose.
"""
CITES_PLAN = ("This follows ITC-20260802-0340, cite an id with its title so "
              "a wrong citation is visible.\n")
CITES_PLAN_WRONG = ("This follows ITC-20260802-0340, the spawn guard reads a "
                    "line window rather than the call.\n")

# Two plan entries sharing one BATCH STAMP, which is the real shape that
# refused the checker's own first version.
STAMPED_ONE = """\
---
id: ITC-20260723-2042-allowlist-drift-is-caught-only-at-replay
status: open
---

## Symptom, measured

Some prose that is a SECTION heading and not a title.
"""
STAMPED_TWO = """\
---
id: ITC-20260723-2042-the-import-policy-is-a-denylist
status: open
---

## Symptom, measured

More prose.
"""
CITES_STAMPED_ONE = ("See ITC-20260723-2042, allowlist drift is caught only "
                     "at replay.\n")
CITES_STAMPED_TWO = ("See ITC-20260723-2042, the import policy is a "
                     "denylist.\n")
CITES_STAMPED_NEITHER = ("See ITC-20260723-2042, the release gate publishes "
                         "without minting an OIDC token.\n")

CONTRADICTORY = """\
# Another index

| id | question |
|---|---|
| OQ-53 | something else entirely about packaging and wheels |
"""

# name, {filename: text}, prose filenames, extra flags, exit code, needle
CASES: list[tuple[str, dict[str, str], list[str], list[str], int, str]] = [
    ("the_real_miscitation_is_refused",
     {"auth.md": AUTHORITY, "p.md": MISCITED}, ["p.md"], [], 1,
     "is cited as 'whether the round ledger is checked at a gate'"),
    ("the_correct_citation_passes",
     {"auth.md": AUTHORITY, "p.md": CORRECT}, ["p.md"], [], 0, "0 refused"),
    ("a_wrapped_citation_is_read_whole_not_to_the_line_break",
     {"auth.md": AUTHORITY, "p.md": WRAPPED_FIRST_LINE_LOOKS_RIGHT},
     ["p.md"], [], 1, "significant words agree"),
    ("a_dangling_id_is_refused",
     {"auth.md": AUTHORITY, "p.md": DANGLING}, ["p.md"], [], 1,
     "allocated nowhere"),
    ("no_title_is_a_note_in_advisory",
     {"auth.md": AUTHORITY, "p.md": NO_TITLE}, ["p.md"], [], 0,
     "NOTE (advisory mode)"),
    ("no_title_is_a_violation_in_mandatory",
     {"auth.md": AUTHORITY, "p.md": NO_TITLE}, ["p.md"],
     ["--mode", "mandatory"], 1, "is cited with no title"),
    # THE MODE GOVERNS ONLY THE NO-TITLE CASE. A repository that stays
    # advisory must still get the check this file is about.
    ("a_mismatch_is_refused_in_advisory_too",
     {"auth.md": AUTHORITY, "p.md": MISCITED}, ["p.md"],
     ["--mode", "advisory"], 1, "significant words agree"),
    ("the_heading_form_indexes_a_title",
     {"auth.md": AUTHORITY, "p.md": HEADING_FORM}, ["p.md"], [], 0,
     "0 refused"),
    ("the_heading_form_catches_a_wrong_title",
     {"auth.md": AUTHORITY, "p.md": HEADING_FORM_WRONG}, ["p.md"], [], 1,
     "significant words agree"),
    ("a_frontmatter_id_registers_its_numeric_form",
     {"auth.md": AUTHORITY, "plan.md": PLAN_ENTRY, "p.md": CITES_PLAN},
     ["p.md"], [], 0, "0 refused"),
    ("a_frontmatter_id_cited_with_another_entrys_title_is_refused",
     {"auth.md": AUTHORITY, "plan.md": PLAN_ENTRY, "p.md": CITES_PLAN_WRONG},
     ["p.md"], [], 1, "significant words agree"),
    # THE FIRST RUN ON A REAL CORPUS REFUSED THE CORPUS, and these two cases
    # are that finding. In one real plan directory the numeric part of a
    # plan-entry id is a BATCH STAMP: 28 entries share ITC-20260723-2042 and
    # six such stamps exist in one directory, while prose still cites the
    # numeric form. A derived id therefore carries many titles, and a
    # citation is checked against all of them.
    ("a_batch_stamped_id_shared_by_two_entries_is_not_a_config_error",
     {"auth.md": AUTHORITY, "a.md": STAMPED_ONE, "b.md": STAMPED_TWO,
      "p.md": CITES_STAMPED_ONE}, ["p.md"], [], 0, "0 refused"),
    ("a_batch_stamped_id_matches_either_entry",
     {"auth.md": AUTHORITY, "a.md": STAMPED_ONE, "b.md": STAMPED_TWO,
      "p.md": CITES_STAMPED_TWO}, ["p.md"], [], 0, "0 refused"),
    ("a_batch_stamped_id_cited_as_neither_is_still_refused",
     {"auth.md": AUTHORITY, "a.md": STAMPED_ONE, "b.md": STAMPED_TWO,
      "p.md": CITES_STAMPED_NEITHER}, ["p.md"], [], 1,
     "entries carry this id"),
    ("two_titles_for_one_id_is_a_config_error",
     {"auth.md": AUTHORITY, "auth2.md": CONTRADICTORY, "p.md": CORRECT},
     ["p.md"], [], 2, "carries two different titles"),
]

MUTANTS: list[tuple[str, str, str, str]] = [
    # THE CHECKER'S OWN FIRST VERSION. It read one line at a time, and the
    # real case escaped it.
    ("read a citation one line at a time, which is the checker's own first "
     "version and let the real miscitation through",
     '            fragment = re.split(r"[.;(\\[]|\\n\\s*\\n", rest[1:], '
     "maxsplit=1)[0]",
     '            fragment = re.split(r"[.;(\\[\\n]", rest[1:], '
     "maxsplit=1)[0]",
     "a_wrapped_citation_is_read_whole_not_to_the_line_break"),
    ("count `whether` as a significant word",
     '    "whether",\n})',
     "})",
     "the_real_miscitation_is_refused"),
    ("accept any overlap at all, however small",
     "            if total and share < THRESHOLD:",
     "            if total and share < -1:",
     "the_real_miscitation_is_refused"),
    ("a cited id that is allocated nowhere is accepted",
     "            if not known:",
     "            if False:",
     "a_dangling_id_is_refused"),
    ("advisory mode downgrades a MISMATCH as well as a missing title",
     "                violations.append(\n"
     "                    f\"{path}:{number}: {ident} is cited as "
     "{fragment!r}, but \"",
     "                (violations if mandatory else notes).append(\n"
     "                    f\"{path}:{number}: {ident} is cited as "
     "{fragment!r}, but \"",
     "a_mismatch_is_refused_in_advisory_too"),
    ("mandatory mode is the same as advisory",
     "            (violations if mandatory else notes).append(message)",
     "            notes.append(message)",
     "no_title_is_a_violation_in_mandatory"),
    ("an id with two different titles takes the first quietly",
     "            raise ConfigError(\n"
     "                f\"{ident} carries two different titles: ",
     "            _ = ConfigError(\n"
     "                f\"{ident} carries two different titles: ",
     "two_titles_for_one_id_is_a_config_error"),
    # AMBIGUOUS IDS, added after the checker's first run on a real corpus
    # refused a workspace's own convention. A derived id may carry many
    # titles; treating that as a contradiction is the false red.
    ("a derived id may carry only one title, which refuses a real "
     "workspace's naming convention",
     "        if derived:\n            self.derived.add(ident)\n"
     "        elif known and ident not in self.derived:",
     "        if False:\n            self.derived.add(ident)\n"
     "        elif known and ident not in self.derived:",
     "a_batch_stamped_id_shared_by_two_entries_is_not_a_config_error"),
    ("check a citation against only the FIRST candidate title",
     "            for candidate, candidate_where in known:",
     "            for candidate, candidate_where in known[:1]:",
     "a_batch_stamped_id_matches_either_entry"),
]


def run_case(module: Path, files: dict[str, str], prose: list[str],
             flags: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="citations-") as tmp:
        root = Path(tmp)
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        authority: list[str] = []
        for name in files:
            if name not in prose:
                authority += ["--authority", str(root / name)]
        args = [sys.executable, str(module)]
        for name in prose:
            args += ["--prose", str(root / name)]
        r = subprocess.run(args + authority + flags,
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def main() -> int:
    if not MODULE.is_file():
        print(f"CONFIG: {MODULE} not found beside this file", file=sys.stderr)
        return 2
    print(f"check_citations guard evidence, {len(CASES)} cases, "
          f"{len(MUTANTS)} mutants")
    failed: list[str] = []
    for name, files, prose, flags, code, needle in CASES:
        got, out = run_case(MODULE, files, prose, flags)
        ok = got == code and needle in out
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: exit {got} "
              f"(expected {code}), needle "
              f"{'found' if needle in out else 'MISSING'}")
        if not ok:
            failed.append(name)
            print("      " + out.strip().replace("\n", "\n      ")[:500])
    if failed:
        print(f"\n{len(failed)} case(s) failed on the real module; the "
              "mutants are not run, because a mutation result over a broken "
              "baseline says nothing.")
        return 1

    source = MODULE.read_text(encoding="utf-8")
    survivors: list[str] = []
    crash_denials: list[str] = []
    with tempfile.TemporaryDirectory(prefix="citations-mutants-") as tmp:
        for i, (label, old, new, case_name) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"  [FAIL] mutant {i} ({label}): the text it replaces "
                      f"occurs {source.count(old)} times, not once")
                survivors.append(label)
                continue
            mutant = Path(tmp) / f"mutant_{i}.py"
            mutant.write_text(source.replace(old, new), encoding="utf-8")
            files, prose, flags, code, needle = next(
                (f, p, fl, c, n) for nm, f, p, fl, c, n in CASES
                if nm == case_name)
            got, out = run_case(mutant, files, prose, flags)
            denied = not (got == code and needle in out)
            kind = "crash" if "Traceback" in out else "verdict"
            if denied and kind == "crash":
                crash_denials.append(label)
            print(f"  [{'denied ' if denied else 'SURVIVED'}] {label} "
                  f"-> {case_name} gave exit {got} (expected {code}), "
                  f"by {kind}")
            if not denied:
                survivors.append(label)

    if survivors:
        print(f"\n{len(survivors)} mutant(s) SURVIVED: {survivors}")
        return 1
    print(f"\nAll {len(CASES)} cases hold and all {len(MUTANTS)} mutants "
          "are denied. The guard can still fail.")
    if crash_denials:
        print(f"{len(crash_denials)} of them were denied BY A CRASH rather "
              f"than by a changed verdict: {crash_denials}. That proves the "
              "line is load bearing and does not prove the check is what "
              "produced the refusal. Stated rather than counted silently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
