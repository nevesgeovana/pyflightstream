"""Integrated strips use exported positions and retain each instantaneous row."""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pyflightstream import _tokens
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import PprocSpec
from pyflightstream.post import harmonics, qsteady
from pyflightstream.post.farfield_fields import non_metre_refusal
from pyflightstream.post.guides import VARIABLE_DEFINITIONS, write_pproc_guides
from pyflightstream.post.products import read_csv_table
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.inputs import PprocArtifact
from tests.tier1_offline import test_goal036_harmonics as harmonics_tests
from tests.tier1_offline.test_f07_section_distributions import _post, _workspace

FIXTURES = Path(__file__).parent / "fixtures"
EXTRA = ("Strip_length", "Fx_int", "Fz_int", "My_int")
BASE = ("Offset", "Chord", "X_QC", "Z_QC", "Fx", "Fz", "Moment")
OFFSETS = (0.0, 0.2, 0.7, 1.0)
#: P0400 (PFS-2081.40): stations at the centers of four equal strips of [0, 1],
#: where the export places them; the extended rule tiles exactly [0, 1].
CENTERED = (0.125, 0.375, 0.625, 0.875)


def _spec(option=None, *, validate=True):
    entry = {"families": "Blade1", "frame": "LOCAL_AXIS", "planes": ["XZ"], "count": 4}
    data = {
        "sections": {"distributions": [entry]},
        "products": {"sections": True},
        "groups": {"TOTAL": "all"},
    }
    if option is not None and validate:
        entry["integrate"] = option
    if validate:
        try:
            return PprocArtifact.model_validate(data)
        except ValidationError as error:
            pytest.fail(f"the distribution must accept integrate={option}: {error}")
    # Exercise the writer on the old tree too, before the option is registered.
    spec = PprocSpec.model_validate(data)
    spec.sections.distributions[0] = spec.sections.distributions[0].model_copy(
        update={"integrate": option}
    )
    return spec


def _case(tmp_path, monkeypatch, *, option=True, blocks=None, stamped=False, validate=False):
    workspace, record = _workspace(tmp_path, monkeypatch, stamped=stamped)
    record.mesh_import = {"units": "METER"}
    spec = _spec(option, validate=validate)
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: spec)
    blocks = blocks or [OFFSETS]
    record.sections_layout = [
        {
            "distribution": 1,
            "distribution_families": "Blade1",
            "families": [f"Blade{k}"],
            "plane": "XZ",
            "frame": f"ROTOR_RMRP{k}",
            "count": len(offsets),
        }
        for k, offsets in enumerate(blocks, 1)
    ]
    # Match the synthetic blocks explicitly, including variable counts used
    # to exercise strip failures. Recorded ownership still groups one file.
    entry = spec.sections.distributions[0]
    spec.sections.distributions = [
        entry.model_copy(
            update={"families": f"Blade{k}", "frame": "LOCAL_AXIS", "count": len(offsets)}
        )
        for k, offsets in enumerate(blocks, 1)
    ]
    record.density_kg_m3 = 2.0 / (30.0**2 * 11.5)  # q S = 1 N
    sim = workspace.sim_dir("7001")
    # A synthetic one-blade polar states the exact integrals on [0, 1]:
    # Fx=2+3r -> 3.5 N; Fz=1+r^2 -> 4/3 N; My=4-2r -> 3 N m.
    native = sim / "AL-020.txt"
    loads = native.read_text()
    loads = re.sub(
        r"(?m)^     (Wing|Total),.*$",
        lambda m: (
            f"     {'Blade1' if m[1] == 'Wing' else 'Total'},"
            "3.5,0,1.333333333333333,1.333333333333333,3.5,0,0,2,0"
        ),
        loads,
    )
    native.write_text(loads)
    for path in sim.glob("AL-020_sloads*.txt"):
        text = path.read_text()
        numeric = [line for line in text.splitlines() if re.match(r"\s*[-+]?\d+\.\d+E", line)]
        first = text.index(numeric[0])
        last = text.index(numeric[-1]) + len(numeric[-1])
        match = re.search(r"iteration=(\d+)", path.name)
        scale = int(match[1]) if match else 1
        samples = [
            (r, 1, 0.25, 0, scale * (2 + 3 * r), scale * (1 + r**2), scale * (4 - 2 * r))
            for offsets in blocks
            for r in offsets
        ]
        rows = "\n".join(
            "     " + ",".join(f"{v:.12E}" for v in sample) + "," for sample in samples
        )
        text = text[:first] + rows + text[last:]
        text = re.sub(r"(Number of Surface Sections:\s*)2", rf"\g<1>{len(samples)}", text)
        path.write_text(text)
    return workspace


