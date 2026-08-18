"""Mutation battery for the stale-tally guard.

A guard is not proven by a suite that passes. It is proven by restoring
the original defect and watching the guard deny.

Registering FlightStream 26.123 on 2026-08-17 falsified the same
enumeration in six committed places at once, with the whole tier-1
currency suite green: the SRS requirement text, the generated
conventions page, two docstrings in ``versions.py``, the ordering
authority's own header, the getting-started page and a shipped example.
``tests/test_claim_currency.py`` gained a guard for that class, and this
is what shows the guard would have caught them.

Each mutant puts the stale sentences of ONE file back exactly as they
stood before the repair, runs the guard alone, and requires the guard to
DENY. The file is then restored and its sha256 compared with the value
taken before, because a battery that leaves the tree changed is worse
than no battery.

DENY IS NOT THE SAME AS A NON-ZERO EXIT, which is what this battery read
until 2026-08-18. pytest exits 2 on a collection error, 4 on a usage
error and 5 when the selection matched no test, and none of those is a
guard denying. Since the selector here is a long node id, a rename of the
guard gave exit 5 on every mutant and this battery would have printed
"6 of 6 mutants killed" and exited 0 while judging nothing. The
three-valued classification is shared, in
``_mutation_harness.verdict``, and an INCONCLUSIVE stops the run rather
than scoring.

THIS BATTERY ANCHORED ON ``git show HEAD:<path>`` UNTIL 2026-08-17 AND
WAS BROKEN BY ITS OWN SUBJECT, which is worth stating because the shape
is subtle and the failure was silent in the direction that matters. The
HEAD blob was the PRE-FIX text only while the fix sat uncommitted; from
the commit that landed the fix onward it is the FIXED text, so five of
the six mutants wrote the file back exactly as it already was, mutated
nothing, and were reported as SURVIVED. The battery then failed loudly,
which is the honest direction, but it failed READING AS THOUGH THE GUARD
HAD MISSED FIVE REAL DEFECTS, and it could never pass again. It was
measured at 1 of 6 by the QA review pass on the day it was written,
having been reported as 6 of 6 by its author the hour before.

The repair is to carry the stale sentences as LITERALS, which is what the
one mutant that still worked already did. A commit pin would only move
the trap to the next rebase.

Every LIVE anchor is asserted PRESENT AND UNIQUE before it is applied. A
mutant whose anchor has drifted mutates nothing and passes vacuously,
which is the same failure in a different costume.

    python scripts/prove_alias_tally_guard.py

Like its sibling batteries it EDITS TRACKED FILES. Run it from a clean
tree and check ``git status`` afterwards; unlike them it fails rather
than warns if a restore is not byte-exact.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mutation_harness import REPO, verdict  # noqa: E402

TEST = (
    "tests/test_claim_currency.py::"
    "test_no_committed_page_writes_a_stale_tally_of_a_shared_vendor_name"
)

REFERENCE_LIVE_1 = (
    '        "build: the vendor reuses a release name across builds, so both "\n'
    '        "26.12 and 26.1 name more than one, each refused with every "\n'
    '        "candidate and its vendor build number named rather than "\n'
    '        "resolving to one. The members are not written out here, and that "\n'
    '        "is deliberate: a hand-written list of them went stale on the two "\n'
    '        "registrations that followed it, so the refusal itself is the "\n'
    '        "list. Reuse is not descent either, and which family is which "\n'
    '        "matters: 26.12 is a release with its hotfixes, while 26.1 is two "\n'
    '        "separate releases that happened to share a name. The registry "\n'
    '        "states descent per build rather than leaving it to be read off "\n'
    '        "the identifier.",\n'
)
REFERENCE_STALE_1 = (
    '        "build: the vendor reuses a release name across builds, so 26.12 "\n'
    '        "names 26.120, 26.121 and 26.122, and 26.1 names both 26.100 and "\n'
    '        "26.101, each refused with every candidate and its vendor build "\n'
    '        "number named rather than resolving to one. Reuse is not descent: "\n'
    '        "the first group is a release and its two hotfixes and the second '
    'is two "\n'
    '        "separate releases, which the registry states per build.",\n'
)
REFERENCE_LIVE_2 = (
    "    one release name, which is most of the 26 series: those builds ship\n"
    "    under one alias and their binaries print one release name, so\n"
    "    neither string separates them. The members are not written out\n"
    "    here, and the sentence saying so used to be followed by a list of\n"
    "    them; the rendered page computes the tally, which is the only copy\n"
    "    that cannot go stale. A table\n"
)
REFERENCE_STALE_2 = (
    '    one release name: 26.120, 26.121 and 26.122 all ship as "26.12" and\n'
    '    all three binaries print "26.1". The tally is not written here\n'
    "    because it moves with every build the vendor issues; the rendered\n"
    "    page computes it. A table\n"
)

VERSIONS_LIVE_1 = (
    "    the hotfixes of one release: the 26.1 family is the February and May\n"
    "    2026 releases sharing a name rather than a release and its hotfix.\n"
    "    Which builds sit in either family is not written here, because the\n"
    "    message this class raises enumerates them from the registry and a\n"
    "    second copy in prose has gone stale on every registration. A display\n"
    "    alias therefore cannot select a build, and returning either one would\n"
    "    hand the caller a silently wrong solver.\n"
)
VERSIONS_STALE_1 = (
    "    the hotfixes of one release: 26.120, 26.121 and 26.122 are all\n"
    '    shipped as "26.12", and 26.100 and 26.101 are both shipped as "26.1" '
    "although\n"
    "    they are the February and May 2026 releases rather than a release\n"
    "    and its hotfix. A display alias therefore cannot select a build, and\n"
    "    returning either one would hand the caller a silently wrong solver.\n"
)
VERSIONS_LIVE_2 = (
    "        of one minor release apart at run time, because every build of\n"
    "        one release prints the same version string. Which builds those\n"
    "        are is not listed here: the generated build page computes it,\n"
    "        and a hand-written list has gone stale on every registration.\n"
    "        Registered from committed evidence, never guessed.\n"
)
VERSIONS_STALE_2 = (
    "        of one minor release apart at run time, because they print the\n"
    '        same version string: 26.120, 26.121 and 26.122 all print "26.1".\n'
    "        Registered from committed evidence, never guessed.\n"
)
VERSIONS_LIVE_3 = (
    "        wherever the vendor has reused a release name, which the 26.12\n"
    "        family is: those builds ship under one alias and print one\n"
    "        release name, so neither string separates them. No tally appears\n"
    "        here, and this sentence used to carry one anyway, which went\n"
    "        stale twice. A reader holding an\n"
)
VERSIONS_STALE_3 = (
    "        wherever the vendor has reused a release name: 26.120, 26.121 and\n"
    '        26.122 all ship as "26.12" and all three print "26.1". No tally\n'
    "        appears here, because it moved the day the third of those was\n"
    "        registered. A reader holding an\n"
)

#: THE TALLY-BEARING SENTENCE ALONE, not the paragraph around it. The
#: first version anchored the whole paragraph and broke the day an
#: executed example was inserted into the middle of it, which is the
#: general lesson: anchor on the smallest span that carries the defect,
#: because everything else in the neighbourhood is free to move.
GETTING_STARTED_LIVE = (
    'The vendor reuses a release name across builds, so both `"26.12"` and\n'
    '`"26.1"` name more than one; each is refused with every candidate and\n'
    "its vendor build number named."
)
GETTING_STARTED_STALE = (
    'The vendor reuses a release name across builds, so `"26.12"` names\n'
    'three and `"26.1"` names two more; both are refused with every candidate\n'
    "and its vendor build number named."
)

#: RE-ANCHORED 2026-08-18, and this one is not a drift: the author ruled
#: that FR-02c should STOP ENUMERATING, so the live text no longer names
#: a build at all. The requirement had been the last committed home of
#: this enumeration after the other six were swept on 2026-08-17, and it
#: had gone stale twice by construction, once per registration.
#:
#: THE STALE TEXT IS THE PRE-26.123 SENTENCE, naming three builds where
#: four share the name, and the first attempt at this re-anchoring got it
#: wrong in a way worth recording. It restored the enumeration as it
#: stood at `fbc647f`, which named all FOUR and was therefore CURRENT;
#: the mutant survived, correctly, because this guard refuses a tally
#: that has gone STALE and not the existence of a list. A mutant that
#: restores a true sentence measures nothing, and the survival was the
#: battery reporting on the mutant rather than on the guard.
SRS_LIVE = "    can name more than one registered build. Resolution refuses such a\n"
SRS_STALE = (
    "    can name more than one registered build: 26.120, 26.121 and 26.122\n"
    '    are all shipped as "26.12", and 26.100 and 26.101 are both shipped as\n'
    '    "26.1" although they are separate releases rather than a release\n'
    "    and its hotfix. Resolution refuses such a\n"
)

EXAMPLE_LIVE = 'FS_VERSION = "26.120"  # canonical; the vendor name 26.12 names several builds\n'
EXAMPLE_STALE = 'FS_VERSION = "26.120"  # canonical; the vendor name 26.12 names three builds\n'

META_LIVE = (
    "#   vendor ships every build of one release under one alias and every\n"
    "#   one of those binaries prints one release name, so neither string\n"
    "#   separates them."
)
META_STALE = (
    "#   vendor ships 26.120, 26.121 and 26.122 under the name 26.12 and all\n"
    "#   three binaries print 26.1."
)

#: One entry per committed home, each carrying every stale span in that
#: file. The ordering authority is last because restoring its sentence is
#: all that may be restored there: putting its whole HEAD blob back would
#: remove the 26.123 row, shrink the alias family to three, and make the
#: stale sentence complete again, so the mutant would survive for a
#: reason that has nothing to do with the guard.
MUTANTS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "src/pyflightstream/reference.py",
        ((REFERENCE_LIVE_1, REFERENCE_STALE_1), (REFERENCE_LIVE_2, REFERENCE_STALE_2)),
    ),
    (
        "src/pyflightstream/versions.py",
        (
            (VERSIONS_LIVE_1, VERSIONS_STALE_1),
            (VERSIONS_LIVE_2, VERSIONS_STALE_2),
            (VERSIONS_LIVE_3, VERSIONS_STALE_3),
        ),
    ),
    ("docs/getting-started.md", ((GETTING_STARTED_LIVE, GETTING_STARTED_STALE),)),
    ("docs/srs/functional-requirements.md", ((SRS_LIVE, SRS_STALE),)),
    ("examples/steady_polar.py", ((EXAMPLE_LIVE, EXAMPLE_STALE),)),
    ("src/pyflightstream/commands/_meta.yaml", ((META_LIVE, META_STALE),)),
)


def sha(path: Path) -> str:
    """Return the sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guard() -> tuple[str, str]:
    """Run the guard alone and classify the outcome in THREE values.

    THIS RETURNED A BARE EXIT STATUS UNTIL 2026-08-18, and the caller
    scored ``bool(status)`` as a kill. pytest exits 1 on a failure, 2 on
    a collection or import error, 4 on a usage error and 5 when the
    selection matched no test; only the first is a guard denying, and the
    other three were counted as kills. This battery's selector is a long
    node id, so the trap was live rather than theoretical: a rename of
    the guard gives exit 5 on every mutant, and the battery would print
    "6 of 6 mutants killed" and exit 0. Three sibling batteries took the
    shared classifier the day it was written and this one, whose diff
    that day renamed the variable without changing the reading, did not.

    The classification lives in ``_mutation_harness.verdict`` rather than
    here, because a fifth copy of it is how the fourth copy came to be
    missed.
    """
    return verdict(TEST)


