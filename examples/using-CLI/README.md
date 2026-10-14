# Four classic cases through the command line

| Workspace | What it plans |
|---|---|
| `steady-wing-polar/` | A synthetic NACA 0012 wing at 0, 2 and 4 degrees |
| `unsteady-isolated-propeller/` | An isolated two-blade propeller, three revolutions at 10 degrees per step |
| `quasi-steady-rotor/` | The same propeller and operating point in the rotating steady frame |
| `mesh-refinement-campaign/` | The same wing at 2 degrees on two mesh densities |

Install pyflightstream, then copy a workspace directory to a writable location.
From the repository root, prepare its synthetic geometry and plan it first:

```text
python examples/using-CLI/prepare.py <copied-workspace>
pyfs-matrix plan <copied-workspace>/matrix.fs --workspace <copied-workspace>
```

Repeat these two commands for any of the four directories. Preparation and
planning use no solver or license. The committed inputs are text; the meshes
are generated locally from analytic wing and blade definitions. `p001` is the
post-processing input. `inputs/executables.toml` contains a placeholder, which
the plan can bind without launching it.

For a licensed run, set that table's 26.124 path to the installed executable,
plan again, then run and post:

```text
pyfs-matrix run <copied-workspace>/matrix.fs --workspace <copied-workspace>
pyfs-matrix post --workspace <copied-workspace>
```

The refinement campaign holds geometry, incidence and solver settings fixed.
Its second mesh doubles both chordwise and spanwise panel counts. Compare its
loads with the coarse row after running; two densities alone do not establish
mesh convergence. `pyfs-workspace geometry refine` is the separate route for
refining an existing mesh; see the site's geometry guide.

The rotor discretization is deliberately small. Three revolutions and a
10-degree step demonstrate the workflow, not a converged wake. The quasi-steady
plan reports its reduced-frequency warning; a ready plan is not an accuracy claim.

The matching [Python examples](../using-API/README.md) use these same matrices
and inputs through the public API. Capability-specific examples live on the
[documentation](../../docs/index.md).
