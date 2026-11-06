"""P0560-WHEEL: wake terminations carried by sector-to-wheel and marked across a merge.

Pipeline role: tier-1 oracle of PFS-2195 (FR-3720, FR-3721), PFS-2187.08 (FR-3722, FR-3723)
and PFS-2187.11 (FR-3724, the body of a nacelle marked with ``merge_into``, compared with the
body of the same sector named for its boundaries). The wheel's sector is the synthetic one of
``test_p0540_wheel``, with its blade base and nacelle base merged into their parents and one
explicit wake-termination node at the tip end of a rim. The node expected in the wheel is that
tip point turned by each copy's angle, computed here, not read from the code under test.
"""

from __future__ import annotations

import json
import tomllib
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import (
    InputArtifactError,
    NotApplicableWarning,
    PyflightstreamWarning,
)
from pyflightstream._fsm import trailing_edge_midpoints
from pyflightstream.workspace import plan_mark_boundaries
from pyflightstream.workspace._wheel import sector_to_wheel
from tests.tier1_offline.test_p0540_wheel import (
    Built,
    _write_points,
    build_sector,
    read_wheel,
    turn,
)
from tests.tier1_offline.test_p0540_wheel_fsm import build_saved_sector

COPIES = 6
RIM = '[trailing_edges.TE_a]\nfile = "sector.TE_a.te.txt"\ntype = "STANDARD"\n'
OTHER_RIM = '[trailing_edges.TE_b]\nfile = "sector.TE_b.te.txt"\ntype = "STANDARD"\n'


def terminated_sector(
    folder: Path, build: str = "26.125", *, auto: bool = False
) -> tuple[Built, np.ndarray]:
    """Write the merged sector with one explicit termination node; return it and that node.

    With ``auto`` the other rim declares autodetected terminations as well.
    """
    built = build_sector(folder, copies=COPIES, separate_base=True)
    _, tip = built.rims["TE_a"][-1]
    point = built.verts[tip]
    _write_points(folder / "sector.TE_a.wake.te.txt", [point])
    sidecar = folder / "sector.obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    assert text.count(RIM) == 1 and text.count('fs_build = "26.124"') == 1
    text = text.replace(RIM, RIM + 'wake_termination_nodes = "sector.TE_a.wake.te.txt"\n')
    if auto:
        assert text.count(OTHER_RIM) == 1
        text = text.replace(OTHER_RIM, OTHER_RIM + 'wake_termination_nodes = "auto"\n')
    sidecar.write_text(text.replace('"26.124"', f'"{build}"'), encoding="utf-8")
    return built, point


