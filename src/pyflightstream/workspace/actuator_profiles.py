"""Actuator-disc radial thrust profiles of ``inputs/profiles/``, built from loads or a shape.

Pipeline role: prepares an INPUT (FR-347, 0.34.0). A matrix row loads an
actuator disc either by its net thrust (``ACTUATOR_THRUST``, the solver's
native ELLIPTICAL model) or by a radial profile (``PROFILE: <stem>``, the
CUSTOM model), a file of the workspace's ``inputs/profiles/`` named by its
stem. This module writes that file, the way :mod:`pyflightstream.workspace.fields`
writes a custom free stream: ``<stem>.csv`` beside a provenance record
``<stem>.provenance.json``, previewing until applied.

THE FORM is the one the run's own copy of a profile is put in
(:func:`~pyflightstream.cases.workflows.read_actuator_profile`, RPT-070):
rows ``r,F``, ``r`` the radius in metres and ``F`` the force per unit span in
newtons per metre PER BLADE (the disc block states its ``blades``, and the
solver reads the file per blade), no header, no count line and no final
newline. Every text written is read back through the same renderer the run
uses, so a file this module writes is a file the plan accepts.

THREE SHAPES:

* ``SECTIONS``, from a POL's written sections: the sectional loads table a
  post writes (``sections/<point>_sloads_<family>.csv``), the thrust per unit
  span read as ``-Fx`` by default (the axial force of a blade whose rotor
  turns about x and pushes towards -x; ``Fx``, ``-Fz`` or ``Fz`` are stated
  otherwise), a zero from the axis to the hub and a zero at the tip. The
  table of an unsteady run that averaged its last revolutions is one set of
  stations; a table holding several steps is averaged over its last ``K``
  steps, stated. A station whose thrust is negative is set to zero, and the
  count is recorded.
* ``UNI``, a uniform pressure jump: ``F = c r`` from the hub to the tip.
* ``BP``, the Betz-Prandtl shape: ``F = c r f_tip f_hub`` with the Prandtl
  factors ``f = (2/pi) acos(exp(-B d / (2 r_ref sin(phi))))`` for ``B`` blades,
  ``d`` the distance to the tip (``r_ref = r``) or to the hub
  (``r_ref = r_hub``), and the helix angle ``tan(phi) = J R / (pi r)``.

The ELLIPTICAL model is native in the solver and needs no file: a row states
``ACTUATOR_THRUST`` and nothing here is involved. Measured on 26.124
(RPT-137), it placed about 0.62 of the thrust asked in the wake, and the
CUSTOM profiles 0.95 to 1.04 of it.

THE SCALE: every shape is multiplied by the one constant that makes
``B * integral(F dr)`` equal the target thrust, the integral taken by the
trapezoid rule over the rows written. The target is a thrust in newtons or a
thrust coefficient in the propeller convention ``CT = T / (rho n^2 D^4)``
(``n`` in rev/s, ``D`` twice the tip radius), never both. The integral of the
written text is taken again and stated in the record, and a text whose
integral misses the target by more than :data:`INTEGRAL_TOLERANCE` (relative)
is refused.

A disc of wake type RELAXED ignores a custom profile (RPT-137); the plan
warns on a row that names one (FR-332), and ``pyfs-workspace profile`` says
so when the disc it reads is RELAXED. ``pyfs-workspace profile`` is this
module's command line.

Examples
--------
>>> from pyflightstream.workspace.actuator_profiles import (
...     DiscGeometry, blade_thrust, scale_profile, uniform_profile)
>>> disc = DiscGeometry(tip_radius_m=0.5, hub_radius_m=0.1, blades=3)
>>> shape = uniform_profile(disc, stations=5)
>>> shape.rows[0], shape.rows[-1]
((0.0, 0.0), (0.5, 0.5))
>>> scaled, _ = scale_profile(shape, blades=3, thrust_n=120.0)
>>> round(blade_thrust(scaled, blades=3), 9)
120.0
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream.script import CommandArgumentError
from pyflightstream.script.helpers import render_actuator_profile
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace.inputs import resolve_reference

__all__ = [
    "DEFAULT_STATIONS",
    "INTEGRAL_TOLERANCE",
    "PROFILE_DIR",
    "PROFILE_PROVENANCE_SCHEMA",
    "PROFILE_SHAPES",
    "PROFILE_SUFFIX",
    "THRUST_COMPONENTS",
    "DiscGeometry",
    "ProfileWrite",
    "RadialProfile",
    "SectionLoads",
    "ThrustTarget",
    "betz_prandtl_profile",
    "blade_thrust",
    "disc_from_reference",
    "find_pol_sections",
    "read_section_loads",
    "render_profile",
    "scale_profile",
    "sections_profile",
    "thrust_target",
    "uniform_profile",
    "write_profile",
]

#: The schema the provenance record of a written profile states.
PROFILE_PROVENANCE_SCHEMA = "pyfs-actuator-profile/1"
#: The folder of ``inputs/`` a row's ``PROFILE`` is resolved in.
PROFILE_DIR = "profiles"
#: The extension of a written profile: rows ``r,F`` separated by one comma.
PROFILE_SUFFIX = ".csv"
#: The shapes a profile is built from (FR-347 R1, R2).
PROFILE_SHAPES = ("SECTIONS", "UNI", "BP")
#: The sectional-loads column, with its sign, read as the thrust per unit span.
THRUST_COMPONENTS = ("-Fx", "Fx", "-Fz", "Fz")
#: The stations of a generic shape from the hub to the tip, as measured.
DEFAULT_STATIONS = 61
#: The largest relative miss of ``B * integral(F dr)`` against the target.
INTEGRAL_TOLERANCE = 1e-9
#: How far inside the hub radius every shape's inner zero sits, in m (the profiles of RPT-137).
_HUB_STEP_M = 1e-4


@dataclass(frozen=True)
class DiscGeometry:
    """The annulus a profile is built over and the blade count it is read per.

    Attributes
    ----------
    tip_radius_m : float
        The disc's outer radius, in m.
    hub_radius_m : float
        The disc's inner radius, in m, ``0 <= hub < tip``.
    blades : int
        The blade count the file's force per unit span is read per.

    Raises
    ------
    WorkspaceError
        A hub that is not inside the tip, or a blade count that is not a
        whole number of at least one.

    Examples
    --------
    >>> DiscGeometry(tip_radius_m=0.5, hub_radius_m=0.1, blades=3).blades
    3
    """

    tip_radius_m: float
    hub_radius_m: float
    blades: int

    def __post_init__(self) -> None:
        """Refuse a disc that is not an annulus or a blade count that is not whole."""
        tip, hub = self.tip_radius_m, self.hub_radius_m
        if not (math.isfinite(tip) and math.isfinite(hub) and 0.0 <= hub < tip):
            raise WorkspaceError(
                f"the disc's hub radius {hub!r} m and tip radius {tip!r} m are not an annulus: "
                "a disc is the ring 0 <= hub < tip, as its reference block states it."
            )
        if isinstance(self.blades, bool) or not isinstance(self.blades, int) or self.blades < 1:
            raise WorkspaceError(
                f"blades = {self.blades!r}: the blade count is a whole number of at least one; "
                "the profile is read per blade."
            )


@dataclass(frozen=True)
class ThrustTarget:
    """The thrust a profile is scaled to, and how it was stated.

    Attributes
    ----------
    thrust_n : float
        The disc's net thrust, in N.
    basis : str
        ``"thrust"`` when stated in newtons, ``"ct"`` when worked out from a
        thrust coefficient.
    parameters : dict
        What was stated: the thrust, or the coefficient with the density, the
        speed and the diameter it was worked out with.
    """

    thrust_n: float
    basis: str
    parameters: dict[str, float]


@dataclass(frozen=True)
class RadialProfile:
    """A radial thrust profile: rows ``(r, F)``, r in m and F in N/m per blade.

    Attributes
    ----------
    rows : tuple of (float, float)
        The rows in increasing radius.
    """

    rows: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class SectionLoads:
    """The thrust per unit span a sectional loads table states at its stations.

    Attributes
    ----------
    stations : tuple of (float, float)
        ``(r, thrust per unit span)``, r in m and the thrust in N/m, in
        increasing radius, a negative thrust set to zero.
    steps : tuple
        The steps averaged, ``None`` for a table that states none.
    clipped : int
        The stations whose thrust was negative and was set to zero.
    component : str
        The column, with its sign, read as the thrust.
    source : Path
        The table read.
    """

    stations: tuple[tuple[float, float], ...]
    steps: tuple[int | None, ...]
    clipped: int
    component: str
    source: Path


@dataclass(frozen=True)
class ProfileWrite:
    """What :func:`write_profile` wrote, or would write.

    Attributes
    ----------
    target : Path
        ``inputs/profiles/<stem>.csv``.
    sidecar : Path
        ``inputs/profiles/<stem>.provenance.json``.
    profile : RadialProfile
        The scaled profile the file holds.
    provenance : dict
        The record's content.
    applied : bool
        Whether the files were written.
    overwritten : tuple of Path
        The files a write replaced.
    """

    target: Path
    sidecar: Path
    profile: RadialProfile
    provenance: dict[str, object]
    applied: bool
    overwritten: tuple[Path, ...]


def disc_from_reference(
    root: str | Path, reference: str, disc: str
) -> tuple[DiscGeometry, dict[str, object]]:
    r"""Read a disc's annulus and blade count from a reference of the workspace.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    reference : str
        The reference id, the stem of ``inputs/references/<id>.toml``.
    disc : str
        The name of the reference's ``kind = "actuator"`` block.

    Returns
    -------
    tuple of (DiscGeometry, dict)
        The disc, and what the record states of it: the reference, the disc,
        its wake type and the reference file with its sha256.

    Raises
    ------
    InputArtifactError
        The reference does not exist or does not validate.
    WorkspaceError
        The reference declares no such disc, the disc states no ``blades``,
        or its ``profile_units`` are not ``NEWTONS``.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> root = Path(tempfile.mkdtemp())
    >>> (root / "inputs" / "references").mkdir(parents=True)
    >>> _ = (root / "inputs" / "references" / "r001.toml").write_text(
    ...     'area_m2 = 1.0\nchord_m = 1.0\nspan_m = 1.0\n\n[PROP]\nkind = "actuator"\n'
    ...     'frame = "MRP"\naxis = "X"\ntip_radius_m = 0.5\nhub_radius_m = 0.1\nblades = 3\n')
    >>> disc_from_reference(root, "r001", "PROP")[0]
    DiscGeometry(tip_radius_m=0.5, hub_radius_m=0.1, blades=3)
    """
    inputs_dir = Path(root) / "inputs"
    artifact = resolve_reference(inputs_dir, reference)
    block = artifact.actuators.get(disc)
    if block is None:
        held = ", ".join(sorted(artifact.actuators)) or "none"
        raise WorkspaceError(
            f"the reference {reference!r} declares no actuator disc {disc!r} (it declares: "
            f'{held}); a disc is a top-level table with kind = "actuator".'
        )
    if block.blades is None:
        raise WorkspaceError(
            f"the disc {disc!r} of {reference!r} states no blades; a profile is read per blade, "
            "so the block states blades = <count>."
        )
    if block.profile_units != "NEWTONS":
        raise WorkspaceError(
            f"the disc {disc!r} of {reference!r} states profile_units = "
            f"{block.profile_units!r}; a written profile is in newtons per metre, so the block "
            'states profile_units = "NEWTONS" (the default).'
        )
    path = inputs_dir / "references" / f"{reference}.toml"
    stated: dict[str, object] = {
        "reference": reference,
        "disc": disc,
        "wake_type": block.wake_type,
        "file": {"path": f"inputs/references/{path.name}", "sha256": file_sha256(path)},
    }
    return DiscGeometry(block.tip_radius_m, block.hub_radius_m, block.blades), stated


def thrust_target(
    *,
    tip_radius_m: float,
    thrust_n: float | None = None,
    ct: float | None = None,
    rho_kg_m3: float | None = None,
    rpm: float | None = None,
) -> ThrustTarget:
    """Return the thrust a profile is scaled to, stated in newtons or by a CT.

    Parameters
    ----------
    tip_radius_m : float
        The disc's tip radius, in m; the diameter of the CT is twice it.
    thrust_n : float, optional
        The net thrust, in N.
    ct : float, optional
        The thrust coefficient ``T / (rho n^2 D^4)``, the propeller convention.
    rho_kg_m3 : float, optional
        The density of the CT, in kg/m^3; required with ``ct``.
    rpm : float, optional
        The speed of the CT, in rev/min; required with ``ct``.

    Returns
    -------
    ThrustTarget
        The thrust in N and what was stated.

    Raises
    ------
    WorkspaceError
        Both or neither of ``thrust_n`` and ``ct`` stated; a CT without its
        density and speed, or a density or speed beside a thrust; a value that
        is not a finite positive number.

    Examples
    --------
    >>> thrust_target(tip_radius_m=0.5, thrust_n=120.0).thrust_n
    120.0
    >>> round(thrust_target(tip_radius_m=0.5, ct=0.1, rho_kg_m3=1.2, rpm=3000.0).thrust_n, 6)
    300.0
    """
    if (thrust_n is None) == (ct is None):
        raise WorkspaceError(
            "state the target once: thrust_n, a thrust in newtons, or ct (CLI: --ct), a thrust "
            "coefficient, with rho_kg_m3, the density, and rpm (CLI: --rpm); not "
            "both and not neither."
        )
    if thrust_n is not None:
        if rho_kg_m3 is not None or rpm is not None:
            raise WorkspaceError(
                "rho_kg_m3, the density, and rpm (CLI: --rpm) state the basis of a "
                "CT; with a thrust in newtons they would not be read, so leave them out."
            )
        _positive(thrust_n, "the thrust, in N")
        return ThrustTarget(thrust_n, "thrust", {"thrust_n": thrust_n})
    if rho_kg_m3 is None or rpm is None:
        raise WorkspaceError(
            "a CT is worked out to a thrust with the density and the speed: state rho_kg_m3 "
            "(the density in kg/m^3), and rpm (CLI: --rpm), in rev/min, beside ct "
            "(CLI: --ct)."
        )
    assert ct is not None  # the first refusal above: one of the two is stated
    for value, what in ((ct, "the CT"), (rho_kg_m3, "the density"), (rpm, "the speed")):
        _positive(value, what)
    n = rpm / 60.0
    diameter = 2.0 * tip_radius_m
    thrust = ct * rho_kg_m3 * n * n * diameter**4
    stated = {"ct": ct, "rho_kg_m3": rho_kg_m3, "rpm": rpm, "n_rev_s": n, "d_m": diameter}
    return ThrustTarget(thrust, "ct", {"thrust_n": thrust, **stated})


def _positive(value: float | None, what: str) -> None:
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise WorkspaceError(f"{what} is {value!r}; it is a finite positive number.")


def find_pol_sections(root: str | Path, pol: str, *, family: str = "Blade1") -> Path:
    """Return the one sectional loads table the post wrote for a POL and a family.

    The post records each table it writes in ``post/<matrix>/products.json``
    with its POL and its families; one level of ``post/`` is read, and no
    link is followed.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    pol : str
        The POL.
    family : str, optional
        The family of the sections distribution, ``Blade1`` by default.

    Returns
    -------
    Path
        The table, ``post/<matrix>/sections/<point>_sloads_<family>.csv``.

    Raises
    ------
    WorkspaceError
        No table, or more than one (several points or matrices), naming each.

    Examples
    --------
    >>> import json, tempfile
    >>> from pathlib import Path
    >>> root = Path(tempfile.mkdtemp())
    >>> (root / "post" / "m" / "sections").mkdir(parents=True)
    >>> _ = (root / "post" / "m" / "sections" / "P7-A_sloads_Blade1.csv").write_text("x")
    >>> _ = (root / "post" / "m" / "products.json").write_text(json.dumps({"products": {
    ...     "sections/P7-A_sloads_Blade1.csv": {"sim_id": "7", "families": ["Blade1"]}}}))
    >>> find_pol_sections(root, "7").name
    'P7-A_sloads_Blade1.csv'
    """
    post = Path(root) / "post"
    found: list[Path] = []
    listed = post.iterdir() if post.is_dir() else ()
    folders = sorted(p for p in listed if p.is_dir() and not p.is_symlink())
    for folder in folders:
        found += _recorded_tables(folder, str(pol), family)
    if len(found) == 1:
        return found[0]
    if not found:
        raise WorkspaceError(
            f"no sectional loads table of POL {pol} and family {family!r} is recorded under "
            f"{post}: post the POL with a pproc that writes sections (products.sections = true "
            "and a [[sections.distributions]] of that family), or name the table itself."
        )
    raise WorkspaceError(
        f"POL {pol} has {len(found)} sectional loads tables of family {family!r} ("
        + ", ".join(str(p) for p in found)
        + "); name the one the profile is built from."
    )


def _recorded_tables(folder: Path, pol: str, family: str) -> list[Path]:
    """Return the sectional loads tables of one post folder's ``products.json`` for a POL."""
    record = folder / "products.json"
    if not record.is_file():
        return []
    try:
        products = json.loads(record.read_text(encoding="utf-8")).get("products", {})
    except (OSError, ValueError, AttributeError):
        return []
    return [
        folder / key
        for key, entry in sorted(products.items())
        if key.startswith("sections/")
        and "_sloads_" in key
        and isinstance(entry, Mapping)
        and str(entry.get("sim_id")) == pol
        and family in _families(entry.get("families"))
        and (folder / key).is_file()
    ]


