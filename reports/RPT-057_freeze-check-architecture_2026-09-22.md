# RPT-057: the freeze check reads the log twice, and guesses the second time

**Date:** 2026-09-22
**Decision:** the owner's, 2026-09-22 -- the native-log freeze check is OPT-IN in 0.25.1
(`--check-frozen`), and the architecture is re-discussed in 0.26.0.
**Status:** REGISTERED for 0.26.0, under `GOAL-030`.
**Superseding decision, the owner's, 2026-09-22:** nothing in the post blocks by default, and
the post always writes a log of its own carrying a warning wherever one applies. That changes
what this report is about: the question below stops being whether the guard refuses the right
products and becomes what the log says. `GeoversePlan/goals/GOAL-030` carries her wording and
the reason.

## What the check is for

A frozen solve keeps printing time steps whose residuals are exactly zero: it has stopped
solving and is still turning. The numbers it exports stay plausible, so an average taken from
them looks like any other and is wrong. 0.25.0 began reading each point's native log while
posting and refusing the averages a freeze touches; a block the solver stopped under cannot be
judged either way, so averages over it are refused too.

## Why it became a question

For a plain average, the steps it reads are the steps its window names. For the AZIMUTHAL
phase-locked average they are not: the reducer samples at moments between plotted steps, one per
blade and one per azimuth of the final revolution, and `numpy` reads the plotted steps bracketing
each moment. Deciding which steps such an average reads therefore means knowing exactly what the
reducer samples.

The guard in `post/products.py` computes that itself, and on 2026-09-22 eight rounds of review
found it wrong in one direction or the other, every time:

| what it did | what it cost |
|---|---|
| judged the declared window | published an average that read an unread step |
| bracketed one revolution earlier | refused clean averages on a dense history, missed a sparse one |
| bracketed the window's opening | refused clean averages wherever the samples are whole steps |
| enumerated every azimuth of the interval | refused clean averages on a fractional clock |
| applied every declared blade offset | refused clean averages on a totals-only history |

Each fix was correct about the case that prompted it and wrong about a case nobody had thought
of yet. That is the signature of a SECOND IMPLEMENTATION of an arithmetic that already exists.

## What 0.26.0 should decide

**The reducer knows its own samples.** `post/unsteady` computes the moments it averages; the
guard should ASK for them rather than recompute them from the plan. The shape worth discussing:

- the reducer exposes the moments, or the steps they bracket, for a given plan and history;
- the guard judges that set against the unread steps, with no arithmetic of its own;
- a totals-only history therefore contributes no blade offsets, because the reducer takes none,
  and a fractional clock contributes exactly the moments the reducer takes.

**And whether it belongs in `post` at all.** The check re-reads, at post time, a log that the
COLLECT stage already read to assess the run. A freeze is a property of the run, recorded once,
rather than a question re-asked of every rebuild. If the record carried the verdict, the post
stage would judge windows against a recorded fact and open no log.

## What is true in 0.25.1 meanwhile

The reading is off unless asked. With it off, a frozen solve's averages are published; with it
on, the refusals are those measured above, conservative where they are imprecise -- they refuse
more than the arithmetic reads, never less, and every refusal is named in `products.json` with
the step and the remedy. The crash that prompted the release is fixed in both modes: a log that
cannot be read never ends the post.

## Addendum, 2026-09-22, from the closing round of v0.25.1

The sentence above, "they refuse more than the arithmetic reads, never less", is corrected: the
V&V lens found one case where the guard reads LESS. The guard takes its blade offsets from the
RECORDED plan, and the reducer takes its families from the reference through alias expansion
(`_section_rotors`). A recorded family alias that expands to two blades gives the reducer a
second blade offset the guard never sees: three steps per revolution, window `[59, 61]`, the
reducer samples 58.5 and reads the plotted step 58; the guard judges `[59, 61]` and an unread
58 passes. This is the same defect shape as the rest of the table, in the other direction, and
it is the strongest reason yet for the shape proposed above: the guard must ASK the reducer
for its samples rather than rebuild them from a different source. It is registered here, under
the opt-in flag, and closes with this report in 0.26.0.

Also from that round, a question this report does not answer and 0.26.0 must: at
`steps_per_revolution = 2.0000000001` the reducer interpolates at 59.99999999995 and the
plotted step 59 carries a weight of about 5e-11. Whether every nonzero weight is judged, or a
stated cutoff applies, is a decision for the numerical seat, and it is taken where the samples
are stated, in the reducer, not in a guard that rebuilds them.
