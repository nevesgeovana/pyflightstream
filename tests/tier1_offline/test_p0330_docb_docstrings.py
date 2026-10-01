"""Tier 1, 0.33.0 package DOC-B: numpydoc docstrings, runnable examples, one home (NFR-30).

Each test names its requirement in its own source, because the goal's checker
reads function sources. The exported functions are walked the way the API
reference walks them (``scripts/gen_api_reference.py``: every public module and
its public surface), so a function the reference shows is a function checked
here. Each check also runs once on a planted defect, so a check that accepts
everything cannot pass.

DOC-B is cut in two parts. Part 1 completed every module but the ones other
packages of 0.33.0 were cutting at the time, and four package roots the
facade ratchet holds; those are pinned below, and the pins only shrink: a
pinned module that passes leaves its list in the same change, and part 2
and the facade cuts empty the lists.
"""

from __future__ import annotations

import ast
import builtins
import doctest
import functools
import importlib
import importlib.util
import inspect
import json
import logging
import re
import sys
import textwrap
from pathlib import Path

import griffe

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pyflightstream"
DOCS = REPO / "docs"

#: Package roots that still define functions and classes of their own. The
#: facade ratchet of the architecture guards (G8) counts every statement line
#: of such a root, docstring lines included, and its entries only shrink, so
#: their docstrings are completed when each root becomes a facade and its
#: definitions move to a module (the cuts of 0.33.0), not by growing the root.
#: What ``probes`` holds back is the Raises section of ``write_points_csv``,
#: so it is pinned on ``NUMPYDOC_PENDING`` too. This table says WHY a root is
#: pending and is tied to the facade baselines; ``NUMPYDOC_PENDING`` is the
#: ratchet, and a held root that is complete leaves it like any other module.
FACADE_HELD = {
    "cases/__init__.py",
    "farfield/__init__.py",
    "probes/__init__.py",
    "script/__init__.py",
}

#: Modules (paths under ``src/pyflightstream``) whose exported functions do not
#: yet all document their parameters, result and the catalogued errors they
#: raise. DOC-B part 2 completes them; the list only shrinks. A pin follows
#: its functions when a cut moves them: WP3 (AD-11) moved the pending
#: functions of `post.guides`, the `results` root and `workspace.inputs` into
#: `post.glossary`, `post.input_template`, `results.core`, `results.loads`,
#: `results.log`, `workspace.hpc` and `workspace.sidecars`, which are pinned
#: in their stead; no function joined the pending set. The `results` root
#: and `run.records`, whose definitions left, pass and leave the list.
#: `cases/workflows.py`, cut by WP4 into the package `cases/workflows/` whose
#: modules all pass, leaves this list and the examples list. WP6
#: (AD-14) moved the pending functions of the `run` root into `run._campaign`,
#: `run._executors`, `run._identity` and `run._plan`, pinned in its stead; the
#: root, a facade now, leaves the list.
#: DOC-B part 2 group g1: `cases`, `cases.windows`, `farfield` and `probes` leave the list.
NUMPYDOC_PENDING = {
    "cases/__init__.py",
    "farfield/__init__.py",
    "probes/__init__.py",
    "results/sectional_loads.py",
    # WP5 (AD-13) moved the pending functions of `post.products` into the four
    # family modules, which are pinned in their stead.
    "post/point_tables.py",
    "post/polar.py",
    "post/rotor_table.py",
    "post/unsteady_polar.py",
    "results/core.py",
    "results/loads.py",
    "results/log.py",
    "results/native_surface.py",
    "results/surface.py",
    "results/tables.py",
    "run/_campaign.py",
    "run/_executors.py",
    "run/_identity.py",
    "run/_plan.py",
    "run/cli.py",
    "workspace/__init__.py",
    "workspace/hpc.py",
    "workspace/inputs.py",
    "workspace/sidecars.py",
}

#: Modules whose documented entry points do not yet all carry an Examples
#: section. DOC-B part 2 completes them; the list only shrinks. The entry
#: points WP3 moved out of the `results` root are pinned in their new homes,
#: `results.exports` and `results.loads`, and the root, which keeps none,
#: leaves the list. Those WP6 moved out of the `run` root are pinned in
#: `run._assessment`, `run._campaign`, `run._executors`, `run._identity` and
#: `run._plan`, and the root leaves the list.
#: DOC-B part 2 group g1: `cases` and `script` leave the list.
EXAMPLES_PENDING = {
    "results/exports.py",
    "results/loads.py",
    "results/surface.py",
    "results/tables.py",
    "run/_assessment.py",
    "run/_campaign.py",
    "run/_executors.py",
    "run/_identity.py",
    "run/_plan.py",
    "run/cli.py",
    "workspace/__init__.py",
    "workspace/inputs.py",
}

