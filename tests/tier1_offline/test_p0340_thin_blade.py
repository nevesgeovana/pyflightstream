"""Tier 1, 0.34.0: the thin blade derived from a blade mesh (FR-330, marker P0340-THIN-BLADE).

Pipeline role: quality gate on the library core of ``pyfs-matrix degenerate
--kind thin-blade``, :func:`pyflightstream.workspace._degenerate.derive_thin_blade`.
The command line itself (FR-330 R1 and R7) is a later package's; what is held
here is the geometry and the files.

THE ORACLE IS BUILT, NOT READ. Each test builds a cambered blade whose two sides
are mirror images about a known mean surface: a NACA-like section of 4 % camber
and 12 % thickness with a closed trailing edge, each side offset from the
camber line by the half thickness, extruded along the span in rings and closed
by a cap at each end. The mean surface the mesh carries is the camber line
through its own vertices, so the derived sheet must lie on it within round-off,
whatever stations the derivation chose. One solver-written saved simulation
(the half wing of the tier-3 library) is read too, so the saved-simulation
route is scored on a file the solver wrote.
"""

from __future__ import annotations

import hashlib
import math
import shutil
from pathlib import Path

import numpy
import pytest

from pyflightstream.workspace import InputArtifactError
from pyflightstream.workspace._degenerate import (
    CHORD_PANELS,
    derive_thin_blade,
    thin_blade_path,
)
from pyflightstream.workspace.sidecars import (
    inventory_sidecar,
    obj_boundary_names,
    read_inventory,
    read_mesh_import,
)

_LIBRARY = Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries"

#: The test blade: chord, root and tip span coordinates, chordwise points per
#: side, and the number of rings.
CHORD, ROOT, TIP, SIDE_POINTS, RINGS = 0.2, 0.2, 1.0, 30, 12


def _camber(x: numpy.ndarray) -> numpy.ndarray:
    """The NACA 4-digit mean line of 4 % camber at 40 % chord, chord 1."""
    m, p = 0.04, 0.4
    return numpy.where(
        x < p, m / p**2 * (2 * p * x - x**2), m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * x - x**2)
    )


def _half_thickness(x: numpy.ndarray) -> numpy.ndarray:
    """The NACA 4-digit half thickness of 12 %, its trailing edge closed, chord 1."""
    return 0.6 * (
        0.2969 * numpy.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4
    )


def _stations() -> numpy.ndarray:
    return 0.5 * (1 - numpy.cos(numpy.pi * numpy.arange(SIDE_POINTS + 1) / SIDE_POINTS))


def _section() -> numpy.ndarray:
    """One closed section (x, y), chord 1: leading edge, upper side, trailing edge, lower."""
    x = _stations()
    inner = x[1:-1]
    upper = numpy.column_stack([inner, _camber(inner) + _half_thickness(inner)])
    lower = numpy.column_stack([inner, _camber(inner) - _half_thickness(inner)])
    return numpy.vstack([[0.0, 0.0], upper, [1.0, 0.0], lower[::-1]])


def _chord(z: numpy.ndarray | float, taper: float) -> numpy.ndarray | float:
    """The local chord at span ``z``: CHORD at the root, less ``taper`` of it at the tip."""
    return CHORD * (1.0 - taper * (z - ROOT) / (TIP - ROOT))


def _blade(
    *, jitter: float = 0.0, closed: bool = True, taper: float = 0.0
) -> tuple[numpy.ndarray, list]:
    """Return the vertices and the triangles of the test blade, spanning z = ROOT to TIP.

    The section is scaled by CHORD and shifted so the quarter chord lies on the
    span axis. ``jitter`` moves each ring vertex along the span by up to that
    length, so the mesh is no longer built in rings. ``closed=False`` keeps the
    upper side only, an open sheet. ``taper`` shrinks the chord linearly along
    the span, each vertex scaled by the chord at its own span coordinate.
    """
    section = _section() if closed else numpy.column_stack([_stations(), _camber(_stations())])
    n = len(section)
    rng = numpy.random.default_rng(7)
    vertices = []
    for z in numpy.linspace(ROOT, TIP, RINGS):
        for x, y in section:
            at = z + (jitter * rng.uniform(-1, 1) if ROOT < z < TIP else 0.0)
            vertices.append([(x - 0.25) * _chord(at, taper), y * _chord(at, taper), at])
    faces = []
    count = n if closed else n - 1
    for k in range(RINGS - 1):
        for j in range(count):
            a, b = k * n + j, k * n + (j + 1) % n
            faces += [[a, b, b + n], [a, b + n, a + n]]
    if closed:
        for k, z in ((0, ROOT), (RINGS - 1, TIP)):
            centre = len(vertices)
            vertices.append([*(section.mean(axis=0) - [0.25, 0.0]) * _chord(z, taper), z])
            faces += [[centre, k * n + (j + 1) % n, k * n + j] for j in range(n)]
    return numpy.asarray(vertices), faces


