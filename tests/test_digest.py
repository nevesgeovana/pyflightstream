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

from pyflightstream import _digest as digest_module
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


def _hashlib_calls(module: Path) -> set[str]:
    """Return the ``hashlib`` constructors a module calls, by name.

    ``hashlib.sha256(...)`` yields ``"sha256"``; ``hashlib.new("md5")``
    yields ``"new"``, which is deliberately reported rather than
    resolved, because a constructor chosen at run time is exactly the
    shape that makes the algorithm unstateable.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
            if function.value.id == "hashlib":
                found.add(function.attr)
    return found


def _modules_that_compute_a_digest() -> dict[str, set[str]]:
    """Map every module under ``src/`` that hashes to the calls it makes."""
    measured = {}
    for module in sorted(SRC.rglob("*.py")):
        calls = _hashlib_calls(module)
        if calls:
            measured[module.relative_to(SRC).as_posix()] = calls
    return measured


@pytest.mark.requirement("NFR-15")
def test_every_digest_the_package_computes_declares_its_canonical_form():
    """NFR-15's rule, held by a registry rather than by a paragraph.

    The requirement asks which ALGORITHM over which CANONICAL FORM, and
    what stays out of it. The algorithm was already stateable by reading
    the code; the canonical form was not, because a digest is a
    statement about a canonical form CHOSEN AT THE CALL SITE, and each
    site chose privately. Nothing stopped a fourth site appearing whose
    canonical form carried a wall-clock timestamp or an absolute path,
    and two identical runs would then have disagreed with no test
    noticing, which is the failure NFR-07 rests on not happening.

    So the rule is DATA. A module that computes a digest declares the
    canonical form it hashes, here, beside the exclusions that hold for
    all of them; a module that appears with no declaration fails.
    """
    measured = set(_modules_that_compute_a_digest())
    declared = set(getattr(digest_module, "CANONICAL_FORMS", {}))

    assert declared == measured, (
        "the digests this package computes and the canonical forms it declares "
        f"have diverged.\n  undeclared: {sorted(measured - declared)}\n"
        f"  declared but gone: {sorted(declared - measured)}\n"
        "Every sha256 computed in this package is a claim that two runs are the "
        "same run, so each one must say what canonical form it hashes. Add the "
        "module to CANONICAL_FORMS in src/pyflightstream/_digest.py, naming the "
        "exact bytes it feeds the hash, or route it through this module."
    )


@pytest.mark.requirement("NFR-15")
def test_the_package_names_one_algorithm_and_uses_no_other():
    """The algorithm half, pinned where it is spent rather than described.

    A digest written into a committed manifest and cited by a
    publication cannot quietly change algorithm, and `hashlib.new` is
    excluded outright: a constructor chosen at run time makes the
    algorithm a property of the input rather than of the code.
    """
    used = set()
    for calls in _modules_that_compute_a_digest().values():
        used |= calls
    algorithm = getattr(digest_module, "ALGORITHM", None)

    assert used == {algorithm}, (
        f"this package computes a digest with {sorted(used)} where the rule names "
        f"{algorithm!r} alone. A manifest digest is cited by "
        "publications, so a second algorithm is a public break and needs the "
        "changelog entry that goes with one."
    )


@pytest.mark.requirement("NFR-15")
def test_a_digest_is_a_statement_about_content_and_nothing_around_it(tmp_path):
    """The exclusion clause, measured rather than promised.

    Wall-clock timestamps, absolute paths and elapsed time are what make
    two identical runs disagree, so the property is asserted directly:
    the same bytes under two names, in two directories, with two
    modification times, hash to one value.
    """
    first = tmp_path / "one" / "wing.stl"
    second = tmp_path / "two" / "a_different_name.stl"
    for path in (first, second):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"solid wing\nfacet\nendsolid\n")

    import os

    # Two different modification times, one of them plainly not "now".
    os.utime(first, (0, 0))
    os.utime(second, (1_000_000_000, 1_000_000_000))

    assert file_sha256(first) == file_sha256(second), (
        "the digest of a file changed with its name, its directory or its "
        "modification time, so two identical runs on two machines cannot agree"
    )

    third = tmp_path / "one" / "changed.stl"
    third.write_bytes(b"solid wing\nfacet\nfacet\nendsolid\n")
    assert file_sha256(third) != file_sha256(first), "the control: content must still count"

    assert text_sha256("SOLVER_SET_AOA 4.0\n") == text_sha256("SOLVER_SET_AOA 4.0\n")


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
