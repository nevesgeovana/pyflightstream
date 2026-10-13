"""P0400-REACH2: the workspace route runs the public probe and far-field functions (PFS-2140.011).

The rule of PFS-2140.011: every public capability is reached from the
workspace. Where the route did the job with a duplicate of a public function,
the route now calls the function, and each test pins both halves: the public
function is what the route runs (a spy that the duplicate never called), and
what the route produces is unchanged (the value or the text the duplicate
produced, computed beside it).
"""

from __future__ import annotations

import numpy as np
import pytest

import pyflightstream.cases.workflows._exports as exports_module
import pyflightstream.post.farfield_fields as farfield_fields
from pyflightstream.cases._farfield_spec import LedgersSpec
from pyflightstream.farfield import sample_coverage, transverse_flux, transverse_force
from pyflightstream.probes.layouts import emit_probe_export
from pyflightstream.script import helpers
from tests.tier1_offline.test_p0400_cases_workflows_probes import _rendered, _steady_with

_REQUIREMENT = "P0400-REACH2"

#: A steady entry with one line of three points and a two-by-two rectangle.
_STEADY_ENTRY = {
    "frame": "REFERENCE",
    "parameters": ["VX"],
    "points": 3,
    "lines": [{"start": [1.0, -0.5, 0.0], "end": [1.0, 0.5, 0.0]}],
    "rectangles": [
        {
            "origin": [2.0, -0.5, -0.25],
            "along_u": [2.0, 0.5, -0.25],
            "along_v": [2.0, -0.5, 0.25],
            "points_u": 2,
            "points_v": 2,
        }
    ],
}


class _Rotor:
    axis = "X"
    diameter_m = 2.0
    x_m, y_m, z_m = 0.5, 0.0, 0.0


def _spy(monkeypatch, module, name: str, function) -> list:
    """Replace ``module.name`` by a wrapper of ``function`` that records each call."""
    calls: list = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper, raising=False)
    return calls


def _sheared_fields():
    """A lattice sampled with a sheared, crossflowing stream and one missing sample."""
    spec = LedgersSpec(rotor="R", stations=(-1.0, 0.5, 1.5), n_r=6, n_psi=16, m_max=2)
    lattice, points_m, axis = farfield_fields.rotor_lattice(spec, _Rotor())
    y, z = points_m[:, 1], points_m[:, 2]
    velocity = np.column_stack([12.0 + 0.4 * y, 0.3 * z - 0.2, 0.5 + 0.25 * y * y])
    velocity[len(points_m) // 2 + 3] = np.nan
    samples = farfield_fields.ProbeSamples(points_m, velocity, 0.01 * y)
    fields = farfield_fields.lattice_samples(samples, slice(0, len(points_m)), lattice, axis, q=0.0)
    return spec, fields


@pytest.mark.requirement("FR-38")
def test_p0400_reach2_the_ledger_runs_transverse_force_and_sample_coverage(monkeypatch):
    """P0400-REACH2 (PFS-2139.008): the ledger runs transverse_force and sample_coverage.

    FY and FZ are transverse_force's plane term and COVERAGE is
    sample_coverage, each value the one the ledger wrote before.
    """
    spec, fields = _sheared_fields()
    forces = _spy(monkeypatch, farfield_fields, "transverse_force", transverse_force)
    coverages = _spy(monkeypatch, farfield_fields, "sample_coverage", sample_coverage)
    rows = farfield_fields.ledger_values(fields, spec, rho=1.2, speed=12.0, near=(3.0, 1.0))
    assert forces and coverages, (_REQUIREMENT, "the ledger runs the public balances")
    fy = transverse_flux(fields, 1.2, component="v")
    fz = transverse_flux(fields, 1.2, component="w")
    finite = np.isfinite(fields["u"]).mean(axis=(-2, -1))
    assert finite.min() < 1.0, "the fixture misses a sample"
    for index, row in enumerate(rows):
        assert row["COVERAGE"] == float(finite[index])
        if index:
            # The duplicate's arithmetic, bit for bit (NaN where a sample is missing).
            np.testing.assert_array_equal(
                [row["FY_PLANE_N"], row["FZ_PLANE_N"]],
                [float(fy[index] - fy[0]), float(fz[index] - fz[0])],
            )
    assert any(np.isfinite(row.get("FZ_PLANE_N", np.nan)) for row in rows[1:])


@pytest.mark.requirement("FR-79")
def test_p0400_reach2_a_steady_row_creates_its_probes_through_the_script_helpers(
    tmp_path, monkeypatch
):
    """P0400-REACH2 (PFS-2140.001): lines and drawn points go through the public helpers.

    The script carries the lines the route wrote before, one ``NEW_PROBE_LINE``
    per declared line and one ``NEW_PROBE_POINT VOLUME`` per rectangle node.
    """
    lines_called = _spy(monkeypatch, helpers, "probe_line", helpers.probe_line)
    points_called = _spy(monkeypatch, helpers, "probe_points", helpers.probe_points)
    lines, _ = _rendered(_steady_with(tmp_path, _STEADY_ENTRY))
    assert len(lines_called) == 1 and len(points_called) == 4, _REQUIREMENT
    assert lines.count("NEW_PROBE_LINE 3 1.0 -0.5 0.0 1.0 0.5 0.0") == 1
    assert [line for line in lines if line.startswith("NEW_PROBE_POINT")] == [
        "NEW_PROBE_POINT VOLUME 2.0 -0.5 -0.25",
        "NEW_PROBE_POINT VOLUME 2.0 -0.5 0.25",
        "NEW_PROBE_POINT VOLUME 2.0 0.5 -0.25",
        "NEW_PROBE_POINT VOLUME 2.0 0.5 0.25",
    ]


@pytest.mark.requirement("FR-81")
def test_p0400_reach2_a_steady_row_exports_its_probes_through_the_probes_home(
    tmp_path, monkeypatch
):
    """P0400-REACH2 (PFS-2140.001): the probe export goes through probes.emit_probe_export.

    One ``UPDATE_PROBE_POINTS`` with the other updates, then the export to the
    row's probes file, as before; the export register names the entry point.
    """
    exports_called = _spy(monkeypatch, exports_module, "emit_probe_export", emit_probe_export)
    helper_called = _spy(monkeypatch, helpers, "export_probes", helpers.export_probes)
    lines, script = _rendered(_steady_with(tmp_path, _STEADY_ENTRY))
    assert len(exports_called) == 1 and len(helper_called) == 1, _REQUIREMENT
    update = lines.index("UPDATE_PROBE_POINTS")
    export = lines.index("EXPORT_PROBE_POINTS")
    assert lines[export + 1] == "point_probes.txt" and lines.count("EXPORT_PROBE_POINTS") == 1
    assert update < export and lines.count("UPDATE_PROBE_POINTS") == 1
    assert script._exported_paths["point_probes.txt"] == "emit_probe_export"
