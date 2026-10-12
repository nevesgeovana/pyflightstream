"""P0400-STREAMLINES (FR-460): a pproc's [streamlines] table traces streamlines on every point.

The table is read and refused at reading (R4); a steady and an unsteady row
emit the trace after the solve and before the exports, against goldens (R1,
R2), with the evidence gate exercised both ways (R-GATE); the plan states the
count (R3); the rows R5 names are refused; the additional extraction deletes
first (R6); and the post writes the VTK polylines of the observed 26.123
export (R7).

THE GATE. The streamline commands were recorded ``documented`` and unprobed on
26.124 when the route was written, so a row reaching them is refused at plan
(R-GATE). The golden tests open the gate only where the database does not
already verify every command on the build (:func:`_open_gate`): once the
licensed probes record them verified, the goldens run the real path unpatched.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import _gap_evidence, build_script, streamline_count
from pyflightstream.cases.workflows._streamlines import streamline_commands
from pyflightstream.post.streamlines import render_streamlines_vtk, write_streamline_products
from pyflightstream.results import parse_off_body_streamlines
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import (
    _case_for,
    _wb_geometry,
    _with_pproc,
    steady_case,
)

GOLDENS = Path(__file__).parent / "goldens"
FIXTURES = Path(__file__).parent / "fixtures"
BUILD = "26.124"

_TABLE: dict[str, object] = {
    "surface": True,
    "direction": "downstream",
    "length_m": 6.0,
    "lines": [
        {"frame": "REFERENCE", "start": [-0.5, 1.9, -0.1], "end": [-0.5, 1.9, 0.1], "count": 20}
    ],
    "tubes": [
        {
            "frame": "MRP",
            "axis": "X",
            "origin": [-0.3, 0.0, 0.0],
            "radius": 0.9,
            "radial": 4,
            "circular": 12,
        }
    ],
}


def _spec(**table: object) -> PprocSpec:
    return PprocSpec.model_validate({"groups": {"1": "all"}, "streamlines": table or _TABLE})


def _open_gate(monkeypatch: pytest.MonkeyPatch, spec: PprocSpec) -> None:
    """Open the evidence gate for the commands the database does not yet verify on BUILD."""
    script = Script(BUILD)
    assert spec.streamlines is not None
    commands = streamline_commands(spec.streamlines, reopened=True)
    if all(_gap_evidence.command_verified(script, name) for name in commands):
        return
    monkeypatch.setattr(_gap_evidence, "command_verified", lambda script, command: True)


def _script(tmp_path: Path, run_type: str, spec: PprocSpec) -> Script:
    """Build one row of ``run_type`` naming ``spec``, its outputs as the pproc declares them."""
    base = steady_case() if run_type == "steady" else _case_for(run_type)
    tmp_path.mkdir(parents=True, exist_ok=True)
    case = _with_pproc(base, _wb_geometry(tmp_path), pproc=spec)
    names = [name.replace("{name}", "P") for name in spec.outputs(run_type != "steady")]
    case = case.model_copy(update={"outputs": names})
    script = Script(BUILD)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        build_script(case, script)
    return script


def _tail(script: Script) -> str:
    """The lines from the first streamline command to the end of the script."""
    lines = script.render().splitlines()
    first = next(i for i, line in enumerate(lines) if "STREAMLINE" in line or "STREAMTUBE" in line)
    return "\n".join(lines[first:]) + "\n"


# --------------------------------------------------------------------------- R4, reading


@pytest.mark.parametrize(
    ("table", "words"),
    [
        ({"surface": True, "length_m": 1.0, "unrestricted": True}, "alternatives"),
        ({"surface": False}, "traces nothing"),
        ({"surface": True, "direction": "upstream"}, "apply to off-body"),
        (
            {"lines": [{"start": [0, 0, 0], "end": [1, 0, 0], "count": 1}]},
            "NEW_OFF_BODY_STREAMLINE",
        ),
        ({"lines": [{"start": [0, 0, 0], "end": [0, 0, 0], "count": 3}]}, "two distinct"),
        ({"surface": True, "colour": "red"}, "colour"),
    ],
)
def test_p0400_streamlines_reading_refuses_by_key(table, words):
    """P0400-STREAMLINES (FR-460 R4): each refusal names its key or the broken single seed."""
    with pytest.raises(ValidationError, match=words):
        PprocSpec.model_validate({"streamlines": table})


def test_p0400_streamlines_outputs_and_count():
    """P0400-STREAMLINES (FR-460 R2, R3): the two export names and the count of 20 + 4 * 12."""
    spec = _spec()
    names = spec.outputs(False)
    assert "{name}_sls.txt" in names and "{name}_slo.txt" in names
    assert spec.streamlines is not None and spec.streamlines.off_body_count() == 68
    surface_only = _spec(surface=True)
    assert "{name}_slo.txt" not in surface_only.outputs(False)
    assert "{name}_sls.txt" not in PprocSpec().outputs(False)


def test_p0400_streamlines_exports_cannot_name_them():
    """P0400-STREAMLINES (FR-460 R2): [exports] cannot switch a trace on or off."""
    with pytest.raises(ValidationError, match=r"\[streamlines\] table"):
        PprocSpec.model_validate({"exports": {"streamlines_off_body": True}})


# --------------------------------------------------------------------------- R1, R2, R-GATE


@pytest.mark.parametrize("run_type", ["steady", "unsteady"])
def test_p0400_streamlines_golden(tmp_path, monkeypatch, run_type):
    """P0400-STREAMLINES (FR-460 R1, R2): the trace after the solve, before the exports."""
    spec = _spec()
    _open_gate(monkeypatch, spec)
    script = _script(tmp_path, run_type, spec)
    heads = [line.split()[0] for line in script.render().splitlines() if line[:1].isalpha()]
    assert heads.index("START_SOLVER") < heads.index("GENERATE_ALL_SURFACE_STREAMLINES")
    assert heads.index("GENERATE_ALL_OFF_BODY_STREAMLINES") < heads.index(
        "EXPORT_ALL_OFF_BODY_STREAMLINES"
    )
    assert "DELETE_ALL_SURFACE_STREAMLINES" not in heads, "a fresh script has nothing to delete"
    golden = GOLDENS / f"p0400_streamlines_{run_type}.txt"
    assert _tail(script) == golden.read_text(encoding="utf-8")


def test_p0400_streamlines_gate_refuses_an_unprobed_build(tmp_path, monkeypatch):
    """P0400-STREAMLINES (FR-460 R-GATE): an unverified command is refused by name at plan."""
    monkeypatch.setattr(
        _gap_evidence,
        "command_verified",
        lambda script, command: command != "NEW_OFF_BODY_STREAMTUBE",
    )
    with pytest.raises(CampaignConfigError, match="NEW_OFF_BODY_STREAMTUBE.*probe"):
        _script(tmp_path, "steady", _spec())


def test_p0400_streamlines_gate_reads_the_database(tmp_path):
    """P0400-STREAMLINES (FR-460 R-GATE): the predicate reads the build's recorded status."""
    script = Script(BUILD)
    assert _gap_evidence.command_verified(script, "NEW_STREAMLINE_DISTRIBUTION")
    assert not _gap_evidence.command_verified(script, "NEW_OFF_BODY_STREAMLINE")
    assert not _gap_evidence.command_verified(script, "NO_SUCH_COMMAND")


