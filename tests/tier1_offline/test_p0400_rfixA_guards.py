"""Positive and negative controls for the static core and recorded-byte guards."""
# ruff: noqa: N999 - the assigned lane name is rfixA.

import pytest

from tests.tier1_offline.test_house_style import RECORDED_WAKE_FIXTURES, _geometry_offenses
from tests.tier1_offline.test_p0400_farfield_core import core_problems

pytestmark = pytest.mark.requirement("P0400-RFIXA-GUARDS")


@pytest.mark.parametrize(
    "source,name",
    [
        ("from ..results import wake", "trefftz.py"),
        ("from ...results.wake import parse_wake_export", "nested/core.py"),
        ("from .. import results", "trefftz.py"),
        ("import numpy as np\nnp.load('x')", "trefftz.py"),
        ("from numpy import load as read\nread('x')", "trefftz.py"),
        ("import numpy as n\nn.loadtxt('x')", "trefftz.py"),
        ("from numpy import genfromtxt\ngenfromtxt('x')", "trefftz.py"),
    ],
)
def test_p0400_rfixa_core_guard_refuses_relative_imports_and_array_readers(source, name):
    assert core_problems(source, name), source


@pytest.mark.parametrize(
    "source,name",
    [
        ("from .fields import PlaneFields", "trefftz.py"),
        ("from ..fields import PlaneFields", "nested/core.py"),
        ("import numpy as np\nnp.array([1, 2])", "trefftz.py"),
        ("from numpy import array as build\nbuild([1])", "trefftz.py"),
        ("def load(x): return x\nload(1)", "trefftz.py"),
    ],
)
def test_p0400_rfixa_core_guard_accepts_pure_arrays_and_lower_imports(source, name):
    assert not core_problems(source, name)


@pytest.mark.parametrize("data", [b"replaced", None])
def test_p0400_rfixa_compressed_wake_bytes_are_pinned(data):
    path = next(p for p in RECORDED_WAKE_FIXTURES if p.endswith(".xz"))
    assert _geometry_offenses([path], read=lambda _: data) == [path]


def test_p0400_rfixa_recorded_wakes_accept_captured_bytes():
    assert not _geometry_offenses(list(RECORDED_WAKE_FIXTURES))
