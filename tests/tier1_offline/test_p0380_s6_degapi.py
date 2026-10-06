"""Tier 1, 0.38.0: the thin blade is public API of the workspace (FR-429, marker P0380-DEGAPI).

Pipeline role: quality gate on FR-429. ``derive_thin_blade``, ``ThinBlade`` and
``thin_blade_path`` of 0.37.0 are offered by ``pyflightstream.workspace`` with
their signatures unchanged, the ``pyfs-matrix degenerate`` command reaches the
function through that public name, and the generated API reference lists the
three. The geometry itself is held by ``test_p0340_thin_blade.py``; the blades
here are the synthetic ones that file builds.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

from pyflightstream import workspace
from pyflightstream.run import cli
from pyflightstream.workspace import _degenerate
from tests.tier1_offline.test_p0340_thin_blade import ROOT, TIP, _blade, _sha, _write_obj

REPO = Path(__file__).resolve().parents[2]
NAMES = ("derive_thin_blade", "ThinBlade", "thin_blade_path")


def _generator():
    """Load ``scripts/gen_api_reference.py`` the way the reference tests do."""
    name = "gen_api_reference"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _source(folder: Path, *, name: str = "blade.obj") -> Path:
    """Write the synthetic closed blade into ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    vertices, faces = _blade()
    return _write_obj(folder / name, vertices, faces)


def _command(capsys, *argv: str) -> tuple[int, str, str]:
    """Run ``pyfs-matrix degenerate`` on ``argv`` and return its code and streams."""
    code = cli.main(["degenerate", *argv])
    seen = capsys.readouterr()
    return code, seen.out, seen.err


def test_the_command_and_the_package_share_one_function_and_the_old_path_still_serves():
    """P0380-DEGAPI (FR-429 R1): the command module's derive_thin_blade IS the
    workspace's, the three names are declared in __all__ and the private module still
    defines the same objects with unchanged signatures."""
    assert cli.derive_thin_blade is workspace.derive_thin_blade
    # the identity alone also holds for an import of the private module, so read the source
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    private = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("_degenerate")
    ]
    assert private == [], f"run/cli.py imports the private module at line(s) {private}"
    for name in NAMES:
        assert name in workspace.__all__
        assert getattr(workspace, name) is getattr(_degenerate, name)
    assert str(inspect.signature(workspace.derive_thin_blade)) == (
        "(geometry: 'str | Path', *, root_offset: 'float', overwrite: 'bool' = False, "
        "boundary: 'str | None' = None) -> 'ThinBlade'"
    )
    assert str(inspect.signature(workspace.thin_blade_path)) == (
        "(geometry: 'str | Path', boundary: 'str | None' = None) -> 'Path'"
    )
    assert inspect.isclass(workspace.ThinBlade)


def test_the_command_and_the_function_write_the_same_bytes(tmp_path, capsys):
    """P0380-DEGAPI (FR-429 R2): on one synthetic blade OBJ the command and the
    function write byte-identical mesh and sidecar files."""
    by_command = _source(tmp_path / "command")
    by_function = _source(tmp_path / "function")
    assert _sha(by_command) == _sha(by_function)
    code, out, err = _command(
        capsys, str(by_command), "--kind", "thin-blade", "--root-offset", "0.05"
    )
    assert code == 0, err
    made = workspace.derive_thin_blade(by_function, root_offset=0.05)
    assert out.splitlines() == [
        str(workspace.thin_blade_path(by_command)),
        str(workspace.thin_blade_path(by_command).with_name("blade_thin_blade.boundaries.toml")),
    ]
    mesh = workspace.thin_blade_path(by_command)
    assert mesh.read_bytes() == made.mesh.read_bytes() and mesh.stat().st_size > 0
    sidecar = mesh.with_name("blade_thin_blade.boundaries.toml")
    assert sidecar.read_bytes() == made.sidecar.read_bytes() and sidecar.stat().st_size > 0
    assert isinstance(made, workspace.ThinBlade)


