"""Regression coverage grouped by subject."""

from __future__ import annotations

import copy
import math
import re
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import pyflightstream.post.section_distributions as distributions
from pyflightstream import _textio
from pyflightstream._errors import ProductError, PyflightstreamWarning, warn
from pyflightstream.cases import AXES_PLOT_COMPONENTS
from pyflightstream.post import OutputProvenance
from pyflightstream.post._tables import (
    COEFFICIENT_COLUMNS,
    ReferenceValues,
    plots_table_series,
    polar_file_name,
    write_csv_table,
)
from pyflightstream.post._tables import read_csv_table as _post2_plots_tables__read_csv_table
from pyflightstream.post._tables import read_csv_table as _post2_series_precision__read_csv_table
from pyflightstream.post._tables import read_csv_table as _post_1_tables__read_csv_table
from pyflightstream.post.custom_polar import (
    custom_polar_file_name,
    read_custom_polar_format,
    write_custom_polar_format,
)
from pyflightstream.post.point_tables import (
    write_plots_table,
    write_sections_table,
    write_unsteady_probes_table,
)
from pyflightstream.post.probe_fields import write_probe_field
from pyflightstream.post.products import read_csv_table as _post_1_point_tables__read_csv_table
from pyflightstream.post.products import write_campaign_products
from pyflightstream.post.section_distributions import _integrated_strips
from pyflightstream.post.settings_table import FLAG_IDS, settings_table
from pyflightstream.post.superfile import _write_legacy_polar, measure_sections
from pyflightstream.post.unsteady_polar import _the_axes_of_the_unsteady_rows
from pyflightstream.post.writers import OutputExistsError
from pyflightstream.script import Script, helpers
from tests.tier1_offline.test_f07_section_distributions import _post as _post_1_series___post
from tests.tier1_offline.test_f07_section_distributions import (
    _workspace as _post_1_series___workspace,
)
from tests.tier1_offline.test_integrated_sectional_loads import (
    _case as _post_1_section_distributions___case,
)
from tests.tier1_offline.test_integrated_sectional_loads import (
    _table as _post_1_section_distributions___table,
)
from tests.tier1_offline.test_pfs2006_declined_induced_drag import (
    _EVERY_BOUNDARY as _POST_1_POLAR___EVERY_BOUNDARY,
)
from tests.tier1_offline.test_post_products import LOADS as _POST2_STALE_SECTIONS__LOADS
from tests.tier1_offline.test_post_products import PLOTS_HEADER as _POST2_PLOTS_TABLES__PLOTS_HEADER
from tests.tier1_offline.test_post_products import PROBES as _POST2_STALE_SECTIONS__PROBES
from tests.tier1_offline.test_post_products import SLOADS as _POST2_PLOTS_TABLES__SLOADS
from tests.tier1_offline.test_post_products import SLOADS as _POST2_SERIES_PRECISION__SLOADS
from tests.tier1_offline.test_post_products import SLOADS as _POST2_STALE_SECTIONS__SLOADS
from tests.tier1_offline.test_post_products import (
    _products_manifest as _post2_plots_tables___products_manifest,
)
from tests.tier1_offline.test_post_products import (
    _products_manifest as _post2_stale_sections___products_manifest,
)
from tests.tier1_offline.test_post_products import (
    _series_call as _post2_series_precision___series_call,
)
from tests.tier1_offline.test_post_products import (
    _unsteady_workspace as _post2_plots_tables___unsteady_workspace,
)
from tests.tier1_offline.test_post_superfile import _PLOTS as _POST_1_POINT_TABLES___PLOTS
from tests.tier1_offline.test_settings_codebook import snapshot as _post_1_settings_table__snapshot


def test_p0420_csv_refusal_preserves_published_table(tmp_path):
    target = tmp_path / "table.csv"
    target.write_bytes(b"x,y\nold,data\n")
    with pytest.raises(ProductError):
        write_csv_table(target, ["x", "y"], [[1, 2], [3]])
    assert target.read_bytes() == b"x,y\nold,data\n"
    assert list(tmp_path.iterdir()) == [target]


def test_p0420_text_encoding_refusal_preserves_published_text(tmp_path):
    target = tmp_path / "text.txt"
    target.write_bytes(b"previous\n")
    with pytest.raises(UnicodeEncodeError):
        _textio.write_text(target, "\ud800")
    assert target.read_bytes() == b"previous\n"
    assert list(tmp_path.iterdir()) == [target]


def test_p0420_line_iterator_failure_preserves_published_text(tmp_path):
    target = tmp_path / "text.txt"
    target.write_bytes(b"previous\n")

    def lines():
        yield "first"
        raise RuntimeError("interrupted producer")

    with pytest.raises(RuntimeError, match="interrupted producer"):
        _textio.write_lines(target, lines())
    assert target.read_bytes() == b"previous\n"
    assert list(tmp_path.iterdir()) == [target]


def test_p0430_atomic_new_file_uses_normal_creation_permissions(tmp_path, monkeypatch):
    """P0430-MODE: request ordinary file permissions, filtered by the OS umask."""
    import os

    real_open = os.open
    modes = []

    def recording_open(path, flags, mode=0o777, **kwargs):
        modes.append(mode)
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)
    _textio.write_text(tmp_path / "new.txt", "complete\n")
    assert modes == [0o666]


def test_p0430_atomic_replacement_preserves_posix_permissions(tmp_path):
    """P0430-MODE: replacement must retain group read/write access."""
    import os
    import stat

    if os.name != "posix":
        pytest.skip("POSIX permission bits require a POSIX filesystem")
    target = tmp_path / "shared.txt"
    target.write_bytes(b"old\n")
    target.chmod(0o640)
    _textio.write_text(target, "new\n")
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert target.read_bytes() == b"new\n"


def test_p0430_atomic_publish_replaces_symlink_not_referent(tmp_path):
    """P0430-SYMLINK: the documented publish replaces the directory entry."""
    referent = tmp_path / "original.txt"
    referent.write_bytes(b"original\n")
    target = tmp_path / "link.txt"
    try:
        target.symlink_to(referent)
    except OSError:
        pytest.skip("creating symlinks requires host permission")
    _textio.write_text(target, "published\n")
    assert not target.is_symlink()
    assert target.read_bytes() == b"published\n"
    assert referent.read_bytes() == b"original\n"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("options", [{}, {"allow_nan": True}])
def test_p0430_json_refuses_nonfinite_without_replacing_target(tmp_path, value, options):
    """P0430-JSON: non-finite floats cannot produce a JSON record."""
    target = tmp_path / "record.json"
    target.write_bytes(b'{"previous": true}\n')
    with pytest.raises(ValueError, match="JSON"):
        _textio.write_json(target, {"nested": [value]}, **options)
    assert target.read_bytes() == b'{"previous": true}\n'
    assert list(tmp_path.iterdir()) == [target]


