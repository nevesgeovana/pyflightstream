"""The warnings ``plan_matrix`` prints once per matrix, before any point runs.

Pipeline role: a private module of :mod:`pyflightstream.run`, below
:mod:`pyflightstream.run.matrix`, which calls each of them from ``plan_matrix``
alone so that ``run`` does not repeat what ``plan`` said. Each names the rows
or points a plan can already see to be a problem (a legacy row that saves no
simulation, points that may not fit the disk, a helical Mach number of 1 or
more, a quasi-steady point outside its assumption, an additional post that
extracts one instant) and none refuses a run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.cases import CampaignConfigError, classify_outputs, point_name
from pyflightstream.cases.matrix import LEGACY_WORKFLOW
from pyflightstream.cases.workflows import (
    ADDITIONAL_PPROC_VARIABLE,
    SONIC_HELICAL_MACH,
    WORKFLOW_KEY,
)
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.matrix import ResolvedMatrix

if TYPE_CHECKING:  # annotation only: the package root does not import this module
    from pyflightstream.run import CampaignPlan


def _warn_the_legacy_rows_saving_no_simulation(resolved: ResolvedMatrix) -> None:
    """Name each LEGACY row whose outputs declare no saved simulation (G11, 0.27.0).

    A row naming a run type saves its final ``.fsm`` on every point, which the
    pproc artifact cannot switch off. A LEGACY row's recipe decides what it
    writes, and only a ``.fsm`` name among its OUTPUTS is collected and hashed,
    so a row declaring none leaves no final state in its record. A warning,
    never a refusal: such a row runs as it always did. Called from
    :func:`plan_matrix` alone, so ``run`` does not repeat what ``plan`` said.
    """
    unsaved = [
        sim.sim_id
        for sim in resolved.campaign.sims
        if sim.variables.get(WORKFLOW_KEY) == LEGACY_WORKFLOW
        and "simulation" not in classify_outputs(sim.outputs)
    ]
    if unsaved:
        warn(
            f"POL {', '.join(unsaved)}: {LEGACY_WORKFLOW} row(s) that declare no saved "
            "simulation. No name among their OUTPUTS ends in .fsm, so no final .fsm of "
            "theirs is collected into datapoints/DP-<point>/ or hashed in their run "
            "record, and nothing can reopen it from the record. A row naming a run type "
            f"saves one on every point; a {LEGACY_WORKFLOW} recipe saves one only when it "
            "writes SAVEAS to a name its OUTPUTS declare, so declare that name and save "
            "to it, or leave the row as it is if its final state is not wanted.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_when_the_points_may_not_fit(workspace: CampaignWorkspace, ready: int) -> None:
    """Warn at plan when the READY points may not fit on the workspace's disk (0.30.0, S6).

    The estimate is the mean recorded datapoint of this workspace times the
    points the run will write; the warning names ``free-space``, the command
    that makes room. A plan with nothing to run, or a disk that cannot be
    measured, says nothing.
    """
    if ready <= 0:
        return
    from pyflightstream.workspace.storage import disk_estimate

    try:
        line, fits = disk_estimate(workspace, ready)
    except OSError:
        return
    if not fits:
        warn(
            f"disk: {line}. The run may not fit: make room first, for example with "
            "`pyfs-matrix free-space m<id>` (a recipe in inputs/management/) after "
            "`pyfs-matrix space-in-use` shows where the space is.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_when_a_helical_mach_may_reach_one(resolved: ResolvedMatrix, plan: CampaignPlan) -> None:
    """Name each polar point whose rotor or disc has a helical Mach of 1 or more (0.30.0, M1).

    ``M_hel = sqrt(V^2 + (Omega R)^2) / a``, the geometric speed the blade tip
    meets the flow at (free stream plus rotation, no induced velocity), over the
    speed of sound; at 1 or more the tip is sonic or
    supersonic. A warning, never a refusal: the plan says it once per matrix,
    naming every such point by its name, its rotor and its ``M_hel``. A row
    whose rotor's numbers are not known (no radius, no resolved speed) is
    named too, with the reason, because the plan cannot say for it. Called
    from :func:`plan_matrix` alone.
    """
    cases = {case.sim_id: case for case in resolved.campaign.sims}
    sonic: list[str] = []
    unknown: dict[str, None] = {}
    for entry in plan.points:
        for alias, mach in entry.rotor_mach.items():
            helical = mach.get("mach_helical")
            if not isinstance(helical, int | float):
                unknown[str(mach.get("note"))] = None
                continue
            # FR-176 R1: the warning reads the advancing tip, which is M_hel in
            # axial flow and the larger edgewise; a record without it reads M_hel.
            advancing = mach.get("mach_advancing")
            tip_mach = advancing if isinstance(advancing, int | float) else helical
            if tip_mach < SONIC_HELICAL_MACH:
                continue
            case = cases.get(entry.sim_id)
            try:
                name = point_name(case, entry.point) if case is not None else entry.run_id
            except CampaignConfigError:
                name = entry.run_id
            kind = mach.get("kind") or "rotor"
            sonic.append(
                f"POL {entry.sim_id} point {name}, {kind} {alias}, M_adv {tip_mach:.3f} "
                f"(M_hel {helical:.3f})"
            )
    if sonic:
        warn(
            f"advancing-tip Mach M_adv >= 1 on {len(sonic)} polar point(s): "
            f"{'; '.join(sonic)}. "
            "M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a is the speed the advancing "
            "blade tip meets the flow at (free stream plus rotation, no induced velocity) "
            "over the speed of sound, so at 1 or more the tip is sonic or supersonic; it "
            "equals M_hel in axial flow and is larger in inclined flow. Nothing is "
            "refused; check these points before running them.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if unknown:
        warn(
            f"helical Mach not known, so the plan cannot say whether it reaches 1: "
            f"{'; '.join(unknown)}.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _sort_the_validity(
    where: str,
    entry: Any,
    validity: Mapping[str, Any],
    sorted_into: tuple[list[str], list[str], list[str]],
) -> None:
    """File one point's validity under above-the-limit, not-known and too-few-clockings."""
    from pyflightstream.cases.qsteady import summarise, summarise_inflow_harmonics

    above, unknown, too_few = sorted_into
    harmonics = validity.get("inflow_fft")
    if isinstance(harmonics, Mapping):
        suggested = harmonics.get("suggested_passage_positions")
        stated = harmonics.get("passage_positions")
        if isinstance(suggested, int) and isinstance(stated, int) and stated < suggested:
            too_few.append(
                f"{where}: PASSAGE_POSITIONS {stated}, the inflow "
                f"needs {suggested} (n_max {harmonics.get('n_max')} on "
                f"{harmonics.get('blades')} blades)"
            )
        effective_share = harmonics.get("span_pct_k_eff_gt_0_1")
        if isinstance(effective_share, int | float):
            # THE VALIDITY WARNING READS k_eff WHEN IT IS KNOWN.
            if effective_share > 0.0:
                above.append(f"{where}: {summarise_inflow_harmonics(harmonics)}")
            return
    if validity.get("note"):
        unknown.append(f"{where}: {validity['note']}")
        return
    share = validity.get("span_pct_k_gt_0_1")
    if isinstance(share, int | float) and share > 0.0:
        above.append(f"{where}: {summarise(validity)}")


