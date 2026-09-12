# RPT-045: the unsteady actions of PFS-2031.18 ran on 26.123, and the four unmeasured things are measured (2026-09-09)

Row 6002 of `tests/tier3_licensed/matriz_actions.fs`, the `unsteady` run
type on the tour's wing with `EXPORT_UNSTEADY_AFTER_ITER: 4` over eight
steps of 0.01 s, run through `pyfs-matrix run` on 26.123. Design 67
(GeoversePlan) said what the run would leave and listed four things the
tier-1 build could not measure; this report reads the run and answers
them. PFS-2031.18.

Verdict: the design works as drawn, on the first licensed run
Build: 26.123 (build #8112026)
Record: `tier3_licensed/sim_6002/a+02.0`, CONVERGED, `action_count` 8

## How it was run

    python -m pyflightstream.run.cli run tests/tier3_licensed/matriz_actions.fs --workspace tests/tier3_licensed --resume

(from the repository root, because row 6001's LEGACY recipe lives under
`tests/` and the console script cannot import it from an installed
package; `--resume` because 6001 is recorded.) The run layer wrote
`actions/pfs_unsteady_actions.py`, the counter program, and
`actions/pfs_unsteady_exports.txt`, empty, before the solver started, and
hashed both into the record (the script's hash is that of zero bytes).
The run type registered, before `INITIALIZE_SOLVER`:

    SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter
    "C:\python\python.exe" "actions/pfs_unsteady_actions.py"

    SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT pfs_unsteady_exports
    actions/pfs_unsteady_exports.txt

## What the run left

| Where | What |
|---|---|
| `actions/pfs_unsteady_actions.count` | `{"count": 8, "time_s": 0.08, "azimuth_deg": null, "revolutions": null, "exporting": true}` |
| `actions/pfs_unsteady_exports.txt` | the three update lines and the five export pairs, rewritten by the program |
| the simulation folder | 25 stamped files: for each iteration 4, 5, 6, 7, 8 the loads `.txt`, the Tecplot `.dat`, `_cp`, `_sloads` and `_probes`; nothing for 1 to 3 |
| the solver log | `Executed runtime command: "C:\python\python.exe" "actions/pfs_unsteady_actions.py"` eight times, each followed by `Running script file: actions/pfs_unsteady_exports.txt` |
| `raw/` | the end-of-run set, eight files, as for any unsteady row |
| the record | `action_program`, `action_script`, `action_count: 8`, both files in `inputs_sha256` |

## The four things design 67 left unmeasured, answered

1. **A quoted two-token command line is accepted as a COMMAND_LINE
   action.** The log echoes it verbatim and ran it eight times.
2. **Relative paths on the registration lines resolve against the
   simulation folder**, both the program on the command line and the
   SCRIPT file: the log names them as written and the files under
   `actions/` were the ones read and rewritten.
3. **The update commands and the four exports beyond the loads table run
   from an action script mid-run**: `_cp`, `_sloads`, `_probes` and the
   Tecplot frame exist for every step from 4, each stamped `_iteration=N`
   before the extension, on a suffixed name as on a bare one.
4. **The solver waits for the COMMAND_LINE action to exit before running
   the SCRIPT action**: every one of the eight pairs in the log is
   ordered command then script, and the file the script action read at
   step 4 already carried the exports the program had just written, which
   it could not have if the solver had not waited.

## What stays open

The per-step files stay in the simulation folder, uncollected. How they
reach the products is the remaining question of scope section E2 and is
not this node's; it is registered as the next child of PFS-2031 for
0.14.0 unless the accepting seat asks for it sooner.