_POST2_CUSTOM_POLAR___ACCENTED = "Asa em cruzeiro, " + chr(0xE2) + "ngulo m" + chr(0xE9) + "dio"


def _post2_custom_polar___write(path, *, description, configuration=None):
    return write_custom_polar_format(
        path,
        polar="3207",
        description=description,
        group=1,
        mach=0.2,
        reference=ReferenceValues(sref_m2=50.0, cref_m=2.5, bref_m=20.0),
        rows=[[0.0] * len(COEFFICIENT_COLUMNS)],
        date="2026-10-12",
        configuration=configuration,
    )


class TestPost2CustomPolar:
    """P0400-ASCIITITLE: a non-ASCII description reaches the custom polar transliterated.

    At the 0.40.0 base the .dat was written in strict ASCII, so one accented
    letter in the row's DESCRIPTION or CONFIGURATION raised a UnicodeEncodeError
    out of the campaign post; the reader refused a non-ASCII file the same way.
    """

    @staticmethod
    def test_p0400_asciititle_a_non_ascii_description_is_transliterated(tmp_path):
        """P0400-ASCIITITLE: the title is written in ASCII, accents dropped, and reads back."""
        written = _post2_custom_polar___write(
            tmp_path / "p.dat",
            description=_POST2_CUSTOM_POLAR___ACCENTED,
            configuration="cruzeiro " + chr(0x2192),
        )
        first = written.read_bytes().split(b"\n")[0]
        assert first == b"FlightStream - Asa em cruzeiro, angulo medio - cruzeiro ?"
        assert read_custom_polar_format(written).description == (
            "Asa em cruzeiro, angulo medio - cruzeiro ?"
        )

    @staticmethod
    def test_p0400_asciititle_the_reader_takes_a_non_ascii_file(tmp_path):
        """P0400-ASCIITITLE: a file someone wrote in UTF-8 is read, its title transliterated."""
        written = _post2_custom_polar___write(tmp_path / "p.dat", description="plain")
        text = written.read_text(encoding="ascii").replace(
            "plain", _POST2_CUSTOM_POLAR___ACCENTED, 1
        )
        written.write_bytes(text.encode("utf-8"))
        assert read_custom_polar_format(written).description == "Asa em cruzeiro, angulo medio"

    @staticmethod
    @pytest.mark.parametrize("line_end", [b"\n", b"\r\n", b"\r"], ids=["lf", "crlf", "cr"])
    def test_p0400_asciititle_reader_preserves_universal_newlines(tmp_path, line_end):
        """P0400-ASCIITITLE: legacy line endings do not become part of header values."""
        written = _post2_custom_polar___write(tmp_path / "p.dat", description="plain")
        written.write_bytes(written.read_bytes().replace(b"\n", line_end))
        table = read_custom_polar_format(written)
        assert table.description == "plain"
        assert table.date == "2026-10-12"


_POST2_PLOTS_TABLES___TABLE = (
    "Time-step,CL_MRP_TOTAL,MACH1,\n1.0000,0.1,0.2,\n2.0000,NaN,0.3,\n3.0000,0.3,NaN,\n"
)


_POST2_PLOTS_TABLES___FOOT = "-" * 60 + "\n     Force Units: Coefficients\n"


def _post2_plots_tables___without_banner(text: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if "Freestream velocity" not in line
    )


