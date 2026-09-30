"""Tier 1, 0.31.0: the quasi-steady wheel's correction machinery (P0310-CAL, routes 1 to 4).

The owner's decisions this file holds: the release ships the MACHINE, every
route is an option OFF by default and NOT VALIDATED; the corrected products are
written BESIDE the raw ones, never over them; route 1 (the Theodorsen and Sears
lift deficiency) is a DIAGNOSTIC only; route 3 (a skewed-wake or dynamic-inflow
model) is REFUSED as a correction; routes 2 (a 0P offset from an axial unsteady
SECTOR run) and 4 (a calibration table the user fitted) are applied by the one
applicator; and everything runs at post, with no solver run.

EVERY EXPECTED NUMBER is worked here from the definitions: the interpolation of
a trilinear function inside a 2 x 2 x 2 grid is that function; the corrected
section is the raw row plus the change of its 0P and 1P terms, computed from the
raw row and the written harmonic product; the route 2 offsets are the difference
of the two rotor table rows turned into newtons with ``rho n^2 D^4``. Nothing
expected is read off the module under test.
"""

from __future__ import annotations

import hashlib
import json
import math
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import PprocSpec
from pyflightstream.cases.corrections import (
    COMPONENTS,
    SECTION_COMPONENTS,
    CalibrationError,
    CalibrationRow,
    QsteadyCorrectionSpec,
    calibration_text,
    parse_calibration,
    read_calibration,
)
from pyflightstream.exceptions import CalibrationError as CataloguedCalibrationError
from pyflightstream.post.corrections import (
    CALIBRATION_SHA256_COLUMN,
    CORRECTION_ROUTE_COLUMN,
    bessel_j,
    bessel_y,
    sears,
    sector_offset_calibration,
    theodorsen,
)
from pyflightstream.post.products import read_csv_table
from pyflightstream.workspace import INPUT_KINDS, CampaignWorkspace, RunRecord

# ---------------------------------------------------------------- helpers


def _row(component: str, j: float, alpha: float, k: float, *coefficients: float) -> str:
    offset, gain_0p, gain_1p, phase = coefficients
    return (
        "\n[[rows]]\n"
        f'COMPONENT = "{component}"\nJ = {j}\nALPHA = {alpha}\nK_1P = {k}\n'
        f"OFFSET_0P = {offset}\nGAIN_0P = {gain_0p}\nGAIN_1P = {gain_1p}\n"
        f"PHASE_1P_DEG = {phase}\n"
    )


def _trilinear(j: float, alpha: float, k: float) -> float:
    """A function multilinear interpolation reproduces exactly: bilinear in J and ALPHA."""
    return 1.0 + 2.0 * j + 0.5 * alpha + 10.0 * k + j * alpha


def _grid_text() -> str:
    text = 'route = "table"\n'
    for j in (0.4, 0.8):
        for alpha in (0.0, 4.0):
            for k in (0.02, 0.1):
                text += _row("THRUST", j, alpha, k, _trilinear(j, alpha, k), 1.0, 1.0, 0.0)
    return text


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------ the calibration file (schema)


def test_init_creates_the_calibrations_folder_like_the_free_streams(tmp_path):
    """``inputs/calibrations/`` is an input kind, so init creates it."""
    # P0310-CAL-SCHEMA
    assert "calibrations" in INPUT_KINDS
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    assert (workspace.inputs_dir / "calibrations").is_dir()


def test_inside_a_2x2x2_grid_the_coefficients_are_interpolated_multilinearly():
    """At (J, ALPHA, K_1P) = (0.5, 1.0, 0.04) the trilinear offset is 3.4 exactly.

    1 + 2 (0.5) + 0.5 (1.0) + 10 (0.04) + 0.5 (1.0) = 3.4, and the cell used is
    the one grid cell bracketing the point on each axis.
    """
    # P0310-CAL-SCHEMA
    calibration = parse_calibration(_grid_text())
    found = calibration.lookup("THRUST", {"J": 0.5, "ALPHA": 1.0, "K_1P": 0.04})
    assert found is not None and found.coefficients is not None
    assert found.coefficients[0] == pytest.approx(3.4, abs=1e-12)
    assert found.coefficients[1:] == pytest.approx((1.0, 1.0, 0.0), abs=1e-12)
    assert dict(found.cell) == {"J": [0.4, 0.8], "ALPHA": [0.0, 4.0], "K_1P": [0.02, 0.1]}
    # A node gives its own row back, and a face point the mean of its two nodes.
    node = calibration.lookup("THRUST", {"J": 0.8, "ALPHA": 4.0, "K_1P": 0.1})
    assert node.coefficients[0] == pytest.approx(_trilinear(0.8, 4.0, 0.1), abs=1e-12)
    face = calibration.lookup("THRUST", {"J": 0.6, "ALPHA": 0.0, "K_1P": 0.02})
    assert face.coefficients[0] == pytest.approx(_trilinear(0.6, 0.0, 0.02), abs=1e-12)


