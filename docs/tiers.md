# Test tiers and licensed tests

Choose the tier by the evidence the change needs.

| Folder | Needs | What it checks |
|---|---|---|
| `tests/tier1_offline` | Package and development dependencies | Parsers, command database, script generation, refusal paths and synthetic fixtures |
| `tests/tier2_validity` | A licensed solver and explicit run authorization | Command behavior on a named solver build |
| `tests/tier3_licensed` | A licensed solver and prepared synthetic workspace | Workflow outputs and physical comparisons |

The default pytest selection excludes `needs_flightstream` tests. Offline
success does not establish solver behavior or physical validity. Use the
package markers in `tests/tier1_offline/packages.json` for focused offline runs; see
[Contributing](contributing.md) for setup and checks.

## Prepare the licensed workspace

The tier-3 workspace follows the ordinary [workspace layout](workspace-and-workflows.md).
Its committed matrices, reference files, setups and post-processing profiles
define the scenarios. Geometry preparation requires the licensed solver;
follow the preparation module's help and retain its provenance records.
Only synthetic geometry belongs in this test workspace.

Write machine-specific executable paths in the gitignored
`tests/tier3_licensed/inputs/executables.local.toml`. Match the build IDs
to each matrix's `FS_BUILD` cells. Never commit machine paths or licensed
outputs.

## Run and inspect

Planning runs offline; running the matrix consumes a solver seat.

```text
pyfs-matrix plan matriz.fs --workspace tests/tier3_licensed
pyfs-matrix run matriz.fs --workspace tests/tier3_licensed
pytest -m needs_flightstream tests/tier3_licensed
```

The tests read the manifest and products recorded by those runs. Read each
test's prerequisites before selecting it. A missing licensed result is not
an offline pass.

The offline tier also checks planned tier-3 scripts against committed
goldens. Regenerate only when the expected script change has been reviewed:

```text
python -m tests.tier3_licensed.offline
python -m tests.tier3_licensed.offline --write
```

For physical comparisons, use the committed case references and their
declared bands. Record solver build, input identity and provenance with
the result. A command compatibility measurement and a physical validation
measurement answer different questions.