class TestPost2PlotsTables:
    """P0400-PLOTSNA and P0400-BANNER: the plots table, its `NA` cells and its banner.

    At the 0.40.0 base a plots export whose banner states no free-stream velocity
    raised a bare AnchorNotFoundError out of write_plots_table, which no caller
    caught, so the whole post ended; a NaN the export carried was written `NA` and
    neither plots_table_series nor the unsteady probes table could read that token
    back.
    """

    @staticmethod
    def test_p0400_banner_a_plots_export_without_its_banner_is_a_product_error(tmp_path):
        """P0400-BANNER: no 'Freestream velocity (m/s)' line is a ProductError naming the file."""
        export = (
            _post2_plots_tables___without_banner(_POST2_PLOTS_TABLES__PLOTS_HEADER)
            + _POST2_PLOTS_TABLES___TABLE
            + _POST2_PLOTS_TABLES___FOOT
        )
        with pytest.raises(ProductError, match="P_plots.csv"):
            write_plots_table(tmp_path / "P_plots.csv", export)

    @staticmethod
    def test_p0400_banner_the_post_records_a_skip_and_goes_on(tmp_path):
        """P0400-BANNER: the campaign post skips the point's plots table instead of ending."""
        from pyflightstream.post.products import write_campaign_products

        workspace = _post2_plots_tables___unsteady_workspace(tmp_path, reductions=None)
        export = workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt"
        export.write_text(
            _post2_plots_tables___without_banner(export.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        write_campaign_products(workspace)
        skipped = _post2_plots_tables___products_manifest(workspace)["skipped"]
        assert "Freestream velocity" in skipped["probes/AL-020_plots.csv"]

    @staticmethod
    def test_p0400_banner_a_sections_export_without_its_reynolds_number_is_a_product_error(
        tmp_path,
    ):
        """P0400-BANNER: the sections table refuses a banner with no Reynolds number by name."""
        text = "".join(
            line
            for line in _POST2_PLOTS_TABLES__SLOADS.splitlines(keepends=True)
            if "Reynolds Number" not in line
        )
        assert text != _POST2_PLOTS_TABLES__SLOADS, "the fixture's Reynolds line moved"
        with pytest.raises(ProductError, match="S_sections.csv"):
            write_sections_table(tmp_path / "S_sections.csv", text, mach=0.2)

    @staticmethod
    def test_p0400_plotsna_a_nan_round_trips_through_the_plots_table(tmp_path):
        """P0400-PLOTSNA: export NaN, table `NA`, series NaN, every other value kept."""
        table = write_plots_table(
            tmp_path / "P_plots.csv",
            _POST2_PLOTS_TABLES__PLOTS_HEADER
            + _POST2_PLOTS_TABLES___TABLE
            + _POST2_PLOTS_TABLES___FOOT,
        )
        _, rows = _post2_plots_tables__read_csv_table(table)
        assert rows[1]["CL_MRP_TOTAL"] == "NA"
        columns, series = plots_table_series(table)
        cl = series.fields["CL_MRP_TOTAL"][:, 0]
        assert math.isnan(cl[1]) and cl[0] == pytest.approx(0.4) and cl[2] == pytest.approx(1.2)
        assert series.steps.tolist() == [1, 2, 3]

    @staticmethod
    def test_p0400_plotsna_one_na_cell_keeps_the_probes_table(tmp_path):
        """P0400-PLOTSNA: an `NA` probe cell is `NA` in the probes table, the rest present."""
        table = write_plots_table(
            tmp_path / "P_plots.csv",
            _POST2_PLOTS_TABLES__PLOTS_HEADER
            + _POST2_PLOTS_TABLES___TABLE
            + _POST2_PLOTS_TABLES___FOOT,
        )
        probes = write_unsteady_probes_table(
            tmp_path / "P_probes.csv",
            table,
            positions={1: (0.0, 0.0, 0.0, "MRP")},
            parameters=["MACH"],
        )
        assert probes is not None
        _, rows = _post2_plots_tables__read_csv_table(probes)
        assert [row["MACH"] for row in rows] == ["0.20000", "0.30000", "NA"]


_POST2_SERIES_PRECISION__MU = 1.7892976260350732e-05


class TestPost2SeriesPrecision:
    """P0400-SIGDIGITS: MU, time_s and coefficients are written at significant digits.

    At the 0.40.0 base every float of every product went through the five-decimal
    funnel, so sea-level viscosity was written 0.00002 (one significant digit, 12
    per cent off the stated value) and a rotor's time steps were quantised.
    """

    @staticmethod
    def test_p0400_sigdigits_the_funnel_keeps_mu_time_and_coefficients(tmp_path):
        """P0400-SIGDIGITS: quantities keep six digits; exact values keep five decimals."""
        table = write_csv_table(
            tmp_path / "t.csv",
            ("time_s", "MU", "CL"),
            [
                (2.78e-5, _POST2_SERIES_PRECISION__MU, 0.123456789),
                (1234.56789, _POST2_SERIES_PRECISION__MU, 1.0),
            ],
        )
        _, rows = _post2_series_precision__read_csv_table(table)
        assert rows[0] == {"time_s": "2.78e-05", "MU": "1.7893e-05", "CL": "0.123457"}
        assert rows[1] == {"time_s": "1234.56789", "MU": "1.7893e-05", "CL": "1.00000"}

    @staticmethod
    def test_p0400_sigdigits_mu_round_trips_in_a_sections_file(tmp_path):
        """P0400-SIGDIGITS: a sections table states MU to four significant digits or more."""
        condition = {
            "ALPHA": 0.0,
            "BETA": 0.0,
            "MACH": 0.2,
            "RHO": 1.225,
            "MU": _POST2_SERIES_PRECISION__MU,
        }
        table = write_sections_table(
            tmp_path / "s.csv", _POST2_SERIES_PRECISION__SLOADS, mach=0.2, condition=condition
        )
        _, rows = _post2_series_precision__read_csv_table(table)
        assert rows and all(
            float(row["MU"]) == pytest.approx(_POST2_SERIES_PRECISION__MU, rel=1e-4) for row in rows
        )

    @staticmethod
    def test_p0400_sigdigits_mu_round_trips_in_a_series(tmp_path):
        """P0400-SIGDIGITS: a series table states MU to four significant digits or more."""
        from pyflightstream.post.series import write_point_series

        workspace, arguments = _post2_series_precision___series_call(tmp_path)
        written, _ = write_point_series(
            workspace.root,
            overwrite=True,
            condition={"MU": _POST2_SERIES_PRECISION__MU, "RHO": 1.225},
            **arguments,
        )
        (series,) = [path for path in written if path.name.endswith("_loads_series.csv")]
        _, rows = _post2_series_precision__read_csv_table(series)
        assert rows and all(
            float(row["MU"]) == pytest.approx(_POST2_SERIES_PRECISION__MU, rel=1e-4) for row in rows
        )

    @staticmethod
    @pytest.mark.parametrize(
        "column",
        [
            "Time (sec)",
            "Time",
            "RHO",
            "Offset",
            "Fx",
            "momentum_thickness",
            "FX_PROP",
            "VX1",
            "BL_MOMENTUM_THICKNESS2",
            "BL_TOTAL_THICKNESS",
            "AZIMUTH_START",
        ],
    )
    def test_p0400_sigdigits_small_dimensional_cells_keep_their_scale(tmp_path, column):
        """P0400-SIGDIGITS: dimensional cells beyond viscosity and series time retain digits."""
        small = 1.234567e-6
        table = write_csv_table(tmp_path / "physical.csv", [column, "CL_PROP"], [[small, small]])
        _, rows = _post2_series_precision__read_csv_table(table)
        assert float(rows[0][column]) == pytest.approx(small, rel=1e-5)
        assert float(rows[0]["CL_PROP"]) == pytest.approx(small, rel=1e-5)


_POST2_STALE_SECTIONS__SECTIONS = "sections/AL-020_sections.csv"


def _post2_stale_sections___no_sections() -> str:
    text = _POST2_STALE_SECTIONS__SLOADS.replace(
        "Number of Surface Sections:                 2",
        "Number of Surface Sections:                 0",
    )
    assert text != _POST2_STALE_SECTIONS__SLOADS, "the fixture's section count line moved"
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("-0.9"))


def _post2_stale_sections___workspace(tmp_path, *, include_probes=False):
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n', encoding="utf-8"
    )
    raw = workspace.sim_dir("3207") / "outputs"
    raw.mkdir(parents=True)
    (raw / "AL-020.txt").write_text(_POST2_STALE_SECTIONS__LOADS, encoding="utf-8")
    (raw / "AL-020_sloads.txt").write_text(_POST2_STALE_SECTIONS__SLOADS, encoding="utf-8")
    if include_probes:
        (raw / "AL-020_probes.txt").write_text(_POST2_STALE_SECTIONS__PROBES, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/AL-020",
            point_name="AL-020",
            sweep_name="AL-020",
            sim_id="3207",
            point={"alpha": -2.0},
            fs_version_requested="26.120",
            package_version="0.13.0.dev0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["outputs/AL-020.txt", "outputs/AL-020_sloads.txt"]
            + (["outputs/AL-020_probes.txt"] if include_probes else []),
            pproc="p001",
            description="STEADY_WB",
            mach=0.2,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
        )
    )
    return workspace, raw / "AL-020_sloads.txt"