def _families(stated: object) -> list[str]:
    """Return a products.json entry's families as a list: one name or a list of names."""
    if isinstance(stated, str):
        return [stated]
    return [str(name) for name in stated] if isinstance(stated, (list, tuple)) else []


def read_section_loads(
    path: str | Path, *, component: str = "-Fx", last: int | None = None
) -> SectionLoads:
    r"""Read the thrust per unit span of a sectional loads table the post wrote.

    The radius is the ``Offset`` column, in m; the thrust is ``component``
    (``-Fx`` by default), in N/m. A table holding one step (or none stated) is
    read as it is; a table holding several is averaged over its ``last``
    steps, station by station, and every averaged step states the same
    stations. A negative thrust is set to zero and counted.

    Parameters
    ----------
    path : str or Path
        The table, ``sections/<point>_sloads_<family>.csv``.
    component : str, optional
        One of :data:`THRUST_COMPONENTS`.
    last : int, optional
        The steps averaged, counted from the last; required when the table
        holds several.

    Returns
    -------
    SectionLoads
        The stations in increasing radius.

    Raises
    ------
    WorkspaceError
        The table cannot be read; it has no ``Offset`` or no such column; it
        holds several clockings, or several steps and no ``last``, or fewer
        steps than ``last``; two rows of one step share a radius; the steps
        averaged state different stations; a value is not a finite number.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> table = Path(tempfile.mkdtemp()) / "P1_sloads_Blade1.csv"
    >>> _ = table.write_text("POL,STEP,Offset,Fx\n1,4,0.3,-2.0\n1,4,0.2,-1.0\n1,4,0.4,0.5\n")
    >>> loads = read_section_loads(table)
    >>> loads.stations, loads.clipped
    (((0.2, 1.0), (0.3, 2.0), (0.4, 0.0)), 1)
    """
    if component not in THRUST_COMPONENTS:
        raise WorkspaceError(
            f"component {component!r} is not one of {', '.join(THRUST_COMPONENTS)}."
        )
    source = Path(path)
    rows = _table_rows(source, component.lstrip("-"))
    groups = _step_groups(rows, source, component)
    steps = sorted(groups, key=lambda step: -1 if step is None else step)
    if len(steps) > 1 and last is None:
        raise WorkspaceError(
            f"{source} holds {len(steps)} steps ({steps[0]} to {steps[-1]}); state how many of "
            "the last are averaged: last (CLI: --last)."
        )
    if last is not None and not 1 <= last <= len(steps):
        raise WorkspaceError(f"last (CLI: --last) is {last}: {source} holds {len(steps)} step(s).")
    chosen = steps[-(last or 1) :]
    stations = _mean_stations([groups[step] for step in chosen], source)
    clipped = sum(1 for _, value in stations if value < 0.0)
    kept = tuple((r, max(0.0, value)) for r, value in stations)
    return SectionLoads(kept, tuple(chosen), clipped, component, source)


