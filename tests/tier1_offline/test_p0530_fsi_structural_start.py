"""P0530-FSI-START (PFS-2185.04): the matrix keys FSI_START_REV and FSI_START_ITER.

A matrix row replaces, for that row only, the input file's ``wake_development_revolutions``
(the rigid wake development before the structural solver starts), as the
``FSI_<PROPERTY>_FACTOR`` keys replace a calibration factor. ``FSI_START_REV`` states revolutions;
``FSI_START_ITER`` states the first time step whose coupling call may write a non-zero field and
becomes revolutions through the row's DELTA_THETA (72 steps a revolution at 5 deg).
"""

from __future__ import annotations

import math
import re
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows._vocabulary import ROW_KEY_MEANINGS
from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi.config import dump_config
from pyflightstream.fsi.loads import SectionFamily, SectionFamilyMap
from pyflightstream.workspace.fsi_setup import FsiSetupError, resolve_row_fsi
from tests.tier1_offline.test_p0370_s6_direct_morphing import (
    LOADS,
    _rotating_config,
    _write_aero_nodes,
)
from tests.tier1_offline.test_workspace_fsi_setup import SUPPLIED

PRINTED_DT_S = 0.004
#: 5 deg a step at the fixture's printed time increment: 72 steps a revolution.
OMEGA_5_DEG_PER_STEP = math.radians(5.0) / PRINTED_DT_S


def _inputs(tmp_path: Path, text: str = SUPPLIED) -> Path:
    target = tmp_path / "fsi" / "f001.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return tmp_path


def _row(**cells: str) -> dict[str, str]:
    return {"FSI": "f001", "DELTA_THETA": "5", **cells}


@pytest.mark.requirement("FR-155")
def test_p0530_start_rev_replaces_the_file_wake_development_for_the_row(tmp_path):
    inputs = _inputs(tmp_path)
    plain = resolve_row_fsi(inputs, _row())
    stated = resolve_row_fsi(inputs, _row(FSI_START_REV="0.5"))
    assert plain.effective.phases.wake_development_revolutions == 1.0
    assert plain.structural_start is None
    assert "structural_start" not in plain.provenance()
    assert stated.effective.phases.wake_development_revolutions == 0.5
    assert stated.base.phases.wake_development_revolutions == 1.0
    record = stated.provenance()["structural_start"]
    assert record["key"] == "FSI_START_REV" and record["value"] == 0.5
    assert record["file_wake_development_revolutions"] == 1.0


@pytest.mark.requirement("FR-155")
def test_p0530_start_iter_becomes_revolutions_through_the_rows_delta_theta(tmp_path):
    inputs = _inputs(tmp_path)
    stated = resolve_row_fsi(inputs, _row(FSI_START_ITER="36"))
    # 36 steps at 5 deg is half a revolution; the start sits half a step short of step 36.
    assert stated.effective.phases.wake_development_revolutions == pytest.approx(35.5 * 5.0 / 360.0)
    assert stated.provenance()["structural_start"]["key"] == "FSI_START_ITER"
    wide = resolve_row_fsi(inputs, {**_row(FSI_START_ITER="36"), "DELTA_THETA": "10"})
    assert wide.effective.phases.wake_development_revolutions == pytest.approx(35.5 * 10.0 / 360.0)


@pytest.mark.requirement("FR-155")
def test_p0530_a_row_with_both_keys_warns_naming_both_and_uses_the_iteration(tmp_path):
    inputs = _inputs(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = resolve_row_fsi(inputs, _row(FSI_START_REV="0.9", FSI_START_ITER="36"))
    said = [
        str(each.message) for each in caught if issubclass(each.category, PyflightstreamWarning)
    ]
    assert len(said) == 1 and "FSI_START_REV" in said[0] and "FSI_START_ITER" in said[0], said
    assert resolved.provenance()["structural_start"]["key"] == "FSI_START_ITER"
    assert resolved.effective.phases.wake_development_revolutions == pytest.approx(
        35.5 * 5.0 / 360.0
    )


@pytest.mark.requirement("FR-155")
@pytest.mark.parametrize("key", ["FSI_START_REV", "FSI_START_ITER"])
@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "abc"])
def test_p0530_a_start_that_is_not_finite_positive_is_refused_as_a_factor_is(tmp_path, key, bad):
    inputs = _inputs(tmp_path)
    with pytest.raises(FsiSetupError, match=key):
        resolve_row_fsi(inputs, _row(**{key: bad}))
    with pytest.raises(FsiSetupError, match="finite positive"):
        resolve_row_fsi(inputs, _row(FSI_BENDING_STIFFNESS_N_M2_FACTOR=bad))


