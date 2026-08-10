"""What "supported" means, per registered FlightStream version.

Pipeline role: cross-cutting reporting layer above the script builder.
It answers one question the rest of the package could only answer by
implication, and answers it in named values rather than in prose.

The package registers a version by adding it to the ordered list in
``commands/_meta.yaml``, and from that moment every public surface
called it supported. That word covered four very different states at
once, and the widest gap between two of them was measured by the
independent review, and it is quoted here as the measurement of
2026-08-02 that it was rather than as a present fact: 26.000 was
registered, was accepted by ``Script(version="26.000")``, and carried
evidence for zero of the database's commands, so nothing whatsoever
could be built for it. The README said as much in a sentence; nothing
said it in a value a caller could read (finding PYFS-019, SRS FR-49).
That build's own manual was read on 2026-08-10 and it now carries 273
emittable commands, which is the levels working: the value moved
without anyone editing a claim.

The four levels, and every one of them is DERIVED. Nothing here is
declared in a file, because a hand-set support level is exactly the
kind of claim that outlives the fact behind it:

``registered``
    In the ordered list, and no command is available. The identifier
    exists so that campaigns naming it are refused by name rather than
    by accident, and so evidence can be backfilled later.
``documented``
    Commands are available, drafted from the manual with page
    citations. No command has been measured against a running solver
    on this version.
``verified``
    At least one command carries probe evidence this version can reach:
    a committed report either confirmed it or recorded it broken. Both
    count, because both are measurements. On a hotfix build the record
    may be the base release's, inherited: see
    :meth:`~pyflightstream.commands.CommandEntry.evidence_in` and the
    compatibility matrix, which marks every inherited cell.
``operational``
    Verified, and the minimal end-to-end workflow of
    :func:`minimal_workflow` builds for it. This is the level that
    claims a user can actually get from geometry to a loads file.

The ladder is ordered and total: every registered version sits at
exactly one level, and the levels ascend in the order above.

Why ``operational`` is not simply "verified plus some commands": the
review asked for a level whose claim is checkable end to end, and a
version can carry probe evidence for a scattering of commands while
lacking one link of the chain that produces a result. So the level is
defined by a workflow that builds, and a tier 1 test builds it for
every version this module reports operational. The claim and its check
are the same object.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict

from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "MINIMAL_WORKFLOW_COMMANDS",
    "SUPPORT_LADDER",
    "SupportLevel",
    "VersionSupport",
    "minimal_workflow",
    "support_level",
    "support_table",
    "version_support",
]


class SupportLevel(enum.StrEnum):
    """How far the evidence for one FlightStream version actually goes.

    Ascending. See the module docstring for what each level requires;
    the definitions live there because they are one story rather than
    four.
    """

    REGISTERED = "registered"
    DOCUMENTED = "documented"
    VERIFIED = "verified"
    OPERATIONAL = "operational"


#: Ascending order of :class:`SupportLevel`, which is the enum's own
#: declaration order. Written out rather than derived from ``__members__``
#: so that a reordering of the class body cannot silently reorder the
#: ladder, and asserted against the class in tests/test_support.py.
SUPPORT_LADDER: tuple[SupportLevel, ...] = (
    SupportLevel.REGISTERED,
    SupportLevel.DOCUMENTED,
    SupportLevel.VERIFIED,
    SupportLevel.OPERATIONAL,
)

#: The commands the minimal workflow emits, in order. Geometry in,
#: solver initialized, solution run, loads out: the shortest path from a
#: mesh file to a number, with nothing in it that is a preference rather
#: than a link in the chain. A version missing any one of these cannot
#: be called operational, and which one is missing is what
#: :attr:`VersionSupport.workflow_missing` reports.
MINIMAL_WORKFLOW_COMMANDS: tuple[str, ...] = (
    "NEW_SIMULATION",
    "IMPORT",
    "SET_SIMULATION_LENGTH_UNITS",
    "AUTO_DETECT_TRAILING_EDGES",
    "SET_FREESTREAM",
    "FLUID_PROPERTIES",
    "INITIALIZE_SOLVER",
    "SOLVER_SET_AOA",
    "SOLVER_SET_VELOCITY",
    "SOLVER_SET_REF_VELOCITY",
    "SOLVER_SET_REF_AREA",
    "SOLVER_SET_REF_LENGTH",
    "SOLVER_SET_ITERATIONS",
    "START_SOLVER",
    "SET_LOADS_AND_MOMENTS_UNITS",
    "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
    "CLOSE_FLIGHTSTREAM",
)


class VersionSupport(BaseModel):
    """The support level of one registered version, with its evidence.

    Attributes
    ----------
    canonical : str
        Canonical identifier, for example ``"26.120"``.
    alias : str
        Vendor release name. Not unique: the vendor ships every hotfix
        of a minor release under one name, so two rows can share it.
    level : SupportLevel
        The derived level.
    commands_available : int
        Commands the database exposes for this version, counting the
        ones recorded broken, because a broken command is a measured
        command.
    commands_probed : int
        Of those, the ones carrying probe evidence (``verified`` or
        ``broken``) that this version can reach. On a hotfix build the
        count INCLUDES records inherited from the base release, so some
        of them were probed on that other build. No number is written
        here: it moves with every probe run. Nor is the split asserted
        anywhere today, which is worth saying plainly because this
        docstring used to credit
        ``tests/test_evidence_provenance.py`` with measuring it and that
        file measures the neighbouring claim, the inherited cell count of
        the rendered matrix, whose two sides both derive from this same
        registry. Reporting the two separately, with the guard that makes
        a wrong split fail, is registered as PLN-20260803-2210.
    workflow_missing : tuple of str
        Commands of :data:`MINIMAL_WORKFLOW_COMMANDS` this version
        cannot emit, in workflow order. Empty when the workflow builds.
    summary : str
        One sentence naming the level and the reason for it, for a
        README table, a docs page or a console.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical: str
    alias: str
    level: SupportLevel
    commands_available: int
    commands_probed: int
    workflow_missing: tuple[str, ...] = ()
    summary: str


