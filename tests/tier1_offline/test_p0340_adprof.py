"""Tier 1, 0.34.0: the actuator-disc profile generator of the workspace (FR-347).

Pipeline role: quality gate on ``pyfs-workspace profile`` and
:mod:`pyflightstream.workspace.actuator_profiles`.

The command writes the radial thrust profile a row's ``PROFILE: <stem>``
names, ``inputs/profiles/<stem>.csv``, beside its provenance record, as the
field operations write a custom free stream: from a POL's written sections
(R1), or as the uniform or the Betz-Prandtl shape (R2); scaled so that
``B * integral(F dr)`` is a thrust in newtons or a CT, never both (R3); the
integral of the written rows taken again and stated (R4); in the form the
run's copy of a profile takes (R5); previewing until applied and never
overwriting unless asked (R6); the ELLIPTICAL disc said to need no file and
the RELAXED disc said to ignore a profile (R7). Every expected number here is
worked out in this file from the fixture, never read back from the module.

What it does NOT check: what the solver does with the file. RPT-070 measured
the form it reads and RPT-137 what the discs delivered, each on one build.
Synthetic fixtures only: no research geometry, no measured loads.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):
# FR-347.

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import read_actuator_profile, workflow_registry
from pyflightstream.run import PlanStatus
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace.actuator_profiles import (
    DiscGeometry,
    RadialProfile,
    betz_prandtl_profile,
    read_section_loads,
    thrust_target,
    uniform_profile,
    write_profile,
)
from pyflightstream.workspace.cli import main as workspace_cli
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_g06_actuator_disc import RECIPES, _profile_workspace

REPO = Path(__file__).resolve().parents[2]

#: A synthetic disc: tip 0.5 m, hub 0.1 m, three blades.
TIP, HUB, BLADES = 0.5, 0.1, 3
DISC = ["--tip-radius", str(TIP), "--hub-radius", str(HUB), "--blades", str(BLADES)]
#: A synthetic sectional loads table of one step, in the post's column order
#: (the stations deliberately out of order, one of them pushing backwards).
TABLE = (
    "POL,STEP,time_s,FAMILY,PLANE,ROTOR,AZIMUTH,Offset,Chord,X_QC,Z_QC,Fx,Fz,Moment\n"
    "7,40,NA,Blade1,XY,NA,NA,0.3,0.1,0,0,-20.0,1.0,0\n"
    "7,40,NA,Blade1,XY,NA,NA,0.2,0.1,0,0,-10.0,1.0,0\n"
    "7,40,NA,Blade1,XY,NA,NA,0.45,0.1,0,0,-15.0,1.0,0\n"
    "7,40,NA,Blade1,XY,NA,NA,0.48,0.1,0,0,2.0,1.0,0\n"
)


def _trapezoid(rows: list[tuple[float, float]]) -> float:
    return sum((b[0] - a[0]) * (a[1] + b[1]) / 2.0 for a, b in zip(rows, rows[1:], strict=False))


def _rows(path: Path) -> list[tuple[float, float]]:
    """The file's rows, refusing a header, a blank line or a final newline."""
    data = path.read_bytes()
    assert not data.endswith(b"\n"), "a final newline is read as one point more (RPT-070)"
    assert b"\r" not in data, "the file is written through the LF route"
    rows = []
    for line in data.decode("ascii").split("\n"):
        r, f = line.split(",")
        rows.append((float(r), float(f)))
    return rows


def _post(root: Path, table: str = TABLE) -> Path:
    """A post folder holding one sectional loads table of POL 7, recorded in products.json."""
    sections = root / "post" / "m" / "sections"
    sections.mkdir(parents=True)
    path = sections / "P7-A_sloads_Blade1.csv"
    path.write_text(table, encoding="utf-8", newline="\n")
    record = {
        "products": {"sections/P7-A_sloads_Blade1.csv": {"sim_id": "7", "families": ["Blade1"]}}
    }
    (root / "post" / "m" / "products.json").write_text(json.dumps(record), encoding="utf-8")
    return path


