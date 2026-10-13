# pyfs-fsi

Generated from the argument parser at build time, so this page and `pyfs-fsi --help` cannot disagree. The entry point is `pyflightstream.fsi.cli:main`.

## `pyfs-fsi`

FSI coupling executable for the FlightStream Aeroelastic Toolbox. Called with no arguments it executes one coupling step in the current directory (coupled with config.json, dummy only when configured).

```text
usage: pyfs-fsi [-h] {init-dummy,step,external}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-fsi init-dummy`: write the dummy configuration into a run directory
- `pyfs-fsi step`: execute one coupling step explicitly
- `pyfs-fsi external`: run one coupling call of an external structural program: run it, archive and validate the call

### `pyfs-fsi init-dummy`

```text
usage: pyfs-fsi init-dummy [-h] --node-count NODE_COUNT [--out DIR | --dir LEGACY_DIR]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--node-count` | `NODE_COUNT` |  |  |
| `--out` | `DIR` | the current directory |  |
| `--dir` | `LEGACY_DIR` |  | deprecated alias of --out |

### `pyfs-fsi step`

```text
usage: pyfs-fsi step [-h] [--out DIR | --dir LEGACY_DIR]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--out` | `DIR` | the current directory |  |
| `--dir` | `LEGACY_DIR` |  | deprecated alias of --out |

### `pyfs-fsi external`

```text
usage: pyfs-fsi external [-h] [--out DIR | --dir LEGACY_DIR]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--out` | `DIR` | the current directory |  |
| `--dir` | `LEGACY_DIR` |  | deprecated alias of --out |
