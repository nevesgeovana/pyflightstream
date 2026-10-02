"""The byte snapshot of the post stage's products (P0330-PRODUCTS-SNAPSHOT, AD-13).

WHY THIS EXISTS. Work package WP5 of 0.33.0 moves the product families out of
``post/products.py`` into sibling modules and cuts ``_sim_products`` into
steps over one context. Every product a user holds is a file whose bytes are
the contract: the order of the manifest's keys, the order of the log's
records, every digit of every CSV. A move that reorders one write or drops
one skip changes those bytes, and a behaviour test that asserts on a column
would not see it. So the bytes of the products of a set of recorded offline
campaigns were stored BEFORE the first move, and this module regenerates
them and compares.

WHAT IS STORED, under ``fixtures/products_snapshot/<campaign>/``:
``products.json``, ``post.log`` and ``post.log.json`` as text, and
``sha256.json``, the SHA-256 of EVERY file under the campaign's ``post/``
folder by its relative path. The campaigns are the offline campaigns the
tier-1 suite already builds from its recorded exports (``fixtures/``) and
its recorded data (``data/``): each entry of :data:`CAMPAIGNS` names the
test module whose builder it reuses, so a campaign here is one a behaviour
test already pins.

WHAT IS NORMALISED, and only this, on both sides (:func:`normalise`): the
wall-clock stamp of each log record (the one difference the parity script
measured between two posts of one workspace), the temporary folder the
campaign was built in and the separator of a path inside it, the package
version and the release tag derived from it, the wall-clock name of an
archive folder a rebuild moves the replaced products into, and the date line
of the custom polar format (the wall clock again). One campaign leaves out
files no normalisation makes stable (:data:`VOLATILE`, with its reason).
Nothing else may differ.

WHAT IS PINNED, because it is an input of the build rather than a field of a
product (:func:`pin_environment`): the line end of a text write, whose bytes
the products digest, and the operator's name, which a run records. The
snapshot was first stored on Windows; run on Linux it differed by these two
and by the separator, and by nothing else (measured 2026-10-01).

THE LINE ENDS ARE JUDGED, NOT PINNED (NFR-32, 0.34.0). The post runs with text
mode forced to write CRLF (:func:`crlf_text_mode`), so a writer that bypasses
the LF route fails the comparison on Linux as it would on Windows, and the
receipt counts the files that hold a CR (``cr_files``, which must be 0) and
names the platform it was made on (``platforms``); the two platforms' receipts
are the two runs of the ``ci.yml`` matrix.

Also ``.gitattributes``: the stored texts are pinned to LF like the goldens.

THE CONTROL. A comparator that cannot see a difference would pass any
refactoring, so :func:`snapshot_receipt` plants three differences into a
regenerated tree (one changed byte of a product, a product removed, a
product added) and requires the comparison to catch each:
``caught 3 of 3``. Those prove the comparison only, so a second control
changes BEHAVIOUR (:func:`behaviour_differences`): one campaign is posted
with a probe value shifted in the code the products are written from, and
its probes table must differ. ``scripts/products_snapshot.py`` writes that receipt
for the goal arm; ``--write`` there regenerates the stored snapshot, which
is done only when a release changes a product on purpose and names it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
import tempfile
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

SNAPSHOT_DIR = Path(__file__).parent / "fixtures" / "products_snapshot"
#: The files stored as text beside the digests.
TEXT_FILES = ("products.json", "post.log", "post.log.json")
DIGESTS = "sha256.json"
_STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:[+-]\d\d:\d\d|Z)?"
#: The folder a rebuild archives the products it replaces into, named by the
#: wall clock (``workspace.naming.ARCHIVE_STAMP``), in a path or in a text.
_ARCHIVE = re.compile(r"(?<=archive/)\d{8}-\d{6}(?=/)")

Builder = Callable[[Path, pytest.MonkeyPatch], Path]


def _post(workspace, **options) -> Path:
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.post.products import write_campaign_products

    with warnings.catch_warnings(), crlf_text_mode():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace, **options)
    return Path(workspace.root)


def _steady_provenance(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_post_products import _steady_workspace_with_provenance

    return _post(_steady_workspace_with_provenance(tmp))


def _unsteady_rotor(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_post_products import ROTOR_PLAN, _unsteady_workspace

    return _post(_unsteady_workspace(tmp, reductions=ROTOR_PLAN))


def _transition_row(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_post_products import TWO_ROTOR_PLAN, _unsteady_workspace

    return _post(_unsteady_workspace(tmp, reductions=TWO_ROTOR_PLAN))


def _windowed(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_post_products import _windowed_workspace

    window = {
        "stated_form": "iterations",
        "stated_value": 3.0,
        "first_step": 3,
        "time_iterations": 5,
        "delta_time_s": 0.01,
        "step_deg": 30.0,
    }
    return _post(_windowed_workspace(tmp, window=window))


def _superfile(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_post_superfile import _workspace

    return _post(_workspace(tmp), matrix_stem="matriz", overwrite=True)


def _named_groups(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal026_item14_named_groups import _named_workspace

    return _post(_named_workspace(tmp), matrix_stem="matriz", overwrite=True)


def _layout_with_plots(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_products_layout import MATRIX, _workspace

    return _post(_workspace(tmp, plots=True), matrix_stem=MATRIX)


def _frozen_rotor(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_b01_frozen_solve import _post_workspace

    workspace = _post_workspace(tmp, 2413, (60, 61), rotor=True)
    return _post(workspace, matrix_stem="products", check_frozen=True)


def _healthy_rotor(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_b01_frozen_solve import _post_workspace

    workspace = _post_workspace(tmp, 2411, (60, 61), rotor=True)
    return _post(workspace, matrix_stem="products")


def _frozen_window(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_b01_frozen_solve import _post_workspace

    return _post(_post_workspace(tmp, 2413, (58, 59)), check_frozen=True)


def _wheel_sections(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal036_wheel_sections import _campaign

    workspace, _ = _campaign(tmp, mp)
    return Path(workspace.root)


def _wheel_harmonics(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal036_harmonics import _wheel

    return _post(_wheel(tmp, mp, blades=6, clockings=2, rpm=1200.0))


def _unsteady_harmonics(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal036_harmonics import _unsteady

    return _post(_unsteady(tmp, mp, blades=3, rpm=-1200.0))


def _qsteady_correction(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal036_qsteady_corrections import (
        _recorded_wheel,
        _zero_p_calibration,
    )

    extra = '\n[qsteady_correction]\nroute = "table"\nfile = "c001"\n'
    files = {"c001.toml": _zero_p_calibration()}
    workspace = _recorded_wheel(tmp, pproc_extra=extra, files=files)
    return _post(workspace, matrix_stem="matriz", overwrite=True)


def _noise(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_p0320_noise_post import _unsteady_rotor_workspace

    return _post(_unsteady_rotor_workspace(tmp, listed=True), overwrite=True)


def _per_revolution(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal036_per_revolution import FX, _workspace

    return _post(_workspace(tmp, FX))


def _per_revolution_rotor(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal036_per_revolution import ROTOR, _rotor_workspace

    return _post(_rotor_workspace(tmp, ROTOR), overwrite=True, archive=True)


def _submitted_series(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal028_series import _submitted_workspace

    return _post(_submitted_workspace(tmp))


def _section_distributions(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_f07_section_distributions import _workspace

    workspace, _ = _workspace(tmp, mp, stamped=True)
    return _post(workspace)


def _probe_source(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_f01_probe_source import _post_workspace

    return _post(_post_workspace(tmp, mp))


def _legacy_probes(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_f01_probe_source import _post_workspace

    return _post(_post_workspace(tmp, mp, legacy=True, drawn=True, plots=True))


def _steady_probes(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_f01_probe_source import _post_workspace

    return _post(_post_workspace(tmp, mp, steady=True))


def _continuation(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_fr96_converged_continuation import _continued_workspace

    return _post(_continued_workspace(tmp, "whole march"), overwrite=True)


def _phase_locked_table(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_goal028_pproc_tables import _workspace

    pproc = "\n[phase_locked]\nmin_revolutions = 3.0\nlast_revolutions_avg = 2.0\n"
    return _post(_workspace(tmp, pproc))


def _additional(tmp: Path, mp: pytest.MonkeyPatch) -> Path:
    from tests.tier1_offline.test_additional_post import (
        POST_ADDITIONAL_TOML,
        a_recorded_campaign,
        a_stub,
        extract,
    )

    workspace, matrix = a_recorded_campaign(tmp, additional=POST_ADDITIONAL_TOML)
    extract(workspace, matrix, a_stub(tmp))
    return _post(workspace, overwrite=True, archive=True, matrix_stem=matrix.stem)


#: Every recorded offline campaign of the snapshot, by name, and its builder.
CAMPAIGNS: dict[str, Builder] = {
    "steady_provenance": _steady_provenance,
    "unsteady_rotor": _unsteady_rotor,
    "transition_row": _transition_row,
    "windowed": _windowed,
    "superfile": _superfile,
    "named_groups": _named_groups,
    "layout_with_plots": _layout_with_plots,
    "frozen_rotor": _frozen_rotor,
    "healthy_rotor": _healthy_rotor,
    "frozen_window": _frozen_window,
    "wheel_sections": _wheel_sections,
    "wheel_harmonics": _wheel_harmonics,
    "unsteady_harmonics": _unsteady_harmonics,
    "qsteady_correction": _qsteady_correction,
    "noise": _noise,
    "per_revolution": _per_revolution,
    "per_revolution_rotor": _per_revolution_rotor,
    "submitted_series": _submitted_series,
    "section_distributions": _section_distributions,
    "probe_source": _probe_source,
    "legacy_probes": _legacy_probes,
    "steady_probes": _steady_probes,
    "continuation": _continuation,
    "phase_locked_table": _phase_locked_table,
    "additional": _additional,
}


#: A path inside the build folder after the folder itself became ``<ROOT>``: its
#: separators, one backslash in a text and two in a JSON string on Windows, one
#: slash elsewhere, up to the first character no path segment here carries.
_ROOTED_PATH = re.compile(r"<ROOT>((?:(?:\\\\|\\|/)[^\s\\/\"',;:()\[\]]+)+)")


def _posix_separators(match: re.Match[str]) -> str:
    return "<ROOT>" + re.sub(r"\\\\|\\", "/", match.group(1))


def normalise(name: str, data: bytes, root: Path) -> bytes:
    """Rewrite the volatile fields of one post file: stamps, the build folder, the version."""
    from pyflightstream import __version__
    from pyflightstream.post.superfile import release_tag

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    # No line end is rewritten: the build writes LF in text mode on every
    # platform (pin_environment), so a CRLF here is one a product chose.
    for form in {str(root), root.as_posix(), json.dumps(str(root))[1:-1]}:
        text = text.replace(form, "<ROOT>")
    # The separator of a path inside the build folder: a message names a file
    # of the workspace through ``str(path)``, which is ``os.sep`` (a backslash
    # on Windows, doubled inside a JSON string). Measured on ubuntu-latest,
    # 2026-10-01: every post.log, post.log.json and products.json that names
    # such a path differed by this and nothing else. Only the separators of a
    # path that starts at ``<ROOT>`` are rewritten, so the path's segments
    # (which file a message names) are still compared, and a backslash
    # anywhere else is kept.
    text = _ROOTED_PATH.sub(_posix_separators, text)
    text = text.replace(__version__, "<VERSION>")
    text = text.replace(f"-{release_tag(__version__)}.json", "-<TAG>.json")
    text = _ARCHIVE.sub("<STAMP>", text)
    if name.endswith(".dat"):
        # The custom polar format's date line (custom_polar.CUSTOM_DATE_FORMAT), the clock.
        text = re.sub(r"\b[A-Z][a-z]{2} [A-Z][a-z]{2} \d\d \d\d:\d\d:\d\d  \d{4}\b", "<DATE>", text)
    if name.endswith(("post.log", "post.log.json")):
        text = re.sub(rf"(?m)^time={_STAMP}(?=\r?$)", "time=<TIME>", text)
        text = re.sub(rf'"time": "{_STAMP}"', '"time": "<TIME>"', text)
    return text.encode("utf-8")


def post_files(root: Path) -> dict[str, bytes]:
    """Every file under ``root/post`` by its relative POSIX path, normalised."""
    post = root / "post"
    out = {}
    for path in sorted(post.rglob("*")):
        if path.is_file():
            name = path.relative_to(post).as_posix()
            out[_ARCHIVE.sub("<STAMP>", name)] = normalise(name, path.read_bytes(), root)
    return out


def digests(files: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}


@contextmanager
def _scratch() -> Iterator[Path]:
    folder = Path(tempfile.mkdtemp(prefix="pfs-"))
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


#: Files a campaign writes that no normalisation makes stable, by campaign, with why.
#: ``additional`` runs its matrix through the stub solver, so the provenance of each
#: run carries that run's wall clock and the digest of a script naming the build
#: folder; the provenance writer is not a family WP5 moves.
VOLATILE: dict[str, tuple[str, ...]] = {"additional": ("*provenance/*.prov.json",)}


#: The operator every build runs as (:func:`pin_environment`).
OPERATOR = "operator"
_OPERATOR_VARIABLES = ("LOGNAME", "USER", "LNAME", "USERNAME")


#: ``scripts/lf_products_check.py`` clears it on Windows, where text mode writes CRLF by itself.
FORCE_CRLF_IN_POST = True


def _crlf_text_writes(open_):
    """``open_`` with CRLF as the default line end of a text file opened to write: Windows's."""

    def opened(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, *a, **k):
        if newline is None and "b" not in mode and any(flag in mode for flag in "wax"):
            newline = "\r\n"
        return open_(file, mode, buffering, encoding, errors, newline, *a, **k)

    return opened


