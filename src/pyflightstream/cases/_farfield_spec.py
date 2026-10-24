"""The ``[farfield]`` table of the pproc artifact and the lattice shape of ``[[probes]]``.

Pipeline role: the input model of the far-field family (FR-454) and of the
survey-lattice probe shape (FR-1072), validated at load with
``extra="forbid"`` and ``allow_inf_nan=False``. It lives beside
:mod:`pyflightstream.cases.pproc` and not inside it, so that module does not
grow; :class:`~pyflightstream.cases.pproc.PprocSpec` holds ``farfield`` and
:class:`~pyflightstream.cases.pproc.ProbesSpec` holds ``lattices`` through
these types. The geometry a table states is the far field's own; a table that
states none leaves the geometry to the plan's reuse rule (FR-1042, FR-455).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from pyflightstream.probes.lattice import ProbeLattice, build_lattice

__all__ = [
    "BALANCES",
    "FARFIELD_DEFAULTS",
    "TREFFTZ_VARIANTS",
    "FarfieldSpec",
    "LatticeShape",
    "LedgersSpec",
    "TrefftzSpec",
]

#: The three accepted Trefftz variants.
TREFFTZ_VARIANTS: tuple[str, ...] = ("sections", "wake", "plane", "power")
#: The six balances of FR-479, in the order the ledgers table writes them.
BALANCES: tuple[str, ...] = (
    "mass",
    "axial",
    "transverse",
    "torque",
    "in_plane_moment",
    "crossflow_energy",
)
#: The defaults of FR-1039 that a table may leave unstated:
#: the plan's station count per side, the plane's distance behind the
#: families and, for the wing plane, its half extents and spacing, all in BREF.
FARFIELD_DEFAULTS: dict[str, float] = {
    "stations": 80,
    "distance_bref": 0.25,
    "half_width_bref": 0.75,
    "half_height_bref": 0.5,
    "spacing_bref": 0.01,
    "m_max": 6,
}

#: The ``probes.build_lattice`` parameters a lattice may state.
_LATTICE_KEYS = (
    "stations",
    "n_r",
    "r_inner",
    "r_outer",
    "n_psi",
    "lateral_radius",
    "lateral_stations",
    "hub_width",
    "tip_width",
)


def _one_or_list(value: object) -> object:
    """Accept one word or a list of words, the way ``families`` is written."""
    return [value] if isinstance(value, str) else value


def _unique(words: list[str], what: str) -> list[str]:
    repeated = sorted({word for word in words if words.count(word) > 1})
    if repeated:
        raise ValueError(f"{what} repeats {', '.join(repeated)}; state each once")
    return words


class LatticeShape(BaseModel):
    """A survey lattice, by its rotor or its frame and the ``build_lattice`` parameters.

    The keys of ``[farfield.ledgers]`` geometry and of one entry of a
    ``[[probes]]`` entry's ``lattices`` (FR-1072): ``rotor`` names the rotor
    whose hub frame and tip radius place the lattice, or ``frame`` and
    ``tip_radius_m`` place a lattice that belongs to no rotor; the rest are the
    parameters of :func:`pyflightstream.probes.build_lattice`, unstated ones
    taking its defaults.

    Attributes
    ----------
    rotor : str, optional
        The rotor alias of the reference.
    frame : str, optional
        The frame whose x axis is the lattice's axis, with ``tip_radius_m``.
    tip_radius_m : float, optional
        The lattice's reference radius in metres, with ``frame``.
    stations, n_r, r_inner, r_outer, n_psi, lateral_radius, lateral_stations, hub_width, tip_width
        As :func:`pyflightstream.probes.build_lattice`.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    rotor: str | None = Field(
        default=None,
        description="The rotor of the reference whose hub frame and tip radius place the lattice.",
    )
    frame: str | None = Field(
        default=None,
        description="A frame whose x axis is the lattice's axis, for a lattice of no rotor.",
    )
    tip_radius_m: float | None = Field(
        default=None, gt=0.0, description="The reference radius of a frame's lattice, in m."
    )
    stations: tuple[float, ...] | None = Field(
        default=None, description="The annular planes' positions x/R, strictly increasing."
    )
    n_r: int | None = Field(default=None, ge=1, description="The ring count of every plane.")
    r_inner: float | None = Field(
        default=None, gt=0.0, description="The first ring edge r/R, off the axis."
    )
    r_outer: float | None = Field(default=None, gt=0.0, description="The last ring edge r/R.")
    n_psi: int | None = Field(
        default=None, ge=8, description="The uniform azimuth count of every ring."
    )
    lateral_radius: float | None = Field(
        default=None, gt=0.0, description="The radius r/R of the lateral closure cylinder."
    )
    lateral_stations: tuple[float, ...] | None = Field(
        default=None, description="The lateral rings' positions x/R; unstated, the stations."
    )
    hub_width: float | None = Field(
        default=None, gt=0.0, description="The width r/R of the ring clustering at the hub."
    )
    tip_width: float | None = Field(
        default=None, gt=0.0, description="The width r/R of the ring clustering at the tip."
    )

    @model_validator(mode="after")
    def _placed_once(self) -> LatticeShape:
        if self.rotor is not None and self.frame is not None:
            raise ValueError(
                "a lattice states rotor or frame, not both: the rotor's hub frame places it, "
                "or a frame with tip_radius_m does"
            )
        if self.rotor is None and (self.frame is None or self.tip_radius_m is None):
            raise ValueError(
                "a lattice states rotor, or frame together with tip_radius_m, to be placed"
            )
        if self.rotor is not None and self.tip_radius_m is not None:
            raise ValueError("tip_radius_m places a frame's lattice; a rotor's is its own radius")
        # The geometry is validated by the lattice itself, with a unit radius:
        # the radius scales every coordinate and changes no rule.
        self.build(1.0)
        return self

    @property
    def states_geometry(self) -> bool:
        """Whether any ``build_lattice`` parameter is stated (FR-1042)."""
        return any(getattr(self, key) is not None for key in _LATTICE_KEYS)

    def build(self, tip_radius: float) -> ProbeLattice:
        """Build the lattice at a tip radius in the simulation's length unit."""
        stated = {
            key: getattr(self, key) for key in _LATTICE_KEYS if getattr(self, key) is not None
        }
        if self.lateral_radius is None:
            stated["lateral_radius"] = max(2.5, self.r_outer or 2.5)
        return build_lattice(tip_radius=tip_radius, **stated)


