<!--
ITACA / pyflightstream shared process kit
kit-version: 0.2.16
artifact: review-policy.md
body-sha256: e0617a4f6f4a70de5dfe55a66e38efc2faaf1e312a4e543c7f6a21e10f1bbf6f
canonical-source: BUILT for the kit (0.2.7) from the author's product-owner decision REVIEW-TIERS, answered 2026-07-29, which asked to become a kit promotion so that it binds every repository rather than the one that raised it. The three moments were renamed from TIER 1/2/3 to GATE/PUSH/RELEASE the same day, because both libraries already use tier 1/2/3 for TEST tiers and this artifact's first level contains all three of them; the file was renamed with them, for what the artifact IS rather than for the labels it currently uses. It also carries guard 3 of INC-20260729-0854-shared, the probe-closure rule, promoted from one checkpoint's decision into a rule for every checkpoint. 0.2.16 adds the PROPERTY SENTENCE inside design before edit, the round ledger's LOCATOR paragraph inside the recursion cap, and the section CITE AN ID WITH ITS TITLE with check_citations.py beside this file. No existing rule moves in meaning. See coordination/DESIGN_HUB-12_kit_batch.md items 5, 7 and 8.
0.2.15 adds two sections, DESIGN BEFORE EDIT and the round-two distinction inside the recursion cap, and adds check_review_rounds.py beside this file. Neither changes GATE, PUSH, RELEASE, the ordering rule or probe closure in meaning. See coordination/DESIGN_HUB-11_kit_batch.md items 3 and 4.
0.2.16 adds the PROPERTY SENTENCE inside design before edit (the author's adoption of ITA-11's proposal, and the machine-checkable half of that rule), the round ledger's LOCATOR paragraph inside the recursion cap, and a new section CITE AN ID WITH ITS TITLE with check_citations.py beside this file. No existing rule moves in meaning: GATE, PUSH, RELEASE, the ordering rule, the round-two distinction and probe closure are untouched. See coordination/DESIGN_HUB-12_kit_batch.md items 5, 7 and 8.
note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
END KIT PROVENANCE (body verbatim below)
-->
# The review policy: three moments, the ordering rule, design before edit, the recursion cap, citations, and probe closure

Authority: the author's product-owner seat, `REVIEW-TIERS`, answered
2026-07-29, recorded in the coordination logbook. She asked for it to become a
kit promotion so that it binds every repository rather than the one that
raised it. It is a POLICY artifact: it decides who reads what and when, and
one of its four rules carries a checker beside it.

Adopted FROM THE NEXT LANE in each repository, never mid-lane. Changing the
rule inside a running lane buys one more review round about the rule change,
which is the loop this is cutting.

## The three moments are GATE, PUSH and RELEASE, and they were called tiers for a day

Recorded because the rename is the kind of thing a later reader will assume was
always so, and because the reason generalizes past this artifact.

They were TIER 1, TIER 2 and TIER 3 when this was drafted. Both libraries
already use tier 1, 2 and 3 for TEST tiers, and this artifact's first level
CONTAINS all three of those: it is the suite plus the type checker plus the
linter plus every existing guard. So "this is tier 1" had two readings that
were both true and not compatible, and the wider one swallowed the narrower.
An integration review raised it; the author renamed it the same day.

Prefixing them as "review-tier 1" was considered and REFUSED. A prefix works
only while everyone writes it out, and the first commit message saying "tier 2"
brings the ambiguity straight back. That is a convention, and the point of a
rename is to get a mechanism instead: two vocabularies that cannot be confused
because they share no word.

It was asked and answered while NO repository had vendored this file. A day
later it would have been a body change, a new hash and a re-vendor in two
repositories, which is the same reasoning the kit applies to a label already
cited by name.