@pytest.mark.parametrize(
    ("at", "axis"),
    [
        ({"J": 0.39, "ALPHA": 1.0, "K_1P": 0.04}, "J"),
        ({"J": 0.5, "ALPHA": 4.5, "K_1P": 0.04}, "ALPHA"),
        ({"J": 0.5, "ALPHA": 1.0, "K_1P": 0.11}, "K_1P"),
    ],
)
def test_a_point_outside_the_grid_is_never_extrapolated(at, axis):
    """Outside on any axis: no coefficients, and the reason names the axis."""
    # P0310-CAL-SCHEMA
    found = parse_calibration(_grid_text()).lookup("THRUST", at)
    assert found is not None and found.coefficients is None and found.outside
    assert f"{axis} = " in found.reason and "never extrapolated" in found.reason


def test_an_axis_with_one_value_is_constant_and_constrains_nothing():
    """A grid over J alone applies at any ALPHA and K_1P, even with none stated."""
    # P0310-CAL-SCHEMA
    text = 'route = "table"\n' + _row("CT", 0.5, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0)
    text += _row("CT", 0.7, 0.0, 0.0, 3.0, 1.0, 1.0, 0.0)
    found = parse_calibration(text).lookup("CT", {"J": 0.65, "ALPHA": 9.0})
    assert found.coefficients[0] == pytest.approx(2.5, abs=1e-12)
    assert dict(found.cell) == {"J": [0.5, 0.7], "ALPHA": [0.0], "K_1P": [0.0]}
    unknown = parse_calibration(text).lookup("CT", {"ALPHA": 0.0})
    assert unknown.coefficients is None and "states no J" in unknown.reason


_GOOD = 'route = "table"\n' + _row("THRUST", 0.5, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0)


@pytest.mark.parametrize(
    ("text", "line", "words"),
    [
        (_GOOD.replace('"table"', '"lookup"'), 1, "unknown route 'lookup'"),
        (_GOOD.replace('"THRUST"', '"THRUSTS"'), 4, "unknown component 'THRUSTS'"),
        (_GOOD.replace("GAIN_1P = 1.0\n", ""), 3, "missing column(s) GAIN_1P"),
        (_GOOD.replace("GAIN_1P = 1.0", "GAIN_1P = nan"), 10, "not a finite number"),
        (_GOOD.replace("OFFSET_0P = 1.0", "OFFSET_0P = inf"), 8, "not a finite number"),
        (_GOOD.replace("J = 0.5", "J = 0.5\nRPM = 3.0"), 6, "unknown column 'RPM'"),
        (_GOOD + _row("THRUST", 0.5, 0.0, 0.0, 2.0, 1.0, 1.0, 0.0), 13, "duplicate row"),
        (
            _GOOD
            + _row("THRUST", 0.7, 0.0, 0.0, 2.0, 1.0, 1.0, 0.0)
            + _row("THRUST", 0.5, 2.0, 0.0, 2.0, 1.0, 1.0, 0.0),
            23,
            "not a grid",
        ),
        ('route = "sector_offset"\n' + _GOOD.split("\n", 1)[1], 1, "must name source_run_id"),
    ],
)
def test_a_calibration_that_cannot_be_read_is_refused_naming_the_line(text, line, words):
    """Each refusal is the catalogued error, naming the line it points at."""
    # P0310-CAL-SCHEMA
    with pytest.raises(CalibrationError) as caught:
        parse_calibration(text)
    assert isinstance(caught.value, CataloguedCalibrationError)
    assert caught.value.line == line
    assert f"line {line}:" in str(caught.value) and words in str(caught.value)
    # The control: the unbroken file reads.
    assert parse_calibration(_GOOD).components == ("THRUST",)


def test_the_component_vocabulary_holds_the_section_export_names():
    """The sectional components are the load columns the sectional export prints."""
    # P0310-CAL-SCHEMA
    from pyflightstream.results.tables import _SECTIONAL_COLUMN_UNITS

    loads = {name for name in _SECTIONAL_COLUMN_UNITS if name not in ("Offset", "Chord")}
    assert set(SECTION_COMPONENTS) == loads - {"X_QC", "Z_QC"}
    assert {"THRUST", "TORQUE", "CT", "CQ", "CN", "CS", "CMN", "CMS"} <= set(COMPONENTS)


def test_the_pproc_table_is_off_by_default_and_forbids_unknown_keys():
    """``[qsteady_correction]``: route and diagnostic default to none; a route names its file."""
    # P0310-CAL-SCHEMA
    assert PprocSpec().qsteady_correction is None
    spec = PprocSpec.model_validate({"qsteady_correction": {}}).qsteady_correction
    assert (spec.route, spec.file, spec.diagnostic) == ("none", None, "none")
    stated = {"route": "table", "file": "c001", "diagnostic": "theodorsen"}
    assert PprocSpec.model_validate({"qsteady_correction": stated}).qsteady_correction == (
        QsteadyCorrectionSpec(**stated)
    )
    for wrong, words in (
        ({"route": "table"}, "names no file"),
        ({"route": "table", "file": "c001", "gain": 2.0}, "gain"),
        ({"route": "table", "file": "calibrations/c001.toml"}, "by its id"),
        ({"diagnostic": "sears_only"}, "diagnostic"),
    ):
        with pytest.raises(ValidationError, match=words):
            PprocSpec.model_validate({"qsteady_correction": wrong})