class TestPost2StaleSections:
    """P0400-STALESECT: a product the writer no longer writes does not stay current.

    At the 0.40.0 base a post without the archive left the previous product in
    place for the writer to overwrite, and a writer that wrote nothing (an export
    declaring no section) left that file on disk, unnamed by the new manifest and
    read as current. The rerun below is the case: the point's export loses its
    sections between two posts.
    """

    @staticmethod
    @pytest.mark.parametrize("archive", [False, True], ids=["force-overwrite", "archive"])
    def test_p0400_stalesect_a_lost_sections_table_is_retired(tmp_path, archive):
        """P0400-STALESECT: after the rerun no sections table is current, under both flags."""
        workspace, sloads = _post2_stale_sections___workspace(tmp_path)
        write_campaign_products(workspace)
        products = workspace.root / "post" / "products"
        assert (products / _POST2_STALE_SECTIONS__SECTIONS).is_file(), (
            "the first post writes the sections table"
        )
        sloads.write_text(_post2_stale_sections___no_sections(), encoding="utf-8")
        write_campaign_products(workspace, overwrite=True, archive=archive)
        assert not (products / _POST2_STALE_SECTIONS__SECTIONS).exists()
        assert (
            _POST2_STALE_SECTIONS__SECTIONS
            not in _post2_stale_sections___products_manifest(workspace)["products"]
        )

    @staticmethod
    @pytest.mark.parametrize("archive", [False, True], ids=["force-overwrite", "archive"])
    def test_p0400_stalesect_a_lost_probes_table_is_retired(tmp_path, archive):
        """P0400-STALESECT: a zero-probe export retires the old table under both flags."""
        workspace, sloads = _post2_stale_sections___workspace(tmp_path, include_probes=True)
        probes = sloads.with_name("AL-020_probes.txt")
        write_campaign_products(workspace)
        relative = "probes/AL-020_probes.csv"
        target = workspace.products_dir(None) / relative
        assert target.is_file()
        empty = Path(__file__).parent / "fixtures" / "probe_points_zero_26.123.txt"
        probes.write_bytes(empty.read_bytes())
        write_campaign_products(workspace, overwrite=True, archive=archive)
        assert not target.exists()
        assert relative not in _post2_stale_sections___products_manifest(workspace)["products"]


_POST2_SUPERFILE__COLUMNS = [
    "POL",
    "SET_SOLVER_VISCOUS_COUPLING",
    "DESCRIPTION",
    "flight_condition_defaults_from",
]


class TestPost2Superfile:
    """P0400-LEGACYWIDTH: every field of the legacy polar super file is separated.

    At the 0.40.0 base each field was right-justified to 16 characters with no
    separator, so a name of 16 characters or more ran into its neighbour and a
    description holding spaces split into several tokens.
    """

    @staticmethod
    def test_p0400_legacywidth_every_line_splits_into_one_field_per_column(tmp_path):
        """P0400-LEGACYWIDTH: the header and every row split into len(columns) fields."""
        rows = [
            ["3207", 1, "wing at cruise", "the matrix row"],
            ["3208", 0, "a description longer than sixteen", 0.5],
        ]
        path = _write_legacy_polar(tmp_path / "SUPER.dat", _POST2_SUPERFILE__COLUMNS, rows)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].split() == _POST2_SUPERFILE__COLUMNS
        for line in lines[1:]:
            assert len(line.split()) == len(_POST2_SUPERFILE__COLUMNS), line
        assert lines[1].split()[2] == "wing_at_cruise"

    @staticmethod
    def test_p0400_legacywidth_short_fields_keep_the_width_of_sixteen(tmp_path):
        """P0400-LEGACYWIDTH control: names and cells under 16 characters keep the 16 width."""
        path = _write_legacy_polar(tmp_path / "SUPER.dat", ["POL", "CL"], [["3207", 0.5]])
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines == ["POL".rjust(16) + "CL".rjust(16), "3207".rjust(16) + "0.50000".rjust(16)]


def _post2_unsteady_polar___rows():
    values = {f"{part}_MRP": 1.0 for part in AXES_PLOT_COMPONENTS}
    condition = {"RHO": 1.225, "VINF": 30.0, "ALPHA": 2.0, "BETA": 0.0}
    return [(condition, values, (0, 9), {})]


class TestPost2UnsteadyPolar:
    """P0400-BREF: the unsteady polar's axis block needs a positive span.

    At the 0.40.0 base the block guarded SREF and CREF but not BREF, so a zero span
    reached ``cref / bref`` and the whole polar ended in a bare ZeroDivisionError.
    """

    @staticmethod
    def test_p0400_bref_a_zero_span_skips_the_axis_block_with_a_note():
        """P0400-BREF: BREF = 0 writes no axis column and says why."""
        notes: list[str] = []
        reference = ReferenceValues(sref_m2=1.0, cref_m=0.5, bref_m=0.0)
        assert (
            _the_axes_of_the_unsteady_rows(
                _post2_unsteady_polar___rows(), reference, notes, ["MRP"]
            )
            == []
        )
        assert any("roll and yaw moments need a span" in note for note in notes)

    @staticmethod
    def test_p0400_bref_a_positive_span_writes_the_axis_block():
        """P0400-BREF control: a positive span writes the axis columns."""
        notes: list[str] = []
        reference = ReferenceValues(sref_m2=1.0, cref_m=0.5, bref_m=2.0)
        assert _the_axes_of_the_unsteady_rows(
            _post2_unsteady_polar___rows(), reference, notes, ["MRP"]
        )


def _post_1_custom_polar___written(tmp_path, reference, rows):
    return write_custom_polar_format(
        tmp_path / "7_M20_g01.dat",
        polar=7,
        description="wing",
        group=1,
        mach=0.2,
        reference=reference,
        rows=rows,
        date="Tue Sep 08 23:41:07  2026",
    )


def _post_1_custom_polar___row(first: float) -> tuple[float, ...]:
    return (first, *([0.125] * (len(COEFFICIENT_COLUMNS) - 1)))


