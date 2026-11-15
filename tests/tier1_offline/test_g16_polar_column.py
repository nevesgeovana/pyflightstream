"""G16 (0.27.0): the first column of every table the post writes is the polar, and no line
precedes the header.

THE RULE, as the definition of record states it once
(`docs/post-processing-definitions.md`, *What every product states*): every table under
``post/<matrix>/``, the additional post's included, opens with the polar its row comes from,
under the name the run matrix gives its polar column, one value per row: the POL of the point
that row comes from. A table whose rows mix polars, the campaign sweep, carries each row's own.
A title line before the header becomes a column after `POL`: the rotor table's alias is
`ROTOR`. Every other column keeps its name and its order after them.

WHY IT IS A RULE ABOUT EVERY TABLE AND IS TESTED AS ONE. A reader filters data by polar in
their own scripts, reading every file of a campaign into one frame; a table that does not carry the
polar, or that opens with a line no CSV reader takes as a header, breaks that for the whole
campaign. So this module does not ask the writers one by one. It posts representative recorded
campaigns END TO END, walks every ``*.csv`` the post folder holds, and asks each one the same
three questions: is its first line the header, is that header's first column the polar, and is
each row's polar the polar of the point it comes from, which ``products.json`` and the run
records say independently of the table. The campaigns are the fixtures other modules already
post, so each family is written by the stage that writes it for a user; each campaign states the
families it must produce, so a fixture that stops producing one fails here rather than letting
the walk pass over fewer tables.

TWO POLARS IN THE STEADY CAMPAIGN, so a writer that put one simulation's polar into another's
table, or one constant into every row of the sweep, cannot pass.

AND EVERY LINE SPLITS ON ',' TO THE HEADER'S COUNT. The same reader loads these tables with
`numpy.genfromtxt`, which honours no CSV quoting: a cell holding a comma, written quoted, was
counted as two columns or more. The matrix cells the super content echoes did exactly that
(`SWEEP_VALUES`, `FLIGHT_CONDITION`). So no cell holds a comma or a double quote: a comma is
written `;`, a double quote a single one, and nothing is quoted.

AND THE POLAR IS STATED ONCE, AS `POL`. The steady polar and its super file carried the same
simulation id a second time, under `POLAR`, the name 0.26.0 gave it. That column is gone from
every table: the walk refuses any header that still names it, the fixed-width super file
included, and a table written before 0.27.0, which names the polar `POLAR` and has no `POL`,
still reads into the super file's union as the polar.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from pyflightstream.cases import PprocSpec
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.post.products import (
    plots_table_series,
    read_csv_table,
    write_campaign_products,
)
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace

#: The polar column, spelled as a matrix file writes it rather than imported, so a tree that
#: names it otherwise fails on the tables and not on an import.
POL = "POL"

#: The name 0.26.0 gave the polar in the steady polar table and its super file. No table the post
#: writes states it since 0.27.0: `POL` alone carries the polar.
RETIRED = "POLAR"

#: The header of a rotor table as 0.26.0 wrote it on its SECOND line, after the alias alone
#: on the first. Every one of these names must survive, in this order, after `POL, ROTOR`.
ROTOR_COLUMNS_BEFORE = (
    "ALPHA,BETA,MACH,RE,VINF,VREF,ALT,RHO,TEMP,MU,J,J_CLOCK,RPM_CLOCK,SREF,CREF,BREF,"
    "RPM_PUSHER,DIAMETER_PUSHER,J_PUSHER,CT_PUSHER,CQ_PUSHER,CP_PUSHER,ETA_PUSHER,ETAW_PUSHER"
)


# ------------------------------------------------------------------ the campaigns --


def _steady_two_polars(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """Two steady rows, POL 3207 and 3208, run through the stub, extracted again, posted.

    The post writes each row's group polar, its super file and its sections tables, and the
    additional post's polars and sections under `additional/p002/`. (The run leaves no
    sweep table here: the stub's recorded loads are not the requested condition, which
    `sweep_table` refuses; the campaign of the super file carries it instead.)
    """
    from tests.tier1_offline.test_additional_post import (
        BUILD,
        MAIN_WITH_SECTIONS_TOML,
        POST_ADDITIONAL_TOML,
        a_campaign,
        a_stub,
        extract,
    )
    from tests.tier1_offline.test_matrix_run import RECIPES, converged

    workspace, matrix = a_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    (workspace.inputs_dir / "pproc" / "p010.toml").write_text(
        MAIN_WITH_SECTIONS_TOML, encoding="utf-8"
    )
    lines = matrix.read_text(encoding="utf-8").splitlines()
    first = lines[2]
    assert first.split("|")[0].strip() == "3207", "the fixture row no longer leads with POL 3207"
    second = "3208" + first[len(first.split("|")[0].rstrip()) :]
    matrix.write_text("\n".join([*lines, second]) + "\n", encoding="utf-8")
    run_matrix(
        matrix,
        workspace,
        name="extracted",
        default_fs_version=BUILD,
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=a_stub(tmp_path),
    )
    extract(workspace, matrix, a_stub(tmp_path))
    write_campaign_products(workspace, overwrite=True, matrix_stem=matrix.stem)
    return workspace


def _matriz_two_polars(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """The super file's campaign: a steady polar and a rotor polar of one matrix, posted,
    and the campaign sweep table the run leaves beside them, whose rows mix the two."""
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    _post(workspace)
    return workspace


def _unsteady_rotor(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """The rotor campaign the clock columns are measured on: rotor table, unsteady polar,
    plots, reductions, sections and the per-step series."""
    from tests.tier1_offline.test_clock_columns_at_the_product import _posted_rotor_campaign

    out = _posted_rotor_campaign(tmp_path)
    return CampaignWorkspace(out.parent.parent)


def _azimuthal_rotor(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """The rotor campaign whose `[phase_locked]` table is the mean at each azimuth, beside
    its one-row-per-blade table."""
    from tests.tier1_offline.test_azimuthal_interpolation_support import _azimuthal_campaign

    _azimuthal_campaign(tmp_path, 2.0)
    return CampaignWorkspace(tmp_path / "test")


def _unsteady_probes(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """An unsteady point whose probes are sampled by fluid plots: the probes history table."""
    from tests.tier1_offline.test_f01_probe_source import _post_workspace

    workspace = _post_workspace(tmp_path, monkeypatch)
    write_campaign_products(workspace)
    return workspace


def _steady_probes(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """A steady point whose probes are the probe-points export: the steady probes table."""
    from tests.tier1_offline.test_f01_probe_source import _post_workspace

    workspace = _post_workspace(tmp_path, monkeypatch, steady=True)
    write_campaign_products(workspace)
    return workspace


def _distributions(tmp_path: Path, monkeypatch) -> CampaignWorkspace:
    """A point with stamped exports of two distributions: the split sectional loads and Cp
    files, and the per-step series."""
    from tests.tier1_offline.test_f07_section_distributions import _workspace

    workspace, _record = _workspace(tmp_path, monkeypatch, stamped=True)
    write_campaign_products(workspace)
    return workspace


#: Each campaign, the matrix stem it is posted under, and the families it must produce: a
#: pattern on the table's path under the post folder, each of which must match at least one.
CAMPAIGNS = {
    "matriz_two_polars": (
        _matriz_two_polars,
        "matriz",
        (
            r"^polars/P6001-g01-ACOEF\.csv$",
            r"^polars/P6002-g01-ACOEF\.csv$",
            r"^polars/FAM-ACOEF-P6001\.csv$",
            r"^polars/FAM-DIM-P6002\.csv$",
            r"^time_history/[^/]*_plots\.csv$",
        ),
    ),
    "steady_two_polars": (
        _steady_two_polars,
        "extracted",
        (
            r"^polars/P3207-TOTAL-ACOEF\.csv$",
            r"^polars/P3208-TOTAL-ACOEF\.csv$",
            r"^polars/FAM-ACOEF-P3207\.csv$",
            r"^polars/FAM-ACOEF-P3208\.csv$",
            r"^sections/P3207-[^/]*_sections\.csv$",
            r"^sections/P3208-[^/]*_sections\.csv$",
            r"^additional/p002/polars/P3207-[^/]*\.csv$",
            r"^additional/p002/polars/P3208-[^/]*\.csv$",
            r"^additional/p002/sections/[^/]*_sections\.csv$",
        ),
    ),
    "unsteady_rotor": (
        _unsteady_rotor,
        "products",
        (
            r"^polars/P7001-PUSHER-RCOEF\.csv$",
            r"^polars/FAM-ACOEF-P7001\.csv$",
            r"^time_history/[^/]*_plots\.csv$",
            r"^reductions/[^/]*_phase_locked\.csv$",
            r"^sections/[^/]*_sections\.csv$",
            r"^series/[^/]*_loads_series\.csv$",
        ),
    ),
    "azimuthal_rotor": (
        _azimuthal_rotor,
        "products",
        (r"^reductions/[^/]*_phase_locked_PUSHER\.csv$",),
    ),
    "unsteady_probes": (_unsteady_probes, None, (r"^probes/[^/]*_probes\.csv$",)),
    "steady_probes": (_steady_probes, None, (r"^probes/[^/]*_probes\.csv$",)),
    "distributions": (
        _distributions,
        None,
        (
            r"^sections/[^/]*_sloads_[^/]*\.csv$",
            r"^sections/[^/]*_cp_[^/]*\.csv$",
            r"^series/[^/]*_sections_series\.csv$",
        ),
    ),
}


# ------------------------------------------------------------------- the reading --


def _rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _tables(out: Path) -> list[Path]:
    """Every table the post folder holds, the archive of an earlier post left out."""
    return sorted(
        path for path in out.rglob("*.csv") if "archive" not in path.relative_to(out).parts
    )


def _sim_of_run(workspace: CampaignWorkspace) -> dict[str, str]:
    """Each recorded point's run id, and the polar its record says it belongs to."""
    return {
        point.run_id: str(point.sim_id)
        for record in workspace.read_manifest()
        for point in record.as_points()
    }


