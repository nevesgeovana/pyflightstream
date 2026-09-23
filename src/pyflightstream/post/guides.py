"""The generated pproc guides: ``VARIABLES.md`` and ``WRITING-EQUATIONS.md``.

Two pages written INTO the pproc input folder of a workspace, where whoever is
writing a pproc artifact is already standing: every variable a product states
with its definition, and how to write a custom equation, a glossary entry, the
phase-locked table and a group rename.

GENERATED FROM THE CODE, which is the property that matters and why this is a
function and not two files in the repository. A page written by hand beside a
schema goes stale the first time the schema moves, and nothing notices. These
read the models and the constants they document, so a table or a column added
without a line here produces a guide that is MISSING it rather than one that is
WRONG about it, and a test turns the missing line into a failure.

WHERE A USER MEETS THEM. ``pyfs-workspace init`` writes them with the rest of the
input library, ``pyfs-matrix plan`` writes them again for a workspace made
before they existed, carrying the ``[glossary]`` of every pproc artifact it
holds, and ``pyfs-matrix post`` does the same. Writing is IDEMPOTENT: a page
whose content would not change is not touched, so a run does not dirty a
versioned workspace. Only the two names in :data:`PPROC_GUIDE_NAMES` are ever
written; any other file of the folder is the user's.

THIS MODULE IS IN `post` AND NOT IN `workspace` because it documents the pproc
spec (`cases`) AND the products (`post`), so it belongs in the layer that may
depend on both. The lower layers reach it through the registry
:func:`pyflightstream.workspace.register_input_guide`, never by an import.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

from pyflightstream._expressions import ALLOWED_FUNCTIONS
from pyflightstream._tokens import FX_INT, FZ_INT, INTEGRATED_SECTION_COLUMNS, MY_INT, STRIP_LENGTH
from pyflightstream.cases import EquationSpec, PhaseLockedSpec, PprocSpec
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.products import (
    PHASE_LOCKED_COLUMNS,
    ROTOR_COEFFICIENT_COLUMNS,
    UNSTEADY_AXIS_COLUMNS,
)

__all__ = [
    "PPROC_GUIDE_NAMES",
    "VARIABLE_DEFINITIONS",
    "write_pproc_guides",
    "write_workspace_pproc_guides",
]

#: The two guides written into the pproc input folder.
PPROC_GUIDE_NAMES: tuple[str, ...] = ("VARIABLES.md", "WRITING-EQUATIONS.md")

#: What each variable IS, with its unit. The package's own glossary; a pproc's
#: ``[glossary]`` is listed beside it and never merged into it. A test holds
#: that every column constant listed by the variables page has an entry here.
VARIABLE_DEFINITIONS: dict[str, str] = {
    STRIP_LENGTH: "m. Midpoint-to-midpoint strip length; the endpoint stations get half strips",
    FX_INT: "N. Fx times Strip_length, in the recorded section axes at this row's STEP and azimuth",
    FZ_INT: "N. Fz times Strip_length, in the recorded section axes at this row's STEP and azimuth",
    MY_INT: (
        "N m. Moment times Strip_length, about this station's quarter chord (X_QC, Z_QC), "
        "retaining the export's section-plane moment sense at this STEP and azimuth"
    ),
    "ALPHA": "deg. The angle of attack the solver reports it ran at, as the row wrote it",
    "BETA": "deg. The sideslip angle the solver reports it ran at, as the row wrote it",
    "MACH": "-. The Mach number of that point",
    "RE": "millions. The Reynolds number the solver reports",
    "VINF": "m/s. The free-stream velocity the solver reports",
    "VREF": "m/s. The solver's reference velocity, which it normalises a coefficient by",
    "ALT": "ft. The altitude the row states; NA where it states none",
    "RHO": "kg/m3. The air density the run resolved for that point",
    "TEMP": "K. The air temperature the run resolved for that point",
    "MU": "Pa s. The dynamic viscosity",
    "J": (
        "-. The advance ratio the row requested; NA on a row that turns no rotor, "
        "and on one that states its speed as RPM"
    ),
    "J_CLOCK": (
        "-. The advance ratio the CLOCK rotor RAN at, V/(n D) from this point's free "
        "stream, the speed the record kept and that rotor's diameter; NA where the "
        "record or the reference does not say"
    ),
    "RPM_CLOCK": (
        "rev/min. The speed the CLOCK rotor turned at, with its hand. The CLOCK rotor "
        "is the one CLOCK_MOTION names, or the only rotor the row turns; a row turning "
        "several and naming none has no clock and both columns are NA"
    ),
    "SREF": "m2. The reference area",
    "CREF": "m. The reference chord",
    "BREF": "m. The reference span",
    "XMOM": "m. The x of the moment reference point",
    "YMOM": "m. The y of the moment reference point",
    "ZMOM": "m. The z of the moment reference point",
    "FIRST_STEP": "-. The first solver step of the window a row was averaged over, 1-based",
    "LAST_STEP": "-. The last solver step of that window, inclusive",
    "STEPS": "-. How many solver steps the window holds",
    "REDUCTION": "-. Which reduction a row is: time_average, phase_locked or per_blade",
    "ROTOR": "-. The alias of the rotor a row is about; NA where it is about none",
    "AZIMUTH": "deg. Where blade one of that rotor is, 0 to 360, from its datum and its sense",
    "STEP": "-. The solver step a row states; in a phase-locked table, of the LAST revolution",
    "REVOLUTIONS": "-. How many revolutions entered the mean at that azimuth",
    "CT": "-. Thrust coefficient, T / (rho n^2 D^4)",
    "CQ": "-. Torque coefficient, Q / (rho n^2 D^5)",
    "CP": "-. Power coefficient, 2 pi CQ",
    "ETA": "-. Propulsive efficiency, J CT / CP",
    "ETAW": "-. The efficiency with the wind-axis force in place of the thrust, J CTW / CP",
    **{
        f"C{part}{axes}{at}": f"-. {what} coefficient in {system} axes{about}"
        for axes, system in (("W", "wind"), ("S", "stability"), ("B", "body"))
        for part, what, at, about in (
            ("D", "Drag", "", ""),
            ("Y", "Side-force", "", ""),
            ("L", "Lift", "", ""),
            ("R", "Rolling-moment", "25", ", about the moment reference point"),
            ("M", "Pitching-moment", "25", ", about the moment reference point"),
            ("N", "Yawing-moment", "25", ", about the moment reference point"),
        )
    },
}

_GENERATED = "GENERATED FROM THE CODE by pyflightstream. Do not edit: it is rewritten."


def _pproc_table_spellings() -> list[str]:
    """How each `PprocSpec` field is spelled in a pproc file, derived not assumed.

    A page that says it is generated from the code is TRUSTED, so a wrong
    spelling in it is worse than the same sentence written by hand, and the
    model declares ``extra="forbid"``: a name offered as a table that is not one
    is a refusal the guide walked its reader into.

    The mapping is the TOML one: a model-typed field is a table, a list of
    model-typed entries is an array of tables, a mapping is a table with your
    own keys under it, and anything else is a key rather than a table.
    """
    spellings: list[str] = []
    for name in sorted(PprocSpec.model_fields):
        annotation = PprocSpec.model_fields[name].annotation
        origin = get_origin(annotation)

        def is_model(candidate: object) -> bool:
            # DUCK-TYPED, and not `issubclass(candidate, BaseModel)`: a module
            # under `post` may reach for numpy and little else, and
            # `model_fields` is the attribute this function reads anyway.
            return isinstance(candidate, type) and hasattr(candidate, "model_fields")

        # `X | None` carries the model in its arguments, and its origin is the
        # union rather than nothing, which is what `phase_locked` is.
        optional = [arg for arg in get_args(annotation) if arg is not type(None)]
        inner = optional[0] if origin in (Union, UnionType) and len(optional) == 1 else None

        if is_model(annotation) or is_model(inner):
            spellings.append(f"`[{name}]`")
        elif origin in (list, tuple) and any(is_model(arg) for arg in get_args(annotation)):
            spellings.append(f"`[[{name}]]`, one table per entry")
        elif origin is dict:
            spellings.append(f"`[{name}]`, with your own keys under it")
        else:
            spellings.append(f"`{name}`, a key rather than a table")
    return spellings


def _defined(name: str, shown: str | None = None) -> str:
    """One line of the variables page: the name, and its definition where there is one."""
    text = VARIABLE_DEFINITIONS.get(name)
    label = f"`{shown or name}`"
    return f"- {label}: {text}" if text else f"- {label}"


def _variables_page(glossary: Sequence[tuple[str, str]]) -> str:
    lines = [
        "# Variables",
        "",
        _GENERATED,
        "",
        "Every name below is a column some product of the post stage states. An",
        "`[equations]` expression may read any column the unsteady polar holds; see",
        f"`{PPROC_GUIDE_NAMES[1]}` beside this page.",
        "",
        "## Every product carries these",
        "",
        "A file that does not state its flight condition cannot say what it is a",
        "file of, which is why these are on every product and not on the polar",
        "alone.",
        "",
    ]
    lines += [_defined(name) for name in CONTEXT_COLUMNS]
    lines += [
        "",
        "## Optional integrated sectional loads",
        "",
        "Requested per distribution with `integrate = true`.",
        "",
    ]
    lines += [_defined(name) for name in INTEGRATED_SECTION_COLUMNS]
    lines += [
        "",
        "## A rotor carries these, one set per rotor",
        "",
        "Each is suffixed with the rotor's alias, because these make physical sense",
        "for ONE rotor and not for several summed together: the diameters and the",
        "speeds that normalise them are different numbers.",
        "",
    ]
    lines += [_defined(name, f"{name}_<alias>") for name in ROTOR_COEFFICIENT_COLUMNS]
    lines += [
        "",
        "## The unsteady polar adds these",
        "",
        "`polars/P<sim>_<name>_uns_avg.csv` opens with the window, then the block",
        "above and the moment point, then EVERY PLOTTED COLUMN under the name the",
        "solver's export prints, `<parameter>_<group>`, averaged over the window;",
        "then the axis coefficients below, then your `[equations]` as",
        "`<NAME>_<alias>`, then the setup of the row.",
        "",
    ]
    lines += [_defined(name) for name in ("FIRST_STEP", "LAST_STEP", "STEPS")]
    lines += [_defined(name) for name in ("XMOM", "YMOM", "ZMOM")]
    lines += [_defined(name, f"{name}_<group>") for name in UNSTEADY_AXIS_COLUMNS]
    lines += [
        "",
        "## The phase-locked table leads with these",
        "",
        "`probes/<point>_phase_locked[_<ALIAS>].csv`, where the pproc declares",
        "`[phase_locked]`: one row per azimuthal position, then the plotted columns.",
        "",
    ]
    lines += [_defined(name) for name in PHASE_LOCKED_COLUMNS if name not in CONTEXT_COLUMNS]
    lines += [
        "",
        "## What a pproc may declare, and how each one is spelled",
        "",
    ]
    lines += [f"- {spelling}" for spelling in _pproc_table_spellings()]
    if glossary:
        lines += [
            "",
            "## Your own definitions, from `[glossary]`",
            "",
            "Listed beside the package's own and never merged into them, so it stays",
            "visible which definitions are yours.",
            "",
        ]
        lines += [f"- `{name}`: {text}" for name, text in glossary]
    lines.append("")
    return "\n".join(lines)


def _equations_page() -> str:
    equation_fields = ", ".join(f"`{name}`" for name in EquationSpec.model_fields)
    gate_fields = ", ".join(f"`{name}`" for name in PhaseLockedSpec.model_fields)
    functions = ", ".join(f"`{name}`" for name in ALLOWED_FUNCTIONS)
    lines = [
        "# Writing equations",
        "",
        _GENERATED,
        "",
        "## An equation points at an ALIAS, never at a mesh family",
        "",
        "That is not a restriction for its own sake. An alias is what gives the",
        "derived coefficient a name that says which body it is about, so every",
        "coefficient you derive is the column `<NAME>_<alias>`. A family list would",
        "give it nothing to be called, and a `families` key is refused.",
        "",
        f"Fields: {equation_fields}.",
        "",
        "```toml",
        "[equations.T]",
        'expression = "-FX"',
        'meshes_alias = "PUSHER"',
        'frame = "SMRP"',
        "```",
        "",
        "writes the column `T_PUSHER`.",
        "",
        "## Where the columns appear",
        "",
        "In the unsteady polar, `polars/P<sim>_<name>_uns_avg.csv`, after the axis",
        "coefficients and before the setup of the row. An expression is evaluated",
        "once per row, from the columns THAT ROW already holds: the window, the",
        f"condition block, the moment point, the averaged plots (see `{PPROC_GUIDE_NAMES[0]}`),",
        "the axis coefficients and whatever of the setup is a number. `pyfs-matrix",
        "post` evaluates them, so an equation added after a campaign ran needs no",
        "new run.",
        "",
        "## What an expression may hold",
        "",
        "Numbers, names, `+ - * / **`, unary minus, parentheses, and the functions",
        f"{functions}. The trigonometric ones take radians. Nothing else: the",
        "text is parsed and walked, never executed, and a construct outside this",
        "list is refused WHEN THE PPROC IS READ, naming it.",
        "",
        "## How a symbol finds its column",
        "",
        "A plotted column is named `<parameter>_<group>`, and you name the group of a",
        "rotor in `[[plots.groups]]`, usually for the alias and the frame. A symbol",
        "`S` of an equation about alias `A` in frame `F` is, first match wins:",
        "",
        "1. another equation named `S`: its value on that row;",
        "2. `S_A_F`, then `S_F_A`, where the equation states a `frame`;",
        "3. `S_A`;",
        "4. the column `S`, exactly as the file spells it (`RHO`, `FX_MRP_TOTAL`).",
        "",
        "The alias comes before the exact name because the equation is ABOUT the",
        "alias: the setup of a row carries the native export's own `CL` and `Cx`, one",
        "instant of the last step, and `CL` of an equation about `WING` is `CL_WING`.",
        "",
        "So `FX` above reads `FX_PUSHER_SMRP`, the axial force a group named",
        "`PUSHER_SMRP` plots. A symbol none of the four answers REFUSES THE WHOLE",
        "BLOCK: no derived column is written, the polar is written without them, and",
        "`products.json` says why under `polars/<file>#equations`, naming the",
        "equation, the symbol, the spellings tried and the columns there are. It is",
        "never a column of `NA`. A row that holds `NA` under a column you read, or",
        "where the arithmetic has no answer, reads `NA` in that one cell, and the",
        "same entry says which.",
        "",
        "## An equation may name another equation",
        "",
        "You write the equations in a TOML table, and a TOML table has no order",
        "you may rely on, so the package works out the order for you: every",
        "equation is evaluated after the ones its expression names.",
        "",
        "```toml",
        "[equations.CT_FLIGHT]",
        'expression = "T / (0.5 * RHO * VINF**2 * SREF)"   # T is evaluated first',
        'meshes_alias = "PUSHER"',
        "",
        "[equations.T]",
        'expression = "-FX"',
        'meshes_alias = "PUSHER"',
        'frame = "SMRP"',
        "```",
        "",
        "A symbol this table does not define is a column the row already carries,",
        "`RHO` above is one, so you never have to declare a base.",
        "",
        "A chain that loops is REFUSED WHEN THIS FILE IS READ, and the refusal",
        "names the equations in the loop, because a cycle has no order to",
        "evaluate it in. If you want the order itself,",
        "`PprocSpec.equation_order()` returns it.",
        "",
        "## The glossary",
        "",
        "`[glossary]` says what each of YOUR symbols means, one line per symbol, and",
        f"`{PPROC_GUIDE_NAMES[0]}` lists it beside the package's own definitions:",
        "",
        "```toml",
        "[glossary]",
        'T = "N. Thrust of the pusher, the axial force of its own frame, sign flipped"',
        'CT_FLIGHT = "-. Thrust over the free-stream dynamic pressure and SREF"',
        "```",
        "",
        "## Renaming",
        "",
        "A group is named by the input that declares it, and the product file",
        "carries that name. If you rename a group, the products you already have",
        "are moved for you by `pyflightstream.workspace.rename_group_products`,",
        "which ARCHIVES each file before it moves it and never deletes anything.",
        "",
        "## The phase-locked table",
        "",
        f"Fields: {gate_fields}.",
        "",
        "```toml",
        "[phase_locked]",
        "min_revolutions = 4.0",
        "last_revolutions_avg = 2.0",
        "```",
        "",
        "The reduction is generated when the matrix row turns AT LEAST",
        "`min_revolutions`, counted over the whole run of that rotor and not over the",
        "exported window. Not reaching it does not refuse the polar or any other",
        "product; it only means no phase-locked table, and `products.json` says so",
        "with both numbers. `last_revolutions_avg` may not exceed `min_revolutions`.",
        "Under one revolution no table from 0 to 360 can be filled, so state at least",
        "1: a smaller depth is skipped at post, saying so.",
        "",
        "With the table, `probes/<point>_phase_locked[_<ALIAS>].csv` is ONE ROW PER",
        "AZIMUTHAL POSITION, 0 to 360: at each azimuth, the mean of the samples at",
        "that azimuth across the last `last_revolutions_avg` revolutions. A column of",
        "one blade, one ending in the blade's family, is tabulated by THAT blade's",
        "azimuth; every other column by blade one's. Without the table the file is",
        "the series of blade passages it has always been.",
        "",
    ]
    return "\n".join(lines)


def _write_if_different(path: Path, text: str) -> bool:
    """Write ``text`` to ``path`` unless it already holds exactly that; say whether it wrote."""
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, UnicodeDecodeError):
        pass  # unreadable is different
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def write_pproc_guides(
    folder: str | Path,
    *,
    glossary: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
    changed: list[Path] | None = None,
) -> list[Path]:
    """Write the variable reference and the equation guide into a pproc input folder.

    Generated from the models and the column constants they document. A page
    whose content would not change is NOT rewritten, so the call is idempotent
    and leaves a versioned workspace clean; no file under another name is ever
    touched.

    Parameters
    ----------
    folder : str or pathlib.Path
        The pproc input folder, ``inputs/pproc`` of a workspace. Created if it
        is not there.
    glossary : mapping or sequence of pairs, optional
        The user's own symbol definitions, from the ``[glossary]`` table of a
        pproc. Listed BESIDE the package's own and never merged into them.
    changed : list, optional
        Receives the pages this call actually wrote, which is none on a second
        call.

    Returns
    -------
    list of pathlib.Path
        The two pages, in :data:`PPROC_GUIDE_NAMES` order, written or not.

    Examples
    --------
    >>> import tempfile
    >>> folder = tempfile.mkdtemp()
    >>> first: list = []
    >>> [page.name for page in write_pproc_guides(folder, changed=first)]
    ['VARIABLES.md', 'WRITING-EQUATIONS.md']
    >>> again: list = []
    >>> _ = write_pproc_guides(folder, changed=again)
    >>> len(first), len(again)
    (2, 0)
    """
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    pairs = sorted(glossary.items()) if isinstance(glossary, Mapping) else list(glossary or ())
    pages = (
        (target / PPROC_GUIDE_NAMES[0], _variables_page(pairs)),
        (target / PPROC_GUIDE_NAMES[1], _equations_page()),
    )
    for path, text in pages:
        if _write_if_different(path, text) and changed is not None:
            changed.append(path)
    return [path for path, _text in pages]


def write_workspace_pproc_guides(inputs_dir: str | Path) -> list[Path]:
    """Write the two guides into ``<inputs_dir>/pproc``; return the pages that CHANGED.

    The input-guide writer this package registers with
    :func:`pyflightstream.workspace.register_input_guide`, which is how
    ``pyfs-workspace init``, ``pyfs-matrix plan`` and ``pyfs-matrix post`` reach
    it. The ``[glossary]`` of EVERY pproc artifact in the folder is listed, each
    entry naming the artifact it came from. An artifact that does not parse is
    left to the stage that reads it, which names the fault; it costs the guides
    nothing but its own glossary.
    """
    folder = Path(inputs_dir) / "pproc"
    pairs: list[tuple[str, str]] = []
    if folder.is_dir():
        for artifact in sorted(folder.glob("*.toml")):
            try:
                stated = tomllib.loads(artifact.read_text(encoding="utf-8")).get("glossary")
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                continue
            if isinstance(stated, Mapping):
                pairs += [
                    (str(name), f"{text} (from {artifact.name})")
                    for name, text in sorted(stated.items())
                ]
    changed: list[Path] = []
    write_pproc_guides(folder, glossary=pairs, changed=changed)
    return changed
