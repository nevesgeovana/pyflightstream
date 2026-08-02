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
2026-07-23): a defect in these two libraries is fixed at its STRUCTURAL
cause on its FIRST occurrence, in the session where it appears, not on
its second. The fix is not complete until it carries a guard that makes
recurrence impossible and the evidence that the guard blocks the
original failure when re-run. That headline is kept here so a clone
reads the rule without leaving the repository; the full policy
statement, including why documentation is not a guard and why a guard
must be proven by mutation, lives in the shared ledger's own README, the
cross-repo authority both libraries point at (located by
`COORD_INCIDENT_LEDGER`; one file per incident, id from a timestamp). The
`incident-analyst` agent (`.claude/agents/`) drafts the record; whether
an incident blocks is the author's call, and the push gate denies a push
while a blocking incident is open for this repository.

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
`<session-root>/STATUS.md`, and ends with /handoff out, which writes the
session handoff under `<session-root>/handoffs/`, appends the
`<session-root>/logbook.csv` row, and updates
`<session-root>/STATUS.md`. Planning lives in _private/plan/, one file
per item, via /plan.

`<session-root>` is a placeholder, not shell syntax: resolve the
`PYFS_SESSION_ROOT` environment variable and use its value. The
placeholder is written this way on purpose. The bash form
`$PYFS_SESSION_ROOT/STATUS.md` is an undefined variable in PowerShell,
this environment's primary shell, where it interpolates to the empty
string with no error and yields `/STATUS.md` at the current drive root.
That is the silent failure this variable exists to prevent, so its own
documentation must not print it. In a PowerShell command write
`$env:PYFS_SESSION_ROOT`; in bash, `$PYFS_SESSION_ROOT`.