def test_a_calibration_file_may_be_named_with_or_without_its_toml_suffix(tmp_path):
    """``c001`` and ``c001.toml`` name one file; a folder is still refused."""
    # P0310-CAL-SCHEMA
    from types import SimpleNamespace

    from pyflightstream.workspace.matrix import _validate_qsteady_calibration

    bare, suffixed = (
        PprocSpec.model_validate(
            {"qsteady_correction": {"route": "table", "file": spelled}}
        ).qsteady_correction
        for spelled in ("c001", "c001.toml")
    )
    assert bare == suffixed and suffixed is not None and suffixed.file == "c001"
    for folder in ("calibrations/c001.toml", "calibrations\\c001", "../c001.toml", ".toml"):
        with pytest.raises(ValidationError, match="by its id"):
            QsteadyCorrectionSpec(route="table", file=folder)
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "calibrations" / "c001.toml").write_text(_GOOD, encoding="utf-8")
    row = SimpleNamespace(pol="7001", pproc_code="p001")
    for spelled in ("c001", "c001.toml"):
        pproc = PprocSpec.model_validate(
            {"qsteady_correction": {"route": "table", "file": spelled}}
        )
        assert _validate_qsteady_calibration(workspace, pproc, row) is None


def test_the_plan_refuses_a_calibration_the_pproc_names_and_cannot_read(tmp_path):
    """The binding reads the named file before a run: absent, broken or of another route."""
    # P0310-CAL-SCHEMA
    from types import SimpleNamespace

    from pyflightstream.workspace import InputArtifactError
    from pyflightstream.workspace.matrix import _validate_qsteady_calibration

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    row = SimpleNamespace(pol="7001", pproc_code="p001")
    pproc = PprocSpec.model_validate({"qsteady_correction": {"route": "table", "file": "c001"}})
    with pytest.raises(InputArtifactError, match="c001"):
        _validate_qsteady_calibration(workspace, pproc, row)
    path = workspace.inputs_dir / "calibrations" / "c001.toml"
    path.write_text(_GOOD.replace('"THRUST"', '"THRUSTS"'), encoding="utf-8")
    with pytest.raises(CalibrationError, match="line 4"):
        _validate_qsteady_calibration(workspace, pproc, row)
    path.write_text('route = "sector_offset"\nsource_run_id = "x"\n' + _GOOD.split("\n", 1)[1])
    with pytest.raises(CalibrationError, match="asks route 'table'") as mismatch:
        _validate_qsteady_calibration(workspace, pproc, row)
    # The refusal names both fixes: the route that matches the file, or a file
    # of the route asked.
    assert "route = 'sector_offset' to match the calibration" in str(mismatch.value)
    assert "a calibration of route 'table'" in str(mismatch.value)
    path.write_text(_GOOD, encoding="utf-8")
    assert _validate_qsteady_calibration(workspace, pproc, row) is None
    assert _validate_qsteady_calibration(workspace, PprocSpec(), row) is None


# ---------------------------------------------- routes 1 and 3 are refused


@pytest.mark.parametrize("route", ["theodorsen", "Theodorsen", "sears", "theodorsen-sears"])
def test_route_1_is_refused_as_a_correction_and_named_a_diagnostic(route, tmp_path):
    """In the pproc and in a calibration, route 1 is refused as a diagnostic only."""
    # P0310-ROUTE1-DIAGNOSTIC
    with pytest.raises(ValidationError, match="DIAGNOSTIC only"):
        PprocSpec.model_validate({"qsteady_correction": {"route": route, "file": "c001"}})
    with pytest.raises(CalibrationError, match="DIAGNOSTIC only") as caught:
        parse_calibration(_GOOD.replace('"table"', f'"{route}"'))
    assert caught.value.line == 1
    # The reason is what the package holds, not a measurement no committed
    # report records (the 0.31.0 release review): not validated, diagnostic only.
    assert "not validated against the unsteady solver" in str(caught.value)
    assert "sign" not in str(caught.value)
    assert PprocSpec.model_validate(
        {"qsteady_correction": {"diagnostic": "theodorsen"}}
    ).qsteady_correction.diagnostic == ("theodorsen")


@pytest.mark.parametrize("route", ["dynamic_inflow", "skewed_wake", "pitt_peters", "coleman"])
def test_route_3_is_refused_because_its_double_counting_is_unmeasured(route):
    """A skewed-wake or dynamic-inflow route is not offered, in the pproc or in a file."""
    # P0310-ROUTE3-REFUSED
    words = "double counting with the solver's own wake is unmeasured"
    with pytest.raises(ValidationError, match=words):
        PprocSpec.model_validate({"qsteady_correction": {"route": route, "file": "c001"}})
    with pytest.raises(CalibrationError, match=words):
        parse_calibration(_GOOD.replace('"table"', f'"{route}"'))


# ------------------------------------------------ route 1 as a diagnostic


def test_the_bessel_functions_hold_to_1e_10_against_scipy():
    """J0, J1, Y0 and Y1 over the reduced frequencies a rotor has, and far beyond."""
    # P0310-ROUTE1-DIAGNOSTIC
    special = pytest.importorskip("scipy.special")
    worst = 0.0
    for x in [1e-6, 1e-3, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 12.5, 29.9, 30.1, 45.0, 200.0]:
        for order in (0, 1):
            for mine, theirs in (
                (bessel_j(order, x), special.jv(order, x)),
                (bessel_y(order, x), special.yv(order, x)),
            ):
                worst = max(worst, abs(mine - theirs) / max(1.0, abs(theirs)))
    assert worst < 1e-10


