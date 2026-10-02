# Workspace queries

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
Changed commands identify line numbers and inputs using rebuild's comparison.

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
