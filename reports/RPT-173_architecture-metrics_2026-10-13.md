<!--
GEOVERSE_HEADER
file_version: 1.0.0
artifact_id: RPT-173
last_modified_at: 2026-10-13T14:25:00-03:00
last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
dependencies: [scripts/arch_metrics.py, tests/tier1_offline/architecture_baselines.json, RPT-172]
authority: pyflightstream
status: active
confidentiality: internal
change_summary: Record architecture growth through rfixAPI, rfixR5 and rfixR6 on integC.
revision_source: git
-->

# RPT-173: architecture metrics (2026-10-13)

## Integration growth and its origin

Measured on lane/0.40.0/integC at HEAD 266e255a, against e5a48e33, the
source tree measured by RPT-172. RPT-173 is the first unused report number
after that preceding record. The raw snapshot measurements are retained
with the integration receipt in integC-audit.json. The lane made no changes
to package implementation.

| Snapshot and lane | Private names reached | Patch targets | Functions over limits |
|---|---:|---:|---:|
| e5a48e33, RPT-172 tree | 330 | 147 | 190 |
| 61d97e40, rfixAPI merged | 333 | 148 | 190 |
| c65667a7, rfixR5 merged | 333 | 149 | 192 |
| 266e255a, rfixR6 merged | 334 | 150 | 191 |

rfixAPI (49ecc99d) adds one private name each on fsi.cli,
run._cli_geometry and workspace._geometry_vtk; the latter adds one patch
target. rfixR5 (bb604887) adds one patch target on workspace._geometry_build.
rfixR6 (efd41023) adds one private name and one patch target on that module.
The exact G5 tables and the two coupling freeze coordinates now record
334 and 150. Reduction to the original coupling remains PFS-2081.47.

The G2 safety costs carried by the later lanes are explicitly recorded:

| Function | RPT-172 complexity / branches / statements | Current | Origin |
|---|---|---|---|
| fsi.external.external_step | 11 / 10 / 45 | 12 / 11 / 49 | rfixR6, refuse step-owned names before execution |
| workspace._geometry_build._refuse_existing | 12 / 11 / 25 | 14 / 13 / 32 | rfixR5 then rfixR6, owned destinations and interrupted promotion |
| workspace.fsi_external_setup.resolve_external_fsi | 9 / 8 / 30 | 11 / 10 / 33 | rfixR6, refuse step-owned input and output names at reading |

rfixR5 temporarily puts _build_one and apply_geometry_build above the function
limits; rfixR6's transaction split takes both back under them. The net count
is therefore one more than RPT-172, rather than the three temporary excesses.
These explicit safety-check entries are re-pinned in the integration table.
All thresholds, the original G7 freeze, dependency orders, SCC membership,
literal and facade-definition allowlists remain intact. The original tests
still plant growth to prove that each guard fires.

Architecture metrics 2026-10-13: 343 modules, 223604 lines, 123292 code lines; the largest 1, 5 and 13 modules hold 1.4, 5.6 and 12.0 percent of the code lines.

Written by `python scripts/arch_metrics.py report --number 173 --date 2026-10-13 --since e5a48e33`; every number below is that run's. The unit of module and function size is the code line of the review lens: a line holding a token other than a comment, docstring lines excluded. The tier-1 test `test_architecture_metrics.py::test_the_record_agrees_with_the_tree` re-measures the tree and refuses a disagreement with the numbers of the newest record, and refuses a record or a baseline table worse than the first record.

## Numbers

| metric | value |
|---|---:|
| module_count | 343 |
| total_lines | 223604 |
| code_lines | 123292 |
| top1_share | 1.4 |
| top5_share | 5.6 |
| top13_share | 12.0 |
| modules_over_1000 | 6 |
| modules_over_2000 | 0 |
| functions_over_100 | 65 |
| functions_over_200 | 8 |
| functions_over_300 | 1 |
| functions_over_limits | 191 |
| cross_package_sccs | 1 |
| largest_fan_out | 36 |
| largest_fan_out_module | exceptions.py |
| largest_fan_out_deferred | 10 |
| largest_fan_out_deferred_module | run/cli.py |
| private_test_names | 334 |
| monkeypatch_targets | 150 |
| workspace_to_run_imports | 0 |
| root_facade_lines | 5673 |

