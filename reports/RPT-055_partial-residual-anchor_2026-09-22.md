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
