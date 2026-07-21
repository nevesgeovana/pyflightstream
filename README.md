# pyflightstream

Version-aware, didactic Python driver for the FlightStream panel-method solver.
Successor of the author's legacy research scripts. MIT licensed.

Status: pre-alpha, milestone M0 (repository skeleton). The package installs and
imports, but no functionality ships yet. See the milestone plan below.

## Why this package

FlightStream is scripted through an ASCII command file whose commands change
between solver versions, and not every change reaches the changelog. This
package makes the FlightStream version an explicit input: every command it
emits is validated against a per-version command database, and old versions
are only ever added, never dropped.

## What is each folder?

| Folder | Purpose in plain language |
|---|---|
| `src/pyflightstream/` | The package itself, one subpackage per pipeline stage |
| `src/pyflightstream/commands/` | The command database: what exists in which FlightStream version, with manual page citations |
| `tests/` | Tier 1 tests, runnable anywhere, no FlightStream needed |
| `reports/` | Committed evidence from licensed machines: which commands actually work (compat) and physics regression results |
| `docs/` | Documentation source (mkdocs) |
| `examples/` | Runnable example scripts in percent format |
| `.claude/skills/` | Maintenance procedures (version updates, command additions, QA runs, releases) |
| `_private/` | Local only, never committed: FlightStream manuals and research geometry |

## Supported FlightStream versions

Planned at launch: 26.000, 26.100, 26.120 (canonical 26.XXX scheme; the last
digit indexes vendor hotfix builds). The ordered list in
`src/pyflightstream/commands/_meta.yaml` is the only ordering authority.

## Development setup

```
pip install -e .[dev]
pre-commit install
pytest
```

Tier 2 (command validity probes) and Tier 3 (physics regression) require a
local FlightStream license and are documented in CONTRIBUTING.md.

## Milestones

M0 skeleton (this) > M1 command database > M2 builder, runner, parser >
M3 compat report > M4 physics cases > M5 docs and example > v0.1.0 (private).

## License

MIT. Contributions must be original or MIT-compatible; code derived from the
AGPL pyFlightscript package is not accepted. See CONTRIBUTING.md.
