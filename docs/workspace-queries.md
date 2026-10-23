# Workspace queries

The query verbs of `pyfs-matrix` are `status`, `show`, `log`, `trace`, `history` and `diff`; each writes nothing.

`pyfs-matrix status --workspace campaign` prints one row per polar, a polar
being one simulation and its sweep. A row states the simulation id,
the polar name, the swept variable, the datapoints as recorded over planned,
the matrix and the status. When every datapoint of the polar has the same
status the row states that word; a mixed polar states the count of each word.
Rows are ordered by matrix and then by simulation id taken as a number.
`--sims` (with or without square brackets), `--matrix`, `--status WORD`
(repeatable) and `--failed` narrow the rows, `--points` prints one row per
datapoint, and `--json` (schema `pyfs-status/1`) and `--csv` print the same
rows for a script. Each datapoint is counted once, by its
effective record: a run that was continued is not counted again.

A point that a plan names and that no record carries is counted with the
status `planned`, written in lower case because it is derived and never a
recorded word. A footer states, for each matrix, whether its plan was made from
the matrix as it is on disk and whether its post indexes every recorded run and
is complete. Recorded words are printed as recorded.
`RAN_MISSING_LOG`, a run that ended with its outputs and whose solver
log is absent, is counted among the runs that ended and apart from
`CONVERGED`; `show` prints its `residual_note`, which names what the absent log
would have carried.
`MAX_ITER_REACHED`, a steady point stopped at the iteration limit its
run requested without its residual settling, is likewise an ended run that is
not a failure, counted apart from `CONVERGED`; `show` prints the limit and the
iterations reached, from its `residual_note`, and its record carries
`iterations` and `iterations_requested`. `COMPLETED_MAX_ITER` stays the status
of an unsteady run that ended its time loop and of a steady point whose
evidence does not show both the counter at the limit and the unsettled
residual.
`status --additional` lists the additional runs register with its recorded
fields and no derived one.

`show` prints the record of one datapoint, taken from a simulation
id and a point, a run id or its alias, outcome first: the status, the verdict
a `mark-failed` or a `mark-converged` gave (with its reason), the warnings and the stopping reason, then the evidence
files with their last lines, the log entries that name the point, the chain of
the run it continues and the run that continued it, the identity of the
package, build and script, and the inputs. A coupled point also names
its coupling records, the files it lacks and its last exchange row. The output
ends with the full resolved record.

`log` prints the activity log oldest first, filtered by `--sims`,
`--run`, `--stage` and `--since`; `--problems` keeps the events with a problem,
`--open` lists the stages that started and have no finish, and `--post MATRIX`
prints the post log grouped by category, product family and message shape with
a count and one example each, as `--pproc-warnings` groups it.
`log --storage` lists the storage calls as they were recorded.
Torn or malformed activity lines and non-ISO timestamps are named in a warning
and skipped; the remaining events are still shown.

`trace PRODUCT` prints, from the post's products index, the
simulation, post options and runs a product holds, with the identity of each
run and the paths of its provenance document and sidecar; `trace --run RUN_ID`
prints the provenance document as a tree of inputs, script and outputs with
their digests.

Every query verb writes no file and takes no lock.

`pyfs-matrix history 2006 --workspace campaign` prints the recorded attempts
of simulation 2006. A point name or a full run id narrows the selection.
Each row keeps its source, archive stamp, status and continuation link.
Present records, archived manifests and record documents in datapoint archives
remain distinguishable. Identical records in different sources remain separate
history rows.

`pyfs-matrix diff sample/sim_2006/A0@20261001-120000 sample/sim_2006/A0 --workspace campaign`
compares an archived run with its current record. A stamp includes a collision
suffix when the archive has one. An absent or ambiguous selector is an error.
The comparison reports changed fields, including versions, digests, solver flags,
flight condition and outcome. Scripts are compared only when their bytes match
the recorded digest; missing or replaced scripts are reported as unavailable.
Each script is normalized against its own execution root. Changed commands
identify line numbers and the `a` and `b` sides; the diff does not attribute
historical changes to the inputs currently on disk.

Both verbs accept `--json`, `--csv` and `--runs NAME`. Their JSON documents
include a schema, workspace, read time, source modification times and rows.
They read simulations in `sims/batch/<matrix>_b<ID>/sim_<id>/` while a batch runs
and in `sims/sim_<id>/` after collection. Compacted archives stay compacted.
Queries write no files and take no manifest lock.

Python callers use `pyflightstream.workspace.ledger`. `status_rows`, `point_rows`,
`point_card`, `activity_rows`, `post_log_groups`, `trace_product`, `history`, `diff`
and `additional_rows` return plain data accepted by `json.dumps`. Passing a
`read_ledger(root)` snapshot lets several queries share the same present records.
Historical queries inspect archives separately. Status and point cards never
merge archives into the present state.

This small example runs without a campaign or pandas:

```python
import json
from tempfile import TemporaryDirectory
from pyflightstream.workspace.ledger import status_rows

with TemporaryDirectory() as root:
    assert json.dumps(status_rows(root)) == "[]"
```

History returns exit code 1 when its target has no recorded run. Invalid
arguments or an unusable manifest return 2. A successful diff returns 0 whether
or not fields differ. Diagnostics go to stderr so machine output stays parseable.
