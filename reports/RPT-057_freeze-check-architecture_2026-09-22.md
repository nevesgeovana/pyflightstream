# RPT-057: the freeze check reads the log twice, and guesses the second time

**Date:** 2026-09-22
**Decision:** the owner's, 2026-09-22 -- the native-log freeze check is OPT-IN in 0.25.1
(`--check-frozen`), and the architecture is re-discussed in 0.26.0.
**Status:** REGISTERED for 0.26.0, under `GOAL-030`.
**Superseding decision, the owner's, 2026-09-22:** nothing in the post blocks by default, and
the post always writes a log of its own carrying a warning wherever one applies. That changes
what this report is about: the question below stops being whether the guard refuses the right
products and becomes what the log says. `GeoversePlan/goals/GOAL-030` carries her wording and
the reason.

## What the check is for

A frozen solve keeps printing time steps whose residuals are exactly zero: it has stopped
solving and is still turning. The numbers it exports stay plausible, so an average taken from
them looks like any other and is wrong. 0.25.0 began reading each point's native log while
posting and refusing the averages a freeze touches; a block the solver stopped under cannot be
judged either way, so averages over it are refused too.

## Why it became a question

For a plain average, the steps it reads are the steps its window names. For the AZIMUTHAL
phase-locked average they are not: the reducer samples at moments between plotted steps, one per
blade and one per azimuth of the final revolution, and `numpy` reads the plotted steps bracketing
each moment. Deciding which steps such an average reads therefore means knowing exactly what the
reducer samples.

The guard in `post/products.py` computes that itself, and on 2026-09-22 eight rounds of review
found it wrong in one direction or the other, every time:

| what it did | what it cost |
|---|---|
| judged the declared window | published an average that read an unread step |
| bracketed one revolution earlier | refused clean averages on a dense history, missed a sparse one |
| bracketed the window's opening | refused clean averages wherever the samples are whole steps |
| enumerated every azimuth of the interval | refused clean averages on a fractional clock |
| applied every declared blade offset | refused clean averages on a totals-only history |

Each fix was correct about the case that prompted it and wrong about a case nobody had thought
of yet. That is the signature of a SECOND IMPLEMENTATION of an arithmetic that already exists.

## What 0.26.0 should decide

**The reducer knows its own samples.** `post/unsteady` computes the moments it averages; the
guard should ASK for them rather than recompute them from the plan. The shape worth discussing:

- the reducer exposes the moments, or the steps they bracket, for a given plan and history;
- the guard judges that set against the unread steps, with no arithmetic of its own;
- a totals-only history therefore contributes no blade offsets, because the reducer takes none,
  and a fractional clock contributes exactly the moments the reducer takes.

**And whether it belongs in `post` at all.** The check re-reads, at post time, a log that the
COLLECT stage already read to assess the run. A freeze is a property of the run, recorded once,
rather than a question re-asked of every rebuild. If the record carried the verdict, the post
stage would judge windows against a recorded fact and open no log.

## What is true in 0.25.1 meanwhile

The reading is off unless asked. With it off, a frozen solve's averages are published; with it
on, the refusals are those measured above, conservative where they are imprecise -- they refuse
more than the arithmetic reads, never less, and every refusal is named in `products.json` with
the step and the remedy. The crash that prompted the release is fixed in both modes: a log that
cannot be read never ends the post.

## Addendum, 2026-09-22, from the closing round of v0.25.1

The sentence above, "they refuse more than the arithmetic reads, never less", is corrected: the
V&V lens found one case where the guard reads LESS. The guard takes its blade offsets from the
RECORDED plan, and the reducer takes its families from the reference through alias expansion
(`_section_rotors`). A recorded family alias that expands to two blades gives the reducer a
second blade offset the guard never sees: three steps per revolution, window `[59, 61]`, the
reducer samples 58.5 and reads the plotted step 58; the guard judges `[59, 61]` and an unread
58 passes. This is the same defect shape as the rest of the table, in the other direction, and
it is the strongest reason yet for the shape proposed above: the guard must ASK the reducer
for its samples rather than rebuild them from a different source. It is registered here, under
the opt-in flag, and closes with this report in 0.26.0.

Also from that round, a question this report does not answer and 0.26.0 must: at
`steps_per_revolution = 2.0000000001` the reducer interpolates at 59.99999999995 and the
plotted step 59 carries a weight of about 5e-11. Whether every nonzero weight is judged, or a
stated cutoff applies, is a decision for the numerical seat, and it is taken where the samples
are stated, in the reducer, not in a guard that rebuilds them.

## CLOSED in 0.26.0, 2026-09-23

**Status:** CLOSED in 0.26.0

P01 is implemented as `post.log` beside `products.json`, named by its `log`
field. Every invocation writes a header, including an empty clean campaign;
every stage warning and named skip is logged, including on interruption. The
old log is archived using the products' rebuild timestamp. P02 is implemented
as warning-only post judgements by default. Computable exports survive frozen,
unread, failed-status and reference-mismatch doubts. The opt-in retains earlier
refusals, with warnings logged too. Data and assignment impossibilities still
have named skips. Native freeze verdicts are cached only for this invocation;
a rebuild reads the changed native log again.

