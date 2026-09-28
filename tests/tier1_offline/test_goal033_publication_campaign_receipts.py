"""Tier 1, GOAL-033: the publication and research-campaign facts, verified at the tag.

WHY THIS FILE EXISTS. The GOAL-033 checker proves its ``publication`` and
``research_campaign`` arms through bindings too: every ``checks`` row of
publication and every ``studies`` row of the campaign must be bound to a
passing test, pinned at the v0.29.0 tag, whose body names that exact
obligation. Those facts exist only after the release is public (tag, GitHub
release, PyPI, Zenodo, CI) or after the licensed campaign ran on the
published wheel, so their tests are in the tag and replay a RECEIPT produced
later. The pattern, the common envelope and the helpers are those of the
sibling ``test_goal033_release_receipts.py`` and are imported from it.

HOW A RECEIPT IS READ. Each marker test reads one JSON receipt from its own
environment variable and SKIPS, naming it, when unset; a skip is never a PASS
for the checker. Receipts and their files live outside the repository.
Nothing in a receipt is trusted: every named file is hashed again from disk,
every public-service answer is kept as the JSON file the service returned
(an artifact, hashed) and is re-read here, the release identity is compared
with this tree's pyproject version and ``git rev-parse HEAD``, and the GitHub
repository is the one this tree's ``origin`` names.

COMMON ENVELOPE: exactly the sibling's (``schema`` ==
``goal033-release-receipt/1``, ``obligation`` ==
``<arm>:<field>:<id>``, ``package`` == ``pyflightstream``, ``version`` ==
the tree's version, ``product_revision`` == HEAD where marked [code],
``recorded_at``, ``artifacts`` ``[{role, path, sha256}]`` re-hashed, and
``facts``). Below, "role X" is an artifact with that role; "JSON role X" is
one holding a service's JSON answer verbatim.

PUBLICATION (variable -> obligation ``publication:checks:<id>``):

* ``GOAL033_REMOTE_TAG_RECEIPT`` -> ``remote_tag`` [code]. JSON role
  ``ref_response`` = GET ``https://api.github.com/repos/<repo>/git/ref/tags/
  v<version>``; if its object is an annotated tag, JSON role
  ``tag_object_response`` = GET ``.../git/tags/<object sha>``. Facts
  ``repository`` == origin's ``owner/name``, ``api_url`` == the ref URL,
  ``resolved_commit``. The ref must be ``refs/tags/v<version>`` and resolve
  (directly or through the tag object) to a commit equal to HEAD and to
  ``resolved_commit``.
* ``GOAL033_GITHUB_RELEASE_RECEIPT`` -> ``github_release``. JSON role
  ``release_response`` = GET ``.../releases/tags/v<version>``. Facts
  ``repository``, ``api_url``. The answer's ``tag_name`` == ``v<version>``,
  ``draft`` and ``prerelease`` are false, ``published_at`` is a timestamp and
  ``html_url`` is ``https://github.com/<repo>/releases/tag/v<version>``.
* ``GOAL033_PYPI_DOWNLOAD_RECEIPT`` -> ``pypi_download``. JSON role
  ``pypi_json`` = GET ``https://pypi.org/pypi/pyflightstream/<version>/json``;
  role ``wheel`` = the file downloaded,
  ``pyflightstream-<version>-py3-none-any.whl``. Facts ``api_url``,
  ``download_url`` (a ``https://files.pythonhosted.org/`` URL) and
  ``pypi_wheel_sha256``. The answer's ``info`` names the package and version;
  its non-yanked ``bdist_wheel`` entry for that file name has that URL and a
  sha256 equal to the fact and to the downloaded file's hash; the wheel's
  METADATA version == version.
* ``GOAL033_ZENODO_RECORD_RECEIPT`` -> ``zenodo_record``. JSON role
  ``record_response`` = GET ``https://zenodo.org/api/records/<record_id>``.
  Facts ``record_id`` (int), ``api_url``, ``doi`` (``10.5281/zenodo.
  <record_id>``), ``concept_doi`` and ``repository``. The answer's ``id``,
  ``doi`` and ``conceptdoi`` equal the facts, the concept DOI differs from the
  version DOI, ``submitted`` is true, ``metadata.version`` == version, and a
  ``metadata.related_identifiers`` entry names ``github.com/<repo>`` and
  ``v<version>``.
* ``GOAL033_ZENODO_FILES_RECEIPT`` -> ``zenodo_files``. JSON role
  ``record_response`` as above; role ``file:<key>`` for EVERY file key of the
  record, and no other ``file:`` role. Facts ``doi``. Each local file is named
  as its key and its md5 equals the record's ``md5:`` checksum (and its size
  the record's size where given); one key carries ``v<version>``.
* ``GOAL033_CI_RECEIPT`` -> ``ci`` and ``GOAL033_DOCS_CI_RECEIPT`` ->
  ``docs_ci`` [code]. JSON role ``runs_response`` = GET
  ``https://api.github.com/repos/<repo>/actions/runs?head_sha=<HEAD>&per_page=100``.
  Facts ``repository``, ``api_url`` and ``workflows``: the sorted names of
  every run in the answer whose lower-cased name contains ``ci`` (for
  ``docs_ci``: ``docs``), non-empty. For each such name the latest run (by
  ``id``) has ``head_sha`` == HEAD, ``status`` ``completed`` and
  ``conclusion`` ``success``; every run in the answer is for HEAD.
* ``GOAL033_PUBLICATION_CLEAN_INSTALL_RECEIPT`` -> ``clean_install``. The
  sibling's clean-install receipt (roles ``wheel``, ``venv_python``,
  ``pip_log``, ``pyfs_matrix_help``; its facts) with this obligation; it is
  validated by the sibling's validator.
* ``GOAL033_PRIVACY_SCAN_RECEIPT`` -> ``privacy_scan``. Roles ``wheel``
  (``pyflightstream-<version>-py3-none-any.whl``), ``sdist``
  (``pyflightstream-<version>.tar.gz``), ``terms`` (the private-term list, one
  term per line, blank lines and ``#`` lines ignored, each term at least 3
  characters; it stays outside the tree). Facts ``pypi_wheel_sha256`` and
  ``pypi_sdist_sha256`` (the artifacts' hashes), ``terms_count``,
  ``scanned_members`` and ``matches`` == ``[]``. The scan is REDONE here:
  every member name and member content of both archives, case-folded, against
  every term; the recomputed counts and matches must equal the facts.

RESEARCH CAMPAIGN (variable ``GOAL033_STUDY_<ID>_RECEIPT``, ``<ID>`` the study
id upper-cased -> obligation ``research_campaign:studies:<id>``), for the ten
flag studies, the five FSI studies, ``synthesis`` and ``comparison_history``.
Every study receipt carries:

* roles ``matrix`` (named ``matrix-qa.fs``), ``wheel``
  (``pyflightstream-<version>-py3-none-any.whl``, METADATA version ==
  version), JSON role ``pypi_json`` (as in ``pypi_download``: its
  ``bdist_wheel`` entry for the wheel's name has the wheel's sha256), JSON
  role ``standards_capture`` (``{"argv": [..., "pyfs-matrix", "plan", ...,
  "--setup-standards"], "exit_code": 0, "wheel_sha256", "outputs": {name:
  sha256}}``, its wheel hash == the wheel's) and ``standard:<name>`` for each
  output, re-hashed to it; role ``report`` (the study's comparison and
  interpretation report, non-empty);
* facts ``study`` == id, ``workspace`` == ``fts-research``, ``matrix`` ==
  ``matrix-qa.fs``, ``execution`` == ``local-licensed``,
  ``pypi_wheel_sha256`` == the wheel's hash, ``campaign_started_at``: later
  than the wheel's PyPI ``upload_time_iso_8601``.

An EXPERIMENT study (flag and FSI) also carries facts ``cases``: non-empty
``[{"id", "status": "completed"}]`` with unique ids, a role ``result:<id>``
for each case (its result file, non-empty), and a report that names every
case id. An FSI study also carries roles ``material_source``,
``supplied_properties`` and ``calibration_file`` (TOML) and facts ``fsi``:
``{"material": "Ti-6Al-4V", "calibrations": {"file": C, "matrix": C}}``, each
C ``{"factors", "base", "effective"}`` over the same non-empty property
names with positive finite factors and effective == base x factor; every
file factor is a key of the TOML with that value; the matrix calibration also
carries ``columns`` {property: column} and each column name occurs in the
matrix file. ``synthesis`` carries facts ``report_file`` (the report's file
name) and ``covered_studies`` == the fifteen experiment studies, each named
in the report. ``comparison_history`` carries ``report_file`` and
``versions``: the release version and at least one earlier one, each named in
the report.

The unmarked tests at the end build a valid synthetic receipt per obligation,
show it ACCEPTED (the control) and show single-field corruptions REFUSED. They
run without any receipt.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import math
import re
import subprocess
import tarfile
import tomllib
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from packaging.version import Version

from tests.tier1_offline.test_goal033_release_receipts import (
    ROOT,
    SCHEMA,
    ReceiptRefusedError,
    Tree,
    _build_clean_install,
    _envelope,
    _need,
    _real_tree,
    _receipt,
    _role,
    _sha256,
    _wheel_metadata,
    validate_clean_install,
)

FLAG_STUDIES = (
    "wake_controls",
    "rotor_induced_velocity_blending",
    "laminar_separation",
    "airfoil_separation",
    "valarezo",
    "adverse_gradient_boundary_layer",
    "wake_decay",
    "incompressible",
    "transonic",
    "temporal_convergence",
)
FSI_STUDIES = (
    "fsi_calculated_titanium",
    "fsi_supplied_properties",
    "fsi_file_calibration",
    "fsi_matrix_calibration",
    "fsi_usability",
)
EXPERIMENT_STUDIES = FLAG_STUDIES + FSI_STUDIES
STUDIES = EXPERIMENT_STUDIES + ("synthesis", "comparison_history")
MATERIAL = "Ti-6Al-4V"
GITHUB = re.compile(
    r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?"
)


def _origin_repository() -> str:
    """The ``owner/name`` this tree's ``origin`` names on GitHub."""
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, check=False
    )
    match = GITHUB.fullmatch(remote.stdout.decode("utf-8", "replace").strip())
    _need(remote.returncode == 0 and match, "origin is not a GitHub repository")
    assert match
    return match.group(1)