def test_p0340_adprof_a_pol_s_written_sections_become_the_profile(tmp_path, capsys):
    """P0340-ADPROF, FR-347 R1 R3 R4 R5: the table of POL 7 found by --pol, -Fx at the
    stations, a zero from the axis to the hub and a zero at the tip, scaled to 100 N, the
    one negative station set to zero and counted, and the record naming the table."""
    # P0340-ADPROF FR-347
    root = tmp_path / "ws"
    table = _post(root)
    args = ["profile", "sections", "--pol", "7", *DISC, "--thrust", "100", "--out", "prop_uns"]
    assert workspace_cli([*args, "--workspace", str(root), "--apply"]) == 0
    out = capsys.readouterr().out
    target = root / "inputs" / "profiles" / "prop_uns.csv"
    rows = _rows(target)
    shape = [
        (0.0, 0.0),
        (HUB - 1e-4, 0.0),
        (0.2, 10.0),
        (0.3, 20.0),
        (0.45, 15.0),
        (0.48, 0.0),
        (TIP, 0.0),
    ]
    scale = 100.0 / (BLADES * _trapezoid(shape))
    assert [r for r, _ in rows] == [r for r, _ in shape]
    assert all(
        math.isclose(f, g * scale, rel_tol=1e-15, abs_tol=0.0)
        for (_, f), (_, g) in zip(rows, shape, strict=True)
    )
    assert math.isclose(BLADES * _trapezoid(rows), 100.0, rel_tol=1e-12)
    record = json.loads((target.parent / "prop_uns.provenance.json").read_text(encoding="utf-8"))
    assert record["schema"] == "pyfs-actuator-profile/1" and record["shape"] == "SECTIONS"
    assert record["parameters"]["negative_stations_set_to_zero"] == 1
    assert record["parameters"]["component"] == "-Fx" and record["parameters"]["steps"] == [40]
    assert record["inputs"] == [
        {"path": "post/m/sections/P7-A_sloads_Blade1.csv", "sha256": file_sha256(table)}
    ], "a table inside the workspace is recorded relative to it"
    assert record["output"] == {
        "file": "inputs/profiles/prop_uns.csv",
        "rows": 7,
        "sha256": file_sha256(target),
    }
    assert record["disc"] == {"tip_radius_m": TIP, "hub_radius_m": HUB, "blades": BLADES}
    assert record["units"] == {"r": "m", "F": "N/m per blade", "profile_units": "NEWTONS"}
    assert "a row names it PROFILE: prop_uns" in out


def test_p0340_adprof_a_table_of_several_steps_is_averaged_over_the_last_k(tmp_path):
    """P0340-ADPROF, FR-347 R1: a history table is refused without --last and averaged over
    its last K steps, station by station, with --last; steps that state different stations
    are refused."""
    # P0340-ADPROF FR-347
    head = TABLE.splitlines()[0]
    lines = [head]
    for step, scale in ((1, 9.0), (2, 1.0), (3, 3.0)):
        lines += [
            f"7,{step},NA,Blade1,XY,NA,NA,{r},0.1,0,0,{-scale * f},0,0"
            for r, f in ((0.2, 1.0), (0.4, 2.0))
        ]
    path = tmp_path / "P7_sloads_Blade1.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="holds 3 steps"):
        read_section_loads(path)
    with pytest.raises(WorkspaceError, match=r"--last\) is 4: .* holds 3 step"):
        read_section_loads(path, last=4)
    loads = read_section_loads(path, last=2)
    assert loads.steps == (2, 3)
    assert loads.stations == ((0.2, 2.0), (0.4, 4.0))
    moved = path.read_text(encoding="utf-8").replace(
        "7,3,NA,Blade1,XY,NA,NA,0.4", "7,3,NA,Blade1,XY,NA,NA,0.41"
    )
    path.write_text(moved, encoding="utf-8")
    with pytest.raises(WorkspaceError, match="same stations"):
        read_section_loads(path, last=2)
    twice = tmp_path / "twice.csv"
    row = "7,1,NA,Blade1,XY,NA,NA,0.2,0.1,0,0,-1,0,0"
    twice.write_text(f"{head}\n{row}\n{row}\n", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="two rows of one step state the same radius"):
        read_section_loads(twice)
    clocked = tmp_path / "clocked.csv"
    clocked.write_text(
        "POL,STEP,CLOCKING,Offset,Fx\n7,1,0,0.2,-1\n7,1,90,0.3,-1\n", encoding="utf-8"
    )
    with pytest.raises(WorkspaceError, match="holds 2 clockings"):
        read_section_loads(clocked)