def minimal_workflow(
    version: str | FsVersion,
    *,
    geometry: str = "wing.stl",
    output: str = "loads.txt",
    registry: CommandRegistry | None = None,
) -> Script:
    """Build the smallest complete script that produces a result.

    Geometry in, solver initialized, solution run, loads exported. It is
    the reference answer to "does this version work at all", and the
    definition of the ``operational`` support level: a version is
    operational when this builds for it.

    Every value in it is a placeholder except the fluid state, which is
    the sea-level standard atmosphere. The script is validated against
    the version like any other, so a version missing one link refuses
    here, naming the command.

    Parameters
    ----------
    version : str or FsVersion
        Target version, canonical identifier or a vendor name that
        identifies exactly one registered build.
    geometry : str
        Mesh file the script imports. Not read: the builder emits a
        path, it never opens one.
    output : str
        Loads spreadsheet the script exports.
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Returns
    -------
    Script
        The built script, ready to render.

    Raises
    ------
    CommandNotInVersionError
        If the version cannot emit one of the workflow's commands. The
        message names which, and that is the honest answer to whether
        the version is usable.

    Examples
    --------
    >>> from pyflightstream.support import minimal_workflow
    >>> print(minimal_workflow("26.120").render().splitlines()[0])
    NEW_SIMULATION
    """
    script = Script(version, registry=registry)
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", geometry, clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("SET_FREESTREAM", "CONSTANT")
    # Explicit properties rather than AIR_ALTITUDE: the altitude command
    # is recorded broken on 26.120 and would make the reference workflow
    # of this package need a waiver to build (FR-48).
    script.emit(
        "FLUID_PROPERTIES",
        density=1.225,
        pressure=101325.0,
        temperature=288.15,
        viscosity=1.789e-5,
        specific_heat_ratio=1.4,
    )
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="INCOMPRESSIBLE",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
    )
    script.emit("SOLVER_SET_AOA", 0.0)
    script.emit("SOLVER_SET_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_AREA", 1.0)
    script.emit("SOLVER_SET_REF_LENGTH", 1.0)
    script.emit("SOLVER_SET_ITERATIONS", 100)
    script.emit("START_SOLVER")
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", output)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


