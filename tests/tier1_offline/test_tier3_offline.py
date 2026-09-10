"""The one offline control tier 1 keeps over the tier-3 workspace (GOAL-012,
PFS-2031.06).

Tier 3 is a campaign workspace run on a licensed solver. A clone with no seat
can still tell its matrices are sound: every matrix plans with the package to
READY on every active point, and every script the builders render equals its
golden under ``tests/tier3_licensed/goldens``. A change in the package that
moves one of those scripts is seen here, on the row it moves, before any seat
is spent.

``python -m tests.tier3_licensed.offline --write`` regenerates the goldens
when a script is meant to move.
"""

from __future__ import annotations

import re
import shutil
import sys

import pytest

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases.matrix import _COLUMNS, MatrixError
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import CampaignWorkspace
from tests.tier3_licensed import offline

MATRICES = offline.matrices()


def test_the_tier3_workspace_has_matrices():
    assert MATRICES, "tests/tier3_licensed holds no matrix"


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_every_tier3_matrix_plans_ready(matrix):
    count, rendered = offline.render(matrix)
    assert count >= 1
    assert len(rendered) == count, "a ready point rendered no script"


# --- what the suite's own workspace exercises (OPS-2006.01, PFS-2018.01) -----------


def _rows_of_every_matrix():
    from pyflightstream.cases.matrix import read_matrix

    return [row for matrix in MATRICES for row in read_matrix(matrix)]


def test_every_registered_run_type_plans_from_the_suite_workspace():
    """OPS-2006.01: the suite's shared case inputs are one workspace with a matrix,
    and every registered run type builds its script through that path rather than
    through a hand-built case. Each name of the registry is the WORKFLOW cell of at
    least one active tier-3 row, and every matrix plans READY (the test above)."""
    from pyflightstream.cases.workflows import workflow_names

    named = {row.workflow for row in _rows_of_every_matrix()}
    missing = [name for name in workflow_names() if name not in named]
    assert not missing, (
        f"registered run type(s) no tier-3 row names in WORKFLOW: {missing}; "
        f"the rows name {sorted(named)}"
    )


def test_the_physics_matrix_plans_ready_on_both_geometries():
    """PFS-2018.01: the physics cases that vary mesh density and isolate one solver
    flag are rows of a committed physics matrix, run through the workflow on both
    geometry families, the wing and the rotor blade."""
    from pyflightstream.cases.matrix import read_matrix

    physics = offline.HERE / "matriz_physics.fs"
    rows = read_matrix(physics)
    families = {row.variables.get("GEOMETRY", "").split("_")[1] for row in rows}
    assert {"WING", "BLADE"} <= families, f"the physics matrix names {sorted(families)}"
    count, rendered = offline.render(physics)
    assert count >= len(rows) and len(rendered) == count, "a row is several points, all READY"


def test_the_unsteady_plots_export_is_named_by_the_run_record():
    """PFS-2015.02.01: a row naming an unsteady run type, planned through the
    workflow, declares the plots export among the outputs the record will name;
    the licensed half (the file present at that path after the run) is
    tests/tier3_licensed/test_tour.py::test_every_unsteady_row_left_the_plots_export_its_record_names."""
    from pyflightstream.cases.matrix import read_matrix
    from pyflightstream.cases.workflows import workflow_names

    unsteady = [n for n in workflow_names() if n.startswith("unsteady")]
    assert unsteady, "the registry names no unsteady run type"
    seen = set()
    for matrix in MATRICES:
        rows = {row.pol: row for row in read_matrix(matrix)}
        _, rendered = offline.render(matrix)
        for stem, script in rendered.items():
            pol = stem.split("-", 1)[1].split("_", 1)[0]
            row = rows.get(pol)
            if row is None or row.workflow not in unsteady:
                continue
            seen.add(row.workflow)
            assert "UNSTEADY_SOLVER_EXPORT_PLOTS\n" + stem + "_plots.txt" in script, stem
    assert seen == set(unsteady), f"rendered {sorted(seen)}, registry {unsteady}"


def test_a_row_may_cite_a_boundary_by_its_renamed_name():
    """PFS-2007.01: the inventory sidecar of the renamed wing, read off the saved
    file's own mesh block, carries the name SURFACE_RENAME gave the boundary and not
    the mesh solid's; the pproc artifact p004 cites that name; row 4004 plans READY
    on it (the plans-ready test above). The licensed half is
    tests/tier3_licensed/test_studies.py::test_a_boundary_renamed_before_the_save_reaches_every_export_by_its_new_name."""
    import tomllib

    sidecar = offline.HERE / "inputs" / "geometries" / "14_WING_RENAMED.boundaries.toml"
    inventory = tomllib.loads(sidecar.read_text(encoding="utf-8"))
    assert inventory["boundaries"] == ["MainWing"], inventory
    pproc = tomllib.loads(
        (offline.HERE / "inputs" / "pproc" / "p004.toml").read_text(encoding="utf-8")
    )
    assert pproc["groups"]["1"] == ["MainWing"]
    from pyflightstream.cases.matrix import read_matrix

    rows = {r.pol: r for r in read_matrix(offline.HERE / "matriz_geometry.fs")}
    assert rows["4004"].pproc_code == "p004"
    assert rows["4004"].variables["GEOMETRY"] == "14_WING_RENAMED.fsm"


# --- the refusals, at plan time, over the tier-3 workspace's own library ----------
#
# PFS-2031.05 asked for the refusals as RUN 0 rows of the matrices; the
# reader refuses a malformed row whatever its RUN cell says, so a refusal
# cannot sit in a matrix that must plan READY. They live here instead, as
# one-row matrices planned against a copy of the tier-3 inputs, and they
# cost no seat.

TIER3 = offline.HERE
TOUR = TIER3 / "matriz.fs"


def _tier3_copy(tmp_path, *, with_tour=False):
    """A workspace root holding a copy of the tier-3 inputs, and the tour when asked."""
    root = tmp_path / "ws"
    shutil.copytree(
        TIER3 / "inputs", root / "inputs", ignore=shutil.ignore_patterns("*.local.toml")
    )
    if with_tour:
        shutil.copy(TOUR, root / TOUR.name)
    return root


def _one_row_matrix(root, name, row):
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    path = root / name
    path.write_text("\n".join([header, rule, row]) + "\n", encoding="utf-8")
    return path


