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
| manual_ref | The page citation backing the entry |
| versions | Per-version presence, status, and (where they differ) per-version argument grammars |
| default / default_ref | Optional evidence-cited default value of a settings flag |

Per-version statuses and their evidence rules:

| Status | Claim | Evidence required |
|---|---|---|
| documented | The manual says so | `manual_ref` page citation |
| verified | A probe proved it works | Committed compat report |
| broken | A probe proved it fails | Committed compat report |
| removed | The manual says it is gone | `manual_ref` page citation |

The ordered version list in `_meta.yaml` is the only version-ordering
authority (never string or float comparison). Canonical identifiers
use the 26.XXX scheme; display aliases map user-facing forms like
"26.12" to 26.120.

## The run manifest

Every campaign writes `runs.json`, append-only with atomic writes and
duplicate-id rejection. Per run it records: run id, case point,
requested and reported FlightStream version and build, package
version, script and input hashes, the raw-emission flag, status
(CONVERGED, COMPLETED_MAX_ITER, FAILED_EXECUTION, FAILED_SCRIPT,
FAILED_INCOMPLETE_OUTPUT, FAILED_DIVERGED), iterations, residual,
wall time, output paths, error text, and (since the v0.3 line) the
solver-setup provenance snapshot.

The manifest is the sole authority on run identity. Folder and file
names are generated conveniences (templatable for human readability)
and are never parsed back; the absence of any parse-back API is
enforced by a test.

## The workspace

The managed folder tree of a campaign:

```
<root>/
  inputs/            the reusable input-artifact library
    geometries/      geometry files, registered by filename stem
    references/      reference-data artifacts (areas, lengths, moment points, propeller data)
    setups/          named solver-setup presets
    groups/          named boundary groups (labels for aggregation)
    profiles/        input profiles (e.g. actuator loading shapes)
    executables.toml the build-id to executable registry
  sims/sim_<id>/     per-simulation staging, scripts, raw and parsed outputs
  post/              post-processing outputs
  archive/           archived simulations (zip)
  runs.json          the manifest
```

Input artifacts are declarative TOML validated by pydantic, resolved
by stable id with didactic misses (the error lists what exists and
where to put what is missing). The executables registry maps build ids
to paths; an unregistered build runs only through an explicit override
path. Campaign definitions (native TOML or the legacy matrix) compose
cases by referencing artifacts by id, translating the author's legacy
research workflow into validated form.

## Provenance chain

A published result traces back as: coefficient table row -> run id ->
manifest record (hashes, versions, solver-setup snapshot) -> script
(regenerable from the snapshot) -> command database entries (manual
citations and probe reports). Every link is a committed artifact or a
recorded hash; publications cite run ids.
