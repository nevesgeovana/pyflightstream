## Durable execution activity

Run, solver/submission, translation, post, collection and continuation stages append
timestamped records to logs/activity.log and logs/activity.log.jsonl beside the
workspace. The text log retains progress; JSONL records include final outcome
counts and exception details. Native scheduler stdout remains native when
EXPORT_LOG is disabled. Recorded diagnostics do not enter these stages or mutate
the logs. A standalone local executor keeps its activity log under its working
directory. Progress goes to stderr; JSON and CSV stdout remain data only.

On the console of a command, a warning of the package's own categories prints
as `[warning] <message>`, without the path of the installed file, its line
number or the echoed source line. A warning longer than 90
columns is wrapped, its continuation lines indented under its text, and every
warning is followed by a blank line; the words are unchanged. The first
`[<stage>] started:` line prints the
workspace root absolute and later lines print paths under it relative to it.
The `[continuation] started` and `finished` lines, said for every point whether
or not it continues a run, print only with `--verbose`.
A forced re-run says one line per simulation, for example
`[warning] force_rerun: the collected outputs of 10 point(s) of sim_4016 were archived (sims/sim_4016/datapoints/DP-*/archive/<stamp>)`,
and writes each point's move, with its absolute path, to `logs/activity.log`.
Pass `--verbose` to `pyfs-matrix plan`, `run`, `post` or `collect` to print
Python's full warning format and one line per point again. A Python caller keeps
Python's standard warnings and absolute paths. Every command ends with the
signature box on stderr; `--help` and `--version` end with one short line.
