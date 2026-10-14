# Probes

Probe geometry is configured in the post-processing input and sampled by the
solver during execution. Post-processing reads the recorded samples. Probe products can support steady, unsteady, and far-field
analyses. Keep probe definitions in one place and link workflow-specific
instructions here.

The probe table and its parameters are defined in
[the probes product definition](definitions/the-probes-table.md). The
[sampled-field example](examples/sampled_field_export.md) shows a complete
export route. The [far-field planning rules](definitions/the-far-field-family.md#what-the-plan-adds)
distinguish package-added points inside the body, which are refused, from
user-declared points inside it, which are kept with a warning.
