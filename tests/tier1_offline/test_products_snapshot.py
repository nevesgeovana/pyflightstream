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
campaign was built in, the package version and the release tag derived from
it, the wall-clock name of an archive folder a rebuild moves the replaced
products into, the date line of the custom polar format (the wall clock
again), and the line end the platform's text mode writes. One
campaign leaves out files no normalisation makes stable (:data:`VOLATILE`,
with its reason). Nothing else may differ.

Also ``.gitattributes``: the stored texts are pinned to LF like the goldens.

THE CONTROL. A comparator that cannot see a difference would pass any
refactoring, so :func:`snapshot_receipt` plants three differences into a
regenerated tree (one changed byte of a product, a product removed, a
product added) and requires the comparison to catch each:
``caught 3 of 3``. ``scripts/products_snapshot.py`` writes that receipt
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

    with warnings.catch_warnings():
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

    return _post(_rotor_workspace(tmp, ROTOR), overwrite=True)


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
    return _post(workspace, overwrite=True, matrix_stem=matrix.stem)


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


def normalise(name: str, data: bytes, root: Path) -> bytes:
    """Rewrite the volatile fields of one post file: stamps, the build folder, the version."""
    from pyflightstream import __version__
    from pyflightstream.post.superfile import release_tag

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    # The line end the platform's text mode writes (CRLF on Windows): the
    # snapshot is the same on every machine the suite runs on.
    text = text.replace("\r\n", "\n")
    for form in {str(root), root.as_posix(), json.dumps(str(root))[1:-1]}:
        text = text.replace(form, "<ROOT>")
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


def regenerate(name: str, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Build and post one campaign and return its normalised post files.

    THE BUILD FOLDER IS NEUTRAL AND THE SAME SHAPE EVERYWHERE, never pytest's
    ``tmp_path`` nor a folder named for the campaign: a warning names the
    workspace path, and the post log's CATEGORY of a warning is a keyword match
    over its text (``post.diagnostics.warning_category``), so a folder called
    ``section_distributions`` turned a ``convergence`` record into a
    ``section-layout`` one. Measured on the first stored snapshot, 2026-10-01.
    """
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


def differences(index: dict[str, str], files: dict[str, bytes]) -> list[str]:
    """Every difference between a stored digest index and regenerated files, named."""
    now = digests(files)
    out = [f"{name}: missing" for name in sorted(set(index) - set(now))]
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


def write_snapshot(name: str, files: dict[str, bytes]) -> None:
    """Store one campaign's snapshot (only on purpose, through the script's --write)."""
    folder = SNAPSHOT_DIR / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / DIGESTS).write_text(json.dumps(digests(files), indent=1) + "\n", encoding="utf-8")
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


def snapshot_receipt(write: bool = False) -> dict[str, object]:
    """Regenerate every campaign, compare (or store, with ``write``), and run the control."""
    checked = 0
    differing: list[str] = []
    caught = planted = 0
    for name in CAMPAIGNS:
        # One patch scope per campaign: a builder's patch must not reach the next.
        with pytest.MonkeyPatch.context() as monkeypatch:
            files = regenerate(name, monkeypatch)
            if write:
                write_snapshot(name, files)
            index, texts = stored(name)
            checked += len(files)
            differing += [
                f"{name}/{d}" for d in differences(index, files) + text_differences(texts, files)
            ]
            for _label, copy in _planted(files):
                planted += 1
                caught += bool(differences(index, copy))
    return {
        "files_checked": checked,
        "campaigns": len(CAMPAIGNS),
        "differing": differing,
        "control": f"caught {caught} of {planted}",
    }


@pytest.mark.parametrize("name", sorted(CAMPAIGNS))
def test_the_products_of_a_recorded_campaign_are_byte_for_byte_the_stored_ones(name, monkeypatch):
    """P0330-PRODUCTS-SNAPSHOT. Every file under ``post/`` of the campaign, its
    ``products.json``, ``post.log`` and ``post.log.json`` included, regenerates to
    the stored digest, and the three stored texts are equal line for line."""
    files = regenerate(name, monkeypatch)
    index, texts = stored(name)
    assert files, f"{name}: the post wrote nothing"
    assert not differences(index, files), differences(index, files)
    assert not text_differences(texts, files), text_differences(texts, files)


def test_a_planted_difference_in_the_products_is_caught(monkeypatch):
    """P0330-PRODUCTS-SNAPSHOT. The control: one changed byte of a product, one product
    removed and one added are each a difference the comparison reports, and the
    unplanted tree is none, so the test above can fail."""
    name = "unsteady_rotor"
    files = regenerate(name, monkeypatch)
    index, _ = stored(name)
    assert not differences(index, files)
    for label, copy in _planted(files):
        assert differences(index, copy), f"the comparison did not catch {label}"


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
