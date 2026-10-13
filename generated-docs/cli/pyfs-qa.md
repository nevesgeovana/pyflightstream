# pyfs-qa

Generated from the argument parser at build time, so this page and `pyfs-qa --help` cannot disagree. The entry point is `pyflightstream.qa.cli:main`.

## `pyfs-qa`

Tier 2 and 3 evidence tooling for the pyflightstream command database; probes run FlightStream locally and need a licensed machine.

```text
usage: pyfs-qa [-h] {probe,apply-compat,physics,drift,cases,cost,update-reference}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-qa probe`: run command-validity probes and write the compat report
- `pyfs-qa apply-compat`: promote database statuses from a committed compat report
- `pyfs-qa physics`: run the physics matrix of a workspace, reduce its records and write the physics report
- `pyfs-qa drift`: run the physics matrix on two builds, each under its own registry, and diff the two reductions
- `pyfs-qa cases`: print the Tier 3 test matrix: one line per registered case id, nothing runs
- `pyfs-qa cost`: report wall-time cost per sim and point from a campaign manifest, one column per solver build; reads runs.json and runs nothing
- `pyfs-qa update-reference`: update or seed one physics reference from a committed physics report

### `pyfs-qa probe`

```text
usage: pyfs-qa probe [-h] --fs-version FS_VERSION --fs-exe FS_EXE [--commands COMMANDS] [--identity-only] [--fsm FSM] [--workroot WORKROOT] [--timeout TIMEOUT] [--report-dir REPORT_DIR] [--label LABEL]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--fs-version` | `FS_VERSION` |  | target FlightStream version: canonical identifier (for example 26.120); a vendor release name works only where it names exactly one registered build Required. |
| `--fs-exe` | `FS_EXE` |  | explicit path of the FlightStream executable (never guessed) Required. |
| `--commands` | `COMMANDS` |  | comma-separated subset to probe; default: every command with a probe spec |
| `--identity-only` |  |  | judge no command: run the baseline, capture the solver's identity banner, and write the report pair. This is how a newly registered build gets its build number into a committed report, which is the only place the version registry accepts one from |
| `--fsm` | `FSM` |  | local simulation (.fsm) file for prelude tiers above none; specs needing it are recorded unprobed when absent |
| `--workroot` | `WORKROOT` | `runs/probes` | scratch root for probe scripts and logs (default from the qa.scratch_root option: runs/probes/, not committed) |
| `--timeout` | `TIMEOUT` | `120.0` | per-probe wall-clock limit, seconds (default from the qa.probe_timeout_s option) |
| `--report-dir` | `REPORT_DIR` | `reports/compat` | directory receiving the compat report pair (default reports/compat/) |
| `--label` | `LABEL` |  | report stem suffix distinguishing several reports on one day |

### `pyfs-qa apply-compat`

```text
usage: pyfs-qa apply-compat [-h] [--root ROOT] [--commands-dir COMMANDS_DIR] report
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<report>` |  |  | the compat report YAML file |
| `--root` | `ROOT` | `.` | repository root; the report is cited relative to it, and the promotions go into its src/pyflightstream/commands (default.) |
| `--commands-dir` | `COMMANDS_DIR` |  | chapter YAML directory to promote into, under --root; default &lt;root>/src/pyflightstream/commands |

### `pyfs-qa physics`

```text
usage: pyfs-qa physics [-h] [--workspace WORKSPACE] [--matrix MATRIX] [--name NAME] [--resume] [--report-dir REPORT_DIR] [--label LABEL]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--workspace` | `WORKSPACE` | `.` | the campaign workspace holding inputs/ and the physics matrix at its root (default: the current directory); tests/tier3_licensed is this repository's |
| `--matrix` | `MATRIX` | `matriz_physics.fs` | the matrix file name at the workspace root (default matriz_physics.fs); every active row fills FS_BUILD with one build id, which the report names |
| `--name` | `NAME` |  | campaign name; without it the workspace directory's name is the campaign's, as pyfs-matrix run names it, so a resumed run finds the points it recorded |
| `--resume` |  |  | skip points already in the manifest and run the rest; on a workspace whose matrix already ran this executes nothing and reports what was recorded. Without it an already-recorded point refuses before anything executes |
| `--report-dir` | `REPORT_DIR` | `reports/physics` | directory receiving the report pair (default reports/physics/) |
| `--label` | `LABEL` |  | report stem suffix distinguishing several reports on one day |

### `pyfs-qa drift`

```text
usage: pyfs-qa drift [-h] [--workspace WORKSPACE] [--matrix MATRIX] --fs-versions FS_VERSIONS --fs-exe VERSION=PATH [--name NAME] [--workroot WORKROOT] [--report-dir REPORT_DIR] [--label LABEL]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--workspace` | `WORKSPACE` | `.` | the campaign workspace whose inputs/ library and physics matrix both sides copy (default: the current directory) |
| `--matrix` | `MATRIX` | `matriz_physics.fs` | the matrix file name at the workspace root (default matriz_physics.fs) |
| `--fs-versions` | `FS_VERSIONS` |  | two comma-separated versions, baseline first (for example 26.100,26.120); the same version twice is the degenerate self-comparison Required. |
| `--fs-exe` | `VERSION=PATH` |  | explicit executable per version (repeatable, never guessed), for example --fs-exe 26.100=C:/fs26100/FS.exe Required. |
| `--name` | `NAME` |  | campaign name of both sides; without it the workspace directory's name |
| `--workroot` | `WORKROOT` | `runs/drift` | where the two side workspaces are made, a_&lt;build> and b_&lt;build>, each a copy of the library with an overlay registry naming that side's executable (default from the qa.scratch_root option: runs/drift/); a side that exists is refused, a drift being two fresh runs |
| `--report-dir` | `REPORT_DIR` | `reports/physics` | directory receiving the report pair (default reports/physics/) |
| `--label` | `LABEL` |  | report stem suffix distinguishing several reports on one day |

### `pyfs-qa cases`

```text
usage: pyfs-qa cases [-h] [--include-smi]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--include-smi` |  |  | include the SMI local-geometry class; like the runs, it never appears implicitly |

### `pyfs-qa cost`

```text
usage: pyfs-qa cost [-h] [--compare BASELINE,CANDIDATE] campaign
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<campaign>` |  |  | campaign root whose runs.json is read; no solver is started |
| `--compare` | `BASELINE,CANDIDATE` |  | two build column labels, baseline first, as the table's own header spells them; only the points both builds timed are compared |

### `pyfs-qa update-reference`

```text
usage: pyfs-qa update-reference [-h] --from-report FROM_REPORT --reason REASON [--root ROOT] [--references-dir REFERENCES_DIR] [--drop METRIC] case
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<case>` |  |  | case identifier, for example PHY-01 |
| `--from-report` | `FROM_REPORT` |  | committed physics report YAML carrying the measured values Required. |
| `--reason` | `REASON` |  | why the reference moves; recorded in the reference file (required) Required. |
| `--root` | `ROOT` | `.` | repository root; the report is recorded relative to it (default.) |
| `--references-dir` | `REFERENCES_DIR` |  | reference directory to write; default the package's qa/references/ |
| `--drop` | `METRIC` | `[]` | a reference metric the report does not carry, removed deliberately; repeatable |