def test_theodorsen_and_sears_are_their_closed_forms():
    """C(1) = 0.5394 - 0.1003 i (the classical table), and S(k) = 2 / (pi k (H0 - i H1))."""
    # P0310-ROUTE1-DIAGNOSTIC
    assert theodorsen(1.0).real == pytest.approx(0.5394, abs=5e-5)
    assert theodorsen(1.0).imag == pytest.approx(-0.1003, abs=5e-5)
    assert theodorsen(0.0) == 1.0 and sears(0.0) == 1.0
    for k in (0.02, 0.1, 0.3, 1.0):
        h0 = complex(bessel_j(0, k), -bessel_y(0, k))
        h1 = complex(bessel_j(1, k), -bessel_y(1, k))
        assert abs(sears(k) - 2.0 / (math.pi * k * (h0 - 1j * h1))) < 1e-12
        assert theodorsen(k).imag < 0.0, "the lift deficiency lags"


# ------------------------------------------ the synthetic wheel (sections)


def _wheel_posted(
    tmp_path: Path, monkeypatch, *, correction: dict | None, calibration: str | None
) -> tuple[CampaignWorkspace, Path, dict, list[str]]:
    """The harmonics test's wheel: 3 blades at 2 clockings, loads of known harmonics."""
    from tests.tier1_offline.test_goal036_harmonics import _pproc, _wheel

    workspace = _wheel(tmp_path, monkeypatch, blades=3, clockings=2, rpm=1200.0)
    stated = _pproc(3).model_dump()
    if correction is not None:
        stated["qsteady_correction"] = correction
    pproc = PprocSpec.model_validate(stated)
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    if calibration is not None:
        (workspace.inputs_dir / "calibrations" / "c001.toml").write_text(
            calibration, encoding="utf-8"
        )
    from tests.tier1_offline.test_goal036_harmonics import _post

    out, manifest, log = _post(workspace)
    return workspace, out, manifest, log


#: The section calibration: over K_1P only, two values bracketing the stations
#: (their K_1P are 0.26083, 0.15486 and 0.10740), for Fx and Fz; Moment is not
#: named and passes unchanged.
_SECTION_COEFFICIENTS = {
    "Fx": {0.1: (0.5, 1.2, 0.8, 10.0), 0.3: (1.5, 1.0, 0.6, 30.0)},
    "Fz": {0.1: (-0.2, 1.0, 1.5, -20.0), 0.3: (0.2, 1.0, 1.5, -20.0)},
}


def _section_calibration(route: str = "table", low: float = 0.1) -> str:
    text = f'route = "{route}"\n'
    if route == "sector_offset":
        text += 'source_run_id = "camp/sim_7001/DP"\n'
    for component, by_k in _SECTION_COEFFICIENTS.items():
        for k, coefficients in by_k.items():
            text += _row(component, 0.5, 0.0, low if k == 0.1 else k, *coefficients)
    return text


def _coefficients(component: str, k: float) -> tuple[float, ...]:
    """Linear in K_1P between the two rows, by hand."""
    low, high = _SECTION_COEFFICIENTS[component][0.1], _SECTION_COEFFICIENTS[component][0.3]
    t = (k - 0.1) / 0.2
    return tuple(a + t * (b - a) for a, b in zip(low, high, strict=True))


@pytest.mark.parametrize("route", ["table", "sector_offset"])
def test_the_corrected_sections_are_the_raw_rows_plus_the_change_of_their_0p_and_1p_terms(
    tmp_path, monkeypatch, route
):
    """Every blade at every clocking, at its own AZIMUTH: the hand formula, to the print.

    load' = load + (H0' - H0) + [A1' cos(psi - PHI1') - A1 cos(psi - PHI1)], with
    H0' = GAIN_0P H0 + OFFSET_0P, A1' = GAIN_1P A1, PHI1' = PHI1 + PHASE_1P_DEG, the
    coefficients at the station's K_1P and the harmonics as the product wrote them.
    """
    # P0310-APPLY-SECTIONS
    # P0310-ROUTE4
    # P0310-ROUTE2
    _, out, manifest, _ = _wheel_posted(
        tmp_path,
        monkeypatch,
        correction={"route": route, "file": "c001"},
        calibration=_section_calibration(route),
    )
    _, raw = read_csv_table(out / "sections" / "DP_sections.csv")
    columns, corrected = read_csv_table(out / "sections" / "DP_sections_corrected.csv")
    _, harmonics = read_csv_table(out / "sections" / "DP_harmonics.csv")
    _, harmonics_corrected = read_csv_table(out / "sections" / "DP_harmonics_corrected.csv")
    fit = {(row["QUANTITY"], float(row["STATION_R_M"])): row for row in harmonics}
    assert len(raw) == len(corrected) == 3 * 2 * 3
    for before, after in zip(raw, corrected, strict=True):
        r, psi, k = float(before["Offset"]), float(before["AZIMUTH"]), float(before["K_1P"])
        for quantity in ("Fx", "Fz"):
            offset, gain_0p, gain_1p, phase = _coefficients(quantity, k)
            h = fit[(quantity, r)]
            h0, a1, phi1 = float(h["H0"]), float(h["H1_AMP"]), float(h["H1_PHASE_DEG"])
            expected = (
                float(before[quantity])
                + (gain_0p * h0 + offset - h0)
                + gain_1p * a1 * math.cos(math.radians(psi - (phi1 + phase)))
                - a1 * math.cos(math.radians(psi - phi1))
            )
            assert float(after[quantity]) == pytest.approx(expected, abs=1.5e-5)
        assert after["Moment"] == before["Moment"]
        assert after[CORRECTION_ROUTE_COLUMN] == route
    # The harmonic product, per station: H0' and A1' and PHI1'; A2 unchanged.
    for before, after in zip(harmonics, harmonics_corrected, strict=True):
        quantity = before["QUANTITY"]
        if quantity == "Moment":
            assert {key: after[key] for key in before} == before
            continue
        r = float(before["STATION_R_M"])
        k = float(next(row["K_1P"] for row in raw if float(row["Offset"]) == r))
        offset, gain_0p, gain_1p, phase = _coefficients(quantity, k)
        assert float(after["H0"]) == pytest.approx(gain_0p * float(before["H0"]) + offset, abs=1e-5)
        assert float(after["H1_AMP"]) == pytest.approx(gain_1p * float(before["H1_AMP"]), abs=1e-5)
        assert float(after["H1_PHASE_DEG"]) == pytest.approx(
            (float(before["H1_PHASE_DEG"]) + phase) % 360.0, abs=1e-4
        )
        for kept in ("H2_AMP", "H2_PHASE_DEG", "RESIDUAL_RMS", "SAMPLES"):
            assert after[kept] == before[kept]
    assert columns[-2:] == (CORRECTION_ROUTE_COLUMN, CALIBRATION_SHA256_COLUMN)
    assert manifest["products"]["sections/DP_sections_corrected.csv"]["route"] == route