def _warn_when_a_quasi_steady_point_leaves_its_assumption(
    resolved: ResolvedMatrix, plan: CampaignPlan
) -> None:
    """Name each quasi-steady wheel point whose blade has k above 0.1 anywhere (0.30.0).

    ``k = Omega c / (2 V_rel)`` is the 1P reduced frequency of a blade station
    (:mod:`pyflightstream.cases.qsteady`); above 0.1 the lag of the unsteady
    wake is no longer small against the once-per-revolution load, so the
    quasi-steady load there is an estimate. A warning, never a refusal, naming
    each point with the four values the plan shows for it. A wheel point whose
    chord is not known at plan time is named in a second warning, with why.
    Called from :func:`plan_matrix` alone.

    WITH ``--inflow-fft`` (0.30.0) a point carrying the harmonic content of its
    custom inflow is judged by ``k_eff = n95 k_1P`` instead of ``k``, where
    that is known, and a point whose row states fewer ``PASSAGE_POSITIONS``
    than ``n_max / N + 1`` is named in a warning of its own. nP is counted on
    ONE BLADE, not the blade-passing N P of a fixed surface, nor the rotor
    total, in which only multiples of N P survive.
    """
    from pyflightstream.cases.qsteady import REDUCED_FREQUENCY_LIMIT

    cases = {case.sim_id: case for case in resolved.campaign.sims}
    above: list[str] = []
    unknown: list[str] = []
    too_few: list[str] = []
    for entry in plan.points:
        validity = entry.qsteady_validity
        if not validity:
            continue
        case = cases.get(entry.sim_id)
        try:
            name = point_name(case, entry.point) if case is not None else entry.run_id
        except CampaignConfigError:
            name = entry.run_id
        _sort_the_validity(
            f"POL {entry.sim_id} point {name}", entry, validity, (above, unknown, too_few)
        )
    if above:
        warn(
            f"quasi-steady rotor: the 1P reduced frequency k = Omega c / (2 V_rel) exceeds "
            f"{REDUCED_FREQUENCY_LIMIT:g} on part of the blade at {len(above)} point(s): "
            f"{'; '.join(above)}. There the unsteady wake lags the once-per-revolution load "
            "and the quasi-steady load is an estimate. Nothing is refused; every product of "
            "these points carries the values.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if unknown:
        warn(
            f"quasi-steady rotor: the 1P reduced frequency is not known at plan time for "
            f"{'; '.join(unknown)}.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if too_few:
        warn(
            f"quasi-steady rotor: {len(too_few)} wheel point(s) state fewer clockings than "
            f"their custom inflow's harmonics need: {'; '.join(too_few)}. n_max is the highest "
            "harmonic one blade meets per revolution holding 95 % of its angle-of-attack "
            "perturbation (nP counted on the blade, not the N P a fixed surface or a balance "
            "under the whole rotor sees; only multiples of N P reach the rotor's total), and "
            "PASSAGE_POSITIONS >= n_max / N + 1 samples them in one blade passage. Nothing is "
            "refused.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_the_rows_whose_additional_post_is_one_instant(resolved: ResolvedMatrix) -> None:
    """Name each unsteady row stating ADDITIONAL_PPROC, whose extraction is one instant (G12).

    The additional post reopens a point's final saved simulation, which holds
    the LAST instant of an unsteady run (RPT-062), so what it extracts there is
    one instant and not the run's per-step history. A warning, never a
    refusal: the plan says it once per matrix, naming the rows, and the post
    says it again per point. Called from :func:`plan_matrix` alone.
    """
    instants = [
        sim.sim_id
        for sim in resolved.campaign.sims
        if sim.variables.get(ADDITIONAL_PPROC_VARIABLE)
        and str(sim.variables.get(WORKFLOW_KEY, "")).startswith("unsteady")
    ]
    if instants:
        warn(
            f"POL {', '.join(instants)}: unsteady row(s) stating "
            f"{ADDITIONAL_PPROC_VARIABLE}. The additional post reopens each point's final "
            "saved simulation, which is the LAST instant of its run (RPT-062): what it "
            "extracts there is that one instant and not the run's per-step history. The "
            "plots history it exports is the run's own.",
            PyflightstreamWarning,
            stacklevel=3,
        )
