# RPT-034: a weight budget for a mesh reader, and the three candidates measured against it

Date: 2026-08-19. Written for `PFS-2025.20.01`, whose acceptance is that
a stated budget covers installed size, transitive dependency count and
licence compatibility, that each candidate is measured against it with
the numbers recorded, and that the chosen one is named with its
measurements rather than with an argument.

"Light" is not a criterion until it is a number. That is the whole
reason this card exists, and it is also why the budget is written down
BEFORE the candidate table: a limit chosen after the numbers are known
is a description of the winner.

**Ordering, stated rather than implied, because it is the one thing a
reader cannot check from the file.** The three limits below were written
into this card before any candidate figure was entered in it, and each
one names an ANCHOR that is a fact of this repository predating every
measurement, so a reader can re-derive the limits without looking at the
table. The measurement commands had already been run in the same
session. The honest guarantee is therefore that the budget is derivable
independently of the results, not that its author had not seen them.

## The budget

### Limit 1: installed size

**The reader and every transitive runtime distribution it brings that
the package does not already require must add at most 5 MiB to an
install.**

Anchor: the runtime set already shipped, measured in this repository's
own environment on the date above.

| Already required | Version | Installed size |
|---|---|---|
| numpy | 2.5.1 | 51.26 MiB |
| pandas | 3.0.3 | 61.19 MiB |
| pydantic | 2.13.4 | 3.61 MiB |
| xarray | 2026.7.0 | 14.98 MiB |
| PyYAML | 6.0.3 | 0.70 MiB |

pydantic, at 3.61 MiB, is the smallest member that does real work
(PyYAML is a parser binding and is not a fair floor for a library).
Reading a surface mesh is a narrower job than a whole validation and
settings framework, so a reader may not cost more than one pydantic,
rounded up to a whole number of mebibytes. Distributions the package
already requires are excluded from the count, because installing them
twice is not a thing that happens: what the budget bounds is the DELTA
a user pays.

### Limit 2: transitive runtime dependency count

**At most ONE new distribution beyond the current runtime set, namely
the reader itself.**

Anchor: NFR-06, which is the single home of record for the runtime set.
It states that the set is minimal and that its COUNT DOES NOT GROW: the
migration takes five to four. A reader arriving with a retinue grows the
count by more than the only movement the author has approved for that
table. One is therefore not a round number picked for tidiness, it is
the largest value consistent with the requirement that governs the
table this dependency would join.

Optional-extra dependencies of a candidate are not counted; what is
counted is what `pip install` resolves with no extras bracket, which is
what a user gets.

### Limit 3: licence

**An SPDX identifier read from the INSTALLED distribution metadata,
permissive and MIT-compatible, for the reader AND for every new
transitive distribution it brings.**

Anchor: NFR-02, whose precedents are `RPT-002`, `RPT-003` and
`RPT-008`. Anything MIT-incompatible is a refusal and not a note. Where
a distribution publishes no PEP 639 `License-Expression`, the field
actually read is recorded rather than flattened into a bare identifier,
in the same shape `RPT-033` uses.

### Recorded beside the budget, not as a limit: format coverage

The solver's own `IMPORT` command accepts ELEVEN file types
(`src/pyflightstream/commands/mesh_import_export.yaml`, the `file_type`
enum): STL, TRI, P3D, INP, STRUCTURED_QUAD, UNSTRUCTURED_QUAD, LAWGS,
VTK, AC, FAC, OBJ. How many of the eleven a candidate reads is recorded
for every candidate.

