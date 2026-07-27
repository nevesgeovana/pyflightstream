---
name: plan
description: Planning state over the plan ledger and the milestone map. Report progress, add agreed items, or propose the next work window.
argument-hint: "[status|add|next]"
disable-model-invocation: true
---

Operation: `$ARGUMENTS`

The milestone map (M0 to M7, v0.1.0, v0.2.0 public, v0.3+) is DEFINED by
the Bootstrap Kit (`_private/design/DLV-004`, Section 7), which stayed in
this repository. Its current STATE (what is done, in progress or
blocked) is tracked in `<session-root>/STATUS.md`, which moved to the
hub. When the two disagree about the map itself, DLV-004 wins; when they
disagree about status, STATUS.md wins. The split is a consequence of the
2026-07-27 migration, so name which one you read.

`_private/plan/` holds the working items, **one file per item**, named
for its own id. The rules and the entry format are in
`_private/plan/README.md`; read it before adding anything.

Two homes, deliberately. The **plan ledger and the design documents stay
in this repository** under `_private/`, because a repository's own plan
and architecture are its own facts (determination
`PLN-20260727-1542-plan-ledger-stays`, and the coordination charter's
"no duplicated project facts"). The **session documents** (state file,
handoffs, logbook, inbox, progress reports) moved to the coordination
hub on 2026-07-27 and are located by the `PYFS_SESSION_ROOT`
environment variable, machine configuration in
`.claude/settings.local.json` and never a literal path in this committed
file. `<session-root>` below is a placeholder, not shell syntax: resolve
the variable and use its value. CLAUDE.md's Session protocol is the
single home of that rule and of the comparison between the three
variables; this file carries only what an operation needs. Neither home
is ever committed to this repository.

**The stop rule is per operation, not for the whole skill.** `add`
writes only to `_private/plan/` and validates with a different variable,
so an unreachable session root does not stop it: proceed and say in the
session record that STATUS.md was not consulted. `status` and `next`
read or write `<session-root>/STATUS.md`, so for those an unset or
unreadable `PYFS_SESSION_ROOT` is a configuration error to report and
stop on, never a silent skip. Blocking `add` on a variable its outcome
does not depend on would be the same needless coupling that
`PLN-20260727-1542-plan-ledger-stays` kept the ledger local to avoid.

The ledger was a single `plan.csv` until 2026-07-23, when a central
counter written by concurrent sessions produced three id collisions in
one day and leaked a wrong citation into a committed file. The table is
archived at `_private/archive/plan_2026-07-23_superseded.csv`; do not
append to it.

Rules:

- **Never allocate an id from the maximum of anything.** A new item gets
  a timestamp id, `PLN-<YYYYMMDD>-<HHMM>-<slug>`, so two sessions
  writing at once cannot collide and nobody has to read the ledger to
  allocate. This rule is the whole reason for the shape.
- **Never renumber or reuse an existing id.** `PLN-001` through
  `PLN-088` keep their identity: they are cited in committed evidence
  reports, the command database, the CHANGELOG and the SRS.
- A status change cites its evidence: a commit, a test run, or a
  committed report.
- New items are added only for work agreed in conversation.

Operations:

* `status`: read `_private/plan/`, `<session-root>/STATUS.md`, and
  the git log. Report per milestone: done, in progress, blocked, with
  the blocking reason and the distance to the exit criterion.
* `add`: write one new file per item decided in conversation, with a
  timestamp id. Items proposed by Claude but not yet confirmed carry
  `status: planned` and say so in the note.
* `next`: propose the next work window: which items, in what order,
  with what acceptance criteria, against the current milestone's exit
  criterion. Never decide alone; iterate with Geovana, then `add` the
  agreed items and update `<session-root>/STATUS.md`'s current
  focus.

