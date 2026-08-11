# ITACA / pyflightstream shared process kit
# kit-version: 0.2.18
# artifact: ci_state.py
# body-sha256: 39977e44aae1cb4116fb2bce3b672ac21b03ec3a5d75f64244eb70eb2f89b3ab
# canonical-source: BUILT for the kit (0.2.17, HUB-13, author decisions 2 and 3 of 2026-08-02). REQ-96 called the local hooks a mirror of CI and ITC-20260802-2300 proved the mirror incomplete in exactly the two ways that bit: it runs on ONE platform and it does not build the SRS, and three lanes ran a green local suite over a test that was red on every CI run. The pre-push tier becomes a fast pre-flight and CI becomes the authority; this file is what reads that authority. Decision 3 is the half that keeps it honest: a close that cannot read CI REFUSES to close, because this project has already paid for a gate that fails OPEN (INC-20260802-1450-shared). See coordination/DESIGN_HUB-13_kit_0217.md items 2 and 3 and coordination/DESIGN_HUB-13_lane.md section 2. 0.2.18 gives poll a TRUNCATION clause: `gh run list` neither paginates nor reports a total, so a full page is UNKNOWN rather than a complete answer, which is the same defect class the promoted push gate was asked to fix in its starting point (an unpaginated check-runs query that discarded total_count). 0.2.18 also gives this body a SECOND caller on the other side of the push: role_review_gate.py binds it at the push boundary and denies on anything but GREEN, so the docstring sentence saying it never blocks a push is corrected rather than left true-of-one-caller.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""What did CI conclude about this exact SHA? Unknown is never green.

Usage:
    ci_state.py poll  --sha <sha> [--repo <path>] [--workflow <name> ...]
    ci_state.py await --sha <sha> [--repo <path>] [--workflow <name> ...]

``poll`` asks once and returns. ``await`` loops until the state is terminal
and is the thing that gets run DETACHED, through ``detached_gate.py``, so a
close can wait for a queued run without inheriting the caller's ceiling.

WHY THIS EXISTS. ``REQ-96`` called the repository's local hooks a mirror of
CI. ``ITC-20260802-2300`` proved that false in the two ways that actually
bit: the local tier runs on ONE platform, and it does not build the SRS.
Three lanes ran a green local suite over a test that was red on every CI run
and pushed anyway, because the green they had looked like the green that
mattered. The answer is not a better mirror. It is to stop pretending, run
what is cheap and catches defects on the machine, and read the AUTHORITY
after the push. This file reads the authority.

THE STATE CONTRACT IS THE SAME FOUR STATES ``detached_gate.py`` HOLDS, in the
same vocabulary and with the same rule, because two mechanisms holding one
rule in two vocabularies is how they drift apart.

    RUNNING   a run exists for this SHA and has not concluded
    GREEN     every run for this SHA concluded successfully
    RED       a run for this SHA concluded unsuccessfully
    UNKNOWN   nothing above could be established

UNKNOWN IS NEVER GREEN, and the enumeration matters more here than anywhere
else in the kit, because every item on it is a thing that WILL happen: no
network, ``gh`` not installed, ``gh`` not authenticated, an expired token, a
rate limit, no run found for the SHA yet, a run whose conclusion this body
does not recognise, output that does not parse, AN ANSWER THAT FILLED THE
WHOLE PAGE AND MAY THEREFORE BE TRUNCATED, and ANY exception raised anywhere
inside this mechanism. All of them are UNKNOWN.

A CONCLUSION THIS BODY DOES NOT RECOGNISE IS UNKNOWN AND NOT GREEN. That is
the clause that survives the provider adding a new one. The recognised sets
are listed below and a value outside both is refused rather than assumed
benign, which is the opposite of what a default-to-pass mapping would do.

NO RUN FOUND IS UNKNOWN AND NOT GREEN, and this is the one most likely to be
argued with. A SHA with no CI run looks clean, and "no news is good news" is
exactly the reasoning that produced ``INC-20260802-1450-shared``, a gate that
failed OPEN. A push whose workflows have not been created yet, a SHA on a
branch CI does not watch, and a run that the API has not indexed yet are all
indistinguishable from here, and none of them is evidence that anything
passed.

TWO CALLERS NOW, AND THEY SIT ON OPPOSITE SIDES OF THE PUSH. Until 0.2.18
this body had one, the handoff, which reads it AFTER the push; the sentence
here said it never blocks a push, and that was a statement about who was
calling rather than about what this answers. Since 0.2.18 ``role_review_gate``
also calls it BEFORE a release-grade push and DENIES on anything but GREEN
(``INC-20260810-2140-shared``: a version tag published fifteen seconds after
its branch, seven of eight jobs still running, five of them red). Nothing in
the four states moved to make that possible, which is the point of binding
this body rather than writing a second decision table.