def _terminations(folder: Path) -> dict[str, str]:
    """Return the wheel's ``wake_termination_nodes`` by trailing-edge label."""
    text = (folder / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    entries = tomllib.loads(text).get("trailing_edges", {})
    return {
        label: entry["wake_termination_nodes"]
        for label, entry in entries.items()
        if isinstance(entry, dict) and "wake_termination_nodes" in entry
    }


def _record(folder: Path, stem: str = "wheel") -> dict:
    return json.loads((folder / f"{stem}.wheel.json").read_text(encoding="utf-8"))


def wheel_of(built: Built, out: Path, **options):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sector_to_wheel(
            built.obj, copies=COPIES, blades=["Blade1"], axis="x", out=out, **options
        )


@pytest.mark.requirement("FR-3720")
@pytest.mark.parametrize("build", ["26.124", "26.125", "26.127"])
def test_p0560_a_wheel_with_explicit_terminations_across_a_merge_passes_the_preview(
    tmp_path: Path, build: str
) -> None:
    built, point = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    side = (tmp_path / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    assert side.count("wake_termination_nodes") == COPIES and side.count("merge_into") == 7

    plan = plan_mark_boundaries(wheel)

    verts, _ = read_wheel(wheel)
    labels = [f"TE_a_{k + 1}" for k in range(COPIES)]
    assert sorted(plan.nodes) == labels
    for k, label in enumerate(labels):
        expected = turn(point[None, :], np.array([1.0, 0.0, 0.0]), np.zeros(3), 60.0 * k)[0]
        (node,) = plan.nodes[label]
        assert np.allclose(verts[node - 1], expected, atol=1e-9), label
    lines = plan.script.splitlines()
    marks = [i for i, line in enumerate(lines) if line == "MARK_WAKE_TERMINATION_NODES"]
    combines = [i for i, line in enumerate(lines) if line.startswith("SURFACE_COMBINE")]
    assert len(marks) == COPIES and len(combines) == 7
    assert max(marks) < min(combines)


@pytest.mark.requirement("FR-3721")
@pytest.mark.parametrize("build", ["26.126"])
def test_p0560_explicit_terminations_across_a_merge_on_an_unmeasured_build_name_the_evidence(
    tmp_path: Path, build: str
) -> None:
    built, _ = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    with pytest.raises(InputArtifactError) as caught:
        plan_mark_boundaries(wheel)
    words = str(caught.value)
    assert build in words and all(name in words for name in ("26.124", "26.125", "26.127"))
    assert "CMP-26125_2026-10-26_marking" in words


@pytest.mark.requirement("FR-3722")
def test_p0560_the_obj_route_carries_the_sector_s_terminations_by_default_and_records_it(
    tmp_path: Path,
) -> None:
    built, point = terminated_sector(tmp_path, auto=True)
    wheel_of(built, tmp_path / "wheel.obj")

    carried = _terminations(tmp_path)
    explicit = {f"TE_a_{k + 1}": k for k in range(COPIES)}
    autos = {f"TE_b_{k + 1}" for k in range(COPIES)}
    assert set(carried) == set(explicit) | autos
    assert all(carried[label] == "auto" for label in autos)
    for label, k in explicit.items():
        rows = (tmp_path / carried[label]).read_text(encoding="utf-8").split()
        assert rows[0] == "METER" and len(rows) == 2, label
        got = np.array([float(c) for c in rows[1].split(",")])
        expected = turn(point[None, :], np.array([1.0, 0.0, 0.0]), np.zeros(3), 60.0 * k)[0]
        assert np.allclose(got, expected, atol=1e-9), label
    assert _record(tmp_path)["wake_terminations"] == "carried"


@pytest.mark.requirement("FR-3723")
def test_p0560_wake_terminations_false_drops_every_termination_and_the_record_says_so(
    tmp_path: Path,
) -> None:
    built, _ = terminated_sector(tmp_path, auto=True)
    wheel_of(built, tmp_path / "wheel.obj", wake_terminations=False)

    assert _terminations(tmp_path) == {}
    assert not list(tmp_path.glob("wheel.*.wake.te.txt"))
    record = _record(tmp_path)
    assert record["wake_terminations"] == "dropped"
    assert not [name for name in record["points_files"] if ".wake." in name]
    side = (tmp_path / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    assert side.count("[trailing_edges.TE_a_") == COPIES and side.count("merge_into") == 7


@pytest.mark.requirement("FR-3723")
def test_p0560_the_command_line_drops_them_with_no_wake_terminations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pyflightstream.workspace.cli import main as workspace_main

    built, _ = terminated_sector(tmp_path)
    argv = ["geometry", "sector-to-wheel", str(built.obj), "--copies", str(COPIES)]
    argv += ["--axis", "x", "--blades", "Blade1", "--out", str(tmp_path / "wheel.obj")]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert workspace_main([*argv, "--no-wake-terminations"]) == 0
    capsys.readouterr()
    assert _terminations(tmp_path) == {}
    assert _record(tmp_path)["wake_terminations"] == "dropped"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert workspace_main([*argv, "--overwrite"]) == 0
    assert len(_terminations(tmp_path)) == COPIES
    assert _record(tmp_path)["wake_terminations"] == "carried"


@pytest.mark.requirement("FR-3723")
def test_p0560_the_saved_route_warns_that_the_switch_does_not_apply_and_carries_them(
    tmp_path: Path,
) -> None:
    sector = build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))
    with pytest.warns(NotApplicableWarning, match="wake_terminations") as caught:
        result = sector_to_wheel(
            sector,
            copies=COPIES,
            blades=["Blade1"],
            axis="x",
            out=tmp_path / "saved.fsm",
            wake_terminations=False,
        )
    assert result.written
    assert any("--no-wake-terminations" in str(item.message) for item in caught)
    assert _record(tmp_path, "saved")["wake_terminations"] == "carried"


def _body(sector: Path, out: Path):
    from pyflightstream.workspace import power_off_body

    return power_off_body(sector, blades=["Blade1"], copies=COPIES, out=out)


@pytest.mark.requirement("FR-3724")
def test_p0560_the_body_of_a_marked_nacelle_is_the_plain_body_under_the_merged_names(
    tmp_path: Path,
) -> None:
    """PFS-2187.11: the mesh and every physics value are the plain sector's; only names move."""
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector
    from tests.tier1_offline.test_p0550_wheel_mark import _marked

    plain = build_blunt_sector(tmp_path)
    marked = _marked(plain, tmp_path / "marked.fsm")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        expected = _body(plain, tmp_path / "plain_body.fsm")
    with pytest.warns(PyflightstreamWarning) as caught:
        got = _body(marked, tmp_path / "marked_body.fsm")
    assert expected.written and got.written
    lines = got.output.read_text(encoding="latin-1").splitlines()
    want = expected.output.read_text(encoding="latin-1").splitlines()
    assert len(lines) == len(want)
    differing = [(w, g) for w, g in zip(want, lines, strict=True) if w != g]
    assert differing == [("N", "NBase"), ("N", "NBase")]
    words = [str(item.message) for item in caught if "merged" in str(item.message)]
    assert len(words) == 1
    assert "NBase into N" in words[0] and "Base1 into Blade1" in words[0]
    assert "keeps NBase" in words[0] and "removes Base1" in words[0]


@pytest.mark.requirement("FR-3724")
def test_p0560_a_plain_sector_s_body_says_nothing_of_merged_families(tmp_path: Path) -> None:
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _body(build_blunt_sector(tmp_path), tmp_path / "body.fsm")
    assert result.written
    assert not [item for item in caught if "merged" in str(item.message)]


@pytest.mark.requirement("FR-3724")
def test_p0560_a_nacelle_base_under_another_boundary_s_name_is_not_guessed(tmp_path: Path) -> None:
    """The nacelle's base named for the spinner: no entry is the nacelle's, nothing is written."""
    from tests.tier1_offline.test_p0540_sector_remesh import build_blunt_sector
    from tests.tier1_offline.test_p0550_wheel_mark import _relabelled

    other = _relabelled(
        build_blunt_sector(tmp_path),
        tmp_path / "other.fsm",
        base="2\nBase1\nS\n F, F,",
        te="3\nBase1\nBase1\nNBase\n1,1,1,",
        term="2\nBase1\nBase1\n1,1,\n",
    )
    with pytest.warns(PyflightstreamWarning) as caught:
        result = _body(other, tmp_path / "body.fsm")
    words = " ".join(str(item.message) for item in caught)
    assert not result.written and not (tmp_path / "body.fsm").exists()
    assert "base region of the nacelle 'N'" in words and "0 such names" in words


# R1-MARK-001: a sector saved by FlightStream 26.127 holds the three edge-slot rows of the mesh
# block as integers, 0 for no trailing edge and the trailing-edge group's number for one
# (FR-3764). The saved route read only T/F rows there, so it warned the layout as not
# recognized and wrote no wheel.
EDGE_ROWS = (21, 22, 23)


def _first_row(lines: list[str]) -> int:
    start = lines.index("$MESH_START$")
    return start + 4 + 3 * int(lines[start + 3]) + 1


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.split(",") if cell.strip()]


