# RPT-168: architecture metrics (2026-10-12)

Architecture metrics 2026-10-12: 342 modules, 220808 lines, 121822 code lines; the largest 1, 5 and 13 modules hold 1.4, 5.6 and 12.1 percent of the code lines.

Written by `python scripts/arch_metrics.py report --number 168 --date 2026-10-12 --since v0.39.0`; every number below is that run's. The unit of module and function size is the code line of the review lens: a line holding a token other than a comment, docstring lines excluded. The tier-1 test `test_architecture_metrics.py::test_the_record_agrees_with_the_tree` re-measures the tree and refuses a disagreement with the numbers of the newest record, and refuses a record or a baseline table worse than the first record.

## Numbers

| metric | value |
|---|---:|
| module_count | 342 |
| total_lines | 220808 |
| code_lines | 121822 |
| top1_share | 1.4 |
| top5_share | 5.6 |
| top13_share | 12.1 |
| modules_over_1000 | 6 |
| modules_over_2000 | 0 |
| functions_over_100 | 64 |
| functions_over_200 | 8 |
| functions_over_300 | 1 |
| functions_over_limits | 181 |
| cross_package_sccs | 1 |
| largest_fan_out | 36 |
| largest_fan_out_module | exceptions.py |
| largest_fan_out_deferred | 10 |
| largest_fan_out_deferred_module | run/cli.py |
| private_test_names | 323 |
| monkeypatch_targets | 140 |
| workspace_to_run_imports | 0 |
| root_facade_lines | 5569 |

Thresholds the guards read: soft_lines 1000, hard_lines 2000, deep_min_lines 60, deep_min_defs 2, facade_cap 300, function_floor 250, fan_out_cap 25; function limits complexity 10, branches 12, statements 50, positional 5.

## By top-level package

One row per top-level package (a single-file module counts as its own), the unit a per-package review or audit is partitioned by.

| package | modules | code lines | share | over 1000 | functions over a G2 limit | private names reached by tests |
|---|---:|---:|---:|---:|---:|---:|
| `cases` | 66 | 24920 | 20.5 | 1 | 38 | 73 |
| `workspace` | 69 | 24654 | 20.2 | 1 | 19 | 32 |
| `post` | 48 | 20987 | 17.2 | 2 | 46 | 61 |
| `run` | 48 | 18701 | 15.4 | 1 | 35 | 74 |
| `qa` | 22 | 10445 | 8.6 | 1 | 6 | 29 |
| `script` | 14 | 4374 | 3.6 | 0 | 9 | 13 |
| `results` | 11 | 4293 | 3.5 | 0 | 9 | 4 |
| `fsi` | 17 | 3881 | 3.2 | 0 | 4 | 6 |
| `utils` | 5 | 1916 | 1.6 | 0 | 6 | 5 |
| `farfield` | 5 | 970 | 0.8 | 0 | 0 | 0 |
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
| `_retired_names` | 1 | 184 | 0.2 | 0 | 0 | 0 |
| `_maturity` | 1 | 182 | 0.1 | 0 | 0 | 0 |
| `_console` | 1 | 162 | 0.1 | 0 | 0 | 0 |
| `support` | 1 | 161 | 0.1 | 0 | 0 | 0 |
| `exceptions` | 1 | 153 | 0.1 | 0 | 0 | 0 |
| `_cli` | 1 | 147 | 0.1 | 0 | 0 | 1 |
| `_digest` | 1 | 141 | 0.1 | 0 | 0 | 0 |
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
| `workspace/storage.py` | 1411 | 2124 | no |
| `run/matrix.py` | 1093 | 2041 | yes |
| `post/_sim.py` | 1077 | 1596 | yes |
| `cases/pproc.py` | 1060 | 2349 | yes |

## Functions

Over 100 code lines: 64.
Over 200 code lines: 8.
Over 300 code lines: 1.
Over a limit of G2 (complexity 10, branches 12, statements 50, positional 5): 181.

| function over 250 code lines | code lines |
|---|---:|
| `post/section_distributions.py:_matching_distributions` | 322 |
| `workspace/setup_standards.py:render_guidelines` | 257 |

## Imports

Same-row cross imports, workspace to run: 0 statements.

Cross-package components (module-level and deferred): 1.

- `pyflightstream`, `pyflightstream.post`, `pyflightstream.post.guides`, `pyflightstream.post.products`, `pyflightstream.run`, `pyflightstream.run._assemble`, `pyflightstream.run._campaign`, `pyflightstream.run._identity`, `pyflightstream.run._plan`, `pyflightstream.run._points`, `pyflightstream.run._rebuild`, `pyflightstream.run._rebuild_evidence`, `pyflightstream.run._sweep`, `pyflightstream.run.collect`, `pyflightstream.run.matrix`, `pyflightstream.run.records`

