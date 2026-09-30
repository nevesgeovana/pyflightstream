"""The analysis settings of a setup: selections, moments model, the rotor link, the actions.

Pipeline role: emission, called by the run-type builders of
:mod:`pyflightstream.cases.workflows`: the boundary selections of the solver
settings and of the loads analysis (:func:`family_indices` and its three
callers, :func:`loads_selections`), the analysis frame and moments model before
the solve (:func:`analysis_frame_and_moments`), and the end of the solver
settings (:func:`emit_setup_extras`).

FR-317, THE MOMENTS MODEL IS A SETUP KEY. Until 0.33.0 every builder wrote
``SET_ANALYSIS_MOMENTS_MODEL PRESSURE`` beside the loads frame, a choosable
value with no key. The key ``moments_model`` now states it; unstated, the line
is the one it always was (PRESSURE, the command database's recorded default
and the package's previous output), so every script of a setup naming none
keeps its bytes.

FR-318, ON A ROTOR THE TWO VORTICITY SETTINGS ARE LINKED. This is a product
requirement set from a prior measurement made outside this package, not an
analysis of the solver made here: on a propeller run with the induced drag
by vorticity (``vorticity_drag_families``) and the moments by pressure, the
thrust came from the vorticity integration and the torque from the pressure
integration. So on a row turning a rotor an unstated moments model follows the
drag list to VORTICITY, warned at plan and recorded in the setup snapshot, and
a moments model stated PRESSURE beside the list is refused at plan.

THE LIMITATION FR-318 STATES, NOT HIDES. The moments model is an init-phase
command (commands/solver_analysis.yaml) and precedes ``START_SOLVER``, so every
step export of a march carries it (RPT-064). The vorticity drag list is an
analysis-phase command in every edition the database records, so it follows
``START_SOLVER``, and on an unsteady row it reaches the final loads export and
not the step exports. Moving it before the solve is neither documented nor
measured; the licensed confirmation is registered in RPT-104 and the order is
kept until it runs.

FR-319, THE PER-STEP ACTIONS. A marching row's ``unsteady_solver_actions`` are
registered at the end of its solver settings; a steady row stating them is
refused, naming the key, because it has no time step.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.cases._setup_keys import DEFAULT_MOMENTS_MODEL
from pyflightstream.script import Script, helpers

__all__ = [
    "LINKED_MOMENTS_MODEL",
    "LOADS_SELECTION_KEYS",
    "analysis_frame_and_moments",
    "analysis_indices",
    "axial_separation_indices",
    "emit_setup_extras",
    "family_indices",
    "loads_selections",
    "moments_model_of",
    "package_actions",
    "vorticity_indices",
]


def family_indices(
    case: SimCase,
    script: Script,
    families: Sequence[str] | None,
    *,
    keyword: str,
    preset_key: str,
    dropped: str,
) -> list[int] | None:
    """Resolve one preset boundary list's FAMILIES through the opened inventory.

    PFS-2030.03.03. A family the geometry does not carry is left out, as the
    reference driver filtered the preset's list to the configuration it opened;
    a list that resolves to nothing is refused, because an empty selection would
    be read by the solver as the default and the preset asked for something else.

    ONE RULE FOR EVERY PER-FAMILY LIST, not one copy per list. This was written
    for `vorticity_drag_families` alone and generalised when
    `axial_separation_families` was added under the same rule as the vorticity
    list. Two copies of this resolution would drift on the day one of them
    learned something about a mesh the other did not, and every one of them
    answers the same question: which boundaries of the opened geometry does this
    family list name?

    ``keyword`` is the helper argument this feeds, used as the resolution
    context so a bad label names the key the user wrote. ``dropped`` completes
    the sentence "or drop the key so ..." in the refusal, because what the
    solver does with an ABSENT list is different for each one and is the fact a
    reader needs in order to choose.
    """
    if families is None:
        return None
    # AN EMPTY LIST IS ITS OWN REFUSAL, and it fell through to the absent-family
    # branch for one commit: the message read "the preset names <key>  and the
    # opened geometry carries none of them (absent: )" -- two spaces, an empty
    # parenthesis, and a sentence claiming the geometry lacks families that were
    # never named. `vorticity_drag_families` is caught earlier and properly by an
    # `EntitySelection` row at input validation; its new twin was given the
    # resolver and not the validation, and the field's own docstring said it
    # followed "the same rule ... through the same function", which is true of
    # the resolver and not of the check. The QA lens of the closing round
    # measured the mangled sentence.
    if not list(families):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the preset states {preset_key} = [], an EMPTY "
            "selection. The solver reads an empty list as its own default, which is "
            f"not what a preset naming the key asked for: either name families, or "
            f"drop {preset_key} so {dropped}."
        )
    chosen: list[int] = []
    absent: list[str] = []
    for name in families:
        try:
            chosen.append(script.resolve_boundary(name, context=keyword))
        except PyflightstreamError:
            absent.append(name)
    if not chosen:
        raise CampaignConfigError(
            # THE PRESET'S OWN SPELLING, not the helper keyword. This named
            # `keyword` -- which is the `solver_settings()` Python argument and
            # is what `resolve_boundary` should be told -- so the refusal sent a
            # user to `axial_separation_boundaries`, a key they cannot write in a
            # preset at all. For `vorticity` an alias softened it; for the new
            # twin there was nothing. The resolver's own docstring promised the
            # opposite: "so a bad label names the key the user wrote".
            f"case {case.sim_id!r}: the preset names {preset_key} "
            f"{', '.join(families)} and the opened geometry carries none of them "
            f"(absent: {', '.join(absent)}), so the selection would be empty. Name "
            f"families the geometry carries, or drop {preset_key} so {dropped}."
        )
    return sorted(chosen)


def vorticity_indices(case: SimCase, script: Script) -> list[int] | None:
    """Resolve the induced-drag boundary list from the preset's families."""
    return family_indices(
        case,
        script,
        case.solver.vorticity_drag_families,
        keyword="vorticity_drag_boundaries",
        preset_key="vorticity_drag_families",
        dropped="the solver integrates surface pressure on every boundary",
    )


