# Reports

Five series, and they are corrected in different ways.

`RPT-nnn_<topic>_<date>.md` are NARRATIVE reports: a person writing
down what a run showed. They are AMENDABLE, and an amendment is
recorded in the title line (`RPT-024 ... (2026-08-09, amended
2026-08-10)`) and, where it retracts something, in the body at the
point it retracts. A reader must be able to see that the file moved
without reading the history.

`compat/CMP-*`, `physics/PHY-*` and `physics/DRF-*` are MACHINE-WRITTEN
evidence and are never overwritten or edited. They are superseded by a
new dated report, or corrected by an erratum beside them; each
directory's own README states its rule. The drift series `DRF-*` was
missing from this sentence until 2026-08-18, which left the
never-edited rule reading as though it did not cover the reports the
cross-version comparison writes. It always did.

`physics/TRI-*` are TRIAGE notes: a disposition of one verdict a
machine-written report recorded, written by a person and citing the
reports it reasons over. They are narrative in the sense above, so they
are amendable and say so when amended, and they never change the
measurement they discuss.

AN ERRATUM IS AMENDED THE WAY A NARRATIVE REPORT IS, which was not
written anywhere until 2026-08-18 and was being relied on before it
was. An erratum is a person's account of a defect, not a measurement,
so it may be corrected in place under the rule above: the title line
records the amendment, and the body records it at the point it
retracts something. What an erratum may never do is change the report
it corrects.

The difference is not ceremony. A narrative report is an argument and
an argument may be corrected in place as long as it says so; a
machine-written report is a measurement, and editing one would change
what a citation elsewhere in the tree resolves to.

## Reports in preparation

These identities extend the existing product series; they do not indicate
acceptance or publication of their findings.

| Identity | Subject | State |
| --- | --- | --- |
| [RPT-081](RPT-081_typed-boundary-and-base-region-operations_2026-09-27.md) | Typed boundary and base-region operations: measured state and effects | Bounded evidence; final release review pending |
| [RPT-082](RPT-082_cad-units-and-custom-inflow-coverage_2026-09-27.md) | CAD units, geometry transforms and custom inflow coverage | Bounded evidence; final release review pending |
| [RPT-083](RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md) | Probe frames, temporal surfaces and walltime export limits | Bounded evidence; final release review pending |
| [RPT-085](RPT-085_native-workspace-evidence_2026-09-27.md) | Native mesh routes, sampled-volume conversion, inlet and actuator controls | Bounded evidence; final release review pending |
| [RPT-086](RPT-086_gui-launch-windows_2026-09-28.md) | The windows 26.124 shows when launched with its GUI: the startup splash asks nothing | Bounded evidence; final release review pending |
| [RPT-087](RPT-087_periodic-native-tecplot-one-zone-per-copy_2026-09-28.md) | A periodic row's native Tecplot holds one zone per copy, each equal to its VTK block | Bounded evidence; final release review pending |
| [RPT-088](RPT-088_26124-unsteady-log-without-a-completion-line_2026-09-28.md) | A 26.124 unsteady log ends without a completion line; every log reader judges it | Bounded evidence; final release review pending |
| [RPT-093](RPT-093_aeroelastic-coupling-on-26124_2026-09-29.md) | The Aeroelastic Coupling Toolbox on 26.124: nine measured facts about the surface-ID mapping, the rotor morph, the RBF kernels and the exports | Bounded evidence; final release review pending |

## Dependency evidence

- [RPT-084: optional Excel extra license evidence](RPT-084_excel-extra-license_2026-09-27.md): XlsxWriter 3.2.9 installed metadata and exact license hashes.