def test_p0340_adprof_the_uniform_and_betz_prandtl_shapes(tmp_path):
    """P0340-ADPROF, FR-347 R2: UNI is F = c r from the hub to the tip with a zero inside the
    hub; BP is c r f_tip f_hub with Prandtl's factors and tan(phi) = J R / (pi r), zero at
    the hub and at the tip, each value worked out here from the formula."""
    # P0340-ADPROF FR-347
    disc = DiscGeometry(TIP, HUB, BLADES)
    uni = uniform_profile(disc, stations=5)
    assert uni.rows[:2] == ((0.0, 0.0), (HUB - 1e-4, 0.0)), "1e-4 m inside the hub, as measured"
    assert [r for r, _ in uni.rows[2:]] == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5])
    assert all(f == r for r, f in uni.rows[2:]), "a uniform jump loads a blade as r"

    j = 1.2
    bp = betz_prandtl_profile(disc, advance_ratio=j, stations=9)
    assert bp.rows[:3] == ((0.0, 0.0), (HUB - 1e-4, 0.0), (HUB, 0.0))
    assert bp.rows[-1] == (TIP, 0.0)
    for r, f in bp.rows[3:-1]:
        phi = math.atan(j * TIP / (math.pi * r))
        tip = 2 / math.pi * math.acos(math.exp(-BLADES * (TIP - r) / (2 * r * math.sin(phi))))
        hub = 2 / math.pi * math.acos(math.exp(-BLADES * (r - HUB) / (2 * HUB * math.sin(phi))))
        assert math.isclose(f, r * tip * hub, rel_tol=1e-12), (r, f)
    root = tmp_path / "ws"
    args = ["profile", "bp", "--advance-ratio", "1.2", "--stations", "9", *DISC]
    assert (
        workspace_cli(
            [*args, "--thrust", "50", "--out", "prop_bp", "--workspace", str(root), "--apply"]
        )
        == 0
    )
    rows = _rows(root / "inputs" / "profiles" / "prop_bp.csv")
    assert math.isclose(BLADES * _trapezoid(rows), 50.0, rel_tol=1e-12)


def test_p0340_adprof_the_target_is_a_thrust_or_a_ct_never_both(tmp_path, capsys):
    """P0340-ADPROF, FR-347 R3: a CT is worked out as T = CT rho n^2 D^4, D twice the tip
    radius; both, neither, or a CT without its density and speed are refused with exit 2."""
    # P0340-ADPROF FR-347
    root = tmp_path / "ws"
    base = ["profile", "uni", *DISC, "--out", "prop_uni", "--workspace", str(root)]
    ct, rho, rpm = 0.12, 1.1, 2400.0
    assert (
        workspace_cli([*base, "--ct", str(ct), "--rho", str(rho), "--rpm", str(rpm), "--apply"])
        == 0
    )
    expected = ct * rho * (rpm / 60.0) ** 2 * (2 * TIP) ** 4
    rows = _rows(root / "inputs" / "profiles" / "prop_uni.csv")
    assert math.isclose(BLADES * _trapezoid(rows), expected, rel_tol=1e-12)
    record = json.loads((root / "inputs" / "profiles" / "prop_uni.provenance.json").read_text())
    assert record["target"]["basis"] == "ct" and math.isclose(
        record["target"]["thrust_n"], expected
    )
    capsys.readouterr()
    for extra, words in (
        (["--thrust", "10", "--ct", "0.1", "--rho", "1", "--rpm", "100"], "not both"),
        ([], "not neither"),
        (["--ct", "0.1"], "rho_kg_m3 (CLI: --rho), the density"),
        (["--thrust", "10", "--rpm", "100"], "leave them out"),
    ):
        assert workspace_cli([*base, "--overwrite", *extra]) == 2
        assert words in capsys.readouterr().err


