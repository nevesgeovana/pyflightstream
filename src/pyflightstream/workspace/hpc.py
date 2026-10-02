"""The HPC profile of a workspace: the cluster it may be opened on (FR-99).

A workspace keeps, under ``hpc/``, the profile of each cluster its campaign
may be submitted to: the scheduler's name for the application (the one
mandatory field), the descriptor format the package writes, the walltime
arithmetic, the log keys (FR-311) and the ``[builds]`` table that maps each
canonical build to the name this scheduler gives it. :func:`read_hpc_profile`
reads one into an :class:`HpcProfile`, refusing an unknown or misplaced key
by name, and :func:`resolve_hpc_profile` finds the one a run names.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.workspace.inputs`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import re
import string
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._digest import aliased_name_fault
from pyflightstream._errors import InputArtifactError
from pyflightstream.versions import AmbiguousVersionAliasError, UnknownVersionError, resolve
from pyflightstream.workspace.sidecars import load_toml

__all__ = [
    "HPC_BUILD_ALIAS",
    "HPC_DIR",
    "HPC_FORMATS",
    "HPC_LOG_KEYS",
    "HPC_PROFILE_KEYS",
    "HPC_REQUIRED",
    "WALLTIME_ARITHMETIC",
    "HpcProfile",
    "descriptor_name_refusal",
    "hpc_profiles",
    "read_hpc_profile",
    "resolve_hpc_profile",
    "select_hpc_profile",
]


# --- FR-99: the HPC profile ---------------------------------

#: Where a workspace keeps the profile of the cluster it may be opened on.
HPC_DIR = "hpc"

#: The one field a profile MUST carry: the scheduler's own name for the
#: application. It is the only field nothing else in the workspace can
#: supply, which is what makes it mandatory and the rest not.
HPC_REQUIRED = ("application_id",)

#: The descriptor formats the package can write. `text` writes the fields
#: as `key: value` lines with no quoting, for a scheduler that reads a
#: plain list.
HPC_FORMATS = ("yaml", "json", "toml", "text")

#: The substitution a descriptor field writes to name the build the way THIS
#: scheduler names it, read from the profile's ``[builds]`` table.
HPC_BUILD_ALIAS = "fs_build_alias"


@dataclass(frozen=True)
class HpcProfile:
    """How ONE cluster is asked to run a job (FR-99).

    NO ROW CITES THIS. The code sees Linux and
    that is the cluster, so a study moves between machines by being opened
    on the other one and changing no cell.

    Attributes
    ----------
    application_id : str
        The scheduler's own name for the application.
    descriptor_format : str
        One of :data:`HPC_FORMATS`. What the descriptor file IS, so the
        package writes it rather than the study pasting a template.
    descriptor_name : str
        What it is called inside the simulation folder.
    fields : dict of str to str
        The keys THIS cluster expects, in the order they are written, and
        what pyflightstream puts in each. A value in braces is substituted.
        A cluster that spells `cpus` or `queue` is served by editing this
        table and nothing else.
    submit : tuple of str
        The command, argument by argument, never one string through a
        shell: a path with a space in it is then not a second argument.
    defaults : dict of str to object
        The floor for a resource a row may state. `ncpus` is deliberately
        not among them: there is one processor count and it lives in the
        matrix row.
    path : Path
        Where this was read from, for a refusal that has to name it.
    builds : dict of str to str
        What this scheduler calls each canonical build, read from the
        ``[builds]`` table and written into a descriptor by the
        ``{fs_build_alias}`` substitution. KEYED BY BUILD, because the
        relation is many-to-one: a family name such as ``26.1`` covers two
        registered builds, so a table keyed by the scheduler's name could not
        say which build a row meant. The matrix cell names the build and
        stays the same on every machine; this table translates it for one
        cluster. It is a DECLARATION and verifies nothing: which build the
        scheduler actually starts is known only from the build number in a
        collected log.
    """

    application_id: str
    descriptor_format: str
    descriptor_name: str
    fields: dict
    submit: tuple
    defaults: dict
    path: Path
    builds: dict = field(default_factory=dict)
    #: WHAT THE DESCRIPTOR'S WALLTIME FIELD CARRIES (0.21.0). ``wall`` is the row's
    #: cell as written, which is what a scheduler taking ``4h`` wants; ``seconds``
    #: is the whole clock in integer seconds, which is what this package wrote until 0.20.x and what
    #: a scheduler with a numeric field wants. The arithmetic a particular
    #: cluster needs is configured here explicitly, and an
    #: unknown value is refused by name rather than silently taken as one of
    #: these two.
    walltime_arithmetic: str = "wall"
    #: WHETHER THE SCRIPT EXPORTS THE SOLVER LOG (0.21.0). Some machines abort at
    #: ``EXPORT_LOG`` and write their own log beside the run instead, so the profile
    #: says it rather than the package assuming one shape of machine.
    export_log: bool = True
    #: THE LOG THAT MACHINE WRITES ITSELF, as a glob relative to the run's
    #: working directory, for example ``FTS{sim}.l*``. `collect` copies the one
    #: file matching it to the standard log name, so everything downstream
    #: reads one file whatever the scheduler called it. None where the
    #: scheduler writes none.
    native_log: str | None = None
    #: THE FILES THE SCHEDULER WRITES WHEN A JOB ENDS (FR-311), as globs relative
    #: to the run's working directory with the placeholders of ``native_log``
    #: (``{sim}``, ``{point}``); the job id, which the package never learns, is
    #: matched by the glob. When every one matches and the solver log does not,
    #: `collect` records the point FAILED_EXECUTION. Empty: `collect` waits.
    job_end_files: tuple[str, ...] = ()
    #: THE LONGEST WALL CLOCK THIS CLUSTER GRANTS A JOB, in seconds, read from the top-level
    #: ``max_walltime = "HH:MM:SS"`` (FR-377); None where the profile states none. A grouped
    #: plan caps a computed walltime at it and refuses a matrix value above it.
    max_walltime_s: float | None = None
    #: WHERE A GROUPED JOB'S SCRIPT PATHS START (FR-377), a template with the placeholders
    #: ``{work_dir}``, ``{batch}`` and ``{sim}``; the default is the job folder as the workspace
    #: sees it.
    job_root: str = "{work_dir}"

    def __post_init__(self) -> None:
        """Refuse a descriptor name that is not a plain file name.

        A PROFILE BUILT IN PYTHON IS HELD TO THE RULE A FILE IS: the executor
        writes the descriptor at ``working_dir / descriptor_name``, so the name
        is checked where every route to the executor passes, not only where a
        TOML file is read.
        """
        refusal = descriptor_name_refusal(str(self.descriptor_name), self.path)
        if refusal is not None:
            raise InputArtifactError(refusal)


def descriptor_name_refusal(name: str, source: object) -> str | None:
    """Why ``name`` cannot name a submission descriptor, or None when it can.

    The descriptor is written in the folder each point runs in, so its name
    is a plain file name: no folder, no parent folder, and no form Windows
    reads as another file's, any of which would put it on a file another
    point's record names. ``source`` names the profile in the sentence.

    Parameters
    ----------
    name : str
        The descriptor name the profile states.
    source : object
        The profile (usually its path), named in the refusal sentence.

    Returns
    -------
    str or None
        The sentence that says why ``name`` is refused, or None when it is an
        acceptable file name.
    """
    alias = aliased_name_fault(name)
    if (
        name.strip()
        and not any(sep in name for sep in "/\\")
        and name not in (".", "..")
        and alias is None
    ):
        return None
    return (
        f"the HPC profile {source} names its descriptor {name!r}; the "
        "descriptor is written in the folder each point runs in, so its name "
        "is a plain file name, with no folder, no parent folder and no form "
        "Windows reads as another file's" + (f" (it {alias})" if alias else "") + "."
    )


def hpc_profiles(inputs_dir: str | Path) -> list[Path]:
    """Every HPC profile a workspace carries, sorted.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory; the profiles are the ``*.toml``
        files of its ``hpc/`` folder.

    Returns
    -------
    list of Path
        The profile files in name order; empty when the folder is absent or
        holds none.
    """
    directory = Path(inputs_dir) / HPC_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.toml"))


#: The profile stem the invocation selected (``--hpc NAME``), or None.
_SELECTED_HPC: ContextVar[str | None] = ContextVar("pyflightstream_selected_hpc", default=None)


def select_hpc_profile(name: str | None) -> None:
    """Select which profile :func:`resolve_hpc_profile` returns (0.35.0).

    Parameters
    ----------
    name : str or None
        The file stem of the profile, ``h002`` for ``inputs/hpc/h002.toml``;
        None clears the selection, which restores the one-profile behaviour.

    Returns
    -------
    None
        The selection is held in a context variable, so it belongs to the
        invocation that made it.
    """
    _SELECTED_HPC.set(name)


def resolve_hpc_profile(inputs_dir: str | Path) -> HpcProfile | None:
    """Return the profile of the cluster this workspace is on, or None.

    ONE PROFILE NEEDS NO SELECTOR. A workspace carrying several and no
    selection (:func:`select_hpc_profile`, CLI ``--hpc NAME``) is REFUSED
    rather than guessed, because guessing spends a queue.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    HpcProfile or None
        The selected profile, else the profile of the one cluster the
        workspace carries, or None when it carries no profile.

    Raises
    ------
    InputArtifactError
        If a selection names no profile of the folder, if the folder holds
        more than one profile and none is selected, or the profile is refused
        by :func:`read_hpc_profile`.
    """
    found = hpc_profiles(inputs_dir)
    selected = _SELECTED_HPC.get()
    if selected is not None:
        for path in found:
            if path.stem == selected:
                return read_hpc_profile(path)
        raise InputArtifactError(
            f"{Path(inputs_dir) / HPC_DIR} holds no profile named {selected!r}; "
            f"available: {', '.join(path.stem for path in found) or 'none'}."
        )
    if not found:
        return None
    if len(found) > 1:
        raise InputArtifactError(
            f"{Path(inputs_dir) / HPC_DIR} holds {len(found)} profiles "
            f"({', '.join(path.name for path in found)}) and nothing says which cluster "
            "this machine is. One profile needs no selector; several need one: select "
            "the profile by its file stem, hpc (CLI: --hpc) taking <name>, or "
            "select_hpc_profile(name); guessing spends a queue."
        )
    return read_hpc_profile(found[0])


#: What a profile may ask the descriptor's walltime field to carry.
WALLTIME_ARITHMETIC: frozenset[str] = frozenset({"wall", "seconds"})

#: THE KEYS A PROFILE MAY CARRY, and the keys its ``[log]`` table may carry.
#: Both sets are CLOSED, for the reason the flight-condition cell's set is
#: closed: a mistyped or misplaced key costs a message rather than a job that
#: aborts at EXPORT_LOG with a profile that looks right in the file. Measured
#: by the interface lens, 2026-09-16: ``export_log`` written at the top level
#: read as True, and ``native_logs`` read as absent.
HPC_PROFILE_KEYS: frozenset[str] = frozenset(
    {
        "application_id",
        "descriptor",
        "submit",
        "defaults",
        "builds",
        "walltime_arithmetic",
        "log",
        "max_walltime",
        "job_root",
    }
)
HPC_LOG_KEYS: frozenset[str] = frozenset({"export_log", "native_log", "job_end_files"})


def _refuse_unknown_keys(
    target: Path, table: Mapping[str, object], allowed: frozenset[str], where: str
) -> None:
    """Refuse a key this package does not read, naming it and the set it is not in."""
    unknown = sorted(str(key) for key in table if str(key) not in allowed)
    if not unknown:
        return
    raise InputArtifactError(
        f"the HPC profile {target} states {', '.join(unknown)} {where}, and this package "
        f"reads {', '.join(sorted(allowed))} there. A key nothing reads is a key that looks "
        "like it works: a misplaced export_log leaves EXPORT_LOG in the script on the very "
        "machine the table exists for. Correct the spelling, or move the key to the table "
        "that takes it."
    )


def _refuse_a_misplaced_key(target: Path, table: Mapping[str, object]) -> None:
    """Refuse a key this package OWNS that is written under some other table.

    The top level and ``[log]`` are closed sets; the tables between them are the
    user's own (``[submit]`` carries the submission's fields, ``[descriptor]``
    the descriptor's names), so closing those would refuse working profiles.
    What is refused here is narrower and is the mistake people actually make:
    a key this package reads, written where this package does not read it.

    WHY IT IS THE LIKELY SPELLING, measured by the qa lens of the closing round
    (2026-09-16): appending ``export_log = false`` to the END of a profile file
    is, in TOML, writing it into the LAST TABLE, which in the documented example
    is ``[submit]``. That was accepted in silence while the message beside it
    told the user to move the key to the table that takes it.
    """
    for name, value in table.items():
        if str(name) == "log" or not isinstance(value, Mapping):
            continue
        for owned in sorted(HPC_LOG_KEYS):
            if owned in value:
                raise InputArtifactError(
                    f"the HPC profile {target} states {owned} under [{name}], and this "
                    f"package reads it under [log]. A key nothing reads is a key that "
                    f"looks like it works: appending a line to the end of the file puts "
                    f"it in the last table, not at the top level. Move {owned} under "
                    f"[log]."
                )
        for nested, deeper in value.items():
            if isinstance(deeper, Mapping):
                for owned in sorted(HPC_LOG_KEYS):
                    if owned in deeper:
                        raise InputArtifactError(
                            f"the HPC profile {target} states {owned} under "
                            f"[{name}.{nested}], and this package reads it under [log]. "
                            f"Move it there."
                        )


def read_hpc_profile(path: str | Path) -> HpcProfile:
    """Read one HPC profile, refusing what it cannot act on.

    Parameters
    ----------
    path : str or Path
        The profile file, a TOML document.

    Returns
    -------
    HpcProfile
        The profile read from the file.

    Raises
    ------
    InputArtifactError
        If the file is not valid TOML, lacks the scheduler's application name,
        asks for a descriptor format or walltime arithmetic this package does
        not write, names a descriptor that is not a plain file name, lists no
        descriptor fields or no submit command, or states a key this package
        does not read (or one it owns under the wrong table).
    """
    target = Path(path)
    table = load_toml(target, "hpc profile")
    for key in HPC_REQUIRED:
        if not str(table.get(key) or "").strip():
            raise InputArtifactError(
                f"the HPC profile {target} states no {key!r}. It is the scheduler's own "
                "name for the application and the one field nothing else in the "
                "workspace can supply, which is why it is the only mandatory one."
            )
    descriptor = table.get("descriptor") or {}
    fmt = str(descriptor.get("format") or "yaml").strip().lower()
    if fmt not in HPC_FORMATS:
        raise InputArtifactError(
            f"the HPC profile {target} asks for a {fmt!r} descriptor; this package "
            f"writes {', '.join(HPC_FORMATS)}."
        )
    # THE DESCRIPTOR IS A FILE OF THE POINT'S FOLDER, named plainly: a name with a
    # folder in it, a parent folder, or a form Windows reads as another file's
    # would write it over a file another point's record names. HpcProfile
    # refuses the same name however it is built; this names the file it came from.
    stated_name = descriptor.get("name")
    if stated_name is not None:
        refusal = descriptor_name_refusal(str(stated_name), target)
        if refusal is not None:
            raise InputArtifactError(refusal)
    fields = descriptor.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        raise InputArtifactError(
            f"the HPC profile {target} lists no descriptor fields, so the file it "
            "writes would be empty. The fields table is what this cluster expects and "
            "what makes the profile portable."
        )
    submit = (table.get("submit") or {}).get("command") or []
    if not isinstance(submit, list) or not submit:
        raise InputArtifactError(
            f"the HPC profile {target} states no submit command. Write it argument by "
            'argument, for example command = ["esub", "{descriptor_path}"]: one string '
            "through a shell splits a path that has a space in it."
        )
    builds = _read_build_aliases(target, table.get("builds"))
    arithmetic = str(table.get("walltime_arithmetic") or "wall").strip().lower()
    if arithmetic not in WALLTIME_ARITHMETIC:
        raise InputArtifactError(
            f"the HPC profile {target} states walltime_arithmetic = {arithmetic!r}, and "
            f"this package writes {', '.join(sorted(WALLTIME_ARITHMETIC))}. 'wall' puts "
            "the row's cell in the descriptor as written (4h stays 4h); 'seconds' puts "
            "the whole clock in integer seconds, which is what this package wrote until "
            "0.20.x. Whatever your scheduler's field means, it is stated here and never "
            "in the row: the row's cell is the wall clock and the watchdog counts down "
            "to it either way."
        )
    _refuse_unknown_keys(target, table, HPC_PROFILE_KEYS, "at its top level")
    _refuse_a_misplaced_key(target, table)
    log = table.get("log") or {}
    if not isinstance(log, Mapping):
        raise InputArtifactError(
            f"the HPC profile {target} has a log entry that is not a table. Write it as "
            "[log], with export_log and native_log under it."
        )
    _refuse_unknown_keys(target, log, HPC_LOG_KEYS, "under [log]")
    export_log = bool(log.get("export_log", True))
    native_log = str(log.get("native_log") or "").strip() or None
    if not export_log and native_log is None:
        raise InputArtifactError(
            f"the HPC profile {target} states export_log = false and no native_log, which "
            "asks for a run with no log at all. This package judges an unsteady run BY its "
            "log -- the time loop always reaches its prescribed end, so without one every "
            "such run is recorded COMPLETED_MAX_ITER whether it converged at every step or "
            'at none. Name the log your scheduler writes, as native_log = "FTS{sim}.l*", '
            "or leave export_log alone and let the script write it."
        )
    return HpcProfile(
        walltime_arithmetic=arithmetic,
        export_log=export_log,
        native_log=native_log,
        job_end_files=_job_end_files(target, log.get("job_end_files", [])),
        max_walltime_s=_max_walltime_s(target, table.get("max_walltime")),
        job_root=_job_root(target, table.get("job_root")),
        builds=builds,
        application_id=str(table["application_id"]),
        descriptor_format=fmt,
        # THE DEFAULT FOLLOWS THE FORMAT, not the word yaml. A profile
        # stating format = "json" and no name used to write JSON into a
        # file called submit.yaml: two fields of one artifact, one
        # silently overriding the other's meaning, and the person
        # debugging a rejected submission opens the file and cannot tell
        # which of the two is authoritative (the interface lens,
        # 2026-09-13). An explicit `name` still wins.
        descriptor_name=str(descriptor.get("name") or f"submit.{'txt' if fmt == 'text' else fmt}"),
        fields={str(k): str(v) for k, v in fields.items()},
        submit=tuple(str(part) for part in submit),
        defaults=dict(table.get("defaults") or {}),
        path=target,
    )


#: The one form ``max_walltime`` takes: hours (which may exceed 24), minutes, seconds.
_CLOCK = re.compile(r"(\d+):([0-5]\d):([0-5]\d)")

#: The placeholders ``job_root`` may carry.
_JOB_ROOT_FIELDS = frozenset({"work_dir", "batch", "sim"})


def _max_walltime_s(target: Path, stated: object) -> float | None:
    """Read the top-level ``max_walltime`` (FR-377): ``HH:MM:SS``, hours beyond 24 allowed."""
    if stated is None:
        return None
    found = _CLOCK.fullmatch(str(stated).strip()) if isinstance(stated, str) else None
    if found is None or not any(int(part) for part in found.groups()):
        raise InputArtifactError(
            f"the HPC profile {target} states max_walltime = {stated!r}. It is the longest "
            "wall clock the cluster grants a job, written HH:MM:SS with hours beyond 24 "
            'allowed, for example "48:00:00"; 2d and 48h are not read, and a clock of zero '
            "grants nothing."
        )
    hours, minutes, seconds = (int(part) for part in found.groups())
    return float(hours * 3600 + minutes * 60 + seconds)


def _job_root(target: Path, stated: object) -> str:
    """Read the top-level ``job_root`` template, refusing a placeholder it does not fill."""
    if stated is None:
        return "{work_dir}"
    text = str(stated).strip()
    try:
        names = {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    except ValueError:
        names = {"?"}
    if not text or not names <= _JOB_ROOT_FIELDS:
        raise InputArtifactError(
            f"the HPC profile {target} states job_root = {stated!r}. It is a path template "
            "whose placeholders are {work_dir}, {batch} and {sim}, for example "
            '"{work_dir}" or "/scratch/{batch}".'
        )
    return text


def _job_end_files(target: Path, ends: object) -> tuple[str, ...]:
    """Read ``[log] job_end_files`` (FR-311): a list of globs with native_log's placeholders."""
    try:
        valid = isinstance(ends, list) and all(
            str(pattern.format(sim="s", point="p")).strip() for pattern in ends
        )
    except (AttributeError, IndexError, KeyError, ValueError):
        valid = False
    if not valid or not isinstance(ends, list):
        raise InputArtifactError(
            f"the HPC profile {target} states job_end_files = {ends!r}. It is a list of the "
            "file names the scheduler writes when a job ends, as globs with the placeholders "
            'of native_log, {sim} and {point}, for example ["FTS{sim}.o*", "FTS{sim}.e*"].'
        )
    return tuple(str(pattern).strip() for pattern in ends)


