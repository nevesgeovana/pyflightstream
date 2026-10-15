# Data and evidence model

Three data structures anchor the package: the command database (what
the solver accepts), the run manifest (what actually happened), and
the workspace (where everything lives). Each is the single authority
over its domain.

## The command database

A set of YAML files, one per manual chapter, loaded into a validated
registry (pydantic models).

Each command entry records:

| Field | Meaning |
|---|---|
| name | The literal script command token |
| layout | The emission grammar (inline, keyword block, parameter lines, ...) |
| phase | The pipeline phase (geometry, setup, init, exec, analysis, export, control) enforced at build time |
| args | Typed argument specifications, with enums and optional flags |
| manual_ref | The manual page citation backing the entry; exclusive with `probe_ref` |
| probe_ref | A committed probe report backing an entry no manual edition documents; exclusive with `manual_ref` |
| versions | Per-version presence, status, and (where they differ) per-version argument grammars, each stating its DIFFERENCE from the entry-level grammar rather than replacing it |
| default / default_ref | Optional evidence-cited default value of a settings flag, including an empty boundary selection, a default that emits no line |

### A per-version grammar states its difference

A version row's `args` inherits, per argument matched by NAME, every
entry-level field it does not itself write.

A version override states only the fields it changes. This preserves the
other grammar fields, including separators and entity citations, without
duplicating them in each version row.

Inheritance reads the RAW file, because that is the only place where
"the row did not write this" is observable: on a parsed model an omitted
field and one set to its default are the same value. Writing any field
as null therefore clears it rather than inheriting it, and an argument
whose name the entry-level list does not carry is taken exactly as
written, so a row may still state a different argument SET.

What a version row still cannot override is the LAYOUT. Ten readings
across four commands are withheld for that reason rather than recorded
in a shape that would emit the newer form under the older edition's
citation.

### What an argument declares, and when it must

An argument specification carries its type, its unit and its allowed
tokens. Four further fields exist because the emitter would otherwise
decide a PER-COMMAND fact by a per-family rule or by guessing from the
argument's name. Each field states the command-specific contract explicitly.

**`values` is the accepted vocabulary**: everything the manual page
says the solver takes for that argument, in every spelling the page
states or samples. The vocabulary describes what the solver accepts:
the emitter reads `values` to REFUSE, and a refusal of a
token the solver accepts is a false refusal with a page citation
beside it. A narrowing this library chooses to offer (a helper that
exposes three of six spellings, say) belongs to the helper and its
docstring, never to `values`; should such a narrowing ever need to be
data, its field is `offered`, and no entry has needed one. The axis
family is the measured case: six arguments whose page states or
samples the index form list `X, Y, Z, "1", "2", "3"`, ten whose page
names the letters alone list the letters, and
the verification suite pins every member of
both halves. An integer passed where the digit is accepted is printed
as that digit.

| Field | Declare it when |
|---|---|
| `cites` | The argument is a 1-based index into one of the entity kinds the script builder tracks (local coordinate systems, actuators, motions, mesh boundaries). Declaring it is what makes a declared label resolve and an out-of-range index refuse. |
| `all_sentinel` | The command's page states a value that selects EVERY entity of that kind. Absent means the page states none, and the emitter then refuses every non-positive index. It requires `cites`, since a sentinel is only ever read where the entity kind is known. |
| `fixed_length` | The manual fixes how many values a list takes and no count argument precedes it. A short payload otherwise makes the solver read the next command as data. |
| `on_command_line` | The command's layout is `keyword_block` and this one argument is written on the COMMAND line rather than on a keyword line of its own. The `on_command_line` arguments must be the LEADING ones, in a run from the first, since the command line is written before any keyword line and cannot be appended to afterwards; and each must be required, since the line is positional and unnamed, so an omitted argument would shift the ones after it into its place and the solver would read a well-formed line meaning something else. |

The chapter files mirror each manual page's own argument names rather
than harmonising them, so that an argument list still matches the page
beside it. `cites` is what makes that affordable: a chapter may spell
one thing four ways and the checking stays one behaviour, because the
emitter reads the declaration and nothing else.