After writing, run the validator so a malformed entry surfaces now
rather than in a later session. The validator is the vendored kit
`check_plan_kit.py` (Option C: the strict guards plus the union
vocabulary), whose location is machine configuration held in the
`PYFS_PLAN_CHECKER` environment variable (set in
`.claude/settings.local.json`, never a literal path in this committed
file, mirroring how `PYFS_INCIDENT_LEDGER` locates the incident
ledger). Read the variable; never assume a path. The counter ids
`PLN-001`..`PLN-088` are grandfathered from the timestamp-id shape guard
by `_private/plan/legacy_ids.txt` (that waiver only; every other guard
still applies, and a new counter-shaped id is still rejected), which is
why the renumber rule above holds without failing the checker.

- **Unset means the check is skipped**, not failed: a clone that never
  configured the validator can still work, exactly as an unset incident
  ledger does not apply. Say plainly in the session record that the
  ledger was written but not machine-validated, so the skipped check is
  visible and not mistaken for a pass.
- Set but pointing at no readable checker is a configuration error to
  report to the author, not a silent skip.

When it is set and readable, run it against the ledger folder. Anchor
the ledger path to THIS repository rather than to the current directory:
a bare `_private/plan` resolves only when the session happens to sit at
the top level, and this repository has already been bitten once by a
relative path that behaved differently from a nested cwd (the gate hook,
HND-047). Use `CLAUDE_PROJECT_DIR`, the anchor that fix already adopted
and that `.claude/settings.json` still uses. In PowerShell (this
environment's primary shell):

```
python "$env:PYFS_PLAN_CHECKER" "$env:CLAUDE_PROJECT_DIR/_private/plan"
```

or in bash:

```
python "$PYFS_PLAN_CHECKER" "$CLAUDE_PROJECT_DIR/_private/plan"
```

Do NOT anchor with `git rev-parse --show-toplevel`. It returns the
toplevel of whichever repository the current directory is in, and since
2026-07-27 a session routinely has a second repository in its path (the
coordination hub). That form would validate the wrong tree, or report a
missing directory for a perfectly clean ledger. If `CLAUDE_PROJECT_DIR`
is empty the path collapses to `/_private/plan`, which the checker
rejects loudly rather than validating something else.

Read the exit code carefully. Five outcomes exist and only the first is
a clean ledger; two of the others look like something they are not.

| Exit | Output | Meaning |
|---|---|---|
| 0 | `N entries checked ... 0 bad` (count is zero) | clean ledger |
| 0 | `no entries in <path>` | **the directory exists but is empty: nothing was validated** |
| 1 | one or a few `FAIL` blocks naming the entry and the guard | a real ledger defect |
| 1 | **every** `PLN-0##` id fails the shape guard at once | **`legacy_ids.txt` is missing or unreadable, NOT 88 bad entries** |
| 1 | `not a directory: <path>` | the path does not resolve, or `CLAUDE_PROJECT_DIR` was empty; nothing was checked |

Rows two and four are the dangerous ones.

**Row two** is why this table replaced a sentence claiming the checker
always fails loud. An empty-but-present directory exits 0, so a checker
aimed at a ledger that moved out from under it reports success and
validates nothing. Not hypothetical: the 2026-07-27 migration moved
trees out of `_private/`, and the sister library registered the same
defect independently the same day.

**Row four** is worse, because it is loud in a way that points at the
wrong fix. `legacy_ids.txt` lives in `_private/plan/` beside the
entries. If it goes missing or unreadable the vendored checker returns
an empty exemption set silently, so all of `PLN-001`..`PLN-088` fail the
timestamp-shape guard at once, each with a message saying the id "would
reintroduce the central counter". A reader who trusts row three reads
that as 88 real defects and reaches for renumbering, which the rules
above forbid outright and which is how a wrong citation once leaked into
a committed file. The signature to recognize is the count: a real defect
is one or a few entries, never every legacy id simultaneously.

Verified 2026-07-27 against the vendored kit 0.2.2, which is what this
repository runs. Kit 0.2.3 replaces row four with an explicit
`CONFIG ERROR:` exit 2; that row is NOT in the vendored checker today
and must not be relied on until the re-vendor
(`PLN-20260727-1707-kit-lag-0-2-3`), which is also when this table
changes. `tests/test_plan_checker.py` pins rows two and five so a
re-vendor cannot change them silently.
