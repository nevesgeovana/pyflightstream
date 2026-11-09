"""PFS-2207 and PFS-2208 (0.57.0): what the geometry worker raises, and what it leaves on disk.

The kernel runs in a worker process. An exception of the package arrives as itself; any
other exception is a defect, not a refusal of the input, and arrives as its own type with the
worker's traceback.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._gmsh_worker import run_isolated

_HERE = "tests.tier1_offline.test_p0570_fix5_gmsh_worker"


class KernelOddError(Exception):
    """An exception type only the worker's own code defines."""


def worker_value_error():
    raise ValueError("a programming error in the worker")


def worker_odd():
    raise KernelOddError("the kernel said something odd")


def worker_missing_extra():
    from pyflightstream.extras import MissingExtraError

    raise MissingExtraError(extra="gmsh", package="gmsh", purpose="the test")


def worker_input_artifact():
    raise InputArtifactError("bad surface. Nothing was written.", kind="geometry")


def _direct(*_args, **_kwargs):
    raise AssertionError("the worker is not the calling process")


def test_p0570_fix5_a_defect_in_the_worker_is_not_an_input_refusal():
    """PFS-2207: a ValueError of the worker arrives as a ValueError, with its traceback."""
    with pytest.raises(ValueError, match="a programming error in the worker") as raised:
        run_isolated(f"{_HERE}:worker_value_error", {}, _direct)
    assert not isinstance(raised.value, InputArtifactError)
    notes = "\n".join(getattr(raised.value, "__notes__", []))
    assert "worker_value_error" in notes and "Traceback" in notes


def test_p0570_fix5_an_unknown_worker_exception_names_its_type():
    """PFS-2207: a type the parent does not know returns as a RuntimeError that names it."""
    with pytest.raises(
        RuntimeError, match="KernelOddError.*the kernel said something odd"
    ) as raised:
        run_isolated(f"{_HERE}:worker_odd", {}, _direct)
    assert not isinstance(raised.value, InputArtifactError)
    assert "worker_odd" in "\n".join(raised.value.__notes__)


def test_p0570_fix5_a_refusal_of_the_package_keeps_its_type_and_kind():
    """PFS-2207: the package's own refusal is still the same type and message."""
    with pytest.raises(InputArtifactError, match="bad surface. Nothing was written.") as raised:
        run_isolated(f"{_HERE}:worker_input_artifact", {}, _direct)
    assert raised.value.kind == "geometry"


def test_p0570_fix5_a_missing_extra_in_the_worker_keeps_its_fields():
    """PFS-2207: a MissingExtraError from the worker still names the extra and the remedy."""
    from pyflightstream.extras import MissingExtraError

    with pytest.raises(MissingExtraError) as raised:
        run_isolated(f"{_HERE}:worker_missing_extra", {}, _direct)
    assert raised.value.extra == "gmsh"
    assert raised.value.package == "gmsh"
    assert raised.value.remedy == 'pip install "pyflightstream[gmsh]"'


# ------------------------------------------------ PFS-2208: nothing is published on a failure


def _crash():
    if os.name == "nt":
        os._exit(-1073741819)
    os.kill(os.getpid(), signal.SIGSEGV)


def _write_outputs(out: str) -> list[Path]:
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    side = [target, Path(str(target) + ".boundaries.toml"), Path(str(target) + ".json")]
    for path in side:
        path.write_text("written\n", encoding="utf-8")
    return side


def worker_writes_then_crashes(out):
    _write_outputs(out)
    _crash()


def worker_writes_then_refuses(out):
    _write_outputs(out)
    raise InputArtifactError("late refusal. Nothing was written.", kind="geometry")


def worker_writes_then_hangs(out):
    import time

    _write_outputs(out)
    time.sleep(60)


def worker_writes(out):
    _write_outputs(out)
    return {"output": Path(out).name, "echo": out}


@pytest.mark.parametrize(
    ("worker", "error", "match"),
    [
        ("worker_writes_then_crashes", InputArtifactError, "kernel failed"),
        ("worker_writes_then_refuses", InputArtifactError, "late refusal"),
    ],
)
def test_p0570_fix5_a_failed_worker_leaves_no_output_behind(tmp_path, worker, error, match):
    """PFS-2208: a conversion that fails after it wrote publishes nothing."""
    out = tmp_path / "result" / "wing.obj"
    with pytest.raises(error, match=match):
        run_isolated(f"{_HERE}:{worker}", {"out": str(out)}, _direct)
    assert not out.parent.exists() or not list(out.parent.iterdir())
    assert not list(tmp_path.rglob("*.json")) and not list(tmp_path.rglob("*.toml"))


def test_p0570_fix5_a_hung_worker_leaves_no_output_behind(tmp_path, monkeypatch):
    """PFS-2208: a worker ended at its time limit after it wrote publishes nothing."""
    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_TIMEOUT", "3")
    out = tmp_path / "wing.obj"
    with pytest.raises(InputArtifactError, match="longer than 3 s"):
        run_isolated(f"{_HERE}:worker_writes_then_hangs", {"out": str(out)}, _direct)
    assert list(tmp_path.iterdir()) == []


def test_p0570_fix5_an_answered_worker_publishes_every_output_at_its_place(tmp_path):
    """PFS-2208: after the answer, the files are at the requested path, under their names."""
    out = tmp_path / "deep" / "wing.obj"
    record = run_isolated(f"{_HERE}:worker_writes", {"out": str(out)}, _direct)
    assert record["output"] == "wing.obj"
    assert sorted(path.name for path in out.parent.iterdir()) == [
        "wing.obj",
        "wing.obj.boundaries.toml",
        "wing.obj.json",
    ]
    assert out.read_text(encoding="utf-8") == "written\n"
    out.write_text("older\n", encoding="utf-8")
    run_isolated(f"{_HERE}:worker_writes", {"out": str(out)}, _direct)
    assert out.read_text(encoding="utf-8") == "written\n"


def worker_refuses_naming_its_output(out):
    _write_outputs(out)
    raise InputArtifactError(f"{out}: late refusal. Nothing was written.", kind="geometry")


def test_p0570_fix5_a_refusal_names_the_requested_path_not_the_staging_folder(tmp_path):
    """PFS-2208: the staging folder is not shown to the caller; the path asked for is."""
    out = tmp_path / "wing.obj"
    with pytest.raises(InputArtifactError) as raised:
        run_isolated(f"{_HERE}:worker_refuses_naming_its_output", {"out": str(out)}, _direct)
    assert str(out.parent) in str(raised.value) and "pyfs-gmsh-" not in str(raised.value)
