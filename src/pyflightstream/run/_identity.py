"""Which package and which solver build ran, and the run read back.

Private to :mod:`pyflightstream.run`, which re-exports every public name
of it. :func:`package_vcs_state` records which commit of this package
ran; :func:`check_solver_identity` and the scheduled-build checks refuse a
build the campaign did not register; :func:`reconstruct` reads one
manifest record back into the invocation that produced it, with a verdict
on whether each file still hashes to what the record says (NFR-07).
"""

from __future__ import annotations

import copy
import inspect
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyflightstream
import pyflightstream._textio as _textio
from pyflightstream._digest import (
    file_sha256,
    optional_file_sha256,
    text_sha256,
)
from pyflightstream.cases import (
    Campaign,
    ScriptRecipe,
    SimCase,
)
from pyflightstream.results import (
    VersionMismatchWarning,
)
from pyflightstream.run._executors import (
    Executor,
    ExecutorConfigurationError,
    SolverBuild,
    _machine_exports_log,
)
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion, resolve
from pyflightstream.workspace import (
    KNOWN_MANIFEST_SCHEMAS,
    CampaignWorkspace,
    InputArtifactError,
    RunRecord,
    WorkspaceError,
    resolve_build,
)
from pyflightstream.workspace._settings_file import (
    ENTRY_ACCEPTANCE_SOURCE,
    entry_acceptance_allowed,
    invocation_sources,
)
from pyflightstream.workspace.storage import ensure_sim_expanded

if TYPE_CHECKING:
    from pyflightstream.workspace.matrix import ResolvedMatrix


def _file_digest(path: str | Path) -> str | None:
    """Hash a file, or None when it cannot be read.

    None rather than a raise: a missing or unreadable solver executable
    is the executor's problem to report, and a provenance field must
    never be the thing that fails a run. That policy now lives in the
    FUNCTION that implements it, :func:`pyflightstream._digest.
    optional_file_sha256`, rather than in a comment beside a second
    copy of the same chunked read.
    """
    return optional_file_sha256(path)


def _recipe_digest(recipe: ScriptRecipe | None) -> str | None:
    """Hash the recipe function's source, or None when not introspectable.

    A recipe is USER CODE resolved by a dotted name, and it can be
    edited between two runs that record the same name. The name says
    which function; this says which version of it (PYFS-015). A lambda,
    a C-implemented callable or a function defined in a REPL has no
    retrievable source, and None there is honest.
    """
    if recipe is None:
        return None
    try:
        source = inspect.getsource(recipe)
    except (OSError, TypeError):
        return None
    return text_sha256(source)


@dataclass(frozen=True)
class Reconstruction:
    """Everything needed to re-run one recorded point (PYFS-015, NFR-07).

    Built by :func:`reconstruct` from a manifest record and the
    workspace it names. Every field is what the run ACTUALLY used, read
    back from the record rather than re-derived from today's code.

    Attributes
    ----------
    argv : tuple of str
        The command line, argument by argument.
    cwd : str
        Working directory the process ran in.
    timeout_s : float or None
        Wall-clock limit that was applied.
    script_text : str
        Text of the generated script, read from the workspace.
    verified : dict of str to str
        One entry per artifact whose recorded hash was checked against
        the file on disk today: the script, each recorded input (keyed
        ``inputs/<name>`` by its name in ``inputs_sha256``, and checked
        where the run read it, see :func:`reconstruct`), each collected
        output, and the solver executable. Three values, and
        the third exists because collapsing it into the second was
        wrong: ``"match"``, ``"differs"`` (the file is there and its
        bytes moved, so somebody edited a result), and ``"missing"``
        (the file cannot be read at all, so the evidence is gone and the
        answer is to restore it from ``archive/``). Those are different
        problems with different answers.
    fs_version_requested, fs_version_reported, fs_build : str or None
        Recorded target version, reported version and vendor build. Missing
        historical values remain None; they are not resolved from today's registry.
    package_version, package_commit : str or None
        Recorded package version and source revision.
    package_dirty : bool or None
        Recorded source-tree state, unknown for a wheel installation.
    solver_setup : dict or None
        Independent copy of the recorded solver-setup snapshot, or None when
        no snapshot was recorded. Mutating it does not change the manifest view.
    """

    argv: tuple[str, ...]
    cwd: str
    timeout_s: float | None
    script_text: str
    verified: dict[str, str]
    fs_version_requested: str | None = None
    fs_version_reported: str | None = None
    fs_build: str | None = None
    package_version: str | None = None
    package_commit: str | None = None
    package_dirty: bool | None = None
    solver_setup: dict | None = None

    @property
    def faithful(self) -> bool:
        """Whether every checked artifact still matches its recorded hash."""
        return all(state == "match" for state in self.verified.values())


