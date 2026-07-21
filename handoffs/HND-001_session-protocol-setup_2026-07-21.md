# HND-001: session protocol and organization setup (2026-07-21)

## 1. Context

First session of the dedicated pyflightstream Claude Code project.
Objective as stated: consolidate a complete understanding of the
project proposal, stages, and requirements, and install the session
organization scheme reused from the author's research workspace
(session objective at start, handoff at close, living log, planning
scheme). The full design record was read: the SRS, SAD, and Bootstrap
Kit in `_private/design/`, and the three research-workspace handoffs
that created this repository (workspace HND-016 seed documents,
HND-017 M0 executed, HND-018 migration closed). State inherited: M0
done, CI green, single clean root commit acc0e0e, next milestone M1.

## 2. Decisions

1. Session documents (STATUS.md, plan.csv, logbook.csv, handoffs/) are
   committed in the repository, protected by the tier 1 guards, and
   will therefore be public development documentation at v0.1
   (decided by Geovana, this session).
2. Every session starts by stating its objective against STATUS.md and
   ends with `/handoff out`; encoded as the Session protocol section
   in CLAUDE.md (decided, per Geovana's opening brief).
3. Handoff numbering in this repository starts fresh at HND-001; the
   research workspace's sequence is cited as "workspace HND-###"
   (decided by Claude, recorded here).
4. Planning uses `plan.csv` with stable PLN ids mirroring the
   Bootstrap Kit milestone map; no spreadsheet bridge exists in this
   project, so `/plan` operates on the CSV directly (adapted from the
   workspace scheme).

## 3. Changes persisted

* `STATUS.md`: milestone table M0 to v0.2+, current focus M1, open
  questions (xarray at M2, SMI genericization option, gh auth),
  recorded deviations.
* `plan.csv`: PLN-001 to PLN-009 covering M1 through M5.
* `logbook.csv`: bootstrap row plus this session's row.
* `.claude/skills/handoff/SKILL.md` and `.claude/skills/plan/SKILL.md`:
  adapted from the research-workspace skills to this repository's
  guards and evidence rules.
* `CLAUDE.md`: Session protocol section appended.
* Tier 1 tests and commit status: recorded in the logbook row and the
  commit that carries this handoff.

## 4. Open questions

* xarray as a runtime dependency: confirm at M2 (carried from
  workspace HND-016).
* Whether to genericize the SMI name in the repository (open option,
  workspace HND-018 decision 5).
* Persistent `gh auth login` browser flow: optional, Geovana.

## 5. Single highest-value next action

Execute M1: `versions.py` with the 26.XXX scheme and ordered registry
(PLN-001), then the database schema and loader (PLN-002), then the
first ~40 core steady commands with manual page citations (PLN-003),
until the tier 1 database tests pass (PLN-004).
