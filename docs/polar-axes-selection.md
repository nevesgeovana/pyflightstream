# Select the polar force axes

Set `polar_axes = "wind"` or `polar_axes = "stability"` in the pproc's
`[products]` table. Ordinary steady and unsteady polar tables then include
`CD`, `CY` and `CL` in that frame, with a `polar_axes` column stating the choice.
The existing body, stability and wind columns remain explicitly labelled.
Absent this setting, no selected-axis columns are added.

This is a force-coordinate choice, not the deferred stability-derivatives toolbox.
