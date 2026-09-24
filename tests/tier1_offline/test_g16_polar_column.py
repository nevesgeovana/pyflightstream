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
    CONTEXT_COLUMNS,
    plots_table_series,
    read_csv_table,
    write_campaign_products,
)
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace

#: The polar column, spelled as a matrix file writes it rather than imported, so a tree that
#: names it otherwise fails on the tables and not on an import.
POL = "POL"

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
            r"^campaign_sweep\.csv$",
            r"^polars/P6001-[^/]*_g01\.csv$",
            r"^polars/P6002-[^/]*_g01\.csv$",
            r"^polars/SUPER-6001-[^/]*\.csv$",
            r"^polars/SUPER-6002-[^/]*\.csv$",
            r"^probes/[^/]*_plots\.csv$",
        ),
    ),
    "steady_two_polars": (
        _steady_two_polars,
        "extracted",
        (
            r"^polars/P3207-[^/]*_g01\.csv$",
            r"^polars/P3208-[^/]*_g01\.csv$",
            r"^polars/SUPER-3207-[^/]*\.csv$",
            r"^polars/SUPER-3208-[^/]*\.csv$",
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
            r"^polars/P7001-PUSHER_rotor\.csv$",
            r"^polars/P7001_[^/]*_uns_avg\.csv$",
            r"^probes/[^/]*_plots\.csv$",
            r"^probes/[^/]*_time_average\.csv$",
            r"^probes/[^/]*_phase_locked\.csv$",
            r"^sections/[^/]*_sections\.csv$",
            r"^series/[^/]*_loads_series\.csv$",
        ),
    ),
    "azimuthal_rotor": (
        _azimuthal_rotor,
        "products",
        (
            r"^probes/[^/]*_phase_locked_PUSHER\.csv$",
            r"^probes/[^/]*_per_blade\.csv$",
        ),
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
        if not body:
            problems.append(f"{relative}: holds no row")
        for number, row in enumerate(body, start=2):
            if len(row) != len(header):
                problems.append(f"{relative} line {number}: {len(row)} cells, {len(header)} names")
        if relative == "campaign_sweep.csv":
            at = header.index("run_id")
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


def test_g16_the_rotor_table_opens_with_its_header_polar_and_rotor(tmp_path):
    """Her rotor table's shape: `POL,ROTOR` and then every column 0.26.0 wrote, in its order.

    Until 0.27.0 the first line was the alias alone and the header the second, so no CSV
    reader took the file as written. The alias is the `ROTOR` column of every row now.
    """
    from tests.tier1_offline.test_clock_columns_at_the_product import (
        ROTOR_TABLE,
        _posted_rotor_campaign,
    )

    table = _posted_rotor_campaign(tmp_path) / ROTOR_TABLE
    first, second = table.read_text(encoding="utf-8").splitlines()[:2]
    assert first == f"POL,ROTOR,{ROTOR_COLUMNS_BEFORE}", first
    assert second.startswith("7001,PUSHER,"), second
    assert ROTOR_COLUMNS_BEFORE.split(",")[: len(CONTEXT_COLUMNS)] == list(CONTEXT_COLUMNS)
    with table.open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    assert (row["POL"], row["ROTOR"], row["RPM_PUSHER"]) == ("7001", "PUSHER", "2200.00000")
    columns, rows = read_csv_table(table)
    assert columns[:2] == (POL, "ROTOR") and rows == [row]


def test_g16_a_rotor_table_written_before_the_rule_still_reads_into_the_union(tmp_path):
    """A 0.26.0 rotor table, alias alone on line one, gives the union its header, not its alias."""
    from pyflightstream.post.superfile import _header

    old = tmp_path / "P4014-PUSHER_rotor.csv"
    old.write_text(f"PUSHER\n{ROTOR_COLUMNS_BEFORE}\n" + ",".join(["0"] * 24) + "\n")
    assert _header(old) == set(ROTOR_COLUMNS_BEFORE.split(","))
    new = tmp_path / "P4014-LIFT_rotor.csv"
    new.write_text(f"POL,ROTOR,{ROTOR_COLUMNS_BEFORE}\n")
    assert _header(new) == {POL, "ROTOR", *ROTOR_COLUMNS_BEFORE.split(",")}


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


def test_g16_the_echoed_matrix_cells_write_their_lists_with_semicolons(tmp_path):
    """`SWEEP_VALUES` and `FLIGHT_CONDITION` as a naive reader counts them: one cell each.

    The super file echoes the matrix row; a list in it was written quoted, its commas inside,
    and a reader splitting on ',' took each comma for a column. The unsteady polar carries the
    same content after its plotted columns.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    _post(workspace)
    polars = workspace.products_dir("matriz") / "polars"
    (steady,) = sorted(polars.glob("SUPER-6001-*_g01.csv"))
    lines = steady.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    for line in lines[1:]:
        cells = line.split(",")
        assert len(cells) == len(header), (len(cells), len(header))
        row = dict(zip(header, cells, strict=True))
        assert ";" in row["SWEEP_VALUES"] and ";" in row["FLIGHT_CONDITION"], row
        assert row["FLIGHT_CONDITION"].count(";") == row["FLIGHT_CONDITION"].count(":") - 1, row


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


def test_g16_the_campaign_sweep_table_writes_no_comma_in_a_cell(tmp_path):
    """The sweep is written through the tabular layer's one write path, under the same rule."""
    import pandas as pd

    from pyflightstream.results.tables import write_table

    frame = pd.DataFrame(
        {
            "POL": ["0001"],
            "status": ["CONVERGED, twice"],
            "CL": [0.4],
            "data_origin": ["raw"],
            "reduction": ["none"],
            "reduction_window": ["not_applicable"],
        }
    )
    written = write_table(frame, tmp_path / "campaign_sweep.csv")
    first, second = written.read_text(encoding="utf-8").splitlines()
    assert len(second.split(",")) == len(first.split(",")) and '"' not in second, second
    assert "CONVERGED; twice" in second, second
    assert frame["status"].iloc[0] == "CONVERGED, twice", "the caller's frame keeps its text"
