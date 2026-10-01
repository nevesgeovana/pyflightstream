"""What a recorded point states: its condition, its state, its clock and its windows.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0), below every product family. Each family writes rows that say what
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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import PprocSpec
from pyflightstream.cases.windows import averaging_span
from pyflightstream.cases.workflows import BLADE_FAMILIES_KEY
from pyflightstream.post._stage import _POST_REFUSES
from pyflightstream.post._tables import ProductError, ReferenceValues, rotor_advance_ratio
from pyflightstream.results import LoadsReport, MalformedOutputError, labeled_value
from pyflightstream.script.solver_setup import VORTICITY_COMMAND
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.flight_condition import resolve_flight_condition
from pyflightstream.workspace.inputs import resolve_reference

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.post.polar import PolarPoint
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


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


def clock_rotor_facts(
    record: RunRecord | None,
    matrix_row: MatrixRow | None,
    artifact: object | None,
) -> dict[str, object]:
    """Return the CLOCK rotor's alias, speed and diameter, as far as they are known.

    THE CLOCK ROTOR is the one ``CLOCK_MOTION`` names, or the only rotor the row
    turns. A row turning several and naming none has no clock, and the two
    columns then read `NA` rather than taking one rotor's number for another's.

    The speed comes from the RECORD, which is what the run actually turned, and
    the diameter from the reference artifact the row cites. Both are needed for
    the ratio and either may be absent on a record written before 0.24.0.
    """
    reductions = getattr(record, "reductions", None)
    rotors = reductions.get("rotors") if isinstance(reductions, Mapping) else None
    speeds: dict[str, float] = {}
    if isinstance(rotors, Mapping):
        for turned, block in rotors.items():
            if isinstance(block, Mapping) and isinstance(block.get("rpm"), int | float):
                speeds[str(turned)] = float(block["rpm"])
    named = str((getattr(matrix_row, "variables", {}) or {}).get("CLOCK_MOTION", "") or "").strip()
    blocks = getattr(artifact, "rotors", None) or {}
    declared: Mapping[str, object] = blocks if isinstance(blocks, Mapping) else {}

    def _spelt(name: str, among: Mapping[str, object] | Mapping[str, float]) -> str | None:
        """Return the key that spells this name, case-folded as the planner folds it."""
        return next((key for key in among if str(key).casefold() == name.casefold()), None)

    # THE IDENTITY FIRST, AND FROM THE NAME. Inferring it from the speed map
    # alone left a row that NAMES its clock unresolved whenever the record kept
    # a flat speed and no rotor block, and the diameter then fell back to the
    # only rotor the reference declared -- another rotor's span under this
    # rotor's ratio (the QA lens, 2026-09-22).
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
        # WITHOUT AN ALIAS TOO. A record with no rotor block turns ONE rotor and
        # the flat field is its speed, whether or not the row names it or the
        # reference declares it: requiring the alias here dropped a speed the
        # record states plainly (the QA lens, 2026-09-22). What stays unknown is
        # the SPAN, so J_CLOCK is still absent.
        # A row that records one speed and NO ROTOR BLOCK AT ALL turns one
        # rotor, and the flat field is its speed. With rotor blocks present and
        # no clock resolved, this published one rotor's speed for a row whose
        # clock nobody could name, and `reduction_windows` records both fields
        # (the architect and V&V lenses, 2026-09-22).
        rpm = float(reductions["rpm"])

    # THE SPAN COMES FROM THE BLOCK BEARING THAT IDENTITY, or from nowhere.
    diameter: float | None = None
    spelt_in_reference = None if alias is None else _spelt(alias, declared)
    if spelt_in_reference is not None:
        span = getattr(declared[spelt_in_reference], "diameter_m", None)
        diameter = float(span) if isinstance(span, int | float) else None
    elif rpm is not None and not speeds and not declared:
        # THE FLAT SINGLE-ROTOR SHAPE: no rotor block in the record and none in
        # the reference, one flat speed and one top-level `rotor_diameter_m`.
        # Both facts are stated and no other rotor exists to borrow from, so
        # `NA` here would refuse a ratio the files supply (the fifth independent
        # reading of GitHub main, 2026-09-23). With named blocks present the
        # flat diameter answers for nobody and is not read.
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
    columns existed from the first commit of this release and the values did
    not; a release round measured `VINF` and `ALT` reading `NA` in every row of
    every polar and super file.

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
            # IN MILLIONS, which is what the `RE` column already means in the
            # two families that carried it before this release: the polar's
            # twenty-four say so at `COEFFICIENT_COLUMNS`, and the sections
            # table writes `_reynolds_millions`. The export states the absolute
            # number, so it is converted HERE.
            #
            # It went in absolute for one commit, which put 4380000 in a rotor
            # table and 4.38 in the polar BESIDE IT, under one column name --
            # six orders of magnitude between two files a reader joins on their
            # condition columns. Aligning the polar instead would change bytes
            # already published for a second time in one release.
            ("RE", None if report.reynolds is None else report.reynolds / 1e6),
        )
        for column, value in reported:
            if value is None:
                continue
            for spelling in [key for key in condition if str(key).casefold() == column.casefold()]:
                del condition[spelling]
            condition[column] = value

    condition.setdefault("MACH", mach)
    # 0.24.0: THE DIVISORS. The reference velocity is the EXPORT's, because that
    # is what its coefficients were normalised by; the air is the POINT's, from
    # its own resolved state. A value the run never stated stays absent and the
    # funnel writes `NA`.
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
    # WHAT THE CLOCK ROTOR RAN AT (0.25.1). `J` above is what the row REQUESTED
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
    """The flow state ONE point of a sweep resolved to, as the post stage holds it.

    A record written before 0.24.0 states the SIMULATION's Mach, velocity and
    air on every point of a row that swept a flow variable: the run layer wrote
    them from the simulation-level case (STATE-SNAPSHOT). What such a record still
    states truthfully is its ``point`` mapping and the row's cell as written, and
    that is enough to resolve the point again with the same function the plan
    used. The record is never rewritten; the products simply stop repeating it.
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
    cell = {**stated, **swept}
    try:
        resolved = resolve_flight_condition(
            cell,
            pol=str(record.sim_id),
            reference_length_m=record.reference_length_m,
            defaults=record.flight_condition_defaults or None,
            defaults_origin=record.flight_condition_defaults_from,
        )
    except PyflightstreamError:
        # A cell this release cannot resolve costs the correction and never the
        # product: the point keeps what its record states, as it always did.
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
    """Return a point's free-stream speed and speed of sound, in m/s (0.30.0, M1).

    Resolved from the record's own condition, the swept value in place, by the
    function the plan resolved it with, so the rotor table's Mach numbers are
    taken at the state the point ran at. A record does not carry the speed of
    sound itself before 0.30.0, which is why it is resolved rather than read.
    None where the record states no condition, or one this release cannot
    resolve.
    """
    stated = dict(record.flight_condition or {})
    swept = {key: value for key, value in (record.point or {}).items() if key in _FLOW_KEYS}
    cell = {**stated, **swept}
    if not cell:
        return None
    try:
        resolved = resolve_flight_condition(
            cell,
            pol=str(record.sim_id),
            reference_length_m=record.reference_length_m,
            defaults=record.flight_condition_defaults or None,
            defaults_origin=record.flight_condition_defaults_from,
        )
    except PyflightstreamError:
        return None
    return resolved.velocity_m_per_s, resolved.sonic_velocity_m_per_s


