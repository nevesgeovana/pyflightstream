# RPT-008: mesher and flow-visualization integration license research (v0.3 line)

Date: 2026-07-22. Research card only: no decision is taken in this
report and no code or dependency change accompanies it. Evidence
gathered from the PyPI JSON API (`https://pypi.org/pypi/<name>/json`),
project sites, and upstream license files, each cited with its URL and
access date, against SRS NFR-02 (dependency licenses must be
MIT-compatible) and the engineering policy of 2026-07-21 (public
libraries for generic needs). The ITACA integration is explicitly out
of scope for this card and remains on hold.

Integration modes used below:

* import extra: the package may become an optional `[extra]`
  dependency that pyflightstream imports (requires clear
  MIT compatibility, as in RPT-002 and RPT-003).
* external tool: pyflightstream never imports the software; the user
  runs it as a separate executable and only files are exchanged.
  Running an executable and reading or writing its file formats
  imposes no license obligations on this repository.
* rejected: neither mode is worth pursuing.

## 1. pyvista (flow visualization)

| Item | Value |
|---|---|
| Package | `pyvista` (PyPI) |
| Version checked | 0.48.4 (latest at check date) |
| License | MIT (PyPI `license_expression: "MIT"`) |
| Evidence | `https://pypi.org/pypi/pyvista/json`, accessed 2026-07-22 |
| Integration mode | import extra (candidate `[viz]`) |
| Verdict | MIT-compatible; NFR-02 satisfied |

Required dependencies and their licenses: `vtk` (BSD-3-Clause;
`https://pypi.org/pypi/vtk/json`, version 9.6.2, classifier
`License :: OSI Approved :: BSD License`, accessed 2026-07-22),
`numpy` (BSD-3-Clause), `matplotlib` (PSF-based, BSD-style),
`pillow` (MIT-CMU), `pooch` (BSD-3-Clause), `scooby` (MIT),
`cyclopts` (MIT), `typing-extensions` (PSF). All permissive and
MIT-compatible. The vtk wheel is large (order of 100 MB installed),
which is another reason to keep it behind an optional extra.

Concrete fit: `src/pyflightstream/post/writers.py` already writes VTK
legacy ASCII polydata (`# vtk DataFile Version 3.0`, `DATASET
POLYDATA` with `POINTS`, `VERTICES`, and `POINT_DATA` scalars and
vectors). `pyvista.read()` opens exactly this legacy `.vtk` format
through VTK's built-in legacy reader, so a `[viz]` extra could
(a) render probe clouds from `write_vtk_points` outputs in examples
without ParaView, and (b) round-trip the writer goldens in tier 1
tests as an independent format check. No change to the writers is
needed; pyvista would sit strictly downstream of `post/`.

Recommendation: strongest candidate of this card for a new optional
`[viz]` extra; before adoption, re-verify the pinned release the same
way RPT-002 did and weigh the vtk wheel cost for CI.

## 2. gmsh (meshing)

| Item | Value |
|---|---|
| Package | `gmsh` (PyPI) / Gmsh (gmsh.info) |
| Version checked | 4.15.2 (latest at check date) |
| License | GPL-2.0-or-later (PyPI license field `GPLv2+`, classifier `GNU General Public License v2 or later (GPLv2+)`) |
| Evidence | `https://pypi.org/pypi/gmsh/json` and `https://gmsh.info/`, both accessed 2026-07-22 |
| Integration mode | external tool only (subprocess and file exchange) |
| Verdict | NOT MIT-compatible as an import dependency; rejected as extra |

License detail: gmsh.info states Gmsh is "distributed under the terms
of the GNU General Public License (GPL) (version 2 or later, with an
exception to allow for easier linking with external libraries)". That
exception eases Gmsh's own linking against external libraries; it does
not relieve programs that import Gmsh from GPL obligations, and the
site itself notes that integration into non-GPL software requires a
commercial license.

Policy consequence: importing the `gmsh` Python module (which loads
the Gmsh shared library into the process) would make pyflightstream a
combined work under the GPL, incompatible with the MIT license and
with NFR-02. Therefore `gmsh` must never appear in any extra and no
module under `src/` may import it. This is the same class of exclusion
as the clean-room rule's AGPL exclusion (invariant 2), applied at the
dependency level.

Acceptable file-based bridge (documentation-level only, no code in
this repo imports or bundles Gmsh): the user authors a `.geo` file (or
CAD input) and runs the Gmsh executable themselves, for example
`gmsh -2 model.geo -o model.stl -format stl`, producing a surface
triangulation; the resulting STL then enters FlightStream through the
existing `IMPORT` command (`file_type: STL` in
`src/pyflightstream/commands/mesh_import_export.yaml`, SRC-003 p.307),
the same import path the QA generators use via
`qa/geometry.py::write_stl`. Running a GPL executable as a separate
process and exchanging files is plain use and imposes no obligations
on this repository. If format conversion beyond what Gmsh exports is
ever needed (for example `.msh` to STL), meshio (Section 4) covers it
under MIT.

Recommendation: reject as dependency; at most, a documented
external-tool recipe (example or how-to page) showing the
geo-to-STL-to-IMPORT chain, with the invocation left to the user.

## 3. OpenVSP (parametric aircraft geometry)

