## Fixed

- FR-319: the setup-key audit (RPT-106) now covers the Solver Initialization chapter. `INITIALIZE_SOLVER` and each of its arguments have a row, and the tier-1 test requires one for every argument of the command. The audit states that `wake_termination_x` is written `DEFAULT` by every workflow, has no setup key and cannot be changed by the raw route, with its measured reason on 26.124; the key is owed to 0.34 (WAKE-LENGTH).
