"""The release requirements agree with their evidence and locator contracts."""
# ruff: noqa: N999 - the assigned lane name is rfixD.

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs/unpublished/requirements/functional-requirements.md"
pytestmark = pytest.mark.requirement("P0400-RFIXD-CONTRACTS")


def box(identifier: str) -> str:
    text = PAGE.read_text(encoding="utf-8")
    start = text.index(f'!!! requirement "{identifier} ')
    end = text.find('\n!!! requirement "', start + 1)
    return text[start : end if end >= 0 else len(text)]


@pytest.mark.requirement("FR-450")
def test_p0400_rfixd_67_solver_adaptation_and_pure_transforms_are_distinct() -> None:
    requirement = box("FR-450")
    architecture = (REPO / "docs/srs/architecture-srs.md").read_text(encoding="utf-8")
    for text in (requirement, architecture):
        assert "solver sign, unit and frame adaptation" in text
        assert "cylindrical_components" in text
        assert "hub_frame_velocities" in text
        assert "pure vector transforms" in text.lower()
    assert "never turns them" not in requirement


@pytest.mark.requirement("FR-452")
def test_p0400_rfixd_77_short_wake_oracle_counts_edges() -> None:
    requirement = box("FR-452")
    assert "160 strips bounded by 161 wake lines" in requirement
    assert "3 of 161" in requirement
    source = (REPO / "tests/tier1_offline/test_p0400_ffproof_post.py").read_text(encoding="utf-8")
    assert "3 of 161 wake lines end before the plane" in source
    assert "3 of 159" not in source


@pytest.mark.requirement("FR-452")
def test_p0400_rfixd_78_shed_strengths_reconstruct_bound_strips() -> None:
    requirement = box("FR-452")
    assert "signed shed circulation at strip edges" in requirement
    assert "`CELL_DATA` `Normalized_Vorticity`" in requirement
    assert "`POINT_DATA` holds redundant X, Y and Z coordinate scalars" in requirement
    assert "Gamma_raw[j] = -sum(value[0:j+1])" in requirement
    assert "negative sum from line j+1 through the tip" in requirement
    assert "midpoint" in requirement
    assert "actual crossings" in requirement
    assert "coincident root lines" in requirement
    assert "p0400_litB_wake_26124.vtk" in requirement
    assert "p0400_litB_wake_26125_fine.vtk.xz" in requirement
    assert "test_p0400_litb_signed_full_sheet_reconstructs_the_strip_loading" in requirement
    assert "line values equal A's circulation" not in requirement
    assert "one sign across the span" not in requirement


@pytest.mark.requirement("FR-451")
def test_p0400_rfixd_81_origin_does_not_claim_unverified_percentages() -> None:
    origin = next(line for line in box("FR-451").splitlines() if "*Origin:" in line)
    assert "unverified motivation" in origin
    assert "under 1 percent" not in origin
    assert "2.5 to 10 percent" not in origin


@pytest.mark.requirement("FR-46")
def test_p0400_rfixd_82_six_statuses_is_historical() -> None:
    requirement = box("FR-46")
    assert "at that consolidation the closed set had six values" in requirement
    assert "current member set is pinned" in requirement
    assert "set stays closed at six" not in requirement


@pytest.mark.requirement("FR-434")
def test_p0400_rfixd_83_footer_and_residual_cases_are_separate() -> None:
    verification = next(
        line
        for line in box("FR-434").splitlines()
        if line.strip().startswith("Verification: test,")
    )
    assert "whose loads footer has no counter is `FAILED_INCOMPLETE_OUTPUT`" in verification
    assert "footer supplies the counter but has no readable residual evidence" in verification


@pytest.mark.requirement("FR-471")
def test_p0400_rfixd_84_audit_failure_retains_partial_without_promotion() -> None:
    requirement = box("FR-471")
    r8 = next(line for line in requirement.splitlines() if "- R8 " in line)
    assert "promotes nothing" in r8
    assert "partial folder" in r8
    assert "inspection" in r8
    assert "Except for a failed audit" not in requirement


@pytest.mark.requirement("FR-472")
def test_p0400_rfixd_85_sweep_overlay_can_write_the_base_folder() -> None:
    requirement = box("FR-472")
    assert "variant builds do not replace the base geometry files" in requirement
    assert "R7 writes the sweep overlay in the base folder" in requirement
    assert "the base folder is not written" not in requirement


@pytest.mark.requirement("FR-79")
def test_p0400_rfixd_86_probe_home_amendment_is_implemented() -> None:
    amendment = next(line for line in box("FR-79").splitlines() if "P0400-PROBEHOME" in line)
    assert "(0.40.0, implemented)" in amendment


@pytest.mark.requirement("FR-433")
def test_p0400_rfixd_87_uniform_tag_defect_is_closed() -> None:
    requirement = box("FR-433")
    assert "Closed in 0.40.0 (PFS-2081.02)" in requirement
    assert "test_p0400_uniform_tag_limit" in requirement
    assert "R2 does not yet hold" not in requirement


@pytest.mark.requirement("FR-38")
def test_p0400_rfixd_88_definition_locators_resolve() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "(../definitions/the-far-field-family.md" not in text
    assert "(../../definitions/the-far-field-family.md#the-balances)" in box("FR-38")
    assert (PAGE.parent / "../../definitions/the-far-field-family.md").resolve().is_file()


@pytest.mark.requirement("FR-460")
def test_p0400_rfixd_89_titles_close_without_an_escape() -> None:
    for identifier in ("FR-460", "FR-461", "FR-462"):
        title = box(identifier).splitlines()[0]
        assert title.endswith('>"'), title


@pytest.mark.requirement("FR-461")
def test_p0400_rfixd_90_trajectory_evidence_has_the_direct_test_and_report() -> None:
    requirement = box("FR-461")
    assert "test_p0400_6dofexport_the_trajectory_is_exported_after_the_march" in requirement
    report = "../../../reports/RPT-167_6dof-trajectory-export-after-march_2026-10-12.md"
    assert f"({report}#trajectory-evidence)" in requirement
    target = (PAGE.parent / report).resolve()
    assert target.is_file()
    assert "## Trajectory evidence" in target.read_text(encoding="utf-8")
    assert "does not establish trajectory-column units" in requirement
