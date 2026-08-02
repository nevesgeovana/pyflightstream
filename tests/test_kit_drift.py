"""Tier 1: the vendored shared-process-kit copies match the kit manifest.

The coordination level owns a shared process kit, at ``ClaudeCoordinator/kit``
since 2026-07-27 (moved from the coordination ``_private/kit``, now retired).
Each library carries a DERIVED copy of every shared artifact, stamped with the
kit version and a body sha256. A change to a shared artifact is made in the kit
and re-vendored, never hand-edited here, because a hand-edit is exactly the
drift this level exists to stop: the gate fix that once sat in one repository
while the other kept the defect it had reported.

Four of the nine vendored provenance headers still name the retired
``_private/kit`` path. Not because a hashed body forbids the correction: the
``note:`` line is NOT hashed (see below), so it could be corrected at any
time. They are stale for the ordinary reason that they have not been
re-vendored since the path moved, and this repository has chosen to let the
re-vendor carry the correction rather than to touch nine headers by hand. The
five re-vendored since (two at 0.2.3, three at 0.2.4) corrected themselves,
and they did so by a route worth naming, because the kit ``README.md`` still
prescribes the old wording and a re-vendor performed to its letter would have
reproduced the stale pointer: the
``note:`` line sits ABOVE ``END KIT PROVENANCE``, so it is not hashed, and the
kit's own rule is that a vendored copy RESTAMPS it. Writing the current path
there is therefore the prescribed per-copy restamp with a corrected target,
not a hand-edit of a pinned body. The remaining four correct themselves on
their next re-vendor; the kit-side wording fix stays the coordination level's.

This test is the mechanism. For every vendored file it splits the body at the
``END KIT PROVENANCE`` marker, recomputes the sha256, and asserts it equals
the value this repository PINNED when it vendored. A hand-edit changes the
body, the recomputed hash no longer matches, and CI goes red. The fixture is
the manifest itself (the version and hashes this repository vendored); the
test never reaches into the coordination tree at run time, so it needs no
cross-repo filesystem access and cannot deadlock a push.

Four notes on reading the manifest below. The first and the last are the
kit's own wrinkles, documented in its ``README.md``; the middle two are this
repository's record of one promotion and its own caveat about this test.

* The manifest below is MIXED, and that is correct rather than drift: it pins
  each file to its own body hash and body version. One file carries a 0.2.16
  body (``role_review_gate.py``, re-vendored 2026-08-02 for the fail-open
  described below), two carry a 0.2.4 body (``incident-analyst.md`` and
  ``snap.sh``, re-vendored 2026-07-28 for the privacy promotion below), two
  carry a 0.2.3 body (both plan-checker files, re-vendored 2026-07-27 for the
  legacy-id grandfather hardening that this repository's own adoption review
  produced), two carry a 0.2.2 body (both side-effect-guard files), and the
  artifacts untouched since S5 keep their 0.1.0 body. Do not read any single
  version below as the kit's version.
* This repository is DELIBERATELY BEHIND on eight of the nine rows, and the gap
  is measured rather than unknown. Against kit master 0.2.17 on 2026-08-02: six
  of the nine vendored files are behind, and the kit manifest carries 25 further
  rows this repository has never vendored at all, for an adoption surface of 31
  artifacts. Only ``role_review_gate.py`` was taken, because it alone was
  blocking (see the next bullet); absorbing the other thirty was declined as
  scope, not overlooked. The bullet below on what this test cannot see is the
  reason that decision has to be written down somewhere a reader will find it.
* ``role_review_gate.py`` sits at 0.2.16 because the 0.2.4 body it replaced had
  a FAIL-OPEN, ``INC-20260802-1450-shared``: ``_strip_heredocs`` treated an
  unterminated heredoc opener as licence to drop every remaining line, so a
  two-line command whose first line merely MENTIONED ``<<EOF`` in a commit
  message took the real push on the second line with it, and the gate returned
  without requiring an attestation, reading the ledger, or checking for a
  release tag. Measured here before the re-vendor, against the deployed 0.2.4
  body: three reduced reproductions each drew NO DECISION at all while the
  control (a bare unattested push) denied; on the 0.2.16 body all four deny and
  neither pinned heredoc behaviour moved. The permanent cases are in
  ``tests/test_push_gate.py``.
* The 0.2.4 promotion was made for privacy, and it is two changes of very
  different weight rather than one. It mattered here because
  ``.claude/tools/snap.sh`` is TRACKED and this remote is public, so a hashed
  kit body was publishing a personal name, a personal email address and a
  personal user-profile path. Removing them from HEAD stops them spreading; it
  does not unpublish them.

  The first change is text only. Three first-name occurrences in the gate's
  deny messages and one in the analyst charter became "the author". For the
  gate this is verified rather than asserted: every replacement sits inside a
  deny ``reason``/``remedy`` string literal, none in a condition, a return
  value, a constant set or a comparison, so no allow or deny decision moved.

  The second change is behaviour, and calling the whole promotion
  behaviour-neutral would be false. ``snap.sh`` stopped setting the snapshot
  repositories' git identity from two literals and now reads the ambient git
  configuration with a neutral fallback, and the shared-ledger tree stopped
  being a literal and became ``COORD_SHARED_LEDGER_TREE``. Its comment says an
  unset variable means the tree is "simply skipped". That is NOT what happens
  once the snapshot repository exists, which is the state of the machine this
  tool runs on: ``ensure()`` returns early on the git-dir test before it ever
  tests the tree, so the run reports ``snapshot taken (0 file(s))`` after four
  git failures. A recovery tool reporting a snapshot it did not take is the
  defect, the body is hash-pinned so it is not correctable here, and it is
  registered as PLN-20260728-1615-snap-shared-tree-false-success against the
  coordination level that owns the master.
* What this test CANNOT see, stated because its green is easily over-read: it
  detects a hand-edit and it does not detect falling behind. The inlined
  manifest is a frozen copy by design, so a kit promotion this repository has
  not taken leaves every assertion here passing. That is exactly how the
  0.2.2-to-0.2.3 lag stood green for three days until the coordination level
  reported it (``PLN-20260727-1707-kit-lag-0-2-3``). Whether the libraries
  gain a hub-reachable staleness check is the author's design call and is
  deliberately not decided by this test.
* ``role_review_gate.py`` USED to carry the one permitted per-repo difference,
  and no longer does. The incident-ledger environment variable was
  ``PYFS_INCIDENT_LEDGER`` here and ``ITACA_INCIDENT_LEDGER`` in the canonical
  body, and this test normalized that single token before hashing. Kit 0.2.8
  retired the split under the author decision ``LEDGER-ENVVAR``: every
  workspace now reads ONE name, ``COORD_INCIDENT_LEDGER``, so the vendored body
  and the master differ in NOTHING and the normalization is gone. The two
  constants survive because the incident-analyst derivation below still needs
  them; that artifact keeps its own per-repo substitution.

  The rename is not cosmetic and the reason belongs here rather than only in a
  changelog: an ABSENT variable used to mean "the check does not apply" and now
  DENIES. That is what let the coordination repository push past a blocking
  incident it had itself written, resolving a variable that had never existed.
  A guard that reads its own missing configuration as permission is not a
  guard. The practical consequence for a fresh clone is that
  ``COORD_INCIDENT_LEDGER`` must be exported BEFORE this body is in place, not
  after: this file is a PreToolUse hook on every shell command, so a copy
  vendored ahead of the variable denies everything until it is set.
  ``ITACA_INCIDENT_LEDGER`` below is therefore a historical name kept for the
  analyst derivation alone, and is not what the gate reads.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

CANONICAL_LEDGER_VAR = "ITACA_INCIDENT_LEDGER"
REPO_LEDGER_VAR = "PYFS_INCIDENT_LEDGER"

# The vendored manifest, mixed body versions by design (see the module
# docstring). Each entry is (repo-relative path, declared kit-version,
# body-sha256, note target). The kit-version and the body-sha256 come verbatim
# from the kit README.md and are the fixture the body assertions use.
#
# The note target is this repository's own record, NOT the kit's. The `note:`
# line sits above END KIT PROVENANCE, so it is outside the hashed body and no
# hash can see it; it is also the one field a vendored copy is required to
# restamp. Recording the expected target here is what makes the difference
# between a prescribed restamp and an undetected hand-edit of the header: the
# files above that still name the retired `_private/kit` path record that
# fact, so their next re-vendor changes this table deliberately rather than
# invisibly. The count lives in the module docstring and deliberately not
# here, because carrying it twice is how it went stale the last time.
MANIFEST: dict[str, tuple[str, str, str]] = {
    ".claude/hooks/role_review_gate.py": (
        "0.2.16",
        "8dd77671321f5d4f76d44ee9ae5ff5eb72288586ba20a31251039fc5e28d8f3a",
        "ClaudeCoordinator/kit",
    ),
    ".claude/hooks/write_attestation.py": (
        "0.1.0",
        "0c6aa3f9bc7e68aadb921463371b0f4a30a3f4bd9da9f1e3915bc48e8f243a91",
        "_private/kit",
    ),
    # The stamped drift-test-of-record for the incident-analyst charter. The
    # runtime agent (.claude/agents/incident-analyst.md) is a derivation of
    # this file, guarded separately below.
    ".claude/tools/incident-analyst.md": (
        "0.2.4",
        "891fa0bce811aade6fe58494d99db2f048987871cf5487fda77d9ff180ef7beb",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_incidents.py": (
        "0.1.0",
        "f6d3430a6d0ee44b4843f7d297a3454ce40d34cd83dc182a2ef840952c5c9c0a",
        "_private/kit",
    ),
    ".claude/tools/snap.sh": (
        "0.2.4",
        "7c9573aabe398576dd00c2a8a5acf0312fa289ff497ae56681225954d843f4cd",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_plan_kit.py": (
        "0.2.3",
        "386ce05647b5e2fa194a0aaf50c334b6ad77c2e7eef4800bcb63ce3f36e32786",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_plan_kit_mutations.py": (
        "0.2.3",
        "410db0d4003dcb085b87eba4af35686d490aa2974d67606ea509ba25bcf6fe8b",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_side_effect_guard.py": (
        "0.2.2",
        "ba9007941dcc44887e31d70dc74be8efe409f51a249d2b79398e66c276e9810c",
        "_private/kit",
    ),
    ".claude/tools/check_side_effect_guard_mutations.py": (
        "0.2.2",
        "af5674911c06e5c67c5a178374c6c79245be25c8e9d1eb742667fc2f4bd8decb",
        "_private/kit",
    ),
}

# Files whose body carries a per-repo substitution and must be normalized back
# to the canonical name before hashing. EMPTY since the 0.2.16 gate re-vendor:
# kit 0.2.8 gave every workspace one ledger variable, so no vendored BODY
# differs from its master any more. Kept as a named, empty set rather than
# deleted, because the mechanism is what makes the "nothing else may differ"
# rule checkable, and the next artifact that needs a per-repo token should
# rejoin this set rather than reinvent the normalization.
NORMALIZE_LEDGER_VAR: set[str] = set()

# The `canonical-source:` line of each vendored copy, pinned as a sha256
# prefix of its value. Like `note:` it sits above the hash boundary and no
# body assertion reaches it, but unlike `note:` it carries an INVARIANT: it
# is where a copy records that its body was built for the kit rather than
# adapted from the AGPL predecessor (hard invariant 2). Fingerprinted rather
# than quoted so this table stays one line per file.
CANONICAL_SOURCE: dict[str, str] = {
    ".claude/hooks/role_review_gate.py": "716d08ccad269a20",
    ".claude/hooks/write_attestation.py": "eec6cd09a22cd4ed",
    ".claude/tools/incident-analyst.md": "5d082c68aa0e7a75",
    ".claude/tools/check_incidents.py": "e3cd74c877e000cb",
    ".claude/tools/snap.sh": "49d402df3ad13508",
    ".claude/tools/check_plan_kit.py": "8c7a308d981c0d78",
    ".claude/tools/check_plan_kit_mutations.py": "cbc57a022fe9debe",
    ".claude/tools/check_side_effect_guard.py": "2ee09438a484dd93",
    ".claude/tools/check_side_effect_guard_mutations.py": "3dcc0997ac083e4b",
}


def _read_lf(path: Path) -> str:
    """Read a file with CRLF and lone CR normalized to LF, as the kit hashes."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _split_at_marker(text: str) -> tuple[list[str], int]:
    """Return (lines, body-start index).

    The body starts on the line AFTER the first ``END KIT PROVENANCE`` line,
    skipping a bare ``-->`` comment terminator when present (the Markdown
    stamp closes its HTML comment on the line after the marker).
    """
    lines = text.split("\n")
    marker = next((i for i, line in enumerate(lines) if "END KIT PROVENANCE" in line), None)
    assert marker is not None, "no END KIT PROVENANCE marker in vendored kit file"
    start = marker + 1
    if start < len(lines) and lines[start].strip() == "-->":
        start += 1
    return lines, start