| Item | Value |
|---|---|
| Software | OpenVSP (github.com/OpenVSP/OpenVSP) |
| License | NASA Open Source Agreement version 1.3 (NOSA 1.3, SPDX `NASA-1.3`) |
| Evidence | `https://raw.githubusercontent.com/OpenVSP/OpenVSP/main/LICENSE` and `https://opensource.org/licenses/NASA-1.3`, both accessed 2026-07-22 |
| Integration mode | external tool only (author's current workflow) |
| Verdict | not clearly MIT-compatible for import; fine as external executable |

License analysis: NOSA 1.3 is OSI-approved
(`https://opensource.org/licenses/NASA-1.3`, accessed 2026-07-22) but
the FSF classifies it as nonfree and GPL-incompatible because it
requires contributed changes to be the contributor's "original
creation" (`https://www.gnu.org/licenses/license-list.html`, accessed
2026-07-22). It is a reciprocal license with its own notice,
registration, and modification-marking conditions; it is not a
permissive license and its compatibility with MIT redistribution is at
best unclear. Under NFR-02's requirement of clear MIT compatibility,
that ambiguity alone disqualifies it as an import dependency. In
practice the question is moot for packaging as well: there is no
`openvsp` distribution on PyPI (`https://pypi.org/pypi/openvsp/json`
returns 404, accessed 2026-07-22); the Python API ships inside the
OpenVSP release itself, so it could not be expressed as a PyPI extra
anyway.

Concrete fit: the author's workflow already uses OpenVSP as an
external executable, which is exactly the mode this card endorses.
OpenVSP exports surface meshes (STL among other formats) from its
parametric models; the exported STL enters FlightStream through the
same `IMPORT ... STL` path as the Gmsh bridge above. No pyflightstream
code needs to know OpenVSP exists; a documentation example may show
the export-then-IMPORT chain.

Recommendation: keep external-tool only, matching current practice; do
not import the OpenVSP Python API from any module in `src/`.

## 4. Brief scan of other MIT-compatible candidates

meshio: version 5.3.5, MIT (classifier
`License :: OSI Approved :: MIT License`, full MIT text in the license
field; `https://pypi.org/pypi/meshio/json`, accessed 2026-07-22);
required dependencies only numpy and rich. A pure-Python mesh format
converter that reads Gmsh `.msh` and writes STL and VTK among some
forty formats. It would make the Gmsh file bridge robust without ever
importing Gmsh, and is small enough to sit in a future mesh-bridge
extra; note that pyvista's own `[io]` extra already pulls meshio, so
adopting pyvista may bring it along for free.

trimesh: version 4.12.2, MIT, already license-verified in RPT-003 and
already shipped in the `[geom]` extra. It loads and exports STL and
offers mesh repair and inspection, so any mesh clean-up need on the
import path can be met with a dependency the project already gates; no
new verification required beyond re-checking at version bumps.

vedo: version 2026.6.1, MIT (classifier
`License :: OSI Approved :: MIT License`;
`https://pypi.org/pypi/vedo/json`, accessed 2026-07-22); depends on
vtk like pyvista. License-wise acceptable, but it duplicates pyvista's
role as a VTK wrapper; carrying two wrappers over the same 100 MB vtk
wheel buys nothing. Worth a line only as the fallback if pyvista were
ever rejected on other grounds.

## Summary

| Candidate | Version checked | License | Integration mode under repo policy | Recommendation |
|---|---|---|---|---|
| pyvista | 0.48.4 | MIT | import extra (candidate `[viz]`) | adopt as optional extra, pending author decision |
| gmsh | 4.15.2 | GPL-2.0-or-later | external tool only; import rejected | document file bridge (geo/msh in, STL out, IMPORT) |
| OpenVSP | current main | NOSA 1.3 | external tool only; import rejected | keep current external-executable workflow |
| meshio | 5.3.5 | MIT | import extra (bridge helper) | optional; may arrive via pyvista `[io]` |
| trimesh | 4.12.2 | MIT | import extra (already in `[geom]`) | reuse, no new gate |
| vedo | 2026.6.1 | MIT | import extra possible | do not adopt; redundant with pyvista |

## Proposed decision list for the author

No decision is taken in this report; each item below is a yes/no for
the author on the v0.3 line.

1. Add a `[viz]` optional extra with pyvista for reading and rendering
   the legacy `.vtk` files that `post/writers.py` already emits, with
   an RPT-style license re-verification of the pinned release at
   adoption time.
2. Add a documentation recipe (not code) for the Gmsh external-tool
   bridge: user-run `gmsh` producing STL, imported via the `IMPORT`
   command; confirm the standing rule that `gmsh` never appears in any
   extra or import.
3. Add a documentation recipe for the OpenVSP export-then-IMPORT
   chain, formalizing the existing external-executable workflow, with
   the same never-import rule for the OpenVSP Python API.
4. Decide whether meshio enters an extra explicitly (as the msh-to-STL
   converter of the Gmsh bridge) or is left to arrive implicitly via
   pyvista's `[io]` extra if item 1 is accepted.
5. Record vedo as considered and not adopted (redundant VTK wrapper),
   so the scan is not repeated.

The ITACA integration remains out of scope and on hold; it is listed
here only so this card's scope boundary is explicit.
