"""Tier 1: public claims are checked against the thing they describe.

REV010-017 and REV010-018. The review found six places where the
documentation and the code disagreed, and the pattern behind all six is
that a claim and its subject live in different files with nothing
comparing them. Prose review catches that only while somebody
remembers to look.

These guards are deliberately narrow. They check claims whose subject
is mechanically readable (a module that does or does not import, an
example file that does or does not exist, a sentence that must not
contradict a sibling document). They do not attempt to validate prose
in general, which would be a guard whose own correctness nobody could
establish.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
EXAMPLES = REPO / "examples"


def test_the_removed_shim_is_not_described_as_surviving() -> None:
    """REV010-017. `pyflightstream.files` was removed at v0.4.0, and three
    surfaces went on saying it survives as a deprecation shim."""
    with pytest.raises(ImportError):
        __import__("pyflightstream.files")

    survives = re.compile(r"files.{0,40}(survives|re-exports)", re.I | re.S)
    for path in (
        REPO / "CLAUDE.md",
        REPO / "src/pyflightstream/__init__.py",
        REPO / "src/pyflightstream/workspace/__init__.py",
    ):
        text = path.read_text(encoding="utf-8")
        assert not survives.search(text), (
            f"{path.name} still describes the files shim as surviving, and importing "
            "it raises ImportError. A removal announced in a released changelog is a "
            "promise; a document that contradicts it tells a reader the opposite."
        )


def test_the_readme_status_line_names_the_version_being_released() -> None:
    """The README IS the PyPI project page, so its status line ships.

    Caught by the release audit at the v0.4.0 tag, by two passes
    independently, and it had survived five review rounds because every
    one of them read the DIFF and this line was not in it. The artifact
    would have announced v0.3.0 as the current release from inside the
    v0.4.0 page, while ``docs/index.md`` in the same tree said v0.4.0.

    Anchored on the CHANGELOG's newest RELEASED heading rather than on a
    literal, so it moves itself at the next release instead of becoming
    the next stale claim.

    Not on ``pyproject.toml``, and the first version of this guard got
    that wrong on the day it was written. During a release commit the two
    agree, which is why the error was invisible; in a development window
    pyproject carries ``.dev0`` of the version being BUILT while this
    sentence is about what is PUBLIC. Anchoring there made the guard
    demand that the README announce a release that does not exist yet.
    The changelog's newest released heading is the single home of "what
    is on PyPI".
    """
    released = re.findall(
        r"^## \[(\d+\.\d+\.\d+)\]", (REPO / "CHANGELOG.md").read_text(encoding="utf-8"), re.M
    )
    assert released, "the changelog states no released version, so this guard reads nothing"
    version = released[0]
    status = [
        line
        for line in README.read_text(encoding="utf-8").splitlines()
        if line.startswith("Status:")
    ]
    assert len(status) == 1, f"expected one README status line, found {len(status)}"
    assert version in status[0], (
        f"the README status line is {status[0]!r} and the newest released version in "
        f"CHANGELOG.md is {version}. That line is rendered by PyPI as the project "
        "page, so a stale one ships as the release's own front page."
    )


def _readme_named_examples() -> set[str]:
    """Example file names the README points a reader at."""
    return set(re.findall(r"examples/([\w.]+\.py)", README.read_text(encoding="utf-8")))


def test_every_example_the_readme_names_exists() -> None:
    """REV010-017. The README promised `examples/` reached "coupled
    aeroelastic runs" and no such example exists: the two FSI-adjacent
    ones are a static deflection and a modal Campbell diagram."""
    named = _readme_named_examples()
    assert named, "the README names no example files; this guard would pass vacuously"
    missing = sorted(name for name in named if not (EXAMPLES / name).is_file())
    assert not missing, (
        f"the README points at examples that do not exist: {missing}. Either add "
        "the example or stop claiming it."
    )


def test_the_readme_does_not_claim_a_coupled_aeroelastic_example() -> None:
    """The specific claim the review measured, kept as its own assertion so
    that rewording the sentence cannot quietly restore it."""
    coupled = [
        path.name
        for path in EXAMPLES.glob("*.py")
        if "coupling_step" in path.read_text(encoding="utf-8")
    ]
    text = README.read_text(encoding="utf-8")
    claims_coupled = re.search(r"examples.{0,120}coupled aeroelastic runs", text, re.S | re.I)
    assert not (claims_coupled and not coupled), (
        "the README says the worked examples reach coupled aeroelastic runs, and no "
        "example calls the coupling driver. Ship the example, or describe what is "
        "actually in examples/."
    )


def test_the_readme_states_the_experimental_boundary() -> None:
    """The author's decision of 2026-08-03: FSI and probe paths are
    experimental behind an EXPLICIT boundary. An unstated boundary is the
    state the review found."""
    text = README.read_text(encoding="utf-8")
    assert "Capability status" in text
    for capability in ("FSI coupled driver", "Rotary two-way coupling", "probe surveys"):
        assert capability.lower() in text.lower(), capability
    assert "experimental" in text.lower()


def test_the_attestation_claim_agrees_with_the_hook_that_implements_it() -> None:
    """REV010-018. The hook's docstring says the attestation does NOT prove
    the reviewer agents ran; the skill called it "the mechanical proof that
    the real agents ran". Two documents, one mechanism, opposite claims."""

    # Whitespace-normalized: both files are hard-wrapped prose, so a phrase
    # this guard looks for is routinely split across a line break. Searching
    # the raw text would make the guard depend on where the wrap happened,
    # which is the difference between a guard and a guard-shaped thing.
    def flat(path: str) -> str:
        return " ".join((REPO / path).read_text(encoding="utf-8").split())

    hook = flat(".claude/hooks/role_review_gate.py")
    skill = flat(".claude/skills/role-review/SKILL.md")

    # The hook is the accurate one, so its disclaimer is the anchor.
    assert "does NOT" in hook and "prove the reviewer agents ran" in hook, (
        "the hook no longer states the limit of what it enforces; that sentence is "
        "what this guard compares the skill against"
    )
    assert "the mechanical proof that the real agents ran" not in skill, (
        "the role-review skill claims the attestation proves the agents ran, which "
        "the hook that implements it explicitly refuses to claim about itself"
    )
    assert "NOT proof" in skill or "not proof" in skill, (
        "the skill should state what the attestation is not, since a reader who "
        "only reads the skill would otherwise infer the wider claim"
    )


