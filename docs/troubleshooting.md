# Troubleshooting

## Hide warnings on the console

Use `--warning-off` before any subcommand of `pyfs-matrix`, `pyfs-workspace`,
`pyfs-fsi`, `pyfs-qa` or `pyfs-manual` to hide warning lines and their grouped
block. For example, `pyfs-matrix --warning-off post --workspace study` keeps
progress, summaries, errors, the final line and the signature visible.
Warnings remain in the activity log, live log, `post.log`, `post.log.json`
and `refine.json` wherever that operation normally records them. The grouped
post-processing lines that `--pproc-warnings` asks for stay visible, because
that flag is an explicit request for them.

Matrix and workspace commands can take the same default from `pyfs.toml`
(or its local overlay):

```toml
[log]
warnings = false
```

The command-line flag wins over that default, including `warnings = true`.
For Python-driven console commands, use the boolean runtime option:

```python
from pyflightstream.options import get_option, option_context

with option_context("console_warnings", False):
    assert get_option("console_warnings") is False
```

The default is `True`. This controls display only: warning capture and
warning-to-error filters still operate. In particular, `--warning-refusals`
still raises a demoted refusal even together with `--warning-off`.

## Refusals and skipped input

A fatal refusal stops work when continuing would write a wrong result, or
required input cannot be read. A demoted refusal warns and skips an offending
entry when doing so leaves every written result correct. Its message names
the cause and remedy and ends with `--warning-refusals makes this a refusal`.

To restore those refusals, put `--warning-refusals` before either CLI's
subcommand, for example `pyfs-matrix --warning-refusals plan matrix.fs`.
For Python, use `set_option("warning_refusals", True)` or a scoped context:

```python
from pyflightstream.options import get_option, option_context

with option_context("warning_refusals", True):
    assert get_option("warning_refusals") is True
```

`plan_matrix`, `run_matrix`, `write_campaign_products`, `refine_mesh` and
`prepare_to_refine` also accept `warning_refusals=True` for one call.
The default is false. Omitting the keyword uses the current runtime option.

Warnings can be filtered through `pyflightstream.exceptions`:
`DemotedRefusalWarning` selects all demoted refusals; `UnknownKeyWarning`,
`NotApplicableWarning`, `EmptySelectionWarning`, `DuplicateValueWarning`,
`OptionalProductWarning` and `RetiredKeyWarning` select individual families.
Normal Python warning filters remain available. The strict option raises the
original exception, preserving the exception class callers already catch.

| Symptom | Likely cause | See |
|---|---|---|
| Planning refuses a row | An input, build capability, or geometry check failed. | [Plan a campaign](workflow-plan-and-cost.md) |
| A point is blocked | A dependency or execution prerequisite is unavailable. | [Continuation and recovery](continuation-recovery.md) |
| A point failed | The solver or a workspace operation returned a failure status. | [Restore and rebuild records](restore-and-rebuild.md) |
| A run reached its limit | Wall time or iteration limits stopped execution. | [Builds, local runs and clusters](workflow-builds-and-hpc.md) |
| A product was skipped | Required source data was not present or did not meet its conditions. | [Post-processing artifact](pproc-artifact.md) |
| A post warning appeared | The product records a diagnostic that requires review. | [Warnings and diagnostics](definitions/warnings-and-recorded-diagnostics.md) |
| A workspace is locked | Another operation may own the workspace lock. | [Continuation and recovery](continuation-recovery.md) |
| Records are missing or inconsistent | Restore from the archive or rebuild products from recorded exports. | [Restore and rebuild](restore-and-rebuild.md) |
