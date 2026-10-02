# RPT-140 - The writers that gave CRLF on Windows in 0.33.1, and the products they left (2026-10-01)

The writer census of **NFR-32 R7**, taken at the start of the 0.34.0 work package LF (marker P0340-LF-PRODUCTS) on the tree of `rel/0-34` at 72d1466d, which is 0.33.1 with the wave 1 packages merged and no LF change. A text file written without a stated line end gets CRLF on Windows and LF elsewhere; this report lists which writers of the package did so. Measured on **win32** (Windows 11, CPython 3.12.0), the one platform the CRLF appears on; the same census run on Linux reports every writer as LF, which is the reason a byte snapshot could not be compared across the two. No solver was run: the measurement is offline, over the recorded offline campaigns of the products snapshot.

## 1. Method

Two readings of the same tree. The static one reads the syntax of every module under `src/` and classifies each text write by what it states: a `write_text` or an `open` in a text writing mode that states no `newline` (or a `newline` other than `"\n"` and `""`) ends its lines with the platform's line end, a `csv.writer` that states no `lineterminator` ends its records with CRLF whatever the handle does, and a write of text encoded to bytes ends them with what the text holds. The measured one posts each of the 25 recorded offline campaigns of `tests/tier1_offline/test_products_snapshot.py` on win32 with text mode left as the platform has it, and reads as bytes every file the package wrote (`package_written` of `tests/tier1_offline/test_p0340_lf_products.py`: the products under `post/`, the emitted solver scripts, the run records and logs).

## 2. Result

- Static: 131 text writers under `src/`; **100 gave CRLF on Windows** (2 csv.writer, 18 open, 80 write_text) and 31 already wrote LF (a `newline` of `"\n"`, a csv writer with `lineterminator="\n"`, or text encoded to bytes). Three programs the solver runs write files from inside the solver and are strings in the source, so the syntax census does not read them; they are listed in section 4.
- Measured: of 381 files the package wrote over the 25 campaigns, **204 held a CR byte** on win32, in 16 distinct path forms (section 3). After the change the same measurement finds **0 of 381**.

## 3. The products and records that held CR on win32 (0.33.1)

| path in a campaign | campaigns holding it |
| --- | ---: |
| `additional.json` | 1 |
| `archive/additional-<STAMP>.json` | 1 |
| `logs/activity.log` | 25 |
| `logs/activity.log.jsonl` | 25 |
| `post/<matrix>/archive/<STAMP>/post.log` | 2 |
| `post/<matrix>/archive/<STAMP>/post.log.json` | 2 |
| `post/<matrix>/archive/<STAMP>/products.json` | 2 |
| `post/<matrix>/post.log` | 25 |
| `post/<matrix>/post.log.json` | 25 |
| `post/<matrix>/products.json` | 25 |
| `post/<matrix>/provenance/<product>.prov.json` | 25 |
| `post/<matrix>/provenance/archive/<STAMP>/<product>.prov.json` | 2 |
| `reports/superfile-0331.json` | 11 |
| `runs.json` | 21 |
| `sims/sim_N/scripts/<script>.txt` (the emitted solver scripts) | 1 |

## 4. The writers, by file

The writers that gave CRLF on win32 (static census, 0.33.1 tree):