def _as_26127(sector: Path, out: Path, *, value: int | None = None) -> Path:
    """Rewrite the edge-slot rows as 26.127 saves them: T as the face's group (row 5), F as 0."""
    lines = sector.read_text().split("\n")
    first = _first_row(lines)
    group = [int(v) for v in _cells(lines[first + 5])]
    for k in EDGE_ROWS:
        flags = _cells(lines[first + k])
        lines[first + k] = "".join(
            f"{(group[i] if value is None else value) if f == 'T' else 0},"
            for i, f in enumerate(flags)
        )
    out.write_text("\n".join(lines))
    return out


def _mesh_rows(path: Path) -> dict[int, list[str]]:
    lines = path.read_text().split("\n")
    first = _first_row(lines)
    return {k: _cells(lines[first + k]) for k in range(25)}


@pytest.mark.requirement("FR-3764")
def test_p0560_r1_mark_001_the_saved_route_repeats_a_26127_sector_with_each_copy_s_groups(
    tmp_path: Path,
) -> None:
    sector = build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))
    saved = _as_26127(sector, tmp_path / "sector_26127.fsm")
    out = tmp_path / "wheel.fsm"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = sector_to_wheel(saved, copies=COPIES, blades=["Blade1"], axis="x", out=out)
    assert not [w for w in caught if "not recognized" in str(w.message)]
    assert result.written
    plain = tmp_path / "plain_wheel.fsm"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sector_to_wheel(sector, copies=COPIES, blades=["Blade1"], axis="x", out=plain)
    # the trailing edges of the wheel of the same sector saved with T/F rows
    assert trailing_edge_midpoints(out) == trailing_edge_midpoints(plain)
    rows, flags = _mesh_rows(out), _mesh_rows(plain)
    group = np.array([int(v) for v in rows[5]])
    named: set[int] = set()
    for k in EDGE_ROWS:
        written = np.array([int(v) for v in rows[k]])
        marked = np.array([f == "T" for f in flags[k]])
        # the integer form is kept, and each flagged edge names its own copy's group
        assert (written[marked] == group[marked]).all()
        assert (written[~marked] == 0).all()
        named |= set(written[marked].tolist())
    # every copy's rim groups, not the sector's repeated: two blade rims per copy and the nacelle
    assert len(named) == 2 * COPIES + 1
    assert set(rows[20]) <= {"T", "F"} and set(rows[24]) <= {"T", "F"}


