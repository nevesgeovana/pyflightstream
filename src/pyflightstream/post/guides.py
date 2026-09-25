"""The generated input guides: the pproc guides, ``INPUTS.md`` and ``input_template.md``.

The pproc guides are ``VARIABLES.md`` and ``WRITING-EQUATIONS.md``. Three pages
are written INTO the pproc input folder of a workspace, where whoever is
writing a pproc artifact is already standing: every variable a product states
with its definition; how to write a custom equation, a glossary entry, the
phase-locked table and a group rename; and, since 0.27.0 (G08), every key an
INPUT artifact may state, the matrix row, the setup, the pproc, the reference
and the geometry sidecar, with what it sets, its unit or values, the run types
or builds that accept it and the solver command it reaches.

A fourth, since 0.28.0 (G47), at the ROOT of the ``inputs`` folder: the input
template, one section per kind of input file a user writes, the files of
``profiles/`` among them, each with a complete example to copy. Every example
is a file the package reads as it stands, which its test holds by writing each
one where its title says and reading it with the reader the run uses; the
matrix's header is the layout's registry, the values a comment lists are read
from the registries that check them, and every key of the glossary's tables is
either stated by an example or named on the page as left out, with the reason.

THE INPUT GLOSSARY READS THE REGISTRIES THE CODE USES: the run types' key
tables, the matrix columns, the flight-condition vocabulary, the preset tables,
the export kinds, the sidecar readers' keys and the fields of every input
model. The MEANING of a key is the code's too: a model field's description,
its ``Attributes`` entry or its ``#:`` comment, or the :class:`InputKey` its
registry carries. A key added without one is a row with no meaning, which the
glossary's test refuses; nothing is written in the page by hand.

GENERATED FROM THE CODE, which is the property that matters and why this is a
function and not two files in the repository. A page written by hand beside a
schema goes stale the first time the schema moves, and nothing notices. These
read the models and the constants they document, so a table or a column added
without a line here produces a guide that is MISSING it rather than one that is
WRONG about it, and a test turns the missing line into a failure.

WHERE A USER MEETS THEM. ``pyfs-workspace init`` writes them with the rest of the
input library, ``pyfs-matrix plan`` writes them again for a workspace made
before they existed, carrying the ``[glossary]`` of every pproc artifact it
holds, and ``pyfs-matrix post`` does the same; the input glossary is written
by the same three, and so is the input template. Writing is IDEMPOTENT: a page
whose content would not change is not touched, so a run does not dirty a
versioned workspace. Only the names in :data:`PPROC_GUIDE_NAMES`,
:data:`INPUT_GLOSSARY_NAME` and :data:`INPUT_TEMPLATE_NAME` are ever written;
any other file of the folder is the user's.

THIS MODULE IS IN `post` AND NOT IN `workspace` because it documents the pproc
spec (`cases`) AND the products (`post`), and the input glossary reads the
preset tables and the sidecar readers of `workspace` besides, so it belongs in
the layer that may depend on all of them. The lower layers reach it through
the registry :func:`pyflightstream.workspace.register_input_guide`, never by an
import.
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import textwrap
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cache, lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import metadata as distribution_metadata
from pathlib import Path
from types import MappingProxyType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pyflightstream._errors import InputArtifactError
from pyflightstream._expressions import ALLOWED_FUNCTIONS
from pyflightstream._tokens import (
    FX_INT,
    FZ_INT,
    INTEGRATED_SECTION_COLUMNS,
    MY_INT,
    POLAR_ID_COLUMN,
    STRIP_LENGTH,
)
from pyflightstream.cases import (
    EXPORT_KIND_MEANINGS,
    EXPORT_KINDS,
    FLAG_PHASES,
    RAW_PHASES,
    SOLVER_SETTING_COMMANDS,
    STEADY_ONLY_EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
    ActuatorBlock,
    CustomFlag,
    EquationSpec,
    InputKey,
    MeshImport,
    PhaseLockedSpec,
    PprocSpec,
    RawCommand,
    SolverSettings,
    SolverToggle,
    default_outputs,
)
from pyflightstream.cases.matrix import ATTITUDE_KEYS, COLUMN_MEANINGS, FLIGHT_CONDITION_KEYS
from pyflightstream.cases.workflows import (
    FREESTREAM_DIR,
    FREESTREAM_FORMS,
    LOADS_SELECTION_KEYS,
    RATE_VARIABLES,
    ROW_KEY_MEANINGS,
    WORKFLOWS,
    command_accepted_on,
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.products import (
    PHASE_LOCKED_COLUMNS,
    ROTOR_COEFFICIENT_COLUMNS,
    UNSTEADY_AXIS_COLUMNS,
)
from pyflightstream.script.helpers import ROTATION_COMMANDS
from pyflightstream.versions import known_versions
from pyflightstream.workspace import REFERENCE_POINTS_FILE
from pyflightstream.workspace.flight_condition import PINNED_KEYS
from pyflightstream.workspace.inputs import (
    EXECUTABLES_FILE,
    GEOMETRY_SIDECAR_KEYS,
    HPC_DIR,
    HPC_FORMATS,
    IMPORT_TABLE,
    LOCAL_EXECUTABLES_FILE,
    RAW_MESH_CONDITION_KEYS,
    TRAILING_EDGE_DETECT_KEYS,
    TRAILING_EDGES_TABLE,
    WALLTIME_ARITHMETIC,
    ReferenceArtifact,
)
from pyflightstream.workspace.matrix import (
    PRESET_ALIASES,
    PRESET_RECORDED_ONLY,
    PRESET_RESERVED_KEYS,
)
from pyflightstream.workspace.wake_edges import edge_types, length_scale, node_file_units

__all__ = [
    "ARTIFACT_HEADINGS",
    "DOCS_URL_LABEL",
    "GLOSSARY_COLUMNS",
    "INPUT_GLOSSARY_NAME",
    "INPUT_TEMPLATE_NAME",
    "PACKAGE_SET_FIELDS",
    "PPROC_GUIDE_NAMES",
    "REFERENCE_BLOCK_HEADINGS",
    "VARIABLE_DEFINITIONS",
    "GlossaryRow",
    "GlossaryTable",
    "TemplateExample",
    "TemplateSection",
    "input_glossary_markdown",
    "input_glossary_tables",
    "input_template_markdown",
    "write_input_glossary",
    "write_input_template",
    "write_pproc_guides",
    "write_workspace_input_glossary",
    "write_workspace_input_template",
    "write_workspace_pproc_guides",
]

#: The two guides written into the pproc input folder.
PPROC_GUIDE_NAMES: tuple[str, ...] = ("VARIABLES.md", "WRITING-EQUATIONS.md")

#: What each variable IS, with its unit. The package's own glossary; a pproc's
#: ``[glossary]`` is listed beside it and never merged into it. A test holds
#: that every column constant listed by the variables page has an entry here.
VARIABLE_DEFINITIONS: dict[str, str] = {
    POLAR_ID_COLUMN: (
        "-. The polar a row comes from, the matrix row's POL; the first column of "
        "every table the post writes"
    ),
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
        "The first column of every table is the polar, and no line precedes the",
        "header:",
        "",
        _defined(POLAR_ID_COLUMN),
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
        "`polars/P<sim>_<name>_uns_avg.csv` opens with `POL` and the window, then the block",
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
        "Every post writes `post.log` beside `products.json`, even when clean;",
        "the manifest names it under `log`. It records every named skip and",
        "stage warning, and a rebuild archives it with the products.",
        "`post.log.json` beside it holds the same records for a program, one",
        "per WARNING line with its point, product, message and remedy; the",
        "manifest names it under `log_json`. Frozen solves and unread blocks",
        "warn by default; `--check-frozen` asks to refuse affected averages",
        "instead.",
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


# --- the input glossary, INPUTS.md (G08 of 0.27.0) ---------------------------

#: The input glossary's file name. It is written beside ``VARIABLES.md``: the
#: page of what the inputs mean next to the page of what the products mean.
INPUT_GLOSSARY_NAME = "INPUTS.md"

#: The columns of every table of the input glossary, in order.
GLOSSARY_COLUMNS: tuple[str, ...] = (
    "Key",
    "What it sets",
    "Unit or values",
    "Accepted by",
    "Command",
)

#: The five input artifacts the glossary covers, in the page's order, by the
#: heading each gets.
ARTIFACT_HEADINGS: Mapping[str, str] = MappingProxyType(
    {
        "matrix": "The run matrix",
        "setup": "The setup artifact, `inputs/setups/<id>.toml`",
        "pproc": "The post-processing artifact, `inputs/pproc/<id>.toml`",
        "reference": "The reference artifact, `inputs/references/<id>.toml`",
        "geometry": "The geometry sidecar, `inputs/geometries/<stem>.boundaries.toml`",
    }
)

#: The three fields of the reference artifact that are NOT keys of the file:
#: each collects named top-level blocks, told apart by their ``kind``, so the
#: glossary gives each block a table of its own under the heading here.
REFERENCE_BLOCK_HEADINGS: Mapping[str, str] = MappingProxyType(
    {
        "rotors": '`[<NAME>]` with `kind = "rotor"`',
        "actuators": '`[<NAME>]` with `kind = "actuator"`',
        "points": "`[<NAME>]` with any other `kind`",
    }
)

#: The fields of an input model that the PACKAGE sets and a file never states,
#: by model and field; the glossary leaves them out. A probe entry's resolved
#: points file is filled when a row binds, and the artifact a raw line or a
#: flag came from is bound by the workspace for the run record.
PACKAGE_SET_FIELDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("ProbesSpec", "resolved_points_file"),
        ("RawCommand", "setup"),
        ("RawCommand", "source"),
        ("CustomFlag", "setup"),
    }
)

#: The solver command a field of an input model reaches, where the model's own
#: module holds no registry that says it; by model and field. The solver
#: settings have theirs beside their model
#: (:data:`pyflightstream.cases.SOLVER_SETTING_COMMANDS`).
_FIELD_COMMANDS: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("PprocSpec", "sections"): "NEW_SURFACE_SECTION_DISTRIBUTION",
        ("PprocSpec", "volume_section"): (
            "CREATE_NEW_RECTANGLE_VOLUME_SECTION, CREATE_NEW_CIRCLE_VOLUME_SECTION"
        ),
        ("PprocSpec", "plots"): "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        ("PprocSpec", "probes"): "UNSTEADY_SOLVER_NEW_FLUID_PLOT, NEW_PROBE_POINT",
        ("PprocSpec", "time_averaging"): "SOLVER_TIME_AVERAGING",
        ("PprocSpec", "vtk_variables"): "SET_VTK_EXPORT_VARIABLES",
        ("PprocSpec", "base_regions"): "DETECT_BASE_REGIONS_BY_SURFACE",
        ("VolumeSectionSpec", "format"): (
            "EXPORT_VOLUME_SECTION_VTK, EXPORT_VOLUME_SECTION_TECPLOT"
        ),
        ("ReferenceArtifact", "area_m2"): "SOLVER_SET_REF_AREA",
        ("ReferenceArtifact", "chord_m"): "SOLVER_SET_REF_LENGTH",
        ("ReferenceArtifact", "frames"): "CREATE_NEW_COORDINATE_SYSTEM",
        ("ActuatorBlock", "axis"): "SET_ACTUATOR_AXIS",
        ("ActuatorBlock", "tip_radius_m"): "SET_ACTUATOR_RADIUS",
        ("ActuatorBlock", "hub_radius_m"): "SET_ACTUATOR_RADIUS",
        ("ActuatorBlock", "swirl"): "SET_PROP_ACTUATOR_SWIRL",
        ("ActuatorBlock", "profile_units"): "SET_PROP_ACTUATOR_PROFILE",
        ("MeshImport", "units"): "IMPORT",
        ("MeshOperation", "op"): (
            "SURFACE_SCALE, SURFACE_RENAME, SURFACE_MIRROR, TRANSLATE_SURFACE_IN_FRAME, "
            + ", ".join(ROTATION_COMMANDS)
        ),
    }
)

#: The words a row says after its meaning when no line of the run's script
#: carries its key's value, followed by what takes the value instead. A column
#: headed "What it sets" otherwise reads as a solver input the run applies, and
#: a key the builders only check (``ROTOR_SHEDDING``) or leave to the post
#: stage, the scheduler or a program beside the script would read as one.
_NO_SCRIPT_LINE = "No line of the script carries its value"

#: What takes the value of an input model's field that no line of the script
#: carries, by model and field; the registries of keys carry theirs on their
#: :class:`InputKey` (``unscripted``). A tier-1 test builds every solver
#: setting at two values and holds both halves: a field named here leaves the
#: script byte-identical, and a field not named here changes it.
_FIELD_UNSCRIPTED: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("SolverSettings", "timeout_s"): "the executor stops the solver process at it.",
        ("SolverSettings", "walltime_margin_s"): (
            "the wall-clock program the run writes beside the script reads it."
        ),
    }
)

#: What each artifact is, one paragraph, under its heading.
_ARTIFACT_INTROS: Mapping[str, str] = MappingProxyType(
    {
        "matrix": (
            "One row per line of the pipe-delimited matrix file, in the columns below. "
            "`FLIGHT_CONDITION` holds `KEY:value` pairs separated by commas, and "
            "`VAR_NAMES_VALUES` holds `KEY: value` pairs separated by `/`. A key no "
            "run type reads is refused, naming the run types that do."
        ),
        "setup": (
            "The solver settings a row's `SET` names, in this package's words or in "
            "the solver's own. A key that names no setting, no alias and no reserved "
            "key is refused, naming the keys that apply."
        ),
        "pproc": (
            "What a row's `PPROC` names: the definitions the script emits before the "
            "solve, the exports a point leaves and the products written after it. The "
            "columns those products write are in `VARIABLES.md`, and how to write an "
            "equation is in `WRITING-EQUATIONS.md`, both beside this page."
        ),
        "reference": (
            "What a row's `REF` names: the reference lengths the coefficients are "
            "divided by, the moment point, the frames, the aliases, and one block per "
            "rotor, actuator disc and named point. Lengths are in metres."
        ),
        "geometry": (
            "The file beside a geometry that names its boundaries and, for a raw mesh "
            "(`.obj`, `.stl`), how it is imported and where its trailing edges are."
        ),
    }
)

_PAGE_INTRO = (
    "Every key an input artifact of a workspace may state, one row each: what it "
    "sets, its unit or the values it takes, the run types or builds that accept it "
    "where the code says, and the solver command it reaches where one does. Each "
    "meaning is read from the code beside the key, so a key the package gains "
    "arrives here with its meaning. A key whose value no line of the run's script "
    f'carries says so, "{_NO_SCRIPT_LINE}", and names what takes the value '
    "instead. A blank `Accepted by` means the code states no "
    "restriction of run type or build; a blank command means the key reaches no "
    f"command of its own. What the products state is in `{PPROC_GUIDE_NAMES[0]}` "
    "beside this page."
)


@dataclass(frozen=True)
class GlossaryRow:
    """One key of an input artifact, as the input glossary states it.

    Attributes
    ----------
    key : str
        The key as the file spells it.
    meaning : str
        What it sets, read from the code.
    values : str
        Its unit, or the values it takes.
    accepted : str
        The run types or builds that accept it, where the code says.
    commands : tuple of str
        The solver commands it reaches.
    """

    key: str
    meaning: str
    values: str = ""
    accepted: str = ""
    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class GlossaryTable:
    """One table of the input glossary: the keys of one table of one artifact.

    Attributes
    ----------
    artifact : str
        Which artifact, a key of :data:`ARTIFACT_HEADINGS`.
    heading : str
        The table as the file spells it, or its name.
    intro : str
        What the table is.
    rows : tuple of GlossaryRow
        One per key the table may hold.
    commands : tuple of str
        The solver commands the key holding this table reaches.
    """

    artifact: str
    heading: str
    intro: str
    rows: tuple[GlossaryRow, ...]
    commands: tuple[str, ...] = ()


_SPHINX_ROLE = re.compile(r":(?:py:)?\w+:`~?([^`]+)`")
_SECTION_RULE = re.compile(r"^-{3,}$")
_FIELD_LINE = re.compile(r"^    (\w+)\s*:")


def _markdown(text: str) -> str:
    """Turn a docstring's reStructuredText inline markup into Markdown's."""
    text = _SPHINX_ROLE.sub(lambda match: f"`{match.group(1).rsplit('.', 1)[-1]}`", text)
    return text.replace("``", "`")


def _first_sentence(text: str) -> str:
    """Return the first sentence of the first paragraph, on one line."""
    paragraph = inspect.cleandoc(text).split("\n\n", 1)[0]
    flat = " ".join(paragraph.split())
    end = re.search(r"(?<!\be\.g)(?<!\bi\.e)\.(?=\s|$)", flat)
    return _markdown(flat[: end.end()] if end else flat)


def _sentence(text: str) -> str:
    """Return a registry's phrase as a sentence: a capital first, a full stop last."""
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith(".") else text + "."