def _table(workspace):
    out, _ = _post(workspace)
    path = out / "sections/AL-020_sloads_Blade1.csv"
    return path, *read_csv_table(path)


def test_p0430_nonmetre_mesh_refuses_unmeasured_strip_integration(tmp_path, monkeypatch):
    workspace = _case(tmp_path, monkeypatch)
    record = workspace.read_manifest()[0]
    record.mesh_import = {"units": "MILLIMETER"}
    with pytest.warns(PyflightstreamWarning, match="MILLIMETER"):
        _, columns, rows = _table(workspace)
    assert rows and not set(EXTRA) & set(columns)


@pytest.mark.parametrize("mesh_import", [None, {}, {"units": None}])
def test_p0440_missing_mesh_units_keep_raw_sections(tmp_path, monkeypatch, mesh_import):
    workspace = _case(tmp_path, monkeypatch)
    workspace.read_manifest()[0].mesh_import = mesh_import
    with pytest.warns(PyflightstreamWarning, match="units.*unmeasured"):
        _, columns, rows = _table(workspace)
    assert rows and not set(EXTRA) & set(columns)


def test_p0440_integration_admission_has_a_checked_type_boundary():
    import inspect

    from pyflightstream.post import section_distributions

    unchecked = [
        name
        for name, function in inspect.getmembers(section_distributions, inspect.isfunction)
        if function.__module__ == section_distributions.__name__ and not function.__annotations__
    ]
    assert not unchecked, f"function bodies omitted from type checking: {unchecked}"


def test_opt_in_columns_and_glossary(tmp_path, monkeypatch):
    workspace = _case(tmp_path, monkeypatch)
    _, columns, rows = _table(workspace)
    assert tuple(columns[-11:]) == (*BASE, *EXTRA), "integrated columns missing after Moment"
    assert [float(rows[0][name]) for name in EXTRA] == pytest.approx([0.2, 0.4, 0.2, 0.8])
    for token, name in zip(("STRIP_LENGTH", "FX_INT", "FZ_INT", "MY_INT"), EXTRA, strict=True):
        assert getattr(_tokens, token, None) == name
        assert name in VARIABLE_DEFINITIONS
    write_pproc_guides(tmp_path / "guides")
    guide = (tmp_path / "guides/VARIABLES.md").read_text()
    assert all(f"`{name}`:" in guide for name in EXTRA)
    assert _spec(True).sections.distributions[0].integrate is True


@pytest.mark.parametrize("option", [None, False])
def test_off_is_byte_identical(tmp_path, monkeypatch, option):
    workspace = _case(tmp_path, monkeypatch, option=option, validate=True)
    path, columns, _ = _table(workspace)
    assert tuple(columns[-7:]) == BASE
    assert path.read_bytes() == (FIXTURES / "sloads_unintegrated.csv").read_bytes()


def test_uneven_midpoint_lengths(tmp_path, monkeypatch):
    _, columns, rows = _table(_case(tmp_path, monkeypatch))
    assert "Strip_length" in columns, "midpoint strip lengths missing"
    widths = [float(row["Strip_length"]) for row in rows]
    # P0400 (PFS-2081.40): the end strips reach half a spacing beyond the end stations.
    assert widths == pytest.approx([0.2, 0.35, 0.4, 0.3], abs=1e-12)
    assert sum(widths) == pytest.approx(1.25)


@pytest.mark.requirement("FR-116")
def test_linear_closed_form_integral(tmp_path, monkeypatch):
    """Linear densities integrate exactly at strip centers; 2e-5 allows CSV half-ulp errors."""
    _, columns, rows = _table(_case(tmp_path, monkeypatch, blocks=[CENTERED]))
    assert "Fx_int" in columns, "closed-form integral has no integrated forces"
    assert sum(float(r["Fx_int"]) for r in rows) == pytest.approx(3.5, abs=2e-5)
    assert sum(float(r["My_int"]) for r in rows) == pytest.approx(3.0, abs=2e-5)