class TrefftzSpec(BaseModel):
    """The ``[farfield.trefftz]`` sub-table: the Trefftz variants and their geometry (FR-454).

    Attributes
    ----------
    variant : list of {'sections', 'wake', 'plane'}
        The variants, written as one word or a list.
    stations : int
        The station count per side the plan lays when it adds a distribution,
        and below which it warns.
    distance_bref : float
        The distance of the B and C plane behind the selected families, in BREF.
    half_width_bref, half_height_bref, spacing_bref : float, optional
        C, wing: the plane's half extents and grid spacing, in BREF; unstated,
        the plan's reuse rule decides and the defaults apply.
    station : float, optional
        C, rotor: the lattice station x/R of the rotor channels; unstated, the
        last station.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    variant: Annotated[
        list[Literal["sections", "wake", "plane", "power"]], BeforeValidator(_one_or_list)
    ] = Field(
        min_length=1,
        description=(
            "The Trefftz variants: sections (the section loads), wake (the solver's wake "
            "lines), plane (a plane of probes); one word or a list."
        ),
    )
    stations: int = Field(
        default=80,
        ge=2,
        description=(
            "The station count per side of the symmetry plane the plan lays when it adds a "
            "distribution, and below which it warns."
        ),
    )
    distance_bref: float = Field(
        default=0.25,
        gt=0.0,
        description="The distance of the wake and probe plane behind the families, in BREF.",
    )
    half_width_bref: float | None = Field(
        default=None, gt=0.0, description="Half the wing plane's extent across the span, in BREF."
    )
    half_height_bref: float | None = Field(
        default=None, gt=0.0, description="Half the wing plane's extent across the height, in BREF."
    )
    spacing_bref: float | None = Field(
        default=None, gt=0.0, description="The wing plane's grid spacing, in BREF."
    )
    station: float | None = Field(
        default=None, description="The rotor lattice station x/R the rotor channels are read at."
    )

    @model_validator(mode="after")
    def _each_variant_once(self) -> TrefftzSpec:
        _unique(list(self.variant), "[farfield.trefftz] variant")
        return self

    @property
    def states_plane(self) -> bool:
        """Whether a plane key is stated (FR-1042)."""
        return any(
            value is not None
            for value in (self.half_width_bref, self.half_height_bref, self.spacing_bref)
        )

    def plane_bref(self) -> tuple[float, float, float]:
        """Return the wing plane's half width, half height and spacing in BREF, with defaults."""
        return (
            self.half_width_bref or FARFIELD_DEFAULTS["half_width_bref"],
            self.half_height_bref or FARFIELD_DEFAULTS["half_height_bref"],
            self.spacing_bref or FARFIELD_DEFAULTS["spacing_bref"],
        )


