# RPT-093 - The Aeroelastic Coupling Toolbox on 26.124: nine measured facts (2026-09-29, amended 2026-10-01)

Amended 2026-10-01: the facts taken from the private campaign's results file are summarised, with their number, date, build and command, in RPT-131; no measurement of this report changed.

A synthesis of licensed probes on **FlightStream 26.124, build 8172026**, executable
SHA-256 withheld from the public tree per NFR-31 (the same
executable as [RPT-086](RPT-086_gui-launch-windows_2026-09-28.md) and
[RPT-087](RPT-087_periodic-native-tecplot-one-zone-per-copy_2026-09-28.md)). It
records what the Aeroelastic Coupling Toolbox does on a fixed wing, on a fixed
research propeller blade (OBJ import) with the rotation carried by the free stream, and
on a rotating research propeller blade, and it is the numbered report [RPT-025](RPT-025_rotor-morphing-across-three-builds_2026-08-11.md)'s
correction section and the command database cite for their dated claims.

## Why it was written

[RPT-025](RPT-025_rotor-morphing-across-three-builds_2026-08-11.md)'s
2026-09-28 correction, and the `ASSIGN_AEROELASTIC_SURFACES` entry of
`src/pyflightstream/commands/aeroelastic_coupling.yaml`, both cited "the 26.124
aeroelastic probes of 2026-09-28, not yet a numbered report." This report is
that number, and it also carries five findings the correction did not need:
the steady-solver log line and blocking behaviour, what each export format
does and does not carry, the two RBF kernels compared on one beam line, the
staged-start case, and the fixed-blade/rotating-freestream case that isolates
the morph from the rotation.

## Source

Every fact below comes from one of two places, both licensed, both on 26.124:

- A private licensed probe campaign of 2026-09-28 (its results file
  `PHASE3-RESULTS.md`, sections 1 to 14, not in this repository; its facts are
  summarised in RPT-131). That
  geometry is private; where a fact is stated with numbers from it, this
  report says so and gives no geometry, project or vendor-order identifier.
- A self-contained, generic-geometry reproduction, the folder
  **`fsi-vendor-case`**
  (zip SHA-256 `413cc6d1feed9a468c2388414e0f80c135202ff8f3eec9d9f813a38cbc7193ad`):
  a synthetic NACA 4409 research propeller blade (tip radius 1.8288 m, root
  radius 0.2743 m, one boundary, 1552 vertices, generated from public shape
  laws) and a synthetic NACA 0012 rectangular wing (1 m chord, 8 m span,
  2052 vertices), with four cases (A to D) and their scripts, geometries and
  figures. Its numbers are cited freely below and are marked "(vendor case)".

Every run in both sources was `-hidden -script`, one FlightStream instance at
a time, with a free-RAM preflight; every arm exited 0 and left no process
behind.

## 1. A scripted structural-frame import stores Reference, whatever frame is named

`IMPORT_AEROELASTIC_STRUCTURAL_NODES <frame> <ENABLE|DISABLE> <path>` writes
the structural coordinate-system field of the saved `$AEROELASTIC$` node block
as `1` (Reference) no matter which frame is given, and the frame argument is
not applied as a coordinate transform: eight scripted variants (order,
placement, coordinate-system index 2, 4 or 5, ENABLE or DISABLE, a linked
frame list, a non-identity frame rotated 30 deg) all stored `1` and all left
the node coordinates equal to the input file. This is a solver scripting
limitation on 26.124, not a property of any one script.

