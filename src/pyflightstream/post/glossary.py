"""The input glossary, ``INPUTS.md``, and the parts every generated input guide shares.

The glossary states every key an INPUT artifact may state, the matrix row, the
setup, the pproc, the reference and the geometry sidecar, with what it sets,
its unit or values, the run types or builds that accept it and the solver
command it reaches (G08 of 0.27.0). It reads the registries the code uses: the
run types' key tables, the matrix columns, the flight-condition vocabulary, the
preset tables, the export kinds, the sidecar readers' keys and the fields of
every input model, and the meaning of a key is the code's too (a model field's
description, its ``Attributes`` entry or its ``#:`` comment, or the
:class:`~pyflightstream.cases.InputKey` its registry carries). A key added
without one is a row with no meaning, which the glossary's test refuses.

Beside it live the parts the generated pages share: the names of the pproc
guides, which the glossary's introduction names, the generated-page banner,
the idempotent write and the link to a documentation page. They are here,
below :mod:`pyflightstream.post.input_template` and
:mod:`pyflightstream.post.guides`, because both of those import this module
and this module imports neither.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.post.guides`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cache, lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import metadata as distribution_metadata
from pathlib import Path
from types import MappingProxyType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import (
    EXPORT_KIND_MEANINGS,
    EXPORT_KINDS,
    SOLVER_SETTING_COMMANDS,
    STEADY_ONLY_EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
    BaseRegionOperation,
    CustomFlag,
    InputKey,
    MeshImport,
    PortBoundary,
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
    command_accepted_on,
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.script.helpers import ROTATION_COMMANDS
from pyflightstream.versions import known_versions
from pyflightstream.workspace.flight_condition import PINNED_KEYS
from pyflightstream.workspace.inputs import ReferenceArtifact
from pyflightstream.workspace.matrix import (
    PRESET_ALIASES,
    PRESET_RECORDED_ONLY,
    PRESET_RESERVED_KEYS,
)
from pyflightstream.workspace.sidecars import (
    GEOMETRY_SIDECAR_KEYS,
    IMPORT_TABLE,
    RAW_MESH_CONDITION_KEYS,
    TRAILING_EDGE_DETECT_KEYS,
    TRAILING_EDGES_TABLE,
)

__all__ = [
    "ARTIFACT_HEADINGS",
    "DOCS_URL_LABEL",
    "GLOSSARY_COLUMNS",
    "INPUT_GLOSSARY_NAME",
    "PACKAGE_SET_FIELDS",
    "PPROC_GUIDE_NAMES",
    "REFERENCE_BLOCK_HEADINGS",
    "GlossaryRow",
    "GlossaryTable",
    "input_glossary_markdown",
    "input_glossary_tables",
    "write_input_glossary",
    "write_workspace_input_glossary",
]


# --- the parts the generated pages share -------------------------------------

#: The two guides written into the pproc input folder.
PPROC_GUIDE_NAMES: tuple[str, ...] = ("VARIABLES.md", "WRITING-EQUATIONS.md")

GENERATED_BANNER = "GENERATED FROM THE CODE by pyflightstream. Do not edit: it is rewritten."


def write_if_different(path: Path, text: str) -> bool:
    """Write ``text`` to ``path`` unless it already holds exactly that; say whether it wrote."""
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except (OSError, UnicodeDecodeError):
        pass  # unreadable is different
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


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
        ("PortBoundary", "profile_sha256"),
        ("PortBoundary", "boundary"),
        ("PortBoundary", "velocity"),
        ("PortBoundary", "profile"),
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
        ("BaseRegionOperation", "boundary"): "CREATE_NEW_BASE_REGION",
        ("BaseRegionOperation", "model"): "CREATE_NEW_BASE_REGION, SET_BASE_REGION_CP",
        ("BaseRegionOperation", "cp"): "CREATE_NEW_BASE_REGION, SET_BASE_REGION_CP",
        ("BaseRegionOperation", "mesh"): "REMESH_BASE_REGION",
        ("PortBoundary", "profile_variable"): "SET_INLET_CUSTOM_PROFILE",
        ("PortBoundary", "remesh"): "REMESH_INLET, REMESH_OUTLET",
        ("PprocSpec", "sections"): "NEW_SURFACE_SECTION_DISTRIBUTION",
        ("PprocSpec", "volume_section"): (
            "CREATE_NEW_RECTANGLE_VOLUME_SECTION, CREATE_NEW_CIRCLE_VOLUME_SECTION"
        ),
        ("PprocSpec", "plots"): "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        ("PprocSpec", "probes"): "UNSTEADY_SOLVER_NEW_FLUID_PLOT, NEW_PROBE_POINT",
        ("PprocSpec", "surface_probes"): "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
        ("SurfaceProbeSpec", "name"): "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
        ("SurfaceProbeSpec", "parameter"): "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
        ("SurfaceProbeSpec", "frame"): "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
        ("SurfaceProbeSpec", "point_m"): "NEW_UNSTEADY_SOLVER_SURFACE_PROBE",
        # G25 of 0.28.0: the window's steps are exported through the unsteady
        # solver actions and averaged by the package; SOLVER_TIME_AVERAGING is
        # never emitted.
        ("PprocSpec", "time_averaging"): "SET_NEW_UNSTEADY_SOLVER_ACTION",
        ("PprocSpec", "vtk_variables"): "SET_VTK_EXPORT_VARIABLES",
        # SS1 of 0.30.0: true adds the native Tecplot export the strength is read from.
        ("PprocSpec", "singularity_strength"): "EXPORT_SOLVER_ANALYSIS_TECPLOT",
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
        ("ActuatorBlock", "wake_type"): "SET_ACTUATOR_WAKE_TYPE",
        ("ActuatorBlock", "thrust_units"): "SET_PROP_ACTUATOR_THRUST",
        ("ActuatorOperation", "op"): (
            "SET_ACTUATOR_NAME, DELETE_ACTUATOR, ENABLE_ACTUATOR, DISABLE_ACTUATOR"
        ),
        ("ActuatorBlock", "profile_units"): "SET_PROP_ACTUATOR_PROFILE",
        ("MeshImport", "units"): "IMPORT",
        ("MeshImport", "cad"): "IMPORT_CAD, CONVERT_CAD_TO_MESH",
        ("CadImportOptions", "tessellation_density"): "IMPORT_CAD",
        ("CadImportOptions", "unreferenced_patches"): "IMPORT_CAD",
        ("CadImportOptions", "num_curvature"): "IMPORT_CAD",
        ("CadImportOptions", "body_index"): "CONVERT_CAD_TO_MESH",
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
    if model is PortBoundary and name == "remesh":
        commands = ("REMESH_OUTLET" if path.startswith("outlets.") else "REMESH_INLET",)
    if model is PortBoundary and name == "profile":
        if path.startswith("outlets."):
            commands = ()
            restriction = "refused: no documented outlet-profile command"
        else:
            restriction = "inlets only; native profile format and build acceptance remain explicit"
    if model is SolverSettings and name == "base_region_operations":
        restriction = "ordered actions; command availability is checked for each selected operation"
    if model is BaseRegionOperation:
        restriction = "selected action arguments only; see boundary-conditions guide"
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

    Returns
    -------
    str
        The Markdown page, ending with a newline.

    Examples
    --------
    >>> text = input_glossary_markdown()
    >>> text.splitlines()[0]
    '# Inputs'
    >>> "| `analysis_families` |" in text
    True
    """
    lines = ["# Inputs", "", GENERATED_BANNER, "", _PAGE_INTRO]
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

    Only the marked generated block is refreshed. Existing unmarked content
    and notes outside that block remain byte-for-byte intact. A legacy glossary
    under ``pproc`` is left in place and linked as preserved compatibility content.

    Parameters
    ----------
    folder : str or pathlib.Path
        Where to write it: the workspace's ``inputs`` root. Created if absent.
    changed : list, optional
        Receives the page when this call actually wrote it.

    Returns
    -------
    pathlib.Path
        The page, written or not.

    Raises
    ------
    InputArtifactError
        If the existing page holds the generated-block markers more than once,
        or in reversed order, so the block cannot be refreshed safely.

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
    begin = b"<!-- pyflightstream:input-glossary:begin -->"
    end = b"<!-- pyflightstream:input-glossary:end -->"
    generated = input_glossary_markdown()
    generated += "\nSetup reference: " + page_link("setup-standards", "Setup standards") + ".\n"
    if (target / "pproc" / INPUT_GLOSSARY_NAME).is_file():
        generated += (
            "\nCompatibility note: [pproc/INPUTS.md](pproc/INPUTS.md) is preserved "
            "unchanged as legacy content. This file is the generated input glossary.\n"
        )
    block = begin + b"\n" + generated.encode("utf-8") + end + b"\n"
    before = page.read_bytes() if page.is_file() else b""
    if begin in before or end in before:
        if before.count(begin) != 1 or before.count(end) != 1:
            raise InputArtifactError(
                f"{page}: ambiguous generated glossary markers; preserve and repair them"
            )
        first, last = before.index(begin), before.index(end)
        if last < first:
            raise InputArtifactError(
                f"{page}: reversed generated glossary markers; preserve and repair them"
            )
        after = before[:first] + block.rstrip(b"\n") + before[last + len(end) :]
    else:
        after = before + (b"\n\n" if before else b"") + block
    if before != after:
        page.write_bytes(after)
        if changed is not None:
            changed.append(page)
    return page


def write_workspace_input_glossary(inputs_dir: str | Path) -> list[Path]:
    """Write ``INPUTS.md`` into ``inputs_dir``; return it if it CHANGED.

    The input-guide writer this package registers with
    :func:`pyflightstream.workspace.register_input_guide` beside the pproc
    guides, which is how ``pyfs-workspace init``, ``pyfs-matrix plan`` and
    ``pyfs-matrix post`` reach it.

    Parameters
    ----------
    inputs_dir : str or pathlib.Path
        The workspace's ``inputs`` root; created if absent.

    Returns
    -------
    list of pathlib.Path
        The page when this call wrote it, otherwise an empty list.
    """
    changed: list[Path] = []
    write_input_glossary(Path(inputs_dir), changed=changed)
    return changed


#: The label of the installed distribution's ``Project-URL`` entry that names
#: the documentation site, as ``pyproject.toml`` declares it under
#: ``[project.urls]``.
DOCS_URL_LABEL = "Documentation"


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


def page_link(name: str, title: str) -> str:
    """Return a link to ``docs/<name>.md`` on the site, or its file where no site is known."""
    site = _documentation_site()
    return f"[{title}]({site}{name}/)" if site else f"{title} (`docs/{name}.md`)"