**There is one entity-resolution mechanism: the argument declaration.** An argument name alone never selects an entity kind; the declaration is visible in its command-database row. See [the migration record](../upgrading.md#older-layouts) for the historical behaviour.

Forgetting is not silent, but the guard is a heuristic and is worth
knowing as one. A tier 1 test fails on any index argument whose NAME
says it cites something and that declares nothing; indices of objects
the builder does not track (CAD bodies and curves, sections,
separations, trailing edges) are listed there by name. An argument that
cites something and is named in a way the heuristic does not recognise
is exactly what the guard cannot see.

### Build registration and rowless entries

The ordered registry in `commands/_meta.yaml` decides whether a registered
build inherits its base release's evidence. `CommandEntry.evidence_in` first
uses a direct version row; only a registry-approved inheriting build may fall
back to its base row. A rowless entry is therefore not universally available.
The returned evidence identifies whether it was inherited and its source.
A build that inherits nothing needs direct rows from its own documentation or
probes. A caller-created version object cannot grant inheritance to itself.

Manual registration compares editions before carrying documented rows forward.
It does not promote them to verified; that requires probe evidence.

Per-version statuses and their evidence rules:

| Status | Claim | Evidence required |
|---|---|---|
| documented | The manual says so, or a probe measured the solver accepting a command no edition documents | `manual_ref` page citation, or `probe_ref` naming a committed report |
| verified | A probe proved it works | Committed compat report |
| broken | A probe proved it fails | Committed compat report |
| removed | The build does not carry the command, and the row says which of three things happened | A note, always, plus a run citation when the note claims a MEASUREMENT: `report` naming the compat yaml when the harness promoted it, or `probe_ref` naming a narrative report for the removals recorded before the harness could measure one |

`removed` is the one status with three provenances, and the row is
required to say which because they are not equally strong. An edition
may STATE the withdrawal; an edition may simply STOP PRINTING the
command, which is a fact about a document and not about the solver; or
a probe may MEASURE the solver refusing the name, which is the only one
of the three that observes the solver at all. The first two cite a
manual page in the note. The third cites its run.

The harness recognizes a removed command from the solver's refusal of
the name. `pyfs-qa apply-compat` promotes that outcome and cites the
compat yaml through `report`. Historical measured-removal rows may cite
a narrative report through `probe_ref`; both citation fields are read.

Both fields are read wherever a measured removal is shown, and that is
load bearing rather than defensive: the refusal message and the
compatibility reference each fall back to the ENTRY's citation when a
row has no run of its own, and the entry cites a page of an edition
that documents the command. Reading only one field would print that
page beside a sentence saying the solver refused the name.

The same field name appears on an ENTRY and on a VERSION ROW and they
are not the same admissibility. On an entry it is the alternative to
`manual_ref` for a command the solver accepts and no edition documents.
On a version row it is admissible for `removed` alone, and the loader
refuses it on any other status, because `verified` and `broken` must
stay checkable against the compat yaml the harness wrote; a guard whose
population quietly shrinks reports green either way. The version-row
field serves historical measured-removal reports until those rows are
re-probed. An edition that stops printing a command cites pages in its
note, not a solver run.

The ordered version list in `_meta.yaml` is the only version-ordering
authority (never string or float comparison). Canonical identifiers
use the YY.XXX scheme; display aliases record the vendor release name
of each build and resolve only where that name identifies exactly one
build.

## The run manifest

The current `runs.json` is a schema-version-4 document owned by
`workspace.record_document`. Its `runs` entries refer to immutable shared
`solver_setups`, `frames` and `geometries` definitions. Output paths and hashes
are paired in artifact entries. `decode_document` resolves the in-memory
records without consulting current input files, preserving historical facts.

`workspace.manifest` owns record mutation under the manifest lease. New-run
append rejects duplicate ids; collect, marking, sync and storage operations
may replace records. One status transition makes one manifest replacement.
The document is not append-only. Requested and reported solver identity,
scientific outputs, provenance, recovery history and distinct times remain
separate even when their values happen to be equal.

Ordinary readers refuse older formats and name the explicit workspace migration
command. [Upgrading](../upgrading.md) is the home of migration instructions.

A run whose script imports trailing edges from a file is also held to
the solver's own count: the log's imported edges must equal the points
the script wrote, or the run is recorded FAILED_SCRIPT, and with no
solver log read it is recorded FAILED_INCOMPLETE_OUTPUT. The node file
the run wrote for the import is among the input hashes.

The manifest is the authority on recorded run identity. Normal operation
uses its records rather than deriving provenance from names. Recovery is a
deliberate exception: rebuild parses `sim_<id>` folder names to find candidate
simulations, then validates the recovered script and evidence. A folder name
alone cannot establish a run's inputs or convergence.

## The workspace

The managed folder tree of a campaign:

```
<root>/
  inputs/            the reusable input-artifact library
    geometries/      geometry files, registered by filename stem, flat or one folder per geometry
      30_WB/         the recommended form: the geometry file,
                     its boundary inventory and its provenance record in one place;
                     GEOMETRY: 30_WB.fsm reads the folder first and the flat file second
    references/      reference-data artifacts (areas, lengths, moment points, rotor data)
    setups/          named solver-setup presets
    pproc/           post-processing artifacts (named boundary groups and the product tables)
    profiles/        input profiles (e.g. actuator loading shapes)
    freestreams/     custom free-stream fields a row's FREESTREAM names: <stem>.txt or <stem>.dat
    calibrations/    quasi-steady wheel calibrations a pproc's [qsteady_correction] names: <id>.toml
    hpc/             how a cluster is asked to run a job; read on Linux
    fsi/             structural configurations a row's FSI names: f<id>.toml
    matrices/        run matrices kept inside the library; new files go here, and a
                     matrix at the workspace root keeps its location
    management/      storage recipes a `pyfs-matrix free-space` call runs: m<id>.toml
    sync-workspaces.toml  the other workspaces `pyfs-matrix sync` brings runs and results from
    executables.toml the build-id to executable registry, with an
                     optional declared version per build
  pyfs.toml          shared workspace defaults
  pyfs.local.toml    machine-local overrides
  logs/              operation logs
  sims/batch/        grouped-job scripts and receipts
  sims/sim_<id>/     per-simulation staged inputs, scripts and raw outputs
  post/              post-processing outputs
  archive/           archived simulations (zip)
  runs.json          the manifest
  storage_management.json  the record of every storage and sync call
```

Optional operation-specific inputs also live under `inputs/costs/` (machine
cost models) and `inputs/sixdof/` (declared rigid-body motion). These directories
are read when requested; workspace initialization does not create them.

Input artifacts are declarative TOML validated by pydantic, resolved
by stable id with didactic misses (the error lists what exists and
where to put what is missing). The executables registry maps build ids
to paths; an unregistered build runs only through an explicit override
path. Run matrices compose cases by referencing artifacts by id. The ordinary
Python case APIs remain available; authored campaign files are not a second
declaration route.

## Provenance chain

A published result traces back as: coefficient table row -> run id ->
manifest record (hashes, versions, solver-setup snapshot) -> script
(regenerable from the snapshot) -> command database entries (each citing a
manual page or a committed probe report). Every link is a committed artifact or a
recorded hash; publications cite run ids.
