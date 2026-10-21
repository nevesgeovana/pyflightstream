"""Private campaign product context, admission and native surface indexing.

The campaign facade supplies its mutable manifest and warning sinks. These
phases preserve record order and do not import the facade or launch a solver.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyflightstream.post._stage as _stage
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.cases import classify_outputs
from pyflightstream.post._condition import warn_pinned_states
from pyflightstream.post._installed_copies import INSTALLED_KIND as INSTALLED_KIND
from pyflightstream.post._settings_product import SETTINGS_KIND as SETTINGS_KIND
from pyflightstream.post._settings_product import write_settings_product as write_settings_product
from pyflightstream.post._stage import _PartialPost, _surface_export_skip
from pyflightstream.post._tables import ROTOR_TABLE_SUFFIX
from pyflightstream.post.provenance import refuse_an_existing_product
from pyflightstream.post.series import surface_export_metadata, translated_surface
from pyflightstream.results import FrozenSolve, UnjudgeableSolve
from pyflightstream.workspace import RunStatus, WorkspaceError, find_matrix, missing_log_warning
from pyflightstream.workspace.naming import ADDITIONAL_DIR
from pyflightstream.workspace.storage import STEP_EXPORTS_PRUNED

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.cases.pproc import PprocSpec
    from pyflightstream.post.superfile import SuperfileDraft
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


#: The statuses whose products ``check_frozen`` never withholds. RAN_MISSING_LOG is
#: one (FR-862): its freeze cannot be read, and the requirement
#: is that the post does not refuse it; the point's one WARNING says so.
_ADMITTED_WHEN_CHECKING = (
    RunStatus.CONVERGED,
    RunStatus.COMPLETED_MAX_ITER,
    RunStatus.MAX_ITER_REACHED,
    RunStatus.RAN_MISSING_LOG,
)


@dataclass(frozen=True)
class _CampaignProducts:
    """Inputs and ordered output sinks shared by the campaign writer phases."""

    workspace: CampaignWorkspace
    records: Sequence[RunRecord]
    by_sim: Mapping[str, list[RunRecord]]
    out: Path
    written: list[Path]
    products_index: dict[str, dict[str, object]]
    manifest: dict[str, object]
    skipped: dict[str, str]
    drafts: list[SuperfileDraft]
    rows_of_the_matrix: Mapping[str, MatrixRow]
    sweep_rows: Mapping[str, Mapping[str, object]] | None
    matrix_stem: str | None
    overwrite: bool
    archive: bool
    archive_stamp: datetime | None
    check_frozen: bool
    partial: _PartialPost | None
    #: The pproc each simulation followed (None where it could not be resolved),
    #: filled as the simulations are written, for the products that span them.
    pprocs: dict[str, PprocSpec | None] = field(default_factory=dict)


def _index_record_surfaces(
    ctx: _CampaignProducts,
    sim_id: str,
    record: RunRecord,
) -> FrozenSolve | None:
    # THE RECORD'S OWN RELEASE reads its outputs (G05): a 0.26.0 record's
    # `_vsec.vtk` is the surface export it was when written.
    """Index existing surface exports and record their missing or refused inputs."""
    output_kinds = classify_outputs(record.outputs, package_version=record.package_version)
    surface_freeze: FrozenSolve | None = None
    averages = (record.surface_time_averaging, record.surface_average_window)
    if any(window is not None for window in averages) and "log" in output_kinds:
        log_path = ctx.workspace.sim_dir(sim_id) / output_kinds["log"]
        if log_path is not None:
            surface_freeze = _stage.freeze_of_log(log_path)
    for kind, name in output_kinds.items():
        if kind not in ("tecplot", "vtk", "csv"):
            continue
        path = ctx.workspace.sim_dir(sim_id) / name
        relative = Path(os.path.relpath(path, ctx.out)).as_posix()
        if not path.is_file():
            ctx.skipped[relative] = f"the recorded {kind} surface export is missing: {path}"
            continue
        metadata = surface_export_metadata(record)
        reason = _surface_export_skip(
            metadata, surface_freeze, point=record.run_id, product=relative
        )
        if reason is not None:
            ctx.skipped[relative] = reason
            continue
        ctx.products_index[relative] = {
            "sim_id": sim_id,
            "pproc": record.pproc,
            "runs": [record.run_id],
            "format": kind,
            **metadata,
            **(translated_surface(record, path) if kind == "tecplot" else {}),
        }
    # G45: A TECPLOT THE RUN COULD NOT WRITE FROM ITS VTK is said, by the
    # sentence the run recorded, never left for a reader to notice.
    problems = [
        str(problem)
        for translation in record.surface_translations or []
        if isinstance(translation, Mapping)
        for problem in translation.get("problems") or []  # type: ignore[attr-defined]
    ]
    if problems:
        ctx.skipped[f"tecplot/{record.run_id}"] = "; ".join(problems)
    return surface_freeze


def _admit_campaign_records(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    *,
    sims: frozenset[str] | None,
    superseded: Mapping[str, str],
    check_frozen: bool,
    by_sim: dict[str, list[RunRecord]],
    skipped: dict[str, str],
) -> None:
    """Expand jobs in record order and admit each current point's products."""
    for record in records:
        if sims is not None and record.sim_id not in sims:
            continue  # FR-307: another simulation's records are not read.
        # FR-95: expand a multi-point job with as_points before checking status
        # or classifying outputs. Each successful point contributes its own
        # loads even if another point in the job failed. A single-point record
        # returns itself.
        for point_record in record.as_points():
            if point_record.run_id in superseded:
                continue
            frozen_failure = _record_has_frozen_failure(
                workspace, point_record, check_frozen=check_frozen
            )
            if not check_frozen or frozen_failure or point_record.status in _ADMITTED_WHEN_CHECKING:
                by_sim.setdefault(point_record.sim_id, []).append(point_record)
            else:
                skipped[f"runs/{point_record.run_id}"] = (
                    f"the recorded status is {point_record.status.value}; check_frozen=True "
                    "withholds this run's products. Collect complete outputs or run the "
                    "point again to settle its status."
                )
    # A fully pinned state at odds with p = rho R T is named in post.log.
    warn_pinned_states(point for points in by_sim.values() for point in points)


