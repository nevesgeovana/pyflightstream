"""Tier 1: the per-step exports of the last revolutions or the last steps of a run (FR-415).

A row of ``unsteady_rotor`` may state ``EXPORT_UNSTEADY_LAST_REV: N`` and a row of
``unsteady`` or ``unsteady_rotor`` ``EXPORT_UNSTEADY_LAST_ITER: K``. Either resolves
to the first step ``TIME_ITERATIONS - n + 1`` and from there on is
``EXPORT_UNSTEADY_AFTER_ITER``: the same script, the same counter program, the same
exports. No solver runs; the one stub below runs the registered counter program the
way the solver runs it.
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    PprocSpec,
    RotorBlock,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.workflows import (
    WORKFLOW_KEY,
    build_script,
    unsteady_export_threshold,
)
from pyflightstream.run._actions_counter import render_program, stage_counter
from pyflightstream.script import Script

AFTER_REV = "EXPORT_UNSTEADY_AFTER_REV"
AFTER_ITER = "EXPORT_UNSTEADY_AFTER_ITER"
LAST_REV = "EXPORT_UNSTEADY_LAST_REV"
LAST_ITER = "EXPORT_UNSTEADY_LAST_ITER"
FOUR_KEYS = (AFTER_REV, AFTER_ITER, LAST_REV, LAST_ITER)

_ROTOR = RotorBlock(
    alias="ROTOR",
    x_m=0.1,
    y_m=0.2,
    z_m=0.3,
    axis="X",
    rpm_sign=1,
    diameter_m=3.6576,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _rotor_row(**overrides: str | None) -> SimCase:
    """A rotor row turning three revolutions at ten degrees a step: 108 steps of 36 a turn."""
    variables: dict[str, str] = {
        WORKFLOW_KEY: "unsteady_rotor",
        "VELOCITY": "30.0",
        "RPM": "1200",
        "ROTOR_AXIS": "X",
        "BLADES": "4",
        "DELTA_THETA": "10",
        "REVOLUTIONS": "3",
        "LAST_REVS_AVG": "0.25",
    }
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        rotors={_ROTOR.alias: _ROTOR},
    )


def _non_integer_rotor_row(**overrides: str | None) -> SimCase:
    """A rotor row of 36.4 steps a revolution (60 rev/min, 1/36.4 s a step) and 73 steps."""
    return _rotor_row(
        RPM="60",
        DELTA_THETA=None,
        REVOLUTIONS=None,
        DELTA_TIME="0.0274725275",
        TIME_ITERATIONS="73",
        **overrides,
    )


def _unsteady_row(**overrides: str | None) -> SimCase:
    """A rotorless unsteady row of 480 steps whose averaging window is the whole run."""
    variables: dict[str, str] = {
        WORKFLOW_KEY: "unsteady",
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.00025",
        "TIME_ITERATIONS": "480",
        "LAST_ITERS_AVG": "480",
    }
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7003",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
    )


def _stage(folder: Path, case: SimCase, script: Script) -> dict[str, object]:
    """Park the empty action files the script names, then stage the counter."""
    for name, text in script.pending_action_scripts.items():
        parked = folder / name
        parked.parent.mkdir(parents=True, exist_ok=True)
        parked.write_text(text, encoding="utf-8")
    fields = stage_counter(folder, script, case, "26.124", {})
    assert fields is not None
    return fields


def _first_step(case: SimCase) -> int:
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is not None
    return threshold.first_step


# --- R1: the first step against hand counts -------------------------------------


@pytest.mark.requirement("FR-415")
def test_the_last_revolution_of_three_exports_steps_73_to_108():
    """P0370-S3-LAST-REV (FR-415) R1: 3 revolutions of 36 steps, the last 1 is steps 73 to 108."""
    threshold = unsteady_export_threshold(_rotor_row(**{LAST_REV: "1"}), version="26.124")
    assert threshold is not None
    assert threshold.time_iterations == 108
    assert threshold.first_step == 73
    assert threshold.time_iterations - threshold.first_step + 1 == 36


@pytest.mark.requirement("FR-415")
def test_a_non_integer_product_rounds_the_count_up():
    """P0370-S3-LAST-REV (FR-415) R1: 0.5 revolution of 36.4 steps a turn is n = 19."""
    threshold = unsteady_export_threshold(
        _non_integer_rotor_row(**{LAST_REV: "0.5"}), version="26.124"
    )
    assert threshold is not None
    assert threshold.time_iterations == 73
    assert threshold.time_iterations - threshold.first_step + 1 == 19
    assert threshold.first_step == 55


@pytest.mark.requirement("FR-415")
@pytest.mark.parametrize(
    ("row", "k", "first"),
    [(_unsteady_row, 1, 480), (_unsteady_row, 12, 469), (_rotor_row, 36, 73), (_rotor_row, 108, 1)],
)
def test_the_last_k_steps_start_at_the_run_length_minus_k_plus_one(row, k, first):
    """P0370-S3-LAST-REV (FR-415) R1: ``n = K``, first step ``TIME_ITERATIONS - K + 1``."""
    assert _first_step(row(**{LAST_ITER: str(k)})) == first


# --- R3: the bounds ---------------------------------------------------------------


@pytest.mark.requirement("FR-415")
def test_n_equal_to_the_run_length_is_accepted_and_one_more_is_refused_naming_the_length():
    """P0370-S3-LAST-REV (FR-415) R3: ``n = TIME_ITERATIONS`` is accepted, one more refused."""
    assert _first_step(_unsteady_row(**{LAST_ITER: "480"})) == 1
    with pytest.raises(CampaignConfigError) as refused:
        build_script(_unsteady_row(**{LAST_ITER: "481"}), Script("26.124"))
    message = str(refused.value)
    assert "481" in message and "480" in message, message
    # The revolutions form: 3 revolutions exactly is every step, a hundredth more is not.
    assert _first_step(_rotor_row(**{LAST_REV: "3"})) == 1
    with pytest.raises(CampaignConfigError) as refused:
        build_script(_rotor_row(**{LAST_REV: "3.01"}), Script("26.124"))
    assert "108" in str(refused.value), refused.value


@pytest.mark.requirement("FR-415")
@pytest.mark.parametrize("key", [LAST_ITER, LAST_REV])
@pytest.mark.parametrize("value", ["0", "-2"])
def test_a_value_that_is_not_positive_is_refused_naming_the_key(key, value):
    """P0370-S3-LAST-REV (FR-415) R3: zero and negative counts are refused at plan."""
    with pytest.raises(CampaignConfigError) as refused:
        build_script(_rotor_row(**{key: value}), Script("26.124"))
    message = str(refused.value)
    assert key in message and "positive" in message, message


@pytest.mark.requirement("FR-415")
def test_a_fractional_step_count_is_refused():
    """P0370-S3-LAST-REV (FR-415): the iterations form is a count of steps, as AFTER_ITER is."""
    with pytest.raises(CampaignConfigError, match="fractional"):
        build_script(_unsteady_row(**{LAST_ITER: "2.5"}), Script("26.124"))


@pytest.mark.requirement("FR-415")
def test_the_revolutions_form_without_a_rotor_clock_names_the_iterations_form():
    """P0370-S3-LAST-REV (FR-415) R3: LAST_REV on the run type that turns nothing names LAST_ITER.

    Reached through the resolver on a row that names its run type by recipe (the
    row-key guard refuses it first on a row with a WORKFLOW cell, naming the keys the
    run type registers, LAST_ITER among them), as AFTER_REV is.
    """
    recipe_row = _unsteady_row(**{LAST_REV: "1"})
    del recipe_row.variables[WORKFLOW_KEY]
    with pytest.raises(CampaignConfigError) as refused:
        unsteady_export_threshold(recipe_row, version="26.124")
    message = str(refused.value)
    assert LAST_REV in message and f"'{LAST_ITER}: <steps>'" in message, message
    with pytest.raises(CampaignConfigError) as guarded:
        build_script(_unsteady_row(**{LAST_REV: "1"}), Script("26.124"))
    assert LAST_REV in str(guarded.value) and LAST_ITER in str(guarded.value), guarded.value
    control = _unsteady_row(**{AFTER_REV: "1"})
    del control.variables[WORKFLOW_KEY]
    with pytest.raises(CampaignConfigError) as before:
        unsteady_export_threshold(control, version="26.124")
    assert f"'{AFTER_ITER}: <steps>'" in str(before.value), before.value


# --- R2: at most one of the four --------------------------------------------------


@pytest.mark.requirement("FR-415")
@pytest.mark.parametrize(("first", "second"), list(itertools.combinations(FOUR_KEYS, 2)))
def test_two_threshold_keys_are_refused_naming_both(first, second):
    """P0370-S3-LAST-REV (FR-415) R2: every pair of the four keys is refused, naming both."""
    row = _rotor_row(**{first: "1", second: "1"})
    with pytest.raises(CampaignConfigError) as refused:
        build_script(row, Script("26.124"))
    message = str(refused.value)
    assert first in message and second in message, message
    assert "7001" in message


# --- R5: the averaging window -----------------------------------------------------


def _averaged_rotor_row(**overrides: str | None) -> SimCase:
    """Four revolutions at ten degrees a step (144 steps) averaging the last 54: from step 91."""
    case = _rotor_row(REVOLUTIONS="4", LAST_REVS_AVG="1", **overrides)
    return case.model_copy(
        update={
            "pproc": PprocSpec(time_averaging={"last_iters": 54}),
            "outputs": ["p.txt", "p.dat", "p_log.txt"],
        }
    )


@pytest.mark.requirement("FR-415")
def test_a_first_step_after_the_averaging_window_start_is_refused():
    """P0370-S3-LAST-REV (FR-415) R5: the window starts at step 91, so the last 53 are refused."""
    with pytest.raises(CampaignConfigError, match=r"step 92.*from step 91"):
        build_script(_averaged_rotor_row(**{LAST_ITER: "53"}), Script("26.124"))
    with pytest.raises(CampaignConfigError, match=r"step 109.*from step 91"):
        build_script(_averaged_rotor_row(**{LAST_REV: "1"}), Script("26.124"))
    # The last 54 steps start on the window's first step, a longer span starts before it.
    for accepted in ("54", "60"):
        build_script(_averaged_rotor_row(**{LAST_ITER: accepted}), Script("26.124"))
    assert _first_step(_averaged_rotor_row(**{LAST_ITER: "54"})) == 91


# --- R4: the record ---------------------------------------------------------------


@pytest.mark.requirement("FR-415")
@pytest.mark.parametrize(
    ("row", "form", "value", "first"),
    [
        (lambda: _rotor_row(**{LAST_REV: "1"}), "last_revolutions", 1.0, 73),
        (lambda: _unsteady_row(**{LAST_ITER: "12"}), "last_iterations", 12.0, 469),
        (lambda: _rotor_row(**{AFTER_REV: "1"}), "revolutions", 1.0, 36),
        (lambda: _unsteady_row(**{AFTER_ITER: "12"}), "iterations", 12.0, 12),
    ],
)
def test_the_export_window_states_the_form_the_value_and_the_first_step(
    tmp_path, row, form, value, first
):
    """P0370-S3-LAST-REV (FR-415) R4: ``export_window`` states form, value and first step."""
    case = row()
    script = Script("26.124")
    build_script(case, script)
    window = _stage(tmp_path, case, script)["export_window"]
    assert isinstance(window, dict)
    assert window["stated_form"] == form
    assert window["stated_value"] == value
    assert window["first_step"] == first
    assert window["time_iterations"] == (108 if case.recipe == "unsteady_rotor" else 480)


# --- R1: the rendered script and counter program are those of AFTER_ITER --------


@pytest.mark.requirement("FR-415")
@pytest.mark.parametrize(
    ("last", "after"),
    [
        (lambda: _rotor_row(**{LAST_REV: "1"}), lambda: _rotor_row(**{AFTER_ITER: "73"})),
        (lambda: _rotor_row(**{LAST_ITER: "20"}), lambda: _rotor_row(**{AFTER_ITER: "89"})),
        (lambda: _unsteady_row(**{LAST_ITER: "12"}), lambda: _unsteady_row(**{AFTER_ITER: "469"})),
        (
            lambda: _non_integer_rotor_row(**{LAST_REV: "0.5"}),
            lambda: _non_integer_rotor_row(**{AFTER_ITER: "55"}),
        ),
    ],
)
def test_a_last_row_renders_the_script_and_program_of_after_iter_at_its_first_step(
    tmp_path, last, after
):
    """P0370-S3-LAST-REV (FR-415) R1: byte-equal script, parked file, counter program, exports."""
    rendered = []
    for case in (last(), after()):
        script = Script("26.124")
        build_script(case, script)
        threshold = unsteady_export_threshold(case, version="26.124")
        assert threshold is not None
        rendered.append(
            (
                script.render(),
                dict(script.pending_action_scripts),
                render_program(threshold, interpreter=sys.executable),
                threshold.exports,
                threshold.first_step,
            )
        )
        folder = tmp_path / str(len(rendered))
        _stage(folder, case, script)
        rendered[-1] += ((folder / "actions" / "pfs_unsteady_actions.py").read_text("utf-8"),)
    assert rendered[0] == rendered[1]
    assert f"THRESHOLD = {float(rendered[0][4])!r}" in rendered[0][2], rendered[0][2]
    assert "THRESHOLD_FORM = 'iterations'" in rendered[0][2]


# --- R1: the counter program exports from the first step to the last --------------


@pytest.mark.requirement("FR-415")
def test_the_counter_program_of_a_last_row_exports_the_last_steps_and_no_earlier_one(tmp_path):
    """P0370-S3-LAST-REV (FR-415) R1: run as the solver runs it, the last 4 of 10 steps export."""
    case = _unsteady_row(
        **{LAST_ITER: "4", "TIME_ITERATIONS": "10", "LAST_ITERS_AVG": "10", "DELTA_TIME": "0.01"}
    )
    script = Script("26.124")
    build_script(case, script)
    _stage(tmp_path, case, script)
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is not None and threshold.first_step == 7
    exports_file = Path(tmp_path) / "actions" / "pfs_unsteady_exports.txt"
    seen = []
    for _ in range(10):
        run = subprocess.run(
            [sys.executable, "actions/pfs_unsteady_actions.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        assert run.returncode == 0, run.stderr
        seen.append(exports_file.read_text(encoding="utf-8") != "")
    assert seen == [False] * 6 + [True] * 4, seen


# --- R7: a row stating none of the four keys is as before -----------------------


@pytest.mark.requirement("FR-415")
def test_a_row_stating_none_of_the_four_keys_has_no_threshold_and_a_count_only_program(tmp_path):
    """P0370-S3-LAST-REV (FR-415) R7: no threshold, no exports action, the count-only program."""
    for case in (_rotor_row(), _unsteady_row()):
        assert unsteady_export_threshold(case, version="26.124") is None
        script = Script("26.124")
        build_script(case, script)
        assert script.pending_action_scripts == {}
        assert "export_window" not in _stage(tmp_path, case, script)
