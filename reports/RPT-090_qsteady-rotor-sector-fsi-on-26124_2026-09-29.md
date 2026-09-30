# RPT-090 - The qsteady_rotor sector with FSI, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.30.0 `qsteady_rotor` workflow on a periodic
**sector** coupled with **FSI**, run through the package's own path
(`pyfs-matrix plan`, `pyfs-matrix run`, the post that `run` performs) on
**FlightStream 26.124, build 8172026**, executable SHA-256
withheld from the public tree per NFR-31 (measured
from the executable that ran, and recorded as `fs_exe_sha256` in both run
records). The package is the tree of `feat/0-30-storage-sync` at `4f12aede`,
which carries the four fixes listed at the end (the records name `c89c603d`,
this report branch on top of it, whose `src/` is identical;
`package_dirty: false`). One solver instance at a time, hidden, far field 5
layers. **Both rows use the pproc's default exports**: no export kind is
turned off.

## What was run

The geometry is one blade of a six-blade research propeller (its geometry is not
published), imported from an OBJ mesh (936 vertices), with `SYMMETRY PERIODIC`
and `PERIODIC_COPIES: 6`. Shaft along X through the origin, blade one at
azimuth 0 on Z. Flight condition: Mach 0.1441, Re 4.38 million on the
reference chord, alpha 0, 473.17227304307556 rev/min, which the run resolves to
49.036 m/s and 0.63261 kg/m3. Steady solver, 500 iterations at most,
convergence 1e-5, `SET_FREESTREAM ROTATION 3 X 473.17227304307556` in the
rotor's hub frame (the emitted script). The pproc declares one XY section
distribution over blade one in the hub frame, 30 cuts.

Two rows, identical but for the FSI keys:

| row | run id | FSI | status | wall time (record `wall_time_s`) |
|---|---|---|---|---|
| rigid | `pfs0300-l1-ws/sim_9011/M144RE438AL+000BE+000RPM00473` | none | CONVERGED (60 iterations, residual 8.28e-7) | 2.3 s |
| coupled | `pfs0300-l1-ws/sim_9012/M144RE438AL+000BE+000RPM00473` | `FSI: f002`, `FSI_BENDING_STIFFNESS_N_M2_FACTOR: 1.0`, `FSI_TORSION_STIFFNESS_N_M2_FACTOR: 1.0` | CONVERGED (427 cumulative iterations, residual 3.18e-7) | 67.0 s |

The whole `pyfs-matrix run` of both rows took 1 min 11 s. The FSI input is a
calculated solid Ti-6Al-4V (grade 5, annealed) blade from the blade's own
section contours, one blade, stiffness factor 1 on both EI and GJ, 48
structural nodes. The post wrote every product of both points and recorded no
skip (`post/l2_sector/products.json`): the polars, the quasi-steady clockings
and average tables, the rotor table, and the sections, sectional-loads and Cp
products of each point, the coupled one included.

## The five points to confirm

**1. Vertices mapped: 936, greater than 0.** The `$AEROELASTIC$` header of the
saved state of the coupled run (`P9012-...fsm` in its datapoint folder) reads
`1,936,1,50,4`: 936 mapped surface vertices (every vertex of the blade), 50
coupling iterations allowed, kernel 4 (`MULTI_QUADRATIC`). The script assigns
the surface as `ASSIGN_AEROELASTIC_SURFACES 1` / `2`, the OBJ blade's boundary
ID (the FSI-1 fix of RPT-093 fact 2).

**2. The FSI residual goes to convergence.** The solver log of the coupled run
(`P9012-..._log.txt`) carries one line per coupling iteration, 18 in all:

```
Aeroelastic solver residual for FSI iteration-1 is  9.3750000E-1
Aeroelastic solver residual for FSI iteration-2 is  3.1141876E-1
Aeroelastic solver residual for FSI iteration-3 is  1.3273779E-1
...
Aeroelastic solver residual for FSI iteration-16 is  2.0769830E-5
Aeroelastic solver residual for FSI iteration-17 is  1.0142337E-5
Aeroelastic solver residual for FSI iteration-18 is  5.6531191E-6
```

The first two steps divide it by 3.0 and 2.3; from iteration 3 to iteration
14 each step multiplies it by 0.46 to 0.50, the step to iteration 15 by 0.83,
and the last three by 0.50, 0.49 and 0.56 (`fsi_residual_ratios`). The
configured `coupling_relaxation` is 0.5 (`fsi_convergence_log.csv`, column
`relaxation`, every call). It stops at iteration 18 of 50, below the 1e-5
convergence limit. The package
stopped the solver after the completion line (`pyfs-aeroelastic-stop.log` in
the datapoint folder: "stopped after the aeroelastic analysis ended (its
completion line printed)"). The post-processing script the toolbox runs after
every coupling iteration (`fsi_post.txt`) updates the sections once, first,
then carries the structure's sectional loads and the row's whole default
export block.

**3. Tip deflection: nonzero, 3.34 mm.** The structural program's last call
(`fsi_convergence_log.csv`, call 18, phase `quasi_steady_rotor`) states a tip
flap of 3.340913e-3 m and a tip twist of 0.128534 deg; the written tip
displacement (`FSIDisp.txt`, the last three rows, the tip station's
elastic-axis, leading-edge and trailing-edge nodes) is (-2.660e-3, +2.022e-3, 0) m
at the elastic-axis node, 3.34 mm, and 3.24 and 3.50 mm at the leading-edge
and trailing-edge nodes (`fsidisp_tip_nodes_m`). The exported deformed surface
(`P9012-...vtk`) against the rigid run's surface (`P9011-...vtk`), over the
936 vertices of blade one, moves by at most 3.55 mm, at the tip
(r = 1.824 m): 2.84 mm toward -x (the thrust side) and 2.14 mm along +y
(`exported_surface_max_displacement_components_m`).

