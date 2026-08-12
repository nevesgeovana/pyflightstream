<!--
ITACA / pyflightstream shared process kit
kit-version: 0.2.21
artifact: version-control.md
body-sha256: a4a219dea812abef16cfed55cac02a83d2f7d1d1525238cc9ee87bd46400ec59
canonical-source: BUILT for the kit (0.2.15, HUB-11) from the author's proposal of 2026-08-01. In two lanes the push step failed five separate ways and none of them was about the code; three of the five are addressed by carrying the correct sequence as a template so an operator does not reconstruct it, at a fraction of the cost of the two the pre-push receipt addresses. Records: ITC-20260801-2330, ITC-20260801-0900, coordination/DESIGN_HUB-11_kit_batch.md item 2. 0.2.17 adds section 6, read CI for the SHA you pushed: HUB-13 items 2 and 3, the local hooks were never the mirror of CI that REQ-96 claims, so CI becomes the authority and a close that cannot read it refuses to say closed. 0.2.17 ALSO moved this file's provenance comment below the frontmatter fence, for BRF-075, because with the comment first a loader reads the comment as the frontmatter region and this skill sat unselectable in itaca's roster from 0.2.15. THAT HALF WAS REVERTED on 2026-08-03 under INC-20260803-0250-both, and the banner is the FIRST thing in the file: four implementations of the body rule exist across three repositories, the promotion changed one and proved itself harmless using that one, and two of the other three live inside the libraries where this level cannot reach them. See "Where the header sits" in the kit README, which is the unamended rule. THIS SENTENCE ASSERTED THE MOVE AS DONE UNTIL 2026-08-11, when ITA-15 routed the consequence up and the master was read rather than trusted; a canonical header that describes a withdrawn change is the same defect class as a success line asserting a property nothing evaluates. BRF-075 STAYS OPEN and its cost is unpaid: a frontmatter-bearing artifact still arrives at a loader with the comment first. Correcting this header moves NO body hash, because it sits above the provenance marker line, and for exactly that reason NOTHING propagates the correction to a vendored copy: no drift test compares header prose. Naming that marker literally in this prose is itself a trap and was hit while writing this correction: the splitter takes the FIRST occurrence, so a header that spells the marker out redefines the body boundary and the digest moves. Refer to it, never spell it. 0.2.21 adds the six CI denial sub-kinds to "If the push is denied", from BRF-090: the gate at 0.2.18 can print [ci-red], [ci-running], [ci-unknown], [ci-config], [ci-budget] and [ci-tag], and the document an operator reads at the moment they are blocked did not know the newest reasons they can be blocked for. Promoted AHEAD of the batched spelling pass and alone, because pyflightstream vendors this artifact for the first time in PFS-12 and a body that changes twice in a week costs two adoptions. MEASURED WHEN PROMOTING, and it is the reason this bump is not cosmetic: the master reached 0.2.17 and NOT ONE deployment took it. itaca's of-record copy and this repository's own deployed skill both still hashed to the 0.2.15 body, and nothing checks a deployed skill body against its master in any of the three trees. See coordination/DESIGN_HUB-13_kit_0217.md items 3 and 5.
note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
END KIT PROVENANCE (body verbatim below)
-->
---
name: version-control
description: The correct sequence for committing, attesting and pushing in a repository carrying the shared push gate, with the verification step that does not trust an exit code. Use whenever work is about to be committed or pushed, when a push was denied and the reason is not obvious, when a push appeared to fail but may have succeeded, or when staging a change that other sessions may share the tree with. It carries the sequence as a template so it is not reconstructed from memory.
allowed-tools: Bash, Read, Grep, Glob
side-effects: none
---

# Committing and pushing, in the order that works

This skill exists because the push step is where lanes lose time to
failures that have nothing to do with the code. In two measured lanes it
failed five separate ways in one evening:

1. a redirection flag after `git push` in the same command string, denied
   by the review gate reading it as a ref it could not resolve;
2. an agent background task killed inside the suite, twice, for a cause
   that is NOT established;
3. `pytest` and `mypy` absent from PATH because the shell had no
   environment activated, so the hook refused, correctly and fail-closed;
4. a PowerShell PATH assignment sent to a bash shell;
5. an in-session shell with a two-minute timeout, so a thirteen-minute
   hook could not run there at all.

Three of those, 1, 3 and 4, are answered by following the sequence below
rather than by any mechanism. Number 5 is answered by the pre-push
receipt, `prepush_receipt.py`, which stops the suite being run a second
time on content that already passed. Number 2 is NOT answered by anything
here, and its cause is not known; do not record it as known.

## The rule this whole file follows from

**The push gate is a `PreToolUse` hook.** It inspects the WHOLE command
string BEFORE anything in it runs. Everything below follows from that one
fact:

- A string that commits and then pushes is checked against a state in
  which the commit does not exist yet.
