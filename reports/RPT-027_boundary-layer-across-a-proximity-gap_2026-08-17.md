# RPT-027: the boundary layer across a proximity gap, 26.122 against 26.123 (2026-08-17)

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

**It is answered: the change is real, it is confined to exactly the
regime the vendor described, and it is present in both modes.** What this
report does NOT say is that the new number is the right one; a different
answer is not a better one, and that judgement is the author's.

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
quarter of a face length it changes the viscous drag by three quarters.

That is the vendor's stated condition, measured, and it is the reason the
gap is expressed as a ratio. It also means the wide-gap cases are a
CONTROL rather than a second data point: they are the same configuration
with the mechanism switched off by geometry.

## Result 2: the two builds differ only where the mapping engages

Total `CDo`, proximity ON:

| gap | mode | 26.122 | 26.123 | change |
|---|---|---|---|---|
| narrow | steady | 0.0166465 | 0.0113265 | **-31.96 %** |
| narrow | unsteady | 0.0166639 | 0.0113488 | **-31.90 %** |
| wide | steady | 0.0260383 | 0.0259471 | -0.35 % |
| wide | unsteady | 0.0260066 | 0.0259023 | -0.40 % |

Thirty-two percent where the boundary layer is mapped across the gap. A
few tenths of a percent where it is not, which is the same order as the
ordinary build-to-build movement the cross-version drift run of the same
day measured on unrelated cases
(`reports/physics/DRF-26122-26123_2026-08-17_full.yaml`).

The steady and unsteady relative changes agree to two decimal places,
which is what the vendor said about the modes.

## What this establishes, and what it does not

**Established.** A change exists between the two builds; it is confined
to the configuration where proximity-based mapping across a gap is
active; it is present in steady and unsteady alike; and it is invisible
in the documentation of either edition.

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
`wing_triangles(..., offset_m=...)`, `mean_edge_length` and the script
builder. The sixteen scripts, their logs and their loads files are on the
machine that ran them.

The one figure a reader may want to recompute without the solver is the
face length, which is `mean_edge_length(wing_triangles(WingSpec()))` and
is 0.15054 m.