def test_p0340_adprof_the_integral_of_the_written_rows_is_stated(tmp_path):
    """P0340-ADPROF, FR-347 R4: the record states B * integral(F dr) of the rows the file
    holds, by the trapezoid rule, equal to the target, worked out here from the bytes; rows
    that miss the target by more than one part in 10^9 are refused and nothing is written."""
    # P0340-ADPROF FR-347
    # Areas of +-5e10 that cancel to 0.1: each scaled value rounds by one part in
    # 10^16 of 1e12 times the scale, so the written rows integrate about 5e-5 away.
    cancelling = RadialProfile(((0.1, 0.0), (0.2, 1e12), (0.3, -1e12 + 1.0), (0.4, 0.0)))
    missed = tmp_path / "missed"
    with pytest.raises(WorkspaceError, match=r"relative miss of .* above 1e-09"):
        write_profile(
            missed,
            "p",
            cancelling,
            disc=DiscGeometry(TIP, HUB, BLADES),
            target=thrust_target(tip_radius_m=TIP, thrust_n=10.0),
            shape="UNI",
            parameters={},
            inputs=[],
            apply=True,
        )
    assert not missed.exists(), "a refused profile wrote something"
    root = tmp_path / "ws"
    args = ["profile", "uni", *DISC, "--stations", "7", "--thrust", "77.5", "--out", "p"]
    assert workspace_cli([*args, "--workspace", str(root), "--apply"]) == 0
    folder = root / "inputs" / "profiles"
    record = json.loads((folder / "p.provenance.json").read_text(encoding="utf-8"))
    from_bytes = BLADES * _trapezoid(_rows(folder / "p.csv"))
    assert record["integral"]["rule"] == "trapezoid over the written rows"
    assert record["integral"]["blades_times_integral_n"] == from_bytes
    assert abs(from_bytes - 77.5) / 77.5 == record["integral"]["relative_miss"] < 1e-12
    shape = uniform_profile(DiscGeometry(TIP, HUB, BLADES), stations=7).rows
    assert record["scale"] == pytest.approx(77.5 / (BLADES * _trapezoid(list(shape))), rel=1e-15)


def test_p0340_adprof_the_plan_reads_the_written_profile(tmp_path, capsys):
    """P0340-ADPROF, FR-347 R5 R7: the file written under the stem a row's PROFILE names is
    the file the row binds and the text the run's copy holds, every point READY; the disc is
    read from the reference (--ref, --disc); a RELAXED disc is noted by the command and still
    warned about by the plan (FR-332), a RIGID one is neither."""
    # P0340-ADPROF FR-347
    for wake, noted in (("RIGID", False), ("RELAXED", True)):
        (tmp_path / wake).mkdir()
        workspace, matrix, given = _profile_workspace(
            tmp_path / wake, "ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct"
        )
        given.unlink()
        reference = workspace.inputs_dir / "references" / "r003.toml"
        reference.write_text(
            reference.read_text(encoding="utf-8") + f'wake_type = "{wake}"\n', encoding="utf-8"
        )
        args = ["profile", "uni", "--ref", "r003", "--disc", "PROP", "--thrust", "120"]
        assert (
            workspace_cli(
                [*args, "--out", "prop_ct", "--workspace", str(workspace.root), "--apply"]
            )
            == 0
        )
        assert ("RELAXED disc ignored a custom profile" in capsys.readouterr().out) is noted
        written = workspace.inputs_dir / "profiles" / "prop_ct.csv"
        assert read_actuator_profile(written) == written.read_text(encoding="utf-8")
        resolved = resolve_matrix(matrix, workspace, name="m", fs_version="26.120", recipes=RECIPES)
        assert [case.actuator_profile for case in resolved.campaign.sims] == [
            str(written.resolve())
        ]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            plan = plan_matrix(
                matrix,
                workspace,
                name="disc",
                default_fs_version="26.124",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                write_plan=False,
            )
        assert {entry.status for entry in plan.points} == {PlanStatus.READY}, [
            entry.error for entry in plan.points
        ]
        said = [
            w
            for w in caught
            if issubclass(w.category, PyflightstreamWarning) and "RPT-137" in str(w.message)
        ]
        assert len(said) == (1 if noted else 0), [str(w.message) for w in said]
        record = json.loads(
            (written.parent / "prop_ct.provenance.json").read_text(encoding="utf-8")
        )
        assert record["parameters"]["disc_source"] == {
            "reference": "r003",
            "disc": "PROP",
            "wake_type": wake,
        }
        assert record["inputs"] == [
            {"path": "inputs/references/r003.toml", "sha256": file_sha256(reference)}
        ]


