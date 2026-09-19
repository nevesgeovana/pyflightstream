# pfs0240: the licensed campaign of 0.24.0

**WHAT THIS IS.** The evidence that the products of 0.24.0 are coherent in number
on real licensed runs, re-measured from the raw exports and the products with the
standard library alone by `scripts/measure_campaign_coherence.py`. The numbers are
in `pfs0240_coherence.json` beside this page; this page says what was run, what
each check found, and what is not a property of the package.

## What was run

FlightStream 26.124 (build #8172026), one workspace, three matrix rows:

| row | geometry | run | points |
|---|---|---|---|
| 2401 | `12_WING_PHY.fsm` | steady | alpha 4, beta 0 and 5 |
| 2411 | `13_NX_B30_NMIN.fsm` | unsteady rotor, one PERIODIC sector of six copies, symmetry loads enabled | alpha 0 |
| 2412 | `24_NX_B30_NMI_FW.fsm` | unsteady rotor, the full wheel of six blades | alpha 0 and 10 |
| 2413 | `17_NX_B30_NMIN_FW.fsm` | unsteady rotor, the full wheel of the sector's own nacelle | alpha 0, **FROZE, see the correction** |
| 2414 | `17_NX_B30_NMIN_FW.fsm` | the same row again, far-field layers stated in the setup | alpha 0 |
| 2415 | `17_NX_B30_NMIN_FW.fsm` | the same, at incidence | alpha 10 |

Both rotor rows turn at 473.1723 rev/min for 144 time steps of 0.0017612 s (two
revolutions of 72 steps) and state `LAST_REVS_AVG: 0.5`, so every average is over
steps 109 to 144. In both scripts the blades and the spinner turn and the nacelle
does not.

Rows 2414 and 2415 turn for the same 144 steps and state the same window. Their
setup `s009` states `farfield_layers = 5`, so their scripts carry
`SOLVER_SET_FARFIELD_LAYERS 5` and a reader reproduces them from the script alone.

**A CHANGE MADE BY HAND, NOT BY THE PACKAGE.** On rows 2412 and 2413 the number of
far-field layers was set to 5 in the solver's interface, DURING the run, to shorten
it. It is not in the script those rows emitted, and its effect on the aerodynamics
is of second order. A reader reproducing row 2412 or 2413 from the script alone will
not have it.

## CORRECTION, 2026-09-19 evening: two runs FROZE, and what that changed

After this page was first written, two of the runs were found to have FROZEN: from
some time step on, the solver's velocity and pressure residuals are exactly zero on
every inner iteration after the first two, and every later load is a constant rather
than a solution. Row 2413 froze at step 60 of 144 and row 2412 at alpha 10 at step
64; rows 2401, 2411 and 2412 at alpha 0 have no frozen step. The window of an average
is the last 0.5 revolution, steps 109 to 144, so the frozen stretch is exactly what
those two averages were taken over.

What follows from it:

- **The alpha-10 line of the first writing of this page came from a frozen stretch**
  (it read `ETA -0.73804, ETAW -0.75313`, from row 2412 at alpha 10). It is withdrawn.
  The alpha-10 row of the table below is row 2415, a run with no frozen step.
- Row 2413's first attempt at the full wheel is likewise withdrawn, and row 2414 is
  the run that answers the sector-against-the-wheel check.
- `scripts/measure_campaign_coherence.py` now reads each point's native log: a point
  whose window touches a frozen step takes part in NO verdict and is listed under
  `no_frozen_solve_in_a_window`, so a check left without a valid point reads
  could-not-measure rather than coherent.
- The package of 0.24.0 accepted a frozen run as a success; detecting it at run and
  at post time is a 0.25.0 item (`B01` of the 0.25.0 scope).
- Both frozen runs are full wheels whose far-field layers were changed by hand in the
  interface while they ran; row 2414, the first with that number stated in the setup
  instead, did not freeze. That is a correlation over three runs, not a measured
  cause.

## What each check found

| check | verdict | measured |
|---|---|---|
| CDW equals the drag the solver integrates | coherent | worst gap 0.28 of its own band, at `P2401-V0300RHO12250AL+040BE+050.txt` |
| rotor table equals the window mean of its history | coherent | worst relative gap 3.6e-05 |
| sector against the full wheel | coherent | CT 0.13222 against 0.13243 on the sector's own nacelle (row 2414), ratio 0.9984; the wheel of the OTHER nacelle (row 2412) reads 0.10194, ratio 1.297, and decides nothing (see below) |
| ETAW equals ETA at alpha 0 | coherent | worst gap 0.0 |
| ETAW departs from ETA with alpha, with ETA's sign | coherent | alpha 10.0 (row 2415): ETA 1.09187, ETAW 1.26777, J CTW/CP from the history 1.26779, gap 1.5e-05 |
| no frozen solve in a window | coherent | the frozen points of rows 2413 and 2412 at alpha 10 are listed and left out of every verdict |
| every unsteady file says average or instant | coherent | no entry silent |
| the manifest equals the disk | coherent | both differences empty |

All eight are coherent, and the instrument exits 0.

## Where these rotors operate: windmilling

At alpha 0 both rotors are WINDMILLING, not propelling. The rotation frame of both
scripts is the export's own (x aft), the rotor turns at +473 rev/min about +x, and:

| alpha 0 | sector | full wheel |
|---|---|---|
| force along the shaft | +931 N, aft | +718 N, aft |
| torque about the shaft | +753 N m | +539 N m |

The force points AFT, a drag, and the torque points WITH the rotation (a positive
rev/min read as a right-hand rotation about +x, the package's convention): the air
drives the rotor. At an advance ratio of 1.70 that is the windmilling regime. So `ETA`
above 1 (1.22 and 1.32) is not a propulsive efficiency: J CT / CP is a ratio of two
quantities that are both reversed. At alpha 10 (row 2415) the wheel of the sector's
own nacelle reads CT 0.10138, `ETA` 1.09187 and `ETAW` 1.26777: the same regime, with
the wind-axis projection above the shaft-axis one because the shaft is inclined to
the stream. The coherence checks compare the package's columns with the history and hold
whatever the regime; the regime is what a reader of `ETA` needs to know.

## The sector against the full wheel

At alpha 0 the rotor's force along its shaft, averaged over the same window:

| | sector (2411, six periodic copies) | full wheel, the sector's nacelle (2414) | full wheel, the other nacelle (2412) |
|---|---|---|---|
| force along the shaft | 931.04 N | 932.49 N | 717.79 N |
| torque about the shaft | 753.07 N m | 753.62 N m | 539.08 N m |
| side force, lift force | 0 and 0 | -- | -115.7 N and +143.1 N |
| one blade's axial coefficient | one value, every copy the same | -- | 0.0017 to 0.0037 around the disc |

Every history is flat over its last revolution: none is a transient.

**ANSWERED, and by the geometry.** The sector and the full wheel OF THE SECTOR'S OWN
NACELLE agree to 0.16 per cent (CT 0.13222 against 0.13243, ratio 0.9984), inside the
5 per cent band stated before the data. The wheel of the other nacelle reads 1.297,
and the paragraphs below say why that comparison was never the sector's.

**The package is not the difference.** The sector's own history states a force
along the shaft and nothing across it, so the solver already reports the WHOLE
rotor from the sector; the package reads it once and multiplies by nothing. Had it
counted the copies twice the sector would read about 5 590 N, and had it missed
them about 155 N. The two emitted runs are equivalent in speed, clock and in which
boundaries turn.

**The two geometries are.** At alpha 0 an axisymmetric rotor has no force across
its shaft and every blade carries the same load. The full wheel carries 184 N
across its shaft and its blades differ by a factor of two, so it is not the
axisymmetric body the periodic sector assumes: that file carries a nacelle which is
NOT axisymmetric, and the periodic sector assumes one. Its nacelle reaches a radius of
0.836 m where the sector's reaches 0.366 m, measured from the two mesh files. The two
files are not one body, and the check is answered only by a full wheel of the
sector's own axisymmetric nacelle: row 2414, whose mesh is the sector's blade six
times over (every vertex of blade 1 identical, blades 2 to 6 exact 60 degree
rotations of it, and the spinner and nacelle areas six times the sector's). The
check's band of 5 per cent, stated before the data, is not widened to pass it.

## How to re-read it

    python scripts/measure_campaign_coherence.py <workspace> matriz pfs0240_coherence.json

over the posted workspace. It reads the raw exports under `sims/` and the products
under `post/matriz/`, imports nothing from the package, and exits 0 only when every
check is coherent.