@pytest.mark.requirement("FR-3764")
def test_p0560_r1_mark_001_an_integer_edge_flag_that_is_not_its_face_s_group_is_not_guessed(
    tmp_path: Path,
) -> None:
    """An integer that is not the rim face's group has no measured meaning: warned, no wheel."""
    sector = build_saved_sector(tmp_path, build_sector(tmp_path, copies=COPIES))
    odd = _as_26127(sector, tmp_path / "odd.fsm", value=7)
    out = tmp_path / "odd_wheel.fsm"
    with pytest.warns(PyflightstreamWarning, match="not recognized"):
        result = sector_to_wheel(odd, copies=COPIES, blades=["Blade1"], axis="x", out=out)
    assert not result.written and not out.exists()


def _same_edges_in_the_26127_form(written: Path, plain: Path) -> None:
    """The 26.127 output marks the plain output's trailing edges, in the integer form."""
    assert trailing_edge_midpoints(written) == trailing_edge_midpoints(plain)
    assert len(trailing_edge_midpoints(written)) > 0
    rows, flags = _mesh_rows(written), _mesh_rows(plain)
    group = np.array([int(v) for v in rows[5]])
    for k in EDGE_ROWS:
        values = np.array([int(v) for v in rows[k]])
        marked = np.array([f == "T" for f in flags[k]])
        assert (values[marked] == group[marked]).all() and (values[~marked] == 0).all()


@pytest.mark.requirement("FR-3764")
def test_p0560_r1_mark_004_the_saved_sector_verbs_read_and_write_a_26127_sector(
    tmp_path: Path,
) -> None:
    """R1-MARK-004: sector-remesh, power-off-body and repitch read the flags of a sector saved
    by 26.127 and write its integer form, where they warned it as not recognized and wrote
    nothing; each output marks the trailing edges of the same verb's output on the T/F sector."""
    from pyflightstream.workspace import sector_remesh
    from tests.tier1_offline.test_p0540_sector_remesh import ARGS, build_blunt_sector
    from tests.tier1_offline.test_p0551_repitch import control, invoke

    source = build_blunt_sector(tmp_path)
    saved = _as_26127(source, tmp_path / "blunt_26127.fsm")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        remesh = sector_remesh(saved, blades=["Blade1"], out=tmp_path / "r127.fsm", **ARGS)
        plain = sector_remesh(source, blades=["Blade1"], out=tmp_path / "r.fsm", **ARGS)
        body = _body(saved, tmp_path / "b127.fsm")
        plain_body = _body(source, tmp_path / "b.fsm")
    assert remesh.written and plain.written and body.written and plain_body.written
    _same_edges_in_the_26127_form(tmp_path / "r127.fsm", tmp_path / "r.fsm")
    _same_edges_in_the_26127_form(tmp_path / "b127.fsm", tmp_path / "b.fsm")

    config = control(tmp_path, 0.0, hub="S")
    config.write_text(
        config.read_text()
        .replace("0.0, 0.0, 1.0", "0.0, 1.0, 0.0")
        .replace("origin = [0.0,", "origin = [0.65,")
    )
    out = tmp_path / "pitched127.fsm"
    assert invoke(tmp_path / "r127.fsm", config, out) == 0
    before, after = _mesh_rows(tmp_path / "r127.fsm"), _mesh_rows(out)
    assert all(before[k] == after[k] for k in EDGE_ROWS)


