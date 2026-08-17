"""The one renderer of a chapter file's flow mappings, asserted rather than trusted.

Tier 1. Two incidents produced this module and this file guards both of
them, which is why the guards look redundant and are not.

``INC-20260811-1511-both``: escaping was a convention any call site could
reach for or skip, with nothing observing which, and one site wrote
silently corrupted YAML for four releases. That was closed by removing
the concept of a call site inside :mod:`pyflightstream.qa.compat`.

2026-08-17: ``pyfs-manual register`` began writing the same chapter files
from :mod:`pyflightstream.utils`, which sits BELOW ``qa`` and could not
import the helper, so it built the mapping by concatenation and the class
came straight back. Measured on the day, before the repair: a note
carrying a backslash or a quote character made the chapter file
unparsable, and a note carrying a newline was written silently
truncated.

So there are two rules, and the second is the one that was missing. The
escaper has exactly one caller. AND no module in the package builds a
flow mapping by hand, wherever it sits in the dependency order.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import pytest
import yaml

from pyflightstream import _yamlflow
from pyflightstream._yamlflow import RAW_KEYS, flow_mapping, flow_scalar

SRC = pathlib.Path(_yamlflow.__file__).resolve().parent

#: A YAML flow mapping being built by hand: a brace opening a
#: ``key: value`` pair inside a string literal.
#:
#: TWO OPENERS, and the second is not decoration. A plain literal writes
#: ``"{status: ...``; an f-string has to double the brace and writes
#: ``{{status: ...``, and the doubled form is preceded by whatever text
#: comes before it rather than by a quote. The first draft of this guard
#: anchored on the quote alone and therefore MISSED a third hand-built
#: site inside this very package while reporting the other two, which is
#: the failure mode a scanner-shaped guard has and the reason the
#: measurement below is recorded rather than assumed.
#:
#: The space after the colon is what separates a mapping from a format
#: spec: ``f"{value:.9e}"`` and ``f"{name:<{width}}"`` have no space and
#: are not this. Measured over the whole package when the guard was
#: written: eleven format specs matched without the space rule, none
#: with it, and the only remaining matches under ``src`` were this
#: module's own doctests and the three real sites.
_HAND_BUILT = re.compile(r"""(?:\{\{|["']\{)\s*[A-Za-z_][A-Za-z_0-9]*:[ ]""")


def test_the_escaper_has_exactly_one_caller():
    """One emitter, asserted rather than trusted.

    Moved here from ``tests/test_qa_compat.py`` on 2026-08-17 with the
    code it guards, and it FAILED on the move rather than passing
    vacuously, which is the property a guard is supposed to have: its
    second assertion refuses a renderer that calls the escaper nowhere,
    so the guard noticed that its subject had left the module.

    Two earlier drafts tried to recognise a rendered row by the shape of
    its f-string, and both flagged an error message whose example text
    contains braces. Counting the escaper's callers needs no heuristic.
    """
    tree = ast.parse(inspect.getsource(_yamlflow))
    callers = [
        f"{node.name} line {inner.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for inner in ast.walk(node)
        if isinstance(inner, ast.Call)
        and getattr(inner.func, "id", "") == "flow_scalar"
        and node.name != "flow_mapping"
    ]
    assert not callers, (
        "flow_scalar is called outside flow_mapping, so a value can again be written "
        "by a site that skips it: " + "; ".join(callers)
    )

    inside = [
        inner
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "flow_mapping"
        for inner in ast.walk(node)
        if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "flow_scalar"
    ]
    assert inside, (
        "flow_mapping does not call flow_scalar at all, so this guard would pass "
        "vacuously on an emitter that escapes nothing"
    )


def test_no_module_builds_a_flow_mapping_by_hand():
    """The rule the first repair did not carry: no site, package wide.

    The 2026-08-11 repair made ``qa.compat`` the one home and said so in
    its docstring. Six days later a second writer appeared BELOW it,
    could not import it, and concatenated its own. A guard scoped to one
    module cannot see that, which is why this one walks the package.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "_yamlflow.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _HAND_BUILT.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()[:80]}")
    assert not offenders, (
        "a YAML flow mapping is being built by hand instead of through "
        "_yamlflow.flow_mapping, which is how INC-20260811-1511-both happened and how "
        "it recurred on 2026-08-17:\n" + "\n".join(offenders)
    )


def test_insert_version_row_takes_no_pre_rendered_yaml():
    """The affordance is removed, not merely unused.

    The recurrence was possible because the splice accepted the flow
    mapping as a STRING, so quoting was the caller's problem and the
    library could not check what it had been handed. A guard that only
    counted callers would have passed on that signature the day before
    it was misused.
    """
    from pyflightstream.utils.manual import insert_version_row

    parameters = inspect.signature(insert_version_row).parameters
    assert "row" not in parameters, (
        "insert_version_row accepts a pre-rendered row again, so a caller can hand it "
        "an unescaped flow mapping and nothing will observe that it did"
    )
    keyword_only = [
        name
        for name, parameter in parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    ]
    assert keyword_only == ["command", "canonical", "status", "note"], keyword_only


@pytest.mark.parametrize(
    "note",
    [
        "SRC-751 p.290, unchanged from SRC-750 p.289",
        "a path C:" + chr(92) + "temp" + chr(92) + "x",
        chr(92) + "q is not a valid escape",
        'the "quoted" edition',
        "first line\nsecond line",
        "trailing backslash " + chr(92),
    ],
    ids=["plain", "backslash", "bad-escape", "quote", "newline", "trailing"],
)
def test_a_rendered_row_round_trips_whatever_the_note_carries(note):
    """The six shapes measured against the hand-built renderer.

    Measured on 2026-08-17 with the note interpolated between two
    literal quote characters, which is what shipped: `backslash`,
    `bad-escape` and `quote` made the chapter file unparsable, and
    `newline` was written silently truncated. All six round trip here.
    """
    text = (
        "SET_X:\n  versions:\n    "
        + '"26.120": '
        + flow_mapping({"status": "documented", "note": note})
    )
    loaded = yaml.safe_load(text)
    assert loaded["SET_X"]["versions"]["26.120"] == {"status": "documented", "note": note}


def test_status_is_the_only_bare_token():
    """A closed vocabulary is written unquoted; nothing else is.

    `OFF` and `NO` reach a YAML file as booleans, and this database has
    already lost an argument default that way, so the quoting rule is
    the blunt one everywhere except the one key whose values are a
    closed set.
    """
    assert RAW_KEYS == {"status"}
    rendered = flow_mapping({"status": "documented", "note": "NO", "extra": "OFF"})
    assert rendered == '{status: documented, note: "NO", extra: "OFF"}'
    assert yaml.safe_load(rendered) == {"status": "documented", "note": "NO", "extra": "OFF"}


def test_flow_scalar_writes_numbers_and_booleans_as_themselves():
    """A number quoted is a string, and an argument default is not text."""
    assert flow_scalar(True) == "true"
    assert flow_scalar(False) == "false"
    assert flow_scalar(None) == "null"
    assert flow_scalar(3) == "3"
    assert flow_scalar(2.5) == "2.5"
    assert flow_scalar(["a", "b"]) == '["a", "b"]'
