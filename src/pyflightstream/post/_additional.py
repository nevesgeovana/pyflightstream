"""The products of the additional post: each current extraction, by the run's own builders.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0), called by the campaign stage of :mod:`pyflightstream.post.products`
(G12). The additional post re-opens a saved simulation with another pproc
artifact and extracts what the run did not; its products are written under
``post/<matrix>/additional/<pid>/`` by the very simulation stage the run's
own products use (:func:`pyflightstream.post._sim._sim_products`), so an
extraction's polar, sections and plots tables are built by one rule.

An extraction is read only while it is CURRENT (:func:`_current_extraction`):
its point is admitted, its saved simulation is the one it opened, and every
file it wrote is on disk and hashes as recorded. One that is not is a skip
of its own, keyed under ``additional/`` so it never retires the run's main
products. The surface solution and the plots history an extraction wrote
are indexed as the solver wrote them (:data:`_ADDITIONAL_NATIVE_KINDS`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.cases import classify_outputs
from pyflightstream.post._condition import _resolve_post_pproc
from pyflightstream.post._sim import _sim_products
from pyflightstream.post._tables import ProductError, ProductExistsError
from pyflightstream.post.series import translated_surface
from pyflightstream.workspace import ExtractionStatus
from pyflightstream.workspace.naming import ADDITIONAL_DIR

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import AdditionalRecord, CampaignWorkspace, RunRecord


#: The export kinds of an extraction that are indexed as the solver wrote them,
#: beside the tables built from it: the surface solution in each format, and on
#: an unsteady point the plots history, which is the run's own (RPT-062).
_ADDITIONAL_NATIVE_KINDS = ("tecplot", "vtk", "csv", "plots")


def _current_extraction(
    workspace: CampaignWorkspace, extraction: AdditionalRecord, point: RunRecord | None
) -> str | None:
    """Say why an extraction no longer describes its point, or None when it does.

    CURRENT means three things: the point is an admitted record of this post, its
    saved simulation is still the one the extraction opened (a forced rerun or a
    continuation archives the point's folder, extraction included, and saves
    another), and every file the extraction wrote is on disk and hashes as it
    recorded.

    THE SAVED SIMULATION IS HASHED ON DISK, not only read off the two records:
    a file deleted or replaced under a record nobody rewrote is not the state
    the extraction opened, and a product of it would describe a state nothing on
    disk holds.
    """
    if point is None:
        return (
            f"the point {extraction.run_id} is not a record this post admits (continued, "
            "withheld by check_frozen, or no longer in the manifest), so its extraction "
            "describes nothing the products hold"
        )
    now = point.outputs_sha256.get(extraction.fsm)
    if now != extraction.fsm_sha256:
        return (
            f"stale: the point's saved simulation {extraction.fsm} is "
            f"{(now or 'unrecorded')[:12]} in its record and the extraction opened "
            f"{extraction.fsm_sha256[:12]}; the point ran again, so extract it again "
            "(pyfs-matrix post --additional-pproc)"
        )
    folder = workspace.sim_dir(extraction.sim_id)
    saved = folder / extraction.fsm
    on_disk = file_sha256(saved) if saved.is_file() else None
    if on_disk != extraction.fsm_sha256:
        found = "is gone" if on_disk is None else f"hashes {on_disk[:12]} on disk"
        return (
            f"stale: the point's saved simulation {saved} {found}, and the extraction "
            f"opened {extraction.fsm_sha256[:12]}; its products would describe a state "
            "nothing on disk holds"
        )
    # ONE PREDICATE WITH THE REUSE OF THE EXTRACTION PASS, so a file refused
    # here is one the next --additional-pproc extracts again.
    changed = workspace.changed_extraction_file(extraction)
    if changed is not None:
        return f"stale: {changed}; extract the point again (pyfs-matrix post --additional-pproc)"
    return None


def _additional_products(
    workspace: CampaignWorkspace,
    admitted: Mapping[str, RunRecord],
    out: Path,
    written: list[Path],
    products_index: dict[str, dict[str, object]],
    skipped: dict[str, str],
    *,
    rows_of_the_matrix: Mapping[str, MatrixRow],
    matrix_stem: str | None,
    overwrite: bool,
    archive: bool,
    archive_stamp: datetime | None,
    check_frozen: bool,
    sims: frozenset[str] | None = None,
) -> None:
    """Write the products of every current extraction of the additional post (G12).

    READS ``additional.json`` AND NOTHING ELSE NEW, so the stage stays one that
    needs no executable. Each extraction is taken at its latest EXTRACTED record,
    and only while CURRENT (:func:`_current_extraction`); one that is not is a
    skip keyed ``additional/<pid>/runs/<extraction id>`` and NEVER ``runs/<run
    id>``, which would retire the main products of the run it came from.

    THE ONE-RULE ROUTE. The current extractions of one simulation and one pproc
    are handed to :func:`_sim_products` as point records carrying the
    extraction's files and the additional pproc, under
    ``post/<matrix>/additional/<pid>/`` (with ``sims``, FR-307, only those
    simulations' extractions are read): the group polars, the sections tables
    and, on an unsteady point, the plots tables and their reductions come from
    the builders the run's own products use. The loads and the surface are the
    ones the run left (RPT-062), so what is new is what the pproc asks of them.
    Each record keeps the RUN's log, not the extraction's, because a frozen solve
    is a fact of the run. Every entry carries three marks: ``pproc`` (the
    additional id), ``additional`` (true) and ``extraction`` (the extraction
    ids), with ``derives_from`` naming the points; the surface exports and the
    plots history are indexed as the solver wrote them, with the same marks.
    """
    extractions: dict[str, AdditionalRecord] = {}
    for extraction in workspace.read_additional():
        if extraction.matrix_stem != matrix_stem:
            continue
        if sims is not None and extraction.sim_id not in sims:
            continue
        if extraction.status is ExtractionStatus.EXTRACTED:
            extractions[extraction.extraction_id] = extraction
    groups: dict[tuple[str, str], list[tuple[AdditionalRecord, RunRecord]]] = {}
    for extraction in extractions.values():
        prefix = f"{ADDITIONAL_DIR}/{extraction.pproc}"
        point = admitted.get(extraction.run_id)
        reason = _current_extraction(workspace, extraction, point)
        if reason is not None or point is None:
            skipped[f"{prefix}/runs/{extraction.extraction_id}"] = str(reason)
            continue
        groups.setdefault((extraction.sim_id, extraction.pproc), []).append((extraction, point))
    for (sim_id, pid), pairs in groups.items():
        prefix = f"{ADDITIONAL_DIR}/{pid}"
        point_of = {extraction.extraction_id: point.run_id for extraction, point in pairs}
        synthetic = []
        for extraction, point in pairs:
            own_log = classify_outputs(point.outputs).get("log")
            files = [
                name for name in extraction.outputs if classify_outputs([name]).get("log") is None
            ]
            synthetic.append(
                point.model_copy(
                    update={
                        "run_id": extraction.extraction_id,
                        "outputs": files + ([own_log] if own_log else []),
                        "outputs_sha256": dict(extraction.outputs_sha256),
                        "pproc": pid,
                        "sections_layout": [dict(block) for block in extraction.sections_layout],
                        "points_ran": [],
                        "probe_points_file": None,
                    }
                )
            )
            if extraction.unsteady:
                # SAID PER EXTRACTION, in the form the post log files under its point
                # and product, because the table below is one instant of the run.
                warn(
                    f"point={extraction.run_id} product={prefix}: the extraction is the "
                    "LAST instant of the run, one instant and not its history (RPT-062); "
                    "its sections table states that step.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
            for kind, name in classify_outputs(extraction.outputs).items():
                if kind not in _ADDITIONAL_NATIVE_KINDS:
                    continue
                path = workspace.sim_dir(sim_id) / name
                products_index[Path(os.path.relpath(path, out)).as_posix()] = {
                    "sim_id": sim_id,
                    "pproc": pid,
                    "additional": True,
                    "extraction": [extraction.extraction_id],
                    "derives_from": [extraction.run_id],
                    "format": kind,
                    **({"kind": "instant"} if extraction.unsteady and kind != "plots" else {}),
                    **(translated_surface(extraction, path) if kind == "tecplot" else {}),
                }
        try:
            files_written, names, reductions_skipped = _sim_products(
                workspace,
                sim_id,
                synthetic,
                out / ADDITIONAL_DIR / pid,
                overwrite=overwrite,
                archive=archive,
                archive_stamp=archive_stamp,
                matrix_row=rows_of_the_matrix.get(sim_id),
                sweep_rows=None,
                drafts=None,
                check_frozen=check_frozen,
                effective_pproc=_resolve_post_pproc(workspace, pid),
            )
        except ProductExistsError:
            raise
        except ProductError as error:
            skipped[f"{prefix}/{sim_id}"] = str(error)
            warn(
                f"additional products of simulation {sim_id} ({pid}) not written: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
            continue
        written.extend(files_written)
        for name, entry in names.items():
            # THE EXTRACTIONS A PRODUCT HOLDS, under their own key: `runs` names
            # run ids everywhere else in the index, and the retirement of a
            # refused run reads it, so it is not written for an extraction.
            runs = entry.get("runs")
            held = [str(run) for run in runs] if isinstance(runs, list) else list(point_of)
            marked = {key: value for key, value in entry.items() if key != "runs"}
            products_index[f"{prefix}/{name}"] = {
                "sim_id": sim_id,
                "pproc": pid,
                "additional": True,
                "extraction": held,
                "derives_from": [point_of[held_id] for held_id in held if held_id in point_of],
                **marked,
            }
        for name, reason in reductions_skipped.items():
            skipped[f"{prefix}/{name}"] = reason