#: Documented entry points whose example cannot run offline without the solver
#: or a recorded workspace, with the reason. Each still has no Examples
#: section; one that gains it leaves this table.
NO_OFFLINE_EXAMPLE = {
    "pyflightstream.fsi.cli.main": "the pyfs-fsi console entry, called by the solver; the CLI "
    "reference documents it",
    "pyflightstream.qa.cli.main": "the pyfs-qa console entry; the CLI reference documents it",
    "pyflightstream.utils.cli.main": "the pyfs-utils console entry; the CLI reference documents it",
    "pyflightstream.workspace.cli.main": "the pyfs-workspace console entry; the CLI reference "
    "documents it",
    "pyflightstream.workspace.excel.main": "the Excel workbook command; the CLI reference "
    "documents it",
    "pyflightstream.workspace.excel_bridge.main": "the bridge the workbook's macro calls; it "
    "reads a snapshot the macro wrote",
    "pyflightstream.workspace.excel_file.read_snapshot": "reads a saved Excel workbook",
    "pyflightstream.workspace.excel_file.patch_cells": "rewrites a saved Excel workbook",
    "pyflightstream.post.boundary_layer.sample_boundary_layer": "reads the surface VTK export "
    "and the section cuts of a run",
    "pyflightstream.post.boundary_layer.write_boundary_layer_table": "writes the samples "
    "sample_boundary_layer reads off a run's exports",
    "pyflightstream.post.corrections.sector_offset_calibration": "reads the rotor tables of "
    "a posted workspace",
    "pyflightstream.run.matrix.plan_additional_post": "reads the recorded runs of a workspace",
    "pyflightstream.workspace.fsi_setup.resolve_fsi_setup": "reads an FSI artifact of a "
    "workspace's inputs",
    "pyflightstream.workspace.fsi_setup.resolve_row_fsi": "reads an FSI artifact of a "
    "workspace's inputs",
}

#: Exported functions whose own ``raise`` lets a catalogued error reach the
#: caller: 304 when the Raises check landed. A resolver that stopped finding
#: the classes would find few and check nothing.
RAISING_FLOOR = 280

_HEADER = re.compile(r"^([A-Z][A-Za-z ]+)\n-{3,}[ \t]*$", re.MULTILINE)


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@functools.cache
def _generator():
    return _script("gen_api_reference")


def _sections(doc: str) -> dict[str, str]:
    """Each numpydoc section of a docstring, by its header, to its body."""
    marks = list(_HEADER.finditer(doc))
    return {
        mark.group(1).strip(): doc[
            mark.end() : marks[i + 1].start() if i + 1 < len(marks) else None
        ]
        for i, mark in enumerate(marks)
    }


#: A numpydoc entry line: one or more names, commas between, an optional type.
_ENTRY = re.compile(r"^\*{0,2}[A-Za-z_]\w*(?:\s*,\s*\*{0,2}[A-Za-z_]\w*)*(?:\s+:\s+\S.*)?$")


def _documented_parameters(body: str) -> set[str]:
    """The names a Parameters section documents.

    A name counts only from an entry line at the section's own indent that
    reads ``name``, ``name : type`` or ``a, b : type``, and only when an
    indented description follows it: stray prose at the indent names nothing,
    and a name with no description is not documented.
    """
    lines = [line for line in body.split("\n") if line.strip()]
    if not lines:
        return set()
    indent = min(len(line) - len(line.lstrip()) for line in lines)
    names: set[str] = set()
    for i, line in enumerate(lines):
        if len(line) - len(line.lstrip()) != indent or not _ENTRY.match(line.strip()):
            continue
        following = lines[i + 1] if i + 1 < len(lines) else ""
        if len(following) - len(following.lstrip()) <= indent:
            continue
        head = line.strip().split(" : ")[0]
        names.update(part.strip().lstrip("*") for part in head.split(","))
    return names


def _documented_types(body: str) -> set[str]:
    """The exception names a Raises section lists: its entry lines, last dotted part."""
    lines = [line for line in body.split("\n") if line.strip()]
    if not lines:
        return set()
    indent = min(len(line) - len(line.lstrip()) for line in lines)
    names: set[str] = set()
    for line in lines:
        if len(line) - len(line.lstrip()) == indent:
            for part in re.split(r",|\bor\b", line.strip()):
                names.add(part.strip(" `~:").removeprefix("class:").split(".")[-1].strip("`~"))
    return names


