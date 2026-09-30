# RPT-100: architecture metrics (2026-09-30)

Architecture metrics 2026-09-30: 150 modules, 146463 lines, 79704 code lines; the largest 1, 5 and 13 modules hold 11.3, 30.6 and 48.2 percent of the code lines.

Written by `python scripts/arch_metrics.py report --number 100 --date 2026-09-30`; every number below is that run's. The unit of module and function size is the code line of the review lens: a line holding a token other than a comment, docstring lines excluded. The tier-1 test `test_architecture_metrics.py::test_the_record_agrees_with_the_tree` re-measures the tree and refuses a disagreement with the numbers of the newest record, and refuses a record or a baseline table worse than the first record.

## Numbers

| metric | value |
|---|---:|
| module_count | 150 |
| total_lines | 146463 |
| code_lines | 79704 |
| top1_share | 11.3 |
| top5_share | 30.6 |
| top13_share | 48.2 |
| modules_over_1000 | 17 |
| modules_over_2000 | 6 |
| functions_over_100 | 75 |
| functions_over_200 | 19 |
| functions_over_300 | 8 |
| functions_over_limits | 230 |
| cross_package_sccs | 2 |
| largest_fan_out | 36 |
| largest_fan_out_module | exceptions.py |
| largest_fan_out_deferred | 11 |
| largest_fan_out_deferred_module | run/records.py |
| private_test_names | 242 |
| monkeypatch_targets | 83 |
| workspace_to_run_imports | 2 |
| root_facade_lines | 23961 |

Thresholds the guards read: soft_lines 1000, hard_lines 2000, deep_min_lines 60, deep_min_defs 2, facade_cap 300, function_floor 250, fan_out_cap 25; function limits complexity 10, branches 12, statements 50, positional 5.

## By top-level package

One row per top-level package (a single-file module counts as its own), the unit a per-package review or audit is partitioned by.

| package | modules | code lines | share | over 1000 | functions over a G2 limit | private names reached by tests |
|---|---:|---:|---:|---:|---:|---:|
| `post` | 27 | 16763 | 21.0 | 3 | 52 | 34 |
| `cases` | 15 | 16724 | 21.0 | 3 | 43 | 68 |
| `run` | 12 | 11877 | 14.9 | 4 | 48 | 57 |
| `workspace` | 19 | 11277 | 14.1 | 4 | 28 | 29 |
| `qa` | 12 | 5243 | 6.6 | 1 | 10 | 10 |
| `script` | 8 | 3635 | 4.6 | 1 | 15 | 10 |
| `results` | 5 | 3363 | 4.2 | 1 | 11 | 3 |
| `fsi` | 15 | 3297 | 4.1 | 0 | 6 | 6 |
| `utils` | 5 | 1826 | 2.3 | 0 | 6 | 0 |
| `reference` | 1 | 875 | 1.1 | 0 | 2 | 9 |
| `probes` | 4 | 603 | 0.8 | 0 | 2 | 2 |
| `_progress` | 1 | 532 | 0.7 | 0 | 1 | 3 |
| `commands` | 1 | 516 | 0.6 | 0 | 1 | 0 |
| `_fsm` | 1 | 430 | 0.5 | 0 | 3 | 0 |
| `_deprecations` | 1 | 384 | 0.5 | 0 | 1 | 0 |
| `_signature` | 1 | 296 | 0.4 | 0 | 0 | 0 |
| `farfield` | 1 | 255 | 0.3 | 0 | 0 | 0 |
| `overview` | 1 | 192 | 0.2 | 0 | 0 | 5 |
| `versions` | 1 | 181 | 0.2 | 0 | 0 | 3 |
| `_console` | 1 | 161 | 0.2 | 0 | 0 | 0 |
| `support` | 1 | 153 | 0.2 | 0 | 0 | 0 |
| `exceptions` | 1 | 149 | 0.2 | 0 | 0 | 0 |
| `_retired_names` | 1 | 132 | 0.2 | 0 | 0 | 0 |
| `options` | 1 | 126 | 0.2 | 0 | 0 | 2 |
| `_atmosphere` | 1 | 106 | 0.1 | 0 | 0 | 0 |
| `_expressions` | 1 | 102 | 0.1 | 0 | 1 | 0 |
| `_digest` | 1 | 97 | 0.1 | 0 | 0 | 0 |
| `_cli` | 1 | 90 | 0.1 | 0 | 0 | 1 |
| `testing` | 1 | 81 | 0.1 | 0 | 0 | 0 |
| `_errors` | 1 | 50 | 0.1 | 0 | 0 | 0 |
| `_tokens` | 1 | 49 | 0.1 | 0 | 0 | 0 |
| `(root)` | 1 | 35 | 0.0 | 0 | 0 | 0 |
| `extras` | 1 | 29 | 0.0 | 0 | 0 | 0 |
| `_lengths` | 1 | 23 | 0.0 | 0 | 0 | 0 |
| `_fsi_calibration` | 1 | 20 | 0.0 | 0 | 0 | 0 |
| `_yamlflow` | 1 | 18 | 0.0 | 0 | 0 | 0 |
| `_mesh` | 1 | 9 | 0.0 | 0 | 0 | 0 |
| `_decimal` | 1 | 5 | 0.0 | 0 | 0 | 0 |

