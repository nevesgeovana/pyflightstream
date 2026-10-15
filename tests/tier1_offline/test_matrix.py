"""Tier 1: run-matrix reader and convert-matrix (FR-10, FR-11).

The fixture mirrors the verified fifteen-column layout of the run matrix
(first data row shaped like the real POL 9001 case); names and
values are synthetic.

THE LAYOUT GREW BY ONE COLUMN on 2026-08-19 (PFS-2025.01, PFS-2025.12).
``WORKFLOW`` names the workflow type a row asks for, in a column of its
own rather than competing with the free ``KEY:VALUE`` pairs of
``VAR_NAMES_VALUES``. The predecessor width is kept in
``tests/tier1_offline/fixtures/pfs202512_matrix15.fs``, byte for byte as the fifteen-
column fixture stood before the change, because two of the three items
are about what happens to a file written under the old width: it is
RECOGNISED and refused naming the converter, and the converter adds the
cell and leaves every other byte alone.

The module reaches ``cases.matrix`` through ``matrix_mod`` as well as by
name, so a test measuring a constant or a converter that does not exist
yet fails on its ASSERTION rather than on the import.
"""

import importlib
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream import cases as cases_mod
from pyflightstream.cases import SimCase, load_campaign, point_tag
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.matrix import (
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
)
from pyflightstream.versions import resolve

FIXTURE = Path(__file__).parent / "fixtures" / "matrix.fs"
#: The same matrix at the width that preceded ``WORKFLOW``.
LEGACY_FIXTURE = Path(__file__).parent / "fixtures" / "pfs202512_matrix15.fs"
RECIPES = {"003": "recipes.steady_polar:build", "004": "recipes.beta_sweep:build"}


@pytest.mark.requirement("FR-10")
def test_read_matrix_parses_the_verified_layout():
    rows = read_matrix(FIXTURE)
    assert [row.pol for row in rows] == ["9001", "9002", "9004", "9005", "9006", "9008"]
    first = rows[0]
    assert first.aircraft == "TestWing"
    assert first.flight_condition == {"MACH": 0.1441, "REmi": 4.38}
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
    """The axis is the FLIGHT_CONDITION key that carries the word (FR-69).

    POL 9001 writes `ALPHA:sweep, BETA:0.0` and POL 9002 writes
    `BETA:sweep`, so the axis is read off the cell rather than off a
    column naming it a second time.
    """
    rows = read_matrix(FIXTURE)
    assert rows[0].sweep.type == "alpha"
    # The sideslip the row HOLDS rides along on every point, which is what
    # keeps the point tag of an upgraded row the one its manifest already
    # carries; the sweep is still one variable.
    assert list(rows[0].sweep.points()) == [
        {"alpha": -4.0, "beta": 0.0},
        {"alpha": 0.0, "beta": 0.0},
        {"alpha": 4.0, "beta": 0.0},
    ]
    assert rows[1].sweep.type == "beta"
    assert rows[1].sweep.values == [-6.0, 0.0, 6.0]


def test_the_held_angle_is_stated_once_and_still_reaches_every_point():
    """POL 9001: three incidences at one sideslip, and the run keeps its name.

    Until 0.15.0 this row was `AL/BE` over `-4.0,0.0,4.0/0.0` and the
    reader BROADCAST the single sideslip across the three points. The row
    STATES it once now, in the cell, beside every other quantity it
    holds; what the reader does with it is unchanged, because a point tag
    is run identity and `pyfs-matrix upgrade` may not rename a run.
    """
    row = read_matrix(FIXTURE)[0]
    assert row.sweep.type == "alpha"
    assert row.sweep.values == [-4.0, 0.0, 4.0]
    assert row.sweep.held == {"beta": 0.0}, "the sideslip is not held on the sweep"
    assert row.variables["BETA"] == 0.0, "the sideslip is not on the row either"


def test_a_beta_sweep_holds_its_incidence_the_same_way():
    """POL 9004: five sideslips at one incidence, and the mirror image.

    The two angles are symmetric in the format: whichever carries the
    word varies, and whichever carries a number is held on the row. A
    reader who learns one has learned the other.
    """
    row = next(row for row in read_matrix(FIXTURE) if row.pol == "9004")
    assert row.sweep.type == "beta"
    assert row.sweep.values == [-6.0, -3.0, 0.0, 3.0, 6.0]
    assert row.variables["ALPHA"] == 2.0
    # AND THE POINT, which is the half this case did not measure until a
    # QA pass scored it: dropping ALPHA from the held keys, so a beta
    # sweep loses its incidence and only a beta sweep, was caught by ONE
    # test in the whole suite, and it was not the one whose name says it
    # holds its incidence.
    assert row.sweep.held == {"alpha": 2.0}
    assert {point["alpha"] for point in row.sweep.points()} == {2.0}


def test_alpha_only_sweep_reads_every_value():
    sweep = next(row for row in read_matrix(FIXTURE) if row.pol == "9005").sweep
    assert sweep.type == "alpha"
    assert sweep.values == [-2.0, 0.0, 2.0, 4.0, 6.0]


def test_a_row_sweeps_one_angle_and_holds_the_other():
    """FR-69, and the cost the author's rule accepts: the paired sweep retires.

    This row was `AL/BE` over `-4.0,0.0,4.0/-2.0,0.0,2.0`, a DIAGONAL
    through the two angles, and it read as three paired points. A sweep is
    one variable now, so the fixture was REWRITTEN, by hand and
    deliberately, as a swept incidence at a held sideslip; two of its three
    points changed sideslip, which is a decision about a fixture built to
    exercise a retired feature and not a conversion. The converter does no
    such thing: it REFUSES a row that varies both angles, and that refusal
    has its own case below.

    The held angle is not lost. It is STATED once, in the cell, and it is
    still carried at every point, so the solver is told -2 degrees at each
    of the three and the run keeps the name its manifest holds.
    """
    row = next(row for row in read_matrix(FIXTURE) if row.pol == "9008")
    assert row.sweep.type == "alpha"
    assert [point["alpha"] for point in row.sweep.points()] == [-4.0, 0.0, 4.0]
    assert {point["beta"] for point in row.sweep.points()} == {-2.0}, (
        "the held sideslip is not carried at every point of the sweep"
    )
    assert row.variables["BETA"] == -2.0


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
        # Since 0.11.0 a LEGACY row carries its recipe code here, where
        # the FS_SCRIPT column put it (PFS-2029.04).
        "RECIPE": "003",
    }
    assert "\n" not in variables["NOTE"]


def _with_condition(tmp_path, replacement, *, values=None):
    """Rewrite POL 9001's FLIGHT_CONDITION cell, and its values, and return the file."""
    original = "MACH:0.1441, REmi:4.38, ALPHA:sweep, BETA:0.0"
    text = FIXTURE.read_text(encoding="utf-8")
    assert text.count(original) == 1, "the fixture no longer writes the cell this case edits"
    text = text.replace(original, replacement, 1)
    if values is not None:
        # A SWEEP OF A FLOW VARIABLE TAKES ITS OWN VALUES: the fixture's are
        # angles, and a Mach number of -4 is not a value a point can hold.
        row = next(line for line in text.splitlines() if line.startswith("9001"))
        assert row.count("-4.0,0.0,4.0") == 1, row
        text = text.replace(row, row.replace("-4.0,0.0,4.0", values, 1), 1)
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    return bad


def test_a_row_whose_condition_names_no_swept_variable_is_refused(tmp_path):
    """FR-69: SWEEP_VALUES with nothing to apply it to is a column nobody reads.

    The word IS the declaration since 0.15.0, so a cell carrying only
    numbers describes a single point, and the values beside it would be
    read by nothing. Refused where the row is read, rather than run as
    its first point.
    """
    bad = _with_condition(tmp_path, "MACH:0.1441, REmi:4.38, ALPHA:2.0, BETA:0.0")
    with pytest.raises(MatrixError) as caught:
        read_matrix(bad)
    message = str(caught.value)
    assert "9001" in message and "sweep" in message
    assert "ALPHA:sweep" in message, "the refusal shows no cell the user could write instead"


