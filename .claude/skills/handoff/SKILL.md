---
name: handoff
description: Session closure documentation. Writes the outgoing session handoff, appends the logbook row, and updates STATUS.md; can also ingest an incoming handoff or capture file.
argument-hint: "[out|in <file>]"
disable-model-invocation: true
---

Operation: `$ARGUMENTS`

Handoffs are the session documentation of this repository: every session
ends with one. They are continuity records, not verified evidence. The
numbering here starts at HND-001 and is independent of the research
workspace's handoff sequence; cite those as "workspace HND-###".

All handoff content obeys the repository guards: English, no em or en
dashes, no manual text, invariant 5 wording (never name the author's
employer or the predecessor toolchain; say "the predecessor toolchain"
or "the author's legacy scripts").

Since 2026-07-23 the session documents live in `_private/` (the
OneDrive-synced junction), never committed: handoffs under
`_private/handoffs/`, the logbook at `_private/logbook.csv`, the state
file at `_private/STATUS.md`, planning at `_private/plan.csv`. The
closing commit covers only repository changes.

## `out`

Allocate the next HND number. Write
`_private/handoffs/HND-###_<topic>_<YYYY-MM-DD>.md` with:

1. Context: the session objective as stated at the start, and what
   actually happened, one paragraph.
2. Decisions made, each marked decided vs proposed, with who decided.
3. Changes persisted: file paths, commits, test and CI status.
4. Open questions and contradictions.
5. Single highest-value next action.

Under two pages. Then append the session row to
`_private/logbook.csv`, update `_private/STATUS.md` (milestone table,
current focus, open questions), and commit the repository-side changes
of the session (the session documents themselves are not committed).

Public-surface pause point (DO-CONFIRM, before the closing commit;
NFR-11 of the SRS): if the session changed anything user-visible
(public API, CLIs, extras, behavior, deprecations), confirm that

1. `CHANGELOG.md` Unreleased describes the change;
2. the affected public pages moved with it (README claims, docs
   pages, the gen_docs_pages EXAMPLES list when examples changed);
3. new or amended requirements landed in `docs/srs/` with status and
   evidence.

A session that cannot complete an item records it as a
`_private/plan.csv` item in the same close; silent deferral is the
failure mode this pause point exists to prevent.

## `in <file>`

Read the given file (typically a capture from a web session). Then:

1. Extract decisions, findings, and next actions.
2. Update `_private/STATUS.md` and stage candidate items in
   `_private/plan.csv` marked proposed, for Geovana to confirm via
   `/plan`.
3. Allocate its HND number, rename it into `_private/handoffs/`, and
   log it.

Never mark an ingested claim as verified without evidence from this
repository (a test, a committed report, or a manual citation).