def _read_build_aliases(target: Path, table: object) -> dict[str, str]:
    """Read a profile's ``[builds]`` table, refusing a key that is not one build.

    A KEY MUST BE A CANONICAL BUILD, and that is the whole reason the table
    is keyed this way round. ``26.1`` is a family: it resolves to more than
    one registered build and is refused by :func:`resolve` for exactly that
    reason, so a table keyed by it could not say which build a row meant.
    The scheduler's name is the VALUE, where several builds may share one.
    """
    if table is None:
        return {}
    if not isinstance(table, Mapping):
        raise InputArtifactError(
            f"the HPC profile {target} has a builds entry that is not a table. Write it as "
            '[builds] with one line per canonical build, for example "26.123" = "26.1".'
        )
    aliases: dict[str, str] = {}
    for key, value in table.items():
        build = str(key).strip()
        try:
            canonical = resolve(build).canonical
        except (AmbiguousVersionAliasError, UnknownVersionError) as error:
            raise InputArtifactError(
                f"the HPC profile {target} maps {build!r} in its [builds] table, and a key "
                "there must name ONE registered build, because several builds can share one "
                f"scheduler name and only the build says which: {error}"
            ) from None
        if canonical != build:
            raise InputArtifactError(
                f"the HPC profile {target} maps {build!r} in its [builds] table; write the "
                f"canonical build {canonical!r}, which is how a matrix row names it."
            )
        alias = str(value).strip() if isinstance(value, str) else ""
        if not alias:
            raise InputArtifactError(
                f"the HPC profile {target} maps build {build!r} to {value!r}; the value is "
                "the name this scheduler gives that build, as text, and it cannot be empty."
            )
        aliases[canonical] = alias
    return aliases
