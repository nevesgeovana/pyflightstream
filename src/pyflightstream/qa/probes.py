"""Tier 2 command-validity probes (SAD Section 11).

Pipeline role: produces the run evidence behind the command database.
Each probe executes exactly one database command in a minimal script on
a licensed machine and classifies it from three failure signals:

1. Sentinel missing: the log exported after the command never appears,
   so script processing aborted at the command.
2. Log error patterns: error messages between the probe sentinels.
3. Failed effect assertion: the script continued past the command but
   its observable effect is absent. A command that runs but does
   nothing is ``broken``, not ``verified``.

The generated scripts wrap the target command between two sentinel
``PRINT`` markers, each followed by an ``EXPORT_LOG``, so the exported
log carries a delimited region that belongs to the target command
alone. The harness therefore relies on three instrument commands
(PRINT, EXPORT_LOG, CLOSE_FLIGHTSTREAM); a baseline probe validates
them before any command is judged, and a baseline failure aborts the
whole run instead of writing false evidence (a dead license must never
read as broken commands).

Statuses are promoted from the resulting compat report only through
``pyfs-qa apply-compat`` (:mod:`pyflightstream.qa.compat`), never by
hand (CLAUDE.md invariant 3).
"""

from __future__ import annotations

import enum
import hashlib
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyflightstream
from pyflightstream.commands import CommandRegistry
from pyflightstream.run import ExecutionResult, Executor, LocalExecutor
from pyflightstream.script import Script
from pyflightstream.script.helpers import initialize_solver
from pyflightstream.versions import FsVersion, resolve

_BEGIN = "PYFS_PROBE_BEGIN"
_END = "PYFS_PROBE_END"
_BASELINE_MARKER = "PYFS_BASELINE_ALIVE"
_LOG_BEFORE = "log_before.txt"
_LOG_AFTER = "log_after.txt"
_LOG_FINAL = "log_final.txt"
_DUMP_BEFORE = "dump_before.txt"
_DUMP_AFTER = "dump_after.txt"
_SCRIPT_NAME = "probe_script.txt"
_BASELINE_DIR = "_baseline"

#: Conservative error patterns, scanned only between the probe
#: sentinels so startup noise never blames the target command. The
#: list grows on real-log evidence, like every other probe input.
DEFAULT_ERROR_PATTERNS: tuple[str, ...] = (
    r"(?i)\berror\b",
    r"(?i)\bunable\b",
    r"(?i)\bfailed\b",
    r"(?i)\binvalid\b",
    r"(?i)not recognized",
)


class ProbeOutcome(enum.StrEnum):
    """Judgment of one probe.

    ``verified`` and ``broken`` are promotable evidence; ``unprobed``
    records why no judgment exists (no probe specification yet, not in
    this run's subset, or an inconclusive execution such as a timeout).
    """

    VERIFIED = "verified"
    BROKEN = "broken"
    UNPROBED = "unprobed"


class Requires(enum.StrEnum):
    """Session state a probe needs before its sentinels (prelude tier).

    ``none`` runs on the empty session; ``sim`` opens a local
    simulation file (explicit input, never committed); ``solver`` adds
    the minimal solver setup and INITIALIZE_SOLVER; ``solution`` adds
    a short START_SOLVER run. Each tier used by a run is validated by
    its own baseline first, so a broken prelude downgrades its probes
    to unprobed instead of blaming the target commands.
    """

    NONE = "none"
    SIM = "sim"
    SOLVER = "solver"
    SOLUTION = "solution"


class ProbeEnvironmentError(RuntimeError):
    """The probe environment is unusable, so no command was judged.

    Raised when the baseline probe fails (solver not starting, license
    checkout failure, log export not landing) or when a probe working
    directory cannot be prepared safely. Environment failures abort the
    run because recording them as broken commands would be false
    evidence.
    """