class TestPost1CustomPolar:
    """P0400 custom polar defects (post-1 lane).

    P0400-CUSTOMREAD (PFS-2095.018): malformed input is a ProductError naming the
    file and the line, never a bare ValueError or UnicodeDecodeError.
    P0400-CUSTOMWIDTH (PFS-2105.012): every field keeps a blank before it, so a
    long reference value or a large coefficient never fuses with its neighbour.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CUSTOMWIDTH")])
    def test_p0400_customwidth_a_long_reference_and_a_large_value_round_trip(tmp_path):
        """P0400-CUSTOMWIDTH: 0.0785398... and -12.3456789 on line 6, 12345.6 in a row."""
        reference = ReferenceValues(sref_m2=0.07853981633974483, cref_m=2.5, bref_m=-12.3456789)
        path = _post_1_custom_polar___written(
            tmp_path,
            reference,
            [_post_1_custom_polar___row(12345.6), _post_1_custom_polar___row(0.5)],
        )
        lines = path.read_text(encoding="ascii").splitlines()
        for line in [lines[5], *lines[9:]]:
            fields = [line[start : start + 10] for start in range(0, len(line), 10)]
            assert all(field.startswith(" ") for field in fields), line
        table = read_custom_polar_format(path)
        assert table.reference.sref_m2 == pytest.approx(0.07853981633974483, rel=1e-6)
        assert table.reference.bref_m == pytest.approx(-12.3456789, rel=1e-6)
        first = COEFFICIENT_COLUMNS[0]
        assert [row[first] for row in table.rows] == pytest.approx([12345.6, 0.5])

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CUSTOMREAD")])
    @pytest.mark.parametrize(
        ("line", "text", "said"),
        [
            (3, "009 xx", "line 4"),
            (5, "0.2 50.0 abc", "line 6"),
            (9, "nonsense", "line 10"),
        ],
    )
    def test_p0400_customread_names_the_line(tmp_path, line, text, said):
        """P0400-CUSTOMREAD: a word where a number belongs is refused naming its line."""
        reference = ReferenceValues(sref_m2=50.0, cref_m=2.5, bref_m=20.0)
        path = _post_1_custom_polar___written(
            tmp_path, reference, [_post_1_custom_polar___row(0.5)]
        )
        lines = path.read_text(encoding="ascii").splitlines()
        if line == 9:
            lines[9] = " ".join([text] * len(COEFFICIENT_COLUMNS))
        elif line == 5:
            lines[5] = " ".join(lines[5].split()[:-1] + ["abc"])
        else:
            lines[line] = text
        path.write_text("\n".join(lines) + "\n", encoding="ascii")
        with pytest.raises(ProductError, match=said):
            read_custom_polar_format(path)

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-CUSTOMREAD")])
    def test_p0400_customread_reads_a_non_ascii_byte(tmp_path):
        """P0400-CUSTOMREAD: a non-ASCII byte is read back, never a bare UnicodeDecodeError.

        The writer transliterates its own titles; the reader follows the same policy.
        """
        reference = ReferenceValues(sref_m2=50.0, cref_m=2.5, bref_m=20.0)
        path = _post_1_custom_polar___written(
            tmp_path, reference, [_post_1_custom_polar___row(0.5)]
        )
        path.write_bytes(path.read_bytes().replace(b"wing", b"w\xe9ng"))
        table = read_custom_polar_format(path)
        assert table is not None


class TestPost1PointTables:
    """P0400-STATICPLOTS (PFS-2105.015): at VINF = 0 the plots table's coefficients read NA.

    Rescaled by (VREF / VINF)^2 they cannot be; the table kept the VREF
    normalisation in silence while the definition says the free stream's.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-STATICPLOTS")])
    def test_p0400_staticplots_coefficients_are_na_and_said(tmp_path):
        """P0400-STATICPLOTS: CL and CDI columns NA, forces kept, and one warning."""
        export = _POST_1_POINT_TABLES___PLOTS.replace(
            "Freestream velocity (m/s)                   49.036",
            "Freestream velocity (m/s)                   .000",
        )
        assert export != _POST_1_POINT_TABLES___PLOTS
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            table = write_plots_table(tmp_path / "P1_plots.csv", export, pol="1")
        assert table is not None
        _columns, rows = _post_1_point_tables__read_csv_table(table)
        assert {row["CL_MRP_TOTAL"] for row in rows} == {"NA"}
        assert {row["CDI_MRP_TOTAL"] for row in rows} == {"NA"}
        assert [row["FX_MRP_TOTAL"] for row in rows] != ["NA", "NA"]
        assert any("free-stream velocity of 0 m/s" in str(w.message) for w in caught), caught


_POST_1_POLAR___B_CDP = "+0.0000333"