def _write_obj(path: Path, vertices: numpy.ndarray, faces: list, group: str = "Blade1") -> Path:
    lines = [f"o {group}"]
    lines += [f"v {x!r} {y!r} {z!r}" for x, y, z in vertices.tolist()]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _read_obj(path: Path) -> numpy.ndarray:
    lines = path.read_text(encoding="utf-8").splitlines()
    return numpy.asarray(
        [[float(v) for v in line.split()[1:4]] for line in lines if line.startswith("v ")]
    )


def _off_the_mean_surface(points: numpy.ndarray) -> numpy.ndarray:
    """Distance of each point, normal to the chord, from the mesh's own mean surface."""
    x = _stations()
    xi = points[:, 0] / CHORD + 0.25
    return numpy.abs(points[:, 1] - CHORD * numpy.interp(xi, x, _camber(x)))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_thin_blade_is_the_mean_surface_between_the_two_sides(tmp_path):
    """FR-330 R2 (P0340-THIN-BLADE): every point of the derived sheet lies on the
    surface the blade's two mirror-image sides are symmetric about, within 1e-9 of
    the span, and strictly between the two sides away from the edges."""
    # P0340-THIN-BLADE, FR-330 R2: the mean surface lies between the two faces.
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    result = derive_thin_blade(source, root_offset=0.05)
    sheet = _read_obj(result.mesh)
    assert len(sheet) == result.stations * (CHORD_PANELS + 1)
    assert _off_the_mean_surface(sheet).max() <= 1e-9 * (TIP - ROOT)
    xi = sheet[:, 0] / CHORD + 0.25
    inside = (xi > 1e-6) & (xi < 1 - 1e-6)
    x = _stations()
    upper = CHORD * numpy.interp(xi, x, _camber(x) + _half_thickness(x))
    lower = CHORD * numpy.interp(xi, x, _camber(x) - _half_thickness(x))
    assert (lower[inside] < sheet[inside, 1]).all()
    assert (sheet[inside, 1] < upper[inside]).all()
    # the sheet keeps the solid section's leading and trailing edge
    assert xi.min() == pytest.approx(0.0, abs=1e-12)
    assert xi.max() == pytest.approx(1.0, abs=1e-12)


def test_a_mesh_not_built_in_rings_and_a_rotated_blade_give_the_same_mean_surface(tmp_path):
    """FR-330 R2 (P0340-THIN-BLADE): the derivation holds off the rings (sections cut
    between vertices) and in any frame (a blade turned about the origin)."""
    # P0340-THIN-BLADE, FR-330 R2: no dependence on rings or on the global axes.
    vertices, faces = _blade(jitter=0.01)
    result = derive_thin_blade(
        _write_obj(tmp_path / "loose.obj", vertices, faces), root_offset=0.05
    )
    assert _off_the_mean_surface(_read_obj(result.mesh)).max() <= 1e-9 * (TIP - ROOT)
    # a tapered blade off the rings: each section is cut between vertices, and
    # its chord (leading to trailing edge, both on edges along the span) is the
    # local chord at the station exactly, which a wrong cut point would move
    vertices, faces = _blade(jitter=0.01, taper=0.4)
    tapered = derive_thin_blade(
        _write_obj(tmp_path / "tapered.obj", vertices, faces), root_offset=0.05
    )
    rows = _read_obj(tapered.mesh).reshape(tapered.stations, CHORD_PANELS + 1, 3)
    chords = numpy.linalg.norm(rows[:, -1] - rows[:, 0], axis=1)
    assert numpy.abs(chords - _chord(rows[:, 0, 2], 0.4)).max() <= 1e-9 * (TIP - ROOT)
    turn = numpy.linalg.qr(numpy.random.default_rng(3).normal(size=(3, 3)))[0]
    vertices, faces = _blade()
    turned = derive_thin_blade(
        _write_obj(tmp_path / "turned.obj", vertices @ turn.T, faces), root_offset=0.05
    )
    back = _read_obj(turned.mesh) @ turn
    assert _off_the_mean_surface(back).max() <= 1e-9 * (TIP - ROOT)
    assert numpy.allclose(turned.span_direction, turn[:, 2], atol=1e-9)