@cache
def _attribute_entries(model: type) -> Mapping[str, str]:
    """Read the ``Attributes`` section of a model's docstring, by field name.

    A numpydoc entry names one field or several, comma separated and possibly
    over several lines, then ``: type``; its description is the indented block
    under it. Only the model's OWN docstring is read, never an inherited one.
    """
    lines = inspect.cleandoc(model.__doc__ or "").splitlines()
    starts = [
        index
        for index in range(len(lines) - 1)
        if lines[index].strip() == "Attributes" and _SECTION_RULE.match(lines[index + 1].strip())
    ]
    entries: dict[str, str] = {}
    if not starts:
        return entries
    names: list[str] = []
    body: list[str] = []

    def flush() -> None:
        for name in names:
            entries.setdefault(name, "\n".join(body).strip())

    index = starts[0] + 2
    while index < len(lines):
        line = lines[index]
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if line.strip() and not line[0].isspace() and _SECTION_RULE.match(following):
            break  # the next section
        if line.strip() and not line[0].isspace():
            flush()
            header = line
            while header.rstrip().endswith(",") and index + 1 < len(lines):
                index += 1
                header += " " + lines[index].strip()
            names = [name.strip() for name in header.split(" : ", 1)[0].split(",") if name.strip()]
            body = []
        else:
            body.append(line.strip())
        index += 1
    flush()
    return entries


@cache
def _class_sources(module_name: str) -> Mapping[str, str]:
    """Return the source of every top-level class of one module, by class name.

    ONE PARSE PER MODULE. ``inspect.getsource`` of a class parses its whole
    module on every call, and the glossary asks it of two hundred fields.
    """
    module = sys.modules.get(module_name)
    try:
        source = inspect.getsource(module) if module is not None else ""
    except (OSError, TypeError):
        return {}
    lines = source.splitlines()
    return {
        node.name: "\n".join(lines[node.lineno - 1 : node.end_lineno])
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef)
    }


@cache
def _comment_entries(model: type) -> Mapping[str, str]:
    """Read the ``#:`` comment above each field of a model's own source, by field name.

    The convention every model here writes a field's documentation in when it
    is not in the docstring. A model whose source cannot be read (an install
    without sources) has none, and its fields fall back to the docstring.
    """
    source = _class_sources(model.__module__).get(model.__name__)
    if not source:
        return {}
    lines = textwrap.dedent(source).splitlines()
    entries: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = _FIELD_LINE.match(line)
        if match is None or match.group(1) not in getattr(model, "model_fields", {}):
            continue
        block: list[str] = []
        above = index - 1
        while above >= 0 and lines[above].strip().startswith("#:"):
            block.append(lines[above].strip()[2:].strip())
            above -= 1
        if block:
            entries[match.group(1)] = "\n".join(reversed(block))
    return entries


def _field_meaning(model: type, name: str, field: Any) -> str:
    """Return a field's meaning: its description, its Attributes entry or its ``#:`` comment."""
    for text in (
        getattr(field, "description", None),
        _attribute_entries(model).get(name),
        _comment_entries(model).get(name),
    ):
        if text and text.strip():
            return _first_sentence(text)
    return ""


def _is_model(candidate: object) -> bool:
    # DUCK-TYPED for the reason `_pproc_table_spellings` gives.
    return isinstance(candidate, type) and hasattr(candidate, "model_fields")


def _nested_model(annotation: object) -> tuple[str, type] | None:
    """Whether a field holds a table: ``("table" | "array" | "named", model)``, else None."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        inner = [arg for arg in args if arg is not type(None)]
        return _nested_model(inner[0]) if len(inner) == 1 else None
    if _is_model(annotation):
        return ("table", annotation)  # type: ignore[return-value]
    if origin in (list, tuple) and args and _is_model(args[0]):
        return ("array", args[0])
    if origin is dict and len(args) == 2 and _is_model(args[1]):
        return ("named", args[1])
    return None


def _toml(value: object) -> str:
    """Render a default the way a TOML file writes it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    return str(value)


_SCALAR_WORDS: Mapping[object, str] = MappingProxyType(
    {bool: "true or false", int: "an integer", float: "a number", str: "text"}
)

#: What a list of each scalar holds, in words.
_LIST_WORDS: Mapping[str, str] = MappingProxyType(
    {"an integer": "integers", "a number": "numbers", "text": "names"}
)


def _type_words(annotation: object) -> str:
    """Say in words what a TOML file writes for a field of this type."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        return " or ".join(_type_words(arg) for arg in args if arg is not type(None))
    if origin is Annotated:
        if annotation == SolverToggle:
            return "true or false, or ENABLE or DISABLE"
        return _type_words(args[0])
    if origin is Literal:
        return " or ".join(f"`{_toml(arg)}`" for arg in args)
    if annotation in _SCALAR_WORDS:
        return _SCALAR_WORDS[annotation]
    if origin is tuple and args and args[-1] is not Ellipsis:
        numeric = all(_type_words(arg) in ("an integer", "a number") for arg in args)
        return f"{len(args)} {'numbers' if numeric else 'values'}"
    if origin in (list, tuple) and args:
        item = _type_words(args[0])
        return "a list of " + _LIST_WORDS.get(item, item)
    if origin is dict:
        return "a table of your own keys"
    return getattr(annotation, "__name__", str(annotation))


def _bounds(field: Any) -> list[str]:
    """Read the numeric bounds a field declares off its metadata, by attribute."""
    words = []
    for item in getattr(field, "metadata", ()):
        for attribute, sign in (("ge", ">="), ("gt", ">"), ("le", "<="), ("lt", "<")):
            bound = getattr(item, attribute, None)
            if bound is not None:
                words.append(f"{sign} {bound}")
    return words


def _command_tokens(commands: Sequence[str]) -> list[str]:
    """Return the tokens of a command's one valued argument, where it has exactly one."""
    registry = CommandRegistry.load()
    for name in commands:
        entry = registry.commands.get(name)
        valued = [arg for arg in (entry.args if entry else ()) if arg.values]
        if len(valued) == 1:
            return [str(token) for token in valued[0].values or ()]
    return []


