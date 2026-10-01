"""Tier 1: the plan says which family a row's geometry does not carry, and never refuses (FR-320).

The defect, measured on 0.32.0 with a real plan: one pproc declares a
``[[sections.distributions]]`` entry over the families ``Blade1`` to ``Blade5``,
and the same matrix holds sector rows whose mesh carries ``Blade1`` alone and
wheel rows carrying all five. Every row planned READY, the sector scripts cut
one blade and the wheel scripts five, and the plan named no family, no blade
and no skip. A misspelled family in the same list vanished the same way.

The skip is the default and stays one (FR-73): the plan warns, once per
artifact and per missing family, naming the rows, and still plans READY.
Everything here is built from the matrix a user writes and planned through
``plan_matrix``, the call the command line makes.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases._skipped_families import (
    declared_names_the_geometry_lacks,
    names_no_boundary_answers,
)
from pyflightstream.cases.matrix import MATRIX_COLUMNS
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate
from tests.tier1_offline.test_matrix_run import RECIPES, make_library, stage_geometry
from tests.tier1_offline.test_workflows import _saved_simulation

BUILD = "26.124"
FIVE = ["Blade1", "Blade2", "Blade3", "Blade4", "Blade5"]
#: The sector row's mesh: the hub and one blade, which is all a sector carries.
SECTOR = ("3301", "sector.fsm", ["Hub", "Blade1"])
#: The wheel row's mesh: the hub and all five blades.
WHEEL = ("3302", "wheel.fsm", ["Hub", *FIVE])


def sections(families: list[str]) -> str:
    """A pproc of one section distribution over ``families``, in the moment frame."""
    listed = ", ".join(f'"{name}"' for name in families)
    return (
        "[[sections.distributions]]\n"
        f"families = [{listed}]\n"
        'frame = "MRP"\n'
        'planes = ["XZ"]\n'
        "count = 12\n"
    )


def a_campaign(
    tmp_path: Path, families: list[str], rows: list[tuple[str, str, list[str]]]
) -> tuple[CampaignWorkspace, Path]:
    """A workspace and a matrix of ``rows`` (POL, geometry, its boundaries), one pproc."""
    workspace = make_library(tmp_path, register_build=(BUILD, "C:/fs/FS.exe"))
    inputs = workspace.inputs_dir
    for _, geometry, boundaries in rows:
        body = _saved_simulation(tmp_path / geometry, boundaries).read_bytes()
        stage_geometry(workspace, geometry, body=body)
    (inputs / "references" / "r050.toml").write_text(
        "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n", encoding="utf-8"
    )
    (inputs / "pproc" / "p020.toml").write_text(sections(families), encoding="utf-8")
    workspace = CampaignWorkspace(
        workspace.root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )
    lines = [" | ".join(MATRIX_COLUMNS), "-" * 40]
    for pol, geometry, _ in rows:
        cells = {
            "POL": pol,
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Prop",
            "DESCRIPTION": "FAMILIES",
            "FLIGHT_CONDITION": "MACH:0.2, REmi:2.3, ALPHA:sweep",
            "SWEEP_VALUES": "0.0",
            "GEOMETRY": geometry,
            "REF": "r050",
            "SET": "s002",
            "PPROC": "p020",
            "SYMMETRY": "NONE",
            "FS_BUILD": BUILD,
            "WORKFLOW": "steady",
            "VAR_NAMES_VALUES": "",
        }
        lines.append(" | ".join(cells.get(name, "-") for name in MATRIX_COLUMNS))
    path = workspace.root / "families.fs"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return workspace, path


def planned(tmp_path: Path, families: list[str], rows, **kwargs):
    """Plan the matrix and return the plan and the FR-320 warnings it raised."""
    workspace, path = a_campaign(tmp_path, families, rows)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            path,
            workspace,
            name="families",
            default_fs_version=BUILD,
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            write_plan=False,
            **kwargs,
        )
    said = [
        str(item.message)
        for item in caught
        if issubclass(item.category, PyflightstreamWarning) and "FR-320" in str(item.message)
    ]
    return plan, said


@pytest.mark.requirement("FR-320")
def test_a_sector_row_lacking_four_blades_is_named_once_per_blade_fr_320(tmp_path):
    """The measured case: one warning per blade the sector lacks, the wheel named in none."""
    plan, said = planned(tmp_path, FIVE, [SECTOR, WHEEL])
    assert plan.points, "the fixture planned no point at all, so this asserted nothing"
    assert len(said) == 4, said
    for blade, message in zip(FIVE[1:], said, strict=True):
        assert f"cites {blade!r}" in message, message
        assert "section distribution 1" in message
        assert "'p020'" in message, "the warning names the pproc artifact"
        assert repr(SECTOR[0]) in message, "the warning names the row that lacks the blade"
        assert repr(WHEEL[0]) not in message, "a row carrying the blade is named in none"
    assert not any("'Blade1'" in message for message in said), "both rows carry Blade1"


@pytest.mark.requirement("FR-320")
def test_a_mistyped_family_warns_naming_the_word_and_the_row_fr_320(tmp_path):
    """A misspelled member beside a good one used to vanish, the list being non-empty."""
    plan, said = planned(tmp_path, ["Blade1", "Bladee2"], [WHEEL])
    assert len(said) == 1, said
    assert "cites 'Bladee2'" in said[0]
    assert repr(WHEEL[0]) in said[0]
    assert [point.status for point in plan.points] == [PlanStatus.READY] * len(plan.points)


@pytest.mark.requirement("FR-320")
def test_a_row_carrying_every_family_gives_no_warning_fr_320(tmp_path):
    """The control: the same pproc over the wheel alone is silent."""
    plan, said = planned(tmp_path, FIVE, [WHEEL])
    assert plan.points
    assert said == []


@pytest.mark.requirement("FR-320")
def test_the_plan_still_plans_ready_and_refuses_only_when_asked_fr_320(tmp_path):
    """The warning never refuses; the refusal stays FR-73's and is asked for by the run.

    A name no boundary of either mesh answers (``Spinner``) plans READY with one
    warning naming both rows, and BLOCKS both when the run asks for the
    refusal, which is then what the user hears. A numbered blade whose family
    the sector carries is not refused even then, so it is still said.
    """
    plan, said = planned(tmp_path / "skip", ["Blade1", "Spinner"], [SECTOR, WHEEL])
    assert plan.points and not plan.blocked
    assert [point.status for point in plan.points] == [PlanStatus.READY] * len(plan.points)
    assert len(said) == 1 and "cites 'Spinner'" in said[0], said
    assert repr(SECTOR[0]) in said[0] and repr(WHEEL[0]) in said[0]
    refused, said = planned(
        tmp_path / "refuse", ["Blade1", "Spinner"], [SECTOR, WHEEL], ignore_missing_families=False
    )
    assert {point.status for point in refused.points} == {PlanStatus.BLOCKED}
    assert said == [], "a refused row is not also warned about"
    numbered, said = planned(
        tmp_path / "numbered", FIVE, [SECTOR, WHEEL], ignore_missing_families=False
    )
    assert {point.status for point in numbered.points} == {PlanStatus.READY}
    assert len(said) == 4, said


@pytest.mark.requirement("FR-320")
def test_a_numbered_name_is_lacking_where_only_its_family_answers_fr_320():
    """The warning's reading: Blade2 is not carried by a mesh of Blade1, though its family is.

    Through an alias as a rotor's own name is one (the rotor path of a
    ``LOCAL_AXIS`` entry), through a list member, and never for a family word
    with no number, a word that names no set, or a name carried in another case.
    """
    inventory = ["Hub", "Blade1"]
    aliases = {"PROP": ["Hub", *FIVE[:3]]}
    assert declared_names_the_geometry_lacks(
        ["PROP", "Bladee2", "each", "blade1", "Blade"], inventory, aliases
    ) == [("PROP", "Blade2"), ("PROP", "Blade3"), (None, "Bladee2")]
    assert declared_names_the_geometry_lacks("all", inventory, aliases) == []
    assert declared_names_the_geometry_lacks(["Spinner"], inventory, {}) == [(None, "Spinner")]


@pytest.mark.requirement("FR-73")
def test_the_refusals_reading_is_unchanged_by_the_move_fr_320():
    """The refusal still asks the selector: Blade2 answers through its family and passes."""
    inventory = ["Hub", "Blade1"]
    aliases = {"PROP": ["Hub", *FIVE[:3]], "TAIL": ["Fin"]}
    assert names_no_boundary_answers(
        ["PROP", "Bladee2", "Blade2", "TAIL", "each"], inventory, aliases, lambda n: "Blade" in n
    ) == [(None, "Bladee2"), ("TAIL", "Fin")]
