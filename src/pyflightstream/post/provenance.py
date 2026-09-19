"""Write each recorded run's provenance as PROV-JSON.

Documents relate staged inputs, scripts and collected outputs to the run and
its agents. The shared product archive helpers preserve existing documents
and tables before a rebuild. Existing import spellings remain available
through :mod:`pyflightstream.post.products`.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._digest import file_sha256
from pyflightstream.cases import classify_outputs
from pyflightstream.post._tables import NOT_APPLICABLE, ProductExistsError
from pyflightstream.post.series import surface_export_metadata
from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP

if TYPE_CHECKING:
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

__all__ = [
    "PROV_PREFIX",
    "SCRIPT_SUFFIX",
    "attributes",
    "prov_document",
    "refuse_an_existing_product",
    "run_provenance",
    "PRODUCT_ARCHIVE_DIR",
    "PRODUCT_ARCHIVE_STAMP",
    "PROVENANCE_DIR",
    "PROVENANCE_SUFFIX",
    "operator_agent",
    "point_name_of",
    "product_archive_dir",
    "provenance_file_name",
]

#: The folder an existing product is moved into before a new one is
#: written, under the matrix's own post folder: ``archive/<day and hour>/``.
#: One folder per rebuild, so a rebuild is one thing a reader can look at.
#:
#: BOTH NAMES MOVED DOWN TO THE NAMING MODULE AT 0.18.0 and are re-exported
#: here under the spellings this layer has always used. A continuation
#: archives a DATAPOINT under the same stamp, and the workspace layer cannot
#: import from post: dependencies flow downward. A second copy of the format
#: in the lower layer would be a second home for one fact, which is the
#: failure this estate keeps paying for, so the fact moved rather than being
#: duplicated.
PRODUCT_ARCHIVE_DIR = ARCHIVE_DIR

#: How the stamp is spelled. Sortable, no separator a file system objects
#: to, and to the SECOND: two rebuilds in one minute are two rebuilds.
PRODUCT_ARCHIVE_STAMP = ARCHIVE_STAMP


def product_archive_dir(path: Path, *, now: datetime | None = None) -> Path:
    """Where the product at ``path`` is archived to before it is rewritten.

    ``<the product's own folder>/archive/<day and hour>/``: the archive
    sits BESIDE the product it replaces, so a reader who has opened
    ``polars/`` to compare two polar tables finds the old one in that same
    folder rather than in a tree somewhere above it.

    THE STAMP IS THE REBUILD'S, passed in by the post stage, so every
    product a rebuild archives lands under one folder name even though the
    folders themselves are per-product.

    THIS DOCSTRING SAID ``post/<matrix>/archive/`` UNTIL 2026-09-13, which
    is one archive for the whole rebuild "keeping whatever folders the
    product sat in below the matrix". That is a different layout from the
    one the body returns and from the one the tier-1 case asserts, and the
    sentence read as a design nobody had built (the QA lens).
    """
    stamp = (now or datetime.now()).strftime(PRODUCT_ARCHIVE_STAMP)
    for parent in path.parents:
        if parent.name == PRODUCT_ARCHIVE_DIR:
            # Already inside an archive: never archive an archive.
            return path.parent
    return path.parent / PRODUCT_ARCHIVE_DIR / stamp


def refuse_an_existing_product(
    path: Path, *, archive: bool = True, stamp: datetime | None = None
) -> Path:
    """Return ``path``, ARCHIVING an existing product rather than losing it.

    A regenerated SUPER file can report different numbers: without
    an archive the previous table is gone and nothing says it ever said
    something else.

    THREE BEHAVIOURS AND ONE FLAG, and the default is the first:

    * the product exists and ``archive`` holds: it is MOVED into
      ``<its own folder>/archive/<day and hour>/`` and the new one is
      written in its place. Nothing is lost and nothing is refused.
    * the product exists and ``archive`` is false: it is overwritten and
      no copy is kept. That is the explicit escape, and the command line
      spells it ``--force-overwrite`` and asks for a confirmation, so it
      cannot be reached by habit.
    * the product does not exist: nothing happens.

    IT TOOK AN ``overwrite`` FLAG TOO, AND THAT WAS THE DEFECT. The guard
    read ``not archive and overwrite``, so a caller asking for no archive
    with no overwrite, which is the documented do-not-archive request,
    fell through and archived anyway: one cell of a two-boolean truth
    table that no test named and no shipped path reached. Making them
    independent left ``overwrite`` deciding nothing at all, and a
    parameter that decides nothing is one the next caller will set and be
    surprised by, so it is gone rather than left dead (the QA lens, rounds
    one and two).

    THE OLD REFUSAL IS GONE, which is the part worth saying plainly. It
    existed to stop a rebuild destroying a product silently, and archiving
    answers that better: a refusal makes the user delete the file, which
    destroys it just as thoroughly and puts the work on them.
    """
    if not path.exists():
        return path
    # THE TWO FLAGS ARE INDEPENDENT, and they were not: the guard read
    # `not archive and overwrite`, so a caller asking for no archive with
    # no overwrite, which is the documented do-not-archive request, fell
    # through and archived anyway. One cell of a two-boolean truth table
    # that no test named and no shipped path reached, which is exactly how
    # it survived (the QA lens, 2026-09-13).
    if not archive:
        return path
    target = product_archive_dir(path, now=stamp)
    target.mkdir(parents=True, exist_ok=True)
    moved = target / path.name
    if moved.exists():
        # Two rebuilds inside one second, which the stamp cannot separate.
        # Numbering is better than either losing one or refusing the write.
        index = 2
        while (target / f"{path.stem}.{index}{path.suffix}").exists():
            index += 1
        moved = target / f"{path.stem}.{index}{path.suffix}"
    path.replace(moved)
    return path


# --- PFS-2012.08.01: a run's provenance in an interchange format, PROV-JSON --------

#: The folder under the matrix's products where the documents land.
PROVENANCE_DIR = "provenance"

#: The suffix of one document, appended to the point's own name, or to
#: the run id with its separators replaced where the point's name is not
#: known or is not unique (FR-86).
PROVENANCE_SUFFIX = ".prov.json"

#: The namespaces a document declares. ``prov`` and ``xsd`` are the W3C's;
#: ``pyfs`` is this package's, for the attributes and identifiers it coins,
#: a URN rather than a web address so the document promises no page.
PROV_PREFIX = {
    "prov": "http://www.w3.org/ns/prov#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "pyfs": "urn:pyflightstream:",
}


#: The extension every generated point script is written under
#: (``run._run_point``: ``write_script(sim_id, f"{stem}.txt", ...)``), and
#: therefore the one this module strips to recover a point's own name
#: from the script the record already names. Stripped by this exact
#: literal rather than by `Path.stem`, because a point stem carries dots
#: of its own: `Path("a+02.0").stem` is `a+02`, and a name shortened that
#: way would collide two points of one sweep.
SCRIPT_SUFFIX = ".txt"


def point_name_of(record: RunRecord) -> str | None:
    """Return the point name a record's script carries, or None (FR-86).

    THE SCRIPT IS THE SOURCE and not the naming template. The template a
    workspace is configured with today is not the one a record from last
    month was written under; the record names the file the run actually
    wrote, and that file's stem IS the convention every other generated
    file of the point carries. A record whose script is not named the way
    this package writes one answers None, and the caller keeps the run
    id, which is what every document was named before 0.16.0.
    """
    declared = record.script_path
    if not declared:
        return None
    name = str(declared).replace("\\", "/").rsplit("/", 1)[-1]
    if not name.endswith(SCRIPT_SUFFIX):
        return None
    return name[: -len(SCRIPT_SUFFIX)] or None


def provenance_file_name(run_id: str, *, point_name: str | None = None) -> str:
    """Return the name of one run's provenance document (FR-86).

    ``<point name>.prov.json`` when the point's own name is known, which
    is the convention the script and every export of the same point carry
    and what lets a reader sort ``scripts/`` and ``provenance/`` side by
    side. ``<run id with '/' replaced by '_'>.prov.json`` otherwise, which
    is what every document was named before 0.16.0.

    NOTHING RENAMES A RUN. The run id is unchanged: it keys the products
    manifest and it is a field inside the document, under
    ``pyfs:run_id``, and it is the identifier of the activity. What moves
    is a file name, which this package never parses for meaning.
    """
    stem = run_id if point_name is None else point_name
    return stem.replace("/", "_") + PROVENANCE_SUFFIX


def attributes(**pairs: object) -> dict[str, object]:
    """Return the attributes of one PROV node, a None value left out rather than written."""
    return {name: value for name, value in pairs.items() if value is not None}


def operator_agent(name: str | None) -> dict[str, object]:
    """Return the `prov:Person` agent for the operator a record names.

    A `prov:Person` and not a string on the activity, because the document is
    W3C PROV and already carries two `prov:SoftwareAgent`s: the operator is the
    third agent the run was associated with, which another tool reads without
    being told anything about this package.

    ``None`` is a run that ALREADY EXISTS. `submitted_by` is a RUN-time fact and
    nobody recorded it for the simulations that already finished; it cannot be
    recovered and none is invented. The field is PRESENT and reads `NA`, so a
    reader tells a run that predates this release from a document that forgot.
    """
    stated = (name or "").strip()
    return {
        "prov:type": "prov:Person",
        "pyfs:submitted_by": stated or NOT_APPLICABLE,
    }


def prov_document(record: RunRecord, sim_dir: Path) -> dict[str, object]:
    """Build one run's PROV-JSON document from its record and the files it left.

    W3C PROV, in the PROV-JSON serialization (the design decision of 2026-09-08,
    design 68): the run record carried every fact a provenance document
    needs and lacked a shape another tool reads without reading this
    package's docs. ENTITIES are each staged input (``inputs_sha256``), the
    script (``script_sha256``) and each collected output, every one with
    its sha256 under ``pyfs:sha256``; an output's hash is computed from
    the file when it is still there and taken from the record otherwise,
    and ``pyfs:sha256_from`` says which.

    WHERE THE FILE'S BYTES ARE NOT THE RECORDED ONES the output entity
    keeps the RECORDED digest and the generation claim, because that
    claim is true, and what the file holds now becomes a second entity,
    ``pyfs:file/<name>``, of type ``pyfs:ChangedOutput``, listed under
    ``wasDerivedFrom`` and generated by no activity (PFS-2038.01). The
    document therefore never asserts that a run produced bytes it did
    not. It does not refuse: an edited or re-exported output is a
    workspace's business, and saying so correctly is the fix.

    The ACTIVITY is the solver run,
    with ``prov:startTime`` and ``prov:endTime`` where the record carries
    them, the wall time, the status and the executor's argv. The AGENTS
    are the package at its version and commit and the solver build at its
    executable identity, both ``prov:SoftwareAgent``. The activity
    ``used`` the inputs and the script, every output ``wasGeneratedBy``
    it, it ``wasAssociatedWith`` both agents, the outputs are attributed
    to the solver and the script to the package. Standard library only:
    the document is a mapping :mod:`json` writes.
    """
    activity_id = f"pyfs:run/{record.run_id}"
    package_id = f"pyfs:package/pyflightstream/{record.package_version}"
    solver_id = f"pyfs:solver/FlightStream/{record.fs_version_requested}"
    # ONE AGENT ID PER OPERATOR, so two runs by the same person are the same
    # agent in the document rather than two agents that happen to agree.
    operator = operator_agent(getattr(record, "submitted_by", None))
    operator_id = f"pyfs:operator/{operator['pyfs:submitted_by']}"
    entities: dict[str, dict[str, object]] = {}
    used: dict[str, dict[str, str]] = {}
    generated: dict[str, dict[str, str]] = {}
    attributed: dict[str, dict[str, str]] = {}
    #: PFS-2038.01. One entry per output whose bytes on disk are not the
    #: bytes the run recorded: what the file holds now, derived from what
    #: the run produced and generated by nothing.
    derived: dict[str, dict[str, str]] = {}
    for name, input_sha256 in sorted(record.inputs_sha256.items()):
        entity_id = f"pyfs:input/{name}"
        entities[entity_id] = attributes(
            **{"prov:type": "pyfs:StagedInput", "pyfs:name": name, "pyfs:sha256": input_sha256}
        )
        used[f"_:used{len(used) + 1}"] = {"prov:activity": activity_id, "prov:entity": entity_id}
    script_id = f"pyfs:script/{record.script_path or 'script'}"
    entities[script_id] = attributes(
        **{
            "prov:type": "pyfs:Script",
            "pyfs:name": record.script_path,
            "pyfs:sha256": record.script_sha256,
            "pyfs:raw": record.raw_flag,
            "pyfs:recipe": record.recipe,
            "pyfs:recipe_sha256": record.recipe_sha256,
        }
    )
    used[f"_:used{len(used) + 1}"] = {"prov:activity": activity_id, "prov:entity": script_id}
    attributed["_:attributed1"] = {"prov:entity": script_id, "prov:agent": package_id}
    for name in record.outputs:
        entity_id = f"pyfs:output/{name}"
        path = sim_dir / name
        recorded = record.outputs_sha256.get(name)
        current = file_sha256(path) if path.is_file() else None
        # PFS-2038.01, GEO-039-F01. THE BYTES ON DISK MAY NOT BE THE BYTES
        # THE RUN WROTE, and this document used to say they were: it
        # preferred the current digest whenever the file existed and then
        # bound that entity to the run through `wasGeneratedBy`. A file
        # edited, repaired or re-exported after the run was therefore
        # attributed to a run that never produced it. That is a false
        # statement rather than a wrong number.
        changed = current is not None and recorded is not None and current != recorded
        if changed:
            # The ORIGINAL entity keeps the recorded digest and keeps the
            # generation claim, which is true: the run did produce those
            # bytes. What is on disk becomes a SEPARATE, DERIVED entity
            # that says so, generated by nothing here and attributed to
            # nobody.
            output_sha256: str | None = recorded
            sha256_from: str | None = "record"
        elif current is not None:
            output_sha256 = current
            sha256_from = "file"
        else:
            output_sha256 = recorded
            sha256_from = "record" if recorded is not None else None
        entities[entity_id] = attributes(
            **{
                "prov:type": "pyfs:Output",
                "pyfs:name": name,
                "pyfs:sha256": output_sha256,
                "pyfs:sha256_from": sha256_from,
                **(
                    {f"pyfs:{key}": value for key, value in surface_export_metadata(record).items()}
                    if set(classify_outputs([name])) & {"tecplot", "vtk", "csv"}
                    else {}
                ),
            }
        )
        generated[f"_:generated{len(generated) + 1}"] = {
            "prov:entity": entity_id,
            "prov:activity": activity_id,
        }
        attributed[f"_:attributed{len(attributed) + 1}"] = {
            "prov:entity": entity_id,
            "prov:agent": solver_id,
        }
        if changed:
            derived_id = f"pyfs:file/{name}"
            entities[derived_id] = attributes(
                **{
                    "prov:type": "pyfs:ChangedOutput",
                    "pyfs:name": name,
                    "pyfs:sha256": current,
                    "pyfs:sha256_from": "file",
                    "pyfs:recorded_sha256": recorded,
                    "pyfs:note": (
                        "the bytes at this path differ from the ones the run recorded; "
                        "this entity is what the file holds now and no activity here "
                        "claims to have produced it"
                    ),
                }
            )
            derived[f"_:derived{len(derived) + 1}"] = {
                "prov:generatedEntity": derived_id,
                "prov:usedEntity": entity_id,
            }
            # NO REFUSAL, and that is the narrowing. The review recommends
            # refusing or marking mismatches before deriving trusted
            # products; a refusal would stop the post stage on any
            # workspace whose outputs were ever touched by hand, including
            # a legitimate re-export or a file repaired after a partial
            # write. Correcting the assertion is the whole defect.
    executor = record.executor
    activity = attributes(
        **{
            "prov:type": "pyfs:SolverRun",
            "prov:startTime": record.started_at,
            "prov:endTime": record.finished_at,
            "pyfs:run_id": record.run_id,
            "pyfs:sim_id": record.sim_id,
            "pyfs:status": record.status.value,
            "pyfs:wall_time_s": record.wall_time_s,
            "pyfs:iterations": record.iterations,
            "pyfs:residual": record.residual,
            "pyfs:executor": executor["class_name"] if executor else None,
            "pyfs:argv": list(executor["argv"]) if executor else None,
            "pyfs:cwd": record.cwd,
            "pyfs:error": record.error,
            # PFS-2033.02: the setup's raw commands the script carried, or nothing.
            "pyfs:raw_commands": [entry.model_dump(mode="json") for entry in record.raw_commands]
            or None,
            # The design decision of 2026-09-09: the setup's aliases the polar tables resolved by.
            "pyfs:aliases": dict(record.aliases) or None,
        }
    )
    agents = {
        package_id: attributes(
            **{
                "prov:type": "prov:SoftwareAgent",
                "pyfs:name": "pyflightstream",
                "pyfs:version": record.package_version,
                "pyfs:commit": record.package_commit,
                "pyfs:dirty": record.package_dirty,
            }
        ),
        # THE OPERATOR, v0.23.0 item 12. Always present: a record that names
        # nobody reads `NA`, so existing records remain usable and the absence
        # is visible rather than silent.
        operator_id: operator,
        solver_id: attributes(
            **{
                "prov:type": "prov:SoftwareAgent",
                "pyfs:name": "FlightStream",
                "pyfs:version_requested": record.fs_version_requested,
                "pyfs:version_reported": record.fs_version_reported,
                "pyfs:build": record.fs_build,
                "pyfs:executable": record.fs_exe,
                "pyfs:executable_sha256": record.fs_exe_sha256,
            }
        ),
    }
    document: dict[str, object] = {
        "prefix": dict(PROV_PREFIX),
        "entity": entities,
        "activity": {activity_id: activity},
        "agent": agents,
        "used": used,
        "wasAssociatedWith": {
            f"_:associated{number}": {"prov:activity": activity_id, "prov:agent": agent_id}
            for number, agent_id in enumerate(agents, start=1)
        },
        "wasAttributedTo": attributed,
    }
    # As applicable: a run that collected nothing generated nothing, and the
    # key is absent rather than empty.
    if generated:
        document["wasGeneratedBy"] = generated
    # PFS-2038.01. Absent on every document whose outputs still hold the
    # bytes they were recorded with, which is every document this package
    # has written until one of them does not.
    if derived:
        document["wasDerivedFrom"] = derived
    return document


def run_provenance(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    out: Path,
    *,
    overwrite: bool,
    archive: bool = True,
    archive_stamp: datetime | None = None,
) -> dict[str, str]:
    """Write one PROV-JSON document per record under ``out/provenance``.

    Every recorded run, whatever its status: a failed run's provenance is
    evidence about the failure. Returns the manifest's ``provenance`` map,
    run id to the document's path relative to ``out``. An existing document
    is refused as an existing table is, unless ``overwrite`` is set.
    """
    # A POINT NAME NEED NOT BE UNIQUE AND A RUN ID IS (FR-86). The
    # default naming template is `{point}`, which carries no sim id, so
    # two simulations of one matrix swept over the same angles render the
    # same stem; so do two records of one point. Naming the document
    # after the point alone would then have had the second run's
    # provenance OVERWRITE the first's and the manifest name one file for
    # two runs, which is the class of defect this whole stage exists to
    # make impossible. Measured over the whole set first and then
    # applied, so the fallback does not depend on manifest order: a stem
    # claimed more than once sends EVERY record that claims it back to
    # the run id, which is unique by construction.
    stems = {record.run_id: point_name_of(record) for record in records}
    claims = Counter(stem for stem in stems.values() if stem is not None)
    index: dict[str, str] = {}
    for record in records:
        stem = stems[record.run_id]
        if stem is not None and claims[stem] > 1:
            stem = None
        relative = f"{PROVENANCE_DIR}/{provenance_file_name(record.run_id, point_name=stem)}"
        target = out / relative
        if target.exists() and archive:
            # THE SAME RULE AS A PRODUCT. A provenance document about to
            # be rewritten is evidence about the run that produced the
            # file it describes, so it is archived rather than replaced.
            refuse_an_existing_product(target, archive=True, stamp=archive_stamp)
        elif target.exists() and not overwrite:
            raise ProductExistsError(
                f"the provenance document {target} exists; pass overwrite=True to rewrite "
                "it from the manifest, and the old one is archived rather than lost. "
                "`pyfs-matrix post` passes it already, so this reaches a library caller "
                "alone: the command-line flag this named until 2026-09-13, --overwrite, "
                "is gone and argparse now refuses it (the interface lens)"
            )
        document = prov_document(record, workspace.sim_dir(record.sim_id))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
        index[record.run_id] = relative
    return index
