---
name: develop
description: Execute one pyflightstream work item end to end, in this repository's own order: pin it to an FR or NFR and a plan node, write the implementation plan before touching anything, usage example, falsifying test measured RED on the base, minimal implementation, records in the same step, the adversarial pass, commit, review, then close the node with what was implemented and the evidence for it. Use whenever a work item is about to be implemented, whether it comes from the plan tree, the plan ledger, a review finding, an incident, or the author directly. Planning is the plan skill, requirement derivation is derive-requirements, a new solver command is add-command, closure of the session is handoff, and the reviewer passes are role-review; this skill covers the middle, where the change is actually made.
argument-hint: "<PFS/OPS plan node id | plan ledger id | FR/NFR id | one sentence naming the item>"
allowed-tools: Bash, PowerShell, Read, Write, Edit, Grep, Glob, Skill
side-effects: writes source, tests, docs and command-database entries in this repository; writes plan ledger items under _private/plan/ and session records under the resolved PYFS_SESSION_ROOT; makes commits. It does NOT push, does not write an attestation, and does not spend a licensed solver seat without the author saying so.
---

Work item: `$ARGUMENTS`

This skill is a **loading order, not a second rulebook**. Every rule it needs
already lives in `CLAUDE.md`, `docs/srs/`, the `plan` and `role-review` skills,
and the shared incident ledger's own README. This file points at them and never
restates them, because a rule copied here is a rule that will drift, and this
repository's own charter forbids the second copy.

It exists because planning, auditing, reviewing, releasing, closing, deriving
requirements and adding a command each have a skill here, and DEVELOPING did
not. The highest-ceremony part of the process was the one running from prose
reconstructed each session.

Two things are new here rather than inherited from the sister library's copy,
and they are the reason this file is not that one: the CLOSURE CONTRACT, which
did not exist when that skill was written, and the LICENSED SEAT, which that
repository has no reason to know about.

## 1. Pin the item, before touching anything

An item that cannot name its authority is not ready. Resolve all four, in this
order, and stop at the first that fails.

* **The requirement.** An `FR` or `NFR` in `docs/srs/`. Find it or ask the
  author. Never infer the requirement from the code, which makes the code its
  own specification. If the item has no requirement behind it, that is the
  `derive-requirements` skill's work and the author's acceptance, not a
  judgment to make here.
* **The plan node**, `PFS-2xxx` or `OPS-2xxx` in the coordination level's
  planning tree. It carries the item's acceptance sentence, and that sentence
  is what this session is trying to satisfy.
* **The session root.** Resolve `PYFS_SESSION_ROOT` and use its value; read
  `CLAUDE.md`, "Session protocol", for the stop rule and for why the bash form
  of the variable must never be written in a PowerShell command. Unset or
  unreadable STOPS; it is never a skip.
* **The ledger entry.** If the item has one under `_private/plan/`, set it
  `doing`. If it has none and it is real work, register it with the `plan`
  skill first. Work that exists only in a transcript is work nobody can find.

**REFUSE A DESIGN-FIRST NODE.** A node flagged design-first is a decision the
author owes, and it legitimately has no children because the design is what
produces them. Implementing one means inventing her answer and then writing it
down where it will look decided. Say which decision is missing and stop.

**A node whose acceptance sentence is empty is not ready either**, and most of
the tree is in that state today. Ask for the sentence, or write one and get it
confirmed, before writing a test: a test written against an unstated acceptance
tests what the implementer imagined.

## 2. Write the implementation plan, BEFORE the work

The plan node carries an `Implementation plan` field and it is written by
planning, before the change, not reconstructed afterwards. Say what will be
built, in enough detail that someone else could tell whether the result matches
it. This is half of the closure contract; step 9 is the other half.

If writing it reveals that the item is really two items, split it in the plan
first. That is the cheapest moment this discovery will ever have.

## 3. Usage example first

Write the call as a user would make it, in the numpydoc `Examples` section or
under `examples/`, before any test. It is the first place a wrong interface is
cheap to fix and it is what the API-designer pass will read. Examples are
percent-format `.py` and never a notebook (`CLAUDE.md`, invariant 7).

**For a defect fix with no new interface** this step is the REPRODUCTION
instead: the shortest call that exhibits the defect, in the test module's own
docstring. Skip the step only when you can name the existing example that
already covers the call, and name it.

## 4. The falsifying test, measured RED on the base

This is the whole technical content of TDD and the only part of it a final diff
can evidence, so it is the one step this skill asks you to **record a
measurement for**.

Write the test that fails for the item's reason. Run it against the tree **as
it is, before the implementation exists**, and keep the output: the test id and
the way it failed.

* **Read the exit status from the process, never through a pipe.** The
  execution guard denies the shape outright; `CLAUDE.md`, "Execution rules",
  carries the reasoning and `version-control` carries the remedy.
* A test that errors on an import or a missing name is not yet a falsifying
  test. Make it fail on the ASSERTION, so what turns it green is the behavior
  and not the existence of a symbol.
* If the test is green before the implementation, the item is either already
  done or the test does not measure it. Both are findings; stop and say which.
* **Measure the carrier, never the mention.** A guard satisfied by an id in a
  comment, a docstring or an assertion message is not a guard.
* **A fixture is not a solver run.** If the only way to make the test fail for
  the right reason is to run the solver, go to step 6 before writing more.

## 5. Minimal implementation, then refactor

Make that test pass and nothing more. Then refactor with the suite green. Scope
beyond the item goes to the ledger, not into the diff.

Three constraints this repository has that a general TDD loop does not:

* **Dependencies flow downward and never upward**
  (`CLAUDE.md`, "Layout"). An import that points up is a design error, not a
  lint finding, and the deferred-import trick that hides one is how the matrix
  reader ended up below the layer it needs.
* **Prefer an existing MIT-compatible library for anything generic**, and keep
  domain logic in-house (`CLAUDE.md`, "Engineering policy"). Solver semantics,
  evidence rules and physics are ours; parsing, validation and arrays are not.
* **The clean-room rule** (`CLAUDE.md`, invariant 2). The emitter is specified
  from the manual and from probe evidence only. Never read or adapt the
  AGPL implementation, including the copy in the old research workspace.

**Before an edit made under review pressure**, design before edit: state what is
wrong and what the change is, then make it. A one-line fix under pressure is the
dangerous one, because it looks too small to be worth thinking about. Note which
file NOT to read for this: `.claude/kit/review-policy.md` is vendored for the
drift row alone and is explicitly NOT adopted as this repository's review policy
(`CLAUDE.md`, "The vendored process kit"). What binds here is the `role-review`
skill and the Role passes paragraph of the definition of done.

## 6. Command-database work and the licensed seat

**A new or changed solver command goes through the `add-command` skill**, never
by hand. Every entry is evidence-backed: a `manual_ref` for documented, a
committed probe report for verified or broken, and **no status is ever
hand-edited** (`CLAUDE.md`, invariant 3). Manual facts appear as paraphrases
with a page citation and never as reproduced text (invariant 1).

**A licensed solver seat is scarce and the author schedules it.** `run-physics`,
`run-validity` and `fts-version-update` each spend one. Do not book one to
satisfy something a fixture or a golden can satisfy, and do not book one at all
without saying, before the run, what question it answers and why nothing
cheaper answers it. A run spent to confirm something already known is a run she
cannot spend on something unknown.

**Do not read an emitted command as a proven one.** A command that emits has
been shown to serialise, not to be accepted by the solver. Where an item rests
on a `documented` entry, say so where a user meets it.

## 7. Records in the same step, not as a closing pass

Whatever the change touches writes its record in the SAME step, so a session
that ends early leaves no undocumented change:

| the change touches | it also writes |
|---|---|
| the public surface: API, CLI, extras, behavior, deprecations | `CHANGELOG.md` Unreleased, plus every public page it invalidates, in this session (`CLAUDE.md`, "Definition of done", SRS NFR-11) |
| a requirement's meaning or status | `docs/srs/` |
| the command database | the entry's evidence fields, through `add-command` |
| anything else worth finding later | a plan ledger item, through the `plan` skill |

**A defect found on the way is an incident.** Fixed at its STRUCTURAL cause on
its FIRST occurrence, in this session, carrying a guard and the evidence that
the guard blocks the original failure when re-run. Documentation is not a
guard, and a guard is proven by restoring the defect and watching it deny, not
by a suite that passes. The full policy is the shared ledger's own README, at
`COORD_INCIDENT_LEDGER`; the `incident-analyst` agent drafts the record and
whether it blocks is the author's call.

## 8. The adversarial pass, then the definition of done

**The adversarial pass is a PRECONDITION of a completion claim, not a round
after it** (`CLAUDE.md`, "Execution rules"). Before reporting anything as done,
run one hostile pass over your own diff whose success condition is BREAKING the
work, and report what it found alongside the work, including what you tried to
break and could not.

Then the definition of done, by pointer: tier-1 tests, typed args and citations
on new commands, fixtures on new parsers, numpydoc with units and reference
frames, the docs build, documentation currency. All of it is in `CLAUDE.md` and
the SRS. Read it there.

**Run the repository's own gate rather than a command written here.** The gate
is `.pre-commit-config.yaml` and it moves; naming its commands in this file
would make the skill stale the week the tiers change. `pre-commit install` once
per clone installs every type it declares.

**A completion claim carries fresh command output in the same message.** No
"done", "passing" or "ready to push" without evidence a reader can see.

## 9. Commit, review, and only then close the node

**Review runs on a COMMITTED range**, so commit first and review second, folding
findings in with `--amend` or a `--fixup`.

Conventional Commits for the subject, per the definition of done. The BODY
carries the two things the diff cannot show by itself: the RED measurement from
step 4, and every FR, NFR, plan node and ledger id the item touched, named. This
repository writes prose bodies rather than machine trailers, so name them in a
sentence rather than inventing a trailer key it does not use.

Then invoke `role-review` over the committed range. It decides which passes
apply, runs the reviewer agents, and drives every finding to fixed or
registered. It also writes the attestation; **this skill never does**, and the
push itself belongs to `version-control`.

**Then close the node, and closing has two fields, not one.**

* `Implemented as`: what was actually built, which is allowed to differ from
  step 2's plan. Where it differs, say why; a plan that is quietly rewritten to
  match the result records nothing.
* `Evidence`: what a reader can CHECK. A commit range, a test id and its output,
  a committed report. Not a claim, not a link to this conversation, and not the
  word "verified".

A node is `implemented` when the first is written and `evidenced` when the
second is, and the two states are deliberately different. **The release does
not ship while any item carries it without evidence**, which is what the
coordination level's release checker enforces on absence rather than on
failure.

**Where the two fields are written is not yet mechanised**, and this is stated
rather than guessed: the plan node lives in the coordination level's tree, this
repository writes into it only through the session root, and no ingest exists
today. Until one does, write both fields into the item's record under
`PYFS_SESSION_ROOT` and say in the handoff that they are owed upward. Do not
invent a path into the other repository.

Finally set the ledger entry `done`, citing the same evidence, and verify the
closure against the CODE rather than against the plan.
