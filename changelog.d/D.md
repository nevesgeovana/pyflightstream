## Added

- `pyfs-workspace field time-mean --fluctuation` writes the per-probe population standard deviation of the averaged steps beside the mean as `<stem>.fluctuation.csv`, named with its sha256 in the provenance record, and `--fluctuation-only --last K` writes that report alone (FR-250).
- `pyflightstream.post.inflow_tools.to_installed_frame` writes a product table in the installed frame (the isolated frame mirrored through `y = 0`) beside the input as `<table>_installed.csv`; the column classification is stated on the post-processing definitions page (FR-251).
- `pyflightstream.post.inflow_tools.blade_view_harmonics`, `inflow_harmonics_map` and `write_inflow_harmonics` add to the plan's `--inflow-fft` the variance share of harmonics 1 to 8, the rms and half peak-to-peak of the angle of attack perturbation, `k_1P` and `k_eff` from the mean relative speed, and the map over the advance ratio (`inflow_harmonics.csv`, `inflow_harmonics_J.csv`) (FR-252).
- `pyfs-workspace field fill-interior --r-body` gives the probes inside the body radius (0.38 m by default) the value of the nearest probe outside it on the same azimuth ray, previewing by default and writing with `--apply` and provenance (FR-253).

## Changed

- `pyflightstream.cases.qsteady` gains `blade_inflow_angles` and `harmonic_variance_shares`, the reading and the shares `blade_inflow_harmonics` and `harmonic_order` already used, now public so the inflow tools read the field one way; their results are unchanged (FR-252).

## Migration

- `field time-mean` accepts `--fluctuation`, `--fluctuation-only` and `--vinf`; without them it behaves as before (FR-250).
- The provenance record of a field written with a fluctuation report carries a `sidecars` list; records written without one are unchanged (FR-250).