@dataclass(frozen=True)
class ProbeArtifacts:
    """Everything a probe left behind, handed to the effect assertion.

    Attributes
    ----------
    workdir : Path
        Working directory of this probe; support files and any solver
        outputs land here.
    log_before : str or None
        Log exported after the BEGIN sentinel and before the target
        command; None when the file never appeared.
    log_after : str or None
        Log exported right after the END sentinel and before the
        epilogue; None when the file never appeared (script aborted at
        the target, or halted by design). Exporting it before the
        epilogue keeps abort attribution clean: an epilogue instrument
        that aborts can never be blamed on the target.
    begin_marker, end_marker : str
        The sentinel texts delimiting the target command's log region.
    execution : ExecutionResult
        Typed outcome of the solver process.
    """

    workdir: Path
    log_before: str | None
    log_after: str | None
    begin_marker: str
    end_marker: str
    execution: ExecutionResult

    def log_final(self) -> str | None:
        """Return the log exported after the epilogue, if any."""
        return _read_log(self.workdir / _LOG_FINAL)

    def dump_before(self) -> str | None:
        """Return the settings dump taken before the target, if any."""
        return _read_log(self.workdir / _DUMP_BEFORE)

    def dump_after(self) -> str | None:
        """Return the settings dump taken after the target, if any."""
        return _read_log(self.workdir / _DUMP_AFTER)

    def target_region(self) -> str:
        """Return the log lines belonging to the target command alone.

        The region runs from the last line carrying the BEGIN marker to
        the first later line carrying the END marker, both exclusive,
        in the log exported after the command. Empty when that log or
        the BEGIN marker is missing.
        """
        if self.log_after is None:
            return ""
        lines = self.log_after.splitlines()
        start = None
        for index, line in enumerate(lines):
            if self.begin_marker in line:
                start = index
        if start is None:
            return ""
        for index in range(start + 1, len(lines)):
            if self.end_marker in lines[index]:
                return "\n".join(lines[start + 1 : index])
        return "\n".join(lines[start + 1 :])


def printed_line(text: str, marker: str) -> bool:
    """Return whether ``marker`` was printed as a log message.

    A line that carries ``PRINT <marker>`` is the script command being
    echoed, not the message itself, and does not count; this keeps the
    check honest on solvers that echo script lines into the log.

    Parameters
    ----------
    text : str
        Log text to scan.
    marker : str
        Exact marker text the probe printed.

    Returns
    -------
    bool
        True when a genuine message line carries the marker.
    """
    for line in text.splitlines():
        if marker in line and f"PRINT {marker}" not in line:
            return True
    return False


@dataclass(frozen=True)
class ProbeSpec:
    """How to probe one command: emission, and the observable effect.

    Attributes
    ----------
    command : str
        Database name of the target command.
    build_target : callable
        ``build_target(script, workdir)`` emits the target command
        (validated emission, never ``raw()``) and may write support
        files into ``workdir``.
    assert_effect : callable, optional
        ``assert_effect(artifacts) -> bool | None`` checks the
        observable effect: True verifies, False breaks (a command that
        runs but does nothing is broken, not verified, SAD Section
        11), None records unprobed because the current instruments
        cannot observe the effect; a probe may never guess. Mandatory
        unless ``expects_halt``.
    expects_halt : bool
        The command is expected to halt script processing (STOP); the
        halt itself is the asserted effect, so the sentinel logic
        inverts: the log before the command must exist and the one
        after it must never appear.
    requires : Requires
        Prelude tier emitted before the sentinels; see
        :class:`Requires`. Tiers above ``none`` need the local
        simulation file passed to :func:`probe_version` as ``fsm``.
    early_prelude : callable, optional
        ``early_prelude(script, workdir)`` emits setup-phase support
        right after OPEN (before the rest of the tier prelude), for
        objects that must exist before solver initialization, such as
        a named coordinate system a later-phase target cites.
    prelude : callable, optional
        ``prelude(script, workdir)`` emits spec-specific setup after
        the tier prelude and before the sentinels (for example the
        object a setter manipulates), so a broken support command is
        never blamed on the target.
    epilogue : callable, optional
        ``epilogue(script, workdir)`` emits effect instruments after
        the END sentinel (for example an export whose file the effect
        assertion reads); its log lines land outside the target
        region, so instrument errors are not blamed on the target.
    dump_state : bool
        Bracket the target with OUTPUT_SETTINGS_AND_STATUS dumps
        (``dump_before.txt`` and ``dump_after.txt``) for
        state-difference effect assertions.
    effect_note : str
        One sentence naming the asserted effect; quoted in the compat
        report evidence line.
    timeout_s : float, optional
        Per-probe override of the run timeout; halting probes use a
        short one because the hidden solver may idle after the halt.
    """

    command: str
    build_target: Callable[[Script, Path], None]
    assert_effect: Callable[[ProbeArtifacts], bool | None] | None = None
    expects_halt: bool = False
    requires: Requires = Requires.NONE
    early_prelude: Callable[[Script, Path], None] | None = None
    prelude: Callable[[Script, Path], None] | None = None
    epilogue: Callable[[Script, Path], None] | None = None
    dump_state: bool = False
    effect_note: str = ""
    timeout_s: float | None = None

    def __post_init__(self) -> None:
        """Reject a probe that could not distinguish broken from verified."""
        if not self.expects_halt and self.assert_effect is None:
            raise ValueError(
                f"probe for {self.command} declares no effect assertion; a command that "
                "runs but does nothing is broken, not verified (SAD Section 11), so "
                "every probe must assert an observable effect"
            )


