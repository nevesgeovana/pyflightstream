# Log fixtures of FT-COLLECT (0.35.0.dev0)

Compacted, scrubbed transcripts of the logs of the licensed re-initialisation probes of
2026-10-02, FlightStream 26.1 build 8172026, synthetic geometry `30_BLADE.fsm` only.
`*.cumulative.txt` are the cumulative `EXPORT_LOG` copies of one solver instance that ran
several points, cut at `Solution cleared. Initialization removed.`; `fresh_*.txt` are the logs
of the same points, each run alone in its own instance.

Compaction (the same rule on every file, so a slice and a fresh log compare like with like):
NUL bytes, CR and blank lines removed; every line outside a time-step block kept; in each run,
the whole block of the first and of the last time step kept (the residual rows the parsers
read), and of every other step only its `Solving unsteady time-step iteration (k/N)` line;
the per-step action echo lines (`Executed runtime command`, `Running script file: actions/`,
`Script run complete`) dropped; every machine path written as `<machine path>`.

Which segment is which fresh point: A2 is 9811 AL+000 then 9812 AL+020 (one polar, a
re-initialisation between); C2b is 9811 AL+000, then 9821 J+150 (a reopened model, the start of
a second polar) and 9821 J+190; E2 is 9811 AL+000, then 9841 AL+000 (a mesh change, the start
of a second polar) and 9841 AL+040. None of these logs prints a wake-edge import line.

| fixture | source (under the licensed probe workspace of 2026-10-02 (RPT-141)) | source sha256 | bytes |
|---|---|---|---|
| `A2.cumulative.txt` | `reinit-test/armA/A2_log.txt` | `048e20f2fc6aee42244d5c1619c31de012f53d612dcbf9db42fd9557b9ceaf17` | 25269 |
| `C2b.cumulative.txt` | `reinit-test/armC/p2b/C2b_log.txt` | `eb710699a1ba4b0668300be8fb01d5a455f5d69eaf1ed39a31a63c3a9b02bf4a` | 47884 |
| `E2.cumulative.txt` | `reinit-test/meshchange/E/b2/E2_log.txt` | `28d4390dbbd23f057216fe5b711d138409bb7f0e682905d04007ed872b1f6d2e` | 64244 |
| `fresh_9811_AL+000.txt` | `reinit-test/ws/sims/sim_9811/datapoints/DP-M144RE438AL+000BE+000/P9811-M144RE438AL+000BE+000_log.txt` | `1352f945ee884121d4b10fe90051782e91c8b7c3e41d0f1cae02899489759727` | 13053 |
| `fresh_9812_AL+020.txt` | `reinit-test/ws/sims/sim_9812/datapoints/DP-M144RE438AL+020BE+000/P9812-M144RE438AL+020BE+000_log.txt` | `cf9a80010d91d4d0a2de5d315800f3df257e6e6b624e83a37e73416c34a6a158` | 12939 |
| `fresh_9821_J+150.txt` | `reinit-test/ws/sims/sim_9821/datapoints/DP-M144RE438AL+000BE+000J+150/P9821-M144RE438AL+000BE+000J+150_log.txt` | `4ea3f043b0025b2ce036442a34e7e059226eb74e63795b464b76c951a38616e4` | 18110 |
| `fresh_9821_J+190.txt` | `reinit-test/ws/sims/sim_9821/datapoints/DP-M144RE438AL+000BE+000J+190/P9821-M144RE438AL+000BE+000J+190_log.txt` | `26551acb0224cd3abb6e40ab10ffd8e31922dbec55e2f38db7503f1b624dbb74` | 17888 |
| `fresh_9841_AL+000.txt` | `reinit-test/meshchange/ws/sims/sim_9841/datapoints/DP-M100RE230AL+000BE+000/P9841-M100RE230AL+000BE+000_log.txt` | `49778b3751003b4b57b22491e6c9bd7da41ecd934fbe04070b9281a463659ed5` | 26078 |
| `fresh_9841_AL+040.txt` | `reinit-test/meshchange/ws/sims/sim_9841/datapoints/DP-M100RE230AL+040BE+000/P9841-M100RE230AL+040BE+000_log.txt` | `4b871a1a164ba0942d697db527ec6202c3133d9ec2c19cc0be3da4e767872c27` | 26192 |