def test_a_station_outside_the_grid_is_a_named_skip_and_a_warning(tmp_path, monkeypatch):
    """The grid starts at K_1P 0.12, so the station at 0.10740 is NA, skipped and warned."""
    # P0310-CAL-SCHEMA
    _, out, manifest, log = _wheel_posted(
        tmp_path,
        monkeypatch,
        correction={"route": "table", "file": "c001"},
        calibration=_section_calibration(low=0.12),
    )
    _, corrected = read_csv_table(out / "sections" / "DP_sections_corrected.csv")
    outer = [row for row in corrected if abs(float(row["Offset"]) - 0.9) < 1e-9]
    inner = [row for row in corrected if abs(float(row["Offset"]) - 0.3) < 1e-9]
    assert outer and all(row["Fx"] == "NA" and row["Fz"] == "NA" for row in outer)
    assert inner and all(row["Fx"] != "NA" for row in inner)
    key = "sections/DP_harmonics_corrected.csv#component=Fx"
    assert "outside the Fx grid" in manifest["skipped"][key]
    assert "never extrapolated" in manifest["skipped"][key]
    said = [line for line in log if line.startswith("WARNING") and "outside the Fx grid" in line]
    assert said and "point=DP" in said[0]


def test_the_raw_files_are_byte_identical_with_and_without_a_route(tmp_path, monkeypatch):
    """Hash every raw product of a post with no route and of one with a route and the diagnostic."""
    # P0310-APPLY-BESIDE
    _, plain, _, _ = _wheel_posted(tmp_path / "a", monkeypatch, correction=None, calibration=None)
    _, routed, manifest, _ = _wheel_posted(
        tmp_path / "b",
        monkeypatch,
        correction={"route": "table", "file": "c001", "diagnostic": "theodorsen"},
        calibration=_section_calibration(),
    )

    def hashes(folder: Path) -> dict[str, str]:
        return {
            path.relative_to(folder).as_posix(): _sha(path)
            for path in folder.rglob("*.csv")
            if not path.name.endswith(("_corrected.csv", "_theodorsen.csv"))
        }

    assert hashes(plain) == hashes(routed)
    assert {"sections/DP_sections.csv", "sections/DP_harmonics.csv"} <= set(hashes(plain))
    beside = {
        "sections/DP_sections_corrected.csv": "sections/DP_sections.csv",
        "sections/DP_harmonics_corrected.csv": "sections/DP_harmonics.csv",
    }
    for corrected, raw in beside.items():
        assert (routed / corrected).is_file() and manifest["products"][corrected]["raw"] == raw
    assert not list(plain.rglob("*_corrected.csv"))


def test_every_corrected_file_states_its_route_and_calibration_and_that_it_is_not_validated(
    tmp_path, monkeypatch
):
    """The two columns on every row, and the entry naming raw, route, file, sha256 and cells."""
    # P0310-APPLY-PROVENANCE
    workspace, out, manifest, _ = _wheel_posted(
        tmp_path,
        monkeypatch,
        correction={"route": "table", "file": "c001"},
        calibration=_section_calibration(),
    )
    sha = _sha(workspace.inputs_dir / "calibrations" / "c001.toml")
    for name in ("DP_sections_corrected.csv", "DP_harmonics_corrected.csv"):
        columns, rows = read_csv_table(out / "sections" / name)
        assert columns[-2:] == (CORRECTION_ROUTE_COLUMN, CALIBRATION_SHA256_COLUMN)
        assert {(row[CORRECTION_ROUTE_COLUMN], row[CALIBRATION_SHA256_COLUMN]) for row in rows} == {
            ("table", sha)
        }
        entry = manifest["products"][f"sections/{name}"]
        assert entry["kind"] == "corrected"
        assert entry["raw"] == f"sections/{name.replace('_corrected', '')}"
        assert entry["route"] == "table"
        assert entry["calibration"] == "inputs/calibrations/c001.toml"
        assert entry["calibration_sha256"] == sha
        assert entry["validation"] == "not validated" and "not validated" in entry["note"]
        assert entry["runs"] == ["camp/sim_7001/DP"]
        cells = {(cell["component"], json.dumps(cell["cell"])) for cell in entry["cells"]}
        assert ("Fx", json.dumps({"J": [0.5], "ALPHA": [0.0], "K_1P": [0.1, 0.3]})) in cells