def axial_separation_indices(case: SimCase, script: Script) -> list[int] | None:
    """Resolve the axial flow separation list from the preset's families.

    `axial_separation_families` is a setup key and follows the same rule as
    `vorticity_drag_families`. It had been reachable only as a helper keyword
    that no campaign path passed -- the API-only shape this release exists to
    catch, one level below the products.

    THE BUILD GUARD STILL DECIDES WHETHER IT MAY RUN, and this does not argue
    with it. `SET_AXIAL_SEPARATION_BOUNDARIES` is documented to 26.100 and no
    further; RPT-018 measured it reported deprecated and then REFUSED by the
    26.101 and 26.121 solvers. So a row naming this key on a later build is
    refused by the mechanism that already refuses any command a build does not
    offer, naming the build -- which is the honest outcome and much better than
    emitting a line the solver will reject mid-run.
    """
    return family_indices(
        case,
        script,
        case.solver.axial_separation_families,
        keyword="axial_separation_boundaries",
        preset_key="axial_separation_families",
        dropped="no boundary is placed on the axial flow separation list",
    )


def analysis_indices(case: SimCase, script: Script) -> list[int] | None:
    """Resolve the families that enter the loads (G09), by the per-family rule."""
    return family_indices(
        case,
        script,
        case.solver.analysis_families,
        keyword="boundaries",
        preset_key="analysis_families",
        dropped="every boundary enters the loads",
    )


#: The setup keys that select what the loads analysis reads (G09 of 0.27.0), each
#: an analysis-phase command emitted after START_SOLVER, which is why a row of an
#: unsteady run type may not state them.
LOADS_SELECTION_KEYS: tuple[str, ...] = ("analysis_families", "load_units", "inviscid_loads")


def loads_selections(case: SimCase, script: Script) -> None:
    """Emit the setup's selections of the loads analysis, after the solve (G09).

    ANALYSIS PHASE, SO AFTER ``START_SOLVER`` and before the exports, which is
    the order the verified inviscid-loads probe ran: the command, then the
    export that reads it. Called once per point, so every point of a warm sweep
    restates them. A setup that states none emits nothing.
    """
    solver = case.solver
    boundaries = analysis_indices(case, script)
    if boundaries is None and solver.load_units is None and solver.inviscid_loads is None:
        return
    helpers.analysis_setup(
        script,
        load_units=solver.load_units,
        boundaries=boundaries,
        inviscid_only=solver.inviscid_loads,
    )


#: The moments model a rotor row's vorticity drag list implies (FR-318).
LINKED_MOMENTS_MODEL = "VORTICITY"

#: The setup keys only a marching row may state (FR-319).
MARCHING_KEYS = ("unsteady_solver_actions",)


