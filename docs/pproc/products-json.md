## products.json: the tree, the units and the frames

<a id="products-json"></a>

`post/<matrix>/products.json` lists every file the post wrote and, beside the list, states
what every column of every file is. The csv files stay lean: units and frames are stated
here once.

| Key | Content |
| --- | --- |
| `schema_version` | the layout of the document, `2` |
| `products` | every file written, with the runs it came from and its `kind` |
| `tree` | each folder of the post tree, what it holds and the kinds of file in it |
| `kinds` | each kind of table: what one row is, its key columns and every column after the run block, with `unit`, `frame`, `quantity`, `sign` where it has one, and the page that `definition` names |
| `run_block` | each column of the [run block](../definitions/the-run-block.md#the-run-block), with its `unit`, its `source` and its definition |
| `frames` | the frames the columns are stated in: the export frame `E`, the body, stability and wind frames, one `R<id>` per rotor with its pitch and toe, and the mesh frame |
| `families` | each family of the geometry, with its `FAMILY_ID`, its name and the id of its rotor |
| `groups` | each group of the polar files, with its `GROUP_ID`, its origin and its member family ids |
| `polars` | each polar, with its description and run type |
| `migrated` | each file of an [earlier layout](#reading-the-earlier-layout) found in the tree, with the path that replaces it; `null` for a table that is no longer written |
| `skipped`, `log`, `log_json`, `provenance`, `complete` | unchanged: what was not written and why, the post logs and the provenance of each run |

Every column of every kind written is listed once, expanded: a per-rotor or per-frame
column is listed by its own name (`CDR0`, `RPM0`). A column that is a scalar has the frame
`null`. The header of every file is the run block of `run_block`, then the columns of its
kind, in that order.

### The tree

| Folder | Holds |
| --- | --- |
| `polars/` | the [FAM](fam-dim.md) and [group](group-files.md) files, one set per polar |
| `time_history/` | [the plots history](time-history.md) |
| `reductions/` | [phase_locked](phase-locked.md), [per_revolution](per-revolution.md), [the harmonics](harmonics.md) and [the disc maps](disc-maps.md) |
| `probes/` | [probe tables](probes.md) only |
| `sections/` | [sections](sections.md) and [Cp](cp.md) |
| `fields/`, `surfaces/`, `streamlines/` | [sampled fields](fields.md), [the averaged surface](averaged-surface.md), [streamlines](streamlines.md) |
| `settings/`, `provenance/` | [settings](settings.md) and the provenance of each run |

### Reading the earlier layout

A file written in an earlier layout and still in the tree is left untouched. The post
names each kind once in one warning and lists the files under `migrated`; a reader inside
the package reads the new path and falls back to the earlier one with the same warning.
