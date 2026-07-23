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
ITACA repository mirrors the same structure with its own specifics.

## 1. Resolve the work item's diff

`$ARGUMENTS` may be a git range (`main..HEAD`, `HEAD~2..`), `staged`,
or `last-commit`.

Default when empty: the uncommitted changes (staged plus unstaged)
PLUS every commit not yet on a remote, that is
`git rev-list HEAD --not --remotes` together with the working tree.
That default is not a convenience. The push gate requires the
attestation to cover every commit the push makes new, so reviewing only
the tip leaves the earlier commits unreviewed and the push blocked.
Reviewing `last-commit` while three commits sit unpushed is the exact
mistake PLN-082 records.

Produce the file list and keep the item's intent in one sentence; the
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
non-delegable seat (product owner, domain expert, numerical analyst;
seat definitions in `ROLE_TEMPLATE.md`) become questions to the
author, never an agent's call.
Re-run a reviewer only when its findings forced substantive rework of
the item.

## 5. Record the passes

The session record (handoff) lists, per work item: the passes that
ran, findings fixed, findings registered, and questions raised to the
author. When the item closes a plan row, the row's note cites the
passes. A clean pass is recorded as clean; silence is not a record.

## 6. Write the push attestation (mandatory, clears the git-push gate)

The `git push` gate (`.claude/hooks/role_review_gate.py`) blocks every
push until an attestation says these agent passes actually ran for the
exact commit being pushed. This exists because a past release ran
paraphrased manual checks instead of the agents; the attestation is
the mechanical proof that the real agents ran.

So, as the closing step, after every applicable pass has run and every
finding is fixed or registered, and after the reviewed work is
committed (the attestation must name the commit that will be pushed):

```
python .claude/hooks/write_attestation.py review architect,qa,vv,tech-writer,api-designer
```

Pass the passes you actually ran (comma-separated). The script stamps HEAD and every commit not yet on a remote into `.claude/.role_review_attestation.json` (local,
gitignored). If you commit anything more after this, the gate blocks
again until you re-review and re-attest the new HEAD: an unreviewed
commit never ships. Never write the attestation without running the
agents; that defeats the seat that catches your own blind spots.

The attestation is necessary, not sufficient: the same gate denies any
push while the shared incident ledger has an open blocking incident for
this repository. If it does, run the `incident-analyst` agent, fix the
incident at its structural cause with a guard and guard evidence, and
set its status to fixed before pushing.
