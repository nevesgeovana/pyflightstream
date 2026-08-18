# RPT-027: the boundary layer across a proximity gap, 26.122 against 26.123 (2026-08-17, amended 2026-08-17)

**Amended the same day, after review.** Four sentences drawing
conclusions were withdrawn and no measurement moved: every number in
every table is the one first published. `reports/README.md` binds this,
and the first version of the amendment carried the date alone, which is
what it forbids: a reader must be able to see that the file moved
without reading the history. So the four are named here as well as
marked where they stood.

1. Result 2's heading said the two builds "differ ONLY where the mapping
   engages". This report's own corroboration section shows three viscous
   drag coefficients moving on cases with no proximity gap in them, so
   the heading now says "most, by far".
2. The wide-gap movement was called "the same order as the ordinary
   build-to-build movement" that the same day's drift run measured. It is
   five to twenty-six times SMALLER than the three moving coefficients in
   that run.
3. The steady and unsteady changes were said to "agree to two decimal
   places". They agree to two significant figures.
4. The summary said the change is "confined to exactly the regime the
   vendor described". Two gap ratios bound the regime; they do not locate
   its boundary.

The vendor described FlightStream 26.123 to the author as improving the
boundary-layer model, specifically mapping the layer across
proximity-detected gaps between components, in steady and unsteady modes.
The documentation diff between the two editions does not show it: of the
seventeen pages that differ, the only boundary-layer page changed by two
spelling corrections and the FSI displacement additions. So either the
improvement is a solver change with no documentation change, or it lives
inside a screenshot where a text diff cannot see it, or it is not
documented in this build at all.

That is answerable only by running the solver. This is that run.

**It is answered: the change is real, it is far larger inside the regime
the vendor described than anywhere else measured, and it is present in
both modes.** Read "far larger" rather than "confined": two gap ratios
were sampled, so where the regime ENDS is bounded and not located, and
the same day's drift run moved three viscous drag coefficients on cases
with no gap in them at all. What this report does NOT say is that the new
number is the right one; a different answer is not a better one, and that
judgement is the author's.

## What was measured

Two copies of one wing, the second offset in the MESH rather than by a
solver transform command, so no transform is under test alongside the
thing being measured. NACA 0012, chord 1 m, span 8 m, the same generated
geometry the PHY-01 and PHY-02 cases use.

| quantity | value |
|---|---|
| mean triangle edge length of the mesh | 0.15054 m |
| section thickness | 0.1199 m |
| narrow gap between the facing surfaces | 0.037635 m, **0.25 face lengths** |
| wide gap between the facing surfaces | 0.301083 m, **2.0 face lengths** |
| free-stream velocity | 30 m/s |
| angle of attack | 2 deg |
| unsteady march | 20 steps at 0.002 s |

**The gaps are stated as a RATIO because the vendor's own caveat is one.**
It says the mapping may fail where the gap is large relative to the faces
around it, so a gap measured in metres with no face length beside it
supports no conclusion in either direction.

Sixteen cases: two builds, two gaps, steady and unsteady, with
`SOLVER_PROXIMAL_BOUNDARIES` enabled over both boundaries and with it
absent. The proximity control is what turns a level into a difference.
Every case returned 0 and wrote its loads.

The instrument is the integrated viscous drag coefficient, the `CDo`
column of the Total row of `EXPORT_SOLVER_ANALYSIS_SPREADSHEET`, which is
`verified` on both builds.

## The instrument this report does NOT use, and why

`EXPORT_BL_VELOCITY_PROFILE` was the obvious instrument: it exports the
boundary-layer velocity profile through the wall at one point, and
comparing matched stations on both components and inside the gap is the
direct form of the question.

**It cannot be used in an unattended run.** Measured on 26.122 on
2026-08-17: the command opens a modal window titled "Boundary layer
velocity profile", carrying a plot of velocity against height above the
surface and a Done button, and **script processing stops there until a
person dismisses it**. Under `-hidden`, with standard output and standard
error redirected. The first case of the first build blocked on the first
of its seven exports, produced no loads file and no log, and was only
recognised as a window rather than a hang because somebody was at the
machine.

This is a NEGATIVE MEASUREMENT and it is stronger than the documentary
silence it replaces: the command's own database entry records that the
manual gives no units for its coordinates, and nothing anywhere said it
is interactive. **No status is changed on the strength of it.** The entry
stays `documented`; a status of `broken` is promoted from a committed
probe report and this was a hand run, and in any case "opens a window" is
not the same claim as "the solver rejects it". The behaviour is recorded
in the entry's notes, citing this report.

The same class is already recorded in this repository for a different
cause: on the 25 series, a build given a command-line spelling it does
not know starts, checks out its licence, receives no script and waits,
ending under `-hidden` in a modal dialog nobody can answer (RPT-023). An
unattended run waits forever on a window whatever put the window there.

## Result 1: the proximity setting behaves exactly as the caveat says

Total `CDo`, with proximity against without:

| gap | mode | build | proximity ON | proximity OFF | change |
|---|---|---|---|---|---|
| narrow (0.25 face) | steady | 26.122 | 0.0166465 | 0.0660567 | -74.8 % |
| narrow | steady | 26.123 | 0.0113265 | 0.0650201 | -82.6 % |
| narrow | unsteady | 26.122 | 0.0166639 | 0.0707226 | -76.4 % |
| narrow | unsteady | 26.123 | 0.0113488 | 0.0694579 | -83.7 % |
| wide (2.0 face) | steady | 26.122 | 0.0260383 | 0.0260383 | **0.000 %** |
| wide | steady | 26.123 | 0.0259471 | 0.0259471 | **0.000 %** |
| wide | unsteady | 26.122 | 0.0260066 | 0.0260066 | **0.000 %** |
| wide | unsteady | 26.123 | 0.0259023 | 0.0259023 | **0.000 %** |

At two face lengths of separation the proximity setting changes nothing
at all, to every printed digit, on both builds and in both modes. At a
quarter of a face length it changes the viscous drag by 75 to 84 percent,
and the spread across those four rows is itself the result: the two
26.123 rows sit at 82.6 and 83.7 percent against 74.8 and 76.4 on
26.122.

That is the vendor's stated condition, measured, and it is the reason the
gap is expressed as a ratio. It also means the wide-gap cases are a
CONTROL rather than a second data point: they are the same configuration
with the mechanism switched off by geometry.

## Result 2: the builds differ most, by far, where the mapping engages

Total `CDo`, proximity ON:

| gap | mode | 26.122 | 26.123 | change |
|---|---|---|---|---|
| narrow | steady | 0.0166465 | 0.0113265 | **-31.96 %** |
| narrow | unsteady | 0.0166639 | 0.0113488 | **-31.90 %** |
| wide | steady | 0.0260383 | 0.0259471 | -0.35 % |
| wide | unsteady | 0.0260066 | 0.0259023 | -0.40 % |

Thirty-two percent where the boundary layer is mapped across the gap. A
few tenths of a percent where it is not, which is at or below the level
of ordinary build-to-build movement: of the thirty-eight metrics the
cross-version drift run of the same day measured on unrelated cases,
twenty-seven are byte-identical between the builds
(`reports/physics/DRF-26122-26123_2026-08-17_full.yaml`).

Do not read that as "the wide gap moves as much as everything else
does". It does not, in either direction. The eleven metrics that DO move
in that run include three viscous drag coefficients moving by 1.8, 2.2
and 9.0 percent, on cases with no proximity gap anywhere in them, which
is five to twenty-six times the STEADY wide-gap movement here, and four
and a half to twenty-three times the unsteady one. The builds
therefore differ in viscous drag by MORE, relatively, on cases where this
mapping cannot engage than in this experiment's own control. That is why
the heading above says "most" and not "only", and it is stated here
rather than left to the corroboration section, which is where this
report first noticed it.

The steady and unsteady relative changes agree to two significant
figures, both rounding to -32 percent, which is what the vendor said
about the modes.

They do NOT agree to two decimal places, and the first version of this
sentence said so in a way that invited two readings, so it is put
unambiguously: -31.96 and -31.90 differ in the second decimal, and
rounding each to one decimal separates them further, to -32.0 and -31.9.

## What this establishes, and what it does not

**Established.** A change exists between the two builds; it is far
larger in the configuration where proximity-based mapping across a gap is
active than anywhere else measured; it is present in steady and unsteady
alike; and it is invisible in the documentation of either edition.

**Not established: where the regime ENDS.** Two gap ratios were run, 0.25
and 2.0 face lengths. What is measured is presence at 0.25 and absence to
the printed digits at 2.0. Nothing between them was sampled, so the
transition is BOUNDED and not located, and a reader should not come away
believing this experiment found the boundary. Sixteen cases at two ratios
is a coarse instrument by design: the question asked was whether the
effect exists at all.

**Not established, and deliberately.** Whether 0.0113 is more nearly
correct than 0.0166 for this configuration. A lower viscous drag is a
different answer, not a better one. Nothing in this repository can settle
that, and the numerical-analyst seat is the author's. No tolerance was
adjusted and no case was re-run in search of a different number.

**Not established either**: that the mechanism is the one the vendor
named. What is measured is the DRAG, and the mapping is the vendor's
explanation for why it should move. The direct instrument, the profile
through the wall on each side of the gap, is the one that would show the
mechanism itself, and it is the one that opens a window.

## Corroboration from a run that was not looking for this

The Tier 3 cross-version drift run of the same day compared all six
physics cases on both builds in one session. Twenty-seven of its
thirty-eight metrics are byte-identical between the builds. Of the
remaining eleven, the only two that exceed their warn band are `CDo`, on
the two SMI cases, and the third case that carries a `CDo` moves the same
way inside its band. Every case in that matrix that measures a viscous
drag coefficient shows it lower on 26.123.

That run was designed to detect drift of any kind, not this. It agrees.

## How to reproduce

The driver lives in the private tree, which is where the licensed
executables and the geometry are; it writes nothing into the repository.
Everything it needs from the package is public: `WingSpec`,
`wing_triangles(..., translation_m=...)`, `generate_wing_stl(..., name=...)`, `mean_edge_length` and the script
builder. The sixteen scripts, their logs and their loads files are on the
machine that ran them.

The one figure a reader may want to recompute without the solver is the
face length, which is `mean_edge_length(wing_triangles(WingSpec()))` and
is 0.15054 m.
