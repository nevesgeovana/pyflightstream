---
name: plan
description: Planning state over the plan ledger and the milestone map. Report progress, add agreed items, or propose the next work window.
argument-hint: "[status|add|next]"
disable-model-invocation: true
---

Operation: `$ARGUMENTS`

The milestone map (M0 to M7, v0.1.0, v0.2.0 public, v0.3+) comes from
the Bootstrap Kit (`_private/design/DLV-004`, Section 7) and is
mirrored in `_private/STATUS.md`, which is the up-to-date authority.

`_private/plan/` holds the working items, **one file per item**, named
for its own id. The rules and the entry format are in
`_private/plan/README.md`; read it before adding anything. Session
documents live in `_private/` since 2026-07-23 and are never committed.

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

* `status`: read `_private/plan/`, `_private/STATUS.md`, and the git
  log. Report per milestone: done, in progress, blocked, with the
  blocking reason and the distance to the exit criterion.
* `add`: write one new file per item decided in conversation, with a
  timestamp id. Items proposed by Claude but not yet confirmed carry
  `status: planned` and say so in the note.
* `next`: propose the next work window: which items, in what order,
  with what acceptance criteria, against the current milestone's exit
  criterion. Never decide alone; iterate with Geovana, then `add` the
  agreed items and update `_private/STATUS.md`'s current focus.

After writing, run the validator so a malformed entry surfaces now
rather than in a later session:
`python C:\WORK\_private_snapshots\check_plan.py _private/plan`