def _field_values(
    field: Any, nested: tuple[str, type] | None, path: str, commands: tuple[str, ...]
) -> str:
    """Describe a field's unit or values: its table, or its type, bounds and default."""
    if nested is not None:
        kind, _model = nested
        return {
            "table": f"a table; see `[{path}]` below",
            "array": f"an array of tables; see `[[{path}]]` below",
            "named": f"tables under your own names; see `[{path}.<NAME>]` below",
        }[kind]
    words = _type_words(field.annotation)
    if words == "text":
        tokens = _command_tokens(commands)
        if tokens:
            words = "one of " + ", ".join(f"`{token}`" for token in tokens)
    parts = [words, *_bounds(field)]
    if field.is_required():
        parts.append("required")
    elif field.default_factory is None and field.default is not None:
        parts.append(f"default `{_toml(field.default)}`")
    elif field.default_factory is None:
        parts.append("optional")
    return ", ".join(part for part in parts if part)


def _builds(commands: Sequence[str]) -> str:
    """Return the registered builds on which a row may reach one of ``commands``.

    By :func:`~pyflightstream.cases.workflows.command_accepted_on`, the rule
    the builders refuse by: documented or verified, and verified for a command
    a feature reaches only once a run verified it (``SOLVER_TIME_AVERAGING``),
    so a key is never listed on a build that refuses it. Empty when that is
    every registered build: the command's own evidence restricts nothing, so
    the row says nothing.
    """
    if not commands:
        return ""
    registry = CommandRegistry.load()
    versions = known_versions()
    accepting = []
    for version in versions:
        for name in commands:
            entry = registry.commands.get(name)
            if entry is not None and command_accepted_on(entry, version):
                accepting.append(version.canonical)
                break
    if len(accepting) == len(versions):
        return ""
    return "builds " + ", ".join(accepting) if accepting else "no registered build"


def _split_commands(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _joined(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


def _meaning_and_what_takes_it(meaning: str, unscripted: str) -> str:
    """Return a meaning, then what takes the value where no line of the script carries it.

    Nothing is added to an EMPTY meaning: a key registered without one must
    stay a row with no meaning, which the glossary's test refuses.
    """
    if not meaning or not unscripted:
        return meaning
    return f"{meaning} {_NO_SCRIPT_LINE}: {unscripted}"


def _field_row(model: type, name: str, field: Any, path: str) -> GlossaryRow:
    """One field of an input model as a row: its meaning, values, builds and command."""
    if model is SolverSettings:
        commands = _split_commands(SOLVER_SETTING_COMMANDS.get(name, ""))
        restriction = "steady rows" if name in LOADS_SELECTION_KEYS else ""
    else:
        commands = _split_commands(_FIELD_COMMANDS.get((model.__name__, name), ""))
        restriction = ""
    nested = _nested_model(field.annotation)
    return GlossaryRow(
        key=name,
        meaning=_meaning_and_what_takes_it(
            _field_meaning(model, name, field),
            _FIELD_UNSCRIPTED.get((model.__name__, name), ""),
        ),
        values=_field_values(field, nested, path, commands),
        accepted=_joined(restriction, _builds(commands)),
        commands=commands,
    )


def _model_tables(
    artifact: str,
    model: type,
    heading: str,
    path: str,
    *,
    commands: tuple[str, ...] = (),
    blocks: Mapping[str, str] | None = None,
    extra: Mapping[str, Callable[[], GlossaryTable]] | None = None,
) -> list[GlossaryTable]:
    """Build a model's table, then the table of every field that holds one, in field order.

    ``path`` is the TOML path of the table, which names the tables under it:
    a model field is ``[path.field]``, a list of models ``[[path.field]]`` and
    a mapping of models ``[path.field.<NAME>]``. ``blocks`` names the fields
    that are collections of top-level blocks and the heading each block
    takes; ``extra`` adds a table of keys no model declares after a field.
    """
    rows: list[GlossaryRow] = []
    children: list[GlossaryTable] = []
    for name, field in model.model_fields.items():  # type: ignore[attr-defined]
        if (model.__name__, name) in PACKAGE_SET_FIELDS:
            continue
        nested = _nested_model(field.annotation)
        if blocks and name in blocks and nested is not None:
            children += _model_tables(artifact, nested[1], blocks[name], "<NAME>")
            continue
        child_path = f"{path}.{name}" if path else name
        row = _field_row(model, name, field, child_path)
        if extra and name in extra:
            # A table of keys no model declares: its row points at that table.
            row = replace(row, values=f"a table; see `[{child_path}]` below")
        rows.append(row)
        if nested is not None:
            kind, child = nested
            child_heading = {
                "table": f"`[{child_path}]`",
                "array": f"`[[{child_path}]]`",
                "named": f"`[{child_path}.<NAME>]`",
            }[kind]
            below = f"{child_path}.<NAME>" if kind == "named" else child_path
            children += _model_tables(artifact, child, child_heading, below, commands=row.commands)
        if extra and name in extra:
            children.append(extra[name]())
    intro = _first_sentence(model.__doc__ or "")
    return [GlossaryTable(artifact, heading, intro, tuple(rows), commands), *children]


def _key_rows(keys: Mapping[str, InputKey]) -> tuple[GlossaryRow, ...]:
    """Rows from a registry of keys that carries an :class:`InputKey` per key."""
    rows = []
    for key, entry in keys.items():
        commands = _split_commands(entry.command)
        rows.append(
            GlossaryRow(
                key=key,
                meaning=_markdown(_meaning_and_what_takes_it(entry.meaning, entry.unscripted)),
                values=entry.values,
                accepted=_joined(entry.accepted, _builds(commands)),
                commands=commands,
            )
        )
    return tuple(rows)


def _matrix_tables() -> list[GlossaryTable]:
    ordered: list[str] = []
    for workflow in WORKFLOWS.values():
        ordered += [key for key in workflow.keys if key not in ordered]
    ordered += [key for key in ROW_KEY_MEANINGS if key not in ordered]
    rows = []
    for key in ordered:
        entry = ROW_KEY_MEANINGS.get(key, InputKey(""))
        readers = [name for name, workflow in WORKFLOWS.items() if key in workflow.keys]
        run_types = "every run type" if len(readers) == len(WORKFLOWS) else ", ".join(readers)
        commands = _split_commands(entry.command)
        rows.append(
            GlossaryRow(
                key=key,
                meaning=_meaning_and_what_takes_it(entry.meaning, entry.unscripted),
                values=entry.values,
                accepted=_joined(run_types or entry.accepted, _builds(commands)),
                commands=commands,
            )
        )
    condition = [
        GlossaryRow(key, _sentence(f"constrains {what}"), unit)
        for key, (unit, what) in FLIGHT_CONDITION_KEYS.items()
    ] + [GlossaryRow(key, _sentence(what), unit) for key, (unit, what) in ATTITUDE_KEYS.items()]
    return [
        GlossaryTable(
            "matrix",
            "The columns",
            "The columns of a row, in file order.",
            _key_rows(COLUMN_MEANINGS),
        ),
        GlossaryTable(
            "matrix",
            "The `FLIGHT_CONDITION` cell",
            "The flow keys are a set of constraints on one flow state, and the keys given "
            "decide which quantity is solved for; the attitude keys fix where the aircraft "
            "points. Matched case-insensitively; the swept key carries the word `sweep`.",
            tuple(condition),
        ),
        GlossaryTable(
            "matrix",
            "The row keys, by run type",
            "Every key a run type reads off its row. Most are written in the "
            "`VAR_NAMES_VALUES` cell; a key with its own column, or of the "
            "`FLIGHT_CONDITION` cell, is written there, as its meaning says. A key "
            "`[[flags]]` of the row's setup declares is a key of the row too.",
            tuple(rows),
        ),
    ]


def _setup_tables() -> list[GlossaryTable]:
    aliases = []
    for alias, name in PRESET_ALIASES.items():
        commands = _split_commands(SOLVER_SETTING_COMMANDS.get(name, ""))
        aliases.append(GlossaryRow(alias, f"Read as `{name}`.", "", _builds(commands), commands))
    recorded = tuple(
        GlossaryRow(key, _sentence(f"kept in the artifact and emitted nowhere: {reason}"))
        for key, reason in PRESET_RECORDED_ONLY.items()
    )
    pins = tuple(
        GlossaryRow(
            key,
            _sentence(f"constrains {FLIGHT_CONDITION_KEYS[key][1]}"),
            FLIGHT_CONDITION_KEYS[key][0],
        )
        for key in PINNED_KEYS
    )
    return [
        *_model_tables("setup", SolverSettings, "Solver settings", ""),
        GlossaryTable(
            "setup",
            "The solver's own names, read as aliases",
            "A preset transcribed from a working session keeps working as written: each "
            "of these names a setting above. Two spellings of one setting in one preset "
            "are refused.",
            tuple(aliases),
        ),
        GlossaryTable(
            "setup",
            "Recorded, and emitting nothing",
            "Kept in the artifact, reaching no script, and named with its reason in a "
            "warning each time a row binds the preset.",
            recorded,
        ),
        GlossaryTable(
            "setup",
            "Tables and reserved keys",
            "The keys a preset may state that are not solver settings.",
            _key_rows(PRESET_RESERVED_KEYS),
        ),
        GlossaryTable(
            "setup",
            "`[flight_condition]`",
            "The fluid pins, each replacing what the standard atmosphere would supply. "
            "The velocity keys and `REmi` may not live here: they make a point that point.",
            pins,
        ),
        *_model_tables("setup", RawCommand, "`[[raw]]`", "raw"),
        *_model_tables("setup", CustomFlag, "`[[flags]]`", "flags"),
    ]


#: The commands a kind reaches where they are not its own verb of
#: :data:`~pyflightstream.cases.EXPORT_KINDS` (G45 of 0.28.0): a campaign's
#: Tecplot is written by the package from the VTK export, so the script reaches
#: the VTK's two commands and never the solver's Tecplot.
_KIND_COMMANDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"tecplot": ("SET_VTK_EXPORT_VARIABLES", "EXPORT_SOLVER_ANALYSIS_VTK")}
)


