The `pfs0240_row2413_steps58-61_log.txt` and
`pfs0240_row2411_steps58-61_log.txt` fixtures are verbatim byte excerpts of
campaign pfs0240, rows 2413 and 2411, respectively. Each contains the native
log's first eight lines (version/copyright header), followed by the bytes from
the start of `Solving unsteady time-step iteration (58/144)` up to, but not
including, the step 62 marker. NUL bytes, tabs and CRLF line endings are retained.

Source relative to the campaign directory:
`sims/sim_<row>/datapoints/DP-M144RE438AL+000BE+000/P<row>-M144RE438AL+000BE+000_log.txt`.

Row 2413 freezes at step 60, with two consecutive frozen steps in this excerpt.
Row 2411 is the healthy control. Their last printed inner-iteration counters in
these excerpts are 1933 and 1728, respectively; these are not time-step numbers.
