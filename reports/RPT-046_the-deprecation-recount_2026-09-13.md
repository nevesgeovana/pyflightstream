# RPT-046: the deprecation re-count at 0.17.0 (2026-09-13)

**WHAT THIS SETTLES.** Twelve deprecations declared `removal_version =
"0.17.0"`, and 0.17.0 is the release being cut. This is the count that moved
all twelve to 0.18.0 instead of removing them, taken so that the person
deciding at 0.18.0 whether the deadline may move again has a prior claim they
can re-run rather than a number in a transcript.

It exists because the V&V lens asked for it in round two of the release
panel: the deadline change was sound and its evidence was missing, and this
repository's own precedent for a measurement behind a decision is a committed
dated report (`RPT-029`, the type-checker exemption re-count).

## The command, and it is in the tree

```
python scripts/count_deprecated_spellings.py --root ../GeoverseResearch/tools/fts_workspace
```

The script is `scripts/count_deprecated_spellings.py`. It walks the
repository always, plus each `--root` given, and counts the spelling of each
name AS AN ARTIFACT CARRIES IT, so a prose mention of the word in a docstring
or in this report is not counted as a use.

## What was walked

| root | what it holds |
|---|---|
| the repository | every committed matrix, reference, setup and post-processing artifact, including the tier-3 fixtures |
| `../GeoverseResearch/tools/fts_workspace` | the recorded campaign workspaces, one per release since 0.3.0 |

The second root is a sibling tree and is not part of this repository, which is
why the count cannot be reproduced from a clone alone. That is stated rather
than hidden: it is also the half that matters most, because those workspaces
hold RECORDED campaigns and a manifest is the one surface a run cannot
regenerate.

NOT WALKED: `sims/`, `post/`, `archive/` and `build/`, which hold what a run
wrote rather than what a user edits. Their exclusion is why the number below
is a FLOOR and not a total.

## The result, 2026-09-13

```
MOVING_BOUNDARIES      54 occurrence(s) in  17 file(s)
ROTOR_AXIS             53 occurrence(s) in  17 file(s)
ROTOR_ORIGIN            0 occurrence(s) in   0 file(s)
RPM_SIGN               52 occurrence(s) in  16 file(s)
BLADES                 15 occurrence(s) in   8 file(s)
[aliases]              22 occurrence(s) in  22 file(s)
[[frames]]              8 occurrence(s) in   6 file(s)
TOTAL                                      39 distinct file(s)
```

**39 distinct files still state one of the deprecated spellings.** Eight of
them are recorded campaign workspaces; the rest are this repository's own
fixtures, which reproduce those campaigns.

`ROTOR_ORIGIN` reads zero. Its deprecation is kept in step with the other
nine of the motion group rather than removed alone, because they are one
migration for a user: a row states the whole `MOTIONS` record form or it
states the flat keys, and removing one name of the set would refuse a file
that is otherwise consistent.

## What this does NOT say

It does not say the migration is hard. It says it has not happened, which is a
different claim and the only one a count can make.

It does not measure the exit criterion. The ledger entry's exit is "no
recorded artifact states one", and nothing takes that measurement
automatically: this script is run when a human remembers. What IS mechanised
is the DATE, and `tests/tier1_offline/test_deprecation_deadline.py` goes red
at 0.18.0 whatever the count is then. That asymmetry is the same one the
`broken_commands` row has carried through three deadlines and it is recorded
here rather than smoothed over.

It does not count a use inside `sims/` or `archive/`, so a workspace that
carries the old spelling only in an output it already produced reads as clean
here and is.

## What a reader should do

Write the `MOTIONS` record form, and put the aliases and the frames on the
reference artifact. Nothing this package writes has emitted any of the twelve
since 0.15.0, and each deprecation warning names its own remedy.