- A string that writes the attestation and then pushes is denied before
  the attestation is written.
- A flag after `git push` is read as part of the push, including a
  redirection the shell would have consumed.

So: **five separate commands, in this order, with nothing appended to any
of them.**

## 1. Activate the environment, and prove it

A hook that runs `pytest` or `mypy` finds them only if the environment is
active in the shell the hook inherits. An inactive environment produces a
refusal that looks like a tooling failure and is not one.

Activate using the syntax of the shell you are actually in. Sending a
PowerShell assignment to a bash tool, or the reverse, is one of the five
measured failures and it does not announce itself; it produces a command
not found, or nothing at all.

    # PowerShell
    .\.venv\Scripts\Activate.ps1

    # bash / git-bash
    source .venv/Scripts/activate     # Windows layout
    source .venv/bin/activate         # POSIX layout

Then PROVE it, in the same shell, before relying on it:

    python -c "import sys; print(sys.prefix)"

If that does not print the repository's own environment, nothing after it
is trustworthy. Do not proceed by adding a directory to PATH by hand;
activate properly, because PATH edits are per-shell and the next tool call
may be a different shell.

## 2. Commit, staging BY PATH

    git add <path> <path> ...
    git commit -m "<message>"

**Never `git add .`, `git add -A`, or a directory.** Another session, an
agent, or a generated artifact may hold changes in the same tree, and a
directory-wide stage commits work you did not make and cannot describe.
This is the tree-ownership rule and it is not advisory: never revert,
restore, checkout, stash or commit a change you did not make.

If the tree carries changes that are not yours, stage only your paths and
say in the message what the commit covers.

## 3. Attest, as its own command, with no pipe

    python .claude/hooks/write_attestation.py review <passes> <ref> [<ref> ...]

Three things, each of which has failed at least once:

- **Its own command.** Not joined to the push by `&&`, `;` or a newline.
  The gate would see the push in the same string and deny before this
  runs.
- **No pipe.** A piped command's exit status is the pipeline's, not the
  writer's. Read the status from the process.
- **Cover the whole range.** The attestation must cover every commit the
  push makes new, plus the ref being pushed. Review the unpushed RANGE,
  not the tip:

      git rev-list HEAD --not --remotes --oneline

  If that lists more than one commit, the review had to cover all of
  them. The writer says so in its own output when it does.

`<passes>` is the comma-separated list of the reviewer passes that
ACTUALLY ran. It is an audit record. A pass named here that did not run is
a false statement in the one file whose job is being trustworthy.

## 4. Push, alone

    git push origin <branch>

Nothing appended. No `2>&1`, no `> log.txt`, no `&& echo done`, no second
command after a semicolon. A redirection after `git push` was denied by
the gate as an unresolvable ref, which is the gate failing CLOSED and
doing its job; the fix is the command, not the gate.

Push a SISTER repository with `git -C <repo> push origin <branch>`, so the
gate resolves that repository's own rules rather than the current
directory's.

## 5. Verify on the remote, NOT by the exit code

**This is the step most often skipped and it is the one that is load
bearing.**

    git ls-remote origin <branch>
    git rev-list HEAD --not --remotes

The first prints the commit the remote now holds; compare it to your
`HEAD`. The second must print NOTHING when the push succeeded: anything it
prints is a commit the remote does not have.

WHY, and it is mechanical rather than stylistic. PowerShell 5.1 wraps a
native command's stderr into an ErrorRecord and sets `$?` to false even
when the process exited 0, and `git push` writes its progress to stderr.
So a SUCCESSFUL push reads as a failure, and a session that trusts the
status will re-push, re-run a suite, or conclude that work was lost that
was not. The remote's own answer is the only trustworthy one.

The same reasoning applies in reverse: never redirect a native command's
stderr in PowerShell to make it look clean. It changes the status you are
about to read.

## 6. Read CI for the SHA you pushed, and refuse to close without it

**WHO OWNS THIS STEP.** The author decided on 2026-08-02 that the closing
ritual lives in EACH REPOSITORY'S OWN HANDOFF, not in the kit. So this
section is not the ritual: it is the push sequence handing off to it, and
what the kit ships is the CHECKER, `ci_state.py`, one body with one set of
mutations. Each repository's `handoff` CALLS it and decides what its own
close does with the answer, which is where a repository states anything
particular to itself. Three handoffs calling one body is a different thing
from three handoffs each implementing the rule.

Three wirings are owed and named: itaca's, pyflightstream's at `PFS-1`, and
the coordination level's own.

**The remote holding your commit is not the same fact as CI accepting it.**
Step 5 proves the bytes arrived. This step is the one that says whether
they work, and it exists because three lanes ran a green local suite over a
test that was red on every CI run and pushed anyway.

    python <your kit path>/ci_state.py poll --sha $(git rev-parse HEAD)

