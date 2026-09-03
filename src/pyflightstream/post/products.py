"""The campaign's post-processed products: polar, section and plot tables as CSV.

PFS-2029.15. A campaign's raw exports are the solver's own text files, one
set per point; the products are the tables a study reads and plots, and
this module writes them as plain CSV, one header line and one row per
record, so any spreadsheet or dataframe reads them with nothing else:

* a POLAR table per boundary GROUP of the pproc artifact,
  ``<polar>_M<mach code>_g<group>.csv``: one row per point of the polar,
  the reference block and the coefficients of the group in body, stability
  and wind axes with the two drag parts;
* a SECTIONS table per point, ``sections/<point>_sections.csv``: the
  sectional loads export re-tabled, when the run defined sections at all;
* a PLOTS table per unsteady point, ``plots/<point>_plots.csv``: the
  unsteady plots export re-tabled, its coefficient columns brought from
  the solver's reference velocity to the free stream.

THE ARITHMETIC IS THE AUTHOR'S, re-derived here from her recorded files and
never imported: the coefficient columns were checked one by one against
her recorded polar tables and the loads tables they came from
(2026-09-02). FlightStream's ``CL``, ``CDi + CDo`` and ``Cy`` are the
STABILITY-axis coefficients; the body axes follow by turning them through
the angle of attack, the wind axes by turning the stability axes through
the sideslip; the rolling and yawing moments are the solver's ``CMx`` and
``CMz`` scaled from the chord to the span and, by her sign convention,
negated. Values are written at five decimals, her precision, so a table
regenerated from the same exports is equal text. The parity arm of
GOAL-011 regenerates her recorded polars and sections through
:func:`write_recorded_polar` and compares them with her own tables,
converted to this shape outside the package.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream.fsi.loads import SectionalLoadsReport, parse_sectional_loads
from pyflightstream.results import (
    LoadsReport,
    MalformedOutputError,
    UnsteadyPlotsReport,
    labeled_value,
    parse_loads,
    parse_unsteady_plots,
)

if TYPE_CHECKING:
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

__all__ = [
    "COEFFICIENT_COLUMNS",
    "POLAR_COLUMNS",
    "SECTION_COLUMNS",
    "GroupCoefficients",
    "PolarPoint",
    "ProductError",
    "ReferenceValues",
    "group_coefficients",
    "polar_file_name",
    "polar_row",
    "read_csv_table",
    "write_csv_table",
    "write_plots_table",
    "write_polar_table",
    "write_campaign_products",
    "write_recorded_polar",
    "write_sections_table",
]

#: The twenty-four coefficient columns of a polar row, in her order: the
#: point, the body axes, the stability axes, the wind axes, the two drag
#: parts. ``RE`` is the Reynolds number in millions.
COEFFICIENT_COLUMNS: tuple[str, ...] = (
    "ALPHA",
    "BETA",
    "MACH",
    "RE",
    "CDB",
    "CYB",
    "CLB",
    "CRB25",
    "CMB25",
    "CNB25",
    "CDS",
    "CYS",
    "CLS",
    "CRS25",
    "CMS25",
    "CNS25",
    "CDW",
    "CYW",
    "CLW",
    "CRW25",
    "CMW25",
    "CNW25",
    "CD0",
    "CDI",
)

#: The reference block every product row carries in front of its values,
#: so a row is self-describing: which polar, which group, which reference.
REFERENCE_COLUMNS: tuple[str, ...] = ("SREF", "CREF", "BREF", "XMOM", "YMOM", "ZMOM")

#: A polar table's columns: the polar, its description, the group, the
#: reference block, the twenty-four coefficients.
POLAR_COLUMNS: tuple[str, ...] = (
    "POLAR",
    "DESCRIPTION",
    "GROUP",
    *REFERENCE_COLUMNS,
    *COEFFICIENT_COLUMNS,
)

#: A sections table's columns: the point and its condition, then the
#: sectional loads export's own seven columns, in its units.
SECTION_COLUMNS: tuple[str, ...] = (
    "POINT",
    "ALPHA",
    "BETA",
    "MACH",
    "VINF",
    "RE",
    "ALT",
    "Offset",
    "Chord",
    "X_QC",
    "Z_QC",
    "Fx",
    "Fz",
    "Moment",
)

#: The plot-column prefixes that are coefficients, which the solver
#: normalises by its reference velocity and the product by the free stream.
COEFFICIENT_PLOT_PREFIXES = ("CL_", "CDI_", "CDO_", "CD_")

#: Decimals written for every coefficient and section value, her precision.
DECIMALS = 5


class ProductError(PyflightstreamError, ValueError):
    """A product cannot be written from what the run left."""


@dataclass(frozen=True)
class ReferenceValues:
    """The reference block of a product: SREF, CREF, BREF and the moment point."""

    sref_m2: float
    cref_m: float
    bref_m: float
    xmom_m: float = 0.0
    ymom_m: float = 0.0
    zmom_m: float = 0.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, float]) -> ReferenceValues:
        """Read the block from a mapping keyed by the column names."""
        try:
            return cls(
                sref_m2=float(values["SREF"]),
                cref_m=float(values["CREF"]),
                bref_m=float(values["BREF"]),
                xmom_m=float(values.get("XMOM", 0.0)),
                ymom_m=float(values.get("YMOM", 0.0)),
                zmom_m=float(values.get("ZMOM", 0.0)),
            )
        except KeyError as missing:
            raise ProductError(
                f"the reference block needs {missing.args[0]}; it carries {sorted(values)}"
            ) from missing

    def as_row(self) -> tuple[float, ...]:
        """Return the six values in :data:`REFERENCE_COLUMNS` order."""
        return (self.sref_m2, self.cref_m, self.bref_m, self.xmom_m, self.ymom_m, self.zmom_m)


@dataclass(frozen=True)
class GroupCoefficients:
    """The stability-axis coefficients of one group, summed over its families.

    ``roll`` and ``yaw`` are already scaled from the chord to the span and
    carry her sign, so they are the body-axis rolling and yawing moments
    the polar row writes.
    """

    drag: float
    side: float
    lift: float
    roll: float
    pitch: float
    yaw: float
    drag_profile: float
    drag_induced: float
    families_used: tuple[str, ...]


@dataclass(frozen=True)
class PolarPoint:
    """One point of a polar: its loads report and where it came from."""

    name: str
    loads: LoadsReport
    loads_path: Path

    @property
    def alpha_deg(self) -> float:
        """The point's angle of attack, from its loads table."""
        return self.loads.angle_of_attack_deg

    @property
    def beta_deg(self) -> float:
        """The point's sideslip, from its loads table."""
        return self.loads.sideslip_deg


