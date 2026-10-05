"""The console printing of the ``pyfs-matrix`` commands.

Pipeline role: lays out what ``pyfs-matrix plan`` and the storage commands
(``free-space``, ``delete-sims``, ``sync``) print, from the entries and the plan
their commands built. Nothing here reads the workspace or decides an exit
code; the commands stay in :mod:`pyflightstream.run.cli`, which calls these
functions, and the text printed is unchanged by the move (AD-18).
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from typing import Any

from pyflightstream._console import blocks, table, wrap
from pyflightstream._progress import print_held_warnings
from pyflightstream.run import (
    CampaignPlan,
    format_cost_table,
    inflow_harmonics_line,
    qsteady_validity_line,
)
from pyflightstream.run._alias import alias_lines
from pyflightstream.run._batch_plan import grouping_table_lines
from pyflightstream.run._continuation_frame import continuation_block


def _print_free_space_paths(step: dict[str, Any], applied: bool) -> None:
    """Print every path one free-space step touches, read from the step's own entry.

    ``pyfs-matrix free-space --list`` (FR-305): nothing is recomputed here;
    the paths, sizes and reasons are the ones ``storage.free_space`` returned
    and recorded in ``storage_management.json``.
    """
    from pyflightstream.workspace.storage import human_bytes

    done = "deleted" if applied else "would delete"
    stated = "keep_last" in step or "delete_steps" in step
    if step["mode"] == "prune_step_exports":
        for point in step["points"]:
            for item in point["files"]:
                print(
                    f"      {item['path']}  {human_bytes(item['bytes'])}  {done} "
                    f"(step {item['step']})"
                )
            for relative in point["protected"]:
                print(f"      {relative}  kept (a record names it as an output)")
            for item in point["kept"]:
                print(
                    f"      {item['path']}  kept ({'' if stated else 'last '}step {item['step']})"
                )
    elif step["mode"] == "compact_sims":
        for item in step["sims"]:
            if applied:
                print(
                    f"    sims/sim_{item['sim_id']}  {human_bytes(item['bytes_before'])}  "
                    f"compacted into {item['archive']} ({human_bytes(item['bytes_after'])})"
                )
            else:
                print(
                    f"    sims/sim_{item['sim_id']}  {human_bytes(item['bytes'])}  "
                    "would be compacted"
                )
    elif step["mode"] == "delete_extensions":
        for item in step["files"]:
            print(f"    {item['path']}  {human_bytes(item['bytes'])}  {done}")
        for relative in step["kept"]:
            print(f"    {relative}  kept (a later post needs it)")
    else:
        if step["action"] == "compact":
            verb = "compacted" if applied else "would be compacted"
        else:
            verb = done
        for item in step["archives"]:
            line = f"    {item['path']}  {human_bytes(item['bytes'])}  {verb}"
            if "archive" in item:
                line += f" into {item['archive']}"
            print(line)


def _print_free_space(entry: dict[str, Any], *, list_paths: bool = False) -> None:
    from pyflightstream.workspace._step_prune import kept_phrase
    from pyflightstream.workspace.storage import human_bytes

    mode = "APPLIED" if entry["applied"] else "preview"
    print(f"free-space {entry['recipe']} ({mode})")
    for step in entry["steps"]:
        if step["mode"] == "prune_step_exports":
            files = [item for point in step["points"] for item in point["files"]]
            print(
                f"  prune_step_exports: {len(step['points'])} point(s), {len(files)} per-step "
                f"file(s), {human_bytes(sum(item['bytes'] for item in files))}; "
                f"{kept_phrase(step)} kept"
            )
            for point in step["points"]:
                steps = point["deleted_steps"]
                shown = f"{steps[0]} to {steps[-1]}" if steps else "none"
                print(f"    {point['folder']}: steps {shown} ({len(steps)} step(s))")
            for sim, why in step["refused"].items():
                print(f"    refused sim {sim}: {why}")
        elif step["mode"] == "compact_sims":
            sims = [str(item["sim_id"]) for item in step["sims"]]
            print(f"  compact_sims: {len(sims)} sim(s) {', '.join(sims)}")
            for sim, why in step["refused"].items():
                print(f"    refused sim {sim}: {why}")
        elif step["mode"] == "delete_extensions":
            size = sum(item["bytes"] for item in step["files"])
            print(
                f"  delete_extensions {', '.join(step['extensions'])}: {len(step['files'])} "
                f"file(s), {human_bytes(size)}; {len(step['kept'])} kept (a later post needs them)"
            )
        else:
            size = sum(item["bytes"] for item in step["archives"])
            print(
                f"  post_archives ({step['action']}): {len(step['archives'])} folder(s), "
                f"{human_bytes(size)}"
            )
        if list_paths:
            _print_free_space_paths(step, entry["applied"])
    if entry["applied"]:
        print(f"  freed {human_bytes(entry['bytes_freed'])}")
    else:
        print("preview only: run again with --apply to change files")


def _print_delete_sims(entry: dict[str, Any]) -> None:
    from pyflightstream.workspace.storage import human_bytes

    mode = "APPLIED" if entry["applied"] else "preview"
    print(f"delete-sims ({mode})")
    for item in entry["sims"]:
        print(
            f"  sim {item['sim_id']}: {len(item['run_ids'])} record(s), "
            f"{human_bytes(item['bytes'])}, matrix {', '.join(item['matrix'])}"
        )
    for sim in entry.get("forced_submitted", []):
        print(f"  sim {sim}: still SUBMITTED, deleted because of --force")
    for folder, found in entry["post"].items():
        print(f"  {folder}: {len(found['own'])} own product(s)")
        for name in found["shared"]:
            print(f"    shared with other points (stale after delete): {name}")
    if not entry["applied"]:
        if entry["stale"]:
            print("  choose --matrix-products points-only or regenerate before --apply")
        print("preview only: run again with --apply to delete")


def _print_sync(entry: dict[str, Any]) -> None:
    from pyflightstream.workspace.storage import human_bytes, sync_summary_lines

    mode = "APPLY" if entry["applied"] else "preview"
    print(f"[{entry['source_name']}] {entry['source']}   level {entry['level']}   {mode}")
    if "skipped" in entry:
        print(f"  skipped: {entry['skipped']}")
        return
    runs, files = entry["runs"], entry["files"]
    print(
        f"  {runs.get('manifest', 'runs.json')}: {len(runs['added'])} added, "
        f"{len(runs['replaced'])} replaced, "
        f"{len(runs['conflicts'])} conflicts, {runs['records_before']} -> "
        f"{runs['records_after']} records"
    )
    for conflict in runs["conflicts"]:
        print(f"    CONFLICT run {conflict.get('run_id')}: {conflict} (main kept)")
    if runs["submitted_sims_record_only"]:
        print(
            "    still SUBMITTED there (record only, no files yet): sims "
            + ", ".join(runs["submitted_sims_record_only"])
        )
    print(
        f"  files: {files['to_copy']} to copy, {files['to_overwrite']} to overwrite, "
        f"{files['identical']} identical, {len(files['conflicts'])} conflicts (main kept)"
    )
    for conflict in files["conflicts"][:20]:
        print(f"    CONFLICT file {conflict}")
    # 0.32.0 (package B2): archives skipped, the sims/ folders, the restore.
    for line in sync_summary_lines(entry):
        print(line)
    for sim, what in entry.get("inputs_links", {}).items():
        print(f"  {sim}/inputs: {what}")
    matrices = entry.get("matrices", {})
    for conflict in matrices.get("conflicts", []):
        winner = "its copy" if conflict["kept"] != "main" else "main's copy"
        print(
            f"  MERGE CONFLICT matrix {conflict['matrix']}: main and {entry['source_name']} "
            f"differ; {conflict['owner']} owns it, so {winner} is kept"
        )
    for item in matrices.get("copied", []):
        verb = "replaces main's" if item["replaced_main"] else "copied"
        print(f"  matrix {item['matrix']}: {verb} ({item['path']})")
    for item in matrices.get("not_copied", []):
        print(f"  matrix {item['matrix']}: not copied, {item['reason']}")
    # 0.30.0: the points the other workspace planned that no merged record carries.
    for stem, plan in entry.get("plan_points_without_record", {}).items():
        if "error" in plan:
            print(f"  plan {stem}: {plan['error']}")
            continue
        missing = plan["without_record"]
        if not missing:
            print(f"  plan {stem}: all {plan['planned']} planned point(s) have a record")
            continue
        print(
            f"  PLANNED WITHOUT RECORD {stem}: {len(missing)} of {plan['planned']} planned "
            "point(s) have no record in the merged runs.json:"
        )
        for run_id in missing:
            print(f"    {run_id}")
    if entry["applied"]:
        print(f"  applied: {human_bytes(entry['bytes_copied'])} copied")


def _print_plan(
    plan: CampaignPlan,
    matrix: str,
    held: list[warnings.WarningMessage],
    *,
    cost: bool,
    rows: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Print a plan as titled blocks, a blank line between two (0.31.0).

    STDOUT carries every block but the warnings, as it carried the summary
    before; the warnings stay on stderr, held until the header is out so they
    arrive under their own title. A block with nothing to say is not printed.
    """
    header = [
        f"  matrix: {matrix}",
        f"  campaign: {plan.campaign}",
        f"  FlightStream build: {plan.fs_version}",
    ]
    print(blocks([("pyfs-matrix plan", header)]), flush=True)
    print_held_warnings(held)
    rest = blocks(_plan_blocks(plan, cost=cost, rows=rows))
    if rest:
        # After the warnings the blank line is already out.
        print(rest if held else f"\n{rest}", flush=True)


