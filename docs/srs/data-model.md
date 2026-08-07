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
| versions | Per-version presence, status, and (where they differ) per-version argument grammars |
| default / default_ref | Optional evidence-cited default value of a settings flag |

### What an argument declares, and when it must

An argument specification carries its type, its unit and its allowed
tokens. Three further fields exist because the emitter would otherwise
decide a PER-COMMAND fact by a per-family rule or by guessing from the
argument's name. Each was added after that guess was measured wrong.

| Field | Declare it when |
|---|---|
| `cites` | The argument is a 1-based index into one of the entity kinds the script builder tracks (local coordinate systems, actuators, motions, mesh boundaries) AND its name is not one the emitter already resolves database-wide. Declaring it is what makes a declared label resolve and an out-of-range index refuse. |
| `all_sentinel` | The command's page states a value that selects EVERY entity of that kind. Absent means the page states none, and the emitter then refuses every non-positive index. It requires `cites`, since a sentinel is only ever read where the entity kind is known. |
| `fixed_length` | The manual fixes how many values a list takes and no count argument precedes it. A short payload otherwise makes the solver read the next command as data. |

The chapter files mirror each manual page's own argument names rather
than harmonising them, so that an argument list still matches the page
beside it. `cites` is what makes that affordable: the emitter resolves
by declaration first and by name only as a fallback, so a chapter may
spell one thing four ways without the checking becoming four different
behaviours. A name that means DIFFERENT things in different chapters,
as `index` does, can only ever be declared.

Forgetting is not silent. A tier 1 guard fails on any index argument
whose name says it cites something and that resolves to nothing;
indices of objects the builder does not track (CAD bodies and curves,
sections, separations, trailing edges) are listed there by name.

Per-version statuses and their evidence rules:

| Status | Claim | Evidence required |
|---|---|---|
| documented | The manual says so, or a probe measured the solver accepting a command no edition documents | `manual_ref` page citation, or `probe_ref` naming a committed report |
| verified | A probe proved it works | Committed compat report |
| broken | A probe proved it fails | Committed compat report |
| removed | The manual says it is gone | `manual_ref` page citation |

The ordered version list in `_meta.yaml` is the only version-ordering
authority (never string or float comparison). Canonical identifiers
use the 26.XXX scheme; display aliases record the vendor release name
of each build and resolve only where that name identifies exactly one
build (FR-02c).

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
path. Campaign definitions (native TOML or the run matrix) compose
cases by referencing artifacts by id, translating the author's
research workflow into validated form.

## Provenance chain

A published result traces back as: coefficient table row -> run id ->
manifest record (hashes, versions, solver-setup snapshot) -> script
(regenerable from the snapshot) -> command database entries (each citing a
manual page or a committed probe report). Every link is a committed artifact or a
recorded hash; publications cite run ids.
