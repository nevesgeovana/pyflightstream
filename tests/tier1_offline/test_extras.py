"""Tier 1: every optional extra refuses the same way, with a remedy that works.

REV-002 finding PYFS-025, the typed half. Three code paths gated on an
optional extra raised three different exception types with three
hand-written remedy strings, so a caller who wanted to handle "an extra
is missing" had to know all three, and nothing checked that the
remedies were spelled the way the packaging spells them.

The license half of the same finding is documentary and lives in
`reports/RPT-016`, with `test_every_extra_has_a_license_card` below
holding it to the extras that actually exist.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import pytest

from pyflightstream.extras import EXTRAS, MissingExtraError, missing_extra
from tests.tier1_offline._docs_site import requirements_text

REPO = Path(__file__).resolve().parents[2]

#: Extras that gate no runtime code path, so no user can reach a
#: refusal for them. Named rather than filtered silently: `dev` is a
#: contributor's install, and a future extra that belongs here should
#: be a deliberate entry rather than an omission nobody notices.
NOT_USER_FACING = {"dev"}


def _declared_extras() -> dict[str, list[str]]:
    with open(REPO / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["optional-dependencies"]


def _pyproject_runtime_dependencies() -> list[str]:
    """The distributions every install of this package carries."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        return tomllib.load(handle)["project"]["dependencies"]


def test_the_extras_table_matches_the_packaging():
    """`EXTRAS` and pyproject are one fact.

    An extra renamed in packaging and not here would build an install
    command that fails, which is worse than no message: it sends the
    reader away confident.
    """
    declared = set(_declared_extras()) - NOT_USER_FACING
    assert declared, (
        "pyproject declares no user-facing extra, so the three parametrized "
        "tests below would run over nothing and pass"
    )
    assert set(EXTRAS) == declared, (
        f"pyflightstream.extras.EXTRAS names {sorted(EXTRAS)} and pyproject "
        f"declares {sorted(declared)} (ignoring {sorted(NOT_USER_FACING)})"
    )


@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_each_extra_names_the_distributions_it_installs(extra):
    """The table says what arrives, so a refusal can name the right package."""
    declared = _declared_extras()[extra]
    # pyproject entries may carry a version bound; compare on the name.
    names = {re.split(r"[<>=!~\[]", spec)[0].strip().lower() for spec in declared}
    assert {package.lower() for package in EXTRAS[extra]} == names, (
        f"extra [{extra}] installs {sorted(names)} but EXTRAS records {sorted(EXTRAS[extra])}"
    )


@pytest.mark.requirement("NFR-25")
@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_the_refusal_carries_the_exact_install_command(extra):
    """One type, and a remedy composed from the extra's own name.

    This is the assertion PYFS-025 owes, parametrized per extra as it
    asks. The remedy is built rather than written, so it cannot drift
    from the name that makes it work.
    """
    error = missing_extra(extra, package="somepkg", purpose="the thing")
    assert isinstance(error, MissingExtraError)
    assert isinstance(error, ImportError)
    assert error.extra == extra
    assert error.remedy == f"pip install pyflightstream[{extra}]"
    assert error.remedy in str(error)
    assert "somepkg" in str(error)
    assert "the thing" in str(error)


def test_a_refusal_cannot_name_an_extra_that_does_not_exist():
    """The failure mode the composed remedy exists to prevent."""
    with pytest.raises(ValueError, match="not an extra of this package"):
        missing_extra("geometry", package="scipy", purpose="the gate")
    # The control: the real name is accepted, so the refusal is about the
    # value and not about the check being unconditional.
    assert missing_extra("geom", package="scipy", purpose="the gate").extra == "geom"