def test_the_index_generator_documents_the_fields_it_emits() -> None:
    """REV010-017. The generator's docstring listed three fields while six
    were being written. A hand-maintained description of a generated
    artifact drifts exactly the way the hand-maintained list it replaced
    did, which the docstring itself says a few lines above."""
    import json

    index = json.loads((REPO / "reports/requirements-index.json").read_text(encoding="utf-8"))
    doc = (REPO / "scripts/gen_requirements_index.py").read_text(encoding="utf-8")
    header = doc.split('"""')[1]

    emitted = set(index["requirements"][0])
    documented = {name for name in emitted if f"``{name}``" in header}
    assert emitted == documented, (
        f"the generator emits {sorted(emitted)} per requirement and its docstring "
        f"documents {sorted(documented)}. The undocumented fields are "
        f"{sorted(emitted - documented)}."
    )
    for key in index:
        assert f"``{key}``" in header, f"top-level key {key!r} is undocumented"


# --- one claim, six homes -------------------------------------------------
#
# Measured rather than anticipated. During the v0.4.0 release the same
# sentence about the exception hierarchy was found false and corrected FIVE
# times, in five different homes, over three days: the SRS requirement, the
# release note, the base exception's docstring, the catalog module's
# docstring, the House conventions register, and finally the ratchet file
# that the others had by then started naming as the single home of the
# residual. Each correction was real. Each time, a home nobody had
# enumerated kept the old wording and the next review round found it.
#
# The defect is not that any one was written carelessly. It is that a claim
# living in six places is swept BY HAND, so the sweep is complete only if
# whoever does it already knows every home. That assumption is what these
# three guards remove.
#
# SCOPE, stated because a guard whose reach is assumed is the other thing
# this release kept finding. They cannot read a sentence and decide whether
# it is true. They assert that every home listed below carries the
# qualifiers the claim needs and none of the forms it was found in while it
# was false. A NEW home is invisible until it is added here. That is a real
# limit and the reason the list is written out rather than discovered:
# adding a public home for this claim is a deliberate act, and adding it
# here is part of that act.


