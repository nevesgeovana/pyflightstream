"""Shared offline fixture builders and record readers, with one definition each."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from pyflightstream._fsm import MESH_MARKER
from pyflightstream.cases import SimCase
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace


def no_sleep(_seconds: float) -> None:
    """The clock, injected. A suite that waited two seconds per point is a suite nobody runs."""


def script_lines(case: SimCase, build: str = "26.124") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_mesh_fixture(path: Path, names: Sequence[str]) -> Path:
    """Write the smallest saved simulation carrying a mesh block.

    Built from the format's own shape rather than copied from a campaign
    geometry, for two reasons: those files are 1 to 9 MB, and some of
    them are derivatives that may not be distributed. What is reproduced
    here is exactly what the reader reads, including the two junk lines
    between the marker and the count and the head numbers STARTING AT 2,
    which is what seven of the eight real geometries do and what makes a
    reader that mistook the head number for the index wrong here.
    """
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    # `newline=""` because the CRLF here is DATA, not formatting. Without
    # it the platform translates each "\n" again and the file gains a
    # blank line between every record, which the reader then reports as a
    # count line that is not a number. The real geometries are CRLF, so
    # this writes the bytes they carry rather than the bytes this
    # platform would have chosen.
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


#: The fixture folder of the tier-1 tests, and the matrices every library fixture is read from.
FIXTURES = Path(__file__).parent / "tier1_offline" / "fixtures"
FIXTURE = FIXTURES / "matrix.fs"
REGISTRY_FIXTURE = FIXTURES / "matrix_registry.fs"

#: Artifact bodies by the THREE-DIGIT TAIL of the code that names them.
#:
#: The fixtures spell their REF, SET and ENTRY codes with a kind letter
#: (``r003``, ``s002``, ``e001``) while a matrix written inline by a test
#: still spells them bare (``003``), and both are legitimate ids: the
#: input library resolves whatever the column says. Keying by the tail is
#: what lets one library cover both, so a fixture that changes its
#: spelling does not silently take the whole module red.
REFERENCE_BODIES = {
    "003": "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n",
    "004": "area_m2 = 12.0\nchord_m = 1.5\nspan_m = 9.0\n",
}
SETUP_BODIES = {
    "002": "iterations = 800\nconvergence = 1e-6\n",
    "003": "iterations = 400\nwake_layers = 4\n",
}
#: Keyed by NUMBER since 0.13.0 (PFS-2032.03): the polar table written per
#: group carries the number in its name, and a word there is refused at plan.
GROUP_BODIES = {"001": '[groups]\n"1" = "all"\n"2" = "wing_left"\n'}


def fixture_codes(path=FIXTURE):
    """Return the REF, SET and ENTRY codes one fixture actually spells.

    Read from the file rather than written here, so the assertions below
    name the codes the matrix names and cannot drift from it.
    """
    rows = read_matrix(path, active_only=False)
    return {
        "ref": [row.ref_code for row in rows],
        "set": [row.set_code for row in rows],
        "entry": [row.pproc_code for row in rows],
    }


def make_library(tmp_path, *, register_build=None):
    """Build a synthetic workspace input library covering the fixtures."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.inputs_dir
    spelled = {"references": set(), "setups": set(), "pproc": set()}
    for path in (FIXTURE, REGISTRY_FIXTURE):
        codes = fixture_codes(path)
        spelled["references"] |= set(codes["ref"])
        spelled["setups"] |= set(codes["set"])
        spelled["pproc"] |= set(codes["entry"])
    # The body tables are keyed by the bare three-digit code, which is
    # what the codes were before 0.8.0. Every id the library can resolve
    # now DECLARES its kind with a leading letter (PFS-2009.01), so the
    # letter is added here rather than staging both spellings: a bare
    # file is one no id can reach, and leaving it on disk would teach a
    # later reader that the old spelling still resolves. Measured
    # 2026-08-19: it staged six such files, found by the currency guard
    # over this builder rather than by any test of the library itself.
    for tail in REFERENCE_BODIES:
        spelled["references"].add(f"r{tail}")
    for tail in SETUP_BODIES:
        spelled["setups"].add(f"s{tail}")
    for tail in GROUP_BODIES:
        spelled["pproc"].add(f"p{tail}")
    for subdir, bodies in (
        ("references", REFERENCE_BODIES),
        ("setups", SETUP_BODIES),
        ("pproc", GROUP_BODIES),
    ):
        for code in sorted(spelled[subdir]):
            body = bodies.get(code[-3:])
            if body is not None:
                (inputs / subdir / f"{code}.toml").write_text(body, encoding="utf-8")
    if register_build is not None:
        build_id, exe_path = register_build
        with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
            handle.write(f'"{build_id}" = "{exe_path}"\n')
    return workspace


def stage_geometry(workspace, name, body=b"fake simulation"):
    """Put one file in the workspace geometry library and return its path."""
    path = workspace.inputs_dir / "geometries" / name
    path.write_bytes(body)
    return path


#: The build the rotor fixture row and its workspace register, and the cell the row carries for
#: CORES and WALLTIME before a test rewrites it.
ROTOR_BUILD = "26.123"
_ROW_FORM = "| 8     | 1h       |"


def rotor_row(tmp_path, *, sweep="0.0,2.0,4.0", extra=""):
    """Write the one-row rotor matrix of the input-path tests and return its path."""
    header, rule, row, *_ = (
        (FIXTURES / "workflow_rotor_matrix.fs").read_text(encoding="utf-8").splitlines()
    )
    for before, after in (
        ("| 0.0            |", f"| {sweep:<14} |"),
        ("| -        | r003", "| wing_clean.fsm | r003"),
        ("| -     | -        | 26.120", f"| 8     | 1h       | {ROTOR_BUILD}"),
        ("LAST_REVS_AVG: 0.25", "LAST_REVS_AVG: 0.25" + extra),
    ):
        assert before in row, (before, row)
        row = row.replace(before, after)
    matrix = tmp_path / "rotor.fs"
    matrix.write_text("\n".join((header, rule, row)) + "\n", encoding="utf-8")
    return matrix


def rotor_workspace(tmp_path):
    """Return a workspace library with the rotor build registered and its geometry staged."""
    workspace = make_library(tmp_path, register_build=(ROTOR_BUILD, "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    return workspace


def grouped_plan_fixture(
    tmp_path: Path, walltimes: Sequence[str] = ("BEST", "BEST", "BEST"), sweep: str = "0.0,2.0,4.0"
):
    """Return a workspace and a matrix of one unsteady rotor polar per walltime cell (NFR-42).

    The one definition of the grouped-plan workspace the plan, split, collect and parity tests
    share; every builder it uses lives in this module.
    """
    workspace = rotor_workspace(tmp_path)
    matrix = rotor_row(tmp_path, sweep=sweep)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    assert _ROW_FORM in row
    rows = [
        row.replace("7001", str(7001 + index)).replace(_ROW_FORM, f"| 8     | {cell:<8} |")
        for index, cell in enumerate(walltimes)
    ]
    matrix.write_text("\n".join([header, rule, *rows]) + "\n", encoding="utf-8")
    return workspace, matrix
