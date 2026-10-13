# pyfs-manual

Generated from the argument parser at build time, so this page and `pyfs-manual --help` cannot disagree. The entry point is `pyflightstream.utils.cli:main`.

## `pyfs-manual`

Read a FlightStream manual and compare it against the command database. The manual is licensed vendor material: pass its path explicitly, it is never guessed, and nothing from it is copied into anything this writes.

```text
usage: pyfs-manual [-h] {coverage,draft,sweep,surface,citations,register}...
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |

Subcommands:

- `pyfs-manual coverage`: report what the manual documents and the database does not
- `pyfs-manual draft`: render database entries for the absent commands, for review
- `pyfs-manual sweep`: read every manual edition and report what no entry covers, and what an edition documents that its own build cannot emit
- `pyfs-manual surface`: report the command surface of each edition and what changed between builds
- `pyfs-manual citations`: re-read the database's page citations against the manuals they name
- `pyfs-manual register`: write documented rows for a new edition, where the documentation did not change

### `pyfs-manual coverage`

```text
usage: pyfs-manual coverage [-h] --manual MANUAL --source SOURCE --chapter-pages FIRST-LAST [--index-pages FIRST-LAST]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--manual` | `MANUAL` |  | path of the manual pdf Required. |
| `--source` | `SOURCE` |  | citation id, for example "SRC-741" Required. |
| `--chapter-pages` | `FIRST-LAST` |  | page range of the scripting reference, one-based inclusive Required. |
| `--index-pages` | `FIRST-LAST` |  | page range of the Script Index, one-based inclusive. Optional: without it the report carries no section labels, which is what an edition with no index gets |

### `pyfs-manual draft`

```text
usage: pyfs-manual draft [-h] --manual MANUAL --source SOURCE --chapter-pages FIRST-LAST [--index-pages FIRST-LAST] --fs-version CANONICAL [--only ONLY] [--out OUT] [--write]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--manual` | `MANUAL` |  | path of the manual pdf Required. |
| `--source` | `SOURCE` |  | citation id, for example "SRC-741" Required. |
| `--chapter-pages` | `FIRST-LAST` |  | page range of the scripting reference, one-based inclusive Required. |
| `--index-pages` | `FIRST-LAST` |  | page range of the Script Index, one-based inclusive. Optional: without it the report carries no section labels, which is what an edition with no index gets |
| `--fs-version` | `CANONICAL` |  | canonical version the drafted entries are documented for; repeatable Required. |
| `--only` | `ONLY` |  | substring filter on the command name, for drafting one family at a time |
| `--out` | `OUT` |  | destination file; required with --write, and named in the dry-run line without it |
| `--write` |  |  | actually write. Without it the draft is printed and nothing is touched, which is the default because a drafted entry is not evidence: it reproduces about three quarters of a hand-authored argument list and leaves the rest as '???' |

### `pyfs-manual sweep`

```text
usage: pyfs-manual sweep [-h] --editions MANIFEST [--by-section] [--fail-if-absent]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--editions` | `MANIFEST` |  | YAML manifest of the editions to read, one row per build, with page ranges written FIRST-LAST (see the example below). Never committed; it names licensed manual paths Required. |
| `--by-section` |  |  | group the absent commands by the section that documents them |
| `--fail-if-absent` |  |  | exit 1 when any command an edition documents cannot be emitted for that build, which subsumes a command with no entry at all. An edition whose label the registry cannot resolve does NOT fail it: nothing was measured there. Without the flag the sweep always exits 0, because a maintainer reading the report is the ordinary use |

### `pyfs-manual surface`

```text
usage: pyfs-manual surface [-h] --editions MANIFEST [--names] [--markdown]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--editions` | `MANIFEST` |  | YAML manifest of the editions to read, one row per build, in RELEASE order: consecutive rows are compared, so the order of the file decides which builds are neighbours Required. |
| `--names` |  |  | list the gained and lost command names, not only the counts. Applies to both renderings; without it a long history stays readable as counts alone |
| `--markdown` |  |  | render as markdown on standard output, to paste into a report under reports/. This subcommand writes no file: it judges nothing and has no evidence to place, unlike draft |

### `pyfs-manual citations`

Re-read every version-row page citation against the edition it names. EXITS 1 WHEN ONE DOES NOT HOLD, unlike sweep, whose findings are work remaining: a citation that does not hold is a statement already shipped. The report also says how many rows could be re-read at all, since most rows carry no page of their own and a count of editions would hide that.

```text
usage: pyfs-manual citations [-h] --editions MANIFEST
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--editions` | `MANIFEST` |  | YAML manifest of the editions to check against. A row the manifest does not carry is not checked and is not reported: the check is against a document, and without the document there is nothing to check Required. |

### `pyfs-manual register`

Compare a new edition against the one before it, command by command, and write a documented version row for every command both editions describe IDENTICALLY. The comparison is of what the edition SAYS (the signature's placeholders, the sample block and the parameter table), never of the page number: a local reflow moves a run of commands by a page without changing a word, and a page rule drops every one of them. Commands the new edition describes DIFFERENTLY are reported and never written: those are a reading somebody owes. Dry run by default.

```text
usage: pyfs-manual register [-h] --editions MANIFEST --fs-version CANONICAL [--commands-dir COMMANDS_DIR] [--write]
```

| Argument | Value | Default | What it does |
|---|---|---|---|
| `-h`, `--help` |  |  | show this help message and exit |
| `--editions` | `MANIFEST` |  | YAML manifest, in RELEASE order: the row before the target is the predecessor it is compared against Required. |
| `--fs-version` | `CANONICAL` |  | build to register, for example 26.123. It must be a row of the manifest AND a registered build, since the row it writes is keyed by the canonical identifier Required. |
| `--commands-dir` | `COMMANDS_DIR` |  | directory of chapter yaml files to edit; defaults to the installed command package. Point it at a copy to rehearse |
| `--write` |  |  | actually write the rows. Without it every row is printed and nothing is touched, which is the default because a row is a published claim about a build |
