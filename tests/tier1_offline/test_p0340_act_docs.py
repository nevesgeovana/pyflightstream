"""Tier 1, 0.34.0: the measured actuator-disc behaviours are documented, and warned of (FR-332).

Pipeline role: quality gate on four statements of the documentation and on one
plan warning.

A research study of the disc on 26.124, summarised in RPT-137, measured four
behaviours a reader would not assume: the probe velocities of a quasi-steady
run are in the rotating frame of the blade (R1); the disc's swirl is one
global factor (R2); the ELLIPTICAL model placed 0.62 of the thrust asked in
the wake (R3); a RELAXED disc ignored a custom profile and carried about half
of the thrust (R4). Each statement is read on its page, in one paragraph with
its fact and its citation of RPT-137, so a page that drops or changes the fact
fails. The plan warns, and never refuses, on a RELAXED disc whose row names a
profile (R5): the warning names the row, the disc and RPT-137, every point
plans READY, and the plan written is the same bytes as without the warning;
a RIGID disc naming a profile and a RELAXED disc loaded by its thrust are the
controls, and warn of nothing.

What it does NOT check: the measurements themselves. Those are RPT-137's, of
one case on one build.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-332.

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import plan_matrix
from tests.tier1_offline.test_g06_actuator_disc import RECIPES, _profile_workspace

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
ACTUATOR_PAGE = DOCS / "workflow-row-flow-inputs.md"
PROBES_PAGE = DOCS / "sampled-fields.md"
QSTEADY_PAGE = DOCS / "workflow-qsteady-rotor.md"
REPORT = "RPT-137"


def _paragraphs(page: Path) -> list[str]:
    """The page's paragraphs, each joined onto one line, whitespace collapsed."""
    text = page.read_text(encoding="utf-8").replace("\r\n", "\n")
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", text) if block.strip()]


def _the_paragraph(page: Path, anchor: str) -> str:
    found = [paragraph for paragraph in _paragraphs(page) if anchor in paragraph]
    assert len(found) == 1, f"{page.name}: {len(found)} paragraphs say {anchor!r}, one should"
    return found[0]


def _says(page: Path, anchor: str, *facts: str) -> None:
    paragraph = _the_paragraph(page, anchor)
    for fact in (*facts, REPORT):
        assert fact in paragraph, (
            f"{page.name}: the paragraph saying {anchor!r} no longer says {fact!r}: {paragraph}"
        )


@pytest.mark.parametrize("page", [PROBES_PAGE, QSTEADY_PAGE], ids=["probes", "qsteady"])
def test_p0340_act_docs_quasi_steady_probe_velocities_are_in_the_blade_frame(page):
    """P0340-ACT-DOCS, FR-332 R1: the probes page and the quasi-steady page each state that
    the probe velocities of a quasi-steady run are expressed in the rotating frame of the
    blade, with the measured -2.618 and RPT-137."""
    _says(
        page,
        "probe velocities of a quasi-steady run",
        "expressed in the rotating frame of the blade",
        "-2.618",
        "26.124",
    )


def test_p0340_act_docs_the_swirl_is_one_global_factor():
    """P0340-ACT-DOCS, FR-332 R2: the actuator page states that the disc's swirl is one global
    factor and not a radial distribution, citing RPT-137."""
    _says(
        ACTUATOR_PAGE,
        "THE SWIRL IS ONE GLOBAL FACTOR",
        "is one global factor",
        "it is not a radial distribution",
    )


def test_p0340_act_docs_elliptical_placed_0_62_of_the_thrust_in_the_wake():
    """P0340-ACT-DOCS, FR-332 R3: the actuator page states that ELLIPTICAL placed 0.62 of
    the thrust asked in the wake on the one case RPT-137 summarises, a measured value and
    not a guaranteed one."""
    _says(
        ACTUATOR_PAGE,
        "ELLIPTICAL PLACED",
        "0.62 of the thrust asked",
        "26.124",
        "a measured value, not a guaranteed one",
    )


