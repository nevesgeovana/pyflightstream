# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method
solver. Successor of the author's legacy research scripts. MIT licensed.

## Hard invariants (never violate)

1. Never reproduce FlightStream manual text, screenshots, or example
   blocks anywhere in this repository. Manual facts appear only as
   paraphrases with a page citation (manual_ref). The manual pdf lives
   in _private/ and never enters Git.
2. Clean-room rule: the command emitter is specified only from the
   official manual and from probe evidence. Never read, quote, or
   adapt code from pyFlightscript (AGPL-3.0), including the vendored
   copy in the old research workspace.
3. Every command database change is evidence-backed: a manual_ref for
   documented entries, a committed probe report for verified/broken.
   No status is hand-edited.
4. Supported FlightStream versions are only added, never dropped.
   Canonical version identifiers use the 26.XXX three-digit scheme;
   the ordered list in commands/_meta.yaml is the only ordering
   authority.
5. No proprietary content: no employer or third-party data, no
   research geometry. SMI geometry stays in _private/ and is referenced
   only by local QA runs; committed reports carry aggregated
   coefficients only. The repository never names the author's employer
   or internal predecessor toolchains; legacy scripts are referenced
   only generically, as inspiration.
6. All folder, file, and identifier names are in English.
7. Examples are percent-format .py; .ipynb never enters Git.
8. Didactic policy: numpydoc docstrings with units and reference
   frames; module top-docstrings state the pipeline role; error
   messages name the physical or version cause.

## Engineering policy

Prefer existing public libraries over in-house implementation whenever
the need is generic (validation, parsing, arrays, IO); licenses must be
MIT-compatible. Domain logic (FlightStream semantics, evidence rules,
physics) stays in-house. Author's decision of 2026-07-21.

## Definition of done

A change is done when: tier 1 tests pass in CI; new commands carry
manual_ref, phase, layout, and typed args; new parsers have fixtures;
public functions have numpydoc docstrings; the docs build; and the
change needing solver evidence has its probe report committed or an
issue tracking the pending probe.

Documentation currency (SRS NFR-11, adopted 2026-07-22): a change to
the public surface (API, CLIs, extras, behavior, deprecations) is done
only when CHANGELOG.md's Unreleased section describes it and the
public pages it invalidates (README, docs, SRS requirement statuses)
move in the same session. Facts live in one home; version-bearing
files agree (test-enforced). The periodic `audit` skill sweeps for
drift; findings are updated or deleted, never left for later.

Role passes (adopted 2026-07-23): before a work item closes, the
`role-review` skill has run its applicable reviewer passes
(architect, QA, V&V, tech writer, API designer; charters in
`.claude/agents/`) on the item's diff, and every finding is fixed or
registered in the plan. The author keeps the non-delegable seats:
product owner, domain expert, numerical analyst (seat definitions in
`.claude/skills/role-review/ROLE_TEMPLATE.md`).

Side-effecting skills: a skill that spends something a read cannot undo
(publishes, tags, deploys, promotes a status, or consumes the licensed
solver seat) declares it in a `side-effects:` frontmatter field naming
what it spends, and sets `disable-model-invocation: true` so the model
cannot fire it. The vendored kit guard `check_side_effect_guard.py`
(tier 1, over `.claude/skills`) enforces the implication; it cannot infer
an undeclared side effect, so declaring the field when you author such a
skill is the API-designer/architect pass's check, not the guard's.

Mandatory push and release gate (adopted 2026-07-23, after the v0.3.0
release ran paraphrased manual checks instead of the specialist
agents): "role-review" means invoking the `role-review` skill so the
real reviewer agents run, never a hand-written paraphrase of their
charters. A PreToolUse hook (`.claude/hooks/role_review_gate.py`, on
the Bash and PowerShell tools) blocks a `git push` until an
attestation stamped by the role-review skill covers every commit the
push makes new plus each ref it sends; a release-grade push (naming a
version tag, for example `git push origin vX.Y.Z`) additionally
requires the release attestation from the release skill (full-scope
audit plus the role-review sweep of every item). The blanket forms
(`--all`, `--mirror`, `--tags`, `--follow-tags`) are refused outright
as unscopable, so a release is pushed by naming the tag, never with
`--tags`. The
attestation is written by `.claude/hooks/write_attestation.py` as the
skill's closing step and lives in
`.claude/.role_review_attestation.json` (local, gitignored). A commit
made after attesting re-arms the gate: an unreviewed commit never
ships.