def _claim_homes() -> dict[str, str]:
    """Every public home that says what the package base exception catches."""
    import pyflightstream.exceptions as exceptions_module
    from pyflightstream.exceptions import PyflightstreamError
    from pyflightstream.reference import CONVENTIONS

    return {
        "PyflightstreamError.__doc__": PyflightstreamError.__doc__ or "",
        "pyflightstream.exceptions.__doc__": exceptions_module.__doc__ or "",
        "reference.CONVENTIONS 'Refusals teach'": next(
            (body for title, body in CONVENTIONS if title == "Refusals teach"), ""
        ),
    }


#: Wordings the claim was live in while it was FALSE. Every one of these
#: was taken out of git (``git show <sha>:<path>``) rather than typed
#: from memory, and that is not a detail: the first version of this list
#: WAS typed from memory, and a mutation restoring one home's real
#: pre-fix sentence passed it, because that home said "everything the
#: package raises" where the list guessed "everything pyflightstream
#: raises". A denylist assembled from recollection reproduces the exact
#: defect this file exists to stop.
FALSE_FORMS = (
    # src/pyflightstream/_errors.py before 08050c6
    "base of every exception this package raises",
    "catch everything pyflightstream raises",
    # src/pyflightstream/exceptions.py before 08050c6
    "catches everything the package raises",
    # src/pyflightstream/reference.py before be70e8c
    "clause catches the package",
    # CHANGELOG.md before 08050c6, kept because the wording can migrate
    # back into a docstring from a release note
    "every exception the package raises now descends from it",
)

#: The structural half of the same rule, and the reason the list above is
#: not the whole guard. Any home that puts "the package" where the object
#: of the catch belongs is making the universal claim whatever words
#: surround it, so the pairing is refused rather than each phrasing.
FALSE_PAIRINGS = (("catch", "the package raises"), ("catches", "the package"))

#: What a truthful statement has to carry. Not style: without the first a
#: reader takes the base for universal, and without the others the
#: residual has no address and no stated reach.
REQUIRED_TOKENS = {
    "the catalog qualifier": ("catalogued", "catalog"),
    "the ratchet that holds the residual": ("ratchet",),
    # Lower case, because every home is matched against a lowered copy.
    "the requirement stating the walk's reach": ("fr-39",),
}


def test_this_guard_reads_the_homes_it_names() -> None:
    """Non-vacuity, and not a formality here.

    Two homes are read through an import and the third by looking up a
    title in a tuple of pairs, so a renamed convention entry yields the
    empty string and every assertion below would pass over nothing. That
    is the exact shape of guard this release spent five rounds finding.
    """
    homes = _claim_homes()
    assert len(homes) == 3, "a home was added or removed without updating this guard"
    for home, text in homes.items():
        assert len(text) > 200, (
            f"{home} yielded {len(text)} characters, too short to be the passage this "
            "guard is written for; the lookup has probably stopped resolving"
        )


def test_no_home_claims_the_base_catches_the_whole_package() -> None:
    """The universal five review rounds found false, in any of its wordings."""
    offenders = []
    for home, text in _claim_homes().items():
        lowered = " ".join(text.lower().split())
        offenders += [f"{home} says {form!r}" for form in FALSE_FORMS if form in lowered]
        for verb, object_ in FALSE_PAIRINGS:
            # Within one sentence of each other, so an unrelated later
            # paragraph mentioning the package cannot trip it.
            for match in re.finditer(re.escape(verb), lowered):
                window = lowered[match.end() : match.end() + 60]
                if object_ in window:
                    offenders.append(f"{home} pairs {verb!r} with {object_!r}")
    assert not offenders, (
        "\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nThe base catches the CATALOG. A residual of bare standard-library "
        "raises survives outside it, so the unqualified form tells a reader that one "
        "except clause suffices when it does not."
    )