def _header_fields(lines: list[str], marker_body_start: int) -> dict[str, str]:
    """Parse the provenance header (comment lines before the body) as a map."""
    fields: dict[str, str] = {}
    for line in lines[:marker_body_start]:
        stripped = line.lstrip("#").strip()
        if stripped in ("<!--", "-->") or "END KIT PROVENANCE" in stripped:
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _body_sha256(rel: str, text: str) -> str:
    lines, start = _split_at_marker(text)
    body = "\n".join(lines[start:])
    if rel in NORMALIZE_LEDGER_VAR:
        body = body.replace(REPO_LEDGER_VAR, CANONICAL_LEDGER_VAR)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("rel", sorted(MANIFEST))
def test_vendored_kit_body_matches_manifest(rel: str) -> None:
    """The recomputed body sha256 equals the manifest value for this repo."""
    _version, want, _note_target = MANIFEST[rel]
    path = REPO / rel
    assert path.is_file(), f"vendored kit file missing: {rel}"
    text = _read_lf(path)
    got = _body_sha256(rel, text)
    assert got == want, (
        f"{rel} body sha256 {got} != manifest {want}. A vendored kit copy was "
        "hand-edited, or the file drifted from the kit. Re-vendor from the "
        "coordination kit master; do not edit the copy here."
    )