def test_blade_strip_sum_matches_fixture_polar(tmp_path, monkeypatch):
    """Band (L04, P0400): 0.00523 N -- the midpoint rule's error h^2/24 f'' plus CSV rounding.

    Fz=1+r^2 on [0,1] has integral 4/3 N. With the stations at the centers
    of four equal strips (the extended rule, PFS-2081.40), the strips are the
    composite midpoint rule: h = 0.25 gives 0.0052083 N error. Four strip
    roundings plus one polar rounding add at most 0.000025 N. The band is
    fixed analytically, independent of the writer's result. The fixture's
    native total states that exact integral with q S = 1 N.
    """
    workspace = _case(tmp_path, monkeypatch, blocks=[CENTERED])
    path, columns, rows = _table(workspace)
    assert "Fz_int" in columns, "blade strips cannot be compared with the fixture polar"
    polars = list((path.parent.parent / "polars").glob("*.csv"))
    assert polars, "the same fixture must also produce its total polar"
    _, polar = read_csv_table(polars[0])
    assert float(polar[0]["CLB"]) == pytest.approx(4 / 3, abs=5e-6)
    assert sum(float(r["Fz_int"]) for r in rows) == pytest.approx(
        float(polar[0]["CLB"]), abs=0.00523, rel=0
    )


def test_each_step_and_block_is_integrated_separately(tmp_path, monkeypatch):
    workspace = _case(tmp_path, monkeypatch, blocks=[OFFSETS, (2, 2.4, 3)], stamped=True)
    _, columns, rows = _table(workspace)
    assert "My_int" in columns, "instant integrated moments missing"
    for step in (3, 4, 5):
        for family, widths in (("Blade1", [0.2, 0.35, 0.4, 0.3]), ("Blade2", [0.4, 0.5, 0.6])):
            selected = [r for r in rows if r["STEP"] == str(step) and r["FAMILY"] == family]
            assert [float(r["Strip_length"]) for r in selected] == pytest.approx(widths)
            for row in selected:
                r = float(row["Offset"])
                assert float(row["My_int"]) == pytest.approx(
                    step * (4 - 2 * r) * float(row["Strip_length"]), abs=5e-6
                )


@pytest.mark.parametrize(
    "offsets,reason",
    [
        ((0.0,), "at least two"),
        ((0, 0.7, 0.2), "monotonic"),
        ((0, 0.2, float("nan")), "finite"),
        ((0, 0.2, 0.2), "monotonic"),
    ],
)
def test_invalid_distribution_warns_and_keeps_plain_file(tmp_path, monkeypatch, offsets, reason):
    workspace = _case(tmp_path, monkeypatch, blocks=[OFFSETS, offsets], stamped=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, columns, rows = _table(workspace)
    messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    assert any(
        "AL-020" in m and "AL-020_sloads_Blade1.csv" in m and reason in m for m in messages
    ), f"missing named integration warning: {messages}"
    assert tuple(columns[-7:]) == BASE
    assert len(rows) == 3 * (4 + len(offsets))


def test_descending_offsets_tile_the_same_interval(tmp_path, monkeypatch):
    _, columns, rows = _table(_case(tmp_path, monkeypatch, blocks=[tuple(reversed(OFFSETS))]))
    assert "Strip_length" in columns, "descending monotonic stations were not integrated"
    assert [float(r["Strip_length"]) for r in rows] == pytest.approx([0.3, 0.4, 0.35, 0.2])


def _reordered_case(tmp_path, monkeypatch, *, legacy=False, ambiguous=False):
    # Strip-centred stations, so the extended rule (PFS-2081.40) tiles exactly [0, 1].
    workspace = _case(tmp_path, monkeypatch, blocks=[CENTERED, CENTERED])
    record = workspace.read_manifest()[0]
    for position, (block, family) in enumerate(
        zip(record.sections_layout, ("Wing", "Blade1"), strict=True), 1
    ):
        block.update(
            distribution=position, distribution_families=family, families=[family], frame="MRP"
        )
        if legacy:
            del block["distribution"]
            del block["distribution_families"]
    blade = {"families": "Blade1", "planes": ["XZ"], "count": 4, "integrate": True}
    wing = {"families": "Wing", "planes": ["XZ"], "count": 4}
    entries = [blade, wing]
    if ambiguous:
        record.aliases["blade_alias"] = ["Blade1"]
        entries.append({**blade, "families": "blade_alias", "integrate": False})
    spec = PprocSpec.model_validate({"sections": {"distributions": entries}})
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: spec)
    return workspace


