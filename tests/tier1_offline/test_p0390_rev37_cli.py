"""P0390-REV37 (NFR-45 R2): the behaviour findings of the 0.37.0 release review.

R37-01 the help constant beside ``listed_sims``; R37-02 the sweep refusal names the
column that differs; R37-03 and R37-04 a quoted ``--sims "2006 2007"`` is two ids in
mark-converged, mark-failed, rebuild and delete-sims, driven through the command
line; R37-09 the mark-converged help names both shapes. (R37-08 is the strengthened
assertion of ``test_p0370_s1_sims_shapes.py``.)
"""

from __future__ import annotations

import pytest

from pyflightstream.results import MalformedOutputError
from pyflightstream.results.exports import _SIMCENTER_SWEEP_COLUMNS, SWEEP_COLUMNS, sweep_columns
from pyflightstream.run import _alias
from pyflightstream.workspace import ledger
from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace, pyfs

REASON = "read by hand"
SIMS = ("7001", "7002", "7003")


def _help(command, tmp_path, capsys):
    capsys.readouterr()
    with pytest.raises(SystemExit):
        pyfs([command, "--help"], tmp_path, capsys)
    return " ".join(capsys.readouterr().out.split())


def test_the_sims_help_constant_lives_beside_listed_sims(tmp_path, capsys):
    """P0390-REV37 (NFR-45 R2, R37-01): defined in workspace.ledger, not in run._alias."""
    assert ledger.SIMS_IDS_HELP and "SIMS_IDS_HELP" in ledger.__all__
    assert not hasattr(_alias, "SIMS_IDS_HELP")
    for command in ("mark-failed", "rebuild", "delete-sims", "mark-converged"):
        assert ledger.SIMS_IDS_HELP in _help(command, tmp_path, capsys), command


def _header(**renamed: str) -> str:
    columns = list(SWEEP_COLUMNS)
    for name, new in renamed.items():
        columns[columns.index(name)] = new
    return ", ".join(columns)


def test_the_sweep_refusal_names_the_column_that_differs_in_each_layout():
    """P0390-REV37 (NFR-45 R2, R37-02): position, expected, found, per layout."""
    with pytest.raises(MalformedOutputError) as refused:
        sweep_columns(_header(CL="CLx"), what="sweeper spreadsheet")
    said = str(refused.value)
    assert said.count("column 7 expected 'CL', found 'CLx'") == 2, said
    assert "layout 1:" in said and "layout 2:" in said, said
    # A rename in the CDo slot differs at column 9 of the first layout but at column 8
    # (CDp expected, CDi found) of the second: each layout names its own first difference.
    assert _SIMCENTER_SWEEP_COLUMNS[7] == "CDp"
    with pytest.raises(MalformedOutputError) as refused:
        sweep_columns(_header(CDo="CDz"), what="sweeper spreadsheet")
    said = str(refused.value)
    assert "layout 1: column 9 expected 'CDo', found 'CDz'" in said, said
    assert "layout 2: column 8 expected 'CDp', found 'CDi'" in said, said


def test_a_header_that_is_a_prefix_is_refused_with_its_length():
    """P0390-REV37 (NFR-45 R2, R37-02): a header cut short names the counts, not a column."""
    with pytest.raises(MalformedOutputError) as refused:
        sweep_columns(", ".join(SWEEP_COLUMNS[:10]), what="sweeper spreadsheet")
    assert "agree as far as they go, and the header has 10 where 12 are expected" in str(
        refused.value
    )


@pytest.mark.parametrize("value", ["7001 7002", "[7001,7002]", "7001\t7002", "7001, 7002"])
def test_listed_sims_reads_blank_and_comma_forms_alike(value):
    """P0390-REV37 (NFR-45 R2, R37-04): a blank separates ids as a comma does."""
    assert ledger.listed_sims(value) == ["7001", "7002"]
    assert ledger.listed_sims("7001") == ["7001"]


def _body(result):
    """The exit code and what the command said before its banner (which echoes the log name)."""
    code, said = result
    return code, said.split("pyfs-matrix ", 1)[0]


def _named(text: str) -> list[str]:
    return [sim for sim in SIMS if sim in text]


