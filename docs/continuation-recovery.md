# Recovering a historical continuation frame

A stopped run recorded before 0.28.0 can lack the analysis loads-frame
placement needed to translate its surface VTK into Tecplot. A RESTART row
now rehearses the original named workflow or supplied Python recipe offline.
The planner and runner use the same check before archiving the stopped point.

Recovery requires the recorded original script and its SHA256, the saved
simulation and its SHA256, every recorded native input identity and hash,
the same point, recipe and FlightStream version, and the same native
scientific commands. Comments and output serialization are excluded from
the command comparison: 0.27 used native Tecplot, while current releases
translate VTK. Frame placement and loads-frame selection remain compared.

A changed row reports the first differing native command or argument.
Changed or missing files identify the failed evidence. An ambiguous frame,
an unplaced restart chain, or unverifiable child-script/FSI dependencies
remain refused. Unit or placement corrections are never silently applied
to an old saved state. Restore the original evidence, or disable Tecplot
under the pproc artifact's exports table if that surface is not needed.

No solver is launched by recovery. Historical manifest frame metadata is
left unchanged. The new run stores the recovered frame and its proof under
surface_translations[].frame_recovery. Records that already contain a frame,
and continuations without Tecplot, retain their existing route.

## Executable offline example

[continuation_frame_recovery.py](examples/continuation_frame_recovery.md)
accepts an existing workspace, a resolved SimCase JSON, a point and a build.
It does not initialize a workspace or submit a solver. Save the resolved case
with case.model_dump_json(); the JSON must retain its RESTART request.

From the checkout, use Python to avoid shell-specific JSON quoting:

<!-- skip: next -->
```python
from examples.continuation_frame_recovery import main

main([
    "campaign", "resolved-case.json",
    "--point", '{"alpha": 0.0}',
    "--fs-version", "26.123",
])
```

The example prints the resolved saved state and recovery evidence. Its same
entry point is exercised by test_g58_documented_example_executes_without_a_solver.
For handwritten recipes, call resolve_continuation with the actual recipe
callable, as the normal campaign runner does.

## What a RESTART row continues (0.33.0)

A row stating `RESTART` continues, point by point, the latest recorded run
of each point (FR-96):

| latest run of the point | `{FINISH_PENDING}` | `{ADDITIONAL_ITERS=n}`, `{ADDITIONAL_REVS=n}` |
|---|---|---|
| stopped by its wall clock (`WALLTIME_REACHED`) | continued by the steps the row still owes | continued by n steps or n revolutions |
| at its iteration cap (`COMPLETED_MAX_ITER`) | refused: nothing records where it stopped | continued |
| `CONVERGED`, run type `unsteady` or `unsteady_rotor` | not run: nothing is pending | continued |
| `CONVERGED`, any other run type | not run: nothing to march | not run: nothing to march |
| a completed continuation of the same request | not run | not run: already continued |
| `SUBMITTED` | not run: collect it first | not run: collect it first |
| failed, or no run recorded | refused by name | refused by name |

**A converged march is continued, once per request.** For an unsteady run,
`CONVERGED` is the residual test at the last time step; an average may still
need more revolutions, and `{ADDITIONAL_REVS=n}` marches them from the saved
simulation instead of running the point again from the mesh. A revolution is
counted on the row's own clock, read from the record. The continuation's
record states the request it answered under `restart`, so running the matrix
again with the same request continues nothing more (the plan and the run say
`already continued by ADDITIONAL_REVS=1`); write another number to march
further. A continuation recorded before 0.33.0 states no request and is read
off the steps it marched: it answered the request the row carries now when
that request asks the same steps of the run it continues, so running the same
matrix again adds nothing, and a changed number continues it as it continues
any other continuation.

**Every point that is not continued is said.** `pyfs-matrix plan` lists each
point of a RESTART row under `Continuations (RESTART)`, with what the
continuation does (`continuing a CONVERGED unsteady run, <run id>, by 1
revolution(s)`) or why it is not run, and `pyfs-matrix run` prints a `not run`
line for each point it does not continue.

**The average covers the end of the whole march.** The post joins the plots
history of the run and of each continuation, and every averaging window of the
point ends at the last step of the march; see
[the averaging window](post-processing-definitions.md#the-averaging-window).
