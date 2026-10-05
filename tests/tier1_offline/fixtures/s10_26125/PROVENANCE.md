`sweep_26.125.txt` and `probe_exponents_26.125.txt` are byte cuts of two solver
exports of the 26.125 probe campaign of 2026-10-05
(`reports/compat/CMP-26125_2026-10-05_probe-campaign.md`), run on the
package's own synthetic test blade (`30_BLADE.fsm` of the tier-3 inputs). The
addendum of 2026-10-05 of
`reports/RPT-160_flightstream-26125-registered-from-its-manual-and-its-outputs_2026-10-05.md`
quotes their header and data lines.

| Fixture | Source, relative to the campaign folder | Probe | sha256 of the source |
|---|---|---|---|
| `sweep_26.125.txt` | `shard1/26.125/SWEEPER_EXPORT_SPREADSHEET/sweep.txt` | `SWEEPER_EXPORT_SPREADSHEET` | `53b0da3610e4c939976257428354ab558ff91b98db2c65007a53ec5642d3fff1` |
| `probe_exponents_26.125.txt` | `shard1/26.125/EXPORT_PROBE_POINTS/probes.txt` | `EXPORT_PROBE_POINTS` | `5b57cf2ee3574001762d5b72a62c124293a6aa9dcf1c8730275f32556e38665b` |

Every line is the source's, whole and in order, with two changes:

- Line 8, `Simulation file:`, keeps the file name `30_BLADE.fsm` and drops the
  directory of the measuring machine in front of it.
- The solver ended every line with CRLF; the fixtures are LF, as
  `.gitattributes` pins every file under `tests/tier1_offline/fixtures/`.

Nothing else was cut, added or edited: the header block, the column header,
the data row, the footer and the value widths are as the solver printed them.
The other fixtures of this folder are not covered by this note.
