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
| default / default_ref | Optional evidence-cited default value of a settings flag |

### A per-version grammar states its difference

Amended 2026-08-10. A version row's `args` used to replace the
entry-level argument list outright, so a row changing one field of one
argument had to restate every other field of every argument. An
override now inherits, per argument matched by NAME, every field it does
not itself write.

The reason is measured rather than aesthetic. Restating a whole argument
to change one flag is how a second flag changes by accident: writing
nineteen overrides in one pass lost a list separator and an entity
citation, which is the same defect a test in this repository already
named as the one this family had produced. A later measurement found the
mechanism covers four kinds of field and only two were guarded, and that
dropping two of the four changed what one command emits on two builds
without failing a single test.

Inheritance reads the RAW file, because that is the only place where
"the row did not write this" is observable: on a parsed model an omitted
field and one set to its default are the same value. Writing any field
as null therefore clears it rather than inheriting it, and an argument
whose name the entry-level list does not carry is taken exactly as
written, so a row may still state a different argument SET.

What a version row still cannot override is the LAYOUT. Ten readings
across four commands are withheld for that reason rather than recorded
in a shape that would emit the newer form under the older edition's
citation (`PLN-20260810-1200`).

### What an argument declares, and when it must

An argument specification carries its type, its unit and its allowed
tokens. Four further fields exist because the emitter would otherwise
decide a PER-COMMAND fact by a per-family rule or by guessing from the
argument's name. Each was added after that guess was measured wrong.

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

**Read that last clause strictly: there is ONE mechanism, and this
document used to describe two.** Until v0.5.0 the emitter resolved by
declaration first and fell back to matching the argument's NAME against
two hardcoded lists, and this page said so. The fallback is deleted. A
name that means different things in different chapters, as `index`
does, was never resolvable by name anyway, and the arrangement's real
cost was that an entry could be right by accident: an argument called
`frame_index` cited a coordinate system with nothing in its own row
saying so, so a chapter renaming it to match its page silently stopped
being checked. Declaring is now the only way, and the declaration is
visible in the row a reader is already looking at.

Forgetting is not silent, but the guard is a heuristic and is worth
knowing as one. A tier 1 test fails on any index argument whose NAME
says it cites something and that declares nothing; indices of objects
the builder does not track (CAD bodies and curves, sections,
separations, trailing edges) are listed there by name. An argument that
cites something and is named in a way the heuristic does not recognise
is exactly what the guard cannot see.

### A chapter enters for every registered version at once

Read the chapter in every registered edition that carries it, in the
same pass, and give each entry a row per edition that documents it, with
that edition's own page. Record which editions do not carry the chapter
at all, because some do not: the February 2026 edition has no
Aeroelastic Coupling Toolbox, so for that chapter three editions are the
whole of it.

This is cheaper than it sounds, because the pages are open anyway, and
it is the only way the per-version grammar differences get found: the
February 2026 build is the one that renames things (EUCLIDEAN rather
than ROTARY, two arguments rather than three), so a chapter entered
from the newest manual alone records a grammar the older builds do not
accept and refuses commands their manuals document.

The rule was adopted on 2026-08-08 after the reverse was measured. The
database was built forward from 26.120, the only registered version for
most of its life, and the two earlier builds were registered later
without a backward sweep, leaving a residual of entries that are
documented in an edition they carry no row for. That residual drains as
the sweep reaches each chapter rather than being attacked on its own, so
it falls without a separate task, and leaving it to fall is only correct
for as long as new chapters keep arriving this way.

The count is the database's own fact and its home is the CHANGELOG
entry, not this page, for the same reason the count of entered commands
is: a number designed to reach zero is the worst candidate for
restating.

Per-version statuses and their evidence rules:

| Status | Claim | Evidence required |
|---|---|---|
| documented | The manual says so, or a probe measured the solver accepting a command no edition documents | `manual_ref` page citation, or `probe_ref` naming a committed report |
| verified | A probe proved it works | Committed compat report |
| broken | A probe proved it fails | Committed compat report |
| removed | The build does not carry the command, and the row says which of three things happened | A note, always, plus `probe_ref` naming a committed report when the note claims a MEASUREMENT |

`removed` is the one status with three provenances, and the row is
required to say which because they are not equally strong. An edition
may STATE the withdrawal; an edition may simply STOP PRINTING the
command, which is a fact about a document and not about the solver; or
a probe may MEASURE the solver refusing the name, which is the only one
of the three that observes the solver at all. The first two cite a
manual page in the note. The third cites its run, and cites it through
`probe_ref` rather than `report` because the probe harness has no
`removed` outcome to write: a build that lacks a command records as
`broken`, which is a claim about a command that is present. So a
measured removal is a run a human wrote down, and the field says so.

The same field name appears on an ENTRY and on a VERSION ROW and they
are not the same admissibility. On an entry it is the alternative to
`manual_ref` for a command the solver accepts and no edition documents.
On a version row it is admissible for `removed` alone, and the loader
refuses it on any other status, because `verified` and `broken` must
stay checkable against the compat yaml the harness wrote; a guard whose
population quietly shrinks reports green either way. Both go away when
the harness learns the outcome
(`PLN-20260809-0300-the-harness-has-no-removed-outcome`).

The ordered version list in `_meta.yaml` is the only version-ordering
authority (never string or float comparison). Canonical identifiers
use the YY.XXX scheme; display aliases record the vendor release name
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
