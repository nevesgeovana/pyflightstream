# FSI with a structural program of your own

An FSI input with `mode = "external"` couples a fixed wing to a structural
program of your own (a finite-element model behind a small wrapper, an in-house
beam code) instead of the package's beam. The row names it as any FSI input,
`FSI: f<id>`, and everything the workspace gives stays: the inputs staged and
hashed, the point named by its row, and every call of your program archived and
checked.

## How a call runs

The new command accepts `--out` for the coupling run directory, for example
`pyfs-fsi external --out point`; it does not accept `--dir`.

The solver's aeroelastic coupling calls the package's step `pyfs-fsi external`
in the point folder at every coupling iteration, and that step:

1. verifies that your program and its declared inputs are the files the plan
   hashed;
2. runs your program in the point folder, with no console window and the
   input's timeout;
3. checks what it wrote: a return code of 0, a displacement file with one row
   per structural node, every value finite;
4. archives the call under `fsi_archive/call_NNNN/` (the loads file, the
   displacement file, your declared outputs and `call.json`, the record of the
   call) and appends one row to `fsi_external_calls.csv`.

A call that fails a check writes `pyfs_fsi_error.log` and returns a nonzero
code. How the solver responds to that code has not been measured.

## The file exchange

It is the exchange the package's own beam uses:

| file | written by | content |
|---|---|---|
| `FS_SurfaceSection_Loads.txt` | the solver, before each call | the section loads of the row's one section distribution over the coupled family |
| `FSIDisp.txt` | your program, at each call | one `dx,dy,dz` row per structural node, in metres, comma separated, in the node file's order |
| the node file | you, once | one `x,y,z` row per node, in metres, in the reference frame |

## The input

```toml
# inputs/fsi/f010.toml
mode = "external"

[external]
executable = "bin/struct_wrapper.exe"   # under inputs/fsi/, hashed by the plan
arguments = []                          # passed after the program's path
structural_nodes = "f010.nodes.txt"     # under inputs/fsi/
inputs = ["f010.model.dat"]             # files it reads, staged in the point folder
outputs = ["struct_log.txt"]            # files it writes per call, archived each call
timeout_s = 3600

[coupling]
families = ["Wing"]                     # the one coupled family
max_iterations = 50                     # a steady row's cap
convergence_threshold = 1.0e-4          # on builds that carry the command
```

The row's pproc declares one section distribution over the coupled family, in a
frame the run creates, as for the package's fixed-wing beam. A steady row ends
at the aeroelastic analysis and runs its exports in the post-processing script;
an unsteady row couples once per time step inside the march.

The point folder receives `fsi-provenance.json`: the digests of the program, the
node file and every declared input, and the route taken.

## What is refused

- A program, node file or declared input that is not a file under
  `inputs/fsi/`; a node file with no node.
- `show_console` (a window per call on your desktop) and `morphing`.
- Any `FSI_*_FACTOR` row key: the package does not know your model's properties.
- A declared input or output named as a file the step owns, in any letter
  case: `call.json`, `fsi_archive`, `fsi_external.json`,
  `fsi_external_calls.csv`, `fsi_external_nodes.csv`,
  `fsi_external_stdout.txt`, `pyfs_fsi_error.log`,
  `FS_SurfaceSection_Loads.txt` and `FSIDisp.txt` (the exchange files are
  archived anyway). The step's record and your program's file would overwrite
  each other, so the input is refused when it is read, the plan refuses it
  with the files it stages, and the step refuses such a manifest before your
  program runs. Names ending in a dot or space are compared as Windows reads
  them: `call.json.` and `call.json` identify the same file and are both refused.
- A run type other than `steady` or `unsteady`; more than one coupled family;
  symmetry copies; a continuation; a geometry that is not a fresh OBJ or STL
  import; a simulation not in metres.