def group_coefficients(
    loads: LoadsReport, families: Sequence[str], *, bref_m: float
) -> GroupCoefficients:
    """Sum the loads table's rows over the families of one group.

    A family the table does not carry is left out, as her writer left it
    out; a group none of whose families is in the table sums to zero,
    which is what her products carry for the propeller groups of a
    wing-body polar. The rolling and yawing moments are the solver's
    ``CMx`` and ``CMz``, scaled from the reference chord to the span and
    negated, her convention.
    """
    cref = loads.reference_length
    if cref is None:
        raise ProductError("the loads table states no reference length, so no span scaling")
    drag = side = lift = roll = pitch = yaw = profile = induced = 0.0
    used: list[str] = []
    for family in families:
        row = loads.surfaces.get(str(family))
        if row is None:
            continue
        used.append(str(family))
        drag += row["CDi"] + row["CDo"]
        side += row["Cy"]
        lift += row["CL"]
        roll -= row["CMx"] * cref / bref_m
        pitch += row["CMy"]
        yaw -= row["CMz"] * cref / bref_m
        profile += row["CDo"]
        induced += row["CDi"]
    return GroupCoefficients(drag, side, lift, roll, pitch, yaw, profile, induced, tuple(used))


def polar_row(
    alpha_deg: float,
    mach: float,
    reynolds_millions: float,
    coefficients: GroupCoefficients,
    *,
    cref_m: float,
    bref_m: float,
) -> tuple[float, ...]:
    """Return the twenty-four coefficient values of one polar row.

    The sideslip her polars wrote is zero on every row, whatever the run
    stated: her tables carried ``BETA 0.0`` and the wind axes coincide with
    the stability axes, and this writer keeps that so the numbers are hers.
    """
    beta_deg = 0.0
    a = math.radians(alpha_deg)
    b = math.radians(beta_deg)
    g = coefficients
    cds, cys, cls = g.drag, g.side, g.lift
    crb, cmb, cnb = g.roll, g.pitch, g.yaw
    cdb = cds * math.cos(a) - cls * math.sin(a)
    cyb = cys
    clb = cds * math.sin(a) + cls * math.cos(a)
    crs = crb * math.cos(a) + cnb * math.sin(a)
    cms = cmb
    cns = -crb * math.sin(a) + cnb * math.cos(a)
    cdw = cds * math.cos(b) - cys * math.sin(b)
    cyw = cds * math.sin(b) + cys * math.cos(b)
    clw = cls
    crw = crs * math.cos(b) + cms * math.sin(b) * cref_m / bref_m
    cmw = -crs * math.sin(b) * bref_m / cref_m + cms * math.cos(b)
    cnw = cns
    return (
        alpha_deg, beta_deg, mach, reynolds_millions,
        cdb, cyb, clb, crb, cmb, cnb,
        cds, cys, cls, crs, cms, cns,
        cdw, cyw, clw, crw, cmw, cnw,
        g.drag_profile, g.drag_induced,
    )  # fmt: skip