@pytest.mark.requirement("NFR-25")
def test_no_extra_installs_a_distribution_the_base_install_already_gives():
    """An extra and the runtime set must not name the same distribution.

    The structural half of the trimesh promotion of 2026-08-19 (DD-27).
    A distribution in BOTH lists is not a redundancy: every refusal built
    from :data:`EXTRAS` says "install this extra to obtain that package",
    and for a package the base install already provides that sentence
    sends the reader to a command which changes nothing and leaves them
    hunting for a dependency that is not the problem. This is the exact
    shape the extras module was written to make impossible, one level up
    from the one it already checks.

    It also holds the promotion itself: putting trimesh back under
    ``[geom]`` while leaving it in ``dependencies`` fails here, and so
    does the reverse of the second half, promoting a distribution and
    forgetting to take it out of its extra.
    """
    runtime = {
        re.split(r"[<>=!~\[]", spec)[0].strip().lower()
        for spec in _pyproject_runtime_dependencies()
    }
    assert runtime, "the runtime dependency list is empty; the comparison is vacuous"
    declared = _declared_extras()
    both = sorted(
        f"{name} (in [{extra}])"
        for extra, specs in declared.items()
        for name in {re.split(r"[<>=!~\[]", spec)[0].strip().lower() for spec in specs}
        if name in runtime
    )
    assert not both, (
        f"these distributions are BOTH a runtime dependency and part of an extra: "
        f"{both}. Every refusal MissingExtraError builds tells the reader to install "
        "the extra in order to obtain the package, and for one the base install "
        "already carries, that command changes nothing"
    )