| writer | function | kind |
| --- | --- | --- |
| `_progress.py:219` | `activity_event` | `open(a)` |
| `_progress.py:221` | `activity_event` | `open(a)` |
| `_progress.py:688` | `_live_log` | `open(x)` |
| `fsi/cli.py:76` | `init_dummy` | `write_text` |
| `fsi/cli.py:180` | `dummy_step` | `write_text` |
| `fsi/cli.py:186` | `dummy_step` | `write_text` |
| `fsi/cli.py:192` | `dummy_step` | `write_text` |
| `fsi/cli.py:120` | `coupled_step` | `open(a)` |
| `fsi/cli.py:153` | `dummy_step` | `write_text` |
| `fsi/cli.py:195` | `dummy_step` | `open(a)` |
| `fsi/cli.py:110` | `coupled_step` | `open(a)` |
| `fsi/config.py:752` | `dump_config` | `write_text` |
| `fsi/driver.py:429` | `_append_log` | `write_text` |
| `fsi/driver.py:431` | `_append_log` | `open(a)` |
| `fsi/nodes.py:830` | `write_node_file` | `write_text` |
| `fsi/nodes.py:844` | `write_node_map` | `write_text` |
| `fsi/nodes.py:1003` | `write_fsidisp` | `write_text` |
| `fsi/state.py:461` | `write_state_atomic` | `write_text` |
| `overview.py:303` | `overview` | `write_text` |
| `post/corrections.py:1372` | `sector_offset_calibration` | `write_text` |
| `post/products.py:1370` | `_write_the_products` | `write_text` |
| `post/products.py:1035` | `_campaign_products` | `write_text` |
| `post/products.py:650` | `write_campaign_products` | `open(w)` |
| `post/products.py:1047` | `_campaign_products` | `write_text` |
| `post/products.py:714` | `write_campaign_products` | `write_text` |
| `post/provenance.py:646` | `run_provenance` | `write_text` |
| `post/qsteady.py:360` | `write_point_validity_file` | `write_text` |
| `post/reductions.py:128` | `write_series` | `csv.writer` |
| `post/reductions.py:206` | `write_reduction` | `csv.writer` |
| `post/settings_table.py:467` | `write_settings_table` | `write_text` |
| `post/superfile.py:942` | `write_superfile_report` | `write_text` |
| `post/superfile.py:1062` | `write_sections_report` | `write_text` |
| `post/superfile.py:1081` | `_write_legacy_polar` | `write_text` |
| `post/writers.py:284` | `write_output_pair` | `write_text` |
| `post/writers.py:285` | `write_output_pair` | `write_text` |
| `probes/__init__.py:441` | `write_points_csv` | `write_text` |
| `qa/_spec_catalog_b.py:70` | `_probe_import_target` | `write_text` |
| `qa/_spec_catalog_b.py:606` | `_postrun_target` | `write_text` |
| `qa/_spec_ccs_noise.py:111` | `_ccs_file` | `write_text` |
| `qa/_spec_ccs_noise.py:269` | `_record_listing` | `write_text` |
| `qa/_spec_ccs_noise.py:548` | `_observers_file` | `write_text` |
| `qa/_spec_t1.py:78` | `_action_unsteady_setup` | `write_text` |
| `qa/compat.py:196` | `write_compat_report` | `write_text` |
| `qa/compat.py:197` | `write_compat_report` | `write_text` |
| `qa/compat.py:666` | `apply_compat` | `write_text` |
| `qa/drift.py:359` | `write_drift_report` | `write_text` |
| `qa/drift.py:360` | `write_drift_report` | `write_text` |
| `qa/geometry.py:355` | `write_stl` | `write_text` |
| `qa/matrix.py:763` | `drift_from_workspace` | `write_text` |
| `qa/physics.py:1234` | `write_physics_report` | `write_text` |
| `qa/physics.py:1235` | `write_physics_report` | `write_text` |
| `qa/physics.py:1413` | `update_reference` | `write_text` |
| `qa/probes.py:1416` | `_run_baseline` | `write_text` |
| `qa/probes.py:1482` | `_run_probe` | `write_text` |
| `qa/probes.py:1271` | `_validate_tiers` | `write_text` |
| `qa/specs.py:79` | `_run_script_target` | `write_text` |
| `qa/specs.py:365` | `_wake_edge_import_target` | `write_text` |
| `reference.py:879` | `help` | `write_text` |
| `run/_actions_counter.py:253` | `stage_counter` | `write_text` |
| `run/_executors.py:1564` | `export_surface_mesh` | `write_text` |
| `run/_executors.py:844` | `run_script` | `write_text` |
| `run/_executors.py:1057` | `_run_until_the_analysis_ends` | `open(w)` |
| `run/_executors.py:1058` | `_run_until_the_analysis_ends` | `open(w)` |
| `run/_executors.py:1029` | `wait_for_the_end` | `open(a)` |
| `run/_executors.py:1049` | `wait_for_the_end` | `open(a)` |
| `run/_executors.py:1133` | `_run_with_progress` | `open(a)` |
| `run/_executors.py:1149` | `_run_with_progress` | `open(a)` |
| `run/_identity.py:479` | `check_solver_identity` | `write_text` |
| `run/_pending.py:382` | `_write_pending_files` | `write_text` |
| `run/_pending.py:397` | `_write_pending_files` | `write_text` |
| `run/_plan.py:1086` | `plan_campaign` | `write_text` |
| `run/_points.py:755` | `_execute_point` | `write_text` |
| `run/_rebuild.py:154` | `_reactivate` | `write_text` |
| `run/_rebuild.py:1086` | `_rebuild_all` | `open(w)` |
| `run/_rebuild.py:931` | `rebuild` | `open(x)` |
| `run/_rebuild_evidence.py:181` | `collect_without_writing` | `write_text` |
| `run/cli.py:1144` | `_cmd_convert` | `open(w)` |
| `run/rename.py:875` | `_plan_changes` | `write_text` |
| `utils/manual.py:2258` | `write_chapter` | `write_text` |
| `workspace/__init__.py:2971` | `write_script` | `write_text` |
| `workspace/__init__.py:3802` | `_replace_manifest` | `write_text` |
| `workspace/__init__.py:2274` | `init` | `write_text` |
| `workspace/__init__.py:2285` | `init` | `write_text` |
| `workspace/__init__.py:3881` | `append_additional` | `write_text` |
| `workspace/excel_bridge.py:126` | `_write_response` | `write_text` |
| `workspace/excel_bridge.py:192` | `bridge` | `write_text` |
| `workspace/excel_file.py:377` | `preview_file` | `write_text` |
| `workspace/excel_file.py:347` | `preview_file` | `open(x)` |
| `workspace/fsi_setup.py:404` | `stage_fsi_setup` | `write_text` |
| `workspace/fsi_setup.py:405` | `stage_fsi_setup` | `write_text` |
| `workspace/inputs.py:1485` | `migrate_groups_to_pproc` | `write_text` |
| `workspace/inputs.py:506` | `strip_rotor_facts` | `write_text` |
| `workspace/sidecars.py:212` | `write_inventory` | `write_text` |
| `workspace/sidecars.py:406` | `ensure_inventory` | `write_text` |
| `workspace/storage.py:242` | `_replace_rows` | `write_text` |
| `workspace/storage.py:1179` | `_forget_products` | `write_text` |
| `workspace/storage.py:313` | `record_storage_call` | `write_text` |
| `workspace/storage.py:861` | `_forget_pruned_listings` | `write_text` |
| `workspace/wake_edges.py:565` | `write_trailing_edge_points` | `write_text` |
| `workspace/wake_edges.py:968` | `write_node_file` | `write_text` |

