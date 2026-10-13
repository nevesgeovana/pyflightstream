"""Tier 1, 0.40.0: CAD bodies before conversion, and the solver-built geometry (FR-475).

P0400-GEOM-CAD (PFS-2081.14). Offline goldens of the emitted lines: the
commands are documented and unprobed, and the build refuses to run them until
a licensed probe verifies them on the build; the build tests guard that gate.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import BrokenCommandError
from pyflightstream.workspace._geometry_build import plan_geometry_build
from tests.tier1_offline._p0400_gaps_rt_support import registry_with
from tests.tier1_offline.test_p0400_geometry_build import geometry, workspace


def _lines(
    tmp_path,
    text: str,
    files: dict[str, str] | None = None,
    *,
    build: str = "26.125",
    registry: CommandRegistry | None = None,
) -> list[str]:
    root = workspace(tmp_path)
    folder = geometry(root, "g", f'fs_build = "{build}"\n' + text, source=None)
    for name, content in (files or {}).items():
        (folder / name).write_text(content, encoding="utf-8")
    plan = plan_geometry_build(folder, registry=registry)
    return [line for line in plan.variants[0].script.text.splitlines() if line]


@pytest.mark.requirement("FR-475")
def test_p0400_geom_cad_body_operations_sit_between_import_and_conversion(tmp_path):
    """P0400-GEOM-CAD (PFS-2081.14): R1, every body operation, in order, in metres."""
    lines = _lines(
        tmp_path,
        'boundaries = ["Wing"]\n[cad]\nfile = "rig.igs"\n'
        '[[cad.operations]]\nop = "delete_by_threshold"\naxis = "X"\nabove_m = 1.2\n'
        '[[cad.operations]]\nop = "mirror"\nbody = 1\nplane = "XZ"\n'
        '[[cad.operations]]\nop = "scale"\nbody = 1\nfactor = 0.5\n'
        '[[cad.operations]]\nop = "translate"\nbody = 1\nvector_m = [0.1, 0.0, 0.0]\n'
        '[[cad.operations]]\nop = "rotate"\nbody = 1\naxis = "Y"\nangle_deg = 2.0\n'
        '[[cad.operations]]\nop = "delete"\nbody = 2\n'
        '[trailing_edges]\ndetect = "auto"\n',
        {"rig.igs": "IGES"},
    )
    start = next(i for i, line in enumerate(lines) if line.startswith("IMPORT_CAD"))
    assert lines[start + 2 : start + 9] == [
        "CAD_BODY_SELECT_BY_THRESHOLD 1 X 1.2 ABOVE DELETE",
        "CAD_BODY_MIRROR 1 XZ",
        "CAD_BODY_SCALE 1 0.5",
        "CAD_BODY_TRANSLATE 1 0.1 0.0 0.0 METER",
        "CAD_BODY_ROTATE 1 Y 2.0",
        "CAD_BODY_DELETE 2",
        "CONVERT_CAD_TO_MESH -1",
    ]


@pytest.mark.requirement("FR-475")
def test_p0400_geom_cad_a_sphere_is_built_by_the_solver(tmp_path):
    """P0400-GEOM-CAD (PFS-2081.14): R2, the settings then the primitive."""
    lines = _lines(
        tmp_path,
        'boundaries = ["Sphere"]\n[create]\nmerge_tolerance_pct = 1.0\n'
        "curvature_points_per_circle = 96\n\n"
        '[[create.bodies]]\nshape = "sphere"\ncenter_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n'
        "[trailing_edges]\nnone = true\n",
    )
    assert lines[1:5] == [
        "CAD_CREATE_INITIALIZE",
        "SET_CAD_CREATE_MERGE_TOLERANCE 1.0",
        "SET_CAD_CURVATURE_REFINEMENT 96",
        "CAD_CREATE_SPHERE 1 0.0 0.0 0.0 0.5",
    ]


SECTIONS = (
    'boundaries = ["WING"]\n[create]\nspline_segments = 100\n'
    '[[create.sections]]\nfile = "naca.txt"\nunits = "METER"\nchord_m = 1.0\n'
    '[[create.sections]]\nfile = "naca.txt"\nunits = "METER"\nchord_m = 0.5\ntwist_deg = -2.0\n'
    "leading_edge_m = [0.15, 2.0, 0.0]\n"
    "[create.loft]\nexport_ccs = true\n"
)


def _curve_import_verified() -> CommandRegistry:
    """The committed database with the curve import marked verified on both builds.

    The route's behaviour is held on a build-agnostic golden: the import is
    broken on 26.124 and 26.125 (RPT-166), so a copy of the database stands in
    for a build on which it works.
    """
    base = registry_with(["CAD_CREATE_IMPORT_CURVE_TXT"], "26.125", Status.VERIFIED)
    return registry_with(["CAD_CREATE_IMPORT_CURVE_TXT"], "26.124", Status.VERIFIED, base=base)


@pytest.mark.requirement("FR-475")
@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0400_geom_cad_the_loft_route_is_refused_where_the_curve_import_is_broken(tmp_path, build):
    """P0400-GEOM-CAD (PFS-2081.14): the section loft is refused on 26.124 and 26.125.

    Its sections enter through CAD_CREATE_IMPORT_CURVE_TXT, recorded broken on both
    builds (RPT-166); the evidence gate names the command and the CCS route is the
    working one.
    """
    with pytest.raises(BrokenCommandError, match="CAD_CREATE_IMPORT_CURVE_TXT is recorded broken"):
        _lines(tmp_path, SECTIONS, {"naca.txt": "1.0 0.0\n0.0 0.0\n1.0 0.0\n"}, build=build)


@pytest.mark.requirement("FR-475")
def test_p0400_geom_cad_a_wing_is_lofted_from_its_sections(tmp_path):
    """P0400-GEOM-CAD (PFS-2081.14): R2, each section placed, then the CCS loft."""
    lines = _lines(
        tmp_path,
        SECTIONS,
        {"naca.txt": "1.0 0.0\n0.0 0.0\n1.0 0.0\n"},
        registry=_curve_import_verified(),
    )
    body = [line for line in lines if not line.startswith(("C:", "/")) and "naca.txt" not in line]
    start = body.index("CAD_CREATE_INITIALIZE")
    assert body[start + 1 :][:14] == [
        "SET_CAD_CREATE_SPLINE_SEGMENTS 100",
        "CAD_CREATE_IMPORT_CURVE_TXT METER 2D 1 XZ",
        "CAD_CREATE_CURVE_SELECT 1",
        "CAD_CREATE_SCALE_CURVES 1.0 DELETE",
        "CAD_CREATE_TRANSLATE_CURVES 0.0 0.0 0.0 DELETE",
        "CAD_CREATE_CURVE_UNSELECT 1",
        "CAD_CREATE_IMPORT_CURVE_TXT METER 2D 1 XZ",
        "CAD_CREATE_CURVE_SELECT 2",
        "CAD_CREATE_SCALE_CURVES 0.5 DELETE",
        "CAD_CREATE_ROTATE_CURVES 1 Y -2.0 DELETE",
        "CAD_CREATE_TRANSLATE_CURVES 0.15 2.0 0.0 DELETE",
        "CAD_CREATE_CURVE_UNSELECT 2",
        "CAD_CREATE_CURVE_SELECT -1",
        "CAD_CREATE_CURVE_EXPORT_CCS",
    ]
    assert "CAD_CREATE_WING_MESH_FROM_CCS WING TRUE SHARP TRUE C2 C0" in lines


REFUSED = [
    (
        "bodies and sections",
        'boundaries = ["A"]\n[create]\n[[create.bodies]]\nshape = "sphere"\n'
        'center_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n[[create.sections]]\nfile = "naca.txt"\n'
        'units = "METER"\nchord_m = 1.0\n\n',
        "exactly one",
    ),
    (
        "mirror curves",
        'boundaries = ["A"]\n[create]\nmirror_curves = true\n[[create.bodies]]\n'
        'shape = "sphere"\ncenter_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n\n',
        "mirror_curves",
    ),
    ("curve drawing", 'boundaries = ["A"]\n[create]\n[[create.bodies]]\nshape = "arc"\n', "shape"),
    (
        "a radius of zero",
        'boundaries = ["A"]\n[create]\n[[create.bodies]]\nshape = "sphere"\n'
        "center_m = [0.0, 0.0, 0.0]\nradius_m = 0.0\n\n",
        "radius_m",
    ),
    (
        "a CAD op without its body",
        'boundaries = ["A"]\n[cad]\nfile = "rig.igs"\n[[cad.operations]]\nop = "mirror"\n'
        'plane = "XZ"\n\n',
        "body",
    ),
]


@pytest.mark.requirement("FR-475")
@pytest.mark.parametrize(("label", "text", "words"), REFUSED, ids=[c[0] for c in REFUSED])
def test_p0400_geom_cad_refusals(tmp_path, label, text, words):
    """P0400-GEOM-CAD (PFS-2081.14): R2 and R3, refused before any solver starts."""
    with pytest.raises(InputArtifactError, match=words):
        _lines(tmp_path, text, {"naca.txt": "1 0\n", "rig.igs": "IGES"})
