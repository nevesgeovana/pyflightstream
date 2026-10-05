"""Tier 1, GOAL-033: facts that exist only after publication, verified at the tag.

WHY THIS FILE EXISTS. The GOAL-033 checker proves an obligation only through
a passing test, pinned to the release tag, whose body names it. Some
obligations are facts that do not exist until after the tag: the wheel on
PyPI installs, the kit is delivered, the licensed regressions ran on the
tagged code, the research campaign ran on the published wheel. Their tests
must therefore already be in the tag and verify a RECEIPT produced later.

HOW A RECEIPT IS READ. Each marker test reads one JSON receipt from its own
environment variable (below) and SKIPS, naming the variable, when it is
unset. A skip is never a PASS for the checker. The receipt lives outside the
repository; no private path enters the tree. Nothing in a receipt is trusted:
every named file is hashed again from disk, every count is recomputed from
the file it counts, the release identity is compared with the tree under
test, and a receipt about code must carry ``product_revision`` equal to
``git rev-parse HEAD`` of this tree.

Each validator is falsifiable: the unmarked tests at the end build a valid
synthetic receipt, show it is ACCEPTED (the control), and show that the same
receipt with one field wrong is REFUSED. They run without any receipt.

COMMON ENVELOPE (every receipt)::

    {
      "schema": "goal033-release-receipt/1",
      "obligation": "<arm>:<field>:<id>",      # e.g. "delivery:checks:clean_install"
      "package": "pyflightstream",
      "version": "<pyproject [project].version of this tree>",
      "product_revision": "<40-hex, == git HEAD>",   # required where marked [code]
      "recorded_at": "<ISO-8601>",
      "artifacts": [{"role": "<unique>", "path": "<absolute, outside the tree>",
                     "sha256": "<64-hex of the file>"}],
      "facts": {...}                                 # per obligation, below
    }

PER OBLIGATION (variable -> obligation: required artifacts roles; facts):

* ``GOAL033_CLEAN_INSTALL_RECEIPT`` -> ``delivery:checks:clean_install``.
  Roles ``wheel`` (the file pip downloaded, named
  ``pyflightstream-<version>-py3-none-any.whl``, its METADATA Version ==
  version), ``venv_python`` (inside a venv: ``pyvenv.cfg`` two levels up),
  ``pip_log`` (carries ``Successfully installed`` and
  ``pyflightstream-<version>``), ``pyfs_matrix_help`` (captured stdout of
  ``pyfs-matrix --help``, carries ``usage``). Facts ``index`` (starts
  ``https://pypi.org/``), ``requirement`` == ``pyflightstream==<version>``,
  ``fresh_venv`` true, ``pypi_wheel_sha256`` (the digest PyPI publishes; must
  equal the downloaded wheel's hash), ``import_version_output`` == version
  (the output of ``import pyflightstream; print(pyflightstream.__version__)``),
  ``pyfs_matrix_help_exit`` == 0.
* ``GOAL033_DEV_WHEELS_RECEIPT`` -> ``delivery:checks:dev_wheels_per_block``
  [code]. Facts ``blocks``: non-empty list of ``{"block": id, "revision":
  40-hex ancestor of HEAD, "wheels": [{"path", "sha256", "version"}]}``; each
  block at least one wheel; each version carries ``.dev``, sorts before the
  release, matches the wheel's METADATA and file name; no wheel is listed twice.
* ``GOAL033_GUIDES_KIT_RECEIPT`` -> ``delivery:checks:guides_kit``. Role
  ``kit``: ``DLV-<nnn>[-<nnn>...]_<deliverable>_pyflightstream-<version>.zip``.
  Facts ``user_guide_member`` (a PDF member) and ``linux_guide_member``; both
  members exist and their text states the version.
* ``GOAL033_LINUX_GUIDE_RECEIPT`` -> ``delivery:checks:linux_guide``. Role
  ``kit``; fact ``linux_guide_member``: its text states the version,
  ``pyflightstream`` and ``pip install``.
* ``GOAL033_D10_RECEIPT`` -> ``capability_ids:items:D10``. Role ``kit``;
  facts ``linux_guide_member`` and ``executables_statement``: exactly the
  module constant ``STATEMENT`` ("To run a matrix locally on Linux, change
  only the executable path in executables.toml."), which must occur in the
  member's extracted text (compared with whitespace removed, case folded).
  A caller-chosen substring is not accepted: the sentence is the claim.
* ``GOAL033_D15_RECEIPT`` -> ``capability_ids:items:D15``. Role ``kit``;
  facts ``user_guide_member``, ``linux_guide_member`` and ``members``: the
  complete list ``[{"name", "sha256"}]`` of the zip's file members, equal to
  the zip's member list exactly, every hash recomputed.
* ``GOAL033_LICENSED_REGRESSIONS_RECEIPT`` -> ``delivery:checks:licensed_regressions``
  [code]. Role ``junit`` (JUnit XML of the tier-3 run) and ``matrix:<name>``
  for each matrix run. Facts ``tier`` == 3, ``build`` (solver build),
  ``executable_sha256``, ``matrices`` (non-empty list of names), ``tests``,
  ``failures``, ``errors``, ``skipped``: equal to the counts recomputed from
  the JUnit; failures == errors == 0 and at least one test passed.
* ``GOAL033_TIER1_TIER2_RECEIPT`` -> ``delivery:checks:tier1_tier2_regressions``
  [code]. Roles ``tier1_junit`` and ``tier2_junit``. Facts ``tier1`` and
  ``tier2``, each ``{"tests", "failures", "errors", "skipped"}`` equal to the
  recomputed counts; failures == errors == 0 in both; tier 1 has more than
  7000 PASSING tests (tests - skipped; a skip is not a pass);
  ``tier2_build`` (the licensed build) and ``tier2_licensed`` true.
* ``GOAL033_G39_RECEIPT`` -> ``capability_ids:items:G39`` [code]. Roles
  ``native_section_saved`` and ``native_section_reopened`` (the native volume
  section as saved and as read back from the reopened .fsm: byte-identical,
  recomputed), ``probe_vtk`` and ``native_export_vtk`` (legacy ASCII VTK;
  their POINTS must be equal, recomputed). Facts
  ``native_volume_byte_identical`` true, ``probe_velocity`` and
  ``native_velocity`` (the velocity array of each VTK's POINT_DATA: a
  ``VECTORS`` name as a string -- the product writes ``Velocity`` -- or a list
  of three ``SCALARS`` names), ``csv_quantization`` (a finite number > 0) and
  ``max_velocity_error``. Every velocity value must be finite. The comparison
  is RECOMPUTED: the largest absolute
  component difference between the two velocity arrays must be <=
  ``csv_quantization`` and equal the stated ``max_velocity_error`` within
  1e-12. ``sources``: ``[{"path", "sha256"}]`` for at least the five post/fsm
  modules below, each equal to the blob at HEAD.
* ``GOAL033_G63_RECEIPT`` -> ``capability_ids:items:G63``. Roles ``wheel``
  (a zip wheel whose METADATA is pyflightstream at the release version, hash
  == ``pypi_wheel_sha256``), ``matrix`` (file named ``matrix-qa.fs``),
  ``synthesis_report`` (non-empty text naming every case id) and
  ``result:<id>`` for every case: a JSON object ``{"case": <id>, "complete":
  true, ...}`` written by the run, re-hashed. Facts ``workspace`` ==
  ``fts-research``, ``matrix`` == ``matrix-qa.fs``, ``pypi_wheel_sha256``,
  ``cases``: non-empty ``[{"id", "status"}]`` all ``completed`` with unique
  ids, and ``completed_cases`` == their count. Completion is derived from the
  per-case artifacts: a receipt saying ``completed`` over a result that says
  otherwise is refused.
* ``GOAL033_G66_RECEIPT`` -> ``capability_ids:items:G66``. Roles
  ``input:<name>`` for the three owner inputs (names below) and
  ``summary:<name>`` for each input's review summary. Facts ``inputs``: the
  three ``{"name", "reviewed": true}``, and ``dispositions`` == 2 + the
  number of file members of ``FLIGHTSTREAM_Refs.zip`` (recomputed).
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import re
import subprocess
import tomllib
import warnings
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from packaging.version import Version

from tests.support_helpers import file_sha256 as _sha256

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "goal033-release-receipt/1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: The source files the T33 native acceptance exercises; its receipt must hash them at HEAD.
G39_SOURCES = (
    "src/pyflightstream/_fsm.py",
    "src/pyflightstream/post/field_frames.py",
    "src/pyflightstream/post/probe_fields.py",
    "src/pyflightstream/post/products.py",
    "src/pyflightstream/post/writers.py",
)

#: D10: the sentence the kit's Linux guide must carry, verbatim up to whitespace and case.
STATEMENT = "To run a matrix locally on Linux, change only the executable path in executables.toml."

#: The three owner inputs the reference intake reviews, by their exact names.
G66_INPUTS = (
    "FLIGHTSTREAM_Refs.zip",
    "[Notes on Numerical Fluid Mechanics №21] H. W. M. Hoeijmakers (auth.), Prof. "
    "Dr.-Ing. Josel Ballmann, Pro - Panel Methods in Fluid Mechanics with Emphasis on "
    "Aerodynamics_ Proceedings of.pdf",
    "Schlichting - Boundary-Layer Theory - 7th Ed 1979.pdf",
)


class ReceiptRefusedError(AssertionError):
    """A receipt failed verification; the message names the field."""


def _need(condition: object, why: str) -> None:
    if not condition:
        raise ReceiptRefusedError(why)


@dataclass(frozen=True)
class Tree:
    """The release identity a receipt is compared with."""

    version: str
    head: str
    is_ancestor: Callable[[str], bool]
    blob_sha256: Callable[[str], str | None]


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, check=False, env=os.environ.copy()
    )


def _real_tree() -> Tree:
    """This tree: the pyproject version and the git HEAD, both required."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    head = _git("rev-parse", "HEAD")
    assert head.returncode == 0, "the tree under test must be a git checkout to compare HEAD"
    revision = head.stdout.decode("ascii").strip()
    assert HEX40.match(revision), revision

    def is_ancestor(rev: str) -> bool:
        return _git("merge-base", "--is-ancestor", rev, revision).returncode == 0

    def blob_sha256(path: str) -> str | None:
        shown = _git("show", f"{revision}:{path}")
        return hashlib.sha256(shown.stdout).hexdigest() if shown.returncode == 0 else None

    return Tree(pyproject["project"]["version"], revision, is_ancestor, blob_sha256)