@dataclass(frozen=True)
class ProbeResult:
    """Evidence line of one command in one probe run.

    Attributes
    ----------
    command : str
        Database name of the probed command.
    outcome : ProbeOutcome
        The judgment; see :class:`ProbeOutcome`.
    detail : str
        Human-readable evidence sentence behind the judgment.
    sentinel_before, sentinel_after : bool
        Whether each sentinel marker was found printed in its exported
        log; the pair discriminates "aborted at the command" from
        "never ran".
    effect : bool or None
        Effect assertion result; None when it never ran.
    log_errors : tuple of str
        Error lines matched between the sentinels, verbatim.
    wall_time_s : float or None
        Wall-clock time of the solver process, seconds.
    return_code : int or None
        Solver process return code; None when killed on timeout.
    script_sha256 : str or None
        Hash of the generated probe script, for reproducibility.
    """

    command: str
    outcome: ProbeOutcome
    detail: str
    sentinel_before: bool = False
    sentinel_after: bool = False
    effect: bool | None = None
    log_errors: tuple[str, ...] = ()
    wall_time_s: float | None = None
    return_code: int | None = None
    script_sha256: str | None = None


@dataclass(frozen=True)
class ProbeRun:
    """One whole probe run: version, environment identity, evidence.

    Attributes
    ----------
    version : str
        Canonical FlightStream version the run targeted.
    solver_identity : tuple of str
        Verbatim log lines naming the solver version and build, taken
        from the baseline probe (FR-18: the printed version string may
        not discriminate hotfix builds; the build number does).
    fs_exe_name : str
        File name of the executable that ran (never the local path;
        executables live outside Git).
    package_version : str
        pyflightstream version that generated the probes.
    results : tuple of ProbeResult
        One evidence line per database command of this version.
    """

    version: str
    solver_identity: tuple[str, ...]
    fs_exe_name: str
    package_version: str
    results: tuple[ProbeResult, ...]

    def outcome_counts(self) -> dict[str, int]:
        """Return how many commands landed in each outcome."""
        counts = {outcome.value: 0 for outcome in ProbeOutcome}
        for result in self.results:
            counts[result.outcome.value] += 1
        return counts


def file_effect(name: str) -> Callable[[ProbeArtifacts], bool]:
    """Make an effect assertion: the command produced a non-empty file.

    Strict on absence: an export that runs without error and writes
    nothing is broken, not verified.

    Parameters
    ----------
    name : str
        File name relative to the probe working directory.
    """

    def check(artifacts: ProbeArtifacts) -> bool:
        path = artifacts.workdir / name
        return path.is_file() and path.stat().st_size > 0

    return check


def dump_gained(token: str, strict: bool = False) -> Callable[[ProbeArtifacts], bool | None]:
    """Make an effect assertion: a distinctive token entered the state dump.

    The token is a value only the probe would set (for example
    ``7.2531``), searched in the OUTPUT_SETTINGS_AND_STATUS dump taken
    after the target (``dump_state`` probes). Absence means None
    (unobservable, unprobed) unless ``strict``, for settings the dump
    is known to expose, where absence is a real no-op (broken).

    Parameters
    ----------
    token : str
        Distinctive text expected in the dump after the command.
    strict : bool
        Whether absence breaks instead of recording unprobed.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        after = artifacts.dump_after()
        if after is None:
            return False if strict else None
        if token in after:
            return True
        return False if strict else None

    return check


def dump_changed() -> Callable[[ProbeArtifacts], bool | None]:
    """Make an effect assertion: the state dump differs after the target.

    A difference proves the command acted; an identical dump proves
    nothing (the dump may simply not expose that state), so it records
    None (unprobed), never False.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        before = artifacts.dump_before()
        after = artifacts.dump_after()
        if before is None or after is None:
            return None
        return True if before != after else None

    return check


