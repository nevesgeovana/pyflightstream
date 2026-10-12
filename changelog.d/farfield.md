## Added
- The far-field family (FR-450 to FR-456): the `[farfield]` table of the pproc artifact selects the Trefftz-plane analyses (`variant = "sections"`, `"wake"`, `"plane"`) and the survey balances (`[farfield.ledgers]`); `pyfs-matrix post` writes `farfield/<group>_trefftz.csv`, `farfield/<group>_ledgers.csv` and `sections/<point>_trefftz_<family>.csv`, each file of an unsteady row as `_instant` and `_average`, and the super file gains `CL_T_<V>`, `CDI_T_<V>` and `E_T_<V>` after every other column.
- `pyfs-matrix plan` reuses what the artifact declares for the far field, adds what is missing (a section distribution, the wake in the VTK export, the far-field plane or lattice as probe points) and refuses only the impossible, stating each input under the point's `farfield` key of `plan.json` (FR-455).
- `results.wake.parse_wake_export` reads the solver's `<name>_wakes.vtk` (FR-452).
- A `[[probes]]` entry declares survey `lattices`; every probe point is checked against the body at plan, a package-added point inside it refused and a declared one warned (FR-459).
## Changed
- `pyflightstream.farfield` takes and returns numpy arrays and small frozen containers; `xarray` is no longer a required dependency (FR-457). The numbers are unchanged to the last bit.
- `pyflightstream.probes` is the one home of probe geometry: the line, rectangle and circle layouts, the survey lattice and the far-field plane (FR-459).
## Removed
- `farfield.rothalpy` and `farfield.irreversible_deficit`, with no deprecation release: both apply to an Euler CFD field, where total enthalpy and entropy exist, and no FlightStream output carries either; a call refuses, naming ITACA, where they went for evaluation (FR-458).
- `farfield.lattice_dataset` and `post.dataset_to_points`; a call refuses, naming the replacement (FR-457 R3).
## Migration
- `lattice_dataset(lattice, fields)` returning an `xarray.Dataset` becomes `lattice_fields(lattice, fields)` returning a `LatticeFields`.
- `post.dataset_to_points(ds)` becomes `LatticeFields.points()`, the same `(points, fields)` pair.
- `cylindrical_components(ds)` becomes `cylindrical_components(fields)`, a `LatticeFields` with `v_r` and `v_theta` added.
- `ds["u"]` and `ds.coords["psi"]` become `fields["u"]` and `fields.psi`, numpy arrays shaped station, ring, azimuth; `ds["u"].sel(station=x)` becomes `fields["u"][fields.station_index(x)]`.
- `azimuthal_harmonics(da, m_max=6)` and `symmetry_floor(da, m_max=6)` become `azimuthal_harmonics(values, psi, m_max=6)` and `symmetry_floor(values, psi, m_max=6)`, azimuth on the last axis.
- `mass_closure(...)["mdot"]`, `transverse_force(...)["total"]`, `in_plane_moment(...)["total"]` and `crossflow_kinetic_energy(...)["swirl"]` become the attributes `.mdot`, `.total` and `.swirl` of small result dataclasses; a flux returned as an `xarray.DataArray` is a numpy array over the stations.
- `axial_force(..., inlet=x)` with a station the lattice lacks raises `FarfieldInputError` naming the stations the lattice has, where it raised `KeyError`.