def _resolve(expression: ast.expr, namespace: dict):
    """The object a ``raise`` or ``except`` expression names in a module namespace."""
    if isinstance(expression, ast.Call):
        expression = expression.func
    if isinstance(expression, ast.Name):
        return namespace.get(expression.id, getattr(builtins, expression.id, None))
    if isinstance(expression, ast.Attribute):
        return getattr(_resolve(expression.value, namespace), expression.attr, None)
    return None


def escaping_catalogued_errors(
    node: ast.FunctionDef | ast.AsyncFunctionDef, namespace: dict
) -> set[str]:
    """The catalogued errors a function's own ``raise`` statements let reach its caller.

    A catalogued error is a :class:`~pyflightstream.exceptions.PyflightstreamError`.
    A ``raise`` inside a ``try`` whose handler catches that class (or a base,
    or everything) does not reach the caller. Only the function's own body is
    read: an error a callee raises is not seen, which is the limit of this check.
    """
    from pyflightstream.exceptions import PyflightstreamError

    found: set[str] = set()

    def caught(handlers: list, cls: type) -> bool:
        return any(h is None or (inspect.isclass(h) and issubclass(cls, h)) for h in handlers)

    def visit(current: ast.AST, handlers: list) -> None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        if isinstance(current, ast.Raise) and current.exc is not None:
            cls = _resolve(current.exc, namespace)
            if (
                inspect.isclass(cls)
                and issubclass(cls, PyflightstreamError)
                and not caught(handlers, cls)
            ):
                found.add(cls.__name__)
        if isinstance(current, (ast.Try, ast.TryStar)):
            types: list = []
            for handler in current.handlers:
                if handler.type is None:
                    types.append(None)
                elif isinstance(handler.type, ast.Tuple):
                    types += [_resolve(e, namespace) for e in handler.type.elts]
                else:
                    types.append(_resolve(handler.type, namespace))
            for statement in current.body:
                visit(statement, handlers + types)
            for statement in (*current.handlers, *current.orelse, *current.finalbody):
                visit(statement, handlers)
            return
        for child in ast.iter_child_nodes(current):
            visit(child, handlers)

    for statement in node.body:
        visit(statement, [])
    return found


def raises_gaps(
    node: ast.FunctionDef | ast.AsyncFunctionDef, doc: str, namespace: dict
) -> list[str]:
    """What a function's docstring lacks of NFR-30 R2's Raises: each escaping catalogued error."""
    listed = _documented_types(_sections(doc).get("Raises", ""))
    missing = sorted(escaping_catalogued_errors(node, namespace) - listed)
    return [f"Raises does not name {missing}"] if missing else []


def _own_nodes(node: ast.AST):
    """Every node of a function's own body, nested functions and classes left out."""
    stack = list(getattr(node, "body", []))
    while stack:
        current = stack.pop()
        yield current
        stack += [
            child
            for child in ast.iter_child_nodes(current)
            if not isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
            )
        ]


def numpydoc_gaps(node: ast.FunctionDef | ast.AsyncFunctionDef, doc: str) -> list[str]:
    """What a function's docstring lacks of NFR-30 R2: Parameters and Returns.

    Every parameter but ``self`` and ``cls`` is named in ``Parameters``
    (``*args`` and ``**kwargs`` with or without their stars, and several names
    on one line separated by commas). A generator states ``Yields`` or
    ``Returns``; any other function annotated with something other than None,
    or returning a value, states ``Returns``.
    """
    sections = _sections(doc)
    arguments = node.args
    names = [a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)]
    names += [a.arg for a in (arguments.vararg, arguments.kwarg) if a is not None]
    names = [name for name in names if name not in ("self", "cls")]
    gaps = []
    if names:
        documented = _documented_parameters(sections.get("Parameters", ""))
        missing = [name for name in names if name not in documented]
        if missing:
            gaps.append(f"Parameters does not name {missing}")
    own = list(_own_nodes(node))
    annotation = node.returns
    returns_none = annotation is not None and (
        (isinstance(annotation, ast.Constant) and annotation.value is None)
        or (isinstance(annotation, ast.Name) and annotation.id in ("None", "NoReturn", "Never"))
    )
    if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in own):
        if "Yields" not in sections and "Returns" not in sections:
            gaps.append("no Yields section")
    elif not returns_none and (
        annotation is not None
        or any(isinstance(n, ast.Return) and n.value is not None for n in own)
    ):
        if "Returns" not in sections:
            gaps.append("no Returns section")
    return gaps


def _definition(function) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """The function's module path under ``src/pyflightstream`` and its ``def`` node."""
    path = Path(inspect.getsourcefile(function)).resolve()
    first = function.__code__.co_firstlineno
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function.__name__
            and first in (node.lineno, *(d.lineno for d in node.decorator_list))
        ):
            return path.relative_to(SRC.resolve()).as_posix(), node
    raise AssertionError(f"no def of {function.__qualname__} in {path}")


