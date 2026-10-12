# Upgrading

Read the migration records for the releases between your installed version and the version you are adopting. Each record states the changes a workspace needs.

- [Migrating to 0.39.0](migrating-to-0.39.0.md)
- [Migrating to 0.38.0](migrating-to-0.38.0.md)
- [Migrating to 0.37.0](migrating-to-0.37.0.md)
- [Migrating to 0.36.0](migrating-to-0.36.0.md)
- [Migrating to 0.35.1](migrating-to-0.35.1.md)
- [Migrating to 0.35.0](migrating-to-0.35.0.md)
- [Migrating to 0.34.0](migrating-to-0.34.0.md)
- [Migrating to 0.33.1](migrating-to-0.33.1.md)
- [Migrating to 0.33.0](migrating-to-0.33.0.md)
- [Migrating to 0.32.0](migrating-to-0.32.0.md)
- [Migrating to 0.31.0](migrating-to-0.31.0.md)
- [Migrating to 0.30.0](migrating-to-0.30.0.md)
- [Migrating to 0.29.0](migrating-to-0.29.0.md)
- [Migrating to 0.28.0](migrating-to-0.28.0.md)
- [Migrating to 0.27.0](migrating-to-0.27.0.md)
- [Migrating to 0.26.0](migrating-to-0.26.0.md)
- [Migrating to 0.25.0](migrating-to-0.25.0.md)
- [Migrating to 0.24.0](migrating-to-0.24.0.md)
- [Migrating to 0.23.0](migrating-to-0.23.0.md)
- [Migrating to 0.22.0](migrating-to-0.22.0.md)
- [Migrating to 0.21.0](migrating-to-0.21.0.md)
- [Migrating to 0.19.0](migrating-to-0.19.0.md)
- [Migrating to 0.18.0](migrating-to-0.18.0.md)
- [Migrating to 0.17.0](migrating-to-0.17.0.md)
- [Migrating to 0.16.0](migrating-to-0.16.0.md)
- [Migrating to 0.15.0](migrating-to-0.15.0.md)
- [Migrating to 0.14.0](migrating-to-0.14.0.md)
- [Migrating to 0.13.0](migrating-to-0.13.0.md)
- [Migrating to 0.11.0](migrating-to-0.11.0.md)
- [Migrating to 0.10.1](migrating-to-0.10.1.md)
- [Migrating to 0.10.0](migrating-to-0.10.0.md)
- [Migrating to 0.8.1](migrating-to-0.8.1.md)
- [Migrating to 0.5.0](migrating-to-0.5.0.md)

[Release notes](release-notes.md) carry the earlier release records.

## 0.40.0: the far field rests on numpy

`pyflightstream.farfield` takes and returns numpy arrays and small frozen containers in 0.40.0, and `xarray` is no longer a required dependency (FR-457). There is no deprecation period: a shim would need the dependency that left. The numbers are unchanged to the last bit.

| 0.39.0 | 0.40.0 |
|---|---|
| `lattice_dataset(lattice, fields)` returning an `xarray.Dataset` | `lattice_fields(lattice, fields)` returning a `LatticeFields`; `lattice_dataset` refuses, naming it |
| `post.dataset_to_points(ds)` | `LatticeFields.points()`, the same `(points, fields)` pair; `dataset_to_points` refuses, naming it |
| `cylindrical_components(ds)` | `cylindrical_components(fields)`, a `LatticeFields` with `v_r` and `v_theta` added |
| `ds["u"]`, `ds.coords["psi"]` | `fields["u"]`, `fields.psi` (numpy arrays shaped station, ring, azimuth) |
| `ds["u"].sel(station=x)` | `fields["u"][fields.station_index(x)]` |
| `azimuthal_harmonics(da, m_max=6)` | `azimuthal_harmonics(values, psi, m_max=6)`, azimuth on the last axis; order `m` is `[..., m]` |
| `symmetry_floor(da, m_max=6)` | `symmetry_floor(values, psi, m_max=6)` |
| `mass_closure(...)["mdot"]`, `["relative_spread"]` | `mass_closure(...).mdot`, `.relative_spread` |
| `transverse_force(...)["total"]` | `transverse_force(...).total` (also `.plane_term`, `.lateral_term`) |
| `in_plane_moment(...)["total"]` | `in_plane_moment(...).total` (also `.loading_term`, `.moment_arm_term`) |
| `crossflow_kinetic_energy(...)["swirl"]` | `crossflow_kinetic_energy(...).swirl` (also `.total`, `.induced`) |
| a flux or integral returned as an `xarray.DataArray` | a numpy array over the stations |
| `axial_force(..., inlet=x)` with a station the lattice lacks: `KeyError` | `FarfieldInputError` naming the stations the lattice has |

`farfield.rothalpy` and `farfield.irreversible_deficit` are removed in 0.40.0 with no deprecation release (FR-458): both apply to an Euler CFD field, where total enthalpy and entropy exist, and no FlightStream output carries either. They were handed to ITACA, the sister library, for evaluation; a call refuses, naming it.

New in the same release, through the workspace: the `[farfield]` table of the pproc artifact selects the Trefftz-plane analyses (`variant = "sections"`, `"wake"`, `"plane"`) and the survey balances (`[farfield.ledgers]`), and `pyfs-matrix post` writes them to `farfield/<group>_trefftz.csv`, `farfield/<group>_ledgers.csv` and `sections/<point>_trefftz_<family>.csv`; on an unsteady row each file is written as `_instant` and `_average`. A `[[probes]]` entry may declare survey `lattices`. The polar and `campaign_sweep.csv` are unchanged. See [The far-field family](definitions/the-far-field-family.md#the-far-field-family).