def _receipt(variable: str) -> dict:
    location = os.environ.get(variable)
    if not location:
        pytest.skip(f"set {variable} to the recorded receipt (schema in this module's docstring)")
    return json.loads(Path(location).read_text(encoding="utf-8"))


def _hashed_file(path: object, digest: object, what: str) -> Path:
    _need(isinstance(path, str) and Path(path).is_absolute(), f"{what}: path must be absolute")
    file = Path(path)
    _need(file.is_file(), f"{what}: {file} does not exist")
    _need(not file.resolve().is_relative_to(ROOT), f"{what}: receipts' files live outside the tree")
    _need(isinstance(digest, str) and HEX64.match(digest), f"{what}: sha256 malformed")
    _need(_sha256(file) == digest, f"{what}: sha256 of {file.name} differs from the receipt")
    return file


def _envelope(receipt: object, obligation: str, tree: Tree, *, code: bool):
    """Check the common envelope; return the hashed artifacts by role and the facts."""
    _need(isinstance(receipt, dict), "receipt is not a JSON object")
    assert isinstance(receipt, dict)
    _need(receipt.get("schema") == SCHEMA, "schema")
    _need(receipt.get("obligation") == obligation, f"obligation is not {obligation}")
    _need(receipt.get("package") == "pyflightstream", "package")
    _need(receipt.get("version") == tree.version, f"version is not {tree.version}")
    _need(isinstance(receipt.get("recorded_at"), str), "recorded_at")
    if code:
        _need(receipt.get("product_revision") == tree.head, f"product_revision is not {tree.head}")
    artifacts = receipt.get("artifacts")
    _need(isinstance(artifacts, list) and artifacts, "artifacts missing")
    roles: dict[str, Path] = {}
    for item in artifacts:
        _need(isinstance(item, dict) and isinstance(item.get("role"), str), "artifact role")
        role = item["role"]
        _need(role not in roles, f"artifact role {role} twice")
        roles[role] = _hashed_file(item.get("path"), item.get("sha256"), role)
    facts = receipt.get("facts")
    _need(isinstance(facts, dict), "facts missing")
    return roles, facts


def _role(roles: dict[str, Path], role: str) -> Path:
    _need(role in roles, f"artifact role {role} missing")
    return roles[role]


def _wheel_metadata(path: Path) -> tuple[str, str]:
    _need(zipfile.is_zipfile(path), f"{path.name}: not a zip, so not a wheel")
    with zipfile.ZipFile(path) as wheel:
        names = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
        _need(len(names) == 1, f"{path.name}: not one METADATA")
        meta = wheel.read(names[0]).decode("utf-8")
    name = re.search(r"^Name: (\S+)", meta, re.M)
    version = re.search(r"^Version: (\S+)", meta, re.M)
    _need(name and version, f"{path.name}: METADATA without Name/Version")
    assert name and version
    return name.group(1), version.group(1)


def _junit(path: Path) -> dict[str, int]:
    root = ET.fromstring(path.read_bytes())  # a local file whose hash the receipt verified
    cases = list(root.iter("testcase"))
    return {
        "tests": len(cases),
        "failures": sum(1 for c in cases if c.find("failure") is not None),
        "errors": sum(1 for c in cases if c.find("error") is not None),
        "skipped": sum(1 for c in cases if c.find("skipped") is not None),
    }


def _counts_match(declared: object, path: Path, what: str) -> dict[str, int]:
    counted = _junit(path)
    _need(declared == counted, f"{what}: declared {declared} != counted {counted}")
    _need(counted["failures"] == 0 and counted["errors"] == 0, f"{what}: failures or errors")
    _need(counted["tests"] - counted["skipped"] >= 1, f"{what}: nothing ran")
    return counted


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _member_text(kit: zipfile.ZipFile, name: object) -> str:
    _need(isinstance(name, str) and name in kit.namelist(), f"kit member {name} missing")
    assert isinstance(name, str)
    data = kit.read(name)
    if name.lower().endswith(".pdf"):
        _need(data.startswith(b"%PDF-"), f"{name} is not a PDF")
        pypdf = pytest.importorskip("pypdf")  # the kit validators alone read PDFs
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pages = pypdf.PdfReader(io.BytesIO(data)).pages
            return " ".join(page.extract_text() or "" for page in pages)
    return data.decode("utf-8")


def _kit(roles: dict[str, Path], tree: Tree) -> zipfile.ZipFile:
    path = _role(roles, "kit")
    pattern = rf"DLV-\d{{3}}(?:-\d{{3}})*_[a-z0-9.-]+_pyflightstream-{re.escape(tree.version)}\.zip"
    _need(re.fullmatch(pattern, path.name), f"kit name {path.name} breaks the DLV naming")
    return zipfile.ZipFile(path)


