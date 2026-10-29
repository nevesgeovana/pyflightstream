"""P0461: a row whose reference declares a rotor places that rotor's static hub frame.

The requirement: every row whose reference declares a rotor places
``<ALIAS>_SMRP`` at the rotor's hub, on the rotor's hub axes, even when the row
turns no blades (a steady power-off row, a rotorless unsteady row), so one
pproc artifact serves the power-off and the power-on rows. ``<ALIAS>_RMRP`` is
not part of the rule: a pproc entry in a rotor frame the row does not place is
left out of that row, and the plan warns once per campaign, naming the entry,
the frame and every row that leaves it out.

The scripts are read as the plan's dry run renders them, through the tier-3
inputs. No solver is invoked.
"""

from __future__ import annotations

import hashlib
import warnings

import pytest

from tests.tier1_offline.test_tier3_offline import TOUR, _one_row_matrix, _rendered, _tier3_copy

#: The run-type cells of the rows below, after the PPROC column.
_TAIL = {
    "steady": "NONE | - | - | - | 26.120 | steady | ",
    "unsteady": (
        "NONE | - | - | - | 26.120 | unsteady | "
        "DELTA_TIME: 0.01 / TIME_ITERATIONS: 12 / LAST_ITERS_AVG: 6"
    ),
    "unsteady_rotor": (
        "NONE | - | - | - | 26.120 | unsteady_rotor | DELTA_THETA: 30 / REVOLUTIONS: 0.5 / "
        "CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER / RPM: 800} / "
        "LAST_REVS_AVG: 1"
    ),
}
#: The pusher configuration: one rotor block, PUSHER, behind a body.
_PUSHER = ("40_PUSHER.fsm", "r004")
#: The twin configuration: two rotor blocks, PORT and STARBOARD.
_TWIN = ("41_TWIN.fsm", "r006")
#: A wing whose reference declares no rotor block.
_WING = ("10_WING.fsm", "r001")


def _probe(frame: str, kind: str = "default") -> str:
    return (
        f'[[probes]]\nkind = "{kind}"\nframe = "{frame}"\nparameters = ["VX"]\n'
        'points = 2\nscale = "m"\n[[probes.lines]]\nstart = [0.5, 0, 0]\nend = [0.5, 1, 0]\n'
    )


def _section(frame: str) -> str:
    return (
        "[sections]\ncount = 5\nplot_direction = 1\ninclude_symmetry = false\n\n"
        f'[[sections.distributions]]\nfamilies = ["Body"]\nframe = "{frame}"\nplanes = ["XZ"]\n'
    )


def _row(pol: int, workflow: str, geometry: str, reference: str, pproc: str) -> str:
    setup = "s001" if workflow == "steady" else "s002"
    return (
        f"{pol} | 0 | 1 | Pusher | - | P0461 | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 "
        f"| {geometry} | {reference} | {setup} | {pproc} | {_TAIL[workflow]}"
    )


