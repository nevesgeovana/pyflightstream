# python -m pyflightstream.workspace.excel

Generated from the argument parser at build time, so this page and `python -m pyflightstream.workspace.excel --help` cannot disagree. The entry point is `pyflightstream.workspace.excel:main`.

## `python -m pyflightstream.workspace.excel`

Create the optional workbook without launching Excel or changing trust settings.

```text
usage: - [-h] {create,preview,apply,cancel,check}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `python -m pyflightstream.workspace.excel create`: Create a new macro-free workbook
- `python -m pyflightstream.workspace.excel preview`: Inspect changes without applying them
- `python -m pyflightstream.workspace.excel apply`: Apply one fresh reviewed batch
- `python -m pyflightstream.workspace.excel cancel`: Cancel a preview without changing inputs
- `python -m pyflightstream.workspace.excel check`: Validate Runs and Dictionary

### `python -m pyflightstream.workspace.excel create`

```text
usage: - create [-h] --workspace WORKSPACE output
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<output>` |  |  |  |
| `--workspace` | `WORKSPACE` |  |  |

### `python -m pyflightstream.workspace.excel preview`

```text
usage: - preview [-h] --workspace WORKSPACE --direction {read,write} --batch BATCH [--matrix MATRICES] workbook
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<workbook>` |  |  |  |
| `--workspace` | `WORKSPACE` |  |  |
| `--direction` | one of `read`, `write` |  |  |
| `--batch` | `BATCH` |  |  |
| `--matrix` | `MATRICES` |  |  |

### `python -m pyflightstream.workspace.excel apply`

```text
usage: - apply [-h] batch
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<batch>` |  |  |  |

### `python -m pyflightstream.workspace.excel cancel`

```text
usage: - cancel [-h] batch
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<batch>` |  |  |  |

### `python -m pyflightstream.workspace.excel check`

```text
usage: - check [-h] workbook
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `<workbook>` |  |  |  |