@pytest.mark.requirement("FR-155")
def test_p0530_a_blank_start_cell_states_nothing_and_the_keys_are_in_the_vocabulary(tmp_path):
    inputs = _inputs(tmp_path)
    blank = resolve_row_fsi(inputs, _row(FSI_START_REV="-", FSI_START_ITER=""))
    assert blank.structural_start is None
    assert blank.effective.phases.wake_development_revolutions == 1.0
    assert "FSI_START_REV" in ROW_KEY_MEANINGS and "FSI_START_ITER" in ROW_KEY_MEANINGS
    with pytest.raises(FsiSetupError, match="states no FSI input"):
        resolve_row_fsi(inputs, {"FSI_START_REV": "0.5"})


@pytest.mark.requirement("FR-155")
def test_p0530_start_iter_without_a_step_is_refused_and_delta_time_converts(tmp_path):
    inputs = _inputs(tmp_path)
    with pytest.raises(FsiSetupError, match="DELTA_THETA"):
        resolve_row_fsi(inputs, {"FSI": "f001", "FSI_START_ITER": "36"})
    spinning = SUPPLIED.replace(
        "omega_rad_per_s = 0.0", f"omega_rad_per_s = {OMEGA_5_DEG_PER_STEP}"
    )
    timed = resolve_row_fsi(
        _inputs(tmp_path / "timed", spinning),
        {"FSI": "f001", "DELTA_TIME": str(PRINTED_DT_S), "FSI_START_ITER": "36"},
    )
    assert timed.effective.phases.wake_development_revolutions == pytest.approx(
        35.5 / 72.0, rel=1e-9
    )


# ------------------------------------------------------- through the driver --


def _first_nonzero_call(tmp_path: Path, phases) -> int:
    """The first call whose written field is not zero, driving the unsteady rotor machine."""
    cfg = _rotating_config("direct")
    cfg = cfg.model_copy(
        update={
            "omega_rad_per_s": OMEGA_5_DEG_PER_STEP,
            "time_increment_s": PRINTED_DT_S,
            "phases": phases,
        }
    )
    run_dir = tmp_path
    run_dir.mkdir(parents=True, exist_ok=True)
    dump_config(cfg, run_dir / driver.CONFIG_FILE)
    family = SectionFamilyMap(
        families=[
            SectionFamily(name="blade_1", count=50),
            SectionFamily(name="hub", count=50, is_blade=False),
        ]
    )
    (run_dir / driver.FAMILY_MAP_FILE).write_text(family.model_dump_json(indent=2) + "\n")
    _write_aero_nodes(run_dir, nodes.node_positions(nodes.generate_node_layout(cfg)))
    for call in range(1, 80):
        text = re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{1000 + call}", LOADS)
        (run_dir / driver.LOADS_FILE).write_text(text, encoding="utf-8")
        driver.coupling_step(run_dir)
        written = nodes.read_fsidisp(run_dir / driver.DISPLACEMENT_FILE)
        if np.abs(written).max() > 0.0:
            return call
    raise AssertionError("no call wrote a non-zero field")


@pytest.mark.requirement("FR-155")
def test_p0530_start_rev_half_and_start_iter_36_give_the_same_first_nonzero_call(tmp_path):
    # The study's f203 start of 0.5 revolution at 5 deg a step wrote its first non-zero field
    # at call 36; FSI_START_ITER 36 must give that call and the same one.
    inputs = _inputs(tmp_path / "inputs")
    by_rev = resolve_row_fsi(inputs, _row(FSI_START_REV="0.5")).effective.phases
    by_iter = resolve_row_fsi(inputs, _row(FSI_START_ITER="36")).effective.phases
    first_rev = _first_nonzero_call(tmp_path / "rev", by_rev)
    first_iter = _first_nonzero_call(tmp_path / "iter", by_iter)
    assert first_iter == 36
    assert first_rev == first_iter