def _record_by_id(workspace: CampaignWorkspace, run_id: str) -> RunRecord:
    """Find one manifest record by its run identity, or refuse by name."""
    records = workspace.read_manifest()
    for record in records:
        if record.run_id == run_id:
            return record
    known = ", ".join(sorted(entry.run_id for entry in records)) or "none"
    raise WorkspaceError(
        f"no run {run_id!r} in the manifest of {workspace.root}. Recorded runs: {known}"
    )


def _recorded_argv(record: RunRecord) -> tuple[str, ...]:
    """Read a usable invocation without inferring an executable from artifacts."""
    if not record.argv or not record.argv[0].strip():
        raise WorkspaceError(
            f"run {record.run_id!r} records argv={record.argv!r}; reconstruction "
            "requires a command line with a nonempty executable. Restore a record "
            "with the original invocation; matching artifact hashes cannot supply it."
        )
    return tuple(record.argv)


def reconstruct(run: RunRecord | str, *, workspace: CampaignWorkspace) -> Reconstruction:
    """Rebuild one recorded run's invocation from the manifest.

    The promise of NFR-07 is that the record plus the staged inputs
    reproduce the run. Until PYFS-015 the record held neither the
    command line, nor the working directory, nor the effective timeout,
    so "reproduce" meant re-deriving all three from executor code that
    may have changed in between. This reads them back instead.

    Parameters
    ----------
    run : RunRecord or str
        A manifest row, as :meth:`CampaignWorkspace.read_manifest`
        returns it, or the ``run_id`` of one. The id form exists so a
        caller can name the run they mean instead of reaching it by list
        position, which is what a reader of the manifest actually has.
    workspace : CampaignWorkspace
        The workspace the run belongs to. Keyword-only, so this cannot
        be confused with
        :func:`~pyflightstream.results.tables.parse_run_loads`, whose
        two positional arguments are the same pair in the other order.

    Returns
    -------
    Reconstruction
        The invocation, the script text, and a per-artifact verdict on
        whether the files still hash to what the record says. Each
        recorded input is checked where the run read it: at the path the
        script names for it, among the simulation's staged inputs, or in
        the folder the run ran in (the record's ``cwd``), where the run
        writes the files it parks beside the script (the trailing-edge node
        file, the actuator profile's copy, the unsteady action programs). It
        reads ``"missing"`` only when the file is not where the run read it.

    Raises
    ------
    WorkspaceError
        If no record carries the given ``run_id``, if the record was
        written under a manifest schema this version does not know, or
        carries no usable argv or script path, or the script is not where it says.
        Refusing beats reconstructing something that is not the run.
    """
    record = run if isinstance(run, RunRecord) else _record_by_id(workspace, run)
    if record.manifest_schema is None:
        # REV010-014. A row with no schema field predates it, and saying so
        # is different from naming a schema it never claimed. This branch
        # was unreachable while the field defaulted to the current value:
        # the legacy row simply asserted the current layout and walked
        # straight into a reconstruction of fields it does not have.
        raise WorkspaceError(
            f"run {record.run_id!r} carries no manifest schema, so it was written "
            "before the field existed and nothing in the row says which layout it "
            "follows. Reconstructing it would mean assuming the current one. Read "
            "it with the pyflightstream version that wrote it, or migrate the "
            "manifest deliberately."
        )
    if record.manifest_schema not in KNOWN_MANIFEST_SCHEMAS:
        # The set, not the current constant. Reconstruction asks which
        # fields the row has, and every stamp in the set describes a layout
        # THIS version can still read, so refusing an older one would make
        # a schema bump equivalent to deleting the manifests written before
        # it: nothing here migrates a manifest, so there is no route back
        # (PFS-2012.03). A stamp outside the set, older or newer, still
        # denies, which is the half the constant's own comment demands.
        raise WorkspaceError(
            f"run {record.run_id!r} was written under manifest schema "
            f"{record.manifest_schema!r} and this version knows "
            f"{', '.join(KNOWN_MANIFEST_SCHEMAS)}. Which fields exist, and what "
            "they mean, is what the schema names; guessing would reconstruct a run "
            "that never happened. Use the pyflightstream version that wrote the "
            "manifest."
        )
    argv = _recorded_argv(record)
    sim = workspace.sim_dir(record.sim_id)
    if not record.script_path:
        raise WorkspaceError(
            f"run {record.run_id!r} records no script path, so its script cannot "
            "be found. Without that field, the run "
            "is not reconstructable from the manifest alone."
        )
    # A simulation compacted by free-space is expanded in place before its script is read.
    ensure_sim_expanded(workspace, record.sim_id, reason="reconstruct")
    script = sim / record.script_path
    if not script.is_file():
        raise WorkspaceError(
            f"the script of run {record.run_id!r} is not at {script}. The record "
            "names it, so the simulation folder was cleaned or edited, or its archive "
            f"(sims/sim_{record.sim_id}.zip, or a copy under archive/) holds it; "
            "restore it before reconstructing."
        )

    def state(path: str | Path, recorded: str) -> str:
        digest = _file_digest(path)
        if digest is None:
            return "missing"
        return "match" if digest == recorded else "differs"

    script_text = script.read_text(encoding="utf-8")
    verified = {record.script_path: state(script, record.script_sha256)}
    # EACH INPUT WHERE THE RUN READ IT. Only the geometry is staged in the
    # simulation's inputs/; the trailing-edge node file, the actuator profile's
    # copy and the action programs are written in the folder the run ran in, and
    # a custom free stream is read where it lives. Looked for among the staged
    # inputs, every one of them read "missing", and a node file whose name the
    # input library also holds read "differs" against a file the run never read.
    work_dir = Path(record.cwd) if record.cwd else sim
    named = _paths_a_script_names(script_text, work_dir)
    outputs = [sim / name for name in record.outputs_sha256]
    for name, digest in record.inputs_sha256.items():
        where = _where_the_run_read(name, sim, work_dir, named, outputs)
        verified[f"inputs/{name}"] = state(where, digest)
    for name, digest in record.outputs_sha256.items():
        verified[name] = state(sim / name, digest)
    if record.fs_exe and record.fs_exe_sha256:
        verified[record.fs_exe] = state(record.fs_exe, record.fs_exe_sha256)
    return Reconstruction(
        argv=argv,
        cwd=record.cwd or str(sim),
        timeout_s=record.timeout_s,
        script_text=script_text,
        verified=verified,
        fs_version_requested=record.fs_version_requested,
        fs_version_reported=record.fs_version_reported,
        fs_build=record.fs_build,
        package_version=record.package_version,
        package_commit=record.package_commit,
        package_dirty=record.package_dirty,
        solver_setup=copy.deepcopy(record.solver_setup),
    )


