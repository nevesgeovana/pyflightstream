"""Retained runtime, privacy and link checks, with shared test support."""

import hashlib
import os
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


SKIP_DIRS = {
    ".git",
    "_private",
    "site",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}


FORBIDDEN_WORDS = (
    "".join(map(chr, (69, 109, 98, 114, 97, 101, 114))),
    "".join(map(chr, (102, 116, 115, 95, 104, 111, 114, 115, 101))),
)


def iter_style_checked_files(root: Path = REPO_ROOT):
    # YAML joined the list on 2026-08-06. The command database is the
    # largest English prose surface in this repository, roughly 900 lines
    # of notes across the chapter files, and invariants 5 and 6 did not
    # reach a line of it: the walk read *.md and *.py only. Nothing was
    # in violation when it was widened, which is the cheap moment to do
    # it rather than the moment it would have caught something.
    # A name in SKIP_DIRS is tested on the part of the path BELOW ``root`` only (a
    # checkout at /build/pyflightstream must not blank itself) and the skipped
    # directories are pruned during the walk, so .venv is never descended into.
    for folder, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix in (".md", ".py", ".yaml"):
                yield Path(folder) / name


def test_the_style_walk_skips_by_name_below_the_root_only(tmp_path):
    """A root that sits under a skipped name is walked; a skipped name below it is not."""
    root = tmp_path / "build" / "site" / "checkout"
    for relative in ("a.md", "pkg/b.py", "data/c.yaml", ".venv/lib/d.py", "pkg/build/e.md"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    (root / "pkg" / "f.txt").write_text("x\n", encoding="utf-8")
    walked = sorted(path.relative_to(root).as_posix() for path in iter_style_checked_files(root))
    assert walked == ["a.md", "data/c.yaml", "pkg/b.py"]


def test_the_style_walk_has_something_to_check():
    """The guard on the three guards, and it is not hypothetical.

    Until 2026-08-19 this walk yielded ZERO files inside a nested second
    checkout of this tree, because it skipped by path component and that
    checkout lived under a directory of the skipped name. Invariants 5 and
    6 were unenforced there and nothing said so: each of the three
    consumers iterates the walk and asserts per file, so an empty walk
    satisfies all of them. See the note above ``SKIP_DIRS``.
    """
    walked = list(iter_style_checked_files())
    assert walked
    # And it must reach the two surfaces the invariants are about, not
    # merely count to the floor on one of them.
    suffixes = {path.suffix for path in walked}
    assert {".md", ".py", ".yaml"} <= suffixes, (
        f"the walk reached only {sorted(suffixes)}; invariants 5 and 6 cover the "
        "command database (yaml) and the prose (md) as well as the code"
    )


def test_no_private_names():
    offenders = []
    for path in iter_style_checked_files():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in FORBIDDEN_WORDS:
            if word.lower() in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: names {word}")
    assert not offenders, "\n".join(offenders)


MIGRATED_SESSION_DIRS = ("STATUS.md", "logbook.csv", "handoffs", "inbox", "progress")


MIGRATED_PATH = re.compile(
    r"_private[/\\](" + "|".join(re.escape(name) for name in MIGRATED_SESSION_DIRS) + r")\b"
)


_AT = chr(64)


MAIL_SHAPE = re.compile(
    r"[A-Za-z0-9._%+-]+" + _AT + r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)


IMPERSONAL_MAIL_HOSTS = ("example.com", "example.org", "example.net", "localhost")


IMPERSONAL_MAIL_TLDS = (".invalid", ".test", ".example", ".localhost")


IMPERSONAL_MAIL_USERS = ("noreply", "no-reply")


PROFILE_PATH_SHAPE = re.compile(
    r"[/\\][Uu]sers[/\\][A-Za-z0-9._-]+|%" + "USER" + "PROFILE%", re.IGNORECASE
)


def _identifier_offenses(text: str) -> list[str]:
    """Return the personal identifiers in ``text``, or an empty list.

    Factored out of the tree scan so the guard can be falsified directly:
    :func:`test_the_identifier_guard_fires_on_what_it_exists_to_catch` feeds it
    the exact shapes the 0.2.4 promotion removed and asserts it reports them.
    A guard whose own detection is never exercised is the class this
    repository keeps registering, so it is exercised here.
    """
    found = []
    for match in MAIL_SHAPE.finditer(text):
        address = match.group(0)
        user, _, host = address.partition(_AT)
        host = host.lower()
        if (
            host in IMPERSONAL_MAIL_HOSTS
            or host.endswith(IMPERSONAL_MAIL_TLDS)
            or user.lower() in IMPERSONAL_MAIL_USERS
        ):
            continue
        found.append(f"an email address ({address})")
    for match in PROFILE_PATH_SHAPE.finditer(text):
        found.append(f"a user-profile path ({match.group(0)})")
    return found


def _tracked_files() -> list[Path]:
    """Every tracked file, from git itself.

    Fails rather than skips when git cannot answer: a guard that reports
    nothing when it cannot run is worse than no guard, because it reports
    green. That failure mode is the one this repository has registered most.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "the personal-identifier guard could not list tracked files "
        f"(git exited {result.returncode}: {result.stderr.strip()}). It scans what is "
        "COMMITTED, so it needs git; a skip here would report green over an unscanned tree."
    )
    files = [REPO_ROOT / name for name in result.stdout.split("\0") if name]
    # A FLOOR, added 2026-08-12, because "git could not run" was never the only
    # way to scan nothing. A QA pass ran this guard with GIT_DIR pointing at a
    # throwaway repository: git exited 0, returned a handful of paths that are
    # not this tree's, and the test PASSED having examined none of the files it
    # exists to examine. That is the false green the assertion above is worded
    # against, arriving through the one door it does not watch, and GIT_DIR is
    # set by ordinary things (`git rebase -x`, any hook, any wrapper).
    assert files
    return files


def test_no_personal_identifier_in_a_tracked_file():
    """No tracked file carries an email address or a user-profile path.

    The name is out of scope by decision (see the comment above): it is
    published deliberately. These two are not published deliberately anywhere.
    """
    offenders = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: no literal to find
        for offense in _identifier_offenses(text):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: contains {offense}")
    assert not offenders, (
        "a tracked file carries a personal identifier, and this remote is public:\n"
        + "\n".join(offenders)
        + "\n\nMachine-specific values belong in a gitignored local settings "
        "file, never in a committed one. There is no exemption from this rule "
        "and no file in this tree has one."
    )


def test_the_identifier_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof: the guard blocks the original failure when re-run.

    The structural-fix rule says a fix is not complete until it carries a guard
    that makes recurrence impossible AND the evidence that the guard blocks the
    original failure. These are the two shapes that were removed from the
    tracked shell tool which published them, reconstructed here rather than
    quoted, so this file stays clean of them while still proving the detector
    fires.
    """
    address = "someone.personal" + _AT + "gmail.com"
    assert _identifier_offenses(f'config user.email "{address}"'), (
        "the guard does not detect a personal email address, which is the exact "
        "literal that reached the public remote"
    )
    # Assembled, never written literally, for the reason PROFILE_PATH_SHAPE gives.
    users = "Users"
    profiles = (
        "/c/" + users + "/someone/" + "One" + "Drive/tree",
        "C:" + chr(92) + users + chr(92) + "someone",
        "%" + "USER" + "PROFILE%",
    )
    for profile in profiles:
        assert _identifier_offenses(f'BASE="{profile}"'), (
            f"the guard does not detect the user-profile path {profile!r}"
        )
    # A version pin is the mail shape without a dotted TLD and must not fire.
    for pin in ("actions/checkout" + _AT + "v4", "pypa/gh-action-pypi-publish" + _AT + "release"):
        assert not _identifier_offenses(pin), f"the guard false-positives on the action pin {pin!r}"
    # And it stays quiet on the impersonal forms the tree legitimately holds,
    # so it is a guard rather than a blanket refusal.
    for benign in (
        "user" + _AT + "example.com",
        "private-snapshot" + _AT + "localhost",
        "noreply" + _AT + "github.com",
        # The RFC 2606 reserved TLDs, added 2026-08-11 with the branch that
        # accepts them. Both of the first two are real literals from vendored
        # kit bodies (role_review_gate_mutations.py and
        # prepush_receipt_mutations.py set a throwaway git identity from them);
        # the rest are the remaining reserved names, asserted so the tuple is
        # exercised rather than trusted, since a name nobody tests is a name
        # that can be dropped without anything going red.
        "gate" + _AT + "example.invalid",
        "kit" + _AT + "example.invalid",
        "anyone" + _AT + "something.test",
        "anyone" + _AT + "host.example",
        "anyone" + _AT + "box.localhost",
    ):
        assert not _identifier_offenses(benign), f"the guard false-positives on {benign!r}"
    # And the reserved names must be matched as a SUFFIX of the host, never as
    # a substring anywhere in it. A domain someone really owns can contain the
    # word, and that address is personal.
    for personal in (
        "someone" + _AT + "invalid-domain.com",
        "someone" + _AT + "example.invalid.co",
        "someone" + _AT + "test.org.uk",
    ):
        assert _identifier_offenses(personal), (
            f"the reserved-TLD exemption swallowed {personal!r}, which is a real host"
        )


def test_no_committed_path_to_a_migrated_session_document():
    """No committed file names a session document under ``_private/``.

    The plan ledger, the design documents and the licensed local assets DID
    stay in ``_private/``, so this guard names the five migrated entries
    explicitly rather than forbidding ``_private/`` wholesale.

    Scope, stated so the limit is visible: ``iter_style_checked_files``
    yields ``*.md``, ``*.py`` and ``*.yaml``, so ``.github/workflows/*.yml``
    and any ``*.json`` or ``*.sh`` in the tree are outside this guard. None
    of them carries such a path today. The two tracked files that used to
    carry one, and could not be corrected here because their canonical copy
    was kept elsewhere, have left the tree.
    """
    offenders = []
    for path in iter_style_checked_files():
        relative = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in MIGRATED_PATH.finditer(text):
            offenders.append(f"{relative}: names the migrated _private/{match.group(1)}")
    assert not offenders, (
        "session documents live under PYFS_SESSION_ROOT since 2026-07-27:\n" + "\n".join(offenders)
    )


GIVEN_NAME = "".join(map(chr, (71, 101, 111, 118, 97, 110, 97)))


def _names_the_author(text: str) -> bool:
    """Whether ``text`` carries the author's given name.

    Factored out so the tree scan and the mutation proof run the SAME
    code, which is the only arrangement under which the proof proves
    anything about the scan. Mirrors ``_identifier_offenses`` above and
    exists for the same reason.
    """
    return GIVEN_NAME.lower() in text.lower()


def test_no_personal_name_inside_the_installed_package():
    """The shipped surface carries no personal name.

    Tracked files under ``src/`` only. A failure here is not a style nit: the
    file reaches a user's machine, and removing it from HEAD stops it
    spreading without unpublishing what already shipped.
    """
    offenders = []
    for path in _tracked_files():
        relative = path.relative_to(REPO_ROOT)
        if relative.parts[0] != "src":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _names_the_author(text):
            offenders.append(str(relative))
    assert not offenders, (
        "a file inside the installed package carries the author's given name:\n"
        + "\n".join(offenders)
        + "\n\nThe name is deliberate in LICENSE, CITATION.cff, README.md and the "
        "docs, which are authorship of a published library. It is not deliberate "
        "inside src/, which ships in the wheel: there it is incidental. Write "
        '"the author" instead, and keep whatever provenance the sentence '
        "carried (BRF-049)."
    )


def test_the_shipped_name_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    The guard must be shown to block the ORIGINAL failure, so the original
    line is reconstructed here (assembled, never written literally) and the
    detector is run against it directly.
    """
    original = (
        "reason: 'metric set redefined to the full polar trend on "
        + GIVEN_NAME
        + "''s instruction'"
    )
    # Run the DETECTOR, not the `in` operator. The first version of this test
    # asserted `GIVEN_NAME in original`, which exercises str.__contains__ and
    # would stay green if the scan above were scoped wrongly or filtered to
    # the wrong file types. The role-review QA pass measured that.
    assert _names_the_author(original), (
        "the detector does not fire on the exact line that shipped in the wheel"
    )
    # And the replacement that shipped instead must NOT fire, so the guard is
    # a guard rather than a refusal of the whole sentence.
    replacement = (
        "reason: 'metric set redefined to the full polar trend on the author''s instruction'"
    )
    assert not _names_the_author(replacement), (
        "the detector fires on the replacement, so it refuses the sentence "
        "rather than the identifier"
    )


GEOMETRY_SUFFIXES = frozenset(
    {
        # IMPORT file_type enum (commands/mesh_import_export.yaml)
        ".stl",
        ".tri",
        ".p3d",
        ".inp",
        ".lawgs",
        ".vtk",
        ".ac",
        ".fac",
        ".obj",
        # saved simulation: carries the mesh (workspace/inputs.py, file_io.yaml)
        ".fsm",
        # CAD and mesh interchange research geometry arrives in
        ".step",
        ".stp",
        ".iges",
        ".igs",
        ".sat",
        ".x_t",
        ".x_b",
        ".3dm",
        ".msh",
        ".cgns",
        ".ply",
        ".off",
        ".nas",
        ".bdf",
    }
)


SYNTHETIC_GEOMETRY_ALLOWLIST = {
    # Hand-written in the file's own header: a closed unit cube, 8 vertices and
    # 12 triangles, for the probe geometry gate. No research content possible.
    "tests/tier1_offline/fixtures/cube.obj",
    # VTK POLYDATA golden with two points at (0,0,0) and (1,0,0): an
    # output-FORMAT golden, not a geometry input.
    "tests/tier1_offline/goldens/planar_probes.vtk",
}


RECORDED_WAKE_PATH = "tests/tier1_offline/fixtures/p0400_lita_solver_wake.vtk"


RECORDED_WAKE_SHA256 = "156fc09059c485346ae83ea266a5c4418c488f2909a02d3c028bc6fe7c08dc8b"


RECORDED_WAKE_FIXTURES = {
    "tests/tier1_offline/fixtures/p0400_litB_wake_26124.vtk": (
        "7a0441d10c8fb78257049c3f5ed506f3f56e78968741a852eecf85c044725d50"
    ),
    "tests/tier1_offline/fixtures/p0400_litB_wake_26125.vtk": (
        "2d69e11aae83a0ccfc9ad0a01bfa7604f03c58d451a1173f7d2e47da41e167bf"
    ),
    "tests/tier1_offline/fixtures/p0400_litB_wake_26125_fine.vtk.xz": (
        "d1ab561feda76c8fa2b400df20b77832b5b07e5707ea2cb906d0ecd1f896c0ed"
    ),
}


SYNTHETIC_LIBRARY = "tests/tier3_licensed/inputs/geometries/"


def _read_tracked(path):
    """The bytes of one tracked path, or None when it is not on disk."""
    target = REPO_ROOT / path
    return target.read_bytes() if target.is_file() else None


def _provenance_admits(fsm_bytes, record_bytes):
    """Whether a provenance record admits the saved simulation beside it.

    The record must parse as TOML, name the generator and the build, and
    carry the sha256 of the file's own bytes; a record that exists and says
    nothing, or says it of another file, admits nothing (review of
    2026-09-08: the guard used to admit on the sidecar's existence alone).
    """
    import hashlib
    import tomllib

    if fsm_bytes is None or record_bytes is None:
        return False
    try:
        record = tomllib.loads(record_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    for key in ("generator", "build", "sha256"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            return False
    return record["sha256"].strip().lower() == hashlib.sha256(fsm_bytes).hexdigest()


def _geometry_offenses(relative_posix_paths, read=_read_tracked):
    """Tracked paths carrying a geometry extension without an allowlist entry.

    Factored out so the tree scan and the mutation proof run the SAME code,
    for the reason ``_names_the_author`` states above. ``read`` returns the
    bytes of a path, so the mutation proof can hand the guard a record
    whose content it controls.
    """
    paths = list(relative_posix_paths)
    tracked = set(paths)

    def provably_synthetic(path):
        if path == RECORDED_WAKE_PATH:
            data = read(path)
            return (
                isinstance(data, bytes) and hashlib.sha256(data).hexdigest() == RECORDED_WAKE_SHA256
            )
        if path in SYNTHETIC_GEOMETRY_ALLOWLIST:
            return True
        if path in RECORDED_WAKE_FIXTURES:
            data = read(path)
            return (
                data is not None
                and hashlib.sha256(data).hexdigest() == RECORDED_WAKE_FIXTURES[path]
            )
        if path.startswith(SYNTHETIC_LIBRARY) and path.lower().endswith(".fsm"):
            record = path[: -len(".fsm")] + ".provenance.toml"
            return record in tracked and _provenance_admits(read(path), read(record))
        return False

    return sorted(
        path
        for path in paths
        if (path in RECORDED_WAKE_FIXTURES or Path(path).suffix.lower() in GEOMETRY_SUFFIXES)
        and not provably_synthetic(path)
    )


@pytest.mark.requirement("NFR-14")
def test_no_geometry_file_is_tracked_outside_the_synthetic_allowlist():
    """NFR-14. Research geometry entering Git is the irreversible breach.

    Irreversible is meant literally: a push publishes it, and removing it
    from HEAD afterwards does not unpublish it from any clone, fork or
    mirror that already fetched. So the guard runs on every tracked path,
    all extensions, and fails loudly rather than skipping.
    """
    offenders = _geometry_offenses(
        str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()
    )
    assert not offenders, (
        "these tracked files carry a geometry or mesh extension and are not in "
        "the synthetic-fixtures allowlist:\n"
        + "\n".join(offenders)
        + "\n\nResearch geometry never enters this repository (CONTRIBUTING.md "
        "invariant 5, SRS NFR-08 and NFR-14). Keep it in _private/ or in the "
        "research workspace and reference it from a local QA run. If the file "
        "really is synthetic, generate it from pyflightstream.qa.geometry "
        "instead of committing it, or add it to SYNTHETIC_GEOMETRY_ALLOWLIST "
        "with the reason it cannot carry research content."
    )


def test_the_geometry_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    Runs the DETECTOR against the exact case measured red above, plus the
    live tree, so the proof is about the scan and not about ``str.endswith``.
    """
    leak = "examples/leaked_blade.stl"
    assert _geometry_offenses([leak]) == [leak], (
        "the detector does not fire on a mesh committed under examples/, which "
        "is the case measured passing the whole suite before this guard existed"
    )
    # Every allowlisted path must be recognised as allowlisted, or the entry is
    # dead and the file it names is unguarded by accident rather than decision.
    assert _geometry_offenses(sorted(SYNTHETIC_GEOMETRY_ALLOWLIST)) == []
    # The allowlist must not be a list of paths that no longer exist: a stale
    # entry silently widens the exemption for whatever later takes that name.
    tracked = {str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()}
    stale = sorted(SYNTHETIC_GEOMETRY_ALLOWLIST - tracked)
    assert not stale, (
        f"allowlisted paths {stale} are not tracked; remove the entry rather "
        "than leaving an exemption waiting for a future file of that name"
    )
    # And the guard must not be vacuous: a suffix outside the set is untouched.
    assert _geometry_offenses(["README.md", "examples/steady_polar.py"]) == []


def test_a_tier3_saved_simulation_is_admitted_only_with_its_provenance_record():
    """The library rule of GOAL-012: a ``.fsm`` under the tier-3 library is
    admitted with its provenance record tracked beside it, naming the generator
    and the build and carrying the file's own sha256, and refused without one,
    with an empty one, or with one whose digest is another file's; the same file
    anywhere else is refused with or without a record."""
    import hashlib

    fsm = SYNTHETIC_LIBRARY + "10_WING.fsm"
    record = SYNTHETIC_LIBRARY + "10_WING.provenance.toml"
    mesh = b"$MESH_START synthetic bytes $MESH_END"
    digest = hashlib.sha256(mesh).hexdigest()
    good = f'generator = "tests.tier3_licensed.recipes"\nbuild = "26.120"\nsha256 = "{digest}"\n'
    flipped = digest[:-1] + ("0" if digest[-1] != "0" else "1")

    def reader(files):
        return lambda path: files.get(path)

    assert _geometry_offenses([fsm, record], read=reader({fsm: mesh, record: good.encode()})) == []
    assert _geometry_offenses([fsm], read=reader({fsm: mesh})) == [fsm]
    assert _geometry_offenses([fsm, record], read=reader({fsm: mesh, record: b""})) == [fsm]
    other = good.replace(digest, flipped)
    assert _geometry_offenses([fsm, record], read=reader({fsm: mesh, record: other.encode()})) == [
        fsm
    ], "a record carrying another file's digest admits nothing"
    unsigned = good.replace(f'sha256 = "{digest}"\n', "")
    assert _geometry_offenses(
        [fsm, record], read=reader({fsm: mesh, record: unsigned.encode()})
    ) == [fsm]
    elsewhere = "tests/tier1_offline/fixtures/10_WING.fsm"
    assert _geometry_offenses(
        [elsewhere, "tests/tier1_offline/fixtures/10_WING.provenance.toml"],
        read=reader({elsewhere: mesh}),
    ) == [elsewhere]
    stl = SYNTHETIC_LIBRARY + "wing.stl"
    assert _geometry_offenses([stl, SYNTHETIC_LIBRARY + "wing.provenance.toml"]) == [stl]
    # And the live library: every committed saved simulation is admitted by
    # its own record read from disk, which is the digest check the records
    # were written for (prepare.py) and nothing read back until now.
    library = sorted(
        str(p.relative_to(REPO_ROOT).as_posix()) for p in (REPO_ROOT / SYNTHETIC_LIBRARY).glob("*")
    )
    assert any(p.endswith(".fsm") for p in library)
    assert _geometry_offenses(library) == []


SPREADSHEET_SUFFIXES = frozenset({".xlsx", ".xlsm", ".xlsb", ".xls", ".ods"})


SPREADSHEET_ALLOWLIST: frozenset[str] = frozenset()


def _spreadsheet_offenses(relative_posix_paths):
    """Tracked paths carrying a spreadsheet extension without an allowlist entry.

    Factored out so the tree scan and the mutation proof run the SAME code,
    for the reason ``_geometry_offenses`` states.
    """
    return sorted(
        path
        for path in relative_posix_paths
        if Path(path).suffix.lower() in SPREADSHEET_SUFFIXES and path not in SPREADSHEET_ALLOWLIST
    )


@pytest.mark.requirement("NFR-14")
def test_the_spreadsheet_hook_refuses_the_same_suffixes_as_the_suite():
    """The forbid-spreadsheets hook's ``files`` pattern and SPREADSHEET_SUFFIXES
    are one set: the comment on the set says they move together, and until the
    release review of 2026-09-09 nothing compared them."""
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook = config.split("- id: forbid-spreadsheets", 1)[1]
    pattern = re.search(r"files: '\(\?i\)\\\.\(([a-z|]+)\)\$'", hook)
    assert pattern is not None, (
        "the forbid-spreadsheets hook's files pattern is not the shape this test reads"
    )
    assert frozenset("." + s for s in pattern.group(1).split("|")) == SPREADSHEET_SUFFIXES


def test_no_spreadsheet_is_tracked_outside_the_allowlist():
    """OPS-2010.23. A spreadsheet in the public tree is opaque to review and may carry a mesh."""
    offenders = _spreadsheet_offenses(
        str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()
    )
    assert not offenders, (
        "these tracked files are spreadsheets and are not in SPREADSHEET_ALLOWLIST:\n"
        + "\n".join(offenders)
        + "\n\nA spreadsheet can carry the point coordinates of a proprietary mesh and "
        "no diff or review can see it (CONTRIBUTING.md invariant 5, SRS NFR-14, "
        "OPS-2010.23). Keep it in _private/ and commit the table as .csv, which is "
        "text a reader can check, or add the path to SPREADSHEET_ALLOWLIST with the "
        "reason it cannot carry research geometry."
    )


def test_the_spreadsheet_guard_fires_on_what_it_exists_to_catch(monkeypatch):
    """Mutation proof: the case measured passing every hook, and the guard's own control.

    The leak is refused; a mixed-case suffix is refused, since the hook
    lowercases nothing and the detector must; every allowlisted path is
    tracked; a `.csv` and a `.md` pass; and with the suffix set emptied, which
    is the tree before this guard, the same leak passes, so the refusal comes
    from the set and not from anything else in the scan.
    """
    leak = "examples/leaked_mesh_points.xlsx"
    assert _spreadsheet_offenses([leak]) == [leak], (
        "the detector does not fire on a spreadsheet committed under examples/, "
        "which is the case measured passing every pre-commit hook on 2026-09-08"
    )
    assert _spreadsheet_offenses(["docs/Blade.XLSM", "tools/table.ods"]) == [
        "docs/Blade.XLSM",
        "tools/table.ods",
    ]
    assert _spreadsheet_offenses(sorted(SPREADSHEET_ALLOWLIST)) == []
    tracked = {str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()}
    stale = sorted(SPREADSHEET_ALLOWLIST - tracked)
    assert not stale, (
        f"allowlisted paths {stale} are not tracked; remove the entry rather "
        "than leaving an exemption waiting for a future file of that name"
    )
    assert (
        _spreadsheet_offenses(
            ["tests/tier1_offline/fixtures/fsi/structural_nodes.csv", "README.md"]
        )
        == []
    )
    # The control: restore the defect (no suffix set) and the leak passes.
    monkeypatch.setitem(globals(), "SPREADSHEET_SUFFIXES", frozenset())
    assert _spreadsheet_offenses([leak]) == [], (
        "with the suffix set emptied the detector still fires, so the refusal "
        "above was not coming from the rule this test exists to prove"
    )


PDF_ALLOWED = re.compile(
    r"^guide/(pyfts-guide-0[1-9]-[a-z0-9-]+|pyflightstream_user_guide"
    r"|latex-sources/0[1-9]-[a-z0-9-]+/figures/[A-Za-z0-9_.-]+)\.pdf$"
)


PDF_SUFFIX = ".pdf"


PDF_RULE_SAMPLES = (
    "guide/pyfts-guide-01-fts-overview.pdf",
    "guide/pyfts-guide-02-workspaces.pdf",
    "guide/pyfts-guide-04-cheatsheet.pdf",
    "guide/pyfts-guide-09-python-environment-offline.pdf",
    "guide/pyfts-guide-0" + "0-fts-overview.pdf",
    "guide/latex-sources/02-workspaces/figures/qsteady_k_vs_J.pdf",
    "guide/pyfts-cheatsheet-pyfs-matrix.pdf",
    "guide/pyfts-cheatsheet-by-stage.pdf",
    "guide/pyfts-cheatsheet-other.pdf",
    "guide/latex-sources/cheatsheet/pyfts-cheatsheet-pyfs-matrix.pdf",
    "guide/pyflightstream_user_guide.tex",
    "guide/pyflightstream_user_guide.pdf",
    "guide/pyflightstream_user_guide_old.pdf",
    "x/guide/pyflightstream_user_guide.pdf",
    "guide/pyfts-guide-10-extra.pdf",
    "guide/fts-guide-01-workspaces.pdf",
    "guide/latex-sources/08-fsi/notes.pdf",
    "guide/latex-sources/08-fsi/figures/sub/deep.pdf",
    "x/guide/pyfts-guide-02-workspaces.pdf",
    "vendor/guide/latex-sources/01-a/figures/manual.pdf",
    "guide/notes.ipynb",
    "Guide/x.pdf",
    "docs/manual_26.124.pdf",
    "reports/Manual.PDF",
    "guide.pdf",
    "docs/guide/deck.pdf",
    "guides/deck.pdf",
    "README.md",
)


CI_REFUSES_AS_NO_PDF = frozenset({"guide/notes.ipynb"})


def _pdf_offenses(relative_posix_paths):
    """Tracked paths carrying a pdf extension that are not a deck's own pdf.

    Factored out so the tree scan, the mutation proof and the equivalence
    with the hook and CI run the SAME code.
    """
    return sorted(
        path
        for path in relative_posix_paths
        if Path(path).suffix.lower() == PDF_SUFFIX and not PDF_ALLOWED.search(path)
    )


@pytest.mark.requirement("FR-177")
@pytest.mark.requirement("NFR-03")
def test_no_pdf_is_tracked_outside_the_guide():
    """A pdf in the public tree is refused unless it is a guide deck or a deck's figure."""
    offenders = _pdf_offenses(
        str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()
    )
    assert not offenders, (
        "these tracked files are pdfs that are not a guide deck or its figure:\n"
        + "\n".join(offenders)
        + "\n\nA licensed manual arrives as a pdf and never enters the repository "
        "(CONTRIBUTING.md invariant 1, SRS NFR-03). Only the nine compiled guides "
        "(the cheatsheet is guide 04), guide/pyfts-guide-0N-*.pdf, the figures their "
        "sources include, guide/latex-sources/0N-*/figures/*.pdf, and the user guide, "
        "guide/pyflightstream_user_guide.pdf, are tracked as pdf."
    )


def test_the_pdf_guard_fires_on_what_it_exists_to_catch(monkeypatch):
    """Mutation proof: a pdf outside the decks is refused, a deck's is admitted,
    and each half comes from its own rule.

    With the exemption withdrawn the decks' own pdfs are refused too, so the
    admission comes from the exemption; with the suffix replaced by one no
    file carries, the leak passes, so the refusal comes from the suffix.
    The user guide's PDF the release publishes is admitted at its one path and
    refused at its near spellings (NFR-46).
    """
    leak = "docs/manual_26.124.pdf"
    assert _pdf_offenses([leak]) == [leak]
    assert _pdf_offenses(
        [
            "reports/Manual.PDF",
            "guide.pdf",
            "docs/guide/deck.pdf",
            "guides/deck.pdf",
            "Guide/x.pdf",
            "guide/pyflightstream_user_guide_old.pdf",
            "x/guide/pyflightstream_user_guide.pdf",
            "guide/pyfts-guide-10-extra.pdf",
            "guide/fts-guide-01-workspaces.pdf",
            "guide/latex-sources/08-fsi/notes.pdf",
            "guide/latex-sources/08-fsi/figures/sub/deep.pdf",
            "x/guide/pyfts-guide-02-workspaces.pdf",
            "vendor/guide/latex-sources/01-a/figures/manual.pdf",
            "guide/pyfts-cheatsheet-other.pdf",
            "guide/latex-sources/cheatsheet/pyfts-cheatsheet-pyfs-matrix.pdf",
        ]
    ) == [
        "Guide/x.pdf",
        "docs/guide/deck.pdf",
        "guide.pdf",
        "guide/fts-guide-01-workspaces.pdf",
        "guide/latex-sources/08-fsi/figures/sub/deep.pdf",
        "guide/latex-sources/08-fsi/notes.pdf",
        "guide/latex-sources/cheatsheet/pyfts-cheatsheet-pyfs-matrix.pdf",
        "guide/pyflightstream_user_guide_old.pdf",
        "guide/pyfts-cheatsheet-other.pdf",
        "guide/pyfts-guide-10-extra.pdf",
        "guides/deck.pdf",
        "reports/Manual.PDF",
        "vendor/guide/latex-sources/01-a/figures/manual.pdf",
        "x/guide/pyflightstream_user_guide.pdf",
        "x/guide/pyfts-guide-02-workspaces.pdf",
    ]
    admitted = [
        "guide/pyfts-guide-01-fts-overview.pdf",
        "guide/pyfts-guide-02-workspaces.pdf",
        "guide/latex-sources/02-workspaces/figures/qsteady_k_vs_J.pdf",
        "guide/pyfts-guide-04-cheatsheet.pdf",
        "guide/pyflightstream_user_guide.pdf",
        "README.md",
    ]
    assert _pdf_offenses(admitted) == []
    # Control 1: withdraw the exemption and the decks' pdfs are refused.
    monkeypatch.setitem(globals(), "PDF_ALLOWED", re.compile(r"(?!)"))
    assert _pdf_offenses(admitted) == sorted(admitted[:5]), (
        "with the exemption withdrawn the decks' pdfs still pass, so their "
        "admission above was not coming from the exemption"
    )
    monkeypatch.undo()
    # Control 2: replace the suffix by one no file carries and the leak passes,
    # so its refusal above came from the suffix test.
    monkeypatch.setitem(globals(), "PDF_SUFFIX", "\0")
    assert _pdf_offenses([leak, "reports/Manual.PDF"]) == [], (
        "with the suffix test matching nothing the leak is still refused, so its "
        "refusal above was not coming from the suffix"
    )


@pytest.mark.requirement("NFR-03")
def test_the_pdf_hook_and_the_ci_guard_admit_exactly_what_the_suite_admits():
    """The forbid-pdf hook, the CI guard job and `_pdf_offenses` are one rule."""
    import yaml

    config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [hook for repo in config["repos"] for hook in repo.get("hooks", ())]
    (hook,) = [hook for hook in hooks if hook["id"] == "forbid-pdf"]
    files, exclude = re.compile(hook["files"]), re.compile(hook.get("exclude", "(?!)"))

    def hook_refuses(path: str) -> bool:
        # pre-commit matches `files` and `exclude` with re.search on the path.
        return bool(files.search(path)) and not exclude.search(path)

    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    line = next(text for text in ci.splitlines() if "git ls-files | grep -E" in text)
    patterns = re.findall(r"grep -E(i?)(v?) '([^']+)'", line)
    # The keep-grep is case-insensitive (a `.PDF` is a pdf); the drop-grep, the
    # exemption, is case-sensitive (a `Guide/` folder is not the guide).
    assert [(case, invert) for case, invert, _ in patterns] == [("i", ""), ("", "v")], (
        f"the CI guard line is not the two-grep shape this test reads: {line.strip()}"
    )
    keep, drop = (
        re.compile(pattern, re.IGNORECASE if case else 0) for case, _, pattern in patterns
    )

    def ci_refuses(path: str) -> bool:
        return bool(keep.search(path)) and not drop.search(path)

    suite = set(_pdf_offenses(PDF_RULE_SAMPLES))
    assert {path for path in PDF_RULE_SAMPLES if hook_refuses(path)} == suite
    assert {path for path in PDF_RULE_SAMPLES if ci_refuses(path)} == suite | CI_REFUSES_AS_NO_PDF


CONTAINER_DIRECTORY = "".join(
    map(chr, (67, 108, 97, 117, 100, 101, 80, 114, 111, 106, 101, 99, 116, 115))
)


def _container_offenders(entries: Iterable[tuple[str, str]]) -> list[str]:
    """Return which of ``(relative_path, text)`` name the container directory.

    Takes its input rather than reading the tree, so the detector can be
    driven with synthetic content. That is not a style preference: the
    first version read `_tracked_files()` itself, which left its
    "mutation proof" with nothing to drive and no way to fail. The
    geometry detector next door was already written this way.
    """
    return [relative for relative, text in entries if CONTAINER_DIRECTORY in text]


def _tracked_text() -> list[tuple[str, str]]:
    """Every tracked file as ``(relative_path, text)``.

    A file that cannot be decoded is yielded as an EMPTY string rather
    than skipped, so the detector sees one entry per tracked file and a
    future binary-with-a-literal cannot vanish between the two.
    """
    entries = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        entries.append((path.relative_to(REPO_ROOT).as_posix(), text))
    return entries


def test_no_tracked_file_names_the_container_directory():
    """A path into the workspace container is machine configuration.

    CONTRIBUTING.md states the rule ("never a literal path in a committed file") and
    until now only prose held it for this shape. The remote is public, so the
    literal names the author's machine layout to everyone who clones.
    """
    offenders = _container_offenders(_tracked_text())
    assert not offenders, (
        "these tracked files carry an absolute path into the workspace "
        "container, which is machine configuration and belongs in a gitignored "
        "local settings file:\n" + "\n".join(offenders)
    )


def test_the_container_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    The DETECTOR is driven, which the first version of this test did not
    do: it compared a constant against strings built from that constant,
    so the detector could have returned an empty list unconditionally and
    every assertion would still have passed. Caught by the QA pass of
    2026-08-03, and the repair is the seam rather than more assertions.

    Run against the shapes actually found in the two vendored bodies,
    reconstructed here rather than quoted, plus the illustrative solver
    paths that must NOT fire: a guard that also refuses
    `C:/cases/wing.fsm` would be turned off within a week.
    """
    leaks = (
        "/c/WORK/" + CONTAINER_DIRECTORY + "/pyflightstream/_private",
        "C:" + "/WORK/" + CONTAINER_DIRECTORY + "/_private/kit/check_plan_kit.py",
        "C:" + chr(92) + "WORK" + chr(92) + CONTAINER_DIRECTORY,
    )
    for leak in leaks:
        assert _container_offenders([("some/file.sh", leak)]) == ["some/file.sh"], leak
    for benign in (
        "C:/cases/wing.fsm",
        "C:/path/to/FlightStream.exe",
        "D:/scratch",
        "/w/wing.stl",
    ):
        assert _container_offenders([("examples/x.py", benign)]) == [], (
            f"the guard fires on the illustrative path {benign!r}, which is "
            "documentation and must stay"
        )
    # NO ENTRY IS EXEMPT, and this is the assertion that replaced the
    # exemption witness when the allowlist went. The same leak under the
    # two paths that used to be excused must now be reported, so a
    # reinstated exemption cannot pass for a clean tree.
    for once_excused in ("tools/snap.sh", "tools/check_plan_kit_mutations.py"):
        assert _container_offenders([(once_excused, leaks[0])]) == [once_excused], (
            f"{once_excused} is not judged by the container guard, so an "
            "exemption has come back; every tracked file is inside this rule"
        )

    # And the live scan must see a plausible number of files, or the
    # tree walk could be empty while every assertion above passes.
    entries = _tracked_text()
    assert entries


_INVISIBLE = frozenset(
    chr(code)
    for code in (
        0x7F,
        0x85,
        0xA0,
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,
        0x2028,
        0x2029,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2060,
        0xFEFF,
        *range(0x80, 0xA0),
    )
)


def test_no_tracked_text_file_carries_a_control_byte():
    """A backspace in a regex spent a guard and nothing could see it.

    On 2026-08-10 a raw string meant to read `\b` was written through a
    shell heredoc and reached the file as byte 0x08. The pattern then
    required a literal backspace, the helper it powered returned the
    empty set, and two assertions built on it stopped asserting: one
    loop ran zero iterations and one set difference was empty minus
    anything. The suite stayed green while seven of eight editions could
    go silent in the published coverage section.

    NOTHING COULD SEE IT BY READING. Editors, diffs and the tools used
    to review this repository all render 0x08 as nothing at all, so the
    line looked correct in every view anyone had of it. Four more of the
    same byte were then found in a second file, from the same cause, and
    one deliberate 0x1f that was functional and indistinguishable from
    the accident.

    Tab, newline and carriage return are the three that belong in text.
    Everything else is written as an escape, which is visible.

    THE FIRST VERSION OF THIS GUARD CHECKED BYTES BELOW 32 ONLY, and a
    reviewer got the same defect past it with a zero-width space: put
    U+200B where the escape belongs and the pattern matches nothing, the
    helper returns the empty set, two assertions go silent, and the
    suite is green. It encodes as three bytes above 127, so a byte
    threshold cannot see it. The set below is every codepoint this
    workflow renders as nothing: the C0 controls, delete, the C1 range,
    the invisible spaces and the direction marks.

    The file list is a BINARY denylist rather than a text allowlist, for
    the same reason: an allowlist scans the extensions somebody thought
    of, so thirteen tracked text files including every golden and
    fixture that is not .txt or .yaml went unscanned by the first
    version.
    """
    offenders = []
    # .fsm: the tier-3 library's saved simulations are the solver's own bytes,
    # pinned binary in .gitattributes and admitted only with a provenance
    # record (SYNTHETIC_LIBRARY); a control byte there is the format, not a leak.
    binary_suffixes = {".obj", ".pdf", ".png", ".jpg", ".ico", ".stl", ".whl", ".gz", ".xz", ".fsm"}
    for path in _tracked_files():
        if path.suffix.lower() in binary_suffixes:
            continue
        raw = path.read_bytes()
        found = sorted({byte for byte in raw if byte < 32 and byte not in (9, 10, 13)})
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        invisible = sorted({char for char in text if char in _INVISIBLE})
        if found or invisible:
            names = [hex(byte) for byte in found]
            names += [f"U+{ord(char):04X}" for char in invisible]
            offenders.append(f"{path}: {', '.join(names)}")
    assert not offenders, (
        "these tracked files carry a control byte, which every editor and diff in "
        "this workflow renders as nothing: " + "; ".join(offenders) + ". Write it as "
        r"an escape (\b, \x1f) so the character is visible to a reader"
    )