def test_the_root_is_moved_outward_along_the_span_by_the_offset(tmp_path):
    """FR-330 R3 (P0340-THIN-BLADE): the sheet starts the root offset above the
    blade's root, ends at its tip ring, and the sidecar states the offset used."""
    # P0340-THIN-BLADE, FR-330 R3: the root offset, along the span from root to tip.
    vertices, faces = _blade()
    for offset in (0.05, 0.13):
        source = _write_obj(tmp_path / f"blade_{offset}.obj", vertices, faces)
        result = derive_thin_blade(source, root_offset=offset)
        sheet = _read_obj(result.mesh)
        assert sheet[:, 2].min() == pytest.approx(ROOT + offset, abs=1e-12)
        assert sheet[:, 2].max() == pytest.approx(TIP, abs=1e-12)
        assert result.span_direction == (0.0, 0.0, 1.0)
        assert (result.root_span, result.root_offset) == (pytest.approx(ROOT + offset), offset)
        assert f"# root_offset = {offset!r}," in result.sidecar.read_text(encoding="utf-8")
    # off the rings the root is still the lowest vertex plus the offset
    vertices, faces = _blade(jitter=0.01)
    loose = derive_thin_blade(_write_obj(tmp_path / "loose.obj", vertices, faces), root_offset=0.05)
    assert _read_obj(loose.mesh)[:, 2].min() == pytest.approx(
        vertices[:, 2].min() + 0.05, abs=1e-12
    )


def test_the_thin_blade_and_its_boundaries_are_written_beside_the_source(tmp_path):
    """FR-330 R4 and R5 (P0340-THIN-BLADE): the OBJ under a name derived from the
    source's stem and its boundary inventory beside it, readable by the raw-mesh
    route, with the source's length unit; LF line ends (NFR-32)."""
    # P0340-THIN-BLADE, FR-330 R4/R5: the output and its boundaries file beside the source.
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "rotor_blade.obj", vertices, faces, group="Blade1")
    inventory_sidecar(source).write_text(
        'boundaries = ["Blade1"]\n\n[import]\nunits = "METER"\n', encoding="utf-8"
    )
    result = derive_thin_blade(source, root_offset=0.05)
    assert result.mesh == tmp_path / "rotor_blade_thin_blade.obj" == thin_blade_path(source)
    assert result.sidecar == tmp_path / "rotor_blade_thin_blade.boundaries.toml"
    assert obj_boundary_names(result.mesh) == ("Blade1",)
    assert read_inventory(result.sidecar) == ("Blade1",)
    stated = read_mesh_import(result.sidecar)
    assert stated is not None and stated.units == "METER" and result.unit == "METER"
    for written in (result.mesh, result.sidecar):
        assert b"\r" not in written.read_bytes()
    text = result.mesh.read_text(encoding="utf-8")
    triangles = [line for line in text.splitlines() if line.startswith("f ")]
    assert len(triangles) == 2 * (result.stations - 1) * CHORD_PANELS
    assert all(len(line.split()) == 4 for line in triangles)


def test_a_source_without_a_stated_unit_gets_no_import_table(tmp_path):
    """FR-330 R5 (P0340-THIN-BLADE): a unit is never assumed; the sidecar says
    where to write it."""
    # P0340-THIN-BLADE, FR-330 R5: no [import] units invented.
    vertices, faces = _blade()
    result = derive_thin_blade(_write_obj(tmp_path / "b.obj", vertices, faces), root_offset=0.05)
    assert result.unit is None
    assert read_mesh_import(result.sidecar) is None
    assert "states no length unit" in result.sidecar.read_text(encoding="utf-8")


def test_a_saved_simulation_written_by_the_solver_is_read(tmp_path):
    """FR-330 R1 and R2 (P0340-THIN-BLADE): the half wing of the tier-3 library,
    a symmetric section written by the solver, gives a sheet on its plane of
    symmetry, its root moved off the plane the wing meets, in metres."""
    # P0340-THIN-BLADE, FR-330: the saved-simulation route.
    source = shutil.copy(_LIBRARY / "11_HALFWING.fsm", tmp_path / "half.fsm")
    result = derive_thin_blade(source, root_offset=0.1)
    sheet = _read_obj(result.mesh)
    assert result.boundary == "Wing" and result.unit == "METER"
    assert result.span_direction == (0.0, 1.0, 0.0)
    assert sheet[:, 1].min() == pytest.approx(0.1, abs=1e-12)
    assert numpy.abs(sheet[:, 2]).max() <= 1e-9 * numpy.ptp(sheet[:, 1])
    assert read_inventory(result.sidecar) == ("Wing",)


