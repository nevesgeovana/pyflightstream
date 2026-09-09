"""Tier 3: the rotor path's thirteen solver-setting emitters on every build the
workspace can reach (PFS-2028.02, ``matriz_builds.fs``).

The 0.10.0 release note said the rotor default path had gained thirteen
solver-setting commands nobody had swept, most of them ``documented``
rather than ``verified`` on most builds. The sweep is one matrix whose
FS_BUILD column names each registered build this machine holds an
executable for (26.120 and 26.123 on 2026-09-08; 26.121 and 26.122 are
named as not covered in RPT-043), one rotor row per build, run through
``pyfs-matrix run``. The evidence is the script each solver received, the
run's terminal status and the log; the compatibility rows are promoted from
``reports/compat/CMP-<build>_2026-09-08_rotor-path.yaml`` by
``pyfs-qa apply-compat`` and are the side product.
"""

from __future__ import annotations

import pytest

from pyflightstream.commands import CommandRegistry
from tests.tier3_licensed.conftest import TERMINAL_OK, line

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_builds"

#: The thirteen, in the order the rotor path emits them (between the
#: reference settings and the surface sections).
THIRTEEN = (
    "SET_MAX_PARALLEL_THREADS",
    "SET_BOUNDARY_LAYER_TYPE",
    "SET_SOLVER_VISCOUS_COUPLING",
    "SET_SOLVER_CONVERGENCE_ITERATIONS",
    "SOLVER_MINIMUM_CP",
    "REYNOLDS_AVERAGED_DRAG_FORCES",
    "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY",
    "SOLVER_SET_FARFIELD_LAYERS",
    "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA",
    "SET_WAKE_ON_WAKE_INDUCTION",
    "ADDITIONAL_WAKE_RELAXATION_ITERATION",
    "SOLVER_STABILIZATION",
    "SET_ANALYSIS_SYMMETRY_LOADS",
)

ROWS = (("7001", "26.120"), ("7002", "26.123"))


@pytest.mark.parametrize(("pol", "build"), ROWS)
def test_the_rotor_row_ran_terminal_on_the_build_it_names(runs, pol, build):
    record = runs.one(MATRIX, pol, alpha=0.0, beta=0.0)
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == build
    assert record.fs_version_source == "row"


@pytest.mark.parametrize(("pol", "build"), ROWS)
def test_the_thirteen_reached_the_script_the_solver_received(runs, pol, build):
    record = runs.one(MATRIX, pol, alpha=0.0, beta=0.0)
    script = runs.script(record)
    for command in THIRTEEN:
        line(script, command)


@pytest.mark.parametrize(("pol", "build"), ROWS)
def test_the_log_carries_no_error_naming_one_of_the_thirteen(runs, workspace, pol, build):
    record = runs.one(MATRIX, pol, alpha=0.0, beta=0.0)
    logs = [o for o in record.outputs if o.endswith("_log.txt")]
    assert len(logs) == 1, record.outputs
    text = (workspace.sim_dir(pol) / logs[0]).read_bytes().decode("utf-8", errors="replace")
    named = [
        t.strip()
        for t in text.splitlines()
        if "error" in t.lower() and any(c in t for c in THIRTEEN)
    ]
    assert not named, named


@pytest.mark.parametrize("build", [b for _, b in ROWS])
def test_the_database_says_verified_on_the_build_and_cites_the_sweep(build):
    """The side product: every one of the thirteen carries a verified row on the
    build, citing this sweep's compat report where the sweep promoted it, or the
    earlier probe report where the row was already verified (the release review of
    2026-09-09: a sweep corroborates a verified row and never replaces its
    discriminating citation with a run-level one)."""
    view = CommandRegistry.load().for_version(build)
    stale = []
    for command in THIRTEEN:
        entry = view[command].versions[build]
        report = str(entry.report or "")
        if entry.status.value != "verified" or not ("rotor-path" in report or "CMP-" in report):
            stale.append((command, entry.status, entry.report))
    assert not stale, stale
