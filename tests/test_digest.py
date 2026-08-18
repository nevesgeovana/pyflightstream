"""Tier 1: one owner for the checksum NFR-07's claim rests on.

Pipeline role: quality gate on the same-inputs claim. NFR-07 says two
runs with the same inputs are recognisably the same run, and until
2026-08-19 that claim rested on a sha256 written in FOUR places: a
chunked read in ``workspace``, a second chunked read in ``run`` differing
only in its failure policy, and two inline text hashes, one in ``run``
and one in ``qa.probes``. Nothing stopped two of them diverging and
nothing would have noticed if they had: the manifest would simply have
said two identical runs were different, or two different runs the same.

The run layer had also reached ACROSS A LAYER BOUNDARY to import
``workspace._sha256``, an underscore-private name, rather than write a
fifth. That import is what made this an architecture item rather than a
tidy-up (PFS-2012.02, `PLN-20260817-2100`).

WHAT THIS MODULE ASSERTS, and the second is the load-bearing one:

* the three former call paths produce ONE hex string for one file, so
  the value did not move when the owner did;
* ``run`` no longer imports a private name out of ``workspace``.

The second is the assertion this file was measured RED on. Importing
``pyflightstream._digest`` before it existed is an IMPORT ERROR rather
than a failing assertion, which `develop` step 4 refuses as a falsifying
measurement, so the base measurement was taken on the import walk
instead: it failed on the assertion, with the import present.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256, optional_file_sha256, text_sha256

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "pyflightstream"


def test_one_file_hashes_to_one_value_through_every_former_call_path(tmp_path):
    """The value must not move when the owner does.

    ``stage_inputs``, ``output_digests``, ``write_script`` and
    ``fs_exe_sha256`` all record digests into committed manifests, so a
    changed value would make every manifest written before today
    unreadable as a comparison. This hashes one fixture through the
    raising form, the optional form and a hand-rolled chunked read, and
    requires all three to agree.
    """
    import hashlib

    target = tmp_path / "input.stl"
    # Bigger than the 65536-byte block, so the chunking is exercised
    # rather than assumed: a single-block fixture cannot tell a correct
    # loop from one that reads once and stops.
    target.write_bytes(b"solid wing\n" + b"x" * 200_000 + b"endsolid\n")

    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    assert file_sha256(target) == expected
    assert optional_file_sha256(target) == expected
    assert file_sha256(str(target)) == expected, "a str path must hash the same as a Path"


def test_the_two_file_functions_differ_only_in_their_failure_policy(tmp_path):
    """A caller who picks the wrong one gets one of two failures.

    Either a run that dies on a provenance field, or a manifest that
    silently records nothing. The policy is carried by the NAME, so both
    directions are pinned here rather than left to a docstring.
    """
    missing = tmp_path / "not_there.stl"

    with pytest.raises(OSError):
        file_sha256(missing)
    assert optional_file_sha256(missing) is None

    unreadable = tmp_path / "a_directory"
    unreadable.mkdir()
    with pytest.raises(OSError):
        file_sha256(unreadable)
    assert optional_file_sha256(unreadable) is None


def test_the_text_digest_names_its_encoding(tmp_path):
    """UTF-8 is named because the digest is written into committed records.

    An encoding chosen by the platform would make the same text hash
    differently on two machines, which is the opposite of what a
    same-inputs claim needs.
    """
    import hashlib

    text = "SOLVER_SET_AOA 4.0\n# a comment with an accent: á\n"
    assert text_sha256(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert text_sha256(text) != hashlib.sha256(text.encode("utf-16")).hexdigest()


def _imports_of(module: Path) -> list[tuple[str, str]]:
    """Return ``(module, name)`` for every ``from x import y`` in a file."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found += [(node.module, alias.name) for alias in node.names]
    return found


def test_no_layer_reaches_into_another_for_a_private_digest():
    """The import that made this an architecture item, and it is gone.

    `run/__init__.py` imported `_sha256` from `pyflightstream.workspace`:
    an underscore-private name crossing a layer boundary, taken because
    the alternative was writing the same chunked read a fourth time.
    Publishing the digest below every layer removes the reason.

    This walks EVERY module under `src/` rather than the one that did it,
    because the next such import will be somewhere else.
    """
    offenders = []
    for module in sorted(SRC.rglob("*.py")):
        for source, name in _imports_of(module):
            if not source.startswith("pyflightstream"):
                continue
            if not name.startswith("_"):
                continue
            if source.rsplit(".", 1)[-1].startswith("_"):
                # A private name out of a private module is that module's
                # own business; `_errors` and `_digest` are exactly that.
                continue
            offenders.append(f"{module.relative_to(SRC).as_posix()} imports {name} from {source}")
    assert not offenders, (
        "a module imports an underscore-private name out of a PUBLIC sibling module, "
        "which is a layer boundary crossed for a helper. Publish the helper where every "
        "layer may reach it, as `_digest` and `_errors` are:\n  " + "\n  ".join(offenders)
    )


def test_the_digest_owner_imports_nothing_from_this_package():
    """What makes it usable from every layer, asserted rather than assumed.

    `_digest` sits below the layer rule exactly as `_errors` does, and
    that is only true while it imports nothing from the package. The day
    it does, some layer can no longer use it and the duplication comes
    back.
    """
    module = SRC / "_digest.py"
    assert module.is_file()
    for source, _ in _imports_of(module):
        assert not source.startswith("pyflightstream"), (
            f"_digest imports {source}, so it no longer sits below every layer and the "
            "reason it exists is gone"
        )
    assert "import pyflightstream" not in module.read_text(encoding="utf-8")


def test_the_run_layers_provenance_digest_answers_none_rather_than_raising(tmp_path):
    """The policy at the CALL SITE, not only in the function it calls.

    `run._file_digest` records the solver executable's hash into the
    manifest (`fs_exe_sha256`). A missing or unreadable executable is the
    executor's problem to report, with the diagnosis it can give, and a
    provenance field must never be the thing that fails a run.

    This test exists because the first version of this module tested
    `optional_file_sha256` directly and nothing else: swapping
    `_file_digest`'s body to the RAISING form left every case here green,
    so the policy was owned by a function nobody checked was the one
    being called. The mutant is the whole point.
    """
    from pyflightstream.run import _file_digest

    present = tmp_path / "FlightStream.exe"
    present.write_bytes(b"not really an executable")
    assert _file_digest(present) == file_sha256(present)

    assert _file_digest(tmp_path / "absent.exe") is None, (
        "an unreadable executable made the digest RAISE, so a run dies on a "
        "provenance field rather than recording that it could not read one"
    )
    assert _file_digest(tmp_path) is None, "a directory is unreadable as a file, not fatal"
