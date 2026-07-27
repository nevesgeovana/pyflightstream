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

Since 2026-07-23 the session documents live outside this repository and
are not committed here. Since 2026-07-27 their home is the coordination
hub, located by the `PYFS_SESSION_ROOT` environment variable (machine
configuration in `.claude/settings.local.json`, never a literal path in
this committed file). Handoffs live under `<session-root>/handoffs/`,
the logbook at `<session-root>/logbook.csv`, the state file at
`<session-root>/STATUS.md`.

**They are committed, in the hub.** Gaining version control is the whole
reason they moved; leaving them dirty in the hub working tree would
throw away what the migration bought. The close therefore makes TWO
commits, in two repositories: the repository-side changes here, and the
session documents in the hub. Keep them separate and do not push the
hub unless asked.

`<session-root>` is a placeholder, not shell syntax. Resolve the
variable and use its value: in PowerShell `$env:PYFS_SESSION_ROOT`, in
bash `$PYFS_SESSION_ROOT`. Writing the bash form in PowerShell yields an
empty string and a path at the drive root, with no error. The full
comparison of the three machine-configuration variables, and the
statement of what does and does not enforce this rule, live once in
CLAUDE.md's Session protocol; this file carries only the operational
rule.

**A `PYFS_SESSION_ROOT` that is unset or unreadable is a configuration
error to stop on, never a silent skip**, because a session that cannot
find the state file cannot state its objective and one that cannot find
the handoff folder would close by writing its record nowhere. Report it
in these terms:

> `PYFS_SESSION_ROOT` is unset, or names a path that is not a readable
> directory containing `STATUS.md` and `handoffs/`. Set it in
> `.claude/settings.local.json` to this repository's session folder in
> the coordination hub, then re-run. Without it the session cannot state
> its objective or write its handoff.

Verify the shape, not just that the path resolves: the hub root carries
a `STATUS.md` of its own, so a variable set too high reads fine and
overwrites the coordination level's state file.

**Planning did not move.** The plan ledger stays in this repository at
`_private/plan/`, because a repository's own plan is one of its own
facts (determination `PLN-20260727-1542-plan-ledger-stays`).

## `out`

Allocate the next HND number. Write
`<session-root>/handoffs/HND-###_<topic>_<YYYY-MM-DD>.md` with:

1. Context: the session objective as stated at the start, and what
   actually happened, one paragraph.
2. Decisions made, each marked decided vs proposed, with who decided.
3. Changes persisted: file paths, commits, test and CI status.
4. Open questions and contradictions.
5. Single highest-value next action.

Under two pages. Then append the session row to
`<session-root>/logbook.csv`, update `<session-root>/STATUS.md`
(milestone table, current focus, open questions). Then commit twice: the
repository-side changes of the session here, and the session documents
in the hub repository. Neither is ever committed to the other. If the
hub-side commit cannot be made, say so in the session record rather than
leaving it silently uncommitted.

Public-surface pause point (DO-CONFIRM, before the closing commit;
NFR-11 of the SRS): if the session changed anything user-visible
(public API, CLIs, extras, behavior, deprecations), confirm that

1. `CHANGELOG.md` Unreleased describes the change;
2. the affected public pages moved with it (README claims, docs
   pages, the gen_docs_pages EXAMPLES list when examples changed);
3. new or amended requirements landed in `docs/srs/` with status and
   evidence.

A session that cannot complete an item records it as a
`_private/plan/` item in the same close; silent deferral is the
failure mode this pause point exists to prevent.

## `in <file>`

Read the given file (typically a capture from a web session). Then:

1. Extract decisions, findings, and next actions.
2. Update `<session-root>/STATUS.md` and stage candidate items in
   `_private/plan/` marked proposed, for Geovana to confirm via
   `/plan`.
3. Allocate its HND number, rename it into
   `<session-root>/handoffs/`, and log it.

Never mark an ingested claim as verified without evidence from this
repository (a test, a committed report, or a manual citation).