def test_a_row_that_sweeps_two_variables_is_refused_naming_both(tmp_path):
    """The author's rule of 2026-09-10: a sweep is applied to EXACTLY ONE variable.

    This is the paired AL/BE sweep arriving through the new spelling, and
    it is refused for the reason the column's removal rests on: two swept
    variables are two runs per point and the row states one.
    """
    bad = _with_condition(tmp_path, "MACH:0.1441, REmi:4.38, ALPHA:sweep, BETA:sweep")
    with pytest.raises(MatrixError) as caught:
        read_matrix(bad)
    message = str(caught.value)
    assert "9001" in message
    assert "ALPHA" in message and "BETA" in message, "the refusal names neither swept key"
    assert "one row per value" in message, "the refusal says no and not what to do instead"


def test_every_key_of_the_cell_can_be_varied_since_0_21_0(tmp_path):
    """The author's rule, implemented: ANY key that defines the condition sweeps.

    0.15.0 varied the two angles and the advance ratio and refused the rest as
    a not-yet naming the three. A row sweeping MACH was legal in the design and
    unimplemented in the code; it runs now, and a key the cell has no meaning
    for is still refused rather than accepted and ignored, which is how the
    advance-ratio sweep failed before 0.15.0.
    """
    good = _with_condition(tmp_path, "MACH:sweep, REmi:4.38, BETA:0.0", values="0.1,0.2,0.3")
    row = next(row for row in read_matrix(good) if row.sweep.type == "MACH")
    assert [point["MACH"] for point in row.sweep.points()] == list(row.sweep.values)
    assert row.flight_condition["REmi"] == 4.38, "the held keys stay on the row"

    bad = _with_condition(tmp_path, "MACH:0.2, WING_SPAN:sweep, BETA:0.0")
    with pytest.raises(MatrixError) as caught:
        read_matrix(bad)
    assert "WING_SPAN" in str(caught.value)


