# Upgrading

Read the migration records for the releases between your installed version and the version you are adopting. Each record states the changes a workspace needs.

## 0.40.0

- New, nothing to migrate: a pproc may state `[streamlines]` ([Streamlines from the pproc artifact](streamlines.md)); a row whose pproc does not is unchanged. Two output suffixes are new, `_sls.txt` and `_slo.txt`; a row whose own declared outputs already end in either is read as a streamline export from 0.40.0 on, so rename such an output.
- New, nothing to migrate: the `unsteady` row key `SIXDOF: d<id>` names a 6DOF input of `inputs/sixdof/` ([One row: a body free to move](sixdof-motion.md)); `_trajectory_6dof.txt` is a new output suffix.
- New, nothing to migrate: an FSI input may state `mode = "external"` ([FSI with a structural program of your own](fsi-external.md)); `pyfs-fsi` gains the subcommand `external`.
- `plan.json` gains the key `streamlines` on a point whose pproc seeds off-body streamlines, and states nothing new on any other point.
- The streamline and 6DOF commands are recorded from the manual only until the licensed probes run; on such a build a row reaching them is refused at plan, naming the command.

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
