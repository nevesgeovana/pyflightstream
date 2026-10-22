"""What a recorded point states: its condition, its state, its clock and its windows.

A private module of :mod:`pyflightstream.post` (AD-13),
below every product family. Each family writes rows that say what
they are rows OF, and every one of them asks the same questions of a
record, a matrix row and an export header; the answers are defined here
once:

* the FLIGHT CONDITION one product row states (:func:`point_condition`),
  reported over requested, with the clock of the rotor that turns
  (:func:`clock_rotor_facts`), and the point's own STATE resolved from its
  row (:func:`point_state`);
* the WINDOWS a point is averaged over: the matrix's as it stands, the
  record's stated one, and the one a record defaulted to;
* the REFERENCE as the workspace holds it today, the rotors each section
  belongs to, the time step an unsteady point ended at, and the refusal
  of a reference the solver did not use;
* the pproc a simulation's products follow and the metadata its first
  record carries.

:mod:`pyflightstream.post.products` re-exports the public names here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import PprocSpec, classify_outputs
from pyflightstream.cases.qsteady import QsteadyRecordError, read_qsteady_record
from pyflightstream.cases.windows import averaging_span
from pyflightstream.cases.workflows import BLADE_FAMILIES_KEY, QSTEADY_ROTOR
from pyflightstream.post._stage import _POST_REFUSES
from pyflightstream.post._tables import ProductError, ReferenceValues, rotor_advance_ratio
from pyflightstream.results import DRAG_PAIRS, LoadsReport, MalformedOutputError, labeled_value
from pyflightstream.script.solver_setup import VORTICITY_COMMAND
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.flight_condition import (
    pinned_state_mismatch,
    resolve_flight_condition,
)
from pyflightstream.workspace.inputs import resolve_reference

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.post.polar import PolarPoint
    from pyflightstream.workspace import CampaignWorkspace, RunRecord
    from pyflightstream.workspace.flight_condition import ResolvedCondition


def _stated_iteration(export_text: str) -> int | None:
    """Return the solver iteration an export states, or None where it states none.

    Both the loads and the surface sections exports carry `Current solver
    iteration number` in their header. A steady export written before the
    solver stamped it carries none, and that is `NA` rather than a guess.
    """
    try:
        return int(float(labeled_value(export_text, "Current solver iteration number:")))
    except (MalformedOutputError, ValueError):
        return None


def _advance_ratio_of(point: PolarPoint) -> float | None:
    """Return the point's advance ratio, or None where the run recorded none.

    None and not zero: zero is a value a rotor row can HAVE, and "not recorded"
    is not it. The funnel writes `NA` for the None, which says the column does
    not apply to this row rather than that the rotor was stopped.
    """
    stated = (point.point or {}).get("advance_ratio")
    return float(stated) if isinstance(stated, int | float) else None


def row_rotor_speeds(record: object | None, loads_path: Path | None) -> dict[str, float]:
    """Return the speed a point's OWN ROW turned its rotor at, where no plan records it.

    A ``qsteady_rotor`` run is steady and plans no reductions, so its record
    states no rotor speed; the builder wrote the row's speed in the
    quasi-steady record beside the point's loads export, and the rotor table
    and the quasi-steady tables read it there (L1). This is that one
    source, ``{alias: rev/min, signed}``, for every other product of the point
    (FR-89, P0370-S11-SUPER-DIAMETER). Empty for any other run type, and for a
    quasi-steady record that cannot be read: its own tables name that refusal.
    """
    if getattr(record, "recipe", None) != QSTEADY_ROTOR or loads_path is None:
        return {}
    try:
        quasi = read_qsteady_record(loads_path)
    except QsteadyRecordError:
        return {}
    return {str(quasi.rotor_alias): float(quasi.rpm)}


def _recorded_speeds(
    reductions: object, own_speeds: Mapping[str, float] | None
) -> dict[str, float]:
    """Return each rotor's speed the record's plan states, or the row's own where it states none.

    THE ROW'S OWN SPEED ONLY WHERE THE PLAN STATES NONE AT ALL, neither a rotor
    block nor the flat field: a plan that states a speed is what the run turned,
    and it is never replaced (FR-89, P0370-S11-SUPER-DIAMETER).
    """
    rotors = reductions.get("rotors") if isinstance(reductions, Mapping) else None
    speeds: dict[str, float] = {}
    if isinstance(rotors, Mapping):
        for turned, block in rotors.items():
            if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float):
                speeds[str(turned)] = float(block["rpm"])
    flat = reductions.get("rpm") if isinstance(reductions, Mapping) else None
    if not speeds and not isinstance(flat, int | float) and own_speeds:
        speeds = {str(alias): float(rpm) for alias, rpm in own_speeds.items()}
    return speeds


def clock_rotor_facts(
    record: RunRecord | None,
    matrix_row: MatrixRow | None,
    artifact: object | None,
    *,
    own_speeds: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Return the CLOCK rotor's alias, speed and diameter, as far as they are known.

    THE CLOCK ROTOR is the one ``CLOCK_MOTION`` names, or the only rotor the row
    turns. A row turning several and naming none has no clock, and the two
    columns then read `NA` rather than taking one rotor's number for another's.

    The speed comes from the RECORD, which is what the run actually turned, and
    the diameter from the reference artifact the row cites. Both are needed for
    the ratio and either may be absent on a record.

    ``own_speeds`` is the row's own speed by alias, :func:`row_rotor_speeds`,
    taken only where the record's plan states no speed at all: a quasi-steady
    point's, which the rotor table and the quasi-steady tables already read
    (FR-89, P0370-S11-SUPER-DIAMETER). Its clock read `NA` until then.

    Parameters
    ----------
    record : RunRecord or None
        The point's run record.
    matrix_row : MatrixRow or None
        The point's matrix row, for ``CLOCK_MOTION``.
    artifact : object or None
        The reference artifact the row cites, for each rotor's diameter.
    own_speeds : mapping of str to float, optional
        The row's own speed by rotor alias, where the record plans none.

    Returns
    -------
    dict
        ``alias``, ``rpm`` and ``diameter_m``, each None where not known.
    """
    reductions = getattr(record, "reductions", None)
    speeds = _recorded_speeds(reductions, own_speeds)
    named = str((getattr(matrix_row, "variables", {}) or {}).get("CLOCK_MOTION", "") or "").strip()
    blocks = getattr(artifact, "rotors", None) or {}
    declared: Mapping[str, object] = blocks if isinstance(blocks, Mapping) else {}

    def _spelt(name: str, among: Mapping[str, object] | Mapping[str, float]) -> str | None:
        """Return the key that spells this name, case-folded as the planner folds it."""
        return next((key for key in among if str(key).casefold() == name.casefold()), None)

    # Resolve the clock identity from its name before consulting speed maps.
    # A record can name its clock while carrying a flat speed and no rotor
    # block; its diameter must belong to that clock rather than another rotor.
    alias: str | None = None
    if named:
        alias = _spelt(named, speeds) or _spelt(named, declared) or named
    elif len(speeds) == 1:
        alias = next(iter(speeds))
    elif not speeds and len(declared) == 1:
        alias = str(next(iter(declared)))

    rpm: float | None = None
    spelt_in_speeds = None if alias is None else _spelt(alias, speeds)
    if spelt_in_speeds is not None:
        rpm = speeds[spelt_in_speeds]
    elif (
        not speeds
        and isinstance(reductions, Mapping)
        and isinstance(reductions.get("rpm"), int | float)
    ):
        # With no rotor blocks, a flat speed describes the single rotor even
        # without an alias. Its unknown span leaves J_CLOCK absent. With rotor
        # blocks present, no flat speed substitutes for an unresolved clock.
        rpm = float(reductions["rpm"])

    # THE SPAN COMES FROM THE BLOCK BEARING THAT IDENTITY, or from nowhere.
    diameter: float | None = None
    spelt_in_reference = None if alias is None else _spelt(alias, declared)
    if spelt_in_reference is not None:
        span = getattr(declared[spelt_in_reference], "diameter_m", None)
        diameter = float(span) if isinstance(span, int | float) else None
    elif rpm is not None and not speeds and not declared:
        # With no rotor blocks in record or reference, the flat speed and
        # top-level rotor_diameter_m supply the ratio. With named blocks, the flat
        # diameter identifies no particular rotor and is not read.
        span = getattr(artifact, "rotor_diameter_m", None)
        diameter = float(span) if isinstance(span, int | float) else None
    return {"alias": alias, "rpm": rpm, "diameter_m": diameter}


