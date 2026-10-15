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

from typing import Annotated, Literal

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
TREFFTZ_VARIANTS: tuple[str, ...] = ("sections", "wake", "plane")
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
        list[Literal["sections", "wake", "plane"]], BeforeValidator(_one_or_list)
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
        min_length=1,
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
    """The ``[farfield]`` table: what the far field is computed over, and how (FR-454).

    Attributes
    ----------
    families : str or list of str
        A selector word, an alias, a family name or a list, the grammar of
        ``[sections]``.
    trefftz : TrefftzSpec, optional
        The Trefftz variants.
    ledgers : LedgersSpec, optional
        The survey balances.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    families: Annotated[str | list[str], BeforeValidator(_family_selection)] = Field(
        description=(
            "What the far field is computed over: a selector word, an alias, a family name or "
            "a list, the grammar of [sections]."
        )
    )
    trefftz: TrefftzSpec | None = Field(default=None, description="The Trefftz-plane analyses.")
    ledgers: LedgersSpec | None = Field(
        default=None, description="The conservation balances of a survey lattice."
    )

    @model_validator(mode="after")
    def _selects_an_analysis(self) -> FarfieldSpec:
        if self.trefftz is None and self.ledgers is None:
            raise ValueError(
                "[farfield] selects no analysis: state [farfield.trefftz] with a variant, "
                "[farfield.ledgers], or both"
            )
        return self