def _exports_table() -> GlossaryTable:
    """Build the table of the kinds ``[exports]`` may name, what each takes and where."""
    rows = []
    for kind, suffix, verb, only_unsteady in EXPORT_KINDS:
        if kind in VOLUME_SECTION_KINDS.values():
            continue
        try:
            PprocSpec(exports={kind: False})
            refuses_false = False
        except ValueError:
            refuses_false = True
        # THE DEFAULT IS READ OFF THE FUNCTION THAT DECIDES IT, with no table
        # and with a table declaring sections, rather than restated here.
        written = {
            has: any(
                name.endswith(suffix)
                for name in default_outputs(only_unsteady, {}, has_sections=has)
            )
            for has in (False, True)
        }
        if refuses_false:
            values = "true; false is refused"
        elif written[False]:
            values = "true or false, default true"
        elif written[True]:
            values = "true or false, default true where `[[sections.distributions]]` declares any"
        else:
            values = "true or false, default false"
        accepted = (
            "unsteady run types"
            if only_unsteady
            else "steady rows"
            if kind in STEADY_ONLY_EXPORT_KINDS
            else ""
        )
        commands = _KIND_COMMANDS.get(kind, (verb,))
        rows.append(
            GlossaryRow(
                key=kind,
                meaning=EXPORT_KIND_MEANINGS.get(kind, ""),
                values=values,
                accepted=_joined(accepted, _builds(commands)),
                commands=commands,
            )
        )
    return GlossaryTable(
        "pproc",
        "`[exports]`",
        "Which of the export kinds a point writes, one key per kind. The volume "
        "section's file is not named here: `[volume_section]` declares it.",
        tuple(rows),
    )


def _body_axes_table() -> GlossaryTable:
    return GlossaryTable(
        "reference",
        "`[body_axes]`",
        "Which model axis each body rate turns about; a configuration declaring none "
        "is one no row may turn.",
        tuple(
            GlossaryRow(axis, f"The model axis the row's `{rate}` turns about.", "`X`, `Y` or `Z`")
            for rate, axis in RATE_VARIABLES
        ),
    )


def _geometry_tables() -> list[GlossaryTable]:
    tables = [
        GlossaryTable(
            "geometry",
            "Top-level keys and tables",
            "Beside a saved simulation, `pyfs-matrix inventory` writes it; beside an OBJ "
            "with none, the plan writes its `boundaries` from the OBJ's groups; beside an "
            "STL, it is written by hand.",
            _key_rows(GEOMETRY_SIDECAR_KEYS),
        ),
        *_model_tables(
            "geometry",
            MeshImport,
            f"`[{IMPORT_TABLE}]`",
            IMPORT_TABLE,
            commands=_split_commands(GEOMETRY_SIDECAR_KEYS[IMPORT_TABLE].command),
        ),
    ]
    for table, keys in RAW_MESH_CONDITION_KEYS.items():
        tables.append(
            GlossaryTable(
                "geometry", f"`[{table}]`", GEOMETRY_SIDECAR_KEYS[table].meaning, _key_rows(keys)
            )
        )
        if table == TRAILING_EDGES_TABLE:
            tables.append(
                GlossaryTable(
                    "geometry",
                    f"`detect = {{ ... }}` of `[{table}]`",
                    "Detection on the surfaces named, the table form of `detect`.",
                    _key_rows(TRAILING_EDGE_DETECT_KEYS),
                )
            )
    return tables


@lru_cache(maxsize=1)
def input_glossary_tables() -> tuple[GlossaryTable, ...]:
    """Every table of the input glossary, in the page's order.

    Read from the registries the readers and the builders use and from the
    models' own fields, so a key the package gains is a row here; its meaning
    comes from the code beside it (a field's description, its ``Attributes``
    entry or its ``#:`` comment, or the registry's :class:`InputKey`), and a
    key that has none is a row with an empty meaning, which the glossary's
    test refuses.

    Returns
    -------
    tuple of GlossaryTable
        The matrix, the setup, the pproc, the reference and the geometry
        sidecar, each artifact's tables together.
    """
    return (
        *_matrix_tables(),
        *_setup_tables(),
        *_model_tables(
            "pproc",
            PprocSpec,
            "The tables and top-level keys",
            "",
            extra={"exports": _exports_table},
        ),
        *_model_tables(
            "reference",
            ReferenceArtifact,
            "Top-level keys and tables",
            "",
            blocks=REFERENCE_BLOCK_HEADINGS,
            extra={"body_axes": _body_axes_table},
        ),
        *_geometry_tables(),
    )


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def input_glossary_markdown() -> str:
    """Return the input glossary, ``INPUTS.md``, as Markdown.

    One section per input artifact and one table per table of the artifact,
    each row a key with its meaning, its unit or values, where it is accepted
    and the command it reaches. Generated from the code on every call.

    Examples
    --------
    >>> text = input_glossary_markdown()
    >>> text.splitlines()[0]
    '# Inputs'
    >>> "| `analysis_families` |" in text
    True
    """
    lines = ["# Inputs", "", _GENERATED, "", _PAGE_INTRO]
    current = None
    for table in input_glossary_tables():
        if table.artifact != current:
            current = table.artifact
            lines += ["", f"## {ARTIFACT_HEADINGS[current]}", "", _ARTIFACT_INTROS[current]]
        lines += ["", f"### {table.heading}", ""]
        if table.intro:
            lines += [table.intro, ""]
        if table.commands:
            lines += [f"Reaches {', '.join(f'`{name}`' for name in table.commands)}.", ""]
        lines.append("| " + " | ".join(GLOSSARY_COLUMNS) + " |")
        lines.append("|" + "---|" * len(GLOSSARY_COLUMNS))
        for row in table.rows:
            cells = [
                row.meaning,
                row.values,
                row.accepted,
                ", ".join(f"`{name}`" for name in row.commands),
            ]
            lines.append(f"| `{row.key}` | " + " | ".join(_cell(cell) for cell in cells) + " |")
    lines.append("")
    return "\n".join(lines)


def write_input_glossary(folder: str | Path, *, changed: list[Path] | None = None) -> Path:
    """Write the input glossary, ``INPUTS.md``, into ``folder``; return its path.

    Rewritten only when its content would change, so the call is idempotent
    and leaves a versioned workspace clean.

    Parameters
    ----------
    folder : str or pathlib.Path
        Where to write it: ``inputs/pproc`` of a workspace, beside
        ``VARIABLES.md``. Created if it is not there.
    changed : list, optional
        Receives the page when this call actually wrote it.

    Returns
    -------
    pathlib.Path
        The page, written or not.

    Examples
    --------
    >>> import tempfile
    >>> folder = tempfile.mkdtemp()
    >>> first: list = []
    >>> write_input_glossary(folder, changed=first).name
    'INPUTS.md'
    >>> again: list = []
    >>> _ = write_input_glossary(folder, changed=again)
    >>> len(first), len(again)
    (1, 0)
    """
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    page = target / INPUT_GLOSSARY_NAME
    if _write_if_different(page, input_glossary_markdown()) and changed is not None:
        changed.append(page)
    return page


def write_workspace_input_glossary(inputs_dir: str | Path) -> list[Path]:
    """Write ``INPUTS.md`` into ``<inputs_dir>/pproc``; return it if it CHANGED.

    The input-guide writer this package registers with
    :func:`pyflightstream.workspace.register_input_guide` beside the pproc
    guides, which is how ``pyfs-workspace init``, ``pyfs-matrix plan`` and
    ``pyfs-matrix post`` reach it.
    """
    changed: list[Path] = []
    write_input_glossary(Path(inputs_dir) / "pproc", changed=changed)
    return changed


# --- the input template, input_template.md (G47 of 0.28.0) --------------------

#: The input template's file name. It is written at the ROOT of a workspace's
#: ``inputs/`` folder, where the files whose format it shows live, and it links
#: the input glossary, which stays beside the pproc artifacts.
INPUT_TEMPLATE_NAME = "input_template.md"

#: The label of the installed distribution's ``Project-URL`` entry that names
#: the documentation site, as ``pyproject.toml`` declares it under
#: ``[project.urls]``.
DOCS_URL_LABEL = "Documentation"

#: The glossary as the template links it, one folder below the template.
_GLOSSARY_LINK = f"[`pproc/{INPUT_GLOSSARY_NAME}`](pproc/{INPUT_GLOSSARY_NAME})"


@cache
def _documentation_site() -> str:
    """Return the documentation site the installed package declares, or ``""``.

    READ FROM THE DISTRIBUTION'S OWN METADATA, the ``Project-URL`` labelled
    :data:`DOCS_URL_LABEL`, because a workspace is opened where the
    repository's ``docs/`` is not, and the address is the project's to
    declare, once, in ``pyproject.toml``. A page is ``<site><name>/`` for
    ``docs/<name>.md``. Without the metadata (the source tree imported with
    nothing installed) the template names each page by its file instead.
    """
    try:
        entries = distribution_metadata("pyflightstream").get_all("Project-URL") or []
    except PackageNotFoundError:
        return ""
    for entry in entries:
        label, _, url = str(entry).partition(",")
        if label.strip() == DOCS_URL_LABEL and url.strip():
            return url.strip().rstrip("/") + "/"
    return ""


def _page_link(name: str, title: str) -> str:
    """Return a link to ``docs/<name>.md`` on the site, or its file where no site is known."""
    site = _documentation_site()
    return f"[{title}]({site}{name}/)" if site else f"{title} (`docs/{name}.md`)"


@dataclass(frozen=True)
class TemplateExample:
    """One example file of the input template.

    Attributes
    ----------
    path : str
        Where the file goes, relative to the workspace root; the example
        block's title, so a reader copies it there and the suite writes it
        there before reading it back.
    language : str
        The language of the block's fence: ``toml``, ``text`` or ``csv``.
    text : str
        The file, ending in a newline.
    note : str
        What to know about this file before copying it, above the block.
    """

    path: str
    language: str
    text: str
    note: str = ""


@dataclass(frozen=True)
class TemplateSection:
    """One kind of input file on the input template.

    Attributes
    ----------
    heading : str
        The section's heading; for the five artifacts the glossary covers, the
        glossary's own heading of that artifact.
    intro : str
        What the file is for and where it lives.
    examples : tuple of TemplateExample
        The files the section shows, each complete and valid as it stands.
    after : str
        What the examples do not say by themselves, below them.
    left_out : mapping
        By the glossary's heading of a table, each reason to the keys of that
        table the examples leave out; an empty tuple of keys stands for every
        key of the table. It is written on the page, and the template's test
        holds that every key of every table is shown or named here.
    pages : tuple of (str, str)
        The documentation pages the section links, as (name, title).
    """

    heading: str
    intro: str
    examples: tuple[TemplateExample, ...]
    after: str = ""
    left_out: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType({})
    pages: tuple[tuple[str, str], ...] = ()


def _in_words(words: Sequence[str], last: str = "or") -> str:
    """Join a closed set of values as a sentence names it: ``a, b or c``."""
    listed = list(words)
    if len(listed) < 2:
        return "".join(listed)
    return f"{', '.join(listed[:-1])} {last} {listed[-1]}"