def _plan(root, matrix):
    return plan_matrix(
        matrix,
        CampaignWorkspace(root),
        name="refusal",
        default_fs_version="26.120",
        recipes={},
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


STEADY = "MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r001 | s001 | p002 | 26.120 | 0 | 1 | steady | "
ROTOR = (
    "MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r004 | s002 | p001 | 26.120 | 0 | 1 "
    "| unsteady_rotor | "
    "GEOMETRY: 40_PUSHER.fsm / SYMMETRY: NONE / ROTOR_AXIS: X / MOVING_BOUNDARIES: Blade / "
    "DELTA_THETA: 30 / REVOLUTIONS: 0.5 / "
)

REFUSALS = {
    "a geometry the library does not hold": (
        f"7001 | Wing | REFUSED | {STEADY}GEOMETRY: 99_MISSING.fsm / SYMMETRY: NONE",
        ("99_MISSING", "geometries"),
    ),
    "a reference code the library does not hold": (
        "7002 | Wing | REFUSED | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r999 | s001 "
        "| p002 | 26.120 | 0 "
        "| 1 | steady | GEOMETRY: 10_WING.fsm / SYMMETRY: NONE",
        ("r999", "references"),
    ),
    "a rotor hub named by a free point name": (
        f"7003 | Pusher | REFUSED | {ROTOR}RPM: -800 / ROTOR_ORIGIN: HUB",
        ("HUB", "ERP"),
    ),
    "a rotor stating RPM and RPM_SIGN both": (
        f"7004 | Pusher | REFUSED | {ROTOR}RPM: -800 / RPM_SIGN: 1 / ROTOR_ORIGIN: ERP3",
        ("RPM_SIGN",),
    ),
    "a LEGACY row with a bare recipe code and no mapping": (
        "7005 | Wing | REFUSED | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r001 | s001 "
        "| p002 | 26.120 | 0 "
        "| 1 | LEGACY | RECIPE: 003 / GEOMETRY: 10_WING.fsm / OUTPUTS: loads_{point}.txt",
        ("recipe mapping",),
    ),
    "a build the registry does not hold": (
        "7006 | Wing | REFUSED | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r001 | s001 "
        "| p002 | 27.000 | 0 "
        "| 1 | steady | GEOMETRY: 10_WING.fsm / SYMMETRY: NONE",
        ("27.000", "executables.toml"),
    ),
    # PFS-2008.02.01: a key no run type registers planned READY on 2026-09-08,
    # and the run would have spent a seat on a row stating something the
    # script does not carry. The refusal names the row, the key and the keys
    # the run type registers; a key ANOTHER run type registers is named with
    # the run type that reads it.
    "a key no run type registers, on a steady row": (
        f"7007 | Wing | REFUSED | {STEADY}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE / FOO_BAR: 1",
        ("7007", "FOO_BAR", "'steady'", "GEOMETRY", "SYMMETRY"),
    ),
    "a key no run type registers, on a rotor row": (
        f"7008 | Pusher | REFUSED | {ROTOR}RPM: -800 / ROTOR_ORIGIN: ERP3 / FOO_BAR: 1",
        ("7008", "FOO_BAR", "'unsteady_rotor'", "MOVING_BOUNDARIES"),
    ),
    "a key another run type registers, on a steady row": (
        f"7009 | Wing | REFUSED | {STEADY}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE / "
        "WINDOW_DEGREES: 90",
        ("7009", "WINDOW_DEGREES", "'steady'", "unsteady_rotor"),
    ),
}


@pytest.mark.parametrize("case", list(REFUSALS), ids=list(REFUSALS))
def test_the_workspace_refuses_a_row_it_cannot_plan_naming_the_cause(tmp_path, case):
    """A refusal arrives in one of two shapes and both are asserted the same way: the
    resolution raises before any point is planned (a code the library lacks, a point
    name outside the convention), or the point's builder refuses and the plan marks
    the point BLOCKED with the reason (a workflow key the run type cannot honor)."""
    row, fragments = REFUSALS[case]
    root = _tier3_copy(tmp_path)
    matrix = _one_row_matrix(root, "refused.fs", row)
    try:
        plan = _plan(root, matrix)
    except PyflightstreamError as error:
        message = str(error)
    else:
        assert plan.blocked, f"{case}: planned READY"
        message = " ".join(str(point.error) for point in plan.blocked)
    for fragment in fragments:
        assert fragment in message, f"{case}: {message}"


def test_a_row_on_a_second_build_is_pre_flighted_under_that_builds_grammar(tmp_path):
    """The residual PFS-2009.05 left, met on 2026-09-09 while pfs0130 was written: a
    matrix whose default is 26.120 with one row on 26.123 stating the unsteady actions
    was BLOCKED at plan time with CommandNotInVersionError for 26.120, a build the row
    never named, and would have run. The plan reads each build's version off the
    registry, no executable bound, and validates the row against it."""
    root = _tier3_copy(tmp_path)
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    steady = f"1001 | Wing | STEADY | {STEADY}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE"
    actions = next(
        line
        for line in (TIER3 / "matriz_actions.fs").read_text(encoding="utf-8").splitlines()
        if line.startswith("6002 ")
    )
    assert "| 26.123 " in actions and "EXPORT_UNSTEADY_AFTER_ITER" in actions
    matrix = root / "two_builds.fs"
    matrix.write_text("\n".join([header, rule, steady, actions]) + "\n", encoding="utf-8")
    plan = _plan(root, matrix)
    assert not plan.blocked, [(p.run_id, p.error) for p in plan.blocked]


def test_a_legacy_row_with_a_recipe_keeps_its_free_keys(tmp_path):
    """PFS-2008.02.01, the other half: a LEGACY row's recipe is the reader of its
    keys, so the tour's own LEGACY row (1090) with FOO_BAR appended plans READY."""
    from pyflightstream.cases.matrix import read_matrix

    legacy = [row for row in read_matrix(TOUR) if row.workflow == "LEGACY"]
    assert legacy, "the tour holds no LEGACY row"
    line = next(
        text
        for text in TOUR.read_text(encoding="utf-8").splitlines()
        if text.startswith(legacy[0].pol)
    )
    root = _tier3_copy(tmp_path)
    matrix = _one_row_matrix(
        root, "legacy.fs", line.replace(legacy[0].pol, "7090", 1) + " / FOO_BAR: 1"
    )
    plan = _plan(root, matrix)
    assert not plan.blocked, f"a LEGACY row lost its free keys: {plan.summary()}"


def _pproc(root, name, text):
    """One more pproc artifact in the copied library, written as a user writes it."""
    path = root / "inputs" / "pproc" / f"{name}.toml"
    path.write_text(text, encoding="utf-8")
    return path


WING_ROW = (
    "MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | r001 | s001 | {pproc} | 26.120 | 0 | 1 | steady | "
)


def test_a_pproc_group_named_by_a_word_is_refused_at_plan_time(tmp_path):
    """PFS-2032.03: `polar_file_name` writes the group NUMBER into the polar table's
    name, so a group named `wing` crashed the whole products stage with a bare
    ValueError after the seat was spent; measured planning READY on 2026-09-08.
    The refusal names the artifact, the key and the polar table the number is for."""
    root = _tier3_copy(tmp_path)
    _pproc(root, "p006", '[groups]\n"wing" = ["Wing"]\n')
    matrix = _one_row_matrix(
        root,
        "word.fs",
        f"7106 | Wing | REFUSED | {WING_ROW.format(pproc='p006')}GEOMETRY: 10_WING.fsm / "
        "SYMMETRY: NONE",
    )
    with pytest.raises(PyflightstreamError) as caught:
        _plan(root, matrix)
    message = str(caught.value)
    assert "p006" in message and "wing" in message and "polar" in message, message


def test_a_top_level_base_regions_list_is_the_documented_off_switch(tmp_path):
    """PFS-2005.04: the docs page shows `base_regions = [...]` at the top level of the
    pproc artifact, and the reader refused exactly that form as an old-shape groups
    file (measured 2026-09-08). The empty list is the documented off switch and
    plans READY; a list naming a family reaches the script as one
    DETECT_BASE_REGIONS_BY_SURFACE per boundary of it."""
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from pyflightstream.workspace.matrix import resolve_matrix

    root = _tier3_copy(tmp_path)
    _pproc(root, "p007", 'base_regions = []\n\n[groups]\n"1" = ["Wing"]\n')
    matrix = _one_row_matrix(
        root,
        "off.fs",
        f"7107 | Wing | READY | {WING_ROW.format(pproc='p007')}GEOMETRY: 10_WING.fsm / "
        "SYMMETRY: NONE",
    )
    plan = _plan(root, matrix)
    assert not plan.blocked, plan.summary()
    _pproc(root, "p008", 'base_regions = ["Base"]\n\n[groups]\n"1" = ["Body"]\n')
    body = _one_row_matrix(
        root,
        "on.fs",
        f"7108 | Body | READY | {WING_ROW.format(pproc='p008')}GEOMETRY: 20_BODY.fsm / "
        "SYMMETRY: NONE",
    )
    resolved = resolve_matrix(
        body, CampaignWorkspace(root), name="switch", fs_version="26.120", recipes={}
    )
    assert resolved.pprocs["p008"].base_regions == ["Base"]
    script = Script("26.120")
    build_script(resolved.campaign.sims[0].model_copy(update={"point": {"alpha": 0.0}}), script)
    detected = [line for line in script.render().splitlines() if "DETECT_BASE_REGIONS" in line]
    assert detected == ["DETECT_BASE_REGIONS_BY_SURFACE 2"], script.render()


# --- PFS-2028.00: names, not indices, on every boundary-citing surface ----------


def _rotor_row(pol, cell):
    return f"{pol} | Pusher | PFS-2028 | {ROTOR.replace('MOVING_BOUNDARIES: Blade', cell)}RPM: -800"


def _moving_payload(root, matrix):
    """The SET_MOTION_BOUNDARIES payload of a one-row matrix, rendered as the plan renders it."""
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from pyflightstream.workspace.matrix import resolve_matrix

    resolved = resolve_matrix(
        matrix, CampaignWorkspace(root), name="names", fs_version="26.120", recipes={}
    )
    script = Script("26.120")
    build_script(resolved.campaign.sims[0].model_copy(update={"point": {"alpha": 0.0}}), script)
    lines = script.render().splitlines()
    at = next(index for index, line in enumerate(lines) if line.startswith("SET_MOTION_BOUNDARIES"))
    return lines[at + 1]


@pytest.mark.requirement("FR-30b")
def test_a_rotor_row_cites_its_moving_boundaries_by_name_at_the_matrix_surface(tmp_path):
    """FR-30b at the surface it claims, which is a matrix row against a staged
    geometry and its inventory sidecar: `MOVING_BOUNDARIES: Blade1,S` on the pusher
    row is refused because 40_PUSHER carries Body, Base and Blade1 and no S, and the
    refusal names the file, the sidecar and what it declares; `Blade1` alone is
    accepted and resolves to the position the sidecar holds it at; a position still
    works. The script-layer half is tests/tier1_offline/test_script_entities.py."""
    root = _tier3_copy(tmp_path)
    refused = _one_row_matrix(root, "s.fs", _rotor_row("7201", "MOVING_BOUNDARIES: Blade1,S"))
    plan = _plan(root, refused)
    assert plan.blocked, "a name the inventory lacks planned READY"
    message = str(plan.blocked[0].error)
    for fragment in ("7201", "'S'", "40_PUSHER.fsm", "40_PUSHER.boundaries.toml", "'Blade1'"):
        assert fragment in message, message
    named = _one_row_matrix(root, "n.fs", _rotor_row("7202", "MOVING_BOUNDARIES: Blade1"))
    assert _moving_payload(root, named) == "3", "Blade1 is the third boundary of 40_PUSHER"
    with pytest.warns(PyflightstreamWarning, match="POSITION"):
        positional = _one_row_matrix(root, "p.fs", _rotor_row("7203", "MOVING_BOUNDARIES: 3"))
        assert _moving_payload(root, positional) == "3"


def test_moving_boundaries_may_name_a_group_of_the_pproc_artifact(tmp_path):
    """PFS-2028.00: MOVING_BOUNDARIES accepts a group of the row's pproc artifact as
    g<number>, resolved to the members the geometry carries. Group 4 of p001 is
    Blade1 and Blade2; the pusher carries Blade1, so the cell moves boundary 3."""
    root = _tier3_copy(tmp_path)
    grouped = _one_row_matrix(root, "g.fs", _rotor_row("7204", "MOVING_BOUNDARIES: g4"))
    assert _moving_payload(root, grouped) == "3"
    # Group 2 of p001 is Wing, which the pusher does not carry: a group that
    # names nothing the geometry holds is refused, not silently emptied.
    empty = _one_row_matrix(root, "e.fs", _rotor_row("7205", "MOVING_BOUNDARIES: g2"))
    plan = _plan(root, empty)
    assert plan.blocked, "a group naming nothing the geometry carries planned READY"
    message = str(plan.blocked[0].error)
    for fragment in ("7205", "g2", "p001", "'Wing'", "40_PUSHER.fsm", "'Blade1'"):
        assert fragment in message, message


def test_moving_boundaries_may_name_an_alias_of_the_setup(tmp_path):
    """The author's decision of 2026-09-09: an alias defined in the row's setup is read
    wherever a boundary is cited. `rotor = ["Blade", "Spinner"]` on a copy of the
    unsteady preset resolves to Blade1 of 40_PUSHER, the third boundary, and the
    member the file lacks is ignored; an alias no member of which the file
    carries is refused as a name the inventory lacks, naming the alias."""
    root = _tier3_copy(tmp_path)
    # THE TABLE LIVES IN THE REFERENCE SINCE 0.15.0 (FR-59): a boundary
    # name is a property of the configuration and a preset is per
    # condition, so the preset stating one is refused. The row is unchanged
    # and cites the setup it always did.
    reference = root / "inputs" / "references" / "r004.toml"
    reference.write_text(
        reference.read_text(encoding="utf-8").replace(
            "[aliases]\n",
            '[aliases]\nrotor = ["Blade", "Spinner"]\nghost = ["Spinner"]\n',
            1,
        ),
        encoding="utf-8",
    )
    aliased = _one_row_matrix(
        root,
        "alias.fs",
        _rotor_row("7209", "MOVING_BOUNDARIES: rotor"),
    )
    assert not _plan(root, aliased).blocked
    assert _moving_payload(root, aliased) == "3"
    ghost = _one_row_matrix(
        root,
        "ghost.fs",
        _rotor_row("7210", "MOVING_BOUNDARIES: ghost"),
    )
    plan = _plan(root, ghost)
    assert plan.blocked, "an alias resolving to nothing planned READY"
    assert "ghost" in str(plan.blocked[0].error)


def test_moving_boundaries_naming_an_empty_group_moves_every_boundary(tmp_path):
    """The author's decision of 2026-09-09 (PFS-2005.02): a group written empty is every
    family the geometry carries, so `MOVING_BOUNDARIES: g1` against an artifact
    whose group 1 is `[]` moves every boundary of 40_PUSHER, the three of its
    inventory, and the artifact plans READY although it cites no name."""
    root = _tier3_copy(tmp_path)
    _pproc(root, "p001", '[groups]\n"1" = []\n')
    every = _one_row_matrix(root, "all.fs", _rotor_row("7208", "MOVING_BOUNDARIES: g1"))
    assert not _plan(root, every).blocked, "an empty group is every family and plans READY"
    assert _moving_payload(root, every) == "1,2,3"


def test_a_pproc_artifact_naming_nothing_the_geometry_carries_is_refused_at_plan(tmp_path):
    """PFS-2028.00, the RED of RPT-044: a group citing the mesh solid name `Wing`
    against 14_WING_RENAMED.fsm, whose inventory carries MainWing only, planned
    READY on 2026-09-09 because a steady row's groups resolve at products time.
    An artifact none of whose cited names the opened geometry carries is refused
    at plan time naming the row, the artifact, the names, the file and its
    inventory. The tier-3 artifacts are shared across geometries and a member
    the file lacks is left out by design, so a member missing from ONE group is
    not what is refused (p002's group 3 is Body and Base, and the wing rows plan
    READY with it): the refusal is the artifact and the geometry sharing no name."""
    root = _tier3_copy(tmp_path)
    _pproc(root, "p005", '[groups]\n"1" = ["Wing"]\n')
    matrix = _one_row_matrix(
        root,
        "renamed.fs",
        f"7206 | Wing | RPT-044 | {WING_ROW.format(pproc='p005')}"
        "GEOMETRY: 14_WING_RENAMED.fsm / SYMMETRY: NONE",
    )
    plan = _plan(root, matrix)
    assert plan.blocked, "the mesh solid name against the renamed file planned READY"
    message = str(plan.blocked[0].error)
    for fragment in ("7206", "p005", "'Wing'", "14_WING_RENAMED.fsm", "'MainWing'"):
        assert fragment in message, message
    # The same artifact against the file whose inventory carries Wing plans READY.
    plain = _one_row_matrix(
        root,
        "plain.fs",
        f"7207 | Wing | RPT-044 | {WING_ROW.format(pproc='p005')}"
        "GEOMETRY: 10_WING.fsm / SYMMETRY: NONE",
    )
    assert not _plan(root, plain).blocked


def test_an_empty_group_does_not_disable_the_shares_no_name_refusal(tmp_path):
    """The interface lens of 2026-09-09: `if not members: return` returned from the
    FUNCTION, so one empty group anywhere in an artifact disabled the RPT-044 guard
    for every other group in it; an artifact holding `"1" = []` and `"2" = ["Wing"]`
    against 14_WING_RENAMED, whose inventory carries MainWing, planned READY and
    every group-2 polar would have summed nothing."""
    root = _tier3_copy(tmp_path)
    _pproc(root, "p007", '[groups]\n"1" = []\n"2" = ["Wing"]\n')
    matrix = _one_row_matrix(
        root,
        "empty_and_named.fs",
        f"7211 | Wing | RPT-044 | {WING_ROW.format(pproc='p007')}"
        "GEOMETRY: 14_WING_RENAMED.fsm / SYMMETRY: NONE",
    )
    plan = _plan(root, matrix)
    assert plan.blocked, "an empty group beside a named one disabled the guard"
    message = str(plan.blocked[0].error)
    for fragment in ("7211", "p007", "'Wing'", "14_WING_RENAMED.fsm", "'MainWing'"):
        assert fragment in message, message


def test_an_artifact_whose_only_group_is_empty_plans_ready_against_any_geometry(tmp_path):
    """The author's decision of 2026-09-09 read at the guard: an empty group is every family
    and resolves by construction, so an artifact that cites no name at all is not
    the artifact-and-geometry-share-no-name case (RPT-044) and plans READY against
    the renamed file, where a group citing `Wing` is refused. A survived mutant of
    the QA lens of the same day: nothing held the by-construction reading."""
    root = _tier3_copy(tmp_path)
    _pproc(root, "p009", '[groups]\n"1" = []\n')
    matrix = _one_row_matrix(
        root,
        "only_empty.fs",
        f"7213 | Wing | RPT-044 | {WING_ROW.format(pproc='p009')}"
        "GEOMETRY: 14_WING_RENAMED.fsm / SYMMETRY: NONE",
    )
    assert not _plan(root, matrix).blocked, "an artifact citing no name was refused"


def test_the_refusal_cites_the_word_the_artifact_writes_not_the_alias_members(tmp_path):
    """The interface lens of 2026-09-09: the guard substituted the alias MEMBERS
    into its message, so it reported names the user never wrote and could not find
    in the file, and it looked them up without case folding while every other site
    folds. The artifact writes `wing`; the message says `wing`."""
    root = _tier3_copy(tmp_path)
    # THE ALIAS LIVES IN THE REFERENCE SINCE 0.15.0 (FR-59), joining the
    # table the file already declares; the row cites the setup it always did.
    reference = root / "inputs" / "references" / "r001.toml"
    reference.write_text(
        reference.read_text(encoding="utf-8").replace(
            "[aliases]\n", '[aliases]\nwing = ["Wing"]\n', 1
        ),
        encoding="utf-8",
    )
    _pproc(root, "p008", '[groups]\n"1" = ["wing"]\n')
    matrix = _one_row_matrix(
        root,
        "aliased_renamed.fs",
        f"7212 | Wing | RPT-044 | {WING_ROW.format(pproc='p008')}"
        "GEOMETRY: 14_WING_RENAMED.fsm / SYMMETRY: NONE",
    )
    plan = _plan(root, matrix)
    assert plan.blocked, "the alias resolving to nothing planned READY"
    message = str(plan.blocked[0].error)
    assert "'wing'" in message, f"the word the file writes: {message}"
    assert "'Wing'" not in message, f"the alias's member, which the file never writes: {message}"
    assert "MainWing" in message, message


def test_the_workspace_refuses_a_pol_the_tour_already_states(tmp_path):
    root = _tier3_copy(tmp_path, with_tour=True)
    matrix = _one_row_matrix(
        root, "second.fs", f"1001 | Wing | REFUSED | {STEADY}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE"
    )
    with pytest.raises(PyflightstreamError) as caught:
        _plan(root, matrix)
    message = str(caught.value)
    assert "1001" in message and "matriz.fs" in message and "second.fs" in message, message


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_every_tier3_script_equals_its_golden(matrix):
    """The golden is the PLAN-TIME render of the builders (offline.py says how it
    differs from the bytes the solver receives); this pins what a row's cells make
    the builders emit, and an orphan golden is a row that no longer exists."""
    # A COMPARISON OF NOTHING IS NOT A COMPARISON. The three arms below
    # catch a drop, a difference and a stale golden, and all three are
    # satisfied by a matrix that rendered no point at all: `count` was only
    # ever interpolated into a failure message. Measured on this tree, the
    # seven matrices render 18, 2, 2, 4, 11, 4 and 8, so the arm is not
    # inert today and nothing held it there (the QA lens of the 0.15.0
    # release review).
    count, absent, differ, orphans = offline.compare(matrix)
    assert count, f"{matrix.name} rendered no script, so this case compared nothing"
    assert not absent, (
        f"{len(absent)} of {count} scripts have no golden: {absent[:4]}; regenerate with "
        "python -m tests.tier3_licensed.offline --write"
    )
    assert not differ, (
        f"{len(differ)} of {count} scripts differ from their golden: {differ[:4]}; a moved "
        "script is either a defect or a golden to regenerate, and the diff says which"
    )
    assert not orphans, f"goldens of no rendered point: {orphans[:4]}; delete them"


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_no_golden_carries_a_machine_path(matrix):
    """Review round two of 2026-09-08 (QA lens, F5): ``offline.portable`` rewrites
    the separators of a line that STARTS with the placeholder, so a builder that
    one day put a path inline after a keyword would leave a backslash the golden
    control never sees. This asserts the property the normalization is for: no
    golden carries a backslash or a drive letter anywhere."""
    folder = offline.GOLDENS / matrix.stem
    bad = []
    for golden in sorted(folder.glob("*.txt")):
        for number, line in enumerate(golden.read_text(encoding="utf-8").splitlines(), 1):
            if "\\" in line or re.search(r"\b[A-Za-z]:[/\\]", line):
                bad.append(f"{golden.name}:{number}: {line.strip()[:60]}")
    assert not bad, f"{len(bad)} golden line(s) carry a machine path: {bad[:4]}"


# --- the probe's verdict discriminates its two worlds (review of 2026-09-08) --------


def test_the_probe_verdict_says_no_when_only_the_registration_text_ever_ran(tmp_path):
    """The solver stamps _iteration=N on every export an action makes, so the
    registration-time export of a NO world is probe_export_initial_iteration=N.txt
    and not probe_export_initial.txt; a verdict that told the two worlds apart by
    that literal name scored the NO world as YES."""
    from tests.tier3_licensed import actions_probe

    def world(name, exports):
        sim = tmp_path / name
        sim.mkdir()
        (sim / "actions_probe.log").write_text("{}\n" * 8, encoding="utf-8")
        for export in exports:
            (sim / export).write_text("", encoding="utf-8")
        return sim

    yes = world("yes", [f"probe_export_{n:03d}_iteration={n}.txt" for n in range(1, 9)])
    no = world("no", [f"probe_export_initial_iteration={n}.txt" for n in range(1, 9)])
    none = world("none", [])
    assert actions_probe.verdict(yes)["verdict"] == "YES"
    assert actions_probe.verdict(no)["verdict"] == "NO"
    assert actions_probe.verdict(none)["verdict"] == "NONE"
    silent = tmp_path / "silent"
    silent.mkdir()
    assert actions_probe.verdict(silent)["verdict"] == "NOT_RUN"


def test_a_nonzero_sideslip_under_mirror_symmetry_is_refused_at_plan_time(tmp_path):
    """PFS-2005.09, met by pfs0130 on the published 0.13.0 (2026-09-09): row 4207, a
    sideslip sweep of -4, 0, 4 deg on a mirrored half wing-body, planned READY, ran
    three seats, and the solver ran every point at zero sideslip, saying so only in
    the log; two of three points were recorded FAILED_INCOMPLETE_OUTPUT because the
    export was evidence of another operating point. RED on 7b20deb: three READY."""
    root = _tier3_copy(tmp_path)
    sweep = STEADY.replace("ALPHA:sweep | 0.0 |", "BETA:sweep | -4,0,4 |")
    assert sweep != STEADY
    mirrored = _one_row_matrix(
        root,
        "yawed_mirror.fs",
        f"4207 | Wing | YAWED | {sweep}GEOMETRY: 10_WING.fsm / SYMMETRY: MIRROR",
    )
    plan = _plan(root, mirrored)
    blocked = {p.run_id: p.error for p in plan.blocked}
    assert set(blocked) == {"refusal/sim_4207/b-04.0", "refusal/sim_4207/b+04.0"}, plan.summary()
    for run_id, error in blocked.items():
        stated = "-4.0000 deg" if run_id.endswith("b-04.0") else "+4.0000 deg"
        assert "SYMMETRY: MIRROR" in error, error
        assert stated in error, (run_id, error)
        assert "SYMMETRY: NONE" in error, (
            "the refusal does not name the cell that lets the sweep run"
        )
    assert len(plan.ready) == 1, "the zero-sideslip point of the same row is not refused"
    # The cell as a user may spell it: the reader folds nothing, the refusal does.
    lower = _one_row_matrix(
        root,
        "yawed_mirror_lower.fs",
        f"4209 | Wing | YAWED | {sweep}GEOMETRY: 10_WING.fsm / SYMMETRY: mirror",
    )
    plan = _plan(root, lower)
    assert len(plan.blocked) == 2, plan.summary()
    full = _one_row_matrix(
        root,
        "yawed_full.fs",
        f"4208 | Wing | YAWED | {sweep}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE",
    )
    plan = _plan(root, full)
    assert not plan.blocked, plan.summary()


def test_a_row_on_a_second_build_is_run_under_that_builds_grammar(tmp_path, monkeypatch):
    """PFS-2009.05.02: the residual PFS-2009.05.01 left on the run path, met by
    pfs0130 on the published 0.13.0 (2026-09-09): `pyfs-matrix plan` said READY and
    `pyfs-matrix run` refused the same matrix, whole, with CommandNotInVersionError
    for 26.120 on the row that named 26.123, so nothing ran. RED on 7b20deb:
    MatrixError, pre-flight blocked 1 matrix point(s)."""
    from pyflightstream.run import LoadsAssessor, LocalExecutor
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_qa_matrix import STUB_PPROC, STUB_SOLVER

    root = _tier3_copy(tmp_path)
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    steady = f"1001 | Wing | STEADY | {STEADY}GEOMETRY: 10_WING.fsm / SYMMETRY: NONE"
    actions = next(
        line
        for line in (TIER3 / "matriz_actions.fs").read_text(encoding="utf-8").splitlines()
        if line.startswith("6002 ")
    )
    matrix = root / "two_builds.fs"
    matrix.write_text("\n".join([header, rule, steady, actions]) + "\n", encoding="utf-8")
    # The stand-in solver writes the loads table alone, so the artifacts the
    # two rows cite declare no other export (test_qa_matrix's STUB_PPROC).
    for artifact in ("p001", "p002"):
        (root / "inputs" / "pproc" / f"{artifact}.toml").write_text(STUB_PPROC, encoding="utf-8")
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB_SOLVER, encoding="utf-8")
    loads = TIER3.parent / "tier1_offline" / "fixtures" / "loads_steady_26.120.txt"

    class StubSolver(LocalExecutor):
        def __init__(self, *args, **kwargs):
            super().__init__(fs_exe=sys.executable, hidden=True)

        def _argv(self, script_path):
            return [sys.executable, str(stub), str(script_path), str(loads)]

    monkeypatch.setattr("pyflightstream.run.matrix.LocalExecutor", StubSolver)
    records = run_matrix(
        matrix,
        CampaignWorkspace(root),
        name="two_builds",
        default_fs_version="26.120",
        recipes={},
        recipe_registry=workflow_registry(),
        assess=LoadsAssessor(),
    )
    by_sim = {record.sim_id: record for record in records}
    assert set(by_sim) == {"1001", "6002"}, sorted(by_sim)
    assert by_sim["6002"].fs_version_requested == "26.123"
    assert by_sim["6002"].fs_version_source == "row"
    assert by_sim["1001"].fs_version_requested == "26.120"


