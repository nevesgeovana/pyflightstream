"""The run block row of each point of a simulation, from what the post resolved (FR-3778).

:func:`point_block_rows` reads the simulation context the stage built and
returns one row of :func:`pyflightstream.post._run_block.run_block_row` per
point, which :func:`pyflightstream.post._block_scope.run_blocks` then lays at the
head of every table written for the point. Nothing is invented: a value the
record does not state is ``NA``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING

from pyflightstream._errors import ProductError, PyflightstreamError
from pyflightstream._tokens import CONTEXT_COLUMNS
from pyflightstream.post._block_scope import run_blocks
from pyflightstream.post._run_block import RUN_TYPES, RotorRunValues, run_block_row
from pyflightstream.post._tables import context_row
from pyflightstream.post.axes import rotor_frame

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext
    from pyflightstream.post.polar import PolarPoint

__all__ = ["point_block_rows", "rotor_ids_of", "run_block_scope"]

_MOMENT_POINT = ("XMOM", "YMOM", "ZMOM")


def rotor_ids_of(ctx: SimContext) -> dict[str, int]:
    """Return the declared id of each rotor alias of the simulation's reference.

    Examples
    --------
    >>> rotor_ids_of.__name__
    'rotor_ids_of'
    """
    rotors = getattr(ctx.live, "rotors", None) or {}
    return {str(alias): int(getattr(block, "id", 0) or 0) for alias, block in rotors.items()}


def _run_type(record: object) -> str:
    recipe = str(getattr(record, "recipe", "") or "")
    return recipe if recipe in RUN_TYPES else "steady"


def _speeds(ctx: SimContext, point: PolarPoint) -> dict[str, float | None]:
    from pyflightstream.post._condition import row_rotor_speeds
    from pyflightstream.post._rotor_plan import _recorded_rotor_rpm

    record = ctx.record_of.get(point.name)
    rotors = getattr(ctx.live, "rotors", None) or {}
    own = row_rotor_speeds(record, point.loads_path)
    speeds: dict[str, float | None] = {}
    for alias in rotors:
        rpm = None
        if record is not None:
            rpm = _recorded_rotor_rpm(record, str(alias), len(rotors))
        if rpm is None:
            rpm = next(
                (v for k, v in own.items() if str(k).casefold() == str(alias).casefold()), None
            )
        speeds[str(alias)] = rpm
    return speeds


def _machs(
    record: object, block: object, rpm: float | None, point: PolarPoint, shaft: tuple[float, ...]
) -> tuple[float | None, float | None]:
    from pyflightstream.post._condition import _free_stream_and_sound
    from pyflightstream.post.rotor_table import _mach_cells

    if record is None or rpm is None:
        return None, None
    try:
        air = _free_stream_and_sound(record)  # type: ignore[arg-type]
    except (PyflightstreamError, ValueError):
        return None, None
    (mtip, mhel), _madv = _mach_cells(
        air,
        float(rpm),
        float(getattr(block, "diameter_m", 0.0) or 0.0),
        (point.alpha_deg, point.beta_deg),
        shaft,  # type: ignore[arg-type]
    )
    return (
        mtip if isinstance(mtip, float) else None,
        mhel if isinstance(mhel, float) else None,
    )


def _window(ctx: SimContext, point: PolarPoint) -> dict[str, object]:
    span = ctx.point_windows.get(point.name)
    if span is None:
        return {}
    steps = span[1] - span[0] + 1
    out: dict[str, object] = {"FIRST_STEP": span[0], "LAST_STEP": span[1], "STEPS": steps}
    reductions = getattr(ctx.record_of.get(point.name), "reductions", None)
    per_rev = reductions.get("steps_per_revolution") if isinstance(reductions, Mapping) else None
    if isinstance(per_rev, int | float) and not isinstance(per_rev, bool) and per_rev > 0:
        revs = steps / float(per_rev)
        out["WINDOW_REVS"] = revs
        out["WINDOW_PASSAGES"] = _passages(ctx, revs)
    return out


def _passages(ctx: SimContext, revs: float) -> float | None:
    rotors = getattr(ctx.live, "rotors", None) or {}
    clock = str((getattr(ctx.matrix_row, "variables", {}) or {}).get("CLOCK_MOTION", "") or "")
    block = next((b for a, b in rotors.items() if str(a).casefold() == clock.casefold()), None)
    if block is None and len(rotors) == 1:
        block = next(iter(rotors.values()))
    blades = getattr(block, "blade_count", None) if block is not None else None
    return revs * blades if isinstance(blades, int) and blades > 0 else None


def point_block_rows(ctx: SimContext) -> dict[str, dict[str, object]]:
    """Return the run block row of every point of the simulation, by point name.

    Parameters
    ----------
    ctx : SimContext
        What the first part of the simulation's post resolved.

    Returns
    -------
    dict of str to dict
        The point name to its row, in the order of the run block. ``POINT_ID``
        is the point's 1-based position in the simulation's sweep order.

    Examples
    --------
    >>> point_block_rows.__name__
    'point_block_rows'
    """
    rotors = getattr(ctx.live, "rotors", None) or {}
    identifiers = dict(getattr(ctx.matrix_row, "identifiers", {}) or {})
    variables = getattr(ctx.matrix_row, "variables", {}) or {}
    lengths = ctx.reference.as_lengths()
    moment = ctx.reference.as_moment_point()
    rows: dict[str, dict[str, object]] = {}
    for index, point in enumerate(ctx.points):
        record = ctx.record_of.get(point.name)
        stated = dict(zip(CONTEXT_COLUMNS, context_row(ctx.condition(point), lengths), strict=True))
        stated.update(
            zip(_MOMENT_POINT, context_row(moment, None, columns=_MOMENT_POINT), strict=True)
        )
        stated = {key: value for key, value in stated.items() if value is not None}
        stated.update(_window(ctx, point))
        if variables.get("ACTUATOR_THRUST") is not None:
            stated["THRUST"] = variables.get("ACTUATOR_THRUST")
        speeds = _speeds(ctx, point)
        values = []
        for alias, block in rotors.items():
            rotor_id = int(getattr(block, "id", 0) or 0)
            frame = rotor_frame(getattr(block, "axis_vector", (0.0, 0.0, 1.0)), rotor_id)
            rpm = speeds.get(str(alias))
            shaft = tuple(float(v) for v in frame.body_to_rotor[0])
            mtip, mhel = _machs(record, block, rpm, point, shaft)
            values.append(
                RotorRunValues(
                    rotor_id=rotor_id,
                    diameter_m=float(getattr(block, "diameter_m", 0.0) or 0.0),
                    pitch_deg=frame.pitch_deg,
                    toe_deg=frame.toe_deg,
                    rpm=rpm,
                    mtip=mtip,
                    mhel=mhel,
                )
            )
        rows[point.name] = run_block_row(
            pol=str(ctx.sim_id),
            point_id=index + 1,
            point=point.name,
            run_type=_run_type(record),
            condition=stated,
            identifiers=identifiers,
            rotors=sorted(values, key=lambda value: value.rotor_id),
        )
    return rows


@contextmanager
def run_block_scope(ctx: SimContext) -> Iterator[None]:
    """Open the tables the simulation's steps write with their point's run block.

    A refusal to build the rows (an identifier that spells a block column, say)
    is named under ``skipped`` and the tables are written without a block, so
    the one defect costs the block and not the post.

    Parameters
    ----------
    ctx : SimContext
        What the first part of the simulation's post resolved.

    Yields
    ------
    None
        The block.
    """
    try:
        rows = point_block_rows(ctx)
    except ProductError as error:
        ctx.skipped[f"run_block/{ctx.sim_id}"] = str(error)
        rows = {}
    with run_blocks(rows, rotor_ids_of(ctx)):
        yield
