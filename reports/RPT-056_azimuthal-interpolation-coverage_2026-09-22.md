# RPT-056: the interpolation guard is not covered on the azimuthal product

**Date:** 2026-09-22
**Found by:** the QA lens, reading `0402a02..3637542` at the push moment of v0.25.1
**Status:** REGISTERED for 0.26.0. The code is correct; the coverage is not.
**Related:** GH-1 of `REL-0251_independent-review.json`, the defect this guard exists for.

## What is guarded, and what is tested

v0.25.1 judges a phase-locked average over the steps its arithmetic READS, one revolution
earlier than its declared window, because its samples are interpolated at fractional moments.

The committed regressions exercise that guard twice: at the helper
(`_window_the_reduction_reads`) and through `write_campaign_products` on a plan whose
`phase_locked` entry carries no `shape`. That plan builds the LEGACY PASSAGE-SERIES product,
not the azimuthal one, and the azimuthal one is what interpolates.

## What was measured

The lens disabled the widening FOR AZIMUTHAL ENTRIES ONLY, in memory, and both changed test
files stayed green:

```
31 passed, 80 warnings in 3.80s
Phase-locked shapes measured: {'None': 24}
```

It then built a separate temporary campaign with 2.5 steps per revolution, an azimuthal window
of `[59, 61]` and step 58 unread: the current code refuses the product, the mutant publishes it,
and a healthy control publishes normally. So the guard works on the azimuthal product and
nothing committed would notice if it stopped.

## Why it is registered rather than fixed here

An azimuthal product needs rotor facts the freeze fixture does not carry -- the blade-one
azimuth and the rotor speed -- and the rotor variant of that fixture writes under another matrix
stem. Building the case is a fixture change with its own correctness question, made at the end
of a patch whose every round found a defect in the previous round's work. The honest move under
the owner's rule -- a finding is fixed or registered, never debated -- is to register it with the
lens's own recipe, which is complete enough to write the test from:

> a declared `[phase_locked]` table, 2.5 steps per revolution, azimuthal window `[59, 61]`,
> unread step 58; assert the healthy product is azimuthal, the affected one refused by name, and
> the time average over the same window kept.

## What is true meanwhile

The guard is proved by the mutant at the helper and by the product-level case on the passage
path, and the lens proved it independently on the azimuthal path with its own probe. What is
missing is a COMMITTED test on that path, so a future change could remove it unnoticed.


## A second gap of the same shape, registered with it

**The clock columns are not asserted at the product level either.** `J_CLOCK` and `RPM_CLOCK`
are proved by unit cases over `clock_rotor_facts` and `point_condition`: the clock chosen by
`CLOCK_MOTION`, case-folded as the planner folds it, the unresolved multi-rotor record stating
neither, a named clock absent from the reference taking no other rotor's diameter, and the ratio
against a measured row. What no committed test does is read the two columns OUT OF the polar,
the rotor table and the per-step series of one campaign and compare them.

The QA lens measured the consequence on 2026-09-22: omitting `clock=` from both repaired callers
left 35 targeted tests green while three rotor-table calls and 33 series calls discarded the
facts. The defect that fix repaired -- those families reading `NA` while the polar beside them
carries values -- can therefore return unnoticed.

WHY IT IS REGISTERED. The freeze fixture this suite reuses carries no rotor diameter in its
reference, so `J_CLOCK` cannot be computed there at all, and the rotor variant writes under
another matrix stem. A campaign-level case needs a reference with `rotor_diameter_m` and a
matrix row naming it, which is a fixture of its own. Measured, not assumed: with that fixture the
facts resolve to `rpm 2200.0` and `diameter_m None`.

WHAT TO WRITE, when it is written: one campaign with a rotor of known diameter and speed, posted
once, asserting that the polar, the rotor table and the per-step series all state the same
`J_CLOCK` and `RPM_CLOCK`, and one campaign whose `CLOCK_MOTION` is written in another case,
asserting the same.
