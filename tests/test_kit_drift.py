"""Tier 1: the vendored shared-process-kit copies match the kit manifest.

The coordination level owns a shared process kit, at ``ClaudeCoordinator/kit``
since 2026-07-27 (moved from the coordination ``_private/kit``, now retired).
Each library carries a DERIVED copy of every shared artifact, stamped with the
kit version and a body sha256. A change to a shared artifact is made in the kit
and re-vendored, never hand-edited here, because a hand-edit is exactly the
drift this level exists to stop: the gate fix that once sat in one repository
while the other kept the defect it had reported.

NO vendored provenance header names the retired ``_private/kit`` path any
more. ``check_incidents.py`` was the last one, restamped on 2026-08-18
(OPS-2013.04); every other row was re-vendored or vendored fresh on
2026-08-11 and carried the current target already.

The restamp is the prescribed per-copy correction rather than a hand-edit of
a pinned body, and the distinction is the reason this paragraph is long: the
``note:`` line sits ABOVE ``END KIT PROVENANCE``, so it is not hashed, and the
kit's own rule is that a vendored copy RESTAMPS it. Nothing about the hashed
body changed, and ``check_incidents.py`` still pins the 0.1.0 body it was
vendored from. This repository had previously chosen to let the next
re-vendor carry the correction, which is what left one pointer aimed at a
directory retired on 2026-07-27 for three weeks; the pointer's cost is paid
by the next editor who follows it, not by the row that carries it, so waiting
had nobody's interest behind it.

That the correction is now MEASURED rather than remembered is the other half
of the same item, and it needs two assertions rather than one because the kit
``README.md`` still prescribes the old wording: a re-vendor performed to its
letter reproduces the stale pointer, and would do so while updating this
file's manifest row in the same edit, so a test pinning the target alone
follows the mistake into the manifest.
``test_no_vendored_note_names_the_retired_kit_path`` forbids the retired
value in any note whatever the manifest says, and
``test_every_manifest_note_target_is_the_live_kit_path`` forbids pinning it
here. The kit-side wording fix stays the coordination level's.

The retired path survives in tracked files as HISTORY, and that is correct
rather than residue: this docstring, the comment above the manifest, the
2026-07-27 restamp precedent below, two lines in ``tests/test_house_style.py``
and one in ``.claude/tools/check_plan_kit_mutations.py`` (which names it as
the absolute path that checker must NOT use). Each names it as retired, or as
forbidden, in its own sentence. Deleting them would destroy the record of why
the path is retired, which is why the guards above read the ``note:`` FIELD
of a stamped file and never count occurrences in a tree.

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
  each file to its own body hash and body version, spanning 0.1.0 to 0.2.22.
  Do not read any single version below as the kit's version, and do not
  "tidy" the spread: a row sits at the version of the master it was vendored
  from, and most masters have not moved since.
* THE ADOPTION GAP IS CLOSED, and this file no longer carries the count.
  PFS-11 (2026-08-11) took the CI arm, the policy rows and the drifted
  bodies; PFS-12, the same night, took everything else on the author's
  decision to end the divergence in one night rather than one row per lane.
  What remains absent is TWO artifacts and it is a DECISION rather than a
  residue: ``release_caller.yml`` and ``release_gate.yml``, declined because
  this repository's ``release.yml`` is a single workflow with no
  ``workflow_call``, has published v0.4.0 through v0.7.0, and rewriting the
  one release path that is proven to work is not a night job. The reason
  lives in CLAUDE.md. It is written as DECIDED-OUT rather than not-yet,
  because failing to distinguish those two is what kept COORD-02 open from
  2026-08-02.

  The counts themselves are asserted rather than narrated, by
  ``test_the_manifest_agrees_with_the_recorded_adoption_residue`` (the row
  count, against ``EXPECTED_ROWS``),
  ``test_the_decided_out_artifacts_are_absent_and_stay_absent`` (the two
  declined ones, against ``DECIDED_OUT``) and
  ``test_every_stamped_file_in_the_tree_has_a_manifest_row``. Prose counts in
  this docstring went stale twice; measurements do not. Note that this
  paragraph made the same claim on 2026-08-11 while only ONE of those three
  tests existed and neither constant did, which is why the sentence now names
  the constants a reader can grep for.
* ``role_review_gate.py`` sits at 0.2.18 for the CI-GREEN TAG RULE: a
  release-grade push is refused unless the commit each version tag names has a
  concluded, successful CI result on the remote, with red, running, unknown and
  unreachable all denying. It replaced a REPOSITORY-OWNED bridge hook
  (``.claude/hooks/ci_release_gate.py``) that answered the same question, and
  the two were never allowed to coexist: the bridge, its wiring in
  ``.claude/settings.json``, its test and its mutation battery were deleted in
  the same commit as this row, because deleting earlier leaves a window in
  which nothing asks CI anything and deleting later leaves two guards answering
  one question with no rule for which one this repository believes.

  The 0.2.16 body this replaced had itself closed a FAIL-OPEN,
  ``INC-20260802-1450-shared``: ``_strip_heredocs`` treated an unterminated
  heredoc opener as licence to drop every remaining line, so a two-line command
  whose first line merely MENTIONED ``<<EOF`` in a commit message took the real
  push on the second line with it, and the gate returned without requiring an
  attestation, reading the ledger, or checking for a release tag. The permanent
  cases are in ``tests/test_push_gate.py``, and they still pass on the 0.2.18
  body.
* ``write_attestation.py`` moved 0.1.0 to 0.2.15 and that row is not routine.
  Kit 0.2.9 made the writer REFUSE to write while tracked files carry
  uncommitted changes, from ``INC-20260729-2355-itaca``: a reviewer agent
  holding ``Bash`` restored tracked files while a lane held uncommitted review
  fixes, silently reverting two of nine, and the attestation that followed was
  TRUE when written and FALSE about the tree it covered. This repository sat at
  0.1.0 for the whole time that guard existed elsewhere, so it was possible
  here to attest over a tree that is not the tree the attestation describes.
  Nothing was observed going wrong; the exposure is what was reported, and this
  row is what closes it.
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
  being a literal and became ``COORD_SHARED_LEDGER_TREE``. The 0.2.4 body's
  comment said an unset variable meant the tree was "simply skipped", and that
  was NOT what happened once the snapshot repository existed, which is the
  state of the machine this tool runs on: ``ensure()`` returned early on the
  git-dir test before it ever tested the tree, so the run reported
  ``snapshot taken (0 file(s))`` after four git failures. A recovery tool
  reporting a snapshot it did not take was the defect, and it was registered as
  PLN-20260728-1615-snap-shared-tree-false-success against the coordination
  level that owns the master.

  CLOSED HERE by taking the 0.2.5 body on 2026-08-11: ``ensure()`` now tests
  the work tree FIRST and only then takes the already-exists shortcut, with the
  reversal named in its own comment as the 2026-07-28 defect. The row was
  available from 0.2.5 and this repository was the thing holding it up, which
  is what the "cannot see falling behind" bullet below is about.
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
  and the master differ in NOTHING and the normalization is gone.

  As of the 0.2.11 ``incident-analyst.md`` body vendored on 2026-08-11, the LAST
  consumer of the split is gone too. That charter used to name
  ``ITACA_INCIDENT_LEDGER`` and the runtime derivation renamed it; the 0.2.11
  body names ``COORD_INCIDENT_LEDGER`` and contains ZERO occurrences of either
  per-repo name, so the substitution below is now a measured NO-OP and the
  runtime agent equals the of-record body byte for byte. The two constants and
  the substitution survive as MECHANISM, not as live behaviour, and the
  derivation test says so explicitly rather than passing an assertion nothing
  can reach. The practical consequence is documented in CLAUDE.md: this repository
  no longer reads ``PYFS_INCIDENT_LEDGER`` anywhere, so it was removed from the
  machine-configuration list in the same commit.

  The rename is not cosmetic and the reason belongs here rather than only in a
  changelog: an ABSENT variable used to mean "the check does not apply" and now
  DENIES. That is what let the coordination repository push past a blocking
  incident it had itself written, resolving a variable that had never existed.
  A guard that reads its own missing configuration as permission is not a
  guard. The practical consequence for a fresh clone is that
  ``COORD_INCIDENT_LEDGER`` must be exported BEFORE this body is in place, not
  after: this file is a PreToolUse hook on every shell command, so a copy
  vendored ahead of the variable denies everything until it is set.
  ``ITACA_INCIDENT_LEDGER`` below is therefore a historical name, kept so the
  derivation can assert its own no-op, and is not what the gate reads.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

CANONICAL_LEDGER_VAR = "ITACA_INCIDENT_LEDGER"
REPO_LEDGER_VAR = "PYFS_INCIDENT_LEDGER"

#: Where the shared process kit lived until 2026-07-27, and where it has not
#: lived since. A provenance ``note:`` naming it sends the next editor to a
#: directory that does not exist, which is the whole cost of the field being
#: unhashed: no body assertion can see it.
RETIRED_KIT_PATH = "_private/kit"

#: Where it lives now, and the only target a ``note:`` may name.
LIVE_KIT_PATH = "ClaudeCoordinator/kit"

# The vendored manifest, mixed body versions by design (see the module
# docstring). Each entry is (repo-relative path, declared kit-version,
# body-sha256, note target). The kit-version and the body-sha256 come verbatim
# from the kit README.md and are the fixture the body assertions use.
#
# The note target is this repository's own record, NOT the kit's. The `note:`
# line sits above END KIT PROVENANCE, so it is outside the hashed body and no
# hash can see it; it is also the one field a vendored copy is required to
# restamp. Recording the expected target here is what makes the difference
# between a prescribed restamp and an undetected hand-edit of the header: a
# copy whose note moves changes this table deliberately rather than
# invisibly. Every row records `ClaudeCoordinator/kit` since 2026-08-18, and
# that is asserted rather than eyeballed, by
# `test_every_manifest_note_target_is_the_live_kit_path`, so a row cannot
# quietly go back to pinning the retired directory. No count lives here: the
# one that used to went stale the last time it was carried twice.
MANIFEST: dict[str, tuple[str, str, str]] = {
    ".claude/hooks/role_review_gate.py": (
        "0.2.18",
        "acd1766cc0425036a96ec825ecf0f1e50660101d7763f97639e31dd088314ada",
        "ClaudeCoordinator/kit",
    ),
    ".claude/hooks/write_attestation.py": (
        "0.2.15",
        "6c70a673f88d0eebffcdbc048e90db7e1f064ec6af0e49d0b75b517435f982ec",
        "ClaudeCoordinator/kit",
    ),
    # The CI-state pair, vendored 2026-08-11 in the SAME commit as the 0.2.18
    # gate above and not a row later. That gate RUNS this body as a
    # subprocess on a release-grade push and treats its absence as a refusal,
    # so a gate vendored without it denies every version-tag push with
    # `[ci-config]` and the cause reads as a gate defect. `_ci_state_body`
    # looks beside the gate FIRST, which is why both sit in `.claude/hooks/`
    # rather than beside the other tools.
    ".claude/hooks/ci_state.py": (
        "0.2.18",
        "39977e44aae1cb4116fb2bce3b672ac21b03ec3a5d75f64244eb70eb2f89b3ab",
        "ClaudeCoordinator/kit",
    ),
    ".claude/hooks/ci_state_mutations.py": (
        "0.2.18",
        "7e1135337732252f7afffc5c7367769035e54bbe06a7d31df7dcfd7e2a362746",
        "ClaudeCoordinator/kit",
    ),
    # The stamped drift-test-of-record for the incident-analyst charter. The
    # runtime agent (.claude/agents/incident-analyst.md) is a derivation of
    # this file, guarded separately below.
    ".claude/tools/incident-analyst.md": (
        "0.2.11",
        "e61e50c5f15543b9edbc6e19e319cf5ea742a231b9fbe3efbacc32a91754229e",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_incidents.py": (
        "0.1.0",
        "f6d3430a6d0ee44b4843f7d297a3454ce40d34cd83dc182a2ef840952c5c9c0a",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/snap.sh": (
        "0.2.5",
        "0835e6ae1bd43d05e213a88552bcd94a1b91ebec946f9dabb5411d7595b265d1",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_plan_kit.py": (
        "0.2.10",
        "a6eca8d542e6189b6b14cde0d4eb92e3f2850f8a21b3dd26a8fc30c06829c39c",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_plan_kit_mutations.py": (
        "0.2.10",
        "19e0082627371279642723f35d7f78af0e59577eda3ff751cc658332dc8151ad",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_side_effect_guard.py": (
        "0.2.19",
        "0e8c7315dd316570e44a294faefabda7971c9c7a228e5c7ac4b48dbee7aec30e",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_side_effect_guard_mutations.py": (
        "0.2.19",
        "67321ce237a4314a988424cff2b7bac22bc9eba6db9862806c66127c606b7bc9",
        "ClaudeCoordinator/kit",
    ),
    # ---- PFS-12, the review process -------------------------------------
    ".claude/tools/check_review_rounds.py": (
        "0.2.16",
        "b09fdec02dc0674a540bb5429c6343a8d4b7747fc286232dcb54f9b6e4508c4e",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_review_rounds_mutations.py": (
        "0.2.16",
        "9da4b72e42fa1369d5c55c114a6096336001a1f905dbea5d69f6627501d81e26",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/review-policy.md": (
        "0.2.16",
        "e0617a4f6f4a70de5dfe55a66e38efc2faaf1e312a4e543c7f6a21e10f1bbf6f",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/review_runner.py": (
        "0.2.17",
        "f906c6c92b3b504ade3e4defcfe03803925b33f66128acf35101800bfab0025c",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/detached_gate.py": (
        "0.2.17",
        "86ac1759c867c6a215e9ccc44779bd4e4954efa058c54b1b3e05cbc3e70831f7",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/budget_isolation.py": (
        "0.2.17",
        "59fb39d9fdb814455ea9a5f8009fb466e1e0fe5b02a02b37c44b4f721d2a6d96",
        "ClaudeCoordinator/kit",
    ),
    # ---- PFS-12, the push and release boundary --------------------------
    # Beside the gate it proves, for the same reason as the ci_state pair.
    ".claude/hooks/role_review_gate_mutations.py": (
        "0.2.18",
        "fe9ecec7baed9a488a7609f9daab0465f4a35798b282435600a5720062ca791d",
        "ClaudeCoordinator/kit",
    ),
    # The stamped of-record for the version-control skill. The DEPLOYED copy
    # (.claude/skills/version-control/SKILL.md) is its body alone, guarded
    # separately below, exactly as incident-analyst.md is.
    ".claude/tools/version-control.md": (
        "0.2.21",
        "a4a219dea812abef16cfed55cac02a83d2f7d1d1525238cc9ee87bd46400ec59",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_release_gate.py": (
        "0.2.15",
        "465caa08e9ce041f3fc359b41701fffcb649ec223a194a533c8d89c8c593f6a2",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_release_gate_mutations.py": (
        "0.2.15",
        "c03575afa540d63c73a75209c8a1521950f53a6a57c0c66cc2f00a3f0f3c6d39",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/prepush_receipt.py": (
        "0.2.16",
        "e44bde8efa27e0bed50db5e10903871936d688c55d833f4c707f29e3ec67aa94",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/prepush_receipt_mutations.py": (
        "0.2.16",
        "228d9e359c55a0d14f2e890b7130d405d279a63273b5d6710b429844af58f633",
        "ClaudeCoordinator/kit",
    ),
    # ---- PFS-12, the evidence and shipping surface ----------------------
    ".claude/tools/check_shipped_surface.py": (
        "0.2.18",
        "f5dffb534da98061352a941cf5e9ca1de907afc4b0fcf059a7fe7d0a4b33a49b",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_shipped_surface_mutations.py": (
        "0.2.18",
        "09b94846024e803116f2308a6aecccc6d70e91da021104fa459ef06c0d486daa",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_probe_closure.py": (
        "0.2.7",
        "5b4a76ea8e94d6185cd200d0f0324e6501967d1d959c94e5a0e0f31019c142a2",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_probe_closure_mutations.py": (
        "0.2.7",
        "59f3f3c120d7b834bae78b047b2e76d638952a4fb749783b78caba9214767b9c",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_citations.py": (
        "0.2.17",
        "e295e4781f0f073caa90ea4920b09b597042824ccb534008c85550910672d395",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_citations_mutations.py": (
        "0.2.16",
        "97a46d08ea2b39fe13403048f22d96f9f4189af768ac2483f037bcafbf0d32aa",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_version_identity.py": (
        "0.2.6",
        "d9fd719a92bc82cd8c81ab60888bcae4eeed320af89bced74b2602350afe68bd",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_version_identity_mutations.py": (
        "0.2.6",
        "49f0dd3c2dd3ef257761ecbac32c5c0d3f56937f5d735080040843f6aeebf58a",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_spawn_env.py": (
        "0.2.16",
        "b5db024d0e110f379bc9c019ed2ef117e14a952b95895593d81a2e394a3c7619",
        "ClaudeCoordinator/kit",
    ),
    ".claude/tools/check_spawn_env_mutations.py": (
        "0.2.16",
        "133ffcab519c483d598aa6ab9cb67feeb22546b4b2a85aaa0f063851646d713b",
        "ClaudeCoordinator/kit",
    ),
    # ---- PFS-12, the execution guard, vendored and wired LAST ------------
    # At 0.2.22 rather than the 0.2.20 the routing brief named: the kit
    # promoted this pair twice while this lane ran, both times on defects the
    # sister library found within an hour of the artifact being offered to it.
    # 0.2.22 is what the kit README carried when this row was written, and the
    # row is pinned from that README rather than from the brief.
    ".claude/hooks/execution_guard.py": (
        "0.2.22",
        "2ebfc38bd69cf625971385834c05f0b189d1121ce78d324a950c568cc32ccf5b",
        "ClaudeCoordinator/kit",
    ),
    ".claude/hooks/execution_guard_mutations.py": (
        "0.2.22",
        "d8131f93820b1d010a219969229d2e9d5749af2bcaa812753f26ea58df5e2ffb",
        "ClaudeCoordinator/kit",
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
    ".claude/hooks/role_review_gate.py": "c4a1c8b9f64bb212",
    ".claude/hooks/write_attestation.py": "bb9379911b7ed3cc",
    ".claude/hooks/ci_state.py": "535c036d26266aca",
    ".claude/hooks/ci_state_mutations.py": "05a3e6d807ed0095",
    ".claude/tools/incident-analyst.md": "2bdbe55a6e1987ae",
    ".claude/tools/check_incidents.py": "e3cd74c877e000cb",
    ".claude/tools/snap.sh": "49d402df3ad13508",
    ".claude/tools/check_plan_kit.py": "8c7a308d981c0d78",
    ".claude/tools/check_plan_kit_mutations.py": "cbc57a022fe9debe",
    ".claude/tools/check_side_effect_guard.py": "74173c7908fd4721",
    ".claude/tools/check_side_effect_guard_mutations.py": "3b952a436a3928f8",
    ".claude/tools/check_review_rounds.py": "4d2726dbbeed012a",
    ".claude/tools/check_review_rounds_mutations.py": "13cb3d72e4c4040f",
    ".claude/tools/review-policy.md": "9ffd73edbd2b6077",
    ".claude/tools/review_runner.py": "2f120183b1211182",
    ".claude/tools/detached_gate.py": "72e440fe428576ad",
    ".claude/tools/budget_isolation.py": "56dd7a1ef1ee9133",
    ".claude/hooks/role_review_gate_mutations.py": "3b16f9f89f978545",
    ".claude/tools/version-control.md": "ef976e3179c033b3",
    ".claude/tools/check_release_gate.py": "f722bba81049e5c6",
    ".claude/tools/check_release_gate_mutations.py": "f5d3746b4228d19e",
    ".claude/tools/prepush_receipt.py": "2172114c92b8dd5e",
    ".claude/tools/prepush_receipt_mutations.py": "369e7dcaeb9836fa",
    ".claude/tools/check_shipped_surface.py": "e32a6c7d6ba0253a",
    ".claude/tools/check_shipped_surface_mutations.py": "8c04f65a622d40a4",
    ".claude/tools/check_probe_closure.py": "e43cd8ad8ef22bd2",
    ".claude/tools/check_probe_closure_mutations.py": "f5395e2aaa3bae0c",
    ".claude/tools/check_citations.py": "f0f80fe0ef080321",
    ".claude/tools/check_citations_mutations.py": "415f9fcda69ac3c7",
    ".claude/tools/check_version_identity.py": "610becda7f486eed",
    ".claude/tools/check_version_identity_mutations.py": "ef94eb1b85764c79",
    ".claude/tools/check_spawn_env.py": "d01f4930a484e57a",
    ".claude/tools/check_spawn_env_mutations.py": "8a3c3587f86a819f",
    ".claude/hooks/execution_guard.py": "f27f3298e1673544",
    ".claude/hooks/execution_guard_mutations.py": "c7131f9a250db397",
}


#: The PROVENANCE HEADER of each vendored copy, pinned by sha256 over every
#: byte above the body. Added 2026-08-18 (OPS-2013.30).
#:
#: What it closes: until it existed, only the BODY was hashed, and the header
#: was reached by three assertions that each read ONE field. `kit-version`,
#: `body-sha256`, `note` and `canonical-source` are checked; anything else a
#: header carries is not. An arbitrary extra line above the marker, a
#: `contact:` field carrying a personal address for instance, passed every
#: assertion in this file, in a directory whose whole reason for a personal
#: identifier guard is that a vendored kit body once published one on this
#: public remote.
#:
#: Why bytes rather than a rule about which keys or line shapes are allowed:
#: the headers are not uniform and cannot be made uniform from here. Every
#: file carries a colon-free title line, the Markdown stamps wrap theirs in an
#: HTML comment, and `review-policy.md` carries two further prose paragraphs
#: above the marker, one of which `_header_fields` already parses as a KEY
#: several hundred characters long. A shape rule needs a carve-out per file
#: and is still a whitelist of prose; a hash needs none and misses nothing.
#:
#: THE BOUNDARY, stated once so the pin and the body hash cannot disagree
#: about a line: the header is `lines[:start]` from :func:`_split_at_marker`
#: and the body is `lines[start:]`, so the header runs from line 1 through the
#: END KIT PROVENANCE line, plus the bare `-->` terminator where the stamp is
#: an HTML comment. The two regions are exact complements and
#: :func:`test_the_header_pin_and_the_body_hash_cover_every_byte` asserts they
#: rebuild the file, which is what makes "every byte is hashed" a measurement
#: rather than a claim.
#:
#: Like the body hash, this is a pin a re-vendor updates DELIBERATELY. A
#: promotion that legitimately restamps a header changes one line here in the
#: same commit; nothing else can.
HEADER_SHA256: dict[str, str] = {
    ".claude/hooks/role_review_gate.py": (
        "40859829f4c1639fdb81485ab5e5d8ba2a130d2af0c44f7b3360aac875c5dc94"
    ),
    ".claude/hooks/role_review_gate_mutations.py": (
        "ca84becab3502e5316eae2bb19351474f1508eb601ae7d0f75132ddc466c7b90"
    ),
    ".claude/hooks/write_attestation.py": (
        "e5e2f512e5c790197f409e1bb4cbdb3c52318c186546bba7928504377d084c15"
    ),
    ".claude/hooks/ci_state.py": "c53ec2254f9320b497838129b0cf06db42f51c7991c01681cf053c371024ef4a",
    ".claude/hooks/ci_state_mutations.py": (
        "7738c822e0b2699e0bb354350a4cc53d3a6d9a312ea51a5b14bb215d5f1c2088"
    ),
    ".claude/hooks/execution_guard.py": (
        "34379ce6951bf5c6b4b06f35ee6124782d4376a258da2487cb2375217f959458"
    ),
    ".claude/hooks/execution_guard_mutations.py": (
        "f8582e0ee9930a9526c6d3c3c18f09739c027dd61fa999d5c45b861e840c099a"
    ),
    ".claude/tools/incident-analyst.md": (
        "fea2df2975d955e13793a5ef10f45ac0ab326cff4f34ac8bb9b9d0aa6b6004bb"
    ),
    ".claude/tools/check_incidents.py": (
        "b1853f7688ce656469cfa31141be0ee9ffb184a732c99d5759d51f7c27fa5335"
    ),
    ".claude/tools/snap.sh": "ce3d7aca330d51c0e845a1defaf43088470474195d91b4a61f4fb34020a161f9",
    ".claude/tools/check_plan_kit.py": (
        "96c7939294a22b01fb5bcbc1b010f062c68405cdaba3a05f7d9c4c0d96cade60"
    ),
    ".claude/tools/check_plan_kit_mutations.py": (
        "3d5f346769c21cbaa306d24f7b5ed789838728f3d32863d284f9a048fd9ab1b5"
    ),
    ".claude/tools/check_side_effect_guard.py": (
        "4f8f08ab66036766771159ac7ea0a23bac2e989b6945118d1ac96eea4b250c81"
    ),
    ".claude/tools/check_side_effect_guard_mutations.py": (
        "f3827283544f3a3867b1980bb302ecf5baf4735ad16822427bca8d9c7e9d55ae"
    ),
    ".claude/tools/check_review_rounds.py": (
        "81e18c453011535ac158c1870bf520e91696383dec09c92973f18e5ee7331970"
    ),
    ".claude/tools/check_review_rounds_mutations.py": (
        "b324c0f797016d299a38b698fa54d6b71776bfad38fb277e1ee345fc0f74066d"
    ),
    ".claude/tools/review-policy.md": (
        "34114369eb6d33c552bca4c806953918c0dfe141ea0ee7cdcfb8eabe5af5a46f"
    ),
    ".claude/tools/review_runner.py": (
        "23b3eb6cb6c67d8fd03b7ccdd1a92f5d1a20a5b619fa70a317eb30c4d4a71f36"
    ),
    ".claude/tools/detached_gate.py": (
        "b7d6aa1b7186a3e487357ec08dcb1245b7557b8d8f0cebf2021da05cbda9d597"
    ),
    ".claude/tools/budget_isolation.py": (
        "f3094afd945bb19f7cb66bc0c6abce75cd9e50eb24c9da84bcb7365ca528f0a2"
    ),
    ".claude/tools/version-control.md": (
        "f770526011c29b43c645f2dc6e499a947b50c3fa785540c1e7b43d3a4a187f7d"
    ),
    ".claude/tools/check_release_gate.py": (
        "9b53b7888c5da223983f74bffbf07041b756322f068876575867e5181b2e59d6"
    ),
    ".claude/tools/check_release_gate_mutations.py": (
        "ccea6212b73663cefc9106f3b33d1ac03714dfcad182523703cb25b1cea83489"
    ),
    ".claude/tools/prepush_receipt.py": (
        "1ac977075379890f6c0d04a61d43aa631cf428993c02d306da29b246af221010"
    ),
    ".claude/tools/prepush_receipt_mutations.py": (
        "773277703e655207b13dcae185b6cd37b715748b6b711e6701435981cc802ad0"
    ),
    ".claude/tools/check_shipped_surface.py": (
        "f696f41a1150cc9dd048a50e53ab06860bfb0f9bdd1a500f05055288ffc8d094"
    ),
    ".claude/tools/check_shipped_surface_mutations.py": (
        "7c23d1a3dbab70e5330098f2ad2c89b741ca5fc338cf4b9c5f981212e8d709f6"
    ),
    ".claude/tools/check_probe_closure.py": (
        "96dad3447e8264271b06c27929dd33866be7459907c8a0e2b2df6838d207a598"
    ),
    ".claude/tools/check_probe_closure_mutations.py": (
        "b68373e18830a2cb1b261e0fa635cd7c883bc071d5820e5bcd84cdc8db35e449"
    ),
    ".claude/tools/check_citations.py": (
        "facc45fb3459c2687db4235995e90d6f805668af99bf790b06263fbb0320eda5"
    ),
    ".claude/tools/check_citations_mutations.py": (
        "0c83f77d1771831e2e733f2fd558aa8b79a2c1de6819b456b9bc7d6472f04ec9"
    ),
    ".claude/tools/check_version_identity.py": (
        "27e2551ba4271f7ffd0154ca2382f06c563a64c1add38dbd900b23458c4476ed"
    ),
    ".claude/tools/check_version_identity_mutations.py": (
        "ea1e99855e468f742527b96e9b3af8aa0448b73d890ec0ef0ece5403ac642e52"
    ),
    ".claude/tools/check_spawn_env.py": (
        "99d65ea567c12f9943b4a61a3bf7d3085c2959a14b89d52c7fb0cc9f855b5386"
    ),
    ".claude/tools/check_spawn_env_mutations.py": (
        "c94c0711f4faddadaf727957552ae4141796f471aa95d9152fb2863e6f2b1d93"
    ),
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


def _header_sha256(text: str) -> str:
    """sha256 over every byte above the body, the boundary being the one
    :func:`_split_at_marker` gives the body.

    Takes the TEXT rather than a path, so the mutation case can hash a file
    that exists only in a temporary directory.
    """
    lines, start = _split_at_marker(text)
    return hashlib.sha256("\n".join(lines[:start]).encode("utf-8")).hexdigest()


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


@pytest.mark.parametrize("rel", sorted(MANIFEST))
def test_no_vendored_note_names_the_retired_kit_path(rel: str) -> None:
    """No provenance ``note:`` may send a reader to the retired kit directory.

    The row above pins the target this repository EXPECTS, so a note is
    checked against a value someone chose. This one is different in kind: it
    forbids one value outright, whatever the manifest says, because the kit
    directory named by ``RETIRED_KIT_PATH`` has not existed since 2026-07-27
    and no correct note can name it as a master.

    It is not redundant with the pinned target, and the reason is written in
    this module's own docstring: the kit ``README.md`` still prescribes the old
    wording, so a re-vendor performed to its letter REPRODUCES the stale
    pointer, and it would do so while updating this file's manifest row in the
    same edit. Pinning the target alone would follow the mistake. Forbidding
    the retired value catches it.
    """
    lines, start = _split_at_marker(_read_lf(REPO / rel))
    note = _header_fields(lines, start).get("note", "")
    assert RETIRED_KIT_PATH not in note, (
        f"{rel}: the provenance note points at the retired kit directory "
        f"{RETIRED_KIT_PATH!r}, which has not existed since 2026-07-27. The "
        f"master lives at {LIVE_KIT_PATH!r}. The `note:` line sits above END "
        "KIT PROVENANCE and is outside the hashed body, so restamping it is "
        f"the prescribed per-copy correction, not a hand-edit. note={note!r}"
    )


def test_every_manifest_note_target_is_the_live_kit_path() -> None:
    """The pinned targets themselves are checked, not only the files.

    Without this the manifest could pin the retired path for a row and the
    per-file assertion above would pass, agreeing with a target that is wrong.
    A row whose note target is legitimately something else is a deliberate
    edit here; nothing may pin the retired directory.
    """
    stale = sorted(rel for rel, (_v, _h, target) in MANIFEST.items() if target != LIVE_KIT_PATH)
    assert not stale, (
        f"these manifest rows record a note target other than {LIVE_KIT_PATH!r}: "
        f"{stale}. The kit moved on 2026-07-27; a row still pinning "
        f"{RETIRED_KIT_PATH!r} makes the note assertion agree with a pointer "
        "that goes nowhere."
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


@pytest.mark.parametrize("rel", sorted(HEADER_SHA256))
def test_vendored_kit_header_matches_the_header_pin(rel: str) -> None:
    """Every byte above the body hashes to the pinned value.

    The three assertions above read one header FIELD each. This one reads the
    whole region, so a line nobody expected is a failure rather than a value
    nothing looks at.
    """
    got = _header_sha256(_read_lf(REPO / rel))
    assert got == HEADER_SHA256[rel], (
        f"{rel}: provenance header sha256 {got} != pinned {HEADER_SHA256[rel]}. "
        "Some byte above END KIT PROVENANCE changed: a field was edited, a "
        "line was added, or the stamp was rewritten. If a re-vendor or a "
        "prescribed restamp did it, update this pin in the same commit; if "
        "nothing was re-vendored, the header was hand-edited."
    )


def test_every_manifest_row_has_a_header_pin() -> None:
    """MANIFEST and HEADER_SHA256 carry the same keys.

    Without this a row could arrive with a body hash and no header pin, and
    every test above would pass while that file's header was covered by
    nothing at all. It is the same contract
    :func:`test_the_manifest_agrees_with_the_recorded_adoption_residue` holds
    for CANONICAL_SOURCE.
    """
    missing = sorted(set(MANIFEST) - set(HEADER_SHA256))
    assert not missing, f"these manifest rows have no header pin: {missing}"
    extra = sorted(set(HEADER_SHA256) - set(MANIFEST))
    assert not extra, f"these header pins name no manifest row: {extra}"


@pytest.mark.parametrize("rel", sorted(MANIFEST))
def test_the_header_pin_and_the_body_hash_cover_every_byte(rel: str) -> None:
    """The two hashed regions are exact complements, so nothing is unhashed.

    "Every byte is hashed" is the claim this item rests on, and a claim about
    coverage that is never measured is how the header came to be unhashed in
    the first place. The split is asserted here rather than trusted: the
    header is ``lines[:start]``, the body is ``lines[start:]``, and rejoining
    them must reproduce the file exactly.
    """
    text = _read_lf(REPO / rel)
    lines, start = _split_at_marker(text)
    assert start > 0, f"{rel}: the header region is empty"
    assert start < len(lines), f"{rel}: the body region is empty"

    # The rebuild alone would be TAUTOLOGICAL and is kept for the one thing it
    # does catch: a split that returns lines it has altered. It is true for any
    # boundary, which the adversarial pass on this item demonstrated by moving
    # the boundary one line and watching it stay green, so the boundary itself
    # is asserted below rather than assumed.
    rebuilt = "\n".join(lines[:start]) + "\n" + "\n".join(lines[start:])
    assert rebuilt == text, (
        f"{rel}: the header and body regions do not rebuild the file, so the "
        "split returned lines it had altered and neither hash is over the "
        "bytes on disk."
    )

    # The boundary is pinned against the FIRST marker line, which is the one
    # _split_at_marker uses. Not against every occurrence: `detached_gate.py`
    # and `prepush_receipt.py` are kit tools that PARSE these stamps, so the
    # string appears again in their bodies as a constant, and a rule reading
    # "the marker never appears below the boundary" fails on both. The
    # adversarial pass found that on the tree rather than in the abstract.
    header, body = lines[:start], lines[start:]
    marker = next(i for i, line in enumerate(lines) if "END KIT PROVENANCE" in line)
    assert marker < start, (
        f"{rel}: the marker line sits in the BODY region, so the boundary is "
        "above it and part of the header is hashed as body"
    )
    trailing = [line.strip() for line in header[marker + 1 :]]
    assert trailing in ([], ["-->"]), (
        f"{rel}: the header region runs past the marker by more than the HTML "
        f"comment terminator ({trailing!r}), so a body line is being hashed as "
        "header"
    )
    assert body[0].strip() != "-->", (
        f"{rel}: the body region starts with the comment terminator, so the "
        "closing `-->` of the stamp is hashed as body and can be deleted "
        "without either pin noticing"
    )


def test_an_injected_header_line_fails_the_pin_while_everything_else_passes() -> None:
    """Mutation proof, on the exact shape this pin exists to catch.

    A vendored file with one extra header line carrying a personal contact
    address: the body is untouched, so its sha256 still matches; the four
    field assertions still find the values they read; and ``_header_fields``
    happily parses the injected line as a key, which is what makes it
    invisible rather than merely unchecked. Only the header pin refuses it.

    The address is assembled from fragments and never written as a literal,
    for the reason ``tests/test_house_style.py`` gives about its own guard:
    this file is tracked and this remote is public, so a test about a leaked
    address must not carry one.
    """
    rel = ".claude/tools/check_incidents.py"
    original = _read_lf(REPO / rel)
    lines = original.split("\n")
    markers = [i for i, line in enumerate(lines) if "END KIT PROVENANCE" in line]
    assert len(markers) == 1, (
        f"{rel}: expected exactly one END KIT PROVENANCE line to anchor the "
        f"injection, found {len(markers)}. An anchor that is not unique makes "
        "the mutation land somewhere nobody chose."
    )
    address = "someone.personal" + chr(64) + "gmail.com"
    injected = f"# contact: {address}"
    mutated = "\n".join(lines[: markers[0]] + [injected] + lines[markers[0] :])
    assert injected in mutated and mutated != original, "the mutation did not apply"

    version, body_hash, note_target = MANIFEST[rel]
    assert _body_sha256(rel, mutated) == body_hash, (
        "the injected line changed the BODY, so this case proves nothing about "
        "the header: it would be caught by the body hash like any other edit"
    )
    mutated_lines, mutated_start = _split_at_marker(mutated)
    fields = _header_fields(mutated_lines, mutated_start)
    assert fields.get("kit-version") == version
    assert fields.get("body-sha256") == body_hash
    assert note_target in fields.get("note", "")
    canonical = fields.get("canonical-source", "")
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16] == CANONICAL_SOURCE[rel]
    assert fields.get("contact") == address, (
        "the injected line is not even parsed as a header field, so this "
        "mutation is not the shape the pin exists to catch"
    )

    assert _header_sha256(mutated) != HEADER_SHA256[rel], (
        "the header pin accepts a vendored file carrying an injected contact "
        "line. Every other assertion in this module passed on it, which is the "
        "unchecked surface this pin was added for."
    )


#: Where a vendored kit body may live in this tree. Both directories are
#: already excluded wholesale from ruff and from the pre-commit hooks (a
#: reformat changes the body bytes and breaks the pin), and both are pinned to
#: LF in `.gitattributes`, so this list is the third face of one decision
#: rather than a new one.
VENDOR_DIRS = (".claude/tools", ".claude/hooks", ".claude/agents", ".claude/skills")

#: The manifest's size, pinned so a row cannot arrive or vanish as a side
#: effect of some other change. 11 at the start of 2026-08-11, 35 at its end.
EXPECTED_ROWS = 35

#: The kit artifacts absent BY DECISION rather than by omission (the author,
#: 2026-08-11). This repository's `.github/workflows/release.yml` is a single
#: workflow with no `workflow_call`, it has published v0.4.0 through v0.7.0,
#: and adopting the kit's caller-plus-reusable-gate topology means rewriting
#: the one release path here that is proven to work. `check_release_gate.py`
#: IS vendored and cannot pass without them, which is recorded beside it in
#: `tests/test_kit_checkers.py`.
DECIDED_OUT = ("release_caller.yml", "release_gate.yml")

#: The DEPLOYED halves of the OQ-56 two-file shape. Each is the body of a
#: stamped of-record with the provenance comment stripped, so neither carries
#: a manifest row and neither is reachable by iterating MANIFEST. They are
#: listed here because the tracked-by-git check is about exactly this class of
#: file: a runtime artifact real in one working tree and absent from clones.
DEPLOYED_DERIVATIONS = (
    ".claude/agents/incident-analyst.md",
    ".claude/skills/version-control/SKILL.md",
)


def _stamped_files() -> list[str]:
    """Every file in the vendor directories carrying a kit provenance stamp."""
    found = []
    for folder in VENDOR_DIRS:
        for path in sorted((REPO / folder).rglob("*")):
            if not path.is_file() or path.suffix == ".pyc":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "END KIT PROVENANCE" in text:
                found.append(str(path.relative_to(REPO)).replace("\\", "/"))
    return found


def test_every_stamped_file_in_the_tree_has_a_manifest_row() -> None:
    """A vendored body nobody pinned is worse than one nobody vendored.

    The manifest above is hand-maintained, so until PFS-12 nothing connected
    it to what the tree actually holds: a body could be copied in, carry its
    stamp, be committed, and be covered by no assertion at all. Every test
    above iterates over MANIFEST, so the file simply would not appear.

    This walks the other way. It finds the population by the stamp marker,
    which is the same thing that defines a kit body, and requires a row for
    each. Going from 11 rows to 35 in one night is exactly when that gap would
    have been cheapest to open.
    """
    unpinned = sorted(set(_stamped_files()) - set(MANIFEST))
    assert not unpinned, (
        f"these files carry a kit provenance stamp and no manifest row: "
        f"{unpinned}. Add a row (version, body-sha256, note target) and a "
        "canonical-source fingerprint, or delete the file."
    )


def test_every_vendored_file_is_tracked_by_git() -> None:
    """A vendored body git does not track is a guard that exists on one machine.

    Written because it happened next door on 2026-08-11: itaca wired a hook to
    a file git does not track, so the guard was real in that working tree and
    absent from every clone and from CI. The manifest cannot see it, because a
    file present on disk satisfies every assertion above.

    THE DEPLOYED DERIVATIONS ARE IN SCOPE and were not until 2026-08-12. They
    carry no manifest row, because their stamps are stripped, so iterating
    MANIFEST skipped exactly the two files this test was written about: a QA
    pass removed the deployed version-control skill from the index and this
    file stayed green at 145 passed, including the test that loads it.
    """
    listed = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    ).stdout.splitlines()
    tracked = set(listed)
    assert len(tracked) > 300, (
        f"git ls-files returned {len(tracked)} paths from {REPO}, which is far "
        "below this repository's real size. The environment is pointing git at "
        "another tree (GIT_DIR or GIT_WORK_TREE is set), so every assertion "
        "below would be about a repository nobody asked about."
    )
    in_scope = sorted(set(MANIFEST) | set(DEPLOYED_DERIVATIONS))
    untracked = sorted(rel for rel in in_scope if rel not in tracked)
    assert not untracked, (
        f"these vendored kit files are NOT tracked by git: {untracked}. They "
        "exist in this working tree and in no clone and in no CI run. Stage "
        "them by path."
    )


def test_the_manifest_agrees_with_the_recorded_adoption_residue() -> None:
    """The row count, and what is deliberately absent, are both asserted.

    The docstring above used to carry the row count and the size of the
    unvendored residue as prose, and both went stale the moment a lane took a
    row. They are measured here instead, so a number in this file is a
    measurement rather than a claim someone remembered to update.

    THIS TEST DID NOT DO THAT UNTIL 2026-08-12, and the gap is worth recording
    because it is the defect this repository polices hardest, found in the
    guard written to prevent it. The docstring described a ``DECIDED_OUT``
    constant and said "the count of rows, and what is deliberately absent, are
    both asserted", while the body asserted only that MANIFEST and
    CANONICAL_SOURCE agreed. No count was pinned, no absent artifact was named,
    and the constant did not exist. Two independent reviewer passes found it.
    """
    assert len(MANIFEST) == len(CANONICAL_SOURCE), (
        f"{len(MANIFEST)} manifest rows against {len(CANONICAL_SOURCE)} "
        "canonical-source fingerprints; every row needs both"
    )
    for rel in MANIFEST:
        assert rel in CANONICAL_SOURCE, f"{rel} has a manifest row and no fingerprint"
    assert len(MANIFEST) == EXPECTED_ROWS, (
        f"{len(MANIFEST)} manifest rows, pinned at {EXPECTED_ROWS}. A row was "
        "added or removed: change this number in the same commit, so the count "
        "moves deliberately rather than as a side effect."
    )


def test_the_decided_out_artifacts_are_absent_and_stay_absent() -> None:
    """The two kit artifacts nobody forgot: they were DECLINED.

    This is the assertion that cannot be derived from the manifest, because
    the manifest records what was taken and says nothing about the difference
    between "not adopted" and "not decided". Failing to distinguish those two
    is what kept COORD-02 open from 2026-08-02, so the distinction gets a
    mechanism rather than a paragraph.

    If a later lane adopts the kit's caller-plus-reusable-gate release
    topology, this test is what it has to change, deliberately, and the
    reasoning in CLAUDE.md moves with it.
    """
    for name in DECIDED_OUT:
        assert name not in {Path(rel).name for rel in MANIFEST}, (
            f"{name} has a manifest row, but it was DECIDED OUT by the author "
            "on 2026-08-11. Either the decision was reversed, in which case "
            "remove it from DECIDED_OUT and say so in CLAUDE.md, or the row "
            "was added by mistake."
        )
        hits = [
            p
            for p in REPO.rglob(name)
            if ".venv" not in p.parts and ".claude/worktrees" not in p.as_posix()
        ]
        assert not hits, (
            f"{name} exists in the tree at {[str(p) for p in hits]} and was "
            "decided out. See CLAUDE.md: this repository's release.yml is a "
            "single workflow with no workflow_call, and the kit topology was "
            "declined rather than deferred."
        )


def test_deployed_version_control_skill_is_the_derivation_of_record() -> None:
    """The loaded skill is exactly the of-record body with the stamp removed.

    The OQ-56 two-file shape, and this repository already runs it for
    ``incident-analyst.md``: a loader that wants YAML frontmatter on line 1
    cannot be handed a file whose first line is ``<!--``, so the DEPLOYED copy
    is the body alone and the stamped copy stays as the drift test's
    of-record. Without this check a hand-edit of the deployed skill escapes
    every assertion above, which only ever reads the of-record.

    Note what is NOT here and is here for the analyst: no per-repo
    substitution. That charter had one (a ledger variable) and the 0.2.11 body
    retired it; this skill never had one, so the deployed copy is the body
    byte for byte and the body hash of the manifest row is also the hash of
    the deployed file. Asserted rather than left implicit, so a future body
    that DOES introduce a substitution fails here instead of silently making
    the two files differ.
    """
    of_record = _read_lf(REPO / ".claude/tools/version-control.md")
    lines, start = _split_at_marker(of_record)
    body = "\n".join(lines[start:])
    deployed_path = REPO / ".claude/skills/version-control/SKILL.md"
    assert deployed_path.is_file(), (
        "the version-control skill is vendored as an of-record and never "
        "deployed, so nothing loads it. Materialize "
        f"{deployed_path.relative_to(REPO)} from the stamped copy."
    )
    deployed = _read_lf(deployed_path)
    assert deployed == body, (
        "the deployed version-control skill is not the body of the stamped "
        "of-record (.claude/tools/version-control.md). Re-materialize it by "
        "stripping the provenance comment; do not edit either copy by hand."
    )
    assert deployed.splitlines()[0].strip() == "---", "deployed skill lost its frontmatter"
    _version, want, _note = MANIFEST[".claude/tools/version-control.md"]
    assert hashlib.sha256(deployed.encode("utf-8")).hexdigest() == want, (
        "the deployed body no longer hashes to the manifest row, which can "
        "only mean a per-repo substitution appeared. That is not forbidden, "
        "but it makes the two files genuinely different and this assertion is "
        "where that has to be acknowledged rather than discovered."
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

    THE SUBSTITUTION HALF IS A NO-OP ON THE 0.2.11 BODY and this test says so
    out loud rather than carrying an assertion nothing reaches. That body names
    ``COORD_INCIDENT_LEDGER`` and neither per-repo name, so the rename changes
    no byte and the old "runtime agent still names the itaca ledger var"
    assertion was vacuously true. The measurement below is what makes the
    difference visible: if a future kit body reintroduces a per-repo token, the
    no-op assertion fails and a reader is told the mechanism went live again,
    instead of the mechanism quietly starting to matter behind a green test.
    """
    of_record = _read_lf(REPO / ".claude/tools/incident-analyst.md")
    lines, start = _split_at_marker(of_record)
    body = "\n".join(lines[start:])
    expected = body.replace(CANONICAL_LEDGER_VAR, REPO_LEDGER_VAR)
    runtime = _read_lf(REPO / ".claude/agents/incident-analyst.md")
    assert runtime == expected, (
        "the runtime incident-analyst agent is not the derivation of the "
        "stamped of-record (.claude/tools/incident-analyst.md). Re-materialize "
        "it: strip the provenance comment and substitute "
        f"{CANONICAL_LEDGER_VAR} -> {REPO_LEDGER_VAR}."
    )
    assert runtime.splitlines()[0].strip() == "---", "runtime agent lost its frontmatter"
    assert expected == body, (
        f"the vendored charter names {CANONICAL_LEDGER_VAR} again, so the "
        "per-repo substitution is LIVE rather than the no-op this repository "
        "measured at kit 0.2.11. That is not a failure of the charter; it means "
        "the two constants above are load-bearing once more and the docstring's "
        "no-op claim, and CLAUDE.md's removal of PYFS_INCIDENT_LEDGER, both need "
        "revisiting."
    )
    assert CANONICAL_LEDGER_VAR not in runtime, "runtime agent still names the itaca ledger var"
