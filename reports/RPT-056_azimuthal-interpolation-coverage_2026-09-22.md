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


---

## ERRATUM, 2026-09-22 (the paragraphs above are the original record, restored)

Commit 4826b12 rewrote the two paragraphs above in place; the V&V lens of the closing round
named that as a breach of report immutability, so they stand again as first written and the
corrections live here. TWO CORRECTIONS. First, the rule the report describes ("one revolution
earlier") was the first of three: the guard then bracketed the window's opening, and now
brackets the SAMPLES, the moments `post.unsteady` takes, each read through the plotted steps on
either side of it. Second, the passage path named as evidence DELIBERATELY BYPASSES the widening
since then, so it is no evidence for the azimuthal guard at all.

## CLOSED on 2026-09-22, by the reading that said it should hold the tag

The third independent reading of GitHub `main` judged this registration directly: RPT-055 is an
honest bounded disclosure and would not hold the tag, but **this one should**, because the
azimuthal path needed committed product-level coverage. It also found what that coverage would
have caught: bracketing the window's OPENING still refused a clean average wherever every
sample lands on a plotted step.

BOTH ARE NOW DONE, so this report is a record rather than a debt:

- the support brackets THE SAMPLES, computed as `post.unsteady` computes them -- each azimuth of
  the final revolution, each blade offset, each moment inside the revolutions asked for -- and a
  moment that is a plotted step brackets to itself;
- `tests/tier1_offline/test_azimuthal_interpolation_support.py` builds an azimuthal rotor
  campaign through `write_campaign_products` and asserts both sides at the product: two steps per
  revolution put every sample on a plotted step and an unread step outside the window costs
  nothing; three put the second blade one and a half steps behind, so a sample at 59.5 is read
  from steps 59 and 60 and an unread 59 refuses the product by name. It is scored against a
  mutant that restores the opening bracket.

WHAT REMAINS REGISTERED from the second half of this report: the cross-family assertion for
`J_CLOCK` and `RPM_CLOCK`, which is coverage of a different promise and is not what the reading
held the tag for.

---

## CLOSED in 0.27.0, 2026-09-23: the clock columns at the product

**Status:** CLOSED in 0.27.0

The half this report still registered after its closure of 2026-09-22, the cross-family
assertion for `J_CLOCK` and `RPM_CLOCK`, was not closed by 0.26.0: `git log v0.25.1..v0.26.0
--grep RPT-056` names none of the 61 commits in that range, and the clock tests that release
carries, in `tests/tier1_offline/test_clock_rotor_columns.py`, are unit cases that post no
campaign. It is closed by `tests/tier1_offline/test_clock_columns_at_the_product.py`. The test
posts ONE rotor campaign once through `write_campaign_products`: the rotor variant of the freeze
fixture, whose reference declares rotor `PUSHER` with `diameter_m = 2.0`, whose record turned it
at 2200 rev/min and whose matrix row names it as `CLOCK_MOTION`, with three stamped loads exports
of steps 3 to 5 and an export window naming them, so the per-step series exists. It reads the two
columns out of every data row of every CSV product that carries them -- the polar
`P7001_AL-020_uns_avg.csv`, the rotor table `P7001-PUSHER_rotor.csv` (its header on the second
row, under the rotor's title), the loads series `AL-020_loads_series.csv`, and beside them the
time average, the phase-locked average and the sections table -- requires the first three to be
present, and asserts that every product states the polar's values and that none is `NA`:
`J_CLOCK` 0.92806 and `RPM_CLOCK` 2200.00000, which is `68.058 / (2200 / 60 * 2.0)` from the
export's free stream. A second case writes the row's clock as `pusher` against the reference's
`PUSHER` and asserts the same. Both cases pass. Each mutant was made on a scratch copy of the
source, and the pytest process reported importing `pyflightstream` from that copy with the
mutated text in the module it loaded: deleting `clock=` from the rotor-table caller failed both
cases with exit 1, the rotor table alone reading `NA` in both columns; deleting it from the
loads-series caller failed both cases with exit 1, the series alone reading `NA` in both columns;
matching the clock name exactly instead of case-folded failed the second case alone with exit 1,
the polar reading `J_CLOCK` `NA` beside `RPM_CLOCK` 2200.00000; an unmutated copy under the same
harness passed both. No solver was run.
