# Migrating to 0.36.0

> Frozen record: not edited after its release.

A workspace using 0.35.1 needs no changes to its inputs. This release
reorganises the implementation and documentation, keeps the public Python
paths, and corrects the grouped-plan exclusion described below.

## Coupled steady rows stay out of grouped jobs (FR-410)

`plan --batch` and `plan --polar-sweep` leave coupled `steady` and
`qsteady_rotor` rows out, naming each row in the plan and its receipt. The
0.35.1 notes stated this exclusion, but its code planned those rows into jobs.
The reason now reads:

> a coupled row on steady or qsteady_rotor: its coupling loop starts only after the script ends, and on 26.124 the next point of the job crashed the instance (RPT-150)

RPT-150 measured the steady case; the `qsteady_rotor` exclusion is inferred
from the shared coupling mechanism, not separately measured. Use the
per-point run mode for these rows. Coupled `unsteady` rows still join grouped
jobs, and coupling on `unsteady_rotor` remains refused (FR-407).

## Grouped-plan notes and help

The plan always prints the acoustic-isolation note when it groups acoustic
polars, naming every acoustic polar that runs in a job of its own with all
its points together (FR-406). The note no longer depends on the requested
job count. The grouping itself is unchanged.

The `--batch` and `--polar-sweep` help now states that `RESTART` and `LEGACY`
rows are left out and that the plan names each excluded row (FR-362 R2).
The per-job warning also names the resolving folder for `COMMAND_LINE`
actions when no relative `SCRIPT` action accompanies them (FR-405). Relative
paths in those commands resolve in the job's folder.

See [Planning and cost](workflow-plan-and-cost.md) for grouped-run options
and limits.

## Public Python names and the reset vocabulary

Keep importing public classes from their public modules. Because a moved
class reports its public module, `inspect.getsource` on it looks in that
module and, on Python 3.12, cannot find the definition; read the defining
module instead (`pyflightstream.workspace.manifest`,
`pyflightstream.workspace._layout`, `pyflightstream.cases._matrix_layouts`,
`pyflightstream.workspace._matrix_binding`). The structural
cuts preserve their `__module__` and pickle identity as well as their import
paths: workspace record classes and `WorkspaceError` remain in
`pyflightstream.workspace`, `ResolvedMatrix` in
`pyflightstream.workspace.matrix`, and `MatrixError` in
`pyflightstream.cases.matrix` (AD-15, NFR-40). The workspace, matrix, run and
post cuts require no caller changes (AD-19, AD-20, AD-21, AD-22, AD-23).

`pyflightstream.versions.SETUP_RESET_LOG_PREFIXES` is a new public, read-only
mapping of solver-version identifiers to the two log prefixes surrounding a
setup reset, for the setup-reset split of a grouped job's log
(FR-407; 0.35.1 review row P1-ARCH-Q4). Its `26.124` entry is
`("Solver mode:", "Symmetry is ")`. The log reader consults this shared
vocabulary to keep a reset between two initializations inside the same
point's log segment. A build without an entry, or a log without build
identity, uses the newest registered entry. Treat the mapping as reference
data; assigning an entry raises `TypeError`.

The Python API reference now shows each public module's maturity level from
one table: `stable`, `provisional`, `experimental` or `internal` (FR-409).
See the Python API section of the documentation menu.

## Finding the documentation and earlier migration records

Documentation topics now have one defining home, with links from the other
pages (NFR-33). [Post-processing definitions](post-processing-definitions.md)
is an index into pages by family, retaining all 53 old heading anchors
(NFR-34). [Mesh inputs](mesh-inputs.md) links to separate how-to, reference
and example pages, retaining all 21 old heading anchors (NFR-35). Existing
links to both original pages and every old anchor still resolve.

Reference pages state the current contract; version history lives in the
migration records (NFR-36). The [Upgrading index](upgrading.md) lists every
migration page, and each release record carries its frozen-record banner
(NFR-37). Use that index for the releases between the version you have and
the version you are adopting.