def _paths_a_script_names(script_text: str, work_dir: Path) -> list[Path]:
    """Return every path a script names on a line of its own, as the solver resolves it.

    A command that reads a file names it on the line after the command, by
    absolute path; a relative one is resolved against the folder
    the run ran in, as the solver resolves it. A line holding whitespace is a
    command with its arguments unless it is an absolute path.
    """
    named: list[Path] = []
    for line in script_text.splitlines():
        text = line.strip()
        if not text:
            continue
        path = Path(text)
        if path.is_absolute():
            named.append(path)
        elif not any(character.isspace() for character in text):
            named.append(work_dir / path)
    return named


def _where_the_run_read(
    name: str,
    sim: Path,
    work_dir: Path,
    named: Sequence[Path],
    outputs: Sequence[Path] = (),
) -> Path:
    """Return where a run read one input its record hashes, for :func:`reconstruct`.

    In this order:

    1. A path the script names that ends in the input's name is where the
       solver read it: a custom free stream where it lives, the node file and
       the actuator profile's copy in the folder the run ran in. When that
       path is this simulation's own staged input
       (``sim_<id>/inputs/<name>``), it is checked in this
       workspace's staged inputs, which a moved workspace still holds; else
       the first such path that holds a file, else the first, which reads
       "missing". A staged input of the same name is never substituted for it.
    2. An input the script does not name is the staged one when the staged
       inputs hold it (a recipe that never names its geometry), else the file
       the run wrote beside the script in the folder it ran in: the action
       programs and the clock. A key with a folder part is relative to the
       simulation folder (a continuation's inherited probe layout,
       ``profiles/<sim>_probe_points.csv``) and is read there when it holds
       it (PFS-2103.027).
    """
    wanted = Path(name).parts
    staged = sim / "inputs" / name
    by_script = [path for path in named if path.parts[-len(wanted) :] == wanted]
    for path in by_script:
        if path.parts[-len(wanted) - 2 : -len(wanted)] == (sim.name, "inputs"):
            return staged
    for path in by_script:
        if path.is_file():
            return path
    if by_script:
        return by_script[0]
    if staged.is_file():
        return staged
    if len(wanted) > 1 and (sim / name).is_file():
        return sim / name
    beside = work_dir / name
    if any(
        os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(beside))
        for path in outputs
    ):
        # A file the run WROTE under this name is not the input it read (F-611): the
        # input is missing, and reads missing in the staged inputs.
        return staged
    return beside


