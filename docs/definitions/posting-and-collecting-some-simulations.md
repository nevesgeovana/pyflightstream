<a id="posting-and-collecting-some-simulations-since-0330"></a>

## Posting and collecting some simulations

`pyfs-matrix post <matrix> --sims 2006,2007` rebuilds only those simulations'
products of the matrix, in place. The ids are written as `delete-sims` takes
them: comma separated, or in brackets (`[2006,2007]`). Each named simulation's
files are overwritten in place as a whole post writes them. With `--archive`,
the replaced files first move into their folder's `archive/<stamp>/`;  every other simulation's files keep their bytes, and
`products.json` keeps their entries, their skips and their provenance as they
were, while the named simulations' entries and skips are replaced. Without a
matrix, each matrix holding a named simulation is posted, limited to the ones
it holds. A named simulation with no record of the matrix is refused by name
before anything is written.

A product built from several simulations is written so that it stays true of
every simulation:

| product | under `--sims` |
|---|---|
| the super files (`polars/SUPER-*`), whose columns are the union over every simulation of the matrix | the named simulations' are rewritten under the column set the others carry, read from the superfile measurement, and the others' are left as they were; when the named simulations bring a column the others lack, each other super file is named under `partial.not_rebuilt`. Without a readable measurement every super file is left as the last whole post wrote it |
| `post/<matrix>/reports/superfile-<release>.json`, the measurement of the super files | rewritten with every super file, each kept one as the last measurement named it |
| the settings table (`settings/<matrix>_settings.csv` and its codebook) | rewritten with the named simulations' rows and every other simulation's rows the last table held |
| `post/<matrix>/reports/sections-<release>.json`, the sections measurement | rebuilt from every recorded simulation of the matrix, as a whole post rebuilds it, unless another simulation's folder is compacted or deleted; then left as it was |
| the provenance documents | written for the named simulations only, under the name a whole post gives them |

Each product left is named with its reason under `partial.not_rebuilt` in
`products.json`, beside `partial.sims`, and in one WARNING line of `post.log`.
`campaign_sweep.csv` is written by the run, not by the post.

`pyfs-matrix post <matrix>` without `--sims` reads the RUN cell of the
matrix's rows: a simulation whose rows state RUN = 0 keeps its product files
and its `products.json` entries as they are, and a matrix with no RUN = 1 row
is warned and nothing of it is posted. With no other option it posts only the
RUN = 1 simulations not posted yet: those holding a recorded point for which
the last post wrote no provenance document, or whose document states another
solver end than the record (a point run again). Products brought by `sync`
count as posted. When nothing is pending it says so and exits 0. `--archive`
and `--force-overwrite` rebuild every RUN = 1 simulation; when that is every
recorded simulation of the matrix, it is the whole post. `--sims` rebuilds
exactly the named simulations, whatever RUN states.

No post deletes a product it could not rebuild, such as a product whose
exports are not on this machine. Without `--archive` the product is kept,
file and `products.json` entry, its reason under `skipped` begins with "kept
as the last post wrote it", and one warning counts them. `--archive` moves it
into `archive/<stamp>/`, and a confirmed `--force-overwrite` removes it.

`pyfs-matrix collect --sims 2006,2007` sweeps only the SUBMITTED records of
those simulations, and of their additional extractions; every other record is
left untouched and is not counted as outstanding, so `--watch` stops once the
named simulations are collected. The post that follows (unless `--no-post`) is
limited to the same simulations. An id no record carries is refused before
anything is swept. In Python the keyword is `sims` of
`write_campaign_products`, `collect_once` and `collect_and_post`.

`pyfs-matrix collect --discard-walltime` marks each latest WALLTIME_REACHED
record in that scope FAILED_MARKED after the sweep, before post, including
records from an earlier collect. Under `--watch` it does this after every
pass. It keeps the previous status in `marked.from` and records
`discarded_by: "collect --discard-walltime"`. Outputs stay on disk. A grouped
plan takes the point again from the start automatically, and its run archives
the old record and outputs; a default-mode plan needs `--force-rerun`.
Without the option collect behaves as before.
