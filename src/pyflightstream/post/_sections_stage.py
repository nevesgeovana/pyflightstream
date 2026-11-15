"""The stage of the sections and Cp tables of a point: granularity, family files, Cp (FR-3786).

Beside the point's sections table (written by the sections step of
:mod:`pyflightstream.post._sim`) this writes what ``[sections] split`` asks for
and the point's Cp table, ``sections/<point>_cp.csv``, from its
``EXPORT_ALL_SURFACE_SECTIONS`` export. Private; the step calls
:func:`finish_sections` once per point.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import classify_outputs
from pyflightstream.post._block_rows import rotor_ids_of
from pyflightstream.post._section_tables import sections_split, write_cp_table
from pyflightstream.post._stage import SECTIONS_DIR
from pyflightstream.post._tables import ProductError

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext
    from pyflightstream.post.polar import PolarPoint

__all__ = ["finish_sections", "split_of"]


def split_of(ctx: SimContext) -> str:
    """Return the pproc's ``[sections] split``, ``point`` where it states none.

    Raises
    ------
    ProductError
        If the pproc states a value that is not ``point``, ``family`` or ``both``.
    """
    return sections_split(getattr(ctx.pproc.sections, "split", None))


def _entry(ctx: SimContext, point: PolarPoint, *, family: bool = False) -> dict[str, object]:
    entry: dict[str, object] = {"runs": ctx.sources[point.name], "kind": "instant"}
    if family:
        entry["split"] = "family"
    return entry


def finish_sections(
    ctx: SimContext, point: PolarPoint, done: Path, family_files: list[Path], split: str
) -> None:
    """Index the family files, drop the point table when only families are asked, write Cp.

    Parameters
    ----------
    ctx : SimContext
        The simulation being posted.
    point : PolarPoint
        The point.
    done : Path
        The point's sections table, already written and carried on.
    family_files : list of Path
        The per-family sections tables the writer made.
    split : {'point', 'family', 'both'}
        ``[sections] split``.
    """
    for path in family_files:
        ctx.add(path, _entry(ctx, point, family=True))
    if split == "family":
        # The point table was written for the products cut from it; only the
        # family files were asked for.
        key = done.relative_to(ctx.out).as_posix()
        ctx.written[:] = [path for path in ctx.written if path != done]
        ctx.written_names.pop(key, None)
        done.unlink(missing_ok=True)
    _cp_products(ctx, point, split)


def _cp_products(ctx: SimContext, point: PolarPoint, split: str) -> None:
    from pyflightstream.post._condition import _last_time_step, _section_rotors

    record = ctx.record_of[point.name]
    exports = classify_outputs(record.outputs, package_version=record.package_version)
    if "sections" not in exports:
        return
    source = ctx.workspace.sim_dir(record.sim_id) / exports["sections"]
    if not source.is_file():
        return
    relative = f"{SECTIONS_DIR}/{point.name}_cp.csv"
    target = ctx.target(ctx.out / relative)
    family_files: list[Path] = []
    try:
        done = write_cp_table(
            target,
            source.read_text(encoding="utf-8", errors="replace"),
            layout=record.sections_layout,
            rotors=_section_rotors(ctx.live, ctx.aliases, record),
            inventory=record.inventory,
            rotor_ids=rotor_ids_of(ctx),
            step=_last_time_step(record),
            condition=ctx.condition(point),
            reference=ctx.reference,
            pol=ctx.sim_id,
            split=split,
            family_files=family_files,
        )
    except (ProductError, PyflightstreamError, OSError) as error:
        ctx.skipped[relative] = str(error)
        return
    if done is None:
        ctx.skipped[relative] = "the Cp export holds no cut point, so no Cp table is written"
        return
    if split in ("point", "both"):
        ctx.add(done, _entry(ctx, point))
    for path in family_files:
        ctx.add(path, _entry(ctx, point, family=True))