def mach_code(mach: float) -> int:
    """Return the two-digit Mach code of her file names: ``round(mach * 100)``."""
    return round(mach * 100)


def polar_file_name(polar: str | int, mach: float, group: str | int) -> str:
    """``<polar>_M<mach code:02d>_g<group:02d>.csv``: one polar table per group."""
    return f"{polar}_M{mach_code(mach):02d}_g{int(group):02d}.csv"


def _cell(value: object) -> str:
    """One CSV cell: floats at five decimals, everything else as written."""
    if isinstance(value, float | np.floating):
        return f"{float(value):.{DECIMALS}f}"
    return str(value)


def write_csv_table(
    path: str | Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> Path:
    """Write one CSV table: a header line and one line per row, floats at five decimals."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            if len(row) != len(columns):
                raise ProductError(f"a row has {len(row)} values for {len(columns)} columns")
            writer.writerow([_cell(value) for value in row])
    return target


def read_csv_table(path: str | Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Read one CSV table back: its columns and its rows as mappings of text.

    Values come back as the text written, so a caller decides what is a
    number; a row whose width differs from the header is refused naming
    the line, which is what makes the round trip a proof.
    """
    target = Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            columns = tuple(next(reader))
        except StopIteration:
            raise ProductError(f"{target} is empty; a table has at least its header") from None
        rows = []
        for number, cells in enumerate(reader, start=2):
            if len(cells) != len(columns):
                raise ProductError(
                    f"{target} line {number} carries {len(cells)} values for {len(columns)} columns"
                )
            rows.append(dict(zip(columns, cells, strict=True)))
    return columns, rows


def write_polar_table(
    path: str | Path,
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
) -> Path:
    """Write one polar table: the reference block and the coefficients per point."""
    lead = (str(polar), description, str(group), *reference.as_row())
    full = []
    for row in rows:
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
        full.append((*lead, *row))
    return write_csv_table(path, POLAR_COLUMNS, full)


def _reynolds_millions(text: str) -> float:
    return float(labeled_value(text, "Reynolds Number")) / 1e6


def _altitude_ft(text: str) -> float:
    try:
        return float(labeled_value(text, "Altitude (ft)"))
    except (MalformedOutputError, ValueError):
        return 0.0


def write_sections_table(
    path: str | Path, export_text: str, *, point: str, mach: float
) -> Path | None:
    """Write one sections table from a sectional loads export.

    Returns None without writing when the export declares no section, as
    a run that defined no distribution leaves; the columns are the point,
    its condition, and the export's own seven, in the export's units.
    """
    # A run that defined no distribution leaves an export declaring zero
    # sections, which the parser refuses as impossible for a real table;
    # here it is the ordinary case of a steady polar and means no product.
    try:
        declared = int(float(labeled_value(export_text, "Number of Surface Sections:")))
    except (MalformedOutputError, ValueError):
        declared = -1
    if declared == 0:
        return None
    try:
        report: SectionalLoadsReport = parse_sectional_loads(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the sectional loads export cannot be read: {error}") from error
    if report.count == 0:
        return None
    table = np.asarray(report.values, dtype=float)
    if table.shape[1] < 7:
        raise ProductError(
            f"the sectional loads export carries {table.shape[1]} columns, fewer than the seven "
            "the product tables"
        )
    lead = (
        point,
        report.angle_of_attack_deg,
        report.sideslip_deg,
        mach,
        report.freestream_velocity_m_s,
        _reynolds_millions(export_text),
        _altitude_ft(export_text),
    )
    rows = [(*lead, *(float(v) for v in row[:7])) for row in table]
    return write_csv_table(path, SECTION_COLUMNS, rows)


def write_plots_table(path: str | Path, export_text: str) -> Path | None:
    """Write one plots table from an unsteady plots export.

    The coefficient columns (``CL_``, ``CDI_``, ``CDO_``, ``CD_``) are
    multiplied by the square of the reference velocity over the free
    stream, so a run whose reference velocity differs from the free stream
    reads as free-stream coefficients. An export the reader cannot parse is
    a refusal naming the file, never a silent skip; an export with no step
    returns None.
    """
    try:
        report: UnsteadyPlotsReport = parse_unsteady_plots(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the unsteady plots export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    vinf = float(labeled_value(export_text, "Freestream velocity (m/s)"))
    try:
        vref = float(labeled_value(export_text, "Reference velocity (m/s)"))
    except (MalformedOutputError, ValueError):
        vref = vinf
    scale = (vref / vinf) ** 2 if vinf else 1.0
    scaled = values.copy()
    for index, name in enumerate(report.columns):
        if name.startswith(COEFFICIENT_PLOT_PREFIXES):
            scaled[:, index] *= scale
    return write_csv_table(
        path, tuple(report.columns), [tuple(float(v) for v in row) for row in scaled]
    )


def _polar_points(polar_dir: Path, *, loads_suffix: str = ".txt") -> list[PolarPoint]:
    """Return the points of a recorded polar: one folder per point, its loads table inside."""
    points: list[PolarPoint] = []
    for folder in sorted(p for p in polar_dir.iterdir() if p.is_dir()):
        loads_path = folder / f"{folder.name}{loads_suffix}"
        if not loads_path.is_file():
            continue
        text = loads_path.read_text(encoding="utf-8", errors="replace")
        try:
            report = parse_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{loads_path} is not a loads table: {error}") from error
        points.append(PolarPoint(name=folder.name, loads=report, loads_path=loads_path))
    if not points:
        raise ProductError(f"{polar_dir} holds no point folder with a loads table")
    return sorted(points, key=lambda point: point.alpha_deg)


def polar_rows(
    points: Sequence[PolarPoint],
    families: Sequence[str],
    *,
    mach: float,
    reference: ReferenceValues,
) -> list[tuple[float, ...]]:
    """Return the coefficient rows of one group over the points of a polar, alpha ascending."""
    rows = []
    for point in points:
        reynolds = point.loads.reynolds
        if reynolds is None:
            raise ProductError(f"{point.loads_path} states no Reynolds number")
        coefficients = group_coefficients(point.loads, list(families), bref_m=reference.bref_m)
        rows.append(
            polar_row(
                point.alpha_deg,
                mach,
                reynolds / 1e6,
                coefficients,
                cref_m=reference.cref_m,
                bref_m=reference.bref_m,
            )
        )
    return rows


def write_recorded_polar(
    polar_dir: str | Path,
    out_dir: str | Path,
    *,
    groups: Mapping[str, Sequence[str]],
    reference: Mapping[str, float] | ReferenceValues,
    description: str,
    mach: float,
    sections: bool = True,
    plots: bool = False,
) -> list[Path]:
    """Write every product of one recorded polar from its point folders.

    ``polar_dir`` is ``POLAR-<n>/`` holding one folder per point, each with
    the point's loads table ``<point>.txt`` and, when the run left them, the
    sectional loads ``<point>_sloads.txt`` and the plots ``<point>_plots.txt``.
    One polar table is written per group of ``groups`` (the pproc
    artifact's ``[groups]`` table, name to families), a sections table per
    point whose export declares sections, and, when asked, a plots table
    per point that has a plots export. Returns the paths written, in order.
    """
    polar_dir = Path(polar_dir)
    out = Path(out_dir)
    ref = (
        reference
        if isinstance(reference, ReferenceValues)
        else ReferenceValues.from_mapping(reference)
    )
    polar = polar_dir.name.split("-")[-1] if polar_dir.name.startswith("POLAR-") else polar_dir.name
    points = _polar_points(polar_dir)
    written: list[Path] = []
    for group, families in groups.items():
        written.append(
            write_polar_table(
                out / polar_file_name(polar, mach, group),
                polar=polar,
                description=description,
                group=group,
                reference=ref,
                rows=polar_rows(points, list(families), mach=mach, reference=ref),
            )
        )
    for point in points:
        folder = point.loads_path.parent
        sloads = folder / f"{point.name}_sloads.txt"
        if sections and sloads.is_file():
            target = write_sections_table(
                out / "sections" / f"{point.name}_sections.csv",
                sloads.read_text(encoding="utf-8", errors="replace"),
                point=point.name,
                mach=mach,
            )
            if target is not None:
                written.append(target)
        plots_export = folder / f"{point.name}_plots.txt"
        if plots and plots_export.is_file():
            target = write_plots_table(
                out / "plots" / f"{point.name}_plots.csv",
                plots_export.read_text(encoding="utf-8", errors="replace"),
            )
            if target is not None:
                written.append(target)
    return written


# --- PFS-2029.15.03: the products of a campaign, from its manifest ---------------

#: The manifest of the products: which file came from which runs and pproc.
PRODUCTS_MANIFEST = "products.json"


def _sim_products(
    workspace: CampaignWorkspace,
    sim_id: str,
    records: Sequence[RunRecord],
    out: Path,
    *,
    overwrite: bool,
) -> tuple[list[Path], dict[str, list[str]]]:
    """Write one simulation's products from its successful records."""
    from pyflightstream.cases import classify_outputs

    first = records[0]
    pproc_id = getattr(first, "pproc", None)
    if pproc_id is None:
        return [], {}
    pproc = workspace.resolve_pproc(pproc_id)
    products = pproc.products
    reference_block = getattr(first, "reference", None)
    description = getattr(first, "description", None) or ""
    mach = getattr(first, "mach", None)
    written: list[Path] = []
    sources: dict[str, list[str]] = {}
    points: list[PolarPoint] = []
    exports: dict[str, tuple[Path | None, Path | None]] = {}
    sim_dir = workspace.sim_dir(sim_id)
    for record in records:
        if not getattr(record, "outputs", None):
            continue
        kinds = classify_outputs([Path(o).name for o in record.outputs])
        by_name = {Path(o).name: sim_dir / o for o in record.outputs}
        loads_name = kinds.get("loads")
        if loads_name is None or not by_name[loads_name].is_file():
            continue
        text = by_name[loads_name].read_text(encoding="utf-8", errors="replace")
        try:
            report = parse_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{by_name[loads_name]} is not a loads table: {error}") from error
        stem = loads_name[: -len(".txt")]
        points.append(PolarPoint(name=stem, loads=report, loads_path=by_name[loads_name]))
        sloads_path = by_name.get(kinds["sectional_loads"]) if "sectional_loads" in kinds else None
        plots_path = by_name.get(kinds["plots"]) if "plots" in kinds else None
        exports[stem] = (sloads_path, plots_path)
        sources.setdefault(stem, []).append(getattr(record, "run_id", ""))
    if not points:
        return [], {}
    points.sort(key=lambda point: point.alpha_deg)
    if mach is None:
        raise ProductError(
            f"simulation {sim_id!r} records no Mach number, so its polar table has none"
        )
    if not reference_block or "BREF" not in reference_block:
        raise ProductError(
            f"simulation {sim_id!r} records no reference block with a span (BREF), which the "
            "polar table scales the rolling and yawing moments to; state span_m on the "
            "reference artifact"
        )
    reference = ReferenceValues.from_mapping(reference_block)
    run_ids = [rid for stem in sources for rid in sources[stem]]
    written_names: dict[str, list[str]] = {}

    def _target(path: Path) -> Path:
        if path.exists() and not overwrite:
            raise ProductError(
                f"the product {path} exists; pass overwrite=True (`pyfs-matrix post "
                "--overwrite`) to rewrite it from the manifest"
            )
        return path

    if products.polars:
        for group, families in pproc.groups.items():
            target = _target(out / polar_file_name(sim_id, mach, group))
            write_polar_table(
                target,
                polar=sim_id,
                description=description,
                group=str(group),
                reference=reference,
                rows=polar_rows(points, [str(f) for f in families], mach=mach, reference=reference),
            )
            written.append(target)
            written_names[target.relative_to(out).as_posix()] = run_ids
    for point in points:
        sloads_path, plots_path = exports[point.name]
        if products.sections and sloads_path is not None and sloads_path.is_file():
            target = _target(out / "sections" / f"{point.name}_sections.csv")
            done = write_sections_table(
                target,
                sloads_path.read_text(encoding="utf-8", errors="replace"),
                point=point.name,
                mach=mach,
            )
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = sources[point.name]
        if products.plots and plots_path is not None and plots_path.is_file():
            target = _target(out / "plots" / f"{point.name}_plots.csv")
            done = write_plots_table(
                target, plots_path.read_text(encoding="utf-8", errors="replace")
            )
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = sources[point.name]
    return written, written_names


def write_campaign_products(workspace: CampaignWorkspace, *, overwrite: bool = False) -> list[Path]:
    """Write the products of every simulation in a workspace's manifest under ``post/products``.

    PFS-2029.15.03. Reads the manifest alone: each successful record names
    its collected exports, its pproc artifact, its description, its Mach and
    its reference block, so the products are rebuilt with no executable
    configured. ``post/products/products.json`` names every file written
    with the run ids it derives from. An existing product is refused
    unless ``overwrite`` is set; the run itself passes it, since a product
    is derived and a resume rewrites it with the new points.
    """
    import json

    from pyflightstream.workspace import RunStatus

    records = workspace.read_manifest()
    out = Path(workspace.root) / "post" / "products"
    by_sim: dict[str, list[RunRecord]] = {}
    for record in records:
        if record.status in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER):
            by_sim.setdefault(record.sim_id, []).append(record)
    written: list[Path] = []
    products_index: dict[str, dict[str, object]] = {}
    manifest: dict[str, object] = {"products": products_index}
    for sim_id, sim_records in by_sim.items():
        files, names = _sim_products(workspace, sim_id, sim_records, out, overwrite=overwrite)
        written.extend(files)
        for name, run_ids in names.items():
            products_index[name] = {
                "sim_id": sim_id,
                "pproc": getattr(sim_records[0], "pproc", None),
                "runs": run_ids,
            }
    if written:
        out.mkdir(parents=True, exist_ok=True)
        (out / PRODUCTS_MANIFEST).write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
    return written
