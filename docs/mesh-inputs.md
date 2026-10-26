<h1>Mesh inputs</h1>

Use the [how-to](mesh/how-to.md), [sidecar reference](mesh/reference.md) or [complete example](mesh/example.md).

<a id="mesh-inputs-and-gui-only-operations"></a>

[Mesh inputs and GUI-only operations](mesh/how-to.md#mesh-inputs-and-gui-only-operations).

<a id="starting-from-an-obj-or-stl"></a>

[Starting from an OBJ or STL](mesh/how-to.md#starting-from-an-obj-or-stl).

<a id="the-surface-names"></a>

[The surface names](mesh/reference.md#the-surface-names).

<a id="the-unit"></a>

[The unit](mesh/reference.md#the-unit).

<a id="explicit-cad-conversion-is-a-separate-route"></a>

[Explicit CAD conversion is a separate route](mesh/reference.md#explicit-cad-conversion-is-a-separate-route).

<a id="a-ccs-file-is-another-route"></a>

[A CCS file is another route](mesh/reference.md#a-ccs-file-is-another-route).

<a id="the-mesh-operations-of-an-import"></a>

[The mesh operations of an import](mesh/reference.md#the-mesh-operations-of-an-import).

<a id="the-boundary-conditions-of-a-raw-mesh"></a>

[The boundary conditions of a raw mesh](mesh/reference.md#the-boundary-conditions-of-a-raw-mesh).

<a id="the-points-file"></a>

[The points file](mesh/reference.md#the-points-file).

<a id="writing-a-points-file-from-a-blades-mesh"></a>

[Writing a points file from a blade's mesh](mesh/how-to.md#writing-a-points-file-from-a-blades-mesh).

<a id="which-build-runs-what-and-what-is-measured"></a>

[Which build runs what, and what is measured](mesh/reference.md#which-build-runs-what-and-what-is-measured).

<a id="a-complete-example-a-wing-obj-with-its-trailing-edge-by-file"></a>

[A complete example: a wing OBJ with its trailing edge by file](mesh/example.md#a-complete-example-a-wing-obj-with-its-trailing-edge-by-file).

<a id="refining-or-coarsening-a-mesh"></a>

[Refining or coarsening a mesh](mesh/how-to.md#refining-or-coarsening-a-mesh).

<a id="the-saved-simulation-gui-once-script-everything-after"></a>

[The saved simulation: GUI once, script everything after](mesh/how-to.md#the-saved-simulation-gui-once-script-everything-after).

<a id="the-gap-this-route-closes"></a>

[The gap this route closes](mesh/how-to.md#the-gap-this-route-closes).

<a id="the-supported-pattern"></a>

[The supported pattern](mesh/how-to.md#the-supported-pattern).

<a id="what-that-content-hash-is-and-what-it-leaves-out"></a>

[What that content hash is: sha256 in `pyflightstream._digest`](mesh/reference.md#what-that-content-hash-is-and-what-it-leaves-out).

<a id="the-boundary-inventory-sidecar"></a>

[The boundary inventory sidecar](mesh/reference.md#the-boundary-inventory-sidecar).

<a id="actions-saved-in-the-geometry-since-0330"></a>

[Actions saved in the geometry](mesh/reference.md#actions-saved-in-the-geometry-since-0330).

<a id="the-refinement-file-and-the-audit"></a>

[The refinement file and the audit](mesh/reference.md#the-refinement-file-and-the-audit).

<a id="mesh-format-policy"></a>

[Mesh format policy](mesh/reference.md#mesh-format-policy).

<a id="the-four-rotor-facts-a-reference-artifact-once-carried"></a>

[The four rotor facts a reference artifact once carried](mesh/reference.md#the-four-rotor-facts-a-reference-artifact-once-carried).

<a id="what-this-policy-is-not"></a>

[What this policy is not](mesh/reference.md#what-this-policy-is-not).

## Matrix geometry in 0.46.0

`GEOMETRY` accepts only a saved simulation (`.fsm`). No flag enables an OBJ
matrix row. Prepare and mark the OBJ once, inspect the saved geometry, and
name the FSM in the matrix:

```text
pyfs-workspace geometry mark-boundaries inputs/geometries/wing.obj --apply
pyfs-matrix plan
```

Marking requires a licensed solver; planning does not run one. Geometry build
keeps its own solver pass. Matrix runs open the saved simulation and never
import a raw mesh or mark its trailing edges or wake-termination nodes.
The row's `BASE_REGIONS` selection on an opened simulation remains supported.

For `wing.fsm`, planning reads the first existing file in this order:

1. `wing.fsm.boundaries.toml`
2. `wing.boundaries.toml`
3. `wing.obj.boundaries.toml`

The plan names the file read. Any `import`, `trailing_edges`,
`wake_termination` or `base_regions` declaration table in that file is
refused with the marking command. When none exists, the inventory read from
the FSM is written to `wing.fsm.boundaries.toml`.

If `wing.mark.json` exists, planning compares every recorded input digest.
A changed or missing mesh, declaration sidecar or points file is refused by
name; repeat marking with `--apply --overwrite`. An FSM with no marking
record is accepted, including one prepared in the GUI. A row's `FS_BUILD`
different from the record's `fs_build` produces one campaign warning listing
all affected rows. It does not prevent planning.



FSI rows retain raw OBJ imports because coupling requires the mesh at each import.
They read `<mesh>.obj.boundaries.toml` with the same strict named declarations as
`mark-boundaries` and use its D3 emitter and VERIFIED command gate at each import.
Every other matrix row requires an `.fsm`; prepare it once with
`pyfs-workspace geometry mark-boundaries <mesh>.obj --apply`.

## Boundary marking from Python

**Experimental**: the five boundary-marking names exported by
`pyflightstream.workspace` may change without a deprecation window. Use them
to preview a marking pass or connect it to an explicit solver runner.
They use the same declarations and evidence gates as the CLI.

- `plan_mark_boundaries(mesh, *, registry=None)` reads the OBJ and its boundary
  sidecar and returns a `BoundaryMarkingPlan` without writing files or running
  a solver. Inspect `script`, `steps`, `outputs` and `awaiting_evidence`.
- `refuse_mark_boundaries(plan, *, overwrite)` checks command evidence, input
  digests and output collisions before execution. Invalid inputs or unavailable
  evidence raise `InputArtifactError`.
- `apply_mark_boundaries(plan, *, runner, overwrite=False, package_version="unknown")`
  runs the supplied callback and returns the marking record after saved-state
  read-back and promotion. `BoundaryMarkingError` reports execution, read-back
  or publication failures. Inspect the staging directory named in the error.

This solver-free example creates a minimal input with an explicit no-edge
declaration and inspects its preview:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from pyflightstream.workspace import plan_mark_boundaries, refuse_mark_boundaries
from pyflightstream.workspace.sidecars import write_inventory

with TemporaryDirectory() as folder:
    mesh = Path(folder) / "wing.obj"
    mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng Wing\nf 1 2 3\n")
    sidecar = write_inventory(mesh)
    with sidecar.open("a") as stream:
        stream.write('\nfs_build = "26.125"\n[import]\nunits = "METER"\n')
        stream.write("[trailing_edges]\nnone = true\n")
    plan = plan_mark_boundaries(mesh)
    refuse_mark_boundaries(plan, overwrite=False)
    assert plan.outputs[0] == mesh.with_suffix(".fsm")
    assert not plan.work.exists()
```

Applying requires a licensed solver. The caller supplies `runner(script_path,
working_directory)`, which executes the script using the declared build and
returns an outcome with `log`, `failed`, `diagnosis`, `executable`, `return_code`
and `wall_s` attributes. On success, the saved FSM and log must be in the
working directory. The callback is the execution boundary; this API does not
select or launch an executable on its own.

For an existing declared OBJ and a configured callback:

<!-- skip: next -->
```python
from pyflightstream.workspace import apply_mark_boundaries, plan_mark_boundaries

plan = plan_mark_boundaries("inputs/geometries/wing.obj")
record = apply_mark_boundaries(plan, runner=runner, package_version="0.46.0")
```

The five promoted outputs are the FSM, its `.fsm.boundaries.toml` inventory,
the `.mark.txt` script, `.mark.log` and `.mark.json` record. Set
`overwrite=True` only when replacing an existing saved simulation is intended.
Planning and fixture tests do not establish solver or physical validity.
