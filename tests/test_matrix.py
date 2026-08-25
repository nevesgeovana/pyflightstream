"""Tier 1: run-matrix reader and convert-matrix (FR-10, FR-11).

The fixture mirrors the verified fifteen-column layout of the run matrix
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
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream import cases as cases_mod
from pyflightstream.cases import SimCase, load_campaign
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
    with pytest.raises(MatrixError, match="verified 15-column layout"):
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
        MatrixError, match=r"data row 1 of .* holds 14 cells against the 15 verified"
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


def test_the_verified_layout_names_fifteen_columns_including_the_workflow():
    """The current layout, and both predecessors kept beside it.

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
    assert len(matrix_mod._COLUMNS) == 15
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
    assert matrix_mod._COLUMNS.index("WORKFLOW") == 13
    assert matrix_mod._COLUMNS.index("FLIGHT_CONDITION") == 3


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
    assert "does not match the verified 15-column layout" in message
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
    `git ls-files --eol tests/fixtures` reports `i/lf` for all seventeen.
    """
    import subprocess

    fixtures = Path(__file__).parent / "fixtures"
    files = sorted(path for path in fixtures.rglob("*") if path.is_file())
    assert len(files) > 10, (
        f"the fixture walk found {len(files)} files, and a walk that finds nothing "
        "passes this assertion for the wrong reason"
    )

    probe = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", *[str(path) for path in files]],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
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
    unpinned = sorted(
        path_part
        for path_part, attributes in pinned.items()
        if not {"text=set", "eol=lf"} <= attributes
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


def _unfolded(data: bytes) -> bytes:
    """Put RE and MACH back where FLIGHT_CONDITION now stands.

    The inverse of the 0.9.0 fold, so the byte comparison below can still
    say "and changed no OTHER byte" now that the conversion touches two
    places instead of one. It is deliberately dumb: it splits the cell on
    the two key names rather than parsing it, because a helper that used
    the parser would pass on any cell the parser accepts.
    """
    index = matrix_mod._COLUMNS.index("FLIGHT_CONDITION")
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


def test_the_upgrade_changes_only_the_cells_the_conversion_touches(tmp_path):
    """Two conversions now, and the invariant is the same one.

    The upgrade used to insert exactly one cell, so removing that cell
    had to give the original back. Since 0.9.0 it ALSO folds RE and MACH
    into FLIGHT_CONDITION (PFS-2027.01), so the inverse of both is what
    must give the original back. The claim being tested is unchanged: a
    user diffing the converted file sees the conversion and nothing else.
    """
    upgrade_matrix = _upgrade()
    index = matrix_mod._COLUMNS.index("WORKFLOW")
    for label, path, original in _line_ending_variants(tmp_path):
        upgraded = upgrade_matrix(path)
        restored = _unfolded(_without_the_new_cell(upgraded, index))
        # THE STRIP IS SCOPED TO THE FOLDED REGION, and that scoping is
        # the point. An earlier version of this test stripped EVERY cell
        # before comparing, which is a band widened so a case could pass:
        # a converter that reflowed the padding of DESCRIPTION or
        # VAR_NAMES_VALUES would have passed it, while the refusal
        # message promises those are untouched. A V and V pass found it.
        # Only the two cells the fold rebuilds may differ in padding;
        # every other cell is compared BYTE FOR BYTE.
        folded = matrix_mod._LEGACY_COLUMNS_16.index("RE")
        restored_rows = [line.split(b"|") for line in restored.splitlines() if b"|" in line]
        original_rows = [line.split(b"|") for line in original.splitlines() if b"|" in line]
        assert len(restored_rows) == len(original_rows), label
        for restored_cells, original_cells in zip(restored_rows, original_rows, strict=True):
            assert len(restored_cells) == len(original_cells), label
            for position, (new_cell, old_cell) in enumerate(
                zip(restored_cells, original_cells, strict=True)
            ):
                if position in (folded, folded + 1):
                    assert new_cell.strip() == old_cell.strip(), f"{label} cell {position}"
                else:
                    assert new_cell == old_cell, (
                        f"{label}: cell {position} changed and the fold does not touch "
                        f"it: {old_cell!r} -> {new_cell!r}"
                    )
        # Line endings and every line carrying no cell survive exactly.
        assert restored.count(b"\r\n") == original.count(b"\r\n"), label
        assert len(restored.splitlines()) == len(original.splitlines()), label


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
    """One row short of a cell, and the refusal names which row.

    The split is on the NORMALIZED bytes. Splitting the fixture on
    ``\r\n`` as read returned one element on any checkout that gave
    LF, so this case raised IndexError on the line below rather than
    testing the converter, on every Linux runner.
    """
    lines = _normalized(LEGACY_FIXTURE.read_bytes()).split(b"\n")
    assert len(lines) > 3, f"the fixture parsed into {len(lines)} lines, which is not a matrix"
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


def _silent_matrix(tmp_path, builds):
    """Write a matrix whose FS_BUILD cells are exactly ``builds``."""
    header = " | ".join(matrix_mod._COLUMNS)
    rows = [
        " | ".join(
            [
                f"900{index}",
                "TestWing",
                "ROW",
                "MACH:0.0890, REmi:3.10",
                "AL",
                "0.0",
                "r003",
                "s002",
                "e001",
                "003",
                build,
                "0",
                "1",
                "LEGACY",
                "OUTPUTS: loads_{point}.txt",
            ]
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


def test_a_blank_default_with_no_silent_row_is_refused_naming_the_option(tmp_path):
    """The other arm, which would otherwise die in the version registry."""
    path = _silent_matrix(tmp_path, ["26.120", "26.120"])
    assert all(row.fs_build for row in read_matrix(path)), (
        "this arm needs a matrix in which NO row is silent"
    )
    with pytest.raises(MatrixError) as caught:
        to_campaign(path, name="camp", fs_version="", fs_exe="fs.exe", recipes=RECIPES)
    message = str(caught.value)
    assert matrix_mod.DEFAULT_VERSION_OPTION in message
    assert "not registered" not in message and "Known versions" not in message, (
        f"a blank default was reported by the version registry: {message}"
    )
    assert "POL" not in message, f"no row is silent, so the refusal must not name one: {message}"


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
    rewrite_codes(target, {"ENTRY": {"e001": "e900"}}, in_place=True)
    after = {row.pol: row.entry_code for row in read_matrix(target, active_only=False)}
    assert after["9003"] == "e900" and after["9007"] == "e900"
    assert set(after.values()) == {"e900"}


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
    row = "|".join(
        [
            "9001",
            "TestWing",
            "ROW",
            "MACH:0.0890, REmi:3.10",
            "AL",
            "0.0",
            "003",
            "s002",
            "e001",
            "003",
            "MANUAL",
            "0",
            "1",
            "LEGACY",
            "OUTPUTS: loads.txt",
        ]
    )
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
    assert "upgrade_matrix" in message
    assert "restore the original" in message
    # And it says WHERE the file differs rather than leaving two lists to diff by eye.
    assert "column 4" in message and "FLIGHT_CONDITION" in message and "REmi" in message

    # A file that is not a run matrix at all keeps the plain break, with
    # no converter named: sending it to one would be a false remedy.
    foreign = tmp_path / "foreign.fs"
    foreign.write_text("POL | ANGLE\n9001 | 4.0\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        read_matrix(foreign)
    assert "upgrade_matrix" not in str(caught.value)