def test_the_theodorsen_diagnostic_sits_beside_the_harmonics_and_corrects_nothing(
    tmp_path, monkeypatch
):
    """Per station K_1P, |C|, its phase, |S|, its phase, beside the measured 1P amplitude."""
    # P0310-ROUTE1-DIAGNOSTIC
    special = pytest.importorskip("scipy.special")
    _, out, manifest, _ = _wheel_posted(
        tmp_path, monkeypatch, correction={"diagnostic": "theodorsen"}, calibration=None
    )
    assert not list(out.rglob("*_corrected.csv")), "a diagnostic is never applied"
    columns, rows = read_csv_table(out / "sections" / "DP_theodorsen.csv")
    _, sections = read_csv_table(out / "sections" / "DP_sections.csv")
    _, harmonics = read_csv_table(out / "sections" / "DP_harmonics.csv")
    assert columns[:2] == ("POL", "ALPHA")
    assert len(rows) == len(harmonics) == 9
    for row, fit in zip(rows, harmonics, strict=True):
        r = float(row["STATION_R_M"])
        k = float(next(s["K_1P"] for s in sections if float(s["Offset"]) == r))
        h0, h1 = special.hankel2(0, k), special.hankel2(1, k)
        c = h1 / (h1 + 1j * h0)
        s = 2.0 / (math.pi * k * (h0 - 1j * h1))
        assert float(row["K_1P"]) == pytest.approx(k, abs=1e-12)
        assert float(row["C_ABS"]) == pytest.approx(abs(c), abs=1e-5)
        assert float(row["C_PHASE_DEG"]) == pytest.approx(
            math.degrees(math.atan2(c.imag, c.real)), abs=1e-5
        )
        assert float(row["S_ABS"]) == pytest.approx(abs(s), abs=1e-5)
        assert float(row["S_PHASE_DEG"]) == pytest.approx(
            math.degrees(math.atan2(s.imag, s.real)), abs=1e-5
        )
        assert (row["H1_AMP"], row["H1_PHASE_DEG"]) == (fit["H1_AMP"], fit["H1_PHASE_DEG"])
    entry = manifest["products"]["sections/DP_theodorsen.csv"]
    assert entry["kind"] == "theodorsen" and entry["source"] == "sections/DP_harmonics.csv"
    assert "never applied as a correction" in entry["diagnostic"]


# -------------------------------------- the recorded wheel (the 0P tables)


def _recorded_wheel(tmp_path: Path, *, pproc_extra: str = "", files: dict | None = None):
    """Polar 6001 of the recorded campaign as a wheel of two clockings at 1200 rev/min.

    The rotor-mean test's fixture, with the pproc's own lines and the
    calibrations written before the post.
    """
    from tests.tier1_offline.test_goal035_l1_defects import _PROP_REFERENCE
    from tests.tier1_offline.test_goal036_rotor_mean import _W_ROW, _w_row
    from tests.tier1_offline.test_post_superfile import _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _PROP_REFERENCE, encoding="utf-8"
    )
    for pproc in ("p001", "p002"):
        path = workspace.inputs_dir / "pproc" / f"{pproc}.toml"
        path.write_text(path.read_text(encoding="utf-8") + pproc_extra, encoding="utf-8")
    for name, text in (files or {}).items():
        (workspace.inputs_dir / "calibrations" / name).write_text(text, encoding="utf-8")
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            loads = workspace.sim_dir("6001") / record.outputs[0]
            recorded = loads.read_text(encoding="utf-8")
            positions = []
            for index, stated in enumerate(((0.0193288, 0.01), (0.0293288, 0.03))):
                path = loads if index == 0 else loads.with_name(f"{loads.stem}_qs{index:02d}.txt")
                path.write_text(recorded.replace(_W_ROW, _w_row(*stated)), encoding="utf-8")
                positions.append(
                    {"index": index, "clocking_deg": 90.0 * index, "rotated_deg": 90.0 * index}
                    | {"loads": path.name}
                )
            quasi = {
                "schema_version": 1,
                "run_type": "qsteady_rotor",
                "case": "wheel",
                "rotor": "PROP",
                "blades": 2,
                "rpm": 1200.0,
                "shaft_frame_axis": "X",
                "hub_m": [0.0, 0.0, 0.0],
                "axis_vector": [1.0, 0.0, 0.0],
                "diameter_m": 2.0,
                "families_general": [],
                "families_blades": ["W", "B"],
                "blade1_azimuth_deg": 0.0,
                "positions": positions,
                "validity": None,
            }
            loads.with_name(loads.stem + "_qsteady.json").write_text(json.dumps(quasi))
            record = record.model_copy(update={"recipe": "qsteady_rotor"})
        workspace.append_record(RunRecord(**record.model_dump()))
    return workspace