**4. The Omega staged is 2 pi rpm / 60.** The staged `config.json` states
`omega_rad_per_s = 49.55048456248367`, and 2 pi x 473.17227304307556 / 60 =
49.55048456248367 rad/s to every printed digit. The run folder carries the
marker `fsi_quasi_steady_rotor`, and every call's phase is
`quasi_steady_rotor`, the rotating solve (centrifugal tension, stiffening,
in-plane softening).

**5. The axial force against the rigid run of the same point.** From each
point's quasi-steady average (`post/l2_sector/polars/P9011-ROTOR_qs_avg.csv`,
`P9012-ROTOR_qs_avg.csv`), rotor loads in N and N m about the hub, and from
each point's rotor table (`P9011-ROTOR_rotor.csv`, `P9012-ROTOR_rotor.csv`, at
J = 1.70001):

| quantity | rigid | coupled | coupled against rigid |
|---|---|---|---|
| axial force Fx (N) | -373.84 | -376.82 | +0.80 % in magnitude |
| shaft moment Mx (N m) | -415.89 | -408.23 | -1.84 % in magnitude |
| in-plane Fy (N) | +338.99 | +333.09 | -1.74 % (`fy_change_pct`) |
| CT | -0.05309 | -0.05351 | +0.8 % in magnitude |
| CQ | -0.01615 | -0.01585 | -1.9 % in magnitude |
| CP | -0.10146 | -0.09959 | -1.8 % in magnitude |
| ETA | 0.88956 | 0.91345 | +2.7 % |

(CT and CQ are negative by the shaft sense of the loads frame, and the
efficiency is positive.) The loads export of the coupled run states `CDo`
0.0000000 where the rigid run states +0.0001225 (both runs have viscous
coupling off), so the two axial coefficients do not hold the same terms: `Cx`
rigid -0.0098306 is `CDi` -0.0099531 plus `CDo`, `Cx` coupled -0.0099088 is
`CDi` alone. On the induced part alone the coupled blade carries 0.45 % less
axial force than the rigid one (-0.0099088 against -0.0099531). The efficiency
is 2.7 % higher coupled: its axial force is 0.8 % larger and its shaft moment
1.8 % smaller. The missing viscous term is 1.25 % of the rigid run's axial
coefficient, more than the whole axial difference; how much of the smaller
shaft moment is the same missing term, these exports do not separate.

## Found and fixed before release

The first confirmation of this point, on `0331fe91`, found four package
defects; each was fixed on `feat/0-30-storage-sync` before this run, and this
run is their confirmation with the default exports:

- a coupled row with the default exports did not build (the sections were
  updated twice, the second time after an export): **69cffa41**;
- a clocked wheel's log was refused by the residual reader, which failed a
  wheel whose trailing edges came from a points file: **c46bee0e** (RPT-091);
- a clocked wheel's sections were not cut over the blade: **24edb353**
  (RPT-091);
- a `qsteady_rotor` point had no rotor table: **4113de02** (the tables above).

Against the first confirmation, measured file by file (`first_confirmation`
in the sidecar): the emitted run scripts are equal apart from paths and run
names; 69cffa41 changed the coupled row's post-processing script, which now
adds `UPDATE_PROBE_POINTS` and the section, sectional-load, probe and
section-Cp exports; and every solver-side number is equal. The loads exports
are equal in every line apart from the file name and the time (seven printed
decimals per coefficient), the averaged six components to every printed digit,
the residual lines, the `$AEROELASTIC$` header, `FSIDisp.txt` and the
convergence log equal, and the two VTK exports byte-identical.

## First confirmation (draft, 0331fe91, not released)

Dated 2026-09-29. The first confirmation ran on `0331fe91` and was committed
as a draft of this report in `c89c603d`; it was never pushed and never on
main, and git history keeps that draft. Its values, from its own run files:

| run id (code `0331fe91`) | status | iterations | residual | wall time |
|---|---|---|---|---|
| `pfs0300-l1-ws/sim_9001/M144RE438AL+000BE+000RPM00473` (rigid) | CONVERGED | 60 | 8.28e-7 | 4.3 s |
| `pfs0300-l1-ws/sim_9002/M144RE438AL+000BE+000RPM00473` (coupled) | CONVERGED | 427 | 3.18e-7 | 81.8 s |

- Loads (quasi-steady average): Fx -373.84 N rigid (9001) and -376.82 N
  coupled (9002), Mx -415.89 and -408.23 N m, Fy +338.99 and +333.09 N.
- Residuals: 18 coupling iterations of 50 on 9002, from 9.375e-1 to 5.65e-6.
- Mapping: `$AEROELASTIC$` header `1,936,1,50,4` on 9002.
- Tip deflection: tip flap 3.340913e-3 m and tip twist 0.128534 deg on 9002,
  the elastic-axis node at (-2.660e-3, +2.022e-3, 0) m.

What changed between it and the run above: with the default exports the plan
refused the coupled row, so 9002 ran with the section, sectional-load, probe
and section-Cp kinds turned off and has no sections product; the post wrote
no rotor table for either point. Both are fixed (69cffa41, 4113de02), and the
numbers above are equal to the re-run's.

## What remains an observation

- The coupled export carries no viscous drag (`CDo` 0 against +0.0001225
  rigid), the same observation RPT-089 section 1 made for a steady run; not
  decided here.
- One point, one stiffness, alpha 0: no sweep, no mesh or node-count study.
- The sector is solved steady with the rotation in the free stream; its
  agreement with a rotating unsteady blade is RPT-089 section 1 and RPT-093
  fact 5, not re-measured here.