def _plan(tmp_path, pproc_text: str, rows: list[tuple[int, str, tuple[str, str]]]):
    """Plan ``rows`` over one pproc artifact; return the plan, its scripts and its warnings."""
    root = _tier3_copy(tmp_path)
    (root / "inputs" / "pproc" / "p061.toml").write_text(pproc_text, encoding="utf-8")
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    lines = [_row(pol, workflow, *where, "p061") for pol, workflow, where in rows]
    matrix = root / "p0461.fs"
    matrix.write_text("\n".join([header, rule, *lines]) + "\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan, rendered = _rendered(root, matrix)
    return plan, rendered, [str(item.message) for item in caught]


def _only(rendered: dict[str, str]) -> str:
    assert len(rendered) == 1, sorted(rendered)
    return next(iter(rendered.values()))


def _frame_index(text: str, name: str) -> int:
    """The index the solver gives frame ``name``: one after every frame created before it."""
    lines = text.splitlines()
    at = lines.index(f"NAME {name}")
    return 1 + sum(line == "CREATE_NEW_COORDINATE_SYSTEM" for line in lines[:at])


def _placement(text: str, name: str) -> dict[str, str]:
    """The origin and axis lines the script states for frame ``name``."""
    lines = text.splitlines()
    at = lines.index(f"NAME {name}")
    return {
        key: value
        for key, value in (
            line.split(maxsplit=1) for line in lines[at + 1 : at + 13] if " " in line
        )
        if key.startswith(("ORIGIN_", "VECTOR_"))
    }


def _probe_lines(text: str) -> list[list[float]]:
    """The global end points of every probe line the script draws."""
    return [
        [float(value) for value in line.split()[2:]]
        for line in text.splitlines()
        if line.startswith("NEW_PROBE_LINE ")
    ]


def _the_line_in(text: str, name: str) -> list[float]:
    """The global end points of the test's probe line laid in frame ``name``."""
    placed = {key: float(value) for key, value in _placement(text, name).items()}
    origin = [placed[f"ORIGIN_{axis}"] for axis in "XYZ"]
    axes = [[placed[f"VECTOR_{a}_{b}"] for b in "XYZ"] for a in "XYZ"]
    ends = []
    for local in ([0.5, 0.0, 0.0], [0.5, 1.0, 0.0]):
        ends += [origin[b] + sum(local[a] * axes[a][b] for a in range(3)) for b in range(3)]
    return ends


def test_p0461_steady_row_places_its_rotors_hub_frame_for_a_probe(tmp_path):
    """RED on v0.46.0: the steady row was BLOCKED, refusing the PUSHER_SMRP probe."""
    plan, rendered, _ = _plan(tmp_path, _probe("PUSHER_SMRP"), [(7101, "steady", _PUSHER)])
    assert not plan.blocked, plan.summary()
    text = _only(rendered)
    assert text.splitlines().count("NAME PUSHER_SMRP") == 1
    # RMRP is not part of the rule: nothing turns on this row.
    assert "NAME PUSHER_RMRP" not in text.splitlines()
    (line,) = _probe_lines(text)
    assert line == pytest.approx(_the_line_in(text, "PUSHER_SMRP"))
    # AT THE HUB, ON THE HUB AXES: the frame the power-on row of the same
    # reference places under the same name.
    on = _probe("PUSHER_SMRP", kind="instantaneous")
    _, rotor, _ = _plan(tmp_path / "on", on, [(7102, "unsteady_rotor", _PUSHER)])
    assert _placement(text, "PUSHER_SMRP") == _placement(_only(rotor), "PUSHER_SMRP")
    assert _placement(text, "PUSHER_SMRP")


def test_p0461_steady_row_cuts_a_section_distribution_in_the_hub_frame(tmp_path):
    """RED on v0.46.0: the distribution named a frame the steady row did not create."""
    plan, rendered, _ = _plan(tmp_path, _section("PUSHER_SMRP"), [(7101, "steady", _PUSHER)])
    assert not plan.blocked, plan.summary()
    lines = _only(rendered).splitlines()
    at = lines.index("NEW_SURFACE_SECTION_DISTRIBUTION")
    assert lines[at + 1] == f"FRAME {_frame_index(_only(rendered), 'PUSHER_SMRP')}"


#: The power-on row's script for a PUSHER_SMRP probe and section, measured on v0.46.0,
#: with the paths under the workspace spelled with forward slashes on every machine.
_UNSTEADY_ROTOR_SHA256 = "38044d82fdda5cdb80f9d40bfe97dc966c52a6641737734a4dd093aa03e4d262"


def test_p0461_unsteady_rotor_row_script_is_unchanged(tmp_path):
    """The power-on row already placed its hub frame, and its bytes do not move."""
    pproc = _probe("PUSHER_SMRP", kind="instantaneous") + _section("PUSHER_SMRP")
    plan, rendered, _ = _plan(tmp_path, pproc, [(7102, "unsteady_rotor", _PUSHER)])
    assert not plan.blocked, plan.summary()
    # The workspace folder is the test's own; every spelling of it is one token.
    text = _only(rendered)
    root = tmp_path / "ws"
    for spelled in sorted({str(root), root.as_posix(), str(root.resolve())}, key=len, reverse=True):
        text = text.replace(spelled, "<WS>").replace(spelled.replace("\\", "/"), "<WS>")
    # A path under the workspace is spelled with the machine's own separator
    # (<WS>\inputs on Windows, <WS>/inputs on Linux): one spelling for both,
    # as tests/support_tier3.portable does for the tier-3 goldens.
    text = "\n".join(
        line if "<WS>" not in line else line.replace("\\", "/") for line in text.split("\n")
    )
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == _UNSTEADY_ROTOR_SHA256, text


def test_p0461_a_reference_with_no_rotor_still_refuses_a_hub_frame_probe(tmp_path):
    plan, _, _ = _plan(tmp_path, _probe("PUSHER_SMRP"), [(7101, "steady", _WING)])
    assert plan.blocked
    message = plan.summary()
    assert "'PUSHER_SMRP'" in message and "this run created no such frame" in message


def test_p0461_a_rotor_frame_the_row_does_not_place_is_warned_once_and_left_out(tmp_path):
    """RED on v0.46.0: both rows were BLOCKED, refusing the PUSHER_RMRP probe."""
    pproc = _probe("MRP") + _probe("PUSHER_RMRP")
    plan, rendered, said = _plan(
        tmp_path, pproc, [(7101, "steady", _PUSHER), (7102, "steady", _PUSHER)]
    )
    assert not plan.blocked, plan.summary()
    about = [message for message in said if "PUSHER_RMRP" in message and "ignored" in message]
    assert len(about) == 1, about
    assert "entry 2" in about[0] and "7101" in about[0] and "7102" in about[0]
    assert "will be ignored on these rows" in about[0]
    for text in rendered.values():
        (line,) = _probe_lines(text)
        assert line == pytest.approx(_the_line_in(text, "MRP"))


def test_p0461_rotorless_unsteady_row_places_every_declared_hub(tmp_path):
    """RED on v0.46.0: a two-rotor reference left both hub frames unplaced."""
    pproc = _probe("PORT_SMRP", kind="instantaneous")
    plan, rendered, _ = _plan(tmp_path, pproc, [(7101, "unsteady", _TWIN)])
    assert not plan.blocked, plan.summary()
    text = _only(rendered)
    names = text.splitlines()
    assert names.count("NAME PORT_SMRP") == 1 and names.count("NAME STARBOARD_SMRP") == 1
    assert "NAME PORT_RMRP" in names and "NAME STARBOARD_RMRP" in names
    root = _tier3_copy(tmp_path / "tour")
    row = next(line for line in TOUR.read_text().splitlines() if line.startswith("1022 "))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, turning = _rendered(root, _one_row_matrix(root, "twin.fs", row))
    for alias in ("PORT", "STARBOARD"):
        assert _placement(text, f"{alias}_SMRP") == _placement(_only(turning), f"{alias}_SMRP")


def _ignored(said: list[str], frame: str) -> list[str]:
    return [message for message in said if f"{frame!r}" in message and "ignored" in message]


def test_p0461_a_section_in_an_unplaced_rotor_frame_is_warned_once_and_left_out(tmp_path):
    """RED on v0.46.0: both steady rows were BLOCKED ("this run created no such frame")."""
    pproc = _section("MRP") + (
        '\n[[sections.distributions]]\nfamilies = ["Body"]\nframe = "PUSHER_RMRP"\n'
        'planes = ["XZ"]\n'
    )
    plan, rendered, said = _plan(
        tmp_path, pproc, [(7101, "steady", _PUSHER), (7102, "steady", _PUSHER)]
    )
    assert not plan.blocked, plan.summary()
    (about,) = _ignored(said, "PUSHER_RMRP")
    assert "section distribution 2" in about and "'7101'" in about and "'7102'" in about
    assert "will be ignored on these rows" in about
    for text in rendered.values():
        lines = text.splitlines()
        assert lines.count("NEW_SURFACE_SECTION_DISTRIBUTION") == 1
        at = lines.index("NEW_SURFACE_SECTION_DISTRIBUTION")
        assert lines[at + 1] == f"FRAME {_frame_index(text, 'MRP')}"


def test_p0461_a_plot_group_in_an_unplaced_blade_frame_is_warned_and_left_out(tmp_path):
    """RED on v0.46.0: the rotorless unsteady row was BLOCKED on PUSHER_RMRP1."""
    pproc = (
        '[plots]\nparameters = ["FX"]\n\n'
        '[[plots.groups]]\nname = "BODY_MRP"\nframe = "MRP"\nfamilies = "all"\n\n'
        '[[plots.groups]]\nname = "BLADE_ONE"\nframe = "PUSHER_RMRP1"\nfamilies = "all"\n'
    )
    plan, rendered, said = _plan(tmp_path, pproc, [(7101, "unsteady", _PUSHER)])
    assert not plan.blocked, plan.summary()
    (about,) = _ignored(said, "PUSHER_RMRP1")
    assert "plot group 'BLADE_ONE'" in about and "'7101'" in about
    text = _only(rendered)
    assert "FX_BODY_MRP" in text and "BLADE_ONE" not in text


@pytest.mark.parametrize("frame", ["PUSHR_RMRP", "LIFTER_SMRP"])
def test_p0461_a_frame_no_declared_rotor_owns_is_still_refused(tmp_path, frame):
    """A typo or an undeclared alias cannot come right on another row: refused, not skipped."""
    pproc = (
        f'{_section("MRP")}\n[[sections.distributions]]\nfamilies = ["Body"]\n'
        f'frame = "{frame}"\nplanes = ["XZ"]\n'
    )
    plan, _, said = _plan(tmp_path, pproc, [(7101, "steady", _PUSHER)])
    assert plan.blocked
    assert f"{frame!r}" in plan.summary() and "this run created no such frame" in plan.summary()
    assert not _ignored(said, frame)


def test_p0470_r6_partly_powered_row_places_the_inactive_rotor_hub(tmp_path):
    """A powered rotor cannot hide the static hub of another declared rotor."""
    root = _tier3_copy(tmp_path)
    (root / "inputs/pproc/p061.toml").write_text(
        _probe("STARBOARD_SMRP", kind="instantaneous"), encoding="utf-8"
    )
    row = _row(7103, "unsteady_rotor", *_TWIN, "p061").replace("PUSHER", "PORT")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan, rendered = _rendered(root, _one_row_matrix(root, "partial.fs", row))
    assert not plan.blocked, plan.summary()
    text = _only(rendered)
    assert text.splitlines().count("NAME STARBOARD_SMRP") == 1
    assert text.splitlines().count("NAME PORT_SMRP") == 1
    assert "NAME STARBOARD_RMRP" not in text.splitlines()
    assert text.splitlines().count("UNSTEADY_SOLVER_NEW_FLUID_PLOT") == 2
    _, idle, _ = _plan(tmp_path / "idle", _probe("STARBOARD_SMRP"), [(7104, "steady", _TWIN)])
    assert _placement(text, "STARBOARD_SMRP") == _placement(_only(idle), "STARBOARD_SMRP")


@pytest.mark.requirement("FR-3350")
@pytest.mark.parametrize("version", ["26.124", "26.125"])
def test_p0500_rotorless_rmrp_motion_has_no_boundaries(tmp_path, version):
    """RPM: 600 on an unsteady twin row turns frames alone (FR-3350)."""
    root = _tier3_copy(tmp_path)
    (root / "inputs/executables.toml").write_text(
        f'"{version}" = {{path = "FlightStream.exe", version = "{version}"}}\n',
        encoding="utf-8",
    )
    (root / "inputs/pproc/p061.toml").write_text(
        _probe("PORT_RMRP", kind="instantaneous"), encoding="utf-8"
    )
    row = _row(7501, "unsteady", *_TWIN, "p061").replace("26.120", version)
    row += " / RPM: 600"
    plan, rendered = _rendered(root, _one_row_matrix(root, "frames.fs", row))
    assert not plan.blocked, plan.summary()
    text = _only(rendered)
    for motion, alias, sign in [(1, "PORT", 1), (2, "STARBOARD", -1)]:
        assert f"NAME {alias}_RMRP" in text
        hub = _frame_index(text, f"{alias}_SMRP")
        moving = _frame_index(text, f"{alias}_RMRP")
        assert moving == hub + 1
        assert _placement(text, f"{alias}_RMRP") == _placement(text, f"{alias}_SMRP")
        block = (
            f"CREATE_NEW_MOTION ROTARY\nSET_MOTION_BOUNDARIES {motion} 0\n"
            f"SET_MOTION_MOVING_FRAMES {motion} 1\n{moving}\n\n"
            f"SET_MOTION_COORDINATE_SYSTEM {motion} {hub}\n"
            f"SET_MOTION_ROTOR_AXIS {motion} X\n"
            f"SET_MOTION_ROTOR_RPM {motion} {sign * 600.0}\n"
        )
        assert block in text
        assert text.index(block) < text.index("SET_SOLVER_UNSTEADY")
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" in text


@pytest.mark.requirement("FR-3351")
def test_p0500_rotorless_fixed_rmrp_warns_once_per_campaign(tmp_path):
    """Absent RPM places the RMRP and its entries; one warning names both rows."""
    plan, rendered, said = _plan(
        tmp_path,
        _probe("PUSHER_RMRP", kind="instantaneous"),
        [(7501, "unsteady", _PUSHER), (7502, "unsteady", _PUSHER)],
    )
    assert not plan.blocked, plan.summary()
    fixed = [message for message in said if "placed fixed: the row states no RPM" in message]
    assert len(fixed) == 1, said
    assert "7501" in fixed[0] and "7502" in fixed[0]
    assert not _ignored(said, "PUSHER_RMRP")
    for text in rendered.values():
        assert "NAME PUSHER_RMRP" in text
        assert _frame_index(text, "PUSHER_RMRP") == _frame_index(text, "PUSHER_SMRP") + 1
        assert _placement(text, "PUSHER_RMRP") == _placement(text, "PUSHER_SMRP")
        assert "CREATE_NEW_MOTION" not in text
        assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" in text


_SURFACE_PROBE = (
    '[[surface_probes]]\nattach = "space"\nname = "upper_cp"\nparameter = "CP_FREE"\n'
    'frame = "REFERENCE"\npoint_m = [0.25, 0.1, 0.02]\n'
)


def test_p0471_surface_probes_on_a_steady_row_are_warned_once_and_skipped(tmp_path):
    """RED on 022dfca8e: both steady rows were BLOCKED ("requires an unsteady march")."""
    pproc = _SURFACE_PROBE + _section("MRP")
    plan, rendered, said = _plan(
        tmp_path, pproc, [(7101, "steady", _PUSHER), (7102, "steady", _PUSHER)]
    )
    assert not plan.blocked, plan.summary()
    about = [m for m in said if "[[surface_probes]]" in m and "will be ignored" in m]
    assert len(about) == 1, about
    assert "unsteady march" in about[0] and "'7101'" in about[0] and "'7102'" in about[0]
    assert "Keep the entry in the one pproc artifact" in about[0]
    for text in rendered.values():
        assert "NEW_UNSTEADY_SOLVER_SURFACE_PROBE" not in text
        assert text.splitlines().count("NEW_SURFACE_SECTION_DISTRIBUTION") == 1


# --- PFS-2184.10: a power-off row runs on its power-on twin's clock ------------------


def _point_cases(tmp_path, rows, condition="MACH:0.1, REmi:2.3, ALPHA:sweep", pproc=""):
    """Plan ``rows`` (POL, run type, configuration, cell); return the plan, cases and warnings.

    The cases are the rows as the workspace resolves them, at their one point.
    """
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_tier3_offline import _plan as plan_the_matrix

    root = _tier3_copy(tmp_path)
    (root / "inputs" / "pproc" / "p061.toml").write_text(pproc, encoding="utf-8")
    # A build that documents the unsteady solver actions the export thresholds run on.
    (root / "inputs" / "executables.toml").write_text(
        '"26.124" = {path = "FlightStream.exe", version = "26.124"}\n', encoding="utf-8"
    )
    header, rule = TOUR.read_text(encoding="utf-8").splitlines()[:2]
    lines = [
        f"{pol} | 0 | 1 | Pusher | - | P0500 | {condition} | 0.0 | {geometry} | {reference} "
        f"| s002 | p061 | NONE | - | - | - | 26.124 | {workflow} | {cell}"
        for pol, workflow, (geometry, reference), cell in rows
    ]
    matrix = root / "p0500.fs"
    matrix.write_text("\n".join([header, rule, *lines]) + "\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_the_matrix(root, matrix)
        resolved = resolve_matrix(
            matrix, CampaignWorkspace(root), name="p0500", fs_version="26.124", recipes={}
        )
    cases = {
        case.sim_id: case.model_copy(update={"point": {"alpha": 0.0}})
        for case in resolved.campaign.sims
    }
    return plan, cases, list(caught)


#: One far-field entry averaging the last half revolution.
_LAST_REVS_FARFIELD = (
    '[[farfields]]\nvariant = "plane"\nexport_type = "avg_window"\nlast_revs = 0.5\n'
)


def _farfield_windows_skipped(plan) -> dict[str, str]:
    """The reason each planned row records for not taking a far-field window, by row."""
    return {
        point.sim_id: entry["reason"]
        for point in plan.points
        for entry in (point.farfield or {}).get("inputs", [])
        if entry.get("input") == "window" and entry.get("state") == "not_applicable"
    }


#: Each clock a power-off row states as its power-on twin does: the configuration,
#: the flight condition, the speed and clock-rotor keys of each row, and the clock and
#: window keys both rows share.
_TWIN_CLOCKS = {
    "advance-ratio-azimuthal-after-rev": (
        _PUSHER,
        "MACH:0.1, REmi:2.3, ALPHA:sweep, ADVANCE_RATIO:0.9",
        "CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER}",
        "CLOCK_MOTION: PUSHER",
        "DELTA_THETA: 10 / REVOLUTIONS: 3 / EXPORT_UNSTEADY_AFTER_REV: 2 / LAST_REVS_AVG: 1",
    ),
    "rpm-explicit-last-rev-two-rotors": (
        _TWIN,
        "MACH:0.1, REmi:2.3, ALPHA:sweep, RPM:800",
        "CLOCK_MOTION: PORT / MOTIONS: {MOVING_BC_ALIAS: PORT}, {MOVING_BC_ALIAS: STARBOARD}",
        "CLOCK_MOTION: PORT",
        "DELTA_TIME: 0.0025 / TIME_ITERATIONS: 90 / EXPORT_UNSTEADY_LAST_REV: 0.5 / "
        "LAST_REVS_AVG: 1.5",
    ),
}


@pytest.mark.requirement("FR-3360")
@pytest.mark.requirement("FR-3361")
@pytest.mark.requirement("FR-3362")
@pytest.mark.parametrize("clock", sorted(_TWIN_CLOCKS))
def test_p0500_power_off_row_runs_on_its_power_on_twins_clock(tmp_path, clock):
    """PFS-2184.10: same step, count, export threshold and averaging windows on both rows."""
    from pyflightstream.cases.workflows import (
        reduction_windows,
        unsteady_export_threshold,
        unsteady_time_stepping,
    )
    from pyflightstream.cases.workflows._farfield import farfield_export_windows
    from pyflightstream.cases.workflows._freestream import rotor_row_stepping

    where, condition, on_keys, off_keys, shared = _TWIN_CLOCKS[clock]
    rows = [
        (7601, "unsteady_rotor", where, f"{on_keys} / {shared}"),
        (7602, "unsteady", where, f"{off_keys} / {shared}"),
    ]
    plan, cases, _ = _point_cases(tmp_path, rows, condition, _LAST_REVS_FARFIELD)
    assert not plan.blocked, plan.summary()
    assert not _farfield_windows_skipped(plan), plan.summary()
    on, off = cases["7601"], cases["7602"]
    powered = rotor_row_stepping(on)
    assert powered.steps_per_revolution is not None
    assert unsteady_time_stepping(off) == powered
    thresholds = [unsteady_export_threshold(case, version="26.124") for case in (on, off)]
    assert None not in thresholds
    fields = ("stated_form", "stated_value", "first_step", "time_iterations")
    fields += ("delta_time_s", "step_deg", "rpm")
    assert [getattr(thresholds[1], name) for name in fields] == [
        getattr(thresholds[0], name) for name in fields
    ]
    windows = [reduction_windows(case)["time_average"]["windows"] for case in (on, off)]
    assert windows[1] == windows[0]
    assert farfield_export_windows(off) == farfield_export_windows(on) != ()


@pytest.mark.requirement("FR-3363")
@pytest.mark.requirement("FR-3364")
def test_p0500_revolution_keys_without_a_clock_warn_and_skip(tmp_path):
    """No ADVANCE_RATIO or RPM: revolution keys warn and are skipped; iteration keys hold."""
    from pyflightstream._errors import NotApplicableWarning
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import (
        build_script,
        reduction_windows,
        unsteady_export_threshold,
    )
    from pyflightstream.options import option_context
    from pyflightstream.script import Script

    clock = "DELTA_TIME: 0.01 / TIME_ITERATIONS: 12"
    rows = [
        (7611, "unsteady", _PUSHER, f"{clock} / EXPORT_UNSTEADY_AFTER_REV: 1 / LAST_REVS_AVG: 1"),
        (7612, "unsteady", _PUSHER, f"{clock} / EXPORT_UNSTEADY_AFTER_ITER: 4 / LAST_ITERS_AVG: 6"),
    ]
    plan, cases, caught = _point_cases(tmp_path, rows)
    assert not plan.blocked, plan.summary()
    skipped = [
        str(item.message) for item in caught if issubclass(item.category, NotApplicableWarning)
    ]
    for key in ("EXPORT_UNSTEADY_AFTER_REV", "LAST_REVS_AVG"):
        said = [message for message in skipped if f"states {key}" in message]
        assert said, skipped
        assert all("'ADVANCE_RATIO: <J>'" in m and "'RPM: <rev/min>'" in m for m in said), said
    clockless, counted = cases["7611"], cases["7612"]
    assert unsteady_export_threshold(clockless, version="26.124") is None
    assert reduction_windows(clockless)["time_average"]["windows"] == [[1, 12]]
    threshold = unsteady_export_threshold(counted, version="26.124")
    assert (threshold.stated_form, threshold.first_step) == ("iterations", 4)
    assert reduction_windows(counted)["time_average"]["windows"] == [[7, 12]]
    with option_context("warning_refusals", True), pytest.raises(CampaignConfigError) as refused:
        build_script(clockless, Script("26.124"))
    assert "'ADVANCE_RATIO: <J>'" in str(refused.value)


@pytest.mark.requirement("FR-3360")
@pytest.mark.requirement("FR-3363")
def test_rel2_001_a_row_declaring_no_rotor_counts_no_revolutions(tmp_path):
    """REL2-001: J with an azimuthal clock on a rotorless reference is no rotor clock."""
    from pyflightstream._errors import NotApplicableWarning
    from pyflightstream.cases.workflows import reduction_windows, unsteady_export_threshold

    cell = "DELTA_THETA: 20 / REVOLUTIONS: 3 / EXPORT_UNSTEADY_AFTER_REV: 2 / LAST_REVS_AVG: 2"
    plan, cases, caught = _point_cases(
        tmp_path,
        [(7621, "unsteady", _WING, cell)],
        "MACH:0.1, REmi:2.3, ALPHA:sweep, ADVANCE_RATIO:1.3",
        _LAST_REVS_FARFIELD,
    )
    assert not plan.blocked, plan.summary()
    case = cases["7621"]
    assert not case.rotors
    skipped = [
        str(item.message) for item in caught if issubclass(item.category, NotApplicableWarning)
    ]
    for key in ("EXPORT_UNSTEADY_AFTER_REV", "LAST_REVS_AVG"):
        assert any(f"states {key}" in message for message in skipped), skipped
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is None or threshold.stated_form != "revolutions", threshold
    # Two revolutions of 18 steps would be steps 19 to 54; the stated key is not counted.
    average = reduction_windows(case)["time_average"]
    assert average["windows"] != [[19, 54]]
    assert "LAST_REVS_AVG" not in average["window_from"]
    assert "7621" in _farfield_windows_skipped(plan)