def test_p0560_r1_mark_002_the_upgrading_notes_say_what_changed_since_0551() -> None:
    """R1-MARK-002: the release changed behaviour a 0.55.1 user meets (a moved face order, an
    unreadable repitch sidecar, hub_method's default, quality warned instead of refused, marking
    across a merge, the body of a marked nacelle, the wheel record, 26.127 saves, the gmsh
    extra) and docs/upgrading.md had no section for it."""
    page = (Path(__file__).resolve().parents[2] / "docs" / "upgrading.md").read_text(
        encoding="utf-8"
    )
    assert "\n## 0.56.0\n" in page
    section = page.split("\n## 0.56.0\n", 1)[1].split("\n## ", 1)[0]
    for words in (
        "face order",
        "--refresh",
        'hub_method = "rings"',
        "checks.passed",
        "merge_into",
        "power-off-body",
        "wake_terminations",
        "26.127",
        'pip install "pyflightstream[gmsh]"',
    ):
        assert words in section, words
    assert page.index("\n## 0.56.0\n") < page.index("\n## 0.55.1\n")


def _two_rim_wheel(folder: Path, build: str) -> Path:
    """The wheel of the sector whose blunt blade rims come two to one file, as a sector the
    solver saved and converted declares them; return the wheel's OBJ."""
    built = build_sector(folder, copies=COPIES, separate_base=True)
    rows = [
        line
        for name in ("sector.TE_a.te.txt", "sector.TE_b.te.txt")
        for line in (folder / name).read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    ]
    (folder / "sector.TE.te.txt").write_text("\n".join(["METER", *rows]) + "\n", encoding="utf-8")
    sidecar = folder / "sector.obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    assert text.count(RIM + OTHER_RIM) == 1
    one = '[trailing_edges.TE]\nfile = "sector.TE.te.txt"\ntype = "STANDARD"\n'
    text = text.replace(RIM + OTHER_RIM, one).replace('"26.124"', f'"{build}"')
    sidecar.write_text(text, encoding="utf-8")
    wheel = folder / "wheel.obj"
    wheel_of(built, wheel)
    return wheel


@pytest.mark.parametrize(("build", "per_file"), [("26.125", 1), ("26.127", 2)])
def test_p0560_r1_mark_s2_a_file_of_two_rims_is_one_group_per_rim_on_26127(
    tmp_path: Path, build: str, per_file: int
) -> None:
    """R1-MARK-S2: on 26.127 one import is one trailing-edge group, so a file holding both
    rims of a blunt edge is imported one rim at a time: the groups the saved route copies, the
    same edges. 26.125 keeps one import per file."""
    wheel = _two_rim_wheel(tmp_path, build)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_mark_boundaries(wheel)
    imports = [line for line in plan.script.splitlines() if line.startswith("IMPORT_WAKE_EDGES")]
    # one file per blade copy and the nacelle's rim
    assert len(imports) == COPIES * per_file + 1
    labels = [entry.label for entry in plan.declarations.trailing_edges]
    spans = plan.group_spans()
    blades = [spans[i][1] for i, label in enumerate(labels) if label.startswith("TE_")]
    assert blades == [per_file] * COPIES
    # the rim files of one entry hold, together, every point of the entry once
    for entry in plan.sets:
        if not entry["label"].startswith("TE_"):
            continue
        number = plan.sets.index(entry) + 1
        stems = (f"edges-{number}", *(f"edges-{number}-{k}" for k in range(1, per_file + 1)))
        names = [n for n in plan.pending if Path(n).stem in stems]
        rows = [
            row
            for name in names
            for row in plan.pending[name].decode("utf-8").splitlines()[2:]
            if row.strip()
        ]
        assert len(names) == per_file
        assert len(rows) == len(set(rows)) == len(entry["points_m"])