def _mutate(relative: str, spans: tuple[tuple[str, str], ...]) -> tuple[str, str, str, str]:
    """Write one mutant, run the guard, restore, and check the restore."""
    path = REPO / relative
    original = path.read_bytes()
    before = sha(path)
    text = original.decode("utf-8")
    # THE SPANS ARE WRITTEN WITH LINE FEEDS AND ONE TARGET IS CRLF ON
    # DISK. Reading BYTES is what makes the restore byte-exact, and it is
    # also what stops a line-feed anchor from matching the one chapter
    # file in this repository that is CRLF; the previous edition read
    # text, so Python normalised the difference away and the question
    # never came up. Translating the anchor rather than the file keeps
    # both properties.
    crlf = "\r\n" in text
    for live, stale in spans:
        if crlf:
            live, stale = live.replace("\n", "\r\n"), stale.replace("\n", "\r\n")
        # ASSERTED PRESENT AND UNIQUE. A drifted anchor replaces nothing
        # and the mutant then measures the unmutated tree, which is the
        # vacuous pass this battery exists to make impossible.
        found = text.count(live)
        if found != 1:
            raise SystemExit(
                f"{relative}: the live span appears {found} times, expected exactly 1. "
                f"The battery cannot mutate what it cannot find: {live.strip()[:70]!r}"
            )
        text = text.replace(live, stale)
    mutated = text.encode("utf-8")
    if mutated == original:
        raise SystemExit(
            f"{relative}: the mutant is byte-identical to the tree, so it mutates nothing"
        )
    mutant_sha = hashlib.sha256(mutated).hexdigest()
    path.write_bytes(mutated)
    try:
        outcome, tail = run_guard()
    finally:
        path.write_bytes(original)
    after = sha(path)
    if after != before:
        raise SystemExit(f"{relative} was not restored byte for byte: {before} -> {after}")
    return before, mutant_sha, outcome, tail


