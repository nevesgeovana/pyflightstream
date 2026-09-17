#!/usr/bin/env python3
"""Ask whether a tag was RELEASED, not merely tagged.

    python scripts/check_release_published.py            # every version tag
    python scripts/check_release_published.py v0.17.0    # one of them
    python scripts/check_release_published.py --offline  # the half that needs no network

WHY THIS EXISTS, measured on 2026-09-13. v0.17.0 was tagged, the tag was
pushed, the Release workflow ran green, and PyPI served the wheel. The
release gate asked whether the version was TAGGED, which it was, and passed.
Nobody created the GitHub release object, which is a MANUAL step that no
workflow performs: `.github/workflows/release.yml` carries four jobs, build,
test-artifact, gates and publish, and declares `contents: read`, so it could
not create one even if it tried.

EVERY CITABLE ARTIFACT OF THIS PROJECT HANGS OFF THAT STEP. The archive
webhook fires on the release object and not on the tag, so no release object
means no archive, no version DOI, and a CITATION.cff row that cannot be paid.
The release existed on one index and nowhere else for a day.

WHAT A RELEASE IS, therefore, and this is the sentence the gate was missing:

    a tag is RELEASED when the release object exists at that tag AND the
    archive has minted a version DOI that CITATION.cff records.

THE TWO HALVES ARE MEASURED DIFFERENTLY, deliberately. The DOI row is in the
repository and is read offline, so a test can run it on every commit. The
release object is on a service and needs the network, so it is asked for only
when this is run without `--offline`. A check that could only run online would
run nowhere; a check that only ran offline would miss the half that actually
broke.

THE WINDOW IS NOT A FAILURE. A version DOI is minted from the release object,
so it is recorded ONE COMMIT AFTER the tag. A tag whose row is not yet paid is
reported as IN THE WINDOW when the change log's Owed section names it, which is
the same rule `test_metadata_currency.py` already applies from the other side.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CITATION = REPO / "CITATION.cff"
CHANGELOG = REPO / "CHANGELOG.md"

#: A version tag: v followed by a digit. The same shape the push gate reads,
#: so a tag this refuses to judge is a tag that gate would not have judged
#: either.
VERSION_TAG = re.compile(r"^v\d[\w.\-]*$")

#: The rows below v0.3.0 were never recorded, which CITATION.cff's own header
#: states. Judging them would report a gap in a LIST as a gap in the archive.
FIRST_RECORDED = "v0.3.0"


def run(argv: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess:
    """Spawn one child with an EXPLICIT environment.

    ``env=`` is not decoration: a repository guard counts every spawn under
    ``src`` and ``scripts`` that inherits by default, and it counted this one
    the first time this file ran. ``os.environ.copy()`` is exactly what an
    omitted ``env=`` gives, so nothing about the child changed; what changed
    is that the inheritance is a decision at the call site, which is where a
    future narrowing has to be made.
    """
    return subprocess.run(  # noqa: S603
        argv, cwd=REPO, capture_output=True, text=True, timeout=timeout, env=os.environ.copy()
    )


def version_tags() -> list[str]:
    """Return every version tag this checkout carries, oldest first."""
    result = run(["git", "tag", "--list"])
    tags = [t.strip() for t in result.stdout.splitlines() if VERSION_TAG.match(t.strip())]
    return sorted(tags, key=_sortable)


def _sortable(tag: str) -> tuple:
    """Return the tag's numbers as a tuple, so v0.9.0 sorts before v0.10.0."""
    return tuple(int(p) if p.isdigit() else 0 for p in re.findall(r"\d+", tag))


def recorded_dois() -> dict[str, str]:
    """Every archive row CITATION.cff carries, keyed by the release it names."""
    text = CITATION.read_text(encoding="utf-8")
    rows: dict[str, str] = {}
    for value, description in re.findall(r'value:\s*(\S+)\s*\n\s*description:\s*"([^"]+)"', text):
        match = re.search(r"release\s+(v\S+)", description)
        if match:
            rows[match.group(1)] = value
    return rows


def owed_in_the_changelog() -> set[str]:
    """Return the tags the change log's Unreleased section names as owed a row.

    THE TIER-1 GUARD'S OWN FUNCTIONS, called rather than restated. This reader
    had three differences from the guard that decides whether a release may
    publish, and every one of them made it MORE permissive: it read the whole
    Unreleased section instead of the ``### Owed`` block, it read PHYSICAL LINES
    instead of bullets, and it never asked for a debt word at all. On 2026-09-16
    it printed "the change log names it OWED, which is the window" for a bullet
    that says "is not minted yet", while the guard refused the same bullet and
    the v0.21.0 publish was skipped. A cheap gate that does not ask the expensive
    one's question is worse than no gate, because it is believed.

    Raises
    ------
    SystemExit
        If the guard's functions cannot be imported. Falling back to a private
        reader is exactly how the two drifted apart, so this refuses instead.
    """
    # THE REPOSITORY ROOT, so `tests` imports when this is run as a script from
    # anywhere. Prepending is deliberate: the guard that decides the release is
    # the one in THIS checkout, never an installed copy of another.
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        from tests.tier1_offline.test_metadata_currency import (  # noqa: PLC0415
            _owed_claims,
            _the_owed_section,
        )
    except ImportError as error:  # pragma: no cover - a checkout without tests
        raise SystemExit(
            f"cannot import the tier-1 owed reader ({error}). This script answers with "
            "the guard's own functions and has no reader of its own, because the one it "
            "had was more permissive than the guard in three ways and reported a release "
            "ready that the release gates then refused. Run it from a checkout that "
            "carries tests/."
        ) from error

    owed = set()
    for claim in _owed_claims(_the_owed_section()):
        lowered = claim.lower()
        if not any(word in lowered for word in ("archive", "doi", "identifier")):
            continue
        if not any(word in lowered for word in ("owed", "owe", "not exist", "missing")):
            continue
        owed.update(re.findall(r"\bv\d[\w.\-]*", claim))
    return owed


