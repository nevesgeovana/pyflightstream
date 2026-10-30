# Compat report: the CCS export sequence on FlightStream 26.127 (2026-10-30)

Tier 2 evidence for FR-3407, gathered beside the 26.127 probe campaigns
(CMP-26127_2026-10-30_probe-campaign and -fsm). The question: do the 26.12
CCS exports need the selected curves assigned to the CCS component before
they write a file, as the vendor's example scripts of 2026-10-30 show? The
CCS export defect reported to the vendor on 26.124 and 26.125 (both exports
failed on a model opened with its curves) is the case this answers.

## Setup

| Item | Value |
|---|---|
| Executable | Flightstream_2612.exe of the 26.127 package (sha256 withheld; build 10282026, local, never committed) |
| Executor | `-hidden -script`, one solver at a time, five scripts in series |
| Models | the vendor's two test models of 2026-10-30, a straight NACA 0012 wing and a transport fuselage, each saved with its CCS curves; local, never committed |
| Instrument | each script opens the model, selects every curve (`CAD_CREATE_CURVE_SELECT -1`), optionally assigns them, and brackets the export with `PRINT` and `EXPORT_LOG` sentinels as `pyfs-qa probe` does; the END log shows script processing continued past the export, the CSV shows the export wrote its file |
| Solver identity | Simcenter Flightstream version 2612, build #10282026 |

## Evidence

| Case | Assignment before the export | Export line | END log | CSV bytes |
|---|---|---|---|---|
| wing | `ASSIGN_SELECTED_CURVES_TO_CCS_WING` | `EXPORT_WING_CCS_FILE Wing TRUE BLUNT OPEN C2 C0` | yes | 12744 |
| wing, control | none | the same | yes | no file |
| fuselage, the page's four-token form | `ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE` | `EXPORT_FUSELAGE_CCS_FILE fuselage CLOSED C2 C0` | yes | 636237 |
| fuselage, control | none | the same | yes | no file |
| fuselage, the heading's six-token form | `ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE` | `EXPORT_FUSELAGE_CCS_FILE fuselage TRUE SHARP CLOSED C2 C0` | yes | 636237 |

Every run exited with return code 0 and no error line between the sentinels.

## Reading

On 26.127 a CCS export writes its file only after the selected curves are
assigned to the component. Without the assignment the export fails
SILENTLY: the script runs on, the log carries no error, and no file
appears, which is why a probe that checks only for an abort cannot see it.
The fuselage export accepts both the four-token form the page's sample
prints and the six-token form of its heading, and writes the same file.

The package already writes the selection and the assignment before every
CCS loft and export on the builds whose command database carries the
assignment command (26.125, 26.126 and 26.127, the command verified on each
by its own probe campaign); 26.127 gets it through its registration
(FR-3406). The tier-1 test
`test_p0520_a_ccs_export_follows_the_select_and_assign_step` pins the order
on 26.126 and 26.127.