## Modules over 1000 code lines

| module | code lines | lines | size exemption |
|---|---:|---:|---|
| `cases/workflows.py` | 9000 | 16171 | no |
| `post/products.py` | 5724 | 9203 | no |
| `run/__init__.py` | 4539 | 8713 | no |
| `post/guides.py` | 2729 | 3349 | no |
| `cases/__init__.py` | 2430 | 5775 | no |
| `run/cli.py` | 2018 | 2594 | no |
| `run/records.py` | 1954 | 2796 | no |
| `workspace/inputs.py` | 1831 | 3635 | no |
| `cases/matrix.py` | 1810 | 3357 | no |
| `script/helpers.py` | 1678 | 3809 | no |
| `workspace/__init__.py` | 1609 | 4148 | no |
| `results/__init__.py` | 1583 | 3571 | no |
| `workspace/storage.py` | 1487 | 2001 | no |
| `workspace/matrix.py` | 1395 | 2721 | no |
| `qa/specs.py` | 1334 | 1708 | no |
| `run/matrix.py` | 1316 | 2302 | no |
| `post/corrections.py` | 1007 | 1257 | no |

## Functions

Over 100 code lines: 75.
Over 200 code lines: 19.
Over 300 code lines: 8.
Over a limit of G2 (complexity 10, branches 12, statements 50, positional 5): 230.

| function over 250 code lines | code lines |
|---|---:|
| `post/products.py:_sim_products` | 826 |
| `post/guides.py:_template_sections` | 685 |
| `run/cli.py:_build_parser` | 556 |
| `run/__init__.py:_execute_point` | 466 |
| `script/helpers.py:solver_settings` | 461 |
| `run/__init__.py:run_campaign` | 423 |
| `run/__init__.py:_execute_sweep` | 348 |
| `post/section_distributions.py:_matching_distributions` | 328 |
| `post/products.py:_rotor_tables` | 292 |
| `run/__init__.py:LoadsAssessor.__call__` | 271 |
| `workspace/setup_standards.py:render_guidelines` | 263 |
| `post/products.py:_write_the_products` | 259 |
| `post/section_distributions.py:write_section_distributions` | 257 |

## Imports

Same-row cross imports, workspace to run: 2 statements.
- `workspace/storage.py:229` (deferred) -> `pyflightstream.run.records`
- `workspace/storage.py:1708` (deferred) -> `pyflightstream.run.records`

Cross-package components (module-level and deferred): 2.

- `pyflightstream`, `pyflightstream.post`, `pyflightstream.post.corrections`, `pyflightstream.post.guides`, `pyflightstream.post.products`, `pyflightstream.post.provenance`, `pyflightstream.post.section_distributions`, `pyflightstream.post.series`, `pyflightstream.post.surfaces`, `pyflightstream.run`, `pyflightstream.run.collect`, `pyflightstream.run.matrix`, `pyflightstream.run.records`, `pyflightstream.workspace.storage`
- `pyflightstream.fsi.loads`, `pyflightstream.results`, `pyflightstream.results.native_surface`, `pyflightstream.results.surface`, `pyflightstream.results.tables`

Largest fan-out at module level: `exceptions.py` 36; deferred: `run/records.py` 11 (cap 25 each).

## Private-name coupling of the tests

242 private names referenced by tests, 83 patch targets.

