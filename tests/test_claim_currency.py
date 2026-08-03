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