def test_the_source_is_never_modified_and_an_output_is_not_overwritten_unasked(tmp_path):
    """FR-330 R4 (P0340-THIN-BLADE): the source keeps its bytes; an existing output
    is refused, naming it, unless overwrite is given."""
    # P0340-THIN-BLADE, FR-330 R4: never modifies the source; --overwrite to rewrite.
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    before = _sha(source)
    first = derive_thin_blade(source, root_offset=0.05)
    assert _sha(source) == before
    written = _sha(first.mesh)
    with pytest.raises(InputArtifactError, match="already exists; pass overwrite") as refused:
        derive_thin_blade(source, root_offset=0.07)
    assert str(first.mesh) in str(refused.value) and "Nothing was written" in str(refused.value)
    assert _sha(first.mesh) == written
    second = derive_thin_blade(source, root_offset=0.07, overwrite=True)
    assert _sha(second.mesh) != written and _sha(source) == before


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("garbage.obj", "v 0 0 zero\nf 1 2 3\n", "cannot be read as an OBJ"),
        ("blade.stl", "solid x\nendsolid x\n", "is a .stl"),
        ("nothing.obj", "o Blade1\nv 0 0 0\n", "holds no surface mesh of a blade"),
        ("broken.fsm", "26,1\n8172026\n", "its mesh block cannot be read"),
    ],
)
def test_a_mesh_that_cannot_be_read_is_refused_by_name_and_nothing_is_written(
    tmp_path, name, content, reason
):
    """FR-330 R6 (P0340-THIN-BLADE): the refusal names the file and the reason."""
    # P0340-THIN-BLADE, FR-330 R6: an unreadable mesh is refused before anything is written.
    source = tmp_path / name
    source.write_text(content, encoding="utf-8")
    with pytest.raises(InputArtifactError, match=reason) as refused:
        derive_thin_blade(source, root_offset=0.05)
    assert str(source) in str(refused.value) and "no thin blade is derived" in str(refused.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == [name]
    with pytest.raises(InputArtifactError, match="it is not a file"):
        derive_thin_blade(tmp_path / "absent.obj", root_offset=0.05)


def test_a_mesh_whose_two_sides_cannot_be_separated_is_refused(tmp_path):
    """FR-330 R6 (P0340-THIN-BLADE): an open sheet (a blade already without
    thickness) has no closed section, and a file of two groups no single blade."""
    # P0340-THIN-BLADE, FR-330 R6: sides that cannot be separated are refused by name.
    vertices, faces = _blade(closed=False)
    sheet = _write_obj(tmp_path / "sheet.obj", vertices, faces)
    with pytest.raises(
        InputArtifactError, match="is not one closed loop.*two sides cannot be separated"
    ) as refused:
        derive_thin_blade(sheet, root_offset=0.05)
    assert str(sheet) in str(refused.value)
    vertices, faces = _blade()
    two = tmp_path / "two.obj"
    _write_obj(two, vertices, faces)
    two.write_text(two.read_text() + "o Spinner\nf 1 2 3\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"2 groups of faces \(Blade1, Spinner\)"):
        derive_thin_blade(two, root_offset=0.05)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sheet.obj", "two.obj"]


def test_a_root_offset_that_is_not_a_length_inside_the_blade_is_refused(tmp_path):
    """FR-330 R3 (P0340-THIN-BLADE): the offset is required, positive and shorter
    than the blade; a blade whose root cannot be told from its tip is refused."""
    # P0340-THIN-BLADE, FR-330 R3: the offset refusals and the root rule.
    vertices, faces = _blade()
    source = _write_obj(tmp_path / "blade.obj", vertices, faces)
    for bad in (0.0, -0.05, math.nan):
        with pytest.raises(InputArtifactError, match="is not a positive length"):
            derive_thin_blade(source, root_offset=bad)
    with pytest.raises(InputArtifactError, match="reaches the blade's last section"):
        derive_thin_blade(source, root_offset=TIP - ROOT)
    middle = vertices - [0.0, 0.0, 0.5 * (ROOT + TIP)]
    centred = _write_obj(tmp_path / "centred.obj", middle, faces)
    with pytest.raises(InputArtifactError, match="cannot be told from its tip"):
        derive_thin_blade(centred, root_offset=0.05)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["blade.obj", "centred.obj"]
