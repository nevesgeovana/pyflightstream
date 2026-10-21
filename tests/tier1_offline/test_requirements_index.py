"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
RADICALS = "INST DEXP SPCM PHYS PROC EXEC RECS DRED TRST WKSP OPER".split()
WORKSPACE_STATEMENT = (
    "The system shall keep the governing state of an experiment, the protocol, the configuration "
    "and the records, in plain-text files that a version control system can compare and merge."
)
# The method table of 0.43.0: UID | Level | Statement | Rationale | Analogy | Verification | Source.
METHOD_COLUMNS = 7


def historical_requirements():
    """Read the frozen migration population through the shared table parser."""
    from scripts._requirements_paths import requirement_rows

    historical = []
    for name in ("functional-requirements", "nonfunctional-requirements"):
        text = subprocess.check_output(
            [
                "git",
                "-C",
                str(REPO),
                "show",
                f"6bad1dac664ef7b0959e683749f4b1f437af6033:docs/unpublished/requirements/{name}.md",
            ],
            encoding="utf-8",
            env=os.environ.copy(),
        )
        historical.extend(requirement_rows(text))
    return historical


@pytest.mark.parametrize(
    "defect", ["unallocated", "out-of-range", "retired", "lane", "node", "missing-lineage"]
)
def test_p0420_srs_application_allocations_refuse_invalid_lineage(tmp_path, monkeypatch, defect):
    """P0420: an allocation is bounded provenance, not an unexplained UID exemption."""
    from scripts._requirements_paths import L3_REQUIREMENTS, ROADMAP, requirement_files

    historical = historical_requirements()
    for source in (*requirement_files(REPO), REPO / L3_REQUIREMENTS, REPO / ROADMAP):
        target = tmp_path / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    identities = json.loads((REPO / "docs/srs/reserved-ids.json").read_text())
    migration = (REPO / "docs/srs/uid-migration.csv").read_text()
    uid = "FR-3206"  # an allocation still live in the SRS after the 0.43.0 trim
    if defect == "unallocated":
        del identities["allocations"][uid]
    elif defect == "out-of-range":
        identities["allocations"]["FR-3300"] = identities["allocations"][uid]
    elif defect == "retired":
        identities["reserved_ids"].append(uid)
    elif defect == "lane":
        identities["allocations"][uid]["lane"] = "unassigned"
    elif defect == "node":
        identities["allocations"][uid]["node"] = ""
    else:
        migration = "\n".join(
            line for line in migration.splitlines() if not line.startswith(uid + ",")
        )
    folder = tmp_path / "docs/srs"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "reserved-ids.json").write_text(json.dumps(identities), encoding="utf-8")
    (folder / "uid-migration.csv").write_text(migration, encoding="utf-8")
    monkeypatch.setitem(globals(), "REPO", tmp_path)
    monkeypatch.setitem(globals(), "historical_requirements", lambda: historical)
    with pytest.raises(AssertionError):
        test_p0420_stage_migration_preserves_historical_statements()


def test_p0420_stage_migration_preserves_historical_statements():
    """P0420: historical identities resolve through explicit content-phase lineage."""
    import csv

    from scripts._requirements_paths import read_l3, read_requirements, roadmap_uids

    migration_path = REPO / "docs/srs/uid-migration.csv"
    assert migration_path.exists(), "historical UID migration is missing"
    records = list(csv.DictReader(migration_path.open(encoding="utf-8")))
    migration = {r["uid"]: r for r in records}
    assert len(migration) == len(records), "duplicate migration UID"
    current = {r["uid"]: r for r in read_requirements(REPO)}
    # 0.43.0 trim: L3 detail rows keep their identity in the L3 file beside the tests, and
    # parked rows keep theirs on the roadmap page, which makes no claim.
    detail = {r["uid"]: r for r in read_l3(REPO)}
    roadmap = roadmap_uids(REPO)
    assert not set(detail) & set(current) and not roadmap & (set(current) | set(detail))
    current.update(detail)
    historical = historical_requirements()
    live = [r for r in historical if r["status"] != "retired"]
    historical_ids = {r["uid"] for r in live}
    assert historical_ids <= set(migration)
    identities = json.loads((REPO / "docs/srs/reserved-ids.json").read_text())
    allocations = identities.get("allocations", {})
    for uid, allocation in allocations.items():
        family, number = uid.split("-")
        lower, upper = identities["allocation_ranges"]["srs-application"][family]
        assert lower <= int(number) <= upper, uid
        assert (uid in current or uid in roadmap) and uid in migration, uid
        assert uid not in historical_ids and uid not in identities["reserved_ids"], uid
        # srs-fix: the 0.43.0 instantiation-review follow-up lane (FR-3241, R-INST-35).
        assert allocation["lane"] in {"srs-apply-1", "srs-apply-2", "srs-fix"}, uid
        assert all(
            re.fullmatch(r"(?:PFS-\d+(?:\.\d+)*|GOAL-033:G52)", node)
            for node in allocation["node"].split("; ")
        ), uid
        destination = migration[uid]["destination"]
        if destination == "kept":
            assert uid not in detail and not migration[uid]["target"], uid
        elif destination == "l3":
            assert uid in detail and detail[uid]["parent"] == migration[uid]["target"], uid
        else:
            assert destination == "roadmap" and uid in roadmap, uid
    split_ids = {uid for r in records for uid in r["new_uids"].split()}
    for uid in set(migration) - historical_ids:
        assert (
            uid in allocations
            or uid in split_ids
            or (uid in current and migration[uid]["new_uids"])
            or (migration[uid]["destination"] == "merged" and migration[uid]["target"] in current)
        ), "unexplained migration UID"
    lettered = [r["uid"] for r in live if r["uid"][-1].isalpha()]
    expected = dict(
        zip(
            lettered,
            [f"FR-{n}" for n in range(1204, 1225)] + [f"NFR-{n}" for n in range(50, 54)],
            strict=True,
        )
    )
    reserved = json.loads((REPO / "docs/srs/reserved-ids.json").read_text())["reserved_ids"]
    assert len(reserved) == len(set(reserved))
    assert set(reserved) == set(lettered) | {
        r["uid"] for r in historical if r["status"] == "retired"
    } | {
        r["uid"]
        for r in records
        if r["destination"] in {"merged", "demoted", "rationale", "retired"}
    }
    for old in historical:
        uid = old["uid"]
        target = expected.get(uid, uid)
        if old["status"] == "retired":
            assert current[uid]["statement"] == old["statement"], uid
            assert current[uid]["status"] == "retired", uid
            continue
        assert (REPO / migration[uid]["file"]).exists()
        disposition = migration[uid]
        assert disposition["destination"] in {
            "kept",
            "merged",
            "demoted",
            "rationale",
            "retired",
            "l3",
            "roadmap",
        }
        for child in disposition["new_uids"].split():
            assert child in current or child in reserved or child in roadmap, (uid, child)
        if disposition["destination"] == "kept":
            assert uid in current and uid not in detail, uid
            assert current[uid]["status"] != "retired", uid
        elif disposition["destination"] == "l3":
            assert uid in detail and detail[uid]["parent"] == disposition["target"], uid
        elif disposition["destination"] == "roadmap":
            assert uid in roadmap and uid not in reserved, uid
        else:
            assert uid in reserved, uid
            if disposition["destination"] != "retired":
                assert disposition["target"], uid
                if disposition["file"].endswith("architecture-srs.md"):
                    assert uid in (REPO / disposition["file"]).read_text("utf-8"), uid
                else:
                    assert disposition["target"] in current, uid
        if uid in expected:
            assert migration[uid]["target"] == target
            assert target in migration[uid]["new_uids"].split()
            if target in roadmap or target in detail:
                continue  # placement of L3 rows is checked by scripts/srs_levels.py
            row = current[target]
            base = uid[:-1]
            promoted = base in current and current[base]["level"] == row["level"]
            if promoted:
                continue  # the 0.43.0 trim made the former child a sibling (ledger row)
            if base in current and current[base]["status"] != "retired":
                assert row["parent"] == base
                assert row["hid"].startswith(current[base]["hid"] + ".")
            else:
                host = migration.get(base, {}).get("target")
                if host and host != target:
                    assert row["parent"] == host
                else:
                    assert current[row["parent"]]["level"] == "L1"
    for name in ("functional-requirements.md", "nonfunctional-requirements.md"):
        assert not (REPO / "docs/unpublished/requirements" / name).exists()