def _scaled_units() -> tuple[str, ...]:
    """Return the length units a points file may name: the recorded ones with a scale."""
    scaled = []
    for unit in node_file_units():
        try:
            length_scale(unit, "METER")
        except InputArtifactError:
            continue
        scaled.append(unit)
    return tuple(scaled)


#: The run matrix of the template, one mapping per row, by column. A column the
#: layout gains and a row does not state is written ``-``, the matrix's word
#: for "states nothing", so the header is always the layout the reader reads.
_MATRIX_ROWS: tuple[Mapping[str, str], ...] = (
    {
        "POL": "1001",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "clean",
        "DESCRIPTION": "ALPHA_SWEEP",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "-2.0,0.0,2.0,4.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "SYMMETRY_LOADS": "-",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "digits: 6",
    },
    {
        "POL": "1002",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "disc",
        "DESCRIPTION": "DISC_FROM_A_PROFILE",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "0.0,4.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "ACTUATOR: DISC / ACTUATOR_RPM: 2400 / PROFILE: prop_thrust",
    },
    {
        "POL": "1003",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "gust",
        "DESCRIPTION": "CUSTOM_FREE_STREAM",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "0.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "FREESTREAM: gust",
    },
)


def _matrix_example() -> str:
    """Return the template's run matrix: the layout's header, a dashed line, the rows."""
    columns = list(COLUMN_MEANINGS)
    table = [columns, *([row.get(column, "-") for column in columns] for row in _MATRIX_ROWS)]
    widths = [max(len(line[index]) for line in table) for index in range(len(columns))]
    lines = [
        " | ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in table
    ]
    return "\n".join([lines[0], "-" * len(lines[0]), *lines[1:]]) + "\n"


def _matrix_after() -> str:
    """How the matrix file is laid out, its columns read from the layout's registry."""
    # The glossary's own pointers ("see the table below") point into the
    # glossary, so they are cut here, where no such table follows.
    columns = "\n".join(
        f"{index}. `{name}`: {meaning.meaning}"
        + (f" ({meaning.values.split('; see ')[0]})" if meaning.values else "")
        for index, (name, meaning) in enumerate(COLUMN_MEANINGS.items(), start=1)
    )
    return (
        "The file is a pipe-separated table: the header line names the columns in "
        "exactly this order, a line of dashes may follow it, and then one row per "
        "line. A cell that states nothing holds `-`. The file carries no comment "
        "lines: every line after the header is a row, so a note goes in "
        "`DESCRIPTION`. A row runs only when `RUN` reads 1.\n\n"
        f"{columns}\n\n"
        "`FLIGHT_CONDITION` holds `KEY:value` pairs separated by commas, and exactly "
        "one key carries the word `sweep` where its value would be: that is the "
        "variable the row varies, over the values of `SWEEP_VALUES`, one point "
        "each. `VAR_NAMES_VALUES` holds `KEY: value` pairs separated by ` / `, the "
        "keys the row's run type reads. `REF`, `SET` and `PPROC` name the three "
        "artifacts below by id, and `GEOMETRY` names a file of "
        "`inputs/geometries/` with its extension.\n\n"
        "The first row sweeps the angle of attack, and writes `digits: 6`, a word "
        "the setup below declares as a flag. The second turns the actuator disc "
        "`DISC` of the reference with the radial thrust profile "
        "`inputs/profiles/prop_thrust.txt`, named by its stem. The third flies "
        "through the custom free stream `inputs/freestreams/gust.txt`, also by "
        "its stem, at zero angles, since the field sets the flow's direction."
    )


_SETUP_EXAMPLE = """\
# A setup artifact: the solver settings a row's SET column names by id. The id
# is the file name without .toml and begins with s, so this file is s001.
# A key is this package's name for a setting, or the solver's own name for it
# (NITER for iterations, max_parallel_threads for max_threads, ...). A key that
# names no setting, no alias and no reserved key is refused, naming the keys
# that apply. Top-level keys come before the first [table].

iterations = 500                  # solver iterations, a whole number >= 1
convergence = 1e-5                # the residual the solve stops at
boundary_layer = "TURBULENT"      # LAMINAR, TRANSITIONAL or TURBULENT
viscous_coupling = true           # true or false, or "ENABLE" or "DISABLE"
wall_collision_avoidance = true   # the solver's proximity avoidance
farfield_layers = 5               # the far-field layers; state them in every setup

# The solver's stabilization, switched and sized as a pair. The direct form,
# solver_stabilization = <strength>, is the other way to say it; a file states
# one of the two.
stabilization = true
stabilization_strength = 1.0

# The FLUID every row citing this setup inherits: pins that replace what the
# standard atmosphere would supply. A row stating one of them wins, key by key,
# and a row that solves its own density (it states REmi) drops RHOkgm3.
[flight_condition]
RHOkgm3 = 1.225                   # density, kg/m^3
MUPas = 1.789e-5                  # dynamic viscosity, Pa s
ASMPS = 340.29                    # speed of sound, m/s
TK = 288.15                       # static temperature, K
PPA = 101325.0                    # static pressure, Pa

# A solver command line stated verbatim, arguments included, which every row
# citing this setup emits before the phase it names, one of:
# @RAW_PHASES@.
[[raw]]
command = "PRINT s001"
before = "init"

# A solver command this setup exposes to the matrix under a word of your own:
# a row citing this setup writes "digits: 6" in its VAR_NAMES_VALUES cell, and
# the script carries SET_SIGNIFICANT_DIGITS 6. The command is written bare; the
# row states the value. before is optional, one of @FLAG_PHASES@.
[[flags]]
name = "digits"
command = "SET_SIGNIFICANT_DIGITS"
before = "setup"
"""

_PPROC_EXAMPLE = """\
# A post-processing artifact: what a row's PPROC column names by id; the id
# begins with p, so this file is p001. It says what each point defines before
# the solve, which files each point exports, and which products are written
# after the run. Every table is optional. The columns the products write are
# in pproc/VARIABLES.md, and how to write an equation in
# pproc/WRITING-EQUATIONS.md, both beside pproc/INPUTS.md.

# Top-level keys come before the first [table]; written under one, TOML files
# them in that table.
blade_pattern = '^Blade\\d+$'      # a regular expression telling a blade family from the airframe
base_regions = ["Base"]           # boundaries made base regions after the mesh opens;
                                  # a row's BASE_REGIONS wins over it
vtk_variables = ["CP_FREESTREAM", "MACH", "VTOT"]   # what the VTK surface export writes

# The groups the polar tables are written per: each group's name to ONE alias
# of the reference, or to "all" where no boundary or alias has that name.
[groups]
AIRFRAME = "airframe"
WING = "lifting"

# Which files each point exports; simulation and loads cannot be switched off.
[exports]
simulation = true
loads = true
tecplot = true
vtk = true
csv = false
force_distributions = false       # the per-panel forces
sections = true
sectional_loads = true
probes = true                     # steady rows
plots = true                      # the unsteady run types
plot_residuals = true             # steady rows: the solver's own plots
plot_loads = true
plot_sections_cp = true           # where [[sections.distributions]] declares any
log = true

# Surface sections cut before the solve, one distribution per entry and plane.
[sections]
count = 50                        # sections of every distribution that states none
plot_direction = 1                # 1 or 2
include_symmetry = false

[[sections.distributions]]
families = "lifting"              # an alias, a family name, or a list of them
frame = "MRP"                     # MRP, a frame of the reference, or a rotor's
planes = ["XZ"]                   # XY, XZ or YZ, one distribution each
count = 40                        # this entry's own count
plot_direction = 1
integrate = true                  # append the strip integrals of the sectional loads

# One flow-field plane each point of a steady row cuts after its solve. A
# rectangle is shown; a circle states shape = "circle", radii_m = [r1, r2] and
# points = [ipts, jpts] in place of corners_m and refinement_layers.
[volume_section]
shape = "rectangle"
frame = "MRP"
plane = "XZ"
offset_m = 0.0                    # along the plane's normal, from the frame's origin
corners_m = [-1.0, -1.0, 1.0, 1.0]   # x1, y1, x2, y2, two diagonal corners in the plane
refinement_layers = 1
format = "vtk"                    # vtk or tecplot

# The unsteady force plots: which parameters, over which groups of families.
[plots]
parameters = ["CL", "CD", "FX", "FZ", "MY"]

[[plots.groups]]
name = "WING"
frame = "MRP"
families = "lifting"

# Fluid probes, one entry per frame sampled: lines, rectangles and circles of
# points, laid out in the entry's frame in the entry's scale ... An unsteady
# row samples the parameters listed; a steady row exports its fixed set of
# variables, the list only switching the entry on, and says so in a warning.
[[probes]]
frame = "MRP"
parameters = ["VX", "VY", "VZ", "CP_FREE"]
points = 11                       # points per line, both ends included
scale = "m"                       # m, or rotor_radius

[[probes.lines]]
start = [2.0, -1.0, 0.0]
end = [2.0, 1.0, 0.0]

[[probes.rectangles]]
origin = [3.0, -1.0, -0.5]        # three corners; the fourth follows from them
along_u = [3.0, 1.0, -0.5]
along_v = [3.0, -1.0, 0.5]
points_u = 5
points_v = 3

[[probes.circles]]
center = [3.0, 0.0, 0.0]
normal = [1.0, 0.0, 0.0]
radius = 0.5
points_radial = 3                 # from the centre to the rim, both included
points_azimuth = 8

# ... or a points file of inputs/profiles/, named without a folder, in place
# of drawing them.
[[probes]]
parameters = ["VX", "VY", "VZ"]
points_file = "wake_survey.csv"

# The phase-locked reduction of an unsteady rotor row: generated when the row
# turns at least min_revolutions, averaged over the last revolutions.
[phase_locked]
min_revolutions = 4.0
last_revolutions_avg = 2.0

# A coefficient the post stage derives into the unsteady polar, about ONE
# alias: this one is the column CX_airframe.
[equations.CX]
expression = "FX / (0.5 * RHO * VINF**2 * SREF)"
meshes_alias = "airframe"
frame = "MRP"

# What your own symbols mean, listed in pproc/VARIABLES.md beside the package's.
[glossary]
CX = "-. The axial force coefficient of the airframe, in the MRP frame"

# A plot column of the unsteady polar renamed for a downstream tool.
[names]
CL_WING = "CL_W"

# Which products are written after the run.
[products]
polars = true
sections = true
plots = true
custom_polar_format = false
superfile_format = "csv"
"""

