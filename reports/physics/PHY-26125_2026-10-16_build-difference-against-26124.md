# Physics report: the native lift and drag differ between 26.124 and 26.125

Date: 2026-10-16. Node PFS-2131.001. Builds: 26.124 build 8172026 and 26.125 build 10052026.
Measurements: `reports/PFS-2131.001_build-comparison_2026-10-16.md` (licensed batch-4 evidence,
GEO-105 release 0.42.0 namespace `6bad1dac664ef7b0959e683749f4b1f437af6033-068e4257b4f4455696618fa3ffab9ab6`).

## Measured difference

The local wing case, solved with the same geometry, trailing-edge, boundary, audit and refinement
inputs (identical hashes), the same physical setup, five far-field layers, a 1500-iteration
ceiling and a requested 1e-6 convergence, gives on 26.125 against 26.124:

| Alpha (degrees) | CL 26.124 | CL 26.125 | CL change (percent) | Total CD 26.124 | Total CD 26.125 | Total CD change (percent) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.3722419 | 0.3525863 | -5.28 | 0.0203316 | 0.0233889 | +15.0 |
| 4 | 0.7240657 | 0.6863511 | -5.21 | 0.0339851 | 0.0380494 | +12.0 |
| 8 | 1.0716228 | 1.0169605 | -5.10 | 0.0553485 | 0.0613150 | +10.8 |

CL is the native exported value, not the post-derived CLW. Total drag is CDi+CDo on 26.124 and
CDp+CDv on 26.125, whose components are not equated. The rendered scripts differ only in the
build-specific grammar of the wake-edge import (METER on 26.124, edge type 1 on 26.125) and the
registered wake-detection command, and the batch-4 writer verification found the same package
code and the same writer on both builds; psutil metadata was added to the environment and is
not a cause of a solver result.

## Session judgement (2026-10-16)

With identical inputs, package code and writer, and only the build varying, the 5.10 to 5.28
percent decrease of CL and the increase of drag on 26.125 are a property of the solver build and
not of the package. The package does not compensate for it: no correction factor, no changed
default and no change of an emitted command follows from this report. Which of the two builds is
physically closer to the truth is not established here.

## Compatibility note for 26.125

On the wing case above, FlightStream 26.125 build 10052026 returns a native CL 5.1 to 5.3 percent
lower than 26.124 build 8172026 at 0, 4 and 8 degrees, and a total drag 10.8 to 15.0 percent
higher, for identical inputs. A campaign that mixes the two builds in one comparison carries that
difference; run both arms of a comparison on one build.

## Vendor question

To the solver vendor, with the two builds, the 26.124 and 26.125 rendered scripts of this node
and the three exported loads of each:

> The same wing, mesh, boundary conditions, trailing-edge marking and solver settings give a
> native CL 5.1 to 5.3 percent lower and a total drag 10.8 to 15.0 percent higher on build
> 10052026 (26.125) than on build 8172026 (26.124). Is this an intended change of the solver
> between the two builds, and which release note describes it?

This question is filed here; the session decides when it is sent.