def _post_recorded(workspace) -> tuple[dict, Path, list[str]]:
    from tests.tier1_offline.test_post_superfile import _post

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        _post(workspace)
    # A second post archives the previous manifest under archive/ (FR-293);
    # the live one is outside it.
    (manifest,) = [p for p in workspace.root.rglob("products.json") if "archive" not in p.parts]
    log = (manifest.parent / "post.log").read_text(encoding="utf-8").splitlines()
    return json.loads(manifest.read_text(encoding="utf-8")), manifest.parent, log


def _zero_p_calibration() -> str:
    """CT, CQ, THRUST and TORQUE over ALPHA in [-4, 4]: gain 1.1, offset a + b ALPHA."""
    text = 'route = "table"\n'
    for component, a, b in (
        ("CT", 0.001, 0.0005),
        ("CQ", 0.0002, 0.00001),
        ("THRUST", 5.0, 1.0),
        ("TORQUE", 1.0, 0.25),
    ):
        for alpha in (-4.0, 4.0):
            text += _row(component, 1.7, alpha, 0.0, a + b * alpha, 1.1, 1.0, 0.0)
    return text


def _offset(component: str, alpha: float) -> float:
    a, b = {"CT": (0.001, 0.0005), "CQ": (0.0002, 0.00001), "THRUST": (5.0, 1.0)}[component]
    return a + b * alpha


def _table(folder: Path, name: str) -> list[dict[str, str]]:
    return read_csv_table(folder / name)[1]


def test_route_4_corrects_the_rotor_and_average_tables_beside_them(tmp_path):
    """q' = GAIN_0P q + OFFSET_0P at each row's ALPHA; what is derived from them is NA."""
    # P0310-ROUTE4
    # P0310-APPLY-BESIDE
    extra = '\n[qsteady_correction]\nroute = "table"\nfile = "c001"\n'
    workspace = _recorded_wheel(
        tmp_path, pproc_extra=extra, files={"c001.toml": _zero_p_calibration()}
    )
    products, folder, _ = _post_recorded(workspace)
    (rotor,) = [name for name in products["products"] if name.endswith("PROP_rotor.csv")]
    (average,) = [name for name in products["products"] if name.endswith("PROP_qs_avg.csv")]
    for raw_name, pairs, derived in (
        (rotor, {"CT_PROP": "CT", "CQ_PROP": "CQ"}, ("CP_PROP", "ETA_PROP", "ETAW_PROP")),
        (
            average,
            {"THRUST_PROP": "THRUST", "CT_PROPELLER": "CT"},
            ("CT_ROTOR", "LAMBDA_I", "CHI_DEG"),
        ),
    ):
        corrected_name = raw_name.replace(".csv", "_corrected.csv")
        raw, corrected = _table(folder, raw_name), _table(folder, corrected_name)
        assert len(raw) == len(corrected) == 2
        for before, after in zip(raw, corrected, strict=True):
            alpha = float(before["ALPHA"])
            for column, component in pairs.items():
                if before[column] == "NA":
                    assert after[column] == "NA"
                    continue
                assert float(after[column]) == pytest.approx(
                    1.1 * float(before[column]) + _offset(component, alpha), abs=1.5e-5
                )
            for column in derived:
                assert after[column] == "NA", column
            assert (
                after["CN_PROP" if raw_name == rotor else "FX_W"]
                == (before["CN_PROP" if raw_name == rotor else "FX_W"])
            )
        entry = products["products"][corrected_name]
        assert entry["raw"] == raw_name and entry["validation"] == "not validated"
        assert set(derived) <= set(entry["derived_na"])
        assert {cell["cell"]["ALPHA"][0] for cell in entry["cells"]} == {-4.0}