def _person_s_verdict(record: RunRecord) -> dict[str, object] | None:
    """Return the ``marked`` of a point a person judged CONVERGED (FR-414), else None."""
    marked = record.marked or {}
    return dict(marked) if marked.get("verdict") == RunStatus.CONVERGED.value else None


def _say_a_person_s_verdict(record: RunRecord) -> None:
    """Name, once in ``post.log``, a point whose CONVERGED is a person's verdict (FR-870)."""
    marked = _person_s_verdict(record)
    if marked is None or record.status is not RunStatus.CONVERGED:
        return
    warn(
        f"point={record.run_id} product=all: CONVERGED is a person's verdict "
        f"(mark-converged, {marked.get('at')}): {marked.get('reason')}; the run was "
        f"{marked.get('from')}, and the package did not judge it converged.",
        PyflightstreamWarning,
        stacklevel=5,
    )


def carry_marks(
    products_index: Mapping[str, dict[str, object]], points: Sequence[RunRecord]
) -> None:
    """Give every product entry built from a point a person judged its ``marked`` (FR-870).

    Keyed by run id under ``marked``, beside ``runs``; an entry built from no
    such point is left byte for byte as it was.
    """
    marks = {point.run_id: mark for point in points if (mark := _person_s_verdict(point))}
    if not marks:
        return
    for entry in products_index.values():
        # An additional product names its points under ``derives_from`` (its
        # ``runs`` would read as run ids to the retirement), so the mark follows both.
        runs: list[object] = []
        for key in ("runs", "derives_from"):
            named = entry.get(key)
            runs.extend(named if isinstance(named, list) else [])
        held = {run: marks[run] for run in runs if run in marks}
        if held:
            entry["marked"] = held


