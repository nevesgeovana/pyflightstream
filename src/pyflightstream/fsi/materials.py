"""Versioned database of structural materials for the blade properties.

Pipeline role: the material half of the blade's structural properties.
:func:`pyflightstream.fsi.sections.blade_properties_from_sections`
multiplies the section constants of a blade's geometry by the density
and the elastic moduli of one entry here, and records the entry, its
source and :data:`MATERIALS_DATABASE_VERSION` beside the numbers it
produced, so a configuration generated from a geometry says where every
number came from.

The rule of this module: no number without a source. Every entry takes
its density, Young's modulus, shear modulus and Poisson's ratio from ONE
cited data set, consistently, so the four numbers of an entry never mix
two references. When a source tabulates no shear modulus the entry
derives it as E / (2 (1 + nu)) and says so in
:attr:`Material.shear_modulus_basis`; every entry shipped today takes
its shear modulus as tabulated, which is not always equal to that
isotropic relation (the titanium entry below differs from it by about
4 percent), and the tabulated value is the one kept.

The numbers are room-temperature typical values of the condition the
entry names, fit for a structural model of a blade and not a substitute
for the design allowables of a certified part.

Changing a number, a source or the set of entries is a new database
version: :data:`MATERIALS_DATABASE_VERSION` moves in the same commit,
so a configuration generated before the change still names the version
it was generated from.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pyflightstream.fsi.errors import FsiInputError

__all__ = [
    "MATERIALS",
    "MATERIALS_DATABASE_VERSION",
    "SHEAR_MODULUS_DERIVED",
    "SHEAR_MODULUS_TABULATED",
    "Material",
    "MaterialSource",
    "material",
]

#: Version of the database below. Moves whenever an entry's number,
#: source, condition or key changes, or an entry is added or removed.
MATERIALS_DATABASE_VERSION = "1"

#: The shear modulus as the source tabulates it.
SHEAR_MODULUS_TABULATED = "tabulated by the source"
#: The shear modulus derived from the source's E and nu.
SHEAR_MODULUS_DERIVED = "derived as E / (2 (1 + nu)) from the source's E and nu"


@dataclass(frozen=True)
class MaterialSource:
    """Where an entry's four numbers were read.

    Attributes
    ----------
    document : str
        Title and publisher of the data set, as printed on it.
    table : str
        The table, section or rows of the document the numbers were
        read from.
    condition : str
        The material condition the data set states (temper, heat
        treatment, product form), with its own qualifiers.
    url : str
        Where the document was consulted.
    consulted : str
        ISO date on which the numbers were read from the document.
    """

    document: str
    table: str
    condition: str
    url: str
    consulted: str

    def citation(self) -> str:
        """Return the source as one line of text, for the provenance record."""
        return (
            f"{self.document}; {self.table}; condition: {self.condition}; "
            f"{self.url} (consulted {self.consulted})"
        )


@dataclass(frozen=True)
class Material:
    """One homogeneous, isotropic, linear elastic material.

    Attributes
    ----------
    key : str
        Lookup key of :func:`material`.
    name : str
        Human-readable name with its condition.
    density_kg_per_m3 : float
        Density rho [kg/m^3].
    youngs_modulus_pa : float
        Young's modulus E [Pa].
    shear_modulus_pa : float
        Shear modulus G [Pa].
    poisson_ratio : float
        Poisson's ratio nu [-].
    shear_modulus_basis : str
        :data:`SHEAR_MODULUS_TABULATED` or :data:`SHEAR_MODULUS_DERIVED`.
    source : MaterialSource
        The one data set all four numbers come from.
    notes : str
        What the source itself says about the numbers' standing.
    """

    key: str
    name: str
    density_kg_per_m3: float
    youngs_modulus_pa: float
    shear_modulus_pa: float
    poisson_ratio: float
    shear_modulus_basis: str
    source: MaterialSource
    notes: str = ""

    def __post_init__(self) -> None:
        """Refuse an entry no isotropic elastic solid can have."""
        for name in ("density_kg_per_m3", "youngs_modulus_pa", "shear_modulus_pa"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise FsiInputError(
                    f"material {self.key!r}: {name} = {value!r} is not a positive "
                    "finite number; a density or a modulus of zero, a negative one "
                    "or a NaN describes no solid"
                )
        if not -1.0 < self.poisson_ratio < 0.5:
            raise FsiInputError(
                f"material {self.key!r}: Poisson's ratio {self.poisson_ratio!r} lies "
                "outside (-1, 0.5), the range a stable isotropic solid can have"
            )
        if self.shear_modulus_basis not in (SHEAR_MODULUS_TABULATED, SHEAR_MODULUS_DERIVED):
            raise FsiInputError(
                f"material {self.key!r}: shear_modulus_basis must say whether G is "
                f"tabulated or derived, got {self.shear_modulus_basis!r}"
            )
        if not self.source.document.strip() or not self.source.url.strip():
            raise FsiInputError(
                f"material {self.key!r} names no source document; no number enters "
                "this database without one"
            )


_TI_6AL_4V = Material(
    key="ti-6al-4v-grade5-annealed",
    name="Titanium Ti-6Al-4V (Grade 5), annealed",
    density_kg_per_m3=4430.0,  # 4.43 g/cc
    youngs_modulus_pa=113.8e9,  # 113.8 GPa
    shear_modulus_pa=44.0e9,  # 44 GPa
    poisson_ratio=0.342,
    shear_modulus_basis=SHEAR_MODULUS_TABULATED,
    source=MaterialSource(
        document=(
            "ASM Aerospace Specification Metals Inc., material data sheet "
            '"Titanium Ti-6Al-4V (Grade 5), Annealed" (UNS R56400)'
        ),
        table=(
            "Physical Properties (Density 4.43 g/cc) and Mechanical Properties "
            "(Modulus of Elasticity 113.8 GPa, Poisson's Ratio 0.342, "
            "Shear Modulus 44 GPa), metric column"
        ),
        condition="annealed, annealing temperature 700-785 C, as the data sheet states",
        url=(
            "https://www.aerospacemetals.com/wp-content/uploads/2023/07/"
            "Titanium-Ti-6Al-4V-Grade-5-Annealed.pdf"
        ),
        consulted="2026-09-25",
    ),
    notes=(
        "The data sheet attributes its values to Allvac and its references. "
        "Its shear modulus is kept as tabulated; E / (2 (1 + nu)) from the same "
        "sheet would give 42.4 GPa."
    ),
)

_AL_7075_T6 = Material(
    key="al-7075-t6",
    name="Aluminum 7075-T6",
    density_kg_per_m3=2810.0,  # 2.81 g/cc
    youngs_modulus_pa=71.7e9,  # 71.7 GPa
    shear_modulus_pa=26.9e9,  # 26.9 GPa
    poisson_ratio=0.33,
    shear_modulus_basis=SHEAR_MODULUS_TABULATED,
    source=MaterialSource(
        document=(
            "ASM Aerospace Specification Metals Inc., material data sheet "
            '"Aluminum 7075-T6; 7075-T651" (UNS A97075)'
        ),
        table=(
            "Physical Properties (Density 2.81 g/cc) and Mechanical Properties "
            "(Modulus of Elasticity 71.7 GPa, Poisson's Ratio 0.33, "
            "Shear Modulus 26.9 GPa), metric column"
        ),
        condition="T6 temper, typical values",
        url=(
            "https://www.aerospacemetals.com/wp-content/uploads/2023/06/"
            "Aluminum-7075-T6-7075-T651.pdf"
        ),
        consulted="2026-09-25",
    ),
    notes=(
        "The data sheet marks the density and the modulus of elasticity as "
        "Aluminum Association typical values, NOT FOR DESIGN; its modulus is "
        "the average of tension and compression."
    ),
)

#: Every entry of the database, by key. Read-only.
MATERIALS: Mapping[str, Material] = MappingProxyType(
    {entry.key: entry for entry in (_TI_6AL_4V, _AL_7075_T6)}
)


def material(key: str) -> Material:
    """Return the database entry named ``key``.

    Parameters
    ----------
    key : str
        One of the keys of :data:`MATERIALS`, for example
        ``"ti-6al-4v-grade5-annealed"``.

    Returns
    -------
    Material
        The entry, with its source.

    Raises
    ------
    FsiInputError
        When no entry carries that key; the message lists the keys.

    Examples
    --------
    >>> from pyflightstream.fsi.materials import material
    >>> titanium = material("ti-6al-4v-grade5-annealed")
    >>> titanium.youngs_modulus_pa
    113800000000.0
    """
    try:
        return MATERIALS[key]
    except KeyError:
        known = ", ".join(sorted(MATERIALS))
        raise FsiInputError(
            f"no material {key!r} in the materials database (version "
            f"{MATERIALS_DATABASE_VERSION}); it holds: {known}. An entry is added "
            "with its source, in src/pyflightstream/fsi/materials.py"
        ) from None