def test_p0340_adprof_preview_overwrite_and_one_file_per_stem(tmp_path, capsys):
    """P0340-ADPROF, FR-347 R6: a preview writes nothing; a second write is refused without
    --overwrite; a stem the folder already holds in another file is refused."""
    # P0340-ADPROF FR-347
    root = tmp_path / "ws"
    args = ["profile", "uni", *DISC, "--thrust", "10", "--out", "p", "--workspace", str(root)]
    assert workspace_cli(args) == 0
    assert "nothing written" in capsys.readouterr().out
    assert not (root / "inputs" / "profiles").exists(), "a preview wrote something"
    assert workspace_cli([*args, "--apply"]) == 0
    capsys.readouterr()
    assert workspace_cli([*args, "--apply"]) == 2
    assert "nothing is overwritten" in capsys.readouterr().err
    assert workspace_cli([*args, "--apply", "--overwrite"]) == 0
    (root / "inputs" / "profiles" / "q.txt").write_text("0,0\n1,1", encoding="utf-8")
    capsys.readouterr()
    assert workspace_cli([*args[:-4], "--out", "q", "--workspace", str(root), "--apply"]) == 2
    assert "would name two files" in capsys.readouterr().err


def test_p0340_adprof_refusals_name_what_is_wrong(tmp_path, capsys):
    """P0340-ADPROF, FR-347 R1 R5 R6: a station outside the disc, a sign that reads no
    thrust, an option of another shape, --family beside a named table, a POL with no
    recorded table, a disc named half by a reference, a disc named by a reference AND
    stated, a reference disc whose profile_units are not NEWTONS, and no blade are refused,
    exit 2, and nothing is written."""
    # P0340-ADPROF FR-347
    root = tmp_path / "ws"
    table = _post(root)
    references = root / "inputs" / "references"
    references.mkdir(parents=True)
    (references / "r001.toml").write_text(
        'area_m2 = 1.0\nchord_m = 1.0\nspan_m = 1.0\n\n[PROP]\nkind = "actuator"\n'
        'frame = "MRP"\naxis = "X"\ntip_radius_m = 0.5\nhub_radius_m = 0.1\nblades = 3\n'
        'profile_units = "KILO-NEWTONS"\n',
        encoding="utf-8",
    )
    out = ["--out", "p", "--workspace", str(root), "--apply"]
    cases = (
        (
            [
                "profile",
                "sections",
                str(table),
                "--tip-radius",
                "0.45",
                "--hub-radius",
                "0.1",
                "--blades",
                "3",
                "--thrust",
                "1",
            ],
            "not inside the disc",
        ),
        (
            ["profile", "sections", str(table), *DISC, "--component", "Fz", "--thrust", "1"],
            "--component",
        ),
        (["profile", "uni", *DISC, "--pol", "7", "--thrust", "1"], "does not read --pol"),
        (
            ["profile", "sections", "--pol", "8", *DISC, "--thrust", "1"],
            "no sectional loads table of POL 8",
        ),
        (["profile", "uni", "--ref", "r001", "--thrust", "1"], "both --ref and --disc"),
        (
            ["profile", "sections", str(table), *DISC, "--family", "Blade9", "--thrust", "1"],
            "leave --family out",
        ),
        (
            ["profile", "uni", "--ref", "r001", "--disc", "PROP", "--tip-radius", "0.5"],
            "not both",
        ),
        (
            ["profile", "uni", "--ref", "r001", "--disc", "PROP", "--thrust", "1"],
            'profile_units = "NEWTONS"',
        ),
        (
            ["profile", "uni", *DISC[:4], "--blades", "0", "--thrust", "1"],
            "of at least one",
        ),
    )
    for args, words in cases:
        assert workspace_cli([*args, *out]) == 2, args
        assert words in capsys.readouterr().err, args
    assert not (root / "inputs" / "profiles").exists(), "a refusal wrote something"