def release_object_exists(tag: str) -> bool | None:
    """Return True, False, or None where the service could not be asked.

    NONE IS NOT A PASS. The caller reports it as UNKNOWN and exits non-zero,
    on the same precedent every gate here follows: a guard that reads its own
    missing information as permission is not a guard.
    """
    result = run(["gh", "release", "view", tag, "--json", "tagName"], timeout=60)
    if result.returncode == 0:
        try:
            return json.loads(result.stdout).get("tagName") == tag
        except ValueError:
            return None
    if "release not found" in (result.stderr or "").lower():
        return False
    return None


def main(argv: list[str] | None = None) -> int:
    """Judge each tag and print one line per tag; return 1 where any failed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", nargs="*", help="the tags to judge; default is every version tag")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="judge only the DOI row, which is in the repository and needs no network",
    )
    args = parser.parse_args(argv)

    tags = args.tag or version_tags()
    if not tags:
        # FOUND-NOTHING IS NOT A PASS, which is the rule this whole script is
        # an instance of. A checkout fetched without tags reached this branch,
        # printed a reasonable sentence and exited 0, so step 7 of the release
        # sequence confirmed a release nobody had looked at. Could-not-measure
        # takes a non-zero status and says what to do about it.
        print(
            "no version tag in this checkout, so NOTHING WAS JUDGED. That is not a pass: a "
            "shallow clone or a fetch without --tags reaches here. Run `git fetch --tags` and "
            "try again, or name the tag to judge.",
            file=sys.stderr,
        )
        return 2
    # A NAMED TAG IS CHECKED AGAINST THE CHECKOUT, and it was not. `args.tag`
    # went straight into the loop below, so asking about a tag that does not
    # exist -- a version not cut yet, or a typo -- printed "TAGGED BUT NOT
    # RELEASED: no release object". The VERDICT was right by accident and the
    # REASON was false, which sends a reader to look for a missing release
    # object on a tag nobody ever cut. Found 2026-09-17 by GOAL-026's release
    # arm, which asks about the version it is trying to ship.
    if args.tag:
        present = set(version_tags())
        absent = [t for t in args.tag if t not in present]
        if absent:
            for tag in absent:
                print(f"  {tag:12} NOT TAGGED: this checkout carries no such tag")
            print(
                "NOT RELEASED: "
                + ", ".join(absent)
                + " is not tagged here, so there is nothing to ask the service about. "
                "That is not the same as a tag whose release object is missing.",
                file=sys.stderr,
            )
            return 1

    judged = [t for t in tags if _sortable(t) >= _sortable(FIRST_RECORDED)]
    skipped = [t for t in tags if t not in judged]

    dois = recorded_dois()
    owed = owed_in_the_changelog()
    problems: list[str] = []
    # THE FAILING TAGS, not the failing CLAIMS. One tag can contribute two
    # problems, a missing release object and a missing row, and the first
    # writing of the summary subtracted the problem count from the tag count
    # and printed "-1 of 1". A success line that reports a number no run
    # could produce is the defect that is hardest to see, because the line
    # looks right until a failure makes it print.
    failed: set[str] = set()
    for tag in judged:
        doi = dois.get(tag)
        if doi:
            row = f"DOI {doi}"
        elif tag in owed and tag == judged[-1]:
            # THE WINDOW IS ONE RELEASE WIDE, and it was unbounded. The
            # docstring defines it as the one commit between a tag and the
            # row that pays it, and nothing enforced that: a sentence in the
            # change log kept any tag reading RELEASED for as long as the
            # sentence stood. v0.14.0, three releases old and archived
            # nowhere, read RELEASED from the very check written to catch
            # exactly that. Found by the quality and verification lenses of
            # the 0.18.0 round, independently, 2026-09-14.
            #
            # `judged[-1]` is the NEWEST judged tag, which is the only one
            # that can legitimately be inside its window: once a further
            # release has shipped, the debt is not a window any more, it is a
            # release that stopped being citable.
            row = "no DOI row yet, and the change log names it OWED, which is the window"
        elif tag in owed:
            row = (
                "NO DOI ROW. The change log names it owed, but a newer tag has shipped since, "
                "so this is no longer the one-commit window between a tag and the row that "
                "pays it: it is a released version that is not citable"
            )
            problems.append(f"{tag}: {row}")
            failed.add(tag)
        else:
            row = "NO DOI ROW and the change log does not name it owed"
            problems.append(f"{tag}: {row}")
            failed.add(tag)
        if args.offline:
            print(f"  {tag:12} {row}")
            continue
        exists = release_object_exists(tag)
        if exists is True:
            state = "released"
        elif exists is False:
            state = "TAGGED BUT NOT RELEASED: no release object, so nothing minted an archive"
            problems.append(f"{tag}: {state}")
            failed.add(tag)
        else:
            state = "UNKNOWN: the service could not be asked, which is not a pass"
            problems.append(f"{tag}: {state}")
            failed.add(tag)
        print(f"  {tag:12} {state}; {row}")

    if skipped:
        print(f"  not judged, older than {FIRST_RECORDED}: {', '.join(skipped)}")
    if problems:
        print(
            f"RELEASED: {len(judged) - len(failed)} of {len(judged)} tag(s); "
            f"{len(failed)} tag(s) failing on {len(problems)} claim(s)"
        )
        for line in problems:
            print(f"  {line}")
        return 1
    half = "the DOI row only" if args.offline else "the release object and the DOI row"
    print(f"RELEASED: {len(judged)} of {len(judged)} tag(s), judged on {half}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
