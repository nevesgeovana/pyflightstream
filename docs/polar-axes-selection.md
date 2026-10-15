# Select the polar force axes

Set `polar_axes = "wind"` or `polar_axes = "stability"` in the pproc's
`[products]` table. Ordinary steady polar tables then include
`CD`, `CY` and `CL` in that frame, with a `polar_axes` column stating the choice.
The existing body, stability and wind columns remain explicitly labelled.
Absent this setting, no selected-axis columns are added.

Averaged unsteady polars retain each plot group's name. Their selected columns
are `selected_drag_coefficient_<group>`,
`selected_side_force_coefficient_<group>` and
`selected_lift_coefficient_<group>`, with the same `polar_axes` choice.
For example, the lift selection for `MRP_TOTAL` is
`selected_lift_coefficient_MRP_TOTAL`. Existing solver plot columns such as
`CL_MRP_TOTAL` retain their values. A selected-column name already used by an
existing column is refused before the table is changed.

This is a force-coordinate choice, not the deferred stability-derivatives toolbox.
