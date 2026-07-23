---
name: plan
description: Planning state over plan.csv and the milestone map. Report progress, add agreed items, or propose the next work window.
argument-hint: "[status|add|next]"
disable-model-invocation: true
---

Operation: `$ARGUMENTS`

The milestone map (M0 to M7, v0.1.0, v0.2.0 public, v0.3+) comes from
the Bootstrap Kit (`_private/design/DLV-004`, Section 7) and is
mirrored in `_private/STATUS.md`, which is the up-to-date authority.
`_private/plan.csv` holds the working items with stable PLN ids
(session documents live in `_private/` since 2026-07-23, never
committed).
Rules: never renumber or silently rewrite existing rows; a status
change cites its evidence (commit, test run, committed report); new
rows are added only for items agreed in conversation.

* `status`: read `_private/plan.csv`, `_private/STATUS.md`, and the
  git log. Report per
  milestone: done, in progress, blocked, with the blocking reason and
  the distance to the exit criterion.
* `add`: append items decided in conversation, allocating the next PLN
  ids. Items proposed by Claude but not yet confirmed are marked
  `proposed` in the status column.
* `next`: propose the next work window: which PLN items, in what
  order, with what acceptance criteria, against the current milestone's
  exit criterion. Never decide alone; iterate with Geovana, then `add`
  the agreed rows and update `_private/STATUS.md`'s current focus.
