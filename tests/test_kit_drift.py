"""Tier 1: the vendored shared-process-kit copies match the kit manifest.

The coordination level owns a shared process kit, at ``ClaudeCoordinator/kit``
since 2026-07-27 (moved from the coordination ``_private/kit``, now retired).
Each library carries a DERIVED copy of every shared artifact, stamped with the
kit version and a body sha256. A change to a shared artifact is made in the kit
and re-vendored, never hand-edited here, because a hand-edit is exactly the
drift this level exists to stop: the gate fix that once sat in one repository
while the other kept the defect it had reported.

Seven of the nine vendored provenance headers still name the retired
``_private/kit`` path. They are hash-pinned bodies, so correcting them here
would be the hand-edit just forbidden. The two re-vendored at 0.2.3 corrected
themselves, and they did so by a route worth naming, because the kit
``README.md`` still prescribes the old wording and a re-vendor performed to
its letter would have reproduced the stale pointer: the ``note:`` line sits
ABOVE ``END KIT PROVENANCE``, so it is not hashed, and the kit's own rule is
that a vendored copy RESTAMPS it. Writing the current path there is therefore
the prescribed per-copy restamp with a corrected target, not a hand-edit of a
pinned body. The remaining seven correct themselves on their next re-vendor;
the kit-side wording fix stays the coordination level's.

This test is the mechanism. For every vendored file it splits the body at the
``END KIT PROVENANCE`` marker, recomputes the sha256, and asserts it equals
the value this repository PINNED when it vendored. A hand-edit changes the
body, the recomputed hash no longer matches, and CI goes red. The fixture is
the manifest itself (the version and hashes this repository vendored); the
test never reaches into the coordination tree at run time, so it needs no
cross-repo filesystem access and cannot deadlock a push.

Two deliberate wrinkles, both documented in the kit ``README.md``:

* The manifest below is MIXED, and that is correct rather than drift: it pins
  each file to its own body hash and body version. Two files carry a 0.2.3
  body (both plan-checker files, re-vendored 2026-07-27 for the legacy-id
  grandfather hardening that this repository's own adoption review produced),
  three carry a 0.2.2 body (the gate ``role_review_gate.py`` deny-message
  taxonomy and both side-effect-guard files), and the artifacts untouched
  since S5 keep their 0.1.0 body. Do not read any single version below as the
  kit's version.
* What this test CANNOT see, stated because its green is easily over-read: it
  detects a hand-edit and it does not detect falling behind. The inlined
  manifest is a frozen copy by design, so a kit promotion this repository has
  not taken leaves every assertion here passing. That is exactly how the
  0.2.2-to-0.2.3 lag stood green for three days until the coordination level
  reported it (``PLN-20260727-1707-kit-lag-0-2-3``). Whether the libraries
  gain a hub-reachable staleness check is the author's design call and is
  deliberately not decided by this test.
* ``role_review_gate.py`` carries the ONE permitted per-repo difference: the
  incident-ledger environment variable is ``PYFS_INCIDENT_LEDGER`` here and
  ``ITACA_INCIDENT_LEDGER`` in the canonical (itaca) body the manifest hash
  is computed over. The test normalizes that single token back to the
  canonical name before hashing, which is why the gate body still reproduces
  the manifest value while the runtime file reads the right variable for this
  repository. Nothing else in a vendored body may differ.
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
# body-sha256, note target). The first three come verbatim from the kit
# README.md and are the fixture the body assertions use.
#
# The note target is this repository's own record, NOT the kit's. The `note:`
# line sits above END KIT PROVENANCE, so it is outside the hashed body and no
# hash can see it; it is also the one field a vendored copy is required to
# restamp. Recording the expected target here is what makes the difference
# between a prescribed restamp and an undetected hand-edit of the header: the
# seven files still naming the retired `_private/kit` path record that fact,
# so their next re-vendor changes this table deliberately rather than
# invisibly.
MANIFEST: dict[str, tuple[str, str, str]] = {
    ".claude/hooks/role_review_gate.py": (
        "0.2.2",
        "762297b3d7752710aa6146719e8c4540b6b05bbf851f71f5a66105b9db58134e",
        "_private/kit",
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
        "0.1.0",
        "9d2bc1bb38d6c249969cb268ce6e9b778457059d691a87cecda172f83f475eac",
        "_private/kit",
    ),
    ".claude/tools/check_incidents.py": (
        "0.1.0",
        "f6d3430a6d0ee44b4843f7d297a3454ce40d34cd83dc182a2ef840952c5c9c0a",
        "_private/kit",
    ),
    ".claude/tools/snap.sh": (
        "0.1.0",
        "0da13e4da525c1c470dc4429ef6c557a3b74600ad817c534344e999180786383",
        "_private/kit",
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

# The single file that carries the one permitted per-repo difference.
NORMALIZE_LEDGER_VAR = {".claude/hooks/role_review_gate.py"}

# The `canonical-source:` line of each vendored copy, pinned as a sha256
# prefix of its value. Like `note:` it sits above the hash boundary and no
# body assertion reaches it, but unlike `note:` it carries an INVARIANT: it
# is where a copy records that its body was built for the kit rather than
# adapted from the AGPL predecessor (hard invariant 2). Fingerprinted rather
# than quoted so this table stays one line per file.
CANONICAL_SOURCE: dict[str, str] = {
    ".claude/hooks/role_review_gate.py": "e2ad526f8de01276",
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
