# RPT-168: architecture metrics (2026-10-12)

Architecture metrics 2026-10-12: 344 modules, 223270 lines, 123070 code lines; the largest 1, 5 and 13 modules hold 1.4, 5.6 and 12.0 percent of the code lines.

Written by `python scripts/arch_metrics.py report --number 168 --date 2026-10-12 --since v0.39.0`; every number below is that run's. The unit of module and function size is the code line of the review lens: a line holding a token other than a comment, docstring lines excluded. The tier-1 test `test_architecture_metrics.py::test_the_record_agrees_with_the_tree` re-measures the tree and refuses a disagreement with the numbers of the newest record, and refuses a record or a baseline table worse than the first record.

## Numbers

| metric | value |
|---|---:|
| module_count | 344 |
| total_lines | 223270 |
| code_lines | 123070 |
| top1_share | 1.4 |
| top5_share | 5.6 |
| top13_share | 12.0 |
| modules_over_1000 | 6 |
| modules_over_2000 | 0 |
| functions_over_100 | 65 |
| functions_over_200 | 8 |
| functions_over_300 | 1 |
| functions_over_limits | 190 |
| cross_package_sccs | 1 |
| largest_fan_out | 36 |
| largest_fan_out_module | exceptions.py |
| largest_fan_out_deferred | 10 |
| largest_fan_out_deferred_module | run/cli.py |
| private_test_names | 330 |
| monkeypatch_targets | 147 |
| workspace_to_run_imports | 0 |
| root_facade_lines | 5673 |

Thresholds the guards read: soft_lines 1000, hard_lines 2000, deep_min_lines 60, deep_min_defs 2, facade_cap 300, function_floor 250, fan_out_cap 25; function limits complexity 10, branches 12, statements 50, positional 5.

## By top-level package

One row per top-level package (a single-file module counts as its own), the unit a per-package review or audit is partitioned by.

| package | modules | code lines | share | over 1000 | functions over a G2 limit | private names reached by tests |
|---|---:|---:|---:|---:|---:|---:|
| `cases` | 67 | 25265 | 20.5 | 1 | 42 | 74 |
| `workspace` | 69 | 24811 | 20.2 | 1 | 20 | 33 |
| `post` | 49 | 21402 | 17.4 | 2 | 46 | 61 |
| `run` | 48 | 18837 | 15.3 | 1 | 37 | 79 |
| `qa` | 22 | 10447 | 8.5 | 1 | 6 | 29 |
| `script` | 14 | 4412 | 3.6 | 0 | 9 | 13 |
| `results` | 11 | 4352 | 3.5 | 0 | 10 | 4 |
| `fsi` | 17 | 3888 | 3.2 | 0 | 5 | 6 |
| `utils` | 5 | 1916 | 1.6 | 0 | 6 | 5 |
| `farfield` | 5 | 1046 | 0.8 | 0 | 0 | 0 |
| `reference` | 1 | 886 | 0.7 | 0 | 2 | 9 |
| `probes` | 6 | 857 | 0.7 | 0 | 2 | 2 |
| `_progress` | 1 | 626 | 0.5 | 0 | 1 | 3 |
| `commands` | 2 | 584 | 0.5 | 0 | 0 | 1 |
| `_fsm` | 1 | 484 | 0.4 | 0 | 3 | 0 |
| `_deprecations` | 1 | 402 | 0.3 | 0 | 1 | 0 |
| `_signature` | 1 | 296 | 0.2 | 0 | 0 | 0 |
| `_fsm_fresh` | 1 | 257 | 0.2 | 0 | 0 | 0 |
| `overview` | 1 | 199 | 0.2 | 0 | 0 | 5 |
| `versions` | 1 | 194 | 0.2 | 0 | 0 | 3 |
| `_retired_names` | 1 | 184 | 0.1 | 0 | 0 | 0 |
| `_maturity` | 1 | 183 | 0.1 | 0 | 0 | 0 |
| `_console` | 1 | 162 | 0.1 | 0 | 0 | 0 |
| `support` | 1 | 162 | 0.1 | 0 | 0 | 0 |
| `exceptions` | 1 | 153 | 0.1 | 0 | 0 | 0 |
| `_digest` | 1 | 152 | 0.1 | 0 | 0 | 0 |
| `_cli` | 1 | 147 | 0.1 | 0 | 0 | 1 |
| `options` | 1 | 136 | 0.1 | 0 | 0 | 2 |
| `_expressions` | 1 | 121 | 0.1 | 0 | 0 | 0 |
| `_atmosphere` | 1 | 106 | 0.1 | 0 | 0 | 0 |
| `testing` | 1 | 85 | 0.1 | 0 | 0 | 0 |
| `_textio` | 1 | 62 | 0.1 | 0 | 0 | 0 |
| `_errors` | 1 | 51 | 0.0 | 0 | 0 | 0 |
| `_tokens` | 1 | 50 | 0.0 | 0 | 0 | 0 |
| `(root)` | 1 | 38 | 0.0 | 0 | 0 | 0 |
| `extras` | 1 | 29 | 0.0 | 0 | 0 | 0 |
| `_lengths` | 1 | 24 | 0.0 | 0 | 0 | 0 |
| `_fsi_calibration` | 1 | 20 | 0.0 | 0 | 0 | 0 |
| `_yamlflow` | 1 | 18 | 0.0 | 0 | 0 | 0 |
| `_decimal` | 1 | 17 | 0.0 | 0 | 0 | 0 |
| `_mesh` | 1 | 9 | 0.0 | 0 | 0 | 0 |

## Modules over 1000 code lines

