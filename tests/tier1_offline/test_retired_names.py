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

import re
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
        # PROVOKED AT THE CONSUMER, not asked of the registry's own message builder: a
        # pproc entry citing the frame is refused by the frame reader (PFS-2135.036).
        from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
        from pyflightstream.cases.workflows._frames import _refuse_a_retired_frame

        case = SimCase(
            sim_id="9001",
            aircraft="Rig",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
        )
        with pytest.raises(CampaignConfigError) as caught:
            _refuse_a_retired_frame(case, wrote, "an entry")
        return str(caught.value)
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


def _spellings_in(data, entry: RetiredName) -> bool:
    """Whether a parsed artifact carries ``entry``'s old spelling as a KEY, a table or a value.

    The tables are walked at every depth: ``kind = "engine"`` lives inside a rotor block or a
    point, never at the top level, and a frame citation is a string VALUE. A word in a comment
    or in a longer key does not count; a key that is the right word with another value does not
    either (``kind = "wing"`` is not ``kind = "engine"``).
    """
    old = entry.old
    pair = old.split(" = ", 1)
    key, value = (pair[0], pair[1].strip('"')) if len(pair) == 2 else (old.strip("[]"), None)
    citation = re.compile(old.replace("<k>", "[0-9]+") + "$")
    is_citation = entry.owner == "a frame citation"

    def walk(node) -> bool:
        if isinstance(node, dict):
            for name, child in node.items():
                if is_citation:
                    if isinstance(child, str) and citation.match(child):
                        return True
                elif name == key and (value is None or child == value):
                    return True
                if walk(child):
                    return True
        elif isinstance(node, list):
            return any(walk(child) for child in node)
        return False

    return walk(data)


def _retired_entry(old: str) -> RetiredName:
    return next(entry for entry in RETIRED if entry.old == old)


def test_no_shipped_artifact_carries_a_retired_spelling():
    """The workspace the documentation points at speaks only 0.15.0.

    An example a reader is told to copy is the one place a retired spelling
    costs most: they copy it, and the refusal they meet is one this
    repository wrote into the file it gave them. Every shipped toml is read: the
    licensed inputs, the examples and the fixtures (PFS-2135.069).
    """
    repo = Path(__file__).resolve().parents[2]
    roots = [repo / "tests" / "tier3_licensed" / "inputs", repo / "examples", repo / "tests"]
    paths = sorted({path for root in roots for path in root.rglob("*.toml")})
    assert len(paths) >= 40, f"the walk found only {len(paths)} shipped tomls"
    offenders: list[str] = []
    for path in paths:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            continue
        for entry in RETIRED:
            if entry.old == "engine_point":
                continue  # an attribute of the workspace object, not a spelling in a file
            if _spellings_in(data, entry):
                offenders.append(f"{path.relative_to(repo).as_posix()}: {entry.old}")
    assert not offenders, f"shipped artifacts carry retired spellings: {offenders}"


def test_the_shipped_artifact_walk_sees_every_kind_of_retired_spelling():
    """The control of the guard above: each kind of entry is found where it is written."""
    planted = {
        "propeller_diameter_m": {"propeller_diameter_m": 3.6},
        "[propeller]": {"propeller": {"radius_m": 1.8}},
        'kind = "engine"': {"PUSHER": {"kind": "engine"}},
        'scale = "propeller_radius"': {"probes": [{"scale": "propeller_radius"}]},
        "PROP_MRP": {"pproc": [{"frame": "PROP_MRP"}]},
        "ROTOR_MRP": {"pproc": [{"frame": "ROTOR_MRP"}]},
        "RotorAxis<k>": {"pproc": [{"frame": "RotorAxis2"}]},
    }
    assert {entry.old for entry in RETIRED} >= set(planted), (
        "an entry was renamed under this control"
    )
    for old, data in planted.items():
        assert _spellings_in(data, _retired_entry(old)), old
    # The current spelling and the right key with another value are not retired.
    assert not _spellings_in({"PUSHER": {"kind": "wing"}}, _retired_entry('kind = "engine"'))
    assert not _spellings_in({"pproc": [{"frame": "PUSHER_SMRP"}]}, _retired_entry("PROP_MRP"))


def test_f_1605_a_numbered_frame_citation_gets_the_index_reason():
    """F-1605: PROP_MRP2 is the positional spelling, so its refusal says it was an index."""
    numbered = retired_frame("PROP_MRP2")
    assert numbered is not None
    text = numbered.message("PROP_MRP2")
    assert "INDEX" in text and "ONE rotor frame" not in text
    plain = retired_frame("PROP_MRP")
    assert plain is not None and "ONE rotor frame" in plain.message()


def test_f_358_rothalpy_refusal_names_the_itaca_home():
    """F-358 (FR-458): the refusal identifies ITACA as the evaluation home."""
    from pyflightstream._retired_names import RETIRED_ATTRIBUTES

    for key in ("pyflightstream.farfield.rothalpy", "pyflightstream.farfield.irreversible_deficit"):
        message = RETIRED_ATTRIBUTES[key].message()
        assert "ITACA" in message and "external Euler CFD tools" in message