def test_p0400_streamlines_plan_count(tmp_path):
    """P0400-STREAMLINES (FR-460 R3): the plan's count is the pproc's off-body count."""
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path), pproc=_spec())
    assert streamline_count(case) == 68
    assert streamline_count(steady_case()) == 0


# --------------------------------------------------------------------------- R5


def test_p0400_streamlines_qsteady_rotor_refuses_off_body_names_the_frame(tmp_path, monkeypatch):
    """P0400-STREAMLINES (FR-460 R5): off-body lines on qsteady_rotor name the rotor-fixed frame."""
    from pyflightstream.cases.workflows._streamlines import refuse_streamlines_where_they_cannot_run

    spec = _spec()
    assert spec.streamlines is not None
    case = _case_for("qsteady_rotor").model_copy(update={"pproc": spec, "pproc_id": "p9"})
    with pytest.raises(CampaignConfigError, match="rotor-fixed frame"):
        refuse_streamlines_where_they_cannot_run(case, spec.streamlines)
    surface = _spec(surface=True)
    assert surface.streamlines is not None
    refuse_streamlines_where_they_cannot_run(case, surface.streamlines)


def test_p0400_streamlines_frame_the_run_does_not_create(tmp_path, monkeypatch):
    """P0400-STREAMLINES (FR-460 R5): a frame the run does not create is refused."""
    table = {
        "lines": [{"frame": "NOWHERE", "start": [0, 0, 0], "end": [1, 0, 0], "count": 2}],
    }
    spec = _spec(**table)
    _open_gate(monkeypatch, spec)
    with pytest.raises(CampaignConfigError, match="NOWHERE"):
        _script(tmp_path, "steady", spec)


