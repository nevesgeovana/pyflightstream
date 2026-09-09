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


STEADY = "MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | p002 | 26.120 | 0 | 1 | steady | "
ROTOR = (
    "MACH:0.1, REmi:2.3 | AL | 0.0 | r004 | s002 | p001 | 26.120 | 0 | 1 | unsteady_rotor | "
    "GEOMETRY: 40_PUSHER.fsm / SYMMETRY: NONE / ROTOR_AXIS: X / MOVING_BOUNDARIES: Blade / "
    "DELTA_THETA: 30 / REVOLUTIONS: 0.5 / "
)

REFUSALS = {
    "a geometry the library does not hold": (
        f"7001 | Wing | REFUSED | {STEADY}GEOMETRY: 99_MISSING.fsm / SYMMETRY: NONE",
        ("99_MISSING", "geometries"),
    ),
    "a reference code the library does not hold": (
        "7002 | Wing | REFUSED | MACH:0.1, REmi:2.3 | AL | 0.0 | r999 | s001 | p002 | 26.120 | 0 "
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
        "7005 | Wing | REFUSED | MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | p002 | 26.120 | 0 "
        "| 1 | LEGACY | RECIPE: 003 / GEOMETRY: 10_WING.fsm / OUTPUTS: loads_{point}.txt",
        ("recipe mapping",),
    ),
    "a build the registry does not hold": (
        "7006 | Wing | REFUSED | MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | p002 | 27.000 | 0 "
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


WING_ROW = "MACH:0.1, REmi:2.3 | AL | 0.0 | r001 | s001 | {pproc} | 26.120 | 0 | 1 | steady | "


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
    count, absent, differ, orphans = offline.compare(matrix)
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
    sweep = STEADY.replace("| AL | 0.0 |", "| BE | -4,0,4 |")
    assert sweep != STEADY
    mirrored = _one_row_matrix(
        root,
        "yawed_mirror.fs",
        f"4207 | Wing | YAWED | {sweep}GEOMETRY: 10_WING.fsm / SYMMETRY: MIRROR",
    )
    plan = _plan(root, mirrored)
    blocked = {p.run_id: p.error for p in plan.blocked}
    assert set(blocked) == {"refusal/sim_4207/b-04.0", "refusal/sim_4207/b+04.0"}, plan.summary()
    for error in blocked.values():
        assert "SYMMETRY: MIRROR" in error and "-4.0000 deg" in error or "+4.0000 deg" in error, (
            error
        )
        assert "SYMMETRY: NONE" in error, (
            "the refusal does not name the cell that lets the sweep run"
        )
    assert len(plan.ready) == 1, "the zero-sideslip point of the same row is refused too"
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