It is deliberately NOT a limit. This repository's mesh seam is OBJ in
and out by standing policy (`docs/mesh-inputs.md`, "Mesh format
policy"), so a coverage floor above one would refuse a candidate for
failing to serve a need the library does not have. It is recorded
because it is what would change if that policy ever widened, and a
budget that hides the axis on which it might be revisited is a budget
that gets quietly reinterpreted.

## Method

A clean environment per candidate, so nothing already installed in the
development environment is counted as free:

```
python -m pip install --target ./tgt_<candidate> <candidate> --no-cache-dir
```

Python 3.12.0, pip 26.1.2, Windows-11-10.0.26200, 2026-08-19. Installed
size is the sum of the file sizes each distribution's own `RECORD`
claims, read back through `importlib.metadata.distributions(path=...)`
against the target directory, so a shared directory cannot double-count.
Licence fields are read from the same installed metadata.

## The candidates

### meshio

| Measurement | Value | Limit | Verdict |
|---|---|---|---|
| Version resolved | 5.3.5 | | |
| Total closure | 63.95 MiB over 6 distributions | | |
| New distributions | 5 (meshio, rich, markdown-it-py, mdurl, Pygments) | at most 1 | **FAILS** |
| Added size | 12.26 MiB | at most 5 MiB | **FAILS** |
| Formats of the eleven | 4: OBJ, STL, VTK, INP | recorded | |

Breakdown, since the failure is not where a reader would guess. meshio
itself is 1.13 MiB, which is well inside limit 1. What it brings is
`rich` (2.47 MiB), a terminal-formatting library, and rich's own
requirements `markdown-it-py` (0.48 MiB), `mdurl` (0.04 MiB) and
`Pygments` (8.14 MiB), a syntax highlighter. `Requires-Dist` on meshio
5.3.5 reads `numpy>=1.20.0` and `rich`, unconditionally: the console
stack is not behind an extra.

So the distribution that fails this budget is a syntax highlighter,
pulled in so that a mesh converter can print a coloured table. That is
worth naming precisely rather than recording as "meshio is heavy",
because it is the kind of dependency that a later meshio release could
move behind an extra, at which point this measurement would want
re-taking.

Licence: meshio 5.3.5 publishes no `License-Expression`; its legacy
`License` field holds the MIT licence text and its classifier reads
`License :: OSI Approved :: MIT License`. rich: legacy `License` field,
`MIT`. markdown-it-py and mdurl: classifier
`License :: OSI Approved :: MIT License`, no expression. Pygments:
`License-Expression: BSD-2-Clause`. All permissive, all MIT-compatible.
**Limit 3 passes; the licence is not what refuses meshio.**

Formats measured from `meshio._helpers.reader_map`, which holds 29
readers. Mapping them onto the solver's eleven: `obj` to OBJ, `stl` to
STL, `vtk` to VTK, `abaqus` (`.inp`) to INP. The other 25 readers name
formats the solver's `IMPORT` does not accept, and seven of the eleven
solver formats (TRI, P3D, STRUCTURED_QUAD, UNSTRUCTURED_QUAD, LAWGS,
AC, FAC) have no meshio reader.

### trimesh

| Measurement | Value | Limit | Verdict |
|---|---|---|---|
| Version resolved | 5.0.0 | | |
| Total closure | 55.38 MiB over 2 distributions | | |
| New distributions | 1 (trimesh) | at most 1 | **passes** |
| Added size | 3.89 MiB | at most 5 MiB | **passes** |
| Formats of the eleven | 2: OBJ, STL | recorded | |

`Requires-Dist` is `numpy>=1.21` and nothing else; every other name in
its metadata sits behind the `easy`, `recommend`, `test` or `test-more`
extras, which is why the closure is two distributions and 51.18 MiB of
it is the numpy this package already requires.

Licence: no `License-Expression`; the legacy `License` field holds the
MIT licence text and the classifier reads
`License :: OSI Approved :: MIT License`. MIT-compatible. The
adoption-time card of record is `RPT-003`, which covered this
distribution when the `[geom]` extra was created.

Formats measured from `trimesh.exchange.load.mesh_loaders`, 16 entries.
Onto the solver's eleven: `obj` to OBJ, `stl` (and `stl_ascii`) to STL.
The rest (3mf, dae, glb, gltf, off, ply, step, xyz and so on) are
outside the solver's enum.

Note on version: 5.0.0 is what a clean `pip install trimesh` resolves
today, while the development environment here carries 4.12.2 through
the `[geom]` extra. The measurement is of what a NEW install pays,
which is the question the budget asks.

### a NumPy-only in-house reader

| Measurement | Value | Limit | Verdict |
|---|---|---|---|
| Version resolved | not applicable | | |
| New distributions | 0 | at most 1 | **passes** |
| Added size | 0 MiB | at most 5 MiB | **passes** |
| Formats of the eleven | 1: OBJ | recorded | |

This candidate is measured as zero rather than estimated, and that is
exactly why it must not be read as the cheapest option. The budget's
three limits are all about what a USER installs, and in-house code
costs a user nothing and the project everything: it is the axis this
budget does not measure. The standing engineering policy is the counter-
weight, and it is a decision already taken: prefer an existing
MIT-compatible public library whenever the need is generic, and keep
in-house only what is domain logic. Parsing OBJ is generic.

Recorded so the comparison is honest in both directions: an OBJ reader
this package writes itself would be a few hundred lines against a format
whose face and vertex records are simple, and it would owe its own
fixtures, its own refusals and its own maintenance for every malformed
file a user meets. Nothing in this card measures that cost.

## Verdict

**Only trimesh meets all three limits**, at 1 new distribution, 3.89 MiB
added, and an MIT licence read from installed metadata.

meshio is refused BY THE BUDGET, on limits 1 and 2, not by preference
and not on licence: its licence and its licence's transitive closure are
clean. It reads twice as many of the solver's formats as trimesh does,
and the budget says that is not worth 5 new distributions and 12.26 MiB
to a package whose mesh seam is OBJ.

The in-house reader meets the numeric limits by not being a dependency
at all, and is refused by the standing engineering policy rather than by
this budget.

**The decision this card does NOT take.** Naming trimesh as the
candidate that fits the budget is not the same as deciding that a mesh
reader becomes a REQUIRED runtime dependency, and this card deliberately
stops short of that. Two standing decisions bind it and neither is a
session's to move:

* NFR-06 is the single home of record for the runtime set and states
  that the count does not grow, five becoming four at the migration.
  Promoting trimesh out of `[geom]` and into `[project.dependencies]`
  makes it six today and five after the migration, which is a change to
  that table.
* `docs/mesh-inputs.md`, "Mesh format policy", records decision D8 of
  2026-07-23: if a workflow needs formats beyond OBJ, MESHIO joins the
  `[geom]` EXTRA behind a project-owned adapter, with validity checks
  staying on trimesh. This card's measurements bear on that decision
  too, since they are what the "behind an adapter, in an extra" shape
  costs, and they say meshio's cost is a console stack rather than a
  mesh library.

So what this card returns to the author is a measured pair of
statements: the reader that fits the budget is already installed by an
extra she has already approved, and the only open question is whether it
moves from the extra to the required set. `PFS-2025.20.02` is that
question and it is answered in NFR-06's table, by her, not here.

## What this card does NOT establish

It measures one resolution of each candidate on one platform on one
date, with one Python. Wheel sizes differ per platform, most visibly for
numpy, which is why numpy is excluded from every delta above rather than
allowed to dominate the totals. It measures installed bytes and
distribution counts and says nothing about import time, memory, or the
correctness of any reader on a real blade mesh.
