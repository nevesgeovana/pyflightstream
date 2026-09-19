# RPT-053: what an unsteady export states, and at which step (2026-09-19)

**WHAT THIS SETTLES.** Two claims 0.24.0 makes about solver behaviour, each
re-read from recorded licensed exports on FlightStream 26.124 (build #8172026),
so that the sentences in the changelog, the tests and the definition of record
rest on a dated, committed measurement instead of on a remembered one:

1. On an UNSTEADY run, the export header's `Current solver iteration number`
   counts the solver's INNER iterations, summed over every time step. It is not
   the time step.
2. On an unsteady rotor point, the force at the LAST time step and the mean
   over the row's averaging window are different numbers, so a table holding one
   under the name of the other publishes a wrong number.

The exports are machine output under the campaign workspaces and are not
tracked; each is identified below by its campaign row, its point, and the first
sixteen hex digits of its SHA-256, so a later reader can tell whether the file
they hold is the one read here.

## 1. The header counts inner iterations

Campaign `pfs0240`, row 2411 (the isolated rotor sector, periodic symmetry,
alpha 0), point `M144RE438AL+000BE+000`. The run record states 144 time steps
and no watchdog stop.

| read from | value |
|---|---|
| `P2411-M144RE438AL+000BE+000_sloads.txt` header, `Current solver iteration number` (sha256 `0f86934edaa3354f`) | **2813** |
| the same line of the loads export `P2411-M144RE438AL+000BE+000.txt` | **2813** |
| `P2411-M144RE438AL+000BE+000_plots.txt`, rows of the history, and its last `Time-step` (sha256 `01e557a57cf97676`) | **144** rows, last step **144** |
| the run record's planned `time_iterations` | **144** |

So the header counts 2813 on a run of 144 time steps, about 19.5 inner
iterations per step. The same mechanism was recorded at three solves per call
in `RPT-005_fsi-dry-run_2026-07-21.md` (header values 154, 504, 722); this is
its confirmation on a rotor run of the current build.

**Consequence in the package:** the sections table of an unsteady point states
the run's last TIME STEP, read from the record, and not the header's number;
its `AZIMUTH` is computed from that step (0.24.0, "the step of an unsteady
point's sections table").

## 2. The last step is not the window average

Campaign `pfs0230`, row 2302, point `M144RE438AL+100BE+000` (alpha 10). The row
states `LAST_REVS_AVG = 0.5` on a clock of 72 steps per revolution, so its
window is steps 109 to 144, as its run record says.

`P2302-M144RE438AL+100BE+000_plots.txt` (sha256 `fdd29e1fd460f6c5`), column
`FX_ROTOR`, in Newtons:

| | value |
|---|---|
| step 144, the last | **-410.75 N** |
| mean of steps 109 to 144, 36 steps | **-287.82 N** |

The two differ by 43 per cent of the mean. A rotor table that states the last
step under the name of the row's average states the first number where the
second was defined.

**A FIGURE THIS REPORT RETIRES.** Earlier text of this release quoted
"-606.6 N at the last step against -397.4 N over the window", from row 2301 of
the same campaign. Re-read here, it does not reproduce: the -606.6 N was the
native loads export's `Cx` of the blade converted to Newtons, not a value of
the plots history, and the plots of row 2301 give -389.42 N at the last step
and -389.37 N over steps 109 to 144. The pair is withdrawn from every page and
replaced by the measurement above.

## What this does not settle

Whether the history of either point has SETTLED is not judged here, and the
package does not judge it: it states whether the iterations within the last
time step converged, and the user reads the history.

## How to re-read it

Every number above is read with the standard library from the files named:
the header line by a regular expression, the history as comma-separated rows
under the `Time-step` header, the window from the run record in the
workspace's `runs.json`. No package code is in the path of the reading.