@contextmanager
def crlf_text_mode() -> Iterator[None]:
    """Run the post with text mode forced to write CRLF, as Windows does (NFR-32).

    THE POST IS THE PACKAGE'S, so it is the one stage run this way: a text
    write that states no line end gets CRLF here on every platform, and a
    write through ``pyflightstream._textio`` states LF and is untouched. A
    product that still holds a CR, or differs from the stored LF bytes, is
    therefore a writer that bypasses the route, on Linux as on Windows. The
    builders' own writes of the recorded inputs stay under the LF pin of
    :func:`pin_environment`, which is the test's input and not a product.
    """
    import builtins
    import io

    if not FORCE_CRLF_IN_POST:
        yield
        return
    with pytest.MonkeyPatch.context() as patch:
        forced = _crlf_text_writes(io.open)
        patch.setattr(io, "open", forced)
        patch.setattr(builtins, "open", forced)
        yield


def _lf_text_writes(open_):
    """``open_`` with LF as the default line end of a text file opened to write."""

    def opened(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, *a, **k):
        if newline is None and "b" not in mode and any(flag in mode for flag in "wax"):
            newline = "\n"
        return open_(file, mode, buffering, encoding, errors, newline, *a, **k)

    return opened


def pin_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give a build the same environment on every platform: these are its INPUTS.

    Each pin, with the difference it removes (measured on ubuntu-latest and
    windows-latest against a snapshot stored on Windows, 2026-10-01):

    THE LINE END OF A TEXT WRITE IS LF. The builders write the campaign's
    recorded exports, records and calibration files with ``Path.write_text``,
    whose text mode writes CRLF on Windows and LF elsewhere, and the products
    RECORD THE SHA-256 OF THOSE INPUTS: each provenance file's
    ``pyfs:sha256`` of an output read from its file, and the corrected polars'
    and ``products.json``'s ``calibration_sha256``. A digest is a product
    value and is never rewritten, so the input it digests is made the same
    instead, as ``.gitattributes`` makes the committed fixtures LF on every
    checkout. Only the default is filled: a write that states its own line
    end (``newline=""`` for the CSV writer, or ``"\\r\\n"``) keeps it, so the
    line end a product chooses is still compared. The pin reaches this
    process only: the stub solver of the ``additional`` campaign runs as its
    own process and writes LF itself (``test_additional_post.a_stub``).

    THE OPERATOR IS :data:`OPERATOR`. A run records who ran it
    (``workspace.naming.submitted_by``, ``getpass.getuser`` over these
    variables), and the polars of the ``additional`` campaign carry it in
    ``submitted_by``: the owner's login where the snapshot was stored, the
    runner's in CI. The name is still written and compared; it is the same
    name everywhere.
    """
    import builtins
    import io

    lf_open = _lf_text_writes(io.open)
    monkeypatch.setattr(io, "open", lf_open)
    monkeypatch.setattr(builtins, "open", lf_open)
    for variable in _OPERATOR_VARIABLES:
        monkeypatch.setenv(variable, OPERATOR)


def regenerate(name: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Build and post one campaign and return its normalised post files.

    THE BUILD FOLDER IS NEUTRAL AND THE SAME SHAPE EVERYWHERE, never pytest's
    ``tmp_path`` nor a folder named for the campaign: a warning names the
    workspace path, and the post log's CATEGORY of a warning is a keyword match
    over its text (``post.diagnostics.warning_category``), so a folder called
    ``section_distributions`` turned a ``convergence`` record into a
    ``section-layout`` one. Measured on the first stored snapshot, 2026-10-01.

    The environment is pinned first (:func:`pin_environment`), so the build is
    the same on every platform the suite runs on.
    """
    pin_environment(monkeypatch)
    with _scratch() as scratch:
        root = CAMPAIGNS[name](scratch / "w", monkeypatch)
        volatile = VOLATILE.get(name, ())
        return {
            file: data
            for file, data in post_files(root).items()
            if not any(fnmatch.fnmatch(file, pattern) for pattern in volatile)
        }