@functools.cache
def _exported() -> tuple[tuple[str, object], ...]:
    """Every exported function and class once, as (dotted path where defined, object)."""
    generator = _generator()
    found: dict[str, object] = {}
    for module_name in generator.public_subpackages():
        module = importlib.import_module(module_name)
        for name in generator.public_surface(module_name):
            obj = getattr(module, name, None)
            target = inspect.unwrap(obj) if inspect.isfunction(obj) else obj
            if inspect.isfunction(target) or inspect.isclass(target):
                found.setdefault(f"{target.__module__}.{target.__qualname__}", target)
    return tuple(sorted(found.items()))


def _functions():
    return [(dotted, obj) for dotted, obj in _exported() if inspect.isfunction(obj)]


def _pending_failures(pending: set[str], failures: dict[str, list[str]]) -> list[str]:
    """Why the pinned list is wrong: a pinned module that now passes, or is gone."""
    wrong = [f"{rel} passes now: take it off the list" for rel in sorted(pending - set(failures))]
    return wrong + [f"{rel} is no module" for rel in sorted(pending) if not (SRC / rel).is_file()]


# ----------------------------------------------------------------- R1 and R2


def test_every_exported_function_documents_its_parameters_and_result():
    """NFR-30 R1 and R2: Parameters, Returns where a value returns, Raises where one escapes.

    The Raises half reads the function's own ``raise`` statements of a
    catalogued error that no enclosing handler catches; an error a callee
    raises is beyond what it reads.

    P0330-DOCSTRINGS-NUMPYDOC
    """
    # P0330-DOCSTRINGS-NUMPYDOC
    functions = _functions()
    # The floor: 767 exported functions when part 1 landed. A walk that stops
    # resolving finds few and would pass over nothing.
    assert len(functions) >= 700, f"only {len(functions)} exported functions were walked"
    failures: dict[str, list[str]] = {}
    raising = 0
    for dotted, function in functions:
        rel, node = _definition(function)
        doc = inspect.getdoc(function) or ""
        raising += bool(escaping_catalogued_errors(node, function.__globals__))
        gaps = numpydoc_gaps(node, doc) + raises_gaps(node, doc, function.__globals__)
        if gaps:
            failures.setdefault(rel, []).append(f"{dotted}: {'; '.join(gaps)}")
    outside = [
        line for rel, lines in failures.items() if rel not in NUMPYDOC_PENDING for line in lines
    ]
    assert outside == [], "exported functions without numpydoc sections:\n" + "\n".join(outside)
    assert _pending_failures(NUMPYDOC_PENDING, failures) == []
    # The Raises floor: RAISING_FLOOR exported functions let a catalogued
    # error of their own reach the caller; a resolver that stopped finding
    # the classes would find none and check nothing.
    assert raising >= RAISING_FLOOR, f"only {raising} functions raise a catalogued error"
    # A root is held only while the facade ratchet tables it.
    baselines = json.loads(
        (REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(
            encoding="utf-8"
        )
    )
    assert sorted(FACADE_HELD - set(baselines["facade_lines"])) == []


def test_every_exported_docstring_parses_cleanly(caplog):
    """NFR-30 R2: the numpydoc parser the reference renders with reads every one cleanly.

    P0330-DOCSTRINGS-NUMPYDOC
    """
    # P0330-DOCSTRINGS-NUMPYDOC: prose after a section with no heading of its
    # own is read as parameters, which is the defect the reference silenced
    # until DOC-B fixed its two docstrings.
    package = griffe.load("pyflightstream", search_paths=[str(REPO / "src")], resolve_aliases=False)
    warned = []
    checked = 0
    for dotted, _obj in _exported():
        docstring = package[dotted.split(".", 1)[1]].docstring
        if docstring is None:
            continue
        checked += 1
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="griffe"):
            griffe.parse_numpy(docstring)
        warned += [f"{dotted}: {record.getMessage()}" for record in caplog.records]
    assert checked >= 900, f"only {checked} docstrings were parsed"
    assert warned == [], "\n".join(warned)

    planted = griffe.Docstring(
        "Do a thing.\n\nParameters\n----------\nx : int\n    The x.\n\n"
        "A paragraph that is no parameter.\n",
        parent=package["versions"],
    )
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="griffe"):
        griffe.parse_numpy(planted)
    assert caplog.records, "the control: prose after Parameters must warn"


