# Python in a loop

A repeated study follows the same sequence as a single campaign: prepare inputs,
plan, run, post-process, then inspect the results table. Keep each iteration's
inputs and outputs identifiable so results can be compared without changing
the run record.

Use `plan_campaign` to validate a Python `Campaign` before calling `run_campaign`.
For a workspace matrix file, use `plan_matrix` and `run_matrix`. Read
the generated results table after execution and handle refused or failed points
before scheduling the next iteration. Estimate resource requirements before
launching a large parameter sweep; see [planning a campaign](../workflow-plan-and-cost.md).

The [Python tutorial](../tutorial-python-api.md) introduces the package objects
used by a script. The [workspace route map](../workspace-route-map.md) shows
which tasks also have a declarative workspace route.