class LedgersSpec(LatticeShape):
    """The ``[farfield.ledgers]`` sub-table: the balances and their survey lattice (FR-38, FR-454).

    Attributes
    ----------
    balances : list of str
        Any of the six balances of FR-479; all six by default.
    m_max : int
        The highest azimuthal order stored and used by gate G3; below half of
        the lattice's azimuth count.
    """

    balances: list[
        Literal["mass", "axial", "transverse", "torque", "in_plane_moment", "crossflow_energy"]
    ] = Field(
        default_factory=lambda: list(BALANCES),  # type: ignore[arg-type]
        description="The balances written: any of the six, all six by default.",
    )
    m_max: int = Field(
        default=6, ge=1, description="The highest azimuthal order stored and used by gate G3."
    )

    @model_validator(mode="after")
    def _the_orders_fit_the_azimuths(self) -> LedgersSpec:
        _unique(list(self.balances), "[farfield.ledgers] balances")
        n_psi = self.build(1.0).n_psi
        if 2 * self.m_max >= n_psi:
            raise ValueError(
                f"m_max = {self.m_max} needs more than {2 * self.m_max} azimuths to avoid "
                f"aliasing, and the lattice has n_psi = {n_psi}"
            )
        return self


def _family_selection(value: object) -> object:
    from pyflightstream.cases.pproc import validated_family_selection

    return validated_family_selection(value)


class FarfieldSpec(BaseModel):
    """One named analysis in ``[[farfields]]``; geometry keys belong to their variant.

    ``sections`` requires families and accepts a station count. ``wake`` and
    ``plane`` read the whole field. ``power`` requires a rotor or a frame
    lattice and optionally writes balances. Names default to the variant.

    Attributes
    ----------
    variant : str
        One analysis: sections (A), wake (B), plane (C), or power (D).
    name : str
        Unique entry label, defaulting to the variant word.
    export_type : str
        last_step, avg_window, or default; default reads the last unsteady step.
    families : str or list of str
        Required selection for sections; the other variants read the whole field.
    stations : int or tuple of float
        A station count per side for sections; lattice positions x/R for power.
    distance_bref : float
        Wake or plane distance behind the whole geometry in BREF.
    half_width_bref, half_height_bref, spacing_bref : float
        Plane half extents and uniform spacing in BREF.
    station : float
        Power station x/R; defaults to the last lattice station.
    rotor : str
        Reference rotor whose hub and radius place the power lattice.
    frame, tip_radius_m : str and float
        Alternative power lattice placement: frame and reference radius in metres.
    n_r, r_inner, r_outer, n_psi : int or float
        Power lattice ring count, radial bounds r/R, and uniform azimuth count.
    lateral_radius, lateral_stations : float or tuple of float
        Power lattice closure cylinder radius r/R and ring positions x/R.
    hub_width, tip_width : float
        Power lattice clustering widths r/R near the hub and tip.
    m_max : int
        Highest azimuthal harmonic, strictly below half the lattice azimuth count.
    balances : list of str
        Optional ledger balances; omitted, no ledger table is requested.
    last_revs : float, optional
        Positive trailing revolutions on the row's rotor clock, for this entry's average.
    last_steps : int, optional
        Positive trailing step count, exclusive with last_revs; omitted, use the row window.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    variant: Literal["sections", "wake", "plane", "power"]
    name: str = Field(default="", min_length=1)
    export_type: Literal["last_step", "avg_window", "default"] = "default"
    families: Annotated[str | list[str] | None, BeforeValidator(_family_selection)] = None
    stations: int | tuple[float, ...] | None = None
    distance_bref: float = Field(default=0.25, gt=0)
    half_width_bref: float | None = Field(default=None, gt=0)
    half_height_bref: float | None = Field(default=None, gt=0)
    spacing_bref: float | None = Field(default=None, gt=0)
    station: float | None = None
    rotor: str | None = None
    frame: str | None = None
    tip_radius_m: float | None = None
    n_r: int | None = None
    r_inner: float | None = None
    r_outer: float | None = None
    n_psi: int | None = None
    lateral_radius: float | None = None
    lateral_stations: tuple[float, ...] | None = None
    hub_width: float | None = None
    tip_width: float | None = None
    m_max: int = 6
    balances: list[str] = Field(default_factory=list)
    last_revs: float | None = Field(default=None, gt=0, strict=True)
    last_steps: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _keys_belong_to_the_variant(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        variant = value.get("variant")
        if not isinstance(variant, str) or variant not in TREFFTZ_VARIANTS:
            return value
        for key in value:
            readers = _KEY_VARIANTS.get(key)
            if readers is not None and variant not in readers:
                reason = ""
                if key == "families":
                    reason = (
                        "; wake, plane and power read the whole field, "
                        "so there is no family selection"
                    )
                raise ValueError(f"{key} is read by {', '.join(readers)}, not {variant!r}{reason}")
        return value

    @model_validator(mode="after")
    def _analysis_geometry(self) -> FarfieldSpec:
        if self.last_revs is not None and self.last_steps is not None:
            raise ValueError("state only one window, not both last_revs and last_steps")
        if not self.name:
            self.name = self.variant
        if self.variant == "sections":
            if self.families is None:
                raise ValueError('variant = "sections" requires families')
            if self.stations is not None and (
                not isinstance(self.stations, int) or self.stations < 2
            ):
                raise ValueError('variant = "sections" reads stations as a count of at least 2')
        if self.variant == "power":
            if isinstance(self.stations, int):
                raise ValueError('variant = "power" reads stations as a list of x/R positions')
            _ = self.ledgers
        return self

    @property
    def trefftz(self) -> TrefftzSpec:
        """Return the numerical trace parameters of this single analysis."""
        keys = ("distance_bref", "half_width_bref", "half_height_bref", "spacing_bref", "station")
        values = {key: getattr(self, key) for key in keys}
        values.update(
            variant=[self.variant], stations=self.stations if self.variant == "sections" else 80
        )
        if values["stations"] is None:
            values["stations"] = 80
        return TrefftzSpec.model_validate(values)

    @property
    def ledgers(self) -> LedgersSpec | None:
        """Return the power analysis's validated lattice, or None for a trace."""
        if self.variant != "power":
            return None
        keys = (*_LATTICE_KEYS, "rotor", "frame", "tip_radius_m", "m_max", "balances")
        return LedgersSpec.model_validate({key: getattr(self, key) for key in keys})


