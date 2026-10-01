"""The public tree carries no identity of a user's machine (NFR-31).

The solver build identifies the executable (FlightStream 26.124 is build
8172026); the SHA-256 of the executable a run used stays in that run's record
on the machine that ran it, and so do the folders it ran in. This guard reads
every tracked text file and refuses three shapes:

1. A labelled executable digest: a 64-hex token on a line that names the
   executable (``fs_exe_sha256``, ``exe_sha256``, ``executable_sha256``, an
   ``.exe`` file name, the word executable), on the line after one that ends
   with such a label (wrapped prose), inside a YAML or JSON block whose key is
   such a label, or in a Markdown table column whose header is one. Any build,
   any machine: the value is refused for where it stands, not for what it is.
2. A withheld digest anywhere, compared by the SHA-256 of its lowercase form so
   this file never carries the value it refuses.
3. An absolute user path: a user-profile folder, a home folder, a OneDrive
   folder, or the work and estate roots of a measuring machine.

A digest-shaped value made of one repeated hexadecimal digit (``"a" * 64``) is
synthetic by rule and allowed: tests and fixtures that need a digest use one.

Mutant controls plant each shape in a temporary copy of a tracked file: a
different token under a label (not the 26.124 digest), a different token
against a patched withheld set, and a user path. The unmutated copy passes and
each planted copy is found.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: SHA-256 (of the lowercase token, UTF-8) of each digest the public tree
#: withholds: the ten builds of the executable identity baseline, 25.000 to
#: 26.124. The digests themselves are never written here.
WITHHELD_DIGESTS = frozenset(
    {
        "2316d59888942ed9ce01dc656d2c61de365c4daae30ca55bbe3c57d2fe85800d",
        "42f63d164271431954068274544e2fdf273c9cb8eaff995d4cfb6646020dded5",
        "b09f780454419cc68338d2210c4ca51a158bac0bdf37c942a4f8b4b3e27fc905",
        "8ff9c8a07a5467d7921100281caaa84485007adaafffb7926e2c72e3c10ac6d3",
        "ce68a962ee79d381475cf78c3e5ce7c18eb30cb7a16e42a3daa36853a617bbb0",
        "c39ea52db23d3e22a5cb61aed41afd416bf5c3c34b05cca538fe262a7c65c349",
        "d543ff7ba6fe6e5307b6ccf0225a7ae8e85861faf992f10d841f889a91f60580",
        "5dfd4fca878a9b865e6df63cb7a33003c0afe45044876e0baf20460549f7f852",
        "2e926aec3467955ed8cf3569cf201270e7228c79e5cc7605d94874d1fe1cb2ab",
        "9befdea3801ebe353c647118c0f5c33ec9462215cb59475744bce3bb2905ed50",
    }
)

#: A run of hexadecimal characters at least one digest long. A longer run is
#: scanned at every offset, so a digest glued to other hex is still found.
HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")
#: A standalone 64-hex token, the shape a labelled digest takes.
HEX_TOKEN = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
#: What names the executable: a field such as fs_exe_sha256, exe_sha256 or
#: executable_sha256, an .exe file name, or the word executable.
LABEL = re.compile(r"(?i)(?:\bexe\b|_exe\b|\bexe_|\.exe\b|executable|fs_exe)")
#: A YAML or JSON key that opens a block (``key:`` or ``"key": {``).
BLOCK_KEY = re.compile(r"""^(\s*)["']?([A-Za-z0-9_.-]+)["']?\s*:\s*[{\[]?\s*$""")
#: Absolute user paths: a profile folder, a home folder, a OneDrive folder, and
#: the work and estate roots of a measuring machine, in either separator.
USER_PATH = re.compile(
    r"(?i)(?:[/\\]users[/\\][a-z0-9._-]+"
    r"|(?<![\w.])/home/[a-z_][\w.-]*"
    r"|[/\\]onedrive(?:[ -][^/\\\n]*)?[/\\]"
    r"|\b[a-z]:[/\\]{1,2}(?:work|geoversegoddess)[/\\]+[\w.<-]"
    r"|(?<![\w.])/[a-z]/(?:work|geoversegoddess)/[\w.<-])"
)

#: Fewer files read than this means the scan did not see the tree.
FILES_READ_FLOOR = 1000


def _tracked() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (
        f"git could not list the tracked files (exit {result.returncode}: "
        f"{result.stderr.strip()}); an unscanned tree must not read as a clean one"
    )
    return [ROOT / name for name in result.stdout.split("\0") if name]


def _synthetic(token: str) -> bool:
    return len(set(token.lower())) == 1


def _withheld(text: str) -> list[str]:
    digests = sys.modules[__name__].WITHHELD_DIGESTS
    found = []
    for run in HEX_RUN.finditer(text):
        value = run.group().lower()
        for start in range(len(value) - 63):
            token = value[start : start + 64]
            if hashlib.sha256(token.encode("utf-8")).hexdigest() in digests:
                found.append(f"a withheld digest at offset {run.start() + start}")
    return found


def _table_columns(line: str) -> set[int]:
    cells = line.strip().strip("|").split("|")
    return {index for index, cell in enumerate(cells) if LABEL.search(cell)}


def _labelled(text: str) -> list[str]:
    found = []
    lines = text.splitlines()
    block: int | None = None
    header: set[int] | None = None
    for number, line in enumerate(lines, start=1):
        indent = len(line) - len(line.lstrip())
        if block is not None and line.strip() and indent <= block:
            block = None
        key = BLOCK_KEY.match(line)
        if key and LABEL.search(key.group(2)):
            block = len(key.group(1))
        is_row = line.lstrip().startswith("|")
        if not is_row:
            header = None
        elif header is None:
            header = _table_columns(line)
        previous = lines[number - 2][-60:] if number > 1 else ""
        for match in HEX_TOKEN.finditer(line):
            if _synthetic(match.group()):
                continue
            column = line[: match.start()].count("|") - 1 if is_row else -1
            if (
                LABEL.search(line)
                or LABEL.search(previous)
                or block is not None
                or (header is not None and column in header)
            ):
                found.append(f"an executable digest on line {number}")
    return found


def _user_paths(text: str) -> list[str]:
    return [f"a user path ({match.group()})" for match in USER_PATH.finditer(text)]


def scan(paths: list[Path]) -> tuple[list[str], int]:
    """Return one line per offending file, and how many text files were read."""
    offenders, read = [], 0
    for path in paths:
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue  # binary
        read += 1
        text = data.decode("utf-8", errors="ignore")
        found = _withheld(text) + _labelled(text) + _user_paths(text)
        if found:
            offenders.append(f"{path.as_posix()}: {'; '.join(found)}")
    return offenders, read


def _names(offenders: list[str]) -> list[str]:
    return [Path(line.split(": ", 1)[0]).name for line in offenders]


def test_no_tracked_text_file_carries_a_machine_identity():
    # P0330-NO-EXE-HASH: every tracked text file, scanned for the three shapes.
    offenders, read = scan(_tracked())
    assert read >= FILES_READ_FLOOR, (
        f"the scan read {read} tracked text files, below the floor of {FILES_READ_FLOOR}; "
        "a scan that reads nothing reports green over an unscanned tree"
    )
    assert offenders == [], (
        "these tracked files identify a user's machine (NFR-31):\n"
        + "\n".join(offenders)
        + "\nState the solver build instead of an executable digest (a digest field reads "
        "'withheld; build <build>'), a path inside the run's workspace instead of an "
        "absolute one, and use one repeated hex digit for a synthetic digest"
    )


def test_a_labelled_digest_of_any_build_is_found(tmp_path):
    # P0330-NO-EXE-HASH: mutant control, a non-26.124 token under each label form.
    token = hashlib.sha256(b"P0330-NO-EXE-HASH another build").hexdigest()
    assert hashlib.sha256(token.encode()).hexdigest() not in WITHHELD_DIGESTS
    source = ROOT / "reports" / "RPT-032_executable-identity-baseline_2026-08-19.md"
    text = source.read_text(encoding="utf-8")
    clean = tmp_path / "clean.md"
    clean.write_text(text, encoding="utf-8")
    assert scan([clean]) == ([], 1)
    planted = {
        "row.md": text.replace("withheld; build 8112026", f"`{token}`", 1),
        "field.yaml": f"fs_version: '26.122'\nfs_exe_sha256: {token.upper()}\n",
        "block.yaml": f"executable_sha256:\n  '26.100': {token}\n",
        "block.json": f'{{\n "exe_sha256": {{\n  "26.101": "{token}"\n }}\n}}\n',
        "prose.md": f"on build 8092026, executable SHA-256\n`{token}`, serially.\n",
        "table.md": f"| Version | Executable SHA-256 |\n|---|---|\n| 26.121 | {token} |\n",
        "code.py": f'ProbeRun(fs_exe_sha256="{token}")\n',
    }
    paths = [clean]
    for name, body in planted.items():
        paths.append(tmp_path / name)
        paths[-1].write_text(body, encoding="utf-8")
    offenders, read = scan(paths)
    assert read == 1 + len(planted)
    assert _names(offenders) == list(planted)


def test_a_withheld_digest_is_found_anywhere_by_its_own_digest(tmp_path, monkeypatch):
    # P0330-NO-EXE-HASH: mutant control, an unlabelled token against a patched set.
    token = hashlib.sha256(b"P0330-NO-EXE-HASH planted control").hexdigest()
    monkeypatch.setattr(
        sys.modules[__name__],
        "WITHHELD_DIGESTS",
        frozenset({hashlib.sha256(token.encode("utf-8")).hexdigest()}),
    )
    bare = tmp_path / "bare.txt"
    bare.write_text(f"a = {token.upper()}\n", encoding="utf-8")
    glued = tmp_path / "glued.txt"
    glued.write_text(f"ab{token}cd\n", encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text(f"a = {hashlib.sha256(b'unrelated').hexdigest()}\n", encoding="utf-8")
    offenders, read = scan([bare, glued, other])
    assert read == 3 and _names(offenders) == ["bare.txt", "glued.txt"]


def test_a_user_path_is_found_and_an_illustrative_path_is_not(tmp_path):
    # P0330-NO-EXE-HASH: mutant control, user paths against example paths.
    users, drive = "Users", "One" + "Drive"
    leaks = (
        "C:" + chr(92) + users + chr(92) + "someone" + chr(92) + "x.fsm",
        "/" + "home/someone/runs",
        "D:/sync/" + drive + " - Personal/runs",
        "C:/" + "WORK/release/probes/round1/README.md",
        "C:" + chr(92) + "work" + chr(92) + "camp",
        "/c/" + "WORK/release",
    )
    for index, leak in enumerate(leaks):
        path = tmp_path / f"leak{index}.md"
        path.write_text(f"files are `{leak}`\n", encoding="utf-8")
        assert len(scan([path])[0]) == 1, leak
    benign = tmp_path / "benign.md"
    benign.write_text(
        "C:/cases/wing.fsm, C:/path/to/FlightStream.exe, D:/scratch, <workspace>/runs.json, "
        "https://example.org/home/x, " + '"C:/' + 'WORK/" + name\n',
        encoding="utf-8",
    )
    assert scan([benign]) == ([], 1)


def test_a_synthetic_digest_of_one_repeated_digit_is_allowed(tmp_path):
    # P0330-NO-EXE-HASH: the rule's one allowance, stated and exercised.
    path = tmp_path / "fixture.json"
    path.write_text('{"executable_sha256": "' + "a" * 64 + '"}\n', encoding="utf-8")
    assert scan([path]) == ([], 1)


def test_the_guard_carries_no_withheld_digest_itself():
    # P0330-NO-EXE-HASH: the guard's own source holds only digests of digests.
    own = Path(__file__).read_text(encoding="utf-8")
    assert _withheld(own) == [] and _labelled(own) == [] and _user_paths(own) == []
    assert all(len(value) == 64 for value in WITHHELD_DIGESTS)