def _table_rows(source: Path, column: str) -> list[dict[str, str]]:
    """Return the rows of a sectional loads table, refused without its two columns."""
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise WorkspaceError(f"{source} cannot be read as UTF-8 text: {error}") from error
    reader = csv.DictReader(io.StringIO(text))
    names = reader.fieldnames or []
    missing = [name for name in ("Offset", column) if name not in names]
    if missing:
        raise WorkspaceError(
            f"{source} has no column {', '.join(missing)}; a sectional loads table the post "
            f"writes states Offset and the forces (its columns: {', '.join(names) or 'none'})."
        )
    rows = list(reader)
    clockings = {row.get("CLOCKING") for row in rows if row.get("CLOCKING") not in (None, "")}
    if len(clockings) > 1:
        raise WorkspaceError(
            f"{source} holds {len(clockings)} clockings; a profile is built from one set of "
            "stations, so build it from a table of one clocking."
        )
    return rows


def _number(text: str | None, source: Path, line: int, column: str) -> float:
    try:
        value = float(text or "")
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise WorkspaceError(f"{source}, row {line}: {column} = {text!r} is not a finite number.")
    return value


def _step_groups(
    rows: Sequence[Mapping[str, str]], source: Path, component: str
) -> dict[int | None, list[tuple[float, float]]]:
    """Return the rows' ``(r, thrust)`` per step; ``None`` for a table that states no step."""
    column = component.lstrip("-")
    sign = -1.0 if component.startswith("-") else 1.0
    groups: dict[int | None, list[tuple[float, float]]] = {}
    for line, row in enumerate(rows, start=2):
        raw = (row.get("STEP") or "").strip()
        step = None if raw in ("", "NA") else int(_number(raw, source, line, "STEP"))
        r = _number(row.get("Offset"), source, line, "Offset")
        value = sign * _number(row.get(column), source, line, column)
        groups.setdefault(step, []).append((r, value))
    if not groups:
        raise WorkspaceError(f"{source} holds no rows.")
    return groups


