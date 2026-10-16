# SMI references on 26.124 build 8172026 without the vorticity-drag selection

Date: 2026-10-16. Node PFS-2006.02.01. Machine-readable twin:
`PHY-26124_2026-10-16_smi-no-vorticity-selection.yaml`.

The session accepted these values as the replacement reference physics. They come from the
licensed namespace `6bad1dac664ef7b0959e683749f4b1f437af6033-e86a7806af7e4d4c8a255d3be9a29d47`
of GEO-105 release 0.42.0 (`analysis.json`, `loads_totals`), read from the Total row of the
exported loads at the printed 0.0001 step. SMI-01 and SMI-02 identify the package's local-only
cases; private geometry names and paths are omitted.

## What changed and why

`qa.physics.build_smi_script` no longer puts every boundary, bodies included, on the vorticity
induced-drag list. On the same build the paired run with the old form differs from the run
without it only in CDi (and Cx, Cz): CL and the three moments are unchanged. So the stored
coefficients move by the selection delta, and by build drift for the part that the old
references (26.120 build 7012026, 2026-07-21) carry.

## Delta against the values made with the old form (same build, 26.124 build 8172026)

| Case | Coefficient | Old form | No selection | Delta |
|---|---|---:|---:|---:|
| SMI-01 | CL | -0.0188 | -0.0188 | 0.0000 |
| SMI-01 | CDi | 0.0030 | 0.0827 | 0.0797 |
| SMI-01 | CDo | 0.1276 | 0.1276 | 0.0000 |
| SMI-01 | CMy | -1.7699 | -1.7699 | 0.0000 |
| SMI-02 | CL | 12.1102 | 12.1102 | 0.0000 |
| SMI-02 | CDi | 0.2235 | 0.3814 | 0.1579 |
| SMI-02 | CDo | 0.4124 | 0.4124 | 0.0000 |
| SMI-02 | CMy | -116.5198 | -116.5198 | 0.0000 |

## Delta of the stored references (the values this commit replaces)

| Case | Coefficient | Reference of 26.120 build 7012026 | New reference | New minus old |
|---|---|---:|---:|---:|
| SMI-01 | CL | -0.0174 | -0.0188 | -0.0014 |
| SMI-01 | CDi | 0.0030 | 0.0827 | 0.0797 |
| SMI-01 | CDo | 0.1305 | 0.1276 | -0.0029 |
| SMI-01 | CMy | -1.7843 | -1.7699 | 0.0144 |
| SMI-02 | CL | 12.1368 | 12.1102 | -0.0266 |
| SMI-02 | CDi | 0.2244 | 0.3814 | 0.1570 |
| SMI-02 | CDo | 0.4229 | 0.4124 | -0.0105 |
| SMI-02 | CMy | -116.6897 | -116.5198 | 0.1699 |

The bands of the references are kept as curated (`update_reference` keeps them).

## Convergence

SMI-01 stops at iteration 25 with a pressure residual of 1.0403e-9, and SMI-02 at iteration 95
with residuals 5.6227e-6 and 9.4962e-7, both well under the 500-iteration limit of the case
and below its 1e-5 criterion where the log prints a value; the velocity residual of SMI-01
prints as stars and is not a numerical measurement. The logged iteration coefficients are those
of the old selection in both arms, because the selection is issued after the solve; the exported
Total row is the value used here.

## Disclosure owed (DOC)

docs/tiers.md (PFS-2006.02) must name the no-selection form and this report as the accepted
source of the SMI references.