def _problems_of(workspace: CampaignWorkspace, out: Path) -> tuple[list[str], list[str]]:
    """Every table under ``out`` and every way one of them breaks the rule."""
    index = json.loads((out / "products.json").read_text(encoding="utf-8"))["products"]
    sim_of_run = _sim_of_run(workspace)
    seen: list[str] = []
    problems: list[str] = []
    for path in _tables(out):
        relative = path.relative_to(out).as_posix()
        seen.append(relative)
        rows = _rows(path)
        if not rows:
            problems.append(f"{relative}: empty")
            continue
        header, body = rows[0], rows[1:]
        # THE NAIVE SPLIT, which is what a reader without CSV quoting does.
        lines = path.read_text(encoding="utf-8").splitlines()
        if any('"' in line for line in lines):
            problems.append(f"{relative}: a cell holds a double quote, or is quoted")
        width = len(lines[0].split(","))
        for number, line in enumerate(lines[1:], start=2):
            if len(line.split(",")) != width:
                problems.append(
                    f"{relative} line {number}: {len(line.split(','))} fields split on ',', "
                    f"the header {width}"
                )
        if header[0] != POL:
            problems.append(
                f"{relative}: its first line is not a header opening with {POL}: {rows[0]!r}"
            )
            continue
        if header.count(POL) != 1:
            # A reader that averaged the plots table's POL as a quantity, or a super
            # content that repeated it, would state it again further along.
            problems.append(f"{relative}: states {POL} {header.count(POL)} times")
        if header.count("ROTOR") > 1:
            problems.append(f"{relative}: states ROTOR {header.count('ROTOR')} times")
        if RETIRED in header:
            # The polar a second time, under the name 0.26.0 gave it.
            problems.append(f"{relative}: states {RETIRED}; {POL} alone carries the polar")
        if not body:
            problems.append(f"{relative}: holds no row")
        for number, row in enumerate(body, start=2):
            if len(row) != len(header):
                problems.append(f"{relative} line {number}: {len(row)} cells, {len(header)} names")
        # A table spanning the matrix names its run per row: the settings table (FR-419) by
        # `RUN_ID`; it belongs to no one simulation.
        run_column = "RUN_ID"
        if relative.startswith("settings/") and run_column in header:
            at = header.index(run_column)
            for number, row in enumerate(body, start=2):
                wanted = sim_of_run.get(row[at])
                if row[0] != wanted:
                    problems.append(
                        f"{relative} line {number}: POL {row[0]!r}, "
                        f"and run {row[at]} is of {wanted!r}"
                    )
            continue
        entry = index.get(relative)
        if entry is None:
            problems.append(f"{relative}: a table products.json does not index")
            continue
        wanted = str(entry["sim_id"])
        runs = entry.get("derives_from") or entry.get("runs") or []
        stated = {sim_of_run.get(str(run)) for run in runs}
        if stated != {wanted}:
            problems.append(f"{relative}: indexed under {wanted!r}, its runs are of {stated}")
        for number, row in enumerate(body, start=2):
            if row[0] != wanted:
                problems.append(
                    f"{relative} line {number}: POL {row[0]!r}, its point is of {wanted!r}"
                )
    return seen, problems