@lru_cache(maxsize=1)
def package_vcs_state() -> tuple[str | None, bool | None]:
    """Return the commit this package's code came from, and whether it is dirty.

    PYFS-017. ``package_version`` reads the installed distribution's
    metadata, a static string in ``pyproject.toml``. Git identity distinguishes
    a development tree from the release named by that metadata.

    Two of the three clauses that finding asks for are a versioning
    scheme change (a dev version carrying the sha, and a guard refusing
    a final version string off a tag), which is a release-mechanics
    decision for the owning seat and is registered rather than taken. This
    is the third: the manifest says which commit ran and whether the
    tree was clean, which is the part that needs no decision because it
    adds evidence without changing what anything claims.

    Returns
    -------
    tuple of (str or None, bool or None)
        Commit sha and dirty flag, or ``(None, None)`` when the package
        did not come from a git work tree. A known commit with ``None`` for
        the flag means ``git status`` failed. None means "not knowable
        here" rather than "clean": a wheel install has no repository to
        ask, and inventing an answer is the failure this pair exists to
        prevent.

    Notes
    -----
    The package directory must be TRACKED, not merely inside a work
    tree. A wheel installed into a virtualenv that happens to sit
    inside the repository is not this repository's code, and reporting
    the repository's HEAD for it would be a confident wrong answer.
    """
    package_dir = Path(pyflightstream.__file__).resolve().parent

    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=package_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                # Explicit, and identical to the inherited default. git needs
                # the ambient environment to find its own installation and the
                # user's configuration, so narrowing it here would change what
                # this function reports rather than harden it.
                env=os.environ.copy(),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    if git("ls-files", "--error-unmatch", "__init__.py") is None:
        return None, None
    commit = git("rev-parse", "HEAD")
    if commit is None:
        return None, None
    status = git("status", "--porcelain")
    return commit, None if status is None else bool(status)


_IDENTITY_MARKER = "PYFS_PREFLIGHT"


# UNANCHORED ON PURPOSE: 26.125 prints "Simcenter Flightstream 2612, build #10052026", not
# "FlightStream version"; no line matching "build <digits>" precedes the banner in any startup
# log of 26.120, 26.124 or 26.125 (L4, X-F-0403, namespace 63503b6a, X-F-0403/analysis.json).
_BUILD_LINE = re.compile(r"build\s*#?\s*(?P<build>\d+)", re.IGNORECASE)


#: The command-line flag that accepts an installed build other than the registered
#: one, named once so the refusal, the warning and the parser agree.
ACCEPT_UNREGISTERED_BUILD_FLAG = "--accept-unregistered-build"


