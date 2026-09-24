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

## A user's own frame spelt like a rotor's, registered here on 2026-09-23

Two entries on a common frame the specification names `X_RMRP`, with no
rotor X anywhere, each integrating its own recorded block. The names those
blocks record are the geometry's own spelling, and an attestation that read
them so let each entry own its block alone. The record carries no provenance
for a block, and the same frame name is a rotor's frame once that rotor is
removed from the reference after export, or its block sits on the rotor's
`_ORIGINAL` twin, or an alias of the rotor cites a custom frame: each of
those recorded the reference's spelling and, attested as the geometry's,
transferred a neighbour's integration to an entry that had it off (measured
2026-09-23 on the nineteenth reading of 8b1f74a). Attestation now reads the
frame's name and the declared rotors' spellings only, so on `X_RMRP` both
entries are refused as ambiguous, by name, with their raw rows kept. The
recorded inventory settles it with the rest.

## Why it is not fixed here

The fallback cannot know the geometry. What settles each case is a live
rotor definition in the reference (the match then calls the builder) or a
recorded boundary inventory, which `RunRecord` does not carry. Recording the
geometry's inventory at export time is a design change for the run and
workspace subpackages, planned for 0.27.0 with the post-completeness work,
rather than a further widening of a matcher that nine rounds narrowed.

## The one case ownership gets wrong by name, registered here on 2026-09-23

Ownership of a legacy layout resolves the recorded pproc's selectors over the
recorded cuts, because there is no other evidence and a raw file has to be
named by something. Two `RMRP` entries, the first selecting `Blade1` on a
rotor that emitted nothing at export time and the second selecting rotor
`ACTIVE` (Blade11, Blade12) with no rotor definition in hand: the cuts hold
one block, the first entry resolves to it by stem, the second resolves to
nothing, and the block is written under the first entry's name with the
manifest naming it as the first distribution. The four rows are all present
and nothing is integrated; the name and the ownership are wrong. The
alternative, refusing the split as unidentified, loses the rows. The name is
settled the same way as the rest of this report: a live rotor definition or
a recorded inventory, and the same 0.27.0 work closes it.

## What the reader can rely on meanwhile

State the rotors in the reference's `[rotors]` table and cite exact boundary
names, aliases or rotor names in an integrating entry; integration then
matches through the builder and is exact. Where a skip names the block,
the raw sectional columns are complete and the integrated columns are the
only thing withheld. Closure requires the recorded inventory, the fallback
re-measured against it, and the false-miss regressions of
`tests/tier1_offline/test_ghmain0260_post.py` and `test_gh3_post.py` turned
into positive matches where the inventory settles them.

## CLOSED in 0.27.0, 2026-09-24

Closed by R03 and R04 of 0.27.0, the three conditions of the section above taken in
order.

**The recorded inventory (R03).** Each run record carries `inventory`, the geometry's
boundary names in the solver's order as the script read them at `OPEN`, written on both
run paths: the point path and the steady one-job path. The same item makes the one-job
path record its `sections_layout`, which it had not done since 0.24.0, so the post refused
the per-distribution split of every steady row of several points: without that, R03
settles nothing for a steady polar. It needs no id of its own and is closed here with
R03. A record written before 0.27.0 carries no names, and the post reads them (R04) from
the mesh block of the geometry file whose sha256 the record carries in `inputs_sha256`,
the simulation's own staged copy first and the library's file of that name second. The
hash, never the name, says the file is the one that ran, and the unhashed
`<stem>.boundaries.toml` sidecar is not read.