def test_route_2_helper_builds_the_offsets_from_a_recorded_sector_and_the_post_applies_them(
    tmp_path,
):
    """OFFSET = sector - wheel at the same J: 0.002 of CT is 0.002 rho n^2 D^4 = 15.68 N.

    rho = 1.225, n = 20 rev/s, D = 2 m: rho n^2 D^4 = 7840 and rho n^2 D^5 = 15680, so
    a CQ 0.0003 higher is 4.704 N m. The sector point is the wheel's axial row with
    its CT and CQ raised, recorded as a run of its own.
    """
    # P0310-CAL-ROUTE2-RUNID
    # P0310-ROUTE2
    workspace = _recorded_wheel(tmp_path)
    products, folder, _ = _post_recorded(workspace)
    (rotor,) = [name for name in products["products"] if name.endswith("PROP_rotor.csv")]
    runs = products["products"][rotor]["runs"]
    wheel_run = next(run for run in runs if "AL+000" in run)
    columns, rows = read_csv_table(folder / rotor)
    axial = dict(rows[runs.index(wheel_run)])
    sector = dict(
        axial,
        **{
            "CT_PROP": f"{float(axial['CT_PROP']) + 0.002:.5f}",
            "CQ_PROP": f"{float(axial['CQ_PROP']) + 0.0003:.5f}",
            "POL": "6003",
        },
    )
    (folder / "polars" / "P6003-PROP_rotor.csv").write_text(
        ",".join(columns) + "\n" + ",".join(sector[c] for c in columns) + "\n", encoding="utf-8"
    )
    sector_run = "camp/sim_6003/SECTOR"
    record = next(r for r in workspace.read_manifest() if r.run_id == wheel_run)
    workspace.append_record(
        RunRecord(**{**record.model_dump(), "run_id": sector_run, "sim_id": "6003", "recipe": None})
    )
    # Its export, where a sweep table of the workspace reads it.
    for output in record.outputs:
        copied = workspace.sim_dir("6003") / output
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes((workspace.sim_dir("6001") / output).read_bytes())
    products["products"]["polars/P6003-PROP_rotor.csv"] = {"runs": [sector_run], "rotor": "PROP"}
    (folder / "products.json").write_text(json.dumps(products), encoding="utf-8")

    path = sector_offset_calibration(
        workspace,
        wheel_run_id=wheel_run,
        sector_run_id=sector_run,
        calibration_id="c002",
        matrix_stem="matriz",
    )
    assert path == workspace.inputs_dir / "calibrations" / "c002.toml"
    calibration = read_calibration(path)
    assert calibration.route == "sector_offset"
    assert (calibration.source_run_id, calibration.wheel_run_id) == (sector_run, wheel_run)
    offsets = {row.component: row for row in calibration.rows}
    assert offsets["THRUST"].offset_0p == pytest.approx(15.68, abs=1e-9)
    assert offsets["TORQUE"].offset_0p == pytest.approx(4.704, abs=1e-9)
    assert offsets["CT"].offset_0p == pytest.approx(0.002, abs=1e-12)
    assert offsets["CQ"].offset_0p == pytest.approx(0.0003, abs=1e-12)
    assert {(row.gain_0p, row.gain_1p, row.phase_1p_deg) for row in calibration.rows} == {
        (1.0, 1.0, 0.0)
    }
    assert offsets["CT"].j == pytest.approx(float(axial["J_PROP"]), abs=1e-12)
    # A second call does not write over it, and a run of another J is refused.
    with pytest.raises(CalibrationError, match="exists"):
        sector_offset_calibration(
            workspace,
            wheel_run_id=wheel_run,
            sector_run_id=sector_run,
            calibration_id="c002",
            matrix_stem="matriz",
        )
    tilted = next(run for run in runs if run != wheel_run)
    with pytest.raises(CalibrationError, match="axial flow"):
        sector_offset_calibration(
            workspace,
            wheel_run_id=tilted,
            sector_run_id=sector_run,
            calibration_id="c003",
            matrix_stem="matriz",
        )
    # The post applies the file as route 2, the offset at every ALPHA of the wheel.
    for pproc in ("p001", "p002"):
        stated = workspace.inputs_dir / "pproc" / f"{pproc}.toml"
        stated.write_text(
            stated.read_text(encoding="utf-8")
            + '\n[qsteady_correction]\nroute = "sector_offset"\nfile = "c002"\n',
            encoding="utf-8",
        )
    products, folder, log = _post_recorded(workspace)
    (average,) = [name for name in products["products"] if name.endswith("PROP_qs_avg.csv")]
    raw = _table(folder, average)
    corrected = _table(folder, average.replace(".csv", "_corrected.csv"))
    for before, after in zip(raw, corrected, strict=True):
        assert float(after["THRUST_PROP"]) == pytest.approx(
            float(before["THRUST_PROP"]) + 15.68, abs=1.5e-5
        )
        assert float(after["TORQUE_PROP"]) == pytest.approx(
            float(before["TORQUE_PROP"]) + 4.704, abs=1.5e-5
        )
    entry = products["products"][average.replace(".csv", "_corrected.csv")]
    assert entry["route"] == "sector_offset" and entry["source_run_id"] == sector_run
    assert not [line for line in log if "is not a run of this workspace" in line]


def test_route_2_warns_when_its_sector_run_is_not_in_runs_json(tmp_path):
    """The file names a run the workspace never recorded: warned, and applied as stated."""
    # P0310-CAL-ROUTE2-RUNID
    text = 'route = "sector_offset"\nsource_run_id = "camp/sim_9999/NOPE"\n'
    text += _row("THRUST", 1.7, 0.0, 0.0, 2.0, 1.0, 1.0, 0.0)
    extra = '\n[qsteady_correction]\nroute = "sector_offset"\nfile = "c009"\n'
    workspace = _recorded_wheel(tmp_path, pproc_extra=extra, files={"c009.toml": text})
    products, folder, log = _post_recorded(workspace)
    said = [line for line in log if line.startswith("WARNING") and "camp/sim_9999/NOPE" in line]
    assert said and "is not a run of this workspace's runs.json" in said[0]
    (average,) = [name for name in products["products"] if name.endswith("PROP_qs_avg.csv")]
    raw = _table(folder, average)
    corrected = _table(folder, average.replace(".csv", "_corrected.csv"))
    assert [float(row["THRUST_PROP"]) for row in corrected] == pytest.approx(
        [float(row["THRUST_PROP"]) + 2.0 for row in raw], abs=1.5e-5
    )


def test_the_calibration_text_reads_back_to_the_same_rows():
    """The writer the route 2 helper uses is read back unchanged."""
    # P0310-CAL-ROUTE2-RUNID
    rows = [CalibrationRow("THRUST", 0.6, 0.0, 0.0, 15.68, 1.0, 1.0, 0.0)]
    text = calibration_text("sector_offset", rows, source_run_id='a "quoted" run')
    read = parse_calibration(text)
    assert read.source_run_id == 'a "quoted" run'
    assert [row.coefficients() for row in read.rows] == [(15.68, 1.0, 1.0, 0.0)]