def test_every_home_carries_the_qualifiers_and_the_same_residual_bases() -> None:
    """A home may not state the claim without its scope, its address and its set.

    The last of the three is the divergence that survived the other two:
    the correction naming ``TypeError`` and ``RuntimeError`` reached two
    homes and not the third, inside the very commit that corrected the
    universal in all three.
    """
    offenders = []
    for home, text in _claim_homes().items():
        lowered = text.lower()
        for what, tokens in REQUIRED_TOKENS.items():
            if not any(token in lowered for token in tokens):
                offenders.append(f"{home} does not name {what}")
        missing = [
            base for base in ("valueerror", "typeerror", "runtimeerror") if base not in lowered
        ]
        if missing:
            offenders.append(f"{home} does not name the residual base {', '.join(missing)}")
    assert not offenders, (
        "\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nEvery home states the same scope, the same address for the residual and "
        "the same set of bases that covers it, or they drift. They drifted five times "
        "during the v0.4.0 release."
    )


#: Prose that a reader may act on, as opposed to a dated record of what
#: once happened. CHANGELOG entries and everything under reports/ are
#: excluded deliberately: a released section and a committed report state
#: what was true on their date, and correcting one would be rewriting
#: history rather than fixing a claim.
_LIVE_PROSE = (
    "README.md",
    "CONTRIBUTING.md",
    "docs",
    "guide",
    "examples",
    "src",
)


def _live_prose_files() -> list[Path]:
    """Tracked files whose text a reader may act on today."""
    root = Path(__file__).resolve().parent.parent
    tracked = subprocess.run(
        ["git", "ls-files", *_LIVE_PROSE],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    suffixes = {".md", ".py", ".tex", ".yaml", ".yml", ".txt"}
    return [root / name for name in tracked if Path(name).suffix in suffixes]


def test_this_guard_reads_a_population_it_could_fail_on() -> None:
    """Non-vacuity: a broken file list would make the sweep below pass."""
    files = _live_prose_files()
    assert len(files) > 50, f"only {len(files)} live prose files found; the listing broke"
    assert any(path.name == "pyflightstream_user_guide.tex" for path in files)
    assert any(path.name == "steady_polar.py" for path in files)


def test_no_live_prose_states_the_script_argument_with_two_dashes() -> None:
    """The spelling is a fact about builds and lives in ONE place.

    `pyflightstream.run.SCRIPT_ARGUMENT` is the home and
    `describe_invocation()` is how a report states it, but prose is not
    reached by either: the user guide and one example each announced the
    invocation in their own words, and both went on saying two dashes
    after the code stopped. A reader following the guide by hand on a
    25.x install would get the failure this release exists to remove,
    and would get it as a hang with a clean licence checkout, which is
    the least diagnosable form it takes.

    Two dashes work from 26.000 onward, so this is not a wrong command
    for most readers. It is a wrong command for exactly the readers with
    the oldest installs, who have the least recourse.
    """
    # Derived from the constant, never from yesterday's wrong spelling.
    # The first version forbade the literal `--script`, which catches the
    # 2026-08-09 defect and nothing after it: change SCRIPT_ARGUMENT
    # again and every page still printing the old value passes, which is
    # the same drift one turn later.
    from pyflightstream.run import SCRIPT_ARGUMENT

    # One file may write another spelling, and only one: the home of the
    # constant, where the difference between them is the subject.
    # Anywhere else it is an instruction, and a reader follows it.
    home = Path("src/pyflightstream/run/__init__.py")
    written = re.compile(r"-{1,2}script\w*")
    offenders = []
    for path in _live_prose_files():
        if path.as_posix().endswith(home.as_posix()):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for found in written.findall(line):
                if found != SCRIPT_ARGUMENT:
                    offenders.append(f"{path.name}:{number}: {found} in {line.strip()[:80]}")
    assert not offenders, (
        "\n  " + "\n  ".join(offenders) + f"\n\nThe script argument is {SCRIPT_ARGUMENT!r} "
        "(pyflightstream.run.SCRIPT_ARGUMENT). Live prose states the current value or "
        "does not state one; a page carrying a spelling the package no longer passes "
        "teaches a reader a command line that hangs on the builds it is wrong for, "
        "with a clean licence checkout and an empty log (RPT-023)."
    )


def test_the_home_of_the_constant_still_explains_the_other_spelling() -> None:
    """The one exemption above must be earning itself.

    `run/__init__.py` is allowed to write the two-dash form because it
    is where the difference is explained. If that explanation is ever
    deleted, the exemption becomes a hole rather than a carve-out, and
    the file could quietly go back to instructing readers wrongly.
    """
    home = Path(__file__).resolve().parents[1] / "src" / "pyflightstream" / "run" / "__init__.py"
    text = home.read_text(encoding="utf-8")
    assert "--script" in text, (
        "the constant's home no longer discusses the two-dash spelling, so the "
        "exemption in the guard above protects nothing; drop the exemption"
    )
    assert "RPT-023" in text, "the explanation no longer cites the measurement behind it"


#: The prose surfaces a reader meets, which is where a hand-written
#: tally does its damage. Test modules are deliberately OUT: they are
#: full of version literals as fixtures and constructor arguments, and a
#: guard that flagged those would be edited away the first week.
_ALIAS_PROSE_GLOBS = (
    "README.md",
    "docs/**/*.md",
    "guide/*.tex",
    "src/**/*.py",
    "src/**/*.yaml",
    "examples/*.py",
)

#: Files whose SUBJECT is the history of these enumerations, so a
#: superseded tally inside one is the record rather than a claim.
_ALIAS_TALLY_HISTORY = {
    # Release history: every entry describes the tree on the day it was
    # written, and a rewritten changelog is a falsified record.
    "CHANGELOG.md",
    # The SRS revision history, whose 1.23.0 and 1.26.0 rows exist
    # precisely to record that an enumeration moved.
    "docs/srs/index.md",
}


#: Number words a tally is written with, plus bare digits. Small on
#: purpose: a family larger than this is a different conversation.
_COUNT_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)
_COUNTS = "|".join([*_COUNT_WORDS, r"\d+"])