def _mean_stations(
    groups: Sequence[list[tuple[float, float]]], source: Path
) -> list[tuple[float, float]]:
    """Return the mean thrust per station over the groups, which state the same stations."""
    ordered = [sorted(group) for group in groups]
    radii = [r for r, _ in ordered[0]]
    if len(set(radii)) != len(radii):
        raise WorkspaceError(
            f"{source}: two rows of one step state the same radius; a profile is one curve "
            "F(r), so build it from a table of one distribution."
        )
    for group in ordered[1:]:
        if [r for r, _ in group] != radii:
            raise WorkspaceError(
                f"{source}: the steps averaged do not state the same stations; a mean is "
                "taken station by station."
            )
    return [(r, sum(group[i][1] for group in ordered) / len(ordered)) for i, r in enumerate(radii)]


def sections_profile(loads: SectionLoads, disc: DiscGeometry) -> RadialProfile:
    """Return the profile of a table's stations: a zero to the hub, the stations, a zero at the tip.

    Parameters
    ----------
    loads : SectionLoads
        The stations, from :func:`read_section_loads`.
    disc : DiscGeometry
        The disc the profile is for.

    Returns
    -------
    RadialProfile
        ``(0, 0)``, ``(hub - 1e-4 m, 0)`` when that lies off the axis, the
        stations, then ``(tip, 0)``; not yet scaled.

    Raises
    ------
    WorkspaceError
        A station at or inside the hub radius, or at or beyond the tip radius.

    Examples
    --------
    >>> from pathlib import Path
    >>> given = SectionLoads(((0.2, 1.0), (0.4, 2.0)), (None,), 0, "-Fx", Path("t.csv"))
    >>> sections_profile(given, DiscGeometry(0.5, 0.1, 3)).rows
    ((0.0, 0.0), (0.0999, 0.0), (0.2, 1.0), (0.4, 2.0), (0.5, 0.0))
    """
    hub, tip = disc.hub_radius_m, disc.tip_radius_m
    outside = [r for r, _ in loads.stations if not hub < r < tip]
    if outside:
        raise WorkspaceError(
            f"{loads.source}: the station at r = {outside[0]!r} m is not inside the disc "
            f"({hub!r} m < r < {tip!r} m); the profile is zero from the axis to the hub and at "
            "the tip. State the disc the table's blade belongs to."
        )
    return RadialProfile((*_inner_zeros(hub), *loads.stations, (tip, 0.0)))