P03 is implemented by the `read_steps` collector on `phase_locked_rows` and
`blade_passage_average` in `post/unsteady.py`. The collector is filled inside
the averaging path. The product guard asks that path using the writer's resolved
families and checks the returned set, without its former moment enumeration or
blade-offset implementation. An unread step in a sparse history's envelope but
outside the actual sample set costs nothing.

The weight decision is every nonzero interpolation weight, without a cutoff.
A small coefficient can multiply a large plotted value, so excluding it would
make the verdict disagree with the numerical result. At 2.0000000001 steps per
revolution, step 59 has weight about 5e-11 and is included. Perturbing every
plotted row independently verifies that the stated set equals the rows that
change the computed result.

| Case | Measured sample set |
|---|---|
| Totals only; two declared blades; three steps per revolution; [59,61] | {59,60,61} |
| Totals only; 3.6 steps per revolution; four revolutions ending at 20 | {6,7,8,9,10,11,12,13,14,15,16,17,18,19,20} |
| Recorded family B expanded by the reference alias to Blade1 and Blade2; three steps per revolution; [59,61] | {58,59,60,61} |
| Two plotted blades; 2.0000000001 steps per revolution; ending at 61 | {59,60,61} |

The tests are in `tests/tier1_offline/test_post_log.py`:

- `test_every_post_writes_and_archives_its_log`: before, exit 1 because the
  clean manifest had no log; a mutant changing the manifest's log name also
  failed with exit 1.
- `test_default_keeps_every_product_with_frozen_and_unread_steps`: before,
  exit 1 because the frozen and unread steps had no post log. It compares all
  products against the defect-free campaign, then checks the warning's point,
  product, steps 58 and 60, and remedy. A mutant forcing refusal in default
  mode lost the time average, phase-locked average, per-blade table and unsteady
  polar and failed with exit 1.
- `test_reducer_samples_control_product_warning_or_refusal`: before, the
  opt-in refused the totals-only product for unread 58 and the fractional-clock
  product for unread 5, while publishing the alias-expanded product over unread
  58. The final cases test inside and outside steps in both modes.
- `test_reducer_states_exactly_the_nonzero_samples`: the lower-bracket mutant
  failed three cases with exit 1, omitting step 6, 58 and 59 respectively.
- `test_guard_judges_the_sample_set_not_its_envelope`,
  `test_every_stage_warning_is_logged_even_if_the_caller_filters_it`,
  `test_interrupted_post_keeps_its_log_and_warning`, and
  `test_a_clean_empty_campaign_also_has_a_log` cover the set and log boundaries.

The reference-refusal mutant failed the three default cases of
`test_round1_post_refusals.py` with exit 1 while the three opt-in cases passed.
Every mutant was written into its implementation file, run in its own pytest
process, and restored from an exact byte snapshot. No test assertion was weakened
to make an implementation pass. The first pytest launch could not import
`pygments`; installing that missing test dependency into the ignored local
`.venv` enabled the measured runs. This environment failure is not counted as red.

RPT-055 closes alongside this change; its closing census states the unavailable
historical repeated-marker fixture explicitly. No full suite or solver was run.

Additional boundary mutants all exited 1: replacing sample-set membership with
its envelope falsely judged unread step 58 in {1,59,60,61}; removing captured
warning lines failed both filtered-warning and interrupted-post cases; restoring
the failed-status filter removed every product of the incomplete point. The
repeat-marker mutant and its measured lost freeze are recorded in RPT-055.
The existing product-directory inventory test was updated to include the new
`post.log`; before that contract update it failed on precisely that extra file.

### Final validation, 2026-09-23

Each file ran in its own pytest process with this worktree's `src` first on
PYTHONPATH. Exit statuses were read from the process, not a shell pipe.

| File in `tests/tier1_offline/` | Exit | Result |
|---|---|---|
| `test_post_log.py` | 0 | 27 passed, 99 warnings |
| `test_b01_frozen_solve.py` | 0 | 19 passed, 118 warnings |
| `test_unread_steps_and_freezes.py` | 0 | 17 passed, 1 warning |
| `test_azimuthal_interpolation_support.py` | 0 | 4 passed, 13 warnings |
| `test_frozen_check_is_opt_in.py` | 0 | 6 passed, 42 warnings |
| `test_round1_post_refusals.py` | 0 | 19 passed, 55 warnings |
| `test_surface_exports.py` | 0 | 21 passed, 26 warnings |
| `test_goal028_reference_agrees.py` | 0 | 4 passed, 4 warnings |
| `test_post_products.py` | 0 | 60 passed, 49 warnings |
| `test_post_unsteady.py` | 0 | 19 passed, 1 warning |
| `test_goal026_item09_phase_locked.py` | 0 | 14 passed, 1 warning |
| `test_goal026_item11_guides.py` | 0 | 7 passed, 1 warning |
| `test_house_style.py` | 0 | 19 passed, 1 warning |
| `test_goal028_definitions_page_quotes_no_one.py` | 0 | 4 passed, 1 warning |
| `test_cli_options_registry.py` | 0 | 8 passed, 1 warning |
| `test_metadata_currency.py` | 0 | 10 passed, 2 skipped, 1 warning |

Ruff check: exit 0. Ruff format check: exit 0, 423 files already formatted.
Mypy with this worktree's `src` on PYTHONPATH: exit 0, 97 source files.
The two metadata skips are the existing development-tree checks for a newest
release row and a release date, not missing dependencies.
