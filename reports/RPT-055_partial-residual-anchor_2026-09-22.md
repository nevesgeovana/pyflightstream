# RPT-055: a residual block whose `Iteration` anchor is cut carries nothing to refuse

**Date:** 2026-09-22
**Found by:** the independent review of GitHub `main` at `0402a02`, before the v0.25.1 tag
**Status:** REGISTERED for 0.26.0, deliberately not fixed under a patch tag
**Affects:** 0.25.0 and 0.25.1 alike. The reviewer confirmed the gap in the 0.25.0 detector, so
it is older than the patch whose review found it.

## What was measured

`results.frozen_time_steps` splits each time-step block into residual pages on the `Iteration`
anchor and reads each page as a delimited table. A page that begins and is then cut mid-write
has no closing rule, so the reader refuses it, and since 0.25.1 the post stage records that step
as UNREAD and refuses the averages whose window covers it.

A block cut THREE CHARACTERS EARLIER behaves differently. With the committed row-2413 fixture:

| where the log is cut | what the detector returns | window `[60, 60]` |
|---|---|---|
| immediately after `Iteration` | the step is unread | refused |
| after `Iterat` | `None` | **accepted** |

With no complete anchor there is no page, so there is no table to refuse: the block yields an
empty row list, cannot be frozen, and says nothing. The step is then treated as a step with no
evidence rather than as one nobody could read, and the freeze of its neighbour -- which needs
two consecutive frozen steps -- is not reported.

## Why it is not fixed here

The obvious repair is to treat every block with no residual page as unread. That is not safe to
make under a patch tag: a real campaign log measured on 2026-09-22 carries 144 step-marker
blocks for 72 steps, because the run's per-step export actions print between them, and a block
that holds only those actions has no residual page either. Treating those as unread would refuse
averages on runs where nothing is wrong, which is the mistake the first version of the 0.25.1
patch already made once across a whole point.

Separating "a block that never had a table" from "a block whose table was cut before its header
finished" needs a rule about what a complete block looks like, measured against real logs of
both shapes. That is 0.26.0 work with its own evidence, not a line in a patch.

## What the reader can rely on meanwhile

The CHANGELOG entry for 0.25.1 and the freeze section of `docs/post-processing-definitions.md`
both state this limit where they state the rule, so nobody reading either page is told the
protection is complete when it is not.

## CLOSED in 0.26.0, 2026-09-23

**Status:** CLOSED in 0.26.0

The detector now marks a terminal marker block without a residual page UNREAD,
including a cut after `Iterat`. A page-less block immediately followed by a
marker for the same step is a repeat and does not reset the evidence. A block
with an actual malformed page remains unread even if the next marker repeats.

`tests/tier1_offline/test_post_log.py::test_partial_iteration_anchor_is_unread_at_the_product`
measures the row-2413 cut after `Iterat`: step 61 is unread, the default writes
its average with a warning, and `check_frozen=True` refuses it. Before the fix,
both parameter cases failed because the verdict was `None`. Restoring that
terminal-block defect as a mutant returned exit 1 with those same two failures.
`test_repeated_markers_are_not_unread` inserts an export-only marker before
each intact marker of both committed excerpts: the healthy verdict stays
healthy and the frozen verdict retains steps 60 and 61. Removing the repeat
branch as a mutant lost that freeze and failed with exit 1. Existing adjacency, restart and per-blade contiguity tests remain green.

Fixture census: both committed `pfs0240_row2411_steps58-61_log.txt` and
`pfs0240_row2413_steps58-61_log.txt` have four markers for four distinct steps,
zero page-less repeat blocks, and a complete terminal page. Scanning every file
in `tests/tier1_offline/fixtures`, including NUL-stripped text, found no real
repeated-marker log. The canonical repository's fixture directory had the same
result. The previously reported 144-block/72-step log was not available at either
location, so that historical count is not claimed as reproduced. The repeat
regression is explicitly synthetic, derived from the documented shape; the
terminal cut uses the committed solver bytes. No solver was run.

### Clarification, 2026-09-23

The terminal page-less marker rule applies only after at least one residual page
has been seen in an unsteady marker block of the log. A log whose markers never
carry pages is not classified as cut. This condition narrows the closure's
statement above; the original report and closure remain unchanged.
`test_goal024_collect_and_times_a_log_whose_markers_carry_no_page_was_not_cut`
covers the marker-only control, and the partial-anchor regression cited above
covers a terminal cut after earlier residual pages.
