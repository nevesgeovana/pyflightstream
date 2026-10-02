"""Tier 1: why CDo reads zero in a coupled FSI run (FR-338) and the XZ cut moment (FR-340), RPT-128.

It restores the two marker tests P0340-FSI-CDO and P0340-FSI-XZ, held out of the 0.34.0 tag
until RPT-128 was committed, with only the branches a post-release commit can leave in the tree,
and adds tests on the recorded exports. On the `solver` branch the product's statement of the
column's meaning is read from docs/post-processing-definitions.md, the definition of record of
every product column.

The fixtures are the loads spreadsheets the three points of RPT-128 exported on FlightStream
26.124 (build 8172026), far field 5: the rigid half wing's own export, the coupled point's own
export and the head export of its last pass, and the head and own exports of the coupled point
capped at one coupling iteration. Only the Total row is read.

A `package_order` cause or a `refuted` verdict cannot be committed after the tag: each leaves a
change in src/ (the export order, FR-338 R2; the warning on every coupled run, FR-340 R4), outside
the post-release allowlist; the first and fifth tests fail on them by design, naming the release
that owes the change.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-338, FR-340.

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream.results.loads import parse_loads

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "reports"
FSI_PAGE = REPO / "docs" / "fsi-workspace.md"
DEFINITIONS = REPO / "docs" / "post-processing-definitions.md"
FIX = Path(__file__).resolve().parent / "fixtures" / "rpt128"


def _front_matter(number: int) -> tuple[Path, dict[str, str]]:
    """Return a report and the ``key: value`` fields of its front matter, or fail naming it."""
    found = sorted(REPORTS.glob(f"RPT-{number}_*.md"))
    if not found:
        pytest.fail(f"RPT-{number} is not in reports/: its licensed run owes it")
    lines = found[0].read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in lines[1:]:
        pytest.fail(f"{found[0].name} opens with no front matter between two '---' lines")
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    return found[0], fields


def _paragraphs(text: str) -> list[str]:
    """Return the page's paragraphs: runs of non-blank lines, each joined into one string."""
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", text) if block.strip()]


def _cdo(name: str) -> float:
    return float(parse_loads((FIX / f"{name}.txt").read_text(encoding="latin-1")).total["CDo"])


def cdo_cause(
    rigid: float, coupled: float, capped_head: float, capped_own: float, one_pass: bool
) -> str:
    """FR-338's reading, fixed before the run (the kit's table): which export first reads zero."""
    if rigid == 0.0 or coupled != 0.0 or not one_pass:
        return "undetermined"
    if capped_head == 0.0:
        return "solver"
    if capped_own == 0.0:
        return "package_order"
    return "undetermined"


def _xz_verdict(moment_ratio: float, force_ratio: float) -> str:
    """FR-340 R2, fixed before the run: confirmed when the moment ratio is as close to 1."""
    return "confirmed" if abs(moment_ratio - 1.0) <= abs(force_ratio - 1.0) else "refuted"


def test_rpt128_states_why_cdo_reads_zero_and_the_tree_holds_its_branch_fr_338():
    """P0340-FSI-CDO, FR-338: `cdo_cause` is `solver`; the page and the product state the column.

    R3 and R4, the `solver` branch: one paragraph of the FSI page states that `CDo` reads zero in a
    coupled run, and why, citing RPT-128; the product's statement of the column is the definition
    of record of every product column, docs/post-processing-definitions.md, which states the
    measured zero and that `CD0` reads it, and no reading RPT-128 does not measure.
    """
    report, fields = _front_matter(128)
    cause = fields.get("cdo_cause")
    assert cause in {"package_order", "solver"}, (
        f"{report.name}: cdo_cause is {cause!r}, and FR-338 accepts package_order or solver"
    )
    if cause == "package_order":
        pytest.fail(
            f"{report.name} names the package's order: the corrected export order, its test "
            "with the 0.33.0 order as the control and the parity entry (FR-338 R2, R4) are "
            "src, owed to 0.35.0"
        )
    stated = [
        p
        for p in _paragraphs(FSI_PAGE.read_text(encoding="utf-8"))
        if "`CDo`" in p and "RPT-128" in p and re.search(r"\bzero\b", p) and "coupled" in p
    ]
    assert stated, (
        "FR-338 R3: one paragraph of the FSI page states that `CDo` reads zero in a coupled "
        "run, citing RPT-128"
    )
    defined = [
        p
        for p in _paragraphs(DEFINITIONS.read_text(encoding="utf-8"))
        if "`CDo`" in p and "RPT-128" in p and "coupled" in p
    ]
    assert defined, (
        "FR-338 R4: the definitions page states what `CDo` reads in a coupled run, citing RPT-128"
    )
    measured = "prints `CDo` as zero from the first export of its first coupling pass"
    assert any(measured in p and "`CD0` reads that zero" in p for p in defined), (
        "FR-338 R4: the definitions paragraph states the measured fact of RPT-128 and that "
        "`CD0` reads that zero"
    )
    unmeasured = (
        "`CDW` equals `CDI`",
        "profile drag of the coupled wing",
        "not the profile drag of a coupled run",
    )
    beyond = [claim for p in defined + stated for claim in unmeasured if claim in p]
    assert not beyond, (
        f"FR-338: the pages state {beyond}, which RPT-128 does not measure; they state the "
        "measured zero and no more"
    )


