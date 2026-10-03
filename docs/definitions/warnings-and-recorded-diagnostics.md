## Warnings and recorded diagnostics

Postprocessing warnings are quiet in command-line runs by default. This applies
to every warning category; errors, progress and the final command status remain
visible. Pass `--pproc-warnings` to `pyfs-matrix run`, `post` or `collect` to
show concise category counts and the detailed log location on stderr.

Every postprocessing stage records all its warnings and skipped products in
`post.log` and `post.log.json`, including category, severity, point, product,
message and any stated remedy. Python callers retain ordinary warning-filter
behavior. Terminal presentation does not change product values or CSV bytes.

`pyfs-matrix post <matrix> --workspace <root> --diagnostics` prints a complete
Markdown report of the saved logs. It reports their timestamps and package
versions and states explicitly when no saved log exists. It does not rerun
postprocessing or write products, guides, manifests or archives. A malformed log
is an error, not a clean diagnostic result. Capture stdout to save the report;
the CLI outcome signature stays on stderr.