A frame chosen in the GUI IS stored (field `4` in a saved project file,
where the file's frame table names it a moving frame), and that stored value
**survives a scripted `OPEN`** of the GUI-saved file, and a scripted delete and
re-import of the nodes: the scripted import does not overwrite the field, it
leaves whatever the session already holds. A GUI-saved template that a script
opens is therefore the only route that carries a non-Reference node frame
into a scripted run.

## 2. The aeroelastic surface list is matched against the boundary ID

`ASSIGN_AEROELASTIC_SURFACES` is stored as written and the solver maps the
boundaries whose ID (the first field of the boundary's record in the saved
`$MESH$` block) matches that list. A script that assigns a surface cites it by
its position in the geometry tree, and the two do not always agree: an OBJ
import numbers its first boundary **2** (every OBJ case measured: the research
propeller blade, and a wing exported and re-imported as OBJ), while an STL
import, or a boundary FlightStream saved and reopened as `.fsm`, numbers its
first boundary **1**. A script that assigns surface `1` to a blade whose
boundary ID is `2` maps **0 vertices, in silence**: no refusal, no warning,
the `$AEROELASTIC$` header's mapped-vertex-count field stays `0` through the
whole run. Assigning the correct ID (`2` for the OBJ blade) maps every vertex
(936 of 936 on the private geometry's blade; 1552 of 1552 on the vendor case's
blade).

## 3. Rotary motion with coupling enabled from the start of the run: the morph replaces the rotation

With a rotating research propeller blade (a `ROTARY` motion, the Aeroelastic
Coupling Toolbox enabled before `START_SOLVER`), the surface-vertex mapping
forms and the structural program is called at every time step, but **after
every structural call the exported surface is put back at its imported (0 deg)
azimuth, carrying the displacement, instead of being morphed at the step's
rotated azimuth.** The next time step starts again from the rigid, rotated
blade at the new azimuth; the morph is evaluated on the un-rotated reference
geometry and replaces the rotated surface rather than composing with it.

Vendor case A measures it exactly this way: mapping 1552 of 1552, the blade
rotating 10 to 90 deg over 9 steps before each structural call and sitting at
0.00 deg carrying the flap after every call, the flap itself correct to
0.11 mm, while the un-rotated-but-flapped exported surface differs from the
correctly rotated-and-flapped blade by 319 mm at step 1 growing to 2588 mm at
the tip by step 9 (the arc the blade should have swept). The same behaviour
was measured on a second, differently shaped research propeller blade and on
build 26.122; it is not a 26.124 regression.

A later diagnostic put the rotation itself into the structural displacement
(a fixed node frame, `FSIDisp = R(theta)(x0 + flap) - x0`): the blade then
lands at the correct rotated-and-flapped position at every step, confirming
that the morph's base is the reference geometry. The RBF does not reproduce a
large rigid rotation exactly, though (up to 37 mm of residual at the root at
90 deg on the private geometry, growing with the angle), and the coupled
solve then diverges within about five steps; that composition is a
diagnostic, not a usable route.

## 4. Enabling the coupling mid-run, without re-initializing, never builds a mapping

Starting an unsteady run rigid (coupling disabled), running one or more
revolutions, then enabling the Aeroelastic Coupling Toolbox and continuing the
SAME solve without `REMOVE_INITIALIZATION` / `INITIALIZE_SOLVER`: the solver
continues the run (its iteration counter and azimuth carry on) and calls the
structural program at every coupled step, but **the surface-vertex mapping
stays 0 for the rest of the run.** Vendor case B measures this on the rotating
blade (mapping 0 throughout, no displacement ever applied); the private
campaign measured the identical result staging one full rigid revolution
(36 steps) before enabling the coupling for 9 more. The mapping is built only
when `START_SOLVER` begins with the coupling already enabled.

## 5. Blade fixed, free stream rotating, steady FSI: it maps and it exports the morph

Moving the rotation from the blade to the free stream (the blade has no
motion; `SET_FREESTREAM ROTATION` carries the rotation instead), with the
steady solver and `EXECUTE_AEROELASTIC_ANALYSIS`: the mapping forms
(936 of 936 mapped vertices on the private geometry's blade with 48 structural
nodes; 1552 of 1552 on the vendor case's blade), the solver prints a residual
per FSI iteration and stops on convergence (2 of 10 for a fixed displacement),
and **the exported surface carries the imposed displacement correctly, with
the blade at the right (fixed) position**: on the private geometry, the final
Tecplot export matches the imposed flap to a maximum error of 0.0001 m and an
RMS of 0.00002 m over every vertex, and the axial force (Fx -404.78 N rigid)
agrees within 0.35 % with the same blade rotating rigidly at the same azimuth
after one full revolution (-403.38 N); the vendor case's blade matches its
flap to 0.11 mm and its rigid axial force to within 0.5 % of the equivalent
rotating-rigid case (-755.26 N against -751.32 N). Fixing the blade and
carrying the rotation in the free stream is therefore the one rotor-blade
route measured here where the coupled surface export shows the correct,
converged, morphed geometry.

## 6. A fixed wing, steady and unsteady: it maps and it exports, both times

On a fixed wing (no rotor motion at all) with a 21-node structural beam line
on the quarter-chord, the mapping is 2052 of 2052 in every arm, steady or
unsteady, and the exported surface is bent:

- Round 1 (rigid control, `PRBF_R1`): CL 0.4221742, undeformed.
- Round 2, steady (`MULTI_QUADRATIC`, converged in 2 of 20 FSI iterations):
  final tip displacement 0.4066 m for a 0.4 m imposed bend, maximum error
  against the imposed shape 0.02419 m (at the trailing edge), CL 0.2464516.
- Round 2, unsteady (`MULTI_QUADRATIC`): the same final surface (tip
  0.4066 m, maximum error 0.02419 m), CL per call matching the round-1
  reference wing to all 7 printed digits before the final coupled call.

## 7. WENDLAND_C2 against MULTI_QUADRATIC on one beam line

With the same 21-node quarter-chord beam line and the same imposed
0.4 m tip bend on the fixed wing, the two RBF kernels the toolbox offers
disagree sharply:

- `MULTI_QUADRATIC` delivers the bend to within 0.0029 m at the leading edge
  and 0.4007 to 0.4066 m at the tip (a 0.34 to 1.22 deg parasitic
  nose-down shear inboard); the coupled solve stays stable.
- `WENDLAND_C2` delivers only **64 % of the imposed bend at the leading edge
  and 1.4 % of it at the trailing edge** (a nose-up shear reaching 14 deg at
  the tip); the coupled solve **diverges** within about three steps.

One beam line is not every possible node layout, but on this layout the
kernel choice is the difference between a stable, close-to-imposed morph and
a divergent, badly sheared one.

## 8. A steady coupled run logs one residual line per iteration, and a script cannot see the result

In a script, `EXECUTE_AEROELASTIC_ANALYSIS` **returns at once**: anything
placed after it in the same script runs before the coupled analysis has
iterated at all (an export placed there shows the rigid, pre-coupling
surface, at solver iteration 0), and a `CLOSE_FLIGHTSTREAM` placed after it
ends the process mid-solve, with no FSI call and no result. The steady
coupled analysis itself does run to completion in the background and prints,
to the console, one line per FSI iteration:

```
Aeroelastic solver residual for FSI iteration-1 is  9.3750000E-1
Aeroelastic solver residual for FSI iteration-2 is  0.0000000E+0
Aeroelastic solver run time: .02 minutes.
```

and stops once the residual reaches its convergence tolerance. The only way a
script observes the coupled result is the post-processing script the toolbox
runs after every FSI iteration (including the last), and the run is complete
once the console prints `Aeroelastic solver run time`.

## 9. What each export format carries: the morph, or the reference geometry

No export column, native Tecplot or VTK, carries the FSI displacement
directly: `FSI_displacement`, `FSI_dx`, `FSI_dy` and `FSI_dz` exist only in
the executable's scene contour-variable table (a GUI display variable, read
per vertex only by colouring the 3D view), not as an export column of any
format checked. What the coordinate columns of each export format carry after
a structural call differs by format:

- The native **Tecplot** and **VTK** surface exports carry the **morphed**
  vertex coordinates, once the export runs after the structural call (in an
  unsteady coupled run the toolbox's post-processing script runs twice per
  step, before and after the call; the file left behind after a step is the
  post-call, morphed one).
- The **TRI** export and a scripted **`SAVEAS`** carry the **reference**
  (undeformed) vertex coordinates in every arm measured, coupled or not.

So a route that must show the coupled deformation reads the Tecplot or VTK
surface export, never the TRI export or a saved `.fsm`'s stored mesh.

## What 0.30.0 does with these facts

- Fact 2 is fixed (**FSI-1**): the coupled route now computes the boundary ID
  the blade's motion holds (a tree position plus 1 for an OBJ import, plus 0
  for an STL import) and emits that ID to `ASSIGN_AEROELASTIC_SURFACES`;
  any other geometry is refused rather than guessed.
