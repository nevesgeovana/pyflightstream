## Group files

<a id="group-files"></a>

`polars/P<POL>-<GROUP>-<KIND>.csv`, one file per polar, group and kind
(`DIM`, `ACOEF`, `RCOEF`). Every file of one polar sorts together. One row per
point, with the columns of the FAM file it mirrors
([FAM-DIM](fam-dim.md#fam-dim), [FAM-ACOEF](fam-acoef.md#fam-acoef),
[FAM-RCOEF](fam-rcoef.md#fam-rcoef)) and `GROUP`, `GROUP_ID` in place of
`FAMILY`, `FAMILY_ID`.

`<GROUP>` in a file name is the group's name with every character other than a
letter, a digit, `-`, `_` or `.` replaced by `_` (the rule of every file named
after an alias), so `Left/Right` is written `P0001-Left_Right-ACOEF.csv`; the
`GROUP` column and `products.json` keep the name as written.

<a id="the-groups"></a>

### The groups

| Group | Members | `GROUP_ID` | Declared |
| --- | --- | --- | --- |
| `TOTAL` | every family | 0 | never; written for every polar |
| `AIRFRAME` | every family not inside a rotor | 1 | never; written for every polar |
| the rotor's alias | the rotor's families | 10 + the rotor's id | never; every rotor is a group by itself |
| a `[groups]` key | the families of the alias it names | 100 + k, the k-th key in the order written | in the pproc |

A `[groups]` key spelled `TOTAL` or `AIRFRAME` (in any case), or equal to a
rotor's alias, is refused by name: the group is written without it. So is a key
spelled `FAM` or `GRP`, or opening with `P` and a digit, which the file names
cannot carry. A numbered key is written `g<NN>` (`"1"` is `g01`). A group that
selects no family of the polar's loads is named under `skipped` and has no file.

A group's values are formed from the SUM of its members' dimensional loads
(forces and moments about the moment reference point; the moment about the
rotor's hub for an RCOEF file), never by summing coefficients
([group definition](../definitions/airframe-coefficients.md#group)). An
unsteady group row is the sum of its families' window averages, or the group's
own plot where the families' plots are not all in the record (`MRP_TOTAL` for
TOTAL, the rotor's own history for a rotor).

An RCOEF file is written only for a group whose members all sit inside one
rotor: every rotor's group, and a declared group of one rotor's families.

<a id="derived-polars"></a>

### The polars derived from a group ACOEF file

Beside each group ACOEF file, under its stem, when the pproc asks:

| File | Key |
| --- | --- |
| `P<POL>-<GROUP>-ACOEF_trim.csv`, the row at zero pitching moment | `[products] trimmed_polar` (moment `trim_moment`, default `CmB`) |
| `P<POL>-<GROUP>-ACOEF_at_<name>.csv`, the polar sampled along a column | `[[polar_at]]` |
| `P<POL>-<GROUP>-ACOEF.dat`, the same rows in the fixed-width custom format | `[products] custom_polar_format` |

`[products] polar_format = "legacy_polar"` writes the FAM and group files in
the fixed-width form instead of csv.
