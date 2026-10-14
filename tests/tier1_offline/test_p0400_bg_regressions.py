"""Tier 1, 0.40.0: one regression test per closed bug node that carried none.

Each test is written from its node's acceptance sentence, what a caller must
observe, and not from the fix. Each was measured failing on the parent of its
fix commit and passing at the release head. Synthetic inputs only; no solver
runs.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from pyflightstream import farfield
from pyflightstream.farfield import (
    FarfieldInputError,
    axial_force,
    cylindrical_components,
    in_plane_moment,
    spurious_diagnostic,
    to_counts,
)
from pyflightstream.probes import build_lattice

RHO = 1.2
V_INF = 30.0


def _survey(stations: tuple[float, ...], fill: Any) -> Any:
    """Survey samples on a unit-tip lattice; ``fill(fields, lattice)`` edits free-stream arrays.

    The assembler is ``lattice_fields``; the regression proof also runs on
    trees older than its 0.40.0 rename, where it is ``lattice_dataset``.
    """
    lattice = build_lattice(tip_radius=1.0, stations=stations, lateral_radius=None)
    shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)
    fields = {
        "u": np.full(shape, V_INF),
        "v": np.zeros(shape),
        "w": np.zeros(shape),
        "p_prime": np.zeros(shape),
    }
    fill(fields, lattice)
    assemble = getattr(farfield, "lattice_fields", None) or farfield.lattice_dataset
    return cylindrical_components(assemble(lattice, fields)), lattice


def test_p0400_bg_drag_counts_need_a_stated_area_and_a_moving_stream():
    """PFS-2081.29: no silent s_ref = 1.0, and hover (v_inf = 0) is refused by name.

    Omitting the reference area used to scale the count by an area nobody
    stated, and ``v_inf = 0`` crashed with ZeroDivisionError.
    """
    with pytest.raises(TypeError, match="s_ref"):
        to_counts(10.0, rho_inf=RHO, v_inf=V_INF)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="s_ref"):
        spurious_diagnostic(10.0, 9.0, rho_inf=RHO, v_inf=V_INF)  # type: ignore[call-arg]
    with pytest.raises(FarfieldInputError, match="v_inf"):
        to_counts(10.0, rho_inf=RHO, v_inf=0.0, s_ref=2.0)
    with pytest.raises(FarfieldInputError, match="v_inf"):
        spurious_diagnostic(10.0, 9.0, rho_inf=RHO, v_inf=0.0, s_ref=2.0)
    # A stated area gives counts = 2 delta / (rho V^2 S) * 1e4.
    expected = 2.0 * 10.0 / (RHO * V_INF**2 * 2.0) * 1.0e4
    assert to_counts(10.0, rho_inf=RHO, v_inf=V_INF, s_ref=2.0) == pytest.approx(expected)


def test_p0400_bg_hpc_and_cost_selection_end_with_the_command_that_made_them(tmp_path, capsys):
    """PFS-2094.022: ``main()`` run twice, the second time without ``--hpc``/``--cost-file``.

    The selection a flag made was a process-wide ContextVar never cleared, so
    the next command, and any later caller, ran under the first one's profile.
    """
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.run.cli import main
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.costs import resolve_cost_file, select_cost_file
    from pyflightstream.workspace.hpc import resolve_hpc_profile, select_hpc_profile

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.root / "inputs"
    (inputs / "hpc").mkdir(parents=True, exist_ok=True)
    (inputs / "costs").mkdir(parents=True, exist_ok=True)
    for stem in ("h001", "h002"):
        (inputs / "hpc" / f"{stem}.toml").write_text(
            f'application_id = "app-{stem}"\n\n[descriptor]\ntemplate = "d.tmpl"\n\n'
            '[descriptor.fields]\nwalltime = "{walltime}"\n\n'
            '[submit]\ncommand = ["sbatch", "{descriptor}"]\n',
            encoding="utf-8",
        )
    for stem in ("c001", "c002"):
        (inputs / "costs" / f"{stem}.toml").write_text("", encoding="utf-8")
    argv = ["plan", str(tmp_path / "absent.fs"), "--workspace", str(workspace.root)]
    select_hpc_profile(None)
    select_cost_file(None)
    try:
        main([*argv, "--hpc", "h002", "--cost-file", "c002"])
        main(argv)
        capsys.readouterr()
        with pytest.raises(InputArtifactError, match="nothing says which cluster"):
            resolve_hpc_profile(inputs)
        with pytest.raises(InputArtifactError, match="nothing says which machine"):
            resolve_cost_file(inputs)
    finally:
        select_hpc_profile(None)
        select_cost_file(None)


def test_p0400_bg_a_quiet_console_still_prints_requested_diagnostics(tmp_path, capsys):
    """PFS-2094.026: ``[log] console = "quiet"`` plus ``post --diagnostics`` prints the Markdown.

    The quiet console held every stdout write, so the command printed nothing
    and exited 0.
    """
    from pyflightstream.run.cli import main
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_matrix_cli import _record_a_converged_polar
    from tests.tier1_offline.test_post_products import LOADS

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    _record_a_converged_polar(workspace, "3207", {"alpha": -2.0}, LOADS)
    args = ["post", "--workspace", str(workspace.root), "--diagnostics"]
    assert main([*args, "--log-level", "normal"]) == 0
    shown = capsys.readouterr().out
    assert shown.strip(), "the normal console printed no diagnostics to compare against"
    (workspace.root / "pyfs.toml").write_text('[log]\nconsole = "quiet"\n', encoding="utf-8")
    assert main(args) == 0
    assert capsys.readouterr().out == shown


def test_p0400_bg_axial_force_finds_a_station_given_as_a_computed_float():
    """PFS-2095.064: ``outlet = 0.1 * 3`` finds the plane at 0.3; a missing plane is explained.

    Stations were selected by exact float equality, so a computed coordinate
    missed the stored one and xarray raised a KeyError naming no station.
    """

    def jump(fields, _lattice):
        fields["u"][1] = 1.1 * V_INF

    survey, _ = _survey((0.0, 0.3), jump)
    assert 0.1 * 3 != 0.3
    stored = axial_force(survey, RHO, V_INF, inlet=0.0, outlet=0.3)
    assert stored != 0.0
    assert axial_force(survey, RHO, V_INF, inlet=0.0, outlet=0.1 * 3) == pytest.approx(stored)
    with pytest.raises(FarfieldInputError) as refused:
        axial_force(survey, RHO, V_INF, inlet=0.0, outlet=0.5)
    assert "0.0" in str(refused.value) and "0.3" in str(refused.value)


def test_p0400_bg_the_window_resolver_refuses_what_the_plan_refuses():
    """PFS-2097.002: 0.01 revolutions, both keys, ``inf`` and a non-positive window are refused.

    The post-time resolver read 0.01 revolutions as a one-step window, read a
    row stating both keys as no window (so the recorded one was kept), and
    raised OverflowError on ``inf``.
    """
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.windows import averaging_steps, stated_key

    for row in (
        {"LAST_REVS_AVG": "0.01"},
        {"LAST_REVS_AVG": "inf"},
        {"LAST_ITERS_AVG": "0"},
        {"LAST_ITERS_AVG": "-5"},
    ):
        with pytest.raises(CampaignConfigError):
            averaging_steps(row, per_revolution=36.0)
    both = {"LAST_REVS_AVG": "2", "LAST_ITERS_AVG": "72"}
    with pytest.raises(CampaignConfigError):
        stated_key(both)
    with pytest.raises(CampaignConfigError):
        averaging_steps(both, per_revolution=36.0)
    # A window the plan accepts still resolves, and the unstated cell is no window.
    assert averaging_steps({"LAST_REVS_AVG": "2"}, per_revolution=36.0) == 72
    assert averaging_steps({"LAST_ITERS_AVG": "40"}, per_revolution=36.0) == 40
    assert averaging_steps({"LAST_REVS_AVG": "-"}, per_revolution=36.0) is None


def test_p0400_bg_post_reaches_lower_layers_through_their_public_names():
    """PFS-2098.004: post imports neither ``cases._setup_keys`` nor ``workspace._missing_log``.

    Both names post needs are exported by their subpackage, so the contract
    between the layers is public.
    """
    import pyflightstream
    import pyflightstream.cases as cases
    import pyflightstream.workspace as workspace

    assert "TEMPLATE_SETTINGS_LEFT_OUT" in cases.__all__
    assert "missing_log_warning" in workspace.__all__
    private = {"pyflightstream.cases._setup_keys", "pyflightstream.workspace._missing_log"}
    post = Path(pyflightstream.__file__).parent / "post"
    reached = []
    for path in sorted(post.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [node.module]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            reached += [f"{path.name}:{node.lineno} {name}" for name in names if name in private]
    assert reached == []


def test_p0400_bg_one_word_selects_the_same_surfaces_in_every_resolver():
    """PFS-2104.030: an alias named like a boundary resolves alike in families and [groups].

    With alias ``Fuselage = ["Fuselage", "Canopy"]`` over a mesh with a
    boundary ``Fuselage``, a plot or section entry summed both surfaces while
    a [groups] polar (and delete_surfaces) took the boundary alone.
    """
    from pyflightstream.cases.selection import select_families, select_group_members

    inventory = ["Fuselage", "Canopy", "Wing"]
    aliases = {"Fuselage": ["Fuselage", "Canopy"]}

    def is_blade(_name: str) -> bool:
        return False

    group = select_group_members(["Fuselage"], inventory, aliases)
    assert group
    for selection in ("Fuselage", ["Fuselage"]):
        (families,) = select_families(selection, inventory, is_blade, aliases)
        assert sorted(families) == sorted(group), (selection, families, group)


def _moment(fill: Any, axis: str, method: str = "quadrature") -> Any:
    survey, _ = _survey((-2.0, 2.0), fill)
    return in_plane_moment(survey, RHO, V_INF, inlet=-2.0, outlet=2.0, axis=axis, method=method)


def test_p0400_bg_in_plane_moments_follow_the_right_handed_cross_product():
    """PFS-2105.004: M_Y and M_Z are the y and z components of r x F, on both code paths.

    A pure 1P loading at the outlet plane: ``p' = A cos(psi)`` puts +x force
    at +z, so ``M_Y = z F_x > 0``; ``p' = A sin(psi)`` puts it at +y, so
    ``M_Z = -y F_x < 0``, of the same size. A uniform transverse flux at
    ``x_p`` gives ``M_Y = -x_p F_z`` and ``M_Z = +x_p F_y``. ``axis="z"``
    returned the opposite sign on every term.
    """
    amplitude = 50.0

    def loading(trig):
        def fill(fields, lattice):
            fields["p_prime"][1] = amplitude * trig(np.asarray(lattice.psi))[None, :]

        return fill

    for method in ("quadrature", "harmonic"):
        m_y = float(_moment(loading(np.cos), "y", method).total)
        m_z = float(_moment(loading(np.sin), "z", method).total)
        assert m_y > 0.0, (method, m_y)
        assert m_z < 0.0, (method, m_z)
        assert m_z == pytest.approx(-m_y, rel=1e-9), method

    speed = 2.0

    def transverse(component):
        def fill(fields, _lattice):
            fields[component][:] = speed

        return fill

    arm_y = float(_moment(transverse("w"), "y").moment_arm_term)
    arm_z = float(_moment(transverse("v"), "z").moment_arm_term)
    assert arm_y < 0.0 < arm_z, (arm_y, arm_z)
    assert arm_z == pytest.approx(-arm_y, rel=1e-9)


def _k_1p(tmp_path: Path, name: str, frame: str, offsets: tuple[float, ...], hub) -> list[str]:
    """K_1P of the XZ stations of rotor PROP cut in ``frame``.

    An XY station in the rotor's own frame rides along, so the table is
    rewritten even where no XZ station can be placed.
    """
    from pyflightstream.post.qsteady import add_reduced_frequency_to_sections

    path = tmp_path / f"{name}.csv"
    path.write_text(
        "ROTOR,FAMILY,PLANE,Offset,Chord,Fx,Fz\n"
        + "".join(f"PROP,B,XZ,{offset},0.2,10.0,2.0\n" for offset in offsets)
        + "PROP,B,XY,1.0,0.2,8.0,1.0\n",
        encoding="utf-8",
    )
    record = SimpleNamespace(
        rotor_alias="PROP",
        rpm=1200.0,
        families_blades=["B"],
        hub_m=hub,
        axis_vector=(1.0, 0.0, 0.0),
        shaft_frame_axis="X",
    )
    layout = [
        {"families": ["B"], "plane": "XZ", "frame": frame},
        {"families": ["B"], "plane": "XY", "frame": "PROP_RMRP"},
    ]
    add_reduced_frequency_to_sections(path, cast(Any, record), velocity_m_per_s=30.0, layout=layout)
    lines = path.read_text(encoding="utf-8").splitlines()
    column = lines[0].split(",").index("K_1P")
    return [line.split(",")[column] for line in lines[1 : 1 + len(offsets)]]


def test_p0400_bg_an_mrp_cut_station_is_measured_from_the_hub(tmp_path):
    """PFS-2105.035: an MRP-frame cut's Offset is not a radius from the hub.

    The hub sits at y = 0.5 m, so MRP-frame stations at Offset 1.5 and 2.0 are
    the rotor-frame stations at 1.0 and 1.5 and carry the same K_1P. A hub off
    the cut's radial line places no station: K_1P is NA.
    """
    hub = (0.0, 0.5, 0.0)
    from_the_hub = _k_1p(tmp_path, "rotor", "PROP_RMRP", (1.0, 1.5), hub)
    from_the_mrp = _k_1p(tmp_path, "mrp", "MRP", (1.5, 2.0), hub)
    assert "NA" not in from_the_hub
    assert from_the_hub != _k_1p(tmp_path, "far", "PROP_RMRP", (1.5, 2.0), hub)
    assert [float(k) for k in from_the_mrp] == pytest.approx([float(k) for k in from_the_hub])
    assert _k_1p(tmp_path, "off", "MRP", (1.5, 2.0), (0.0, 0.0, 0.3)) == ["NA", "NA"]


def test_p0400_bg_a_section_export_carries_its_file_name_and_is_not_verified(tmp_path):
    """PFS-2135.001: EXPORT_SURFACE_SECTIONS writes its file name on its own line.

    The solver read the next script line as the file name, so the 26.125
    probe's END sentinel never ran; that row cannot read verified, and a probe
    whose END sentinel did not print verifies nothing.
    """
    from pyflightstream.commands import CommandRegistry, Status
    from pyflightstream.qa import ProbeOutcome
    from pyflightstream.script import Script
    from tests.tier1_offline.test_qa_probes import FakeFlightStream, run_pilot

    entry = CommandRegistry.load().commands["EXPORT_SURFACE_SECTIONS"]
    assert entry.versions["26.125"].status is not Status.VERIFIED
    assert [arg.name for arg in entry.args if arg.own_line] == ["filename"]
    script = Script(version="26.124")
    script.emit("EXPORT_SURFACE_SECTIONS", 1, "section_1.txt")
    script.emit("PRINT", "next")
    lines = [line.strip() for line in script.render().splitlines() if line.strip()]
    at = lines.index("EXPORT_SURFACE_SECTIONS 1")
    assert lines[at + 1].endswith("section_1.txt")
    assert lines[at + 2] == "PRINT next"

    class NoEndSentinel(FakeFlightStream):
        def _say(self, message):
            if message != "PYFS_PROBE_END_PRINT":
                super()._say(message)

    results, _ = run_pilot(tmp_path, NoEndSentinel(), commands=["PRINT"])
    assert results["PRINT"].outcome is not ProbeOutcome.VERIFIED


def test_p0400_bg_the_detection_route_check_counts_every_marked_line(monkeypatch):
    """PFS-2135.031: a surface marked twice, or 16 then 0, fails the detection-route check.

    The licensed check built a dict from the log's marked lines, keeping only
    the last count per surface; it is run here on synthetic logs. The module is
    loaded by its file, so tier 1 holds no import of the licensed tier.
    """
    path = Path(__file__).resolve().parents[1] / "tier3_licensed" / "test_mesh.py"
    spec = importlib.util.spec_from_file_location("tier3_check_test_mesh", path)
    assert spec is not None and spec.loader is not None
    test_mesh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_mesh)
    check = test_mesh.test_the_detection_route_marked_the_edges_the_saved_file_carries
    runs = SimpleNamespace(one=lambda *args, **kwargs: object())
    once = "16 trailing edges marked on surface Wing\n"
    for log, passes in (
        (once, True),
        (once + once, False),
        (once + "0 trailing edges marked on surface Wing\n", False),
    ):
        monkeypatch.setattr(test_mesh, "_log", lambda _runs, _record, text=log: text)
        if passes:
            check(runs, "4103", "Wing", 16)
        else:
            with pytest.raises(AssertionError):
                check(runs, "4103", "Wing", 16)
