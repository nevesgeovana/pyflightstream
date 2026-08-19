"""Tier 1: run-matrix reader and convert-matrix (FR-10, FR-11).

The fixture mirrors the verified sixteen-column layout of the run matrix
(first data row shaped like the real POL 9001 case); names and
values are synthetic.

THE LAYOUT GREW BY ONE COLUMN on 2026-08-19 (PFS-2025.01, PFS-2025.12).
``WORKFLOW`` names the workflow type a row asks for, in a column of its
own rather than competing with the free ``KEY:VALUE`` pairs of
``VAR_NAMES_VALUES``. The predecessor width is kept in
``tests/fixtures/pfs202512_matrix15.fs``, byte for byte as the fifteen-
column fixture stood before the change, because two of the three items
are about what happens to a file written under the old width: it is
RECOGNISED and refused naming the converter, and the converter adds the
cell and leaves every other byte alone.

The module reaches ``cases.matrix`` through ``matrix_mod`` as well as by
name, so a test measuring a constant or a converter that does not exist
yet fails on its ASSERTION rather than on the import.
"""

import importlib
from pathlib import Path

import pytest

from pyflightstream.cases import load_campaign
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.matrix import (
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
)

FIXTURE = Path(__file__).parent / "fixtures" / "matrix.fs"
#: The same matrix at the width that preceded ``WORKFLOW``.
LEGACY_FIXTURE = Path(__file__).parent / "fixtures" / "pfs202512_matrix15.fs"
RECIPES = {"003": "recipes.steady_polar:build", "004": "recipes.beta_sweep:build"}


def test_read_matrix_parses_the_verified_layout():
    rows = read_matrix(FIXTURE)
    assert [row.pol for row in rows] == ["9001", "9002", "9004", "9005", "9006", "9008"]
    first = rows[0]
    assert first.aircraft == "TestWing"
    assert first.re_millions == 4.38
    assert first.mach == 0.1441
    assert first.script_code == "003"
    assert first.fs_build == "MANUAL"
    assert first.hidden is False
    assert rows[1].hidden is True


def test_run_filtering_follows_the_run_flag():
    assert len(read_matrix(FIXTURE)) == 6
    everything = read_matrix(FIXTURE, active_only=False)
    assert [row.run for row in everything] == [1, 1, 0, 1, 1, 1, 0, 1]
    assert [row.pol for row in everything if row.run == 0] == ["9003", "9007"]


def test_sweeps_convert_to_native_axes():
    rows = read_matrix(FIXTURE)
    assert rows[0].sweep.type == "alpha_beta"
    assert list(rows[0].sweep.points()) == [
        {"alpha": -4.0, "beta": 0.0},
        {"alpha": 0.0, "beta": 0.0},
        {"alpha": 4.0, "beta": 0.0},
    ]
    assert rows[1].sweep.type == "beta"
    assert rows[1].sweep.values == [-6.0, 0.0, 6.0]


def test_single_beta_broadcasts_over_the_alpha_sweep():
    # POL 9001: three alphas against one beta value.
    sweep = read_matrix(FIXTURE)[0].sweep
    assert sweep.type == "alpha_beta"
    assert [point["beta"] for point in sweep.points()] == [0.0, 0.0, 0.0]


def test_single_alpha_broadcasts_over_the_beta_sweep():
    # POL 9004: one alpha against five beta values.
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9004").sweep
    assert sweep.type == "alpha_beta"
    points = list(sweep.points())
    assert [point["alpha"] for point in points] == [2.0] * 5
    assert [point["beta"] for point in points] == [-6.0, -3.0, 0.0, 3.0, 6.0]


def test_alpha_only_sweep_reads_every_value():
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9005").sweep
    assert sweep.type == "alpha"
    assert sweep.values == [-2.0, 0.0, 2.0, 4.0, 6.0]


def test_equal_length_al_be_lists_pair_up():
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9008").sweep
    assert sweep.type == "alpha_beta"
    assert list(sweep.points()) == [
        {"alpha": -4.0, "beta": -2.0},
        {"alpha": 0.0, "beta": 0.0},
        {"alpha": 4.0, "beta": 2.0},
    ]