def _record_has_frozen_failure(
    workspace: CampaignWorkspace, point_record: RunRecord, *, check_frozen: bool = False
) -> bool:
    """Report a failed status and read whether its log proves a freeze.

    A RAN_MISSING_LOG point has no log to read: its one WARNING names the
    status and what is unavailable, and with ``check_frozen`` that its freeze
    cannot be read (FR-862).
    """
    frozen_failure = False
    _say_a_person_s_verdict(point_record)
    if point_record.status is RunStatus.RAN_MISSING_LOG:
        warn(
            missing_log_warning(point_record.run_id, check_frozen=check_frozen),
            PyflightstreamWarning,
            stacklevel=4,
        )
    elif point_record.status is RunStatus.MAX_ITER_REACHED:
        # FR-977: an ended run that is not a failure; its products are written
        # and its one WARNING names the point and the limit the run stopped at.
        warn(
            f"point={point_record.run_id} product=all: the recorded status is "
            f"{RunStatus.MAX_ITER_REACHED.value}: "
            f"{point_record.residual_note or 'the solver stopped at its requested iteration limit'}"
            "; every product is written from its outputs, which are not a settled solution.",
            PyflightstreamWarning,
            stacklevel=4,
        )
    elif point_record.status not in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER):
        warn(
            f"point={point_record.run_id} product=available-exports: "
            f"the recorded status is {point_record.status.value}. "
            "Collect complete outputs or run the point again to settle its status.",
            PyflightstreamWarning,
            stacklevel=4,
        )
    # Read a failed point's log for evidence of a freeze independently of
    # check_frozen. This admission check withholds nothing; the optional
    # averaging refusal is a separate decision.
    if point_record.status is RunStatus.FAILED_DIVERGED:
        kinds = classify_outputs(point_record.outputs)
        log_name = kinds.get("log")
        log_path = workspace.sim_dir(point_record.sim_id) / log_name if log_name else None
        if log_path is not None and log_path.is_file():
            # A log proving a freeze admits the point even when another block is
            # unreadable, preserving histories, instants and eligible averages for
            # their own checks. A log proving no freeze remains excluded without
            # raising here.
            verdict = _stage.freeze_of_log(log_path)
            frozen_failure = verdict is not None and (
                not isinstance(verdict, UnjudgeableSolve) or verdict.frozen_from is not None
            )
    return frozen_failure


def _warn_unreadable_matrix(
    workspace: CampaignWorkspace,
    matrix_stem: str | None,
    rows_of_the_matrix: Mapping[str, MatrixRow],
) -> None:
    """Explain why post choices must fall back to the recorded matrix values."""
    if matrix_stem and not rows_of_the_matrix:
        # SAID, NOT SWALLOWED (PO-06). `matrix_rows` answers `{}` for a matrix that
        # is in neither home, for one it cannot parse, and (RST-1) for a
        # stem held in both homes with different bytes, and every post-only
        # choice then falls back to the run records in silence: an edited window
        # does nothing and the rotor tables, which need the row's reference, are
        # not written at all.
        try:
            found = find_matrix(workspace.root, matrix_stem)
            state = (
                "cannot be read"
                if found is not None
                else "is in neither the workspace root nor inputs/matrices/"
            )
        except WorkspaceError as two_homes:
            state = f"is refused: {two_homes}"
        warn(
            f"the matrix {matrix_stem}.fs {state}. Every post-only choice falls back to the run "
            "records, and the rotor tables, which take their geometry from the row's "
            "reference, are not written.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def products_to_retire(
    skipped: Mapping[str, str],
    previous_products: Mapping[str, Mapping[str, object]],
) -> set[str]:
    """Return every product of a previous post that this post's refusals retire.

    A refused rebuild MUST retire the product it refuses. The manifest stops
    naming it, and a file left beside the new ones is read as current: the
    numbers in it are the ones the refusal says cannot be trusted.

    A skip is named after what was refused
    and that is not always a file:

    * ``polars/<file>.csv`` -- the file itself, with or without a ``#marker``.
    * ``sections/<stem>#distributions`` -- a family of files that share a stem.
    * ``runs/<run_id>`` -- previous entries whose ``runs`` include this point.
      The caller keeps files regenerated from surviving points or independent exports.
    * ``polars/<sim>#rotor_tables`` -- the rotor tables of ONE SIMULATION, whose
      files are ``polars/P<sim>-<alias>_rotor.csv`` and share no prefix with the
      skip key at all. The previous
      manifest records each product's ``sim_id``, so the identity is read rather
      than parsed out of a name.
    """
    refused = {name.split("#", 1)[0] for name in skipped}
    refused.update(
        name for name, entry in previous_products.items() if entry.get("sim_id") in skipped
    )
    refused_runs = {name.removeprefix("runs/") for name in skipped if name.startswith("runs/")}
    refused.update(
        name
        for name, entry in previous_products.items()
        if isinstance(runs := entry.get("runs"), list) and any(run in refused_runs for run in runs)
    )
    distribution_prefixes = [
        name.split("#", 1)[0] + "_" for name in skipped if name.endswith("#distributions")
    ]
    refused.update(
        name
        for name in previous_products
        if any(name.startswith(prefix) for prefix in distribution_prefixes)
    )
    refused.update(
        name
        for name, entry in previous_products.items()
        if name.endswith(ROTOR_TABLE_SUFFIX)
        and f"{_stage.POLARS_DIR}/{entry.get('sim_id')}#rotor_tables" in skipped
    )
    return refused


