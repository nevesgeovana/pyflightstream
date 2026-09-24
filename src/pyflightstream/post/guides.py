"""The generated input guides: ``VARIABLES.md``, ``WRITING-EQUATIONS.md`` and ``INPUTS.md``.

Three pages written INTO the pproc input folder of a workspace, where whoever is
writing a pproc artifact is already standing: every variable a product states
with its definition; how to write a custom equation, a glossary entry, the
phase-locked table and a group rename; and, since 0.27.0 (G08), every key an
INPUT artifact may state, the matrix row, the setup, the pproc, the reference
and the geometry sidecar, with what it sets, its unit or values, the run types
or builds that accept it and the solver command it reaches.

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
by the same three. Writing is IDEMPOTENT: a page whose content would not change
is not touched, so a run does not dirty a versioned workspace. Only the names
in :data:`PPROC_GUIDE_NAMES` and :data:`INPUT_GLOSSARY_NAME` are ever written;
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
from pathlib import Path
from types import MappingProxyType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pyflightstream._expressions import ALLOWED_FUNCTIONS
from pyflightstream._tokens import FX_INT, FZ_INT, INTEGRATED_SECTION_COLUMNS, MY_INT, STRIP_LENGTH
from pyflightstream.cases import (
    EXPORT_KIND_MEANINGS,
    EXPORT_KINDS,
    SOLVER_SETTING_COMMANDS,
    STEADY_ONLY_EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
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
    LOADS_SELECTION_KEYS,
    RATE_VARIABLES,
    ROW_KEY_MEANINGS,
    WORKFLOWS,
)
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.products import (
    PHASE_LOCKED_COLUMNS,
    ROTOR_COEFFICIENT_COLUMNS,
    UNSTEADY_AXIS_COLUMNS,
)
from pyflightstream.script.helpers import ROTATION_COMMANDS
from pyflightstream.versions import known_versions
from pyflightstream.workspace.flight_condition import PINNED_KEYS
from pyflightstream.workspace.inputs import (
    GEOMETRY_SIDECAR_KEYS,
    IMPORT_TABLE,
    RAW_MESH_CONDITION_KEYS,
    TRAILING_EDGE_DETECT_KEYS,
    TRAILING_EDGES_TABLE,
    ReferenceArtifact,
)
from pyflightstream.workspace.matrix import (
    PRESET_ALIASES,
    PRESET_RECORDED_ONLY,
    PRESET_RESERVED_KEYS,
)

__all__ = [
    "ARTIFACT_HEADINGS",
    "GLOSSARY_COLUMNS",
    "INPUT_GLOSSARY_NAME",
    "PACKAGE_SET_FIELDS",
    "PPROC_GUIDE_NAMES",
    "REFERENCE_BLOCK_HEADINGS",
    "VARIABLE_DEFINITIONS",
    "GlossaryRow",
    "GlossaryTable",
    "input_glossary_markdown",
    "input_glossary_tables",
    "write_input_glossary",
    "write_pproc_guides",
    "write_workspace_input_glossary",
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
    "arrives here with its meaning. A blank `Accepted by` means the code states no "
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
    """Return the registered builds on which one of ``commands`` is documented or verified.

    Empty when that is every registered build: the command's own evidence
    restricts nothing, so the row says nothing.
    """
    if not commands:
        return ""
    registry = CommandRegistry.load()
    versions = known_versions()
    accepting = []
    for version in versions:
        for name in commands:
            entry = registry.commands.get(name)
            record = entry.status_in(version) if entry is not None else None
            if record is not None and record.status in (Status.DOCUMENTED, Status.VERIFIED):
                accepting.append(version.canonical)
                break
    if len(accepting) == len(versions):
        return ""
    return "builds " + ", ".join(accepting) if accepting else "no registered build"


def _split_commands(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _joined(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


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
        meaning=_field_meaning(model, name, field),
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
                meaning=_markdown(entry.meaning),
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
                meaning=entry.meaning,
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
        rows.append(
            GlossaryRow(
                key=kind,
                meaning=EXPORT_KIND_MEANINGS.get(kind, ""),
                values=values,
                accepted=_joined(accepted, _builds((verb,))),
                commands=(verb,),
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
            "Beside a saved simulation, `pyfs-matrix inventory` writes it; beside a raw "
            "mesh, it is written by hand.",
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