def moments_model_of(case: SimCase, *, rotor: bool) -> tuple[str | None, bool]:
    """Return the moments model a row states or implies, and whether it was implied.

    ``(None, False)`` where the row states none and implies none, which the
    caller writes as the default. On a row turning a rotor whose setup states
    ``vorticity_drag_families``, an unstated model is implied VORTICITY and
    warned, and a model stated PRESSURE is refused naming both keys (FR-318).
    """
    solver = case.solver
    stated = solver.moments_model
    if not rotor or solver.vorticity_drag_families is None:
        return stated, False
    families = ", ".join(solver.vorticity_drag_families)
    if stated is None:
        warnings.warn(
            f"case {case.sim_id!r} turns a rotor and its setup states "
            f"vorticity_drag_families ({families}) and no moments_model, so its moments "
            f"model is {LINKED_MOMENTS_MODEL} too: on a rotor the two are linked, so the "
            "thrust and the torque come from one integration (FR-318). The run record "
            "names the rule; state moments_model = VORTICITY to write it in the setup.",
            PyflightstreamWarning,
            stacklevel=3,
        )
        return LINKED_MOMENTS_MODEL, True
    if stated != LINKED_MOMENTS_MODEL:
        raise CampaignConfigError(
            f"case {case.sim_id!r} turns a rotor and its setup states "
            f"vorticity_drag_families ({families}) with moments_model = {stated}: the "
            "thrust would come from the vorticity integration and the torque from the "
            f"{stated.lower()} integration, and on a rotor FR-318 links the two. Drop "
            "moments_model or state it VORTICITY; or drop vorticity_drag_families to "
            "integrate the pressure for both."
        )
    return stated, False


def analysis_frame_and_moments(
    case: SimCase, script: Script, frame: int | None, *, rotor: bool
) -> None:
    """Point the analysis at the MRP frame and state the moments model, BEFORE the solve.

    THE ORDER DECIDES WHAT THE STEP EXPORTS STATE (B05, RPT-064): set before
    ``START_SOLVER``, every step export of a march prints the frame and the
    last step's moments equal the final export's; set after it, only the
    final export did. Both lines are init-phase commands in the database.

    A row with no moment point (and a continuation, which passes none) emits
    no frame, and a moments model only where its setup states or implies one;
    so a setup naming none emits exactly what it emitted before FR-317.
    """
    model, implied = moments_model_of(case, rotor=rotor)
    if frame is None and model is None:
        return
    helpers.analysis_setup(script, loads_frame=frame, moments_model=model or DEFAULT_MOMENTS_MODEL)
    if implied and script.solver_setup is not None:
        derived = {
            **script.solver_setup.derived,
            "moments_model": (
                f"{LINKED_MOMENTS_MODEL}: implied by vorticity_drag_families on a row "
                "turning a rotor (FR-318)"
            ),
        }
        script.solver_setup = script.solver_setup.model_copy(update={"derived": derived})


def emit_setup_extras(case: SimCase, script: Script, *, marching: bool) -> None:
    """Record the row's setup keys and register the setup's per-step actions (FR-316, FR-319).

    The setup keys the matrix row stated over its preset reach the snapshot the
    run record carries, so a record says which effective values came from the
    row. Then, on a marching row, the user's per-step actions where the setup
    states them; a steady row stating them is refused.
    """
    solver = case.solver
    if case.setup_from_row and script.solver_setup is not None:
        script.solver_setup = script.solver_setup.model_copy(
            update={"from_row": dict(case.setup_from_row)}
        )
    stated = [key for key in MARCHING_KEYS if getattr(solver, key) is not None]
    if stated and not marching:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {case.recipe!r} and its setup states "
            f"{', '.join(stated)}, which the solver applies to the time steps of an unsteady "
            "run; a steady run has none, so the key would change nothing while reading as "
            "though it had (FR-319). Drop the key from the preset this row names, or give "
            "the row a preset of its own."
        )
    for action in solver.unsteady_solver_actions or ():
        helpers.unsteady_action(
            script, name=action.name, kind=action.type, filename=action.filename
        )


def package_actions(case: SimCase, script: Script) -> list[str]:
    """Return the names of the per-step actions the package registered, not the setup's.

    The march label of a row (actions or a single march) says whether the
    package's own per-step machinery runs; a setup's ``unsteady_solver_actions``
    (FR-319) are the user's, registered on either kind of march.
    """
    own = {action.name for action in case.solver.unsteady_solver_actions or ()}
    return [use.name for use in script.unsteady_actions if use.name not in own]
