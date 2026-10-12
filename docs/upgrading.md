# Upgrading

## Which version are you on

Read the section for each release after the version used by the workspace, in
ascending order. Use `pyfs-matrix upgrade` to convert workspace layouts and
`pyfs-matrix rename` to update legacy names.

## 0.40.0

### Who is affected

All workspaces with post products created by an earlier release.

### What changes in a workspace

Integrated sectional loads now extend the first and last strip by half their
adjacent station spacing. Tip values for `Strip_length`, `Fx_int`, `Fz_int`,
and `My_int` therefore change. Interior strip lengths retain the midpoint
rule. Rebuild post products to apply the full span integration.

This release also changes documentation page URLs. Old page links do not
redirect and must be updated to the new site structure.

### The command that does it

Run `pyfs-matrix post` to rebuild products from recorded solver exports.

## 0.39.0

### Who is affected

Workspaces adopting the 0.39.0 compatibility and workflow additions.

### What changes in a workspace

Review the 0.39.0 migration record in the repository changelog for any
workspace-specific changes.

### The command that does it

Run `pyfs-matrix upgrade` when the workspace layout requires conversion.

## 0.38.0

### Who is affected

Workspaces adopting the 0.38.0 release.

### What changes in a workspace

Review the 0.38.0 migration record in the repository changelog for any
workspace-specific changes.

### The command that does it

Run `pyfs-matrix upgrade` when the workspace layout requires conversion.

## Older layouts

For releases before 0.38.0, use `pyfs-matrix upgrade` to convert earlier
matrix layouts and `pyfs-matrix rename` to convert legacy 0.20.x names.