def test_p0340_adprof_pol_finds_its_family_s_table_alone(tmp_path, capsys):
    """P0340-ADPROF, FR-347 R1: --pol finds the table of its family whether products.json
    states the families as a list or as one name, a family whose name begins another's
    (Blade1 and Blade12) is not taken for it, and a POL with two tables of the family is
    refused, naming both."""
    # P0340-ADPROF FR-347
    root = tmp_path / "ws"
    sections = root / "post" / "m" / "sections"
    sections.mkdir(parents=True)
    decoy = TABLE.replace(",Blade1,", ",Blade12,")
    (sections / "P7-A_sloads_Blade12.csv").write_text(decoy, encoding="utf-8")
    record = {
        "products": {"sections/P7-A_sloads_Blade12.csv": {"sim_id": "7", "families": "Blade12"}}
    }
    products = root / "post" / "m" / "products.json"
    products.write_text(json.dumps(record), encoding="utf-8")
    args = ["profile", "sections", "--pol", "7", *DISC, "--thrust", "1", "--out", "p"]
    run = [*args, "--workspace", str(root), "--apply"]
    assert workspace_cli([*run, "--family", "Blade1"]) == 2, "Blade12 was taken for Blade1"
    assert "no sectional loads table of POL 7 and family 'Blade1'" in capsys.readouterr().err
    assert workspace_cli([*run, "--family", "Blade12"]) == 0, "one name read as a family"
    capsys.readouterr()
    (sections / "P7-B_sloads_Blade12.csv").write_text(decoy, encoding="utf-8")
    record["products"]["sections/P7-B_sloads_Blade12.csv"] = {
        "sim_id": "7",
        "families": ["Blade12"],
    }
    products.write_text(json.dumps(record), encoding="utf-8")
    assert workspace_cli([*run, "--family", "Blade12", "--overwrite"]) == 2
    err = capsys.readouterr().err
    assert "POL 7 has 2 sectional loads tables of family 'Blade12'" in err
    assert "P7-A_sloads_Blade12.csv" in err and "P7-B_sloads_Blade12.csv" in err


def test_p0340_adprof_the_elliptical_disc_needs_no_file_and_the_pages_say_so(capsys):
    """P0340-ADPROF, FR-347 R7: the command's description and the page say the ELLIPTICAL
    disc is native and needs no file, that a RELAXED disc ignores a profile (RPT-137), and
    the page and the cheatsheet name the command."""
    # P0340-ADPROF FR-347
    with pytest.raises(SystemExit):
        workspace_cli(["profile", "--help"])
    words = " ".join(capsys.readouterr().out.split())
    assert "ELLIPTICAL disc is native in the solver and needs no file" in words
    assert "RELAXED disc ignores a custom profile (RPT-137)" in words
    page = " ".join((REPO / "docs" / "actuator-profiles.md").read_text(encoding="utf-8").split())
    for fact in (
        "ELLIPTICAL model is native in the solver and needs no file",
        "pyfs-workspace profile sections",
        "pyfs-workspace profile uni",
        "pyfs-workspace profile bp",
        "RPT-137",
        "RPT-070",
    ):
        assert fact in page, fact
    sheet = (
        REPO / "guide" / "latex-sources" / "04-cheatsheet" / "text" / "02-by-stage.tex"
    ).read_text(encoding="utf-8")
    assert "pyfs-workspace profile} sections" in sheet