@pytest.mark.parametrize("legacy", [False, True])
def test_reordered_pproc_integrates_recorded_blade(tmp_path, monkeypatch, legacy):
    """Record Wing then Blade, then post Blade then Wing with only Blade opted in."""
    out, manifest = _post(_reordered_case(tmp_path, monkeypatch, legacy=legacy))
    blade_path = "sections/AL-020_sloads_Blade1.csv"
    blade_columns, blade = read_csv_table(out / blade_path)
    wing_columns, wing = read_csv_table(out / "sections/AL-020_sloads_Wing.csv")
    assert tuple(blade_columns[-4:]) == EXTRA, "recorded Blade block lost its integration request"
    assert tuple(wing_columns[-7:]) == BASE, "recorded Wing inherited Blade's integration request"
    assert {r["FAMILY"] for r in blade} == {"Blade1"}
    assert {r["FAMILY"] for r in wing} == {"Wing"}
    assert sum(float(r["Fx_int"]) for r in blade) == pytest.approx(3.5, abs=2e-5)
    assert manifest["products"][blade_path]["distribution"] == (1 if legacy else 2)


def test_ambiguous_integration_warns_and_keeps_recorded_block_plain(tmp_path, monkeypatch):
    workspace = _reordered_case(tmp_path, monkeypatch, ambiguous=True)
    out, manifest = _post(workspace)
    relative = "sections/AL-020_sloads_Blade1.csv"
    columns, rows = read_csv_table(out / relative)
    assert tuple(columns[-7:]) == BASE
    assert len(rows) == 4
    log = (out / "post.log").read_text()
    assert relative in log and "ambiguous" in log, "ambiguous integration needs a named warning"
    assert "ambiguous" in manifest["skipped"].get(f"{relative}#integration", "")


@pytest.mark.parametrize("difference", [{"planes": ["XY"]}, {"frame": "other"}, {"count": 3}])
def test_integration_match_uses_plane_frame_and_count(tmp_path, monkeypatch, difference):
    workspace = _reordered_case(tmp_path, monkeypatch, ambiguous=True)
    spec = workspace.resolve_pproc("p001")
    spec.sections.distributions[-1] = spec.sections.distributions[-1].model_copy(update=difference)
    out, manifest = _post(workspace)
    relative = "sections/AL-020_sloads_Blade1.csv"
    columns, _ = read_csv_table(out / relative)
    assert tuple(columns[-4:]) == EXTRA
    assert f"{relative}#integration" not in manifest["skipped"]


METER = "$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n"
MILLIMETER = "$GLOBAL_START$\n0.001\n2\n$GLOBAL_END$\n"
PLACEHOLDER = "a placeholder with no global block\n"


def _saved(workspace, text, name):
    """Give the recorded point a saved simulation whose head is ``text``."""
    record = workspace.read_manifest()[0]
    (workspace.sim_dir(record.sim_id) / name).write_text(text, encoding="utf-8")
    record.outputs.append(name)


def test_p0420_the_refusal_names_the_unit_and_the_run_that_would_settle_it(tmp_path):
    """PFS-2119.041: the sentence says what is refused, why, and what lifts it."""
    (tmp_path / "a.fsm").write_text(MILLIMETER, encoding="utf-8")
    record = SimpleNamespace(outputs=["a.fsm"], package_version="0.42.0")
    text = non_metre_refusal(tmp_path, record, "the integrated columns")
    assert text is not None
    assert "1000 simulation length units per metre" in text
    assert "MILLIMETER sectional export" in text and "PFS-2119.041" in text


