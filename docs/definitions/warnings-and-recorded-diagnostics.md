## Warnings and recorded diagnostics

Postprocessing warnings are quiet in command-line runs by default, except for
accepted deprecated input keys, which name their replacements once. Errors,
progress and the final command status remain
visible. Pass `--pproc-warnings` to `pyfs-matrix run`, `post` or `collect` to
show concise category counts and the detailed log location on stderr.

For example, a pproc with `[products] superfile_format = "legacy_polar"` names
`polar_format` when `pyfs-matrix post --workspace study` reads it. Rename the
key to `polar_format`; the output format stays the same. The older
`trim_moment = "CMB25"` similarly names `CmB`. These input warnings also appear
when a Python caller reads the TOML file, using the ordinary default filters.
`PyflightstreamDeprecationWarning` derives from `FutureWarning` and
`PyflightstreamWarning`; filter that package category explicitly to suppress it.
`PYTHONWARNINGS` and `--warning-off` retain their chosen behavior. An old form
already removed is still refused by name.

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
