# RPT-049: a rotor on the builds before the rotary motion (2026-09-15)

**WHAT THIS SETTLES.** The `unsteady_rotor` workflow writes a rotor as a
`ROTARY` motion with `SET_MOTION_ROTOR_AXIS` and `SET_MOTION_ROTOR_RPM`, which
26.101 is the first edition to document. The three editions before it (25.100,
26.000 and 26.100) name the motion type `EUCLIDEAN` and set it with
`SET_MOTION_ANGULAR_VELOCITY` and `SET_MOTION_IS_ROTOR`, and the scripting page
of `SET_MOTION_ANGULAR_VELOCITY` states no unit (SRC-741 p.329). Whether the
package can write the same rotor in that vocabulary rests on three facts no page
settles: the unit, the sense of rotation, and whether each build accepts the
commands its manual prints. This round measured them.

**EVIDENCE.** `reports/probes/RPT-049_2026-09-15_evidence.yaml` carries the
matrix and setup of the rotor rows, each rendered script's digest and its
motion lines, the digest of every output file, the run records, the measured
centroids and angles, the scripts of every rotor-mark variant with whether its
log was written, and the executable name scan. The surface exports and saved
simulations are mesh data and stay on the measuring machine; they are named
there by digest.

**THE VERDICT.**

1. On 26.000 a Euclidean motion with `SET_MOTION_ANGULAR_VELOCITY` equal to the
   rotor speed in RAD/S along the axis, marked with `SET_MOTION_IS_ROTOR 1
   ENABLE X`, turns the blade exactly as the `ROTARY` motion at the same speed in
   rev/min turns it on 26.120: same angle, same sense, every exported node within
   1.7e-12 m. The unit is the one the manual's rotor tutorial has the reader
   convert the rotor speed into for the dialog field, radians per second
   (SRC-741 p.394).
2. On 26.100 the solver answers `SET_MOTION_IS_ROTOR` as an unrecognized
   command in every form tried and stops the script, exactly as it answers a
   name no build has; the 26.100 executable carries no command of that name. It
   is recorded as removed on 26.100. The executables of 25.100 and 26.000 carry
   it, and 26.000 runs it.
3. So the package writes the Euclidean rotor on 25.100 and 26.000, and 26.100
   has no scripted way to mark a motion as a rotor. That build's rotor cell
   remains unsupported rather than substituted.

## The probe, and the one thing it moves

The tier-3 synthetic blade (`tests.tier3_licensed.recipes.SHAPES["blade"]`,
one blade of radius 1.8288 m about the X axis), imported from the recipe's STL
and saved separately by each build, because 26.100 cannot open the simulation
26.120 saved: it answers that `OPEN` with an error opening the simulation file,
stops the script and writes no log, and it opens the one it saved itself
(`open_26100_*` in the evidence file). Two rows of one matrix, the same reference, setup and
post-processing, differing in `FS_BUILD` and in the geometry file the build
saved:

| row | build | motion the workflow wrote |
|---|---|---|
| control | 26.120 (build 7012026) | `CREATE_NEW_MOTION ROTARY`, `SET_MOTION_ROTOR_AXIS 1 X`, `SET_MOTION_ROTOR_RPM 1 473.1723` |
| probe | 26.000 (build 10202025) | `CREATE_NEW_MOTION EUCLIDEAN`, `SET_MOTION_ANGULAR_VELOCITY 1 49.55048738540619 0.0 0.0`, `SET_MOTION_IS_ROTOR 1 ENABLE X` |

473.1723 rev/min is 49.5504874 rad/s. Both rows march three steps of 30 degrees
(`DELTA_THETA: 30`, `REVOLUTIONS: 0.25`), a time step of 0.010566975 s. The
setup is the tier-3 unsteady preset without four settings 26.000 does not
document as commands (the stabilization pair, wake-on-wake induction and the
additional wake relaxation), removed from BOTH rows so the rows still differ
only in the build and its motion vocabulary; 26.100 lacks the same four except
the two wake settings, and the header of the reduced preset, written for the
first attempt on 26.100, names only the stabilization pair. Both runs converged.

## What moved

The surface export after the last step, 262 nodes, against the recipe's own
STL:

| | centroid (x, y, z) m | angle about X |
|---|---|---|
| the recipe's STL | 0.0362, 0.0257, 1.0516 | 88.601 deg |
| 26.120, ROTARY | 0.0362, -1.0516, 0.0257 | 178.601 deg, turned +90.000 |
| 26.000, EUCLIDEAN | 0.0362, -1.0516, 0.0257 | 178.601 deg, turned +90.000 |

Largest distance between the two exports, node for node: 1.7e-12 m. Three
steps of 30 degrees is 90 degrees, so the blade reached the end of the third
step in both, turning the same way. Had the command read degrees per second the
blade would have turned 1.6 degrees; had it read rev/min, 9.4 degrees.

The loads of the two rows are not equal and this round does not claim they
should be: the solvers are different builds. Over the three steps the total
axial force (the evidence file's `axial_force_per_step`) was -480.09, -480.11, -480.12 N on 26.120 and -480.09, -474.31,
-473.56 N on 26.000, equal at the first step and 1.4 percent apart at the
third. The in-plane force components rotate with the blade in both, which is
the same sense of rotation seen in the loads.

## `SET_MOTION_IS_ROTOR` on 26.100

Seven scripts on 26.100, each opening the blade 26.100 saved, creating a
Euclidean motion over every boundary, adding one variant and exporting the log:

| variant | the log was written |
|---|---|
| no rotor mark (control) | yes |
| `SET_MOTION_IS_ROTOR 1 ENABLE X` | no |
| `SET_MOTION_IS_ROTOR 1 DISABLE X` | no |
| `SET_MOTION_IS_ROTOR 1 ENABLE Y` | no |
| `SET_MOTION_IS_ROTOR 1 ENABLE 1` | no |
| the angular velocity, then `SET_MOTION_IS_ROTOR 1 ENABLE X` | no |
| `SET_MOTION_IS_ROTOR 1 ENABLE` | no |

Every variant with the command stopped with no log. The same
seven scripts on 26.000, on the blade 26.000 saved: the control and the five
forms with two arguments wrote their logs, and the form with one argument did
not. The full rotor script was first bisected on 26.100 to the line
`SET_MOTION_IS_ROTOR 1 ENABLE X`, the first after which the log is not written;
that bisection's scripts are not committed, and the variant and control scripts
below, with the solver's own messages, are the committed record.

A second round the same morning put the command beside a name no build has,
`SET_MOTION_NOT_A_COMMAND_PROBE 1 ENABLE X`, in the same script, with the solver's
standard output kept (each script's error lines and the digest of its output
are in the evidence file). On 26.100 both lines drew the same two messages, an
unrecognized command in the script at that line and an error at that line, and
neither script wrote its log; the script without the extra line wrote it. On
26.000 the rotor mark ran and the log was written, and the unknown name drew
the same two messages; the one-argument rotor mark drew the error line alone,
so 26.000 knows the name and refuses those arguments. Every rotor-mark variant
was run again with its output kept, with the outcomes of the tables above. So 26.100 does not reject the rotor mark's arguments: it
does not know the name. That is the outcome this database records as a removal
(as RPT-021 did for a name 26.121 answered the same way), and the seven-script
table was rerun on both builds with its output kept, with the outcome above.

The executables' own command-name strings agree (the evidence file's
`executable_name_scan`, with each executable's digest): `SET_MOTION_IS_ROTOR` occurs
in the 25.100 and 26.000 executables and not in the 26.100 one, which also
lacks `SET_MOTION_VELOCITY` and `SET_MOTION_ACCELERATION` while carrying
`SET_MOTION_ANGULAR_VELOCITY` and `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION`.
The SRC-741 manual prints all of them. The removal rests on the solver's own
answer above; nothing is changed on the strength of the strings alone.

## What this does NOT say

- 25.100 was not run. Its database carries no `AUTO_DETECT_TRAILING_EDGES`, so
  the tier-3 preparation cannot save a blade on it. The substitution on 25.100
  rests on its manual (SRC-748 pp.306-307, the same grammar as 26.000) and on
  the 26.000 measurement, and on its executable carrying the command name.
- One axis, one sense and one speed were run. A negative speed and the Y and Z
  axes follow from the vector the command takes and were not measured.
- The rotor mark's effect on the solution (the slipstream treatment it
  selects) was not isolated: both rows mark the rotor, each in its own
  vocabulary.
- Nothing here measures a periodic sector beyond the one blade with six
  periodic copies the tier-3 rotor row states.