def _count_value(token: str) -> int:
    """Read a tally token, word or digit, as a number."""
    lowered = token.lower()
    if lowered in _COUNT_WORDS:
        return _COUNT_WORDS.index(lowered) + 1
    return int(lowered)


def _alias_families() -> dict[str, tuple[str, ...]]:
    """Vendor names that identify more than one registered build."""
    from pyflightstream.versions import known_versions

    families: dict[str, list[str]] = {}
    for version in known_versions():
        families.setdefault(version.alias, []).append(version.canonical)
    return {alias: tuple(members) for alias, members in families.items() if len(members) > 1}


def _prose_units(text: str) -> list[str]:
    """Split prose into units a tally could live inside.

    MARKDOWN TABLE ROWS ARE DROPPED, and that is the rule this guard got
    wrong twice before it got it right. A table of registered builds
    holds one build per row and names the alias in a CELL, so its rows
    trip a naive reading twice over: joined, they read as one run-on
    passage naming several builds; separated, a row still carries its own
    alias cell beside a reference to some other build. Neither is a tally
    of the family, because a table cannot be one: it is a per-build
    record and it is exactly the surface a registration already has to
    move, since a build with no row fails a different guard.

    The cost is stated rather than hidden: a genuine tally written inside
    a table cell is invisible here.
    """
    units: list[str] = []
    for block in text.split("\n\n"):
        lines = block.splitlines()
        if any(line.lstrip().startswith("|") for line in lines):
            units.extend(line for line in lines if not line.lstrip().startswith("|"))
            continue
        units.extend(re.split(r"(?<=[.;:])\s", block))
    return units


