# RPT-002: PyNiteFEA license verification (NFR-02 gate for the [fsi] extra)

Date: 2026-07-21. Evidence gathered from the PyPI JSON API
(`https://pypi.org/pypi/PyNiteFEA/json`, accessed 2026-07-21) before
adding `PyNiteFEA` as the optional `[fsi]` extra required by the M6
FSI subpackage (DLV-007 Section 1; SRS NFR-02: dependency licenses
must be MIT-compatible).

## Finding

| Item | Value |
|---|---|
| Package | `PyNiteFEA` (PyPI) |
| Version checked | 3.0.0 (latest at check date) |
| License | MIT (classifier `License :: OSI Approved :: MIT License`) |
| Verdict | MIT-compatible; NFR-02 satisfied |

## Required dependencies and their licenses

All licenses below are permissive and MIT-compatible.

| Dependency | Constraint | License |
|---|---|---|
| numpy | >=2.4.0 | BSD-3-Clause |
| scipy | none | BSD-3-Clause |
| matplotlib | none | PSF-based (matplotlib license, BSD-style) |
| PrettyTable | none | BSD-3-Clause (PyPI `license_expression`, accessed 2026-07-21) |

Optional extras of PyNiteFEA (vtk, pyvista, jupyter tooling, sympy,
and others) are not pulled in by a plain install and are not part of
this verification; re-verify if any is ever added explicitly.

## Notes

* `PyNiteFEA` is the distribution name; the import package in the 3.x
  series is `Pynite`. Confirm the import name at WP0 install time and
  record it in the `fsi/` module docstring.
* This check gates only the `[fsi]` optional extra. The core runtime
  dependency set (NFR-06) is unchanged.