WHAT THE POST-PUSH CALLER DOES WITH EACH STATE, which is decision 3 and is
the half that has teeth for the handoff.

    GREEN     the lane may say closed
    RED       the lane may NOT say closed; the report names the failing run
    RUNNING   the lane may NOT say closed; it reports work pushed with CI
              state NOT VERIFIED, naming the SHA and the run to read
    UNKNOWN   the lane may NOT say closed; it reports work pushed with CI
              state NOT VERIFIED, naming the SHA and THE REASON

The word "closed" is forbidden in three of the four states. The obvious
objection is that the common case, a run still queued right after a push,
would then turn every ordinary close into a human action. It does not, and
the reason is the whole point of the pairing: ``await`` run detached has no
CALLER-side ceiling, so the close starts one and reads its record. It does
carry a 6 hour bound on an orphaned waiter, whose expiry is UNKNOWN and so
cannot become a false pass; the caller's 10 minute cut is what is gone. The
author chose this strict form over "wait with a limit, then refuse", and
``detached_gate.py`` is what makes the strict form affordable.

WHAT THIS IS NOT. It is not a CI trigger, it does not re-run anything, and it
takes no action on a red. It answers one question about one SHA.

Standalone, stdlib only, and it shells out to ``gh``, which is the one
external dependency and whose absence is UNKNOWN rather than an error.

Exit status: 0 GREEN, 1 RED, 3 RUNNING, 4 UNKNOWN, 2 a CONFIG error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

GREEN = "GREEN"
RED = "RED"
RUNNING = "RUNNING"
UNKNOWN = "UNKNOWN"
EXIT = {GREEN: 0, RED: 1, RUNNING: 3, UNKNOWN: 4}
CONFIG = 2

# A run that concluded and is FINE. `skipped` and `neutral` are here because
# a skipped job is a job the workflow itself decided not to run, which is not
# a failure and not evidence of one either; a workflow that is ENTIRELY
# skipped still needs at least one success to read green, which is what the
# "any success" clause below requires.
GOOD = {"success", "skipped", "neutral"}
# A run that concluded and is NOT fine.
BAD = {"failure", "cancelled", "timed_out", "action_required",
       "startup_failure", "stale"}

#: How many runs one question asks for. It is a CEILING, not a page size:
#: `gh run list` neither paginates nor reports a total, so a SHA with more
#: runs than this returns a full page and says nothing about what was left
#: behind. See the truncation clause in `poll`; the constant is named once so
#: the request and the check cannot disagree about the number.
LIST_LIMIT = 100
POLL_SECONDS = 20.0
AWAIT_CEILING_SECONDS = 6 * 60 * 60


def _gh(repo: str, args: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True,
                           cwd=repo, env=os.environ.copy(), timeout=120)
    except FileNotFoundError:
        return False, "gh is not installed or not on PATH"
    except subprocess.TimeoutExpired:
        return False, "gh did not answer within 120s"
    except Exception as exc:                       # noqa: BLE001
        return False, f"gh could not be run: {exc!r}"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "gh failed with no "
                       "message").strip().splitlines()[0][:300]
    return True, r.stdout