@pytest.mark.requirement("FR-124")
@pytest.mark.parametrize("campaign", sorted(CAMPAIGNS))
def test_g16_every_table_the_post_writes_opens_with_the_polar_of_its_rows(
    campaign, tmp_path, monkeypatch
):
    """First line the header, first column POL, every row the polar of the point it comes from;
    and every line splits on ',' to the header's count, with no double quote anywhere.
    """
    build, stem, families = CAMPAIGNS[campaign]
    workspace = build(tmp_path, monkeypatch)
    out = workspace.products_dir(stem)
    seen, problems = _problems_of(workspace, out)
    missing = [family for family in families if not any(re.search(family, t) for t in seen)]
    assert not missing, f"{campaign} no longer writes {missing}; it wrote {seen}"
    assert not problems, f"{campaign}:\n  " + "\n  ".join(problems)


def test_g16_the_polar_column_is_named_as_the_matrix_names_its_polar_column(tmp_path):
    """The matrix layout's first column, and the header a matrix file is written with."""
    from tests.tier1_offline.test_additional_post import a_campaign

    assert matrix_mod._COLUMNS[0] == POL
    assert POL in matrix_mod.COLUMN_MEANINGS
    _, matrix = a_campaign(tmp_path)
    header = matrix.read_text(encoding="utf-8").splitlines()[0]
    assert header.split("|")[0].strip() == POL, header


