# Compatibility reanalysis: 26.125 (2026-10-16)

Analysis only; no solver run. Source execution: [reports/compat/CMP-26125_2026-10-05_probe-campaign.yaml](CMP-26125_2026-10-05_probe-campaign.yaml), dated 2026-10-05. Execution identity, script hashes and signals are retained.

- `CREATE_FREE_SURFACE_TFI_MESH`: unprobed. PFS-2138.009: the modal error names a perimeter curve with zero assigned virtual curves. The probe did not establish the required precondition, so its abort does not distinguish a command defect from invalid setup. Withdraw broken; preserve the baseline, aborted target and script hash. No new solver run.