def stored(name: str) -> tuple[dict[str, str], dict[str, str]]:
    """The stored digests and texts of one campaign."""
    folder = SNAPSHOT_DIR / name
    index = json.loads((folder / DIGESTS).read_text(encoding="utf-8"))
    texts = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(folder.iterdir())
        if path.name != DIGESTS
    }
    return index, texts


#: The products FR-348 (0.34.0) appends one last column to, and the column: the super
#: files and the unsteady polars carry the face count of each row's geometry.
FR348_PRODUCTS = ("*/SUPER-*.csv", "*_uns_avg.csv")
FR348_COLUMN = "MESH_FACES"
#: A cell of that column: NA where the inventory states no count, else a whole number.
_FR348_CELL = re.compile(r"NA|[0-9]+")


def without_the_fr348_column(data: bytes) -> bytes | None:
    """The product with the column FR-348 appends taken off, or None where it is not there.

    The header must end in ``,MESH_FACES`` and every row in one more cell that is
    ``NA`` or a whole number; that cell and its comma are removed, all of them and
    nothing else, so a product that differs from the stored one by anything beside
    the column still fails its digest.
    """
    text = data.decode("utf-8", "replace")
    lines = text.split("\n")
    if len(lines) < 2 or lines[-1] != "" or not lines[0].endswith(f",{FR348_COLUMN}"):
        return None
    kept = [lines[0][: -len(f",{FR348_COLUMN}")]]
    for line in lines[1:-1]:
        head, comma, cell = line.rpartition(",")
        if not comma or not _FR348_CELL.fullmatch(cell):
            return None
        kept.append(head)
    return ("\n".join(kept) + "\n").encode("utf-8")