# ----------------------------------------------------------------- the rotor table --


def test_g16_the_rotor_group_table_opens_with_the_run_block_then_its_rotor(tmp_path):
    """The rotor table's successor: the ROTOR group's RCOEF file opens with `POL` and the run block.

    The rotor table (`P<sim>-<sweep>_<ROTOR>_rotor.csv`, alias alone on line one in 0.26.0, then
    `POL,ROTOR` and the alias-suffixed columns) is retired: the rotor is the group of its own
    RCOEF file, `P<POL>-<ROTOR>-RCOEF.csv`, whose columns lost the alias suffix and whose speed,
    advance ratio and tip and helical Mach numbers are in the run block as `RPM<id>`, `J<id>`,
    `MTIP<id>`, `MHEL<id>` (design-post-outputs 2.3). After the block: `GROUP`, `GROUP_ID`,
    `ROTOR_ID`, then the rotor coefficients.
    """
    from pyflightstream.post._run_block import run_block_columns
    from tests.tier1_offline.test_clock_columns_at_the_product import _posted_rotor_campaign

    table = _posted_rotor_campaign(tmp_path) / "polars" / "P7001-PUSHER-RCOEF.csv"
    block = run_block_columns((), (0,))
    first, second = table.read_text(encoding="utf-8").splitlines()[:2]
    header = first.split(",")
    assert header[0] == POL and RETIRED not in header, header
    assert header[: len(block)] == list(block), header[: len(block)]
    assert header[len(block) : len(block) + 3] == ["GROUP", "GROUP_ID", "ROTOR_ID"], header
    assert {"CT", "CQ", "CP", "ETA", "ETAW"} <= set(header)
    assert not [name for name in header if name.endswith("_PUSHER")], "the alias suffix is gone"
    assert second.startswith("7001,"), second
    with table.open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    assert (row["POL"], row["GROUP"], row["ROTOR_ID"]) == ("7001", "PUSHER", "0")
    assert float(row["RPM0"]) == 2200.0
    columns, rows = read_csv_table(table)
    assert columns[0] == POL and rows == [row]


# ----------------------------------------------------------------- the steady polar --


def test_g16_the_steady_polar_and_its_family_file_state_the_polar_once_as_pol(
    tmp_path, monkeypatch
):
    """`POL`, then the run block, in order; and no `POLAR` anywhere.

    The steady polar and its super file are replaced by the group file and the FAM file of
    the polar (design-post-outputs 2.2); the 0.26.0 lead (`DESCRIPTION`, `GROUP`, ...) is the
    run block now.
    """
    from pyflightstream.post._run_block import run_block_columns

    lead = list(run_block_columns((), ()))
    workspace = _matriz_two_polars(tmp_path, monkeypatch)
    polars = workspace.products_dir("matriz") / "polars"
    tables = [polars / "P6001-g01-ACOEF.csv", polars / "FAM-ACOEF-P6001.csv"]
    for path in tables:
        first, second = path.read_text(encoding="utf-8").splitlines()[:2]
        header = first.split(",")
        assert header[: len(lead)] == lead, (path.name, header)
        assert RETIRED not in header, (path.name, header)
        assert header.count(POL) == 1, (path.name, header)
        assert second.split(",")[0] == "6001", (path.name, second[:60])


