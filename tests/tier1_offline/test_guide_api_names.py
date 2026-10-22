"""Tier 1: the user guide's code samples name things that exist.

Pipeline role: quality gate on the didactic material. The guide teaches
recipes by showing code, and its listings are never executed, so a name
that drifted from the API (or was never in it) reaches the reader as a
working example and fails in their session with an AttributeError or an
ImportError. The guide taught ``case.staged_geometry``, which the
campaign loop never set (it rewrites ``case.geometry``), and imported
``LoadsAssessor`` from ``pyflightstream.results``, where it does not
live (incident INC-20260723-2041-pyflightstream).

Scope, in two halves, because the guide teaches its six objects in two
different ways and a guard over one half is blind to the other.

The DOTTED half: the attributes the guide reads off the objects a recipe
author handles (``case``, ``helpers``, ``script``, ``campaign``) and the
names its ``from pyflightstream... import ...`` lines claim.

The CLASS half: the class names the guide names in ``\\code{}`` spans,
which is how ``CampaignWorkspace``, ``RunRecord`` and the rest of the
object table are taught. Measured 2026-08-18, ``workspace`` and
``record`` carry ZERO dotted hits in the guide, so until this half
existed the two objects a reader meets in every managed-run listing were
outside the guard entirely: renaming ``RunRecord`` left the whole module
green (OPS-2005.05).

The check is on names, not on running the samples; executing the guide
would need a licensed solver.
"""

import re
from importlib import import_module
from pathlib import Path

from pydantic import BaseModel

from pyflightstream.cases import Campaign, SimCase
from pyflightstream.script import Script, helpers

GUIDE = Path(__file__).parents[2] / "guide" / "pyflightstream_user_guide.tex"

#: ``<name>.<attribute>``, in listings and in prose (where LaTeX
#: escapes the underscore as ``\_``). A quote or a path separator
#: before the word means a file name such as ``"case.txt"``, not an
#: attribute access.
ATTRIBUTE = r"""(?<!["'/\\])\b{name}\.([A-Za-z_][A-Za-z0-9_]*(?:\\_[A-Za-z0-9_]*)*)"""

#: ``from pyflightstream.<module> import a, b`` inside a listing, with
#: the parenthesized continuation form the campaign slide uses.
IMPORT = re.compile(r"from\s+(pyflightstream[A-Za-z0-9_.]*)\s+import\s+(?:\(([^)]*)\)|([^\n(]+))")

#: One ``\code{...}`` span, allowing the escaped braces the guide uses
#: for placeholders such as ``loads\_\{point\}.txt``.
CODE_SPAN = re.compile(r"\\code\{((?:[^{}]|\\[{}])*)\}")

#: A class name, as the guide writes one: one or more capitalized groups,
#: each carrying a lowercase letter. The lowercase letter is what keeps
#: ``CP``, ``ENABLE`` and ``DISABLE`` out; they are solver command words
#: and API-constant fragments, not classes, and admitting them would put
#: three names into the floor that no module is expected to resolve.
CLASS_SHAPE = re.compile(r"^(?:[A-Z][a-z][A-Za-z0-9]*)+$")

#: Modules a guide class name may live in, beyond the ones the guide's
#: own import lines name. ``WingSpec`` resolves only in ``qa.geometry``
#: and ``BrokenCommandError`` is taught in prose with no import line, so
#: its declaring module is named rather than relying on the re-export.
CLASS_HOME_MODULES = ("pyflightstream.exceptions", "pyflightstream.qa.geometry")

#: File-extension tokens. ``campaign.toml`` written without quotes is a
#: FILE NAME in running prose, not an attribute read: the ATTRIBUTE
#: look-behind only catches the quoted and path-prefixed forms, and the
#: guide's two bare occurrences would otherwise be reported as a missing
#: attribute on ``Campaign``. Filtered in ONE place, so the guard and
#: the floors below cannot disagree about what was measured.
#:
#: The residual is stated rather than hidden: an attribute whose NAME is
#: one of these seven tokens is invisible to the guard. Measured
#: 2026-08-18 by teaching ``script.json`` in the guide, which the module
#: does not report. No object in ``TAUGHT_OBJECTS`` has such a field
#: today, and of the 75 raw hits the four objects carry only the two
#: ``campaign.toml`` occurrences are dropped, leaving 73.
FILE_EXTENSIONS = frozenset({"toml", "txt", "json", "csv", "fs", "py", "tex"})

#: Objects the guide hands the reader, and what they are. ``workspace``
#: and ``record`` are deliberately absent: they carry no dotted hits at
#: all, and the class half below is what covers them.
TAUGHT_OBJECTS = {
    "case": SimCase,
    "helpers": helpers,
    "script": Script,
    "campaign": Campaign,
}


def guide_text() -> str:
    assert GUIDE.is_file(), f"the user guide is not at {GUIDE}; update this guard's path"
    return GUIDE.read_text(encoding="utf-8")


def guide_attribute_hits(name: str) -> list[str]:
    """Return every attribute the guide reads off ``name``, one per hit.

    Parameters
    ----------
    name : str
        The variable the guide binds the object to, for example
        ``"case"`` or ``"campaign"``.

    Returns
    -------
    list of str
        The attribute names, in file order and with repeats kept, with
        the LaTeX underscore escape undone and file-extension tokens
        dropped (see :data:`FILE_EXTENSIONS`). Repeats are kept because
        the floors in
        :func:`test_the_checks_actually_find_the_samples` count hits,
        and a floor that counted distinct names would measure something
        the guard above does not read.
    """
    pattern = re.compile(ATTRIBUTE.format(name=name))
    hits = [match.replace("\\_", "_") for match in pattern.findall(guide_text())]
    return [attribute for attribute in hits if attribute not in FILE_EXTENSIONS]


def guide_attributes(name: str) -> set[str]:
    """Return every attribute the guide reads off ``name``."""
    return set(guide_attribute_hits(name))


def guide_class_names() -> set[str]:
    """Return every class name the guide names in a ``\\code{}`` span.

    Returns
    -------
    set of str
        The distinct spans of class shape (:data:`CLASS_SHAPE`), with
        the LaTeX underscore escape undone. Measured 13 on 2026-08-18.
    """
    found: set[str] = set()
    for span in CODE_SPAN.findall(guide_text()):
        candidate = span.replace("\\_", "_")
        if candidate.isidentifier() and CLASS_SHAPE.match(candidate):
            found.add(candidate)
    return found


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
        if isinstance(target, type) and issubclass(target, BaseModel):
            known |= set(target.model_fields)
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


def test_every_class_the_guide_names_resolves():
    """Every class name in a ``\\code{}`` span is importable somewhere.

    This is the half that covers ``workspace`` and ``record``. The guide
    teaches both by naming ``CampaignWorkspace`` and ``RunRecord`` in
    the object table and then showing listings that bind them to local
    variables, so the dotted guard never sees them.

    Resolution is against the modules the guide's own import lines name
    plus :data:`CLASS_HOME_MODULES`, and NOT against the top-level
    package: measured 2026-08-18, not one of the 13 resolves on
    ``pyflightstream`` itself, so ``hasattr(pyflightstream, name)``
    would report all 13 as broken.
    """
    modules = [import_module(name) for name in CLASS_HOME_MODULES]
    for module_name in sorted({module for module, _ in guide_imports()}):
        try:
            modules.append(import_module(module_name))
        except ImportError:
            continue  # already reported, by name, by the import guard above
    unresolved = sorted(
        name for name in guide_class_names() if not any(hasattr(module, name) for module in modules)
    )
    assert not unresolved, (
        f"the user guide names the classes {unresolved}, which resolve in none of "
        f"{sorted(module.__name__ for module in modules)}; a reader who looks one up "
        "finds nothing. Rename it in the guide, or name the module it moved to"
    )


def test_the_checks_find_attributes_imports_and_classes(tmp_path, monkeypatch):
    """Exercise the extractors without pinning the guide's sample inventory."""
    sample = tmp_path / "guide.tex"
    sample.write_text(
        "case.geometry helpers.new_simulation campaign.name campaign.toml\n"
        "from pyflightstream.cases import Campaign, SimCase\n"
        r"\code{CampaignWorkspace} \code{CP} \code{RunRecord}",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "GUIDE", sample)
    assert guide_attribute_hits("case") == ["geometry"]
    assert guide_attribute_hits("helpers") == ["new_simulation"]
    assert guide_attribute_hits("campaign") == ["name"]
    assert guide_imports() == [
        ("pyflightstream.cases", "Campaign"),
        ("pyflightstream.cases", "SimCase"),
    ]
    assert guide_class_names() == {"CampaignWorkspace", "RunRecord"}


def test_the_checks_actually_find_the_samples():
    """Non-vacuity floors (F-865): an extractor that finds nothing proves nothing.

    Measured on the committed guide: 12, 36 and 27 attribute hits for ``case``,
    ``helpers`` and ``script``, 16 import claims and 13 class names. The floors sit a
    little below, so an edited guide may shrink but a broken pattern cannot pass.
    """
    floors = {"case": 10, "helpers": 30, "script": 20}
    found = {name: len(guide_attribute_hits(name)) for name in floors}
    assert all(found[name] >= floor for name, floor in floors.items()), found
    assert len(guide_imports()) >= 14
    assert len(guide_class_names()) >= 11
