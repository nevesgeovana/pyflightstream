"""The run-type table, its conventions, and the build coverage of a workflow.

:class:`Workflow` is one run type; :class:`WorkflowConventions` is the
workspace naming the run layer passes down, because ``workspace`` sits above
``cases``; :func:`select_workflow` and :func:`resolve_workflow` read the
``WORKFLOW`` cell against :data:`WORKFLOWS`; :func:`covered_builds`,
:func:`require_coverage`, :class:`BuildCapabilities` and
:func:`command_accepted_on` judge a solver build against the commands a
workflow emits.

THE TABLE OBJECT LIVES HERE and its entries are written by ``_registry``.
The entries name the builders, which sit above every reader of the table,
and the readers (the selection of a run type, the refusal of a key no run
type registers) sit below the builders. One dict, created here empty and
filled once when the package is imported, is what lets both hold without an
import that points up. Every module of the package is imported through the
package root, which imports ``_registry``, so no caller ever sees the table
before its entries.
"""

from __future__ import annotations

from collections.abc import (
    Callable,
)
from dataclasses import (
    dataclass,
)

from pyflightstream._errors import (
    PyflightstreamError,
)
from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)
from pyflightstream.commands import (
    CommandEntry,
    CommandRegistry,
    Status,
    VersionView,
)
from pyflightstream.script import (
    Script,
    helpers,
    rotor_vocabulary,
)
from pyflightstream.versions import (
    FsVersion,
    known_versions,
    resolve,
)

from ._vocabulary import (
    _LEGACY,
    WORKFLOW_KEY,
)


class WorkflowCoverageError(PyflightstreamError, RuntimeError):
    """A workflow was asked for a solver build it does not cover.

    Raised BEFORE the first emission and before any executor is
    constructed, so nothing is spent and no half-built script exists
    (PFS-2025.18). The message names the build received, the builds the
    workflow covers in release order, and the commands whose absence
    forced the range.

    ``RuntimeError`` is the standard-library base rather than
    ``ValueError``, because this refusal is about the ENVIRONMENT the
    script would run in and not about an argument the caller passed:
    every argument may be perfectly well formed and the answer still be
    that this build cannot run this study.

    There is deliberately NO override route. The escape already exists
    one level up, in :meth:`pyflightstream.script.Script.allow_broken`,
    which is a recorded waiver naming a reason; a second, quieter one
    here would be a way past the guard that leaves no record.
    """


# --- the conventions the layer above passes down -----------------------------


@dataclass(frozen=True)
class WorkflowConventions:
    """What the run layer tells a workflow about the workspace.

    ``workspace`` sits ABOVE ``cases``, so a workflow can never reach
    the naming template that rendered these names; they arrive as data
    or they do not arrive at all.

    Attributes
    ----------
    outputs : tuple of str
        Output file names for the point being built, relative to the
        execution directory, already rendered by the workspace. A
        workflow exports these and never a literal, which is what keeps
        two points of one case from overwriting each other.
    animation_folder : str
        Folder, relative to the execution directory, that the unsteady
        animation writes its per-timestep frames into.
    """

    outputs: tuple[str, ...] = ()
    animation_folder: str = "frames"

    @classmethod
    def for_case(cls, case: SimCase) -> WorkflowConventions:
        """Fall back to the names the case itself carries.

        Used when no caller passed conventions in. The campaign loop
        renders :attr:`SimCase.outputs` for the point before the builder
        runs, so this is the same information one layer earlier.
        """
        return cls(outputs=tuple(case.outputs))


# --- the table ----------------------------------------------------------------


@dataclass(frozen=True)
class Workflow:
    """One run type, and everything needed to judge it before it runs.

    Attributes
    ----------
    name : str
        The name a ``WORKFLOW`` cell writes.
    summary : str
        One sentence, in plain language, saying what the type is FOR.
    commands : tuple of str
        Every command the builder ALWAYS emits, whatever the case says.
        This is what :func:`covered_builds` derives coverage from, so a
        command that is only sometimes emitted must NOT be listed:
        listing it would narrow the range for runs that never reach it.
    builder : callable
        ``builder(case, script, conventions) -> None``.
    keys : tuple of str
        Every ``VAR_NAMES_VALUES`` key the run type READS: the row's
        vocabulary, and the list a refusal prints when a row states a
        key outside it (PFS-2008.02.01, the rule of 2026-09-08: a row
        states only what the script will carry). A key here is one the
        builder, the clock, the window or the point name resolves; a key
        another run type reads is refused on this one naming that type,
        because a value nothing reads would change nothing about the
        run while reading as though it had. The tier-3 workspace is the
        control that the tuple is complete: every matrix there plans
        READY, so a key a row of it states is registered here.
    """

    name: str
    summary: str
    commands: tuple[str, ...]
    builder: Callable[[SimCase, Script, WorkflowConventions], None]
    keys: tuple[str, ...]