def _inner_zeros(hub: float) -> tuple[tuple[float, float], ...]:
    """Return the zeros inside the hub: the axis, and ``hub - 1e-4 m`` when that is off it."""
    step = hub - _HUB_STEP_M
    return ((0.0, 0.0), (step, 0.0)) if step > 0.0 else ((0.0, 0.0),)


def _radii(disc: DiscGeometry, stations: int) -> list[float]:
    if isinstance(stations, bool) or not isinstance(stations, int) or stations < 2:
        raise WorkspaceError(f"stations = {stations!r}; a shape is sampled at two or more.")
    hub, tip = disc.hub_radius_m, disc.tip_radius_m
    return [hub + (tip - hub) * i / (stations - 1) for i in range(stations)]


def uniform_profile(disc: DiscGeometry, *, stations: int = DEFAULT_STATIONS) -> RadialProfile:
    """Return the uniform pressure jump: ``F = r`` from the hub to the tip, not yet scaled.

    A uniform jump ``dp`` loads each blade with ``F = dp 2 pi r / B``, a force
    per unit span proportional to the radius. Inside the hub the profile is
    zero: a row ``(0, 0)`` and one just inside the hub radius, at
    ``hub - 1e-4 m`` as in the profiles RPT-137 summarises, so the step at the
    hub is between two radii.

    Parameters
    ----------
    disc : DiscGeometry
        The disc.
    stations : int, optional
        The stations from the hub to the tip, both included.

    Returns
    -------
    RadialProfile
        The shape.

    Raises
    ------
    WorkspaceError
        Fewer than two stations.

    Examples
    --------
    >>> uniform_profile(DiscGeometry(1.0, 0.0, 2), stations=3).rows
    ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0))
    """
    rows = [(r, r) for r in _radii(disc, stations)]
    inner = _inner_zeros(disc.hub_radius_m) if rows[0][0] > 0.0 else ()
    return RadialProfile((*inner, *rows))