@pytest.mark.parametrize("value", ["7001 7002", "[7001,7002]", "7001\t7002"])
def test_mark_converged_reads_a_quoted_value_as_two_ids_through_the_cli(value, tmp_path, capsys):
    """P0390-REV37 (NFR-45 R2, R37-03): quoted, bracket and tab values give the two-id preview."""
    workspace = grouped_workspace(tmp_path / "ws", mode="alone", logs=False, sims=SIMS)
    base = ["mark-converged", "--reason", REASON]
    want = pyfs([*base, "--sims", "7001,7002"], workspace.root, capsys)
    got = pyfs([*base, "--sims", value], workspace.root, capsys)
    assert _body(got) == _body(want) and got[0] == 0, got
    assert _named(_body(got)[1]) == ["7001", "7002"], got


def test_mark_converged_help_names_the_quoted_value_and_the_mixed_shape(tmp_path, capsys):
    """P0390-REV37 (NFR-45 R2, R37-09): the help names one quoted value and the mixed shape."""
    text = _help("mark-converged", tmp_path, capsys)
    assert "reads as two ids" in text and "'2006 2007'" in text, text
    assert text.count("quoted value") == 1, text
    assert "also as separate words (2006 2007) or a mix (2006 2007,2008)" in text, text


@pytest.mark.parametrize(
    "command",
    [["mark-failed", "--reason", REASON, "--sims"], ["rebuild", "--sims"]],
)
@pytest.mark.parametrize("value", ["7001 7002", "[7001, 7002]", "7001\t7002"])
def test_a_quoted_sims_value_is_two_ids_in_mark_failed_and_rebuild(
    command, value, tmp_path, capsys
):
    """P0390-REV37 (NFR-45 R2, R37-04): the quoted value gives what the comma form gives."""
    workspace = grouped_workspace(tmp_path / "ws", mode="alone", logs=False, sims=SIMS)
    want = pyfs([*command, "7001,7002"], workspace.root, capsys)
    got = pyfs([*command, value], workspace.root, capsys)
    assert want[0] == 0 and _body(got) == _body(want), (want, got)
    assert _named(_body(got)[1]) == ["7001", "7002"], got


@pytest.mark.parametrize("value", ["7001,7002", "[7001,7002]", "7001, 7002"])
def test_every_form_accepted_before_still_reads_the_same_ids(value, tmp_path, capsys):
    """P0390-REV37 (NFR-45 R2, R37-04): the comma and bracket forms of 0.38.0 keep their result."""
    workspace = grouped_workspace(tmp_path / "ws", mode="alone", logs=False, sims=SIMS)
    code, said = pyfs(["delete-sims", value], workspace.root, capsys)
    assert code == 0, said
    assert _named(_body((code, said))[1]) == ["7001", "7002"], said


def test_delete_sims_reads_a_quoted_value_as_two_ids(tmp_path, capsys):
    """P0390-REV37 (NFR-45 R2, R37-04): ``delete-sims "7001 7002"`` previews both, not 70017002."""
    workspace = grouped_workspace(tmp_path / "ws", mode="alone", logs=False, sims=SIMS)
    want = pyfs(["delete-sims", "7001,7002"], workspace.root, capsys)
    got = pyfs(["delete-sims", "7001 7002"], workspace.root, capsys)
    assert want[0] == 0 and _body(got) == _body(want), (want, got)
    assert "70017002" not in got[1] and _named(_body(got)[1]) == ["7001", "7002"], got


def test_a_single_layout_refusal_names_the_first_difference_without_a_layout_number():
    """P0390-REV37 (NFR-45 R2, R37-02): one expected layout says "The first difference"."""
    from pyflightstream.results.exports import _pinned_columns

    layout = ("A", "B", "C")
    with pytest.raises(MalformedOutputError) as refused:
        _pinned_columns("A, X, C", layout, what="demo")
    said = str(refused.value)
    assert "The first difference: column 2 expected 'B', found 'X'" in said, said
    assert "Against each" not in said and "layout 1" not in said, said
    with pytest.raises(MalformedOutputError) as refused:
        _pinned_columns("A, X, C", layout, ("A", "Y", "C"), what="demo")
    said = str(refused.value)
    assert "Against each, layout 1: column 2 expected 'B'" in said and "layout 2:" in said, said