def test_variables_parse_spaced_values_and_lowercase_keys():
    variables = read_matrix(FIXTURE)[0].variables
    assert variables["SYMMETRY_TYPE"] == "PERIODIC 6"
    assert variables["ADVANCE_RATIO"] == "1.7"
    assert variables["unsteady_delta_theta_deg"] == "10.0"


def test_full_variables_cell_keeps_every_pair_verbatim():
    # POL 9006 carries the fullest VAR_NAMES_VALUES cell of the fixture,
    # including an escaped newline (a literal backslash-n sequence) that
    # must survive verbatim: the reader never interprets values.
    variables = next(row for row in read_matrix(FIXTURE) if row.pol == "9006").variables
    assert variables == {
        "CONFIG": "NSX",
        "FSM_FILE": "wing_flapped",
        "NOTE": "first line\\nsecond line",
        "SYMMETRY_TYPE": "PERIODIC 6",
        "RESTART": "DISABLE",
        "TRIM_TARGET": "CL 0.45",
        "scale_inv": "1.0",
        # Declared since 2026-08-03: a row that names no outputs is
        # refused, because a campaign that collects nothing spends the
        # solver and then records the point as a failure.
        "OUTPUTS": "loads_{point}.txt",
    }
    assert "\n" not in variables["NOTE"]