Since 2026-07-23 (author's decision) the session documents are not
committed to THIS repository; since 2026-07-27 (author's decision,
executed by this repository's own session) they live in the coordination
hub rather than in _private/, located by PYFS_SESSION_ROOT below. Note
what changed: the hub is a git repository with a remote, so the
documents are now committed and versioned THERE. They were previously in
no repository at all.

Content guards, stated as the residual rather than as a guarantee: the
session documents are supposed to satisfy the same guards as this
repository (English, no dashes, invariant 5 wording), and the migrated
set does NOT. `tests/test_house_style.py` skips `_private/` by design,
so the guard never applied to these files while they lived there, and it
cannot reach them now that they live in another repository. Three
migrated files carry the forbidden predecessor-toolchain identifier and
several are in Portuguese. The sweep is owned at the hub and is
registered as PLN-20260727-1704-migrated-set-unswept; do not read the
first sentence of this paragraph as a claim that it has run.

Committed history from before 2026-07-23 keeps the old in-repo copies.
Nothing from the 2026-07-23 to 2026-07-27 window was ever committed
anywhere.

The plan ledger and the design documents did NOT move: a repository's
own plan and architecture are its own facts, which is the coordination
charter's own rule (determination
PLN-20260727-1542-plan-ledger-stays). They stay local-only in
_private/plan/ and _private/design/, alongside the categories that can
never move at all: the licensed manual, the solver executables and the
research geometry. The local design documents are the SAD and the
Bootstrap Kit; the SRS is no longer among them, having gone public on
2026-07-23 as docs/srs/ (a living document superseding the private
DLV-002).

Public items being discontinued move to the committed deprecated/
folder, never scattered at the top level. Conversation with the author
may be in Portuguese; every committed artifact is in English
(invariant 6).

Machine configuration (never a literal path in a committed file). Five
environment variables locate the local, machine-specific tooling and
state, and all live in the gitignored `.claude/settings.local.json`, so
a fresh clone must set them. It was four until 2026-08-02, when the
0.2.16 gate vendor split the incident ledger into the variable the GATE
reads and the one the ANALYST still reads; the two are listed separately
below rather than merged, because they will not stay the same for long. The rule in the first sentence is enforced
since 2026-07-28 by `tests/test_house_style.py`, which fails on an email
address or a user-profile path in any tracked file; it was prose until a
vendored tool published both on the public remote:

- `PYFS_PLAN_CHECKER` names the plan-ledger validator the `plan` skill
  runs; the skill (`.claude/skills/plan/SKILL.md`) holds the authoritative
  description of how it is invoked. As a summary that defers to the skill:
  it currently points at the vendored kit `check_plan_kit.py`, which
  grandfathers the legacy counter ids listed in
  `_private/plan/legacy_ids.txt` (shape guard only; every other guard
  still applies) and requires timestamp ids for new work. Unset skips
  validation; set but unreadable is a configuration error to report and,
  unlike the incident ledger below, does not block a push.
- `COORD_INCIDENT_LEDGER` names the shared incident ledger directory that
  THE PUSH GATE reads (the reasoning lives in
  `.claude/hooks/role_review_gate.py`, the single home of that rule).
  **Unset DENIES every push, and set but unreadable also blocks.** There
  is no configuration of this variable under which the gate proceeds
  without an answer.

  Two things about it are easy to get wrong, so both are stated rather
  than left to be discovered.

  It replaced `PYFS_INCIDENT_LEDGER` on 2026-08-02 when the 0.2.16 gate
  body was vendored, under the coordination-level decision
  `LEDGER-ENVVAR`: every workspace now reads ONE name, so the kit master
  and each vendored copy differ in nothing at all. Both variables are
  live here and they are NOT interchangeable, because the rename has not
  reached the other consumer yet: the gate reads this one, and the
  `incident-analyst` agent still reads `PYFS_INCIDENT_LEDGER` below. Set
  both, to the same directory, until that agent is re-vendored.

  And the unset behaviour INVERTED rather than tightened. It used to mean
  the incident check did not apply, which sounds like a courtesy to a
  fork and was measured to be something else: the coordination
  repository, which is the level that WRITES the incidents, derived a
  variable name that had never existed, read unset as does-not-apply,
  and pushed past a blocking incident of its own authorship. Of three
  workspaces the gate stopped two, and the silence was in the one with
  the most to lose. A guard that reads its own missing configuration as
  permission is not a guard. A genuine fork exports the variable at any
  readable ledger, which the deny text names.

  ORDER MATTERS ON A FRESH CLONE, and it is the reverse of the obvious
  one: export this variable BEFORE the gate body is in place, not after.
  The gate is a PreToolUse hook on every shell command, so a clone that
  has the body and not the variable denies every command until it is
  set. Recoverable in one export, but recovering is not the same as
  planning.
- `PYFS_INCIDENT_LEDGER` names the same directory for the
  `incident-analyst` agent, which is the only consumer it has left since
  the gate moved to `COORD_INCIDENT_LEDGER` above. It is not read by any
  hook, so it blocks nothing on its own: unset degrades the analyst
  rather than a push. It survives because the agent charter is a
  hash-pinned vendored body (`.claude/tools/incident-analyst.md`, kit row
  still at 0.2.4 here) and cannot be corrected in this repository; it
  goes away on that row's next re-vendor, and this bullet goes with it.
- `PYFS_SESSION_ROOT` names the session-document home in the
  coordination hub, read by the `handoff`, `plan`, `audit` and
  `derive-requirements` skills. It must name the directory that DIRECTLY
  contains this repository's `STATUS.md`, `logbook.csv`, `handoffs/`,
  `inbox/` and `progress/`. Check that shape before the first write: the
  hub root also carries a
  `STATUS.md` and a `coordination/logbook.csv` of its own, so a variable
  set one or two levels too high is readable, passes every rule stated
  here, and makes a pyflightstream session overwrite the coordination
  level's state file. Unset or unreadable is a configuration error to
  report and stop on, never a skip. The asymmetry with the plan checker
  and the incident ledger is
  deliberate: an unset validator leaves a ledger written but unchecked,
  which is degraded and recoverable, whereas an unset session root would
  let a session believe it closed while writing its record nowhere
  (`PLN-20260727-1541-session-root-indirection`).
- `COORD_SHARED_LEDGER_TREE` names the shared incident-ledger work tree
  that the vendored `.claude/tools/snap.sh` snapshots. It carries the
  `COORD_` prefix rather than `PYFS_`, and that is not an oversight: the
  tree is owned at the coordination level and shared with the sister
  library, so the kit names it. (It was the only such variable until
  2026-08-02; `COORD_INCIDENT_LEDGER` above now shares the prefix for the
  same reason, and sharing a prefix is all they share.) It is listed here
  anyway because a fresh clone reads THIS file and nothing else, and
  because the variable arrived inside a hash-pinned body that cannot
  document itself. It is unrelated to both ledger variables above despite
  the similar name: those LOCATE the ledger the push gate and the analyst
  consult, this one names the tree the snapshot tool backs up. If both point at
  the same directory on a machine, that is a coincidence of setup and
  neither reads the other. Unset means the shared tree is skipped and
  no push is blocked. Read the next paragraph before relying on that
  word: it is what the tool's comment claims, not what it does.

  The 0.2.4 body is defective here and the defect is registered as
  `PLN-20260728-1615-snap-shared-tree-false-success` against the
  coordination level, which owns the master. `ensure()` returns early
  when the snapshot repository already exists, before it ever tests the
  tree, so on a machine that has snapshotted the shared tree before,
  an unset variable does not skip: the run prints four git failures and
  then `snapshot taken (0 file(s))`. A recovery tool reporting a
  snapshot it did not take is the reason this is written down rather
  than left for the next reader to discover. Until 0.2.5 lands, set the
  variable or read the output of `snap.sh` rather than trusting its
  last line.

Two names collide across the boundary and the collision is deliberate,
not an oversight. The session root has an `archive/` (the migrated inbox
history, INB-001 onward) and this repository keeps its own
`_private/archive/` (the superseded plan table). They are different
folders with the same name in different homes; say which one you mean.
The tier-1 guard in `tests/test_house_style.py` deliberately does NOT
list `archive` among the migrated names, because `_private/archive/` is
still a legitimate path here.

A sixth variable, `CLAUDE_PROJECT_DIR`, appears in
`.claude/settings.json` and in the `plan` skill's validator command. It
is NOT in the list above and must not be added to
`.claude/settings.local.json`: the harness provides it at run time
rather than the clone configuring it. Where it is empty the paths built
from it collapse to a drive-relative path (`/_private/plan` resolves
against the current drive), which the tool it feeds rejects loudly so
long as no such directory exists at that drive root. It is used as the
anchor anyway because the alternative is worse: `git rev-parse` resolves
whichever repository the current directory sits in, and since 2026-07-27
a session routinely has two, so its failure mode is to silently validate
a DIFFERENT repository. Loud-and-contingent beats silent-and-wrong.

Summary of the five, because the unset and unreadable columns differ
per variable and the difference is the trap:

| Variable | Unset | Set but unreadable | Enforced by |
|---|---|---|---|
| `PYFS_PLAN_CHECKER` | skips validation | report, does not block a push | instruction only (the drift test guards the checker body, not this behaviour) |
| `COORD_INCIDENT_LEDGER` | **blocks a push** | blocks a push | `role_review_gate.py`, tier-1 `test_push_gate.py` |
| `PYFS_INCIDENT_LEDGER` | degrades the `incident-analyst` agent, blocks nothing | same | instruction only; no hook reads it since 2026-08-02 |
| `PYFS_SESSION_ROOT` | stop, configuration error | stop, configuration error | **instruction only, see below** |
| `COORD_SHARED_LEDGER_TREE` | shared tree skipped, and see the defect above | same skip | documented-here only; `tests/test_env_contract.py` enforces that it IS documented, not what it does |

`COORD_INCIDENT_LEDGER` is the only row whose two columns agree, and that
is the point of it rather than an accident of drafting: it is the one
variable for which there is no configuration that lets a push proceed on
a question nobody asked.

Weakness stated, not hidden, for both variables that have one.

An omitted `PYFS_PLAN_CHECKER` degrades to a silent skip (no
validation), so this documentation is the only thing that makes the
omission visible. The load-bearing guard is the tier-1 kit drift test
(`tests/test_kit_drift.py`), which fails in CI if the vendored checker is
missing or drifts from the kit; the env var only points the `plan` skill
at whichever checker is active.

`PYFS_SESSION_ROOT` makes the strongest promise of the four and has the
weakest enforcement: **no code reads it.** No hook, no test and no
module in `src/` consults it, because its consumer is an agent following
a skill, not a program. A session that ignores the stop rule fails
exactly as quietly as an unset variable would. Two mechanical backstops
exist and neither is the contract itself: `tests/test_house_style.py`
asserts that no committed file re-hardcodes a migrated session path, and
`tests/test_env_contract.py` asserts that every skill naming the
variable also states the stop rule and that the variable is documented
here. Closing the gap properly is registered as
PLN-20260727-1712-session-root-has-no-guard. Under this repository's own
structural-fix rule, documentation is not a guard, and this paragraph
exists so the strong wording above is not mistaken for a mechanism.