def _mach_of(point: object, fallback: float) -> float:
    """Return the Mach number of THIS point, the simulation's where it states none."""
    own = getattr(point, "state", None)
    mach = getattr(own, "mach", None)
    return float(mach) if isinstance(mach, int | float) else fallback


def _matrix_window(matrix_row: MatrixRow | None, record: object) -> tuple[int, int] | None:
    """Return the window the MATRIX states NOW, resolved against the recorded clock.

    ITEM 16 IS POST-ONLY AND IT WAS NOT. `_stated_window` below reads the window
    off the RUN RECORD, which `reduction_windows` wrote when the point EXECUTED.
    So editing `LAST_REVS_AVG` in the matrix and re-running only the post stage
    changed nothing, and a record written before 0.23.0 carries no
    `window_stated` flag at all, so its polar fell back to the native
    last-time-step export. Both silently.

    THE ACCEPTANCE RULE FOR THIS WHOLE RELEASE: finished simulations already
    exist and only the post-processing is redone, on Windows and on HPC alike;
    an item that requires a re-run is not ready. A window a user cannot change
    without re-running the solver fails it. The direction is therefore to
    recompute it here, and the MATRIX WINS THE RECORD.

    IT COSTS NO RE-RUN BECAUSE THE CLOCK IS ALREADY IN THE RECORD. The plan
    writes `steps_per_revolution` and `time_iterations` next to the window it
    derived, so a count of revolutions has a length in solver steps and the run
    has a last step -- which is everything the derivation needs. Nothing here
    reads the solver, the geometry or the script.

    PRECEDENCE, stated because a silent precedence is the defect one level up:

    1. The matrix row's `LAST_REVS_AVG` or `LAST_ITERS_AVG`, resolved here.
    2. Failing that, the window the record states AND FLAGS as stated, which is
       `_stated_window` -- a point whose matrix no longer names a key still
       reduces the way it was run.
    3. Failing both, None: the caller then averages over the window the record
       defaulted to (:func:`_defaulted_window`) and says so in a warning.

    Returns None rather than raising for every shape it cannot resolve: a
    malformed record costs this product and never the stage.
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
    # THE ARITHMETIC IS `cases.windows` AND NOTHING ELSE (0.24.0). It stood here
    # as a second copy of what the plan derives, and a third copy fed the
    # reductions from the frozen record, which is how one edit to the matrix
    # moved the polar and left `<point>_time_average.csv` behind (PO-01).
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
#: the same number: the export prints three decimals, so half of the last one, plus
#: a relative part for a large area.
_REFERENCE_PRINT_TOLERANCE = 5.0e-4


_REFERENCE_RELATIVE_TOLERANCE = 1.0e-6


def _refuse_a_reference_the_solver_did_not_use(
    sim_id: str, points: Sequence[PolarPoint], reference: ReferenceValues
) -> None:
    """Refuse a simulation whose export was normalised by another area or length (CC-05).

    THE PACKAGE EMITS NO REFERENCE-SETTING COMMAND, so the solver divides every
    coefficient by the area and the length its own project file carries, and the
    loads export prints both. Every product states `SREF` and `CREF` from the
    reference ARTIFACT. Where the two differ the table is wrong by a constant
    factor that nothing in it reveals. Since 0.26.0 the campaign post warns by
    default; its explicit refusal mode retains the reference refusal.

    An export that prints neither line is not refused; there is nothing to compare.
    """
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
            allowed = _REFERENCE_PRINT_TOLERANCE + _REFERENCE_RELATIVE_TOLERANCE * abs(stated)
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
        # record states each rotor's blade families since 0.24.0, so it answers.
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
        return int(first[0]), int(first[1])
    except (TypeError, ValueError):
        return None


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
    # ONLY A WINDOW THE ROW ASKED FOR. A record written before 0.23.0 carries no
    # such flag and is therefore not re-sourced, which is exactly right: it never
    # stated an averaging window, and averaging its polar from step one would
    # publish the transient as though it were the answer.
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
        key=lambda record: record.status not in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER),
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

    G09 (0.27.0). The table's own footer says so. Every product reads its
    columns by coefficient name, and what header the solver prints under
    ``SET_LOADS_AND_MOMENTS_UNITS NEWTONS`` has not been measured, so a table
    whose footer names another unit is not summed as though it held
    coefficients.
    """
    return all(
        units.strip().lower() == "coefficients"
        for units in (report.force_units, report.moment_units)
    )
