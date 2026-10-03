<a id="posting-and-collecting-some-simulations-since-0330"></a>

## Posting and collecting some simulations

`pyfs-matrix post <matrix> --sims 2006,2007` rebuilds only those simulations'
products of the matrix, in place. The ids are written as `delete-sims` takes
them: comma separated, or in brackets (`[2006,2007]`). Each named simulation's
files are archived into their folder's `archive/<stamp>/` and rewritten as a
whole post writes them; every other simulation's files keep their bytes, and
`products.json` keeps their entries, their skips and their provenance as they
were, while the named simulations' entries and skips are replaced. Without a
matrix, each matrix holding a named simulation is posted, limited to the ones
it holds. A named simulation with no record of the matrix is refused by name
before anything is written.

A product built from several simulations is never written from some of them:

| product | under `--sims` |
|---|---|
| the super files (`polars/SUPER-*`), whose columns are the union over every simulation of the matrix | left as the last whole post wrote them, the named simulations' included |
| `reports/superfile-<release>.json`, the measurement of the super files | left as it was |
| `reports/sections-<release>.json`, the sections measurement | rebuilt from every recorded simulation of the matrix, as a whole post rebuilds it, unless another simulation's folder is compacted or deleted; then left as it was |
| the provenance documents | written for the named simulations only, under the name a whole post gives them |

Each product left is named with its reason under `partial.not_rebuilt` in
`products.json`, beside `partial.sims`, and in one WARNING line of `post.log`.
`pyfs-matrix post <matrix>` without `--sims` is the whole post and rebuilds
them. `campaign_sweep.csv` is written by the run, not by the post.

`pyfs-matrix collect --sims 2006,2007` sweeps only the SUBMITTED records of
those simulations, and of their additional extractions; every other record is
left untouched and is not counted as outstanding, so `--watch` stops once the
named simulations are collected. The post that follows (unless `--no-post`) is
limited to the same simulations. An id no record carries is refused before
anything is swept. In Python the keyword is `sims` of
`write_campaign_products`, `collect_once` and `collect_and_post` (FR-307).

`pyfs-matrix collect --discard-walltime` marks each latest WALLTIME_REACHED
record in that scope FAILED_MARKED after the sweep, before post, including
records from an earlier collect. Under `--watch` it does this after every
pass. It keeps the previous status in `marked.from` and records
`discarded_by: "collect --discard-walltime"`. Outputs stay on disk. A grouped
plan takes the point again from the start automatically, and its run archives
the old record and outputs; a default-mode plan needs `--force-rerun`.
Without the option collect behaves as before (FR-400).
