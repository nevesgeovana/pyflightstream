"""The settings table and its codebook as a campaign product (FR-419).

Pipeline role: the post stage, after the simulations' products. The library
writer :func:`pyflightstream.post.settings_table.write_settings_table` has
existed since 0.22.0 with no caller; this module is the caller. With
``[products] settings_codebook = true`` in a simulation's pproc, the
simulation's recorded points enter ONE table per matrix, one numeric row per
point, written from the solver-setup snapshot each record carries.

A row opens with ``POL`` and ``RUN_ID``, its key, as every table of the post opens
with its polar; the rest is the numeric wide form. A point whose record holds no
usable snapshot gets no row, never a blank one, and is named by one INFO line of
``post.log``: it is not a skip, since the table is on by default and a record that
predates the snapshot is not a refused product. With no snapshot anywhere the two
files are not written and ``post.log`` says so once.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._tokens import POLAR_ID_COLUMN
from pyflightstream.post._stage import post_note
from pyflightstream.post.provenance import refuse_an_existing_product
from pyflightstream.post.settings_table import write_settings_table
from pyflightstream.script.solver_setup import SolverSetup

if TYPE_CHECKING:
    from pyflightstream.post._products_campaign import _CampaignProducts
    from pyflightstream.workspace import RunRecord

__all__: list[str] = []

#: The folder of the settings products under a matrix's products folder.
SETTINGS_DIR = "settings"
#: The ``kind`` of both files in ``products.json``.
SETTINGS_KIND = "settings_codebook"


def _snapshot_of(point: RunRecord) -> SolverSetup | str:
    """Return a point's setup snapshot, or the reason it has none."""
    if not point.solver_setup:
        return "its record holds no solver-setup snapshot"
    try:
        return SolverSetup.model_validate(point.solver_setup)
    except ValueError as error:
        return f"its recorded solver-setup snapshot cannot be read: {error}"


def _asking_sims(ctx: _CampaignProducts) -> list[str]:
    """Return the simulations whose pproc asks for the table, in post order."""
    asking = []
    for sim_id in ctx.by_sim:
        pproc = ctx.pprocs.get(sim_id)
        if pproc is not None and pproc.products.settings_codebook:
            asking.append(sim_id)
    return asking


def write_settings_product(ctx: _CampaignProducts) -> None:
    """Write the matrix's settings table and codebook where a pproc asks for them.

    Parameters
    ----------
    ctx : _CampaignProducts
        The campaign's context: its admitted records by simulation, the pproc
        each simulation followed, and the sinks the manifest is written from.
        A post limited to some simulations does not rebuild the table, whose
        rows span the whole matrix; it names the files in ``partial.not_rebuilt``
        as it does for a super file.
    """
    sims = _asking_sims(ctx)
    if not sims:
        return
    stem = ctx.out.name
    table = f"{SETTINGS_DIR}/{stem}_settings.csv"
    legend = f"{SETTINGS_DIR}/{stem}_settings.codebook.json"
    if ctx.partial is not None:
        for name in (table, legend):
            ctx.partial.not_rebuilt.setdefault(
                name,
                "the settings table has one row per point of the whole matrix, so a post "
                f"limited to some simulations does not write it; {ctx.partial.whole} writes it",
            )
        return
    setups: list[SolverSetup] = []
    keys: list[dict[str, str]] = []
    for sim_id in sims:
        for record in ctx.by_sim[sim_id]:
            for point in record.as_points():
                snapshot = _snapshot_of(point)
                if isinstance(snapshot, str):
                    # AN INFO LINE AND NOT A SKIP: the table is on by default, and a record
                    # that predates the snapshot is not a refused product, so it must not
                    # turn `--strict` red or count as a recorded skip.
                    post_note(
                        point.run_id,
                        table,
                        f"no row in the settings table: {snapshot}; run the point again "
                        "to record it",
                    )
                    continue
                setups.append(snapshot)
                keys.append({POLAR_ID_COLUMN: sim_id, "RUN_ID": point.run_id})
    if not setups:
        post_note(
            "campaign",
            table,
            "no point of the matrix has a solver-setup snapshot, so the settings table "
            "and its codebook are not written",
        )
        return
    paths = [
        refuse_an_existing_product(ctx.out / name, archive=ctx.archive, stamp=ctx.archive_stamp)
        for name in (table, legend)
    ]
    # THE REFUSAL TO REPLACE IS THE POST LOG'S (a rebuild is asked for with
    # ``overwrite``); here the previous pair is already archived or is to be replaced.
    written = write_settings_table(
        paths[0], setups, wide=True, legend=paths[1], keys=keys, overwrite=True
    )
    runs = [key["RUN_ID"] for key in keys]
    for path in written:
        ctx.written.append(Path(path))
        ctx.products_index[Path(path).relative_to(ctx.out).as_posix()] = {
            "kind": SETTINGS_KIND,
            "runs": runs,
        }