@pytest.mark.parametrize("rel", sorted(MANIFEST))
def test_vendored_kit_header_declares_the_pinned_version_and_hash(rel: str) -> None:
    """The stamp header agrees with the manifest: version and body-sha256."""
    version, want, _note_target = MANIFEST[rel]
    lines, start = _split_at_marker(_read_lf(REPO / rel))
    fields = _header_fields(lines, start)
    assert fields.get("kit-version") == version, (
        f"{rel}: header kit-version {fields.get('kit-version')!r} != pinned {version!r}"
    )
    assert fields.get("body-sha256") == want, (
        f"{rel}: header body-sha256 {fields.get('body-sha256')!r} != manifest {want!r}"
    )


@pytest.mark.parametrize("rel", sorted(MANIFEST))
def test_vendored_kit_note_points_where_the_manifest_records(rel: str) -> None:
    """The unhashed ``note:`` line still has a recorded expected value.

    Without this the header carries fields no assertion reaches, and the
    2026-07-27 re-vendor is the proof that they change: it corrected two notes
    from the retired ``_private/kit`` path to the current one. That correction
    is the prescribed per-copy restamp, and nothing distinguished it from an
    arbitrary hand-edit of an unhashed field. Recording the target makes the
    next such change a deliberate manifest edit.
    """
    _version, _want, note_target = MANIFEST[rel]
    lines, start = _split_at_marker(_read_lf(REPO / rel))
    note = _header_fields(lines, start).get("note", "")
    assert note_target in note, (
        f"{rel}: the provenance note does not name {note_target!r}. Either the "
        "copy was re-vendored (update this manifest row deliberately) or the "
        f"header was hand-edited. note={note!r}"
    )


