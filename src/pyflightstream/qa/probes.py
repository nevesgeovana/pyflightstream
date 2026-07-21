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
from pyflightstream.versions import FsVersion, resolve

_BEGIN = "PYFS_PROBE_BEGIN"
_END = "PYFS_PROBE_END"
_BASELINE_MARKER = "PYFS_BASELINE_ALIVE"
_LOG_BEFORE = "log_before.txt"
_LOG_AFTER = "log_after.txt"
_SCRIPT_NAME = "probe_script.txt"
_BASELINE_DIR = "_baseline"
_NESTED_NAME = "nested_probe.txt"

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
        Log exported after the END sentinel; None when the file never
        appeared (script aborted, or halted by design).
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
        ``assert_effect(artifacts) -> bool`` checks the observable
        effect. Mandatory unless ``expects_halt``: a command that runs
        but does nothing is broken, not verified (SAD Section 11), so
        a probe without an effect assertion cannot exist.
    expects_halt : bool
        The command is expected to halt script processing (STOP); the
        halt itself is the asserted effect, so the sentinel logic
        inverts: the log before the command must exist and the one
        after it must never appear.
    prelude : callable, optional
        ``prelude(script, workdir)`` emits the minimal model the
        command needs before the sentinels (geometry, solver setup);
        None for control commands that run on an empty session.
    effect_note : str
        One sentence naming the asserted effect; quoted in the compat
        report evidence line.
    timeout_s : float, optional
        Per-probe override of the run timeout; halting probes use a
        short one because the hidden solver may idle after the halt.
    """

    command: str
    build_target: Callable[[Script, Path], None]
    assert_effect: Callable[[ProbeArtifacts], bool] | None = None
    expects_halt: bool = False
    prelude: Callable[[Script, Path], None] | None = None
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


def generate_probe_script(
    spec: ProbeSpec,
    version: str | FsVersion,
    workdir: Path,
    registry: CommandRegistry | None = None,
) -> Script:
    """Build the probe script for one command, sentinels included.

    The script is validated emission end to end (no ``raw()``): the
    optional prelude, the BEGIN sentinel with its log export, the
    target command, the END sentinel with its log export, and
    CLOSE_FLIGHTSTREAM so the hidden solver exits.

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
    if spec.prelude is not None:
        spec.prelude(script, workdir)
    script.emit("PRINT", f"{_BEGIN}_{spec.command}")
    script.emit("EXPORT_LOG", workdir / _LOG_BEFORE)
    spec.build_target(script, workdir)
    script.emit("PRINT", f"{_END}_{spec.command}")
    script.emit("EXPORT_LOG", workdir / _LOG_AFTER)
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
    timeout_s: float = 120.0,
    error_patterns: Sequence[str] = DEFAULT_ERROR_PATTERNS,
    registry: CommandRegistry | None = None,
) -> ProbeRun:
    """Probe the commands of one FlightStream version.

    Runs the baseline probe first (aborting on an unusable
    environment), then one probe per command that has a specification,
    and records every remaining database command of the version as
    ``unprobed``, so the compat report carries one evidence line per
    command.

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
        Probe specifications; defaults to :data:`PROBE_SPECS`.
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
    active_specs = PROBE_SPECS if specs is None else specs
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
        else:
            results.append(
                _run_probe(spec, resolved, executor, workroot, timeout_s, error_patterns, registry)
            )
    return ProbeRun(
        version=resolved.canonical,
        solver_identity=solver_identity,
        fs_exe_name=fs_exe_name,
        package_version=pyflightstream.__version__,
        results=tuple(results),
    )


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
) -> ProbeResult:
    """Run one probe end to end and judge its three signals."""
    workdir = _fresh_dir(workroot / spec.command)
    script = generate_probe_script(spec, version, workdir, registry=registry)
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
    effect = bool(spec.assert_effect(artifacts))
    if not effect:
        return ProbeResult(
            outcome=ProbeOutcome.BROKEN,
            detail=(
                "the command ran (script processing continued past it) but its effect "
                f"was not observed; expected: {spec.effect_note}"
            ),
            effect=False,
            **common,
        )
    return ProbeResult(
        outcome=ProbeOutcome.VERIFIED,
        detail=(
            "script processing continued past the command, no error between the "
            f"sentinels, and the effect was observed: {spec.effect_note}"
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


# ---------------------------------------------------------------------------
# Probe specifications. Pilot family: script controls (SRC-003 p.281).
# The sweep over the remaining database families grows here, one
# evidence-backed specification per command.


def _print_target(script: Script, workdir: Path) -> None:
    script.emit("PRINT", "PYFS_EFFECT_PRINT")


def _print_effect(artifacts: ProbeArtifacts) -> bool:
    return printed_line(artifacts.target_region(), "PYFS_EFFECT_PRINT")


def _stop_target(script: Script, workdir: Path) -> None:
    script.emit("STOP")


def _run_script_target(script: Script, workdir: Path) -> None:
    # The nested file is fixed probe support data (a single PRINT), not
    # emitted through a builder: it must exist on disk before the run.
    nested = workdir / _NESTED_NAME
    nested.write_text(
        "# nested script for the RUN_SCRIPT probe\nPRINT PYFS_EFFECT_NESTED\n",
        encoding="utf-8",
    )
    script.emit("RUN_SCRIPT", nested)


def _run_script_effect(artifacts: ProbeArtifacts) -> bool:
    return printed_line(artifacts.target_region(), "PYFS_EFFECT_NESTED")


PROBE_SPECS: dict[str, ProbeSpec] = {
    "PRINT": ProbeSpec(
        command="PRINT",
        build_target=_print_target,
        assert_effect=_print_effect,
        effect_note="the probe message PYFS_EFFECT_PRINT appears as a log line of its own",
    ),
    "STOP": ProbeSpec(
        command="STOP",
        build_target=_stop_target,
        expects_halt=True,
        effect_note="script processing halts at STOP",
        timeout_s=60.0,
    ),
    "RUN_SCRIPT": ProbeSpec(
        command="RUN_SCRIPT",
        build_target=_run_script_target,
        assert_effect=_run_script_effect,
        effect_note=(
            "the nested script's message PYFS_EFFECT_NESTED appears in the log, so the "
            "called script really ran"
        ),
    ),
}
