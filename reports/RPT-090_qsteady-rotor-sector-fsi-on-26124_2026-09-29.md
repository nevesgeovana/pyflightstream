# RPT-090 - The qsteady_rotor sector with FSI, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.30.0 `qsteady_rotor` workflow on a periodic
**sector** coupled with **FSI**, run through the package's own path
(`pyfs-matrix plan`, `pyfs-matrix run`, the post that `run` performs) on
**FlightStream 26.124, build 8172026**, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65` (measured
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

It roughly halves per iteration (the configured `coupling_relaxation` 0.5) and
stops at iteration 18 of 50, below the 1e-5 convergence limit. The package
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
at the elastic-axis node, 3.34 mm, and 3.24 to 3.50 mm at the other two. The
exported deformed surface (`P9012-...vtk`) against the rigid run's surface
(`P9011-...vtk`), over the 936 vertices of the meshed blade, moves by at most
3.55 mm, at the tip (r = 1.824 m): 2.84 mm toward -x (the thrust side) and
2.14 mm along +y.

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
| in-plane Fy (N) | +338.99 | +333.09 | -1.74 % |
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
axial force than the rigid one (-0.0099088 against -0.0099531), and much of
the efficiency difference is that missing viscous term, not the deformation.

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

The solver-side numbers of this point are identical to every printed digit to
the first confirmation's (loads, residuals, mapping, displacement).

## What remains an observation

- The coupled export carries no viscous drag (`CDo` 0 against +0.0001225
  rigid), the same observation RPT-089 section 1 made for a steady run; not
  decided here.
- One point, one stiffness, alpha 0: no sweep, no mesh or node-count study.
- The sector is solved steady with the rotation in the free stream; its
  agreement with a rotating unsteady blade is RPT-089 section 1 and RPT-093
  fact 5, not re-measured here.