_REFERENCE_EXAMPLE = """\
# A reference artifact: what a row's REF column names by id; the id begins
# with r, so this file is r001. The lengths the coefficients are divided by,
# the moment point, the frames, your names for groups of boundaries, and one
# block per rotor, actuator disc and named point. Lengths are in metres, in
# the geometry's own frame.

area_m2 = 8.0                     # S_ref, m^2
chord_m = 1.0                     # c_ref, m
span_m = 8.0                      # b_ref, m
rotor_diameter_m = 1.2            # D, m: what an ADVANCE_RATIO and C_T divide by

[moment_point]                    # the moment reference point
x_m = 0.25
y_m = 0.0
z_m = 0.0

[body_axes]                       # the mesh axis each body rate turns about
roll = "X"
pitch = "Y"
yaw = "Z"

# Your own names for groups of boundaries, read wherever a boundary is cited:
# a pproc group, a families entry, a row's rotation. A member may be another
# alias, and a member the opened mesh does not carry is left out.
[aliases]
airframe = ["Wing", "Body", "Base"]
lifting = ["Wing"]

# The recorded rotor; its position is the one field a builder reads.
[rotor]
radius_m = 0.6                    # optional; half of rotor_diameter_m when stated
hub_radius_m = 0.1
n_blades = 3                      # the blade count of the mesh a row opens
pitch_deg = 0.0                   # recorded
toe_deg = 0.0                     # recorded

[rotor.position]
x_m = -0.5
y_m = 0.0
z_m = 0.0

# Custom coordinate systems, in the order written: origin in metres, two axis
# directions, the third their right-handed cross product. A row's AXIS and a
# pproc entry's frame cite them by name.
[[frames]]
name = "DISC_HUB"
origin = [0.4, 3.0, 0.0]
x_axis = [1.0, 0.0, 0.0]
y_axis = [0.0, 1.0, 0.0]

# One block per rotor: a top-level table with kind = "rotor". Its name is the
# word a row moves, and an alias over everything the rotor owns.
[PROP]
kind = "rotor"
alias = "PROP"                    # optional; equal to the block's name
axis = "X"                        # X, Y or Z, or the shaft direction [x, y, z]
diameter_m = 1.2
x_m = -0.5
y_m = 0.0
z_m = 0.0
rpm_sign = 1                      # +1 is the right-hand rule about axis
families_general = ["Spinner"]    # what turns with the rotor and is not a blade
families_blades = ["Blade1", "Blade2", "Blade3"]   # one per blade, in order

[PROP.blade1]                     # where blade one is, and what its azimuth is measured from
azimuth_deg = 0.0
zero = "Y"                        # an axis letter, with at most one sign

# One block per actuator disc: a top-level table with kind = "actuator". A
# row's ACTUATOR names it; a disc no row names emits nothing.
[DISC]
kind = "actuator"
frame = "DISC_HUB"                # a frame of [[frames]], MRP, or a rotor's frame
axis = "X"                        # the frame's axis the disc turns about
offset_m = 0.0                    # along that axis, from the frame's origin
tip_radius_m = 0.5
hub_radius_m = 0.1
rpm_sign = 1
blades = 3                        # required by a row stating PROFILE
swirl = 0.5                       # the fraction of the swirl kept, 0 to 1
profile_units = "NEWTONS"         # @PROFILE_UNITS@

# A named point: a top-level table with any other kind (rotor or airframe).
# It is read and kept; a row that names a point finds it in
# inputs/reference_points.toml.
[ARP]
kind = "airframe"
x_m = 0.25
y_m = 0.0
z_m = 0.0
"""

_REFERENCE_POINTS_EXAMPLE = """\
# The named reference points of this workspace, one table per name: ARP is the
# airframe point, and a rotor point is ERP with one propulsor or ERP1 to ERPn
# with more. A row's ROTOR_ORIGIN may name a rotor point instead of stating
# coordinates. The coordinates are metres in the geometry's own frame.

[ARP]
x_m = 0.25
y_m = 0.0
z_m = 0.0

[ERP1]
kind = "rotor"                    # rotor or airframe; unstated, the name decides
x_m = -0.5
y_m = 0.0
z_m = 0.0
"""

_INVENTORY_EXAMPLE = """\
# The boundary inventory of aircraft.fsm, as `pyfs-matrix inventory` writes it
# from the file's own mesh block: the solver's order, the name at position i
# being boundary i. A run whose sidecar disagrees with the file is refused
# before the solver starts; rewrite it from the file with
# `pyfs-matrix inventory inputs/geometries/aircraft/aircraft.fsm --overwrite`.
file = "aircraft.fsm"
boundaries = [
    "Wing",
    "Body",
    "Base",
    "Spinner",
    "Blade1",
    "Blade2",
    "Blade3",
]
"""

_RAW_MESH_SIDECAR_EXAMPLE = """\
# The sidecar of a raw mesh, wing_raw.obj. An OBJ's boundaries are its groups
# that hold a face, in the order of the file: when no sidecar stands beside it,
# the plan writes this list from them, and the tables below go beneath it. An
# STL names no group, so its list is written by hand. A mesh file carries no
# length unit, so the [import] table is always written by hand.
file = "wing_raw.obj"
boundaries = ["naca"]             # the file's surfaces, in the file's order

[import]
units = "MILLIMETER"              # the unit the mesh file is written in; never assumed

# The operations applied right after the import, in the order written, each
# naming the surface it acts on by the file's name or an earlier rename's.
# A rename is shown; the others are
#   op = "scale",     factors = [fx, fy, fz]        (each above zero)
#   op = "translate", vector = [x, y, z]            (in the [import] unit)
#   op = "rotate",    axis = "Z", angle_deg = 90.0
#   op = "mirror",    surface = "<name>", plane = "XZ"
# A scale, a translation and a rotation take surface = "all" by default. A
# trailing-edge points file names edges of the file as written, so a mesh
# whose edges come from one takes no operation but a rename.
[[import.operations]]
op = "rename"
surface = "naca"
to = "Wing"

# The trailing edges, marked from a points file beside this sidecar (the file
# below). The other route is the solver's detection, in place of these three
# keys: detect = "auto", or detect = { surfaces = ["Wing"], sweep_angle = 60.0 }.
[trailing_edges]
file = "wing_raw.te.txt"
type = "STANDARD"                 # @EDGE_TYPES@
tolerance = 0.0001                # m: how close an edge's mid-point is to a point of the file

[wake_termination]                # only when written
detect = "auto"                   # or { surfaces = ["Wing"] }

[base_regions]                    # only when written
detect = "auto"
"""

_TRAILING_EDGE_POINTS_EXAMPLE = """\
MILLIMETER
1000.0,0.0,0.0
1000.0,2000.0,0.0
1000.0,4000.0,0.0
"""

_PROVENANCE_EXAMPLE = """\
# Where aircraft.fsm came from. The package reads no key of this file: it
# keeps the record beside its geometry, leaves it out of what a GEOMETRY cell
# can name, and moves it with the geometry. Write what a reader needs to trust
# or rebuild the mesh; these keys are a suggestion.
source = "exported from the CAD model, revision C"
prepared_with = "FlightStream 26.124"
prepared_on = "2026-01-15"
units = "METER"
sha256 = "the SHA-256 of aircraft.fsm, as `certutil -hashfile` or `sha256sum` prints it"
sidecar = "aircraft.boundaries.toml"
"""

_ACTUATOR_PROFILE_EXAMPLE = """\
0.2,0.0
0.3,84.2
0.4,110.3
0.5,123.3
0.6,127.3
0.7,123.3
0.8,110.3
0.9,84.2
1.0,0.0
"""

_PROBE_SURVEY_EXAMPLE = """\
3
2.0,-1.0,0.0,1
2.0,0.0,0.0,1
2.0,1.0,0.0,1
"""

_FREESTREAM_EXAMPLE = """\
3 3
-2.0 -5.0 -1.0 50.0 0.0 0.0
-2.0 -5.0 0.0 50.0 0.0 0.0
-2.0 -5.0 1.0 50.0 0.0 0.0
-2.0 0.0 -1.0 50.0 0.0 1.5
-2.0 0.0 0.0 50.0 0.0 1.5
-2.0 0.0 1.0 50.0 0.0 1.5
-2.0 5.0 -1.0 50.0 0.0 0.0
-2.0 5.0 0.0 50.0 0.0 0.0
-2.0 5.0 1.0 50.0 0.0 0.0
"""

_HPC_EXAMPLE = """\
# The profile of the cluster this workspace may be opened on. No row cites it:
# a run on Linux with one profile here submits each point to the scheduler
# instead of running it. One profile per workspace; several are refused.

application_id = "flightstream"   # the scheduler's own name for the application; required

# What {walltime} carries, @WALLTIME_ARITHMETIC@: wall is the row's WALLTIME as
# written (4h), seconds the whole clock in seconds (14400).
walltime_arithmetic = "wall"

# The descriptor file written in each point's folder, and its fields: the keys
# this scheduler expects, each a text in which {name} is replaced by the
# point's value of that name: sim, point, fs_build, fs_build_alias, ncpus,
# walltime, walltime_s, walltime_written, application_id, script_path or
# work_dir. A name the point cannot supply is refused, never written empty.
[descriptor]
format = "yaml"                   # @HPC_FORMATS@
name = "submit.yaml"              # a plain file name

[descriptor.fields]
ApplicationId = "{application_id}"
job_name = "FTS{sim}"
master_file = "{script_path}"
workdir = "{work_dir}"
ncpus = "{ncpus}"
walltime = "{walltime}"
version = "{fs_build_alias}"

# The submission, argument by argument, never one string through a shell;
# {descriptor_path} is the descriptor just written.
[submit]
command = ["esub", "{descriptor_path}"]

# Values the profile keeps beside its fields. A descriptor carries only what
# [descriptor.fields] writes.
[defaults]
walltime = 28800

# What this scheduler calls each build a row names, keyed by the canonical
# build: several builds may share one scheduler name. {fs_build_alias} writes it.
[builds]
"26.124" = "26.1"

# The solver's log. A machine that aborts at the script's EXPORT_LOG states
# export_log = false and names the log it writes itself, as a pattern relative
# to the point's folder; collect copies it to the standard log name.
[log]
export_log = true
native_log = "FTS{sim}.l*"
"""

_EXECUTABLES_EXAMPLE = """\
# The build registry: what each build id of a row's FS_BUILD cell means on
# this workspace, one entry per build. A path may be a placeholder in a
# workspace kept in version control, with this machine's real path in
# executables.local.toml beside this file.

# A bare path declares no version: the rows on this build are emitted under
# the campaign's default version.
"26.120" = "C:/path/to/FlightStream_26120/FlightStream.exe"

# A table declares the version the build's scripts are emitted under, which
# lets one matrix send rows to several builds. The version is a string.
"26.124" = { path = "C:/path/to/FlightStream_26124/FlightStream.exe", version = "26.124" }
"""

_LOCAL_EXECUTABLES_EXAMPLE = """\
# This machine's paths for the builds executables.toml declares, read over it.
# Keep this file out of version control. A bare path keeps the version the
# registry declares; a table replaces the entry. A build the registry does not
# declare is refused.
"26.124" = "C:/path/to/this/machine/FlightStream.exe"
"""


def _filled(text: str) -> str:
    """Fill the value lists an example's comments name, from the code that reads them."""
    values = {
        "@RAW_PHASES@": _in_words(RAW_PHASES),
        "@FLAG_PHASES@": _in_words(FLAG_PHASES),
        "@PROFILE_UNITS@": _in_words(
            get_args(ActuatorBlock.model_fields["profile_units"].annotation)
        ),
        "@EDGE_TYPES@": _in_words(edge_types()),
        "@WALLTIME_ARITHMETIC@": _in_words(sorted(WALLTIME_ARITHMETIC)),
        "@HPC_FORMATS@": _in_words(HPC_FORMATS),
    }
    for token, value in values.items():
        text = text.replace(token, value)
    return text