Programs the solver runs, written by the package as text and writing files of their own:

| source | program | writes |
| --- | --- | --- |
| `run/_actions_counter.py` | `TEMPLATE (counter program)` | write_text x2: the count file and the export script |
| `run/_actions_counter.py` | `COUNT_ONLY_TEMPLATE` | write_text x1: the count file |
| `cases/workflows/_clock.py` | `WALLTIME_CLOCK_TEMPLATE` | write_text x2: the stop script and the state file |

Writers that already wrote LF in 0.33.1 and went through the route unchanged in effect:

`post/_tables.py`, `post/boundary_layer.py`, `post/custom_polar.py`, `post/glossary.py`, `post/inflow_tools.py`, `post/qsteady.py`, `post/reductions.py`, `results/surface.py`, `run/_pending.py`, `run/_points.py`, `run/matrix.py`, `utils/database.py`, `workspace/__init__.py`, `workspace/_degenerate.py`, `workspace/_geometry_clean.py`, `workspace/fields.py`, `workspace/setup_standards.py`.

## 5. Not routed, with the reason

Binary writes are not text files and are not in the route: the byte-exact rewrite of a user's matrix (`cases/matrix.py`, which keeps the line end the user's file had), the glossary page (`post/glossary.py`, replaced block by block in bytes), the bytes of a pending input (`run/_pending.py`), the rotor table (`post/rotor_table.py`, the bytes of a table the route wrote), the matrix recode (`workspace/inputs.py`), and the workbooks (`workspace/excel_*.py`). The guard refuses a `write_bytes` of text encoded on the spot, so none of these is a disguised text write.

## 6. Evidence and its limits

NFR-32 R7, R1 to R3. The measurement is of this tree on one Windows machine; the numbers are counts of files and carry no research quantity. The solver reading an LF script is NOT established here: RPT-070 found that line ends change nothing in the disc profile file the solver reads, and the licensed runs of 0.34.0 are the confirmation (NFR-32 R6).
