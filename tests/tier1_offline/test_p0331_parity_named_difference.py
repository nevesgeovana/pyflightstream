"""Tier 1: the parity checker names the section-plot drop of 0.33.1 only where FR-51 states it.

P0331-SECTIONS-ABSENT-FAMILY (FR-51): a script that lost its section Cp plot is a named
difference only when the release script cuts no section, the difference is a pure removal
of the plot's lines, and FR-51 is defined in the release SRS.

FR-321 with FR-51: a rotor row of 0.34.0 that also lost its section plot in 0.33.1 (the
tier-3 P1021 script) carries both differences at once, and one composite entry names the
pair only where each single entry would name its own part.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.workflow_payloads import before_plots_scene_0530, before_pressure_0460

REPO = Path(__file__).resolve().parents[2]
#: What the one ``git show`` below needs to start and find its config, and nothing else.
_GIT_ENV_KEYS = ("PATH", "SYSTEMROOT", "SystemRoot", "HOME", "USERPROFILE")

_PLOT = "SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\nrow_plot_cp_sections.txt\n"
_SECTION = "NEW_SURFACE_SECTION_DISTRIBUTION\n"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_parity_under_test", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _name(old: str, new: str, defined: set[str]) -> dict:
    return _load().name_difference("scripts", "row.txt", old, new, defined)


def _post_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _post_058_tables():
    # Independent example of the documented block, with twelve steps per turn.
    block = dict(POL="7", POINT_ID="1", POINT="P7-case", RUN_TYPE="unsteady_rotor")
    block.update(dict.fromkeys("ALPHA BETA MACH RE VINF VREF".split(), "0"))
    block.update(dict.fromkeys("RPM0 J0 MTIP0 MHEL0 J J_CLOCK RPM_CLOCK THRUST".split(), "NA"))
    block.update(dict.fromkeys("ALT RHO TEMP MU SREF CREF BREF XMOM YMOM ZMOM".split(), "0"))
    block.update(dict.fromkeys("D0 ADISC0 PITCH0 TOE0".split(), "0"))
    block.update(
        FIRST_STEP="1", LAST_STEP="6", STEPS="6", WINDOW_REVS="0.50000", WINDOW_PASSAGES="0.50000"
    )
    companion = _post_csv([{**block, "FAMILY": "Blade", "FAMILY_ID": "1"}])
    old = [
        {
            "POL": "7",
            "FIRST_STEP": str(first),
            "LAST_STEP": str(first + 1),
            "STEPS": "2",
            "REDUCTION": "phase_locked",
            "FX": str(first),
        }
        for first in (1, 3, 5)
    ]
    new = [
        {
            **{k: v for k, v in block.items() if k != "WINDOW_PASSAGES"},
            **row,
            "WINDOW_REVS": "0.166667",
            "ROTOR_ID": "NA",
        }
        for row in old
    ]
    return block, old, new, companion


def _post_058_logs(record):
    header = dict(
        version="<VERSION>", workspace="ws", matrix="m", time="<TIME>", check_frozen=False
    )
    remedy = f" Remedy: {record['remedy']}" if record["remedy"] else ""
    text = (
        "pyflightstream <VERSION> post\nworkspace=ws\nmatrix=m\ntime=<TIME>\n"
        "check_frozen=False (refuse instead of warn)\n"
        f"{record['severity'].upper()} point={record['point']} product={record['product']}: "
        f"{record['message']}{remedy}\n"
    )
    return {"m/post.log": text, "m/post.log.json": json.dumps({**header, "records": [record]})}


def test_p0580_post_parity_preserves_warning_records_across_the_path_move():
    """P0580-POST-LOG: FR-3789 permits paths, never a lost record or changed severity."""
    checker = _load()
    record = dict(
        point="P7-case",
        product="sections/P7-case_harmonics.csv",
        message="No sectional series",
        remedy=None,
        category="section-layout",
        severity="warning",
    )
    base = _post_058_logs(record)
    release = _post_058_logs({**record, "product": "reductions/P7-case_harmonics.csv"})

    def named(candidate, requirements=frozenset({"FR-3789"}), version="0.57.0"):
        result = checker.compare_texts("post", "file", base, candidate, requirements, version)
        return [row.get("requirement") for row in result["differing"]]

    assert named(release) == ["FR-3789", "FR-3789"]
    for key in record:
        wrong = _post_058_logs(
            {**record, "product": "reductions/P7-case_harmonics.csv", key: "wrong"}
        )
        assert named(wrong) == [None, None], key
    assert named({**release, "m/post.log": release["m/post.log"] + "lost data\n"}) == [None, None]
    assert named(release, requirements=frozenset()) == [None, None]
    assert named(release, version="0.58.0") == [None, None]


def test_p0580_post_parity_requires_inventory_evidence_for_an_empty_group_warning():
    """P0580-POST-LOG-GROUP: a recorded alias containing a real family cannot be skipped."""
    checker = _load()
    message = (
        "group 'g02' selects no family of the loads exports of simulation '7' (Blade): "
        "its selector 2 = Wing names no surface or alias there; its files are not written."
    )
    record = dict(
        point="polars/P7-g02",
        product="polars/P7-g02",
        message=message,
        remedy="restore the required data or correct the stated inputs and post again.",
        category="postprocessing",
        severity="warning",
    )
    release = _post_058_logs(record)
    manifest = dict(
        families=[dict(FAMILY="Blade", ROTOR_ID=0)], groups=[], skipped={"polars/P7-g02": message}
    )
    release["m/products.json"] = json.dumps(manifest)
    payload = json.loads(release["m/post.log.json"])
    base = {
        "m/post.log.json": json.dumps({**payload, "records": []}),
        "m/post.log": release["m/post.log"].split("WARNING")[0],
    }
    defined = {"FR-3789", "FR-3775", "FR-3780", "FR-3783"}

    def named(before, after):
        result = checker.compare_texts("post", "file", before, after, defined, "0.57.0")
        return [row.get("requirement") for row in result["differing"]]

    assert named(base, release) == ["FR-3789", "FR-3789"]
    wrong = {**release, "m/products.json": json.dumps({**manifest, "skipped": {}})}
    assert named(base, wrong) == [None, None]
    before = {
        **base,
        "m/provenance/p.prov.json": json.dumps(
            {"activity": {"run": {"pyfs:aliases": {"Wing": ["Blade"]}}}}
        ),
    }
    assert named(before, release)[:2] == [None, None]


def test_p0580_post_parity_preserves_manifest_provenance_and_closed_schema_keys():
    """P0580-POST-MANIFEST: FR-3779 adds schema metadata while retaining existing facts."""
    checker = _load()
    old = dict(
        products={"../../sims/point.vtk": {"kind": "instant", "source_sha256": "frozen"}},
        log="post.log",
        log_json="post.log.json",
        skipped={},
        provenance={"record": "unchanged"},
        complete=False,
    )
    new = {
        **old,
        "schema_version": 2,
        "tree": {
            "polars": {
                "holds": "polar files",
                "kinds": ["FAM-DIM", "FAM-ACOEF", "FAM-RCOEF", "DIM", "ACOEF", "RCOEF"],
            },
            "time_history": {"holds": "history", "kinds": ["plots"]},
            "reductions": {
                "holds": "reductions",
                "kinds": ["phase_locked", "per_revolution", "harmonics", "disc_map"],
            },
            "probes": {"holds": "probes", "kinds": ["probes", "probes_history"]},
        },
        "kinds": {},
        "run_block": [],
        "frames": {},
        "families": [],
        "groups": [],
        "polars": {},
        "migrated": {},
    }
    name = "m/products.json"

    def named(
        candidate,
        requirements=frozenset({"FR-3779", "FR-3777", "FR-3789", "FR-3787"}),
        version="0.57.0",
    ):
        result = checker.compare_texts(
            "post",
            "file",
            {name: json.dumps(old)},
            {name: json.dumps(candidate)},
            requirements,
            version,
        )
        return result["differing"][0].get("requirement")

    assert named(new) == "FR-3779"
    assert (
        named(
            {
                **new,
                "products": {
                    "../../sims/point.vtk": {"kind": "instant", "source_sha256": "changed"}
                },
            }
        )
        is None
    )
    column = dict(
        name="FX_MRP",
        unit="N",
        frame="MRP",
        quantity="force along x",
        definition="docs/definitions/airframe-coefficients.md#dim",
    )
    kinds = {"FAM-DIM": {"columns": [column]}}
    assert named({**new, "kinds": kinds}) == "FR-3779"
    assert named({**new, "kinds": {"FAM-DIM": {"columns": [{**column, "unit": "wrong"}]}}}) is None
    for key, value in (
        ("schema_version", 3),
        ("provenance", {}),
        ("complete", True),
        ("unknown", {}),
        ("log", "other.log"),
    ):
        assert named({**new, key: value}) is None, key
    wrong = {**new, "tree": {**new["tree"], "probes": {"holds": "wrong", "kinds": ["plots"]}}}
    assert named(wrong) is None
    assert named(new, requirements=frozenset()) is None
    assert named(new, version="0.58.0") is None


def test_p0580_post_parity_keeps_exact_cells_and_each_reduction_window():
    """P0580-POST-PARITY: FR-3778/3789 name only the defined row block and move."""
    checker = _load()
    _, old, new, companion = _post_058_tables()
    name = "m/probes/P7-case_phase_locked.csv"
    target = "m/reductions/P7-case_phase_locked.csv"
    release = {target: _post_csv(new), "m/polars/FAM-DIM-P7.csv": companion}
    defined = {"FR-3778", "FR-3789"}

    def named(candidate, requirements=defined, version="0.57.0"):
        result = checker.compare_texts(
            "post", "file", {name: _post_csv(old)}, candidate, requirements, version
        )
        return result["differing"][0].get("requirement")

    assert named(release) == "FR-3778"
    for field, value in (
        ("FX", "999"),
        ("FIRST_STEP", "2"),
        ("WINDOW_REVS", "0.50000"),
        ("POINT", "other"),
        ("RUN_TYPE", "steady"),
    ):
        wrong = [dict(row) for row in new]
        wrong[0][field] = value
        assert named({**release, target: _post_csv(wrong)}) is None, field
    assert (
        named({**release, target: _post_csv([{**row, "WINDOW_PASSAGES": "0.5"} for row in new])})
        is None
    )
    assert named({**release, target: _post_csv(new[:-1])}) is None
    assert named({target: _post_csv(new)}) is None
    assert named(release, defined - {"FR-3789"}) is None
    assert named(release, version="0.58.0") is None


def test_p0580_post_parity_requires_the_defined_aft_rotor_signs():
    """P0580-POST-ROTOR: FR-3777 preserves CP and reverses CT/CQ/ETA on an aft shaft."""
    checker = _load()
    block, _, _, companion = _post_058_tables()
    name = "m/polars/P7-Rotor_rotor.csv"
    target = "m/polars/P7-Rotor-RCOEF.csv"
    old = dict(
        POL="7",
        ROTOR="Rotor",
        CT_Rotor="-0.25",
        CQ_Rotor="-0.125",
        CP_Rotor="-0.5",
        ETA_Rotor="0.75",
    )
    row = {
        **block,
        "GROUP": "Rotor",
        "ROTOR_ID": "0",
        "CT": "0.25",
        "CQ": "0.125",
        "CP": "-0.5",
        "ETA": "-0.75",
    }
    release = {
        target: _post_csv([row]),
        **{f"m/polars/FAM-{kind}-P7.csv": companion for kind in ("DIM", "ACOEF", "RCOEF")},
        "m/post.log": "Rotor Rotor declares its axis aft; 0.58.0 counts thrust positive forward",
    }

    def named(candidate):
        result = checker.compare_texts(
            "post", "file", {name: _post_csv([old])}, candidate, {"FR-3777"}, "0.57.0"
        )
        return result["differing"][0].get("requirement")

    assert named(release) == "FR-3777"
    for key in ("CT", "CQ", "CP", "ETA", "PITCH0", "TOE0", "POL"):
        assert named({**release, target: _post_csv([{**row, key: "123"}])}) is None
    assert named({**release, target: _post_csv([{**row, "PITCH0": "wrong"}])}) is None
    assert named({**release, "m/post.log": "unrelated warning"}) is None


def test_p0580_post_parity_requires_the_retired_tables_replacement_loads():
    """P0580-POST-RETIREMENT: FR-3777 requires the same point and dimensional loads."""
    checker = _load()
    block, _, _, _ = _post_058_tables()
    old = {"POL": "7", "REDUCTION": "per_blade", "FAMILY": "Blade", "FX_MRP": "12.00000"}
    name = "m/probes/P7-case_per_blade.csv"
    replacement = "m/polars/FAM-DIM-P7.csv"
    rows = [{**block, "FAMILY": "Blade", "FAMILY_ID": "1", "FX_MRP": "12.00000"}]
    release = {
        replacement: _post_csv(rows),
        "m/polars/FAM-ACOEF-P7.csv": _post_csv([{**block, "FAMILY": "Blade", "CDW": "1"}]),
        "m/polars/FAM-RCOEF-P7.csv": _post_csv([{**block, "FAMILY": "Blade", "CT": "1"}]),
    }

    def named(candidate, requirements=frozenset({"FR-3777"}), version="0.57.0"):
        result = checker.compare_texts(
            "post", "file", {name: _post_csv([old])}, candidate, requirements, version
        )
        return result["differing"][0].get("requirement")

    assert named(release) == "FR-3777"
    for field, value in (("FX_MRP", "13.00000"), ("POINT", "other"), ("FAMILY", "Other")):
        assert named({**release, replacement: _post_csv([{**rows[0], field: value}])}) is None
    assert named({replacement: release[replacement]}) is None
    assert named(release, requirements=set()) is None
    assert named(release, version="0.58.0") is None


def test_p0551_gate_unavailable_b_rows_keep_every_other_cell():
    """P0551-GATE: FR-3601/3602 name targets, never changed measurements."""
    checker = _load()
    old = "POL,FAMILY,VARIANT,CL_T,CDI_T,STATUS\n1,net,B,NA,NA,CONVERGED\n"
    new = old.replace("net", "wing") + "1,TOTAL,B,NA,NA,CONVERGED\n"
    args = ("post", "matrix/farfield/point_trefftz_instant.csv")
    defined = {"FR-3601", "FR-3602", "FR-3604", "FR-3605"}
    assert "requirement" in checker.name_difference(*args, old, new, defined, "0.55.0")
    for wrong in (
        new.replace("NA", "1", 1),
        new.replace("CONVERGED", "BAD", 1),
        new.replace("TOTAL", "wing"),
        new.replace("POL,", "OTHER,"),
    ):
        assert "requirement" not in checker.name_difference(*args, old, wrong, defined, "0.55.0")
    assert "requirement" not in checker.name_difference(*args, old, new, defined, "0.55.1")


def test_p0551_gate_warning_allowance_keeps_record_fields():
    """P0551-GATE: FR-3613 permits its warning, not a changed severity or other record."""
    checker = _load()
    message = (
        "product=farfield: T_NEAR_N, Q_NEAR_NM, DT_WAKE_COUNTS and DQ_WAKE_COUNTS compare "
        "one rotor with one rotor. The near field includes friction and W does not: Cx = CDi + CDo."
    )
    record = dict(
        point="campaign",
        product="stage",
        message=message,
        remedy=None,
        category="postprocessing",
        severity="warning",
    )
    old = json.dumps(dict(records=[], matrix="m"))
    new = json.dumps(dict(records=[record], matrix="m"))
    args = ("post", "matrix/post.log.json")
    defined = {"FR-3602", "FR-3601", "FR-3605", "FR-3613", "FR-3625"}
    assert "requirement" in checker.name_difference(*args, old, new, defined, "0.55.0")
    for field in record:
        wrong = json.dumps(dict(records=[{**record, field: "wrong"}], matrix="m"))
        assert "requirement" not in checker.name_difference(*args, old, wrong, defined, "0.55.0")
    for wrong in (
        new.replace('"matrix": "m"', '"matrix": "other"'),
        json.dumps(dict(records=[{**record, "extra": 1}], matrix="m")),
    ):
        assert "requirement" not in checker.name_difference(*args, old, wrong, defined, "0.55.0")
    assert "requirement" not in checker.name_difference(
        *args, old, new, defined - {"FR-3613"}, "0.55.0"
    )


def test_p0551_gate_frame_allowance_keeps_every_provenance_field():
    """P0551-GATE: FR-3606 names equivalent origins only, with all metadata preserved."""
    checker = _load()
    frame = dict(
        frame="moment_point",
        translation_m=[0.0, 0.0, 0.0],
        moment_point_distance_m=None,
        geometry_distance_m=None,
        distance_statistic="maximum_nearest_vertex",
        moment_point_max_distance_m=None,
        geometry_max_distance_m=None,
        tolerance_m=1e-7,
        ambiguous=False,
        rotation="untested; translation candidates only",
        evidence_source="equivalent_origins",
    )
    key = "farfield/p_trefftz_instant.csv"

    def document(evidence):
        product = {"kind": "instant"}
        if evidence is not None:
            product["wake_frames"] = {"p": {"datapoints/dp/p_wakes.vtk": evidence}}
        return json.dumps({"products": {key: product}, "skipped": {}})

    old, new = document(None), document(frame)
    args = ("post", "matrix/products.json")
    defined = {"FR-3606", "FR-3602", "FR-3605", "FR-3625"}
    assert "requirement" in checker.name_difference(*args, old, new, defined, "0.55.0")
    for field in frame:
        assert "requirement" not in checker.name_difference(
            *args, old, document({**frame, field: "wrong"}), defined, "0.55.0"
        )
    for wrong in (
        new.replace('"instant"', '"average"'),
        document({**frame, "extra": 1}),
        new.replace("datapoints/dp/p_wakes.vtk", "unrelated.vtk"),
    ):
        assert "requirement" not in checker.name_difference(*args, old, wrong, defined, "0.55.0")


@pytest.mark.parametrize("name", ["post.log", "post.log.json", "products.json"])
def test_p0551_gate_rotor_warning_identity_matches_its_key(name):
    """P0551-R3: a warning about another rotor is not the documented diagnostic."""
    checker = _load()
    key = "point#rotor=ROTOR#entry=wake"
    message = "ROTOR: unavailable blade contributions: Blade1"
    remedy = "restore the required data or correct the stated inputs and post again."

    def document(body):
        if name == "products.json":
            return json.dumps({"products": {}, "skipped": {} if body is None else {key: body}})
        if name == "post.log.json":
            record = dict(
                point=key,
                product=key,
                message=body,
                remedy=remedy,
                category="postprocessing",
                severity="warning",
            )
            return json.dumps({"records": [] if body is None else [record]})
        return (
            "" if body is None else f"WARNING point={key} product={key}: {body} Remedy: {remedy}\n"
        )

    old = document(None)
    # Keep the text file's final-newline state identical in the empty baseline.
    if name == "post.log":
        old = "INFO retained\n"
        good = old + document(message)
        bad = old + document(message.replace("ROTOR:", "OTHER:"))
    else:
        good = document(message)
        bad = document(message.replace("ROTOR:", "OTHER:"))
    defined = {"FR-3601", "FR-3602", "FR-3605", "FR-3606", "FR-3613", "FR-3625"}
    args = ("post", f"matrix/{name}")
    assert "requirement" in checker.name_difference(*args, old, good, defined, "0.55.0")
    assert "requirement" not in checker.name_difference(*args, old, bad, defined, "0.55.0")


def test_p0551_ffname2_parity_preserves_non_farfield_cells():
    """P0551-FFNAME2: naming the rename cannot excuse other coefficients changing."""
    checker = _load()
    old = "POL,CL,CDI_T_B_wake\n1,0.5,0.02\n"
    new = "POL,CL,CDI_FF_B_TOTAL,CDI_FF_B_W\n1,0.5,0.02,0.01\n"
    args = ("post", "matrix/polars/SUPER-test.csv")
    assert (
        checker.name_difference(*args, old, new, {"FR-1062"}, "0.55.0")["requirement"] == "FR-1062"
    )
    for wrong in (
        new.replace("0.5", "0.6"),
        new.replace("0.02", "0.03"),
        new.replace("CDI_FF_B_W", "UNRELATED"),
    ):
        assert "requirement" not in checker.name_difference(
            *args, old, wrong, {"FR-1062"}, "0.55.0"
        )
    assert "requirement" not in checker.name_difference(*args, old, new, {"FR-1062"}, "0.55.1")


def test_section_plot_drop_is_named_fr_51_only_where_the_release_cuts_no_section() -> None:
    """P0331-SECTIONS-ABSENT-FAMILY, FR-51: named only in its stated direction and state."""
    module = _load()
    assert any(n["requirement"] == "FR-51" for n in module.NAMED_DIFFERENCES)
    base = "OPEN\nSOLVE\n" + _PLOT + "\nCLOSE\n"
    dropped = "OPEN\nSOLVE\nCLOSE\n"
    defined = {"FR-51"}

    named = _name(base, dropped, defined)
    assert named.get("requirement") == "FR-51"

    # The release script still cuts a section: not the state FR-51 names.
    still_cuts = "OPEN\n" + _SECTION + "SOLVE\nCLOSE\n"
    kept = _name("OPEN\n" + _SECTION + "SOLVE\n" + _PLOT + "\nCLOSE\n", still_cuts, defined)
    assert "requirement" not in kept

    # A plot ADDED is the opposite direction.
    assert "requirement" not in _name(dropped, base, defined)

    # A drop together with another changed line is not wholly the named difference.
    assert "requirement" not in _name(base, "OPEN\nSOLVE\nEXTRA\nCLOSE\n", defined)

    # FR-51 absent from the release SRS: the drop stays unnamed, with the reason.
    unnamed = _name(base, dropped, set())
    assert "requirement" not in unnamed
    assert "FR-51" in unnamed["unnamed_because"]


# --- FR-321 with FR-51: the 4R termination line and the section-plot drop in one script ---

_P1021 = "P1021-M100RE230AL+000"
_P1021_GOLDEN = REPO / "tests" / "tier3_licensed" / "goldens" / "matriz" / f"{_P1021}.txt"
_TERMINATION = "SET_WAKE_TERMINATION_TIME_STEPS 35\n"
_P1021_PLOT = f"SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n{_P1021}_plot_cp_sections.txt\n\n"
_EXPORT_LOG = "\nEXPORT_LOG\n"
_BOTH = {"FR-321", "FR-51"}


def _p1021_pair() -> tuple[str, str]:
    """The tier-3 P1021 script as 0.33.0 rendered it and as the release renders it.

    The release side is the committed golden; the 0.33.0 side is that golden less the
    termination line and with the section plot back before EXPORT_LOG, which is the
    v0.33.0 golden byte for byte (asserted wherever the tag is in the clone).
    """
    golden = _P1021_GOLDEN.read_text(encoding="utf-8").rstrip("\n")
    # 0.53.0 (FR-3442): the golden carries the plots-scene line before START_SOLVER; the
    # pressure digests were pinned on the bytes without it.
    release = before_pressure_0460(before_plots_scene_0530(golden)) + "\n"
    # P0451-CIFIX: PFS-2168 restores the v0.33.0 basis, so no axis undo is
    # needed. Remove only the added BMRP and undo the resulting frame IDs.
    body_frame = (
        "CREATE_NEW_COORDINATE_SYSTEM\nEDIT_COORDINATE_SYSTEM\n"
        "FRAME 3\nNAME PUSHER_BMRP\n"
        "ORIGIN_X 4.5\nORIGIN_Y 0.0\nORIGIN_Z 0.0\n"
        "VECTOR_X_X 1.0\nVECTOR_X_Y 0.0\nVECTOR_X_Z 0.0\n"
        "VECTOR_Y_X 0.0\nVECTOR_Y_Y 1.0\nVECTOR_Y_Z 0.0\n"
        "VECTOR_Z_X 0.0\nVECTOR_Z_Y 0.0\nVECTOR_Z_Z 1.0\n\n"
    )
    assert release.count(body_frame) == 1
    release = release.replace(body_frame, "", 1)
    for before, after, count in (
        ("FRAME 4", "FRAME 3", 191),
        ("FRAME 5", "FRAME 4", 1),
        ("FRAME 6", "FRAME 5", 12),
        ("ROTATION_FRAME 4", "ROTATION_FRAME 3", 1),
        ("5,6", "4,5", 1),
        ("SET_MOTION_COORDINATE_SYSTEM 1 4", "SET_MOTION_COORDINATE_SYSTEM 1 3", 1),
    ):
        assert release.splitlines().count(before) == count
        release = release.replace("\n" + before + "\n", "\n" + after + "\n")
    assert release.count(_TERMINATION) == 1 and "SECTIONS_CP" not in release
    base = release.replace(_TERMINATION, "", 1).replace(
        _EXPORT_LOG, "\n" + _P1021_PLOT + "EXPORT_LOG\n", 1
    )
    shown = subprocess.run(
        ["git", "show", f"v0.33.0:tests/tier3_licensed/goldens/matriz/{_P1021}.txt"],
        cwd=REPO,
        capture_output=True,
        check=False,
        env={key: os.environ[key] for key in _GIT_ENV_KEYS if key in os.environ},
    )
    if shown.returncode == 0:
        assert base == shown.stdout.decode("utf-8").replace("\r\n", "\n")
    return base, release


def _entry(module, requirement: str, marker: str) -> dict:
    """The one entry of ``requirement`` whose ``lines`` pattern holds ``marker``."""
    (entry,) = [
        n
        for n in module.NAMED_DIFFERENCES
        if n["requirement"] == requirement and marker in n.get("lines", "")
    ]
    return entry


def _both_sides(text: str, anchor: str, inserted: str) -> str:
    """``text`` with ``inserted`` placed before the first ``anchor``."""
    assert anchor in text, anchor
    return text.replace(anchor, inserted + anchor, 1)


def test_p1021_both_parts_are_named_fr_321_by_the_composite() -> None:
    """FR-321 with FR-51: the real P1021 pair is named, by the composite entry."""
    module = _load()
    composite = _entry(module, "FR-321", "SECTIONS_CP")
    termination = _entry(module, "FR-321", r"SET_WAKE_TERMINATION_TIME_STEPS \d+$")
    plot = _entry(module, "FR-51", "SECTIONS_CP")
    # The composite's conditions are its single entries' own, not looser ones.
    assert composite["release_has"] == termination["release_has"]
    assert composite["base_lacks"] == termination["base_lacks"]
    assert composite["release_lacks"] == plot["release_lacks"]

    base, release = _p1021_pair()
    assert module.changed_lines(base, release) == [
        _TERMINATION.rstrip("\n"),
        "SET_PLOT_TYPE SECTIONS_CP",
        "SAVE_PLOT_TO_FILE",
        f"{_P1021}_plot_cp_sections.txt",
        "",
    ]
    named = _name(base, release, _BOTH)
    assert named.get("requirement") == "FR-321", named
    assert named["why"] == composite["why"]
    # FR-321 absent from the release SRS: unnamed, with the reason.
    unnamed = _name(base, release, {"FR-51"})
    assert "requirement" not in unnamed
    assert "FR-321" in unnamed["unnamed_because"]
    # FR-51 absent: the section part has no requirement, so the pair is unnamed too.
    assert composite["also_requires"] == "FR-51"
    unnamed = _name(base, release, {"FR-321"})
    assert "requirement" not in unnamed, unnamed
    assert "FR-51" in unnamed["unnamed_because"]


def test_p1021_the_composite_refuses_every_other_state() -> None:
    """Each condition refuses alone; either part alone goes to its own single entry."""
    module = _load()
    base, release = _p1021_pair()
    real = module.changed_lines(base, release)

    def refused(old: str, new: str, *, same_lines: bool) -> None:
        if same_lines:
            # The changed lines are the real pair's: only the condition under test refuses.
            assert module.changed_lines(old, new) == real
        assert "requirement" not in _name(old, new, _BOTH)

    # (a) the release still plots a section Cp, or still cuts a section, on lines both
    # sides carry: release_lacks alone refuses.
    for inserted in ("SET_PLOT_TYPE SECTIONS_CP\n", "NEW_SURFACE_SECTION_DISTRIBUTION\n"):
        refused(
            _both_sides(base, "SET_PLOT_TYPE RESIDUALS\n", inserted),
            _both_sides(release, "SET_PLOT_TYPE RESIDUALS\n", inserted),
            same_lines=True,
        )

    # (b) a second termination line, or any other changed line.
    refused(base, _both_sides(release, _TERMINATION, _TERMINATION), same_lines=False)
    other = release.replace("SOLVER_SET_ITERATIONS 300\n", "SOLVER_SET_ITERATIONS 301\n", 1)
    assert other != release
    refused(base, other, same_lines=False)

    # (c) a steady script, and a script that turns no rotor: release_has alone refuses.
    for was, now in (
        ("SET_SOLVER_UNSTEADY\n", "SET_SOLVER_STEADY\n"),
        ("CREATE_NEW_MOTION ROTARY\n", "CREATE_NEW_MOTION TRANSLATE\n"),
    ):
        assert was in release
        refused(base.replace(was, now, 1), release.replace(was, now, 1), same_lines=True)

    # (d) the base already wrote a termination line, kept by the release: base_lacks alone.
    stated = "SET_WAKE_TERMINATION_TIME_STEPS 9\n"
    refused(
        _both_sides(base, "SET_WAKE_ON_WAKE_INDUCTION", stated),
        _both_sides(release, "SET_WAKE_ON_WAKE_INDUCTION", stated),
        same_lines=True,
    )

    # (e) one part alone goes to its single entry, not to the composite.
    termination = _entry(module, "FR-321", r"SET_WAKE_TERMINATION_TIME_STEPS \d+$")
    plot = _entry(module, "FR-51", "SECTIONS_CP")
    plotted = release.replace(_EXPORT_LOG, "\n" + _P1021_PLOT + "EXPORT_LOG\n", 1)
    only_termination = _name(base, plotted, _BOTH)
    assert only_termination.get("requirement") == "FR-321", only_termination
    assert only_termination["why"] == termination["why"]
    only_plot = _name(plotted, release, _BOTH)
    assert only_plot.get("requirement") == "FR-51", only_plot
    assert only_plot["why"] == plot["why"]
    # The plot part alone is never FR-321's, even when FR-51 is not defined: on a base
    # that wrote no termination line and a release that writes none, so only the
    # composite's block (not base_lacks) can refuse it.
    assert "requirement" not in _name(plotted, release, {"FR-321"})
    unterminated = release.replace(_TERMINATION, "", 1)
    assert module.changed_lines(base, unterminated) == real[1:]
    assert _name(base, unterminated, _BOTH).get("requirement") == "FR-51"
    assert "requirement" not in _name(base, unterminated, {"FR-321"})