def test_the_numpydoc_check_refuses_planted_defects():
    """NFR-30 R2: the check is shown to refuse each defect it exists for.

    P0330-DOCSTRINGS-NUMPYDOC
    """
    # P0330-DOCSTRINGS-NUMPYDOC: controls, so a check that accepts everything fails.
    complete = textwrap.dedent(
        '''
        def f(a, b=1, *args, c, **kwargs) -> int:
            """Summary.

            Parameters
            ----------
            a : int
                The a.
            b, c : int
                Two on one line.
            *args
                More.
            **kwargs
                Keywords.

            Returns
            -------
            int
                The value.
            """
            return a
        '''
    )

    def gaps(source: str) -> list[str]:
        node = ast.parse(source).body[0]
        assert isinstance(node, ast.FunctionDef)
        return numpydoc_gaps(node, ast.get_docstring(node) or "")

    assert gaps(complete) == []
    # `complete` is dedented: its docstring lines sit four spaces in.
    assert gaps(complete.replace("    b, c : int\n", "    b : int\n")) == [
        "Parameters does not name ['c']"
    ]
    no_returns = complete.split("    Returns")[0] + '    """\n    return a\n'
    assert gaps(no_returns) == ["no Returns section"]
    generator = (
        'def g(n) -> Iterator[int]:\n    """Summary.\n\n    Parameters\n    ----------\n'
        '    n : int\n        How many.\n    """\n    yield n\n'
    )
    assert gaps(generator) == ["no Yields section"]
    nothing = (
        'def h(x) -> None:\n    """Summary.\n\n    Parameters\n    ----------\n'
        '    x : int\n        The x.\n    """\n'
    )
    assert gaps(nothing) == []
    # Stray prose at the entry indent names nothing, and a name with no
    # description is not documented.
    prose = nothing.replace("    x : int\n        The x.\n", "    The x, an int.\n")
    assert gaps(prose) == ["Parameters does not name ['x']"]
    bare = nothing.replace("    x : int\n        The x.\n", "    x : int\n")
    assert gaps(bare) == ["Parameters does not name ['x']"]

    # The Raises half, on a raise that escapes and on one its own handler catches.
    from pyflightstream.exceptions import ProductError

    namespace = {"ProductError": ProductError}
    raising = (
        'def r(x) -> None:\n    """Summary.\n\n    Parameters\n    ----------\n'
        "    x : int\n        The x.\n\n    Raises\n    ------\n    ProductError\n"
        '        Always.\n    """\n    raise ProductError("no")\n'
    )

    def raised(source: str) -> list[str]:
        node = ast.parse(source).body[0]
        assert isinstance(node, ast.FunctionDef)
        return raises_gaps(node, ast.get_docstring(node) or "", namespace)

    assert raised(raising) == []
    undocumented = raising.replace(
        "    Raises\n    ------\n    ProductError\n        Always.\n", ""
    )
    assert raised(undocumented) == ["Raises does not name ['ProductError']"]
    wrong_name = raising.replace("    ProductError\n", "    ValueError\n")
    assert raised(wrong_name) == ["Raises does not name ['ProductError']"]
    handled = undocumented.replace(
        '    raise ProductError("no")\n',
        '    try:\n        raise ProductError("no")\n    except ProductError:\n        pass\n',
    )
    assert raised(handled) == []

    # And on a real exported function with its Raises entry cut out.
    from pyflightstream.fsi.driver import coupling_step

    _, step = _definition(coupling_step)
    step_doc = inspect.getdoc(coupling_step) or ""
    assert raises_gaps(step, step_doc, coupling_step.__globals__) == []
    assert raises_gaps(
        step, step_doc.replace("StaleLoadsError\n", "StaleLoads\n"), coupling_step.__globals__
    ) == ["Raises does not name ['StaleLoadsError']"]

    # And on a real exported function with its Parameters section cut out.
    from pyflightstream.versions import resolve

    _, node = _definition(resolve)
    doc = inspect.getdoc(resolve) or ""
    assert numpydoc_gaps(node, doc) == []
    cut = doc.replace("Parameters\n----------", "Parameter list\n--------------")
    assert numpydoc_gaps(node, cut) and "Parameters does not name" in numpydoc_gaps(node, cut)[0]


# ----------------------------------------------------------------- R3


def _example_gaps(doc: str) -> list[str]:
    """What a docstring lacks of R3: an Examples section holding doctest examples."""
    section = _sections(doc).get("Examples")
    if section is None:
        return ["no Examples section"]
    if not doctest.DocTestParser().get_examples(textwrap.dedent(section)):
        return ["an Examples section with no >>> example"]
    return []