def test_unverified_sweep_code_is_refused_with_evidence_language(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8").replace("| AL/BE ", "| J     ")
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(MatrixError, match="verified\\s+codes"):
        read_matrix(bad)


def test_header_deviation_is_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("A | B | C\n1 | 2 | 3\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="verified 16-column layout"):
        read_matrix(bad)


def test_empty_matrix_file_is_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("\n-----\n\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="no matrix content"):
        read_matrix(bad)


def test_truncated_row_is_refused_naming_the_row(tmp_path):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    # Drop the last cell of the first data row (POL 9001, file line 3).
    lines[2] = lines[2].rsplit("|", 1)[0].rstrip()
    bad = tmp_path / "matrix.fs"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(
        MatrixError, match=r"data row 1 of .* holds 15 cells against the 16 verified"
    ):
        read_matrix(bad)


def test_to_campaign_maps_codes_and_preserves_them():
    campaign = to_campaign(
        FIXTURE, name="matrix", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    case = campaign.sims[0]
    assert case.sim_id == "9001"
    assert case.reynolds == 4.38e6
    assert case.recipe == "recipes.steady_polar:build"
    assert case.variables["matrix_ref"] == "r003"
    assert case.variables["matrix_fs_build"] == "MANUAL"
    assert case.variables["matrix_hidden"] is False
    assert case.variables["SYMMETRY_TYPE"] == "PERIODIC 6"


def test_unmapped_script_code_is_refused():
    with pytest.raises(MatrixError, match="no recipe\\s+mapping"):
        to_campaign(FIXTURE, name="matrix", fs_version="26.120", fs_exe="C:/fs.exe", recipes={})


def test_convert_matrix_round_trips_through_load_campaign(tmp_path):
    text = convert_matrix(
        FIXTURE, name="matrix", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    path = tmp_path / "campaign.toml"
    path.write_text(text, encoding="utf-8")
    campaign = load_campaign(path)
    direct = to_campaign(
        FIXTURE, name="matrix", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    # DUMPS, NOT MODELS, since 2026-08-19. `Campaign` gained a private
    # `_source_path`, which `load_campaign` fills and `to_campaign` leaves
    # None, and pydantic compares private attributes in `__eq__`. So the
    # two campaigns are unequal while carrying identical DATA, and it is
    # the data that FR-11 calls lossless. Comparing the dumps keeps that
    # promise measured and stops this pin asserting where a campaign was
    # loaded from, which it never meant to.
    assert campaign.model_dump() == direct.model_dump()
    # The escaped newline survives the TOML round trip verbatim.
    full = next(sim for sim in campaign.sims if sim.sim_id == "9006")
    assert full.variables["NOTE"] == "first line\\nsecond line"


def test_earlier_conversions_with_legacy_keys_stay_loadable(tmp_path):
    # The changelog promise: campaign.toml files converted before the
    # matrix_* rename keep their legacy_* variable keys and load
    # verbatim; variables are free-keyed by design.
    path = tmp_path / "campaign.toml"
    path.write_text(
        '[campaign]\nname = "old"\nfs_version = "26.120"\nfs_exe = "C:/fs.exe"\n\n'
        '[[sim]]\nsim_id = "9001"\naircraft = "TestWing"\n'
        'sweep = {type = "alpha", values = [0.0]}\n'
        'recipe = "recipes.steady_polar:build"\n'
        "[sim.variables]\n"
        'legacy_ref = "003"\nlegacy_hidden = false\n',
        encoding="utf-8",
    )
    campaign = load_campaign(path)
    assert campaign.sims[0].variables["legacy_ref"] == "003"
    assert campaign.sims[0].variables["legacy_hidden"] is False


# --- the removed pyflightstream.cases.matrix_legacy shim --------------------


def test_the_matrix_legacy_shim_is_gone():
    """v0.4.0 removed it on the horizon its ledger entry recorded.

    The shim tests that used to live here asserted the re-exports and the
    stated removal version. They are replaced rather than deleted,
    because a removal promised in a released changelog is itself a
    promise: a partial revert that re-added the module would otherwise be
    caught by nothing.
    """
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pyflightstream.cases.matrix_legacy")
    # And the canonical names it forwarded to are still the ones it named.
    canonical = importlib.import_module("pyflightstream.cases.matrix")
    assert hasattr(canonical, "MatrixError")
    assert hasattr(canonical, "MatrixRow")


# --- the sixteenth column (PFS-2025.01, PFS-2025.12.01) ---------------------


def test_the_verified_layout_names_sixteen_columns_including_the_workflow():
    """One column, at a stated position, and the old width kept beside it.

    The two constants are asserted against EACH OTHER rather than each
    against a written-out list, so a column added to one and not the
    other cannot pass: the predecessor is exactly today's names minus
    the new one.
    """
    assert "WORKFLOW" in matrix_mod._COLUMNS
    assert len(matrix_mod._COLUMNS) == 16
    legacy = getattr(matrix_mod, "_LEGACY_COLUMNS_15", ())
    assert legacy == tuple(name for name in matrix_mod._COLUMNS if name != "WORKFLOW")
    # Stated position: the free KEY:VALUE cell stays last, because it is
    # the only cell whose width is not fixed by the format.
    assert matrix_mod._COLUMNS[-1] == "VAR_NAMES_VALUES"
    assert matrix_mod._COLUMNS.index("WORKFLOW") == 14


def test_the_workflow_column_parses_and_reaches_every_row():
    rows = read_matrix(FIXTURE, active_only=False)
    assert [getattr(row, "workflow", None) for row in rows] == ["LEGACY"] * 8


def test_the_workflow_reaches_the_case_losslessly():
    campaign = to_campaign(
        FIXTURE, name="matrix", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    assert campaign.sims[0].variables["matrix_workflow"] == "LEGACY"


def test_an_unknown_workflow_is_refused_naming_it_and_the_types_that_exist(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8").replace("| LEGACY   |", "| CFD_MAGIC|", 1)
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(bad)
    message = str(caught.value)
    assert "CFD_MAGIC" in message
    assert "9001" in message
    assert "LEGACY" in message


def test_an_unknown_workflow_is_refused_on_a_parked_row_too(tmp_path):
    """A refusal a user only meets after flipping RUN to 1 is one that waited."""
    text = FIXTURE.read_text(encoding="utf-8")
    parked = next(line for line in text.splitlines() if line.startswith("9003"))
    text = text.replace(parked, parked.replace("| LEGACY   |", "| CFD_MAGIC|"))
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(MatrixError, match=r"WORKFLOW value 'CFD_MAGIC' of POL 9003"):
        read_matrix(bad)  # active_only=True: POL 9003 carries RUN = 0


def test_a_registered_workflow_type_is_accepted_and_the_reader_asks_the_registry(tmp_path):
    """The accepted set is READ from the workflow table, never kept twice.

    A reader holding its own list refuses a value for naming a workflow
    that was registered last week, which is the same defect as accepting
    one that names nothing.
    """
    from pyflightstream.cases.workflows import workflow_names

    registered = workflow_names()
    assert registered, "the workflow registry is empty, so this case measures nothing"
    assert matrix_mod.workflow_types() == ("LEGACY", *registered)
    text = FIXTURE.read_text(encoding="utf-8").replace("| LEGACY   |", f"| {registered[0]:<9}|", 1)
    good = tmp_path / "matrix.fs"
    good.write_text(text, encoding="utf-8")
    assert read_matrix(good)[0].workflow == registered[0]


def test_the_width_in_a_refusal_is_counted_and_not_written_out(tmp_path):
    """The message a user reads cannot go stale behind the constant.

    Both refusals used to carry the literal 15 while the width was
    ``len(_COLUMNS)``, so the next column would have left a wrong number
    in the only place a user meets it.
    """
    source = Path(matrix_mod.__file__).read_text(encoding="utf-8")
    body = source.split("def read_matrix", 1)[1]
    assert "15-column" not in body
    assert "16-column" not in body, "the width is counted from _COLUMNS, never written out"


# --- a fifteen-column file is RECOGNISED (PFS-2025.12.02) -------------------


def test_a_fifteen_column_file_is_recognised_and_named_with_its_converter():
    with pytest.raises(MatrixError) as caught:
        read_matrix(LEGACY_FIXTURE)
    message = str(caught.value)
    assert str(LEGACY_FIXTURE) in message
    assert "upgrade_matrix" in message, "the refusal names no converter, so it teaches nothing"
    assert "WORKFLOW" in message


def test_the_legacy_refusal_is_a_different_message_from_the_foreign_one(tmp_path):
    """A migration and a break read differently, which is the whole item."""
    foreign = tmp_path / "matrix.fs"
    foreign.write_text("POL | ANGLE\n9001 | 4.0\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(foreign)
    message = str(caught.value)
    assert "does not match the verified 16-column layout" in message
    assert "upgrade_matrix" not in message


def test_nothing_parses_after_the_fifteen_column_refusal():
    """Every consumer reaches rows through read_matrix, so all inherit it."""
    with pytest.raises(MatrixError, match="upgrade_matrix"):
        to_campaign(
            LEGACY_FIXTURE,
            name="matrix",
            fs_version="26.120",
            fs_exe="C:/fs.exe",
            recipes=RECIPES,
        )
    with pytest.raises(MatrixError, match="upgrade_matrix"):
        convert_matrix(
            LEGACY_FIXTURE,
            name="matrix",
            fs_version="26.120",
            fs_exe="C:/fs.exe",
            recipes=RECIPES,
        )


# --- the converter (PFS-2025.12.03) ----------------------------------------


def _upgrade():
    converter = getattr(matrix_mod, "upgrade_matrix", None)
    assert converter is not None, (
        "cases.matrix offers no converter for the fifteen-column layout, so the "
        "refusal that names one is naming something a user cannot run"
    )
    return converter


def _peel(line: bytes) -> tuple[bytes, bytes]:
    for terminator in (b"\r\n", b"\n", b"\r"):
        if line.endswith(terminator):
            return line[: -len(terminator)], terminator
    return line, b""


def _without_the_new_cell(data: bytes, index: int) -> bytes:
    rebuilt = []
    for line in data.splitlines(keepends=True):
        body, terminator = _peel(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        del parts[index]
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


def _line_ending_variants(tmp_path):
    """The CRLF fixture, an LF copy, and one with no final terminator."""
    crlf = LEGACY_FIXTURE.read_bytes()
    assert b"\r\n" in crlf, "the committed fixture is CRLF; this case measures nothing without it"
    lf = crlf.replace(b"\r\n", b"\n")
    unterminated = lf.rstrip(b"\n")
    for label, data in (("crlf", crlf), ("lf", lf), ("unterminated", unterminated)):
        path = tmp_path / f"{label}.fs"
        path.write_bytes(data)
        yield label, path, data


def test_the_upgrade_adds_one_cell_and_changes_no_other_byte(tmp_path):
    upgrade_matrix = _upgrade()
    index = matrix_mod._COLUMNS.index("WORKFLOW")
    for label, path, original in _line_ending_variants(tmp_path):
        upgraded = upgrade_matrix(path)
        assert _without_the_new_cell(upgraded, index) == original, label


def test_the_upgraded_bytes_are_what_the_reader_accepts(tmp_path):
    """The clause the byte comparison alone cannot state.

    Removing the inserted cell and rejoining passes for ANY content, so
    a converter writing the label into the data rows, or an empty cell
    into the header, would satisfy it. What settles the two roles is
    that the reader takes the result.
    """
    target = tmp_path / "matrix.fs"
    target.write_bytes(_upgrade()(LEGACY_FIXTURE))
    rows = read_matrix(target, active_only=False)
    assert [row.pol for row in rows] == [
        "9001",
        "9002",
        "9003",
        "9004",
        "9005",
        "9006",
        "9007",
        "9008",
    ]
    assert {row.workflow for row in rows} == {matrix_mod.LEGACY_WORKFLOW}


def test_the_header_takes_the_label_and_the_rows_take_the_workflow():
    upgraded = _upgrade()(LEGACY_FIXTURE).decode("utf-8")
    index = matrix_mod._COLUMNS.index("WORKFLOW")
    piped = [line for line in upgraded.splitlines() if "|" in line]
    assert piped[0].split("|")[index].strip() == "WORKFLOW"
    assert {line.split("|")[index].strip() for line in piped[1:]} == {matrix_mod.LEGACY_WORKFLOW}


def test_the_inserted_cell_is_written_with_exactly_one_space_on_each_side():
    """The padding is a contract, and nothing else could measure it.

    The byte comparison passes for ANY padding, because removing the cell
    removes whatever it held, and the reader strips every cell before it
    looks. So a converter writing a lavishly padded cell would satisfy
    both and still hand the author a column that does not line up with
    the one beside it, in a file she reads by eye.
    """
    index = matrix_mod._COLUMNS.index("WORKFLOW")
    last = index == len(matrix_mod._COLUMNS) - 1
    trailing = b"" if last else b" "
    piped = [line for line in _upgrade()(LEGACY_FIXTURE).splitlines() if b"|" in line]
    assert piped[0].split(b"|")[index] == b" WORKFLOW" + trailing
    assert {line.split(b"|")[index] for line in piped[1:]} == {
        b" " + matrix_mod.LEGACY_WORKFLOW.encode() + trailing
    }


def test_the_upgrade_leaves_no_trailing_whitespace_on_any_line():
    """The pre-commit hook strips it, which would rewrite a committed matrix.

    The cell is written unpadded on its right when it is the LAST column
    and padded when it is not, so this holds however the stated position
    moves.
    """
    for line in _upgrade()(LEGACY_FIXTURE).splitlines():
        assert line == line.rstrip(), line


def test_a_file_with_no_cell_separator_at_all_is_refused(tmp_path):
    empty = tmp_path / "nothing.fs"
    empty.write_bytes(b"\r\n-----\r\n\r\n")
    with pytest.raises(MatrixError, match="no matrix content"):
        _upgrade()(empty)


def test_an_already_upgraded_matrix_is_returned_byte_for_byte():
    assert _upgrade()(FIXTURE) == FIXTURE.read_bytes()


def test_a_file_that_is_not_a_run_matrix_is_refused_by_the_converter(tmp_path):
    """Refused on its HEADER, and the message has to say so.

    Matching the file name alone was not enough: with the header check
    removed, this file reached the row check instead and was refused
    there, naming the same path. Both refusals are correct in isolation
    and only one of them is this one.
    """
    foreign = tmp_path / "notamatrix.fs"
    foreign.write_bytes(b"A | B | C\r\n1 | 2 | 3\r\n")
    with pytest.raises(MatrixError) as caught:
        _upgrade()(foreign)
    message = str(caught.value)
    assert "notamatrix.fs" in message
    assert "its header names A, B, C" in message


def test_a_row_of_the_wrong_width_is_refused_by_the_converter_naming_the_row(tmp_path):
    lines = LEGACY_FIXTURE.read_bytes().split(b"\r\n")
    lines[2] = lines[2].rsplit(b"|", 1)[0]
    ragged = tmp_path / "ragged.fs"
    ragged.write_bytes(b"\r\n".join(lines))
    with pytest.raises(MatrixError) as caught:
        _upgrade()(ragged)
    message = str(caught.value)
    assert "data row 1 of" in message
    assert "ragged.fs" in message
    assert "holds 14 cells" in message


def test_in_place_rewrites_the_source_and_returns_the_same_bytes(tmp_path):
    target = tmp_path / "matrix.fs"
    target.write_bytes(LEGACY_FIXTURE.read_bytes())
    returned = _upgrade()(target, in_place=True)
    assert target.read_bytes() == returned
    assert len(read_matrix(target, active_only=False)) == 8
    # and the source file is untouched when nothing asks for the write
    other = tmp_path / "second.fs"
    other.write_bytes(LEGACY_FIXTURE.read_bytes())
    _upgrade()(other)
    assert other.read_bytes() == LEGACY_FIXTURE.read_bytes()


# --- two sweeps in one row (PFS-2025.17.01) --------------------------------


def _with_variable(text: str, pair: str) -> str:
    """Put one KEY:VALUE pair at the head of POL 9001's variables cell."""
    return text.replace("| CONFIG:NSX   /", f"| {pair} / CONFIG:NSX   /", 1)


def test_an_aerodynamic_and_a_geometric_sweep_together_are_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text(
        _with_variable(FIXTURE.read_text(encoding="utf-8"), "angle_sweep_deg:0.0,5.0,10.0"),
        encoding="utf-8",
    )
    with pytest.raises(MatrixError) as caught:
        read_matrix(bad)
    message = str(caught.value)
    assert "9001" in message
    assert "alpha_beta" in message
    assert "3" in message
    assert "0.0,5.0,10.0" in message
    assert "angle_deg" in message, "the refusal names no fixed-offset form, so it only says no"


def test_two_sweeps_are_refused_on_a_parked_row_too(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8")
    parked = next(line for line in text.splitlines() if line.startswith("9007"))
    # POL 9007 is RUN = 0 and carries a three-point beta sweep once widened.
    widened = parked.replace("| 0.0  ", "| -3.0,0.0,3.0").replace(
        "| FSM_FILE:wing_clean", "| angle_sweep_deg:0.0,5.0 / FSM_FILE:wing_clean"
    )
    bad = tmp_path / "matrix.fs"
    bad.write_text(text.replace(parked, widened), encoding="utf-8")
    with pytest.raises(MatrixError, match=r"POL 9007 asks for two sweeps at once"):
        read_matrix(bad)


def test_a_single_valued_rotation_beside_a_sweep_runs_normally(tmp_path):
    good = tmp_path / "matrix.fs"
    good.write_text(
        _with_variable(FIXTURE.read_text(encoding="utf-8"), "angle_sweep_deg:7.5"),
        encoding="utf-8",
    )
    assert read_matrix(good)[0].variables["angle_sweep_deg"] == "7.5"


def test_a_fixed_offset_beside_a_sweep_runs_normally(tmp_path):
    good = tmp_path / "matrix.fs"
    good.write_text(
        _with_variable(FIXTURE.read_text(encoding="utf-8"), "angle_deg:7.5"),
        encoding="utf-8",
    )
    assert read_matrix(good)[0].variables["angle_deg"] == "7.5"


def test_a_rotation_sweep_on_a_single_point_row_runs_normally(tmp_path):
    # POL 9003 holds one alpha value, so only one sweep is being asked for.
    good = tmp_path / "matrix.fs"
    good.write_text(
        FIXTURE.read_text(encoding="utf-8").replace(
            "| FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt\n9004",
            "| angle_sweep_deg:0.0,5.0 / FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt\n9004",
            1,
        ),
        encoding="utf-8",
    )
    rows = read_matrix(good, active_only=False)
    assert rows[2].variables["angle_sweep_deg"] == "0.0,5.0"


def test_the_rotation_keys_are_read_whatever_their_case(tmp_path):
    """PFS-2025.14 owns the spelling; this refusal must not depend on it."""
    bad = tmp_path / "matrix.fs"
    bad.write_text(
        _with_variable(FIXTURE.read_text(encoding="utf-8"), "ANGLE_SWEEP_DEG:0.0,5.0"),
        encoding="utf-8",
    )
    with pytest.raises(MatrixError, match="angle_deg"):
        read_matrix(bad)
