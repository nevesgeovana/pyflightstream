"""Execution of FlightStream on generated scripts.

Pipeline role: runs the solver headless on a rendered script and
reports what happened, typed. The campaign loop (next layer of
milestone M2) composes an :class:`Executor` with the managed workspace
of :mod:`pyflightstream.files` so that every executed point lands in
the manifest with exactly one terminal status; silent skips are
structurally impossible.

The local mechanism is the documented command-line script execution:
``FlightStream.exe --script <file>`` (SRC-003 p.279), with the
``-hidden`` flag for windowless batch runs; in hidden mode an
abnormal termination writes ``FlightStreamLog.txt`` into the command
execution directory, which is why the executor runs the solver inside
the simulation folder and captures that file (SRC-003 p.280). An HPC
executor with the same interface is deferred (FR-15).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_LOG_NAME = "FlightStreamLog.txt"


class ExecutorConfigurationError(ValueError):
    """The executor cannot run as configured.

    Raised at construction time, because a missing solver executable
    must surface before a campaign starts, not at its first point.
    The FlightStream path is always explicit input (SAD Section 5):
    nothing is read from environment variables or guessed.
    """


@dataclass(frozen=True)
class ExecutionResult:
    """Typed outcome of one solver process.

    Attributes
    ----------
    return_code : int or None
        Process return code; None when the run timed out and the
        process was killed.
    wall_time_s : float
        Wall-clock duration of the process in seconds.
    timed_out : bool
        Whether the timeout expired before the process finished.
    log_text : str or None
        Content of ``FlightStreamLog.txt`` from the execution
        directory when the solver wrote one (hidden-mode abnormal
        termination, SRC-003 p.280); None otherwise.
    stdout : str
        Captured standard output of the process.
    stderr : str
        Captured standard error of the process.
    """

    return_code: int | None
    wall_time_s: float
    timed_out: bool
    log_text: str | None
    stdout: str
    stderr: str

    @property
    def failed(self) -> bool:
        """Whether the process timed out or returned a nonzero code."""
        return self.timed_out or self.return_code != 0


class Executor(Protocol):
    """Anything that can run one rendered script to completion.

    Implementations must be interchangeable without touching the
    campaign model (FR-15): :class:`LocalExecutor` today, an HPC
    submission executor later.
    """

    def run_script(
        self, script_path: Path, working_dir: Path, timeout_s: float | None = None
    ) -> ExecutionResult:
        """Run one script and return the typed outcome."""
        ...


class LocalExecutor:
    """Runs FlightStream as a local subprocess (SRC-003 pp.279-280).

    Parameters
    ----------
    fs_exe : str or Path
        Explicit path of the FlightStream executable; it must exist.
        Never read from environment variables or guessed.
    hidden : bool
        Pass the ``-hidden`` flag for a windowless run; this is the
        batch mode that writes ``FlightStreamLog.txt`` on abnormal
        termination (SRC-003 p.280). Disable only for local debugging
        with the interface visible.
    """

    def __init__(self, fs_exe: str | Path, hidden: bool = True):
        self.fs_exe = Path(fs_exe)
        self.hidden = hidden
        if not self.fs_exe.is_file():
            raise ExecutorConfigurationError(
                f"FlightStream executable not found at {self.fs_exe}. The path is "
                "explicit campaign input (fs_exe); check the installation folder of "
                "the version the campaign requests."
            )

    def _argv(self, script_path: Path) -> list[str]:
        argv = [str(self.fs_exe)]
        if self.hidden:
            argv.append("-hidden")
        argv.extend(["--script", str(script_path)])
        return argv

    def run_script(
        self, script_path: Path, working_dir: Path, timeout_s: float | None = None
    ) -> ExecutionResult:
        """Run one rendered script to completion.

        The process runs inside ``working_dir`` so that the hidden-mode
        error log lands next to the run's files and can be captured.

        Parameters
        ----------
        script_path : Path
            Rendered ASCII script to execute.
        working_dir : Path
            Execution directory of the process; also where
            ``FlightStreamLog.txt`` appears on abnormal termination.
        timeout_s : float, optional
            Wall-clock limit; on expiry the process is killed and the
            result reports ``timed_out``.

        Returns
        -------
        ExecutionResult
            Typed outcome; no exception is raised for solver failure,
            the campaign loop decides the manifest status.
        """
        argv = self._argv(script_path)
        start = time.perf_counter()
        timed_out = False
        return_code: int | None = None
        stdout = ""
        stderr = ""
        try:
            completed = subprocess.run(
                argv,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            return_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            stdout = _decode(expired.stdout)
            stderr = _decode(expired.stderr)
        wall_time_s = time.perf_counter() - start
        log_path = Path(working_dir) / _LOG_NAME
        log_text = None
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        return ExecutionResult(
            return_code=return_code,
            wall_time_s=wall_time_s,
            timed_out=timed_out,
            log_text=log_text,
            stdout=stdout,
            stderr=stderr,
        )


def _decode(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream
