"""Tier 1: the user guide's code samples name things that exist.

Pipeline role: quality gate on the didactic material. The guide teaches
recipes by showing code, and its listings are never executed, so a name
that drifted from the API (or was never in it) reaches the reader as a
working example and fails in their session with an AttributeError or an
ImportError. The guide taught ``case.staged_geometry``, which the
campaign loop never set (it rewrites ``case.geometry``), and imported
``LoadsAssessor`` from ``pyflightstream.results``, where it does not
live (incident INC-20260723-2041-pyflightstream).

Scope: the dotted names the guide teaches on the objects a recipe
author handles (``case``, ``helpers``, ``script``) and the names its
``from pyflightstream... import ...`` lines claim. The check is on
names, not on running the samples; executing the guide would need a
licensed solver.
"""

import re
from importlib import import_module
from pathlib import Path

from pyflightstream.cases import SimCase
from pyflightstream.script import Script, helpers

GUIDE = Path(__file__).parents[1] / "guide" / "pyflightstream_user_guide.tex"

#: ``<name>.<attribute>``, in listings and in prose (where LaTeX
#: escapes the underscore as ``\_``). A quote or a path separator
#: before the word means a file name such as ``"case.txt"``, not an
#: attribute access.
ATTRIBUTE = r"""(?<!["'/\\])\b{name}\.([A-Za-z_][A-Za-z0-9_]*(?:\\_[A-Za-z0-9_]*)*)"""

#: ``from pyflightstream.<module> import a, b`` inside a listing, with
#: the parenthesized continuation form the campaign slide uses.
IMPORT = re.compile(r"from\s+(pyflightstream[A-Za-z0-9_.]*)\s+import\s+(?:\(([^)]*)\)|([^\n(]+))")

#: Objects the guide hands the reader, and what they are.
TAUGHT_OBJECTS = {"case": SimCase, "helpers": helpers, "script": Script}


def guide_text() -> str:
    assert GUIDE.is_file(), f"the user guide is not at {GUIDE}; update this guard's path"
    return GUIDE.read_text(encoding="utf-8")


def guide_attributes(name: str) -> set[str]:
    """Return every attribute the guide reads off ``name``."""
    pattern = re.compile(ATTRIBUTE.format(name=name))
    return {match.replace("\\_", "_") for match in pattern.findall(guide_text())}


def guide_imports() -> list[tuple[str, str]]:
    """Return every (module, name) the guide's import lines claim."""
    claimed: list[tuple[str, str]] = []
    for module, parenthesized, single_line in IMPORT.findall(guide_text()):
        for raw in (parenthesized or single_line).replace("\n", " ").split(","):
            name = raw.strip().split(" as ")[0].strip()
            if name and name.isidentifier():
                claimed.append((module, name))
    return claimed


def test_every_attribute_the_guide_teaches_exists():
    missing: list[str] = []
    for name, target in TAUGHT_OBJECTS.items():
        known = {attribute for attribute in dir(target) if not attribute.startswith("_")}
        if target is SimCase:
            known |= set(SimCase.model_fields)
        missing += [
            f"{name}.{attribute}" for attribute in guide_attributes(name) if attribute not in known
        ]
    assert not missing, (
        f"the user guide teaches {sorted(missing)}, which the library does not have; a "
        "reader copying the sample gets an AttributeError. Fix the guide, or add the "
        "name if the guide is describing intended API"
    )


def test_every_import_the_guide_teaches_resolves():
    missing: list[str] = []
    for module, name in guide_imports():
        try:
            imported = import_module(module)
        except ImportError:
            missing.append(f"{module} (module)")
            continue
        if not hasattr(imported, name):
            missing.append(f"{module}:{name}")
    assert not missing, (
        f"the user guide imports {sorted(missing)}, which does not resolve; a reader "
        "copying the listing gets an ImportError on the first line they run"
    )


def test_the_checks_actually_find_the_samples():
    # A pattern that silently stopped matching would leave both guards
    # reporting green over an unread file, which is the failure mode
    # this project has already had once (the self-skipping push-gate
    # script). Floors, not membership: they survive edits to the guide.
    text = guide_text()
    assert len(re.compile(ATTRIBUTE.format(name="case")).findall(text)) >= 8
    assert len(re.compile(ATTRIBUTE.format(name="helpers")).findall(text)) >= 20
    assert len(guide_imports()) >= 10
