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

    Anchored on ``pyproject.toml`` rather than on a literal, so it moves
    itself at the next bump instead of becoming the next stale claim.
    """
    import tomllib

    version = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    status = [
        line
        for line in README.read_text(encoding="utf-8").splitlines()
        if line.startswith("Status:")
    ]
    assert len(status) == 1, f"expected one README status line, found {len(status)}"
    assert version in status[0], (
        f"the README status line is {status[0]!r} and pyproject declares {version}. "
        "That line is rendered by PyPI as the project page for the version being "
        "published, so a stale one ships as the release's own front page."
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