_KEY_VARIANTS = {
    "families": ("sections",),
    "stations": ("sections", "power"),
    "distance_bref": ("wake", "plane"),
    **{key: ("plane",) for key in ("half_width_bref", "half_height_bref", "spacing_bref")},
    **{
        key: ("power",)
        for key in (
            *_LATTICE_KEYS[1:],
            "station",
            "rotor",
            "frame",
            "tip_radius_m",
            "m_max",
            "balances",
        )
    },
}


def farfield_entries(value: Any) -> Any:
    """Refuse the retired table with equivalent array entries."""
    if not isinstance(value, dict):
        return value
    if value.get("farfield") is not None:
        old = value["farfield"]
        entries = []
        if isinstance(old, dict):
            trace = old.get("trefftz", {})
            variants = trace.get("variant", [])
            for variant in [variants] if isinstance(variants, str) else variants:
                entry = {"variant": variant}
                entry.update(
                    {k: v for k, v in trace.items() if variant in _KEY_VARIANTS.get(k, ())}
                )
                if variant == "sections":
                    entry["families"] = old.get("families", "all")
                entries.append(entry)
            if "ledgers" in old:
                power = {"variant": "power", "balances": list(BALANCES), **old["ledgers"]}
                if "station" in trace:
                    power["station"] = trace["station"]
                entries.append(power)
        replacement = "\n\n".join(
            "[[farfields]]\n"
            + "\n".join(f"{key} = {json.dumps(val)}" for key, val in entry.items())
            for entry in entries
        )
        raise ValueError(
            "[farfield] was replaced by [[farfields]], one analysis per entry:\n"
            + replacement
            + '\nA 0.44.0 "plane" with ledgers on a rotor row becomes the "power" entry (D), '
            'not the "plane" entry (C); keep C only to request the velocity plane as well.'
        )
    return value


def _refuse_filename_collisions(entries: Any) -> None:
    """Refuse sanitized filename collisions even on case-insensitive filesystems."""
    names: dict[str, str] = {}
    for entry in entries if isinstance(entries, list | tuple) else ():
        name = (
            entry.name
            if isinstance(entry, FarfieldSpec)
            else (entry.get("name", entry.get("variant")) if isinstance(entry, dict) else None)
        )
        if not isinstance(name, str):
            continue
        spelling = re.sub(r"[^A-Za-z0-9_.+-]", "_", name).casefold()
        previous = names.get(spelling)
        if previous is not None and previous != name:
            raise ValueError(
                f"[[farfields]] names {previous!r} and {name!r} share file spelling "
                f"{spelling!r} ignoring case; choose names with distinct file spellings"
            )
        names[spelling] = name