**The fallback re-measured against it.** With the names in hand the match reads a
selection by the export builder's own expansion over them. The tests are in
`tests/tier1_offline/test_r03_r04_recorded_inventory.py`, and the positive cases below
are the matches the section above says the inventory settles. Where the geometry carries
no boundary named `Blade` and no third blade, a family stem (`Blade` over Blade1 and
Blade2) integrates. A numbered name over a wider family (`Blade1` over Blade11 and
Blade12, where the geometry has no `Blade1`) integrates. `all`, recorded as an empty
family list, integrates over the whole inventory. Each of two entries on a user's own
`X_RMRP`, with the geometry's Blade1 and Blade2, integrates its own block. The legacy
ownership case of this report is also settled. Entry `Blade1` is a boundary the geometry
carries, so it emitted no block of Blade11 and Blade12. The block therefore goes by
elimination to entry `ACTIVE`, the one entry whose word nothing resolves. It is written
as `sections/<point>_sloads_ACTIVE.csv`, distribution 2, with its four rows and no
integrated column. The matching refusals hold by name: a stem the geometry also carries
as a boundary, a third blade, and a numbered name the geometry carries exactly.

**The regressions.** The false-miss cases of `test_ghmain0260_post.py` and
`test_gh3_post.py` are unchanged and still pass, because their records carry no names.
They are the controls without an inventory. Their positive counterparts are the cases
above.

**What stays refused by name, on purpose.** These cases keep the raw columns and a named
skip, as before:

- a rotor's name with no rotor definition in hand, for integration: over the names it
  resolves to nothing, so its entry stays a possible owner of every block of its frame
  kind, plane and count;
- on an expanding frame with no rotor definition, the recorded-frame grouping still
  decides, because the names say what a selection holds and not which rotor owns it. An
  entry the grouping refuses stays a possible owner there, so ownership by elimination
  names no single owner when such an entry sits beside the rotor's name, and the cuts
  decide as before. The case is `a-certain-rival-on-a-rotor-frame`: `Blade`, which
  selects Blade1, Blade11 and Blade12, beside `ACTIVE`;
- a geometry changed or deleted since the run: no file carries the recorded hash, so the
  cuts decide, and the rows are kept;
- a record of a run that opened no geometry declaring names: a LEGACY recipe, or a file
  without a mesh block. Such a record has no `inventory` key.

**Compatibility.** Adding the field did not move `MANIFEST_SCHEMA`, and the key is
absent where no names were recorded, which is the `forced_local` rule. This was measured
on 2026-09-24 with the `RunRecord` of the v0.26.0 tag. A 0.27.0 row without the key
reads. A row with it is refused with `extra_forbidden`. Every 0.27.0 workflow record of
a `.fsm` with a mesh block carries the key, so such a manifest needs 0.27.0 to read it.

**Evidence.** On the tree before the fix the new tests failed:

- the settled selection: `ValueError: "RunRecord" object has no field "inventory"`;
- the records: `KeyError: 'inventory'`;
- the job's layout: `assert None == [{'distribution': 1, ...}]`;
- the legacy split: `sections/AL-020_sloads_ACTIVE.csv` was absent, and the block was
  written as `..._Blade1.csv`, distribution 1;
- the recovery by hash: `'CampaignWorkspace' object has no attribute
  'recorded_inventory'`.

After the fix, 20 of 20 pass. Each of 15 mutants was made on a scratch copy of the
source, and the pytest process printed the `pyflightstream` it imported from that copy.
An unmutated copy under the same harness passed 20 of 20. Every mutant turned at least
one case red:

- the names never reaching the matcher: 5 red;
- the cuts read in place of the names: 5 red;
- each of the three writer lines deleted, and the serializer keeping a null: 1 or 2 red
  each;
- the job's layout line deleted: 1 red;
- no elimination: 1 red;
- no fallback to the cuts: 2 red;
- no digest compared: 2 red;
- the hash read before the record's own names: 1 red;
- the post asking for no names: 1 red;
- elimination over uncertain entries only: 1 red;
- a certain entry never possible over the names: 1 red;
- the digest memo without its two-second guard: 1 red. This filesystem kept one
  modification time across 195 of 200 back-to-back rewrites of the same size, so this
  case is red on nearly every run rather than on every run.

No solver was run.

**Status:** CLOSED in 0.27.0
