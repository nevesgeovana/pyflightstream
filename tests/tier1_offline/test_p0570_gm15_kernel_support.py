"""PFS-2220 G15: ``kernel_or_skip`` skips where the kernel cannot load, fails where required."""

from __future__ import annotations

import importlib.abc
import sys

import pytest

from tests.tier1_offline._kernel_support import REQUIRE_VARIABLE, kernel_or_skip


class _LibraryFails(importlib.abc.MetaPathFinder):
    """Make ``import gmsh`` raise OSError, as a missing shared library does."""

    def find_spec(self, name, path=None, target=None):
        if name == "gmsh":
            raise OSError("libGLU.so.1: cannot open shared object file")
        return None


@pytest.fixture
def library_fails(monkeypatch):
    monkeypatch.delitem(sys.modules, "gmsh", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_LibraryFails(), *sys.meta_path])


@pytest.fixture
def library_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "gmsh", None)


@pytest.mark.parametrize("broken", ["library_absent", "library_fails"])
def test_p0570_gm15_a_kernel_that_cannot_load_skips_by_default(broken, request, monkeypatch):
    request.getfixturevalue(broken)
    monkeypatch.delenv(REQUIRE_VARIABLE, raising=False)
    with pytest.raises(pytest.skip.Exception, match="cannot load"):
        kernel_or_skip()


@pytest.mark.parametrize("broken", ["library_absent", "library_fails"])
@pytest.mark.parametrize("value", ["1"])
def test_p0570_gm15_a_kernel_that_cannot_load_fails_when_required(
    broken, value, request, monkeypatch
):
    request.getfixturevalue(broken)
    monkeypatch.setenv(REQUIRE_VARIABLE, value)
    # BaseException: a skip raised in its place must read as a failure of this test, not a skip.
    with pytest.raises(BaseException, match="PYFS_REQUIRE_KERNEL=1 requires it") as raised:
        kernel_or_skip()
    assert isinstance(raised.value, pytest.fail.Exception), type(raised.value)


def test_p0570_gm15_a_value_other_than_one_does_not_require_the_kernel(library_absent, monkeypatch):
    monkeypatch.setenv(REQUIRE_VARIABLE, "0")
    with pytest.raises(pytest.skip.Exception):
        kernel_or_skip()


def test_p0570_gm15_a_loadable_kernel_is_returned():
    assert kernel_or_skip().__name__ == "gmsh"
