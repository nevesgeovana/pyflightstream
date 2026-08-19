"""Tier 1: the coupled state survives the rename of its digest field.

Pipeline role: quality gate on the FSI persisted state. ``config_hash``
was renamed to ``config_sha256`` so the field names the algorithm that
produced it, matching ``RunRecord.script_sha256`` and
``outputs_sha256``. The rename is an approved public break for 0.8.0
(NFR-20's pre-1.0 clause), but a break in the API is not licence to
break a FILE that a half-finished coupled run left on disk.

THE REPRODUCTION, and it is why this module exists rather than a line
in ``tests/test_fsi_driver.py``. :class:`~pyflightstream.fsi.state.FsiState`
sets ``extra="forbid"``. A plain rename therefore turns every
``state.json`` written before today into an unloadable file: the key
``config_hash`` is no longer a field, so it is an EXTRA key, and
``load_state`` refuses the whole document. The user meeting that is
mid-campaign, with a run folder holding the only copy of a
relaxation memory and a convergence history, and the diagnosis they get
names a key rather than the release that moved it.

The migration is a validation alias, not a shim: the field accepts
either spelling on the way IN and writes only the new one on the way
OUT, so the first resume of an old run rewrites its own state file into
the new vocabulary and the legacy key is gone from that folder for good.

Usage, as a resumed run reaches it::

    from pyflightstream.fsi.state import load_state
    state = load_state(run_dir / "state.json")   # either spelling loads
    state.config_sha256                          # always the new name

WHAT THIS MODULE ASSERTS:

* a ``state.json`` carrying the legacy key loads and lands on
  ``config_sha256``;
* a state written back out carries the new key and NOT the legacy one,
  so the migration completes rather than persisting both;
* ``extra="forbid"`` still refuses a genuinely unknown key, which is
  the property the alias could plausibly have widened;
* exactly two paths under ``src/`` and ``tests/`` still carry the
  legacy literal, so the old name cannot grow back one site at a time.

OPS-2009.01.14. Requirement: NFR-18 (manifest and state keys move only
under NFR-20's policy) and NFR-20's pre-1.0 clause.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pyflightstream.fsi.state import FsiState, load_state, write_state_atomic

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The literal being retired, built by concatenation so that this
#: module's own guard below cannot be satisfied by the very string it
#: is hunting appearing somewhere it does not intend.
LEGACY_KEY = "config" + "_hash"

#: The only two paths permitted to carry that literal after the rename:
#: the model that declares the alias and documents the legacy key, and
#: this module, which must name it to migrate it.
PERMITTED_LEGACY_PATHS = {
    "src/pyflightstream/fsi/state.py",
    "tests/test_fsi_state_migration.py",
}

_DIGEST = "0f" * 32


def _legacy_state_document() -> str:
    """Return a ``state.json`` exactly as releases before 0.8.0 wrote it."""
    return json.dumps(
        {
            LEGACY_KEY: _DIGEST,
            "call_count": 7,
            "step_count": 42,
            "phase": 2,
            "last_solver_iteration": 3,
            "previous_displacements": None,
            "previous_twist_rad": [[0.0, 0.01]],
            "load_history": [],
            "revolution_history": [],
            "recorded_twist": [],
            "phase4_start_step": None,
        },
        indent=2,
    )


def test_a_state_written_before_the_rename_still_loads(tmp_path):
    """The run folder is the user's only copy; the rename must not eat it.

    ``extra='forbid'`` is what makes this sharp: without the alias the
    legacy key is not "ignored", it is REFUSED, and the whole document
    goes with it.
    """
    path = tmp_path / "state.json"
    path.write_text(_legacy_state_document(), encoding="utf-8")

    state = load_state(path)

    assert getattr(state, "config_sha256", None) == _DIGEST, (
        "a state.json written before 0.8.0 did not migrate its digest field: the "
        "run folder of a half-finished coupled run is the only copy of its "
        "relaxation memory, so the rename must be readable in both directions"
    )
    assert state.call_count == 7
    assert state.previous_twist_rad == [[0.0, 0.01]]


def test_the_new_spelling_loads_too(tmp_path):
    """The alias must not have replaced the field name with the old one."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"config_sha256": _DIGEST}), encoding="utf-8")

    assert getattr(load_state(path), "config_sha256", None) == _DIGEST


def test_a_written_state_carries_the_new_key_and_not_the_legacy_one(tmp_path):
    """The migration COMPLETES on the first write back.

    Writing both spellings would leave every run folder carrying a field
    whose two copies can disagree, which is a worse record than the one
    this rename set out to improve.
    """
    path = tmp_path / "state.json"
    path.write_text(_legacy_state_document(), encoding="utf-8")

    write_state_atomic(load_state(path), path)
    written = path.read_text(encoding="utf-8")

    assert '"config_sha256"' in written, "the written state does not name the digest field"
    assert f'"{LEGACY_KEY}"' not in written, (
        "the written state still carries the legacy key, so the migration never "
        "finishes and a run folder holds the same digest under two names"
    )
    assert json.loads(written)["config_sha256"] == _DIGEST


def test_the_alias_did_not_widen_what_the_state_accepts(tmp_path):
    """The control. An alias is a second NAME, never a second door.

    ``extra='forbid'`` is what makes a typo in a hand-edited state file
    fail loudly, and it is exactly the setting the alias touches.
    """
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"config_shasum": _DIGEST}), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_state(path)

    with pytest.raises(ValidationError):
        FsiState(config_shasum=_DIGEST)  # type: ignore[call-arg]


def _walked_paths() -> list[Path]:
    """Every readable text file under ``src/`` and ``tests/``."""
    found = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "tests"):
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            found.append(path)
    return found


def test_exactly_two_paths_still_name_the_legacy_key():
    """The ratchet, and the reason it is a whole-tree walk.

    A rename that is 95 percent done reads as done. The two paths below
    are the two that must keep the literal, and a THIRD is how the old
    name grows back: a docstring here, a keyword there, and the field
    has two spellings again with the suite green.
    """
    walked = _walked_paths()
    assert len(walked) > 100, (
        "the walk collected almost nothing, so a green result here would mean "
        "the guard found no files rather than no offenders"
    )

    carrying = set()
    for path in walked:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if LEGACY_KEY in text:
            carrying.add(path.relative_to(REPO_ROOT).as_posix())

    assert carrying == PERMITTED_LEGACY_PATHS, (
        "the set of paths naming the retired digest key is not the set the rename "
        f"left behind.\n  unexpected: {sorted(carrying - PERMITTED_LEGACY_PATHS)}\n"
        f"  missing:    {sorted(PERMITTED_LEGACY_PATHS - carrying)}\n"
        "The two permitted paths are the model that declares the validation alias "
        "and documents the legacy key, and this migration test. Anything else is "
        "the old name growing back."
    )
