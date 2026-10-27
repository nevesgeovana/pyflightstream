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


#: The power-on row's script for a PUSHER_SMRP probe and section, measured on v0.46.0.
_UNSTEADY_ROTOR_SHA256 = "14e92e15029269b168bee158b8c3edda962f2676c08b32b4228879200023f5ef"


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
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == _UNSTEADY_ROTOR_SHA256


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
    assert "NAME PORT_RMRP" not in names and "NAME STARBOARD_RMRP" not in names
    root = _tier3_copy(tmp_path / "tour")
    row = next(line for line in TOUR.read_text().splitlines() if line.startswith("1022 "))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, turning = _rendered(root, _one_row_matrix(root, "twin.fs", row))
    for alias in ("PORT", "STARBOARD"):
        assert _placement(text, f"{alias}_SMRP") == _placement(_only(turning), f"{alias}_SMRP")