# --- validators, one per obligation ---------------------------------------------------


def validate_clean_install(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "delivery:checks:clean_install", tree, code=False)
    v = tree.version
    _need(str(facts.get("index", "")).startswith("https://pypi.org/"), "index is not PyPI")
    _need(facts.get("requirement") == f"pyflightstream=={v}", "requirement")
    _need(facts.get("fresh_venv") is True, "fresh_venv")
    wheel = _role(roles, "wheel")
    _need(wheel.name == f"pyflightstream-{v}-py3-none-any.whl", f"wheel name {wheel.name}")
    _need(_sha256(wheel) == facts.get("pypi_wheel_sha256"), "wheel differs from PyPI's digest")
    _need(_wheel_metadata(wheel) == ("pyflightstream", v), "wheel METADATA")
    python = _role(roles, "venv_python")
    _need((python.parent.parent / "pyvenv.cfg").is_file(), "venv_python is not in a venv")
    log = _role(roles, "pip_log").read_text(encoding="utf-8", errors="replace")
    _need("Successfully installed" in log and f"pyflightstream-{v}" in log, "pip log")
    _need(facts.get("import_version_output") == v, "import reports another version")
    helped = _role(roles, "pyfs_matrix_help").read_text(encoding="utf-8", errors="replace")
    exit_code = facts.get("pyfs_matrix_help_exit")
    _need(type(exit_code) is int and exit_code == 0, "pyfs-matrix --help exit")
    _need("usage" in helped.lower(), "pyfs-matrix --help printed no usage")


def validate_dev_wheels(receipt: object, tree: Tree) -> None:
    _, facts = _envelope(receipt, "delivery:checks:dev_wheels_per_block", tree, code=True)
    blocks = facts.get("blocks")
    _need(isinstance(blocks, list) and blocks, "blocks missing")
    assert isinstance(blocks, list)
    ids, digests = set(), set()
    for block in blocks:
        _need(isinstance(block, dict) and isinstance(block.get("block"), str), "block id")
        name = block["block"]
        _need(name and name not in ids, f"block {name} empty or twice")
        ids.add(name)
        revision = block.get("revision")
        _need(isinstance(revision, str) and HEX40.match(revision), f"{name}: revision")
        _need(tree.is_ancestor(revision), f"{name}: revision is not an ancestor of HEAD")
        wheels = block.get("wheels")
        _need(isinstance(wheels, list) and wheels, f"{name}: no wheel")
        for wheel in wheels:
            path = _hashed_file(wheel.get("path"), wheel.get("sha256"), f"{name} wheel")
            version = wheel.get("version")
            _need(isinstance(version, str) and ".dev" in version, f"{name}: not a dev version")
            _need(Version(version) < Version(tree.version), f"{name}: {version} is not before")
            _need(path.name.startswith(f"pyflightstream-{version}-"), f"{name}: file name")
            _need(path.suffix == ".whl", f"{name}: not a wheel")
            _need(_wheel_metadata(path) == ("pyflightstream", version), f"{name}: METADATA")
            _need(wheel["sha256"] not in digests, f"{name}: a wheel is listed twice")
            digests.add(wheel["sha256"])


def validate_guides_kit(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "delivery:checks:guides_kit", tree, code=False)
    with _kit(roles, tree) as kit:
        user = facts.get("user_guide_member")
        _need(str(user).lower().endswith(".pdf"), "user guide is not a PDF member")
        _need(tree.version in _member_text(kit, user), "user guide does not state the version")
        linux = _member_text(kit, facts.get("linux_guide_member"))
        _need(tree.version in linux, "Linux guide does not state the version")


def validate_linux_guide(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "delivery:checks:linux_guide", tree, code=False)
    with _kit(roles, tree) as kit:
        text = _member_text(kit, facts.get("linux_guide_member"))
    _need(tree.version in text, "Linux guide does not state the version")
    squashed = _squash(text)
    _need("pyflightstream" in squashed and "pipinstall" in squashed, "Linux guide install text")


def validate_d10(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "capability_ids:items:D10", tree, code=False)
    _need(
        facts.get("executables_statement") == STATEMENT,
        "statement must assert the executables-only change",
    )
    with _kit(roles, tree) as kit:
        text = _member_text(kit, facts.get("linux_guide_member"))
    _need(_squash(STATEMENT) in _squash(text), "the statement is not in the Linux guide")


def validate_d15(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "capability_ids:items:D15", tree, code=False)
    members = facts.get("members")
    _need(isinstance(members, list) and members, "members missing")
    assert isinstance(members, list)
    with _kit(roles, tree) as kit:
        listed = [m.get("name") for m in members if isinstance(m, dict)]
        files = [i.filename for i in kit.infolist() if not i.is_dir()]
        _need(sorted(listed) == sorted(files), "members differ from the zip's")
        for member in members:
            digest = hashlib.sha256(kit.read(member["name"])).hexdigest()
            _need(digest == member.get("sha256"), f"member {member['name']} hash")
        _need(str(facts.get("user_guide_member")).lower().endswith(".pdf"), "user guide")
        _need(tree.version in _member_text(kit, facts.get("user_guide_member")), "user guide")
        _need(tree.version in _member_text(kit, facts.get("linux_guide_member")), "Linux guide")


def validate_licensed_regressions(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "delivery:checks:licensed_regressions", tree, code=True)
    _need(facts.get("tier") == 3, "tier is not 3")
    _need(isinstance(facts.get("build"), str) and facts["build"], "build")
    _need(HEX64.match(str(facts.get("executable_sha256"))), "executable_sha256")
    matrices = facts.get("matrices")
    _need(isinstance(matrices, list) and matrices, "matrices missing")
    assert isinstance(matrices, list)
    for matrix in matrices:
        _role(roles, f"matrix:{matrix}")
    declared = {k: facts.get(k) for k in ("tests", "failures", "errors", "skipped")}
    _counts_match(declared, _role(roles, "junit"), "tier 3")


def validate_tier1_tier2(receipt: object, tree: Tree) -> None:
    obligation = "delivery:checks:tier1_tier2_regressions"
    roles, facts = _envelope(receipt, obligation, tree, code=True)
    tier1 = _counts_match(facts.get("tier1"), _role(roles, "tier1_junit"), "tier 1")
    _need(
        tier1["tests"] - tier1["skipped"] > 7000,
        "tier 1 has not more than 7000 passing tests",
    )
    _counts_match(facts.get("tier2"), _role(roles, "tier2_junit"), "tier 2")
    _need(isinstance(facts.get("tier2_build"), str) and facts["tier2_build"], "tier2_build")
    _need(facts.get("tier2_licensed") is True, "tier2_licensed")


def _floats(tokens: list[str], at: int, count: int, what: str) -> list[float]:
    values = tokens[at : at + count]
    _need(len(values) == count, f"{what}: truncated")
    try:
        parsed = [float(t) for t in values]
    except ValueError:
        raise ReceiptRefusedError(f"{what}: a value is not a number") from None
    _need(all(math.isfinite(v) for v in parsed), f"{what}: nonfinite value")
    return parsed