def poll(repo: str, sha: str, workflows: list[str]) -> tuple[str, str]:
    """One question, one answer. Any failure inside means UNKNOWN."""
    try:
        ok, out = _gh(repo, ["run", "list", "--commit", sha,
                             "--limit", str(LIST_LIMIT),
                             "--json", "status,conclusion,workflowName,"
                                       "databaseId,url"])
        if not ok:
            return UNKNOWN, f"CI could not be read: {out}"
        try:
            runs = json.loads(out)
        except ValueError as exc:
            return UNKNOWN, f"gh output did not parse: {exc}"
        if not isinstance(runs, list):
            return UNKNOWN, "gh output was not a list of runs"

        # A FULL PAGE IS AN UNANSWERED QUESTION, added at 0.2.18 with the
        # push-boundary binding. This is the same defect class the promoted
        # gate was asked to fix in its starting point, where an unpaginated
        # `check-runs?per_page=100` discarded `total_count` and a job past the
        # cut could not be seen: a red run beyond the ceiling would be missing
        # from the set, every run inside it could be successful, and this body
        # would answer GREEN over an answer it knows may be partial. `gh run
        # list` reports no total, so a full page is the ONLY signal available
        # and it is read as UNKNOWN rather than resolved.
        if len(runs) >= LIST_LIMIT:
            return UNKNOWN, (
                f"the remote returned {len(runs)} run(s) for {sha}, which is "
                f"the whole of the {LIST_LIMIT} asked for, so this answer may "
                "be truncated and a run past the cut cannot be ruled out. A "
                "partial answer is not a green one")

        if workflows:
            # A NAMED WORKFLOW THAT IS NOT VISIBLE IS UNKNOWN, NOT ABSENT.
            # Through the first draft this filter only SUBTRACTED, so a SHA
            # whose runs were partly indexed kept the one green run that had
            # appeared and answered GREEN. That is the same "no news is good
            # news" reasoning the no-run-at-all clause below refuses, applied
            # per workflow instead of per SHA. An architecture lens found it
            # in round one.
            seen = {r.get("workflowName") for r in runs}
            missing = sorted(set(workflows) - seen)
            if missing:
                return UNKNOWN, (
                    f"no run is visible for {sha} for required workflow(s) "
                    f"{missing}. A named workflow that has not appeared is "
                    "not a workflow that passed")
            runs = [r for r in runs
                    if r.get("workflowName") in set(workflows)]

        if not runs:
            return UNKNOWN, (
                f"no CI run is visible for {sha}. That is NOT evidence that "
                "anything passed: a workflow not yet created, a branch CI "
                "does not watch, and a run the API has not indexed yet all "
                "look exactly like this")

        # PRECEDENCE, and it is stated because the docstring's mapping table
        # reads as if the states were disjoint. A SHA with one FAILED run and
        # one still queued answers RUNNING, not RED: the set has not settled,
        # and re-reading it later is what resolves it. The direction is safe,
        # since RUNNING is not GREEN and the caller's obligation is identical,
        # and a V and V lens asked for it to be written rather than inferred.
        pending = [r for r in runs if r.get("status") != "completed"]
        if pending:
            names = ", ".join(sorted({str(r.get("workflowName"))
                                      for r in pending}))
            return RUNNING, (f"{len(pending)} of {len(runs)} run(s) for {sha} "
                             f"have not concluded: {names}")

        bad = [r for r in runs if r.get("conclusion") in BAD]
        if bad:
            first = bad[0]
            return RED, (f"{len(bad)} of {len(runs)} run(s) for {sha} "
                         f"concluded badly; {first.get('workflowName')} "
                         f"is {first.get('conclusion')} at {first.get('url')}")

        unrecognised = [r for r in runs if r.get("conclusion") not in GOOD]
        if unrecognised:
            values = sorted({str(r.get("conclusion")) for r in unrecognised})
            return UNKNOWN, (f"a run for {sha} concluded {values}, which this "
                             "body does not recognise. An unrecognised "
                             "conclusion is refused rather than assumed "
                             "benign")

        if not any(r.get("conclusion") == "success" for r in runs):
            return UNKNOWN, (f"every run for {sha} was skipped or neutral, so "
                             "nothing actually ran and nothing passed")

        return GREEN, (f"all {len(runs)} run(s) for {sha} concluded "
                       "successfully")
    except Exception as exc:                       # noqa: BLE001
        return UNKNOWN, f"this mechanism raised: {exc!r}"


def await_terminal(repo: str, sha: str, workflows: list[str]) -> tuple[str, str]:
    """Poll until the state is terminal.

    THE CEILING HERE IS NOT THE ONE THIS PROJECT IS FIXING. It bounds a
    process that is already detached, so it never truncates a caller's
    command; it exists so an orphaned waiter does not poll a repository
    forever. Reaching it is UNKNOWN, which is not green, so the bound cannot
    turn into a false pass.
    """
    deadline = time.time() + AWAIT_CEILING_SECONDS
    state, reason = UNKNOWN, "the wait never ran"
    while time.time() < deadline:
        state, reason = poll(repo, sha, workflows)
        if state in (GREEN, RED):
            return state, reason
        # UNKNOWN is not terminal HERE, deliberately: right after a push the
        # ordinary answer is "no run is visible yet", and that resolves on
        # its own within seconds. It stays UNKNOWN for the CALLER if the
        # wait ends on it.
        time.sleep(POLL_SECONDS)
    return UNKNOWN, (f"waited {AWAIT_CEILING_SECONDS}s without CI reaching a "
                     f"conclusion for {sha}; last answer: {reason}")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("poll", "await"):
        print(__doc__, file=sys.stderr)
        return CONFIG
    verb = argv[1]
    opts: dict = {}
    workflows: list[str] = []
    it = iter(argv[2:])
    for a in it:
        if a == "--workflow":
            workflows.append(next(it, ""))
        elif a.startswith("--"):
            opts[a[2:]] = next(it, "")
    sha = opts.get("sha", "").strip()
    if not sha:
        print("ci-state: --sha is required", file=sys.stderr)
        return CONFIG
    repo = opts.get("repo", ".")

    if verb == "poll":
        state, reason = poll(repo, sha, workflows)
    else:
        state, reason = await_terminal(repo, sha, workflows)
    print(f"ci-state: {state}, {reason}")
    if state != GREEN:
        print("ci-state: this lane may NOT report itself closed. Report the "
              f"work as pushed with CI state NOT VERIFIED, naming {sha} and "
              "the reason above.")
    return EXIT[state]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