# --------------------------------------------------------------------------- R6


def test_p0400_streamlines_reopened_deletes_first(monkeypatch):
    """P0400-STREAMLINES (FR-460 R6): an extraction deletes what the saved simulation carries."""
    spec = _spec()
    assert spec.streamlines is not None
    commands = streamline_commands(spec.streamlines, reopened=True)
    assert commands[:2] == ["DELETE_ALL_SURFACE_STREAMLINES", "DELETE_ALL_OFF_BODY_STREAMLINES"]
    assert "DELETE_ALL_SURFACE_STREAMLINES" not in streamline_commands(spec.streamlines)


def test_p0400_streamlines_additional_outputs():
    """P0400-STREAMLINES (FR-460 R6): an additional pproc's extraction declares the traces."""
    from pyflightstream.cases.workflows._additional import (
        additional_outputs,
        refuse_what_a_saved_point_cannot_give,
    )

    spec = _spec()
    refuse_what_a_saved_point_cannot_give(spec, pproc_id="p9", where="row")
    names = additional_outputs(spec, stem="P", unsteady=False)
    assert "P_sls.txt" in names and "P_slo.txt" in names


# --------------------------------------------------------------------------- R7


def test_p0400_streamlines_vtk_of_the_observed_export(tmp_path):
    """P0400-STREAMLINES (FR-460 R7): three polylines of thirty points, with the variables."""
    source = tmp_path / "P_slo.txt"
    source.write_bytes((FIXTURES / "off_body_streamlines_26.123.txt").read_bytes())
    outcomes = write_streamline_products(
        {"streamlines_off_body": source, "streamlines_surface": tmp_path / "P_sls.txt"},
        tmp_path / "post",
        "P",
    )
    written = outcomes["P_off_body.vtk"]
    assert isinstance(written, Path)
    text = written.read_text(encoding="utf-8")
    report = parse_off_body_streamlines(source.read_text(encoding="utf-8"))
    total = sum(line.points for line in report.streamlines)
    assert f"POINTS {total} double" in text
    assert f"LINES {report.count} {total + report.count}" in text
    for name in (
        "SCALARS Mach",
        "SCALARS Cp_ref",
        "SCALARS vtot",
        "SCALARS Cp",
        "VECTORS velocity",
    ):
        assert name in text
    assert "not yet measured" in str(outcomes["P_surface.vtk"])
    first = report.streamlines[0].values[0]
    assert f"{float(first[0])!r} {float(first[1])!r} {float(first[2])!r}" in text
    assert render_streamlines_vtk(report, title="t").startswith("# vtk DataFile Version 3.0")


def test_p0400_streamlines_vtk_off_writes_nothing(tmp_path):
    """P0400-STREAMLINES (FR-460 R7): vtk = false writes no product."""
    assert write_streamline_products({}, tmp_path, "P", vtk=False) == {}
