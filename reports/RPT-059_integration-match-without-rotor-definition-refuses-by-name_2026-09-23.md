# RPT-059: the integration match without a rotor definition refuses by name

**Date:** 2026-09-23
**Found by:** the QA reads of the fixes of the second and third independent readings of 0.26.0
**Status:** REGISTERED for 0.27.0
**Affects:** `integrate = true` on a `[[sections.distributions]]` entry matched against a recorded layout with no live rotor definition (a legacy layout, a reference without rotors, a rotor named by an entry that no reference in hand defines)

## What was measured

The integrated sectional loads of 0.26.0 bind a current entry's integration
request to a recorded block through `post/section_distributions.py`,
`_matching_distributions`. With live rotor definitions the match calls the
export builder's own expansion and is exact. Without them the match falls
back to the recorded frame names and the recorded cuts, and nine measured
rounds of that fallback established one rule: a block is owned only when the
recorded evidence says the builder would have emitted it for that entry, and
wherever membership is uncertain the raw columns are kept with a named
skip.

The rule is conservative on purpose, and the reads measured its false
misses, each a refusal that keeps the raw columns and names the block:

- a family STEM (`families = "Blade"`) or a numbered name over a wider
  family (`Blade1` over `Blade11` and `Blade12`) asked by any entry: the
  cuts cannot say whether the geometry carries a boundary the stem names
  or a third blade, so no integration is added (ownership of a legacy
  layout still resolves the stem over the cuts and keeps the raw split);
- a ROTOR name (`families = "ACTIVE"`) on a layout without distribution
  identity and with no rotor definition in hand: nothing resolves the name,
  and the split is refused as unidentified, on this matcher and on every
  earlier one;
- a selected family recorded only in a common frame beside an expanding
  entry, a literally cited rotor frame supplying another rotor's family, a
  whole-geometry selector (`all`, `blades`, `airframe`) whose completeness the
  record cannot prove.

None of them costs a number: every refusal is named in `products.json` under
the file's key with `#integration` (or `#distributions` for the unidentified
split) and in `post.log`.

## Why it is not fixed here

The fallback cannot know the geometry. What settles each case is a live
rotor definition in the reference (the match then calls the builder) or a
recorded boundary inventory, which `RunRecord` does not carry. Recording the
geometry's inventory at export time is a design change for the run and
workspace subpackages, planned for 0.27.0 with the post-completeness work,
rather than a further widening of a matcher that nine rounds narrowed.

## What the reader can rely on meanwhile

State the rotors in the reference's `[rotors]` table and cite exact boundary
names, aliases or rotor names in an integrating entry; integration then
matches through the builder and is exact. Where a skip names the block,
the raw sectional columns are complete and the integrated columns are the
only thing withheld. Closure requires the recorded inventory, the fallback
re-measured against it, and the false-miss regressions of
`tests/tier1_offline/test_ghmain0260_post.py` and `test_gh3_post.py` turned
into positive matches where the inventory settles them.
