"""Tier 1: the registry snapshot/restore fixture actually isolates tests.

Pipeline role: quality gate on the module-state hygiene adopted from
the 2026-07-23 library review (pyvista conftest discipline). The
autouse fixture in ``conftest.py`` snapshots every inventoried
module-level registry before each test and restores it after; the
tests here prove the mechanism both directly (driving the fixture
generator by hand) and across test boundaries (an ordered pair in this
file: the first test mutates, the second observes pristine state).
"""

from __future__ import annotations

import conftest
import pytest

from pyflightstream.cases import matrix as _matrix
from pyflightstream.qa import physics as _physics
from pyflightstream.qa import specs as _specs

_SENTINEL = "PYFS-TEST-SENTINEL"


def test_restore_logic_reverts_a_mutation_directly():
    """Drive the fixture generator by hand: mutate, finalize, pristine."""
    gen = conftest._restore_module_registries.__wrapped__()
    next(gen)
    _physics.PHYSICS_CASES[_SENTINEL] = object()
    _specs.PROBE_SPECS[_SENTINEL] = object()
    _matrix._SWEEP_CODES[_SENTINEL] = "sentinel"
    with pytest.raises(StopIteration):
        next(gen)
    assert _SENTINEL not in _physics.PHYSICS_CASES
    assert _SENTINEL not in _specs.PROBE_SPECS
    assert _SENTINEL not in _matrix._SWEEP_CODES


def test_inventory_snapshots_only_mutable_mappings():
    """Every inventoried state object supports the snapshot contract."""
    for state in conftest._mutable_module_state():
        assert hasattr(state, "clear") and hasattr(state, "update"), (
            f"{state!r} cannot be restored by clear/update; the snapshot "
            "fixture only handles mutable mappings"
        )


# The ordered pair: pytest runs tests of one module in definition
# order, so the second test observes the state the autouse fixture
# restored after the first. Running the second test alone also passes,
# by design; the pair only adds cross-test-boundary proof.


def test_zz_ordered_pair_mutates_the_registries():
    _physics.PHYSICS_CASES[_SENTINEL] = object()
    _physics.SMI_CASES[_SENTINEL] = object()
    _specs.PROBE_SPECS[_SENTINEL] = object()
    assert _SENTINEL in _physics.PHYSICS_CASES


def test_zz_ordered_pair_observes_pristine_registries():
    assert _SENTINEL not in _physics.PHYSICS_CASES
    assert _SENTINEL not in _physics.SMI_CASES
    assert _SENTINEL not in _specs.PROBE_SPECS
