"""P0400-DECIDED-DOCS-2: the tier-3 programs a tier-1 run can hold to what they promise.

Four programs of ``tests/tier3_licensed`` are started by people or by the solver, never by
pytest, so nothing offline ever ran them as they are run (PFS-2135.004, .047, .057, .080).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests import support_program_checks

REPO = Path(__file__).resolve().parents[2]
TIER3 = REPO / "tests" / "tier3_licensed"


def test_p0400_offline_program_checks_import_no_licensed_modules(monkeypatch):
    """The pure checks must work when the licensed tier cannot be imported."""
    import builtins
    import importlib

    original = builtins.__import__

    def offline_import(name, *args, **kwargs):
        licensed = name == "tests.tier3_licensed" or name.startswith("tests.tier3_licensed.")
        assert not licensed, name
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", offline_import)
    importlib.reload(support_program_checks)
    test_p0400_a_gap_of_exactly_one_printed_unit_is_inside_the_band_for_the_unit_answer()
    test_p0400_the_rotation_null_reads_the_simulation_id_a_point_name_leads_with()


def _isolated_program(tmp_path: Path, name: str) -> Path:
    """Copy the real entrypoint and its support into a tree holding no run artifacts."""
    tests = tmp_path / "program-tree" / "tests"
    scripts = tests / "tier3_licensed"
    scripts.mkdir(parents=True)
    for filename in ("__init__.py", "support_tier3.py"):
        shutil.copyfile(REPO / "tests" / filename, tests / filename)
    target = scripts / f"{name}.py"
    shutil.copyfile(TIER3 / target.name, target)
    return target


def _clean_environment() -> dict[str, str]:
    """The environment of a solver-started action: no PYTHONPATH to hide a missing root."""
    return {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}


def test_p0400_the_actions_probe_starts_as_the_solvers_command_line_action(tmp_path):
    """P0400-TIER3-PROBE-START: ``python actions_probe.py --verdict`` from another folder.

    The action's ``.cmd`` runs the file as a script, so ``sys.path[0]`` is its own folder and
    the repository root is absent; the program must find ``tests`` from its own location.
    """
    program = _isolated_program(tmp_path, "actions_probe")
    done = subprocess.run(
        [sys.executable, str(program), "--verdict"],
        cwd=tmp_path,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-600:]
    assert json.loads(done.stdout)["verdict"] == "NOT_RUN", done.stdout
    assert not (program.parent / "sims").exists()


def test_p0400_the_duct_generator_runs_as_the_script_the_docs_name(tmp_path):
    """P0400-TIER3-DUCT-START: ``python tests/tier3_licensed/duct.py out.obj`` writes the duct."""
    from tests.support_tier3 import write_duct_obj

    target = tmp_path / "duct.obj"
    program = _isolated_program(tmp_path, "duct")
    done = subprocess.run(
        [sys.executable, str(program), str(target)],
        cwd=tmp_path,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-600:]
    expected = write_duct_obj(tmp_path / "expected.obj")
    assert target.read_bytes() == Path(expected).read_bytes()


def test_p0400_a_gap_of_exactly_one_printed_unit_is_inside_the_band_for_the_unit_answer():
    """P0400-TIER3-MESH-BAND: ``unit_answer`` shares the slack ``outside`` applies."""
    mesh_routes = support_program_checks

    band = 1.0e-4
    one_unit = 1.0000000000000085e-4  # the binary quotient of a one-unit gap over the floor
    assert one_unit > band
    table = {"units": {"gaps": {"CL": one_unit, "CD": 0.5e-4}}}
    assert mesh_routes.unit_answer(table, band).startswith("IMPORT CONVERTS")
    banded = {"routes": {"4101": {"banded": True, "gaps": {"CL": one_unit}}}}
    assert mesh_routes.outside(banded, band) == {}
    table["units"]["gaps"]["CL"] = 1.01e-4
    assert mesh_routes.unit_answer(table, band).startswith("IMPORT DOES NOT CONVERT")
    assert mesh_routes.outside(
        {"routes": {"4101": {"banded": True, "gaps": {"CL": 1.01e-4}}}}, band
    )


def test_p0400_the_rotation_null_reads_the_simulation_id_a_point_name_leads_with():
    """P0400-TIER3-ROTATION-NULL-SIM: both turned points resolve to a row of the sweep table."""
    rotation_null = support_program_checks

    assert [rotation_null.sim_id_of(point) for point in rotation_null.TURNED] == ["9002", "9003"]
    assert rotation_null.sim_id_of(rotation_null.CONTROL) == "9001"
    sweep = {sim: {"sim_id": sim} for sim in ("9001", "9002", "9003")}
    for point in rotation_null.TURNED:
        assert rotation_null.sim_id_of(point) in sweep