def workflow_names() -> tuple[str, ...]:
    """Return the registered workflow names, sorted."""
    return tuple(sorted(WORKFLOWS))


def resolve_workflow(name: str) -> Workflow:
    """Look one workflow up in the table.

    Parameters
    ----------
    name : str
        The workflow type, as a ``WORKFLOW`` cell writes it.

    Returns
    -------
    Workflow
        The registered workflow.

    Raises
    ------
    CampaignConfigError
        If no workflow of that name is registered. The refusal lists
        what IS registered, because a workflow cannot be supplied from
        outside: an unknown name is always a typo or a version gap, and
        never a module the caller forgot to install.
    """
    try:
        return WORKFLOWS[name]
    except KeyError:
        raise CampaignConfigError(
            f"{name!r} names no registered workflow type. The registered types are "
            f"{', '.join(workflow_names())}. A workflow is looked up in this package's "
            "own table and is never imported by reference, which is what separates it "
            "from a recipe: if you meant a function of your own, write it as a recipe "
            "reference ('package.module:function') and leave the WORKFLOW cell at "
            f"{_LEGACY}."
        ) from None


# --- selection: exactly one builder per case ---------------------------------


def _workflow_cell(case: SimCase) -> str | None:
    """Return the workflow a case names, or None when it names none."""
    declared = getattr(case, "workflow", None)
    if declared is None:
        declared = case.variables.get(WORKFLOW_KEY)
    if declared is None:
        return None
    name = str(declared).strip()
    if not name or name == _LEGACY:
        return None
    return name


def select_workflow(case: SimCase) -> str:
    """Return the workflow a case names, refusing two builders or none.

    Parameters
    ----------
    case : SimCase
        The case, as converted from a matrix row or authored in
        ``campaign.toml``.

    Returns
    -------
    str
        The workflow name; :func:`resolve_workflow` turns it into the
        builder.

    Raises
    ------
    CampaignConfigError
        If the case names BOTH a workflow and a user recipe, printing
        both values so the user can see which to delete; or if it
        names NEITHER, listing the types that exist.
    """
    workflow = _workflow_cell(case)
    recipe = (case.recipe or "").strip()
    # A recipe cell that simply repeats a registered workflow name is the
    # SAME statement said twice (the FS_SCRIPT code mapped to the type),
    # never a second builder, so it is not a conflict.
    recipe_is_a_workflow = recipe in WORKFLOWS
    if workflow and recipe and not recipe_is_a_workflow:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names a workflow AND a recipe: the workflow "
            f"{workflow!r} and the recipe {recipe!r}. One case builds its script one "
            "way. A workflow is this package's own run type and a recipe is a function "
            "you wrote; keeping both would leave which one runs to the order the loop "
            f"happens to check. Delete one: set the WORKFLOW cell to {_LEGACY} to keep "
            "the recipe, or drop the recipe reference to keep the workflow."
        )
    if workflow and recipe_is_a_workflow and recipe != workflow:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names a workflow AND a recipe: the workflow "
            f"{workflow!r} and the recipe {recipe!r}. Both are registered workflow "
            "types and they disagree, so nothing here can tell which run type the "
            "user meant. Make the two agree, or leave only one of them."
        )
    if workflow:
        return workflow
    if recipe_is_a_workflow:
        return recipe
    if not recipe:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names neither a workflow nor a recipe, so nothing "
            "would build its script. Name a run type in the WORKFLOW cell (the "
            f"registered types are {', '.join(workflow_names())}), or point FS_SCRIPT "
            "at a recipe reference of your own."
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the recipe {recipe!r} and no workflow, so this "
        "call has no workflow to build. Use the recipe path, or name a run type in the "
        f"WORKFLOW cell; the registered types are {', '.join(workflow_names())}."
    )


# --- coverage: the build is an input -----------------------------------------


