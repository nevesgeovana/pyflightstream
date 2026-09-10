"""Tier 1: every retired spelling refuses, and says what to write instead.

THIS MODULE EXISTS BECAUSE ITS ABSENCE WAS FOUND. `_retired_names.RETIRED`
carried the sentence "Iterated by the input readers ... and by the Tier 1
guard that proves each one refuses", and no test imported the module at all.
Three review lenses reached that finding by three different routes on the
0.15.0 release review, and two of the seven entries turned out to be
referenced by nothing but their own definition: a registry that says it fires
and does not is the convention-dressed-as-a-mechanism defect this estate names
by that phrase.

WHAT THE GUARD ASSERTS, and it is deliberately narrow. For each entry it
provokes the old spelling at the surface the entry's own `owner` names, and
asserts the refusal carries the entry's `message()`. It does NOT assert the
message is a good message; that is a reading, and a test cannot do it. What it
removes is the possibility of an entry that is documented and enforced
nowhere, which is what two of them were.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from pyflightstream._retired_names import (
    RETIRED,
    RETIRED_FRAME_CITATIONS,
    RetiredName,
    retired_frame,
    retired_key,
)


def _provoke(entry: RetiredName, tmp_path: Path) -> str:
    """Write the old spelling where its owner says it appeared, and return the refusal."""
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.inputs import resolve_reference

    references = tmp_path / "inputs" / "references"
    references.mkdir(parents=True, exist_ok=True)
    lengths = "area_m2 = 10.0\nchord_m = 1.0\nspan_m = 8.0\n"

    def refusal(body: str) -> str:
        (references / "r900.toml").write_text(body, encoding="utf-8")
        with pytest.raises(PyflightstreamError) as caught:
            resolve_reference(tmp_path / "inputs", "r900")
        return str(caught.value)

    if entry.old == "propeller_diameter_m":
        return refusal(lengths + "propeller_diameter_m = 3.6576\n")
    if entry.old == "[propeller]":
        return refusal(lengths + "\n[propeller]\nradius_m = 1.8288\n")
    if entry.old == 'kind = "engine"' and "rotor block" in entry.owner:
        return refusal(lengths + '\n[PUSHER]\nkind = "engine"\naxis = "X"\n')
    if entry.old == 'kind = "engine"':
        from pyflightstream.workspace.inputs import PointXyz

        with pytest.raises(Exception) as caught:
            PointXyz.model_validate({"kind": "engine"})
        return str(caught.value)
    if entry.old == 'scale = "propeller_radius"':
        from pyflightstream.cases import ProbesSpec

        with pytest.raises(Exception) as caught:
            ProbesSpec(frame="PUSHER_SMRP", scale="propeller_radius")
        return str(caught.value)
    if entry.owner == "a frame citation":
        # THE SPELLING AS A USER WRITES IT, which for the positional form is
        # `RotorAxis<k>` in the entry and `RotorAxis2` in a file.
        wrote = entry.old.replace("<k>", "2")
        found = retired_frame(wrote)
        assert found is entry, (
            f"the frame registry answers {found} for {wrote!r} and the tuple holds "
            f"{entry}, so one fact has two homes"
        )
        return found.message(wrote=wrote)
    if entry.old == "engine_point":
        workspace = CampaignWorkspace(tmp_path)
        with pytest.raises(AttributeError) as caught:
            workspace.engine_point("ERP1")
        return str(caught.value)
    raise AssertionError(
        f"{entry.old!r} of {entry.owner!r} has no provocation here, so this guard would "
        "count it as covered while proving nothing about it. Add one, or take the entry "
        "out of RETIRED: a retirement that cannot fire belongs in the changelog."
    )


@pytest.mark.parametrize("entry", RETIRED, ids=lambda e: f"{e.owner}:{e.old}")
def test_every_retired_spelling_refuses_and_names_its_replacement(entry, tmp_path):
    """The sentence `_retired_names` writes about itself, made true."""
    message = _provoke(entry, tmp_path)
    assert entry.new in message, (
        f"the refusal for {entry.old!r} does not name {entry.new!r}, so a reader is told "
        f"what is wrong and not what to write: {message}"
    )
    assert "no longer accepted" in message, (
        f"the refusal for {entry.old!r} does not say the spelling is refused: {message}"
    )
    assert entry.why in message, (
        f"the refusal for {entry.old!r} carries no reason, so it reads as churn: {message}"
    )


def test_the_registry_is_not_empty():
    """Without this the parametrized guard above passes on an empty tuple."""
    assert len(RETIRED) >= 7, f"RETIRED holds {len(RETIRED)} entries"


def test_retired_key_answers_for_a_table_and_for_a_bare_key():
    """Two spellings reach one entry: `propeller` as a table and as a key."""
    assert retired_key("propeller_diameter_m") is not None
    assert retired_key("propeller") is not None, "a table name is written without brackets"
    assert retired_key("rotor_diameter_m") is None, "the CURRENT spelling is not retired"


def test_retired_frame_reads_the_numbered_forms_too():
    """The positional names carried an index, which is why they went."""
    for name in RETIRED_FRAME_CITATIONS:
        assert retired_frame(name) is not None, name
        assert retired_frame(f"{name}2") is not None, f"{name}2"
    assert retired_frame("PUSHER_SMRP") is None, "a rotor's own frame is not retired"
    assert retired_frame("MRP") is None, "the moment frame is not retired"


def test_a_worked_reference_of_this_repository_still_loads():
    """THE CONTROL. Every case above asserts a refusal, and a guard that only
    ever refuses is satisfied by a reader that refuses everything. This one
    reads the reference the documentation sends a reader to copy."""
    from pyflightstream.workspace.inputs import resolve_reference

    inputs = Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs"
    reference = resolve_reference(inputs, "r006")
    assert sorted(reference.rotors) == ["PORT", "STARBOARD"], sorted(reference.rotors)


def test_no_shipped_artifact_carries_a_retired_spelling():
    """The workspace the documentation points at speaks only 0.15.0.

    An example a reader is told to copy is the one place a retired spelling
    costs most: they copy it, and the refusal they meet is one this
    repository wrote into the file it gave them.
    """
    inputs = Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs"
    offenders: list[str] = []
    for path in sorted(inputs.rglob("*.toml")):
        text = path.read_text(encoding="utf-8")
        for entry in RETIRED:
            token = entry.old.strip("[]").split(" =")[0]
            if token in text and f"{token}s" not in text.replace(token + "s", ""):
                # A KEY, NOT A SUBSTRING: read the parsed file rather than
                # the bytes, so a word inside a comment or a longer key does
                # not read as a declaration.
                data = tomllib.loads(text)
                if token in data:
                    offenders.append(f"{path.name}: {entry.old}")
    assert not offenders, f"shipped artifacts carry retired spellings: {offenders}"