def _json(roles: dict[str, Path], role: str) -> dict:
    try:
        data = json.loads(_role(roles, role).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptRefusedError(f"{role}: not JSON ({error})") from error
    _need(isinstance(data, dict), f"{role}: not a JSON object")
    return data


def _when(value: object, what: str) -> datetime:
    _need(isinstance(value, str), f"{what}: timestamp missing")
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ReceiptRefusedError(f"{what}: not ISO-8601") from error
    _need(moment.tzinfo is not None, f"{what}: timestamp without offset")
    return moment


def _publication(receipt: object, ident: str, tree: Tree, *, code: bool = False):
    return _envelope(receipt, f"publication:checks:{ident}", tree, code=code)


def _github_facts(facts: dict, repo: str, url: str) -> None:
    _need(facts.get("repository") == repo, f"repository is not origin's {repo}")
    _need(facts.get("api_url") == url, f"api_url is not {url}")


# --- publication validators ----------------------------------------------------------


def validate_remote_tag(receipt: object, tree: Tree, repo: str) -> dict:
    roles, facts = _publication(receipt, "remote_tag", tree, code=True)
    tag = f"v{tree.version}"
    base = f"https://api.github.com/repos/{repo}"
    _github_facts(facts, repo, f"{base}/git/ref/tags/{tag}")
    ref = _json(roles, "ref_response")
    _need(ref.get("ref") == f"refs/tags/{tag}", f"the answer is not refs/tags/{tag}")
    target = ref.get("object")
    _need(isinstance(target, dict), "the ref answer has no object")
    if target.get("type") == "tag":
        annotated = _json(roles, "tag_object_response")
        _need(annotated.get("sha") == target.get("sha"), "the tag object is another tag's")
        _need(annotated.get("tag") == tag, f"the tag object is not {tag}")
        target = annotated.get("object")
        _need(isinstance(target, dict), "the tag object points at nothing")
    _need(target.get("type") == "commit", "the tag does not resolve to a commit")
    _need(
        target.get("sha") == tree.head,
        f"the remote tag resolves to another commit than {tree.head}",
    )
    _need(facts.get("resolved_commit") == tree.head, "resolved_commit")
    return facts


def validate_github_release(receipt: object, tree: Tree, repo: str) -> dict:
    roles, facts = _publication(receipt, "github_release", tree)
    tag = f"v{tree.version}"
    _github_facts(facts, repo, f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    release = _json(roles, "release_response")
    _need(release.get("tag_name") == tag, f"the release is not {tag}")
    _need(release.get("draft") is False, "the release is a draft")
    _need(release.get("prerelease") is False, "the release is a prerelease")
    _when(release.get("published_at"), "published_at")
    expected = f"https://github.com/{repo}/releases/tag/{tag}"
    _need(release.get("html_url") == expected, "html_url is not this repository's release")
    return release


def _pypi_wheel_entry(pypi: dict, wheel: Path, tree: Tree) -> dict:
    info = pypi.get("info")
    _need(isinstance(info, dict), "PyPI answer has no info")
    _need(
        str(info.get("name", "")).lower() == "pyflightstream", "PyPI answer names another package"
    )
    _need(info.get("version") == tree.version, f"PyPI answer is not {tree.version}")
    urls = pypi.get("urls")
    _need(isinstance(urls, list), "PyPI answer has no files")
    entries = [
        u
        for u in urls
        if isinstance(u, dict)
        and u.get("filename") == wheel.name
        and u.get("packagetype") == "bdist_wheel"
        and not u.get("yanked")
    ]
    _need(len(entries) == 1, f"PyPI does not publish {wheel.name} exactly once")
    digest = entries[0].get("digests", {}).get("sha256")
    _need(digest == _sha256(wheel), "the wheel differs from PyPI's digest")
    return entries[0]


def _release_wheel(roles: dict[str, Path], tree: Tree) -> Path:
    wheel = _role(roles, "wheel")
    _need(wheel.name == f"pyflightstream-{tree.version}-py3-none-any.whl", f"wheel {wheel.name}")
    _need(_wheel_metadata(wheel) == ("pyflightstream", tree.version), "wheel METADATA")
    return wheel


def validate_pypi_download(receipt: object, tree: Tree) -> dict:
    roles, facts = _publication(receipt, "pypi_download", tree)
    url = f"https://pypi.org/pypi/pyflightstream/{tree.version}/json"
    _need(facts.get("api_url") == url, f"api_url is not {url}")
    wheel = _release_wheel(roles, tree)
    entry = _pypi_wheel_entry(_json(roles, "pypi_json"), wheel, tree)
    _need(facts.get("pypi_wheel_sha256") == _sha256(wheel), "pypi_wheel_sha256")
    download = facts.get("download_url")
    _need(download == entry.get("url"), "download_url is not PyPI's URL for the wheel")
    _need(str(download).startswith("https://files.pythonhosted.org/"), "download host")
    return facts


def validate_zenodo_record(receipt: object, tree: Tree, repo: str) -> dict:
    roles, facts = _publication(receipt, "zenodo_record", tree)
    ident = facts.get("record_id")
    _need(type(ident) is int and ident > 0, "record_id")
    _need(facts.get("api_url") == f"https://zenodo.org/api/records/{ident}", "api_url")
    _need(facts.get("repository") == repo, "repository")
    doi, concept = facts.get("doi"), facts.get("concept_doi")
    _need(doi == f"10.5281/zenodo.{ident}", "the version DOI is not this record's")
    _need(isinstance(concept, str) and re.fullmatch(r"10\.5281/zenodo\.\d+", concept), "concept")
    _need(concept != doi, "the version DOI is the concept DOI")
    record = _json(roles, "record_response")
    _need(record.get("id") == ident, "the answer is another record")
    _need(record.get("doi") == doi and record.get("conceptdoi") == concept, "the answer's DOIs")
    _need(record.get("submitted") is True, "the deposit is not published")
    metadata = record.get("metadata")
    _need(isinstance(metadata, dict), "the answer has no metadata")
    _need(metadata.get("version") == tree.version, f"metadata.version is not {tree.version}")
    links = [
        str(x.get("identifier", ""))
        for x in metadata.get("related_identifiers", [])
        if isinstance(x, dict)
    ]
    tag = f"v{tree.version}"
    _need(
        any(f"github.com/{repo}" in x and tag in x for x in links),
        f"no related identifier names {repo} at {tag}",
    )
    return record


def validate_zenodo_files(receipt: object, tree: Tree) -> dict:
    roles, facts = _publication(receipt, "zenodo_files", tree)
    record = _json(roles, "record_response")
    _need(isinstance(facts.get("doi"), str) and record.get("doi") == facts["doi"], "doi")
    files = record.get("files")
    _need(isinstance(files, list) and files, "the record publishes no file")
    keys = [f.get("key") for f in files if isinstance(f, dict)]
    _need(len(keys) == len(files) == len(set(keys)) and all(keys), "file keys")
    local = {r.split(":", 1)[1] for r in roles if r.startswith("file:")}
    _need(local == set(keys), f"local files {sorted(local)} are not the record's {sorted(keys)}")
    for entry in files:
        path = roles[f"file:{entry['key']}"]
        _need(path.name == entry["key"], f"{entry['key']}: the local file has another name")
        checksum = str(entry.get("checksum", ""))
        _need(checksum.startswith("md5:"), f"{entry['key']}: checksum domain")
        md5 = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
        _need(md5 == checksum[4:], f"{entry['key']}: md5 differs from the record")
        if "size" in entry:
            _need(entry["size"] == path.stat().st_size, f"{entry['key']}: size")
    _need(any(f"v{tree.version}" in k for k in keys), "no published file of this release")
    return record


def _validate_runs(receipt: object, ident: str, family: str, tree: Tree, repo: str) -> dict:
    roles, facts = _publication(receipt, ident, tree, code=True)
    url = f"https://api.github.com/repos/{repo}/actions/runs?head_sha={tree.head}&per_page=100"
    _github_facts(facts, repo, url)
    runs = _json(roles, "runs_response").get("workflow_runs")
    _need(isinstance(runs, list), "the answer has no workflow_runs")
    _need(all(isinstance(r, dict) and r.get("head_sha") == tree.head for r in runs), "head_sha")
    names = sorted({str(r.get("name", "")) for r in runs if family in str(r.get("name")).lower()})
    _need(names, f"no {family} workflow ran for HEAD")
    _need(facts.get("workflows") == names, f"workflows is not {names}")
    for name in names:
        latest = max((r for r in runs if r.get("name") == name), key=lambda r: r.get("id", 0))
        _need(latest.get("status") == "completed", f"{name}: not completed")
        _need(
            latest.get("conclusion") == "success", f"{name}: concluded {latest.get('conclusion')}"
        )
    return facts


def validate_ci(receipt: object, tree: Tree, repo: str) -> dict:
    return _validate_runs(receipt, "ci", "ci", tree, repo)


def validate_docs_ci(receipt: object, tree: Tree, repo: str) -> dict:
    return _validate_runs(receipt, "docs_ci", "docs", tree, repo)


def validate_publication_clean_install(receipt: object, tree: Tree) -> dict:
    _need(isinstance(receipt, dict), "receipt is not a JSON object")
    assert isinstance(receipt, dict)
    obligation = "publication:checks:clean_install"
    _need(receipt.get("obligation") == obligation, f"obligation is not {obligation}")
    validate_clean_install(receipt | {"obligation": "delivery:checks:clean_install"}, tree)
    return receipt["facts"]


def _archive_members(path: Path) -> list[tuple[str, bytes]]:
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            return [(i.filename, archive.read(i)) for i in archive.infolist() if not i.is_dir()]
    members = []
    with tarfile.open(path, "r:gz") as archive:
        for info in archive.getmembers():
            stream = archive.extractfile(info) if info.isfile() else None
            members.append((info.name, stream.read() if stream else b""))
    return members


def validate_privacy_scan(receipt: object, tree: Tree) -> dict:
    roles, facts = _publication(receipt, "privacy_scan", tree)
    wheel = _release_wheel(roles, tree)
    sdist = _role(roles, "sdist")
    _need(sdist.name == f"pyflightstream-{tree.version}.tar.gz", f"sdist {sdist.name}")
    _need(facts.get("pypi_wheel_sha256") == _sha256(wheel), "pypi_wheel_sha256")
    _need(facts.get("pypi_sdist_sha256") == _sha256(sdist), "pypi_sdist_sha256")
    lines = _role(roles, "terms").read_text(encoding="utf-8").splitlines()
    terms = [t.strip().casefold() for t in lines if t.strip() and not t.lstrip().startswith("#")]
    _need(terms and all(len(t) >= 3 for t in terms), "the private-term list is empty or short")
    _need(facts.get("terms_count") == len(terms), "terms_count")
    members = _archive_members(wheel) + _archive_members(sdist)
    _need(facts.get("scanned_members") == len(members), "scanned_members")
    matches = sorted(
        {
            f"{name}: {term}"
            for name, data in members
            for term in terms
            if term in name.casefold() or term in data.decode("utf-8", "ignore").casefold()
        }
    )
    _need(facts.get("matches") == matches, "the recorded matches differ from the rescan")
    _need(not matches, f"private terms in the published archives: {matches[:5]}")
    return facts


# --- research-campaign validator ---------------------------------------------------------


def _calibration(block: object, what: str) -> dict:
    _need(isinstance(block, dict), f"{what} calibration missing")
    assert isinstance(block, dict)
    factors, base, effective = (block.get(k) for k in ("factors", "base", "effective"))
    _need(all(isinstance(x, dict) for x in (factors, base, effective)), f"{what}: tables")
    assert isinstance(factors, dict) and isinstance(base, dict) and isinstance(effective, dict)
    _need(factors and set(factors) == set(base) == set(effective), f"{what}: property names")
    for name, factor in factors.items():
        values = (factor, base[name], effective[name])
        _need(all(type(v) in (int, float) and math.isfinite(v) for v in values), f"{what}: {name}")
        _need(factor > 0, f"{what}: {name} factor is not positive")
        product = base[name] * factor
        _need(math.isclose(effective[name], product, rel_tol=1e-9), f"{what}: {name} effective")
    return factors


def _toml_values(node: object, found: dict[str, list]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            found.setdefault(key, []).append(value)
            _toml_values(value, found)


def _validate_fsi(roles: dict[str, Path], facts: dict) -> None:
    fsi = facts.get("fsi")
    _need(isinstance(fsi, dict) and fsi.get("material") == MATERIAL, f"material is not {MATERIAL}")
    assert isinstance(fsi, dict)
    _need(_role(roles, "material_source").stat().st_size > 0, "material source empty")
    _need(_role(roles, "supplied_properties").stat().st_size > 0, "supplied properties empty")
    calibrations = fsi.get("calibrations")
    _need(isinstance(calibrations, dict), "calibrations missing")
    assert isinstance(calibrations, dict)
    from_file = _calibration(calibrations.get("file"), "file")
    try:
        parsed = tomllib.loads(_role(roles, "calibration_file").read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ReceiptRefusedError(f"calibration_file is not TOML ({error})") from error
    found: dict[str, list] = {}
    _toml_values(parsed, found)
    for name, factor in from_file.items():
        _need(factor in found.get(name, []), f"file factor {name} is not in the calibration file")
    from_matrix = _calibration(calibrations.get("matrix"), "matrix")
    columns = calibrations["matrix"].get("columns")
    _need(isinstance(columns, dict) and set(columns) == set(from_matrix), "matrix columns")
    matrix_text = _role(roles, "matrix").read_text(encoding="utf-8", errors="replace")
    for name, column in columns.items():
        _need(isinstance(column, str) and column in matrix_text, f"matrix column for {name}")


def validate_study(receipt: object, study: str, tree: Tree) -> dict:
    _need(study in STUDIES, f"{study} is not a campaign study")
    roles, facts = _envelope(receipt, f"research_campaign:studies:{study}", tree, code=False)
    _need(facts.get("study") == study, "study")
    _need(facts.get("workspace") == "fts-research", "workspace is not fts-research")
    _need(facts.get("matrix") == "matrix-qa.fs", "matrix is not matrix-qa.fs")
    _need(_role(roles, "matrix").name == "matrix-qa.fs", "matrix file")
    _need(facts.get("execution") == "local-licensed", "execution is not local-licensed")
    wheel = _release_wheel(roles, tree)
    _need(facts.get("pypi_wheel_sha256") == _sha256(wheel), "pypi_wheel_sha256")
    entry = _pypi_wheel_entry(_json(roles, "pypi_json"), wheel, tree)
    uploaded = _when(entry.get("upload_time_iso_8601"), "PyPI upload time")
    started = _when(facts.get("campaign_started_at"), "campaign_started_at")
    _need(started > uploaded, "the campaign did not start after the wheel was published")
    capture = _json(roles, "standards_capture")
    argv = capture.get("argv")
    _need(isinstance(argv, list) and all(isinstance(a, str) for a in argv), "standards argv")
    assert isinstance(argv, list)
    _need(any(Path(a).stem == "pyfs-matrix" for a in argv), "standards not from pyfs-matrix")
    _need("plan" in argv and "--setup-standards" in argv, "not `plan --setup-standards`")
    exit_code = capture.get("exit_code")
    _need(type(exit_code) is int and exit_code == 0, "standards generation failed")
    _need(capture.get("wheel_sha256") == _sha256(wheel), "standards from another wheel")
    outputs = capture.get("outputs")
    _need(isinstance(outputs, dict) and outputs, "no generated standard")
    assert isinstance(outputs, dict)
    for name, digest in outputs.items():
        _need(_sha256(_role(roles, f"standard:{name}")) == digest, f"standard {name} changed")
    report = _role(roles, "report").read_text(encoding="utf-8", errors="replace")
    _need(report.strip(), "report empty")
    if study in EXPERIMENT_STUDIES:
        cases = facts.get("cases")
        _need(isinstance(cases, list) and cases, "cases missing")
        assert isinstance(cases, list)
        ids = [c.get("id") for c in cases if isinstance(c, dict)]
        _need(len(ids) == len(cases) == len(set(ids)) and all(ids), "case ids")
        for case in cases:
            _need(case.get("status") == "completed", f"case {case['id']} did not complete")
            _need(_role(roles, f"result:{case['id']}").stat().st_size > 0, "result empty")
            _need(case["id"] in report, f"the report does not interpret case {case['id']}")
    if study in FSI_STUDIES:
        _validate_fsi(roles, facts)
    if study in ("synthesis", "comparison_history"):
        _need(facts.get("report_file") == roles["report"].name, "report_file")
    if study == "synthesis":
        covered = facts.get("covered_studies")
        _need(
            isinstance(covered, list) and sorted(covered) == sorted(EXPERIMENT_STUDIES), "covered"
        )
        missing = [s for s in EXPERIMENT_STUDIES if s not in report]
        _need(not missing, f"the synthesis does not name {missing}")
    if study == "comparison_history":
        versions = facts.get("versions")
        _need(isinstance(versions, list) and tree.version in versions, "versions lack this release")
        assert isinstance(versions, list)
        _need(any(Version(v) < Version(tree.version) for v in versions), "no earlier version")
        _need(all(v in report for v in versions), "the history does not name every version")
    return facts


# --- the marker tests: publication ---------------------------------------------------------

PUBLICATION_CHECKS = (
    "remote_tag",
    "github_release",
    "pypi_download",
    "zenodo_record",
    "zenodo_files",
    "ci",
    "docs_ci",
    "clean_install",
    "privacy_scan",
)


def test_publication_remote_tag_receipt():
    """GitHub answers refs/tags/v0.29.0 with a commit equal to this tree's HEAD.

    GOAL033:publication:checks:remote_tag
    """
    receipt, tree = _receipt("GOAL033_REMOTE_TAG_RECEIPT"), _real_tree()
    facts = validate_remote_tag(receipt, tree, _origin_repository())
    assert facts["resolved_commit"] == tree.head


def test_publication_github_release_receipt():
    """The GitHub release of v0.29.0 is published, neither draft nor prerelease.

    GOAL033:publication:checks:github_release
    """
    receipt, tree = _receipt("GOAL033_GITHUB_RELEASE_RECEIPT"), _real_tree()
    release = validate_github_release(receipt, tree, _origin_repository())
    assert (release["tag_name"], release["draft"], release["prerelease"]) == (
        f"v{tree.version}",
        False,
        False,
    )


def test_publication_pypi_download_receipt():
    """The wheel downloaded from PyPI re-hashes to PyPI's digest and is this version.

    GOAL033:publication:checks:pypi_download
    """
    facts = validate_pypi_download(_receipt("GOAL033_PYPI_DOWNLOAD_RECEIPT"), _real_tree())
    assert re.fullmatch(r"[0-9a-f]{64}", facts["pypi_wheel_sha256"])


def test_publication_zenodo_record_receipt():
    """The Zenodo version record has its own DOI, this version, and names the tag.

    GOAL033:publication:checks:zenodo_record
    """
    receipt, tree = _receipt("GOAL033_ZENODO_RECORD_RECEIPT"), _real_tree()
    record = validate_zenodo_record(receipt, tree, _origin_repository())
    assert record["metadata"]["version"] == tree.version and record["doi"] != record["conceptdoi"]


def test_publication_zenodo_files_receipt():
    """Every file Zenodo publishes was re-read locally and matches its md5.

    GOAL033:publication:checks:zenodo_files
    """
    record = validate_zenodo_files(_receipt("GOAL033_ZENODO_FILES_RECEIPT"), _real_tree())
    assert record["files"]


def test_publication_ci_receipt():
    """Every ci workflow run for HEAD concluded success.

    GOAL033:publication:checks:ci
    """
    receipt, tree = _receipt("GOAL033_CI_RECEIPT"), _real_tree()
    assert validate_ci(receipt, tree, _origin_repository())["workflows"]


def test_publication_docs_ci_receipt():
    """Every docs workflow run for HEAD concluded success.

    GOAL033:publication:checks:docs_ci
    """
    receipt, tree = _receipt("GOAL033_DOCS_CI_RECEIPT"), _real_tree()
    assert validate_docs_ci(receipt, tree, _origin_repository())["workflows"]


def test_publication_clean_install_receipt():
    """The published wheel installs from PyPI into a fresh venv and runs.

    GOAL033:publication:checks:clean_install
    """
    receipt, tree = _receipt("GOAL033_PUBLICATION_CLEAN_INSTALL_RECEIPT"), _real_tree()
    facts = validate_publication_clean_install(receipt, tree)
    assert facts["import_version_output"] == tree.version


def test_publication_privacy_scan_receipt():
    """The published wheel and sdist carry none of the private terms, rescanned here.

    GOAL033:publication:checks:privacy_scan
    """
    facts = validate_privacy_scan(_receipt("GOAL033_PRIVACY_SCAN_RECEIPT"), _real_tree())
    assert facts["matches"] == [] and facts["terms_count"] > 0


# --- the marker tests: research campaign ------------------------------------------------------


def _study(study: str) -> str:
    """Validate the study's receipt from its variable; return the study it proved."""
    receipt = _receipt(f"GOAL033_STUDY_{study.upper()}_RECEIPT")
    return validate_study(receipt, study, _real_tree())["study"]


def test_campaign_wake_controls_receipt():
    """GOAL033:research_campaign:studies:wake_controls"""
    assert _study("wake_controls") == "wake_controls"


def test_campaign_rotor_induced_velocity_blending_receipt():
    """GOAL033:research_campaign:studies:rotor_induced_velocity_blending"""
    assert _study("rotor_induced_velocity_blending") == "rotor_induced_velocity_blending"


def test_campaign_laminar_separation_receipt():
    """GOAL033:research_campaign:studies:laminar_separation"""
    assert _study("laminar_separation") == "laminar_separation"


def test_campaign_airfoil_separation_receipt():
    """GOAL033:research_campaign:studies:airfoil_separation"""
    assert _study("airfoil_separation") == "airfoil_separation"


def test_campaign_valarezo_receipt():
    """GOAL033:research_campaign:studies:valarezo"""
    assert _study("valarezo") == "valarezo"


def test_campaign_adverse_gradient_boundary_layer_receipt():
    """GOAL033:research_campaign:studies:adverse_gradient_boundary_layer"""
    assert _study("adverse_gradient_boundary_layer") == "adverse_gradient_boundary_layer"


def test_campaign_wake_decay_receipt():
    """GOAL033:research_campaign:studies:wake_decay"""
    assert _study("wake_decay") == "wake_decay"


def test_campaign_incompressible_receipt():
    """GOAL033:research_campaign:studies:incompressible"""
    assert _study("incompressible") == "incompressible"


def test_campaign_transonic_receipt():
    """GOAL033:research_campaign:studies:transonic"""
    assert _study("transonic") == "transonic"


def test_campaign_temporal_convergence_receipt():
    """GOAL033:research_campaign:studies:temporal_convergence"""
    assert _study("temporal_convergence") == "temporal_convergence"


def test_campaign_fsi_calculated_titanium_receipt():
    """GOAL033:research_campaign:studies:fsi_calculated_titanium"""
    assert _study("fsi_calculated_titanium") == "fsi_calculated_titanium"


def test_campaign_fsi_supplied_properties_receipt():
    """GOAL033:research_campaign:studies:fsi_supplied_properties"""
    assert _study("fsi_supplied_properties") == "fsi_supplied_properties"


def test_campaign_fsi_file_calibration_receipt():
    """GOAL033:research_campaign:studies:fsi_file_calibration"""
    assert _study("fsi_file_calibration") == "fsi_file_calibration"


def test_campaign_fsi_matrix_calibration_receipt():
    """GOAL033:research_campaign:studies:fsi_matrix_calibration"""
    assert _study("fsi_matrix_calibration") == "fsi_matrix_calibration"


def test_campaign_fsi_usability_receipt():
    """GOAL033:research_campaign:studies:fsi_usability"""
    assert _study("fsi_usability") == "fsi_usability"


def test_campaign_synthesis_receipt():
    """GOAL033:research_campaign:studies:synthesis"""
    assert _study("synthesis") == "synthesis"


def test_campaign_comparison_history_receipt():
    """GOAL033:research_campaign:studies:comparison_history"""
    assert _study("comparison_history") == "comparison_history"


def test_every_obligation_has_exactly_one_marker_function():
    source = Path(__file__).read_text(encoding="utf-8")
    functions = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)]
    markers = [f"publication:checks:{c}" for c in PUBLICATION_CHECKS]
    markers += [f"research_campaign:studies:{s}" for s in STUDIES]
    for marker in markers:
        tag = "GOAL033:" + marker
        holders = [f.name for f in functions if tag in (ast.get_source_segment(source, f) or "")]
        assert len(holders) == 1, (marker, holders)
        body = next(f for f in functions if f.name == holders[0])
        assert any(isinstance(n, ast.Assert) for n in ast.walk(body)), holders[0]


# --- falsifiability: synthetic receipts, accepted and corrupted ------------------------------

VERSION = "0.29.0"
HEAD = "a" * 40
REPO = "owner/pyflightstream"
UPLOADED = "2026-09-28T10:00:00.000000Z"


def _tree() -> Tree:
    return Tree(VERSION, HEAD, lambda rev: False, lambda path: None)


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def _dump(path: Path, data: dict) -> Path:
    return _write(path, json.dumps(data))


def _art(role: str, path: Path) -> dict:
    return {"role": role, "path": str(path), "sha256": _sha256(path)}


def _base(obligation: str, artifacts: list[dict], facts: dict, code: bool) -> dict:
    receipt = {
        "schema": SCHEMA,
        "obligation": obligation,
        "package": "pyflightstream",
        "version": VERSION,
        "recorded_at": "2026-09-28T12:00:00Z",
        "artifacts": artifacts,
        "facts": facts,
    }
    if code:
        receipt["product_revision"] = HEAD
    return receipt


def _wheel(tmp: Path, extra: str = "") -> Path:
    path = tmp / f"pyflightstream-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        meta = f"Metadata-Version: 2.1\nName: pyflightstream\nVersion: {VERSION}\n"
        wheel.writestr(f"pyflightstream-{VERSION}.dist-info/METADATA", meta)
        wheel.writestr("pyflightstream/__init__.py", f"__version__ = '{VERSION}'\n{extra}")
    return path


def _pypi_json(tmp: Path, wheel: Path) -> Path:
    answer = {
        "info": {"name": "pyflightstream", "version": VERSION},
        "urls": [
            {
                "filename": wheel.name,
                "packagetype": "bdist_wheel",
                "yanked": False,
                "url": f"https://files.pythonhosted.org/packages/x/{wheel.name}",
                "digests": {"sha256": _sha256(wheel)},
                "upload_time_iso_8601": UPLOADED,
            }
        ],
    }
    return _dump(tmp / "pypi.json", answer)


def _replace_json(role: str, change: Callable[[dict], None]) -> Callable[[dict], None]:
    """Corrupt a JSON artifact's content and re-hash it, so only the content is wrong."""

    def mutate(receipt: dict) -> None:
        item = next(a for a in receipt["artifacts"] if a["role"] == role)
        path = Path(item["path"])
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")
        item["sha256"] = _sha256(path)

    return mutate


def _replace_text(role: str, text: str) -> Callable[[dict], None]:
    def mutate(receipt: dict) -> None:
        item = next(a for a in receipt["artifacts"] if a["role"] == role)
        path = Path(item["path"])
        path.write_text(text, encoding="utf-8")
        item["sha256"] = _sha256(path)

    return mutate


def _drop_role(role: str) -> Callable[[dict], None]:
    def mutate(receipt: dict) -> None:
        receipt["artifacts"] = [a for a in receipt["artifacts"] if a["role"] != role]

    return mutate


def _set(*keys: str | int, value: object) -> Callable[[dict], None]:
    def mutate(receipt: dict) -> None:
        target = receipt
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return mutate


def _bad_hash(receipt: dict) -> None:
    receipt["artifacts"][0]["sha256"] = "0" * 64


def _build_remote_tag(tmp: Path) -> dict:
    ref = {
        "ref": f"refs/tags/v{VERSION}",
        "object": {"type": "tag", "sha": "c" * 40},
    }
    annotated = {"sha": "c" * 40, "tag": f"v{VERSION}", "object": {"type": "commit", "sha": HEAD}}
    url = f"https://api.github.com/repos/{REPO}/git/ref/tags/v{VERSION}"
    return _base(
        "publication:checks:remote_tag",
        [
            _art("ref_response", _dump(tmp / "ref.json", ref)),
            _art("tag_object_response", _dump(tmp / "tag.json", annotated)),
        ],
        {"repository": REPO, "api_url": url, "resolved_commit": HEAD},
        code=True,
    )


def _build_github_release(tmp: Path) -> dict:
    release = {
        "tag_name": f"v{VERSION}",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-09-28T09:00:00Z",
        "html_url": f"https://github.com/{REPO}/releases/tag/v{VERSION}",
    }
    url = f"https://api.github.com/repos/{REPO}/releases/tags/v{VERSION}"
    return _base(
        "publication:checks:github_release",
        [_art("release_response", _dump(tmp / "release.json", release))],
        {"repository": REPO, "api_url": url},
        code=False,
    )


def _build_pypi_download(tmp: Path) -> dict:
    wheel = _wheel(tmp)
    return _base(
        "publication:checks:pypi_download",
        [_art("pypi_json", _pypi_json(tmp, wheel)), _art("wheel", wheel)],
        {
            "api_url": f"https://pypi.org/pypi/pyflightstream/{VERSION}/json",
            "download_url": f"https://files.pythonhosted.org/packages/x/{wheel.name}",
            "pypi_wheel_sha256": _sha256(wheel),
        },
        code=False,
    )


def _zenodo_answer(files: list[dict]) -> dict:
    return {
        "id": 7001,
        "doi": "10.5281/zenodo.7001",
        "conceptdoi": "10.5281/zenodo.7000",
        "submitted": True,
        "metadata": {
            "version": VERSION,
            "related_identifiers": [
                {"identifier": f"https://github.com/{REPO}/tree/v{VERSION}", "relation": "x"}
            ],
        },
        "files": files,
    }


def _build_zenodo_record(tmp: Path) -> dict:
    return _base(
        "publication:checks:zenodo_record",
        [_art("record_response", _dump(tmp / "record.json", _zenodo_answer([{"key": "a"}])))],
        {
            "record_id": 7001,
            "api_url": "https://zenodo.org/api/records/7001",
            "doi": "10.5281/zenodo.7001",
            "concept_doi": "10.5281/zenodo.7000",
            "repository": REPO,
        },
        code=False,
    )


def _build_zenodo_files(tmp: Path) -> dict:
    archive = _write(tmp / "files" / f"pyflightstream-v{VERSION}.zip", b"PK archive bytes")
    md5 = hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()
    entry = {"key": archive.name, "checksum": f"md5:{md5}", "size": archive.stat().st_size}
    return _base(
        "publication:checks:zenodo_files",
        [
            _art("record_response", _dump(tmp / "record.json", _zenodo_answer([entry]))),
            _art(f"file:{archive.name}", archive),
        ],
        {"doi": "10.5281/zenodo.7001"},
        code=False,
    )


def _build_runs(tmp: Path, ident: str, names: list[str]) -> dict:
    runs = [
        {"id": 10, "name": "ci", "head_sha": HEAD, "status": "completed", "conclusion": "failure"},
        {"id": 11, "name": "ci", "head_sha": HEAD, "status": "completed", "conclusion": "success"},
        {
            "id": 12,
            "name": "docs",
            "head_sha": HEAD,
            "status": "completed",
            "conclusion": "success",
        },
        {"id": 13, "name": "Release", "head_sha": HEAD, "status": "completed", "conclusion": "x"},
    ]
    url = f"https://api.github.com/repos/{REPO}/actions/runs?head_sha={HEAD}&per_page=100"
    return _base(
        f"publication:checks:{ident}",
        [_art("runs_response", _dump(tmp / "runs.json", {"workflow_runs": runs}))],
        {"repository": REPO, "api_url": url, "workflows": names},
        code=True,
    )


def _build_ci(tmp: Path) -> dict:
    return _build_runs(tmp, "ci", ["ci"])


def _build_docs_ci(tmp: Path) -> dict:
    return _build_runs(tmp, "docs_ci", ["docs"])


def _build_publication_clean_install(tmp: Path) -> dict:
    return _build_clean_install(tmp) | {"obligation": "publication:checks:clean_install"}


def _build_privacy_scan(tmp: Path) -> dict:
    wheel = _wheel(tmp)
    sdist = tmp / f"pyflightstream-{VERSION}.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        data = b"print('public')\n"
        info = tarfile.TarInfo(f"pyflightstream-{VERSION}/src/mod.py")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    terms = _write(tmp / "terms.txt", "# private\nsecretcampaign\nownerhost\n")
    return _base(
        "publication:checks:privacy_scan",
        [_art("wheel", wheel), _art("sdist", sdist), _art("terms", terms)],
        {
            "pypi_wheel_sha256": _sha256(wheel),
            "pypi_sdist_sha256": _sha256(sdist),
            "terms_count": 2,
            "scanned_members": 3,
            "matches": [],
        },
        code=False,
    )


def _build_study(tmp: Path, study: str) -> dict:
    wheel = _wheel(tmp)
    standard = _write(tmp / "standards" / "setup.toml", "[standards]\n")
    capture = {
        "argv": ["C:/venv/Scripts/pyfs-matrix.exe", "plan", "matrix-qa.fs", "--setup-standards"],
        "exit_code": 0,
        "wheel_sha256": _sha256(wheel),
        "outputs": {"setup.toml": _sha256(standard)},
    }
    matrix = _write(tmp / "matrix-qa.fs", "POL | RUN | FSI_EI_SCALE\nP1 | 1 | 1.1\n")
    cases = [
        {"id": f"{study}-c1", "status": "completed"},
        {"id": f"{study}-c2", "status": "completed"},
    ]
    report = f"Interpretation of {study}: {cases[0]['id']} and {cases[1]['id']}.\n"
    facts: dict = {
        "study": study,
        "workspace": "fts-research",
        "matrix": "matrix-qa.fs",
        "execution": "local-licensed",
        "pypi_wheel_sha256": _sha256(wheel),
        "campaign_started_at": "2026-09-29T08:00:00+00:00",
    }
    artifacts = [
        _art("matrix", matrix),
        _art("wheel", wheel),
        _art("pypi_json", _pypi_json(tmp, wheel)),
        _art("standards_capture", _dump(tmp / "standards.json", capture)),
        _art("standard:setup.toml", standard),
    ]
    if study in EXPERIMENT_STUDIES:
        facts["cases"] = cases
        for case in cases:
            artifacts.append(_art(f"result:{case['id']}", _write(tmp / f"{case['id']}.csv", "1\n")))
    if study in FSI_STUDIES:
        calibration = _write(tmp / "F.toml", "[calibration]\nbending_stiffness = 1.2\n")
        facts["fsi"] = {
            "material": MATERIAL,
            "calibrations": {
                "file": {
                    "factors": {"bending_stiffness": 1.2},
                    "base": {"bending_stiffness": 100.0},
                    "effective": {"bending_stiffness": 120.0},
                },
                "matrix": {
                    "factors": {"bending_stiffness": 1.1},
                    "base": {"bending_stiffness": 100.0},
                    "effective": {"bending_stiffness": 110.00000000000001},
                    "columns": {"bending_stiffness": "FSI_EI_SCALE"},
                },
            },
        }
        artifacts += [
            _art("material_source", _write(tmp / "ti64.csv", "E,113.8e9\n")),
            _art("supplied_properties", _write(tmp / "blade.toml", "[blade]\nEI = 1\n")),
            _art("calibration_file", calibration),
        ]
    if study == "synthesis":
        facts["covered_studies"] = list(EXPERIMENT_STUDIES)
        report = "Synthesis: " + ", ".join(EXPERIMENT_STUDIES) + "\n"
    if study == "comparison_history":
        facts["versions"] = ["0.28.0", VERSION]
        report = f"History across 0.28.0 and {VERSION}.\n"
    path = _write(tmp / f"{study}-report.md", report)
    artifacts.append(_art("report", path))
    if study in ("synthesis", "comparison_history"):
        facts["report_file"] = path.name
    return _base(f"research_campaign:studies:{study}", artifacts, facts, code=False)


COMMON = {
    "version": _set("version", value="0.28.0"),
    "obligation": _set("obligation", value="publication:checks:docs"),
    "artifact_hash": _bad_hash,
}
CODE = {"revision": _set("product_revision", value="d" * 40)}


def _with_repo(validate: Callable) -> Callable:
    return lambda receipt, tree: validate(receipt, tree, REPO)


PUBLICATION: dict[str, tuple[Callable, Callable, dict[str, Callable[[dict], None]]]] = {
    "remote_tag": (
        _build_remote_tag,
        _with_repo(validate_remote_tag),
        CODE
        | {
            "other_commit": _replace_json(
                "tag_object_response", lambda d: d["object"].update(sha="e" * 40)
            ),
            "other_ref": _replace_json("ref_response", lambda d: d.update(ref="refs/tags/v0.28.0")),
            "not_commit": _replace_json(
                "tag_object_response", lambda d: d["object"].update(type="tree")
            ),
            "tag_object_missing": _drop_role("tag_object_response"),
            "repository": _set("facts", "repository", value="someone/else"),
        },
    ),
    "github_release": (
        _build_github_release,
        _with_repo(validate_github_release),
        {
            "draft": _replace_json("release_response", lambda d: d.update(draft=True)),
            "prerelease": _replace_json("release_response", lambda d: d.update(prerelease=True)),
            "tag": _replace_json("release_response", lambda d: d.update(tag_name="v0.28.0")),
            "unpublished": _replace_json("release_response", lambda d: d.update(published_at=None)),
        },
    ),
    "pypi_download": (
        _build_pypi_download,
        validate_pypi_download,
        {
            "pypi_digest": _replace_json(
                "pypi_json", lambda d: d["urls"][0]["digests"].update(sha256="e" * 64)
            ),
            "yanked": _replace_json("pypi_json", lambda d: d["urls"][0].update(yanked=True)),
            "pypi_version": _replace_json(
                "pypi_json", lambda d: d["info"].update(version="0.28.0")
            ),
            "fact_digest": _set("facts", "pypi_wheel_sha256", value="e" * 64),
            "download_url": _set("facts", "download_url", value="https://example.org/x.whl"),
        },
    ),
    "zenodo_record": (
        _build_zenodo_record,
        _with_repo(validate_zenodo_record),
        {
            "concept_is_version": _set("facts", "concept_doi", value="10.5281/zenodo.7001"),
            "metadata_version": _replace_json(
                "record_response", lambda d: d["metadata"].update(version="v0.28.0")
            ),
            "not_submitted": _replace_json("record_response", lambda d: d.update(submitted=False)),
            "no_release_link": _replace_json(
                "record_response", lambda d: d["metadata"].update(related_identifiers=[])
            ),
            "other_record": _replace_json(
                "record_response", lambda d: d.update(doi="10.5281/zenodo.1")
            ),
        },
    ),
    "zenodo_files": (
        _build_zenodo_files,
        validate_zenodo_files,
        {
            "md5": _replace_json(
                "record_response", lambda d: d["files"][0].update(checksum="md5:" + "0" * 32)
            ),
            "unread_file": _replace_json(
                "record_response",
                lambda d: d["files"].append({"key": "extra.zip", "checksum": "md5:" + "0" * 32}),
            ),
            "local_missing": _drop_role(f"file:pyflightstream-v{VERSION}.zip"),
            "size": _replace_json("record_response", lambda d: d["files"][0].update(size=1)),
        },
    ),
    "ci": (
        _build_ci,
        _with_repo(validate_ci),
        CODE
        | {
            "latest_failed": _replace_json(
                "runs_response", lambda d: d["workflow_runs"][1].update(conclusion="failure")
            ),
            "other_head": _replace_json(
                "runs_response", lambda d: d["workflow_runs"][0].update(head_sha="e" * 40)
            ),
            "omitted_workflow": _replace_json(
                "runs_response",
                lambda d: d["workflow_runs"].append(
                    {"id": 20, "name": "ci-extra", "head_sha": HEAD, "conclusion": "failure"}
                ),
            ),
            "api_url": _set("facts", "api_url", value="https://api.github.com/"),
        },
    ),
    "docs_ci": (
        _build_docs_ci,
        _with_repo(validate_docs_ci),
        CODE
        | {
            "failed": _replace_json(
                "runs_response", lambda d: d["workflow_runs"][2].update(conclusion="failure")
            ),
            "running": _replace_json(
                "runs_response", lambda d: d["workflow_runs"][2].update(status="in_progress")
            ),
            "no_docs": _replace_json("runs_response", lambda d: d["workflow_runs"].pop(2)),
        },
    ),
    "clean_install": (
        _build_publication_clean_install,
        validate_publication_clean_install,
        {
            "delivery_obligation": _set("obligation", value="delivery:checks:clean_install"),
            "pypi_digest": _set("facts", "pypi_wheel_sha256", value="e" * 64),
            "import_version": _set("facts", "import_version_output", value="0.28.0"),
        },
    ),
    "privacy_scan": (
        _build_privacy_scan,
        validate_privacy_scan,
        {
            "term_present": _replace_text("terms", "secretcampaign\n__version__\n"),
            "term_in_name": _replace_text("terms", "secretcampaign\nmod.py\n"),
            "matches_nonempty": _set("facts", "matches", value=["x: y"]),
            "terms_count": _set("facts", "terms_count", value=3),
            "members_count": _set("facts", "scanned_members", value=2),
            "empty_terms": _replace_text("terms", "# nothing\n"),
        },
    ),
}


def _study_corruptions(study: str) -> dict[str, Callable[[dict], None]]:
    own = {
        "workspace": _set("facts", "workspace", value="fts-workspace"),
        "execution": _set("facts", "execution", value="cluster"),
        "wheel_not_pypi": _replace_json(
            "pypi_json", lambda d: d["urls"][0]["digests"].update(sha256="e" * 64)
        ),
        "before_publication": _set("facts", "campaign_started_at", value="2026-09-27T00:00:00Z"),
        "standards_other_wheel": _replace_json(
            "standards_capture", lambda d: d.update(wheel_sha256="e" * 64)
        ),
        "standards_not_cli": _replace_json(
            "standards_capture", lambda d: d.update(argv=["python", "make_standards.py"])
        ),
        "standards_failed": _replace_json("standards_capture", lambda d: d.update(exit_code=1)),
        "standard_unhashed": _drop_role("standard:setup.toml"),
        "study": _set("facts", "study", value="valarezo" if study != "valarezo" else "transonic"),
        "report_empty": _replace_text("report", "   \n"),
    }
    if study in EXPERIMENT_STUDIES:
        own |= {
            "case_failed": _set("facts", "cases", 1, "status", value="failed"),
            "case_duplicate": _set("facts", "cases", 1, "id", value=f"{study}-c1"),
            "result_missing": _drop_role(f"result:{study}-c2"),
            "report_silent": _replace_text("report", f"Interpretation of {study}-c1 only.\n"),
        }
    if study in FSI_STUDIES:
        fsi = ("facts", "fsi", "calibrations")
        own |= {
            "material": _set("facts", "fsi", "material", value="Al-7075"),
            "effective": _set(*fsi, "file", "effective", "bending_stiffness", value=100.0),
            "factor_not_in_file": lambda r: r["facts"]["fsi"]["calibrations"]["file"].update(
                factors={"bending_stiffness": 1.3}, effective={"bending_stiffness": 130.0}
            ),
            "matrix_column": _set(*fsi, "matrix", "columns", "bending_stiffness", value="NOPE"),
            "no_material_source": _drop_role("material_source"),
            "no_supplied": _drop_role("supplied_properties"),
        }
    if study == "synthesis":
        own |= {
            "covered": lambda r: r["facts"]["covered_studies"].pop(),
            "report_silent": _replace_text("report", "Synthesis of nothing.\n"),
            "report_file": _set("facts", "report_file", value="other.md"),
        }
    if study == "comparison_history":
        own |= {
            "no_earlier": _set("facts", "versions", value=[VERSION]),
            "no_release": _set("facts", "versions", value=["0.28.0"]),
            "report_silent": _replace_text("report", f"Only {VERSION}.\n"),
        }
    return own


def _study_case(study: str) -> tuple[Callable, Callable, dict[str, Callable[[dict], None]]]:
    return (
        lambda tmp: _build_study(tmp, study),
        lambda receipt, tree: validate_study(receipt, study, tree),
        _study_corruptions(study),
    )


CASES = {f"publication:{k}": v for k, v in PUBLICATION.items()} | {
    f"study:{s}": _study_case(s) for s in STUDIES
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_publication_campaign_validator_accepts_the_valid_receipt(name, tmp_path):
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
def test_publication_campaign_validator_refuses_a_corrupted_copy(name, field, tmp_path):
    build, validate, own = CASES[name]
    receipt = build(tmp_path)
    validate(copy.deepcopy(receipt), _tree())  # the control: unchanged, it is accepted
    (COMMON | own)[field](receipt)
    with pytest.raises(ReceiptRefusedError):
        validate(receipt, _tree())


def test_a_marker_test_skips_naming_its_variable_when_the_receipt_is_absent(monkeypatch):
    monkeypatch.delenv("GOAL033_STUDY_VALAREZO_RECEIPT", raising=False)
    with pytest.raises(pytest.skip.Exception, match="GOAL033_STUDY_VALAREZO_RECEIPT"):
        _study("valarezo")


def test_the_origin_pattern_names_owner_and_repository():
    match = GITHUB.fullmatch("https://github.com/nevesgeovana/pyflightstream.git")
    assert match and match.group(1) == "nevesgeovana/pyflightstream"
    assert GITHUB.fullmatch("https://gitlab.com/x/y.git") is None