def _documented_entry_points() -> list[tuple[str, object, str]]:
    """The reference's documented tier: (dotted, object, module path), exceptions left out."""
    generator = _generator()
    words = generator.guide_words(REPO)
    used = set()
    for module_name in generator.public_subpackages():
        module = importlib.import_module(module_name)
        for name in generator.public_surface(module_name):
            if name in words:
                obj = getattr(module, name, None)
                target = inspect.unwrap(obj) if inspect.isfunction(obj) else obj
                used.add(id(target))
    found = []
    for dotted, obj in _exported():
        if id(obj) not in used or (inspect.isclass(obj) and issubclass(obj, BaseException)):
            continue
        path = Path(inspect.getsourcefile(obj)).resolve()
        found.append((dotted, obj, path.relative_to(SRC.resolve()).as_posix()))
    return found


def _root_conftest():
    spec = importlib.util.spec_from_file_location("_docb_root_conftest", REPO / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_documented_entry_points_carry_examples_the_gate_runs():
    """NFR-30 R3: every documented entry point carries examples, and CI runs them.

    P0330-DOC-EXAMPLES
    """
    # P0330-DOC-EXAMPLES
    entry_points = _documented_entry_points()
    assert len(entry_points) >= 60, f"only {len(entry_points)} documented entry points"
    failures: dict[str, list[str]] = {}
    exempt_but_documented = []
    for dotted, obj, rel in entry_points:
        gaps = _example_gaps(inspect.getdoc(obj) or "")
        if dotted in NO_OFFLINE_EXAMPLE:
            if not gaps:
                exempt_but_documented.append(dotted)
            continue
        if gaps:
            failures.setdefault(rel, []).append(f"{dotted}: {gaps[0]}")
    outside = [
        line for rel, lines in failures.items() if rel not in EXAMPLES_PENDING for line in lines
    ]
    assert outside == [], "documented entry points without examples:\n" + "\n".join(outside)
    assert _pending_failures(EXAMPLES_PENDING, failures) == []
    assert exempt_but_documented == [], (
        f"take these off NO_OFFLINE_EXAMPLE: {exempt_but_documented}"
    )
    tier = {dotted for dotted, _obj, _rel in entry_points}
    assert set(NO_OFFLINE_EXAMPLE) <= tier, sorted(set(NO_OFFLINE_EXAMPLE) - tier)

    # The gate: the CI step runs the docstring examples of the package source,
    # and the root conftest's docstring collector reads every module defining one.
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"run: pytest src/pyflightstream\b", ci), (
        "the executable-examples step is gone"
    )
    conftest = _root_conftest()
    # Sybil is a dev dependency (pyproject), and every CI test leg installs
    # [dev]: without it the gate does not run, so its absence is a failure
    # here rather than a silent pass.
    assert getattr(conftest, "_SYBIL", False), (
        "sybil is not installed, so the executable-examples gate collects nothing"
    )
    docstrings = conftest.EXAMPLE_SYBILS[0]
    for _dotted, _obj, rel in entry_points:
        assert docstrings.should_parse(SRC / rel), f"the examples gate does not read {rel}"


def test_the_examples_check_refuses_planted_defects():
    """NFR-30 R3: the examples check refuses a missing section and an empty one.

    P0330-DOC-EXAMPLES
    """
    # P0330-DOC-EXAMPLES: controls.
    good = "Summary.\n\nExamples\n--------\n>>> 1 + 1\n2\n"
    assert _example_gaps(good) == []
    assert _example_gaps("Summary.\n\nReturns\n-------\nint\n    One.\n") == ["no Examples section"]
    assert _example_gaps("Summary.\n\nExamples\n--------\nCall it with one.\n") == [
        "an Examples section with no >>> example"
    ]
    from pyflightstream.versions import resolve

    assert _example_gaps(inspect.getdoc(resolve) or "") == []
    assert _example_gaps((inspect.getdoc(resolve) or "").split("Examples\n--------")[0]) == [
        "no Examples section"
    ]


# ----------------------------------------------------------------- R4

#: The page that defines the reductions, and the section that lists them.
REDUCTIONS_HOME = "post-processing-definitions.md"
REDUCTIONS_ANCHOR = "the-reductions-of-an-unsteady-point"
REDUCTIONS = ("time_average", "per_blade", "phase_locked", "per_revolution")
_REDUCTION_FILE = re.compile(r"_(time_average|phase_locked|per_blade|per_revolution|harmonics)\b")
_REDUCTION_NAMED = re.compile(
    r"`(time_average|per_blade|phase_locked|per_revolution)`"
    r"|_(time_average|phase_locked|per_blade|per_revolution)[._<\[]"
)
#: A claim a page once made against the definition of record (GEO-072 docs audit, item 6).
_STALE_CLAIMS = ("What does NOT ship yet is the step that runs those four",)