Largest fan-out at module level: `exceptions.py` 36; deferred: `run/cli.py` 10 (cap 25 each).

## Private-name coupling of the tests

323 private names referenced by tests, 140 patch targets.

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
| `pyflightstream.cases.workflows._frames` | 9 | 1 |
| `pyflightstream.cases.workflows._freestream` | 9 | 1 |
| `pyflightstream.cases.workflows._geometry` | 5 | 0 |
| `pyflightstream.cases.workflows._motion` | 3 | 0 |
| `pyflightstream.cases.workflows._names` | 1 | 0 |
| `pyflightstream.cases.workflows._probes` | 6 | 0 |
| `pyflightstream.cases.workflows._reductions` | 1 | 0 |
| `pyflightstream.cases.workflows._registry` | 0 | 1 |
| `pyflightstream.cases.workflows._rows` | 6 | 0 |
| `pyflightstream.cases.workflows._skeleton` | 1 | 0 |
| `pyflightstream.cases.workflows._solver_settings` | 2 | 0 |
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
| `pyflightstream.run._campaign` | 2 | 4 |
| `pyflightstream.run._cli_parsers` | 2 | 0 |
| `pyflightstream.run._cli_print` | 4 | 1 |
| `pyflightstream.run._cli_query_point` | 2 | 0 |
| `pyflightstream.run._collect_logs` | 1 | 0 |
| `pyflightstream.run._continuation` | 1 | 0 |
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
| `pyflightstream.run.cli` | 11 | 13 |
| `pyflightstream.run.collect` | 5 | 3 |
| `pyflightstream.run.matrix` | 6 | 8 |
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
| `pyflightstream.workspace._links` | 1 | 0 |
| `pyflightstream.workspace.cli` | 1 | 0 |
| `pyflightstream.workspace.costs` | 1 | 0 |
| `pyflightstream.workspace.excel` | 0 | 1 |
| `pyflightstream.workspace.fsi_setup` | 0 | 1 |
| `pyflightstream.workspace.hpc` | 1 | 0 |
| `pyflightstream.workspace.matrix` | 13 | 0 |
| `pyflightstream.workspace.naming` | 1 | 1 |
| `pyflightstream.workspace.sidecars` | 2 | 0 |
| `pyflightstream.workspace.storage` | 6 | 3 |
| `pyflightstream.workspace.wake_edges` | 1 | 0 |

## Package roots

| root | statement lines beyond the facade |
|---|---:|
| `workspace/__init__.py` | 1961 |
| `script/__init__.py` | 1600 |
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