def _workflow_gaps(version: FsVersion, registry: CommandRegistry) -> tuple[str, ...]:
    """Return the workflow commands this version cannot emit, in order."""
    view = registry.for_version(version)
    return tuple(name for name in MINIMAL_WORKFLOW_COMMANDS if name not in view)


def version_support(
    version: str | FsVersion, *, registry: CommandRegistry | None = None
) -> VersionSupport:
    """Report the support level of one registered version, with its evidence.

    Parameters
    ----------
    version : str or FsVersion
        Target version, canonical identifier or an unambiguous vendor
        name.
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Returns
    -------
    VersionSupport
        The level and the counts it was derived from.

    Examples
    --------
    >>> from pyflightstream.support import version_support
    >>> version_support("26.000").level
    <SupportLevel.DOCUMENTED: 'documented'>
    """
    resolved = resolve(version)
    registry = registry or CommandRegistry.load()
    available = 0
    probed = 0
    for entry in registry.commands.values():
        record = entry.status_in(resolved)
        if record is None or record.status is Status.REMOVED:
            continue
        available += 1
        if record.status in (Status.VERIFIED, Status.BROKEN):
            probed += 1
    missing = _workflow_gaps(resolved, registry)

    if available == 0:
        level = SupportLevel.REGISTERED
        why = (
            "the identifier is registered and ordered, and no command carries "
            "evidence for it, so nothing can be built for this version yet"
        )
    elif probed == 0:
        level = SupportLevel.DOCUMENTED
        why = (
            f"{available} commands carry recorded evidence for this build, and none "
            "has been measured against a running solver on this version"
        )
    elif missing:
        level = SupportLevel.VERIFIED
        why = (
            f"{probed} of {available} commands carry probe evidence reachable for this "
            f"version, and the minimal workflow does not build: {', '.join(missing)} "
            "cannot be emitted"
        )
    else:
        level = SupportLevel.OPERATIONAL
        why = (
            f"{probed} of {available} commands carry probe evidence reachable for this "
            "version, and the minimal end-to-end workflow builds for it"
        )
    return VersionSupport(
        canonical=resolved.canonical,
        alias=resolved.alias,
        level=level,
        commands_available=available,
        commands_probed=probed,
        workflow_missing=missing,
        summary=f"FlightStream {resolved.canonical} is {level}: {why}.",
    )


def support_level(
    version: str | FsVersion, *, registry: CommandRegistry | None = None
) -> SupportLevel:
    """Return the support level of one registered version.

    Shorthand for :func:`version_support`'s ``level``, for the caller
    who wants the value and not the evidence behind it.

    Parameters
    ----------
    version : str or FsVersion
        Target version.
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Returns
    -------
    SupportLevel
        The derived level.
    """
    return version_support(version, registry=registry).level


def support_table(*, registry: CommandRegistry | None = None) -> tuple[VersionSupport, ...]:
    """Report every registered version, in release order.

    Release order comes from ``commands/_meta.yaml``, which is the only
    ordering authority (CLAUDE.md invariant 4). It is NOT support order.
    The two agree at this release only because the builds split cleanly
    by age: the ones whose manuals have been read but whose solvers have
    not been probed derive ``documented``, and the probed ones derive
    ``operational``. No tally is written here, because it moves with
    every build registered. They came apart as recently as v0.5.0's own
    development, when 26.100 sat at ``verified`` behind both of its
    successors for want of database rows rather than for anything about
    the solver, and nothing prevents them coming apart again the moment a
    build is registered ahead of its evidence. Read the level off the
    row, never off the position.

    Parameters
    ----------
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Returns
    -------
    tuple of VersionSupport
        One row per registered version, oldest release first.

    Examples
    --------
    >>> from pyflightstream.support import support_table
    >>> {row.canonical: str(row.level) for row in support_table()}["26.000"]
    'documented'
    """
    registry = registry or CommandRegistry.load()
    return tuple(version_support(version, registry=registry) for version in known_versions())
