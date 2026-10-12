# Probes

Probe geometry is configured in the post-processing input and sampled during
post-processing. Probe products can support steady, unsteady, and far-field
analyses. Keep probe definitions in one place and link workflow-specific
instructions here.

The probe table and its parameters are defined in
[the probes product definition](definitions/the-probes-table.md). The
[sampled-field example](examples/sampled_field_export.md) shows a complete
export route. Probe locations inside the body are invalid and are rejected
during planning when geometry information is available.