def _prandtl(distance: float, radius: float, blades: int, sin_phi: float) -> float:
    """Return the Prandtl factor ``(2/pi) acos(exp(-B d / (2 r sin(phi))))``."""
    return (2.0 / math.pi) * math.acos(math.exp(-blades * distance / (2.0 * radius * sin_phi)))


def betz_prandtl_profile(
    disc: DiscGeometry, *, advance_ratio: float, stations: int = DEFAULT_STATIONS
) -> RadialProfile:
    """Return the Betz-Prandtl shape ``F = r f_tip f_hub``, not yet scaled.

    ``f_tip`` and ``f_hub`` are Prandtl's factors for ``B`` blades, at the
    distance to the tip over ``r`` and to the hub over ``r_hub``, with the
    helix angle ``tan(phi) = J R / (pi r)``; both are zero where their
    distance is, so the shape is zero at the hub and at the tip. A disc whose
    hub is the axis has no hub factor.

    Parameters
    ----------
    disc : DiscGeometry
        The disc.
    advance_ratio : float
        The advance ratio ``J = V / (n D)``, positive.
    stations : int, optional
        The stations from the hub to the tip, both included.

    Returns
    -------
    RadialProfile
        The shape.

    Raises
    ------
    WorkspaceError
        An advance ratio that is not a finite positive number, or fewer than
        two stations.

    Examples
    --------
    >>> shape = betz_prandtl_profile(DiscGeometry(1.0, 0.2, 4), advance_ratio=1.0, stations=5)
    >>> shape.rows[2], shape.rows[-1]
    ((0.2, 0.0), (1.0, 0.0))
    """
    _positive(advance_ratio, "the advance ratio")
    hub, tip, blades = disc.hub_radius_m, disc.tip_radius_m, disc.blades
    rows = []
    for r in _radii(disc, stations):
        if r == 0.0:
            rows.append((r, 0.0))
            continue
        sin_phi = math.sin(math.atan2(advance_ratio * tip, math.pi * r))
        f_hub = _prandtl(r - hub, hub, blades, sin_phi) if hub > 0.0 else 1.0
        rows.append((r, r * _prandtl(tip - r, r, blades, sin_phi) * f_hub))
    inner = _inner_zeros(hub) if rows[0][0] > 0.0 else ()
    return RadialProfile((*inner, *rows))