def test_no_committed_page_writes_a_stale_tally_of_a_shared_vendor_name() -> None:
    """A hand-written list of the builds sharing an alias goes stale on
    every registration, and six of them did at once.

    Registering 26.123 falsified the same enumeration in the SRS
    requirement text, the generated conventions page, two version
    docstrings, the ordering authority's own header, the getting-started
    page and a shipped example, with the whole tier-1 currency suite
    green. Two of those six said in the same sentence that no tally
    appears there.

    The rule is narrow on purpose, because the general version flags
    correct prose: a unit that BOTH names the shared vendor name AND
    enumerates two or more of the builds carrying it must enumerate ALL
    of them. A sentence naming two builds for some other reason is
    untouched, and so is one that names the family without listing it,
    which is what the fix for those six was.

    THE SECOND ARM CATCHES THE WORD FORM, and it exists because the
    first arm did not: run as a mutation battery against the six real
    sites, four died and two survived, and both survivors wrote the tally
    as a COUNT rather than a list ("`\"26.12\"` names three", "the vendor
    name 26.12 names three builds"). A guard that catches four of six
    reads as coverage it does not have. The count is tied to a family by
    ADJACENCY: it must follow the alias within a short window, so a
    sentence naming two families keeps each count with its own alias.

    What neither arm covers, stated rather than left to be discovered: a
    tally inside a markdown table cell, a count separated from its alias
    by more than the window, and any file outside the prose globs.
    """
    families = _alias_families()
    assert families, (
        "no vendor alias names more than one registered build, so this guard "
        "asserts nothing. Say so and delete it rather than leaving it green"
    )

    walked = sorted(
        {
            path
            for pattern in _ALIAS_PROSE_GLOBS
            for path in REPO.glob(pattern)
            if path.is_file() and path.relative_to(REPO).as_posix() not in _ALIAS_TALLY_HISTORY
        }
    )
    assert len(walked) > 50, (
        f"the prose walk reached only {len(walked)} files, so a glob has stopped "
        "matching and this guard is reading almost nothing"
    )

    offenders = []
    for path in walked:
        relative = path.relative_to(REPO).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for alias, members in families.items():
            alias_pattern = re.escape(alias) + r"(?!\d)"
            if not re.search(alias_pattern, text):
                continue
            for unit in _prose_units(text):
                if not re.search(alias_pattern, unit):
                    continue
                flat = " ".join(unit.split())
                named = {m for m in members if re.search(re.escape(m) + r"(?!\d)", flat)}
                if len(named) >= 2 and named != set(members):
                    missing = sorted(set(members) - named)
                    offenders.append(
                        f"{relative}: a passage naming {alias} lists "
                        f"{', '.join(sorted(named))} and omits {', '.join(missing)}"
                    )
                    break
                counted = re.search(
                    alias_pattern + r"[^\w]{0,12}(?:\w+\s+){0,2}?names?\s+(" + _COUNTS + r")\b",
                    flat,
                )
                if counted and _count_value(counted.group(1)) != len(members):
                    offenders.append(
                        f"{relative}: a passage says {alias} names "
                        f"{counted.group(1)}, and it names {len(members)}"
                    )
                    break

    assert not offenders, (
        "these committed passages write a PARTIAL list of the builds sharing a "
        "vendor name, which is the enumeration that goes stale on every "
        "registration:\n  " + "\n  ".join(sorted(offenders)) + "\nName the family and "
        "let the refusal enumerate it, which is what the six corrected on "
        "2026-08-17 now do, or list every member"
    )


# --- the standards page states its own enforcement -------------------------
#
# ``docs/srs/standards.md`` is the page an outside reader uses to judge how
# much of this project's discipline is mechanical and how much is habit. Its
# Adopted table carried one prose column, so a row backed by a tier-1 test
# and a row backed by nobody's memory read the same. The three guards below
# hold the two claims that column now makes: that every adopted row names
# what enforces it, and that the row about role-based review names the hook
# that REFUSES a push rather than a routine somebody runs.
#
# SCOPE. They cannot read a cell and decide whether the named mechanism
# really enforces the practice; that judgement is the reviewer's. What they
# remove is the cheaper failure: a cell left empty, and a cell naming a path
# or a CI command the repository no longer holds.

STANDARDS = REPO / "docs/srs/standards.md"

#: Where a CI command in the "Enforced by" column has to appear verbatim.
#: A path is checked against the tree; a command has no such existence, so
#: it is checked against the files that actually run it. Without this arm a
#: command cell would be the one token kind nothing verifies.
_CI_HOMES = (".github/workflows/ci.yml", ".pre-commit-config.yaml")

#: The Adopted table's enforcement column, resolved by LABEL. A markdown
#: table makes no promise about column ORDER, so a guard that indexes by
#: position starts reading the reference column the day a column moves.
_ENFORCEMENT_COLUMN = "Enforced by"

#: The literal that says, deliberately, that nothing refuses a breach.
_CONVENTION = "convention"


