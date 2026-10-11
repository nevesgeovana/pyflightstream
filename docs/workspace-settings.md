# The workspace settings files

`pyfs.toml` and `pyfs.local.toml` state, once for a workspace, the defaults of
the `pyfs-matrix` options a campaign types on every command: the version, the
HPC profile, the cost file, the acceptance of the installed build and how much
the console says. With them, `pyfs-matrix plan polars.fs` and `pyfs-matrix run
polars.fs` typed without those options give the plan and the run the options
would give, and an option typed on one command still wins (FR-436).

## The two files

The workspace is the folder `--workspace` names, or the current directory when
the option is absent.

| file | where | meant to be |
|---|---|---|
| `pyfs.toml` | the workspace root | versioned with the workspace |
| `pyfs.local.toml` | beside `pyfs.toml` | this machine's overlay, kept out of version control as `inputs/executables.local.toml` is |

Either file may exist without the other. `pyfs.local.toml` is read over
`pyfs.toml` key by key. `--workspace` is never a key of either file, because
it is what locates them. A workspace without either file runs exactly as it
does without this support.

Each file holds an optional `schema_version = 1`, a `[defaults]` table and a
`[log]` table, and nothing else:

```toml title="pyfs.toml"
schema_version = 1

[defaults]
fs_version = "26.124"
cost_file = "c001"
accept_unregistered_build = true

[log]
console = "quiet"
```

```toml title="pyfs.local.toml"
[defaults]
hpc = "h001"
```

## What a file may set

A key of `[defaults]` is a long option without its leading dashes, inner
dashes written as underscores (`--cost-file` is `cost_file`). It applies to
every command that takes that option and is left unused by a command that
does not. Each value has the type its option takes.

| table | keys |
|---|---|
| `[defaults]` | `fs_version`, `hpc`, `cost_file`, `runs`, `accept_unregistered_build`, `fs_exe`, `point_name`, `recipe`, `workflow`, `ignore_missing_families`, `check_frozen`, `progress_every`, `local` |
| `[log]` | `console` (`"quiet"`, `"normal"` or `"verbose"`), `pproc_warnings` |

Each of these is refused before any work, with a message naming the key (or
the parse error) and the file; nothing is written in the workspace and the
command exits non-zero:

- a key that acts on one invocation: `apply`, `yes`, `overwrite`, `resume`,
  `force_rerun`, `force_rerun_all`, `discard_walltime`, `sims`, `points`,
  `no_post`, `update_ids`, `watch`, `rounds`, `from_sims`;
- a key no command takes, a misspelling among them, and `workspace`;
- a table other than `[defaults]` and `[log]`;
- a value of the wrong type, and a `console` value outside the three levels;
- a `schema_version` other than 1;
- a file that is not valid TOML.

## Which value wins

For each option of a command:

1. the option typed on the command line;
2. else the value in `pyfs.local.toml`;
3. else the value in `pyfs.toml`;
4. else the package default.

A value option typed on the command line replaces the files' value for that
command. Every boolean a file can set has a `--no-` form on each command that
takes the option, which sets it to false for that command whatever the files
say: `--no-accept-unregistered-build`, `--no-check-frozen`, `--no-local`,
`--no-pproc-warnings` and `--no-ignore-missing-families`. Typing an option and
its `--no-` form on one command is refused by the parser.

## The console level

Every command that takes `--verbose` also takes `--log-level quiet|normal|verbose`,
and `[log] console` sets the same level for the workspace. `--verbose` is
`--log-level verbose`; typing `--verbose` with `--log-level` naming another
level is refused by the parser.

| level | the console shows |
|---|---|
| `quiet` | the errors, the final summary line and the package signature |
| `normal` | the default console |
| `verbose` | the detailed console, and before the work every value taken from a file with the file it came from |

The package signature prints at every level, and `logs/activity.log` keeps its
full detail at every level: the same command at the three levels writes the
same activity log apart from its times.

## Accepting an unregistered build

A run whose installed build differs from the registered one is refused unless
the build is accepted. It is accepted by any of three routes:

- `--accept-unregistered-build` typed on the command;
- the workspace acceptance: `accept_unregistered_build = true` in `[defaults]`,
  once `pyfs.local.toml` is overlaid on `pyfs.toml` (so a `false` in
  `pyfs.local.toml` withdraws a `true` in `pyfs.toml`);
- the entry acceptance: `accept_unregistered_build = true` on the table-valued
  build entry of `inputs/executables.local.toml` that the row selects, which
  accepts the installed build of that entry only; a row naming another version
  whose installed build differs is still refused.

```toml title="inputs/executables.local.toml"
"26.124" = { path = "C:/builds/26124/FlightStream.exe", version = "26.124", accept_unregistered_build = true }
```

`--no-accept-unregistered-build` typed on a command refuses whatever the files
state. In `inputs/executables.toml` the key is refused, naming the key and the
file. However it is stated, the run warns on every run exactly as the option
does, naming where the acceptance came from.

## What the plan and the records say

`plan.json` and every run record carry `settings_sources`, an object mapping
each option whose value was taken from a file to the file that supplied it,
`"pyfs.toml"` or `"pyfs.local.toml"`. Its key `accept_unregistered_build` names
the source of the acceptance: `"pyfs.toml"`, `"pyfs.local.toml"`,
`"executables.local.toml"` or `"typed"`. When more than one route accepts, the
source is the first that accepts of: typed, the workspace acceptance, the
entry. For example:

```json
"settings_sources": {
  "accept_unregistered_build": "executables.local.toml",
  "cost_file": "pyfs.toml",
  "hpc": "pyfs.local.toml"
}
```

The object is absent when no value and no acceptance came from a file; a value
typed on the command line or left at the package default is recorded as it is
without the files. The acceptance itself is recorded in `plan.json` and the
run records as it is when the option is typed, so a plan still rehearses the
command line its run executes.

## `pyfs-workspace`

`pyfs-workspace` reads the same two files under the same refusals and takes
from them the console level of `[log]` only; no key of `[defaults]` reaches any
of its commands.
