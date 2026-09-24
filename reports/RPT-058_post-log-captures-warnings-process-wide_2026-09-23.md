# RPT-058: post log captures warnings process-wide

**Date:** 2026-09-23
**Found by:** the architect lens of the opening round of 0.26.0
**Status:** REGISTERED for 0.27.0
**Affects:** concurrent campaign posts in threads of one Python process

## What was measured

`post/products.py` wraps a campaign post in
`warnings.catch_warnings(record=True)`. On the measured CPython 3.12.0 runtime
this changes process-wide warning capture. The surrounding `ContextVar`s
isolate verdicts and refusal policy, but do not isolate that warning sink.

A controlled two-thread probe posted two synthetic empty campaigns. Thread A
entered its post capture first; thread B then entered its capture; A emitted
`point=campaign-A product=probe: capture ownership witness` while B's capture
was active. B finished before A. Both campaigns' `post.log` files contained
the campaign-A warning. B captured another campaign's warning, then re-emitted
it into A's still-active capture. No solver was run. The initial probe's
stronger expectation that A would lose the warning failed: this ordering
duplicates it instead. The cross-campaign attribution defect was reproduced.

Other exit orderings can change which capture retains or re-emits the warning.
This measurement establishes contamination of B's log, not every possible
thread ordering. It conflicts with AD-03 and campaign-local log ownership.

## Why it is not fixed here

The package posts one campaign per process in every documented path. A
campaign-local sink is a design change for the post-completeness release,
0.27.0, rather than a rewrite of the log mechanism during these 0.26.0 fixes.

## What the reader can rely on meanwhile

Post one campaign per process. The definitions page and the CHANGELOG's log
entry state this limit. Closure requires a campaign-local sink and a controlled
two-thread, two-workspace regression proving warnings cannot cross campaigns,
including interruption and warning re-emission.

## CLOSED in 0.27.0, 2026-09-24

The package's warnings now take one route, `pyflightstream._errors.warn`.
Inside `collecting_warnings()` it appends the warning to a sink held in a
`ContextVar`. Outside every sink it is `warnings.warn`, attributed to the same
line. Every `warnings.warn` under `post/`, `results/` and `cases/`, 40 sites,
now calls it. `write_campaign_products` collects in a sink of its own instead
of `warnings.catch_warnings(record=True)` and writes what it collected to
`post.log`. After the sink is reset, it replays those warnings with
`warnings.warn_explicit`, so the replay reaches the caller's filters and no
campaign's log. On CPython 3.12 a new thread starts with an empty context, so
two posts in two threads hold two sinks.

A second form of the same defect was found and measured while closing this
one, and it is closed by the same change. `_sweep_rows` silenced the sweep
table's own warning with a process-wide `simplefilter("ignore")`. A warning
another post raised while that filter was active reached neither campaign's
log: the warning was lost, not just attributed to the wrong campaign. The
sweep table's warning now goes to a discarded sink held by that thread alone.

What a reader sees differently: a warning raised during a post by code outside
the package is no longer written to `post.log`, and it reaches the caller's
warning filters as before. `run/`, `script/` and `workspace/` keep their bare
`warnings.warn` calls, 14 sites. The reconnaissance for this closure traced
calls by name from `write_campaign_products`, which over-approximates what a
post reaches, and that trace reached none of those 14 sites.

The regressions are in `tests/tier1_offline/test_post_log.py`:

- `test_two_posts_in_two_threads_keep_their_own_warnings`, with and without B
  interrupted, runs the ordering measured above on two empty synthetic
  workspaces. Each warning goes through a real package site, `_judge_average`.
  On the parent tree both logs held campaign-A and campaign-B once each, in
  both cases. The spied `warnings.warn_explicit` recorded four replays: B
  replayed A's warning and its own, and A did the same. The test failed at its
  first assertion, B's log holding campaign-A. It now passes: each log holds
  its own campaign's warning once and not the other's, B's log keeps its
  interruption, and each thread replays only its own warning.
- `test_one_posts_silenced_sweep_does_not_silence_another_post` makes B warn
  while A is reading its sweep table. On the parent B's log held campaign-B 0
  times, and so did A's. It now holds it once.
- `test_the_sweep_tables_own_warning_stays_out_of_the_post_log` keeps the
  discard. Its control asserts that a warning from the stage itself, on the
  same route, is logged.
- `test_no_bare_warnings_warn_where_a_post_reaches` walks `post/`, `results/`
  and `cases/` and refuses any bare `warnings.warn`. On the parent it listed
  40 sites. A floor on the routed calls stops it passing on an empty walk.
- The two existing tests that injected a bare `warnings.warn` into the stage
  now inject through `warn`, because a bare call is outside the package.

Each mutant was made on a scratch copy of the source. The pytest process
reported importing `pyflightstream` from that copy, and `sys.monitoring`
recorded that the mutated line executed:

- Replacing `sink = _SINK.get()` with `sink = None` in `warn` failed all six
  selected tests with exit 1: both thread cases, the sweep-silence case, the
  sweep-discard test at its control, and both edited tests.
- Turning `_judge_average`'s `warn(` back into `warnings.warn(` failed all
  three selected tests with exit 1. Both thread cases failed with B's log
  missing campaign-B, because both witnesses pass through that site. The walk
  failed naming `post/products.py:1845`.
- Replacing `_sweep_rows`'s `with collecting_warnings():` with
  `with contextlib.nullcontext():` failed the discard test with exit 1, with
  the sweep-table witness in `post.log`.

An unmutated copy run the same way passed each selection, and its original
line executed. No solver was run.

**Status:** CLOSED in 0.27.0