def products_kept_after_pruning(
    skipped: Mapping[str, str],
    previous_products: Mapping[str, Mapping[str, object]],
    out: Path,
) -> dict[str, dict[str, object]]:
    """Return the previous products a refusal for a pruned step keeps, with their entries.

    A PRODUCT MADE BEFORE ``free-space`` PRUNED ITS STEPS STAYS. The
    refusal is about rebuilding it, not about the file already made from
    every step: that file stays in its folder and its previous entry stays in
    the manifest, marked ``kept_after_pruning`` with the refusal. A refusal
    opens with :data:`~pyflightstream.workspace.storage.STEP_EXPORTS_PRUNED`
    and is keyed by the product's own name; a product sharing that name's
    stem (the VTK beside an averaged Tecplot) is kept with it. Only a file
    still on disk is kept.
    """
    kept: dict[str, dict[str, object]] = {}
    for key, reason in skipped.items():
        if not str(reason).startswith(STEP_EXPORTS_PRUNED):
            continue
        base = key.split("#", 1)[0]
        family = base.rsplit(".", 1)[0]
        for name, entry in previous_products.items():
            same = name == base or name.rsplit(".", 1)[0] == family
            if same and (out / name).is_file():
                kept[name] = {**entry, "kept_after_pruning": reason}
    return kept


def _retire_campaign_products(
    out: Path,
    *,
    skipped: dict[str, str],
    previous_products: Mapping[str, dict[str, Any]],
    products_index: dict[str, dict[str, object]],
    by_sim: Mapping[str, list[RunRecord]],
    archive: bool,
    archive_stamp: datetime,
) -> None:
    # What a previous post made from steps free-space has since
    # pruned stays, file and entry, and is therefore not retired below.
    """Retire campaign products."""
    for name, entry in products_kept_after_pruning(skipped, previous_products, out).items():
        products_index.setdefault(name, entry)
    # Retire refused generated tables under both rebuild policies. Native exports
    # outside this folder remain evidence and are never removed here.
    for name, entry in previous_products.items():
        if (
            name.startswith(f"{_stage.POLARS_DIR}/")
            and entry.get("sim_id") in by_sim
            and name not in products_index
        ):
            skipped.setdefault(
                name,
                f"retired previous table of simulation {entry['sim_id']}: no current "
                "product uses this name; polar names follow contributing records",
            )
    # G12: an additional product no current extraction supplies is retired,
    # archived like a refused table, rather than left in its folder unnamed.
    for name in previous_products:
        if name.startswith(f"{ADDITIONAL_DIR}/") and name not in products_index:
            skipped.setdefault(
                name,
                "retired previous additional product: no current extraction supplies this file",
            )
    _retire_optional_products(skipped, previous_products, products_index)
    refused = products_to_retire(skipped, previous_products)
    for name in refused - products_index.keys():
        if name in previous_products:
            skipped.setdefault(
                name, "retired previous product; its inputs no longer supply this file"
            )
        path = out / name
        if path.resolve().is_relative_to(out.resolve()) and path.is_file():
            refuse_an_existing_product(path, archive=archive, stamp=archive_stamp)
            if not archive:
                path.unlink()


def _retire_optional_products(
    skipped: dict[str, str],
    previous_products: Mapping[str, dict[str, Any]],
    products_index: Mapping[str, dict[str, object]],
) -> None:
    """Retire a previous optional product that the pproc no longer asks for (FR-419).

    A table the pproc stopped requesting is not rewritten, and a file left beside
    the new products is read as current; each is named in ``skipped`` so the
    retirement below archives or removes it, as it does for a refused table.
    """
    for name, entry in previous_products.items():
        if entry.get("kind") in _OPTIONAL_KINDS and name not in products_index:
            skipped.setdefault(
                name,
                "retired previous product; this post no longer writes it "
                "([products] key, or no snapshot)",
            )


#: The ``kind`` of the products a pproc key switches on and off (FR-419).
_OPTIONAL_KINDS = (SETTINGS_KIND, INSTALLED_KIND, "loading_noise")
