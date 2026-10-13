# Troubleshooting

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