def validate_structure(rows, reserved, historical, migration):
    """P0420 structural guard shared with planted controls."""
    live = [r for r in rows if r["status"] != "retired"]
    ids = {r["uid"] for r in live}
    assert len(migration) == len(set(migration)), "duplicate migration UID"
    assert not ids & set(reserved), "reserved UID live"
    assert set(historical) <= set(migration), "historical UID missing"
    generator = _generator()
    projected = []
    for row in live:
        assert re.fullmatch(r"N?FR-\d+", row["uid"]), "numeric UID"
        assert row.get("level") in {"L1", "L2", "L3"}, "Level"
        assert row.get("verification_method") in {
            "test",
            "analysis",
            "inspection",
            "demonstration",
        }, "Verification method"
        assert row["hid"].split("-")[0] in {
            *RADICALS,
            *"QFSU QPEFF QCOMP QUSA QREL QSEC QMNT QFLX QSAF".split(),
        }, "HID radical"
        projected.append(
            {
                "id": row["uid"],
                "parent": "" if row["parent"] == "-" else row["parent"],
                "area": row["hid"].split("-")[0],
                "status": row["status"],
                "hid": "",
            }
        )
    generator._hierarchy(projected)
    for row, generated in zip(live, projected, strict=True):
        assert row["hid"] == generated["hid"], "generated HID"
        assert row["level"] == f"L{row['hid'].count('.') + 1}", "tree Level"


def test_p0420_structure_guard():
    import csv

    from scripts._requirements_paths import read_requirements

    reserved = REPO / "docs/srs/reserved-ids.json"
    assert reserved.exists(), "reserved UID list is missing"
    migration = list(csv.DictReader((REPO / "docs/srs/uid-migration.csv").open(encoding="utf-8")))
    validate_structure(
        read_requirements(REPO),
        json.loads(reserved.read_text())["reserved_ids"],
        [r["uid"] for r in historical_requirements() if r["status"] != "retired"],
        [r["uid"] for r in migration],
    )


def test_p0420_s3_architecture_dispositions_preserve_rules():
    """P0420: architecture destinations retain historical content and anchors."""
    import csv

    from scripts._requirements_paths import read_requirements

    historical = {r["uid"]: r for r in historical_requirements()}
    current = {r["uid"]: r for r in read_requirements(REPO)}
    architecture = (REPO / "docs/srs/architecture-srs.md").read_text("utf-8")
    migration = {
        r["uid"]: r
        for r in csv.DictReader((REPO / "docs/srs/uid-migration.csv").open(encoding="utf-8"))
    }
    reserved = json.loads((REPO / "docs/srs/reserved-ids.json").read_text())["reserved_ids"]
    for uid in ("FR-928", "FR-991", "FR-1073", "FR-744", "FR-1002", "FR-1189", "FR-1155"):
        assert uid not in current, uid
        assert uid in reserved
        assert migration[uid]["destination"] == "demoted"
        assert migration[uid]["file"] == "docs/srs/architecture-srs.md"
        assert migration[uid]["target"].startswith("architecture-srs#")
        assert historical[uid]["statement"] in architecture
        assert historical[uid]["code"] in architecture
        assert historical[uid]["test"] in architecture
    assert "FR-2269" not in current and "FR-2269" in reserved
    assert "FR-2269" in architecture
    # FR-965 stays a live identity; the 0.43.0 trim moved the detail to the L3 file.
    from scripts._requirements_paths import read_l3

    assert "FR-965" in {r["uid"] for r in read_l3(REPO)} and "FR-965" not in reserved
    assert migration["FR-965"]["destination"] == "l3"