#: The reason a key of a table is left out of every example because the
#: example shows the table's other form, and the comment beside it shows this.
_IN_THE_COMMENT = "the other form, shown in the comment above its table"

#: The setup's solver settings the example leaves at their defaults.
_SETTINGS_LEFT_OUT: tuple[str, ...] = (
    "forced_iterations",
    "max_threads",
    "timeout_s",
    "walltime_margin_s",
    "solver_model",
    "convergence_iterations",
    "minimum_cp",
    "mesh_induced_wake_velocity",
    "unsteady_pressure_and_kutta",
    "wake_on_wake_induction",
    "additional_wake_relaxation",
    "reynolds_averaged_drag",
    "laminar_separation",
    "kutta_joukowski_lift",
    "aeroelastic_rbf_type",
    "print_rotor_induced_velocities",
    "adaptive_field_grid_refinement",
    "rotor_induced_velocity_blending",
    "wake_numerical_relaxation",
    "wake_relaxation",
    "wake_decay_constant_per_m",
    "wake_streamwise_agglomeration",
    "jet_wake_decay_normalized_length",
    "jet_wake_filaments_grid_induction",
    "adverse_gradient_boundary_layer",
    "vortex_ring_normalization",
    "wake_termination_revolutions",
    "wake_termination_steps",
    "symmetry_loads",
    "significant_digits",
    "reference_velocity_m_per_s",
    "vorticity_drag_families",
    "axial_separation_families",
    "load_solver_initialization",
    "analysis_families",
    "load_units",
    "inviscid_loads",
    "vorticity_lift_model",
    "unsteady_viscous_coupling_iteration",
)


def _page(name: str, title: str) -> tuple[str, str]:
    """Return a documentation page the template links: ``docs/<name>.md`` and its title."""
    return (name, title)