def _alias_block(plan: CampaignPlan, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return one line per planned point: its run id alias beside the point (FR-395 R3)."""
    planned: dict[str, list[str]] = {}
    for entry in plan.points:
        planned.setdefault(entry.sim_id, []).append(_point_of(entry.run_id))
    return [
        f"  {alias}  POL {sim} {point}"
        for alias, sim, point in alias_lines(rows, planned)
        if point in planned[sim]
    ]


def _plan_blocks(
    plan: CampaignPlan, *, cost: bool, rows: Sequence[Mapping[str, Any]] = ()
) -> list[tuple[str, list[str]]]:
    """Return every block of a plan after its header and its warnings, titled, in order."""
    from pyflightstream.workspace.setup_inspection import setup_inspection_block

    cases = [
        f"  points: {len(plan.ready)} ready, {len(plan.blocked)} blocked, "
        f"{len(plan.already_recorded)} already recorded"
    ]
    if plan.build_groups:
        cases.append(f"  solver installations: {len(plan.build_groups)}")
        for key, sims in plan.build_groups.items():
            cases.extend(
                wrap(
                    f"{CampaignPlan.installation_label(key)}: {len(sims)} case(s) "
                    f"({', '.join(sims)})",
                    first="    ",
                )
            )
    waiving = [entry for entry in plan.points if entry.waived_commands]
    if waiving:
        commands = sorted({name for entry in waiving for name in entry.waived_commands})
        cases.extend(
            wrap(
                f"{len(waiving)} point(s) waive a command recorded broken: {', '.join(commands)}",
                first="  ",
            )
        )
    raw = [entry for entry in plan.points if entry.raw]
    if raw:
        cases.append(f"  {len(raw)} point(s) use the raw() escape hatch")
    blocked: list[str] = []
    for entry in plan.blocked:
        blocked.append(f"  {entry.run_id}")
        blocked.extend(wrap(str(entry.error), first="    "))
    validity: list[str] = []
    for entry in plan.points:
        if not entry.qsteady_validity:
            continue
        validity.append(f"  POL {entry.sim_id} point {_point_of(entry.run_id)}")
        validity.extend(wrap(qsteady_validity_line(entry.qsteady_validity), first="    "))
        harmonics = entry.qsteady_validity.get("inflow_fft")
        if isinstance(harmonics, Mapping):
            validity.extend(wrap(inflow_harmonics_line(harmonics), first="    "))
    costs: list[str] = []
    if plan.costs:
        costs = format_cost_table(plan.costs).splitlines()
    elif cost:
        # A FLAG THE USER PASSED MUST ANSWER. `point_costs` returns nothing
        # when no planned point resolves to a case, and printing nothing is
        # indistinguishable from not having passed the flag at all (the
        # interface lens, 2026-09-11).
        costs = wrap(
            "no cost row: none of the planned points resolved to a case of this "
            "matrix, so there is nothing to table. The plan above still stands.",
            first="  ",
        )
    files = [f"  plan: {plan.plan_file}"] if plan.plan_file is not None else []
    files.extend(f"  guide: {guide}" for guide in plan.guides)
    return [
        ("Cases", cases),
        ("Point aliases", _alias_block(plan, rows)),
        (f"Blocked points ({len(plan.blocked)})", blocked),
        ("Continuations (RESTART)", continuation_block(plan.points)),
        ("Rotor Mach numbers", _rotor_mach_block(plan)),
        ("Quasi-steady validity per point", validity),
        ("Solver setup per case", setup_inspection_block(plan.setup_inspections)),
        ("Solver cost per point", costs),
        ("Batch jobs", grouping_table_lines(plan.grouping) if plan.grouping else []),
        ("Files written", files),
    ]


def _point_of(run_id: str) -> str:
    """Return the point name a run id ends with (``<campaign>/sim_<POL>/<point>``)."""
    return run_id.rpartition("/")[2]


def _rotor_mach_block(plan: CampaignPlan) -> list[str]:
    """Return one aligned row per rotor per point, then each rotor the plan could not compute."""
    rows = [["POL", "point", "rotor", "M_tip", "M_hel"]]
    unknown: list[str] = []
    for entry in plan.points:
        for alias, mach in entry.rotor_mach.items():
            rotor = f"{mach.get('kind') or 'rotor'} {alias}"
            tip, helical = mach.get("mach_tip"), mach.get("mach_helical")
            if isinstance(tip, int | float) and isinstance(helical, int | float):
                rows.append(
                    [entry.sim_id, _point_of(entry.run_id), rotor, f"{tip:.3f}", f"{helical:.3f}"]
                )
            else:
                unknown.extend(
                    wrap(
                        f"POL {entry.sim_id} point {_point_of(entry.run_id)}, {rotor}: "
                        f"M_tip and M_hel not computed: {mach.get('note')}",
                        first="  ",
                    )
                )
    return [*(table(rows) if len(rows) > 1 else []), *unknown]
