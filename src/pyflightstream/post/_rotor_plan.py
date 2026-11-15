"""Where a rotor's loads come from: its plot source and its recorded speed.

A private module of :mod:`pyflightstream.post` (AD-13). The polar step
(:mod:`pyflightstream.post._polar_stage`) reads a rotor's speed through
:func:`_recorded_rotor_rpm` and, where its families' plots are not all in the
record, its history through :func:`rotor_plot_source`, which names the plot
group (the one the solver adds itself, or one the pproc declares over exactly
the rotor's families in the moment-reference frame; a group in the rotor's
own frame is never a source); the unsteady polar's axes ask the same question
of a frame through :func:`_plot_name_can_emit` and :func:`_emitted_by_another`,
and :func:`_warn_rotor_advance_ratio` says when the swept rotor did not run at
the row's advance ratio. The 0.57.0 rotor-table planner is removed with the
rotor table (PFS-2231); the helpers its rows were made of remain.
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import (
    AXES_PLOT_COMPONENTS,
    ROTOR_PLOT_GROUP_PREFIX,
    select_families,
)
from pyflightstream.cases.workflows import FLAT_RPM_KEY, ORIGINAL_FRAME_SUFFIX
from pyflightstream.post.polar import PolarPoint

if TYPE_CHECKING:
    from pyflightstream.workspace import RunRecord


# The window is the last revolutions or iterations the row states.
# cases.windows.averaging_span supplies the shared derivation used by
# _matrix_window and the plan.


def _plot_name_can_emit(
    template: str,
    name: str,
    families: str | Sequence[str],
    *,
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    aliases: Mapping[str, Sequence[str]] | None = None,
    frame: str = "",
) -> bool:
    """Whether a declared plot name CAN occupy an automatic group's name.

    The label a ``{family}`` group puts
    in its name is chosen by the script builder from the run's case and frames
    (`cases.workflows.pproc_emissions`), which the post stage does not hold.
    Any template that COULD produce the automatic name
    counts as producing it: a history that might be the wrong one is never read,
    and its table is skipped with the reason. New runs record the emitted names,
    frames and families; rotor tables read that record directly. This matcher
    remains the conservative fallback for older records.
    """
    del families, inventory, is_blade, aliases, frame
    # The builder appends the original frame's suffix to a group plotted in a
    # retained ORIGINAL frame, so a declaration emits its name AND that name
    # suffixed; both can occupy an automatic name.
    # EVERY replacement field is a wildcard, whatever its format spec: the builder
    # applies `str.format`, so `{family}`, `{family:.0}` (empty) or `{family!r}`
    # can each put any text, or none, where they stand.
    # Parsed with Python's own format parser, which handles nested specs; each
    # top-level field becomes a wildcard. The pproc refuses anything but a bare
    # `{family}` when it is read, so this is the second line of defence.
    pattern = "".join(
        re.escape(literal) + (".*" if field is not None else "")
        for literal, field, _spec, _conversion in string.Formatter().parse(template)
    )
    suffix = re.escape(ORIGINAL_FRAME_SUFFIX)
    # Case-insensitive: whether the solver keeps a plot name's case is not measured,
    # so two names equal but for case are taken as able to collide.
    return re.fullmatch(f"{pattern}(?:{suffix})?", name, flags=re.IGNORECASE) is not None


def _emitted_by_another(
    name: str, groups: Sequence[object], own: object, *, outside_frame: str | None = None
) -> bool:
    """Whether a group OTHER than ``own`` could emit plot group ``name``.

    A history column states a group's name and nothing else, so a name two
    declarations could produce is ambiguous: its history may be the other one's.
    An ambiguous name is never read as a source. With ``outside_frame``, only a
    group in ANOTHER frame counts: for the global axes, a second group in the same
    global frame still yields a global history.
    """
    return any(
        group is not own
        and (
            outside_frame is None
            or str(getattr(group, "frame", "")).strip().upper() != outside_frame
        )
        and _plot_name_can_emit(
            str(getattr(group, "name", "")),
            name,
            (),
            inventory=(),
            is_blade=lambda _family: False,
        )
        for group in groups
    )


def rotor_plot_source(
    pproc: object | None,
    alias: str,
    *,
    rotor_families: Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[str], str | None]:
    """Return the plot groups a rotor's six components may be read from, and why not.

    A force plot is named ``<parameter>_<group name>``, the group being an entry of
    the pproc's ``[[plots.groups]]``. So a rotor's history is found THROUGH THE
    PPROC, never by guessing a name:

    1. a group in the global ``MRP`` frame whose families are exactly the rotor's
       own, as the artifact declares it (``HUB_PUSHER`` is as good a name as any);
    2. the automatic group ``ROTOR_<ALIAS>``, also in ``MRP``.

    A GROUP THAT MERELY SHARES THE ALIAS'S NAME IS NOT ONE: an artifact may call a
    group ``PROP`` over the blades alone while the rotor ``PROP`` owns a spinner
    too, and the table would then average another set of surfaces than the one it
    integrates on a steady run.

    A GROUP IN A ROTOR'S OWN FRAME IS NEVER A SOURCE. Its force is stated in axes
    that turn with the rotor and its moment is already about the hub (the package
    takes a group in a frame to state its loads in that frame; no committed report
    measures the rotor-frame group of an export), while the rotor table turns a
    geometry-frame force and transfers the moment from the moment point. An
    expanding frame names its emissions by ``{family}``, which is
    the one way a bare ``FX_<alias>`` arises, so that spelling is refused when the
    artifact declares it there.

    Returns the candidate group names, best first, and what was ruled out and
    why. Without a pproc, a caller holding a plots table and nothing else, the
    alias itself is the only candidate.
    """
    if pproc is None:
        return [alias], None
    wanted = {str(family) for family in rotor_families}
    candidates: list[str] = []
    refused: str | None = None
    generated = f"{ROTOR_PLOT_GROUP_PREFIX}{alias}"
    generated_is_declared = False
    #: The group that takes the generated name, and the frame it takes it in.
    taken_by: tuple[str, str] | None = None
    plots = getattr(pproc, "plots", None)
    components_declared = set(getattr(plots, "parameters", ()) or ()) & set(AXES_PLOT_COMPONENTS)
    is_blade = getattr(pproc, "is_blade", lambda _name: False)
    for group in getattr(getattr(pproc, "plots", None), "groups", ()) or ():
        frame = str(getattr(group, "frame", "")).strip().upper()
        name = str(getattr(group, "name", ""))
        named = group.families if isinstance(group.families, list) else [group.families]
        # Expanding rotor frames label their emissions with the cited rotor.
        took = _plot_name_can_emit(
            name,
            generated,
            group.families if frame in {"SMRP", "RMRP"} else (),
            inventory=inventory,
            is_blade=is_blade,
            aliases=aliases,
            frame=frame,
        )
        generated_is_declared |= took
        if took and taken_by is None:
            taken_by = (name, frame)
        try:
            resolved = select_families(
                group.families, list(inventory), is_blade, aliases, strict=False
            )
        except PyflightstreamError:
            continue
        if frame not in {"SMRP", "RMRP"}:
            took = _plot_name_can_emit(
                name,
                generated,
                [family for selected in resolved for family in selected],
                inventory=inventory,
                is_blade=is_blade,
            )
            generated_is_declared |= took
            if took and taken_by is None:
                taken_by = (name, frame)
        if frame != "MRP":
            if "{family}" in name and alias in {str(member) for member in named}:
                refused = (
                    f"the pproc plots {name.replace('{family}', alias)!r} in the frame {frame}, "
                    "which is the rotor's own: a force there is not in the geometry's axes and "
                    "its moment is already about the hub, so it is not what a rotor table is "
                    "built from. Declare a plot group over the rotor's families with "
                    'frame = "MRP"'
                )
            continue
        if "{family}" in name:
            continue
        if any(wanted and set(families) == wanted for families in resolved):
            if _emitted_by_another(name, getattr(plots, "groups", ()) or (), group):
                continue
            candidates.append(name)
    # A declared name keeps its declared frame and families. The run skips
    # already emitted names when adding its automatic plots.
    if not (generated_is_declared and components_declared):
        candidates.append(generated)
    elif not candidates and refused is None and taken_by is not None:
        # When a user plot occupies the automatic global-MRP name and no other
        # source is eligible, name that collision in the refusal so the user can
        # identify the pproc entry to change.
        declared, declared_frame = taken_by
        # Distinguish a rotor-frame collision from a global plot over the wrong
        # families. Rotor frames may use the artifact radicals SMRP/RMRP or the
        # emitted alias-qualified names; both identify the frame mismatch.
        radical = declared_frame.rsplit("_", 1)[-1].rstrip("0123456789")
        why = (
            f"in the frame {declared_frame}, which is the rotor's own"
            if radical in {"SMRP", "RMRP"}
            else f"in the frame {declared_frame}, over families that are not exactly the rotor's"
        )
        refused = (
            f"the pproc's plot group {declared!r} already emits {generated!r} {why}, so the run "
            f"did not add its automatic {generated!r} in the global MRP frame over exactly the "
            f"rotor's families, and this run has no such history of rotor {alias!r} at all. No "
            f"post-processing can recover it. Rename that group to a name that is not "
            f"{generated!r} (for example 'SHAFT_{{family}}'), or declare a plot group over "
            f'exactly the rotor\'s families with frame = "MRP"; either way the rotor table '
            "returns on the next run"
        )
    return candidates, refused


def _recorded_rotor_rpm(record: RunRecord, alias: str, rotor_count: int) -> float | None:
    """Read the rotor speed, using flat keys only for a single-rotor plan."""
    reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
    stated = reductions.get("rotors")
    rpm: float | None = None
    if isinstance(stated, Mapping):
        # The clock lookup of the window folds case; the speed lookup does the same.
        block = next(
            (
                value
                for key, value in stated.items()
                if str(key).casefold() == str(alias).casefold()
            ),
            None,
        )
        if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float):
            rpm = float(block["rpm"])
    flat = reductions.get(FLAT_RPM_KEY)
    if (
        rpm is None
        and not (isinstance(stated, Mapping) and stated)
        and rotor_count == 1
        and isinstance(flat, int | float)
        and not isinstance(flat, bool)
    ):
        # A ROW THAT STATES ITS ROTOR WITH FLAT KEYS plans no per-rotor
        # block and records its speed at the top of the plan. With ONE
        # rotor in the reference that speed can only be this rotor's;
        # with several nothing says whose it is, and the skip stays.
        rpm = float(flat)
    return rpm


def _warn_rotor_advance_ratio(
    point: PolarPoint,
    alias: str,
    *,
    diameter_m: float,
    rpm: float | None,
    rotor_id: int,
    rotor_count: int,
    matrix_row: object | None,
) -> None:
    # BOTH ADVANCE RATIOS ARE IN THE ROW, and the stage says when they part
    # (NL-09). `J` is what the row REQUESTED; `J<id>` is what this rotor RAN
    # at, from its own speed and diameter, and it is the one every coefficient
    # of its RCOEF files uses. On the rotor the row sweeps the two should
    # agree; on a second rotor of the row they are not expected to, so nothing
    # is said about it.
    """Warn when the swept rotor's actual advance ratio differs from the row."""
    requested = (point.point or {}).get("advance_ratio")
    flight = point.loads.freestream_velocity_m_s if point.loads is not None else None
    span = float(diameter_m or 0.0)
    clock = str(getattr(matrix_row, "variables", {}).get("CLOCK_MOTION", "") or "")
    if (
        isinstance(requested, int | float)
        and isinstance(flight, int | float)
        and span > 0.0
        and rpm
        # CASE-FOLDED, as clock_rotor_facts resolves the same name.
        and (rotor_count == 1 or clock.casefold() == str(alias).casefold())
    ):
        ran = float(flight) / (abs(rpm) / 60.0 * span)
        if abs(ran - float(requested)) > 5e-4 * max(1.0, abs(float(requested))):
            warn(
                f"{point.name}: the row asks for J = {float(requested):g} and rotor "
                f"{alias} ran at J{rotor_id} = {ran:.5g} ({float(flight):g} m/s, "
                f"{abs(rpm):g} rev/min, D {span:g} m). The coefficients of its RCOEF "
                f"files use J{rotor_id}.",
                PyflightstreamWarning,
                stacklevel=4,
            )