def region_printed(marker: str) -> Callable[[ProbeArtifacts], bool]:
    """Make an effect assertion: a marker was printed in the target region."""

    def check(artifacts: ProbeArtifacts) -> bool:
        return printed_line(artifacts.target_region(), marker)

    return check


def emit_solver_setup(script: Script) -> None:
    """Emit the minimal steady setup preceding INITIALIZE_SOLVER.

    Constant free stream, sea-level standard atmosphere, and a short
    iteration budget: the smallest state in which the solver
    initializes and runs on an opened simulation (M2 pipeline shape).
    """
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit("AIR_ALTITUDE", 0.0, "METERS")
    script.emit("SOLVER_SET_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_AREA", 1.0)
    script.emit("SOLVER_SET_REF_LENGTH", 1.0)
    script.emit("SOLVER_SET_ITERATIONS", 5)
    script.emit("SET_SOLVER_STEADY")


def emit_tier_prelude(
    script: Script,
    tier: Requires,
    fsm: Path,
    after_open: Callable[[Script], None] | None = None,
) -> None:
    """Emit the standard prelude of one tier (SAD Section 11).

    ``sim`` opens the local simulation file; ``solver`` adds the
    minimal steady setup of the M2 pipeline (constant free stream,
    sea-level atmosphere, short iteration budget) and
    INITIALIZE_SOLVER on all boundaries without symmetry; ``solution``
    adds START_SOLVER. Physical relevance is not the point: the tier
    only manufactures the session state the target command needs to
    act on.

    Parameters
    ----------
    script : Script
        Script under construction.
    tier : Requires
        Tier to emit; ``none`` emits nothing.
    fsm : Path
        Local simulation (.fsm) file for the OPEN command.
    after_open : callable, optional
        ``after_open(script)`` emits setup-phase support right after
        OPEN, before the solver setup (the ``early_prelude`` hook).
    """
    if tier is Requires.NONE:
        return
    script.emit("OPEN", fsm)
    if after_open is not None:
        after_open(script)
    if tier is Requires.SIM:
        return
    emit_solver_setup(script)
    initialize_solver(script)
    if tier is Requires.SOLVER:
        return
    script.emit("START_SOLVER")


def generate_probe_script(
    spec: ProbeSpec,
    version: str | FsVersion,
    workdir: Path,
    registry: CommandRegistry | None = None,
    fsm: Path | None = None,
) -> Script:
    """Build the probe script for one command, sentinels included.

    The script is validated emission end to end (no ``raw()``): the
    tier prelude, the spec prelude, the BEGIN sentinel with its log
    export, the target command (bracketed by state dumps when
    ``dump_state``), the END sentinel, the spec epilogue, the final
    log export, and CLOSE_FLIGHTSTREAM so the hidden solver exits.

    Parameters
    ----------
    spec : ProbeSpec
        What to probe and how.
    version : str or FsVersion
        Target FlightStream version; emission is validated against it.
    workdir : Path
        Probe working directory; log exports point into it.
    registry : CommandRegistry, optional
        Alternative database, used by tests.
    fsm : Path, optional
        Local simulation file for tier preludes above ``none``;
        required by those tiers.

    Returns
    -------
    Script
        The rendered-ready probe script.
    """
    # The solver runs inside the probe directory, but log exports and
    # support files are addressed absolutely so the script is valid
    # from any execution directory (a relative path made the real
    # 26.120 export fail silently: the target folder did not exist
    # under the execution directory).
    workdir = Path(workdir).resolve()
    script = Script(version, registry=registry)
    script.comment(f"tier 2 probe for {spec.command}, generated by pyflightstream")
    if spec.requires is not Requires.NONE:
        if fsm is None:
            raise ProbeEnvironmentError(
                f"probe for {spec.command} needs the {spec.requires} prelude tier, "
                "which opens a local simulation file; pass fsm (CLI: --fsm)"
            )
        after_open = None
        if spec.early_prelude is not None:
            early = spec.early_prelude

            def after_open(inner: Script) -> None:
                early(inner, workdir)

        emit_tier_prelude(script, spec.requires, Path(fsm).resolve(), after_open)
    elif spec.early_prelude is not None:
        spec.early_prelude(script, workdir)
    if spec.prelude is not None:
        spec.prelude(script, workdir)
    script.emit("PRINT", f"{_BEGIN}_{spec.command}")
    script.emit("EXPORT_LOG", workdir / _LOG_BEFORE)
    if spec.dump_state:
        script.emit("OUTPUT_SETTINGS_AND_STATUS", workdir / _DUMP_BEFORE)
    spec.build_target(script, workdir)
    if spec.dump_state:
        script.emit("OUTPUT_SETTINGS_AND_STATUS", workdir / _DUMP_AFTER)
    script.emit("PRINT", f"{_END}_{spec.command}")
    script.emit("EXPORT_LOG", workdir / _LOG_AFTER)
    if spec.epilogue is not None:
        spec.epilogue(script, workdir)
        script.emit("EXPORT_LOG", workdir / _LOG_FINAL)
    script.emit("CLOSE_FLIGHTSTREAM")
    return script


