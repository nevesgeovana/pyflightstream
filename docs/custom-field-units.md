# Custom-field units

A custom field defines global-frame coordinates and velocity components. It does not rotate with ALPHA, BETA, or a body transform. Nonzero ALPHA/BETA beside a custom field remains refused.

Use `FREESTREAM_UNITS: SI` beside `FREESTREAM: shear` in a matrix row when the source contains metres and metres per second. In Python, set `SimCase.freestream_units="SI"`. The builder prepares a separate solver input, scaling all six XYZ/VXYZ columns once for a measured METER or MILLIMETER simulation. For MILLIMETER the numeric factor is 1000; seconds do not change. The source stays byte-identical, and the physical vector and its orientation stay the same. The run hashes both files and their provenance record.

`FREESTREAM_UNITS: NATIVE` declares that all six columns already use the simulation's length unit, with velocity in that unit per second. Its bytes and path are preserved. Omitting the declaration keeps legacy file behavior; it does not infer SI from a filename or numerical range. Coverage of an undeclared MILLIMETER field is reported as unverified.

Explicit SI conversion currently accepts only METER and MILLIMETER. Unknown and other units are refused. The custom-file measurement applies to FlightStream 26.124 build 8172026. It does not imply that unsteady fluid-plot coordinates use the same units: their VERTEX argument was measured in metres independently of the simulation display unit.

STRUCTURED `.txt` inputs retain their two-count header; UNSTRUCTURED `.dat` inputs contain only six-column rows. Formatting of a prepared SI copy may change, but no interpolation, coordinate rotation, or automatic installation of an exported field occurs. Select a reusable SI field explicitly.

The [SI custom-field example](examples/prepare_custom_field.md) prepares a MILLIMETER input from an SI source without launching a solver.

Migration: existing undeclared files are not rewritten or upgraded. Add the SI declaration only after checking the source's actual unit contract. A field changed after preparation is refused before the solver starts.

After geometry transforms are emitted, the run records a conservative body and full-rotor-sweep envelope. A grid-bounds exceedance warns; partial selections may overestimate the occupied region. The `within-grid-bounds` result only compares external YZ bounds and does not certify interior interpolation support. Raw commands, unknown placements or unavailable units leave the diagnostic explicitly unknown. Continuation preserves the diagnostic only when geometry/motion evidence and the unit declaration remain unchanged.

See [RPT-082](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-082_cad-units-and-custom-inflow-coverage_2026-09-27.md) for the bounded uniform/shear and METER/MM controls, including preserved negative cases.