def check_solver_identity(
    executor: Executor,
    version: FsVersion,
    workdir: Path,
    *,
    timeout_s: float = 60.0,
    accept_unregistered_build: bool = False,
    accepted_by: str | None = None,
) -> None:
    """Refuse before the campaign runs if the wrong solver build is configured.

    The build-time refusal of an ambiguous vendor name settles which
    build a campaign ASKED for; it cannot show which one is installed at
    ``fs_exe``, and the version string the solver prints cannot either,
    because every registered 26.1x prints the same one. This runs the
    cheapest possible script (a PRINT sentinel, a log export, and close)
    and reads the build number out of the exported log, so a campaign
    pointed at the wrong installation stops before its first point
    instead of after its last.

    Layered rather than sole: a mismatch is refused HERE, on positive
    evidence, and every parsed result is still cross-checked against the
    registered build afterwards. So an identity this cannot read
    degrades to the parse-time check rather than to nothing, which is
    why the unreadable case warns instead of refusing. Refusing there
    would make the guard's own failure mode "no campaign runs at all".

    Does nothing at all when the version has no registered build: there
    is nothing to compare, so no solver process is spent.

    On a machine that cannot export the log (an executor whose HPC profile
    states ``export_log = false``) the sentinel script exports none and
    the build is read from what the solver printed; a build it did not print
    is warned about, naming the profile, and never refused.

    Parameters
    ----------
    executor : Executor
        The executor the campaign will use, so the check exercises the
        same executable.
    version : FsVersion
        Version the campaign declares.
    workdir : Path
        Scratch directory for the sentinel script and its log.
    timeout_s : float, keyword-only
        Wall-clock limit for the sentinel run, in seconds.
    accept_unregistered_build : bool, keyword-only
        With True, an installed build other than the registered one is
        warned about and accepted instead of refused. Default False.
    accepted_by : str, keyword-only, optional
        The file that stated the acceptance (FR-998): ``pyfs.toml``,
        ``pyfs.local.toml`` or ``executables.local.toml`` (a build entry of
        ``inputs/executables.local.toml``), which the warning names; None
        where the command line typed it. Default None.

    Raises
    ------
    ExecutorConfigurationError
        When the exported log names a build that is not the registered
        build of ``version``.

    Warns
    -----
    VersionMismatchWarning
        When the log carries no readable build number, so the installed
        build could be confirmed neither right nor wrong.
    """
    if version.build is None:
        return
    # RESOLVED FIRST, and this is the boundary with the worst failure of
    # the four. `log_path` below becomes SCRIPT TEXT, in an EXPORT_LOG,
    # and the solver runs with its working directory set to `workdir`.
    # Spelled relatively, the solver writes the log one level too deep,
    # this function finds no log, reads no build number, and takes the
    # WARN branch instead of raising: a campaign pointed at the wrong
    # installation proceeds, and the warning blames the solver for
    # "could not read a build number" when the cause was our own path.
    # A guard that reads its own missing evidence as permission is not a
    # guard. The same shape was measured against a real 26.120 export in
    # qa.probes, where it failed silently for exactly this reason.
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    log_path = workdir / "preflight_log.txt"
    if log_path.exists():
        log_path.unlink()
    # A MACHINE THAT ABORTS AT EXPORT_LOG IS NOT ASKED TO EXPORT ONE HERE
    # EITHER. Its HPC profile says so (`export_log = false`), and the build is
    # read from what the solver printed instead; a build it did not print is a
    # warning naming the profile, never a refusal.
    exports_log = _machine_exports_log(executor)
    script = Script(version)
    script.comment("pre-flight: which FlightStream build is actually installed")
    script.emit("PRINT", _IDENTITY_MARKER)
    if exports_log:
        script.emit("EXPORT_LOG", log_path)
    script.emit("CLOSE_FLIGHTSTREAM")
    script_path = workdir / "preflight.txt"
    _textio.write_text(script_path, script.render())
    result = executor.run_script(script_path, working_dir=workdir, timeout_s=timeout_s)

    if log_path.exists():
        # Real 26.120 hidden-mode exports carry NUL bytes (RPT-001).
        text = log_path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    else:
        text = "" if exports_log else result.captured_output().replace("\x00", "")
    found = _BUILD_LINE.search(text)
    if found is None and not exports_log:
        warnings.warn(
            "this machine's HPC profile (inputs/hpc/) states [log] export_log = false, so the "
            "identity pre-flight exported no log, and the solver printed no build number "
            "either: the installation at the campaign's executable was neither confirmed nor "
            f"refused as {version.canonical} (build #{version.build}). Every parsed result is "
            "still cross-checked against the registered build.",
            VersionMismatchWarning,
            stacklevel=2,
        )
        return
    if found is None:
        # THE CAUSE IS NAMED WHEN IT IS KNOWN. The result of the run was
        # discarded here, so a solver that failed to start, or one killed
        # by the timeout, produced the same sentence as a solver that ran
        # perfectly and printed nothing: "could not read a build number
        # from the solver". That is the misattribution this function's
        # own path fix was about, one line further on, and the timeout
        # case is one the operator can act on by raising timeout_s.
        # PFS-2094.012: what the run said comes from ExecutionResult.diagnosis,
        # the single home, which reads stdout too.
        if result.timed_out:
            cause = (
                f"the pre-flight run {result.diagnosis()}, so no build number could be "
                "read; raise timeout_s if this installation is simply slow to start"
            )
        elif result.failed:
            cause = (
                f"the pre-flight run {result.diagnosis()} and wrote no readable log, so no "
                "build number could be read"
            )
        else:
            cause = "the pre-flight could not read a build number from the solver"
        warnings.warn(
            f"{cause}, so the "
            f"installation at the campaign's executable was neither confirmed nor "
            f"refused as {version.canonical} (build #{version.build}). Every parsed "
            "result is still cross-checked against the registered build.",
            VersionMismatchWarning,
            stacklevel=2,
        )
        return
    installed = found.group("build")
    if installed != version.build:
        # A build that EXISTS and is
        # not the registered one may be accepted on request, and then its
        # compatibility is the user's responsibility. It is warned, and every
        # record of the run says the acceptance was made.
        if accept_unregistered_build:
            warnings.warn(
                f"the executable is FlightStream build #{installed} and the campaign "
                f"declares {version.canonical}, registered as build #{version.build}. "
                f"Running anyway, because {_acceptance_reason(accepted_by)}",
                VersionMismatchWarning,
                stacklevel=2,
            )
            return
        raise ExecutorConfigurationError(
            f"the executable is FlightStream build #{installed}, but the campaign "
            f"declares {version.canonical}, which is build #{version.build}. Nothing "
            "ran. The printed version string cannot show this, because both builds of "
            "a minor release print the same one, and their records differ; check "
            "fs_exe against the installation folder of the version the campaign names. "
            f"If this build is one you know to be compatible, run with "
            f"{ACCEPT_UNREGISTERED_BUILD_FLAG} (accept_unregistered_build=True): its "
            "compatibility is then your responsibility, and the records say so."
        )