def fr348_admitted(files: dict[str, bytes]) -> tuple[dict[str, bytes], list[str]]:
    """The files with the FR-348 column taken off each product it names, and those that lack it.

    The admission is the products of :data:`FR348_PRODUCTS` alone, and it is not
    optional: one of them without the column is named as lacking it.
    """
    admitted, lacking = dict(files), []
    for name, data in files.items():
        if any(fnmatch.fnmatch(name, pattern) for pattern in FR348_PRODUCTS):
            restored = without_the_fr348_column(data)
            if restored is None:
                lacking.append(name)
            else:
                admitted[name] = restored
    return admitted, lacking


def differences(index: dict[str, str], files: dict[str, bytes]) -> list[str]:
    """Every difference between a stored digest index and regenerated files, named.

    The stored digests are of the products as 0.33 wrote them; the one column
    FR-348 appends to the super files and the unsteady polars is taken off
    before they are compared (:func:`fr348_admitted`), and such a product
    without it is a difference.
    """
    files, lacking = fr348_admitted(files)
    now = digests(files)
    out = [f"{name}: lacks the {FR348_COLUMN} column FR-348 appends" for name in sorted(lacking)]
    out += [f"{name}: missing" for name in sorted(set(index) - set(now))]
    out += [f"{name}: not in the snapshot" for name in sorted(set(now) - set(index))]
    out += [
        f"{name}: bytes differ"
        for name in sorted(set(index) & set(now))
        if index[name] != now[name]
    ]
    return out