def _user_pages() -> dict[str, str]:
    """Every hand-written user page but the home: the release records are history."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(DOCS.glob("*.md"))
        if path.name != REDUCTIONS_HOME
        and not path.name.startswith(("migrating-to-", "release-notes"))
    }


def reductions_restated(name: str, text: str) -> list[str]:
    """Why a page other than the home defines the reductions instead of linking to them.

    A ratchet on the markers a restatement was measured to carry, not a
    reading of prose: a table row naming a reduction's file, a stale claim
    the audit found, and a page that names a reduction without linking the
    home. A page that restates a definition in its own prose and links the
    home passes, and nothing here compares the home's text with the code;
    both are review's to catch.
    """
    found = [
        f"{name}: a table row defines a reduction file: {line.strip()[:80]}"
        for line in text.splitlines()
        if line.lstrip().startswith("|") and _REDUCTION_FILE.search(line)
    ]
    found += [f"{name}: {claim!r}" for claim in _STALE_CLAIMS if claim in text]
    if _REDUCTION_NAMED.search(text) and REDUCTIONS_HOME not in text:
        found.append(f"{name}: names a reduction and does not link to {REDUCTIONS_HOME}")
    return found


def test_the_unsteady_reductions_have_one_home():
    """NFR-30 R4: the definitions page defines the reductions; every other page links to it.

    P0330-DOC-REDUCTIONS-HOME
    """
    # P0330-DOC-REDUCTIONS-HOME
    home = (DOCS / REDUCTIONS_HOME).read_text(encoding="utf-8")
    heading = "## The reductions of an unsteady point\n"
    assert heading in home, f"{REDUCTIONS_HOME} has no section listing the reductions"
    section = home.split(heading, 1)[1].split("\n## ", 1)[0]
    for anchor in (*REDUCTIONS, "the-per-station-harmonics", "the-averaging-window"):
        assert f"(#{anchor})" in section, f"the section does not link to #{anchor}"
    for reduction in REDUCTIONS:
        assert f"\n## `{reduction}`\n" in home, f"{REDUCTIONS_HOME} does not define {reduction}"
    assert f"[`{REDUCTIONS[0]}`](#{REDUCTIONS[0]})" in section

    pages = _user_pages()
    naming = [name for name, text in pages.items() if _REDUCTION_NAMED.search(text)]
    assert len(naming) >= 4, f"only {naming} name a reduction; the walk has lost its pages"
    for linked in ("workflow-unsteady.md", "workflow-unsteady-rotor.md"):
        assert f"{REDUCTIONS_HOME}#{REDUCTIONS_ANCHOR}" in pages[linked], linked
    restated = [line for name, text in pages.items() for line in reductions_restated(name, text)]
    assert restated == [], "\n".join(restated)


def test_the_reductions_check_refuses_planted_defects():
    """NFR-30 R4: a restated table, a stale claim and a missing link are each refused.

    P0330-DOC-REDUCTIONS-HOME
    """
    # P0330-DOC-REDUCTIONS-HOME: controls on the real page.
    page = (DOCS / "workflow-unsteady.md").read_text(encoding="utf-8")
    assert reductions_restated("workflow-unsteady.md", page) == []
    row = "| `probes/<point>_time_average.csv` | `unsteady` | the averaging window |\n"
    assert len(reductions_restated("planted", page + row)) == 1
    assert len(reductions_restated("planted", page + _STALE_CLAIMS[0])) == 1
    unlinked = page.replace(REDUCTIONS_HOME, "elsewhere.md")
    assert reductions_restated("planted", unlinked) == [
        f"planted: names a reduction and does not link to {REDUCTIONS_HOME}"
    ]


# ----------------------------------------------------------------- __all__ of DOC-B

#: The public modules DOC-B part 1 gave an ``__all__`` (decision 10). Each
#: lists every public name it defines; a name nobody should use is made
#: private rather than left out. Re-exported imports are not listed: they
#: still import from the module, and leave only its star-import surface.
DOCB_ALL_MODULES = (
    "pyflightstream.cases.acoustics",
    "pyflightstream.cases.field_coverage",
    "pyflightstream.cases.freestream",
    "pyflightstream.cases.fsi_workspace",
    "pyflightstream.cases.qsteady",
    "pyflightstream.cases.setup_surfaces",
    "pyflightstream.commands",
    "pyflightstream.fsi.beam",
    "pyflightstream.fsi.centrifugal",
    "pyflightstream.fsi.cli",
    "pyflightstream.fsi.config",
    "pyflightstream.fsi.driver",
    "pyflightstream.fsi.kinematics",
    "pyflightstream.fsi.loads",
    "pyflightstream.fsi.nodes",
    "pyflightstream.fsi.state",
    "pyflightstream.fsi.wing",
    "pyflightstream.options",
    "pyflightstream.overview",
    "pyflightstream.post.boundary_layer",
    "pyflightstream.post.diagnostics",
    "pyflightstream.post.qsteady",
    "pyflightstream.probes.errors",
    "pyflightstream.qa.cli",
    "pyflightstream.qa.compat",
    "pyflightstream.qa.errors",
    "pyflightstream.qa.probes",
    "pyflightstream.reference",
    "pyflightstream.script.entities",
    "pyflightstream.script.motion",
    "pyflightstream.utils.cli",
    "pyflightstream.versions",
    "pyflightstream.workspace.cli",
    "pyflightstream.workspace.excel",
    "pyflightstream.workspace.excel_bridge",
    "pyflightstream.workspace.excel_file",
    "pyflightstream.workspace.excel_sync",
    "pyflightstream.workspace.flight_condition",
    "pyflightstream.workspace.fsi_setup",
    "pyflightstream.workspace.naming",
    "pyflightstream.workspace.rename_groups",
    "pyflightstream.workspace.setup_inspection",
    "pyflightstream.workspace.setup_standards",
)

#: A module-level name that is no API: the module's logger.
NOT_LISTED = frozenset({"logger"})


def defined_public_names(source: str) -> set[str]:
    """The public names a module's own top level defines: def, class and assignment."""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {name for name in names if not name.startswith("_")} - NOT_LISTED


