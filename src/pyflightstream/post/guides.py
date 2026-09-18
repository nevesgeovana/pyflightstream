"""The generated pproc guides (v0.23.0 item 11).

THIS MODULE IS IN `post` AND NOT IN `workspace`, and the move was made by a
guard rather than by taste. The first writing put it in `workspace.inputs` and
deferred its imports of `post` to call time; the convention test refused it
with the sentence that settles the whole question:

    Deferring an import to call time does not change its direction.

The guides document the pproc SPEC (`cases`) and the PRODUCTS (`post`), so they
belong in the layer that already depends on both. `post` imports `cases` and
`workspace`; neither imports `post`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

from pydantic import BaseModel

from pyflightstream.cases import EquationSpec, PhaseLockedSpec, PprocSpec
from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.products import ROTOR_COEFFICIENT_COLUMNS

#: The two guides item 11 writes into the pproc input folder.
PPROC_GUIDE_NAMES: tuple[str, ...] = ("VARIABLES.md", "WRITING-EQUATIONS.md")


def _pproc_table_spellings() -> list[str]:
    """How each `PprocSpec` field is spelled in a pproc file, derived not assumed.

    A page that advertises itself as generated from the code is TRUSTED, so a
    wrong spelling in it is worse than the same sentence written by hand. This
    listed every field as `[name]` until the 0.23.0 release round, which offered
    a reader `[blade_pattern]` for a `str`, `[base_regions]` for a `list[str]`,
    and `[probes]` for a field whose single-table form has been REFUSED by name
    since 0.16.0. The model declares `extra="forbid"`, so each of those is a
    refusal the guide walked the reader into.

    The mapping is the TOML one: a model-typed field is a table, a list of
    model-typed entries is an array of tables, a mapping is a table with your
    own keys under it, and anything else is a key rather than a table.
    """
    spellings: list[str] = []
    for name in sorted(PprocSpec.model_fields):
        annotation = PprocSpec.model_fields[name].annotation
        origin = get_origin(annotation)

        def is_model(candidate: object) -> bool:
            return isinstance(candidate, type) and issubclass(candidate, BaseModel)

        # `X | None` carries the model in its arguments, and its origin is the
        # union rather than nothing -- which is what made `phase_locked`, the
        # one optional table, come out as a key on the first pass.
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


def write_pproc_guides(
    folder: str | Path, *, glossary: Mapping[str, str] | None = None
) -> list[Path]:
    """Write the variable reference and the equation guide beside a pproc.

    v0.23.0 item 11, the owner's request of 2026-09-17: "dentro da pasta pproc
    de inputs, eu quero gerar um arquivo com todas as variáveis definições e um
    guia de como escrever equações customizadas, renomear, etc".

    GENERATED FROM THE CODE, which is the property that matters and the reason
    this is a function rather than two files in the repository. A page written
    by hand beside a schema goes stale the first time the schema moves, and
    nothing notices; this reads the models and the constants it documents, so a
    field added without a line here produces a guide that is missing it rather
    than a guide that is wrong about it.

    Parameters
    ----------
    folder : str or pathlib.Path
        The pproc input folder. Created if it is not there.
    glossary : mapping, optional
        The user's own symbol definitions, from the pproc's `[glossary]`
        table. They are listed BESIDE the package's own rather than merged
        into them, so a reader can tell which definitions are hers.

    Returns
    -------
    list of pathlib.Path
        The two files written, in :data:`PPROC_GUIDE_NAMES` order.
    """
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Variables",
        "",
        "GENERATED FROM THE CODE. Do not edit: a page written by hand beside a",
        "schema goes stale the first time the schema moves, and nothing notices.",
        "",
        "## Every product carries these",
        "",
        "A file that does not state its flight condition cannot say what it is a",
        "file of, which is why these are on every product rather than on the polar",
        "alone.",
        "",
    ]
    lines += [f"- `{name}`" for name in CONTEXT_COLUMNS]
    lines += [
        "",
        "## A rotor carries these, one set per rotor",
        "",
        "Each is suffixed with the rotor's alias, because these make physical sense",
        "for ONE rotor and not for several summed together: the diameters and the",
        "speeds that normalise them are different numbers.",
        "",
    ]
    lines += [f"- `{name}_<alias>`" for name in ROTOR_COEFFICIENT_COLUMNS]
    lines += [
        "",
        "## What a pproc may declare, and how each one is spelled",
        "",
    ]
    lines += [f"- {spelling}" for spelling in _pproc_table_spellings()]
    if glossary:
        lines += ["", "## Your own definitions, from `[glossary]`", ""]
        lines += [f"- `{name}`: {text}" for name, text in sorted(glossary.items())]
    lines.append("")
    variables = target / PPROC_GUIDE_NAMES[0]
    variables.write_text("\n".join(lines), encoding="utf-8")

    equation_fields = ", ".join(f"`{name}`" for name in EquationSpec.model_fields)
    gate_fields = ", ".join(f"`{name}`" for name in PhaseLockedSpec.model_fields)
    guide = [
        "# Writing equations",
        "",
        "GENERATED FROM THE CODE. Do not edit.",
        "",
        "## An equation points at an ALIAS, never at a mesh family",
        "",
        "That is not a restriction for its own sake. An alias is what gives the",
        "derived coefficient a name that says which body it is about, so every",
        "coefficient you derive carries `_<alias>`. A family list would give it",
        "nothing to be called.",
        "",
        f"Fields: {equation_fields}.",
        "",
        "```toml",
        "[equations.CTX]",
        'expression = "CT * 2"',
        'meshes_alias = "PUSHER"',
        'frame = "BODY"',
        "```",
        "",
        "`frame` matters because an axis matters: the same expression in the body",
        "and the wind axes is two different coefficients.",
        "",
        "## An equation may name another equation",
        "",
        "You write the equations in a TOML table, and a TOML table has no order",
        "you may rely on, so the package works out the order for you: every",
        "equation is evaluated after the ones its expression names.",
        "",
        "```toml",
        "[equations.CTX]",
        'expression = "CT * 2"',
        'meshes_alias = "PUSHER"',
        "",
        "[equations.CTX_WIND]",
        'expression = "CTX * 3"          # CTX is evaluated first',
        'meshes_alias = "PUSHER"',
        "```",
        "",
        "A symbol this table does not define is a variable the products already",
        "carry -- `CT` above is one -- so you never have to declare a base.",
        "",
        "A chain that loops is REFUSED WHEN THIS FILE IS READ, and the refusal",
        "names the equations in the loop, because a cycle has no order to",
        "evaluate it in. You do not have to go and ask: the check runs where the",
        "mistake is, when you load the pproc. If you want the order itself,",
        "`PprocSpec.equation_order()` returns it.",
        "",
        "## Renaming",
        "",
        "A group is named by the input that declares it, and the product file",
        "carries that name. If you rename a group, the products you already have",
        "are moved for you by `pyflightstream.workspace.rename_group_products`,",
        "which ARCHIVES each file before it moves it and never deletes anything.",
        "",
        "## The phase-locked gate",
        "",
        f"Fields: {gate_fields}. The reduction is generated when the matrix",
        "specifies AT LEAST `min_revolutions`. Not reaching it does not refuse the",
        "polar; it only means no phase-locked reduction.",
        "",
    ]
    equations = target / PPROC_GUIDE_NAMES[1]
    equations.write_text("\n".join(guide), encoding="utf-8")
    return [variables, equations]