def text_differences(texts: dict[str, str], files: dict[str, bytes]) -> list[str]:
    """The stored texts against the regenerated ones, by file name, first changed line."""
    out = []
    for base, text in texts.items():
        match = [name for name in files if name.rsplit("/", 1)[-1] == base]
        if len(match) != 1:
            out.append(f"{base}: {len(match)} regenerated files carry the name")
            continue
        new = files[match[0]].decode("utf-8")
        if new != text:
            first = next(
                (
                    i
                    for i, (a, b) in enumerate(
                        zip(text.splitlines(), new.splitlines(), strict=False)
                    )
                    if a != b
                ),
                min(len(text.splitlines()), len(new.splitlines())),
            )
            out.append(f"{match[0]}: text differs from line {first + 1}")
    return out


#: How much of a file stored only as a digest a failure prints, as regenerated.
_SHOWN_LINES = 150


def _first_difference(stored_text: str, new: str) -> str:
    old_lines, new_lines = stored_text.splitlines(), new.splitlines()
    for number, (old, now) in enumerate(zip(old_lines, new_lines, strict=False), start=1):
        if old != now:
            return f"line {number}:\n    stored: {old!r}\n    now:    {now!r}"
    number = min(len(old_lines), len(new_lines)) + 1
    return f"line {number}: stored {len(old_lines)} lines, now {len(new_lines)}"