def probe_version(
    version: str | FsVersion,
    *,
    workroot: str | Path,
    fs_exe: str | Path | None = None,
    executor: Executor | None = None,
    commands: Sequence[str] | None = None,
    specs: Mapping[str, ProbeSpec] | None = None,
    fsm: str | Path | None = None,
    timeout_s: float = 120.0,
    error_patterns: Sequence[str] = DEFAULT_ERROR_PATTERNS,
    registry: CommandRegistry | None = None,
) -> ProbeRun:
    """Probe the commands of one FlightStream version.

    Runs the baseline probe first (aborting on an unusable
    environment), validates each prelude tier the run will use, then
    one probe per command that has a specification, and records every
    remaining database command of the version as ``unprobed``, so the
    compat report carries one evidence line per command.

    Parameters
    ----------
    version : str or FsVersion
        Target version, canonical or alias.
    workroot : str or Path
        Root directory receiving one working subdirectory per probe;
        scratch evidence, never committed (the report is the evidence).
    fs_exe : str or Path, optional
        Explicit path of the FlightStream executable (SAD Section 5:
        never read from the environment or guessed). Required unless
        ``executor`` is given.
    executor : Executor, optional
        Alternative executor, used by tests; overrides ``fs_exe``.
    commands : sequence of str, optional
        Subset to probe; every name must exist in the version's view.
        Commands outside the subset are recorded as unprobed.
    specs : mapping of str to ProbeSpec, optional
        Probe specifications; defaults to the packaged catalog in
        :mod:`pyflightstream.qa.specs`.
    fsm : str or Path, optional
        Local simulation (.fsm) file for prelude tiers above ``none``;
        explicit input, never committed. Specs needing it are recorded
        unprobed when it is absent.
    timeout_s : float
        Wall-clock limit per probe, unless the spec overrides it.
    error_patterns : sequence of str
        Regular expressions scanned between the sentinels.
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Returns
    -------
    ProbeRun
        One evidence line per command of the version.

    Raises
    ------
    ProbeEnvironmentError
        When the baseline probe fails or a probe directory cannot be
        prepared; no command evidence is produced in that case.
    ValueError
        When ``commands`` names a command outside the version's view.
    """
    resolved = resolve(version)
    view = (registry or CommandRegistry.load()).for_version(resolved)
    if specs is None:
        from pyflightstream.qa import specs as spec_catalog

        active_specs: Mapping[str, ProbeSpec] = spec_catalog.PROBE_SPECS
    else:
        active_specs = specs
    if executor is None:
        if fs_exe is None:
            raise ProbeEnvironmentError(
                "probe_version needs the FlightStream executable as explicit input "
                "(fs_exe); paths are never read from the environment or guessed "
                "(SAD Section 5)"
            )
        executor = LocalExecutor(fs_exe)
    fs_exe_name = Path(executor.fs_exe).name if isinstance(executor, LocalExecutor) else "fake"
    workroot = Path(workroot)
    workroot.mkdir(parents=True, exist_ok=True)
    fsm_path = None if fsm is None else Path(fsm).resolve()
    if fsm_path is not None and not fsm_path.is_file():
        raise ProbeEnvironmentError(
            f"the simulation file {fsm_path} does not exist; the prelude tiers need a "
            "real local .fsm as explicit input"
        )

    available = list(view)
    if commands is not None:
        unknown = sorted(set(commands) - set(available))
        if unknown:
            raise ValueError(
                f"cannot probe {', '.join(unknown)}: not available in FlightStream "
                f"{resolved.canonical}. Probes only run database commands of the "
                "target version."
            )
    requested = None if commands is None else set(commands)

    solver_identity = _run_baseline(executor, resolved, workroot, timeout_s, registry)

    planned = [
        active_specs[name]
        for name in available
        if name in active_specs and (requested is None or name in requested)
    ]
    tier_failures = _validate_tiers(
        planned, resolved, executor, workroot, fsm_path, timeout_s, registry
    )

    results: list[ProbeResult] = []
    for name in available:
        spec = active_specs.get(name)
        if requested is not None and name not in requested:
            results.append(ProbeResult(name, ProbeOutcome.UNPROBED, "not probed in this run"))
        elif spec is None:
            results.append(
                ProbeResult(
                    name, ProbeOutcome.UNPROBED, "no probe specification for this command yet"
                )
            )
        elif spec.requires is not Requires.NONE and fsm_path is None:
            results.append(
                ProbeResult(
                    name,
                    ProbeOutcome.UNPROBED,
                    f"needs the {spec.requires} prelude tier; supply a local simulation "
                    "file (--fsm) to probe it",
                )
            )
        elif spec.requires in tier_failures:
            results.append(
                ProbeResult(
                    name,
                    ProbeOutcome.UNPROBED,
                    f"the {spec.requires} prelude tier failed its baseline, so the "
                    f"command was not judged: {tier_failures[spec.requires]}",
                )
            )
        else:
            results.append(
                _run_probe(
                    spec,
                    resolved,
                    executor,
                    workroot,
                    timeout_s,
                    error_patterns,
                    registry,
                    fsm_path,
                )
            )
    return ProbeRun(
        version=resolved.canonical,
        solver_identity=solver_identity,
        fs_exe_name=fs_exe_name,
        package_version=pyflightstream.__version__,
        results=tuple(results),
    )


