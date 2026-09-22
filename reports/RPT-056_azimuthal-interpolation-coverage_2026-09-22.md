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