def test_p0420_l1_rows_follow_the_approved_feature_statements():
    import hashlib

    from scripts._requirements_paths import read_requirements

    rows = read_requirements(REPO, live_only=True)
    by_id = {r["uid"]: r for r in rows}
    features = sorted(
        (r for r in rows if r.get("level") == "L1"), key=lambda r: int(r["uid"].split("-")[1])
    )
    # 0.43.0 trim (instantiation-ledger-0.43.0.csv): 45 L1 merged into named survivors;
    # FR-3082, FR-3093, FR-3138 and FR-3149 parked on the roadmap; FR-3152 parked and
    # restored by the instantiation review (R-INST-32) because its behaviour exists;
    # FR-3021, FR-3023 to FR-3026 merged into the refinement features (R-INST-34).
    left = {3004, 3010, 3011, 3017, 3033, 3034, 3035, 3036, 3037, 3040, 3041, 3042, 3043, 3047}
    left |= {3021, 3023, 3024, 3025, 3026}
    left |= {3056, 3081, 3082, 3090, 3093, 3098, 3100, 3101, 3103, 3104, 3105, 3106, 3107}
    left |= {3110, 3111, 3117, 3121, 3122, 3124, 3126, 3127, 3128, 3130, 3132, 3134, 3138}
    left |= {3140, 3147, 3149, 3151, 3156, 3159, 3162, 3163, 3166}
    # FR-3241 (derived equation products and trimmed polars) split from FR-3094 (R-INST-35).
    expected = [f"FR-{n}" for n in range(3000, 3167) if n not in left] + ["FR-3241"]
    assert [r["uid"] for r in features] == expected
    # Trimmed L1 statements, numeric UID order, UTF-8 joined by LF (no trailing LF); nine
    # rewordings of the 0.43.0 instantiation review (R-INST-17, R-INST-18), the
    # restored FR-3152 (R-INST-32), the two widened refinement features (R-INST-34)
    # and FR-3241 (R-INST-35).
    assert hashlib.sha256("\n".join(r["statement"] for r in features).encode()).hexdigest() == (
        "2739695a606e486095b74cbe1583b60eca658c570ddbf9b28b75a07b3a7347b0"
    )
    for feature in features:
        members = [
            r
            for r in rows
            if r["parent"] == feature["uid"]
            or by_id.get(r["parent"], {}).get("parent") == feature["uid"]
        ]
        assert feature["status"] == (
            "implemented"
            if members and all(r["status"] == "implemented" for r in members)
            else "pending"
        )
        assert feature["verification_method"] == "analysis"
        assert feature["code"] == feature["test"] == feature["parent"] == "-"


@pytest.mark.parametrize("status", ["pending", "implemented"], ids=lambda s: "P0420-empty-" + s)
def test_p0420_s3_empty_feature_is_pending(status):
    generator = _generator()
    rows = [
        {
            "id": "FR-3000",
            "parent": "",
            "area": "INST",
            "hid": "",
            "level": "L1",
            "authored_hid": "INST-1",
            "status": status,
        }
    ]
    if status == "pending":
        generator._hierarchy(rows)
    else:
        with pytest.raises(generator.MalformedRequirementPageError, match="L1 status"):
            generator._hierarchy(rows)


@pytest.mark.parametrize(
    "subject",
    ["The library", "The library's workspace settings module"],
    ids=["P0420-library", "P0420-named-component"],
)
def test_p0420_s3_writing_subjects_follow_authored_format(subject):
    from scripts.check_writing_rules import check

    assert "W07" not in check({"statement": subject + " shall record the result."})
    assert "W07" in check({"statement": subject + " shall be recorded."})


@pytest.mark.parametrize(
    "defect",
    ["numeric", "radical", "hid", "verification", "level", "reserved", "migration", "duplicate"],
    ids=lambda x: "P0420-" + x,
)
def test_p0420_structure_planted_controls(defect):
    row = {
        "uid": "FR-3000",
        "parent": "-",
        "hid": "INST-1",
        "level": "L1",
        "status": "pending",
        "verification_method": "analysis",
    }
    validate_structure([row], [], ["FR-3000"], ["FR-3000"])
    reserved, migration = [], ["FR-3000"]
    if defect == "numeric":
        row["uid"] = "FR-1a"
    elif defect == "radical":
        row["hid"] = "OTHER-1"
    elif defect == "hid":
        row["hid"] = "INST-2"
    elif defect == "verification":
        row["verification_method"] = "review"
    elif defect == "level":
        row.pop("level")
    elif defect == "reserved":
        reserved = ["FR-3000"]
    elif defect == "duplicate":
        migration.append("FR-3000")
    else:
        migration = []
    with pytest.raises(AssertionError):
        validate_structure([row], reserved, ["FR-3000"], migration)