def _validate_tiers(
    planned: Sequence[ProbeSpec],
    version: FsVersion,
    executor: Executor,
    workroot: Path,
    fsm: Path | None,
    timeout_s: float,
    registry: CommandRegistry | None,
) -> dict[Requires, str]:
    """Run one baseline per prelude tier the planned specs use.

    A tier whose baseline fails downgrades its probes to unprobed with
    the failure recorded; a broken prelude must never read as broken
    target commands.
    """
    failures: dict[Requires, str] = {}
    tiers = {spec.requires for spec in planned} - {Requires.NONE}
    if fsm is None:
        return failures
    for tier in sorted(tiers, key=list(Requires).index):
        workdir = _fresh_dir(workroot / f"_tier_{tier.value}")
        script = Script(version, registry=registry)
        script.comment(f"prelude tier baseline: {tier.value}")
        emit_tier_prelude(script, tier, fsm)
        marker = f"{_BASELINE_MARKER}_{tier.value.upper()}"
        script.emit("PRINT", marker)
        script.emit("EXPORT_LOG", workdir / _LOG_AFTER)
        script.emit("CLOSE_FLIGHTSTREAM")
        script_path = workdir / _SCRIPT_NAME
        script_path.write_text(script.render(), encoding="utf-8")
        execution = executor.run_script(script_path, working_dir=workdir, timeout_s=timeout_s)
        log_text = _read_log(workdir / _LOG_AFTER)
        if log_text is None or not printed_line(log_text, marker):
            hint = execution.log_text or execution.stderr or f"return code {execution.return_code}"
            failures[tier] = f"prelude did not reach its sentinel ({hint or 'no solver output'})"
    return failures


def _fresh_dir(workdir: Path) -> Path:
    """Create an empty probe directory, wiping only what the harness owns.

    A stale log in a reused directory would fake a probe signal, so the
    directory is recreated; anything not created by a previous probe
    (no probe script inside a non-empty directory) is refused instead
    of deleted.
    """
    workdir = workdir.resolve()
    if workdir.exists():
        contents = list(workdir.iterdir())
        if contents and not (workdir / _SCRIPT_NAME).is_file():
            raise ProbeEnvironmentError(
                f"refusing to wipe {workdir}: it is not empty and holds no probe script, "
                "so it was not created by the probe harness. Choose a clean workroot."
            )
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    return workdir


