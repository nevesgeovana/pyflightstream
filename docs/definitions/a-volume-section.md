## A volume section

`[volume_section]` declares one sampled flow plane through
probes on steady rows and fluid-plot histories on unsteady/rotor rows. The
package writes a velocity **vertex cloud**, without interpolated surface
panels or invented volume cells. This is the approved workspace route; it
uses no native volume-section index.

| Field | Definition |
|---|---|
| Files | `post/<matrix>/fields/<point>_vsec.vtk` or `.dat`; unsteady products add `_step_<STEP>` before the extension. Each has a provenance JSON companion. |
| Plane | Rectangle `corners_m` or annular `radii_m`, in the declared `frame` and `plane`, with `offset_m` on the remaining positive axis. Authored lengths are meters. |
| Samples | Rectangle `points` gives the two axis counts (25 by 25 when omitted); each extra `refinement_layers` bisects intervals. A circle states radial/azimuthal counts and samples its zero-radius center once. |
| Source | The written probe CSV, derived from the native steady probe export or the actual unsteady fluid-plot STEPs. No missing STEP is synthesized. |
| Physical meaning | Positions in REFERENCE coordinates and meters; absolute REFERENCE velocity components in m/s. Export-kind, unit, executable and motion evidence must support the conversion. |
| Time | One instantaneous steady sample set, or a separate field for each actual unsteady STEP; never an implied time average. |
| Provenance | Source hash, recorded sample identities/positions, declared and resolved frames, units, actual STEP where present, native convention evidence and recorded solver setup. Unknown setup values remain unknown. |

A saved FSM may already contain native sections: the new sampling grid does
not use those sections as its addressing basis. The direct native/custom API
still does not discover their indices. Its caller must establish the actual
native section inventory, as explained in [sampled fields](../sampled-fields.md).
A new grid or a missing history cannot be reconstructed merely by posting old
results. See [the workspace example](../pproc-artifact.md#a-volume-section)
for input syntax and the measured-domain restrictions.

### Historical native volume exports, 0.27.x and 0.28.x

The following contract is retained for old run records only. It is not the
implementation of a new 0.29.0 workspace `[volume_section]` request.

A volume section is ONE flow-field plane through the solution, declared by the
pproc's `[volume_section]` table and cut by every point of a
**steady** row after its solve. It is a native solver export, like the surface
files above, and the package writes no product from it:

| field | definition |
|---|---|
| file | `{name}_vsec.vtk` (`format = "vtk"`, `EXPORT_VOLUME_SECTION_VTK`) or `{name}_vsec.dat` (`format = "tecplot"`, `EXPORT_VOLUME_SECTION_TECPLOT`), in the point's `datapoints/DP-<point>/`, hashed in its record |
| plane | a rectangle between two diagonal corners (`corners_m`), or an annulus between two radii (`radii_m`), in the `plane` of the named `frame`, `offset_m` along its normal; every length in metres, written in the simulation's length unit, and a saved simulation whose unit the package cannot read is refused at plan ([the workflows page](../workflow-row-flow-inputs.md#one-row-one-actuator-disc)) |
| instant | the converged state of THAT point: the section is created after the point's `START_SOLVER`, its flow computed by `UPDATE_ALL_VOLUME_SECTIONS` before the export, and a later point of a sweep deletes the previous section before creating its own, so each file is its own point's plane; a section exported with no update held every cell at 0.0 in the licensed run of 2026-09-24 (RPT-070), and with the update the rerun's 96 cell values of each point are all non-zero and differ between its two points (RPT-070) |
| which section | the pproc's own: the export and the delete cite the index the pproc's section takes in the solver's list, counting every section the script cuts, a raw line's included, so a section a raw line cut before it never fills the pproc's file; a raw line deleting the pproc's section leaves the file nothing to export, and the row is refused when its script is built |

The `_vsec` infix is what tells the file from a surface export of the same
extension for a native volume export. **A historical surface export keeps its recorded kind**: its `P_vsec.vtk` or
`P_vsec.dat` was a surface VTK or Tecplot export, and the post keeps it one, a
native-surface entry of `products.json` with its instant or average metadata in
PROV-JSON, because upgrading the reader does not rewrite what a record says.
The post reads every recorded output by the kinds the record's
`package_version` knew. There is one section per pproc; an unsteady row naming a pproc that
declares one is refused, because its step exports run before a section cut
after the march exists. The commands are verified on 26.120 to 26.124 one at a
time; the delete-then-create sequence of a sweep is not measured.