def test_the_converters_pypdf_accessor_refuses_in_the_shared_shape(monkeypatch):
    """The one gated path added on 2026-08-10, asserted rather than assumed.

    ``scripts/chm_to_pdf._pypdf`` was written mirroring
    ``probes.geometry._trimesh``, which is GONE since 2026-08-19: trimesh
    became a runtime dependency and its accessor moved to
    :mod:`pyflightstream._mesh` with no refusal to make, so this is now
    the accessor of that shape whose refusal is exercised rather than the
    second of two. Without this, a wrong extra name in the accessor would
    raise ``UnknownExtraError`` instead of the didactic refusal, and
    would ship silently, because the branch only runs where pypdf is
    absent and no environment here is.
    """
    # Loaded by path rather than by putting scripts/ on sys.path: a
    # permanently prepended directory shadows later imports for the rest
    # of the session, which this workspace already has an incident about.
    spec = importlib.util.spec_from_file_location(
        "chm_to_pdf_under_test", REPO / "scripts" / "chm_to_pdf.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(MissingExtraError) as caught:
        module._pypdf()
    assert caught.value.extra == "manual"
    assert caught.value.package == "pypdf"
    assert "pip install pyflightstream[manual]" in str(caught.value)


def _remedies_in_raises(source: str) -> list[int]:
    """Line numbers of raises whose literals write an install remedy by hand.

    Takes source text rather than a path, so the scan itself can be
    driven with synthetic input; a negative assertion over the tree
    cannot otherwise be told from a scan that finds nothing.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Raise):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                if "pip install pyflightstream[" in inner.value:
                    found.append(node.lineno)
    return sorted(set(found))


def test_every_gated_path_raises_the_shared_type():
    """No path may go back to a bare ImportError with a typed-out remedy.

    Read from the source rather than by triggering each path, because
    triggering them needs the extras to be ABSENT and this suite runs
    with them installed. What it pins is the invariant that made the
    finding: an install remedy appears in this package only inside the
    one class that builds it.
    """
    # The scan finds what it is looking for. Without this the whole test
    # is satisfied by a wrong rglob root or an over-broad skip, which is
    # the shape a negative assertion always has.
    hand_written = 'raise ImportError("needs it: pip install pyflightstream[fsi]")'
    assert _remedies_in_raises(hand_written) == [1], "the scan cannot find a remedy"
    # And it does NOT fire on the same string in a docstring, which is the
    # case an earlier line-based version got wrong.
    in_prose = '"""Install with pip install pyflightstream[geom]."""\nx = 1\n'
    assert _remedies_in_raises(in_prose) == [], "the scan flags documentation"

    offenders = []
    # `scripts/` joined the scan on 2026-08-10, because the class this
    # guard exists to prevent had a live instance there and the guard
    # could not see it: scripts/chm_to_pdf.py typed out its own install
    # command for the [manual] extra. A tree that gates on an extra is a
    # tree this must reach.
    scanned = [*sorted((REPO / "src").rglob("*.py")), *sorted((REPO / "scripts").rglob("*.py"))]
    for path in scanned:
        if path.name == "extras.py":
            continue  # the one home of the string
        # Only the literals INSIDE a raise. A module docstring or a
        # comment naming the install command is documentation and is
        # meant to stay: probes/geometry.py's own top-docstring does
        # exactly that, and an earlier version of this guard flagged it,
        # which would have taught the reader to delete the prose instead
        # of the duplication.
        rel = path.relative_to(REPO).as_posix()
        offenders += [
            f"{rel}:{line}" for line in _remedies_in_raises(path.read_text(encoding="utf-8"))
        ]
    assert not offenders, (
        "these raises write an install remedy by hand instead of using "
        "MissingExtraError, which is how three paths came to print three "
        f"different strings: {sorted(set(offenders))}"
    )


def test_the_geometry_gate_is_still_its_own_catchable_name():
    """The one extra whose absence is recoverable keeps a name of its own.

    A caller can continue without culling, so singling the geometry gate
    out is a real need; it is a SUBCLASS so `except MissingExtraError`
    catches it too.
    """
    from pyflightstream.probes.geometry import GeometryEngineMissingError

    assert issubclass(GeometryEngineMissingError, MissingExtraError)
    assert issubclass(GeometryEngineMissingError, ImportError)


def test_a_missing_spatial_index_names_the_index_and_not_the_reader(monkeypatch):
    """The re-pointed refusal of the geometry gate (DD-27 section 5).

    Both queries the gate makes are searches through scipy's kd-tree and
    rtree's bounds tree, and both used to refuse by naming trimesh. That
    was right while one extra installed all three and became wrong the
    day trimesh was promoted: from then on the only way to reach these
    branches is with the reader present and the index absent, so a
    refusal naming the reader sends the reader to reinstall a
    distribution they already have.

    Driven with objects that raise ``ImportError`` where the index is
    reached, because the alternative is an environment with trimesh and
    without scipy, which no leg of this suite has. The containment arm
    is the one the promotion CREATED: before it, an installation could
    not carry the reader without the index.
    """
    import numpy as np
    import trimesh.proximity

    from pyflightstream.probes.geometry import _inside, _surface_distance

    class NoIndex:
        """A mesh whose containment search cannot reach its bounds tree."""

        def contains(self, points):
            raise ImportError("No module named 'rtree'")

    class NoKdTree:
        """trimesh's own placeholder shape: it raises when it is USED."""

        def __init__(self, mesh):
            raise ImportError("No module named 'scipy'")

    monkeypatch.setattr(trimesh.proximity, "ProximityQuery", NoKdTree)

    points = np.zeros((1, 3))
    for call, arm in ((_inside, "containment"), (_surface_distance, "distance")):
        with pytest.raises(MissingExtraError) as caught:
            call(NoIndex(), points)
        assert caught.value.extra == "geom", arm
        assert caught.value.package.startswith("scipy and rtree"), (
            f"the {arm} refusal names {caught.value.package!r} as what is missing; "
            "after the promotion the missing thing is the spatial index, and naming "
            "the reader sends a reader to reinstall what they already have"
        )
        assert "pip install pyflightstream[geom]" in str(caught.value), arm
        assert isinstance(caught.value.__cause__, ImportError), (
            f"the {arm} refusal discarded the original ImportError, so a failure "
            "that is not a missing distribution is no longer diagnosable"
        )


@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_every_extra_has_a_license_card(extra):
    """NFR-02: evidence before adoption, and the cards must cover the set.

    Measured at PYFS-025: the runtime dependencies had no card at all
    and `[plot]` had none either, while `[fsi]` and `[geom]` did. The
    cards are prose, so this checks coverage rather than content: every
    extra's distributions are named somewhere under `reports/`.
    """
    cards = (REPO / "docs/install.md").read_text(encoding="utf-8").lower()
    missing = [package for package in EXTRAS[extra] if package.lower() not in cards]
    assert not missing, (
        f"extra [{extra}] installs {missing} and no committed report under "
        "reports/ names them. NFR-02 wants a license-evidence card before "
        "adoption, not after"
    )


#: A markdown heading of level two or deeper. Level one is the report's
#: own title, which names a topic rather than a distribution, so a card
#: cannot be claimed by the line at the top of the file.
_CARD_HEADING = re.compile(r"^#{2,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _normalised(name: str) -> str:
    """PEP 503 normalisation, so `pytest-cov` and `pytest_cov` are one name."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def card_headings(texts) -> set[str]:
    """Normalised heading texts of every card section in the given documents.

    Takes TEXTS rather than paths, for the same reason
    :func:`_remedies_in_raises` above does: a coverage assertion that can
    only be run over the real tree cannot be told apart from one that
    matches everything, and the difference between this and a substring
    sweep is the whole point of the check below.

    Parameters
    ----------
    texts : iterable of str
        Markdown documents.

    Returns
    -------
    set of str
        One entry per level-two-or-deeper heading, normalised.
    """
    return {_normalised(heading) for text in texts for heading in _CARD_HEADING.findall(text)}


def _dev_distributions() -> list[str]:
    """Distribution names of the `dev` extra, in pyproject order."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        declared = tomllib.load(handle)["project"]["optional-dependencies"]["dev"]
    return [re.split(r"[<>=!~\[]", spec)[0].strip() for spec in declared]


@pytest.mark.requirement("NFR-02")
def test_every_runtime_dependency_has_a_license_card():
    """The set that reaches every user, which is the one that had no card."""
    with open(REPO / "pyproject.toml", "rb") as handle:
        runtime = tomllib.load(handle)["project"]["dependencies"]
    names = [re.split(r"[<>=!~\[]", spec)[0].strip() for spec in runtime]
    assert names, "the runtime dependency list is empty; the scan is broken"
    cards = (REPO / "docs/install.md").read_text(encoding="utf-8").lower()
    missing = [name for name in names if name.lower() not in cards]
    assert not missing, (
        f"runtime dependencies {missing} have no license-evidence card under "
        "reports/. These reach every user of the package"
    )


def test_the_requirement_that_calls_itself_the_home_of_record_names_the_shipped_set():
    """NFR-06 names exactly the shipped runtime dependency set."""
    from tests.tier1_offline._docs_site import requirement_rows

    srs = requirements_text(REPO)
    statement = requirement_rows(srs)["NFR-06"][4]
    stated = {name.lower() for name in re.findall(r"`([^`]+)`", statement)}
    assert stated, "NFR-06 must explicitly name its runtime dependencies"
    shipped = {
        re.split(r"[<>=!~\[ ]", entry, maxsplit=1)[0].strip().lower()
        for entry in _pyproject_runtime_dependencies()
    }
    assert stated == shipped, (
        "NFR-06 calls itself the single home of record for the runtime dependency "
        f"set, and it disagrees with what ships.\n  stated and not shipped: "
        f"{sorted(stated - shipped)}\n  shipped and not stated: {sorted(shipped - stated)}\n"
        "Amend the requirement in the same commit as the packaging change, with the "
        "reason and the measurement, which is what home of record costs."
    )


@pytest.mark.requirement("NFR-25")
def test_workbook_creation_uses_the_shared_missing_extra(tmp_path, monkeypatch):
    from pyflightstream.workspace.excel import create_workbook

    monkeypatch.setitem(sys.modules, "xlsxwriter", None)
    target = tmp_path / "not-created" / "matrix.xlsx"
    with pytest.raises(MissingExtraError) as caught:
        create_workbook(target, workspace=tmp_path)
    assert caught.value.extra == "excel"
    assert caught.value.package == "XlsxWriter"
    assert caught.value.remedy == "pip install pyflightstream[excel]"
    assert isinstance(caught.value.__cause__, ImportError)
    assert not target.parent.exists()


def test_f_1281_missing_extra_error_survives_pickling():
    """F-1281 X-F-1133: the keyword-only constructor must not break a round trip."""
    import pickle

    error = MissingExtraError(extra="plot", package="matplotlib", purpose="Drawing")
    again = pickle.loads(pickle.dumps(error))
    assert isinstance(again, MissingExtraError)
    assert (again.extra, again.package, again.purpose) == ("plot", "matplotlib", "Drawing")
    assert str(again) == str(error)