def explain(index: dict[str, str], texts: dict[str, str], files: dict[str, bytes]) -> str:
    """Every difference, and WHERE each changed file differs, for a failure message.

    A file whose text is stored (:data:`TEXT_FILES`) is compared line by line
    and its first differing line is printed on both sides. A file stored only
    as a digest has nothing to compare a line with, so its regenerated text is
    printed (its first :data:`_SHOWN_LINES` lines) for a reader to compare with
    a regeneration on the machine the snapshot was stored on.
    """
    out = []
    for difference in differences(index, files) + text_differences(texts, files):
        out.append(difference)
        name = difference.split(": ", 1)[0]
        if not difference.endswith("bytes differ") or name not in files:
            continue
        base = name.rsplit("/", 1)[-1]
        unique = sum(n.rsplit("/", 1)[-1] == base for n in files) == 1
        new = files[name].decode("utf-8", "replace")
        if base in texts and unique:
            out.append("  first difference, " + _first_difference(texts[base], new))
        else:
            lines = new.splitlines()
            out.append(f"  stored as a digest only; as regenerated ({len(lines)} lines):")
            out += [f"  | {line}" for line in lines[:_SHOWN_LINES]]
    return "\n".join(out)


def write_snapshot(name: str, files: dict[str, bytes]) -> None:
    """Store one campaign's snapshot (only on purpose, through the script's --write)."""
    folder = SNAPSHOT_DIR / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    # The digests stay those of the 0.33 shape: the FR-348 column is admitted, not stored.
    admitted, _lacking = fr348_admitted(files)
    (folder / DIGESTS).write_text(json.dumps(digests(admitted), indent=1) + "\n", encoding="utf-8")
    for base in TEXT_FILES:
        match = [n for n in files if n.rsplit("/", 1)[-1] == base]
        if len(match) == 1:
            (folder / base).write_bytes(files[match[0]])


