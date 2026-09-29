# RPT-090 - The qsteady_rotor sector with FSI, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.30.0 `qsteady_rotor` workflow on a periodic
**sector** coupled with **FSI**, run through the package's own path
(`pyfs-matrix plan`, `pyfs-matrix run`, the post that `run` performs) on
**FlightStream 26.124, build 8172026**, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65` (measured
from the executable that ran, and recorded as `fs_exe_sha256` in both run
records). Package at commit `0331fe91` (0.30.0.dev2, `package_dirty: false` in
both records). One solver instance at a time, hidden, far field 5 layers.

## What was run

The geometry is one blade of a six-blade research propeller (its geometry is not
published), imported from an OBJ mesh (936 vertices), with `SYMMETRY PERIODIC`
and `PERIODIC_COPIES: 6`. Shaft along X through the origin, blade one at
azimuth 0 on Z. Flight condition: Mach 0.1441, Re 4.38 million on the
reference chord, alpha 0, 473.17227304307556 rev/min, which the run resolves to
49.036 m/s and 0.63261 kg/m3. Steady solver, 500 iterations at most,
convergence 1e-5, `SET_FREESTREAM ROTATION 3 X 473.17227304307556` in the
rotor's hub frame (the emitted script).

Two rows, identical but for the FSI keys:

| row | run id | FSI | status | wall time (record `wall_time_s`) |
|---|---|---|---|---|
| rigid | `pfs0300-l1-ws/sim_9001/M144RE438AL+000BE+000RPM00473` | none | CONVERGED (60 iterations, residual 8.28e-7) | 4.3 s |
| coupled | `pfs0300-l1-ws/sim_9002/M144RE438AL+000BE+000RPM00473` | `FSI: f002`, `FSI_BENDING_STIFFNESS_N_M2_FACTOR: 1.0`, `FSI_TORSION_STIFFNESS_N_M2_FACTOR: 1.0` | CONVERGED (427 cumulative iterations, residual 3.18e-7) | 81.8 s |

The whole `pyfs-matrix run` of both rows took 1 min 28 s. The FSI input is a
calculated solid Ti-6Al-4V (grade 5, annealed) blade from the blade's own
section contours, one blade, stiffness factor 1 on both EI and GJ, 48
structural nodes.

## The five points to confirm

**1. Vertices mapped: 936, greater than 0.** The `$AEROELASTIC$` header of the
saved state of the coupled run (`P9002-...fsm` in its datapoint folder) reads
`1,936,1,50,4`: 936 mapped surface vertices (every vertex of the blade), 50
coupling iterations allowed, kernel 4 (`MULTI_QUADRATIC`). The script assigns
the surface as `ASSIGN_AEROELASTIC_SURFACES 1` / `2`, the OBJ blade's boundary
ID (the FSI-1 fix of RPT-093 fact 2).

**2. The FSI residual goes to convergence.** The solver log of the coupled run
(`P9002-..._log.txt`) carries one line per coupling iteration, 18 in all:

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
completion line printed)").

**3. Tip deflection: nonzero, 3.34 mm.** The structural program's last call
(`fsi_convergence_log.csv`, call 18, phase `quasi_steady_rotor`) states a tip
flap of 3.340913e-3 m and a tip twist of 0.128534 deg; the written tip
displacement (`FSIDisp.txt`, the last three rows, the tip station's
elastic-axis, leading-edge and trailing-edge nodes) is (-2.660e-3, +2.022e-3, 0) m
at the elastic-axis node, 3.34 mm, and 3.24 to 3.50 mm at the other two. The exported deformed surface (`P9002-...vtk`)
against the rigid run's surface (`P9001-...vtk`), over the 936 vertices of the
meshed blade, moves by at most 3.55 mm, at the tip (r = 1.824 m): 2.84 mm
toward -x (the thrust side) and 2.14 mm along +y. The flap converged within
the first calls (3.3610e-3 m at call 1, 3.3409e-3 m at call 18).

**4. The Omega staged is 2 pi rpm / 60.** The staged `config.json` states
`omega_rad_per_s = 49.55048456248367`, and 2 pi x 473.17227304307556 / 60 =
49.55048456248367 rad/s to every printed digit. The run folder carries the
marker `fsi_quasi_steady_rotor` ("the structure turning at 49.55048456248367
rad/s"), and every call's phase is `quasi_steady_rotor`, the rotating solve
(centrifugal tension, stiffening, in-plane softening). The FSI input stated
the same speed, so `fsi-provenance.json` records no move from the row.

**5. The axial force against the rigid run of the same point.** From each
point's quasi-steady average (`polars/P9001-ROTOR_qs_avg.csv`,
`polars/P9002-ROTOR_qs_avg.csv`), rotor loads in N and N m about the hub:

| quantity | rigid | coupled | coupled against rigid |
|---|---|---|---|
| axial force Fx (N) | -373.84 | -376.82 | +0.80 % in magnitude |
| shaft moment Mx (N m) | -415.89 | -408.23 | -1.84 % in magnitude |
| in-plane Fy (N) | +338.99 | +333.09 | -1.74 % |

The loads export of the coupled run states `CDo` 0.0000000 where the rigid
run states +0.0001225 (both runs have viscous coupling off), so the two axial
coefficients do not hold the same terms: `Cx` rigid -0.0098306 is `CDi`
-0.0099531 plus `CDo`, `Cx` coupled -0.0099088 is `CDi` alone. On the induced
part alone the coupled blade carries 0.45 % less axial force than the rigid one
(-0.0099088 against -0.0099531).

## Findings

- **F1, a defect: a coupled row with the default pproc exports does not
  build.** With the section distribution the route requires and the default
  `[exports]` (the section, sectional-loads, probe and section-Cp kinds are on by
  default), the plan refused the coupled row: `ScriptOrderError:
  UPDATE_ALL_SURFACE_SECTIONS is a analysis command, but the script already
  reached the export phase (EXPORT_SURFACE_SECTIONAL_LOADS at line 3)`. The
  aeroelastic post-processing script exports the structure's sectional loads
  first (`cases/fsi_workspace.py:343-345`, `aeroelastic_post`), and the row's own
  export block then emits `UPDATE_ALL_SURFACE_SECTIONS` again whenever a
  section kind is declared (`cases/workflows.py:11165-11166`, `_export_block`).
  The coupled row ran with those four kinds set to false in its pproc (the
  rigid row kept the defaults), so the coupled point has no row-level
  sectional export and no sections product. The fixed-wing route has the same
  defect (RPT-092).
- **F2: the coupled export carries no viscous drag** (`CDo` 0 against +0.0001225
  rigid), the same observation RPT-089 section 1 made for a steady run; not
  decided here.
- **F3: no rotor table for a `qsteady_rotor` point.** The post skipped
  `polars/P9001-ROTOR_rotor.csv` and `polars/P9002-ROTOR_rotor.csv`: "its record
  states no speed for 'ROTOR'". The quasi-steady average table carries the
  loads; the rotor coefficients (J, CT, CQ, CP, eta) are not written.
- **F4: the completion line is not kept.** The console capture that carried
  "Aeroelastic solver run time" is not among the collected outputs; the
  completion is attested by `pyfs-aeroelastic-stop.log` and the exported log
  ends before it.

## What this does not establish

- One point, one stiffness, alpha 0: no sweep, no mesh or node-count study.
- The sector is solved steady with the rotation in the free stream; its
  agreement with a rotating unsteady blade is RPT-089 section 1 and RPT-093
  fact 5, not re-measured here.
- The coupled axial force differs from the rigid one by less than the viscous
  term the coupled export omits; the aeroelastic effect on thrust at this
  point is therefore small and its sign depends on whether the viscous term is
  counted.