def validate_method(text):
    rows = [
        [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        for line in text.splitlines()
        if line.startswith("| NL-")
    ]
    for radical in RADICALS:
        assert any(
            len(row) == METHOD_COLUMNS
            and row[0] == "NL-" + radical
            and row[1] == "L0"
            and row[2].startswith("The system shall ")
            and all(row)
            for row in rows
        ), radical
    assert any(
        row[0] == "NL-WKSP-1" and row[1] == "L1" and row[2] == WORKSPACE_STATEMENT for row in rows
    )


def test_p0420_method_stages_and_workspace_version_control():
    path = REPO / "docs/srs/numerical-laboratory-method.md"
    validate_method(path.read_text("utf-8") if path.exists() else "")


@pytest.mark.parametrize("missing", [*RADICALS, "WKSP-1"], ids=lambda x: "P0420-" + x)
def test_p0420_method_planted_missing_row(missing):
    rows = [f"| NL-{r} | L0 | The system shall act. | why | like | test | src |" for r in RADICALS]
    rows.append(f"| NL-WKSP-1 | L1 | {WORKSPACE_STATEMENT} | why | like | test | src |")
    text = "\n".join(rows)
    validate_method(text)
    mutant = "\n".join(row for row in rows if not row.startswith(f"| NL-{missing} |"))
    with pytest.raises(AssertionError):
        validate_method(mutant)


def test_p0420_areas_cover_method_and_quality():
    path = REPO / "docs/srs/areas.yaml"
    import yaml

    areas = yaml.safe_load(path.read_text("utf-8")) if path.exists() else {}
    assert set(areas.get("stages", {})) == set(RADICALS)
    codes = "QFSU QPEFF QCOMP QUSA QREL QSEC QMNT QFLX QSAF".split()
    assert list(areas["quality"]) == codes
    for i, value in enumerate(areas["quality"].values(), 1):
        assert value["clause"] == f"3.{i}"
        assert value["standard"] == "ISO/IEC 25010:2023"


def test_p0420_hid_legend_reads_authored_vocabulary(tmp_path):
    generator = _generator()
    srs = tmp_path / "docs/srs"
    srs.mkdir(parents=True)
    (srs / "areas.yaml").write_text(
        "stages:\n  INST: {stage: Changed title, mnemonic: Changed mnemonic}\nquality: {}\n",
        encoding="utf-8",
    )
    legend = generator.hid_legend(tmp_path)
    assert "| INST | Changed title | Changed mnemonic |" in legend


def test_p0420_register_uses_public_manual_identity():
    from scripts._requirements_paths import read_l3, read_requirements

    rows = [*read_requirements(REPO), *read_l3(REPO)]  # FR-909 is L3 detail since 0.43.0
    definitions = [row["statement"] for row in rows if row["uid"] == "FR-909"]
    assert len(definitions) == 1
    assert "FSM-26.125" in definitions[0]
    assert "SRC-" not in definitions[0]


@pytest.mark.parametrize("header", [True, False], ids=["P0420-columns", "P0420-no-columns"])
def test_p0420_parity_uses_the_validated_requirement_reader(tmp_path, header):
    """P0420: a malformed table must not silently define an exception UID."""
    from scripts.check_parity import srs_ids

    page = tmp_path / "docs/unpublished/requirements/functional-requirements.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        ("| UID | Parent | Area | Status | Statement | Code | Test |\n" if header else "")
        + "| FR-900 | truncated |\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="malformed requirement row"):
        srs_ids(tmp_path)


GENERATOR = REPO / "scripts" / "gen_requirements_index.py"


@pytest.mark.parametrize(
    ("status", "rationale", "accepted"),
    [
        ("pending", "Planning node PFS-2142.001 remains open.", True),
        ("pending", "No planning node.", False),
        ("implemented", "Planning node PFS-2142.001.", False),
        ("deferred", "Planning node PFS-2142.001.", False),
    ],
    ids=["P0420-pending-node", "P0420-no-node", "P0420-implemented", "P0420-deferred"],
)
def test_p0420_s3_missing_anchors_require_pending_planning_node(status, rationale, accepted):
    generator = _generator()
    text = (
        "| UID | Parent | HID | Level | Status | Verification method | Statement "
        "| Rationale | Derives from | Code | Test |\n"
        f"| FR-1600 | FR-3000 | INST-1.1 | L2 | {status} | test | "
        f"The library shall record a result. | {rationale} | NL-INST | - | - |\n"
    )
    if accepted:
        rows = generator._table_rows(Path("inst.md"), text)
        generator._check_anchors(rows, REPO)
        assert rows[0]["code"] == rows[0]["test"] == ""
    else:
        with pytest.raises(generator.MalformedRequirementPageError, match="anchors"):
            generator._table_rows(Path("inst.md"), text)


def test_p0420_srs_reader_preserves_authored_attributes():
    from scripts._requirements_paths import requirement_rows

    text = (
        "| UID | Parent | HID | Level | Status | Verification method | Statement "
        "| Rationale | Derives from | Code | Test |\n"
        "| FR-1230 | - | INST-1 | L1 | pending | inspection | The library shall record a&#124;b. "
        "| reason | NL-INST | - | - |\n"
    )
    rows = requirement_rows(text)
    assert rows[0]["statement"] == "The library shall record a|b."
    assert rows[0]["verification_method"] == "inspection"
    assert rows[0]["derives_from"] == "NL-INST"
    with pytest.raises(ValueError, match="malformed"):
        requirement_rows(text.replace(" | reason", ""))


@pytest.mark.parametrize("uid", ["XR-1230", "FR_1230", "1230"])
def test_p0420_srs_reader_refuses_mistyped_uid(uid):
    """A mistyped UID in an authored table must not disappear from its readers."""
    from scripts._requirements_paths import requirement_rows

    generator = _generator()
    text = (
        "| UID | Parent | HID | Level | Status | Verification method | Statement "
        "| Rationale | Derives from | Code | Test |\n"
        f"| {uid} | - | INST-1 | L1 | pending | analysis | The library shall record a result. "
        "| reason | NL-INST | - | - |\n"
    )
    with pytest.raises(ValueError, match="invalid UID"):
        requirement_rows(text)
    with pytest.raises(generator.MalformedRequirementPageError, match="invalid UID"):
        generator._table_rows(Path("inst.md"), text)


def test_p0420_srs_reader_bounds_requirement_table():
    from scripts._requirements_paths import requirement_rows

    text = (
        "| UID | Parent | HID | Level | Status | Verification method | Statement "
        "| Rationale | Derives from | Code | Test |\n" + "|" + " --- |" * 11 + "\n"
        "| FR-1230 | - | INST-1 | L1 | pending | analysis | The library shall record a result. "
        "| reason | NL-INST | - | - |\n"
        "\nUnrelated table follows.\n\n| Name | Value |\n| alpha | beta |\n"
    )
    assert [row["uid"] for row in requirement_rows(text)] == ["FR-1230"]
    with pytest.raises(ValueError, match="malformed requirement row"):
        requirement_rows("| FR-1230 | orphan |\n")


def test_p0420_writing_rules_controls_and_baseline():
    path = REPO / "scripts/check_writing_rules.py"
    assert path.is_file(), "the repository writing-rule checker is missing"
    spec = importlib.util.spec_from_file_location("srs_writing_rules", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.controls() == {f"W{i:02}": True for i in range(1, 12)}
    counts = {rule: 0 for rule in module.RULES}
    assert not module.compare_baseline(counts, {"rules": counts})
    assert module.compare_baseline({**counts, "W03": 1}, {"rules": counts})
    assert module.compare_baseline(counts, {"rules": {}})


@pytest.mark.parametrize("receipt_name", ["receipt.json", "receipt.log"])
def test_p0420_writing_receipt_binds_committed_inputs(tmp_path, monkeypatch, receipt_name):
    from scripts import check_writing_rules as checker

    page = "docs/unpublished/requirements/inst.md"
    source = (
        "| UID | Parent | HID | Level | Status | Verification method | Statement "
        "| Rationale | Derives from | Code | Test |\n"
        "| FR-1230 | - | INST-1 | L1 | pending | inspection | The system shall record names. "
        "| - | NL-INST | - | - |\n"
    )
    sources = {
        page: source,
        "docs/unpublished/requirements/index.md": "# Index\n",
        "docs/srs/numerical-laboratory-method.md": "# Method\n",
        "docs/srs/uid-migration.csv": "uid,destination,target,new_uids,file\n",
        "docs/srs/reserved-ids.json": '{"reserved_ids": []}\n',
        "scripts/check_writing_rules.py": "# checker fixture\n",
    }
    head = "a" * 40

    def git_fixture(root, *args):
        if args[0] == "rev-parse":
            return head
        if args[0] == "status":
            return ""
        if args[0] == "ls-tree":
            return "\n".join(p for p in sources if p.startswith("docs/unpublished/"))
        assert args[0] == "show"
        return sources[args[1].split(":", 1)[1]].strip()

    monkeypatch.setattr(checker, "git", git_fixture)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"rules": dict.fromkeys(checker.RULES, 0)}), "utf-8")
    receipt_path = tmp_path / receipt_name
    assert (
        checker.main(
            ["--root", str(REPO), "--baseline", str(baseline), "--receipt", str(receipt_path)]
        )
        == 0
    )
    receipt = json.loads(receipt_path.read_text("utf-8"))
    assert receipt["head"] == head
    assert receipt["inputs"] == {
        name: checker.digest(value.strip().encode()) for name, value in sources.items()
    }
    assert receipt["input_hash_domain"] == "git-show-utf8-stripped"
    assert receipt["baseline_sha256"] == checker.digest(baseline.read_bytes())
    assert receipt["log_sha256"] == checker.digest(Path(receipt["log"]).read_bytes())
    assert receipt["checker"] == {
        "path": "scripts/check_writing_rules.py",
        "sha256": receipt["inputs"]["scripts/check_writing_rules.py"],
    }
    assert receipt["check_id"] == "srs-writing-rules"
    assert receipt["hash_domain"] == "exact-file-bytes"
    assert receipt["exit_status"] == 0

    baseline.write_text('{"rules": {}}', "utf-8")
    assert (
        checker.main(
            ["--root", str(REPO), "--baseline", str(baseline), "--receipt", str(receipt_path)]
        )
        == 1
    )
    assert json.loads(receipt_path.read_text("utf-8"))["exit_status"] == 1

    baseline.write_bytes(b"")
    with pytest.raises(json.JSONDecodeError):
        checker.main(["--root", str(REPO), "--baseline", str(baseline)])