46 modules created since v0.39.0; 20 under 150 code lines.
- `cases/_fsi_external.py` 143
- `cases/sixdof.py` 120
- `cases/workflows/_gap_evidence.py` 64
- `cases/workflows/_row_cells.py` 130
- `cases/workflows/_sixdof.py` 144
- `cases/workflows/_streamlines.py` 148
- `farfield/quadrature.py` 96
- `post/_transfer_functions.py` 89
- `post/streamlines.py` 96
- `probes/lattice.py` 143
- `qa/_spec_0400_gapbase.py` 149
- `run/_cli_parsers_storage.py` 138
- `run/_collect_notes.py` 96
- `run/_rebuild_summary.py` 63
- `script/_wake_edge_file.py` 74
- `workspace/_geometry_record.py` 148
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
| `pyflightstream.cases.workflows._freestream` | 8 to 9 | 1 to 1 | `test_approved_capabilities_029`, `test_custom_field_units`, `test_g15_custom_freestream` and 2 more |
| `pyflightstream.cases.workflows._geometry` | 4 to 5 | 0 to 0 | `test_boundary_setup_coverage`, `test_p0400_workspace_1_degenerate`, `test_setup_standards` |
| `pyflightstream.cases.workflows._reductions` | 0 to 1 | 0 to 0 | `test_p0400_cases_workflows_reductions` |
| `pyflightstream.cases.workflows._rows` | 5 to 6 | 0 to 0 | `test_p0400_cases_workflows_rows`, `test_setup_standards` |
| `pyflightstream.commands` | 0 to 1 | 0 to 0 | `_p0400_gaps_rt_support`, `test_command_db`, `test_command_db_census` and 39 more |
| `pyflightstream.post._additional` | 0 to 4 | 0 to 3 | `test_p0400_post2_additional`, `test_p0400_post_1_additional` |
| `pyflightstream.post._products_campaign` | 0 to 2 | 0 to 0 | `test_p0400_run_2_records`, `test_p0400_workspace_2_manifest` |
| `pyflightstream.post._reduction_stage` | 2 to 5 | 0 to 0 | `test_p0400_post2_reduction_stage` |
| `pyflightstream.post._rotor_plan` | 3 to 9 | 1 to 6 | `test_goal035_rotor_mach` |
| `pyflightstream.post._rotor_products` | 3 to 5 | 0 to 1 | `test_p0320_noise_post`, `test_p0400_post2_rotor_products`, `test_p0400_post_1_rotor_products` |
| `pyflightstream.post._sim` | 1 to 5 | 1 to 6 | `test_p0400_integfix_post_groupkey`, `test_p0400_post2_sim` |
| `pyflightstream.post.corrections` | 0 to 2 | 0 to 3 | `test_goal036_qsteady_corrections`, `test_p0330_docb_docstrings`, `test_p0400_integfix_post_sector` and 3 more |
| `pyflightstream.post.section_distributions` | 1 to 2 | 0 to 2 | `test_p0400_post_1_section_distributions`, `test_public_api` |
| `pyflightstream.post.series` | 0 to 1 | 0 to 5 | `test_p0400_post2_series_precision`, `test_post_products`, `test_public_api` |
| `pyflightstream.post.superfile` | 1 to 2 | 0 to 0 | `test_g16_polar_column`, `test_goal022_translate`, `test_p0400_integfix_release_tag` and 5 more |
| `pyflightstream.post.unsteady_polar` | 0 to 2 | 0 to 0 | `test_p0400_post2_unsteady_polar`, `test_public_api` |
| `pyflightstream.probes.geometry` | 2 to 2 | 0 to 1 | `test_examples`, `test_extras`, `test_p0400_farfield_probes` and 4 more |
| `pyflightstream.qa._spec_0400_gap` | 0 to 1 | 0 to 0 | `test_p0400_gapprobes_specs` |
| `pyflightstream.qa._spec_0400_gapkit` | 0 to 11 | 0 to 2 | `test_p0400_sweep-1_routes` |
| `pyflightstream.qa._spec_ccs_noise` | 0 to 1 | 0 to 0 | none changed since v0.39.0 |
| `pyflightstream.qa.cli` | 1 to 1 | 3 to 4 | `test_cli_options_registry`, `test_p0330_docb_docstrings`, `test_p0340_kill_wave1` and 4 more |
| `pyflightstream.qa.compat` | 5 to 5 | 0 to 1 | `test_command_db`, `test_p0330_docb_docstrings`, `test_p0400_probes_database` and 5 more |
| `pyflightstream.qa.matrix` | 0 to 4 | 0 to 6 | `test_fr310_matrix_homes_all`, `test_public_api` |
| `pyflightstream.qa.probes` | 3 to 5 | 0 to 0 | `test_p0330_docb_docstrings`, `test_p0340_kill_wave1`, `test_p0370_s10_build_26125` and 8 more |
| `pyflightstream.qa.reports` | 0 to 0 | 0 to 1 | `test_exceptions_catalog`, `test_p0400_qa_matrix`, `test_public_api` |
| `pyflightstream.results.tables` | 3 to 4 | 3 to 4 | `test_conventions`, `test_exceptions_catalog`, `test_g16_polar_column` and 7 more |
| `pyflightstream.run._additional` | 0 to 0 | 0 to 2 | none changed since v0.39.0 |
| `pyflightstream.run._batch_collect` | 0 to 1 | 0 to 0 | `test_p0400_integfix_run1_review`, `test_p0400_workspace_1_batch_life` |
| `pyflightstream.run._batch_plan` | 0 to 0 | 0 to 1 | `test_p0350_batch_plan`, `test_p0351_batch_tavg`, `test_p0400_reach_guard` |
| `pyflightstream.run._batch_run` | 0 to 2 | 0 to 0 | `test_p0350_batch_run`, `test_p0350_collect_discard`, `test_p0351_batch_tavg` and 1 more |
| `pyflightstream.run._campaign` | 1 to 2 | 3 to 4 | `test_p0330_docb_docstrings`, `test_p0390_r03`, `test_run_campaign` |
| `pyflightstream.run._cli_parsers` | 1 to 2 | 0 to 0 | `test_p0350_archive_opt_in`, `test_p0350_hpc_selector`, `test_p0390_r03` and 5 more |
| `pyflightstream.run._cli_print` | 3 to 4 | 1 to 1 | `test_p0400_run_1_alias`, `test_p0400_sweep-1_core` |
| `pyflightstream.run._cli_query_point` | 0 to 2 | 0 to 0 | `test_p0400_run_1_alias` |
| `pyflightstream.run._collect_logs` | 0 to 1 | 0 to 0 | `test_p0400_integfix_run1_review` |
| `pyflightstream.run._executors` | 4 to 5 | 1 to 2 | `test_goal021_build_alias` |
| `pyflightstream.run._grouped` | 0 to 1 | 0 to 0 | `test_p0360_rv`, `test_p0400_run_1_grouped` |
| `pyflightstream.run._plan` | 5 to 7 | 0 to 0 | `test_p0330_docb_docstrings`, `test_p0350_batch_plan`, `test_p0400_madv` and 5 more |
| `pyflightstream.run._rebuild` | 2 to 2 | 1 to 2 | none changed since v0.39.0 |
| `pyflightstream.run._rebuild_grouped` | 0 to 1 | 0 to 0 | none changed since v0.39.0 |
| `pyflightstream.run.cli` | 9 to 11 | 9 to 13 | `test_clean_log`, `test_cli_options_registry`, `test_exceptions_catalog` and 27 more |
| `pyflightstream.run.collect` | 6 to 5 | 4 to 3 | `test_fr311_collect_job_ended`, `test_g06_actuator_disc`, `test_goal024_profile_log` and 15 more |
| `pyflightstream.run.matrix` | 5 to 6 | 8 to 8 | `test_additional_post`, `test_conventions`, `test_examples` and 30 more |
| `pyflightstream.run.records` | 1 to 2 | 2 to 3 | `test_cli_options_registry`, `test_mark_failed`, `test_p0330_doca_reference` and 7 more |
| `pyflightstream.run.rename` | 1 to 3 | 1 to 2 | `test_fr310_matrix_homes_all`, `test_goal024_rename_command`, `test_goal028_codex_rename_manifest` and 2 more |
| `pyflightstream.script` | 7 to 10 | 0 to 0 | `test_additional_post`, `test_approved_capabilities_029`, `test_boundary_layer_products` and 93 more |
| `pyflightstream.utils.cli` | 0 to 2 | 0 to 1 | `test_cli_options_registry`, `test_p0330_docb_docstrings`, `test_p0400_sweep-1_contracts` and 2 more |
| `pyflightstream.utils.database` | 0 to 2 | 0 to 0 | `test_p0400_core_small_database`, `test_public_api` |
| `pyflightstream.utils.manual` | 0 to 1 | 1 to 2 | `test_p0400_core_small_chm_to_pdf`, `test_p0400_core_small_manual`, `test_public_api` and 1 more |
| `pyflightstream.workspace` | 4 to 4 | 5 to 7 | `test_additional_post`, `test_approved_capabilities_029`, `test_architecture_metrics` and 214 more |
| `pyflightstream.workspace._batch_life` | 0 to 1 | 0 to 1 | none changed since v0.39.0 |
| `pyflightstream.workspace._batches` | 0 to 0 | 0 to 1 | `test_p0350_batch_run`, `test_p0400_run_1_batch_run`, `test_p0400_sweep-1_routes` |
| `pyflightstream.workspace.costs` | 0 to 1 | 0 to 0 | `test_p0390_r03`, `test_p0400_workspace_1_costs`, `test_p0400_workspace_2_costs` and 2 more |
| `pyflightstream.workspace.hpc` | 0 to 1 | 0 to 0 | `test_p0350_hpc_selector`, `test_p0390_r03`, `test_p0400_run_1_batch_run` and 4 more |
| `pyflightstream.workspace.sidecars` | 3 to 2 | 0 to 0 | `test_goal031_g08_input_glossary`, `test_p0340_thin_blade`, `test_p0400_farfield_plan` and 9 more |
| `pyflightstream.workspace.storage` | 5 to 6 | 3 to 3 | `test_cli_options_registry`, `test_delete_sims_force`, `test_goal035_storage` and 6 more |

## The numbers, as the tool wrote them

<!-- arch-metrics:begin -->
```json
{
  "code_lines": 121822,
  "cross_package_sccs": 1,
  "functions_over_100": 64,
  "functions_over_200": 8,
  "functions_over_300": 1,
  "functions_over_limits": 181,
  "largest_fan_out": 36,
  "largest_fan_out_deferred": 10,
  "largest_fan_out_deferred_module": "run/cli.py",
  "largest_fan_out_module": "exceptions.py",
  "module_count": 342,
  "modules_over_1000": 6,
  "modules_over_2000": 0,
  "monkeypatch_targets": 140,
  "private_test_names": 323,
  "root_facade_lines": 5569,
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
  "top13_share": 12.1,
  "top1_share": 1.4,
  "top5_share": 5.6,
  "total_lines": 220808,
  "workspace_to_run_imports": 0
}
```
<!-- arch-metrics:end -->
