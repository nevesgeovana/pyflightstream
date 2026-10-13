<a id="the-post-of-other-records-since-0320"></a>

## The post of other records

The products of `pyfs-matrix post` are rebuilt from `runs.json` by default.
Two options post other records, and their products stand apart from the
default ones so the two can be compared; the columns inside are the default
post's. The file names of `--runs NAME` are the default post's too; those of
`--from-sims` carry the point names and the sweep token the records were
assembled with (below), since the naming a run outside the package used is
not recorded anywhere to be repeated.

| command | the records | the products folder |
|---|---|---|
| `pyfs-matrix post <matrix>` | `runs.json` | `post/<matrix>/` |
| `pyfs-matrix post <matrix> --runs NAME` | the manifest `NAME` in the workspace root | `post/<matrix>@<NAME without .json>/` |
| `pyfs-matrix post <matrix> --from-sims` | assembled in memory from `sims/` | `post/<matrix>@sims/` |

An apart folder holds its own `products.json`, `post.log`, `archive/` and its
own measurement reports under `reports/`; nothing under `post/<matrix>/` or the
workspace's `reports/` is written by it. `pyfs-matrix collect --runs NAME`
completes the submitted records of `NAME` and posts them apart the same way.

**What `--from-sims` assembles, and what it refuses.** Each loads export under
`sims/sim_<POL>/` of a row of the matrix is one point (outside the `archive`,
`scripts` and `inputs` folders), and the files beside it named its stem plus
the suffix of another export kind (`<stem>.dat`, `<stem>_plots.txt`,
`<stem>_log.txt` and the rest) are its other exports; a file whose name only
begins with the stem is another point's. The record takes:

- the point: the value of the row's sweep at the angles the export reports;
- the flight condition: the row's, the swept value in place, resolved with the
  setup's pins, while the export's reported velocity, angles and Reynolds
  number still win in every product row, as they do for a recorded run;
- the reference block and the aliases: the row's reference;
- the averaging window: the row's `LAST_REVS_AVG` or `LAST_ITERS_AVG`, cut over
  the steps of the point's plots export, with `--steps-per-revolution N` for a
  window in revolutions;
- the point's name: its `DP-<name>` folder's, else the export's stem; the
  sweep token in the file names is `<code>+sweep`, for example
  `P6001-AL+sweep_g02.csv`;
- the status: the collect's assessment of the exports, so a steady point with
  no log export reads `FAILED_INCOMPLETE_OUTPUT` and is posted with a warning.

What cannot be recovered is refused by name and that point or row is left out,
printed and written into `post.log`: a reference that does not resolve, a
condition that does not resolve, an export whose angles are no value of the
sweep (or a row sweeping anything but an angle over more than one value), two
exports at one point, a time history with no window in the row, and a window in
revolutions with no `--steps-per-revolution`. Such a record carries no rotor
block, so the rotor tables and the per-rotor reductions of its point are named
skips. No manifest is written.