@pytest.mark.parametrize("rel", sorted(CANONICAL_SOURCE))
def test_vendored_kit_canonical_source_is_unchanged(rel: str) -> None:
    """The unhashed ``canonical-source:`` line is pinned by fingerprint.

    This is the field that records where a vendored body CAME FROM, and it is
    the one header line with an invariant behind it: hard invariant 2 says the
    command emitter and everything around it is specified from the manual and
    from probe evidence, never adapted from the AGPL predecessor. A line
    reading "BUILT for the kit" rewritten to name any other lineage is a claim
    about provenance that no other assertion in this file can see, because the
    header sits above the hash boundary.

    Pinned as a sha256 prefix of the value rather than as the value itself, so
    the manifest above stays readable and this table stays one line per file.
    A re-vendor that legitimately changes the line updates the fingerprint
    deliberately, which is the same contract the note targets carry.
    """
    lines, start = _split_at_marker(_read_lf(REPO / rel))
    value = _header_fields(lines, start).get("canonical-source", "")
    assert value, f"{rel}: the provenance header lost its canonical-source line"
    got = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    assert got == CANONICAL_SOURCE[rel], (
        f"{rel}: canonical-source changed (fingerprint {got}, pinned "
        f"{CANONICAL_SOURCE[rel]}). This line records the body's LINEAGE and "
        "is not covered by the body hash. If a re-vendor changed it, update "
        "this table deliberately; if nothing was re-vendored, the header was "
        f"hand-edited. value={value!r}"
    )


def test_runtime_incident_analyst_is_the_derivation_of_record() -> None:
    """The loaded agent is exactly the of-record body with the stamp removed
    and the one ledger variable substituted, so the two cannot silently
    diverge.

    The agent loader wants YAML frontmatter on line 1, so the runtime file at
    .claude/agents/incident-analyst.md cannot carry the HTML-comment stamp;
    it is materialized from the stamped .claude/tools/incident-analyst.md by
    stripping the comment and renaming the ledger variable to this repo's.
    Without this check a hand-edit of the runtime agent would escape the
    drift test, which only reads the of-record.
    """
    of_record = _read_lf(REPO / ".claude/tools/incident-analyst.md")
    lines, start = _split_at_marker(of_record)
    expected = "\n".join(lines[start:]).replace(CANONICAL_LEDGER_VAR, REPO_LEDGER_VAR)
    runtime = _read_lf(REPO / ".claude/agents/incident-analyst.md")
    assert runtime == expected, (
        "the runtime incident-analyst agent is not the derivation of the "
        "stamped of-record (.claude/tools/incident-analyst.md). Re-materialize "
        "it: strip the provenance comment and substitute "
        f"{CANONICAL_LEDGER_VAR} -> {REPO_LEDGER_VAR}."
    )
    assert runtime.splitlines()[0].strip() == "---", "runtime agent lost its frontmatter"
    assert CANONICAL_LEDGER_VAR not in runtime, "runtime agent still names the itaca ledger var"