def test_p0420_srs_w01_w02_w10_zero():
    from scripts._requirements_paths import read_requirements
    from scripts.check_writing_rules import check

    violations = {
        row["uid"]: sorted(set(check(row)) & {"W01", "W02", "W10"})
        for row in read_requirements(REPO, live_only=True)
    }
    assert not {uid: rules for uid, rules in violations.items() if rules}


def test_p0420_srs_writing_rules_never_exceed_the_s3_baseline():
    """PFS-2142: every measured writing-rule count may fall, never rise."""
    from scripts._requirements_paths import read_requirements
    from scripts.check_writing_rules import RULES, check, compare_baseline

    # 0.43.0 trim: 571 live L1/L2 rows measure zero on every rule (S3 baseline of
    # 2026-10-15 was 0, 0, 2, 0, 0, 0, 40, 3, 15, 0, 6 over 1,868 rows).
    limits = dict.fromkeys(RULES, 0)
    findings = [check(row) for row in read_requirements(REPO, live_only=True)]
    counts = {rule: sum(rule in found for found in findings) for rule in RULES}
    assert compare_baseline(counts, {"rules": limits}) == []
    for rule in RULES:
        raised = {**limits, rule: limits[rule] + 1}
        assert compare_baseline(raised, {"rules": limits}), rule
        lowered = {**limits, rule: max(0, limits[rule] - 1)}
        assert compare_baseline(lowered, {"rules": limits}) == [], rule


def test_p0410_pa2_owned_citations_use_stable_uids() -> None:
    """P0410-PA2: source, tests and authored SRS reject former child citations."""
    paths = subprocess.check_output(
        [
            "git",
            "ls-files",
            "src",
            "tests",
            "docs/srs",
            "docs/unpublished/requirements",
        ],
        cwd=REPO,
        text=True,
    ).splitlines()
    old = re.compile(r"\b(?:FR|NFR)-\d+[a-z]?(?:[ .]+|\s*\)\s*:?\s*)" + r"R\d+\b")
    broken = []
    for relative in paths:
        path = REPO / relative
        if path.suffix not in {".py", ".md", ".json", ".toml", ".yaml", ".yml"}:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if old.search(line):
                broken.append(f"{relative}:{number}")
    assert not broken, broken


GOOD_BOX = (
    "!!! requirement \"FR-901 A title <span class='srs-implemented'>implemented</span>\"\n"
    "    *Origin: a fixture. Evidence: tests/tier1_offline/test_requirements_index.py.*\n"
    "\n"
    "    The statement.\n"
)


def _generator() -> ModuleType:
    """Import the generator by path, since ``scripts`` is not a package."""
    spec = importlib.util.spec_from_file_location("pyflightstream_gen_index", GENERATOR)
    assert spec is not None and spec.loader is not None, f"cannot load {GENERATOR}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0410_pa2_generated_requirement_page_links_resolve() -> None:
    """P0410-PA2: generated pages contain no dangling local Markdown links."""
    generator = _generator()
    pages = generator.requirement_pages(generator.collect(generator.SRS))
    broken = []
    for name, body in pages.items():
        for target in re.findall(r"\]\(([^)]+\.md)(?:#[^)]*)?\)", body):
            if "://" not in target and target not in pages:
                broken.append(f"{name}: {target}")
    assert not broken, broken