The size table of `tests/tier1_offline/architecture_baselines.json` freezes every module over 1000 code lines at the freeze, those under 2000 included (the goal checker's A0 arm refuses a module over the soft ceiling missing from the table), so a listed module needs no `Size exemption:` line while it is listed; an entry may not grow, a fall fails until the entry is lowered, and a module that leaves the table above 1000 needs the line. A package root absent from the `facade_lines` table holds nothing beyond its docstring, imports, `__all__` and a lazy `__getattr__`.

| module | code lines | lines | size exemption |
|---|---:|---:|---|
| `qa/_spec_0400_gap.py` | 1765 | 1959 | yes |
| `post/input_template.py` | 1455 | 1676 | yes |
| `workspace/storage.py` | 1412 | 2127 | no |
| `run/matrix.py` | 1141 | 2100 | yes |
| `post/_sim.py` | 1077 | 1596 | yes |
| `cases/pproc.py` | 1060 | 2349 | yes |

## Functions

Over 100 code lines: 65.
Over 200 code lines: 8.
Over 300 code lines: 1.
Over a limit of G2 (complexity 10, branches 12, statements 50, positional 5): 190.

| function over 250 code lines | code lines |
|---|---:|
| `post/section_distributions.py:_matching_distributions` | 321 |
| `workspace/setup_standards.py:render_guidelines` | 257 |

## Imports

Same-row cross imports, workspace to run: 0 statements.

Cross-package components (module-level and deferred): 1.

- `pyflightstream`, `pyflightstream.post`, `pyflightstream.post.guides`, `pyflightstream.post.products`, `pyflightstream.run`, `pyflightstream.run._assemble`, `pyflightstream.run._campaign`, `pyflightstream.run._identity`, `pyflightstream.run._plan`, `pyflightstream.run._points`, `pyflightstream.run._rebuild`, `pyflightstream.run._rebuild_evidence`, `pyflightstream.run._sweep`, `pyflightstream.run.collect`, `pyflightstream.run.matrix`, `pyflightstream.run.records`

Largest fan-out at module level: `exceptions.py` 36; deferred: `run/cli.py` 10 (cap 25 each).

## Private-name coupling of the tests

330 private names referenced by tests, 147 patch targets.

| module | private names | patch targets |
|---|---:|---:|
| `pyflightstream._cli` | 1 | 1 |
| `pyflightstream._digest` | 0 | 1 |
| `pyflightstream._progress` | 3 | 3 |
| `pyflightstream._signature` | 0 | 1 |
| `pyflightstream._textio` | 0 | 2 |
| `pyflightstream.cases.freestream` | 0 | 1 |
| `pyflightstream.cases.fsi_workspace` | 0 | 1 |
| `pyflightstream.cases.matrix` | 19 | 0 |
| `pyflightstream.cases.qsteady` | 1 | 1 |
| `pyflightstream.cases.setup_surfaces` | 1 | 0 |
| `pyflightstream.cases.windows` | 0 | 1 |
| `pyflightstream.cases.workflows._actuator` | 2 | 0 |
| `pyflightstream.cases.workflows._clock` | 2 | 0 |
| `pyflightstream.cases.workflows._conventions` | 2 | 0 |
| `pyflightstream.cases.workflows._exports` | 1 | 0 |
| `pyflightstream.cases.workflows._farfield` | 1 | 0 |
| `pyflightstream.cases.workflows._frames` | 9 | 1 |
| `pyflightstream.cases.workflows._freestream` | 9 | 1 |
| `pyflightstream.cases.workflows._geometry` | 5 | 0 |
| `pyflightstream.cases.workflows._motion` | 3 | 0 |
| `pyflightstream.cases.workflows._names` | 1 | 0 |
| `pyflightstream.cases.workflows._probes` | 6 | 0 |
| `pyflightstream.cases.workflows._reductions` | 1 | 0 |
| `pyflightstream.cases.workflows._rows` | 6 | 0 |
| `pyflightstream.cases.workflows._skeleton` | 1 | 0 |
| `pyflightstream.cases.workflows._solver_settings` | 2 | 0 |
| `pyflightstream.cases.workflows._steady` | 0 | 1 |
| `pyflightstream.cases.workflows._vocabulary` | 2 | 0 |
| `pyflightstream.commands` | 1 | 0 |
| `pyflightstream.fsi.centrifugal` | 0 | 3 |
| `pyflightstream.fsi.driver` | 5 | 1 |
| `pyflightstream.fsi.loads` | 1 | 0 |
| `pyflightstream.options` | 2 | 0 |
| `pyflightstream.overview` | 5 | 0 |
| `pyflightstream.post` | 1 | 0 |
| `pyflightstream.post._additional` | 4 | 3 |
| `pyflightstream.post._condition` | 6 | 0 |
| `pyflightstream.post._products_campaign` | 2 | 0 |
| `pyflightstream.post._reduction_stage` | 5 | 0 |
| `pyflightstream.post._rotor_plan` | 9 | 6 |
| `pyflightstream.post._rotor_products` | 5 | 1 |
| `pyflightstream.post._sim` | 5 | 6 |
| `pyflightstream.post._stage` | 7 | 1 |
| `pyflightstream.post._tables` | 2 | 0 |
| `pyflightstream.post.corrections` | 2 | 3 |
| `pyflightstream.post.farfield_fields` | 0 | 1 |
| `pyflightstream.post.glossary` | 1 | 1 |
| `pyflightstream.post.harmonics` | 1 | 0 |
| `pyflightstream.post.point_tables` | 0 | 1 |
| `pyflightstream.post.probe_fields` | 0 | 1 |
| `pyflightstream.post.products` | 4 | 3 |
| `pyflightstream.post.section_distributions` | 2 | 2 |
| `pyflightstream.post.series` | 1 | 5 |
| `pyflightstream.post.superfile` | 2 | 0 |
| `pyflightstream.post.unsteady_polar` | 2 | 0 |
| `pyflightstream.probes.geometry` | 2 | 1 |
| `pyflightstream.qa._spec_0400_gap` | 1 | 0 |
| `pyflightstream.qa._spec_0400_gapkit` | 11 | 2 |
| `pyflightstream.qa._spec_ccs_noise` | 1 | 0 |
| `pyflightstream.qa.cli` | 1 | 4 |
| `pyflightstream.qa.compat` | 5 | 1 |
| `pyflightstream.qa.cost` | 1 | 0 |
| `pyflightstream.qa.matrix` | 4 | 6 |
| `pyflightstream.qa.physics` | 0 | 1 |
| `pyflightstream.qa.probes` | 5 | 0 |
| `pyflightstream.qa.reports` | 0 | 1 |
| `pyflightstream.reference` | 9 | 0 |
| `pyflightstream.results.core` | 0 | 1 |
| `pyflightstream.results.tables` | 4 | 4 |
| `pyflightstream.run._additional` | 0 | 2 |
| `pyflightstream.run._assessment` | 4 | 1 |
| `pyflightstream.run._batch_collect` | 1 | 0 |
| `pyflightstream.run._batch_plan` | 0 | 1 |
| `pyflightstream.run._batch_run` | 2 | 0 |
| `pyflightstream.run._campaign` | 3 | 5 |
| `pyflightstream.run._cli_geometry` | 2 | 2 |
| `pyflightstream.run._cli_parsers` | 2 | 0 |
| `pyflightstream.run._cli_print` | 4 | 1 |
| `pyflightstream.run._cli_query_point` | 2 | 0 |
| `pyflightstream.run._collect_logs` | 1 | 0 |
| `pyflightstream.run._continuation` | 2 | 0 |
| `pyflightstream.run._continuation_frame` | 1 | 0 |
| `pyflightstream.run._executors` | 5 | 2 |
| `pyflightstream.run._grouped` | 1 | 0 |
| `pyflightstream.run._identity` | 2 | 2 |
| `pyflightstream.run._ids` | 3 | 1 |
| `pyflightstream.run._pending` | 4 | 1 |
| `pyflightstream.run._plan` | 7 | 0 |
| `pyflightstream.run._rebuild` | 2 | 2 |
| `pyflightstream.run._rebuild_evidence` | 1 | 0 |
| `pyflightstream.run._rebuild_grouped` | 1 | 0 |
| `pyflightstream.run._solver_windows` | 1 | 2 |
| `pyflightstream.run.cli` | 11 | 14 |
| `pyflightstream.run.collect` | 5 | 3 |
| `pyflightstream.run.matrix` | 7 | 8 |
| `pyflightstream.run.records` | 2 | 3 |
| `pyflightstream.run.rename` | 3 | 2 |
| `pyflightstream.script` | 10 | 0 |
| `pyflightstream.script.entities` | 1 | 0 |
| `pyflightstream.script.motion` | 1 | 0 |
| `pyflightstream.script.solver_setup` | 1 | 0 |
| `pyflightstream.utils.cli` | 2 | 1 |
| `pyflightstream.utils.database` | 2 | 0 |
| `pyflightstream.utils.manual` | 1 | 2 |
| `pyflightstream.versions` | 3 | 1 |
| `pyflightstream.workspace` | 4 | 7 |
| `pyflightstream.workspace._batch_life` | 1 | 1 |
| `pyflightstream.workspace._batches` | 0 | 1 |
| `pyflightstream.workspace._geometry_build` | 1 | 1 |
| `pyflightstream.workspace._links` | 1 | 0 |
| `pyflightstream.workspace.cli` | 1 | 0 |
| `pyflightstream.workspace.costs` | 1 | 0 |
| `pyflightstream.workspace.excel` | 0 | 1 |
| `pyflightstream.workspace.fsi_setup` | 0 | 1 |
| `pyflightstream.workspace.hpc` | 1 | 0 |
| `pyflightstream.workspace.matrix` | 13 | 0 |
| `pyflightstream.workspace.naming` | 1 | 1 |
| `pyflightstream.workspace.sidecars` | 2 | 0 |
| `pyflightstream.workspace.storage` | 6 | 4 |
| `pyflightstream.workspace.wake_edges` | 1 | 0 |

## Package roots

| root | statement lines beyond the facade |
|---|---:|
| `workspace/__init__.py` | 2013 |
| `script/__init__.py` | 1652 |
| `cases/__init__.py` | 1135 |
| `commands/__init__.py` | 812 |
| `fsi/__init__.py` | 25 |
| `post/__init__.py` | 13 |
| `__init__.py` | 9 |
| `run/__init__.py` | 8 |
| `farfield/__init__.py` | 6 |
| `cases/workflows/__init__.py` | 0 |
| `probes/__init__.py` | 0 |
| `qa/__init__.py` | 0 |
| `results/__init__.py` | 0 |
| `utils/__init__.py` | 0 |
| `workspace/_refine/__init__.py` | 0 |

## Modules created since v0.39.0 under 150 code lines

48 modules created since v0.39.0; 20 under 150 code lines.
- `cases/restart_records.py` 17
- `cases/sixdof.py` 120
- `cases/workflows/_gap_evidence.py` 64
- `cases/workflows/_row_cells.py` 130
- `cases/workflows/_sixdof.py` 139
- `cases/workflows/_streamlines.py` 148
- `farfield/quadrature.py` 96
- `post/_field_inputs.py` 101
- `post/_transfer_functions.py` 89
- `post/streamlines.py` 96
- `probes/lattice.py` 143
- `qa/_spec_0400_gapbase.py` 149
- `run/_cli_parsers_storage.py` 143
- `run/_collect_notes.py` 96
- `run/_rebuild_summary.py` 63
- `script/_wake_edge_file.py` 74
- `workspace/_geometry_sidecar.py` 94
- `workspace/_geometry_vtk.py` 135
- `workspace/fsi_external_setup.py` 115
- `workspace/sixdof_setup.py` 98

## Baselines the 0.40.0 integration moved

The integrated tree of 0.40.0 (every lane, review and sweep merged) was measured
against the baselines of the 0.39.0 integration. Every size, limit and facade
entry that fell was lowered or deleted, and the metrics table follows this
record; no size, limit, fan-out or facade entry was raised. Modules the lanes
outgrew were split into private siblings instead (`workspace/_free_space.py`,
`run/_collect_notes.py`, `run/_rebuild_summary.py`, `run/_cli_parsers_storage.py`,
`run/_matrix_warnings.py`, `commands/_schema.py`, `script/_arg_checks.py`,
`script/_ledger_tables.py`, `script/_wake_edge_file.py`,
`post/_transfer_functions.py`, `post/_products_campaign.py`,
`cases/workflows/_row_cells.py`, `qa/_spec_0400_gapbase.py`,
`qa/_spec_0400_gapedges.py`), each placed in its package order where the package
declares one; `run._cli_geometry` sits outside the run order, because
`run/__init__` imports it and it imports `run._cli_mesh`, which the order places
before `__init__`.

THE TEST-COUPLING FREEZE IS RE-PINNED, and it is the one number of the first
record that moved. The 0.40.0 lanes' tests reach 323 private
names and 140 patch targets, against
237 and 83 at the 0.39.0
integration and 242 and 83 in the first record (RPT-100). The release decision
of 2026-10-12 (capabilities first, rigor in its own release) accepted the
growth for 0.40.0: `scripts/arch_metrics.py` `COUPLING_REPIN` states the two
numbers the metrics table is compared with in place of the first record's, and
the reduction back to 242 and 83 is planned as PFS-2081.47 (0.42.0). The table
below is that reduction's work list: each module whose coupling changed, and
the test files changed since v0.39.0 that reference it.

| module | private names | patch targets | tests changed since v0.39.0 that reference it |
|---|---|---|---|
| `pyflightstream._textio` | 0 to 0 | 0 to 2 | `test_p0340_lf_products`, `test_p0400_post2_products`, `test_p0400_post_1_products` and 2 more |
| `pyflightstream.cases.freestream` | 0 to 0 | 0 to 1 | `test_approved_capabilities_029`, `test_custom_field_units`, `test_p0330_docb_docstrings` and 1 more |
| `pyflightstream.cases.workflows._clock` | 1 to 2 | 0 to 0 | `test_p0340_lf_products`, `test_p0400_integfix_fsi`, `test_unsteady_actions` |
| `pyflightstream.cases.workflows._frames` | 7 to 9 | 1 to 1 | `test_goal022_translate`, `test_p0400_cases_workflows_frames`, `test_retired_names` |
| `pyflightstream.cases.workflows._freestream` | 8 to 9 | 1 to 1 | `test_approved_capabilities_029`, `test_custom_field_units`, `test_g15_custom_freestream` and 3 more |
| `pyflightstream.cases.workflows._geometry` | 4 to 5 | 0 to 0 | `test_boundary_setup_coverage`, `test_p0400_workspace_1_degenerate`, `test_setup_standards` |
| `pyflightstream.cases.workflows._reductions` | 0 to 1 | 0 to 0 | `test_p0400_cases_workflows_reductions`, `test_p0400_integfix_blades` |
| `pyflightstream.cases.workflows._registry` | 0 to 0 | 1 to 0 | `test_p0400_reach_guard` |
| `pyflightstream.cases.workflows._rows` | 5 to 6 | 0 to 0 | `test_p0400_cases_workflows_rows`, `test_setup_standards` |
| `pyflightstream.cases.workflows._steady` | 0 to 0 | 0 to 1 | none changed since v0.39.0 |
| `pyflightstream.commands` | 0 to 1 | 0 to 0 | `_p0400_gaps_rt_support`, `test_command_db`, `test_command_db_census` and 41 more |
| `pyflightstream.post._additional` | 0 to 4 | 0 to 3 | `test_p0400_post2_additional`, `test_p0400_post_1_additional` |
| `pyflightstream.post._products_campaign` | 0 to 2 | 0 to 0 | `test_p0400_run_2_records`, `test_p0400_workspace_2_manifest` |
| `pyflightstream.post._reduction_stage` | 2 to 5 | 0 to 0 | `test_goal036_per_revolution`, `test_p0400_post2_reduction_stage` |
| `pyflightstream.post._rotor_plan` | 3 to 9 | 1 to 6 | `test_goal035_rotor_mach` |
| `pyflightstream.post._rotor_products` | 3 to 5 | 0 to 1 | `test_p0320_noise_post`, `test_p0400_post2_rotor_products`, `test_p0400_post_1_rotor_products` |
| `pyflightstream.post._sim` | 1 to 5 | 1 to 6 | `test_p0400_integfix_post_groupkey`, `test_p0400_post2_sim` |
| `pyflightstream.post.corrections` | 0 to 2 | 0 to 3 | `test_goal036_qsteady_corrections`, `test_p0330_docb_docstrings`, `test_p0400_integfix_post_sector` and 3 more |
| `pyflightstream.post.section_distributions` | 1 to 2 | 0 to 2 | `test_p0400_post_1_section_distributions`, `test_public_api` |
| `pyflightstream.post.series` | 0 to 1 | 0 to 5 | `test_p0400_post2_series_precision`, `test_post_products`, `test_public_api` |
| `pyflightstream.post.superfile` | 1 to 2 | 0 to 0 | `test_g16_polar_column`, `test_goal022_translate`, `test_p0340_mesh_faces` and 6 more |
| `pyflightstream.post.unsteady_polar` | 0 to 2 | 0 to 0 | `test_p0400_post2_unsteady_polar`, `test_public_api` |
| `pyflightstream.probes.geometry` | 2 to 2 | 0 to 1 | `test_examples`, `test_extras`, `test_p0400_farfield_probes` and 4 more |
| `pyflightstream.qa._spec_0400_gap` | 0 to 1 | 0 to 0 | `test_p0400_gapprobes_specs` |
| `pyflightstream.qa._spec_0400_gapkit` | 0 to 11 | 0 to 2 | `test_p0400_sweep-1_routes` |
| `pyflightstream.qa._spec_ccs_noise` | 0 to 1 | 0 to 0 | none changed since v0.39.0 |
| `pyflightstream.qa.cli` | 1 to 1 | 3 to 4 | `test_cli_options_registry`, `test_p0330_docb_docstrings`, `test_p0340_kill_wave1` and 5 more |
| `pyflightstream.qa.compat` | 5 to 5 | 0 to 1 | `test_command_db`, `test_p0330_docb_docstrings`, `test_p0400_probes_database` and 5 more |
| `pyflightstream.qa.matrix` | 0 to 4 | 0 to 6 | `test_fr310_matrix_homes_all`, `test_public_api` |
| `pyflightstream.qa.probes` | 3 to 5 | 0 to 0 | `test_error_messages`, `test_p0330_docb_docstrings`, `test_p0340_kill_wave1` and 9 more |
| `pyflightstream.qa.reports` | 0 to 0 | 0 to 1 | `test_exceptions_catalog`, `test_p0400_qa_matrix`, `test_public_api` |
| `pyflightstream.results.tables` | 3 to 4 | 3 to 4 | `test_conventions`, `test_exceptions_catalog`, `test_g16_polar_column` and 7 more |
| `pyflightstream.run._additional` | 0 to 0 | 0 to 2 | none changed since v0.39.0 |
| `pyflightstream.run._batch_collect` | 0 to 1 | 0 to 0 | `test_p0400_integfix_run1_review`, `test_p0400_workspace_1_batch_life` |
| `pyflightstream.run._batch_plan` | 0 to 0 | 0 to 1 | `test_p0350_batch_plan`, `test_p0351_batch_steady`, `test_p0351_batch_tavg` and 1 more |
| `pyflightstream.run._batch_run` | 0 to 2 | 0 to 0 | `test_p0350_batch_run`, `test_p0350_collect_discard`, `test_p0351_batch_tavg` and 1 more |
| `pyflightstream.run._campaign` | 1 to 2 | 3 to 4 | `test_error_messages`, `test_p0330_docb_docstrings`, `test_p0390_r03` and 1 more |
| `pyflightstream.run._cli_parsers` | 1 to 2 | 0 to 0 | `test_p0350_archive_opt_in`, `test_p0350_hpc_selector`, `test_p0390_r03` and 5 more |
| `pyflightstream.run._cli_print` | 3 to 4 | 1 to 1 | `test_p0400_run_1_alias`, `test_p0400_sweep-1_core` |
| `pyflightstream.run._cli_query_point` | 0 to 2 | 0 to 0 | `test_p0400_run_1_alias` |
| `pyflightstream.run._collect_logs` | 0 to 1 | 0 to 0 | `test_p0400_integfix_run1_review` |
| `pyflightstream.run._executors` | 4 to 5 | 1 to 2 | `test_goal021_build_alias` |
| `pyflightstream.run._grouped` | 0 to 1 | 0 to 0 | `test_p0360_rv`, `test_p0400_run_1_grouped` |
| `pyflightstream.run._plan` | 5 to 7 | 0 to 0 | `test_p0330_docb_docstrings`, `test_p0350_batch_plan`, `test_p0400_madv` and 5 more |
| `pyflightstream.run._rebuild` | 2 to 2 | 1 to 2 | none changed since v0.39.0 |
| `pyflightstream.run._rebuild_grouped` | 0 to 1 | 0 to 0 | none changed since v0.39.0 |
| `pyflightstream.run.cli` | 9 to 11 | 9 to 13 | `test_clean_log`, `test_cli_options_registry`, `test_error_messages` and 33 more |
| `pyflightstream.run.collect` | 6 to 5 | 4 to 3 | `test_fr311_collect_job_ended`, `test_g06_actuator_disc`, `test_goal024_profile_log` and 16 more |
| `pyflightstream.run.matrix` | 5 to 6 | 8 to 8 | `test_additional_post`, `test_conventions`, `test_examples` and 34 more |
| `pyflightstream.run.records` | 1 to 2 | 2 to 3 | `test_cli_options_registry`, `test_mark_failed`, `test_p0330_doca_reference` and 7 more |
| `pyflightstream.run.rename` | 1 to 3 | 1 to 2 | `test_fr310_matrix_homes_all`, `test_goal024_rename_command`, `test_goal028_codex_rename_manifest` and 2 more |
| `pyflightstream.script` | 7 to 10 | 0 to 0 | `test_additional_post`, `test_aeroelastic_typed_setup`, `test_approved_capabilities_029` and 99 more |
| `pyflightstream.utils.cli` | 0 to 2 | 0 to 1 | `test_cli_options_registry`, `test_p0330_docb_docstrings`, `test_p0400_sweep-1_contracts` and 3 more |
| `pyflightstream.utils.database` | 0 to 2 | 0 to 0 | `test_p0400_core_small_database`, `test_public_api`, `test_utils_database` |
| `pyflightstream.utils.manual` | 0 to 1 | 1 to 2 | `test_p0400_core_small_chm_to_pdf`, `test_p0400_core_small_manual`, `test_public_api` and 2 more |
| `pyflightstream.workspace` | 4 to 4 | 5 to 7 | `test_additional_post`, `test_approved_capabilities_029`, `test_architecture_metrics` and 225 more |
| `pyflightstream.workspace._batch_life` | 0 to 1 | 0 to 1 | none changed since v0.39.0 |
| `pyflightstream.workspace._batches` | 0 to 0 | 0 to 1 | `test_p0350_batch_run`, `test_p0400_run_1_batch_run`, `test_p0400_sweep-1_routes` |
| `pyflightstream.workspace.costs` | 0 to 1 | 0 to 0 | `test_p0390_r03`, `test_p0400_workspace_1_costs`, `test_p0400_workspace_2_costs` and 2 more |
| `pyflightstream.workspace.hpc` | 0 to 1 | 0 to 0 | `test_p0350_hpc_selector`, `test_p0390_r03`, `test_p0400_run_1_batch_run` and 4 more |
| `pyflightstream.workspace.sidecars` | 3 to 2 | 0 to 0 | `test_goal031_g08_input_glossary`, `test_p0340_mesh_faces`, `test_p0340_thin_blade` and 10 more |
| `pyflightstream.workspace.storage` | 5 to 6 | 3 to 3 | `test_cli_options_registry`, `test_delete_sims_force`, `test_g47_input_template` and 7 more |


## Final lane recount on 2026-10-13

This recount measures lane/0.40.0/docsR at 1c1f23f3, after the final review lanes and integration fixes. It uses the same readers, report generator and count tables as the preceding RPT-168 refresh (1ee2ad0b and 3e66ae5a). Only recorded numeric observations are refreshed. Layer imports, forbidden dependencies, SCC and literal allowlists, package order, facade definitions, depth thresholds and modules_at_freeze are unchanged. The coupling re-pin follows the release decision already recorded above, now 330 private names and 147 patch targets; the planned reduction remains PFS-2081.47.

Some function-table dimensions were already below their default rule cap and did not need to be pinned exactly in the earlier recount. Bringing those historical observations current changes their recorded values even when the source did not change after 3e66ae5a. Those rows identify the earlier 0.40.0 source lane, or state explicitly when the source is unchanged since v0.39.0.

Each changed module or function count is listed below with the responsible lane and the source changes that explain it. The log range is 3e66ae5a..1c1f23f3. Function complexity, branches, statements and argument counts are measured observations; their rule defaults remain 10, 12, 50 and 5.

| guard and module or function | previous | recorded | lane and reason |
|---|---:|---:|---|
| module_code_lines: `run/matrix.py` | `1093` | `1141` | early selected-row validation and geometry CLI routing; 35c3f2dc integB: the early row selection refuses in FR-326's words and order (regression of the last6 merge); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| module_code_lines: `workspace/storage.py` | `1411` | `1412` | storage recipe validation and test coverage; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/_fsi_external.py:wire_external_fsi` | `0` | `{'complexity': 13, 'branches': 13, 'statements': 49, 'positional': 2}` | external-FSI wiring and canonical digest form; 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/fsi_workspace.py:validate_workspace_fsi` | `{'complexity': 11, 'branches': 11, 'statements': 23, 'positional': 2}` | `{'complexity': 11, 'branches': 10, 'statements': 21, 'positional': 2}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/matrix.py:convert_matrix` | `{'complexity': 11, 'branches': 10, 'statements': 27, 'positional': 1}` | `{'complexity': 11, 'branches': 10, 'statements': 29, 'positional': 1}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/selection.py:select_families` | `{'complexity': 11, 'branches': 12, 'statements': 27, 'positional': 4}` | `{'complexity': 11, 'branches': 11, 'statements': 22, 'positional': 4}` | released behavior re-measured; historical sub-limit observations brought current; integfix: bc3054fb integfix: the full-suite red round on the integrated tree, by cause; integfix: 3fbdb589 PFS-2029.25: the absent-numbered-boundary refusal is bounded to a token cited alone (FR-320, FR-435); layering, fan-out and surface fixes |
| function_limits: `cases/workflows/_clock.py:unsteady_export_threshold` | `0` | `{'complexity': 11, 'branches': 11, 'statements': 40, 'positional': 2}` | unsteady export-threshold and restart clock corrections; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/workflows/_farfield.py:_complete_declared_plots` | `0` | `{'complexity': 6, 'branches': 5, 'statements': 22, 'positional': 6}` | declared far-field plot completion and probe-set histories; lanes rfixF and rfixF2; 99adb4fb PFS-2081.100: one rule for a declared section distribution, in plan and post; 3b6d96c2 PFS-2081.99: a reused declared probe set on an unsteady row gets the histories it lacks; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid |
| function_limits: `cases/workflows/_farfield.py:farfield_probes` | `0` | `{'complexity': 11, 'branches': 10, 'statements': 31, 'positional': 3}` | declared far-field plot completion and probe-set histories; lanes rfixF and rfixF2; 99adb4fb PFS-2081.100: one rule for a declared section distribution, in plan and post; 3b6d96c2 PFS-2081.99: a reused declared probe set on an unsteady row gets the histories it lacks; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid |
| function_limits: `cases/workflows/_freestream.py:_free_stream` | `{'complexity': 12, 'branches': 12, 'statements': 38, 'positional': 4}` | `{'complexity': 11, 'branches': 11, 'statements': 38, 'positional': 4}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/workflows/_geometry.py:_setup_ports` | `{'complexity': 18, 'branches': 17, 'statements': 46, 'positional': 2}` | `{'complexity': 17, 'branches': 16, 'statements': 43, 'positional': 2}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/workflows/_probes.py:_emit_one_probe_table` | `{'complexity': 20, 'branches': 20, 'statements': 39, 'positional': 5}` | `{'complexity': 20, 'branches': 20, 'statements': 38, 'positional': 5}` | released behavior re-measured; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid; 1236bfbd litB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/workflows/_rotor.py:_rotor_motions` | `{'complexity': 6, 'branches': 5, 'statements': 48, 'positional': 7}` | `{'complexity': 5, 'branches': 4, 'statements': 48, 'positional': 7}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 0be1b0d9 integfix: pinned-state warning, the 0.40.0 architecture SRS section, ratchet round three, reviews2 owed items; reviews2: f6a5626d cases-workflows: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `cases/workflows/_skeleton.py:_script_init` | `{'complexity': 16, 'branches': 16, 'statements': 45, 'positional': 3}` | `{'complexity': 16, 'branches': 16, 'statements': 43, 'positional': 3}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 1130ac9f merge release/0.40.0 (gaps-rt, geometry, sweep-1, farfield and the review fixes) into lane/0.40.0/integfix; gaps-rt: eb68d585 PFS-2081.15, PFS-2081.16, PFS-2081.17: guards green, gate tests on a chosen database, FR-460 to FR-462 implemented |
| function_limits: `cases/workflows/_solver_settings.py:_settings` | `{'complexity': 16, 'branches': 16, 'statements': 42, 'positional': 2}` | `{'complexity': 16, 'branches': 16, 'statements': 43, 'positional': 2}` | released behavior re-measured; historical sub-limit observations brought current; source unchanged since v0.39.0; the table retained an earlier sub-limit observation |
| function_limits: `fsi/beam.py:modal_frequencies` | `{'complexity': 12, 'branches': 12, 'statements': 49, 'positional': 5}` | `{'complexity': 12, 'branches': 12, 'statements': 50, 'positional': 5}` | released behavior re-measured; historical sub-limit observations brought current; fsi: a7a9fc77 PFS-2095.010, PFS-2085.002, PFS-2088.003: modal_frequencies holds its ratchet entry; the convergence test reaches no private name; fsi: c1a33152 PFS-2095.010, PFS-2085.002, PFS-2088.003, PFS-2095.011, PFS-2085.013, PFS-2095.012, PFS-2095.013: modal and rotating-solve fixes |
| function_limits: `fsi/external.py:external_step` | `0` | `{'complexity': 11, 'branches': 10, 'statements': 45, 'positional': 1}` | external-FSI step handling; 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `post/_additional.py:_additional_products` | `{'complexity': 16, 'branches': 15, 'statements': 43, 'positional': 6}` | `{'complexity': 16, 'branches': 15, 'statements': 45, 'positional': 6}` | released behavior re-measured; historical sub-limit observations brought current; integfix: bc3054fb integfix: the full-suite red round on the integrated tree, by cause; gaps-rt: 08266c67 Merge release/0.40.0 into lane/0.40.0/gaps-rt (PFS-2081.15, PFS-2081.16, PFS-2081.17) |
| function_limits: `post/acoustics.py:write_acoustic_products` | `{'complexity': 14, 'branches': 13, 'statements': 43, 'positional': 2}` | `{'complexity': 14, 'branches': 13, 'statements': 44, 'positional': 2}` | released behavior re-measured; historical sub-limit observations brought current; post-1: 6a9ee69f post-1: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `post/rotor_table.py:write_rotor_table` | `{'complexity': 10, 'branches': 9, 'statements': 57, 'positional': 1}` | `{'complexity': 9, 'branches': 8, 'statements': 57, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: f771286a integfix: after the release and review merges, the ratchet, the lane collisions and the stale tests; mach: 872b7c5f PFS-2113.031: advancing-tip Mach number M_adv in the plan, record and rotor table |
| function_limits: `post/section_distributions.py:_matching_distributions` | `{'complexity': 51, 'branches': 12, 'statements': 133, 'positional': 8}` | `{'complexity': 51, 'branches': 9, 'statements': 133, 'positional': 8}` | released behavior re-measured; historical sub-limit observations brought current; integfix: bc3054fb integfix: the full-suite red round on the integrated tree, by cause; integfix: f771286a integfix: after the release and review merges, the ratchet, the lane collisions and the stale tests |
| function_limits: `post/section_distributions.py:_matching_distributions.entry_matches` | `{'complexity': 13, 'branches': 10, 'statements': 39, 'positional': 3}` | `{'complexity': 13, 'branches': 10, 'statements': 40, 'positional': 3}` | released behavior re-measured; historical sub-limit observations brought current; integfix: bc3054fb integfix: the full-suite red round on the integrated tree, by cause; integfix: f771286a integfix: after the release and review merges, the ratchet, the lane collisions and the stale tests |
| function_limits: `post/superfile.py:measure_sections` | `{'complexity': 14, 'branches': 14, 'statements': 45, 'positional': 2}` | `{'complexity': 14, 'branches': 14, 'statements': 46, 'positional': 2}` | released behavior re-measured; c61eb487 litA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `post/superfile.py:union_the_workspace_knows` | `{'complexity': 11, 'branches': 10, 'statements': 28, 'positional': 3}` | `{'complexity': 11, 'branches': 10, 'statements': 29, 'positional': 3}` | released behavior re-measured; c61eb487 litA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `post/unsteady.py:_read_tecplot_frame` | `{'complexity': 12, 'branches': 11, 'statements': 36, 'positional': 1}` | `{'complexity': 12, 'branches': 11, 'statements': 37, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: f771286a integfix: after the release and review merges, the ratchet, the lane collisions and the stale tests; merge review/0.40.0/post-2 into release/0.40.0: a9d674f1 review(post-2): Codex review fixes, committed by the orchestrator |
| function_limits: `probes/geometry.py:_refine_band` | `{'complexity': 11, 'branches': 12, 'statements': 41, 'positional': 2}` | `{'complexity': 11, 'branches': 12, 'statements': 39, 'positional': 2}` | released behavior re-measured; historical sub-limit observations brought current; release integration: 2eea42cb merge review/0.40.0/qa into release/0.40.0; merge review/0.40.0/qa into release/0.40.0: 5903d6b6 review(qa): Codex review fixes, committed by the orchestrator |
| function_limits: `qa/compat.py:_rewritten_flow_entry` | `{'complexity': 10, 'branches': 9, 'statements': 28, 'positional': 6}` | `{'complexity': 8, 'branches': 7, 'statements': 19, 'positional': 6}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 0be1b0d9 integfix: pinned-state warning, the 0.40.0 architecture SRS section, ratchet round three, reviews2 owed items; integfix: bac2e0e7 merge release/0.40.0 (reviews2: core-small, workspace-2, cases-workflows and five fixed findings) into lane/0.40.0/integfix |
| function_limits: `qa/probes.py:generate_probe_script` | `{'complexity': 12, 'branches': 10, 'statements': 35, 'positional': 5}` | `{'complexity': 12, 'branches': 10, 'statements': 36, 'positional': 5}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 0be1b0d9 integfix: pinned-state warning, the 0.40.0 architecture SRS section, ratchet round three, reviews2 owed items; probes: 80eb48a3 merge release/0.40.0 (eba2f05e) into lane/0.40.0/probes |
| function_limits: `results/tables.py:to_table` | `{'complexity': 15, 'branches': 14, 'statements': 20, 'positional': 1}` | `{'complexity': 15, 'branches': 14, 'statements': 21, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 1130ac9f merge release/0.40.0 (gaps-rt, geometry, sweep-1, farfield and the review fixes) into lane/0.40.0/integfix; integfix: 38136546 release parity: the six 0.39.0 module names importable again, the 26.100 rotor refusal named under FR-101 |
| function_limits: `results/wake.py:_blocks` | `0` | `{'complexity': 11, 'branches': 11, 'statements': 26, 'positional': 1}` | truthful native wake block parsing; ad804263 rfixA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); 1236bfbd litB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/_assessment.py:_judge_the_clockings` | `{'complexity': 14, 'branches': 14, 'statements': 47, 'positional': 6}` | `{'complexity': 14, 'branches': 14, 'statements': 50, 'positional': 6}` | released behavior re-measured; historical sub-limit observations brought current; integfix: a0be2112 PFS-2103.021: the solve-count refusal is a quasi-steady wheel's alone; a sweep point keeps its judgment; integfix: a2026797 PFS-2094.037, PFS-2094.010, PFS-2103.020: reconcile the run-1 and run-2 submission and clocking paths |
| function_limits: `run/_cli_print.py:_print_free_space_paths` | `{'complexity': 15, 'branches': 17, 'statements': 24, 'positional': 2}` | `{'complexity': 15, 'branches': 17, 'statements': 25, 'positional': 2}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 1130ac9f merge release/0.40.0 (gaps-rt, geometry, sweep-1, farfield and the review fixes) into lane/0.40.0/integfix; mach: 872b7c5f PFS-2113.031: advancing-tip Mach number M_adv in the plan, record and rotor table |
| function_limits: `run/_continuation.py:_continued_step_offset` | `0` | `{'complexity': 12, 'branches': 11, 'statements': 34, 'positional': 2}` | whole-march restart step-offset arithmetic; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/_plan.py:_plan_point` | `{'complexity': 8, 'branches': 7, 'statements': 28, 'positional': 7}` | `{'complexity': 9, 'branches': 8, 'statements': 29, 'positional': 7}` | planning now reads the restart wire records; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/_solver_windows.py:_native_windows` | `{'complexity': 14, 'branches': 4, 'statements': 48, 'positional': 1}` | `{'complexity': 14, 'branches': 3, 'statements': 48, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 00650438 architecture ratchet after the 13-lane merge: storage split, run, results, qa, utils, commands and script refactors; run-1: a098dd51 PFS-2094.017, PFS-2101.003: an unread control text is kept apart from a window's text; the G06 scan keeps refusal lines, streamed |
| function_limits: `run/cli.py:_cmd_plan` | `{'complexity': 13, 'branches': 12, 'statements': 41, 'positional': 2}` | `{'complexity': 13, 'branches': 12, 'statements': 42, 'positional': 2}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f1a3e865 merge lane/0.40.0/integfix into release/0.40.0 |
| function_limits: `run/cli.py:main` | `{'complexity': 13, 'branches': 12, 'statements': 21, 'positional': 1}` | `{'complexity': 13, 'branches': 12, 'statements': 23, 'positional': 1}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f1a3e865 merge lane/0.40.0/integfix into release/0.40.0 |
| function_limits: `run/collect.py:_complete` | `{'complexity': 11, 'branches': 10, 'statements': 45, 'positional': 5}` | `{'complexity': 11, 'branches': 10, 'statements': 36, 'positional': 5}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/collect.py:collect_once` | `{'complexity': 11, 'branches': 12, 'statements': 49, 'positional': 1}` | `{'complexity': 11, 'branches': 12, 'statements': 50, 'positional': 1}` | released behavior re-measured; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/matrix.py:_extract` | `{'complexity': 11, 'branches': 12, 'statements': 50, 'positional': 3}` | `{'complexity': 11, 'branches': 10, 'statements': 48, 'positional': 3}` | early selected-row validation and geometry CLI routing; 35c3f2dc integB: the early row selection refuses in FR-326's words and order (regression of the last6 merge); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/matrix.py:_selected_rows` | `0` | `{'complexity': 4, 'branches': 3, 'statements': 13, 'positional': 7}` | early selected-row validation and geometry CLI routing; 35c3f2dc integB: the early row selection refuses in FR-326's words and order (regression of the last6 merge); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `run/rename.py:_rename_workspace_locked` | `{'complexity': 12, 'branches': 11, 'statements': 31, 'positional': 1}` | `{'complexity': 12, 'branches': 11, 'statements': 32, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 1130ac9f merge release/0.40.0 (gaps-rt, geometry, sweep-1, farfield and the review fixes) into lane/0.40.0/integfix; merge review/0.40.0/run-2 into release/0.40.0: 59f26c16 review(run-2): Codex review fixes, committed by the orchestrator |
| function_limits: `script/helpers.py:actuator_disc` | `{'complexity': 17, 'branches': 17, 'statements': 45, 'positional': 2}` | `{'complexity': 17, 'branches': 17, 'statements': 46, 'positional': 2}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 0be1b0d9 integfix: pinned-state warning, the 0.40.0 architecture SRS section, ratchet round three, reviews2 owed items; integfix: bac2e0e7 merge release/0.40.0 (reviews2: core-small, workspace-2, cases-workflows and five fixed findings) into lane/0.40.0/integfix |
| function_limits: `script/helpers.py:analysis_setup` | `{'complexity': 14, 'branches': 13, 'statements': 39, 'positional': 1}` | `{'complexity': 14, 'branches': 13, 'statements': 33, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 0be1b0d9 integfix: pinned-state warning, the 0.40.0 architecture SRS section, ratchet round three, reviews2 owed items; integfix: bac2e0e7 merge release/0.40.0 (reviews2: core-small, workspace-2, cases-workflows and five fixed findings) into lane/0.40.0/integfix |
| function_limits: `script/solver_setup.py:_family_record` | `{'complexity': 19, 'branches': 19, 'statements': 33, 'positional': 3}` | `{'complexity': 19, 'branches': 19, 'statements': 32, 'positional': 3}` | released behavior re-measured; historical sub-limit observations brought current; integfix: 1130ac9f merge release/0.40.0 (gaps-rt, geometry, sweep-1, farfield and the review fixes) into lane/0.40.0/integfix; merge review/0.40.0/script into release/0.40.0: 8e4141aa review(script): Codex review fixes, committed by the orchestrator |
| function_limits: `utils/cli.py:main` | `{'complexity': 11, 'branches': 11, 'statements': 34, 'positional': 1}` | `{'complexity': 11, 'branches': 10, 'statements': 24, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: f771286a integfix: after the release and review merges, the ratchet, the lane collisions and the stale tests; integfix: 1130ac9f merge release/0.40.0 (gaps-rt, geometry, sweep-1, farfield and the review fixes) into lane/0.40.0/integfix |
| function_limits: `utils/manual.py:_parameters_after` | `{'complexity': 12, 'branches': 11, 'statements': 25, 'positional': 3}` | `{'complexity': 12, 'branches': 11, 'statements': 26, 'positional': 3}` | released behavior re-measured; historical sub-limit observations brought current; integfix: bac2e0e7 merge release/0.40.0 (reviews2: core-small, workspace-2, cases-workflows and five fixed findings) into lane/0.40.0/integfix; reviews2: 3cb3ee47 review(core-small): Codex review fixes, committed by the orchestrator |
| function_limits: `workspace/__init__.py:CampaignWorkspace.collect_outputs` | `{'complexity': 15, 'branches': 14, 'statements': 38, 'positional': 2}` | `{'complexity': 18, 'branches': 17, 'statements': 48, 'positional': 2}` | collect-output behavior and geometry workflow methods; c61eb487 litA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `workspace/_geometry_build.py:_refuse_existing` | `0` | `{'complexity': 12, 'branches': 11, 'statements': 25, 'positional': 2}` | existing-output refusal and geometry-build validation; 1f1eb0e8 rfixG: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| function_limits: `workspace/builds.py:resolve_build` | `{'complexity': 14, 'branches': 14, 'statements': 38, 'positional': 3}` | `{'complexity': 14, 'branches': 14, 'statements': 40, 'positional': 3}` | released behavior re-measured; historical sub-limit observations brought current; workspace-2: 4864446d PFS-2100.007: a bad version in executables.local.toml is refused naming the overlay |
| function_limits: `workspace/fsi_setup.py:resolve_fsi_setup` | `{'complexity': 15, 'branches': 15, 'statements': 48, 'positional': 1}` | `{'complexity': 15, 'branches': 15, 'statements': 49, 'positional': 1}` | released behavior re-measured; historical sub-limit observations brought current; integfix: f771286a integfix: after the release and review merges, the ratchet, the lane collisions and the stale tests; gaps-rt: 08266c67 Merge release/0.40.0 into lane/0.40.0/gaps-rt (PFS-2081.15, PFS-2081.16, PFS-2081.17) |
| fan_out: `run/_plan.py` | `0` | `26` | planning now reads the restart wire records; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| private_test_names: `pyflightstream.cases.workflows._farfield` | `0` | `1` | declared far-field plot completion and probe-set histories; lanes rfixF and rfixF2; 99adb4fb PFS-2081.100: one rule for a declared section distribution, in plan and post; 3b6d96c2 PFS-2081.99: a reused declared probe set on an unsteady row gets the histories it lacks; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid |
| private_test_names: `pyflightstream.run._campaign` | `2` | `3` | tests cover the released behavior and its refusal paths; c61eb487 litA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| private_test_names: `pyflightstream.run._cli_geometry` | `0` | `2` | tests cover the released behavior and its refusal paths; 1f1eb0e8 rfixG: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| private_test_names: `pyflightstream.run._continuation` | `1` | `2` | whole-march restart step-offset arithmetic; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| private_test_names: `pyflightstream.run.matrix` | `6` | `7` | early selected-row validation and geometry CLI routing; 35c3f2dc integB: the early row selection refuses in FR-326's words and order (regression of the last6 merge); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| private_test_names: `pyflightstream.workspace._geometry_build` | `0` | `1` | existing-output refusal and geometry-build validation; 1f1eb0e8 rfixG: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| monkeypatch_targets_by_module: `pyflightstream.post.farfield_fields` | `0` | `1` | tests cover the released behavior and its refusal paths; lanes rfixF and rfixF2; 168b270f PFS-2081.58, PFS-2081.102, PFS-2081.103: far-field sets matched in their own frame, to printed precision; c874d7a9 PFS-2081.96, PFS-2081.97: far-field rows say what they are of; ce5bb894 PFS-2081.95, PFS-2081.94: the far-field probe field checked against the solver's own wake (RPT-170) |
| monkeypatch_targets_by_module: `pyflightstream.run._campaign` | `4` | `5` | tests cover the released behavior and its refusal paths; c61eb487 litA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| monkeypatch_targets_by_module: `pyflightstream.run._cli_geometry` | `0` | `2` | tests cover the released behavior and its refusal paths; 1f1eb0e8 rfixG: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| monkeypatch_targets_by_module: `pyflightstream.run.cli` | `13` | `14` | tests cover the released behavior and its refusal paths; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); f1a3e865 merge lane/0.40.0/integfix into release/0.40.0 |
| monkeypatch_targets_by_module: `pyflightstream.workspace._geometry_build` | `0` | `1` | existing-output refusal and geometry-build validation; 1f1eb0e8 rfixG: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes); 36e50cd1 rfixB: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| monkeypatch_targets_by_module: `pyflightstream.workspace.storage` | `3` | `4` | storage recipe validation and test coverage; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| facade_lines: `script/__init__.py` | `1600` | `1652` | strict case-fold option propagation and command validation; b60a70b6 PFS-2081.56, PFS-2081.58: the far field integrates exactly the probes the run laid; f09e31b4 last6: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |
| facade_lines: `workspace/__init__.py` | `1961` | `2013` | collect-output behavior and geometry workflow methods; c61eb487 litA: Codex-finished lane work, committed by the orchestrator (the sandbox refused git writes) |

The G5 total moves from 323 to 330 private names and from 140 to 147 patch targets. The per-module rows above account for all seven additions to each total.

| aggregate metric | previous | recorded | reason |
|---|---:|---:|---|
| top13_share | 12.1 | 12.0 | Final-lane module and function changes listed above; test references re-counted on the integrated tree. |
| functions_over_100 | 64 | 65 | Final-lane module and function changes listed above; test references re-counted on the integrated tree. |
| functions_over_limits | 181 | 190 | Final-lane module and function changes listed above; test references re-counted on the integrated tree. |
| private_test_names | 323 | 330 | Final-lane module and function changes listed above; test references re-counted on the integrated tree. |
| monkeypatch_targets | 140 | 147 | Final-lane module and function changes listed above; test references re-counted on the integrated tree. |
| root_facade_lines | 5569 | 5673 | Final-lane module and function changes listed above; test references re-counted on the integrated tree. |

The regenerated report records 344 modules, 223270 total lines and 123070 code lines, previously 343, 221662 and 122002. The added module is `cases/restart_records.py`, from last6 (f09e31b4), separating persisted restart threshold and stopped-step wire types from the public averaging window.

### Rule failure kept visible

G1 still refuses `cases/restart_records.py`: two top-level definitions but only 17 code lines, below the 60-line floor for a module created after the freeze. It is not added to modules_at_freeze and the floor is not lowered. This source architecture issue requires its owning lane to reconcile the placement of the wire types. The count refresh does not claim that this rule passed.

## The numbers, as the tool wrote them

<!-- arch-metrics:begin -->
```json
{
  "code_lines": 123070,
  "cross_package_sccs": 1,
  "functions_over_100": 65,
  "functions_over_200": 8,
  "functions_over_300": 1,
  "functions_over_limits": 190,
  "largest_fan_out": 36,
  "largest_fan_out_deferred": 10,
  "largest_fan_out_deferred_module": "run/cli.py",
  "largest_fan_out_module": "exceptions.py",
  "module_count": 344,
  "modules_over_1000": 6,
  "modules_over_2000": 0,
  "monkeypatch_targets": 147,
  "private_test_names": 330,
  "root_facade_lines": 5673,
  "thresholds": {
    "deep_min_defs": 2,
    "deep_min_lines": 60,
    "facade_cap": 300,
    "fan_out_cap": 25,
    "function_floor": 250,
    "hard_lines": 2000,
    "limits": {
      "branches": 12,
      "complexity": 10,
      "positional": 5,
      "statements": 50
    },
    "soft_lines": 1000
  },
  "top13_share": 12.0,
  "top1_share": 1.4,
  "top5_share": 5.6,
  "total_lines": 223270,
  "workspace_to_run_imports": 0
}
```
<!-- arch-metrics:end -->