def _acceptance_reason(accepted_by: str | None) -> str:
    """Say why an installed build other than the registered one runs, naming who stated it."""
    if accepted_by is None:
        return (
            f"{ACCEPT_UNREGISTERED_BUILD_FLAG} was given: whether this build computes what "
            "the registered one does is yours to know, and every record of this run says the "
            "flag was used."
        )
    return (
        f"{accepted_by} sets accept_unregistered_build: whether this build computes what the "
        "registered one does is yours to know, and every record of this run says so and "
        f"names {accepted_by}."
    )


def acceptance_of(
    key: str, accept_unregistered_build: bool, accepted_builds: Collection[str]
) -> tuple[bool, str | None]:
    """Return whether one installation's build is accepted, and the file that said so.

    FR-998: the acceptance is stated by the command line, by a workspace
    settings file, or by the build's own entry in
    ``inputs/executables.local.toml``; either route accepts, and the entry
    accepts its own build only.

    Parameters
    ----------
    key : str
        The installation, as the identity check groups cases: a build id, or
        the empty string for the campaign's own installation.
    accept_unregistered_build : bool
        The acceptance of the whole invocation, typed or taken from a file.
    accepted_builds : collection of str
        The installations whose own entry accepts their build.

    Returns
    -------
    tuple of bool and (str or None)
        Whether the build is accepted, and the file that stated it: None
        where the command line did, or where nothing accepts.
    """
    if accept_unregistered_build:
        return True, invocation_sources().get("accept_unregistered_build")
    if key in accepted_builds:
        return True, ENTRY_ACCEPTANCE_SOURCE
    return False, None


def _effective_build_contract(campaign, versions, accepted, accepted_builds, row_builds=None):
    """Record resolved installation keys and effective acceptance, regardless of input source."""
    keys = row_builds if row_builds is not None else [case.fs_build for case in campaign.sims]
    return {
        case.sim_id: {
            "build": key or resolve(campaign.fs_version).canonical,
            "version": resolve((versions or {}).get(case.sim_id, campaign.fs_version)).canonical,
            "accepted": bool(accepted or (key or "") in accepted_builds),
        }
        for case, key in zip(campaign.sims, keys, strict=True)
    }


def entry_accepted_builds(
    resolved: ResolvedMatrix,
    workspace: CampaignWorkspace,
    default: str | None,
    fs_exe: str | Path | None,
) -> frozenset[str]:
    """Return the installations whose own build entry accepts their installed build (FR-998).

    Read off the registry entries the bound matrix resolved, for the
    installations its rows use once the selection narrowed them (an entry no
    selected row runs on accepts nothing); the campaign's own installation,
    the key ``""``, is the entry of the default version, asked only where a
    row names no build. An explicit executable override names no
    entry, so it accepts nothing, and a command line that typed
    ``--no-accept-unregistered-build`` lets no entry accept.

    Parameters
    ----------
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
        The bound matrix.
    workspace : CampaignWorkspace
        The campaign workspace, whose registry holds the default's entry.
    default : str or None
        The campaign default version, the build id a silent row falls back to.
    fs_exe : str or Path or None
        The explicit executable override, when one was given.

    Returns
    -------
    frozenset of str
        The accepted installations, keyed as :func:`acceptance_of` reads them.
    """
    if fs_exe is not None or not entry_acceptance_allowed():
        return frozenset()
    # Only the installations the selected rows run on (R7, R8): a narrowed run
    # never states the acceptance of a build none of its rows uses.
    used = {build for build in resolved.row_builds if build}
    keys = {
        build
        for build, entry in resolved.builds.items()
        if build in used and entry.accept_unregistered_build
    }
    fallback = (default or "").strip()
    if fallback and any(build is None for build in resolved.row_builds):
        if resolve_build(workspace.inputs_dir, fallback).accept_unregistered_build:
            keys.add("")
    return frozenset(keys)