def all_gaps(module, source: str) -> list[str]:
    """Why a module's ``__all__`` is not its public surface: a defined name left out, or a ghost."""
    listed = vars(module).get("__all__")
    if listed is None:
        return [f"{module.__name__} declares no __all__"]
    gaps = [
        f"{module.__name__}: {name} is defined and not listed"
        for name in sorted(defined_public_names(source) - set(listed))
    ]
    gaps += [
        f"{module.__name__}: {name} is listed and does not import"
        for name in listed
        if not hasattr(module, name)
    ]
    return gaps


def test_the_modules_docb_gave_all_list_every_name_they_define():
    """Decision 10 and NFR-29 R8: an ``__all__`` DOC-B added drops no defined public name.

    The API reference reads ``__all__`` (``gen_api_reference.public_surface``),
    so a name left out would leave the reference and its completeness check
    together; this test reads the source instead. The 0.32.0 surface of these
    modules was measured against this tree when the check landed: every name
    they define, and every name they import, still imports from its path.

    P0330-DOC-API-COMPLETE
    """
    # P0330-DOC-API-COMPLETE
    gaps = []
    for name in DOCB_ALL_MODULES:
        module = importlib.import_module(name)
        gaps += all_gaps(module, Path(inspect.getsourcefile(module)).read_text(encoding="utf-8"))
    assert gaps == [], "\n".join(gaps)

    # Controls: a defined name left out, and a listed name that does not import.
    from pyflightstream import versions

    source = Path(inspect.getsourcefile(versions)).read_text(encoding="utf-8")
    assert all_gaps(versions, source + "\ndef planted_public():\n    pass\n") == [
        "pyflightstream.versions: planted_public is defined and not listed"
    ]
    assert all_gaps(versions, source + "\nlogger = None\n") == []


# ----------------------------------------------------------------- the field operations page


def test_the_field_operations_page_names_the_one_operation_that_fills_a_body():
    """The page's "What it does not do" names ``fill-interior``, which replaces interior points.

    The sentence said the field operations replace no point inside a body;
    ``field fill-interior`` (0.32.0, ``workspace.fields.fill_interior``) does.

    P0330-DOC-FILL-INTERIOR
    """
    # P0330-DOC-FILL-INTERIOR
    from pyflightstream.workspace import fields

    assert callable(fields.fill_interior)
    cli = (SRC / "workspace" / "cli.py").read_text(encoding="utf-8")
    assert '"fill-interior"' in cli, "the field fill-interior subcommand is gone"

    def wrong(page: str) -> list[str]:
        section = page.split("## What it does not do\n", 1)[1].split("\n## ", 1)[0]
        flat = " ".join(section.split())
        found = []
        if "`fill-interior`" not in flat:
            found.append("the section does not name fill-interior")
        if "It does not replace points that lie inside a body" in flat:
            found.append("the section says no operation replaces interior points")
        return found

    page = (DOCS / "field-operations.md").read_text(encoding="utf-8")
    assert wrong(page) == []
    # Control: the sentence as 0.32.0 shipped it.
    old = (
        "## What it does not do\n\nIt does not interpolate. It does not replace points "
        "that lie inside a body,\nwhere a survey carries no flow; the field is written "
        "as sampled.\n"
    )
    assert wrong(old) == [
        "the section does not name fill-interior",
        "the section says no operation replaces interior points",
    ]