- Fact 3 is why FSI on the `unsteady_rotor` workflow is refused by the plan
  (**FSI-GUARD**): "FSI on unsteady_rotor is still in debug on this release
  (the morph is applied to the un-rotated blade, reported to the vendor)."
- Facts 5 and 6 are why FSI on `steady` and on `unsteady` without rotor motion
  arrives with the fixed-wing/fixed-blade structural route of this release
  (**FSI-G**), and why the `qsteady_rotor` workflow (rotation carried by the
  free stream, one steady solve per clocking) has its own entry and its
  sector structural route.
- Fact 7 is why the coupled route emits `AEROELASTIC_RBF_TYPE MULTI_QUADRATIC`
  unless a row's setup states another kernel.
- Fact 1 is why a route that needs a moving node frame saves the built
  simulation, patches the node block's frame field directly in the saved
  file, and opens the patched file, rather than relying on the scripted
  import's frame argument.
- Fact 9 is why the coupled route's exports that must show the deformation
  run inside the toolbox's post-processing script rather than after it.

## What is not established

- What makes the solver assign boundary ID 2 to an OBJ import and 1 to an STL
  import or a FlightStream-saved boundary is read from behaviour, not from
  the manual or the executable's strings; another import route was not
  tested.
- Whether the RBF kernel comparison of fact 7 generalises past one beam-line
  node layout was not measured.
- Composing the morph with a large rigid rotation exactly (fact 3's
  diagnostic) was shown to work geometrically but destabilises the coupled
  solve; no stable composed route is established by this report.