def _case_build(
    case: SimCase,
    builds: Mapping[str, SolverBuild] | None,
) -> SolverBuild | None:
    """Return the build a case names, or None for the campaign's own.

    Refuses a case naming a build the caller did not supply, rather
    than falling back to the campaign's executable. The fallback is
    what makes a record lie: the point would run on one installation
    and the manifest would name another, which is the exact failure the
    run matrix's single-build refusal existed to prevent.

    Parameters
    ----------
    case : SimCase
        The case about to be planned or run.
    builds : mapping of str to SolverBuild, optional
        What the caller supplied.

    Returns
    -------
    SolverBuild or None
        None means the campaign's own ``fs_exe`` and ``fs_version``.

    Raises
    ------
    ExecutorConfigurationError
        When the case names a build the mapping does not carry.
    """
    if case.fs_build is None:
        return None
    if builds and case.fs_build in builds:
        return builds[case.fs_build]
    known = ", ".join(sorted(builds)) if builds else "none"
    raise ExecutorConfigurationError(
        f"case {case.sim_id!r} declares fs_build {case.fs_build!r} and the builds "
        f"mapping carries {known}. Nothing ran. A case naming a build is asking to "
        "run on a DIFFERENT installation from the campaign's, so falling back to "
        "campaign.fs_exe would record every point against an executable it never "
        "used. Pass builds={<id>: SolverBuild(fs_exe=..., fs_version=..., "
        "executor=...)} covering every fs_build the campaign names, or clear the "
        "field to run the case on the campaign's own installation."
    )


def _build_groups(campaign: Campaign) -> dict[str, list[str]]:
    """Group a campaign's cases by the installation each one runs on.

    The key is :attr:`~pyflightstream.cases.SimCase.fs_build`, verbatim
    and in first-appearance order, with the EMPTY STRING standing for
    the campaign's own installation. The empty key is the same one the
    campaign loop already uses internally to key its pre-flight, so the
    grouping a reader sees and the grouping the loop spends are one
    thing rather than two that can disagree.

    Parameters
    ----------
    campaign : Campaign
        What is about to be planned or run.

    Returns
    -------
    dict of str to list of str
        Build id to the ``sim_id`` values naming it, in the order the
        campaign declares them.
    """
    groups: dict[str, list[str]] = {}
    for case in campaign.sims:
        groups.setdefault(case.fs_build or "", []).append(case.sim_id)
    return groups


def _build_label(key: str) -> str:
    """Name one grouping key the way a message should say it."""
    return f"build {key!r}" if key else "the campaign's own installation"


def _plan_bindings(
    campaign: Campaign, workspace: CampaignWorkspace, matrix_path: str | Path | None
) -> dict[str, dict[str, Any]]:
    """Return the instrument and the inputs a matrix plan measured (NL-EXEC-1, FR-1556).

    ``instrument`` holds, per build of :func:`_build_groups` (the empty key
    for the campaign's own), the executable and its SHA-256; the plan
    launches no solver, so the file is the build it can observe, and a
    digest of None says the file was not there to read. A row build the
    registry does not resolve is left out, as the plan refuses that row.
    ``inputs_sha256`` holds the SHA-256 of every geometry file a case opens.
    A campaign authored in Python has no plan receipt and records neither.
    """
    if not matrix_path:
        return {}
    executables: dict[str, str | Path] = {"": campaign.fs_exe}
    for key in _build_groups(campaign):
        try:
            executables[key] = (
                executables.get(key) or resolve_build(workspace.inputs_dir, key).fs_exe
            )
        except (InputArtifactError, OSError):
            continue
    inputs = {
        case.geometry: file_sha256(case.geometry)
        for case in campaign.sims
        if case.geometry and Path(case.geometry).is_file()
    }
    return {
        "instrument": {
            key: {"fs_exe": str(path), "fs_exe_sha256": _file_digest(path)}
            for key, path in executables.items()
        },
        "inputs_sha256": inputs,
    }


def _instrument_or_inputs_changed(
    payload: Mapping[str, Any], plan_file: Path, fs_exe: str | Path | None
) -> str | None:
    """Return why the instrument or an input differs from what the plan measured, or None.

    NL-EXEC-1, FR-1556. A plan written before the plan recorded them carries
    neither table and constrains nothing here; an executable the plan found
    absent (digest None) is not compared.
    """
    instrument = payload.get("instrument") or {}
    own = instrument.get("") or {}
    if fs_exe is not None and own.get("fs_exe"):
        if Path(own["fs_exe"]).resolve() != Path(fs_exe).resolve():
            return (
                f"the run names the executable {fs_exe} and the plan at {plan_file} measured "
                f"{own['fs_exe']}; a plan of one instrument is not a plan for another. Plan "
                "it again with the same executable."
            )
    for key, observed in instrument.items():
        planned, current = observed.get("fs_exe_sha256"), _file_digest(observed["fs_exe"])
        if planned is not None and planned != current:
            return (
                f"the executable of {_build_label(key)}, {observed['fs_exe']}, changed since it "
                f"was planned: the plan at {plan_file} measured {planned[:12]} and it is "
                f"{str(current)[:12]} now. Plan it again on the installed build."
            )
    for path, planned in (payload.get("inputs_sha256") or {}).items():
        if planned != (current := _file_digest(path)):
            return (
                f"the input {path} changed since it was planned: the plan at {plan_file} "
                f"measured {planned[:12]} and it is {str(current)[:12]} now. Plan it again; "
                "a plan of other inputs is not a plan for these."
            )
    return None