Thresholds the guards read: soft_lines 1000, hard_lines 2000, deep_min_lines 60, deep_min_defs 2, facade_cap 300, function_floor 250, fan_out_cap 25; function limits complexity 10, branches 12, statements 50, positional 5.

## By top-level package

One row per top-level package (a single-file module counts as its own), the unit a per-package review or audit is partitioned by.

| package | modules | code lines | share | over 1000 | functions over a G2 limit | private names reached by tests |
|---|---:|---:|---:|---:|---:|---:|
| `cases` | 66 | 25253 | 20.5 | 1 | 42 | 74 |
| `workspace` | 69 | 24956 | 20.2 | 1 | 21 | 35 |
| `post` | 49 | 21402 | 17.4 | 2 | 46 | 61 |
| `run` | 48 | 18849 | 15.3 | 1 | 37 | 80 |
| `qa` | 22 | 10447 | 8.5 | 1 | 6 | 29 |
| `script` | 14 | 4412 | 3.6 | 0 | 9 | 13 |
| `results` | 11 | 4352 | 3.5 | 0 | 10 | 4 |
| `fsi` | 17 | 3919 | 3.2 | 0 | 5 | 7 |
| `utils` | 5 | 1916 | 1.6 | 0 | 6 | 5 |
| `farfield` | 5 | 1062 | 0.9 | 0 | 0 | 0 |
| `reference` | 1 | 886 | 0.7 | 0 | 2 | 9 |
| `probes` | 6 | 857 | 0.7 | 0 | 2 | 2 |
| `_progress` | 1 | 626 | 0.5 | 0 | 1 | 3 |
| `commands` | 2 | 584 | 0.5 | 0 | 0 | 1 |
| `_fsm` | 1 | 484 | 0.4 | 0 | 3 | 0 |
| `_deprecations` | 1 | 433 | 0.4 | 0 | 1 | 0 |
| `_signature` | 1 | 296 | 0.2 | 0 | 0 | 0 |
| `_fsm_fresh` | 1 | 257 | 0.2 | 0 | 0 | 0 |
| `overview` | 1 | 199 | 0.2 | 0 | 0 | 5 |
| `versions` | 1 | 194 | 0.2 | 0 | 0 | 3 |
| `_retired_names` | 1 | 184 | 0.1 | 0 | 0 | 0 |
| `_maturity` | 1 | 182 | 0.1 | 0 | 0 | 0 |
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
Over a limit of G2 (complexity 10, branches 12, statements 50, positional 5): 191.

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

334 private names referenced by tests, 150 patch targets.

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
| `pyflightstream.fsi.cli` | 1 | 0 |
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
| `pyflightstream.run._cli_geometry` | 3 | 2 |
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
| `pyflightstream.workspace._geometry_build` | 2 | 3 |
| `pyflightstream.workspace._geometry_vtk` | 1 | 1 |
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

## Modules created since e5a48e33 under 150 code lines

0 modules created since e5a48e33; 0 under 150 code lines.

## The numbers, as the tool wrote them

<!-- arch-metrics:begin -->
```json
{
  "code_lines": 123292,
  "cross_package_sccs": 1,
  "functions_over_100": 65,
  "functions_over_200": 8,
  "functions_over_300": 1,
  "functions_over_limits": 191,
  "largest_fan_out": 36,
  "largest_fan_out_deferred": 10,
  "largest_fan_out_deferred_module": "run/cli.py",
  "largest_fan_out_module": "exceptions.py",
  "module_count": 343,
  "modules_over_1000": 6,
  "modules_over_2000": 0,
  "monkeypatch_targets": 150,
  "private_test_names": 334,
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
  "total_lines": 223604,
  "workspace_to_run_imports": 0
}
```
<!-- arch-metrics:end -->
