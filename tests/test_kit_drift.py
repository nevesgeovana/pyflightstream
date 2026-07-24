"""Tier 1: the vendored shared-process-kit copies match the kit manifest.

The coordination level owns a shared process kit
(``C:\\WORK\\ClaudeProjects\\_private\\kit``); each library carries a DERIVED
copy of every shared artifact, stamped with the kit version and a body
sha256. A change to a shared artifact is made in the kit and re-vendored,
never hand-edited here, because a hand-edit is exactly the drift this level
exists to stop: the gate fix that once sat in one repository while the other
kept the defect it had reported.

This test is the mechanism. For every vendored file it splits the body at the
``END KIT PROVENANCE`` marker, recomputes the sha256, and asserts it equals
the value the kit 0.2.1 manifest declares. A hand-edit changes the body, the
recomputed hash no longer matches, and CI goes red. The fixture is the
manifest itself (the version and hashes this repository vendored); the test
never reaches into the coordination tree at run time, so it needs no
cross-repo filesystem access and cannot deadlock a push.

Two deliberate wrinkles, both documented in the kit ``README.md``:

* The kit version is 0.2.1. ``role_review_gate.py`` carries a 0.2.1 body (the
  heredoc-stripper regression fix, INC-20260724-0912, which the 0.2.0
  promotion had re-forked in); the two S3 side-effect-guard files carry a
  0.2.0 body; the artifacts untouched since S5 keep their 0.1.0 body and
  header. The manifest pins each file to its own hash and body version, so a
  mixed manifest is correct, not drift.
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

# The kit 0.2.1 manifest, verbatim from the kit README.md. Each entry is
# (repo-relative path, declared kit-version, body-sha256). This is the
# fixture: the test asserts the vendored file reproduces it.
MANIFEST: dict[str, tuple[str, str]] = {
    ".claude/hooks/role_review_gate.py": (
        "0.2.1",
        "60f13fa5080a99592c8beb766cfd8b901b38fa638ca15804e6be5f46518f5801",
    ),
    ".claude/hooks/write_attestation.py": (
        "0.1.0",
        "0c6aa3f9bc7e68aadb921463371b0f4a30a3f4bd9da9f1e3915bc48e8f243a91",
    ),
    # The stamped drift-test-of-record for the incident-analyst charter. The
    # runtime agent (.claude/agents/incident-analyst.md) is a derivation of
    # this file, guarded separately below.
    ".claude/tools/incident-analyst.md": (
        "0.1.0",
        "9d2bc1bb38d6c249969cb268ce6e9b778457059d691a87cecda172f83f475eac",
    ),
    ".claude/tools/check_incidents.py": (
        "0.1.0",
        "f6d3430a6d0ee44b4843f7d297a3454ce40d34cd83dc182a2ef840952c5c9c0a",
    ),
    ".claude/tools/snap.sh": (
        "0.1.0",
        "0da13e4da525c1c470dc4429ef6c557a3b74600ad817c534344e999180786383",
    ),
    ".claude/tools/check_plan_kit.py": (
        "0.1.0",
        "4a18d1aa061b92c7fc677c16479730b25cdd6b759625857d4c1720628a5415a6",
    ),
    ".claude/tools/check_plan_kit_mutations.py": (
        "0.1.0",
        "e434e5be6e3c796ab297b0d110e37b58aa213b8199b77367db134f51ed77ed2f",
    ),
    ".claude/tools/check_side_effect_guard.py": (
        "0.2.0",
        "f11972715660cdcda4fd06cd29925276369878eedafefb007e3cbafaf64d3456",
    ),
    ".claude/tools/check_side_effect_guard_mutations.py": (
        "0.2.0",
        "fc5e7fdabd50a7784e53f0e8a636e87ff19e19260c9a711fb05892f78c1ad97f",
    ),
}

# The single file that carries the one permitted per-repo difference.
NORMALIZE_LEDGER_VAR = {".claude/hooks/role_review_gate.py"}


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
    version, want = MANIFEST[rel]
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
    version, want = MANIFEST[rel]
    lines, start = _split_at_marker(_read_lf(REPO / rel))
    fields = _header_fields(lines, start)
    assert fields.get("kit-version") == version, (
        f"{rel}: header kit-version {fields.get('kit-version')!r} != pinned {version!r}"
    )
    assert fields.get("body-sha256") == want, (
        f"{rel}: header body-sha256 {fields.get('body-sha256')!r} != manifest {want!r}"
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