def test_the_recorded_exports_give_the_cause_rpt128_states_fr_338():
    """P0340-FSI-CDO, FR-338 R1: the cause recomputed from the five recorded loads exports."""
    report, fields = _front_matter(128)
    one_pass = fields.get("capped_one_pass") == "true"
    cause = cdo_cause(
        _cdo("rigid"), _cdo("coupled"), _cdo("capped_head"), _cdo("capped_own"), one_pass
    )
    assert cause == fields.get("cdo_cause"), (
        f"{report.name} states {fields.get('cdo_cause')!r}; the exports give {cause!r}"
    )


def test_the_rigid_export_is_the_control_that_can_say_different_fr_338():
    """P0340-FSI-CDO, FR-338: the rigid CDo is not zero where the coupled one is (the control)."""
    assert _cdo("rigid") != 0.0
    assert _cdo("coupled") == 0.0


#: Each recorded export, by the start of its row in RPT-128's `CDo` table.
_TABLE_ROWS = {
    "9341, own export": "rigid",
    "9342, own export": "coupled",
    "9342, head export of the last pass": "coupled_head_last_pass",
    "9343, head export": "capped_head",
    "9343, own export": "capped_own",
}


def test_each_recorded_export_reads_the_cdo_rpt128_tabulates_fr_338():
    """P0340-FSI-CDO, FR-338 R1: every fixture is the export RPT-128's `CDo` table states.

    The head export of the coupled point's last pass decides nothing (it follows the updates of
    every earlier pass); its row is read like the others, so no recorded export is unread.
    """
    report, _ = _front_matter(128)
    stated: dict[str, float] = {}
    for line in report.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2:
            continue
        for start, name in _TABLE_ROWS.items():
            if cells[0].startswith(start) and re.match(r"[-+.\d]", cells[1]):
                stated[name] = float(cells[1].split()[0])
    assert sorted(stated) == sorted(_TABLE_ROWS.values()), (
        f"{report.name}: the `CDo` table has rows for {sorted(stated)}, not all five exports"
    )
    for name, value in stated.items():
        assert _cdo(name) == value, (
            f"{report.name} tabulates CDo {value} for {name}; "
            f"its recorded export reads {_cdo(name)}"
        )


def test_a_planted_reading_moves_the_cause_fr_338():
    """P0340-FSI-CDO, FR-338: the control of the cause table, each branch reached by one change."""
    assert cdo_cause(0.0094, 0.0, 0.0, 0.0, True) == "solver"
    assert cdo_cause(0.0094, 0.0, 0.0091, 0.0, True) == "package_order"
    assert cdo_cause(0.0094, 0.0, 0.0091, 0.0090, True) == "undetermined"
    assert cdo_cause(0.0094, 0.0, 0.0, 0.0, False) == "undetermined"
    assert cdo_cause(0.0, 0.0, 0.0, 0.0, True) == "undetermined"


def test_rpt128_xz_moment_verdict_follows_its_two_ratios_and_the_tree_holds_it_fr_340():
    """P0340-FSI-XZ, FR-340: the verdict recomputed from the two ratios by R2; the page cites it."""
    report, fields = _front_matter(128)
    verdict = fields.get("xz_moment_verdict")
    assert verdict in {"confirmed", "refuted"}, (
        f"{report.name}: xz_moment_verdict is {verdict!r}, and FR-340 accepts confirmed or refuted"
    )
    try:
        moment_ratio = float(fields["xz_moment_ratio"])
        force_ratio = float(fields["xz_force_ratio"])
    except (KeyError, ValueError):
        pytest.fail(f"{report.name} does not state xz_moment_ratio and xz_force_ratio as numbers")
    assert _xz_verdict(moment_ratio, force_ratio) == verdict, (
        f"{report.name}: the ratios {moment_ratio} and {force_ratio} give "
        f"{_xz_verdict(moment_ratio, force_ratio)} by FR-340 R2, not {verdict}"
    )
    if verdict == "refuted":
        pytest.fail(
            f"{report.name} refutes the XZ moment: the warning every coupled run plans with, "
            "naming "
            "RPT-128, and its test (FR-340 R4) are src, owed to 0.35.0"
        )
    page = FSI_PAGE.read_text(encoding="utf-8")
    anchor = "moment column of an XZ cut"
    assert anchor in page, f"FR-340 R3: the FSI page has no XZ reading ({anchor!r})"
    xz = page.split(anchor, 1)[1][:1200]
    assert "RPT-128" in xz, "FR-340 R3: the FSI page's XZ reading cites RPT-128"


def test_a_planted_ratio_pair_flips_the_xz_verdict_fr_340():
    """P0340-FSI-XZ, FR-340 R2: the control of the criterion, on RPT-092's symmetric ratios."""
    assert _xz_verdict(0.43689, 0.98444) == "refuted"
    assert _xz_verdict(0.99, 0.98444) == "confirmed"
    assert _xz_verdict(1.01, 0.98444) == "confirmed"
