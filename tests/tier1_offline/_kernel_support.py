"""Shared test support: the CAD kernel library, imported for a test that needs it.

gmsh is a base dependency, so a kernel test is expected to run everywhere. Where the library
cannot load (a Linux machine without its system libraries), ``import`` raises ``ImportError``
when it is absent and ``OSError`` when a shared library it links against fails to load. The
helper turns both into a skip, unless ``PYFS_REQUIRE_KERNEL=1``, which the jobs that must prove
the kernel set: there the same condition fails the test, so a kernel test cannot skip silently
on the job meant to prove it.
"""

from __future__ import annotations

import os
from types import ModuleType

import pytest

REQUIRE_VARIABLE = "PYFS_REQUIRE_KERNEL"


def kernel_or_skip() -> ModuleType:
    """Return the gmsh module, skip the test when it cannot load, or fail it when required."""
    try:
        import gmsh
    except (ImportError, OSError) as error:
        message = f"the CAD kernel library gmsh cannot load: {error}"
        if os.environ.get(REQUIRE_VARIABLE) == "1":
            pytest.fail(f"{message} ({REQUIRE_VARIABLE}=1 requires it)", pytrace=False)
        pytest.skip(message)
    return gmsh