def _template_sections() -> tuple[TemplateSection, ...]:
    """Return the sections of the input template, in the page's order.

    One per kind of input file a user writes. The five artifacts the input
    glossary covers are headed as it heads them, so a reader moving between
    the two pages meets one name for each.
    """
    return (
        TemplateSection(
            heading=ARTIFACT_HEADINGS["matrix"],
            intro=(
                "What to run: one row per simulation, each naming its flight condition, "
                "its sweep, its geometry and, by id, the three artifacts below. The "
                "matrix lives in the workspace ROOT, beside `inputs/`, under a name "
                "of your own ending in `.fs`; `pyfs-matrix plan <file> --workspace .` "
                "checks it without running anything, and `pyfs-matrix run` runs it."
            ),
            examples=(TemplateExample("campaign.fs", "text", _matrix_example()),),
            after=_matrix_after(),
            left_out=MappingProxyType(
                {
                    "The `FLIGHT_CONDITION` cell": MappingProxyType(
                        {"a closed vocabulary, on the flight-conditions page": ()}
                    ),
                    "The row keys, by run type": MappingProxyType(
                        {"the vocabulary of every run type, with the run types that read each": ()}
                    ),
                }
            ),
            pages=(
                _page("workspace-and-workflows", "The workspace and the workflow"),
                _page("flight-conditions", "Flight conditions"),
            ),
        ),
        TemplateSection(
            heading=ARTIFACT_HEADINGS["setup"],
            intro=(
                "The solver settings of a condition, shared by every row whose `SET` "
                "names it. One file per setup in `inputs/setups/`, named by its id."
            ),
            examples=(TemplateExample("inputs/setups/s001.toml", "toml", _filled(_SETUP_EXAMPLE)),),
            after=(
                "A key the package keeps in the file and sends nowhere is warned "
                "about, naming the key and why, every time the setup is read; "
                '`recorded_only = ["my_setting"]` declares one of your own that way.'
            ),
            left_out=MappingProxyType(
                {
                    "Solver settings": MappingProxyType(
                        {
                            "optional; unstated, each keeps the default INPUTS.md gives": (
                                _SETTINGS_LEFT_OUT
                            ),
                            "the direct form of the stabilization pair the example states": (
                                "solver_stabilization",
                            ),
                        }
                    ),
                    "The solver's own names, read as aliases": MappingProxyType(
                        {"the solver's own spellings of the settings; either is read": ()}
                    ),
                    "Recorded, and emitting nothing": MappingProxyType(
                        {"kept in the file and sent nowhere, each warned about": ()}
                    ),
                    "Tables and reserved keys": MappingProxyType(
                        {
                            "names keys of your own to keep and send nowhere, each warned about": (
                                "recorded_only",
                            ),
                        }
                    ),
                }
            ),
            pages=(
                _page("settings-codebook", "The settings codebook"),
                _page("flight-conditions", "Flight conditions"),
            ),
        ),
        TemplateSection(
            heading=ARTIFACT_HEADINGS["pproc"],
            intro=(
                "What each point defines before the solve, exports after it, and "
                "which products the campaign writes, shared by every row whose "
                "`PPROC` names it. One file per artifact in `inputs/pproc/`, beside "
                "the three generated guides."
            ),
            examples=(TemplateExample("inputs/pproc/p001.toml", "toml", _PPROC_EXAMPLE),),
            after=(
                "Some tables belong to one kind of run. The unsteady force plots, the "
                "phase-locked table and the equations serve the unsteady run types, "
                "and a steady row passes them over. The other way is a REFUSAL, not an "
                "omission: an unsteady row naming a pproc with a `[volume_section]`, or "
                "with `plot_sections_cp = true`, is refused at plan, so this example "
                "plans on a steady row; the residual and load plots are saved on both. "
                "Every table is read and checked when the file is, so a mistake in one "
                "is refused on any row."
            ),
            left_out=MappingProxyType(
                {
                    "The tables and top-level keys": MappingProxyType(
                        {
                            "refused on a build that cannot run it; INPUTS.md names the builds": (
                                "time_averaging",
                            ),
                        }
                    ),
                    "`[time_averaging]`": MappingProxyType(
                        {
                            "the table is left out, for the reason above": (
                                "last_revs",
                                "last_iters",
                            ),
                        }
                    ),
                    "`[volume_section]`": MappingProxyType(
                        {"a circle's keys, " + _IN_THE_COMMENT: ("radii_m", "points")}
                    ),
                }
            ),
            pages=(
                _page("post-processing-definitions", "The post-processing definitions"),
                _page("workspace-and-workflows", "The workspace and the workflow"),
            ),
        ),
        TemplateSection(
            heading=ARTIFACT_HEADINGS["reference"],
            intro=(
                "What a configuration IS, shared by every row whose `REF` names it: "
                "the reference lengths, the moment point, the frames, your aliases, "
                "and one block per rotor, actuator disc and named point. One file "
                "per reference in `inputs/references/`."
            ),
            examples=(
                TemplateExample("inputs/references/r001.toml", "toml", _filled(_REFERENCE_EXAMPLE)),
            ),
            after=(
                "A block is told apart by its `kind`, so its NAME is yours: the word "
                "a row moves or names. A name may be no other block's, alias's or "
                "frame's, and a rotor's name may not carry `_SMRP` or `_RMRP`, the "
                "frames the package builds for it."
            ),
            left_out=MappingProxyType(
                {
                    table: MappingProxyType(
                        {"the kind a named point states, which says nothing of this one": ("kind",)}
                    )
                    for table in ("`[moment_point]`", "`[rotor.position]`")
                }
            ),
            pages=(
                _page("workspace-and-workflows", "The workspace and the workflow"),
                _page("mesh-inputs", "Mesh inputs"),
            ),
        ),
        TemplateSection(
            heading="The named reference points, `inputs/reference_points.toml`",
            intro=(
                "Optional, one per workspace: the points a row may name instead of "
                "writing coordinates, written once for the whole campaign."
            ),
            examples=(
                TemplateExample(
                    f"inputs/{REFERENCE_POINTS_FILE}", "toml", _REFERENCE_POINTS_EXAMPLE
                ),
            ),
            after=(
                "A name outside the convention is refused, and a rotor motion may "
                "turn only about a rotor point. Every key a point takes is in the "
                f"example; {_GLOSSARY_LINK} lists the keys of the files a row cites."
            ),
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
        TemplateSection(
            heading=ARTIFACT_HEADINGS["geometry"],
            intro=(
                "The file beside a geometry that names its boundaries, "
                "`<stem>.boundaries.toml`. A geometry sits in `inputs/geometries/` "
                "directly, or in a folder named by its stem with everything that "
                "belongs to it, which is the layout the examples use; a row's "
                "`GEOMETRY` names the file the same way in both. A saved simulation "
                "(`.fsm`) gets its sidecar from `pyfs-matrix inventory`. An OBJ with no "
                "sidecar gets one from the plan, its `boundaries` read from the OBJ's "
                "groups, and an STL's is written by hand; beside a raw mesh, you add how "
                "it is imported and where its trailing edges are."
            ),
            examples=(
                TemplateExample(
                    "inputs/geometries/aircraft/aircraft.boundaries.toml",
                    "toml",
                    _INVENTORY_EXAMPLE,
                    note="Beside a saved simulation, `aircraft.fsm`:",
                ),
                TemplateExample(
                    "inputs/geometries/wing_raw/wing_raw.boundaries.toml",
                    "toml",
                    _filled(_RAW_MESH_SIDECAR_EXAMPLE),
                    note="Beside a raw mesh, `wing_raw.obj`:",
                ),
            ),
            left_out=MappingProxyType(
                {
                    "`[[import.operations]]`": MappingProxyType(
                        {
                            "the keys of the other operations, shown in the comment": (
                                "factors",
                                "vector",
                                "axis",
                                "angle_deg",
                                "plane",
                            ),
                        }
                    ),
                    "`[trailing_edges]`": MappingProxyType({_IN_THE_COMMENT: ("detect",)}),
                    "`detect = { ... }` of `[trailing_edges]`": MappingProxyType(
                        {_IN_THE_COMMENT: ("surfaces", "sweep_angle")}
                    ),
                }
            ),
            pages=(
                _page("mesh-inputs", "Mesh inputs"),
                _page("workspace-and-workflows", "The workspace and the workflow"),
            ),
        ),
        TemplateSection(
            heading="The trailing-edge points file, beside a raw mesh's sidecar",
            intro=(
                "The mid-point of every trailing-edge edge of a raw mesh, named by "
                "the `file` key of the sidecar's `[trailing_edges]` table and kept "
                "beside the sidecar. It holds no comment: the first line names the "
                "length unit of the points, one of "
                f"{_in_words(_scaled_units())}, and every later line is one point, "
                "`x,y,z`, three numbers separated by commas. The unit is what lets "
                "the run convert the points to the simulation's metres; each point "
                "is matched to an edge of the mesh within the sidecar's `tolerance`."
            ),
            examples=(
                TemplateExample(
                    "inputs/geometries/wing_raw/wing_raw.te.txt",
                    "text",
                    _TRAILING_EDGE_POINTS_EXAMPLE,
                ),
            ),
            after=(
                f"It has no keys of its own; the sidecar's are in {_GLOSSARY_LINK}. "
                "`pyflightstream.workspace.wake_edges.write_trailing_edge_points` "
                "writes one from a list of points."
            ),
            pages=(_page("mesh-inputs", "Mesh inputs"),),
        ),
        TemplateSection(
            heading="The provenance record, `<stem>.provenance.toml` beside a geometry",
            intro=(
                "Optional: where a geometry came from, kept beside it as TOML. The "
                "package reads no key of it, so the keys are yours; it keeps the "
                "record out of what a `GEOMETRY` cell can name and moves it with its "
                "geometry (`pyfs-workspace migrate-geometries`)."
            ),
            examples=(
                TemplateExample(
                    "inputs/geometries/aircraft/aircraft.provenance.toml",
                    "toml",
                    _PROVENANCE_EXAMPLE,
                ),
            ),
            after=f"No key of it is read, so none is in {_GLOSSARY_LINK}.",
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
        TemplateSection(
            heading="The actuator radial thrust profile, `inputs/profiles/<stem>.<ext>`",
            intro=(
                "The load of an actuator disc along its radius, for a row that names "
                "a disc and states `PROFILE: <stem>`, the file's name without its "
                "extension. One row per radial station, `r,F`: the station as a "
                "fraction of the tip radius, and the sectional thrust per unit span of "
                "ONE blade, in the force unit the disc block's `profile_units` names. "
                "The numbers pass to the solver as written. No header, no count "
                "and no comment: the solver reads every line as a point, so the file "
                "holds the rows and nothing else, at least two of them. The disc's "
                "`blades` says how many blades the distribution is per."
            ),
            examples=(
                TemplateExample(
                    "inputs/profiles/prop_thrust.txt", "text", _ACTUATOR_PROFILE_EXAMPLE
                ),
            ),
            after=(
                "The file stays as your editor saved it: the run writes the copy the "
                "solver reads, with no final newline and no blank line, where the "
                f"point runs. The disc's keys are in {_GLOSSARY_LINK}, under the "
                "reference's actuator block, and the row's under the row keys."
            ),
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
        TemplateSection(
            heading="The probe survey, `inputs/profiles/<name>`",
            intro=(
                "Points to sample the flow at, for a pproc `[[probes]]` entry that "
                'states `points_file = "<name>"`, the file\'s name with its '
                "extension, instead of drawing lines and planes. The first line is "
                "the count of points; every later line is one point, `X,Y,Z,TYPE`, "
                "TYPE 0 for a point on the surface and 1 for one in the volume. No "
                "comment and no header."
            ),
            examples=(
                TemplateExample("inputs/profiles/wake_survey.csv", "csv", _PROBE_SURVEY_EXAMPLE),
            ),
            after=(
                "On a steady row the script imports the file where it lives, its "
                "coordinates in metres in the reference frame; on an unsteady row "
                "the plan reads it and places each point in the entry's `frame` and "
                f"`scale`. The entry's keys are in {_GLOSSARY_LINK}, under "
                "`[[probes]]`."
            ),
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
        TemplateSection(
            heading=f"The custom free stream, `inputs/{FREESTREAM_DIR}/<stem>.txt`",
            intro=(
                "A velocity field over the YZ plane of the global frame, for a row "
                "stating `FREESTREAM: <stem>`, which the run writes in place of the "
                "constant free stream. The extension is the form: "
                + _in_words(
                    [f"`{suffix}` is {form}" for suffix, form in FREESTREAM_FORMS.items()],
                    "and",
                )
                + ". The STRUCTURED form is shown: a first line `Npts Mpts`, two "
                "positive integers, then Npts x Mpts rows `x y z vx vy vz`, the first "
                "index outer and the second inner, in metres and metres per second. "
                "Every row states the same x, and the rows state at least two "
                "distinct y and two distinct z. The UNSTRUCTURED form is the rows "
                "alone, one per vertex, with no first line. No comment in either."
            ),
            examples=(
                TemplateExample(f"inputs/{FREESTREAM_DIR}/gust.txt", "text", _FREESTREAM_EXAMPLE),
            ),
            after=(
                "The field sets the flow's direction, so a row flying through one "
                "states zero angles of attack and sideslip, and no body rate: write an "
                "incidence into vy and vz. The body is then loaded as at that incidence, "
                "and the loads export prints CL and CDi in the axes of the zero angle the "
                "row states, so read the body forces Cx, Cy and Cz, or turn CL and CDi by "
                "the field's incidence. Make the grid reach past the body: beyond it the "
                "solver does not extend the field, and the plan warns when the body "
                "reaches outside it. Both forms were run on FlightStream 26.124 "
                f"(RPT-071, RPT-077). The row key is in {_GLOSSARY_LINK}, under the row "
                "keys."
            ),
            pages=(_page("gui-to-pyfs", "From the GUI to pyfs"),),
        ),
        TemplateSection(
            heading=f"The HPC profile, `inputs/{HPC_DIR}/<name>.toml`",
            intro=(
                "How the cluster this workspace may be opened on is asked to run a "
                "job: the descriptor file it reads, the command that submits it, and "
                "what it calls each build. Optional, and at most one per workspace."
            ),
            examples=(
                TemplateExample(f"inputs/{HPC_DIR}/h001.toml", "toml", _filled(_HPC_EXAMPLE)),
            ),
            after=(
                "A key the package does not read is refused, naming it, and so is "
                "`export_log` or `native_log` written under any table but `[log]`. "
                f"Every key a profile takes is in the example; {_GLOSSARY_LINK} lists "
                "the keys of the files a row cites."
            ),
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
        TemplateSection(
            heading=f"The build registry, `inputs/{EXECUTABLES_FILE}`",
            intro=(
                "What each build id a row's `FS_BUILD` names means: the solver's "
                "executable and, optionally, the version its scripts are emitted "
                "under. `pyfs-workspace init` writes a commented one; replace it with "
                "entries like these."
            ),
            examples=(TemplateExample(f"inputs/{EXECUTABLES_FILE}", "toml", _EXECUTABLES_EXAMPLE),),
            after=(
                "An entry is a path, or a table of `path` and `version` and nothing "
                "else; any other key is refused, naming it. Every key an entry takes "
                f"is in the example; {_GLOSSARY_LINK} lists the keys of the files a "
                "row cites."
            ),
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
        TemplateSection(
            heading=f"This machine's paths, `inputs/{LOCAL_EXECUTABLES_FILE}`",
            intro=(
                "Optional: the real paths of the builds on this machine, for a "
                "workspace whose registry keeps placeholders because it is in version "
                "control. Read over the registry; keep it out of version control."
            ),
            examples=(
                TemplateExample(
                    f"inputs/{LOCAL_EXECUTABLES_FILE}", "toml", _LOCAL_EXECUTABLES_EXAMPLE
                ),
            ),
            after=(
                f"Its entries take the registry's shapes; {_GLOSSARY_LINK} lists the "
                "keys of the files a row cites."
            ),
            pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
        ),
    )


_TEMPLATE_INTRO = (
    "One section per kind of input file you write, each with what the file is "
    "for, where it lives, and a complete example to copy. Copy an example to the "
    "path its block's title names, relative to the workspace root, and edit the "
    "values: every example is a file the package reads as it stands, and the "
    "test suite writes each one where its title says and reads it with the "
    "function the run reads it with. The examples cite each other, so the matrix "
    "runs against the setup, the pproc, the reference, the geometry, the profile "
    "and the free stream shown here. What every key of the matrix row, the "
    f"setup, the pproc, the reference and the geometry sidecar sets, with its "
    f"unit and its values, is in the input glossary, {_GLOSSARY_LINK}; a key an "
    "example leaves out is named under it, with the reason."
)


def _left_out_lines(section: TemplateSection) -> list[str]:
    if not section.left_out:
        return []
    lines = [
        "**Left out of the example.** Each is a key this file may state; what it sets, "
        f"its unit and its values are in {_GLOSSARY_LINK}, under the table named.",
        "",
    ]
    for table, reasons in section.left_out.items():
        for reason, keys in reasons.items():
            named = "every key" if not keys else ", ".join(f"`{key}`" for key in keys)
            lines.append(f"- **{table}** ({reason}): {named}.")
    lines.append("")
    return lines


def input_template_markdown() -> str:
    """Return the input template, ``input_template.md``, as Markdown.

    One section per kind of input file a user writes, each with what the file
    is for, where it lives and a complete example: the run matrix, the setup,
    the pproc, the reference, the named points, the geometry sidecar and the
    trailing-edge points file beside it, the provenance record, the actuator
    profile and the probe survey of ``profiles/``, the custom free stream, the
    HPC profile and the build registry with its overlay. Each example is a
    file the package reads as it stands, and the keys an example leaves out are
    named with the reason. Generated on every call.

    Examples
    --------
    >>> text = input_template_markdown()
    >>> text.splitlines()[0]
    '# Input templates'
    >>> 'title="inputs/setups/s001.toml"' in text
    True
    """
    sections = _template_sections()
    lines = ["# Input templates", "", _GENERATED, "", _TEMPLATE_INTRO, "", "Sections:", ""]
    lines += [f"- {section.heading}" for section in sections]
    for section in sections:
        lines += ["", f"## {section.heading}", "", section.intro, ""]
        for example in section.examples:
            if example.note:
                lines += [example.note, ""]
            lines.append(f'```{example.language} title="{example.path}"')
            lines += [example.text.rstrip("\n"), "```", ""]
        if section.after:
            lines += [section.after, ""]
        lines += _left_out_lines(section)
        links = [_GLOSSARY_LINK] + [_page_link(name, title) for name, title in section.pages]
        lines += [f"Read more: {'; '.join(links)}."]
    lines.append("")
    return "\n".join(lines)


def write_input_template(folder: str | Path, *, changed: list[Path] | None = None) -> Path:
    """Write the input template, ``input_template.md``, into ``folder``; return its path.

    Rewritten only when its content would change, so the call is idempotent
    and leaves a versioned workspace clean.

    Parameters
    ----------
    folder : str or pathlib.Path
        Where to write it: the ``inputs`` folder of a workspace. Created if it
        is not there.
    changed : list, optional
        Receives the page when this call actually wrote it.

    Returns
    -------
    pathlib.Path
        The page, written or not.

    Examples
    --------
    >>> import tempfile
    >>> folder = tempfile.mkdtemp()
    >>> first: list = []
    >>> write_input_template(folder, changed=first).name
    'input_template.md'
    >>> again: list = []
    >>> _ = write_input_template(folder, changed=again)
    >>> len(first), len(again)
    (1, 0)
    """
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    page = target / INPUT_TEMPLATE_NAME
    if _write_if_different(page, input_template_markdown()) and changed is not None:
        changed.append(page)
    return page


def write_workspace_input_template(inputs_dir: str | Path) -> list[Path]:
    """Write ``input_template.md`` at the root of ``inputs_dir``; return it if it CHANGED.

    The input-guide writer this package registers with
    :func:`pyflightstream.workspace.register_input_guide` beside the glossary,
    which is how ``pyfs-workspace init``, ``pyfs-matrix plan`` and
    ``pyfs-matrix post`` reach it.
    """
    changed: list[Path] = []
    write_input_template(inputs_dir, changed=changed)
    return changed