def _check_scheduled_builds(
    campaign: Campaign,
    executor: Executor,
    scheduled: list[tuple[SimCase, SolverBuild | None]],
    *,
    accept_unregistered_build: bool = False,
    accepted_builds: Collection[str] = (),
) -> None:
    """Confirm every installation that still has work, before any of it runs.

    Check every build before the first point executes, using one process per
    installation. A misconfigured build must be refused before another build
    consumes licensed solver time (PFS-2009.09.02).

    THE LAZINESS IS KEPT, which is the constraint that makes this
    subtle. Only builds with points still PENDING are asked, so a resume
    with nothing left to do still launches no solver process at all, and
    a build all of whose points are recorded is not probed either. The
    naive fix, probing every declared build up front, closes one spend
    by opening another in exactly the case that spends nothing today.

    Parameters
    ----------
    campaign : Campaign
        The campaign being run; its own version answers for cases
        naming no build.
    executor : Executor
        The campaign's own executor, likewise.
    scheduled : list of (SimCase, SolverBuild or None)
        The cases that have at least one point left to run, paired with
        the build each resolved to.
    accept_unregistered_build : bool, keyword-only
        With True, an installed build other than the registered one is
        warned about and accepted instead of refused. Default False.
    accepted_builds : collection of str, keyword-only
        The installations whose own entry of ``inputs/executables.local.toml``
        accepts their build (FR-998), keyed as the cases are grouped; each
        accepts that build only. Default empty.

    Raises
    ------
    ExecutorConfigurationError
        When any installation reports a build other than the one the
        campaign asked for. ONE refusal naming every failing build and
        the cases that asked for it, rather than the first one found.
    """
    groups: dict[str, tuple[Executor, str, list[str]]] = {}
    for case, build in scheduled:
        key = case.fs_build or ""
        if key not in groups:
            groups[key] = (
                build.executor if build is not None else executor,
                build.fs_version if build is not None else campaign.fs_version,
                [],
            )
        groups[key][2].append(case.sim_id)
    failures: list[str] = []
    for key, (case_executor, case_version, sims) in groups.items():
        # FR-99. A SUBMITTING EXECUTOR HAS NO SOLVER TO ASK. The identity
        # check runs a small script and reads the build back, which is a
        # question about the executable ON THIS MACHINE; a cluster's solver
        # is on the cluster, and asking would submit a probe job to a queue
        # to answer a question the descriptor states. WHAT IT STATES IS A
        # NAME, NOT A GUARANTEE: on a real cluster the descriptor carries the
        # scheduler's family name (`26.1`), which covers more than one build,
        # and the profile's [builds] table only DECLARES which build that
        # name means (PFS-2010.01.06). So a submitted point is NOT guarded
        # here; which build it ran on is known only from the build number in
        # its collected log.
        from pyflightstream.run._executors import submits_jobs

        if submits_jobs(case_executor):
            continue
        workdir = Path(tempfile.mkdtemp(prefix="pyfs-preflight-"))
        accepted, accepted_by = acceptance_of(key, accept_unregistered_build, accepted_builds)
        try:
            check_solver_identity(
                case_executor,
                resolve(case_version),
                workdir,
                accept_unregistered_build=accepted,
                accepted_by=accepted_by,
            )
        except ExecutorConfigurationError as error:
            failures.append(
                f"  {_build_label(key)}, asked for by case(s) {', '.join(sims)}: {error}"
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    if failures:
        raise ExecutorConfigurationError(
            f"the identity pre-flight refused {len(failures)} of {len(groups)} solver "
            "installation(s) this campaign still has work for. NOTHING ran and no "
            "point was recorded:\n" + "\n".join(failures) + "\nEvery installation with "
            "work left is confirmed before the first point of ANY of them executes, so "
            "a misconfigured build cannot spend the licensed seats of a healthy one "
            "first. Fix the executable each case above points at, or drop those cases "
            "from this run."
        )