def _read_log(path: Path) -> str | None:
    """Read an exported log, scrubbing the stray NUL bytes of hidden mode.

    Real 26.120 hidden-mode exports carry NUL bytes between lines
    (RPT-001 finding 2); they are scrubbed here exactly as in
    ``parse_residual_history``.
    """
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")


def _run_baseline(
    executor: Executor,
    version: FsVersion,
    workroot: Path,
    timeout_s: float,
    registry: CommandRegistry | None,
) -> tuple[str, ...]:
    """Validate the probe instruments and capture the solver identity.

    The baseline script is PRINT plus EXPORT_LOG plus
    CLOSE_FLIGHTSTREAM, the instrument set every probe relies on. Its
    failure means the environment (executable, license, log export) is
    unusable, and the run aborts instead of producing false evidence.
    """
    workdir = _fresh_dir(workroot / _BASELINE_DIR)
    log_path = workdir / _LOG_AFTER
    script = Script(version, registry=registry)
    script.comment("tier 2 baseline probe: validates the probe instruments")
    script.emit("PRINT", _BASELINE_MARKER)
    script.emit("EXPORT_LOG", log_path)
    script.emit("CLOSE_FLIGHTSTREAM")
    script_path = workdir / _SCRIPT_NAME
    script_path.write_text(script.render(), encoding="utf-8")
    execution = executor.run_script(script_path, working_dir=workdir, timeout_s=timeout_s)
    log_text = _read_log(log_path)
    if log_text is None or not printed_line(log_text, _BASELINE_MARKER):
        hint = execution.log_text or execution.stderr or f"return code {execution.return_code}"
        raise ProbeEnvironmentError(
            "baseline probe failed: the PRINT sentinel never reached the exported log, "
            "so the environment (executable, license checkout, or log export) is "
            f"unusable and no command was judged. Solver said: {hint or 'nothing'}"
        )
    identity = tuple(
        line.strip()
        for line in log_text.splitlines()
        if ("version" in line.lower() or "build" in line.lower()) and _BASELINE_MARKER not in line
    )[:5]
    return identity


def _run_probe(
    spec: ProbeSpec,
    version: FsVersion,
    executor: Executor,
    workroot: Path,
    timeout_s: float,
    error_patterns: Sequence[str],
    registry: CommandRegistry | None,
    fsm: Path | None = None,
) -> ProbeResult:
    """Run one probe end to end and judge its three signals."""
    workdir = _fresh_dir(workroot / spec.command)
    script = generate_probe_script(spec, version, workdir, registry=registry, fsm=fsm)
    text = script.render()
    script_path = workdir / _SCRIPT_NAME
    script_path.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    limit = spec.timeout_s if spec.timeout_s is not None else timeout_s
    execution = executor.run_script(script_path, working_dir=workdir, timeout_s=limit)
    artifacts = ProbeArtifacts(
        workdir=workdir,
        log_before=_read_log(workdir / _LOG_BEFORE),
        log_after=_read_log(workdir / _LOG_AFTER),
        begin_marker=f"{_BEGIN}_{spec.command}",
        end_marker=f"{_END}_{spec.command}",
        execution=execution,
    )
    return _judge(spec, artifacts, error_patterns, sha, limit)