| module | private names | patch targets |
|---|---:|---:|
| `pyflightstream._cli` | 1 | 1 |
| `pyflightstream._digest` | 0 | 1 |
| `pyflightstream._progress` | 3 | 3 |
| `pyflightstream._signature` | 0 | 1 |
| `pyflightstream.cases.fsi_workspace` | 0 | 1 |
| `pyflightstream.cases.matrix` | 19 | 0 |
| `pyflightstream.cases.qsteady` | 1 | 1 |
| `pyflightstream.cases.setup_surfaces` | 1 | 0 |
| `pyflightstream.cases.windows` | 0 | 1 |
| `pyflightstream.cases.workflows` | 47 | 3 |
| `pyflightstream.fsi.centrifugal` | 0 | 3 |
| `pyflightstream.fsi.driver` | 5 | 1 |
| `pyflightstream.fsi.loads` | 1 | 0 |
| `pyflightstream.options` | 2 | 0 |
| `pyflightstream.overview` | 5 | 0 |
| `pyflightstream.post` | 1 | 0 |
| `pyflightstream.post._tables` | 1 | 0 |
| `pyflightstream.post.guides` | 1 | 1 |
| `pyflightstream.post.harmonics` | 1 | 0 |
| `pyflightstream.post.probe_fields` | 0 | 1 |
| `pyflightstream.post.products` | 28 | 7 |
| `pyflightstream.post.section_distributions` | 1 | 0 |
| `pyflightstream.post.superfile` | 1 | 0 |
| `pyflightstream.probes.geometry` | 2 | 0 |
| `pyflightstream.qa.cli` | 1 | 3 |
| `pyflightstream.qa.compat` | 5 | 0 |
| `pyflightstream.qa.cost` | 1 | 0 |
| `pyflightstream.qa.physics` | 0 | 1 |
| `pyflightstream.qa.probes` | 3 | 0 |
| `pyflightstream.reference` | 9 | 0 |
| `pyflightstream.results` | 0 | 1 |
| `pyflightstream.results.tables` | 3 | 3 |
| `pyflightstream.run` | 24 | 9 |
| `pyflightstream.run._continuation_frame` | 1 | 0 |
| `pyflightstream.run._solver_windows` | 1 | 2 |
| `pyflightstream.run.cli` | 13 | 10 |
| `pyflightstream.run.collect` | 6 | 4 |
| `pyflightstream.run.matrix` | 5 | 8 |
| `pyflightstream.run.records` | 6 | 3 |
| `pyflightstream.run.rename` | 1 | 1 |
| `pyflightstream.script` | 7 | 0 |
| `pyflightstream.script.entities` | 1 | 0 |
| `pyflightstream.script.motion` | 1 | 0 |
| `pyflightstream.script.solver_setup` | 1 | 0 |
| `pyflightstream.utils.manual` | 0 | 1 |
| `pyflightstream.versions` | 3 | 1 |
| `pyflightstream.workspace` | 4 | 5 |
| `pyflightstream.workspace._links` | 1 | 0 |
| `pyflightstream.workspace.cli` | 1 | 0 |
| `pyflightstream.workspace.excel` | 0 | 1 |
| `pyflightstream.workspace.fsi_setup` | 0 | 1 |
| `pyflightstream.workspace.inputs` | 3 | 0 |
| `pyflightstream.workspace.matrix` | 13 | 0 |
| `pyflightstream.workspace.naming` | 1 | 1 |
| `pyflightstream.workspace.storage` | 5 | 3 |
| `pyflightstream.workspace.wake_edges` | 1 | 0 |

## Package roots

| root | statement lines beyond the facade |
|---|---:|
| `run/__init__.py` | 7971 |
| `cases/__init__.py` | 5064 |
| `workspace/__init__.py` | 3625 |
| `results/__init__.py` | 3001 |
| `script/__init__.py` | 1954 |
| `commands/__init__.py` | 1199 |
| `farfield/__init__.py` | 644 |
| `probes/__init__.py` | 441 |
| `post/__init__.py` | 28 |
| `fsi/__init__.py` | 25 |
| `__init__.py` | 9 |
| `qa/__init__.py` | 0 |
| `utils/__init__.py` | 0 |

## Modules created since v0.32.0 under 150 code lines

0 modules created since v0.32.0; 0 under 150 code lines.

## The numbers, as the tool wrote them

<!-- arch-metrics:begin -->
```json
{
  "code_lines": 79704,
  "cross_package_sccs": 2,
  "functions_over_100": 75,
  "functions_over_200": 19,
  "functions_over_300": 8,
  "functions_over_limits": 230,
  "largest_fan_out": 36,
  "largest_fan_out_deferred": 11,
  "largest_fan_out_deferred_module": "run/records.py",
  "largest_fan_out_module": "exceptions.py",
  "module_count": 150,
  "modules_over_1000": 17,
  "modules_over_2000": 6,
  "monkeypatch_targets": 83,
  "private_test_names": 242,
  "root_facade_lines": 23961,
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
  "top13_share": 48.2,
  "top1_share": 11.3,
  "top5_share": 30.6,
  "total_lines": 146463,
  "workspace_to_run_imports": 2
}
```
<!-- arch-metrics:end -->