def blade_thrust(profile: RadialProfile, *, blades: int) -> float:
    """Return ``B * integral(F dr)`` by the trapezoid rule over the rows, in N.

    Parameters
    ----------
    profile : RadialProfile
        The rows.
    blades : int
        The blade count ``B``.

    Returns
    -------
    float
        The disc's thrust the rows state.

    Examples
    --------
    >>> blade_thrust(RadialProfile(((0.0, 0.0), (1.0, 2.0))), blades=3)
    3.0
    """
    rows = profile.rows
    area = sum((b[0] - a[0]) * (a[1] + b[1]) / 2.0 for a, b in zip(rows, rows[1:], strict=False))
    return blades * area


def scale_profile(
    profile: RadialProfile, *, blades: int, thrust_n: float
) -> tuple[RadialProfile, float]:
    """Return the profile scaled so that ``B * integral(F dr)`` is ``thrust_n``, and the scale.

    Parameters
    ----------
    profile : RadialProfile
        The shape.
    blades : int
        The blade count.
    thrust_n : float
        The target thrust, in N.

    Returns
    -------
    tuple of (RadialProfile, float)
        The scaled profile and the factor applied.

    Raises
    ------
    WorkspaceError
        The shape carries no positive thrust to scale.

    Examples
    --------
    >>> scale_profile(RadialProfile(((0.0, 0.0), (1.0, 2.0))), blades=1, thrust_n=2.0)[1]
    2.0
    """
    carried = blade_thrust(profile, blades=blades)
    if not (math.isfinite(carried) and carried > 0.0):
        raise WorkspaceError(
            f"the shape carries a thrust of {carried!r} N before scaling; a profile is scaled "
            "to the target from a positive thrust. For a table, check the column read as the "
            "thrust, component (CLI: --component), and its sign: a wrong sign reads every "
            "station as zero."
        )
    scale = thrust_n / carried
    return RadialProfile(tuple((r, f * scale) for r, f in profile.rows)), scale


def render_profile(profile: RadialProfile) -> str:
    """Return the file text of a profile: rows ``r,F``, no header and no final newline.

    Each number is written in its shortest exact form, so the file holds the
    profile's values to the last bit and its integral is the one checked.

    Parameters
    ----------
    profile : RadialProfile
        The rows.

    Returns
    -------
    str
        The text, newline separated and NOT newline terminated (RPT-070).

    Raises
    ------
    WorkspaceError
        The text is not one the run's profile reader takes as it is.

    Examples
    --------
    >>> print(render_profile(RadialProfile(((0.0, 0.0), (0.5, 12.5), (1.0, 0.0)))))
    0.0,0.0
    0.5,12.5
    1.0,0.0
    """
    text = "\n".join(f"{float(r)!r},{float(f)!r}" for r, f in profile.rows)
    try:
        read = render_actuator_profile(text, source="the written profile")
    except CommandArgumentError as error:
        raise WorkspaceError(str(error)) from None
    if read != text:
        raise WorkspaceError("the written profile is not in the form the run's copy takes.")
    return text


def _check_stem(stem: str) -> str:
    text = stem.strip()
    if (
        not text
        or text != stem
        or any(ch in text for ch in '/\\:*?"<>|')
        or text.startswith(".")
        or Path(text).suffix
    ):
        raise WorkspaceError(
            f"output stem {stem!r}: name the profile by its stem, a plain file name with no "
            "folder and no extension, as a row's PROFILE names it (the file is <stem>.csv)."
        )
    return text


def _written_thrust(text: str, *, blades: int, thrust_n: float) -> dict[str, float]:
    """Integrate the written text again and refuse a miss above the tolerance."""
    rows = tuple((float(r), float(f)) for r, f in (line.split(",") for line in text.split("\n")))
    check = blade_thrust(RadialProfile(rows), blades=blades)
    miss = abs(check - thrust_n) / thrust_n
    if miss > INTEGRAL_TOLERANCE:
        raise WorkspaceError(
            f"the written profile integrates to {check!r} N against {thrust_n!r} N asked, a "
            f"relative miss of {miss:.3g} above {INTEGRAL_TOLERANCE:g}."
        )
    return {"blades_times_integral_n": check, "relative_miss": miss}