@pytest.mark.parametrize("head", [METER, PLACEHOLDER, None])
def test_p0420_a_metre_setup_and_an_unreadable_one_are_not_refused(tmp_path, head):
    """PFS-2119.041 control: the legacy behaviour is unchanged where no other unit is known."""
    outputs = []
    if head is not None:
        (tmp_path / "a.fsm").write_text(head, encoding="utf-8")
        outputs = ["a.fsm"]
    record = SimpleNamespace(outputs=outputs, package_version=None)
    assert non_metre_refusal(tmp_path, record, "x") is None


def test_p0420_the_integrated_columns_are_not_written_off_a_millimetre_setup(tmp_path, monkeypatch):
    """PFS-2119.041: Strip_length would be labelled m and Fx_int N over native lengths."""
    workspace = _case(tmp_path, monkeypatch)
    _saved(workspace, MILLIMETER, "AL-020.fsm")
    with pytest.warns(PyflightstreamWarning, match="not in metres"):
        _, columns, _ = _table(workspace)
    assert "Strip_length" not in columns and "Fx_int" not in columns
    assert tuple(columns[-7:]) == BASE


def test_p0420_the_integrated_columns_are_written_on_a_metre_setup(tmp_path, monkeypatch):
    """PFS-2119.041 control."""
    workspace = _case(tmp_path, monkeypatch)
    _saved(workspace, METER, "AL-020.fsm")
    _, columns, rows = _table(workspace)
    assert "Strip_length" in columns and len(rows) == 4


def test_p0420_a_millimetre_wheel_writes_no_harmonics_and_names_why(tmp_path, monkeypatch):
    """PFS-2119.036: STATION_R_M and R_OVER_R would treat Offset as metres."""
    workspace = harmonics_tests._wheel(tmp_path, monkeypatch, blades=6, clockings=2, rpm=1200.0)
    _saved(workspace, MILLIMETER, "DP.fsm")
    out, manifest, _ = harmonics_tests._post(workspace)
    assert not (out / "sections" / "DP_harmonics.csv").exists()
    reason = manifest["skipped"]["sections/DP_harmonics.csv"]
    assert "not in metres" in reason and "1000 simulation length units per metre" in reason
    disc = [value for key, value in manifest["skipped"].items() if "disc" in key]
    assert disc and all("no disc map" in value for value in disc)


def test_p0420_a_millimetre_wheel_writes_no_k_1p(tmp_path, monkeypatch):
    """PFS-2119.036: the validity columns that read Offset and Chord in metres are named skips."""
    workspace = harmonics_tests._wheel(tmp_path, monkeypatch, blades=6, clockings=2, rpm=1200.0)
    _saved(workspace, MILLIMETER, "DP.fsm")
    _out, manifest, _ = harmonics_tests._post(workspace)
    assert "not in metres" in manifest["skipped"]["sections/DP_sections.csv#k_1p"]


def test_p0420_a_metre_wheel_still_writes_its_harmonics(tmp_path, monkeypatch):
    """PFS-2119.036 control."""
    workspace = harmonics_tests._wheel(tmp_path, monkeypatch, blades=6, clockings=2, rpm=1200.0)
    _saved(workspace, METER, "DP.fsm")
    out, _manifest, _ = harmonics_tests._post(workspace)
    _, rows = read_csv_table(out / "sections" / "DP_harmonics.csv")
    assert rows


def test_p0420_a_millimetre_unsteady_rotor_writes_no_harmonics(tmp_path, monkeypatch):
    """PFS-2119.036: the unsteady route is refused the same way."""
    workspace = harmonics_tests._unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
    _saved(workspace, MILLIMETER, "AL-020.fsm")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        out, manifest, _ = harmonics_tests._post(workspace)
    assert not (out / "sections" / "AL-020_harmonics.csv").exists()
    assert "not in metres" in manifest["skipped"]["sections/AL-020_harmonics.csv"]


def test_p0420_one_station_tolerance_serves_the_harmonics_and_the_quasi_steady_alignment():
    """PFS-2124.036: the two modules read one value, a thousandth of the largest radius."""
    assert harmonics.STATION_MATCH_TOLERANCE == qsteady.STATION_TOLERANCE == 1e-3