THE FILENAME MOVED TOO, from `review-tiers.md` to `review-policy.md`, and that
was a separate call with its own reason. A file called `review-tiers.md` whose
body never says "tier" is a small lie of exactly the kind this rename was
fixing. Naming it for its current labels, something like `review-moments.md`,
would put the next relabel back in this position; naming it for what the
artifact IS survives a relabel, because it will be the review policy whatever
the three moments come to be called. The cost is that the manifest key changes
with it, and that cost is only small NOW, for the same reason the rename is.

## The measurement the decision rests on

Recorded because a decision without its evidence becomes a preference the
first time someone disagrees with it.

Over ten days one library was 81 commits and 48700 lines added: 32.3 percent
library tests, 30.3 percent library code, 22.5 percent documentation and
requirements, and 10.9 percent process, CI and guards.

The instinct that the work had become infrastructure was WRONG ON VOLUME and
RIGHT ON ATTENTION. In the last 24 hours of that period one guard saga was 913
lines of 9678, under 10 percent, and it was four of the last six commits. Code
arrives in few large blocks and process arrives in many short rounds, and every
round costs a human read. The policy is aimed at the rounds, not at the lines.

## GATE, every commit

Machine only. No human and no agent reads prose. The suite, the type checker,
the linter, and every guard the repository already carries.

Green or red is the whole output. GATE has no findings, only failures.

## PUSH, once before a push, fixed scope, ONE round

The question is exactly one: does the code do what its commit message says it
does.

Only a finding that CHANGES BEHAVIOUR, or that MISDESCRIBES it, may stop the
push. A text inconsistency is registered as a plan item and stops nothing.

One round. Not one round per finding, and not one round per file.

## RELEASE, only before a tag

The full panel: every lens, the artifact boundary, and a review OF the guards
rather than only through them.

A release is the only moment at which the expensive read is worth its price,
because it is the only moment at which the result becomes permanent for someone
who is not in the room.

## The agent assignment

DERIVED from the decision rather than stated in it, and open to correction on
the first lane that finds it wrong. Both libraries carry the same five role
reviewers.

| Lens | Moment | Why |
|---|---|---|
| `qa-engineer` | PUSH | produced the false closure, and the two tests that passed against pre-fix code |
| `vv-engineer` | PUSH | produced the guard that stayed green on the commit that shipped the defect |
| `architect-reviewer` | PUSH | produced the STABLE requirements amended without an amendment |
| `tech-writer` | RELEASE | produced the spelling sweep and the citation corrections |
| `api-designer` | RELEASE | produced surface findings that are real and are not worth a release-week read |

The three at PUSH are there because those three produced every finding that
changed an outcome in the lane this was decided from. The two at RELEASE are
there because theirs were real and none of them changed an outcome.

## The ordering rule

A TEXT finding never precedes a BEHAVIOUR finding, in any report, at any moment.

This is an ordering rule and not a scheduling one: it applies inside RELEASE as
well, where both kinds are in scope. Pedantry about how a comment is worded
while the code itself is not yet tested is backwards, and a report that opens
with the comment teaches the reader that the report is not about the code.

## Design before edit

Added 0.2.15, HUB-11. It is a rule about the moment BEFORE an edit, which is
why it sits between the ordering rule and the cap: it is what makes the cap
affordable.

THE RULE. Before editing in response to a finding, write down what the change
does and WHAT IT CANNOT BREAK. Per finding, not per session. The second half
is the load-bearing one, and it is written before the edit rather than after,
because after the edit it is a justification and before it is a prediction
that the next round can falsify.

MEASURED, in a controlled comparison inside ONE session, which is why this is
a rule and not a preference. In lane ITA-2E one half of the work was designed
in writing first, with a per-finding statement of what the fix could not
break, and it generated NO review round. The other half was a one-line
allowlist edit made under review pressure, and it produced two rounds and
1h40. Same session, same reviewers, same day.

The corroboration is stronger than the measurement. The next lane, ITA-4,
adopted the practice UNASKED, with nobody having proposed it to that lane.
A practice a session reaches for on its own, having felt the cost, is better
evidence than a practice a policy asks for.