def _rendered(root, matrix):
    """The dry-run scripts of a matrix over ``root``, by point stem.

    The hook the offline renderer of tier 3 uses, so a test reads what the
    solver would receive rather than what a builder was told.
    """
    import pyflightstream.run as prun
    from pyflightstream.script import Script

    rendered = {}
    original = prun._plan_point

    def hooked(campaign, case, point, ws, recipe, case_error, recorded, *, fs_version):
        plan = original(
            campaign, case, point, ws, recipe, case_error, recorded, fs_version=fs_version
        )
        if plan.status.name in ("READY", "ALREADY_RECORDED") and recipe is not None:
            stem, outputs = prun._point_names(campaign, case, point, ws)
            script = Script(version=fs_version)
            recipe(case.model_copy(update={"point": dict(point), "outputs": outputs}), script)
            rendered[stem] = script.render()
        return plan

    prun._plan_point = hooked
    try:
        plan = _plan(root, matrix)
    finally:
        prun._plan_point = original
    return plan, rendered


def test_a_setup_with_frames_renders_them_after_the_packages_own_and_before_the_motion(tmp_path):
    """PFS-2034.01: a rotor row citing a setup that defines NAC has the frame created
    after ROTOR_MRP and before the motion; a row citing the plain setup renders no
    extra frame (the goldens are the control). RED on b376b14: the setup is refused
    as stating a key naming no setting."""
    root = _tier3_copy(tmp_path)
    # A COORDINATE SYSTEM IS GEOMETRIC DATA and lives in the reference
    # since 0.15.0 (FR-72), so the frame is declared there and the row
    # cites the setup it always did.
    reference = root / "inputs" / "references" / "r003.toml"
    reference.write_text(
        reference.read_text(encoding="utf-8").rstrip("\n")
        + '\n\n[[frames]]\nname = "NAC"\norigin = [0.4, 0.0, 0.1]\n',
        encoding="utf-8",
    )
    rotor = next(
        line
        for line in TOUR.read_text(encoding="utf-8").splitlines()
        if "| unsteady_rotor " in line
    )
    cells = rotor.split("|")
    matrix = _one_row_matrix(root, "frames.fs", "|".join(cells))
    plan, rendered = _rendered(root, matrix)
    assert not plan.blocked, plan.summary()
    lines = next(iter(rendered.values())).splitlines()
    # A frame is a keyword block: EDIT_COORDINATE_SYSTEM, then FRAME n, then NAME.
    edits = [i for i, line in enumerate(lines) if line == "EDIT_COORDINATE_SYSTEM"]
    names = [lines[i + 2].split(" ", 1)[1] for i in edits]
    assert names[:3] == ["MRP", "NAC", "ROTOR_SMRP"], names
    named = lines.index("NAME NAC")
    motion = next(i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_MOTION"))
    assert named < motion, "the setup's frame must exist before the motion is created"


ROTATE_TWO = (
    " / ROTATE: {ANGLE: 3 / AXIS: NAC-Y / ALIAS: ROTOR}, {ANGLE: -2 / AXIS: NAC-Z / ALIAS: ROTOR}"
)


def _rotor_row_on_a_setup_with_nac(tmp_path, tail):
    """The tour's first rotor row on setup s090, which defines frame NAC, plus ``tail``."""
    root = _tier3_copy(tmp_path)
    # A COORDINATE SYSTEM IS GEOMETRIC DATA and lives in the reference
    # since 0.15.0 (FR-72), so the frame is declared there and the row
    # cites the setup it always did.
    reference = root / "inputs" / "references" / "r003.toml"
    reference.write_text(
        reference.read_text(encoding="utf-8").rstrip("\n")
        + '\n\n[[frames]]\nname = "NAC"\norigin = [0.4, 0.0, 0.1]\n',
        encoding="utf-8",
    )
    rotor = next(
        line
        for line in TOUR.read_text(encoding="utf-8").splitlines()
        if "| unsteady_rotor " in line
    )
    cells = rotor.split("|")
    return root, _one_row_matrix(root, "rotate.fs", "|".join(cells).rstrip() + tail)


def test_a_rotor_row_rotating_its_blades_renders_the_rotations_after_the_frames_before_the_motion(
    tmp_path,
):
    """PFS-2034.02, the author's design of 2026-09-09: two ROTATE records are two rotations
    in the order written, each about the named axis of the setup's frame, emitted
    after every frame exists and before the motion is created; ROTOR_MRP, named
    as an auxiliary, is rotated with the mesh and so are the blade axis frames the
    package derived from it. RED on bf9fe31: BLOCKED as a key of no run type."""
    root, matrix = _rotor_row_on_a_setup_with_nac(tmp_path, ROTATE_TWO)
    plan, rendered = _rendered(root, matrix)
    assert not plan.blocked, plan.summary()
    lines = next(iter(rendered.values())).splitlines()
    nac = int(lines[lines.index("NAME NAC") - 1].split()[1])
    prop = int(lines[lines.index("NAME ROTOR_SMRP") - 1].split()[1])
    frames = [
        i
        for i, line in enumerate(lines)
        if line in ("EDIT_COORDINATE_SYSTEM", "CREATE_NEW_COORDINATE_SYSTEM")
    ]
    # On 26.120 the rotation is the keyword block SURFACE_ROTATE: FRAME, AXIS, ANGLE, ...
    rotations = [i for i, line in enumerate(lines) if line == "SURFACE_ROTATE"]
    assert len(rotations) == 2, [line for line in lines if "ROTATE" in line]
    first, second = (lines[i + 1 : i + 4] for i in rotations)
    assert first == [f"FRAME {nac}", "AXIS Y", "ANGLE 3.0"], first
    assert second == [f"FRAME {nac}", "AXIS Z", "ANGLE -2.0"], second
    motion = next(i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_MOTION"))
    # THE COPY A ROTATION KEEPS IS CREATED BY THE ROTATION, so it is the
    # one frame that legitimately follows the first: <ALIAS>_SMRP_ORIGINAL
    # is the rotor's hub before anything turned it (FR-71).
    kept = [i for i in frames if any(line.endswith("_ORIGINAL") for line in lines[i : i + 5])]
    assert kept, "no frame is the rotation's kept copy, so this filter proves nothing"

    assert max(i for i in frames if i not in kept) < rotations[0] < rotations[1] < motion, (
        frames,
        rotations,
        motion,
    )
    # A frame rotation is a keyword block: FRAME, ROTATION_FRAME, ROTATION_AXIS, ANGLE.
    aux = [
        i for i, line in enumerate(lines) if line == "ROTATE_COORDINATE_SYSTEM" and i > rotations[0]
    ]
    turned = [(lines[i + 1], lines[i + 2], lines[i + 3], lines[i + 4]) for i in aux]
    assert (f"FRAME {prop}", f"ROTATION_FRAME {nac}", "ROTATION_AXIS Y", "ANGLE 3.0") in turned, (
        turned
    )
    assert (f"FRAME {prop}", f"ROTATION_FRAME {nac}", "ROTATION_AXIS Z", "ANGLE -2.0") in turned, (
        turned
    )
    # THE BLADE FRAME CARRIES ITS ROTOR'S ALIAS since 0.15.0: a MOTIONS
    # record's per-blade frame is <ALIAS>_RMRP<k>, where the flat row's was
    # BladeAxis<k>. It still has to turn with the hub it was derived from,
    # which is the property this arm is about.
    blade_axis = int(lines[lines.index("NAME ROTOR_RMRP1") - 1].split()[1])
    assert (
        f"FRAME {blade_axis}",
        f"ROTATION_FRAME {nac}",
        "ROTATION_AXIS Y",
        "ANGLE 3.0",
    ) in turned, "the blade frame the package derived from the hub did not turn with it"
    assert all(i < motion for i in aux), "an auxiliary frame turned after the motion was created"
    # The rotations of record one all precede the rotation of record two.
    assert all(i < rotations[1] for i in aux if lines[i + 4] == "ANGLE 3.0"), aux


def test_a_rotation_naming_a_word_the_reference_lacks_is_blocked_naming_the_cell(tmp_path):
    """PFS-2034.02, in the 0.15.0 vocabulary: a rotation names a set the
    REFERENCE owns, the way a motion does, so the thing that can be wrong is
    the word rather than a family inside a list. A word the reference does
    not declare blocks the row at plan time naming the key, the token and
    the words the file does declare."""
    root, matrix = _rotor_row_on_a_setup_with_nac(
        tmp_path, ROTATE_TWO.replace("ALIAS: ROTOR", "ALIAS: NoSuchAlias")
    )
    plan, _ = _rendered(root, matrix)
    assert plan.blocked, "a rotation naming a word the reference lacks planned READY"
    reason = str(plan.blocked[0].error)
    assert "ROTATE" in reason and "NoSuchAlias" in reason, reason
    assert "declares" in reason and "ROTOR" in reason, reason


def test_a_rotation_naming_an_unknown_frame_is_refused(tmp_path):
    """PFS-2034.03: an AXIS or AUX_FRAMES frame nothing defined blocks the row at plan
    time naming the token and the frames the case does define."""
    root, matrix = _rotor_row_on_a_setup_with_nac(tmp_path, ROTATE_TWO.replace("NAC-Z", "TAIL-Z"))
    plan, _ = _rendered(root, matrix)
    assert plan.blocked, "a rotation about a frame nothing defined planned READY"
    reason = str(plan.blocked[0].error)
    assert "ROTATE" in reason and "TAIL" in reason, reason
    assert "NAC" in reason and "ROTOR_MRP" in reason, reason


def test_a_rotation_axis_not_of_the_form_frame_axis_is_refused(tmp_path):
    """PFS-2034.03: the axis token is refused when the matrix is read, naming the POL,
    so no point of the row is ever planned."""
    root, matrix = _rotor_row_on_a_setup_with_nac(tmp_path, ROTATE_TWO.replace("NAC-Y", "NACY"))
    with pytest.raises(MatrixError, match="POL 1020.*ROTATE.*NACY.*frame-axis"):
        _rendered(root, matrix)


def test_a_rotation_on_a_legacy_row_is_refused(tmp_path):
    """PFS-2034.03: a LEGACY row is built by its recipe, which reads no rotation, so the
    variable on it is refused when the matrix is read rather than silently dropped."""
    root = _tier3_copy(tmp_path)
    legacy = next(
        line for line in TOUR.read_text(encoding="utf-8").splitlines() if "| LEGACY " in line
    )
    matrix = _one_row_matrix(root, "legacy_rotate.fs", legacy.rstrip() + ROTATE_TWO)
    with pytest.raises(MatrixError, match="LEGACY.*ROTATE|ROTATE.*LEGACY"):
        _rendered(root, matrix)


# --- PFS-2033.01: raw commands emitted before the named phase, through the emitter ----


def _steady_row_on_a_setup_with_raw(tmp_path, entries, name="raw.fs"):
    root = _tier3_copy(tmp_path)
    plain = (root / "inputs" / "setups" / "s001.toml").read_text(encoding="utf-8")
    body = "".join(
        f'\n[[raw]]\ncommand = "{command}"\nbefore = "{before}"\n' for command, before in entries
    )
    (root / "inputs" / "setups" / "s091.toml").write_text(
        plain.rstrip("\n") + "\n" + body, encoding="utf-8"
    )
    steady = next(
        line for line in TOUR.read_text(encoding="utf-8").splitlines() if "| steady " in line
    )
    cells = steady.split("|")
    cells[_COLUMNS.index("SET")] = " s091 "
    return root, _one_row_matrix(root, name, "|".join(cells))


def _row_with_a_raw_cell(tmp_path, cell, name="rawcell.fs", preset=()):
    """A steady row of the tour whose VAR_NAMES_VALUES carries a RAW list (FR-67)."""
    root = _tier3_copy(tmp_path)
    if preset:
        plain = (root / "inputs" / "setups" / "s001.toml").read_text(encoding="utf-8")
        body = "".join(
            f'\n[[raw]]\ncommand = "{command}"\nbefore = "{before}"\n' for command, before in preset
        )
        (root / "inputs" / "setups" / "s091.toml").write_text(
            plain.rstrip("\n") + "\n" + body, encoding="utf-8"
        )
    steady = next(
        line for line in TOUR.read_text(encoding="utf-8").splitlines() if "| steady " in line
    )
    cells = steady.split("|")
    if preset:
        cells[_COLUMNS.index("SET")] = " s091 "
    tail = cells[-1].strip()
    cells[-1] = f" {tail} / {cell}" if tail else f" {cell}"
    return root, _one_row_matrix(root, name, "|".join(cells))


def _raw_file(root, body, name="extra.txt"):
    """Write a raw command file under the workspace's inputs."""
    raw = root / "inputs" / "raw"
    raw.mkdir(exist_ok=True)
    (raw / name).write_text(body, encoding="utf-8")
    return f"raw/{name}"


def test_a_raw_line_from_a_file_reaches_the_emitted_script_in_file_order(tmp_path):
    """NOTHING RENDERED A SCRIPT FROM A ROW'S RAW CELL until this round.

    Every case of `test_raw_on_the_row.py` stops at the resolved case, so
    the whole path from a FILE record to an emitted line was measured
    nowhere (the QA lens, 2026-09-10).
    """
    root, matrix = _row_with_a_raw_cell(tmp_path, "RAW: {FILE: raw/extra.txt / BEFORE: init}")
    _raw_file(
        root, "# a file that explains itself\n\nPRINT from_line_three\nPRINT from_line_four\n"
    )
    plan, rendered = _rendered(root, matrix)
    assert not plan.blocked, plan.summary()
    lines = next(iter(rendered.values())).splitlines()
    assert "PRINT from_line_three" in lines, [line for line in lines if line.startswith("PRINT")]
    assert lines.index("PRINT from_line_three") < lines.index("PRINT from_line_four"), (
        "the file's lines are emitted out of file order"
    )
    assert lines.index("PRINT from_line_four") < lines.index("INITIALIZE_SOLVER")


def test_a_refusal_from_a_raw_file_names_the_file_and_the_line(tmp_path):
    """FR-67's own capitalised sentence, measured for the first time.

    The cell holds a PATH and the mistake may be thirty lines away, so a
    refusal that named the cell would send the author to the wrong file.
    """
    root, matrix = _row_with_a_raw_cell(tmp_path, "RAW: {FILE: raw/extra.txt / BEFORE: init}")
    _raw_file(root, "# two good lines and then one this build lacks\nPRINT fine\nNOT_A_COMMAND 1\n")
    plan = _plan(root, matrix)
    assert plan.blocked, plan.summary()
    reason = plan.summary()
    assert "raw/extra.txt:3" in reason, reason
    assert "NOT_A_COMMAND" in reason, reason


def test_a_refusal_from_the_rows_own_cell_says_so(tmp_path):
    """The other arm: the line IS in the cell, so the cell is where to look."""
    root, matrix = _row_with_a_raw_cell(tmp_path, "RAW: {COMMAND: NOT_A_COMMAND 1 / BEFORE: init}")
    plan = _plan(root, matrix)
    assert plan.blocked, plan.summary()
    reason = plan.summary()
    assert "the row's own RAW cell" in reason, reason


def test_a_raw_command_is_emitted_before_the_phase_it_names_and_after_the_one_before(tmp_path):
    """RED on aff689e: the setup is refused as stating a key naming no setting."""
    root, matrix = _steady_row_on_a_setup_with_raw(
        tmp_path, [("SOLVER_SET_AOA 1.0", "init"), ("PRINT raw_before_export", "export")]
    )
    plan, rendered = _rendered(root, matrix)
    assert not plan.blocked, plan.summary()
    lines = next(iter(rendered.values())).splitlines()
    raw = [i for i, line in enumerate(lines) if line == "SOLVER_SET_AOA 1.0"]
    assert raw, [line for line in lines if line.startswith("SOLVER_SET_AOA")]
    init = lines.index("INITIALIZE_SOLVER")
    velocity = next(i for i, line in enumerate(lines) if line.startswith("SOLVER_SET_VELOCITY"))
    assert velocity < raw[-1] < init, (velocity, raw, init)
    printed = lines.index("PRINT raw_before_export")
    export = next(i for i, line in enumerate(lines) if line.startswith("EXPORT_"))
    analysis = lines.index("START_SOLVER")
    assert analysis < printed < export, (analysis, printed, export)


def test_a_raw_command_the_build_lacks_blocks_the_row_with_the_emitters_own_refusal(tmp_path):
    """The line passes the same check every emission passes: a command the build
    has no evidence for is the emitter's refusal, naming the setup and the entry."""
    root, matrix = _steady_row_on_a_setup_with_raw(
        tmp_path, [("SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE", "control")]
    )
    plan, _ = _rendered(root, matrix)
    assert plan.blocked, "a raw command the build lacks planned READY"
    reason = str(plan.blocked[0].error)
    assert "CommandNotInVersionError" in reason or "no recorded evidence" in reason, reason
    assert "s091" in reason and "SET_NEW_UNSTEADY_SOLVER_ACTION" in reason, reason


@pytest.mark.parametrize(
    ("entry", "fragment"),
    [
        (("SOLVER_SET_AOA one", "init"), "SOLVER_SET_AOA"),
        (("SURFACE_ROTATE 1 X 20", "setup"), "keyword block"),
        (("START_SOLVER", "setup"), "exec command"),
    ],
)
def test_a_raw_line_the_emitter_cannot_carry_blocks_the_row_naming_the_setup(
    tmp_path, entry, fragment
):
    """An argument of the wrong type, a command that is a block and not a line, and a
    command of a later phase declared before an earlier one are each the emitter's
    refusal, naming the setup and the line."""
    root, matrix = _steady_row_on_a_setup_with_raw(tmp_path, [entry])
    plan, _ = _rendered(root, matrix)
    assert plan.blocked, f"{entry} planned READY"
    reason = str(plan.blocked[0].error)
    assert "s091" in reason and fragment in reason, reason


def test_a_setup_without_the_raw_table_renders_as_before(tmp_path):
    """The control: the seven tier-3 matrices are the goldens; here one row of them."""
    root, matrix = _steady_row_on_a_setup_with_raw(tmp_path, [])
    plan, rendered = _rendered(root, matrix)
    assert not plan.blocked, plan.summary()
    text = next(iter(rendered.values()))
    assert "PRINT" not in text and text.count("SOLVER_SET_AOA") == 1


@pytest.mark.parametrize(
    "body",
    [
        '\n[[raw]]\ncommand = "SOLVER_SET_ITERATIONS 350"\nbefore = "init"\n',
        '\n[[frames]]\nname = "NAC"\norigin = [0.4, 0.0, 0.1]\n',
    ],
)
def test_a_legacy_row_naming_a_setup_with_a_frames_or_raw_table_is_refused(tmp_path, body):
    """QA-4 of REL-0140, measured: the tour's LEGACY row on a setup carrying either
    table planned READY, the script carried neither, and the record would have
    claimed the raw line. Refused when the matrix binds, naming the POL, the setup
    and the table."""
    root = _tier3_copy(tmp_path)
    plain = (root / "inputs" / "setups" / "s001.toml").read_text(encoding="utf-8")
    (root / "inputs" / "setups" / "s093.toml").write_text(
        plain.rstrip("\n") + "\n" + body, encoding="utf-8"
    )
    legacy = next(
        line for line in TOUR.read_text(encoding="utf-8").splitlines() if "| LEGACY " in line
    )
    cells = legacy.split("|")
    cells[_COLUMNS.index("SET")] = " s093 "
    matrix = _one_row_matrix(root, "legacy_setup.fs", "|".join(cells))
    with pytest.raises(PyflightstreamError) as refused:
        _rendered(root, matrix)
    message = str(refused.value)
    # A [[frames]] TABLE ON A PRESET IS REFUSED FOR EVERY ROW since 0.15.0
    # moved it to the reference, so this row meets that sentence before the
    # LEGACY one. Both name the preset and the table, which is what a
    # reader needs; one sentence is better than two.
    assert "s093" in message, message
    assert ("LEGACY" in message) or ("reference" in message), message