def _judge(
    spec: ProbeSpec,
    artifacts: ProbeArtifacts,
    error_patterns: Sequence[str],
    script_sha256: str,
    timeout_s: float,
) -> ProbeResult:
    """Turn the probe signals into one evidence line."""
    execution = artifacts.execution
    sentinel_before = artifacts.log_before is not None and printed_line(
        artifacts.log_before, artifacts.begin_marker
    )
    sentinel_after = artifacts.log_after is not None and printed_line(
        artifacts.log_after, artifacts.end_marker
    )
    common = {
        "command": spec.command,
        "sentinel_before": sentinel_before,
        "sentinel_after": sentinel_after,
        "wall_time_s": execution.wall_time_s,
        "return_code": execution.return_code,
        "script_sha256": script_sha256,
    }
    if spec.expects_halt:
        return _judge_halt(spec, artifacts, common)
    if execution.timed_out:
        return ProbeResult(
            outcome=ProbeOutcome.UNPROBED,
            detail=(
                f"probe timed out after {timeout_s:g} s and the process was killed; "
                "inconclusive, rerun with a larger timeout or probe by hand"
            ),
            **common,
        )
    if artifacts.log_after is None:
        if artifacts.log_before is None:
            return ProbeResult(
                outcome=ProbeOutcome.UNPROBED,
                detail=(
                    "the solver exported neither sentinel log although the baseline "
                    "probe passed; inconclusive, environment drifted mid-run "
                    f"(return code {execution.return_code})"
                ),
                **common,
            )
        return ProbeResult(
            outcome=ProbeOutcome.BROKEN,
            detail=(
                "script processing aborted at the command: the log exported before it "
                "exists, the one after it never appeared (END sentinel missing)"
            ),
            **common,
        )
    matches = _scan_errors(artifacts.target_region(), error_patterns)
    if matches:
        return ProbeResult(
            outcome=ProbeOutcome.BROKEN,
            detail=(
                "the solver logged errors between the probe sentinels: " + "; ".join(matches[:3])
            ),
            log_errors=tuple(matches),
            **common,
        )
    epilogue_note = ""
    if spec.epilogue is not None and artifacts.log_final() is None:
        epilogue_note = (
            " (the epilogue instruments aborted after the target; the effect was "
            "judged from the artifacts they left)"
        )
    effect = spec.assert_effect(artifacts)
    if effect is None:
        return ProbeResult(
            outcome=ProbeOutcome.UNPROBED,
            detail=(
                "the command ran without a script abort or logged error, but its "
                "effect is not observable with the current instruments; asserted "
                f"effect: {spec.effect_note}{epilogue_note}"
            ),
            effect=None,
            **common,
        )
    if not effect:
        return ProbeResult(
            outcome=ProbeOutcome.BROKEN,
            detail=(
                "the command ran (script processing continued past it) but its effect "
                f"was not observed; expected: {spec.effect_note}{epilogue_note}"
            ),
            effect=False,
            **common,
        )
    return ProbeResult(
        outcome=ProbeOutcome.VERIFIED,
        detail=(
            "script processing continued past the command, no error between the "
            f"sentinels, and the effect was observed: {spec.effect_note}{epilogue_note}"
        ),
        effect=True,
        **common,
    )


def _judge_halt(
    spec: ProbeSpec, artifacts: ProbeArtifacts, common: dict[str, object]
) -> ProbeResult:
    """Judge a probe whose expected effect is halting the script.

    Killing the process at the timeout is not a failure here: a hidden
    solver may idle after the halt, and the halt evidence is the pair
    of logs, not the exit.
    """
    if artifacts.log_before is None or not common["sentinel_before"]:
        return ProbeResult(
            outcome=ProbeOutcome.UNPROBED,
            detail=(
                "the log exported before the command is missing or lacks its sentinel "
                "although the baseline probe passed; inconclusive"
            ),
            **common,
        )
    if artifacts.log_after is not None:
        return ProbeResult(
            outcome=ProbeOutcome.BROKEN,
            detail=(
                "the command was expected to halt script processing, but the log after "
                "it was exported (processing continued)"
            ),
            effect=False,
            **common,
        )
    killed = (
        " (the idle hidden process was killed at the timeout)"
        if (artifacts.execution.timed_out)
        else ""
    )
    return ProbeResult(
        outcome=ProbeOutcome.VERIFIED,
        detail=(
            "script processing halted at the command: the log before it exists, the "
            f"one after it never appeared; expected: {spec.effect_note}{killed}"
        ),
        effect=True,
        **common,
    )


def _scan_errors(region: str, error_patterns: Sequence[str]) -> list[str]:
    """Return the region lines matching any error pattern, verbatim."""
    compiled = [re.compile(pattern) for pattern in error_patterns]
    matches = []
    for line in region.splitlines():
        if any(pattern.search(line) for pattern in compiled):
            matches.append(line.strip()[:160])
    return matches


# The probe specification catalog lives in pyflightstream.qa.specs,
# one evidence-backed specification per command; probe_version imports
# it lazily so the catalog can build on the machinery of this module.
