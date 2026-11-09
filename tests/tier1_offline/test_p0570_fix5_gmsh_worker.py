"""PFS-2207 (0.57.0): what the geometry worker raises.

The kernel runs in a worker process. An exception of the package arrives as itself; any
other exception is a defect, not a refusal of the input, and arrives as its own type with the
worker's traceback.
"""

from __future__ import annotations

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
