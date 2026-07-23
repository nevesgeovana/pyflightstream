---
name: role-review
description: Run the role-based reviewer passes (architect, QA, V&V, tech writer, API designer) on a work item's diff and drive every finding to fixed or registered. Use before closing any work item; the definition of done cites this skill.
argument-hint: "[git range | staged | last-commit]"
---

Role-based review per the team-role model adopted 2026-07-23
(PLN-025): the implementer never closes an item as its only reviewer.
Each pass is an agent from `.claude/agents/` with its own charter;
this skill decides which passes apply, runs them, and enforces the
update-or-fix rule on their findings. The template behind the
charters is documented in `ROLE_TEMPLATE.md` next to this file; the
itaca repository mirrors the same structure with its own specifics.

## 1. Resolve the work item's diff

`$ARGUMENTS` may be a git range (`main..HEAD`, `HEAD~2..`), `staged`,
or `last-commit`. Default when empty: the uncommitted changes
(staged plus unstaged) if any exist, else the last commit. Produce
the file list and keep the item's intent in one sentence; the
reviewers receive both and read the repository themselves.

## 2. Decide the applicable passes

| Reviewer | Runs when the diff touches |
|---|---|
| architect-reviewer | public API or `__init__` exports; new or moved modules; imports across subpackages; pyproject dependencies or extras |
| qa-engineer | anything under `src/` or `tests/` |
| vv-engineer | `src/pyflightstream/commands/`; `reports/`; physics references or drift bands; any solver-behavior claim |
| tech-writer | any public surface: public functions or CLIs under `src/`, README, docs/, CHANGELOG, examples/, guide/ |
| api-designer | new or changed public signatures; CLI commands or flags; error messages; examples |

Any code change runs at least qa-engineer and tech-writer. A
docs-only change runs tech-writer alone. When in doubt whether a
pass applies, it applies.

## 3. Run the passes

Spawn every applicable reviewer in parallel (one Agent call each),
passing the git range, the file list, and the intent sentence. Do
not summarize the diff for them beyond that; their charters tell
them what to read. Wait for all passes before acting on any finding.

## 4. Update or fix, never leave for later

For each finding, in severity order: fix it in-session, or register
it as a `_private/plan.csv` item naming the decision owner, or record
in the session notes why it is not a defect (with the reviewer named,
so the disagreement is auditable). Findings that require a
non-delegable seat (product owner, aerodynamics SME, numerical
analyst) become questions to the author, never an agent's call.
Re-run a reviewer only when its findings forced substantive rework of
the item.

## 5. Record the passes

The session record (handoff) lists, per work item: the passes that
ran, findings fixed, findings registered, and questions raised to the
author. When the item closes a plan row, the row's note cites the
passes. A clean pass is recorded as clean; silence is not a record.