def test_p0340_act_docs_relaxed_ignored_a_custom_profile_and_carried_about_half():
    """P0340-ACT-DOCS, FR-332 R4: the actuator page states that a RELAXED disc ignored a
    custom profile and carried about half of the thrust on the same case, a measured value
    and not a guaranteed one, citing RPT-137."""
    _says(
        ACTUATOR_PAGE,
        "RELAXED IGNORED A CUSTOM PROFILE",
        "gave the same wake for every loading profile",
        "about half of the thrust",
        "a measured value, not a guaranteed one",
        "The plan warns",
    )


def test_p0340_act_docs_the_actuator_page_states_the_hand():
    """P0340-ACT-DOCS with FR-331 R2: the actuator page states that a disc of rpm_sign +1
    swirls the way a rotor of rpm_sign +1 turns, how the script hands the solver the sign,
    and the change from 0.33.0."""
    _says(
        ACTUATOR_PAGE,
        "THE HAND, SINCE 0.34.0",
        "swirls its wake the way a rotor of `rpm_sign = 1` turns",
        "minus the block's sign times the row's speed",
        "Up to 0.33.0 the script handed plus",
    )


RELAXED = 'wake_type = "RELAXED"\n'
RIGID = 'wake_type = "RIGID"\n'
WITH_A_PROFILE = "ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct"
WITH_A_THRUST = "ACTUATOR: PROP / ACTUATOR_RPM: 2400 / ACTUATOR_THRUST: 120"
AS_RECORDS = "ACTUATOR: {ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct}"


def _plan_written(tmp_path: Path, cell: str, wake: str) -> tuple[list[str], list[str], bytes]:
    """Plan a one-row matrix whose disc block states ``wake``; return the plan's warnings
    of this package, the statuses of its points and the bytes of the plan it wrote."""
    workspace, matrix, _ = _profile_workspace(tmp_path, cell)
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + wake, encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            matrix,
            workspace,
            name="disc",
            default_fs_version="26.124",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
        )
    said = [
        str(warning.message)
        for warning in caught
        if issubclass(warning.category, PyflightstreamWarning)
        and "actuator disc" in str(warning.message)
    ]
    assert plan.plan_file is not None
    text = plan.plan_file.read_text(encoding="utf-8")
    root = str(workspace.root)
    for form in (json.dumps(root)[1:-1], root, root.replace("\\", "/")):
        text = text.replace(form, "<ROOT>")
    return said, [str(point.status) for point in plan.points], text.encode("utf-8")


@pytest.mark.parametrize("cell", [WITH_A_PROFILE, AS_RECORDS], ids=["flat", "records"])
def test_p0340_act_docs_the_plan_warns_on_a_relaxed_disc_naming_a_profile(tmp_path, cell):
    """P0340-ACT-DOCS, FR-332 R5: a row whose RELAXED disc names a PROFILE is warned about,
    naming the row, the disc and RPT-137; it is never refused (every point READY), and the
    plan written is the same bytes as the plan of the same row with a RIGID disc, which is
    not warned about."""
    said, statuses, written = _plan_written(tmp_path / "relaxed", cell, RELAXED)
    assert len(said) == 1, said
    assert all(word in said[0] for word in ("'3207'", "'PROP'", "RELAXED", "'prop_ct'", REPORT)), (
        said
    )
    assert statuses == [str(PlanStatus.READY)], statuses
    control, control_statuses, control_written = _plan_written(tmp_path / "rigid", cell, RIGID)
    assert control == [], f"a RIGID disc naming a profile was warned about: {control}"
    assert control_statuses == statuses
    assert written == control_written, "the warning changed the plan the row writes"


def test_p0340_act_docs_a_relaxed_disc_loaded_by_its_thrust_is_not_warned_about(tmp_path):
    """P0340-ACT-DOCS, FR-332 R5 control: a RELAXED disc loaded by its net thrust names no
    profile, and the plan says nothing of it."""
    said, statuses, _ = _plan_written(tmp_path, WITH_A_THRUST, RELAXED)
    assert said == [], said
    assert statuses == [str(PlanStatus.READY)], statuses
