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

import importlib
import json
import os
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyflightstream import _errors
from pyflightstream._errors import InputArtifactError

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
        request.write_text(
            json.dumps({"operation": operation, "arguments": arguments}), encoding="utf-8"
        )
        limit = float(os.environ.get(TIMEOUT_ENV, _DEFAULT_TIMEOUT_S))
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
        warnings.warn(message, getattr(_errors, category, _errors.PyflightstreamWarning), 2)
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


def _rebuilt(error: dict[str, str | None]) -> Exception:
    """Return the exception the worker raised, as the parent's own type and message."""
    name, message = str(error["type"]), str(error["message"])
    if name == "MissingExtraError":
        return _errors_missing(message)
    if name == "InputValueError":
        return _errors.InputValueError(message)
    return InputArtifactError(message, kind=error.get("kind") or "geometry")


def _errors_missing(message: str) -> Exception:
    from pyflightstream.extras import MissingExtraError

    error = MissingExtraError.__new__(MissingExtraError)
    Exception.__init__(error, message)
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
            }
    reply["warnings"] = [(w.category.__name__, str(w.message)) for w in caught]
    answer.write_text(json.dumps(reply), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(_main(Path(sys.argv[1]), Path(sys.argv[2])))
