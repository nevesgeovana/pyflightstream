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
change in src/ (the export order, FR-338; the warning on every coupled run, FR-340), outside
the post-release allowlist; the first and fifth tests fail on them by design, naming the release
that owes the change.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream.results.loads import parse_loads
from tests.tier1_offline._workflow_docs import DEFINITION_DOCS

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "reports"
FSI_PAGE = REPO / "docs" / "fsi-workspace.md"
DEFINITIONS = DEFINITION_DOCS
FIX = Path(__file__).resolve().parent / "fixtures" / "rpt128"


def _front_matter(number: int) -> tuple[Path, dict[str, str]]:
    """Return a report and the ``key: value`` fields of its front matter, or fail naming it."""
    found = [FIX / "expected.txt"]
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
    """FR-340, fixed before the run: confirmed when the moment ratio is as close to 1."""
    return "confirmed" if abs(moment_ratio - 1.0) <= abs(force_ratio - 1.0) else "refuted"


def test_the_recorded_exports_give_the_cause_rpt128_states_fr_338():
    """P0340-FSI-CDO, FR-338: the cause recomputed from the five recorded loads exports."""
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
    """P0340-FSI-CDO, FR-338: every fixture is the export RPT-128's `CDo` table states.

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


def test_a_planted_ratio_pair_flips_the_xz_verdict_fr_340():
    """P0340-FSI-XZ, FR-340: the control of the criterion, on RPT-092's symmetric ratios."""
    assert _xz_verdict(0.43689, 0.98444) == "refuted"
    assert _xz_verdict(0.99, 0.98444) == "confirmed"
    assert _xz_verdict(1.01, 0.98444) == "confirmed"
    _, fields = _front_matter(128)
    assert (
        _xz_verdict(float(fields["xz_moment_ratio"]), float(fields["xz_force_ratio"]))
        == fields["xz_moment_verdict"]
    )
