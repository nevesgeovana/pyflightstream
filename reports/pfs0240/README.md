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

Both rotor rows turn at 473.1723 rev/min for 144 time steps of 0.0017612 s (two
revolutions of 72 steps) and state `LAST_REVS_AVG: 0.5`, so every average is over
steps 109 to 144. In both scripts the blades and the spinner turn and the nacelle
does not.

**A CHANGE MADE BY HAND, NOT BY THE PACKAGE.** On the full-wheel run the number of
far-field layers was set to 5 in the solver's interface to shorten the run. It is
not in the script the package emitted, and its effect on the aerodynamics is of
second order. A reader reproducing row 2412 from the script alone will not have it.

## What each check found

| check | verdict | measured |
|---|---|---|
| CDW equals the drag the solver integrates | coherent | worst gap 0.28 of its own band, at `P2401-V0300RHO12250AL+040BE+050.txt` |
| rotor table equals the window mean of its history | coherent | worst relative gap 3.6e-05 |
| sector against the full wheel | INCOHERENT | CT 0.13222 against 0.10194, ratio 1.297 (see below) |
| ETAW equals ETA at alpha 0 | coherent | worst gap 0.0 |
| ETAW departs from ETA with alpha, with ETA's sign | coherent | alpha 10.0: ETA -0.73804, ETAW -0.75313, the magnitude of J CTW/CP from the history 0.75314 |
| every unsteady file says average or instant | coherent | no entry silent |
| the manifest equals the disk | coherent | both differences empty |

Six of seven are coherent. The seventh is not a property of the package, as the next section measures.

## The sector against the full wheel

At alpha 0 the rotor's force along its shaft, averaged over the same window:

| | sector (six periodic copies) | full wheel |
|---|---|---|
| force along the shaft | 931.04 N | 717.79 N |
| torque about the shaft | 753.07 N m | 539.08 N m |
| side force, lift force | 0 and 0 | -115.7 N and +143.1 N |
| one blade's axial coefficient | one value, every copy the same | 0.0017 to 0.0037 around the disc |

Both histories are flat over their last revolution: neither is a transient.

**The package is not the difference.** The sector's own history states a force
along the shaft and nothing across it, so the solver already reports the WHOLE
rotor from the sector; the package reads it once and multiplies by nothing. Had it
counted the copies twice the sector would read about 5 590 N, and had it missed
them about 155 N. The two emitted runs are equivalent in speed, clock and in which
boundaries turn.

**The two geometries are.** At alpha 0 an axisymmetric rotor has no force across
its shaft and every blade carries the same load. The full wheel carries 184 N
across its shaft and its blades differ by a factor of two, so it is not the
axisymmetric body the periodic sector assumes. Whether the two files are meant to
be one rotor is a question about the geometries and not about the package, and the
check's band of 5 per cent, stated before the data, is not widened to pass it.

## How to re-read it

    python scripts/measure_campaign_coherence.py <workspace> matriz pfs0240_coherence.json

over the posted workspace. It reads the raw exports under `sims/` and the products
under `post/matriz/`, imports nothing from the package, and exits 0 only when every
check is coherent.
