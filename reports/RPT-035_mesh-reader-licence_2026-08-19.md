# RPT-035: licence evidence for a mesh reader promoted to the required runtime set

Date: 2026-08-19. Written for `PFS-2025.20.02`, which asks for the
NFR-02 licence card that a mesh reader would need in order to become a
REQUIRED runtime dependency rather than an optional extra. `RPT-034`
measured three candidates against a stated weight budget and only
trimesh met all three limits, so trimesh is the distribution carded
here.

## This card does not replace RPT-003, and it must not be read as a second opinion

`RPT-003_geom-extra-licenses_2026-07-21.md` is the ADOPTION-TIME card
for trimesh and it stands unchanged. It gated the creation of the
`[geom]` extra and it covers trimesh, rtree and scipy together, because
the geometry gate needs all three.

What that card could not cover is a question that did not exist in July:
the licence surface a user is exposed to when a distribution moves from
an extra a user opts into, to the required set every install pulls. That
surface is the reader's TRANSITIVE CLOSURE with no extras bracket, and
this card measures exactly that, on today's resolution. Where the two
cards state the same fact they agree; where they differ, RPT-003 is the
older reading of an older version and this one says so.

## Method

A clean environment, so nothing already present in the development
environment is inherited:

```
python -m pip install --target ./tgt_trimesh trimesh --no-cache-dir
```

Python 3.12.0, pip 26.1.2, Windows-11-10.0.26200, 2026-08-19. Licence
values are read from the INSTALLED distribution metadata of the target
directory, through `importlib.metadata`, not from a project web page.
The field each value came from is named, in the shape `RPT-033` uses,
because `License-Expression` is an SPDX expression by definition while
the legacy `License` field is free text that someone must read.

## The closure, and every licence in it

`pip install trimesh` with no extras bracket resolves TWO distributions.
That is the whole surface a required-dependency promotion would add.

| Distribution | Version read | Field read | Value | SPDX identifier | MIT-compatible |
|---|---|---|---|---|---|
| trimesh | 5.0.0 | `License` (legacy), corroborated by `Classifier` | MIT licence text, copyright Michael Dawson-Haggerty; `License :: OSI Approved :: MIT License` | MIT, read from the legacy field | yes, identical licence |
| numpy | 2.5.2 | `License-Expression` | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | as published | yes, every term permissive |

numpy is in that table because a clean install resolves it, and it is
**already a required dependency of this package**, so it adds nothing to
what a user installs. It is carded in `RPT-016` as part of the runtime
set. Its conjunction of five identifiers is the vendored-code reality of
a scientific wheel rather than a complication: BSD-3-Clause, 0BSD, MIT,
Zlib and CC0-1.0 are all permissive and none is copyleft.

trimesh's own `Requires-Dist` names numpy unconditionally and everything
else behind the `easy`, `recommend`, `test`, `test-more` and
`deprecated` extras, which a bare install does not take. So the DELTA a
promotion would add to a user's install is one distribution, trimesh
itself, under one licence, MIT.

## The reading that RPT-003 states differently, recorded rather than reconciled silently

`RPT-003` records trimesh 4.12.2 as "MIT" with no field named. Today's
5.0.0 publishes no `License-Expression` either, so the identifier is
still a reading of the legacy `License` field, which holds the full MIT
licence text, plus a classifier that says the same thing. The
conclusion is the same and the EVIDENCE is one grade weaker than a
published SPDX expression would be, which RPT-003 did not say and this
card does.

That is not a defect in RPT-003; the distinction between a published
expression and a read field is one this repository started making later
(`RPT-033`, 2026-08-19). It is recorded here because a required
dependency is the place where the difference matters most: it reaches
every user with no opt-in.

## Verdict

A mesh reader promoted to the required runtime set costs one new
distribution under an MIT licence, read from the installed metadata of
version 5.0.0 on the date above, with a transitive closure that adds
nothing this package does not already require. **Nothing here is a
refusal.** NFR-02's licence condition for the promotion is satisfied.

## What this card does NOT establish

**It does not decide the promotion, and no card can.** NFR-06 is the
single home of record for the runtime set and states that the count does
not grow; `docs/mesh-inputs.md` records decision D8, that a widening of
the mesh seam puts meshio in the `[geom]` EXTRA behind a project-owned
adapter. Both are the author's to move. This card answers only the
licence question that a promotion would raise, so that when the decision
is taken the evidence is not the thing holding it up.

It also reads one resolution on one date. trimesh below 1.0 by SemVer's
own rule promises nothing across minors, which is a versioning question
for NFR-22 rather than a licensing one, and it is why
`PFS-2025.20.02`'s own plan requires a tested range at both ends rather
than a bare name.