Substitute your repository's own vendoring path. The three consumers
differ and a kit master does not carry one repository's layout: itaca
vendors under `.claude/kit/`, pyflightstream under `.claude/tools/`,
and the coordination level deploys individual bodies under
`.claude/hooks/`.

Four answers, and only one of them lets you use the word closed:

- `GREEN`: every run for that SHA concluded successfully. Say closed.
- `RED`: name the failing run in your report. Not closed.
- `RUNNING`: CI has not concluded yet. Not closed, YET, and see below.
- `UNKNOWN`: no network, no `gh`, an expired token, no run visible for the
  SHA, or a conclusion the body does not recognise. Not closed, and the
  report names the SHA and THE REASON.

**Unknown is never green.** A SHA with no CI run looks clean and is not:
"no news is good news" is exactly the reasoning behind a gate that failed
OPEN, which this project has already paid for once. The refusal never
blocks the push, which has already happened; it forbids the CLAIM.

### The ordinary case, which is RUNNING, and why it costs you nothing

Right after a push, CI is queued. If that turned every close into a human
action the step would be routed around within a week, so it does not:

    python <your kit path>/detached_gate.py start --label ci -- \
        python <your kit path>/ci_state.py await --sha <sha>

That returns AT ONCE with a run id. The wait happens in a process that
outlives your session and has no ceiling. Later, in any shell:

    python <your kit path>/detached_gate.py state --label ci

which prints `GREEN`, `RED`, `RUNNING` or `UNKNOWN` in the same four-state
vocabulary, and `report --label ci` prints the captured output when it is
red. This is the same mechanism the pre-push hook's own long tier can be
run under, composed with itself rather than a second mechanism holding
the same rule in a second vocabulary.

## If the push is denied

Read the deny message; it names its own category.

- `[config]` and a variable name: the incident ledger variable is not set
  in this shell. An ABSENT ledger DENIES, deliberately, because an
  unreadable ledger cannot prove that no blocking incident exists. Export
  it and try again.
- A blocking incident: the ledger holds an open blocking record naming
  this repository. It is fixed or downgraded through the incident process,
  never worked around.
- A review refusal: the attestation is missing, or covers fewer commits
  than the push makes new. Re-read step 3, including the range.
- An unresolvable ref: something was appended to the push. Re-read step 4.

### The six CI categories, which only a RELEASE-GRADE push can meet

A push carrying a version tag is refused unless the commit that tag names has
a concluded, successful CI result on the remote. An ordinary branch push never
enters this arm, so meeting one of these means a tag was in the command.

- `[ci-red]`: CI concluded and FAILED on that commit. Nothing here is
  negotiable; fix the build and tag again.
- `[ci-running]`: CI has not concluded yet. WAIT and re-read, rather than
  re-pushing. The one thing this arm exists to stop is a tag going out
  seconds after the branch with jobs still running.
- `[ci-unknown]`: the remote answered, and the answer does not establish
  success. No run for the sha, an unauthenticated or failing `gh`, or a full
  page of results with no total are all UNKNOWN, and UNKNOWN IS NOT GREEN.
  This is the fail-closed half and it is deliberate: a guard reading its own
  missing information as permission is not a guard.
- `[ci-config]`: the CI state reader is not vendored beside the gate. It is a
  REFUSAL and never a skip, so a repository that re-vendored the gate alone
  meets this on every release push and the cause reads as a gate defect when
  it is a missing file.
- `[ci-budget]`: the gate ran out of the seconds it allows itself before an
  answer arrived. Two causes and they need different fixes: a slow remote, or
  a harness timeout smaller than the budget the gate body grants itself, in
  which case the gate is killed before it can decide and the deployment is
  what needs changing, not the gate.
- `[ci-tag]`: the tag could not be resolved to a commit to ask about.

The last two are reached by NO test today, and the gate's own companion prints
them as unreached on every run rather than counting them as covered. Do not
write evidence claiming coverage the companion reports as absent.

**Never `--no-verify`.** Every mechanism above exists because a step was
routed around once.

## What this skill does not do

Steps 1 to 5 run nothing and enforce nothing. They are the sequence written
down so that it is not reconstructed under pressure, and every refusal they
describe still fires exactly as before if they are ignored.

**Step 6 is different, and the difference is deliberate.** A rule that
unknown is never green cannot be carried by a paragraph, because a
paragraph cannot fail. So step 6 names two mechanisms, `ci_state.py` and
`detached_gate.py`, which answer in four states and exit non-zero on three
of them. This file still does not RUN them for you; what it stops doing is
asking you to hold the rule in your head.

It also does not cover merges, conflicts, branching strategies or multiple
remotes. The repositories it was written for carry linear history and one
remote, and describing a workflow nobody here runs would be a worse lie
than saying so.