def write_profile(
    root: str | Path,
    stem: str,
    profile: RadialProfile,
    *,
    disc: DiscGeometry,
    target: ThrustTarget,
    shape: str,
    parameters: Mapping[str, object],
    inputs: Sequence[Mapping[str, object]] = (),
    apply: bool = False,
    overwrite: bool = False,
) -> ProfileWrite:
    """Scale a shape to its target and write it into ``<root>/inputs/profiles/``, or preview it.

    The file is ``<stem>.csv``, the form the run's copy of a profile takes;
    the record ``<stem>.provenance.json`` names the shape, its parameters,
    the disc, the target, the scale, the integral of the written rows, every
    input with its sha256 and the written file's own sha256. Without
    ``apply`` nothing is written and the same refusals fire.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    stem : str
        The name a row's ``PROFILE`` cites, a plain name.
    profile : RadialProfile
        The shape, not yet scaled.
    disc : DiscGeometry
        The disc; its blade count is the ``B`` of the integral.
    target : ThrustTarget
        The thrust the profile is scaled to.
    shape : str
        One of :data:`PROFILE_SHAPES`, recorded.
    parameters : mapping of str to object
        The shape's parameters, recorded.
    inputs : sequence of mapping, optional
        The input files, each ``{"path": ..., "sha256": ...}``, recorded.
    apply : bool, optional
        Write the files; without it nothing is written.
    overwrite : bool, optional
        Replace a file or record that already exists instead of refusing it.

    Returns
    -------
    ProfileWrite
        The paths, the scaled profile, the record, whether it was written and
        the files it replaced.

    Raises
    ------
    WorkspaceError
        The stem is not a plain name; the folder holds another file of that
        stem; the file or its record exists and ``overwrite`` is not set; the
        shape carries no positive thrust; the written integral misses.

    Examples
    --------
    >>> import tempfile
    >>> disc = DiscGeometry(0.5, 0.1, 3)
    >>> done = write_profile(
    ...     tempfile.mkdtemp(), "prop_uni", uniform_profile(disc, stations=5), disc=disc,
    ...     target=thrust_target(tip_radius_m=0.5, thrust_n=120.0), shape="UNI",
    ...     parameters={"stations": 5}, apply=True)
    >>> done.target.name, done.provenance["integral"]["relative_miss"] < 1e-12
    ('prop_uni.csv', True)
    """
    name = _check_stem(stem)
    if shape not in PROFILE_SHAPES:
        raise WorkspaceError(f"shape {shape!r} is not one of {', '.join(PROFILE_SHAPES)}.")
    scaled, scale = scale_profile(profile, blades=disc.blades, thrust_n=target.thrust_n)
    text = render_profile(scaled)
    integral = _written_thrust(text, blades=disc.blades, thrust_n=target.thrust_n)
    folder = Path(root) / "inputs" / PROFILE_DIR
    path = folder / f"{name}{PROFILE_SUFFIX}"
    sidecar = folder / f"{name}.provenance.json"
    others = sorted(
        p for p in (folder.iterdir() if folder.is_dir() else ()) if p.stem == name and p != path
    )
    if others:
        raise WorkspaceError(
            f"{others[0]} exists: the stem {name!r} would name two files of {folder}, and a "
            "row's PROFILE names one. Choose another stem, or remove it."
        )
    existing = tuple(p for p in (path, sidecar) if p.exists())
    if existing and not overwrite:
        raise WorkspaceError(
            f"{', '.join(str(p) for p in existing)} exists; nothing is overwritten unless "
            "overwrite (CLI: --overwrite) is set."
        )
    provenance: dict[str, object] = {
        "schema": PROFILE_PROVENANCE_SCHEMA,
        "shape": shape,
        "parameters": dict(parameters),
        "disc": {
            "tip_radius_m": disc.tip_radius_m,
            "hub_radius_m": disc.hub_radius_m,
            "blades": disc.blades,
        },
        "target": {"basis": target.basis, **target.parameters},
        "scale": scale,
        "integral": {"rule": "trapezoid over the written rows", **integral},
        "inputs": [dict(each) for each in inputs],
        "output": {
            "file": f"inputs/{PROFILE_DIR}/{path.name}",
            "rows": len(scaled.rows),
            "sha256": text_sha256(text),
        },
        "units": {"r": "m", "F": "N/m per blade", "profile_units": "NEWTONS"},
    }
    if apply:
        folder.mkdir(parents=True, exist_ok=True)
        # Through the LF route (NFR-32): the record's sha256 is of these exact
        # bytes, and the text holds no final newline (RPT-070).
        _textio.write_text(path, text)
        _textio.write_text(sidecar, json.dumps(provenance, indent=2) + "\n")
    return ProfileWrite(path, sidecar, scaled, provenance, apply, existing if apply else ())