def _vtk(path: Path) -> tuple[list[float], dict[str, list[float]]]:
    """Read a legacy ASCII VTK: its POINTS and its POINT_DATA arrays, by name.

    The layout is the one ``pyflightstream.post.writers.write_vtk_points``
    writes (``POINTS n float``, then ``POINT_DATA n`` with ``SCALARS name
    type [components]`` + ``LOOKUP_TABLE`` or ``VECTORS name type``). The
    product has no reader for point clouds (``read_vtk_surface`` reads
    surfaces and refuses VECTORS), so the receipt test parses it here.
    """
    lines = path.read_text(encoding="ascii").splitlines()
    _need(len(lines) > 4 and lines[2].strip().upper() == "ASCII", f"{path.name}: not ASCII VTK")
    tokens = " ".join(lines[3:]).split()  # the title line is free text
    _need("POINTS" in tokens, f"{path.name}: no POINTS")
    at = tokens.index("POINTS")
    count = int(tokens[at + 1])
    _need(count > 0, f"{path.name}: no points")
    points = _floats(tokens, at + 3, 3 * count, f"{path.name} POINTS")
    arrays: dict[str, list[float]] = {}
    if "POINT_DATA" not in tokens:
        return points, arrays
    at = tokens.index("POINT_DATA")
    _need(int(tokens[at + 1]) == count, f"{path.name}: POINT_DATA count differs from POINTS")
    at += 2
    while at < len(tokens) and tokens[at] != "CELL_DATA":
        keyword, name = tokens[at].upper(), tokens[at + 1]
        _need(name not in arrays, f"{path.name}: array {name} twice")
        if keyword == "VECTORS":
            at += 3
            width = 3
        elif keyword == "SCALARS":
            at += 3
            width = 1
            if at < len(tokens) and tokens[at].upper() != "LOOKUP_TABLE":
                _need(tokens[at] in {"1", "2", "3", "4"}, f"{path.name}: {name} components")
                width = int(tokens[at])
                at += 1
            _need(
                at < len(tokens) and tokens[at].upper() == "LOOKUP_TABLE",
                f"{path.name}: SCALARS {name} without its LOOKUP_TABLE",
            )
            at += 2
        else:
            raise ReceiptRefusedError(f"{path.name}: POINT_DATA holds {keyword}, not read here")
        arrays[name] = _floats(tokens, at, width * count, f"{path.name} {name}")
        at += width * count
    return points, arrays


def _velocity(arrays: dict[str, list[float]], named: object, what: str) -> list[float]:
    """The velocity array as ``[vx0, vy0, vz0, vx1, ...]``: one VECTORS or three SCALARS."""
    if isinstance(named, str):
        _need(named in arrays, f"{what}: no array {named}")
        values = arrays[named]
        _need(len(values) % 3 == 0, f"{what}: {named} is not a vector array")
        return values
    _need(
        isinstance(named, list) and len(named) == 3 and all(isinstance(n, str) for n in named),
        f"{what}: velocity must name one VECTORS or three SCALARS arrays",
    )
    assert isinstance(named, list)
    for name in named:
        _need(name in arrays, f"{what}: no array {name}")
    columns = [arrays[name] for name in named]
    _need(len({len(c) for c in columns}) == 1, f"{what}: velocity components differ in length")
    return [value for row in zip(*columns, strict=True) for value in row]


def validate_g39(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "capability_ids:items:G39", tree, code=True)
    saved = _role(roles, "native_section_saved").read_bytes()
    reopened = _role(roles, "native_section_reopened").read_bytes()
    _need(saved and saved == reopened, "native volume section is not byte-identical")
    _need(facts.get("native_volume_byte_identical") is True, "native_volume_byte_identical")
    probe_points, probe_arrays = _vtk(_role(roles, "probe_vtk"))
    native_points, native_arrays = _vtk(_role(roles, "native_export_vtk"))
    _need(probe_points == native_points, "probe points differ from the native export")
    probe = _velocity(probe_arrays, facts.get("probe_velocity"), "probe_vtk")
    native = _velocity(native_arrays, facts.get("native_velocity"), "native_export_vtk")
    _need(len(probe) == len(native) == len(probe_points), "velocity count differs from points")
    measured = max(abs(a - b) for a, b in zip(probe, native, strict=True))
    error, quantum = facts.get("max_velocity_error"), facts.get("csv_quantization")
    _need(
        type(quantum) in (int, float) and math.isfinite(quantum) and quantum > 0,
        "csv_quantization",
    )
    _need(measured <= quantum, f"velocities differ by {measured}, beyond the CSV quantization")
    _need(
        isinstance(error, int | float) and abs(error - measured) <= 1e-12,
        f"max_velocity_error {error} is not the recomputed {measured}",
    )
    sources = facts.get("sources")
    _need(isinstance(sources, list), "sources missing")
    assert isinstance(sources, list)
    hashed = {s.get("path"): s.get("sha256") for s in sources if isinstance(s, dict)}
    _need(set(G39_SOURCES) <= set(hashed), f"sources lack {set(G39_SOURCES) - set(hashed)}")
    for path, digest in hashed.items():
        _need(str(path).startswith("src/pyflightstream/"), f"source {path} outside the package")
        _need(tree.blob_sha256(str(path)) == digest, f"source {path} is not the one at HEAD")