def point_condition(
    point: PolarPoint,
    *,
    mach: float,
    cell: Mapping[str, object] | None = None,
    clock: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the flight condition ONE product row states.

    Item 5: every file the post stage writes says what it is a file OF, which
    means the condition has to reach the row rather than only the header. The
    condition values therefore accompany their columns in every product family.

    THE REPORTED CONDITION WINS OVER THE REQUESTED ONE. Two sources exist per
    point and they are not equivalent: ``cell`` is the matrix row, what was
    ASKED for, and ``point.loads`` is the export header, what the solver SAYS it
    ran at. A file that says what it is a file of must carry the second, because
    the two differ exactly when something went wrong -- which is the case a
    reader most needs to see, and the one a product silently stating the request
    would hide.

    The winner is chosen HERE and not by dictionary insertion order: each
    reported value replaces every other spelling of its column before it is
    written, so a swept ``alpha`` cannot outrank the ``ALPHA`` the run reports
    because it happened to be inserted first.

    Parameters
    ----------
    point : PolarPoint
        The point, carrying its loads report and the sweep point it was asked
        for.
    mach : float
        The row's Mach number, which no export header states.
    cell : mapping, optional
        The matrix row's flight condition, for the keys no export reports --
        the altitude among them.
    clock : mapping, optional
        The clock rotor's facts, as :func:`clock_rotor_facts` returns them: its
        ``rpm`` and ``diameter_m``. They add the measured ``RPM_CLOCK`` and
        ``J_CLOCK`` keys; left out, those keys are absent.

    Returns
    -------
    dict
        Keys in the spellings :func:`pyflightstream.post._tables.context_row`
        resolves, which is the column's own name or one of its recorded aliases.
    """
    # THE POINT'S OWN STATE WINS THE SIMULATION'S (CC-01). The caller hands the
    # FIRST record's Mach and cell, which is right for a row that sweeps an angle
    # and publishes one Mach on every row of a Mach sweep.
    own = getattr(point, "state", None)
    if own is not None:
        cell = own.cell or cell
        mach = own.mach if own.mach is not None else mach
    condition: dict[str, object] = {}
    for source in (cell or {}, point.point or {}):
        condition.update(source)

    report = point.loads
    if report is not None:
        reported: tuple[tuple[str, object | None], ...] = (
            ("ALPHA", report.angle_of_attack_deg),
            ("BETA", report.sideslip_deg),
            ("VINF", report.freestream_velocity_m_s),
            # Convert the export's absolute Reynolds number to millions here,
            # matching RE in polar, sections and rotor tables. The unit belongs to
            # the shared column contract.
            ("RE", None if report.reynolds is None else report.reynolds / 1e6),
        )
        for column, value in reported:
            if value is None:
                continue
            for spelling in [key for key in condition if str(key).casefold() == column.casefold()]:
                del condition[spelling]
            condition[column] = value

    condition.setdefault("MACH", mach)
    # The divisors: reference velocity comes from the export that normalised
    # the coefficients; air comes from the point's resolved state. Unstated
    # values remain absent and the funnel writes NA.
    if report is not None and getattr(report, "reference_velocity_m_s", None) is not None:
        condition["VREF"] = report.reference_velocity_m_s
    if own is not None:
        for column, value in (("RHO", own.density_kg_m3), ("TEMP", own.temperature_k)):
            if value is not None:
                condition[column] = value
        if own.viscosity_pa_s is not None:
            # IN SCIENTIFIC NOTATION, AS TEXT. The funnel writes five decimals, and
            # air's viscosity is 1.8e-05: `0.00002` would be a column of one digit.
            condition["MU"] = f"{own.viscosity_pa_s:.5e}"
    # WHAT THE CLOCK ROTOR RAN AT. `J` above is what the row REQUESTED
    # and is `NA` on a row that states RPM; these two are measured from the run:
    # the speed the record kept and the ratio it implies against this point's
    # own free stream and the rotor's diameter. Either stays absent -- and the
    # funnel writes `NA` -- where the record or the reference does not say.
    if clock is not None:
        rpm = clock.get("rpm")
        diameter = clock.get("diameter_m")
        if isinstance(rpm, int | float) and not isinstance(rpm, bool):
            condition["RPM_CLOCK"] = float(rpm)
        ran = rotor_advance_ratio(condition.get("VINF"), rpm, diameter)
        if ran is not None:
            # J = V / (n D), with n in rev/s and the MAGNITUDE of the speed: the
            # hand of the rotation is the rotor's and `RPM_CLOCK` carries it.
            condition["J_CLOCK"] = ran
    return condition


@dataclass(frozen=True)
class PointState:
    """The flow state of one sweep point, as held by post-processing.

    A record can carry simulation-level Mach, velocity and air while its
    point mapping and row cell state a swept flow condition (STATE-SNAPSHOT).
    Resolve that point again through the plan's resolver. Products use the
    resolved state without rewriting the source record.
    """

    mach: float | None
    cell: Mapping[str, object]
    density_kg_m3: float | None
    temperature_k: float | None
    viscosity_pa_s: float | None
    density_source: str | None
    #: What the record said where this differs from it, for the warning.
    differs: tuple[str, ...] = ()


#: The keys of a sweep point that move the FLOW, as a row's cell spells them.
_FLOW_KEYS = ("MACH", "TASmps", "REmi", "ALTFT", "dISA", "RHOkgm3", "MUPas", "ASMPS", "TK", "PPA")


def point_state(record: RunRecord) -> PointState:
    """Return the state of the record's OWN point, re-resolved where it swept the flow."""
    stated = dict(record.flight_condition or {})
    recorded = PointState(
        mach=record.mach,
        cell=stated,
        density_kg_m3=record.density_kg_m3,
        temperature_k=record.temperature_k,
        viscosity_pa_s=record.viscosity_pa_s,
        density_source=record.density_source,
    )
    swept = {key: value for key, value in (record.point or {}).items() if key in _FLOW_KEYS}
    if not swept:
        return recorded
    cell, resolved, error = _resolve_point_cell(record)
    if resolved is None:
        # An unresolvable cell skips the correction, not the product: retain
        # the state recorded for the point, and say so once for the point.
        _warn_once_unresolved(record, error)
        return PointState(**{**recorded.__dict__, "cell": cell})
    differs = tuple(
        f"{label} {was:g} is {now:g}"
        for label, was, now in (
            ("Mach", record.mach, resolved.mach),
            ("density", record.density_kg_m3, resolved.density_kg_m3),
        )
        if isinstance(was, int | float) and abs(float(was) - float(now)) > 1e-9 * max(1.0, abs(now))
    )
    return PointState(
        mach=resolved.mach,
        cell=cell,
        density_kg_m3=resolved.density_kg_m3,
        temperature_k=resolved.temperature_k,
        viscosity_pa_s=resolved.viscosity_pa_s,
        density_source=resolved.density_source,
        differs=differs,
    )


def _free_stream_and_sound(record: RunRecord) -> tuple[float, float] | None:
    """Return a point's free-stream speed and speed of sound, in m/s (M1).

    Resolved from the record's own condition, the swept value in place, by the
    function the plan resolved it with, so the rotor table's Mach numbers are
    taken at the state the point ran at. A record does not carry the speed of
    sound in every record shape, so it is resolved rather than read.
    None where the record states no condition, or one the package cannot
    resolve.
    """
    resolved = _resolved_point(record)
    if resolved is None:
        return None
    return resolved.velocity_m_per_s, resolved.sonic_velocity_m_per_s


def classify_record_outputs(record: RunRecord) -> dict[str, str]:
    """Return the export kinds of a record's outputs, read by the release that wrote them.

    THE ONE CLASSIFICATION OF A RECORD'S OUTPUTS: a name means what the release that wrote it
    meant (one file name can denote different exports in different releases), so every reader
    passes the record's ``package_version`` and none classifies without it.
    """
    return classify_outputs(
        [Path(str(output)).name for output in record.outputs],
        package_version=record.package_version,
    )


def _resolve_point_cell(
    record: RunRecord,
) -> tuple[dict[str, float], ResolvedCondition | None, PyflightstreamError | None]:
    """Resolve the record's own cell (the swept value in place): the ONE resolver of a point.

    :func:`point_state` and :func:`_free_stream_and_sound` both read it, so the state a table
    states and the speeds the rotor table's Mach numbers are taken at cannot drift apart.
    Returns the cell, the resolution, and the refusal when there is one.
    """
    stated = dict(record.flight_condition or {})
    swept = {key: value for key, value in (record.point or {}).items() if key in _FLOW_KEYS}
    cell = {**stated, **swept}
    if not cell:
        return cell, None, None
    try:
        resolved = resolve_flight_condition(
            cell,
            pol=str(record.sim_id),
            reference_length_m=record.reference_length_m,
            defaults=record.flight_condition_defaults or None,
            defaults_origin=record.flight_condition_defaults_from,
        )
    except PyflightstreamError as error:
        return cell, None, error
    return cell, resolved, None


#: The points whose failed re-resolution has been warned of: once per point, not per product.
_UNRESOLVED_WARNED: set[str] = set()


def _warn_once_unresolved(record: RunRecord, error: PyflightstreamError | None) -> None:
    """Warn that a swept cell could not be re-resolved, once per point (PFS-2119.031)."""
    run_id = str(record.run_id)
    if error is None or run_id in _UNRESOLVED_WARNED:
        return
    _UNRESOLVED_WARNED.add(run_id)
    warn(
        f"point={run_id}: its swept flight condition cannot be re-resolved ({error}); the state "
        "recorded for the point is kept, and a swept value that moved the flow is not applied",
        PyflightstreamWarning,
        stacklevel=3,
    )


def _resolved_point(record: RunRecord) -> ResolvedCondition | None:
    """Return the record's own point resolved, the swept value in place, else None.

    None where the record states no condition, or one the package cannot
    resolve: an unresolvable cell costs the check, never the
    product.
    """
    return _resolve_point_cell(record)[1]


def warn_pinned_states(points: Iterable[RunRecord]) -> None:
    """Warn in ``post.log`` for each point whose pinned state disagrees with p = rho R T.

    A point pinning density, temperature and pressure all three is checked by
    :func:`~pyflightstream.workspace.flight_condition.pinned_state_mismatch`,
    the check the plan calls, and each distinct mismatch is warned once
    through the post's warning sink. Nothing is refused or withheld.
    """
    mismatches = (_pinned_mismatch_of(point) for point in points)
    for message in dict.fromkeys(message for message in mismatches if message):
        warn(message, PyflightstreamWarning, stacklevel=2)


def _pinned_mismatch_of(record: RunRecord) -> str | None:
    """Return the pinned-state warning one recorded point earns, else None."""
    resolved = _resolved_point(record)
    return None if resolved is None else pinned_state_mismatch(resolved, pol=str(record.sim_id))


def _mach_of(point: object, fallback: float) -> float:
    """Return the Mach number of THIS point, the simulation's where it states none."""
    own = getattr(point, "state", None)
    mach = getattr(own, "mach", None)
    return float(mach) if isinstance(mach, int | float) else fallback


def _matrix_window(matrix_row: MatrixRow | None, record: object) -> tuple[int, int] | None:
    """Return the matrix's stated window resolved against the recorded clock.

    The matrix wins over the recorded window so LAST_REVS_AVG or
    LAST_ITERS_AVG can change without rerunning the solver (item 16).
    Recorded steps_per_revolution and time_iterations supply the clock and
    last step; this function reads no solver, geometry or script.

    Precedence is the stated matrix window, then the record's window flagged
    as stated (_stated_window), then the recorded default (_defaulted_window),
    which the caller labels with a warning.

    Return None for a malformed record. An invalid stated matrix window
    raises CampaignConfigError, recorded by admission as this run's refusal.
    """
    if matrix_row is None:
        return None
    variables = getattr(matrix_row, "variables", None)
    if not isinstance(variables, Mapping):
        return None
    plan = getattr(record, "reductions", None)
    if not isinstance(plan, Mapping):
        return None
    last_step = plan.get("time_iterations")
    if isinstance(last_step, bool) or not isinstance(last_step, int | float) or last_step <= 0:
        return None
    per_revolution = plan.get("steps_per_revolution")
    # Share cases.windows arithmetic with planning and recorded reductions
    # so matrix-window resolution and exported time averages agree (PO-01).
    return averaging_span(
        variables,
        last_step=int(last_step),
        per_revolution=(
            float(per_revolution)
            if isinstance(per_revolution, int | float) and not isinstance(per_revolution, bool)
            else None
        ),
    )


#: How far an export's printed reference may sit from the stated one and still be
#: the same number: the recorded loads exports under tests/ print three decimals, so
#: half of the last one and nothing else (no committed report states the print width;
#: it is read from those recorded files). The definition warns "by more than the
#: export's printed precision", and a part relative to the area widened that precision
#: tenfold for a large one.
_REFERENCE_PRINT_TOLERANCE = 5.0e-4


#: A comparison band wider than this fraction of the stated value is too coarse to tell a wrong
#: reference from the right one.
_REFERENCE_UNCHECKABLE_FRACTION = 0.005

#: Floating-point slack only: a stated 1.0005 beside a printed 1.001 is half a unit
#: of the last printed digit, whatever the arithmetic of the subtraction says.
_REFERENCE_ARITHMETIC_SLACK = 1.0e-9


def _refuse_a_reference_the_solver_did_not_use(
    sim_id: str, points: Sequence[PolarPoint], reference: ReferenceValues
) -> None:
    """Refuse a simulation whose export was normalised by another area or length (CC-05).

    THE PACKAGE EMITS NO REFERENCE-SETTING COMMAND, so the solver divides every
    coefficient by the area and the length its own project file carries, and the
    loads export prints both. Every product states `SREF` and `CREF` from the
    reference ARTIFACT. Where the two differ the table is wrong by a constant
    factor that nothing in it reveals. The campaign post warns by
    default; its explicit refusal mode retains the reference refusal.

    An export that prints neither line is not refused; there is nothing to compare.
    Where the band of the comparison is wider than half a percent of the stated value (a
    small model, whose printed digits are few), the agreement is noted as only that
    precise, once per simulation.
    """
    said: set[tuple[str, str]] = set()
    for point in points:
        loads = point.loads
        if loads is None:
            continue
        for label, column, printed, stated in (
            ("area", "SREF", getattr(loads, "reference_area", None), reference.sref_m2),
            ("length", "CREF", getattr(loads, "reference_length", None), reference.cref_m),
        ):
            if not isinstance(printed, int | float):
                continue
            allowed = _REFERENCE_PRINT_TOLERANCE + _REFERENCE_ARITHMETIC_SLACK
            if abs(float(printed) - stated) > allowed:
                reason = (
                    f"simulation {sim_id!r}: the loads export of {point.name} states a reference "
                    f"{label} of {float(printed):g}, which is what the solver divided its "
                    f"coefficients by, and the reference the products would state is {column} "
                    f"{stated:g}. A table stating {column} {stated:g} beside coefficients "
                    f"divided by {float(printed):g} is wrong by a constant factor nothing in it "
                    "shows. The solver takes its "
                    "reference from the project file it opened: state the same area and chord on "
                    "the reference artifact the row names, or set them in that project, and post "
                    "again."
                )
                if _POST_REFUSES.get():
                    raise ProductError(reason)
                warn(
                    f"point={point.name} product=simulation/{sim_id}: {reason}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
            elif (
                allowed > _REFERENCE_UNCHECKABLE_FRACTION * abs(stated)
                and (label, column) not in said
            ):
                # THE BAND IS WIDER THAN THE DIFFERENCE IT HAS TO CATCH: on a small model the
                # printed digits cannot tell a wrong reference from the right one, and the
                # agreement above proves less than it seems. Said once per simulation.
                said.add((label, column))
                band = f"+-{100.0 * allowed / abs(stated):.3g}%" if stated else "no relative band"
                warn(
                    f"point={point.name} product=simulation/{sim_id}: the reference {label} "
                    f"({column} {stated:g}) could only be checked to {band}, because the export "
                    f"prints {float(printed):g} to a fixed number of digits; a different "
                    "reference of this size would pass the check. Compare the reference artifact "
                    "with the project file the solver opened.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )


def _last_time_step(record: RunRecord) -> int | None:
    """Return the time step an UNSTEADY point's end-of-run exports belong to, else None.

    The sections export of an unsteady run is written once, when the march ends,
    so it is a photograph of the run's last time step: where a watchdog stopped
    the run, the step it stopped at; otherwise the steps the plan marched. None on
    a steady record, whose export states its own iteration and is read from there.
    """
    plan = record.reductions if isinstance(record.reductions, Mapping) else {}
    export = record.export_window if isinstance(record.export_window, Mapping) else {}
    if not plan and not export and record.recipe not in ("unsteady", "unsteady_rotor"):
        return None
    stopped = record.stopped_at if isinstance(record.stopped_at, Mapping) else {}
    for stated in (stopped.get("step"), plan.get("time_iterations"), export.get("time_iterations")):
        if isinstance(stated, int | float) and not isinstance(stated, bool) and stated > 0:
            return int(stated)
    return None


def _section_rotors(
    live: object | None, aliases: Mapping[str, Sequence[str]] | None, record: RunRecord
) -> dict[str, dict[str, object]]:
    """Return what the sections table needs of each rotor: its families and its clock.

    The families come from the reference the row names today, expanded through
    the aliases, because a section block states geometry families. The speed,
    the steps per revolution and blade one's datum come from the point's own
    record, which is the only place a run states them.
    """
    blocks = getattr(live, "rotors", None) or {}
    reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
    stated = reductions.get("rotors")
    table: dict[str, dict[str, object]] = {}
    if not blocks:
        # NO REFERENCE TO ASK, which is a workspace posted without its matrix. The
        # record's per-rotor blade families supply the answer.
        recorded = stated if isinstance(stated, Mapping) and stated else {"": reductions}
        for alias, own in recorded.items():
            named = own.get(BLADE_FAMILIES_KEY) if isinstance(own, Mapping) else None
            if not isinstance(named, Sequence) or isinstance(named, str):
                continue
            stated_blades: list[str] = []
            per_blade: list[list[str]] = []
            for name in named:
                members = [str(m) for m in (aliases or {}).get(str(name), (name,))]
                stated_blades.extend(members)
                per_blade.append(members)
            table[str(alias)] = {
                "families": stated_blades,
                "blade_families": per_blade,
                **{
                    key: own.get(key)
                    for key in ("steps_per_revolution", "blade1_azimuth_deg", "rpm")
                },
            }
        return table
    for alias, block in blocks.items():
        families: list[str] = []
        per_blade_families: list[list[str]] = []
        for name in getattr(block, "families_blades", ()) or ():
            members = [str(m) for m in (aliases or {}).get(str(name), (name,))]
            families.extend(members)
            per_blade_families.append(members)
        own = stated.get(str(alias)) if isinstance(stated, Mapping) else None
        if not isinstance(own, Mapping) and len(blocks) == 1:
            # THE ROW-LEVEL PATH: one rotor, whose clock is the plan's own.
            own = reductions
        entry: dict[str, object] = {"families": families, "blade_families": per_blade_families}
        if isinstance(own, Mapping):
            for key in ("steps_per_revolution", "blade1_azimuth_deg", "rpm"):
                entry[key] = own.get(key)
        table[str(alias)] = entry
    return table


def _live_reference(workspace: CampaignWorkspace, matrix_row: MatrixRow | None) -> object | None:
    """Return the reference artifact the matrix row names TODAY, or None.

    None where the stage has no matrix row or the workspace can no longer resolve
    the artifact: a caller then falls back to what the run recorded, and a missing
    reference never costs a product that does not need it.
    """
    if matrix_row is None:
        return None
    try:
        return resolve_reference(workspace.inputs_dir, matrix_row.ref_code)
    except PyflightstreamError:
        return None


def _defaulted_window(record: object) -> tuple[int, int] | None:
    """Return the window a record DEFAULTED to, where its row stated none.

    `reduction_windows` always fills the time average of an unsteady point: from
    the row's key, from a retired `WINDOW_*` key, or, failing both, from the last
    revolution (a rotor row) or the whole run. `window_stated` says which. This
    answers only for a record of an unsteady run type whose row stated nothing;
    a steady record has no reductions and gets None.
    """
    if getattr(record, "recipe", None) not in ("unsteady", "unsteady_rotor"):
        return None
    plan = getattr(record, "reductions", None)
    if not isinstance(plan, Mapping) or plan.get("window_stated"):
        return None
    return _recorded_window(plan)


def _recorded_window(plan: object) -> tuple[int, int] | None:
    """Return the time-average window a reductions plan states, or None."""
    if not isinstance(plan, Mapping):
        return None
    entry = plan.get("time_average")
    stated = entry.get("windows") if isinstance(entry, Mapping) else None
    if not isinstance(stated, Sequence) or not stated:
        return None
    first = stated[0]
    if not isinstance(first, Sequence) or len(first) != 2:
        return None
    try:
        window = int(first[0]), int(first[1])
    except (TypeError, ValueError):
        return None
    # ORDER-CHECKED LIKE `_stated_window`: a window that runs backwards is no window.
    return window if window[1] >= window[0] else None


def _stated_window(record: object) -> tuple[int, int] | None:
    """Return the window the ROW STATED, off the run record, or None.

    THE NAME IS THE CONTRACT AND IT WAS FALSE. This read the record's
    `time_average` window and returned it whatever produced it -- and
    `reduction_windows` fills that slot from FOUR sources: the row's averaging
    key, a retired `WINDOW_*` key, the last revolution, and finally the whole
    run. So "the row stated a window" was really "this point is unsteady at
    all", and a row that stated nothing had its POLAR averaged from step one,
    transient included. That is the design error this package refuses by name
    elsewhere, shipped under the name of the check that refuses it. The
    architect lens of the release round found it.
    The plan now records `window_stated`, and only a window the row actually
    asked for reaches the unsteady polar.


    Item 16's window as the PRODUCTS stage meets it. The plan writes it once,
    under `time_average`, from `last_revs_avg` or `last_iters_avg`; every
    unsteady product of the point reads it from there rather than deriving one,
    which is what makes "one window" true of the files rather than of a docstring.

    None for a record with no reductions at all -- a steady point -- and for one
    whose time average was SKIPPED, because a row whose clock could not be
    resolved has no window to average the polar over either.
    """
    plan = getattr(record, "reductions", None)
    if not isinstance(plan, Mapping):
        return None
    # Re-source only a window explicitly flagged as stated. Without that
    # flag, averaging from step one could publish the transient as the answer.
    if not plan.get("window_stated"):
        return None
    entry = plan.get("time_average")
    if not isinstance(entry, Mapping):
        return None
    windows = entry.get("windows")
    if not isinstance(windows, Sequence) or not windows:
        return None
    first = windows[0]
    if not isinstance(first, Sequence) or len(first) != 2:
        return None
    # EVERY MALFORMED SHAPE YIELDS None, WHICH IS WHAT THE DOCSTRING PROMISED.
    # The `int()` conversions sat outside every guard, so a record carrying a
    # string window aborted the WHOLE products stage for that simulation with a
    # bare ValueError naming neither the simulation nor the key. A window that
    # runs backwards was passed straight through and made every point of the
    # polar drop silently. The QA lens of the release round measured both.
    try:
        window = (int(first[0]), int(first[1]))
    except (TypeError, ValueError):
        return None
    if window[1] < window[0]:
        return None
    return window


def _resolve_post_pproc(
    workspace: CampaignWorkspace, pproc_id: str | None
) -> tuple[str | None, PprocSpec | None, str | None]:
    """Keep a specification failure separate from independently recorded exports."""
    try:
        return pproc_id, workspace.resolve_pproc(pproc_id) if pproc_id else None, None
    except (PyflightstreamError, OSError, ValueError) as error:
        return pproc_id, None, f"pproc {pproc_id!r} cannot be resolved: {error}"


def _simulation_metadata(records: Sequence[RunRecord]) -> RunRecord:
    """Take each shared field from a carrier, preferring successful records."""
    preferred = sorted(
        records,
        key=lambda record: (
            record.status
            not in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER, RunStatus.MAX_ITER_REACHED)
        ),
    )
    fields = ("pproc", "reference", "description", "mach", "flight_condition", "aliases")
    values = {}
    for field in fields:
        for record in preferred:
            value = getattr(record, field)
            if value is not None and value != "" and value != {}:
                values[field] = value
                break
    return preferred[0].model_copy(update=values)


def _effective_pproc(
    workspace: CampaignWorkspace,
    sim_id: str,
    first: RunRecord,
    matrix_row: MatrixRow | None,
) -> tuple[str | None, PprocSpec | None, str | None]:
    """Resolve the matrix's post choices once for the simulation and its series."""
    pproc_id = first.pproc
    stated = getattr(matrix_row, "pproc_code", None)
    if stated and str(stated) not in ("-", "NA") and str(stated) != str(pproc_id):
        warn(
            f"simulation {sim_id}: the row names pproc {stated} and the run recorded "
            f"{pproc_id}. The products follow {stated}; its [exports] half still describes "
            "what the run wrote, so an export the run did not make is not there to read.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        pproc_id = str(stated)
    return _resolve_post_pproc(workspace, pproc_id)


def _vorticity_selection(record: RunRecord) -> object:
    """Return the induced-drag boundary selection a run recorded, or None where it recorded none."""
    flags = (record.solver_setup or {}).get("flags")
    flag = flags.get(VORTICITY_COMMAND) if isinstance(flags, Mapping) else None
    return flag.get("value") if isinstance(flag, Mapping) else None


def _in_coefficients(report: LoadsReport) -> bool:
    """Whether a loads table prints coefficients, the unit every product here reads.

    G09. The table's own footer says so. Every product reads its
    columns by coefficient name, and what header the solver prints under
    ``SET_LOADS_AND_MOMENTS_UNITS NEWTONS`` has not been measured, so a table
    whose footer names another unit is not summed as though it held
    coefficients.
    """
    return all(
        units.strip().lower() == "coefficients"
        for units in (report.force_units, report.moment_units)
    )


def _on_the_vorticity_list(names: Sequence[str], selection: object) -> set[str]:
    """Return the surfaces ``selection`` puts on the vorticity induced-drag list."""
    if isinstance(selection, str):
        return set(names) if selection == "all" else set()
    if isinstance(selection, Sequence) and selection:
        placed = [
            names[item - 1]
            for item in selection
            if isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= len(names)
        ]
        return set(placed) if len(placed) == len(selection) else set(names)
    return set()


def declined_profile_drag_125(loads: LoadsReport, selection: object) -> tuple[str, ...]:
    """Return the listed surfaces a 26.125 table prints with ``CDp`` exactly zero.

    PFS-2085.021, P0400-DECLINED125. On 26.125 a surface the solver declined to
    compute (on the vorticity induced-drag list, without a trailing edge) prints
    ``CDp`` 0, as earlier builds print ``CDi`` 0 (RPT-166, probes D-01 and D-01c:
    the same sphere prints CDp 0 on the list and -0.0005 off it). The rule of
    :func:`declined_induced_drag` reads ``CDi`` and so judges nothing on a table
    printing the 26.125 split (``CDp``, ``CDv``); this one reads ``CDp`` there.
    On 26.124 the same surface prints ``CDi`` 0 both on and off the list, so that
    build cannot discriminate and this rule does not apply to it.

    Parameters
    ----------
    loads : LoadsReport
        The parsed loads table.
    selection : object
        The recorded value of ``SET_VORTICITY_DRAG_BOUNDARIES``.

    Returns
    -------
    tuple of str
        The listed surfaces whose printed ``CDp`` is exactly ``0.0``, in table
        order; empty on a table printing ``CDi``.
    """
    if DRAG_PAIRS[0][0] in loads.total:
        return ()
    names = list(loads.surfaces)
    listed = _on_the_vorticity_list(names, selection)
    return tuple(
        name for name in names if name in listed and loads.surfaces[name].get("CDp") == 0.0
    )