def _markdown_table(text: str, heading: str) -> tuple[list[str], list[list[str]]]:
    """Header labels and body rows of the table under ``heading``.

    Parameters
    ----------
    text : str
        The whole markdown page.
    heading : str
        The section heading line, for example ``"## Adopted"``.

    Returns
    -------
    tuple of (list of str, list of list of str)
        The header labels, and one list of stripped cells per body row.
    """
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == heading]
    assert len(starts) == 1, f"expected exactly one {heading!r} heading, found {len(starts)}"
    rows: list[list[str]] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        if line.lstrip().startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    assert len(rows) >= 3, f"the table under {heading!r} has no body rows; the parse broke"
    separator = rows[1]
    assert all(set(cell) <= set("-: ") and cell for cell in separator), (
        f"the second table line under {heading!r} is not a separator row, so the "
        "header was not where this parser expected it"
    )
    return rows[0], rows[2:]


def _adopted_table() -> tuple[list[str], list[list[str]]]:
    """The Adopted table of the standards page."""
    return _markdown_table(STANDARDS.read_text(encoding="utf-8"), "## Adopted")


def _enforcement_token(cell: str) -> tuple[str, str]:
    """Classify one "Enforced by" cell into its token kind.

    The kind is decided BEFORE anything is checked against the tree, which
    is the whole reason the vocabulary is three closed shapes rather than
    prose: read as a path, ``convention`` is a missing file and the Sybil
    command is a missing directory.

    Returns
    -------
    tuple of (str, str)
        The kind (``convention``, ``seat``, ``path`` or ``command``) and the
        token to check, empty for ``convention``.
    """
    if cell == _CONVENTION:
        return _CONVENTION, ""
    quoted = re.findall(r"`([^`]+)`", cell)
    if len(quoted) != 1:
        return "unreadable", cell
    token = quoted[0]
    if cell.startswith("seat:"):
        return "seat", token
    if re.search(r"\s", token):
        return "command", token
    return "path", token


def test_the_enforcement_guard_reads_the_table_it_names() -> None:
    """Non-vacuity: a broken parse would make the sweep below pass silently.

    Both anchors are practices, not mechanisms, so this assertion survives
    every change the guard below is meant to allow and fails on the one
    thing it cannot see, which is a table it stopped finding.
    """
    headers, rows = _adopted_table()
    assert len(rows) >= 14, f"the Adopted table parsed to {len(rows)} rows, which is too few"
    practices = " ".join(row[0] for row in rows)
    for anchor in ("SemVer 2.0.0", "Role-based review"):
        assert anchor in practices, f"the Adopted table no longer names {anchor!r}"
    assert _ENFORCEMENT_COLUMN in headers, (
        f"the Adopted table has no {_ENFORCEMENT_COLUMN!r} column, so a reader cannot "
        f"tell an enforced row from an unenforced one; the columns are {headers}"
    )
    column = headers.index(_ENFORCEMENT_COLUMN)
    kinds = {_enforcement_token(row[column])[0] for row in rows}
    assert kinds & {"path", "command"}, (
        "no row names a repository path or a CI command, so the existence half of "
        "the guard below checks nothing at all"
    )