def _post_1_polar___log_of(tmp_path, monkeypatch, *, b_printed_at_zero: bool) -> list[str]:
    import tests.tier1_offline.test_post_superfile as sf

    setup: dict[str, Any] = copy.deepcopy(sf._SOLVER_SETUP)
    setup["flags"]["SET_VORTICITY_DRAG_BOUNDARIES"] = dict(_POST_1_POLAR___EVERY_BOUNDARY)
    assert sf._LOADS.count("CL, CDi, CDo,") == 1
    loads = sf._LOADS.replace("CL, CDi, CDo,", "CL, CDp, CDv,")
    if b_printed_at_zero:
        assert loads.count(_POST_1_POLAR___B_CDP) == 1
        loads = loads.replace(_POST_1_POLAR___B_CDP, "+0.0000000")
    monkeypatch.setattr(sf, "_LOADS", loads)
    monkeypatch.setattr(sf, "_SOLVER_SETUP", setup)
    workspace = sf._workspace(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sf._post(workspace)
    log = (workspace.products_dir("matriz") / "post.log").read_text(encoding="utf-8")
    return [line for line in log.splitlines() if "CDp exactly 0" in line]


class TestPost1Polar:
    """P0400-DECLINED125 (PFS-2085.021): a declined surface on 26.125 prints CDp 0 and is warned.

    RPT-166 (D-01, D-01c): on 26.125 a surface with no trailing edge on the vorticity
    induced-drag list prints CDp exactly 0, as earlier builds print CDi 0. The rule
    reads CDi, which a 26.125 export does not print, so such a surface got numbers
    in its axis drag columns and nothing said the solver had not computed them.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-DECLINED125")])
    def test_p0400_declined125_a_listed_surface_at_cdp_zero_is_warned(tmp_path, monkeypatch):
        """P0400-DECLINED125: every point warns, naming the surface and the build 26.125."""
        said = _post_1_polar___log_of(tmp_path, monkeypatch, b_printed_at_zero=True)
        assert len(said) >= 2, said
        assert all("build 26.125" in line and "exactly 0 for B, on the" in line for line in said), (
            said
        )

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-DECLINED125")])
    def test_p0400_declined125_a_listed_surface_with_a_cdp_is_not_warned(tmp_path, monkeypatch):
        """P0400-DECLINED125: a listed surface printing a real CDp was computed, so no warning."""
        assert _post_1_polar___log_of(tmp_path, monkeypatch, b_printed_at_zero=False) == []


class TestPost1ProbeFields:
    """P0400-FIELDREFUSAL (PFS-2096.021): an overwrite refusal arrives before any write.

    write_probe_field tested each format's pair on its own, so an existing .dat
    refused after the .vtk pair had already been written.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-FIELDREFUSAL")])
    def test_p0400_fieldrefusal_writes_nothing_when_one_destination_exists(tmp_path):
        """P0400-FIELDREFUSAL: field.dat exists; field.vtk and its record are not written."""
        setup = helpers.solver_settings(Script(version="26.120"), velocity=30.0)
        provenance = OutputProvenance(run_id="probe/sim_1/a+00.0", setup=setup)
        source = tmp_path / "samples.csv"
        source.write_text("PROBE,X,Y,Z", encoding="utf-8")
        (tmp_path / "field.dat").write_text("earlier", encoding="utf-8")
        points = np.array([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        velocity = np.array([[30.0, 0.0, 0.0], [30.0, 0.0, 0.0]])
        with pytest.raises(OutputExistsError):
            write_probe_field(
                tmp_path / "field",
                points,
                velocity,
                source=source,
                provenance=provenance,
                formats=("vtk", "tecplot"),
            )
        assert sorted(path.name for path in tmp_path.iterdir()) == ["field.dat", "samples.csv"]


class TestPost1SectionDistributions:
    """P0400 section-distribution defects (post-1 lane).

    P0400-EXTENDEDSTRIPS (PFS-2081.40): the integrated sectional loads put the
    strip edges half a spacing beyond the end stations, which the export places at
    strip centers; a uniform load integrates to its whole span.
    P0400-BUILDERQUIET (PFS-2100.014): the export builder's run-time warnings are
    collected at every builder call of the section-distribution matching, never
    written by the post stage.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-EXTENDEDSTRIPS")])
    def test_p0400_extendedstrips_a_uniform_load_integrates_to_its_span():
        """P0400-EXTENDEDSTRIPS: four stations at strip centers of [0, 1], Fx = 1 N/m: 1 N."""
        stations = [[r, 1.0, 0.25, 0.0, 1.0, 2.0, 0.5] for r in (0.125, 0.375, 0.625, 0.875)]
        strips = _integrated_strips(stations)
        assert [strip[0] for strip in strips] == pytest.approx([0.25] * 4)
        assert sum(strip[1] for strip in strips) == pytest.approx(1.0)
        assert sum(strip[2] for strip in strips) == pytest.approx(2.0)
        assert sum(strip[3] for strip in strips) == pytest.approx(0.5)

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-WINDOWSTEPS")])
    def test_p0400_windowsteps_a_stamped_step_outside_the_window_is_named_not_tabled(
        tmp_path, monkeypatch
    ):
        """P0400-WINDOWSTEPS (PFS-2105.039): window 3 to 5; a leftover step 9 is skipped by name."""
        from tests.tier1_offline.test_f07_section_distributions import _post, _workspace

        workspace, _record = _workspace(tmp_path, monkeypatch, stamped=True)
        sim = workspace.sim_dir("7001")
        for kind in ("_sloads", "_cp"):
            stamped = sim / f"AL-020{kind}_iteration=5.txt"
            (sim / f"AL-020{kind}_iteration=9.txt").write_text(
                stamped.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
            )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out, manifest = _post(workspace)
        tables = sorted((out / "sections").glob("AL-020_sloads_*.csv"))
        assert tables
        from pyflightstream.post.products import read_csv_table

        for table in tables:
            steps = {row["STEP"] for row in read_csv_table(table)[1]}
            assert steps == {"3", "4", "5"}, (table.name, steps)
        named = [key for key in manifest["skipped"] if key.endswith("#step=9")]
        assert named and all(
            "outside the record's export window" in manifest["skipped"][k] for k in named
        )

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-BUILDERQUIET")])
    def test_p0400_builderquiet_no_builder_warning_reaches_the_post(tmp_path, monkeypatch):
        """P0400-BUILDERQUIET: a warning the builder raises during matching stays the builder's."""
        real_emissions = distributions.pproc_emissions
        real_select = distributions.select_families
        said: list[str] = []

        def emissions(*args, **kwargs):
            said.append("emissions")
            warn("BUILDER-WARNING emissions", PyflightstreamWarning)
            return real_emissions(*args, **kwargs)

        def select(*args, **kwargs):
            said.append("select")
            warn("BUILDER-WARNING select", PyflightstreamWarning)
            return real_select(*args, **kwargs)

        monkeypatch.setattr(distributions, "pproc_emissions", emissions)
        monkeypatch.setattr(distributions, "select_families", select)
        workspace = _post_1_section_distributions___case(tmp_path, monkeypatch)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            path, _columns, _rows = _post_1_section_distributions___table(workspace)
        assert said, "the matching reached no builder call"
        log = (path.parent.parent / "post.log").read_text(encoding="utf-8")
        assert "BUILDER-WARNING" not in log
        assert not [w for w in caught if "BUILDER-WARNING" in str(w.message)]


class TestPost1Series:
    """P0400-TABLEDSTEPS (PFS-2105.038): the sections series lists only the steps it tabled.

    A step whose export declares zero sections has a file and no row; the
    manifest's ``steps_tabled`` listed it all the same.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-TABLEDSTEPS")])
    def test_p0400_tableddsteps_a_step_of_no_section_is_not_listed(tmp_path, monkeypatch):
        """P0400-TABLEDSTEPS: step 4 declares no section; steps_tabled is [3, 5]."""
        workspace, _record = _post_1_series___workspace(tmp_path, monkeypatch, stamped=True)
        step = workspace.sim_dir("7001") / "AL-020_sloads_iteration=4.txt"
        text = step.read_text(encoding="utf-8")
        emptied = re.sub(r"(Number of Surface Sections:\s*)\d+", r"\g<1>0", text)
        assert emptied != text
        step.write_text(emptied, encoding="utf-8", newline="\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _out, manifest = _post_1_series___post(workspace)
        (entry,) = [
            value
            for key, value in manifest["products"].items()
            if key.endswith("_sections_series.csv")
        ]
        assert entry["steps_tabled"] == [3, 5], entry


class TestPost1SettingsTable:
    """P0400-WIDEFILL (PFS-2105.019): the wide settings table never carries the fill sentinel.

    The fill reached the tidy code columns before the wide projection read them,
    so a list-valued flag's ``f<id>_value`` became 999 in place of its length.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-WIDEFILL")])
    def test_p0400_widefill_a_list_flag_keeps_its_length():
        """P0400-WIDEFILL: SET_VORTICITY_DRAG_BOUNDARIES (an empty list) reads 0, never 999."""
        (row,) = settings_table([_post_1_settings_table__snapshot()], wide=True, fill=999)
        selection = FLAG_IDS["SET_VORTICITY_DRAG_BOUNDARIES"]
        assert row[f"f{selection}_value"] == 0
        assert 999 not in [value for key, value in row.items() if key.endswith("_value")]


_POST_1_SUPERFILE___PPROC = """[sections]
[[sections.distributions]]
families = "W"
frame = "MRP"
planes = ["XZ"]
count = 10

[[sections.distributions]]
families = "T"
frame = "MRP"
planes = ["XY"]
count = 20
"""


def _post_1_superfile___script(*counts: int) -> str:
    return "".join(
        f"NEW_SURFACE_SECTION_DISTRIBUTION\nFRAME 1\nNUM_SECTIONS {count}\n" for count in counts
    )


def _post_1_superfile___measured(
    tmp_path, *counts: int, layout=None, pproc=_POST_1_SUPERFILE___PPROC
) -> dict:
    import hashlib

    (tmp_path / "inputs" / "pproc").mkdir(parents=True)
    (tmp_path / "inputs" / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8")
    (tmp_path / "sims" / "sim_1").mkdir(parents=True)
    (tmp_path / "sims" / "sim_1" / "P1.txt").write_text(
        _post_1_superfile___script(*counts), encoding="utf-8"
    )
    record = {"sim_id": "1", "pproc": "p001", "run_id": "camp/sim_1/P1", "script_path": "P1.txt"}
    record["script_sha256"] = hashlib.sha256(
        (tmp_path / "sims" / "sim_1" / "P1.txt").read_bytes()
    ).hexdigest()
    if layout is not None:
        record["sections_layout"] = layout
    (case,) = measure_sections(tmp_path, [record])
    return case


@pytest.mark.parametrize(
    "digest", ["0" * 64, ""], ids=["P0430-F-482-changed", "P0430-F-482-absent"]
)
def test_p0430_sections_measurement_rejects_changed_script(tmp_path, digest):
    _post_1_superfile___measured(tmp_path, 10)
    record = {
        "sim_id": "1",
        "run_id": "point",
        "script_path": "P1.txt",
        "sections_layout": [{"count": 10}],
        "script_sha256": digest,
    }
    assert measure_sections(tmp_path, [record]) == []


@pytest.mark.parametrize((), [pytest.param(id="P0430-F-787")])
def test_p0430_sections_count_cannot_cross_a_block_boundary(tmp_path):
    import hashlib

    _post_1_superfile___measured(tmp_path, 10, 10)
    path = tmp_path / "sims" / "sim_1" / "P1.txt"
    path.write_text(
        "NEW_SURFACE_SECTION_DISTRIBUTION\nFRAME 1\n"
        "NEW_SURFACE_SECTION_DISTRIBUTION\nFRAME 2\nNUM_SECTIONS 10\n",
        encoding="utf-8",
    )
    record = {
        "sim_id": "1",
        "run_id": "point",
        "script_path": "P1.txt",
        "sections_layout": [{"count": 10}, {"count": 10}],
        "script_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (case,) = measure_sections(tmp_path, [record])
    assert case["emitted"] != case["expected"]
    assert case["blocks"] == 2


@pytest.mark.parametrize(
    "kind", ["csv", "force_distributions"], ids=["P0430-F-1369-surface", "P0430-F-1369-force"]
)
def test_p0430_retabled_exports_state_polar_and_condition(tmp_path, kind):
    from types import SimpleNamespace

    from pyflightstream.post import point_tables
    from pyflightstream.post._tables import CONTEXT_COLUMNS, ReferenceValues, read_csv_table
    from tests.tier1_offline.test_results import read_fixture

    fixture, output, native_columns = (
        ("solver_analysis_26.123.csv", "DP.csv", ("x", "y", "z", "scalar"))
        if kind == "csv"
        else (
            "force_distributions_26.123.txt",
            "DP_force_distributions.txt",
            ("Boundary", "X", "Y", "Z", "Cx", "Cy", "Cz", "Cxv", "Cyv", "Czv"),
        )
    )
    (tmp_path / output).write_text(read_fixture(fixture), encoding="utf-8")
    written = []
    ctx = SimpleNamespace(
        points=[SimpleNamespace(name="DP")],
        sim_id="42",
        record_of={
            "DP": SimpleNamespace(
                outputs=[output],
                package_version="0.42.0",
                sim_id="42",
                fs_version_requested="26.123",
            )
        },
        workspace=SimpleNamespace(sim_dir=lambda _: tmp_path),
        out=tmp_path,
        sources={"DP": ["run"]},
        skipped={},
        target=lambda path: path,
        add=lambda path, entry: written.append(path),
        condition=lambda point: {"ALPHA": 7.0},
        reference=ReferenceValues(2.0, 3.0, 4.0),
    )
    point_tables.export_tables(ctx)
    columns, rows = read_csv_table(written[0])
    assert list(columns) == ["POL", *CONTEXT_COLUMNS, *native_columns]
    assert rows[0]["POL"] == "42"
    assert float(rows[0]["ALPHA"]) == 7.0
    assert float(rows[0]["SREF"]) == 2.0
    assert len(rows) > 1


class TestPost1Superfile:
    """P0400-PERENTRYCOUNT (PFS-2105.021): measure_sections reads each entry's own count.

    Compared with one artifact-wide number, a script whose entries ask 10 and 20
    sections was reported as a disagreement (-1) although it emitted what was asked.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
    def test_p0400_perentrycount_a_correct_script_agrees(tmp_path):
        """P0400-PERENTRYCOUNT: entries of 10 and 20, blocks of 10 and 20: expected == emitted."""
        case = _post_1_superfile___measured(tmp_path, 10, 20)
        assert case["expected"] == case["emitted"] == [10, 20], case

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
    def test_p0400_perentrycount_a_wrong_block_still_disagrees(tmp_path):
        """P0400-PERENTRYCOUNT: the control, a block of 15 where 20 was asked, disagrees."""
        case = _post_1_superfile___measured(tmp_path, 10, 15)
        assert case["expected"] != case["emitted"], case

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
    def test_p0400_perentrycount_each_plane_and_duplicate_block_is_counted(tmp_path):
        """P0400-PERENTRYCOUNT: two planes of the first entry require two blocks of ten."""
        pproc = _POST_1_SUPERFILE___PPROC.replace('planes = ["XZ"]', 'planes = ["XZ", "XY"]')
        case = _post_1_superfile___measured(tmp_path, 10, 20, pproc=pproc)
        assert case["expected"] == [10, 10, 20]
        assert case["expected"] != case["emitted"]

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-PERENTRYCOUNT")])
    def test_p0400_perentrycount_recorded_layout_wins_over_edited_artifact(tmp_path):
        """P0400-PERENTRYCOUNT: the run recorded fifteen, even if the live file now says ten."""
        case = _post_1_superfile___measured(tmp_path, 15, layout=[{"count": 15, "plane": "XZ"}])
        assert case["expected"] == case["emitted"] == [15]


class TestPost1Tables:
    """P0400 table-helper defects (post-1 lane).

    P0400-NAMEDGROUP (PFS-2095.044): the recorded file-name helpers refuse a
    named group with a ProductError, never a bare ValueError.
    P0400-SKIPLINE (PFS-2100.013): read_csv_table names the file's own line when
    it skips lines before the header.
    """

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-NAMEDGROUP")])
    def test_p0400_namedgroup_is_a_product_error():
        """P0400-NAMEDGROUP: a group named WING is refused by both helpers, by name."""
        assert polar_file_name(7, 0.2, "3") == "7_M20_g03.csv"
        with pytest.raises(ProductError, match="'WING'"):
            polar_file_name(7, 0.2, "WING")
        with pytest.raises(ProductError, match="'WING'"):
            custom_polar_file_name(7, mach=0.2, group="WING")

    @staticmethod
    @pytest.mark.parametrize((), [pytest.param(id="P0400-SKIPLINE")])
    def test_p0400_skipline_names_the_files_line(tmp_path):
        """P0400-SKIPLINE: with skip=1 the short first data row is file line 3."""
        table = tmp_path / "rotor.csv"
        table.write_text("PUSHER\nPOL,CT\n1\n", encoding="utf-8")
        with pytest.raises(ProductError, match="line 3 carries 1 values"):
            _post_1_tables__read_csv_table(table, skip=1)


# --------------------------------------------------------------------------- F4-0102 tables
def _march_export(steps, values=None):
    from pyflightstream.post._tables import _PlotsExport

    values = np.asarray(
        [[float(s), 0.1 * s] for s in steps] if values is None else values, dtype=float
    )
    rows = [f"{row[0]:.4f},{row[1]:.5f}," for row in values]
    return _PlotsExport(
        head=[],
        rows=rows,
        tail=[],
        columns=("Time-step", "CL"),
        values=values,
        steps=np.asarray(steps, dtype=int),
        scale=(None, None),
    )


def _march_history_of(export):
    return (export.rows, export.values, export.steps)


def test_f135_a_seam_with_missing_solver_steps_is_not_joined():
    """F-135: steps 5 and 6 are in neither run, so the exports are not one history."""
    from pyflightstream.post._tables import _join

    assert _join(_march_history_of(_march_export([1, 2, 3, 4])), _march_export([7, 8, 9])) is None
    joined = _join(_march_history_of(_march_export([1, 2, 3, 4])), _march_export([5, 6]))
    assert joined is not None and list(joined[0][2]) == [1, 2, 3, 4, 5, 6]


def test_f136_a_shorter_restatement_keeps_the_later_steps_and_the_march_end():
    """F-136: a restatement of steps 1 to 4 leaves steps 5 to 8 of the history in place."""
    from pyflightstream.post._tables import _join

    joined = _join(_march_history_of(_march_export(range(1, 9))), _march_export(range(1, 5)))
    assert joined is not None
    (rows, values, steps), _how = joined
    assert list(steps) == list(range(1, 9)) and len(rows) == 8 and len(values) == 8


def test_f173_nan_cells_do_not_make_a_restated_march_a_new_one():
    """F-173: a NaN the history and its restatement both carry is a match, not a difference."""
    from pyflightstream.post._tables import _join

    values = [[1.0, 0.1], [2.0, math.nan], [3.0, 0.3], [4.0, 0.4]]
    joined = _join(
        _march_history_of(_march_export([1, 2, 3, 4], values)),
        _march_export([1, 2, 3, 4], values),
    )
    assert joined is not None
    assert list(joined[0][2]) == [1, 2, 3, 4] and "restating" in joined[1]


def test_f174_a_chain_with_an_older_run_missing_leaves_the_continuations_own_export(tmp_path):
    """F-174: the history of the run before the middle one is gone, so no partial chain."""
    from types import SimpleNamespace

    from pyflightstream.post._tables import _march_history
    from pyflightstream.results import parse_unsteady_plots
    from tests.tier1_offline.test_restart_continuation import (
        _fr96_converged_continuation___export as export,
    )

    out = ["outputs/AL-020_plots.txt"]
    first = SimpleNamespace(continues=None, run_id="camp/sim_7001/AL-020", outputs=out)
    middle = SimpleNamespace(
        continues=first.run_id,
        run_id="camp/sim_7001/r20261001-110000/AL-020",
        outputs=out,
        recipe="unsteady",
    )
    last = SimpleNamespace(
        continues=middle.run_id,
        run_id="camp/sim_7001/r20261001-120000/AL-020",
        outputs=out,
        recipe="unsteady",
    )
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "AL-020_plots.txt").write_text(export(range(9, 13)), "utf-8")
    archive = tmp_path / "outputs" / "archive" / "20261001-120000"
    archive.mkdir(parents=True)
    (archive / "AL-020_plots.txt").write_text(export(range(5, 9)), "utf-8")
    manifest = {r.run_id: r for r in (first, middle, last)}
    march = _march_history(tmp_path, last, manifest)
    assert march is not None and "Not joined" in march.said
    steps = [int(v) for v in parse_unsteady_plots(march.text).values[:, 0]]
    assert steps == [9, 10, 11, 12]


def test_f134_a_rotor_that_states_its_blade_count_spaces_a_sector_by_it():
    """F-134: two blades of a four-blade rotor sit a quarter turn apart, not half."""
    from pyflightstream.post._tables import _own_blade_azimuth

    rotor = {"blade_families": [["B1"], ["B2"]], "blades": 4}
    assert _own_blade_azimuth(["B2"], rotor, 0.0) == pytest.approx(90.0)
    assert _own_blade_azimuth(["B2"], {"blade_families": [["B1"], ["B2"]]}, 0.0) == (
        pytest.approx(180.0)
    )


def test_f170_the_shared_csv_funnel_writes_infinities_as_na(tmp_path):
    """F-170: inf and -inf are not cells a table can state."""
    path = write_csv_table(tmp_path / "t.csv", ("A", "B", "C"), [(math.inf, -math.inf, 1.5)])
    assert path.read_text(encoding="utf-8").splitlines()[1] == "NA,NA,1.50000"


def test_f1364_two_columns_cannot_receive_the_same_new_name():
    """F-1364: renaming A and B to X would lose a value on reading."""
    from pyflightstream.post._tables import renamed_columns

    with pytest.raises(ProductError, match="two columns the name X"):
        renamed_columns(("A", "B"), {"A": "X", "B": "X"}, printed=("A", "B"), where="w")


def test_f1378_the_plots_reader_takes_the_historical_dash_as_na(tmp_path):
    """F-1378: a table written by an earlier release states a dash, which readers accept."""
    path = tmp_path / "p.csv"
    path.write_text("POL,Time-step,CL\n1,1,-\n1,2,0.5\n", encoding="utf-8")
    _columns, series = plots_table_series(path)
    assert math.isnan(series.fields["CL"][0, 0]) and series.fields["CL"][1, 0] == 0.5


def test_f1379_a_header_only_plots_table_is_a_named_product_error(tmp_path):
    """F-1379: no incidental IndexError for a table with no time step."""
    path = tmp_path / "p.csv"
    path.write_text("POL,Time-step,CL\n", encoding="utf-8")
    with pytest.raises(ProductError, match="no rows"):
        plots_table_series(path)


def test_pfs_2121_004_a_continued_points_march_is_joined_once_per_post(tmp_path, monkeypatch):
    """PFS-2121.004: the records and the plots table read one march, not two."""
    from pyflightstream.post import _tables
    from tests.tier1_offline.test_restart_continuation import (
        _fr96_converged_continuation___continued_workspace as continued,
    )
    from tests.tier1_offline.test_restart_continuation import (
        _fr96_converged_continuation___posted as posted,
    )

    calls = []
    original = _tables._march_history

    def counting(*args, **kwargs):
        calls.append(args[1].run_id)
        return original(*args, **kwargs)

    monkeypatch.setattr(_tables, "_march_history", counting)
    posted(continued(tmp_path, "numbered on"))
    assert len(calls) == len(set(calls)) == 1, calls