def covered_builds(
    workflow: Workflow, *, registry: CommandRegistry | None = None
) -> tuple[str, ...]:
    """Return the solver builds a workflow covers, DERIVED from the database.

    A build is covered when its command view carries every command the
    workflow always emits, or the build's own documented vocabulary for
    that command's job (:data:`_SUBSTITUTES`, which the builder writes on
    that build). Nothing is declared: a build registered
    tomorrow joins this tuple the moment its evidence lands, and a
    command whose status moves narrows it in the same commit.

    Parameters
    ----------
    workflow : Workflow
        The run type.
    registry : CommandRegistry, optional
        Alternative database, used by tests; defaults to the packaged
        one.

    Returns
    -------
    tuple of str
        Canonical identifiers, in RELEASE order, which is the order of
        ``commands/_meta.yaml`` and the only ordering authority
        (CONTRIBUTING.md invariant 4).
    """
    database = registry or CommandRegistry.load()
    covered = []
    for build in known_versions():
        view = database.for_version(build)
        if all(_carried(view, name) for name in workflow.commands):
            covered.append(build.canonical)
    return tuple(covered)


def _carried(view: VersionView, name: str) -> bool:
    return name in view or (
        name in _SUBSTITUTES
        and (
            rotor_vocabulary.euclidean_rotor(view)
            or rotor_vocabulary.unmarked_euclidean_rotor(view)
        )
    )


def _missing_commands(
    workflow: Workflow, version: FsVersion, registry: CommandRegistry
) -> tuple[str, ...]:
    view = registry.for_version(version)
    return tuple(name for name in workflow.commands if not _carried(view, name))


def require_coverage(
    workflow: Workflow,
    version: str | FsVersion,
    *,
    registry: CommandRegistry | None = None,
) -> None:
    """Refuse a build the workflow does not cover, before anything is emitted.

    Parameters
    ----------
    workflow : Workflow
        The run type about to build.
    version : str or FsVersion
        The target FlightStream build.
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Raises
    ------
    WorkflowCoverageError
        If the build's command database does not carry every command
        the workflow always emits. The message names the build, the
        covered range in release order, and the commands that forced
        it.
    """
    database = registry or CommandRegistry.load()
    target = resolve(version)
    missing = _missing_commands(workflow, target, database)
    if not missing:
        return
    covered = covered_builds(workflow, registry=database)
    view = database.for_version(target)
    # The substitute, named only where the build carries PART of it, so
    # this sentence is a checkable truth on the builds it appears on: a
    # build with all of it, or with the angular velocity and no mark, is
    # covered, and one with none of it has nothing to be told about.
    note = ""
    for substitute in dict.fromkeys(_SUBSTITUTES[name] for name in missing if name in _SUBSTITUTES):
        carried = [other for other in substitute if other in view]
        absent = [other for other in substitute if other not in view]
        if carried and absent:
            note += (
                f" That build carries {', '.join(carried)} of the earlier vocabulary this "
                f"package writes in their place, and not {', '.join(absent)}, so it cannot be "
                "written there either."
            )
    covered_text = ", ".join(covered) if covered else "no registered build"
    raise WorkflowCoverageError(
        f"the {workflow.name!r} workflow does not cover FlightStream build "
        f"{target.canonical}. It covers {covered_text}, in release order. "
        f"{target.canonical} is outside that range because its command database carries "
        f"no {', '.join(missing)}.{note} Run this study on a build the workflow covers. "
        "There is no override: emitting a command a build does not carry is not a "
        "decision this package makes for you, and the one recorded way past a command "
        "the database refuses is Script.allow_broken, which names its reason."
    )


#: Commands that do the same job as a rotor workflow's own on the builds
#: that predate its vocabulary, and are WRITTEN there: the rotor axis and
#: speed of a ROTARY motion are, on a build whose motion type is EUCLIDEAN,
#: its angular velocity and its rotor mark (helpers.rotary_motion, GOAL-023),
#: or its angular velocity alone on the build without the mark (RPT-051).
#: A build where ``rotor_vocabulary.euclidean_rotor`` or
#: ``rotor_vocabulary.unmarked_euclidean_rotor`` holds covers the command
#: (``_carried``); the decision is made there and only there. This table lists
#: the MARKED substitute's commands, which the refusal note reads to name the
#: half a build carries; the unmarked substitute is its angular velocity alone.
_SUBSTITUTES: dict[str, tuple[str, ...]] = dict.fromkeys(
    rotor_vocabulary.ROTARY_ROTOR_COMMANDS, rotor_vocabulary.EUCLIDEAN_ROTOR_COMMANDS
)


# --- how a build is marched (ARCH-0200, GOAL-023) ---------------------------

#: :data:`pyflightstream.script.MARCH_ACTIONS` and ``MARCH_SINGLE`` are the
#: two marches, defined in the script layer that carries them; re-exported
#: here beside the seam that chooses between them.

#: The one command whose presence in a build's database is the per-step
#: action capability, the name the emitter itself uses.
_ACTION_COMMAND = helpers.UNSTEADY_ACTION_COMMAND


