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

## `out`

Allocate the next HND number. Write
`handoffs/HND-###_<topic>_<YYYY-MM-DD>.md` with:

1. Context: the session objective as stated at the start, and what
   actually happened, one paragraph.
2. Decisions made, each marked decided vs proposed, with who decided.
3. Changes persisted: file paths, commits, test and CI status.
4. Open questions and contradictions.
5. Single highest-value next action.

Under two pages. Then append the session row to `logbook.csv`, update
STATUS.md (milestone table, current focus, open questions), and commit
everything together.

Public-surface pause point (DO-CONFIRM, before the closing commit;
NFR-11 of the SRS): if the session changed anything user-visible
(public API, CLIs, extras, behavior, deprecations), confirm that

1. `CHANGELOG.md` Unreleased describes the change;
2. the affected public pages moved with it (README claims, docs
   pages, the gen_docs_pages EXAMPLES list when examples changed);
3. new or amended requirements landed in `docs/srs/` with status and
   evidence.

A session that cannot complete an item records it as a plan.csv item
in the same close; silent deferral is the failure mode this pause
point exists to prevent.

## `in <file>`

Read the given file (typically a capture from a web session). Then:

1. Extract decisions, findings, and next actions.
2. Update STATUS.md and stage candidate items in `plan.csv` marked
   proposed, for Geovana to confirm via `/plan`.
3. Allocate its HND number, rename it into `handoffs/`, and log it.

Never mark an ingested claim as verified without evidence from this
repository (a test, a committed report, or a manual citation).