def test_every_adopted_standard_names_what_enforces_it() -> None:
    """Every Adopted row carries an enforcement cell, and it resolves.

    A page that mixes a practice held by a tier-1 test with one held by
    habit, in the same prose column, publishes a discipline a reader cannot
    grade. The cell is one of three closed shapes: a repository path, a CI
    command, a named review seat with its charter, or the literal word
    ``convention``, which says that nothing refuses a breach and is a real
    answer rather than an omission.
    """
    headers, rows = _adopted_table()
    assert _ENFORCEMENT_COLUMN in headers, (
        f"the Adopted table has no {_ENFORCEMENT_COLUMN!r} column: {headers}"
    )
    column = headers.index(_ENFORCEMENT_COLUMN)
    ci_text = "\n".join((REPO / home).read_text(encoding="utf-8") for home in _CI_HOMES)

    offenders = []
    for row in rows:
        practice = row[0]
        assert len(row) == len(headers), (
            f"the {practice!r} row has {len(row)} cells and the header has {len(headers)}"
        )
        cell = row[column]
        if not cell:
            offenders.append(f"{practice}: the enforcement cell is empty")
            continue
        kind, token = _enforcement_token(cell)
        if kind == "unreadable":
            offenders.append(
                f"{practice}: {cell!r} is neither the word {_CONVENTION!r} nor exactly one "
                "backticked path, command or seat charter"
            )
        elif kind in ("path", "seat") and not (REPO / token).exists():
            offenders.append(f"{practice}: names {token!r}, which the repository does not hold")
        elif kind == "command" and token not in ci_text:
            offenders.append(
                f"{practice}: names the command {token!r}, which appears verbatim in none of "
                f"{', '.join(_CI_HOMES)}, so nothing runs it"
            )
    assert not offenders, (
        "\n  "
        + "\n  ".join(offenders)
        + "\n\nEvery adopted row states how it lands AND what holds it there. A cell "
        "naming a path or a command the tree no longer holds is the stale claim this "
        "column exists to prevent; the word convention is how a row says, on purpose, "
        "that nothing mechanical refuses a breach."
    )


def test_the_role_based_review_row_names_the_gate_that_refuses_a_push() -> None:
    """The row says a tool refuses the push, not that a reviewer remembers.

    The page described role-based review as five charters run by a skill
    before a work item closes, which is true and stopped being complete when
    the push gate landed: an unattested push is DENIED, and a push made
    while a blocking incident is open in the shared ledger is denied too.
    A public claim that understates its own mechanism is the mirror of one
    that overstates it, and this repository's changelog had announced both
    gates while the SRS still described a habit.
    """
    headers, rows = _adopted_table()
    matching = [row for row in rows if row[0].startswith("Role-based review")]
    assert len(matching) == 1, f"expected one Role-based review row, found {len(matching)}"
    assert "How it lands here" in headers, f"the Adopted table columns are {headers}"

    # THE PROSE CELL, not the joined row, and the difference is measured
    # rather than stylistic: the enforcement cell of this same row names the
    # hook too, so a guard reading the whole row passed with the hook deleted
    # from the sentence a reader actually reads.
    cell = matching[0][headers.index("How it lands here")]

    hook = ".claude/hooks/role_review_gate.py"
    assert (REPO / hook).is_file(), (
        f"{hook} is not in the tree, so the row below would name a mechanism that no "
        "longer exists; the row and the hook move together"
    )
    assert hook in cell, (
        "the Role-based review row does not name the push-gate hook where it describes "
        "the practice, so a reader of that row alone learns that a skill runs five "
        f"charters and not that an unattested push is refused by {hook}"
    )
    assert ".claude/agents/" in cell, (
        "the row no longer names the reviewer charters, which are what the gate "
        "attests to; naming the gate is an addition to that sentence, not a swap"
    )
    assert "COORD_INCIDENT_LEDGER" in cell, (
        "the incident half is stated without naming the variable that locates the "
        "ledger, so a reader cannot follow it to the machine-configuration table "
        "in CLAUDE.md, which is that fact's one home"
    )

    # Per CLAUSE, for the same reason. Both halves of the gate live in one
    # sentence, so a sentence-level or row-level search let "reminds the
    # author about the attestation" pass on the word "denies" belonging to
    # the OTHER half. A refusal has to be stated where the mechanism is.
    clauses = re.split(r"[.;:]\s+", cell)
    refusal = ("denies", "refuses", "refusal", "blocks")
    for what, marker in (("attestation half", hook), ("incident half", "incident")):
        carrying = [clause for clause in clauses if marker.lower() in clause.lower()]
        assert carrying, (
            f"the row's prose does not mention the {what} of the gate at all "
            f"(looked for {marker!r}), so a reader learns about only one of the two "
            "refusals that stand behind role-based review here"
        )
        assert any(any(verb in clause.lower() for verb in refusal) for clause in carrying), (
            f"the row names the {what} without saying, in the same clause, that it "
            f"REFUSES the push (one of {', '.join(refusal)}). A gate described as a "
            "reminder reads exactly like the reviewer's memory it replaced, which is "
            "the understatement this row was corrected for"
        )