def test_a_swept_row_with_no_values_is_refused(tmp_path):
    """The other half of the pair: a declaration with nothing to apply."""
    text = FIXTURE.read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.startswith("9005"))
    emptied = line.replace("| -2.0,0.0,2.0,4.0,6.0 ", "|                      ")
    assert emptied != line, "the fixture no longer writes the values cell this case empties"
    bad = tmp_path / "matrix.fs"
    bad.write_text(text.replace(line, emptied, 1), encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(bad)
    message = str(caught.value)
    assert "9005" in message and "no values at all" in message
    assert "0.0,2.0,4.0" in message, "the refusal shows nothing the user could type"
    assert "only separators" in message, (
        "the refusal does not say why a cell that looks filled holds nothing"
    )


def test_header_deviation_is_refused(tmp_path):
    bad = tmp_path / "matrix.fs"
    bad.write_text("A | B | C\n1 | 2 | 3\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="verified 19-column layout"):
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
        MatrixError, match=r"data row 1 of .* holds 18 cells against the 19 verified"
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


def test_the_campaign_toml_sweep_on_the_page_is_the_one_the_loader_takes(tmp_path):
    """The worked example of `held`, executed so the page cannot rot.

    `docs/workspace-and-workflows.md` shows the inline table
    `pyfs-matrix convert` writes and a hand-written file may write. The
    same three lines are loaded here, and the run names they produce are
    asserted, because the names are the reason the field exists.
    """
    from pyflightstream.cases import SweepAxis

    sweep = SweepAxis(type="alpha", values=[-4.0, 0.0, 4.0], held={"beta": 0.0})
    assert [point_tag(point) for point in sweep.points()] == [
        "a-04.0_b+00.0",
        "a+00.0_b+00.0",
        "a+04.0_b+00.0",
    ]
    # And the two refusals the page promises beside it.
    # Pydantic wraps a validator's refusal, so the MESSAGE is asserted and
    # not the class: what a user reads is the sentence, and the sentence is
    # what a refactor drops.
    with pytest.raises(ValidationError, match=r"holds 'mach'.*not a point axis"):
        SweepAxis(type="alpha", values=[0.0], held={"mach": 0.2})
    with pytest.raises(ValidationError, match=r"varies alpha and also HOLDS it"):
        SweepAxis(type="alpha", values=[0.0], held={"alpha": 2.0})
    # A file written before the field existed loads unchanged.
    assert SweepAxis(type="alpha", values=[0.0]).held == {}


def test_the_swept_key_is_found_by_the_constant_the_page_names():
    """The worked example of `SWEEP_WORD`, executed so the page cannot rot.

    `docs/flight-conditions.md` names the constant for the script that
    WRITES a matrix rather than for the person who types one, and shows
    the two lines that ask a parsed condition which key it varies. Those
    lines are run here, and the tolerance the page promises beside them,
    which is what makes the constant the canonical spelling rather than
    the only accepted one.
    """
    from pyflightstream.cases.matrix import SWEEP_WORD

    condition = {"MACH": 0.2, "REmi": 5.5, "ALPHA": SWEEP_WORD, "BETA": 0.0}
    assert [key for key, value in condition.items() if value == SWEEP_WORD] == ["ALPHA"]
    # And a row a person typed in any casing parses to that same constant.
    # The three the page names, plus the canonical one.
    # THE LEADING SPACE IS BACK and is the one that exercises the key and
    # value split rather than the value fold; it went out of this list in
    # the FR-65 commit with no cause visible in the diff, and it still
    # passes (the QA lens, 2026-09-10).
    for typed in ("sweep", "SWEEP", "Sweep", "sweep ", " sweep "):
        parsed = matrix_mod._parse_flight_condition(
            f"MACH:0.2, REmi:5.5, ALPHA:{typed}, BETA:0.0", "9001"
        )
        assert parsed["ALPHA"] == SWEEP_WORD, typed
    # THE COUPLING THE PAGE SELLS RUNS BOTH WAYS. The reader compares a
    # folded cell against the constant, which recognises the constant's own
    # spelling only while the constant is itself lower case: respell it and
    # the reader stops accepting the word it stores, with the page still
    # promising the two cannot drift (the technical-writing lens).
    assert SWEEP_WORD == SWEEP_WORD.casefold()
    # AND WHAT A READER OF A MATRIX GETS, which is the other half of the
    # page and a different answer: the row says which axis, and the flow
    # state has the word taken out.
    row = read_matrix(FIXTURE)[0]
    assert row.sweep.type == "alpha"
    assert SWEEP_WORD not in row.flight_condition.values()


def test_every_held_key_is_a_key_the_release_can_sweep():
    """The containment `_HELD_POINT_KEYS` relies on, as a rule and not a coincidence.

    `_sweep_of_condition` indexes `_CONDITION_SWEEP_AXES` for every member
    of `_HELD_POINT_KEYS`, so a key added to the narrower list and not the
    wider one is a KeyError at read time rather than a refusal. The two
    lists are deliberately different sizes (the architecture lens,
    2026-09-10): the wider one can grow when a release learns to vary
    another key, and the narrower one may not grow at all, because only
    the two angles have ever named a point.
    """
    assert set(matrix_mod._HELD_POINT_KEYS) <= set(matrix_mod._CONDITION_SWEEP_AXES)
    assert set(matrix_mod._HELD_POINT_KEYS) == {"ALPHA", "BETA"}


def test_the_verified_layout_names_nineteen_columns_and_no_sweep_type():
    """FR-93, the run matrix carries nineteen columns, and FR-94, a row may name
    its configuration.

    The current layout, and both predecessors kept beside it.

    THE PREDECESSORS ARE ASSERTED AS LITERALS, which is a deliberate
    reversal. They used to be derived here as today's names minus the
    new one, and that was correct exactly while ONE column was the only
    difference between the layouts. When RE and MACH left at 0.9.0
    (PFS-2027.01), a derived predecessor would have silently followed
    the change and stopped describing any file that ever existed, so the
    recognition message would have vanished for the very files it was
    written for. A frozen historical layout is a literal or it is not
    frozen.
    """
    assert "WORKFLOW" in matrix_mod._COLUMNS
    assert "FLIGHT_CONDITION" in matrix_mod._COLUMNS
    assert "PPROC" in matrix_mod._COLUMNS
    assert len(matrix_mod._COLUMNS) == 19
    # SWEEP_TYPE is gone at 0.15.0 (FR-69): the flight-condition cell says
    # which variable varies by carrying the word `sweep` on it, and a
    # column naming the same fact is a second home for one fact. The
    # layout that carried it is frozen as a literal of its own, like the
    # three before it.
    assert "SWEEP_TYPE" not in matrix_mod._COLUMNS
    assert "SWEEP_VALUES" in matrix_mod._COLUMNS
    assert matrix_mod._LAYOUT_0_11_0[4] == "SWEEP_TYPE"
    assert len(matrix_mod._LAYOUT_0_11_0) == 14
    # FS_SCRIPT and ENTRY are gone at 0.11.0 (PFS-2029.04, PFS-2029.07.02),
    # and the layout that carried them is frozen as a literal of its own.
    assert "FS_SCRIPT" not in matrix_mod._COLUMNS
    assert "ENTRY" not in matrix_mod._COLUMNS
    assert matrix_mod._LAYOUT_0_9_0[8:10] == ("ENTRY", "FS_SCRIPT")
    assert len(matrix_mod._LAYOUT_0_9_0) == 15
    # RE and MACH are gone: a run states its flow condition in one place.
    assert "RE" not in matrix_mod._COLUMNS
    assert "MACH" not in matrix_mod._COLUMNS
    # Both predecessors still name them, because they describe files on
    # disk rather than the code's current opinion.
    assert matrix_mod._LEGACY_COLUMNS_15[3:5] == ("RE", "MACH")
    assert matrix_mod._LEGACY_COLUMNS_16[3:5] == ("RE", "MACH")
    assert len(matrix_mod._LEGACY_COLUMNS_15) == 15
    assert len(matrix_mod._LEGACY_COLUMNS_16) == 16
    # The 16 is the 15 plus WORKFLOW, which is the one relationship
    # between the two predecessors that IS still a derivation.
    assert matrix_mod._LEGACY_COLUMNS_15 == tuple(
        name for name in matrix_mod._LEGACY_COLUMNS_16 if name != "WORKFLOW"
    )
    # Stated position: the free KEY:VALUE cell stays last, because it is
    # the only cell whose width is not fixed by the format. The flight
    # condition takes the slot the two numeric columns had.
    assert matrix_mod._COLUMNS[-1] == "VAR_NAMES_VALUES"
    assert matrix_mod._COLUMNS.index("WORKFLOW") == 17
    assert matrix_mod._COLUMNS.index("FLIGHT_CONDITION") == 6


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
    assert "pyfs-workspace migrate" in message, (
        "the refusal names no converter, so it teaches nothing"
    )
    assert "WORKFLOW" in message


def test_the_legacy_refusal_is_a_different_message_from_the_foreign_one(tmp_path):
    """A migration and a break read differently, which is the whole item."""
    foreign = tmp_path / "matrix.fs"
    foreign.write_text("POL | ANGLE\n9001 | 4.0\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(foreign)
    message = str(caught.value)
    assert "does not match the verified 19-column layout" in message
    assert "pyfs-workspace migrate" not in message


def test_nothing_parses_after_the_fifteen_column_refusal():
    """Every consumer reaches rows through read_matrix, so all inherit it."""
    with pytest.raises(MatrixError, match="pyfs-workspace migrate"):
        to_campaign(
            LEGACY_FIXTURE,
            name="matrix",
            fs_version="26.120",
            fs_exe="C:/fs.exe",
            recipes=RECIPES,
        )
    with pytest.raises(MatrixError, match="pyfs-workspace migrate"):
        convert_matrix(
            LEGACY_FIXTURE,
            name="matrix",
            fs_version="26.120",
            fs_exe="C:/fs.exe",
            recipes=RECIPES,
        )


# --- the converter (PFS-2025.12.03) ----------------------------------------


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


def _normalized(data: bytes) -> bytes:
    """The fixture's bytes with line endings reduced to LF.

    Every case that cares about line endings builds the shape it wants
    from this, so none of them depends on how git checked the file out.
    """
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _line_ending_variants(tmp_path, fixture: str | None = None):
    """A CRLF copy, an LF copy, and one with no final terminator.

    CONSTRUCTED from a normalized base rather than read off the
    fixture, and that is the whole point of this function rather than a
    detail of it. Git rewrites line endings on checkout, so the
    committed fixture arrives CRLF on Windows and LF on Linux; reading
    its endings made this case a measurement of the checkout. The
    version that did fired its own non-vacuity assertion on every Linux
    runner and kept CI red while nine local groups were green.

    What is under test is that the width upgrade preserves bytes under
    each line-ending shape, which is a property of the converter and of
    nothing else.
    """
    source_file = (
        LEGACY_FIXTURE if fixture is None else Path(__file__).parent / "fixtures" / fixture
    )
    base = _normalized(source_file.read_bytes())
    crlf = base.replace(b"\n", b"\r\n")
    lf = base
    unterminated = lf.rstrip(b"\n")
    assert b"\r\n" in crlf and b"\r" not in lf, (
        "the two variants are not the two shapes this case exists to compare"
    )
    assert unterminated != lf, (
        "the fixture already ends without a terminator, so the third variant repeats "
        "the second and this case measures two shapes while naming three"
    )
    for label, data in (("crlf", crlf), ("lf", lf), ("unterminated", unterminated)):
        path = tmp_path / f"{label}.fs"
        path.write_bytes(data)
        yield label, path, data


def test_every_committed_fixture_is_pinned_against_line_ending_conversion():
    """The structural half of the two CRLF failures of 2026-08-19.

    Both were repaired by CONSTRUCTING the line-ending variants instead
    of reading them, which fixes two cases and not the class: the next
    fixture arrives unpinned and the next reader reads bytes.

    Two earlier versions of this guard were wrong and both are recorded,
    because each was the tempting answer. The first asserted that no
    fixture carries a carriage return and went red naming eleven that
    do. The second concluded from that red that the CRLF was captured
    solver output worth preserving, and pinned `-text` to preserve it.
    The measurement neither version took is `git ls-files --eol`: every
    fixture is `i/lf` in the INDEX, so nothing was being preserved and
    the CR was this machine's `core.autocrlf` writing it at checkout.

    What the pin gives, and what this asserts, is that the index holds LF
    and the checkout writes LF, so the file a case reads is the same file
    on every platform. Measured rather than assumed:
    `git ls-files --eol tests/tier1_offline/fixtures` reports `i/lf` for all seventeen.
    """
    import subprocess

    fixtures = Path(__file__).parent / "fixtures"
    files = sorted(path for path in fixtures.rglob("*") if path.is_file())
    assert len(files) > 10, (
        f"the fixture walk found {len(files)} files, and a walk that finds nothing "
        "passes this assertion for the wrong reason"
    )

    probe = subprocess.run(
        ["git", "check-attr", "binary", "text", "eol", "--", *[str(path) for path in files]],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
        env=os.environ.copy(),
    )
    assert probe.returncode == 0, f"git check-attr failed: {probe.stderr}"
    # BOTH attributes: `text: set` is what normalizes on the way IN, so a
    # CRLF cannot enter the index, and `eol: lf` is what writes LF on the
    # way out. The first version of this guard read `text` alone and
    # accepted `unset`, which is the `-text` rule it was written against
    # before a review pass measured that premise false.
    pinned: dict[str, set[str]] = {}
    for line in probe.stdout.splitlines():
        if not line:
            continue
        path_part, attribute, value = line.rsplit(": ", 2)
        pinned.setdefault(path_part, set()).add(f"{attribute}={value}")
    # A COMPRESSED recording (the 26.125 wake of PFS-2081.50, `*.xz binary`) is
    # bytes, not text: `binary` is its pin, since no conversion touches it either
    # way, and normalizing it as text would corrupt it. Only a compressed suffix
    # may take that pin, so a text fixture marked binary still fails here.
    unpinned = sorted(
        path_part
        for path_part, attributes in pinned.items()
        if not {"text=set", "eol=lf"} <= attributes
        and not (
            path_part.strip('"').endswith((".xz", ".gz", ".zip"))
            and {"binary=set", "text=unset"} <= attributes
        )
    )
    assert not unpinned, (
        "these fixtures are not pinned against line-ending conversion: "
        + ", ".join(unpinned)
        + ". Unpinned, a fixture is CRLF on Windows and LF on Linux, so a case that "
        "reads it as bytes measures the checkout rather than the file. Two did, and "
        "both failed on every Linux runner while nine local groups were green"
    )


def test_rewriting_a_code_cell_changes_no_line_ending(tmp_path):
    """The promise `rewrite_codes` makes, asserted in bytes.

    Its docstring says every other cell, separator, comment rule and line
    ending survives unchanged, and the case above says the same in its
    own words, and both assert through `splitlines()`, which throws the
    terminators away. A review pass rewrote every CRLF terminator to LF
    inside the function and watched 56 cases in this module and 213 in
    the modules covering its caller pass over it.

    The sibling `upgrade_matrix` has carried a byte comparison since it
    was written. The asymmetry was the finding.
    """
    from pyflightstream.cases.matrix import rewrite_codes

    # DRIVEN FROM THE SHARED HELPER, so this case gets the same three
    # shapes the sibling gets, including the one without a final
    # terminator. Built by hand it covered two, and a review pass measured
    # what the third would have caught: a rewrite that APPENDS a
    # terminator to a file that had none survives here and dies in the
    # sibling, which is driven from the helper.
    for label, source, original in _line_ending_variants(tmp_path, "matrix.fs"):
        rewritten, counts = rewrite_codes(source, {"REF": {"r003": "r009"}})
        assert counts.get("REF"), (
            f"{label}: the rewrite changed no cell, so this case would pass over a "
            "function that returned its input untouched"
        )

        assert rewritten.count(b"\r\n") == original.count(b"\r\n"), (
            f"{label}: the rewrite changed the number of CRLF terminators, which its "
            "own docstring promises survive unchanged"
        )
        assert rewritten.count(b"\n") == original.count(b"\n"), (
            f"{label}: the rewrite changed the number of lines"
        )
        # AND the bytes outside the rewritten cells are untouched, which
        # the two counts above do not say on their own.
        # THE PROMISE ITSELF, in one line: undo the rename and the file is
        # the file. Every other cell, separator, comment rule and line
        # ending survives, which is what the docstring says and what
        # splitlines() cannot check.
        assert rewritten != original, f"{label}: the rewrite changed nothing at all"
        assert rewritten.replace(b"r009", b"r003") == original, (
            f"{label}: undoing the rename does not give the original file back, so the "
            "rewrite changed a byte outside the code cells it was asked to edit"
        )
        assert rewritten.count(b"r009") == counts["REF"], (
            f"{label}: the file carries {rewritten.count(b'r009')} rewritten codes and "
            f"the call reported {counts['REF']}"
        )


def test_rewriting_a_code_cell_leaves_the_same_id_alone_outside_its_column(tmp_path):
    """Over-application of the rename is invisible to an inverse replace.

    `rewritten.replace(new, old) == original` undoes the corruption along
    with the rename, so a mutant applying the mapping to EVERY column
    passes it while corrupting cells and reporting zero rewrites. What
    sees it is a row whose non-code column carries the same bare id, and
    the committed fixture never has one, so this builds it.

    The clause under test is the rewrite's own: the code columns are the
    named ones and every other cell survives unchanged.
    """
    from pyflightstream.cases.matrix import rewrite_codes

    base = _normalized((Path(__file__).parent / "fixtures" / "matrix.fs").read_bytes())
    lines = base.split(b"\n")
    # The DESCRIPTION cell of the first data row carries the id the REF
    # column carries, so a rewrite that ignores its column edits it too.
    header, first = lines[0], lines[2]
    assert b"DESCRIPTION" in header, "the fixture header is not the layout this case reads"
    cells = first.split(b"|")
    description = 2
    # EXACTLY the bare id, padded to the original width. `_retag_cell`
    # rewrites a cell whose whole stripped content is the id, so a
    # description carrying the id among other words does not exercise the
    # over-application at all; the first version of this case did that and
    # the mutant walked through it.
    cells[description] = b" r003" + b" " * (len(cells[description]) - 5)
    lines[2] = b"|".join(cells)
    source = tmp_path / "collide.fs"
    source.write_bytes(b"\n".join(lines))

    rewritten, counts = rewrite_codes(source, {"REF": {"r003": "r009"}})
    assert counts["REF"], "the rewrite changed no code cell, so this case measures nothing"

    rewritten_description = rewritten.split(b"\n")[2].split(b"|")[description]
    assert rewritten_description == cells[description], (
        "the rewrite edited the DESCRIPTION cell, which is not a code column: it "
        f"reads {rewritten_description!r} where the source had {cells[description]!r}"
    )


def _one_row_at_the_0_11_0_layout(tmp_path, name, condition, code, values):
    """Write a one-row matrix at the layout the converter reads, and return it."""
    layout = matrix_mod._LAYOUT_0_11_0
    cells = dict.fromkeys(layout, "")
    cells.update(
        {
            "POL": "9100",
            "AIRCRAFT": "TestWing",
            "DESCRIPTION": "ROUND",
            "FLIGHT_CONDITION": condition,
            "SWEEP_TYPE": code,
            "SWEEP_VALUES": values,
            "REF": "r003",
            "SET": "s003",
            "PPROC": "p001",
            "FS_BUILD": "MANUAL",
            "HIDDEN": "0",
            "RUN": "1",
            "WORKFLOW": "LEGACY",
            "VAR_NAMES_VALUES": "FSM_FILE:wing_clean / RECIPE: 003",
        }
    )
    path = tmp_path / name
    path.write_text(
        "\n".join(
            [
                " | ".join(layout),
                "-" * 20,
                " | ".join(cells[key] for key in layout),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _unfolded(data: bytes) -> bytes:
    """Put RE and MACH back where FLIGHT_CONDITION now stands.

    The inverse of the 0.9.0 fold, so the byte comparison below can still
    say "and changed no OTHER byte" now that the conversion touches two
    places instead of one. It is deliberately dumb: it splits the cell on
    the two key names rather than parsing it, because a helper that used
    the parser would pass on any cell the parser accepts.
    """
    # THE INDEX COMES FROM THE LAYOUT THE DATA IS AT, not from the current
    # one. This helper is handed the TWO-STAGE result, which sits at the
    # sixteen-column layout with FLIGHT_CONDITION standing where RE was, so
    # the current layout's index is the wrong number the moment the two
    # stop agreeing. They agreed until 0.17.0 moved FLIGHT_CONDITION from
    # position 3 to position 6, and then this helper unfolded the wrong
    # cell: exactly the positional mistake the padding test below carries a
    # comment about.
    index = matrix_mod._LEGACY_COLUMNS_16.index("RE")
    rebuilt = []
    header_seen = False
    for line in data.splitlines(keepends=True):
        body, terminator = _peel(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            parts[index : index + 1] = [b" RE      ", b" MACH    "]
        else:
            cell = parts[index].strip()
            mach, _, remi = cell.partition(b", REmi:")
            mach = mach.replace(b"MACH:", b"", 1)
            parts[index : index + 1] = [b" " + remi + b"   ", b" " + mach + b"  "]
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


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
    assert "alpha" in message
    assert "FLIGHT_CONDITION" in message, (
        "the refusal still names the column the layout dropped at 0.15.0"
    )
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
            "| FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003\n9004",
            "| angle_sweep_deg:0.0,5.0 / FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt "
            "/ RECIPE: 003\n9004",
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


# --- one owner for the limit (PFS-2025.17, PFS-2025.17.02) ------------------


def test_the_matrix_reads_the_rotation_keys_the_cases_layer_owns():
    """The keys are IMPORTED, not respelled here.

    Two spellings is two limits, and the drift would be discovered by a
    user whose hand-written campaign.toml ran what their matrix refuses.
    Reading the constants off `pyflightstream.cases` is what makes this
    test move with the spelling instead of pinning a second copy of it.
    """
    assert matrix_mod.ROTATION_SWEEP_KEY is cases_mod.ROTATION_SWEEP_KEY
    assert matrix_mod.ROTATION_OFFSET_KEY is cases_mod.ROTATION_OFFSET_KEY
    source = Path(matrix_mod.__file__).read_text(encoding="utf-8")
    for quote in ('"', "'"):
        respelled = f"= {quote}{cases_mod.ROTATION_SWEEP_KEY}{quote}"
        assert respelled not in source, (
            f"the matrix module assigns the geometric sweep key its own value again "
            f"({respelled}); the limit has two owners and they can disagree"
        )


def test_the_row_the_matrix_refuses_is_refused_natively_too(tmp_path):
    """Both declaration doors refuse the same declaration.

    The matrix refusal is read off the file; this rebuilds the same row
    as a SimCase, which is the door a user who writes campaign.toml by
    hand comes through, and requires that it closes too.
    """
    text = _with_variable(FIXTURE.read_text(encoding="utf-8"), "angle_sweep_deg:0.0,5.0,10.0")
    bad = tmp_path / "matrix.fs"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(MatrixError, match="asks for two sweeps at once"):
        read_matrix(bad)
    # The same row without the extra variable, so the case below is built
    # from what the file really declares rather than from a hand-made echo.
    good = tmp_path / "clean.fs"
    good.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    row = read_matrix(good)[0]
    with pytest.raises(ValidationError, match="asks for two sweeps at once"):
        SimCase(
            sim_id=row.pol,
            aircraft=row.aircraft,
            sweep=row.sweep,
            recipe=RECIPES[row.script_code],
            variables={**row.variables, "angle_sweep_deg": "0.0,5.0,10.0"},
        )


# --- PFS-2009.08.03: row_number, and the row that names no build ------------


def test_every_row_carries_its_1_based_data_row_number():
    """Assigned before the RUN filter, so an inactive row does not shift it."""
    everything = read_matrix(FIXTURE, active_only=False)
    assert len(everything) == 8, (
        "the fixture stopped holding eight data rows, so the numbering below "
        "would be checked against a population it no longer has"
    )
    assert [row.row_number for row in everything] == [1, 2, 3, 4, 5, 6, 7, 8]
    # POL 9003 and 9007 are the two RUN = 0 rows, at positions 3 and 7. The
    # active view must keep the ORIGINAL numbers rather than renumber.
    active = read_matrix(FIXTURE)
    assert [row.pol for row in active if row.run == 1]
    assert [row.row_number for row in active] == [1, 2, 4, 5, 6, 8], (
        "the numbers were reassigned after the RUN filter, so a refusal would "
        "send a user to the wrong line of their file"
    )
    assert [row.pol for row in active] == ["9001", "9002", "9004", "9005", "9006", "9008"]


def test_the_number_counts_content_rows_and_not_physical_lines():
    """Blank lines and the dashed rule carry no cell and are not counted."""
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    assert any(set(line.strip()) <= {"-"} for line in lines if line.strip()), (
        "the fixture no longer carries a dashed rule, so this distinction is "
        "not being measured at all"
    )
    first = read_matrix(FIXTURE, active_only=False)[0]
    assert first.row_number == 1, (
        "the first data row is 1 even though the dashed rule sits above it"
    )


def _row_by_name(**cells) -> str:
    """One matrix row, its cells placed BY COLUMN NAME.

    A row written as a positional list is a row that moves to the wrong
    columns the next time the layout changes, silently, because the cell
    count can still be right. These fixtures learned that once already:
    the padding test carries a comment about an index that read the SET
    cell after RE and MACH folded at 0.9.0. Six columns arrived at 0.17.0
    and the positional lists broke again, so they are placed by name now.

    A column not named reads the dash that means the row states nothing.
    """
    return " | ".join(str(cells.get(name, "-")) for name in matrix_mod._COLUMNS)


def _silent_matrix(tmp_path, builds):
    """Write a matrix whose FS_BUILD cells are exactly ``builds``."""
    header = " | ".join(matrix_mod._COLUMNS)
    rows = [
        _row_by_name(
            POL=f"900{index}",
            HIDDEN="0",
            RUN="1",
            AIRCRAFT="TestWing",
            DESCRIPTION="ROW",
            FLIGHT_CONDITION="MACH:0.0890, REmi:3.10, ALPHA:sweep",
            SWEEP_VALUES="0.0",
            REF="r003",
            SET="s002",
            PPROC="p001",
            FS_BUILD=build,
            WORKFLOW="LEGACY",
            VAR_NAMES_VALUES="OUTPUTS: loads_{point}.txt / RECIPE: 003",
        )
        for index, build in enumerate(builds, start=1)
    ]
    path = tmp_path / "pfs20090803_matrix.fs"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_a_silent_row_with_no_default_is_refused_naming_the_rows(tmp_path):
    """Every silent row, by number and POL, and the option that fixes it."""
    path = _silent_matrix(tmp_path, ["26.120", "  ", ""])
    rows = read_matrix(path)
    assert [row.fs_build for row in rows] == ["26.120", "", ""], (
        "the fixture must hold one row that names a build and two that do not"
    )
    with pytest.raises(MatrixError) as caught:
        to_campaign(path, name="camp", fs_version="  ", fs_exe="fs.exe", recipes=RECIPES)
    message = str(caught.value)
    assert "row 2 (POL 9002)" in message and "row 3 (POL 9003)" in message, (
        f"every silent row must be named by number and POL: {message}"
    )
    assert "9001" not in message, (
        f"the row that names a build is not silent and must not be listed: {message}"
    )
    assert matrix_mod.DEFAULT_VERSION_OPTION in message
    # NEVER the version registry: that message talks about registered
    # versions and names nothing the user can act on here.
    assert "not registered" not in message


def test_a_blank_default_with_no_silent_row_is_accepted(tmp_path):
    """PFS-2029.01: every row names its build, so the default answers for nothing.

    Until 0.11.0 this arm refused, on the argument that a row added
    tomorrow with an empty cell would need the default; that row is
    refused by name the day it is added (the test above), which is the
    better answer than repeating on the command line a build every row
    already states.
    """
    path = _silent_matrix(tmp_path, ["26.120", "26.120"])
    assert all(row.fs_build for row in read_matrix(path)), (
        "this arm needs a matrix in which NO row is silent"
    )
    campaign = to_campaign(path, name="camp", fs_version="", fs_exe="fs.exe", recipes=RECIPES)
    assert [sim.sim_id for sim in campaign.sims] == ["9001", "9002"]
    assert [sim.variables["matrix_fs_build"] for sim in campaign.sims] == ["26.120", "26.120"]


def test_a_default_that_is_given_lets_a_silent_row_through(tmp_path):
    """The control: the refusal is about the ABSENT default, not the blank cell.

    A silent row with a default is the ordinary case and is exactly what
    the default exists for; refusing it would break every matrix that
    leaves FS_BUILD empty.
    """
    path = _silent_matrix(tmp_path, ["", ""])
    campaign = to_campaign(path, name="camp", fs_version="26.120", fs_exe="fs.exe", recipes=RECIPES)
    assert [sim.sim_id for sim in campaign.sims] == ["9001", "9002"]
    assert campaign.fs_version == "26.120"


# --- PFS-2009.03: rewriting the id cells, byte for byte ---------------------


def test_rewrite_codes_changes_only_the_named_cells(tmp_path):
    """Every other byte, separator, rule and line ending survives."""
    from pyflightstream.cases.matrix import rewrite_codes

    target = tmp_path / "pfs200903_rewrite.fs"
    target.write_bytes(FIXTURE.read_bytes())
    before = target.read_bytes()
    assert b"| r003 |" in before and b"| s003 |" in before, (
        "the fixture no longer spells the ids this rewrite is asked to change"
    )

    text, counts = rewrite_codes(target, {"REF": {"r003": "x003"}}, in_place=False)
    assert counts == {"REF": 7}, (
        f"the REF column carries seven r003 cells across the eight data rows; "
        f"the rewrite reported {counts}"
    )
    assert target.read_bytes() == before, "in_place=False wrote to the file"
    # Exactly the changed cells differ, and the line count does not move.
    assert text.count(b"x003") == 7
    assert len(text.splitlines()) == len(before.splitlines())
    changed = [
        (old, new)
        for old, new in zip(before.splitlines(), text.splitlines(), strict=True)
        if old != new
    ]
    assert len(changed) == 7
    for old, new in changed:
        assert old.replace(b"r003", b"x003") == new, (
            "a byte outside the REF cell moved: "
            f"{old.decode('utf-8', 'replace')} -> {new.decode('utf-8', 'replace')}"
        )


def test_rewrite_codes_touches_the_inactive_rows_too(tmp_path):
    """A RUN = 0 row is a row somebody switches on tomorrow."""
    from pyflightstream.cases.matrix import rewrite_codes

    target = tmp_path / "pfs200903_inactive.fs"
    target.write_bytes(FIXTURE.read_bytes())
    parked = [row for row in read_matrix(target, active_only=False) if row.run == 0]
    assert [row.pol for row in parked] == ["9003", "9007"], (
        "the fixture no longer carries an inactive row, so this is unmeasured"
    )
    rewrite_codes(target, {"PPROC": {"p001": "p900"}}, in_place=True)
    after = {row.pol: row.pproc_code for row in read_matrix(target, active_only=False)}
    assert after["9003"] == "p900" and after["9007"] == "p900"
    assert set(after.values()) == {"p900"}


def test_rewrite_codes_refuses_a_column_that_carries_no_library_id(tmp_path):
    from pyflightstream.cases.matrix import rewrite_codes

    target = tmp_path / "pfs200903_bad_column.fs"
    target.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(MatrixError, match="FS_BUILD"):
        rewrite_codes(target, {"FS_BUILD": {"MANUAL": "26.120"}})


def test_rewrite_codes_refuses_a_file_at_the_previous_layout(tmp_path):
    """A fifteen-column file is not silently rewritten at the wrong index."""
    from pyflightstream.cases.matrix import rewrite_codes

    target = tmp_path / "pfs200903_legacy.fs"
    target.write_bytes(LEGACY_FIXTURE.read_bytes())
    with pytest.raises(MatrixError, match="verified layout"):
        rewrite_codes(target, {"REF": {"r003": "x003"}})


def test_rewrite_codes_refuses_a_row_holding_the_wrong_number_of_cells(tmp_path):
    """The arm no fixture reaches by accident, reached on purpose."""
    from pyflightstream.cases.matrix import rewrite_codes

    target = tmp_path / "pfs200903_short_row.fs"
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    lines[2] = lines[2].rsplit("|", 1)[0]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="data row 1 of"):
        rewrite_codes(target, {"REF": {"r003": "x003"}})


def test_rewrite_codes_refuses_a_file_carrying_no_cell_separator(tmp_path):
    from pyflightstream.cases.matrix import rewrite_codes

    target = tmp_path / "pfs200903_no_cells.fs"
    target.write_text("not a matrix at all\n\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="no line carries a cell separator"):
        rewrite_codes(target, {"REF": {"r003": "x003"}})


def test_a_cell_with_no_padding_to_spare_grows_rather_than_losing_a_character(tmp_path):
    """The third arm of the padding rule: a wider column beats a wrong id."""
    from pyflightstream.cases.matrix import _COLUMNS, rewrite_codes

    target = tmp_path / "pfs200903_tight.fs"
    header = "|".join(_COLUMNS)
    by_name = {
        "POL": "9001",
        "HIDDEN": "0",
        "RUN": "1",
        "AIRCRAFT": "TestWing",
        "DESCRIPTION": "ROW",
        "FLIGHT_CONDITION": "MACH:0.0890, REmi:3.10, ALPHA:sweep",
        "SWEEP_VALUES": "0.0",
        "REF": "003",
        "SET": "s002",
        "PPROC": "p001",
        "FS_BUILD": "MANUAL",
        "WORKFLOW": "LEGACY",
        "VAR_NAMES_VALUES": "OUTPUTS: loads.txt / RECIPE: 003",
    }
    # NO PADDING ANYWHERE, which is the whole point of this fixture: the
    # REF cell has not one space to give up, so the rewrite must widen the
    # column rather than truncate the id.
    row = "|".join(by_name.get(name, "-") for name in _COLUMNS)
    target.write_text(header + "\n" + row + "\n", encoding="utf-8")
    text, counts = rewrite_codes(target, {"REF": {"003": "r003"}})
    assert counts == {"REF": 1}
    body = text.splitlines()[1].split(b"|")
    # Derived rather than written as 7: the index moved when RE and MACH
    # folded into FLIGHT_CONDITION at 0.9.0, and a literal position
    # silently read the SET cell instead and asserted against it.
    ref = _COLUMNS.index("REF")
    assert body[ref] == b"r003", (
        "a cell with no pad space to give up must GROW; truncating it would "
        f"invent an id: {body[ref]!r}"
    )
    assert len(body) == len(_COLUMNS)


def test_a_half_edited_matrix_is_told_how_to_recover_and_a_foreign_file_is_not(tmp_path):
    """The fallthrough refusal serves two populations, so it asks which.

    An API review found this was the only refusal in this module naming
    no converter, and that the reader most likely to reach it is the one
    who deleted RE and MACH by hand and never added FLIGHT_CONDITION.
    That reader is then stuck in a two-refusal loop: the reader says the
    header is wrong and the converter says the layout is not one it
    upgrades, and the sentence that rescues them, restore the original
    and convert THAT, is said nowhere.

    Adding it unconditionally broke a deliberate decision that a
    migration and a break read differently, which the test above pins.
    So the message asks which file it has: majority overlap with a
    layout this package knows means a half-done edit.
    """
    half_edited = list(matrix_mod._COLUMNS)
    half_edited[3] = "REmi"
    edited = tmp_path / "half_edited.fs"
    edited.write_text(" | ".join(half_edited) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(edited)
    message = str(caught.value)
    assert "pyfs-workspace migrate" in message
    assert "restore the original" in message
    # And it says WHERE the file differs rather than leaving two lists to diff by eye.
    assert "column 4" in message and "FLIGHT_CONDITION" in message and "REmi" in message

    # A file that is not a run matrix at all keeps the plain break, with
    # no converter named: sending it to one would be a false remedy.
    foreign = tmp_path / "foreign.fs"
    foreign.write_text("POL | ANGLE\n9001 | 4.0\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(foreign)
    assert "pyfs-workspace migrate" not in str(caught.value)


# --- PFS-2029.04 and PFS-2029.07.02: the 0.11.0 layout ------------------------

LAYOUT_0_9_0_FIXTURE = Path(__file__).parent / "fixtures" / "pfs202609_matrix15.fs"
LAYOUT_0_11_0_FIXTURE = Path(__file__).parent / "fixtures" / "pfs202609_matrix14.fs"


def test_the_0_11_0_layout_is_recognised_and_refused_naming_its_converter():
    """The layout EVERY 0.14.0 matrix on disk is written in (FR-69).

    It is the one a user upgrading to 0.15.0 actually meets, so it is
    recognised by its header and answered with the command that converts
    it. Before this case the file fell through to the generic break,
    which offers the half-edited remedy: restore the original and upgrade
    THAT. That sentence is false for a file nobody edited, and it sends a
    user looking for a backup they do not need.
    """
    with pytest.raises(MatrixError) as caught:
        read_matrix(LAYOUT_0_11_0_FIXTURE)
    message = str(caught.value)
    assert "predates 0.38.0" in message and "FLIGHT_CONDITION" in message
    assert "pyfs-workspace migrate" in message and "older package" in message
    assert "restore the original" not in message, (
        "a file at a known layout is told to restore a backup it does not need"
    )
    assert matrix_mod._LAYOUT_0_11_0[4] == "SWEEP_TYPE"


def test_the_0_11_0_refusal_reaches_the_planner_too():
    """The same refusal from `to_campaign`, so nothing parses past the header."""
    with pytest.raises(MatrixError, match="pyfs-workspace migrate"):
        to_campaign(
            LAYOUT_0_11_0_FIXTURE, name="m", fs_version="26.120", fs_exe="fs.exe", recipes=RECIPES
        )


def test_a_legacy_row_carries_its_recipe_code_as_a_variable():
    """A LEGACY row carries its recipe code as the RECIPE variable (PFS-2029.04).

    Read on the CURRENT fixture. It was read on the 0.11.0 one until
    0.15.0, when that layout stopped being readable at all, and the claim
    is about the variables cell rather than about a layout: measuring it
    on a file the reader refuses would measure the refusal.
    """
    rows = read_matrix(FIXTURE, active_only=False)
    assert all(row.workflow == "LEGACY" for row in rows)
    assert {row.script_code for row in rows} == {"003", "004"}
    assert all(row.variables[matrix_mod.RECIPE_VARIABLE] == row.script_code for row in rows)
    assert {row.pproc_code for row in rows} == {"p001"}


def test_the_0_9_0_layout_is_refused_naming_upgrade():
    """Recognised by its HEADER ROW, and named with the command that converts it."""
    with pytest.raises(MatrixError) as caught:
        read_matrix(LAYOUT_0_9_0_FIXTURE)
    message = str(caught.value)
    assert "predates 0.38.0" in message and "FLIGHT_CONDITION" in message
    assert "pyfs-workspace migrate" in message and "older package" in message


def test_the_fifteen_column_layout_is_refused_naming_upgrade():
    """The same refusal from `to_campaign`, so nothing parses past the header."""
    with pytest.raises(MatrixError, match="pyfs-workspace migrate"):
        to_campaign(
            LAYOUT_0_9_0_FIXTURE, name="m", fs_version="26.120", fs_exe="fs.exe", recipes=RECIPES
        )


def test_a_partly_edited_layout_is_refused_naming_upgrade(tmp_path):
    """A header that renamed ENTRY by hand and kept FS_SCRIPT is a half-done edit."""
    text = LAYOUT_0_9_0_FIXTURE.read_text(encoding="utf-8")
    half = tmp_path / "half.fs"
    half.write_text(text.replace("| ENTRY  |", "| PPROC  |", 1), encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(half)
    message = str(caught.value)
    assert "pyfs-workspace migrate" in message, message
    assert "15" in message and "19" in message


# --- PFS-2029.11.01: the variables cell reads a list of records ------------------------


def _cell(text):
    variables = matrix_mod._parse_variables(text)
    return variables, matrix_mod._parse_motions(variables, "9001")


def test_a_cell_reads_a_list_of_records():
    variables, motions = _cell(
        "VELOCITY: 30.0 / MOTIONS: {MOVING_BOUNDARIES: S,Blade1 / RPM_SIGN: -1 / ROTOR_AXIS: X}, "
        "{MOVING_BOUNDARIES: Blade2 / RPM_SIGN: 1 / ROTOR_AXIS: X / ROTOR_ORIGIN: ERP2}"
        " / OUTPUTS: l.txt"
    )
    assert variables == {"VELOCITY": "30.0", "OUTPUTS": "l.txt"}, (
        "the list leaked into the flat keys"
    )
    assert motions == [
        {"MOVING_BOUNDARIES": "S,Blade1", "RPM_SIGN": "-1", "ROTOR_AXIS": "X"},
        {"MOVING_BOUNDARIES": "Blade2", "RPM_SIGN": "1", "ROTOR_AXIS": "X", "ROTOR_ORIGIN": "ERP2"},
    ]
    # A cell without the key reads exactly as before, records empty.
    variables, motions = _cell("VELOCITY: 30.0 / RPM: 1200")
    assert variables == {"VELOCITY": "30.0", "RPM": "1200"} and motions == []


def test_a_malformed_record_list_is_refused_naming_the_cell():
    with pytest.raises(MatrixError, match="POL 9001.*MOTIONS.*brace"):
        _cell("MOTIONS: {MOVING_BOUNDARIES: S / RPM_SIGN: 1")
    with pytest.raises(MatrixError, match="POL 9001.*MOTIONS.*ROTOR_AXIS twice"):
        _cell("MOTIONS: {ROTOR_AXIS: X / ROTOR_AXIS: Y}")
    with pytest.raises(MatrixError, match="POL 9001.*MOTIONS.*flat key.*RPM_SIGN"):
        _cell("RPM_SIGN: 1 / MOTIONS: {ROTOR_AXIS: X}")
    # A brace on another key is that key's own: an output template keeps it.
    variables, motions = _cell("OUTPUTS: loads_{point}.txt / MOTIONS: {ROTOR_AXIS: X}")
    assert variables == {"OUTPUTS": "loads_{point}.txt"} and motions == [{"ROTOR_AXIS": "X"}]


def test_every_fixture_cell_parses_unchanged():
    """The fixture suite: no fixture cell carries a record list, and every one still reads."""
    for row in read_matrix(FIXTURE, active_only=False):
        assert row.motions == []
        assert "MOTIONS" not in row.variables


# --- a LEGACY row names its recipe in the cell (PFS-2031.11, GOAL-012) -----

_NAMED_RECIPE_HEADER = (
    "POL | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION "
    "| FLIGHT_CONDITION | SWEEP_VALUES | GEOMETRY | REF | SET | PPROC "
    "| SYMMETRY | SYMMETRY_LOADS | NCPUS | WALLTIME | FS_BUILD | WORKFLOW "
    "| VAR_NAMES_VALUES"
)


def a_recipe_named_in_the_cell(case, script):
    """A recipe a matrix row can reach by naming this module and function."""
    script.emit("NEW_SIMULATION")
    script.emit("CLOSE_FLIGHTSTREAM")


def _one_legacy_row(path, pol, recipe_cell):
    row = (
        f"{pol} | 0 | 1 | Wing | - | NAMED | MACH:0.2, REmi:3.1, ALPHA:sweep | 0.0 "
        f"| - | r003 | s002 | p001 | - | - | - | - | 26.120 | LEGACY "
        f"| RECIPE: {recipe_cell} / OUTPUTS: out.txt"
    )
    path.write_text(_NAMED_RECIPE_HEADER + "\n" + "-" * 20 + "\n" + row + "\n", encoding="utf-8")
    return path


def test_a_legacy_row_may_name_its_recipe_as_module_and_function_in_the_cell(tmp_path):
    """THE DEFECT: the tier-3 workspace's preparation rows name their recipe
    in the RECIPE cell as ``package.module:function``, which is the one form a
    recipe reference has always taken in Python, and ``to_campaign`` still
    demanded a command-line mapping for it, so a matrix that carried everything
    it needed could not be planned with ``pyfs-matrix plan matriz.fs`` alone,
    against FR-50's own sentence. A code that is a reference resolves as one; a
    bare code still needs its mapping (the test below this one).
    """
    reference = "tests.tier1_offline.test_matrix:a_recipe_named_in_the_cell"
    matrix = _one_legacy_row(tmp_path / "named.fs", 7101, reference)
    campaign = to_campaign(
        matrix, name="named", fs_version="26.120", fs_exe="C:/fs.exe", recipes={}
    )
    assert campaign.sims[0].recipe == reference


def test_a_legacy_row_with_a_bare_code_and_no_mapping_is_still_refused(tmp_path):
    """The other half of the same rule: a code that is not a reference is a
    code, and a code with no mapping is refused naming the remedy, exactly as
    before.
    """
    matrix = _one_legacy_row(tmp_path / "bare.fs", 7102, "003")
    with pytest.raises(MatrixError, match="has no recipe mapping"):
        to_campaign(matrix, name="bare", fs_version="26.120", fs_exe="C:/fs.exe", recipes={})


# --- PFS-2009.04: campaign.toml stores the resolved build identifier --------------


def test_campaign_toml_carries_the_resolved_build_identifier(tmp_path):
    """THE DEFECT: the campaign model resolved the version a user wrote and then
    stored what they wrote, so a matrix converted with the vendor name ``26.1``
    wrote ``26.1`` into campaign.toml, and the day a second build claimed that
    name (2026-08-04, when 26.101 was registered) the file was refused on a
    machine where nothing changed but the installed package. ``26.0`` is the
    alias that still names exactly one build, 26.000, so it is the one that
    converts today and would be refused tomorrow; the file holds the canonical
    identifier and the alias stays in the matrix, where it is read with today's
    registry every time.
    """
    assert resolve("26.0").canonical == "26.000", "this arm needs an alias naming ONE build"
    path = _silent_matrix(tmp_path, ["26.0", "26.0"])
    assert [row.fs_build for row in read_matrix(path)] == ["26.0", "26.0"]
    # No default: the first active row's build is the campaign version.
    text = convert_matrix(path, name="camp", fs_version="", fs_exe="fs.exe", recipes=RECIPES)
    assert 'fs_version = "26.000"' in text, text
    assert 'fs_version = "26.0"' not in text, text
    # A default typed as the alias resolves the same way.
    text = convert_matrix(path, name="camp", fs_version="26.0", fs_exe="fs.exe", recipes=RECIPES)
    assert 'fs_version = "26.000"' in text, text
    # The cell itself survives as typed: matrix_fs_build is the registry key
    # the row named, which a workspace resolves through its own build
    # registry (FR-11), and a registry key is not required to be a version.
    assert text.count('"matrix_fs_build" = "26.0"') == 2, text
    # What is written is what loads back, and it loads back canonical.
    (tmp_path / "campaign.toml").write_text(text, encoding="utf-8")
    assert load_campaign(tmp_path / "campaign.toml").fs_version == "26.000"
    # And the model itself is where the answer is kept: a campaign built
    # in Python from the alias records the build, not the name.
    campaign = to_campaign(path, name="camp", fs_version="26.0", fs_exe="fs.exe", recipes=RECIPES)
    assert campaign.fs_version == "26.000"


# --- PFS-2034.02: the variables cell reads a ROTATE list of records ---------------------


def _rotate_cell(text):
    variables = matrix_mod._parse_variables(text)
    return variables, matrix_mod._parse_rotations(variables, "9001")


def test_a_cell_reads_a_rotate_list_in_the_order_written():
    """PFS-2034.02, the author's grammar: ROTATE: {...}, {...} is two rotations, in input
    order, each with ANGLE, AXIS as frame-axis, FAMILIES and optionally AUX_FRAMES;
    the list leaves the flat keys, and a cell without it reads as before."""
    variables, rotations = _rotate_cell(
        "VELOCITY: 30.0 / ROTATE: "
        "{ANGLE: 3 / AXIS: NAC-Y / FAMILIES: Blade,S / AUX_FRAMES: ROTOR_MRP},"
        " {ANGLE: -2 / AXIS: NAC-Z / FAMILIES: Blade,S} / OUTPUTS: l.txt"
    )
    assert variables == {"VELOCITY": "30.0", "OUTPUTS": "l.txt"}
    assert rotations == [
        {"ANGLE": "3", "AXIS": "NAC-Y", "FAMILIES": "Blade,S", "AUX_FRAMES": "ROTOR_MRP"},
        {"ANGLE": "-2", "AXIS": "NAC-Z", "FAMILIES": "Blade,S"},
    ]
    variables, rotations = _rotate_cell("VELOCITY: 30.0")
    assert variables == {"VELOCITY": "30.0"} and rotations == []


@pytest.mark.parametrize(
    ("cell", "pattern"),
    [
        ("ROTATE: {ANGLE: 3 / AXIS: NAC-Y", "POL 9001.*ROTATE.*brace"),
        (
            "ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: S / ANGLE: 4}",
            "POL 9001.*ROTATE.*ANGLE twice",
        ),
        ("ROTATE: {AXIS: NAC-Y / FAMILIES: S}", "POL 9001.*ROTATE.*ANGLE"),
        ("ROTATE: {ANGLE: three / AXIS: NAC-Y / FAMILIES: S}", "POL 9001.*ROTATE.*three.*degrees"),
        ("ROTATE: {ANGLE: 3 / AXIS: NACY / FAMILIES: S}", "POL 9001.*ROTATE.*NACY.*frame-axis"),
        ("ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: S / PITCH: 1}", "POL 9001.*ROTATE.*PITCH"),
    ],
)
def test_a_malformed_rotate_record_is_refused_naming_the_cell(cell, pattern):
    with pytest.raises(MatrixError, match=pattern):
        _rotate_cell(cell)


def test_a_rotate_list_reaches_the_row_and_the_case(tmp_path):
    """The records travel MatrixRow.rotations to SimCase.rotations, beside motions."""
    text = FIXTURE.read_text(encoding="utf-8")
    header, rule, first = text.splitlines()[:3]
    cells = first.split("|")
    # The fixture row is LEGACY, whose recipe reads no rotation, and a
    # workflow row decides its own exports, so the cell is rewritten whole.
    cells[-2] = " steady "
    cells[-1] = " GEOMETRY: wb.fsm / ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: S}"
    path = tmp_path / "rotate.fs"
    path.write_text("\n".join([header, rule, "|".join(cells)]) + "\n", encoding="utf-8")
    row = read_matrix(path, active_only=False)[0]
    assert row.rotations == [{"ANGLE": "3", "AXIS": "NAC-Y", "FAMILIES": "S"}]
    assert "ROTATE" not in row.variables
    case = to_campaign(
        path, name="m", fs_version="26.123", fs_exe="C:/fs.exe", recipes=RECIPES
    ).sims[0]
    assert case.rotations == row.rotations


def test_a_rotate_list_on_a_legacy_row_is_refused_naming_the_pol(tmp_path):
    """PFS-2034.03: the recipe of a LEGACY row is the reader of its keys and reads no
    rotation, so the list on such a row is refused when the matrix is read."""
    text = FIXTURE.read_text(encoding="utf-8")
    header, rule, first = text.splitlines()[:3]
    cells = first.split("|")
    assert cells[-2].strip() == "LEGACY", cells[-2]
    cells[-1] = cells[-1].rstrip() + " / ROTATE: {ANGLE: 3 / AXIS: NAC-Y / FAMILIES: S}"
    path = tmp_path / "legacy.fs"
    path.write_text("\n".join([header, rule, "|".join(cells)]) + "\n", encoding="utf-8")
    with pytest.raises(MatrixError, match="POL 9001.*LEGACY.*ROTATE"):
        read_matrix(path, active_only=False)


@pytest.mark.parametrize("ran_in_datapoint", [False, True], ids=["P0400-WAKE-SIM", "P0400-WAKE-DP"])
def test_p0400_bgtests2_collect_files_the_wake_sidecar(tmp_path, ran_in_datapoint):
    """PFS-2081.50: collecting a surface also files and records its optional wake."""
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import PointName

    workspace = CampaignWorkspace(tmp_path / "campaign")
    sim = workspace.create_sim("9001")
    source = sim / "datapoints/DP-AL+040" if ran_in_datapoint else sim
    source.mkdir(parents=True, exist_ok=True)
    surface = source / "surface.vtk"
    surface.write_bytes(b"surface export")
    wake_bytes = (Path(__file__).parent / "fixtures/p0400_lita_solver_wake.vtk").read_bytes()
    (source / "surface_wakes.vtk").write_bytes(wake_bytes)
    collected = workspace.collect_outputs(
        "9001", [surface], datapoint=PointName("AL+040"), ran_in_datapoint=ran_in_datapoint
    )
    assert collected == [
        "datapoints/DP-AL+040/surface.vtk",
        "datapoints/DP-AL+040/surface_wakes.vtk",
    ]
    assert (sim / collected[1]).read_bytes() == wake_bytes
    assert not (sim / "surface_wakes.vtk").exists()
