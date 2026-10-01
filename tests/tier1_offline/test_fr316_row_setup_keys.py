"""Tier 1: a matrix row states native setup keys over its preset (FR-316).

The evidence line of FR-316 cites this module (docs/srs/functional-requirements.md).

The rule under test: ``plan`` warns for every row that writes setup keys,
naming the row and the keys; a key the preset does not state is added for that
row only; an equal value is accepted; a different value for a key the preset
states is refused, naming the row, the key and both values. The preset here is
``s002`` of the synthetic library: ``iterations = 800`` and
``convergence = 1e-6``.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import SimCase
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows._solver_settings import _settings
from pyflightstream.script import Script
from pyflightstream.workspace._row_setup import structured_setup_keys
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix


def _row(pol: str, cell: str) -> str:
    """One active steady row naming preset s002, with ``cell`` as its VAR_NAMES_VALUES."""
    return (
        f"{pol} | TestWing | ROW_SETUP | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
        f"| 003 |          | 0 | 1 | {cell}"
    )


def _resolve(tmp_path, *rows: str) -> dict[str, SimCase]:
    workspace = make_library(tmp_path)
    path = write_matrix(tmp_path / "rows.fs", list(rows))
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("| LEGACY ", "| steady "), encoding="utf-8")
    resolved = resolve_matrix(
        path,
        workspace,
        name="rows",
        fs_version="26.124",
        recipes=RECIPES,
        fs_exe="C:/fs/FlightStream.exe",
    )
    return {sim.sim_id: sim for sim in resolved.campaign.sims}


def _settings_lines(case: SimCase) -> list[str]:
    script = Script(version="26.124")
    _settings(case, script)
    return script.render().splitlines()


def test_a_key_the_preset_lacks_is_added_for_that_row_only_and_warned(tmp_path):
    """FR-316: warn-only on a key the preset does not state; the next row keeps its preset."""
    with pytest.warns(PyflightstreamWarning, match=r"POL 9401.*viscous_coupling = ENABLE"):
        cases = _resolve(
            tmp_path,
            _row("9401", "viscous_coupling: ENABLE"),
            _row("9402", ""),
        )
    stated, control = cases["9401"], cases["9402"]
    assert stated.solver.viscous_coupling is True
    assert stated.setup_from_row == {"viscous_coupling": "ENABLE"}
    assert "viscous_coupling" not in stated.variables
    # THE CONTROL: the override does not leak into the next row of the same preset.
    assert control.solver.viscous_coupling is None
    assert control.setup_from_row == {}
    assert "SET_SOLVER_VISCOUS_COUPLING ENABLE" in _settings_lines(stated)
    assert not any("VISCOUS_COUPLING" in line for line in _settings_lines(control))


def test_an_equal_value_is_accepted_with_the_warning(tmp_path):
    """FR-316: warn-only on an equal value, judged by the loader (1e-6 equals 0.000001)."""
    with pytest.warns(PyflightstreamWarning, match=r"POL 9403.*iterations = 800"):
        cases = _resolve(tmp_path, _row("9403", "iterations: 800 / convergence: 0.000001"))
    case = cases["9403"]
    assert case.solver.iterations == 800
    assert case.solver.convergence == pytest.approx(1e-6)
    assert case.setup_from_row == {"iterations": "800", "convergence": "0.000001"}


def test_a_differing_value_for_a_key_the_preset_states_is_refused(tmp_path):
    """FR-316: refused at plan, naming the row, the key and both values."""
    with pytest.raises(MatrixError) as refused:
        _resolve(tmp_path, _row("9404", "iterations: 500"))
    said = str(refused.value)
    assert "9404" in said, said
    assert "iterations = 500" in said, said
    assert "iterations = 800" in said, said
    assert "does not overwrite" in said, said


def test_a_solver_alias_is_a_setup_key_and_follows_the_same_rule(tmp_path):
    """FR-316: NITER, the solver's spelling of iterations, differing from 800, is refused."""
    with pytest.raises(MatrixError, match=r"NITER = 500.*iterations = 800"):
        _resolve(tmp_path, _row("9405", "NITER: 500"))


def test_an_unstated_row_resolves_its_preset_unchanged(tmp_path):
    """FR-316 control: a row stating no setup key carries the preset's own settings object."""
    cases = _resolve(tmp_path, _row("9406", ""))
    case = cases["9406"]
    assert case.setup_from_row == {}
    assert case.solver.iterations == 800
    assert case.solver.viscous_coupling is None


def test_an_unknown_key_is_still_refused(tmp_path):
    """FR-316 control: a key that is neither a run-type key nor a setup field stays refused."""
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import build_script

    cases = _resolve(tmp_path, _row("9407", "viscous_couplingg: ENABLE"))
    with pytest.raises(CampaignConfigError, match="viscous_couplingg"):
        build_script(cases["9407"], Script(version="26.124"))


def test_a_table_valued_key_is_refused_naming_what_a_row_can_carry(tmp_path):
    """FR-316: a cell cannot carry a table, so the key is a preset's only."""
    assert "airfoil_separation" in structured_setup_keys()
    assert "vorticity_drag_families" not in structured_setup_keys()
    with pytest.raises(MatrixError, match=r"airfoil_separation.*cannot carry a table"):
        _resolve(tmp_path, _row("9408", "airfoil_separation: wing"))


def test_a_list_of_names_is_carried_comma_separated(tmp_path):
    """FR-316: a list-valued key is written in the cell as comma-separated names."""
    with pytest.warns(PyflightstreamWarning):
        cases = _resolve(tmp_path, _row("9409", "vorticity_drag_families: wing, tail"))
    assert cases["9409"].solver.vorticity_drag_families == ["wing", "tail"]


def test_one_setting_in_both_vocabularies_is_refused_as_ambiguous(tmp_path):
    """FR-316: SYMMETRY_LOADS (run type) beside symmetry_loads (setup) names one setting twice."""
    with pytest.raises(MatrixError, match=r"ambiguous"):
        _resolve(tmp_path, _row("9410", "SYMMETRY_LOADS: DISABLE / symmetry_loads: ENABLE"))


def test_an_invalid_value_is_refused_by_the_presets_own_loader(tmp_path):
    """FR-316: the value is validated by the loader the preset went through, naming the row."""
    with pytest.raises(MatrixError, match=r"(?s)POL 9411.*farfield_layers"):
        _resolve(tmp_path, _row("9411", "farfield_layers: 9"))


def test_the_row_keys_reach_the_setup_snapshot_of_the_run_record(tmp_path):
    """FR-316: the snapshot the record carries says which effective values came from the row."""
    with pytest.warns(PyflightstreamWarning):
        cases = _resolve(tmp_path, _row("9412", "viscous_coupling: ENABLE"))
    script = Script(version="26.124")
    _settings(cases["9412"], script)
    assert script.solver_setup is not None
    dumped = script.solver_setup.model_dump(mode="json")
    assert dumped["from_row"] == {"viscous_coupling": "ENABLE"}
    assert dumped["flags"]["SET_SOLVER_VISCOUS_COUPLING"]["value"] in (True, "ENABLE")
    # THE CONTROL: a snapshot with nothing from the row serializes without the key.
    bare = Script(version="26.124")
    _settings(_resolve(tmp_path / "b", _row("9413", ""))["9413"], bare)
    assert bare.solver_setup is not None
    assert "from_row" not in bare.solver_setup.model_dump(mode="json")