WHAT IT IS NOT. It is not a design document per lane, not an approval step,
and not a gate. Nothing waits on it and nobody signs it. For a one-line fix
it is one or two sentences beside the finding.

THE COST, and it is real. It moves work earlier, into the moment when the
finding is fresh and the temptation is to just fix it. Lanes that skipped it
did not go faster; they paid the same time in a later round, at the higher
price of a round.

A repository states where the statement lives. It is expected to POINT at
this section rather than restate it, because a rule restated in three places
is a rule that will disagree with itself.

### The property sentence, which is the machine-checkable half

Added 0.2.16, HUB-12, the author's adoption of lane ITA-11's proposal.

THE RULE. A fix recorded in a round ledger carries a `property=` field: ONE
SENTENCE STATING THE INVARIANT THE FIX ESTABLISHES, written BEFORE the edit.
`check_review_rounds.py` refuses a `fixed` row that lacks one.

Design before edit asks for two statements, what the change does and what it
cannot break, and nothing can check either. This is the half a machine can
hold, and it is the half that carries the most: an invariant is what the fix
must be true of, so writing it is the moment at which a fix that proves the
wrong thing becomes visible.

THE EVIDENCE, and it is the strongest any proposal here has had, because the
lane that proposed it is the lane that demonstrated the failure four times,
and in each of the four THE SENTENCE CONTAINS THE DEFECT INSIDE IT.

- A guard repaired from substring to parsed proved the right PROGRAM runs and
  not that it measures THIS tree, so a run pointed at another directory
  entirely was accepted. The sentence, "the wrapper is the vendored receipt
  gating THIS repository's tree under a label unique to the hook", contains
  the defect.
- A commit-tier marker whose whole purpose is to admit a test to a gate
  admitted it to a gate that did not MEASURE it, found independently by all
  three lenses. The sentence, "a test admitted by the fast marker is measured
  by the budget of the tier it joined", is again the defect stated.
- The repair of that repair matched a word instead of the condition one line
  later, so an unmarked test whose parametrize id read `slow` was exempt.
- A cost figure was asserted twice from methods that could not resolve it.

WHAT IT CANNOT DO, in the same words the attestation uses about itself: it is
a PRESENCE check. It proves a sentence exists, not that it is a good
sentence. THE GAIN IS AT THE MOMENT OF WRITING, which is the only moment at
which stating an invariant can change what gets built. A checker claiming
more than that would be the defect the rule exists to catch, one level up.

ONLY A `fixed` ROW NEEDS ONE. A registered finding has no fix and therefore
no invariant; a withdrawn one already carries a required reason. Requiring
one of all three would produce a field written to satisfy a checker.

## Cite an id with its title

Added 0.2.16, HUB-12, from `ITC-20260802-0340`, cite an id with its title so
a wrong citation is visible. It sits here rather than in a repository because
a review is where a wrong citation is currently caught, expensively.

THE RULE. When prose cites an allocated id, it names the id AND a fragment of
that id's own title:

    OQ-53, whether the vendored kit is checked for CURRENCY

THE DEFECT IT IS FOR, and the guard a reader reaches for first does not catch
it. A lane cited an open question for a question that question does not ask.
Three reviewer lenses caught it independently. "Every cited id must exist"
would have PASSED, because the id exists: the error was a wrong-but-EXISTING
citation, which is semantic. Carrying the title makes the mismatch visible
while the sentence is being written, which is where it is cheapest.

THIS LEVEL HAS ITS OWN, and it moved code rather than prose: a finding was
classified here as a defect while a requirement chartered the behaviour, and
two lanes implemented and reverted a fix before the authority chain stopped
it.