def main() -> None:
    """Run every mutant and report how many the guard killed."""
    control, control_tail = run_guard()
    print(f"control, unmutated tree: {control} ({control_tail})")
    if control != "SURVIVED":
        raise SystemExit(
            "the guard does not pass on the unmutated tree, so nothing below means "
            f"anything: {control} ({control_tail})"
        )

    killed = 0
    survived: list[str] = []
    for relative, spans in MUTANTS:
        original_sha, mutant_sha, outcome, tail = _mutate(relative, spans)
        print(
            f"  {outcome:12s} {relative} ({len(spans)} span(s))  "
            f"tree {original_sha[:12]} mutant {mutant_sha[:12]}"
        )
        # AN INCONCLUSIVE STOPS THE RUN RATHER THAN SCORING. It means the
        # guard was never asked the question, so neither a kill nor a
        # survival has been measured, and a battery that keeps going
        # publishes a tally over mutants it did not judge.
        if outcome == "INCONCLUSIVE":
            raise SystemExit(f"{relative}: the guard was not asked the question: {tail}")
        if outcome == "KILLED":
            killed += 1
        else:
            survived.append(relative)

    final, final_tail = run_guard()
    print(f"control, tree restored: {final} ({final_tail})")
    print(f"\n{killed} of {len(MUTANTS)} mutants killed")
    if survived:
        print("SURVIVED:", ", ".join(survived))
    if killed != len(MUTANTS) or final != "SURVIVED":
        sys.exit(1)


if __name__ == "__main__":
    main()