def _run_on(page_text: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Run the generator over one hostile page, writing inside ``tmp_path``.

    Returns
    -------
    tuple of (int, str, pathlib.Path)
        The process return code, everything the run wrote to stderr, and
        the output path it was pointed at. The path is inside
        ``tmp_path``, so a run that writes when it should refuse is
        visible here and cannot touch the committed index.
    """
    srs = tmp_path / "srs"
    srs.mkdir()
    (srs / "functional-requirements.md").write_text(page_text, encoding="utf-8")
    out = tmp_path / "requirements-index.json"

    module = _generator()
    monkeypatch.setattr(module, "SRS", srs)
    monkeypatch.setattr(module, "OUT", out)
    monkeypatch.setattr(module, "TESTS", tmp_path / "tests")
    # REPO travels with them: the success message reports the output path
    # relative to it, and leaving it pointing at the real repository makes
    # a green run raise instead of printing.
    monkeypatch.setattr(module, "REPO", tmp_path)
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(sys, "argv", ["gen_requirements_index.py"])

    err = io.StringIO()
    with redirect_stderr(err), redirect_stdout(io.StringIO()):
        code = module.main()
    return code, err.getvalue(), out


def test_a_requirement_box_with_no_badge_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A box with no ``srs-`` badge refuses, naming the page and the id.

    This is the shape with the worst consequence. Until this refusal, a
    box whose badge was lost in an edit defaulted to ``implemented``, so
    a requirement nobody has built was published to an external
    dashboard as done, with a priority of ``M``.
    """
    page = '!!! requirement "FR-901 A title"\n\n    The statement.\n'
    code, err, out = _run_on(page, monkeypatch, tmp_path)
    assert code != 0, f"the generator published a badgeless box and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert "FR-901" in err, err
    assert "badge" in err.lower(), err


def test_a_badge_token_outside_the_known_set_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unknown badge token refuses rather than being published as-is.

    ``srs-implemnted`` is a typo, not a status. Published unread it
    reaches the consumer as a status string no dashboard column knows,
    and priority ``M``, which is the deferred-published-as-mandatory
    failure with an extra step.
    """
    page = GOOD_BOX.replace("srs-implemented", "srs-implemnted")
    code, err, out = _run_on(page, monkeypatch, tmp_path)
    assert code != 0, f"the generator published an unknown badge token and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert "FR-901" in err, err
    assert "implemnted" in err, err


def test_a_repeated_requirement_id_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two boxes with one id refuse, naming the page and the id.

    The index is keyed by id for its consumer. Two boxes sharing one id
    publish two entries a reader cannot tell apart, and whichever sorts
    last silently answers for both.
    """
    second = GOOD_BOX.replace("A title", "The same id, said twice")
    code, err, out = _run_on(GOOD_BOX + "\n" + second, monkeypatch, tmp_path)
    assert code != 0, f"the generator published a repeated id and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert "FR-901" in err, err


def test_a_requirement_header_the_parser_cannot_read_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A header the box pattern misses refuses, naming the line number.

    This is the silent one. A header the pattern does not match produces
    no entry at all, and its body is absorbed into the PREVIOUS box,
    whose own statement still looks right, so the run is green and one
    requirement has simply stopped existing. The id is what failed to
    parse, so the message names the line rather than an id it does not
    have.
    """
    broken = '!!! requirement "FR902 No hyphen in the id"\n\n    The statement.\n'
    code, err, out = _run_on(GOOD_BOX + "\n" + broken, monkeypatch, tmp_path)
    assert code != 0, f"the generator published an unreadable header and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert "functional-requirements.md" in err, err
    assert ":6" in err, f"the message must name the line the header is on: {err}"
    assert "id" in err.lower() and "pars" in err.lower(), err


def test_a_header_whose_identifier_parses_is_refused_without_blaming_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other half of an unreadable header, and it names the right half.

    A header can be unreadable with a perfectly good identifier: no
    title, no closing quote, or no line after it. The refusal still
    fires, because the consequence is the same silent absorption, but
    the message names the identifier as parsed rather than sending the
    author to look at the one part of the line that is correct.
    """
    broken = '!!! requirement "FR-903"\n\n    The statement.\n'
    code, err, out = _run_on(GOOD_BOX + "\n" + broken, monkeypatch, tmp_path)
    assert code != 0, f"the generator published a titleless header and exited {code}"
    assert not out.exists(), "the generator wrote an index from a page it should refuse"
    assert ":6" in err, f"the message must name the line the header is on: {err}"
    assert "FR-903" in err, err
    assert "parses" in err, f"the message must not blame the identifier that parsed: {err}"


def test_a_well_formed_page_still_publishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The strict form is not strict about the shape the SRS actually uses.

    A refusal battery that also refuses the healthy page would pass every
    test above and stop the build, so the well-formed fixture is asserted
    to publish rather than assumed to.
    """
    code, err, out = _run_on(GOOD_BOX, monkeypatch, tmp_path)
    assert code == 0, err
    published = json.loads(out.read_text(encoding="utf-8"))["requirements"]
    assert [e["id"] for e in published] == ["FR-901"], published
    assert published[0]["status"] == "implemented"


def test_p0410_srs_uids_survive_reordering_while_hids_follow_the_tree(tmp_path):
    """PFS-2081.37: stable identity is independent of generated placement."""
    page = tmp_path / "functional-requirements.md"
    header = "| UID | Parent | Area | Status | Statement | Code | Test |\n"
    rows = [
        "| FR-1 | - | MESH | implemented | Refine a mesh. | m:refine | t.py::test_refine |\n",
        "| FR-2 | FR-1 | MESH | implemented | Preserve the interface. "
        "| m:join | t.py::test_join |\n",
        "| NFR-1 | - | MESH | implemented | Refuse invalid input. | m:read | t.py::test_read |\n",
        "| FR-3 | - | MESH | retired | Removed route. | - | - |\n",
    ]
    page.write_text(header + "".join(rows), encoding="utf-8")
    generator = _generator()
    first = {r["id"]: r for r in generator.collect(tmp_path)}
    assert set(first) == {"FR-1", "FR-2", "NFR-1", "FR-3"}
    assert first["FR-1"]["hid"] == "MESH-1"
    assert first["FR-2"]["hid"] == "MESH-1.1"
    assert first["NFR-1"]["hid"] == "MESH-2"
    assert first["FR-3"]["hid"] == ""
    pages = generator.requirement_pages(list(first.values()))
    assert '<a id="FR-2"></a>' in pages["mesh.md"]
    assert "FR-2 / MESH-1.1" in pages["mesh.md"]
    assert "FR-3" not in pages["mesh.md"]
    assert "FR-3" in pages["index.md"]
    page.write_text(header + "".join([rows[2], *rows[:2], rows[3]]), encoding="utf-8")
    second = {r["id"]: r for r in generator.collect(tmp_path)}
    assert second["FR-1"]["hid"] == "MESH-2"
    assert second["FR-2"]["hid"] == "MESH-2.1"
    assert {uid: r["text"] for uid, r in first.items()} == {
        uid: r["text"] for uid, r in second.items()
    }


@pytest.mark.parametrize(
    "bad_row",
    [
        "| FR-1 | - | MESH | implemented | Duplicate. | m:f | t.py::test_f |",
        "| FR-2 | FR-99 | MESH | implemented | Missing parent. | m:f | t.py::test_f |",
        "| FR-2 | FR-2 | MESH | implemented | Cycle. | m:f | t.py::test_f |",
        "| FR-2 | - | MESH | implemented | Missing code. | - | t.py::test_f |",
        "| FR-2 | - | MESH | implemented | Missing test. | m:f | - |",
    ],
)
def test_p0410_srs_refuses_ambiguous_or_unanchored_rows(tmp_path, bad_row):
    """PFS-2081.37: incomplete trace links cannot publish as verified claims."""
    (tmp_path / "functional-requirements.md").write_text(
        "| UID | Parent | Area | Status | Statement | Code | Test |\n"
        "| FR-1 | - | MESH | implemented | Refine. | m:f | t.py::test_f |\n" + bad_row + "\n",
        encoding="utf-8",
    )
    generator = _generator()
    with pytest.raises(generator.MalformedRequirementPageError):
        generator.collect(tmp_path)


@pytest.mark.parametrize(
    "broken",
    [
        "code",
        "test",
        "none",
        "assignment",
        "annotation",
        "helper_class",
        "class_only",
        "test_class",
        "code_constant",
    ],
)
def test_p0410_srs_resolves_anchors_before_publishing(tmp_path, monkeypatch, broken):
    """An invented symbol or test must not become a published trace link."""
    srs = tmp_path / "srs"
    srs.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (src / "sample.py").write_text("def refine():\n    pass\n", encoding="utf-8")
    (tests / "test_sample.py").write_text("def test_refine():\n    assert True\n", encoding="utf-8")
    symbol = "missing" if broken == "code" else "refine"
    test = "test_missing" if broken == "test" else "test_refine"
    if broken in {"assignment", "annotation", "helper_class", "class_only", "test_class"}:
        content = {
            "assignment": "test_refine = None\n",
            "annotation": "test_refine: object = None\n",
            "helper_class": "class Helper:\n    def test_refine(self):\n        assert True\n",
            "class_only": "class test_refine:\n    pass\n",
            "test_class": "class TestExample:\n    def test_refine(self):\n        assert True\n",
        }[broken]
        (tests / "test_sample.py").write_text(content, encoding="utf-8")
        if broken in {"helper_class", "test_class"}:
            test = ("Helper" if broken == "helper_class" else "TestExample") + "::test_refine"
    if broken == "code_constant":
        (src / "sample.py").write_text("refine = 1\n", encoding="utf-8")
    (srs / "functional-requirements.md").write_text(
        "| UID | Parent | Area | Status | Statement | Code | Test |\n"
        f"| FR-1 | - | MESH | implemented | Refine. | sample:{symbol} "
        f"| tests/test_sample.py::{test} |\n",
        encoding="utf-8",
    )
    generator = _generator()
    monkeypatch.setattr(generator, "REPO", tmp_path)
    if broken in {"none", "test_class", "code_constant"}:
        assert generator.build(srs, tests)["requirements"][0]["id"] == "FR-1"
    else:
        with pytest.raises(generator.MalformedRequirementPageError, match="FR-1"):
            generator.build(srs, tests)


def test_p0410_srs_main_writes_and_checks_the_generated_pages(tmp_path, monkeypatch):
    """The command must deliver its pages and detect edits to a generated page."""
    code, err, out = _run_on(GOOD_BOX, monkeypatch, tmp_path)
    assert code == 0, err
    index = out.parent / "requirements" / "index.md"
    assert index.is_file(), "the generator published its JSON but omitted the pages"
    index.write_text("stale\n", encoding="utf-8")
    generator = _generator()
    monkeypatch.setattr(generator, "SRS", tmp_path / "srs")
    monkeypatch.setattr(generator, "OUT", out)
    monkeypatch.setattr(generator, "TESTS", tmp_path / "tests")
    monkeypatch.setattr(generator, "REPO", tmp_path)
    monkeypatch.setattr(sys, "argv", ["gen_requirements_index.py", "--check"])
    assert generator.main() == 1


def test_p0410_pa2_unreadable_saved_actions_warn_with_the_file(tmp_path):
    """P0410-PA2 (FR-538): an unreadable file is named without raising."""
    from pyflightstream.workspace._geometry_clean import saved_action_warning

    source = tmp_path / "unreadable.fsm"
    message = saved_action_warning(source, source.name, ["P7"])
    assert message is not None
    assert source.name in message and "P7" in message
    assert "cannot be read" in message
    assert not source.exists()


@pytest.mark.parametrize("sideslip", [-2.0, 2.0])
def test_p0410_pa2_section_trefftz_names_a_sideslip_skip(sideslip):
    """P0410-PA2 (FR-1018): an inapplicable section analysis writes no result."""
    from types import SimpleNamespace

    from pyflightstream.cases import PprocSpec
    from pyflightstream.exceptions import PyflightstreamWarning
    from pyflightstream.post.farfield_products import farfield_products

    context = SimpleNamespace(
        pproc=PprocSpec.model_validate(
            {"farfield": {"families": ["Wing"], "trefftz": {"variant": ["sections"]}}}
        ),
        skipped={},
        farfield_super={},
        sources={"P7": ["run7"]},
        record_of={"P7": SimpleNamespace(recipe="steady", point={})},
        matrix_row=SimpleNamespace(variables={}),
    )
    point = SimpleNamespace(
        name="P7",
        state=SimpleNamespace(density_kg_m3=1.2),
        loads=SimpleNamespace(
            freestream_velocity_m_s=30.0, angle_of_attack_deg=0.0, sideslip_deg=sideslip
        ),
    )
    with pytest.warns(PyflightstreamWarning, match="point=P7.*sideslip"):
        context.points = [point]
        farfield_products(context)
    assert context.farfield_super == {}
    assert len(context.skipped) == 1
    reason = next(iter(context.skipped.values()))
    assert "sideslip" in reason and "variants B and C" in reason


# ---------------------------------------------------------------------------
# Documentation facts of package F7-05 (0.43.0): each page states what the
# command line, the code and the command database do.
# ---------------------------------------------------------------------------


def _doc(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def test_p0430_install_check_command_succeeds():
    """The installation check documented on docs/install.md exits 0 (X-F-1271)."""
    from pyflightstream.run.cli import main

    section = _doc("docs/install.md").split("## Check the installation")[1].split("\n## ")[0]
    flags = re.findall(r"`pyfs-matrix (--[a-z-]+)`", section)
    assert flags, "the page documents no pyfs-matrix check command"
    for flag in flags:
        with pytest.raises(SystemExit) as stopped:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                main([flag])
        assert stopped.value.code == 0, flag


def test_p0430_steady_page_states_the_rotation_the_package_applies():
    """No page teaches `angle_deg` as a rotation: nothing reads it (X-F-1400)."""
    text = _doc("docs/workflow-steady.md")
    assert "angle_deg: 5.0" not in text
    assert "`ROTATE: {ANGLE: 5 / AXIS: MRP-Y / ALIAS: airframe}`" in text


def test_p0430_window_keys_are_described_as_retired():
    """WINDOW_* keys are refused, and the rotor page says so (F-1730, X-F-1401)."""
    text = _doc("docs/workflow-unsteady-rotor.md")
    assert "keep their one job" not in text
    assert "are retired and a row that states one is refused" in text


def test_p0430_the_translation_unit_is_one_statement():
    """A translation is in metres whatever the simulation unit (F-1729)."""
    text = _doc("docs/workflow-row-geometry-motion.md")
    assert "right only on a simulation whose" not in text
    assert "so a translation is in metres whatever that unit is" in text


def test_p0430_input_library_does_not_call_an_emitting_key_refused():
    """The keys with emitters are not listed as refused; the admonition renders (F-1725, F-1726)."""
    text = _doc("docs/workflow-input-library.md")
    assert "Two other refused keys are" not in text
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith('!!! warning "`axial_separation'))
    body = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        body.append(line)
    assert body and all(line.startswith("    ") for line in body)
    assert "no further and" not in " ".join(body)


def _guide_numbers() -> dict[int, str]:
    """Guide number to the folder that builds it, from each guide's own title macro."""
    found = {}
    for source in sorted((REPO / "guide/latex-sources").glob("0*/main.tex")):
        found[int(source.parent.name[:2])] = source.parent.name
    return found


def test_p0430_guide_two_numbers_the_other_guides_as_the_folders_do():
    """Guide 2 lists guides by the numbers they carry and never itself (F-1785, X-F-1473)."""
    numbers = _guide_numbers()
    text = (REPO / "guide/latex-sources/02-workspaces/main.tex").read_text(encoding="utf-8")
    block = text.split(r"\begin{block}{The other guides}")[1].split(r"\end{block}")[0]
    listed = [int(n) for n in re.findall(r"(?:\\item|\\quad)\s*(\d+):", block)]
    assert listed and 2 not in listed
    assert set(listed) <= set(numbers)
    assert 9 in listed and "9: installing Python" in block


def test_p0430_offline_guide_spells_the_wheel_folder_once():
    """Every pfs-wheels path of Guide 9 names the folder the download wrote (F-1788, X-F-1490)."""
    text = (REPO / "guide/latex-sources/09-python-environment-offline/main.tex").read_text(
        encoding="utf-8"
    )
    bare = re.findall(r"pfs-wheels/(?:\(\*@\\envname@\*\)|\\envname)(?!-)", text)
    assert not bare, bare


def test_p0430_motion_start_time_status_matches_the_command_database():
    """The user guide states the builds on which SET_MOTION_START_TIME is broken (F-1784)."""
    import yaml

    database = yaml.safe_load(_doc("src/pyflightstream/commands/motion_definitions.yaml"))
    versions = database["SET_MOTION_START_TIME"]["versions"]
    broken = sorted(build for build, entry in versions.items() if entry["status"] == "broken")
    assert broken == ["26.101", "26.121"]
    guide = _doc("guide/pyflightstream_user_guide.tex")
    for sentence in re.findall(r"SET\\_MOTION\\_START\\_TIME is recorded.*?\.(?=\s)", guide):
        assert "26.120 and 26.121" not in sentence, sentence
        assert "26.101 and 26.121" in sentence


def test_p0430_rebuild_archive_policy_is_one_statement():
    """Guide text and figure agree: a rebuild overwrites, `post --archive` keeps (F-1789)."""
    guide = _doc("guide/pyflightstream_user_guide.tex")
    figure = _doc("guide/latex-sources/shared/tikz/guide-post-anatomy.tex")
    assert "does not archive" not in guide
    assert "pyfs-matrix post --archive" in guide
    assert "post --archive keeps a copy" in figure
    assert "archive it yourself" not in figure


def test_p0430_cheat_sheet_uses_the_supported_sims_form():
    """The cheat sheet shows `--sims`, not the deprecated positional selector (F-1555)."""
    line = next(
        ln
        for ln in _doc("guide/pyflightstream_user_guide.tex").splitlines()
        if ln.startswith("pyfs-matrix delete-sims")
    )
    assert "--sims 4001 2009" in line and "4001,2009" not in line


def test_p0430_rotor_slide_says_a_missing_blade_family_is_skipped():
    """A blade family the geometry lacks gets no frame; it is not refused (X-F-1474)."""
    text = _doc("guide/latex-sources/05-references/text/04-rotors.tex")
    assert "is skipped" in text
    assert "naming a blade family the opened geometry does not" not in text
