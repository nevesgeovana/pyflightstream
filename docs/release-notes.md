# Release notes

## 0.42.0 - 2026-10-16

This release reorganises the documentation site around Workspace CLI, Python API,
Reference and Understanding pyflightstream, restructures the requirements specification,
and validates command arguments before a script is written. Positional calls of the
fsi section functions and the positional ids of `delete-sims` are deprecated and are
removed in 0.43.0; use keyword arguments and `--sims`. The changelog records the full scope.

## 0.41.0 - 2026-10-15

Python 3.12 or newer is required. The registered FlightStream builds are
25.000, 25.100, 26.000, 26.100, 26.101 and 26.120 through 26.125. See
[builds](builds.md) for vendor names, support levels and the evidence boundary.

This release consolidates workspace migration, removes authored campaign-file
loading, and makes the matrix the campaign declaration route. It also corrects
user guidance and retires the unused `cases.point_tag` naming helper; current
point naming uses `point_name(case, point)`. The changelog records the full scope.

The [changelog](https://github.com/nevesgeovana/pyflightstream/blob/main/CHANGELOG.md)
records the changes from 0.38.0 onward. Earlier release notes remain in the
corresponding Git tags.

Before updating an existing workspace, read [Upgrading](upgrading.md).
It is the single home for format changes, affected products and migration
instructions.
