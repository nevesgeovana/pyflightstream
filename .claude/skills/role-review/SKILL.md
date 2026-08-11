---
name: role-review
description: Run the role-based reviewer passes (architect, QA, V&V, tech writer, API designer) on a work item's diff and drive every finding to fixed or registered. Use before closing any work item; the definition of done cites this skill.
side-effects: writes the push-gate attestation at .claude/.role_review_attestation.json (local, gitignored), which is the file that unblocks a git push; it also spawns reviewer agents, one of which mutates tracked files inside an isolated worktree
argument-hint: "[git range | staged | last-commit]"
---

## The adversarial pass is a precondition, not a round

A completion claim is not made and then reviewed. The adversarial pass runs
BEFORE the claim, and the claim is not available until it has run.

Before reporting any implementation, guard, test or script as done, run one
hostile pass over your OWN diff, whose success condition is BREAKING the
work rather than confirming it. At minimum:

- every mutation anchor is asserted PRESENT and UNIQUE before it is applied,
  because a mutant whose anchor drifted mutates nothing and passes vacuously
- every new test is shown to go RED when the code it covers is sabotaged; a
  test that stays green under sabotage is not a test
- every regex carries the flags its case needs, and every CLI flag parse
  matches the tool's real precedence rather than the obvious one
- every success message names ONLY properties this run evaluated. A line
  that asserts something the code no longer checks is the defect that is
  hardest to see, because the line looks right
- every arm no case reaches is PRINTED as unreached, never counted as
  covered

- name what you TRIED to break and could not, not only what broke. A pass
  reporting nothing is unfalsifiable until a reader can see which attacks
  were attempted; with the attempts named, a reader can tell a clean diff
  from an incurious one

Report the findings of that pass ALONGSIDE the implementation, including the
ones you fixed. A pass that reports nothing is itself a finding, and says so
rather than staying silent.

This does not replace the gated role-review, which is independent by design
and reviews what a session cannot review about itself. It removes the rounds
that were spent on defects the session could have found alone.

The wording above is `BRF-082`, approved by the author on 2026-08-11 and
taken VERBATIM from the coordination level rather than restated here, because
itaca receives the same text and two independently drafted versions of one
rule diverge inside a month. That is the failure this coordination level was
created from. Every clause traces to a defect this project actually shipped
rather than to a checklist category; the traces are in the brief. Aimed at
this repository in particular because v0.7.0 took EIGHT reviewer passes, and
none of what the later ones found (guards carrying the defect they were
written to prevent, six false allows in a gate that fails closed) was found
before an earlier round had already said done.

CLAUDE.md carries a three-line POINTER to this section under
`## Execution rules`, and the split is deliberate: a precondition that only
exists once someone remembers to invoke a skill is not a precondition, and
restating the reasoning in both files would create the second copy this
project forbids.

## The reviewer passes

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
mistake PLN-20260723-2146-gate-range-defect records.

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

**A pass that MUTATES tracked files runs isolated**, with
`isolation: "worktree"`, and in practice that is the QA pass, because
proving a guard by mutation means editing the file the guard protects.
Four reviewers are read-only by charter and do not need it.

Two reasons, and the second is the one that is not obvious. Four
read-only agents and one mutating agent on the same tree means the
readers see the file mid-mutation: on 2026-08-06 an architect reported
a missing dispatch branch that existed, having read the file while the
QA pass had it edited, and the finding was refuted as wrong when it was
merely mistimed. And a write-then-restore harness cannot survive its own
process being killed. Later the same day a review run died with its host
process and left two mutations in the working tree, each reverting a fix
the session had just made; a blanket `git add -A` would have committed
both under a message claiming the opposite
(PLN-20260806-1400).

**Commit the reviewed work BEFORE the review runs.** That is what made
the incident above recoverable rather than a loss, and it is a
sequencing convention rather than a mechanism: nothing enforces it.
Under this repository's own rule documentation is not a guard, so treat
this paragraph as the reason to check `git status` after a review, not
as protection.

## 4. Update or fix, never leave for later

For each finding, in severity order: fix it in-session, or register
it as a `_private/plan/` item naming the decision owner, or record
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
push until an attestation names every commit in scope for the push.
This exists because a past release ran paraphrased manual checks
instead of the agents.

**What the attestation is, stated exactly, because this file used to
claim more** (REV010-018, corrected 2026-08-03). It is a record that
the local workflow ran and which passes it says it ran. It is NOT
proof that the reviewer agents ran: the `passes` field is recorded and
never checked BY THE GATE (the writer validates the names, so the
sentence is about enforcement rather than about validation), the file is local and gitignored, any process that can
write it clears the gate, and no release job consumes it. The hook's
own module docstring has said this from the start; this section used
to call the attestation mechanical evidence that the reviewer agents
had run, which is the wider claim the hook explicitly refuses to make
about itself. Writing the
attestation without running the agents defeats the seat that catches
your own blind spots, and nothing mechanical will notice; that
residual trust sits with the operator, which is exactly why it is
written down here rather than assumed.

So, as the closing step, after every applicable pass has run and every
finding is fixed or registered, and after the reviewed work is
committed (the attestation must name the commit that will be pushed):

```
python .claude/hooks/write_attestation.py review architect,qa,vv,tech-writer,api-designer [<ref> ...]
```

Pass the passes you actually ran (comma-separated). Name every ref the
push sends; the writer defaults to HEAD, so a ref that sits behind HEAD
(a tag, or a branch that is not checked out) never becomes covered and
the gate keeps denying with the same message. The script stamps each
named ref together with every commit not yet on a remote into
`.claude/.role_review_attestation.json` (local, gitignored). If you
commit anything more after this, the gate blocks again until you
re-review and re-attest the new HEAD: an unreviewed commit never ships.
Never write the attestation without running the agents; that defeats
the seat that catches your own blind spots.

Push the branch and any tag by name, in separate commands.
`--follow-tags`, `--tags`, `--all` and `--mirror` are denied: the gate
cannot resolve what they send without asking the remote, and
`--follow-tags` is how an unattested tag reached a publish workflow
once. Keep the attestation write and the push in separate commands too,
since the hook reads the whole command string and would see the push.

The attestation is necessary, not sufficient: the same gate denies any
push while the shared incident ledger has an open blocking incident for
this repository. If it does, run the `incident-analyst` agent, fix the
incident at its structural cause with a guard and guard evidence, and
set its status to fixed before pushing.