Structural-fix rule and the shared incident ledger (adopted
2026-07-23, after three failures hit one private file in a single
session and two of them had been silent for many sessions): unlike the
research environment, where a workaround is acceptable, a defect in
these two libraries is fixed at its STRUCTURAL cause on its FIRST
occurrence, in the session where it appears. Every problem and its fix
is recorded in the incident ledger shared with ITACA (protocol and
format in its README; one file per incident, id from a timestamp,
because two of the founding failures were caused by concurrent writes
to a shared table with a central counter). An incident is only `fixed`
when it carries a `guard`, the mechanism that makes recurrence
impossible, AND `guard_evidence`, proof the guard blocks the original
failure when re-run. A symptom fix, an untested guard, or documentation
offered as a guard leaves it open. The `incident-analyst` agent
(`.claude/agents/`) owns this analysis; the five review charters all
look at a change about to land, not at a failure that happened. The
push gate reads the ledger and denies a push while an open incident
blocks this repository.

PyPI publishing is trusted publishing only (OIDC), never a manual
token upload: a pushed `vX.Y.Z` tag triggers
`.github/workflows/release.yml`, which builds and publishes from the
GitHub `pypi` environment. The release skill's Pause 5 is the
authority; do not run `twine upload` by hand. Per the co-development
decision (ITACA DD-23), this mirrors the ITACA release workflow.

## Layout

src layout per the SAD. Dependencies flow downward:
versions <- commands <- script/results <- cases <- run/workspace <- post/qa.
Never import upward. (`workspace` is the renamed `files`; the old name
survives only as a deprecation shim.)

## Session protocol

Every working session starts by stating its objective against
_private/STATUS.md, and ends with /handoff out, which writes the
session handoff under _private/handoffs/, appends the
_private/logbook.csv row, and updates _private/STATUS.md. Planning
lives in _private/plan/, one file per item, via /plan. Since 2026-07-23 (author's
decision) the session documents live in _private/ (OneDrive-synced,
never committed); they still satisfy the same content guards as the
repository (English, no dashes, invariant 5 wording). Committed
history before that date keeps the old in-repo copies. Public items
being discontinued move to the committed deprecated/ folder, never
scattered at the top level. Conversation with the author may be in Portuguese;
every committed artifact is in English (invariant 6). The design
documents (SRS, SAD, Bootstrap Kit) are local-only in _private/design/.

Machine configuration (never a literal path in a committed file). Two
environment variables locate the local, machine-specific tooling, and
both live in the gitignored `.claude/settings.local.json`, so a fresh
clone must set them:

- `PYFS_PLAN_CHECKER` names the plan-ledger validator the `plan` skill
  runs; the skill (`.claude/skills/plan/SKILL.md`) is the single home of
  which checker and how it is invoked. Do not name the file here: today
  it points at `check_plan.py`. The kit checker `check_plan_kit.py` is
  vendored and drift-guarded but is NOT yet the active validator; adopting
  it waits on the counter-id migration, which is paused and routed to
  coordination (see `_private/plan/PLN-20260724-1808`). Unset skips
  validation; set but unreadable is a configuration error to report and,
  unlike the incident ledger below, does not block a push.
- `PYFS_INCIDENT_LEDGER` names the shared incident ledger directory (the
  `incident-analyst` agent and the push gate read it; the reasoning lives
  in `.claude/hooks/role_review_gate.py`, the single home of that rule).
  Unset means the incident check does not apply; set but unreadable
  blocks a push.

Weakness stated, not hidden: an omitted `PYFS_PLAN_CHECKER` degrades to a
silent skip (no validation), so this documentation is the only thing that
makes the omission visible. The load-bearing guard is the tier-1 kit
drift test (`tests/test_kit_drift.py`), which fails in CI if the vendored
checker is missing or drifts from the kit; the env var only points the
`plan` skill at whichever checker is active.
