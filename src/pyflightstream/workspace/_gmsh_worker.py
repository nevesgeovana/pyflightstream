"""Run a geometry-kernel conversion in a disposable worker process.

The OpenCASCADE kernel behind gmsh can fault natively on a malformed surface (an access
violation), and a Python ``except`` cannot establish that the kernel is usable afterwards. So
each conversion that needs the kernel runs in a worker process of its own: the parent never
initializes gmsh for it, a fault ends only the worker, and the parent reports the failure with
its cause and goes on. A failed conversion is fatal for that conversion: no kernel state is
reused, no retry is made in the same process, and nothing is published, because the operations
write their outputs only after the last kernel call returns.

The request and the answer travel as JSON files named on the worker's command line, never
through the standard streams, which the kernel writes to.
"""

from __future__ import annotations

import builtins
import importlib
import json
import math
import os
import subprocess
import sys
import tempfile
import traceback
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyflightstream._errors import (
    InputArtifactError,
    InputValueError,
    PyflightstreamError,
    warn_by_name,
)
from pyflightstream._textio import write_text

__all__ = ["run_isolated"]

#: The environment variable that, set to ``0``, runs the kernel in the calling process instead
#: of a worker. It exists for tests that patch the kernel in their own process.
ISOLATE_ENV = "PYFLIGHTSTREAM_GMSH_ISOLATE"

#: The environment variable that sets the seconds a worker may run before it is ended and
#: reported. A conversion of an assembly takes seconds to minutes, and a hung kernel must not
#: hold the caller for ever; the default is an hour.
TIMEOUT_ENV = "PYFLIGHTSTREAM_GMSH_TIMEOUT"
_DEFAULT_TIMEOUT_S = 3600.0

#: The Windows process-creation flag that opens no console window for the worker.
_NO_WINDOW = 0x08000000
#: The last lines of the worker's error stream carried into the refusal, at most.
_TAIL_LINES = 12


def _describe(code: int) -> str:
    if code < 0 and os.name != "nt":
        return f"signal {-code}"
    return f"exit code {code} ({code & 0xFFFFFFFF:#x})"


def _timeout() -> float:
    """Return the worker's time limit in seconds, refusing a value that is not a positive number."""
    text = os.environ.get(TIMEOUT_ENV)
    if text is None:
        return _DEFAULT_TIMEOUT_S
    try:
        limit = float(text)
    except ValueError:
        limit = math.nan
    if not (math.isfinite(limit) and limit > 0):
        raise InputValueError(
            f"{TIMEOUT_ENV}={text!r} must be a positive number of seconds (default "
            f"{_DEFAULT_TIMEOUT_S:g}). Nothing was written."
        )
    return limit


def run_isolated(
    operation: str, arguments: dict[str, Any], direct: Callable[..., dict[str, Any]]
) -> dict[str, Any]:
    """Return the record of ``operation`` run in a worker with ``arguments``.

    ``operation`` is ``"<module>:<function>"``, a function of this package that takes
    ``arguments`` as keywords and returns a JSON-serializable record. ``direct`` is the same
    function, called here when :data:`ISOLATE` is off.

    Raises
    ------
    InputArtifactError
        The worker ended without an answer (a kernel fault, a timeout): the message gives the
        cause and says nothing was written.
    """
    if os.environ.get(ISOLATE_ENV) == "0":
        return direct(**arguments)
    with tempfile.TemporaryDirectory(prefix="pyfs-gmsh-") as folder:
        request, answer = Path(folder) / "request.json", Path(folder) / "answer.json"
        write_text(request, json.dumps({"operation": operation, "arguments": arguments}))
        limit = _timeout()
        flags = _NO_WINDOW if os.name == "nt" else 0
        env = {**os.environ, _ENV: "1"}
        try:
            done = subprocess.run(
                [sys.executable, "-m", __name__, str(request), str(answer)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=limit,
                creationflags=flags,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise _failed(f"it ran longer than {limit:g} s and was ended", "") from error
        if not answer.is_file():
            tail = "\n".join((done.stderr or "").strip().splitlines()[-_TAIL_LINES:])
            raise _failed(f"its worker process ended with {_describe(done.returncode)}", tail)
        reply = json.loads(answer.read_text(encoding="utf-8"))
    for category, message in reply.get("warnings", []):
        warn_by_name(message, category, 2)
    if "error" in reply:
        raise _rebuilt(reply["error"])
    result: dict[str, Any] = reply["result"]
    return result


def _failed(cause: str, tail: str) -> InputArtifactError:
    detail = f" The worker said:\n{tail}\n" if tail else " "
    return InputArtifactError(
        f"the geometry kernel failed on this input: {cause}.{detail}This conversion cannot "
        "continue: the kernel is not reused after a fault. Nothing was written. Check the "
        "IGES file (a malformed surface can fault the kernel), write it again from its CAD "
        "system and run again; the calling process is unaffected.",
        kind="geometry",
    )


def _rebuilt(error: dict[str, Any]) -> Exception:
    """Return the exception the worker raised, as the parent's own type and message.

    A refusal of this package keeps its own type. Anything else is a defect or a fault of
    the kernel's own, not a refusal of the input: it returns as the same builtin type where
    there is one, else as a ``RuntimeError`` naming the type, and carries the worker's
    traceback as a note, so it reads as it does with ``PYFLIGHTSTREAM_GMSH_ISOLATE=0``.
    """
    name, message = str(error["type"]), str(error["message"])
    if name == "MissingExtraError":
        return _errors_missing(message, error.get("attrs") or {})
    if name == "InputValueError":
        return InputValueError(message)
    if error.get("package"):
        return InputArtifactError(message, kind=error.get("kind") or "geometry")
    found = getattr(builtins, name, None)
    rebuilt: Exception
    try:
        if not (isinstance(found, type) and issubclass(found, Exception)):
            raise TypeError(name)
        rebuilt = found(message)
    except Exception:
        rebuilt = RuntimeError(f"the geometry worker raised {name}: {message}")
    trace = str(error.get("traceback") or "").strip()
    if trace:
        rebuilt.add_note(f"worker traceback:\n{trace}")
    return rebuilt


def _errors_missing(message: str, attrs: dict[str, str]) -> Exception:
    from pyflightstream.extras import MissingExtraError

    error = MissingExtraError.__new__(MissingExtraError)
    Exception.__init__(error, message)
    for key, value in attrs.items():
        setattr(error, key, value)
    return error


_ENV = "PYFLIGHTSTREAM_GMSH_WORKER"


def _main(request: Path, answer: Path) -> int:
    """Run the requested operation and write its answer; a native fault writes none."""
    body = json.loads(request.read_text(encoding="utf-8"))
    module, _, function = str(body["operation"]).partition(":")
    reply: dict[str, Any] = {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            call = getattr(importlib.import_module(module), function)
            reply["result"] = call(**body["arguments"])
        except Exception as error:
            reply["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "kind": getattr(error, "kind", None),
                "package": isinstance(error, PyflightstreamError),
                "attrs": {
                    key: str(getattr(error, key))
                    for key in ("extra", "package", "purpose", "remedy")
                    if hasattr(error, key)
                },
                "traceback": traceback.format_exc(),
            }
    reply["warnings"] = [(w.category.__name__, str(w.message)) for w in caught]
    write_text(answer, json.dumps(reply))
    return 0


if __name__ == "__main__":
    sys.exit(_main(Path(sys.argv[1]), Path(sys.argv[2])))