NACELLE_RIM = '[trailing_edges.N]\nfile = "sector.N.te.txt"\ntype = "STANDARD"\n'
NACELLE_BASE = '[base_regions.NBase]\ntrailing_edges = "auto"\n'


@pytest.mark.requirement("FR-3765")
@pytest.mark.parametrize("build", ["26.125", "26.127"])
def test_p0560_r1_mark_s3_every_base_is_created_before_the_first_import_on_26127(
    tmp_path: Path, build: str
) -> None:
    """R1-MARK-S3: on 26.127 every wake-edge import placed before the first
    CREATE_NEW_BASE_REGION was lost at the save and every one after the creates survived
    (receipt 0.56.0/receipts/wheel-routes-0550.json, marked_counts_b67210f0b). So every base is
    created first, then every entry and file rim is imported, then the ``auto`` rims; 26.125
    keeps create, rim."""
    built = build_sector(tmp_path, copies=COPIES, separate_base=True)
    sidecar = tmp_path / "sector.obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    assert text.count(NACELLE_RIM) == 1 and text.count(NACELLE_BASE) == 1
    text = text.replace(NACELLE_RIM, "").replace(
        NACELLE_BASE,
        '[base_regions.NBase]\ntrailing_edges = { file = "sector.N.te.txt", type = "STANDARD" }\n',
    )
    sidecar.write_text(text.replace('"26.124"', f'"{build}"'), encoding="utf-8")
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_mark_boundaries(wheel)
    lines = plan.script.splitlines()
    imports = [i for i, line in enumerate(lines) if line.startswith("IMPORT_WAKE_EDGES")]
    creates = [i for i, line in enumerate(lines) if line.startswith("CREATE_NEW_BASE_REGION")]
    autos = [i for i, line in enumerate(lines) if line.startswith("SET_BASE_REGION_TRAILING")]
    assert imports and creates and autos
    if build == "26.127":
        assert max(creates) < min(imports) < max(imports) < min(autos)
    else:
        assert max(imports) > min(creates)
    # the read-back expects as many groups as the script marks
    assert sum(count for _, count in plan.group_spans()) == len(imports) + len(autos)


def test_p0560_r1_mark_005_two_declarations_of_the_same_rim_are_warned_naming_both(
    tmp_path: Path,
) -> None:
    """R1-MARK-005: a second entry naming the rim file of another is planned (never refused)
    and warned, naming both entries; a sector that declares each edge once is not."""
    built = build_sector(tmp_path, copies=COPIES, separate_base=True)
    sidecar = tmp_path / "sector.obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    dup = '[trailing_edges.TE_c]\nfile = "sector.TE_a.te.txt"\ntype = "STANDARD"\n'
    sidecar.write_text(text.replace(OTHER_RIM, OTHER_RIM + dup), encoding="utf-8")
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_mark_boundaries(wheel)
    words = [str(item.message) for item in caught if "name the same" in str(item.message)]
    assert plan.script
    assert any("TE_a_1 and TE_c_1" in line for line in words), words
    assert not any("TE_a_1 and TE_b_1" in line for line in words), words


def test_p0560_r1_mark_005_the_read_back_does_not_blame_a_replacing_import_on_26127(
    tmp_path: Path,
) -> None:
    """R1-MARK-005: the marking probes of 26.124, 26.125 and 26.127 show a second import adding
    a group and keeping the first, so the missing-edge verdict names that evidence there and
    keeps the unmeasured reading on another build."""
    import shutil

    from pyflightstream.workspace.wake_edges import saved_wake_edge_verdict

    library = Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries"
    shutil.copy(library / "10_WING.fsm", tmp_path / "wing.fsm")
    sets = [{"file": "far.te.txt", "points_m": [(99.0, 99.0, 99.0)], "tolerance": 1e-4}]
    _, measured = saved_wake_edge_verdict(sets, tmp_path, ["wing.fsm"], "26.127")
    assert "far.te.txt are missing" in measured and "replacing" not in measured
    assert "adds a group and keeps the first" in measured
    assert "CMP-26127_2026-11-06_marking" in measured
    _, other = saved_wake_edge_verdict(sets, tmp_path, ["wing.fsm"], "26.120")
    assert "replacing the first" in other
