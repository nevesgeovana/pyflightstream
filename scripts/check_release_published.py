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
    """Return the tags the change log's Unreleased section names as owed a row."""
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(r"^##\s*\[Unreleased\][^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not match:
        return set()
    body = match.group(1)
    owed = set()
    for line in body.splitlines():
        if not re.search(r"archive|DOI|identifier", line, re.I):
            continue
        owed.update(re.findall(r"\bv\d[\w.\-]*", line))
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
        print("no version tag in this checkout, so there is nothing to judge")
        return 0
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
        elif tag in owed:
            row = "no DOI row yet, and the change log names it OWED, which is the window"
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