class BuildCapabilityError(WorkflowCoverageError):
    """A row asks a build for a feature that only a capability the build lacks provides.

    Raised by :func:`march_strategy` before the first emission, so a plan
    reports the point BLOCKED with this sentence and nothing is spent. The
    message names the build, each feature the row asked for, the builds that
    do document the capability, and what to write instead. A subclass of
    :class:`WorkflowCoverageError`, because it is the same kind of answer: the
    row is well formed and this build cannot run it as written.
    """


@dataclass(frozen=True)
class BuildCapabilities:
    """What one build can do, derived from its command database and nothing else.

    Never kept as a list: a command row landing for a build changes that
    build's capabilities the moment it lands, and the goal's support-matrix
    test re-derives them on every run.

    Attributes
    ----------
    build : str
        The canonical build identifier.
    unsteady_actions : bool
        Whether the build documents ``SET_NEW_UNSTEADY_SOLVER_ACTION``, the
        per-step action every actions-only feature rests on.
    """

    build: str
    unsteady_actions: bool

    @classmethod
    def of(cls, view: VersionView) -> BuildCapabilities:
        """Derive the capabilities of the build ``view`` answers for."""
        return cls(build=view.version.canonical, unsteady_actions=_ACTION_COMMAND in view)

    @classmethod
    def for_build(cls, build: str, *, registry: CommandRegistry | None = None) -> BuildCapabilities:
        """Derive the capabilities of a build named as a matrix ``FS_BUILD`` cell names it.

        Examples
        --------
        >>> BuildCapabilities.for_build("26.120").unsteady_actions
        False
        >>> BuildCapabilities.for_build("26.123").unsteady_actions
        True
        """
        return cls.of((registry or CommandRegistry.load()).for_version(build))


def _builds_with_actions(registry: CommandRegistry | None = None) -> tuple[str, ...]:
    """Return the registered builds that document the per-step action, in release order."""
    database = registry or CommandRegistry.load()
    return tuple(
        version.canonical
        for version in known_versions()
        if _ACTION_COMMAND in database.for_version(version.canonical)
    )


#: The command the per-step exports of a ``[time_averaging]`` window run through
#: (G25): the counter action that rewrites the exports script every step.
_AVERAGE_ACTION = "SET_NEW_UNSTEADY_SOLVER_ACTION"

#: THE COMMANDS A ROW REACHES ONLY WHERE A RUN VERIFIED THEM on the build,
#: which asks more than the documented status any other emission needs.
#: ``SOLVER_TIME_AVERAGING`` is documented from 26.122 and was measured hanging
#: 26.124 (C01, 2026-09-19). Since 0.28.0 no row reaches it at all:
#: ``[time_averaging]`` is averaged by the package from the per-step exports
#: (G25) and the command is never emitted. The input glossary states the builds
#: a key is accepted on by :func:`command_accepted_on`.
VERIFIED_ONLY_COMMANDS: frozenset[str] = frozenset({"SOLVER_TIME_AVERAGING"})


def command_accepted_on(entry: CommandEntry, version: FsVersion) -> bool:
    """Say whether a row may reach a command on a build: the rule the builders refuse by.

    A command documented or verified on the build is one a script emits there;
    a command of :data:`VERIFIED_ONLY_COMMANDS` must be verified there. A
    build with no record of the command, or one recording it broken or
    removed, accepts it under neither rule.

    Parameters
    ----------
    entry : CommandEntry
        The command's database entry.
    version : FsVersion
        The build, whose record is read with hotfix inheritance.

    Returns
    -------
    bool
        True where a row reaching the command is not refused for its status.

    Examples
    --------
    >>> from pyflightstream.commands import CommandRegistry
    >>> from pyflightstream.versions import resolve
    >>> command_accepted_on(CommandRegistry.load().commands["SOLVER_SET_AOA"], resolve("26.120"))
    True
    """
    record = entry.status_in(version)
    if record is None:
        return False
    if entry.name in VERIFIED_ONLY_COMMANDS:
        return record.status is Status.VERIFIED
    return record.status in (Status.DOCUMENTED, Status.VERIFIED)


#: The registered run types, by the name a ``WORKFLOW`` cell writes, in the
#: order ``_registry`` states them. Created empty here, below every builder,
#: so that the readers of the table (:func:`select_workflow`,
#: :func:`resolve_workflow`, the refusal of an unregistered key) reach it
#: without an import that points up; ``_registry``, which imports the
#: builders, writes the entries into this object once, when the package is
#: imported. It is the same object the package root exports.
WORKFLOWS: dict[str, Workflow] = {}
