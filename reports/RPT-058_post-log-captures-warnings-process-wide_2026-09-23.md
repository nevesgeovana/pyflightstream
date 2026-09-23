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