def test_g16_a_polar_file_in_the_fixed_width_format_states_the_polar_once_as_pol(tmp_path):
    """`polar_format = "legacy_polar"` (once `superfile_format`) applies to FAM and group files."""
    from pyflightstream.post._run_block import run_block_columns
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    lead = list(run_block_columns((), ()))
    workspace = _workspace(tmp_path)
    for code in ("p001", "p002"):
        path = workspace.inputs_dir / "pproc" / f"{code}.toml"
        path.write_text(
            path.read_text(encoding="utf-8") + '\n[products]\npolar_format = "legacy_polar"\n',
            encoding="utf-8",
        )
    written = [Path(p) for p in _post(workspace) if Path(p).parent.name == "polars"]
    assert written, "the post wrote no polar file"
    for path in written:
        header = path.read_text(encoding="utf-8").splitlines()[0].split()
        assert header[: len(lead)] == lead, (path.name, header)
        assert RETIRED not in header, (path.name, header[:6])


# ------------------------------------------------------------------ the readers --


def test_g16_the_plots_table_polar_is_read_as_no_plotted_quantity(tmp_path):
    """The reductions read every column of the plots table but `POL` back as a quantity."""
    written = tmp_path / "with.csv"
    written.write_text("POL,Time-step,CL_MRP_TOTAL\n4014,1,0.5\n4014,2,0.7\n", encoding="utf-8")
    older = tmp_path / "without.csv"
    older.write_text("Time-step,CL_MRP_TOTAL\n1,0.5\n2,0.7\n", encoding="utf-8")
    for path in (written, older):
        columns, series = plots_table_series(path)
        assert columns == ("Time-step", "CL_MRP_TOTAL"), (path.name, columns)
        assert POL not in series.fields, path.name
        assert [int(step) for step in series.steps] == [1, 2]


def test_g16_a_names_entry_cannot_take_the_polar_columns_name():
    """`[names]` may not give a plotted column the name the first column carries."""
    with pytest.raises(ValueError, match="reserved"):
        PprocSpec.model_validate({"groups": {"1": "all"}, "names": {"CL_MRP_TOTAL": POL}})


# ------------------------------------------------------- no comma and no quote in a cell --


def test_g16_the_polar_files_split_on_comma_to_the_header_count(tmp_path):
    """The reader without CSV quoting counts each line of a polar file as the header does.

    The matrix cells the super file echoed (`SWEEP_VALUES`, `FLIGHT_CONDITION`) left the polar
    rows with it (design-post-outputs 2.3: the run block and `products.json` hold what they
    said), so no list cell is left in `polars/` to write with semicolons; what stays is that no
    cell of those files holds a comma or a double quote.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    _post(workspace)
    polars = workspace.products_dir("matriz") / "polars"
    tables = sorted(polars.glob("*.csv"))
    assert len(tables) == 20
    for table in tables:
        lines = table.read_text(encoding="utf-8").splitlines()
        header = lines[0].split(",")
        assert len(lines) > 1, table.name
        for line in lines[1:]:
            assert '"' not in line, (table.name, line[:80])
            assert len(line.split(",")) == len(header), (table.name, len(line.split(",")))


def test_g16_a_text_cell_writes_no_comma_no_quote_and_no_line_break(tmp_path):
    """The funnel every product passes through, header included, and nothing quoted."""
    from pyflightstream.post.products import write_csv_table

    written = write_csv_table(
        tmp_path / "t.csv",
        ("POL", "A,B", 'say "x"'),
        [("0001", "MACH:0.2, REmi:2.3", 'a "b"\nc')],
    )
    assert written.read_text(encoding="utf-8") == (
        "POL,A;B,say 'x'\n0001,MACH:0.2; REmi:2.3,a 'b' c\n"
    )


def test_f251_a_declined_cell_of_a_table_writes_as_na(tmp_path):
    """F-251: a NaN cell is the NA token, never an empty field a reader takes as missing data."""
    from pyflightstream.results import parse_unsteady_plots, to_csv

    report = parse_unsteady_plots(
        "Time, CDI, CL\n0, nan, 0.4,\n"
        + "-" * 60
        + "\nSoftware : Flightstream version 26.1, build #7012026\n"
    )
    written = to_csv(report, tmp_path / "plots.csv")
    header, row = written.read_text(encoding="utf-8").splitlines()[:2]
    cells = dict(zip(header.split(","), row.split(","), strict=True))
    assert cells["CDI"] == "NA", row
    assert cells["CL"] == "0.4", row