def _planted(files: dict[str, bytes]) -> list[tuple[str, dict[str, bytes]]]:
    """Three copies of ``files``, each with one planted difference the comparison must catch."""
    products = [n for n in files if n.endswith(".csv")] or sorted(files)
    victim = products[0]
    changed = dict(files)
    data = changed[victim]
    changed[victim] = data[:-1] + bytes([data[-1] ^ 1]) if data else b"x"
    removed = {n: d for n, d in files.items() if n != victim}
    added = dict(files, **{"products/__planted__.csv": b"planted\n"})
    return [("a changed byte", changed), ("a product removed", removed), ("a product added", added)]


#: The campaign and the product the behaviour control changes through the code.
BEHAVIOUR_CAMPAIGN = "steady_probes"
BEHAVIOUR_PRODUCT = "products/probes/AL-020_probes.csv"


def behaviour_differences(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Post one campaign with one changed value in the product code; return what was caught.

    The planted copies of :func:`_planted` change bytes AFTER the post wrote
    them, so they prove the comparison and not the path from the code to the
    compared bytes (the build, the normalisation, the file selection). This
    one changes behaviour instead: ``point_tables`` reads the probe export
    through a ``parse_probe_points`` whose values are shifted by 1e-3, which
    the five-decimal probes table must show, and nothing else is touched.
    """
    import dataclasses

    from pyflightstream.post import point_tables

    original = point_tables.parse_probe_points

    def shifted(text, *args, **kwargs):
        report = original(text, *args, **kwargs)
        return dataclasses.replace(report, values=report.values + 1e-3)

    monkeypatch.setattr(point_tables, "parse_probe_points", shifted)
    index, _ = stored(BEHAVIOUR_CAMPAIGN)
    return differences(index, regenerate(BEHAVIOUR_CAMPAIGN, monkeypatch))


def _behaviour_caught(found: list[str]) -> bool:
    """Whether the behaviour control's changed product is among the differences."""
    return f"{BEHAVIOUR_PRODUCT}: bytes differ" in found


def _platform() -> str:
    """The platform a receipt was made on, as the goal checker spells it: linux or win32."""
    import sys

    return "win32" if sys.platform == "win32" else "linux"


def snapshot_receipt(write: bool = False) -> dict[str, object]:
    """Regenerate every campaign, compare (or store, with ``write``), and run the controls.

    ``control`` counts the planted copies of every campaign and the one
    behaviour control together; ``behaviour_control`` reports the latter
    alone, so a receipt says which kind of control it carries.
    """
    checked = 0
    differing: list[str] = []
    caught = planted = cr_files = 0
    for name in CAMPAIGNS:
        # One patch scope per campaign: a builder's patch must not reach the next.
        with pytest.MonkeyPatch.context() as monkeypatch:
            files = regenerate(name, monkeypatch)
            if write:
                write_snapshot(name, files)
            index, texts = stored(name)
            checked += len(files)
            cr_files += sum(1 for data in files.values() if b"\r" in data)
            differing += [
                f"{name}/{d}" for d in differences(index, files) + text_differences(texts, files)
            ]
            for _label, copy in _planted(files):
                planted += 1
                caught += bool(differences(index, copy))
    with pytest.MonkeyPatch.context() as monkeypatch:
        behaviour = int(_behaviour_caught(behaviour_differences(monkeypatch)))
    return {
        "files_checked": checked,
        "campaigns": len(CAMPAIGNS),
        "platforms": [_platform()],
        "line_ends_judged": True,
        "cr_files": cr_files,
        "differing": differing,
        "control": f"caught {caught + behaviour} of {planted + 1}",
        "behaviour_control": f"caught {behaviour} of 1",
    }


@pytest.mark.parametrize("name", sorted(CAMPAIGNS))
def test_the_products_of_a_recorded_campaign_are_byte_for_byte_the_stored_ones(name, monkeypatch):
    """P0330-PRODUCTS-SNAPSHOT. Every file under ``post/`` of the campaign, its
    ``products.json``, ``post.log`` and ``post.log.json`` included, regenerates to
    the stored digest, and the three stored texts are equal line for line."""
    files = regenerate(name, monkeypatch)
    index, texts = stored(name)
    assert files, f"{name}: the post wrote nothing"
    assert not differences(index, files), explain(index, texts, files)
    assert not text_differences(texts, files), explain(index, texts, files)


def test_a_planted_difference_in_the_products_is_caught(monkeypatch):
    """P0330-PRODUCTS-SNAPSHOT. The control: one changed byte of a product, one product
    removed and one added are each a difference the comparison reports, and the
    unplanted tree is none, so the test above can fail."""
    name = "unsteady_rotor"
    files = regenerate(name, monkeypatch)
    index, texts = stored(name)
    assert not differences(index, files), explain(index, texts, files)
    for label, copy in _planted(files):
        assert differences(index, copy), f"the comparison did not catch {label}"


def test_a_changed_value_in_the_product_code_is_caught(monkeypatch):
    """P0330-PRODUCTS-SNAPSHOT. The behaviour control: the probe values the
    product code reads, shifted by 1e-3, change the stored probes table's bytes,
    so a refactoring that changes a value cannot pass the snapshot through the
    build or the normalisation."""
    found = behaviour_differences(monkeypatch)
    assert _behaviour_caught(found), found


def test_the_normalisation_rewrites_only_the_volatile_fields(tmp_path):
    """P0330-PRODUCTS-SNAPSHOT. The stamp, the build folder and the version are rewritten;
    a number in a product is not, so a normalisation cannot hide a changed value."""
    from pyflightstream import __version__

    root = tmp_path / "camp"
    log = (
        f"pyflightstream {__version__} post\nworkspace={root}\ntime=2026-10-01T01:42:51.05-03:00\n"
    )
    assert normalise("products/post.log", log.encode(), root).decode() == (
        "pyflightstream <VERSION> post\nworkspace=<ROOT>\ntime=<TIME>\n"
    )
    row = b"ALPHA,CL\n-2.00000,0.41234\n"
    assert normalise("products/polars/P1.csv", row, root) == row
    crlf = row.replace(b"\n", b"\r\n")
    assert normalise("products/polars/P1.csv", crlf, root) == crlf, "a chosen CRLF is compared"


def test_the_separator_of_a_path_in_the_build_folder_is_the_only_path_change(tmp_path):
    """P0330-PRODUCTS-SNAPSHOT. A path inside the build folder reads the same with
    either separator, in a text and in a JSON string; a different file in it is
    still a difference, and a backslash outside such a path is kept."""
    root = tmp_path / "camp"

    def norm(text: str) -> bytes:
        return normalise("products/post.log", text.encode(), root)

    posix = "no export found in <ROOT>/sims/sim_7001 or its outputs"
    assert norm(posix.replace("/", "\\")) == norm(posix) == posix.encode()
    json_posix = '"message": "missing: <ROOT>/sims/sim_7010/p.vtk",'
    assert norm(json_posix.replace("/", "\\\\")) == norm(json_posix)
    assert norm(f"in {root / 'sims' / 'sim_7001'} or") == b"in <ROOT>/sims/sim_7001 or"
    assert norm("<ROOT>\\sims\\sim_7002 or") != norm(posix)
    kept = "a separator a\\b outside the build folder"
    assert norm(kept) == kept.encode()


def test_the_pinned_environment_fills_only_defaults(tmp_path, monkeypatch):
    """P0330-PRODUCTS-SNAPSHOT. Under the pin a text write with no stated line end
    writes LF and the operator is :data:`OPERATOR`; a write that states its line
    end keeps it, so a product's own CRLF is still compared, not hidden."""
    import getpass

    from pyflightstream.workspace.naming import submitted_by

    pin_environment(monkeypatch)
    (tmp_path / "default.txt").write_text("a\nb\n", encoding="utf-8")
    with open(tmp_path / "opened.txt", "w", encoding="utf-8") as handle:
        handle.write("a\n")
    (tmp_path / "stated.txt").write_text("a\n", encoding="utf-8", newline="\r\n")
    assert (tmp_path / "default.txt").read_bytes() == b"a\nb\n"
    assert (tmp_path / "opened.txt").read_bytes() == b"a\n"
    assert (tmp_path / "stated.txt").read_bytes() == b"a\r\n"
    assert getpass.getuser() == submitted_by() == OPERATOR