THE MECHANISM. `check_citations.py`, beside this file. It refuses a citation
whose quoted title contradicts the id's own title, and an id allocated
nowhere. WHETHER A TITLE IS MANDATORY IS EACH REPOSITORY'S CALL, made in its
own charter and passed to the checker as `--mode`: the default is advisory,
where a citation carrying no title is a note. A MISMATCH is refused in both
modes, so a repository that stays advisory still gets the check this rule is
about.

WHAT IT CANNOT CATCH: prose that cites correctly and then concludes something
the cited authority does not support. That is review's.

## The recursion cap, and what a round-two finding actually is

A review of a GUARD FIX does not spawn another review of the guard. Two rounds
maximum.

The saga this came from took four. Rounds two and three found real defects, and
that is not evidence that unbounded rounds are good: it is evidence that the
FIRST round was scoped wrong, reviewing the fix instead of the artifact the fix
was about. The cap forces the scoping error to surface as a cap breach rather
than as three more rounds.

### The distinction the cap cannot be built without

Added 0.2.15, HUB-11, from a finding that arrived ONE DAY before the cap was
mechanised, which is luck rather than design.

The obvious mechanism for a two-round cap is "two rounds, then register
whatever is left". That mechanism would have shipped lane ITA-4's defects.
Measured, in that lane's own words: its round-one FIXES were themselves
defective. Six guards it wrote did not guard, one false-fired on correct
code, and it introduced a fresh defect in the same commit that added the
guard against the old one, with the lane's central fix passing green on a
tree that was never built. Only round two saw any of it. Had round two been
register-only, all of it would have shipped, documented as known.

So a flat count is not merely weaker than the rule; it is wrong in exactly
the case the cap most often meets, because a round-two report is dominated by
findings about round one's fixes.

THE RULE, therefore:

- A round-two finding ABOUT ROUND ONE'S FIX is **the fix not being done**. It
  belongs to round two and is FIXED, not registered. It does not buy a third
  round and it does not get deferred.
- A round-two finding on **NEW GROUND** is what gets REGISTERED, as a plan
  item, and the lane closes.

A round-two fix is verified by its own evidence, not by a third review round:
the failing measurement before it and the passing one after, per the
INERTNESS rule above. That is what replaces the round the cap forbids.

THE ESCALATION, which is precedent rather than invention. Lane ITA-2E reached
the cap and did not open a third round: it stopped and asked the author, she
authorised the fix, and it was recorded as AUTHORISED rather than counted as
a round. A third round exists only with a named authority, and the record
says who.

THE MECHANISM. `check_review_rounds.py`, beside this file, reads a lane's
round ledger and refuses a closure that registers a finding about a previous
round's fix, an unauthorised third round, a ledger that certifies nothing,
and a `fixed` row with no property sentence. Its format is documented in its
own docstring and is PROPOSED rather than settled, on the same terms as the
probe ledger below: it was written from three lanes' data and the next lane
is entitled to correct it, by promotion.

WHERE THE LEDGER LIVES, added 0.2.16 from `ITC-20260802-0120`, the round
ledger has no locator so nothing can check it. The cap was stated from 0.2.7
and mechanised at 0.2.15, and NOTHING applied the checker to a ledger: a
skill instructed an operator to run it, which is an instruction rather than a
mechanism, and both libraries hold that documentation is not a guard. The
convention is now written down, and it is the one the first lane to write a
ledger used unprompted:

    <root>/<lane>_rounds.ledger

The checker resolves it with `--root <dir> --lane <id>`, or checks every
ledger under a root with `--root <dir> --all`, and a root holding none is a
configuration error rather than a clean run. It reads NO environment
variable: what an absent root means at a gate is each repository's charter
call, not the kit's.

## Probe closure, and the checker beside this file

This is guard 3 of `INC-20260729-0854-shared`, promoted here from a decision
made for one checkpoint into a rule for every checkpoint. It is the cheapest of
that incident's three guards and the one this level most needed.

THE RULE. A probe counts as CLOSED only if it REPRODUCED against the tree where
the defect existed. Two executions, in sequence, and they are not alternatives:

1. every probe runs against the reviewed base and MUST reproduce. One that does
   not is a BROKEN PROBE, and its finding stays open regardless of what the
   current tree says;
2. every probe runs against the current tree and none may reproduce.

WHY THIS FRAMING. The question is not which tree to test. It is what
distinguishes "the fix works" from "the probe never worked", and exactly one
measurement separates those. A probe reporting a finding closed looks identical
whether the code changed or the probe was always inert.

MEASURED, not supposed. One review round found TWO tests that passed against
pre-fix code: one whose fixture contained no delimiter at all, and one that
turned on an identifier neither tree imports. Both were green and both proved
nothing. In the same checkpoint, execution A ran 33 probes against the reviewed
base and all 33 reproduced, which is the mechanism demonstrated on a real
population rather than on an argument.

COST. Two executions instead of one, on what is already the most expensive
check in a release plan. Accepted deliberately: a checkpoint that cannot tell a
working fix from a broken probe is the same defect it exists to catch, one
level up.

INERTNESS (added 0.2.11, BRF-061 item 16). A reproduction that cannot show it
exercised the claimed path is not evidence. Every probe, reproduction or guard
demonstration must carry, beside its verdict, what proves the probe touched
the code it claims to test: the failure string from the pre-fix run, the pass
summary with counts, or the observable side effect it caused and reverted.
Measured on 98 verdicts in one verification pass, and the rule earned its
place before it was written: an itaca checkpoint caught evidence labeled
fitvalue that actually exercised fitmodel, green and irrelevant.

THE MECHANISM. `check_probe_closure.py`, beside this file, reads a checkpoint's
probe ledger and refuses a closure that skipped step 1, a ledger whose two bases
are the same commit, and a ledger that certifies nothing. Its format is
documented in its own docstring and is PROPOSED rather than settled: it was
written from one checkpoint's data and the next checkpoint is entitled to
correct it.

UNRESOLVED, and deliberately left so: whether a call of this class belongs to
the author's seat or to the coordination level. It was answered once by her,
and one instance answered does not settle the ownership.

## What this artifact does NOT do

It does not make any lens fire. It says which lens is expected when, and a
repository still has to wire its own reviewers, exactly as the attestation
vocabulary made an honest answer expressible without making any pass required.

It is also NOT YET SAID WHERE AN OPERATOR READS IT. The push gate's review-deny
message is what a person actually sees at the moment of pushing, and it still
names five lenses with no moment attached. The kit's own 0.2.6 changelog argues
that a vocabulary the gate never mentions is a lens nobody knows to run, and
that argument applies here unchanged. This artifact shipped at 0.2.7 without
that half, DELIBERATELY and for one version: the gate is the most load-bearing
body in the kit and its deny prose is pinned by hand in a test, so changing it
is its own promotion with its own review. It is a NAMED item of 0.2.8, with an
owner, and it rides beside the gate's stale canonical-source line, which has
been waiting since 0.2.6 for a promotion with another reason to touch that
file. Deferring with a number is not the same as forgetting, and this paragraph
is what makes the difference checkable.

It does not apply to a workspace with no continuous integration. GATE is
defined as machine-only, and a repository with no CI has no GATE to speak of;
saying so here is better than a policy that silently describes a level that does
not exist.

## The costs, written because a decision recorded without its cost is a
conclusion

FIRST, and measured. A RELEASE lens co-raised a genuine product question about
what a source distribution ships, which is not pedantry. Moving that lens to
RELEASE means questions of that shape surface later in every lane. It is
mitigated only partly by RELEASE running before the tag, which is while
release-scope questions are still answerable.

SECOND. An interface lens at RELEASE means a public signature can be built wrong
and be caught when changing it is most expensive.

THIRD. Adopting from the next lane means the lane in flight finishes under the
old process, which is deliberate and is the cost of not spending a round on the
rule itself.