def _garbage(folder: Path) -> tuple[Path, list[str]]:
    source = folder / "garbage.obj"
    source.write_text("v 0 0 zero\nf 1 2 3\n", encoding="utf-8")
    return source, ["--root-offset", "0.05"]


def _absent(folder: Path) -> tuple[Path, list[str]]:
    return folder / "absent.obj", ["--root-offset", "0.05"]


def _stl(folder: Path) -> tuple[Path, list[str]]:
    source = folder / "blade.stl"
    source.write_text("solid x\nendsolid x\n", encoding="utf-8")
    return source, ["--root-offset", "0.05"]


def _zero_offset(folder: Path) -> tuple[Path, list[str]]:
    return _source(folder), ["--root-offset", "0"]


def _negative_offset(folder: Path) -> tuple[Path, list[str]]:
    return _source(folder), ["--root-offset=-0.05"]


def _long_offset(folder: Path) -> tuple[Path, list[str]]:
    return _source(folder), ["--root-offset", str(TIP - ROOT)]


def _open_sheet(folder: Path) -> tuple[Path, list[str]]:
    vertices, faces = _blade(closed=False)
    folder.mkdir(parents=True, exist_ok=True)
    return _write_obj(folder / "sheet.obj", vertices, faces), ["--root-offset", "0.05"]


def _two_groups(folder: Path) -> tuple[Path, list[str]]:
    source = _source(folder, name="two.obj")
    source.write_text(source.read_text() + "o Spinner\nf 1 2 3\n", encoding="utf-8")
    return source, ["--root-offset", "0.05"]


def _no_such_boundary(folder: Path) -> tuple[Path, list[str]]:
    return _source(folder), ["--root-offset", "0.05", "--boundary", "Nacelle"]


def _already_written(folder: Path) -> tuple[Path, list[str]]:
    source = _source(folder)
    workspace.derive_thin_blade(source, root_offset=0.05)
    return source, ["--root-offset", "0.05"]


_INVALID = [
    _garbage,
    _absent,
    _stl,
    _zero_offset,
    _negative_offset,
    _long_offset,
    _open_sheet,
    _two_groups,
    _no_such_boundary,
    _already_written,
]


@pytest.mark.parametrize("build", _INVALID, ids=lambda build: build.__name__.strip("_"))
def test_every_refusal_has_the_same_text_from_the_command_and_the_function(tmp_path, capsys, build):
    """P0380-DEGAPI (FR-429 R2): a refused input gives the one message from both, the
    command prints it on standard error with exit code 2, and neither writes anything
    the other did not find."""
    source, flags = build(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    offset = float(
        flags[flags.index("--root-offset") + 1]
        if "--root-offset" in flags
        else flags[0].split("=", 1)[1]
    )
    boundary = flags[flags.index("--boundary") + 1] if "--boundary" in flags else None
    with pytest.raises(workspace.InputArtifactError) as refused:
        workspace.derive_thin_blade(source, root_offset=offset, boundary=boundary)
    text = str(refused.value)
    assert str(source) in text and text.strip()
    code, out, err = _command(capsys, str(source), "--kind", "thin-blade", *flags)
    assert code == 2 and out == ""
    # the banner of the command line precedes the refusal; the refusal is a whole line
    assert text in err.splitlines()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_the_generated_reference_lists_the_three_names():
    """P0380-DEGAPI (FR-429 R3): the API reference page of pyflightstream.workspace holds
    an entry for each of the three names, and the surface the generator reads holds them."""
    generator = _generator()
    module = "pyflightstream.workspace"
    page = generator.api_reference_pages()[f"{generator.page_slug(module)}.md"]
    assert generator.documented_names(page, module) >= set(NAMES)
    for name in NAMES:
        assert f"::: {module}.{name}\n" in page
    assert set(NAMES) <= set(generator.public_surface(module))
