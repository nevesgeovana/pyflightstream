## The per-step series

<a id="series"></a>

`series/<point>_loads_series.csv`, `series/<point>_sections_series.csv` and
`series/<point>_probes_series.csv`, one table per export kind of a point whose matrix row states
`EXPORT_UNSTEADY_AFTER_REV` or `EXPORT_UNSTEADY_AFTER_ITER`. From the stated threshold on the
solver exports its loads, sectional loads and probe points on every step, each file stamped
`_iteration=<N>`; the post tables the stamped files of the point's export window, so that a
folder of stamped spreadsheets becomes one table per kind. A kind the run did not export has no
file. The native surface, Cp and Tecplot files of the window stay where the solver wrote them and
are listed in [`products.json`](products-json.md), which also states the unit and the frame of every
column.

Every table opens with the lead columns below, then the run block
([the run block](../definitions/the-run-block.md#the-run-block)), then the columns of its kind.
`time_s` and `azimuth_deg` come from the clock the run record carries (the step's time in s and
the unwrapped azimuth of the clock rotor in degrees), and are empty where the record states no
clock.

| Table | Lead columns | Columns after the run block |
| --- | --- | --- |
| loads | `STEP`, `time_s`, `azimuth_deg` | one column per surface and coefficient, `<SURFACE>_<COEFFICIENT>`, for every surface of the export and `Total`: `Cx`, `Cy`, `Cz`, `CL`, `CDi`, `CDo`, `CMx`, `CMy`, `CMz` (`CDp`, `CDv` in the place of `CDi`, `CDo` on a build that prints them), all dimensionless, in the solver's export frame |
| sections | `STEP`, `time_s`, `FAMILY`, `PLANE`, `ROTOR`, `AZIMUTH` | `Offset`, `Chord`, `X_QC`, `Z_QC` in the model length, `Fx`, `Fz` and `Moment` as the sectional export prints them; one row per step and section |
| probes | `STEP`, `time_s`, `azimuth_deg`, `PROBE` | the columns of the probe export, in its units and order; `PROBE` numbers the probe from one, in the export's order; one row per step and probe |

A series is one column set over every step: a step that prints other surfaces, drag-split names or
probe columns than the first stamped step is refused, naming the file, and the steps of one build
are posted together. A step that `free-space` deleted from the simulation is a named refusal, never
a silent gap.