def validate_g63(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "capability_ids:items:G63", tree, code=False)
    _need(facts.get("workspace") == "fts-research", "workspace")
    _need(facts.get("matrix") == "matrix-qa.fs", "matrix")
    _need(_role(roles, "matrix").name == "matrix-qa.fs", "matrix file")
    wheel = _role(roles, "wheel")
    _need(wheel.name == f"pyflightstream-{tree.version}-py3-none-any.whl", "wheel name")
    _need(_sha256(wheel) == facts.get("pypi_wheel_sha256"), "wheel is not PyPI's")
    _need(_wheel_metadata(wheel) == ("pyflightstream", tree.version), "wheel METADATA")
    cases = facts.get("cases")
    _need(isinstance(cases, list) and cases, "cases missing")
    assert isinstance(cases, list)
    ids = [c.get("id") for c in cases if isinstance(c, dict)]
    _need(len(ids) == len(cases) == len(set(ids)) and all(ids), "case ids")
    _need(all(isinstance(i, str) for i in ids), "case ids must be strings")
    _need(all(c.get("status") == "completed" for c in cases), "a case did not complete")
    _need(facts.get("completed_cases") == len(cases), "completed_cases")
    for case in ids:
        try:
            result = json.loads(_role(roles, f"result:{case}").read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ReceiptRefusedError(f"result of {case} is not JSON") from None
        _need(isinstance(result, dict) and result.get("case") == case, f"result of {case}: case")
        _need(result.get("complete") is True, f"result of {case} does not state completion")
    report = _role(roles, "synthesis_report").read_text(encoding="utf-8", errors="replace")
    _need(report.strip(), "synthesis report empty")
    unnamed = [case for case in ids if case not in report]
    _need(not unnamed, f"the synthesis report does not name {unnamed}")


def validate_g66(receipt: object, tree: Tree) -> None:
    roles, facts = _envelope(receipt, "capability_ids:items:G66", tree, code=False)
    inputs = facts.get("inputs")
    _need(isinstance(inputs, list), "inputs missing")
    assert isinstance(inputs, list)
    names = [i.get("name") for i in inputs if isinstance(i, dict)]
    _need(sorted(names) == sorted(G66_INPUTS), "inputs are not the three owner inputs")
    _need(all(i.get("reviewed") is True for i in inputs), "an input is not reviewed")
    for name in G66_INPUTS:
        _role(roles, f"input:{name}")
        _need(_role(roles, f"summary:{name}").stat().st_size > 0, f"summary of {name} empty")
    with zipfile.ZipFile(roles[f"input:{G66_INPUTS[0]}"]) as refs:
        members = [i for i in refs.infolist() if not i.is_dir()]
    _need(facts.get("dispositions") == 2 + len(members), "dispositions do not cover the inputs")


# --- the marker tests: each reads its own receipt ---------------------------------------


def test_release_clean_install_from_pypi_receipt():
    """The published wheel installs from PyPI into a fresh venv and runs.

    GOAL033:delivery:checks:clean_install
    """
    receipt = _receipt("GOAL033_CLEAN_INSTALL_RECEIPT")
    validate_clean_install(receipt, _real_tree())
    assert receipt["obligation"] == "delivery:checks:clean_install"


def test_release_dev_wheel_per_block_receipt():
    """Each development block built its own dev wheel, at an ancestor of the tag.

    GOAL033:delivery:checks:dev_wheels_per_block
    """
    receipt = _receipt("GOAL033_DEV_WHEELS_RECEIPT")
    validate_dev_wheels(receipt, _real_tree())
    assert receipt["obligation"] == "delivery:checks:dev_wheels_per_block"


def test_release_guides_kit_receipt():
    """The delivered kit carries the user guide PDF and the Linux guide of this version.

    GOAL033:delivery:checks:guides_kit
    """
    receipt = _receipt("GOAL033_GUIDES_KIT_RECEIPT")
    validate_guides_kit(receipt, _real_tree())
    assert receipt["obligation"] == "delivery:checks:guides_kit"


def test_release_linux_guide_receipt():
    """The Linux guide in the kit installs this version with pip.

    GOAL033:delivery:checks:linux_guide
    """
    receipt = _receipt("GOAL033_LINUX_GUIDE_RECEIPT")
    validate_linux_guide(receipt, _real_tree())
    assert receipt["obligation"] == "delivery:checks:linux_guide"


def test_release_d10_local_run_changes_only_executables_toml_receipt():
    """The Linux guide states that running locally changes only executables.toml.

    GOAL033:capability_ids:items:D10
    """
    receipt = _receipt("GOAL033_D10_RECEIPT")
    validate_d10(receipt, _real_tree())
    assert receipt["obligation"] == "capability_ids:items:D10"


def test_release_d15_kit_manifest_receipt():
    """The kit's members are exactly the listed ones, each hash recomputed.

    GOAL033:capability_ids:items:D15
    """
    receipt = _receipt("GOAL033_D15_RECEIPT")
    validate_d15(receipt, _real_tree())
    assert receipt["obligation"] == "capability_ids:items:D15"


def test_release_licensed_regressions_receipt():
    """The tier-3 licensed regressions ran on the tagged code with no failure.

    GOAL033:delivery:checks:licensed_regressions
    """
    receipt = _receipt("GOAL033_LICENSED_REGRESSIONS_RECEIPT")
    validate_licensed_regressions(receipt, _real_tree())
    assert receipt["obligation"] == "delivery:checks:licensed_regressions"


def test_release_tier1_tier2_regressions_receipt():
    """The final tier-1 suite and the licensed tier 2 passed on the tagged code.

    GOAL033:delivery:checks:tier1_tier2_regressions
    """
    receipt = _receipt("GOAL033_TIER1_TIER2_RECEIPT")
    validate_tier1_tier2(receipt, _real_tree())
    assert receipt["obligation"] == "delivery:checks:tier1_tier2_regressions"


def test_release_g39_native_volume_acceptance_receipt():
    """T33 re-run at the tag: native section kept, probe points and velocities agree.

    GOAL033:capability_ids:items:G39
    """
    receipt = _receipt("GOAL033_G39_RECEIPT")
    validate_g39(receipt, _real_tree())
    assert receipt["obligation"] == "capability_ids:items:G39"


def test_release_g63_research_campaign_receipt():
    """The research campaign ran matrix-qa.fs in fts-research on the published wheel.

    GOAL033:capability_ids:items:G63
    """
    receipt = _receipt("GOAL033_G63_RECEIPT")
    validate_g63(receipt, _real_tree())
    assert receipt["obligation"] == "capability_ids:items:G63"


def test_release_g66_reference_intake_receipt():
    """The three owner inputs were reviewed and every reference disposed of.

    GOAL033:capability_ids:items:G66
    """
    receipt = _receipt("GOAL033_G66_RECEIPT")
    validate_g66(receipt, _real_tree())
    assert receipt["obligation"] == "capability_ids:items:G66"


# --- G67: setup/BC completeness, measured now -------------------------------------------


def test_setup_bc_is_complete_every_in_scope_command_operational_the_rest_refused(tmp_path):
    """The setup/BC chapters of the 26.124 database are complete at this tree.

    GOAL033:capability_ids:items:G67

    Measured, not listed: the 13 setup/BC chapters hold 155 commands, and
    they divide exactly into 121 in scope and 34 not applicable (151, 121
    and 30 until 0.37.0, whose 26.125 database adds four setup commands no
    26.124 row carries, each refused on 26.124). Every
    in-scope command with a script route is BUILT here, stated and control,
    and the stated script carries the command's block while the control does
    not; the 12 whose operation is the native replay's carry that replay's
    marker in its file. Every one of the 33 commands 26.124 lacks is refused
    by the emitter naming it, and the one the owner excluded appears in no
    script any route writes.
    """
    from pyflightstream.commands import CommandRegistry
    from pyflightstream.script import Script
    from tests.tier1_offline import test_goal034_setup_operational_commands as setup

    registry = CommandRegistry.load()
    chapters = {n for n, e in registry.commands.items() if e.chapter in setup.SETUP_CHAPTERS}
    elsewhere = {c for commands in setup.PROVED_ELSEWHERE.values() for c in commands}
    routed = set(setup.ROUTES) | set(setup.SCRIPT_ROUTES) | elsewhere
    refused = set(setup.REFUSED_ON_26124) | set(setup.OWNER_EXCLUDED)
    assert len(setup.SETUP_CHAPTERS) == 13
    assert (len(chapters), len(routed), len(refused)) == (155, 121, 34)
    assert routed | refused == chapters and not routed & refused

    broken, written = [], []
    for index, (command, route) in enumerate(sorted(setup.ROUTES.items())):
        stated_dir, control_dir = tmp_path / f"r{index}s", tmp_path / f"r{index}c"
        stated_dir.mkdir()
        control_dir.mkdir()
        lines, why = setup._render(route.stated(stated_dir))
        if lines is None or not setup._carries(lines, route.block):
            broken.append(f"{command}: stated {why[:120] or 'lacks its block'}")
            continue
        written.extend(lines)
        if route.control is not None:
            control, why = setup._render(route.control(control_dir))
            if control is None or setup._carries(control, route.block):
                broken.append(f"{command}: control {why[:120] or 'carries the block'}")
    for index, (command, route) in enumerate(sorted(setup.SCRIPT_ROUTES.items())):
        stated_dir, control_dir = tmp_path / f"s{index}s", tmp_path / f"s{index}c"
        stated_dir.mkdir()
        control_dir.mkdir()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            lines, control = route.stated(stated_dir), route.control(control_dir)
        written.extend(lines)
        if not setup._carries(lines, route.block) or setup._carries(control, route.block):
            broken.append(f"{command}: script route does not discriminate")
    for path, commands in setup.PROVED_ELSEWHERE.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        broken += [c for c in commands if f"GOAL033:setup_bc:operational_commands:{c}" not in text]
    assert not broken, "in scope and not operational:\n  " + "\n  ".join(broken)

    admitted = []
    for command, error in setup.REFUSED_ON_26124.items():
        script = Script(setup.BUILD)
        with pytest.raises(error) as refusal:
            script.emit(command)
        if command not in str(refusal.value) or command in script.render():
            admitted.append(command)
    assert not admitted, f"not refused by name: {admitted}"
    excluded = [line for line in written if line.split(" ", 1)[0] in setup.OWNER_EXCLUDED]
    assert not excluded, f"an owner-excluded command is written: {excluded[:3]}"


# --- falsifiability: every validator accepts a valid receipt and refuses a wrong field ---

VERSION = "0.29.0"
HEAD = "a" * 40
ANCESTOR = "b" * 40
SOURCE_BYTES = b"source at head\n"


def _tree() -> Tree:
    return Tree(
        VERSION,
        HEAD,
        lambda rev: rev == ANCESTOR,
        lambda path: hashlib.sha256(SOURCE_BYTES).hexdigest() if path in G39_SOURCES else None,
    )


def _pdf(text: str) -> bytes:
    """A one-page PDF whose extracted text is ``text`` (no parentheses)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def _wheel(path: Path, version: str) -> Path:
    with zipfile.ZipFile(path, "w") as wheel:
        meta = f"Metadata-Version: 2.1\nName: pyflightstream\nVersion: {version}\n"
        wheel.writestr(f"pyflightstream-{version}.dist-info/METADATA", meta)
    return path


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def _art(role: str, path: Path) -> dict:
    return {"role": role, "path": str(path), "sha256": _sha256(path)}


def _base(obligation: str, artifacts: list[dict], facts: dict, code: bool) -> dict:
    receipt = {
        "schema": SCHEMA,
        "obligation": obligation,
        "package": "pyflightstream",
        "version": VERSION,
        "recorded_at": "2026-09-28T00:00:00Z",
        "artifacts": artifacts,
        "facts": facts,
    }
    if code:
        receipt["product_revision"] = HEAD
    return receipt


LINUX_TEXT = (
    f"pyflightstream {VERSION} on Linux: pip install pyflightstream=={VERSION}.\n"
    "To run a matrix locally on Linux, change only\nthe executable path in executables.toml."
)


def _kit_zip(tmp: Path) -> Path:
    path = tmp / f"DLV-014-015_fts-guides_pyflightstream-{VERSION}.zip"
    with zipfile.ZipFile(path, "w") as kit:
        kit.writestr("guide.pdf", _pdf(f"The fts-workspace guide for pyflightstream {VERSION}"))
        kit.writestr("linux.md", LINUX_TEXT)
    return path


def _junit_file(path: Path, tests: int, failures: int = 0, skipped: int = 0) -> Path:
    def body(i: int) -> str:
        return "<failure/>" if i < failures else "<skipped/>" if i >= tests - skipped else ""

    cases = "".join(f'<testcase name="t{i}">{body(i)}</testcase>' for i in range(tests))
    return _write(path, f"<testsuites><testsuite>{cases}</testsuite></testsuites>")


G39_POINTS = "POINTS 2 float\n0 0 0 1 0.5 0.25\nVERTICES 2 4\n1 0\n1 1"
PROBE_DATA = "POINT_DATA 2\nVECTORS Velocity float\n30 0 0\n29.5 0.1 0"
NATIVE_DATA = (
    "POINT_DATA 2\nSCALARS Vx float 1\nLOOKUP_TABLE default\n30.0004 29.5\n"
    "SCALARS Vy float\nLOOKUP_TABLE default\n0 0.1\n"
    "SCALARS Vz float 1\nLOOKUP_TABLE default\n0.0002 0"
)


def _vtk_file(path: Path, body: str) -> Path:
    return _write(
        path, f"# vtk DataFile Version 3.0\nPOINTS title\nASCII\nDATASET POLYDATA\n{body}\n"
    )


def _replace(receipt: dict, role: str, data: bytes | str) -> Path:
    """Rewrite one artifact's file and re-hash it, so only its content differs."""
    item = next(a for a in receipt["artifacts"] if a["role"] == role)
    path = _write(Path(item["path"]), data)
    item["sha256"] = _sha256(path)
    return path


def _rewrite_vtk(role: str, data: str) -> Callable[[dict], None]:
    """Replace one G39 VTK's POINT_DATA with ``data`` and re-hash it."""

    def mutate(receipt: dict) -> None:
        item = next(a for a in receipt["artifacts"] if a["role"] == role)
        _vtk_file(Path(item["path"]), f"{G39_POINTS}\n{data}")
        item["sha256"] = _sha256(Path(item["path"]))

    return mutate


def _build_clean_install(tmp: Path) -> dict:
    wheel = _wheel(tmp / f"pyflightstream-{VERSION}-py3-none-any.whl", VERSION)
    _write(tmp / "venv" / "pyvenv.cfg", "home = x\n")
    python = _write(tmp / "venv" / "Scripts" / "python.exe", b"MZ")
    log = _write(tmp / "pip.log", f"Successfully installed pyflightstream-{VERSION}\n")
    helped = _write(tmp / "help.txt", "usage: pyfs-matrix [-h]\n")
    return _base(
        "delivery:checks:clean_install",
        [_art("wheel", wheel), _art("venv_python", python), _art("pip_log", log)]
        + [_art("pyfs_matrix_help", helped)],
        {
            "index": "https://pypi.org/simple/",
            "requirement": f"pyflightstream=={VERSION}",
            "fresh_venv": True,
            "pypi_wheel_sha256": _sha256(wheel),
            "import_version_output": VERSION,
            "pyfs_matrix_help_exit": 0,
        },
        code=False,
    )


def _build_dev_wheels(tmp: Path) -> dict:
    blocks = []
    for number in (1, 2):
        version = f"{VERSION}.dev{number}"
        path = _wheel(tmp / f"pyflightstream-{version}-py3-none-any.whl", version)
        wheel = {"path": str(path), "sha256": _sha256(path), "version": version}
        blocks.append({"block": f"B{number}", "revision": ANCESTOR, "wheels": [wheel]})
    return _base("delivery:checks:dev_wheels_per_block", [], {"blocks": blocks}, code=True) | {
        "artifacts": [_art("log", _write(tmp / "build.log", "built\n"))]
    }


def _kit_receipt(tmp: Path, obligation: str, facts: dict) -> dict:
    return _base(obligation, [_art("kit", _kit_zip(tmp))], facts, code=False)


def _build_guides_kit(tmp: Path) -> dict:
    facts = {"user_guide_member": "guide.pdf", "linux_guide_member": "linux.md"}
    return _kit_receipt(tmp, "delivery:checks:guides_kit", facts)


def _build_linux_guide(tmp: Path) -> dict:
    return _kit_receipt(tmp, "delivery:checks:linux_guide", {"linux_guide_member": "linux.md"})


def _build_d10(tmp: Path) -> dict:
    facts = {"linux_guide_member": "linux.md", "executables_statement": STATEMENT}
    return _kit_receipt(tmp, "capability_ids:items:D10", facts)


def _build_d15(tmp: Path) -> dict:
    kit = _kit_zip(tmp)
    with zipfile.ZipFile(kit) as opened:
        members = [
            {"name": n, "sha256": hashlib.sha256(opened.read(n)).hexdigest()}
            for n in opened.namelist()
        ]
    facts = {"user_guide_member": "guide.pdf", "linux_guide_member": "linux.md"}
    return _base(
        "capability_ids:items:D15", [_art("kit", kit)], facts | {"members": members}, code=False
    )


def _build_licensed(tmp: Path) -> dict:
    junit = _junit_file(tmp / "tier3.xml", 5)
    matrix = _write(tmp / "matrix-a.csv", "row\n")
    counts = {"tests": 5, "failures": 0, "errors": 0, "skipped": 0}
    return _base(
        "delivery:checks:licensed_regressions",
        [_art("junit", junit), _art("matrix:matrix-a", matrix)],
        {"tier": 3, "build": "26.124", "executable_sha256": "c" * 64, "matrices": ["matrix-a"]}
        | counts,
        code=True,
    )


def _build_tier1_tier2(tmp: Path) -> dict:
    tier1 = _junit_file(tmp / "tier1.xml", 7001)
    tier2 = _junit_file(tmp / "tier2.xml", 3)
    return _base(
        "delivery:checks:tier1_tier2_regressions",
        [_art("tier1_junit", tier1), _art("tier2_junit", tier2)],
        {
            "tier1": {"tests": 7001, "failures": 0, "errors": 0, "skipped": 0},
            "tier2": {"tests": 3, "failures": 0, "errors": 0, "skipped": 0},
            "tier2_build": "26.124",
            "tier2_licensed": True,
        },
        code=True,
    )


def _build_g39(tmp: Path) -> dict:
    section = b"$VOLUME_SECTION_START$\n1 2 3\n$VOLUME_SECTION_END$\n"
    digest = hashlib.sha256(SOURCE_BYTES).hexdigest()
    probe = _vtk_file(tmp / "probe.vtk", f"{G39_POINTS}\n{PROBE_DATA}")
    native = _vtk_file(tmp / "native.vtk", f"{G39_POINTS}\n{NATIVE_DATA}")
    return _base(
        "capability_ids:items:G39",
        [
            _art("native_section_saved", _write(tmp / "saved.txt", section)),
            _art("native_section_reopened", _write(tmp / "reopened.txt", section)),
            _art("probe_vtk", probe),
            _art("native_export_vtk", native),
        ],
        {
            "native_volume_byte_identical": True,
            "probe_velocity": "Velocity",
            "native_velocity": ["Vx", "Vy", "Vz"],
            "max_velocity_error": 30.0004 - 30.0,
            "csv_quantization": 0.0005,
            "sources": [{"path": p, "sha256": digest} for p in G39_SOURCES],
        },
        code=True,
    )


def _build_g63(tmp: Path) -> dict:
    wheel = _wheel(tmp / f"pyflightstream-{VERSION}-py3-none-any.whl", VERSION)
    results = [
        _art(f"result:{case}", _write(tmp / f"{case}.json", json.dumps(result)))
        for case, result in (
            ("c1", {"case": "c1", "complete": True}),
            ("c2", {"case": "c2", "complete": True}),
        )
    ]
    return _base(
        "capability_ids:items:G63",
        [
            _art("wheel", wheel),
            _art("matrix", _write(tmp / "matrix-qa.fs", "matrix\n")),
            _art("synthesis_report", _write(tmp / "synthesis.md", "# synthesis\nc1 and c2\n")),
            *results,
        ],
        {
            "workspace": "fts-research",
            "matrix": "matrix-qa.fs",
            "pypi_wheel_sha256": _sha256(wheel),
            "cases": [{"id": "c1", "status": "completed"}, {"id": "c2", "status": "completed"}],
            "completed_cases": 2,
        },
        code=False,
    )


def _build_g66(tmp: Path) -> dict:
    refs = tmp / "inputs" / G66_INPUTS[0]
    refs.parent.mkdir(parents=True)
    with zipfile.ZipFile(refs, "w") as archive:
        archive.writestr("a/", "")
        archive.writestr("a/one.pdf", b"%PDF-1.4")
        archive.writestr("two.txt", "x")
    artifacts = [_art(f"input:{G66_INPUTS[0]}", refs)]
    for number, name in enumerate(G66_INPUTS):
        if number:
            artifacts.append(_art(f"input:{name}", _write(tmp / f"in{number}.pdf", b"%PDF-1.4")))
        artifacts.append(_art(f"summary:{name}", _write(tmp / f"summary{number}.md", "read\n")))
    inputs = [{"name": name, "reviewed": True} for name in G66_INPUTS]
    return _base(
        "capability_ids:items:G66",
        artifacts,
        {"inputs": inputs, "dispositions": 4},
        code=False,
    )


def _set(*keys: str | int, value: object) -> Callable[[dict], None]:
    def mutate(receipt: dict) -> None:
        target = receipt
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return mutate


def _bad_hash(receipt: dict) -> None:
    receipt["artifacts"][0]["sha256"] = "0" * 64


COMMON = {
    "version": _set("version", value="0.28.0"),
    "obligation": _set("obligation", value="delivery:checks:docs"),
    "artifact_hash": _bad_hash,
}
CODE = {"revision": _set("product_revision", value="d" * 40)}

CASES: dict[str, tuple[Callable, Callable, dict[str, Callable[[dict], None]]]] = {
    "clean_install": (
        _build_clean_install,
        validate_clean_install,
        {
            "pypi_digest": _set("facts", "pypi_wheel_sha256", value="e" * 64),
            "import_version": _set("facts", "import_version_output", value="0.28.0"),
            "help_exit": _set("facts", "pyfs_matrix_help_exit", value=2),
            "not_pypi": _set("facts", "index", value="https://test.pypi.org/simple/"),
        },
    ),
    "dev_wheels": (
        _build_dev_wheels,
        validate_dev_wheels,
        CODE
        | {
            "not_dev": _set("facts", "blocks", 0, "wheels", 0, "version", value=VERSION),
            "not_ancestor": _set("facts", "blocks", 0, "revision", value="f" * 40),
            "empty_block": _set("facts", "blocks", 1, "wheels", value=[]),
            "wheel_hash": _set("facts", "blocks", 0, "wheels", 0, "sha256", value="0" * 64),
        },
    ),
    "guides_kit": (
        _build_guides_kit,
        validate_guides_kit,
        {
            "no_member": _set("facts", "linux_guide_member", value="absent.md"),
            "user_not_pdf": _set("facts", "user_guide_member", value="linux.md"),
        },
    ),
    "linux_guide": (
        _build_linux_guide,
        validate_linux_guide,
        {"wrong_member": _set("facts", "linux_guide_member", value="guide.pdf")},
    ),
    "d10": (
        _build_d10,
        validate_d10,
        {
            "not_in_guide": _set("facts", "executables_statement", value="edit executables.toml"),
            "no_toml": _set("facts", "executables_statement", value="change only the path"),
            "bare_filename": _set("facts", "executables_statement", value="executables.toml"),
            "member_lacks_it": _set("facts", "linux_guide_member", value="guide.pdf"),
        },
    ),
    "d15": (
        _build_d15,
        validate_d15,
        {
            "member_hash": _set("facts", "members", 0, "sha256", value="0" * 64),
            "member_missing": lambda r: r["facts"]["members"].pop(),
        },
    ),
    "licensed_regressions": (
        _build_licensed,
        validate_licensed_regressions,
        CODE
        | {
            "count": _set("facts", "tests", value=6),
            "tier": _set("facts", "tier", value=2),
            "matrix_unhashed": _set("facts", "matrices", value=["matrix-a", "matrix-b"]),
        },
    ),
    "tier1_tier2": (
        _build_tier1_tier2,
        validate_tier1_tier2,
        CODE
        | {
            "tier1_count": _set("facts", "tier1", "tests", value=7002),
            "tier2_licensed": _set("facts", "tier2_licensed", value=False),
        },
    ),
    "g39": (
        _build_g39,
        validate_g39,
        CODE
        | {
            "error": _set("facts", "max_velocity_error", value=0.0006),
            "error_understated": _set("facts", "max_velocity_error", value=0.0),
            "quantization": _set("facts", "csv_quantization", value=0.0001),
            # CXQ8R6-3: a later NaN is ignored by max(), and a NaN or infinite
            # quantization compares False/True the wrong way.
            "native_nan": _rewrite_vtk(
                "native_export_vtk", NATIVE_DATA.replace("0.0002 0", "0.0002 nan")
            ),
            "probe_inf": _rewrite_vtk(
                "probe_vtk", PROBE_DATA.replace("29.5 0.1 0", "29.5 0.1 inf")
            ),
            "quantization_nan": _set("facts", "csv_quantization", value=float("nan")),
            "quantization_inf": _set("facts", "csv_quantization", value=float("inf")),
            "quantization_zero": _set("facts", "csv_quantization", value=0.0),
            "quantization_bool": _set("facts", "csv_quantization", value=True),
            "velocity_array": _set("facts", "probe_velocity", value="Pressure"),
            "velocity_scalars": _set("facts", "native_velocity", value=["Vx", "Vy"]),
            "source": _set("facts", "sources", 0, "sha256", value="0" * 64),
            "sources_short": lambda r: r["facts"]["sources"].pop(),
            "bool_only": _set("facts", "native_volume_byte_identical", value=False),
        },
    ),
    "g63": (
        _build_g63,
        validate_g63,
        {
            "workspace": _set("facts", "workspace", value="fts-workspace"),
            "wheel_digest": _set("facts", "pypi_wheel_sha256", value="e" * 64),
            "incomplete": _set("facts", "cases", 1, "status", value="failed"),
            "count": _set("facts", "completed_cases", value=3),
            "result_missing": lambda r: r["artifacts"].pop(),
            "case_unreported": _set("facts", "cases", 1, "id", value="c3"),
        },
    ),
    "g66": (
        _build_g66,
        validate_g66,
        {
            "dispositions": _set("facts", "dispositions", value=3),
            "unreviewed": _set("facts", "inputs", 2, "reviewed", value=False),
            "two_inputs": lambda r: r["facts"]["inputs"].pop(),
        },
    ),
}


#: The validators that read a PDF member of the kit; only they need the optional pypdf.
READS_PDF = {"guides_kit", "linux_guide", "d10", "d15"}


@pytest.mark.parametrize("name", sorted(CASES))
def test_receipt_validator_accepts_the_valid_receipt(name, tmp_path):
    if name in READS_PDF:
        pytest.importorskip("pypdf")
    build, validate, _ = CASES[name]
    validate(build(tmp_path), _tree())


@pytest.mark.parametrize(
    "name,field",
    [
        (name, field)
        for name, (_, _, own) in sorted(CASES.items())
        for field in sorted(COMMON | own)
    ],
)
def test_receipt_validator_refuses_one_wrong_field(name, field, tmp_path):
    if name in READS_PDF:
        pytest.importorskip("pypdf")
    build, validate, own = CASES[name]
    receipt = copy.deepcopy(build(tmp_path))
    validate(copy.deepcopy(receipt), _tree())  # the control: unchanged, it is accepted
    (COMMON | own)[field](receipt)
    with pytest.raises(ReceiptRefusedError):
        validate(receipt, _tree())


# --- artifact content, not receipt fields: each edit rewrites a hashed file and re-hashes ---


def _refused_after(build, validate, edit, tmp_path, match: str) -> None:
    receipt = build(tmp_path)
    validate(copy.deepcopy(receipt), _tree())  # the control
    edit(receipt)
    with pytest.raises(ReceiptRefusedError, match=match):
        validate(receipt, _tree())


def test_g39_recomputes_the_velocity_difference_rather_than_trusting_the_receipt(tmp_path):
    """Velocities 100 apart with ``max_velocity_error`` 0 are refused (CXQ8R5-2)."""

    def edit(receipt: dict) -> None:
        shifted = NATIVE_DATA.replace("30.0004 29.5", "130 29.5")
        _replace(
            receipt,
            "native_export_vtk",
            f"# vtk DataFile Version 3.0\nx\nASCII\nDATASET POLYDATA\n{G39_POINTS}\n{shifted}\n",
        )
        receipt["facts"]["max_velocity_error"] = 0

    _refused_after(_build_g39, validate_g39, edit, tmp_path, "beyond the CSV quantization")


def test_g39_refuses_a_velocity_array_the_export_does_not_carry(tmp_path):
    def edit(receipt: dict) -> None:
        _replace(receipt, "native_export_vtk", f"# vtk\nx\nASCII\nDATASET POLYDATA\n{G39_POINTS}\n")

    _refused_after(_build_g39, validate_g39, edit, tmp_path, "no array Vx")


def test_g63_refuses_a_wheel_that_is_not_a_zip(tmp_path):
    """A file saying ``not a zip or wheel`` with PyPI's digest set to its hash (CXQ8R5-2)."""

    def edit(receipt: dict) -> None:
        wheel = _replace(receipt, "wheel", b"not a zip or wheel")
        receipt["facts"]["pypi_wheel_sha256"] = _sha256(wheel)

    _refused_after(_build_g63, validate_g63, edit, tmp_path, "not a zip")


def test_g63_refuses_a_wheel_of_another_version(tmp_path):
    def edit(receipt: dict) -> None:
        wheel = _replace(receipt, "wheel", b"")
        _wheel(wheel, "0.28.0")
        receipt["artifacts"][0]["sha256"] = receipt["facts"]["pypi_wheel_sha256"] = _sha256(wheel)

    _refused_after(_build_g63, validate_g63, edit, tmp_path, "METADATA")


def test_g63_refuses_completed_over_a_case_result_that_says_incomplete(tmp_path):
    def edit(receipt: dict) -> None:
        _replace(receipt, "result:c2", json.dumps({"case": "c2", "complete": False}))

    _refused_after(_build_g63, validate_g63, edit, tmp_path, "does not state completion")


def test_g63_refuses_a_case_result_of_another_case(tmp_path):
    def edit(receipt: dict) -> None:
        _replace(receipt, "result:c2", json.dumps({"case": "c1", "complete": True}))

    _refused_after(_build_g63, validate_g63, edit, tmp_path, "case")


def test_g63_refuses_a_synthesis_that_names_no_case(tmp_path):
    def edit(receipt: dict) -> None:
        _replace(receipt, "synthesis_report", "ALL CASES FAILED\n")

    _refused_after(_build_g63, validate_g63, edit, tmp_path, "does not name")


def test_g63_refuses_an_empty_synthesis(tmp_path):
    def edit(receipt: dict) -> None:
        _replace(receipt, "synthesis_report", "  \n")

    _refused_after(_build_g63, validate_g63, edit, tmp_path, "empty")


def test_tier1_counts_passing_tests_not_skipped_ones(tmp_path):
    """7001 cases of which one skipped is 7000 passing: refused (CXQ8R5-3)."""

    def edit(receipt: dict) -> None:
        junit = _junit_file(tmp_path / "tier1.xml", 7001, skipped=1)
        item = next(a for a in receipt["artifacts"] if a["role"] == "tier1_junit")
        item["sha256"] = _sha256(junit)
        receipt["facts"]["tier1"]["skipped"] = 1

    _refused_after(_build_tier1_tier2, validate_tier1_tier2, edit, tmp_path, "passing tests")


def test_a_code_receipt_is_refused_without_its_product_revision(tmp_path):
    receipt = _build_g39(tmp_path)
    del receipt["product_revision"]
    with pytest.raises(ReceiptRefusedError, match="product_revision"):
        validate_g39(receipt, _tree())
