"""The post stage's shared vocabulary: layout, verdicts, names, plans and the log.

A private module below every product family of :mod:`pyflightstream.post`
(AD-13). The families
(:mod:`~pyflightstream.post.polar`, :mod:`~pyflightstream.post.rotor_table`,
:mod:`~pyflightstream.post.unsteady_polar`, :mod:`~pyflightstream.post.point_tables`)
and the private stage modules each read what is here, and nothing here reads
a family back, so each of these is defined once:

* the LAYOUT of the products folder: the manifest, the two logs and the
  ``polars/``, ``sections/`` and ``probes/`` folders;
* the VERDICT of a frozen solve over an averaging window
  (:func:`freeze_of_log`, :func:`_judge_average`), with the two context
  variables a campaign post sets for the run of one stage. Every stage looks
  :func:`freeze_of_log` up HERE, through this module, so the one verdict is
  replaced once, here, by a test;
* the NAME a file may carry for an alias, and the refusal of two aliases a
  file name cannot tell apart;
* the shared COLUMN TUPLES of the moment point and the plots clock, and the
  PLAN of a reduction a record states;
* the RECORDS of the post log (``post.log`` and ``post.log.json``), one
  source for both, and the PARTIAL post: how a post of selected simulations
  keeps the manifest entries of the others.

:mod:`pyflightstream.post.products` re-exports every public name here and
the names its own stage code reads.
"""

from __future__ import annotations

import json
import math
import re
import warnings
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from pyflightstream import _textio
from pyflightstream._cli import post_warning_policy
from pyflightstream._digest import text_sha256
from pyflightstream._errors import (
    ProductExistsError,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases.corrections import CalibrationError
from pyflightstream.cases.windows import AZIMUTHAL
from pyflightstream.cases.workflows import ROTORS_KEY
from pyflightstream.post._tables import _PLOTS_STEP_COLUMN as PLOTS_STEP_COLUMN
from pyflightstream.post._tables import ROTOR_TABLE_SUFFIX, ProductError, read_csv_table
from pyflightstream.post.unsteady import TimestepSeries, blade_passage_average, phase_locked_rows
from pyflightstream.results import FrozenSolve, UnjudgeableSolve, frozen_time_steps, parse_log_times
from pyflightstream.workspace.naming import SUPER_FILE_PREFIX

if TYPE_CHECKING:
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


def failure_reason(error: Exception) -> str:
    """Name one product's failure: a refusal as it reads, anything else with its type (FR-2313).

    An unexpected failure costs its own product, never the post, so it is named
    in a way that reads as the defect it is and not as a refusal.
    """
    if isinstance(error, PyflightstreamError):
        return str(error)
    return f"{type(error).__name__}: {error} (an unexpected failure of this product)"


def _contained(skipped: dict[str, str], key: str, make, empty):
    """Run one product of a point; a refusal costs only that product, named in ``skipped``.

    The independent products of a point are not isolated from each other otherwise: a refusal
    from one orphans what the others have written. An existing product still refuses. An
    unexpected failure costs the product too, named with its type (FR-2313).
    """
    try:
        return make()
    except (ProductExistsError, Warning):
        raise
    except Exception as error:  # noqa: BLE001 -- every failure is named, never fatal here
        skipped[key] = said = failure_reason(error)
        warn(f"{key} not written: {said}", PyflightstreamWarning, stacklevel=2)
        return empty


def _surface_export_skip(
    entry: Mapping[str, object], frozen: FrozenSolve | None, *, point: str, product: str
) -> str | None:
    """Apply the existing average refusal rule to a native surface window."""
    if "skipped" in entry:
        return str(entry["skipped"])
    window = entry.get("window")
    bounds = window.get("iterations") if isinstance(window, Mapping) else None
    if isinstance(bounds, list):
        return _judge_average(
            frozen, [int(bounds[0]), int(bounds[1])], point=point, product=product
        )
    return None


def _the_plan_of_a_reduction(
    plan: Mapping[str, object] | None, rotor: str | None
) -> Mapping[str, object] | None:
    """Return the plan block a reduction is about: the rotor's own, or the row's.

    A row turning several rotors keeps each one's blades, clock and speed under
    `rotors[<alias>]`, and the top level then states none of them.
    """
    if rotor is None or not isinstance(plan, Mapping):
        return plan
    blocks = plan.get(ROTORS_KEY)
    own = blocks.get(rotor) if isinstance(blocks, Mapping) else None
    return own if isinstance(own, Mapping) else plan


def _window_the_reduction_reads(
    name: str,
    entry: Mapping[str, object],
    window: tuple[int, ...],
    series: TimestepSeries,
    columns: Sequence[str],
    blades: int,
    facts: Mapping[str, object],
) -> set[int]:
    """Ask the reducer for its plotted steps, using the writer's resolved families."""
    read: set[int] = set()
    if name == _PHASE_LOCKED and entry.get("shape") == AZIMUTHAL:
        stated = facts.get("families", ())
        families = list(stated) if isinstance(stated, list | tuple) else []
        rpm = facts.get("rpm")
        phase_locked_rows(
            series,
            [column for column in columns if column not in _PLOTS_CLOCK_COLUMNS],
            last_step=window[-1],
            revolutions=float(entry.get("revolutions") or 0.0),  # type: ignore[arg-type]
            steps_per_revolution=float(entry.get("steps_per_revolution") or 0.0),  # type: ignore[arg-type]
            blade1_azimuth_deg=float(facts.get("blade1_azimuth_deg") or 0.0),  # type: ignore[arg-type]
            sense=-1.0 if isinstance(rpm, int | float) and rpm < 0 else 1.0,
            blades=blades,
            blade_families=families,
            read_steps=read,
        )
    else:
        blade_passage_average(series, window=(window[0], window[-1]), read_steps=read)
    return read


# THE CONTEXT VARIABLES OF A POST IN PROGRESS, all three, in one place. They are set by
# ``write_campaign_products`` for the length of one post and reset when it ends, so a
# writer reached directly, outside a post, sees the defaults below.
#
# * ``_POST_REFUSES``: whether a product whose steps the solver did not freeze is REFUSED
#   (``check_frozen=True``) or written with a warning. The default is False, the policy the
#   campaign documents: warn and write every computable product.
# * ``_POST_VERDICTS``: the frozen-solve verdict of each (loads file, unsteady) pair read so
#   far in this post, so a file is judged once. None outside a post.
# * ``_POST_NOTES``: the INFO records of the post (FR-419). None outside a post.
_POST_REFUSES: ContextVar[bool] = ContextVar("post_refuses", default=False)


_POST_VERDICTS: ContextVar[dict[tuple[Path, bool], FrozenSolve | None] | None] = ContextVar(
    "post_verdicts", default=None
)


#: The INFO records of the post in progress (FR-419): what a post says in ``post.log``
#: that is neither a warning nor a skip. None outside a post, where nothing is kept.
_POST_NOTES: ContextVar[list[dict[str, str | None]] | None] = ContextVar("post_notes", default=None)


def _judge_average(
    frozen: FrozenSolve | None,
    steps: Sequence[int] | set[int],
    *,
    point: str,
    product: str,
) -> str | None:
    """Warn for an affected product, and refuse it only when the stage asks."""
    reason = _frozen_window_reason(frozen, steps)
    if reason is not None:
        warn(
            f"point={point} product={product}: {reason}. "
            "Recollect the native log or run the point again to settle this average.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return reason if _POST_REFUSES.get() else None


def _frozen_window_reason(
    frozen: FrozenSolve | None, window: Sequence[int] | set[int]
) -> str | None:
    """Explain why an average reaches the frozen, or the unreadable, part of a solve."""
    # cases.windows and the products' STEP use inclusive 1-based time steps,
    # just like the log's (k/N): there is no offset and no inner-iteration mapping.
    if frozen is None or not window:
        return None
    samples = window if isinstance(window, set) else None
    bounds = (min(window), max(window)) if isinstance(window, set) else (window[0], window[1])
    if isinstance(frozen, UnjudgeableSolve):
        # AN UNREAD BLOCK SAYS NOTHING ABOUT THE STEPS AROUND IT, which is the
        # whole difference from a freeze: a freeze contaminates every step after
        # its first, while a block the solver stopped under leaves its
        # neighbours exactly as measurable as they were. So this refuses a
        # window only when an unread step falls INSIDE it.
        inside = [
            step
            for step in frozen.steps
            if (step in samples if samples is not None else bounds[0] <= step <= bounds[1])
        ]
        reaches_freeze = frozen.frozen_from is not None and bounds[1] >= frozen.frozen_from
        if not inside and frozen.steps and not reaches_freeze:
            return None
        return f"{frozen.reason}; averaging samples span steps {bounds[0]} to {bounds[1]}"
    if bounds[1] >= frozen.first_step:
        return f"{frozen.reason}; averaging samples span steps {bounds[0]} to {bounds[1]}"
    return None


# --- PFS-2015.04: the reductions of a plots table, beside it -----------------------


def _names_location(folder: str, path: str | Path) -> str:
    """Locate a names refusal relative to the products directory."""
    return f"{folder}/{Path(path).name}#names"


# --- PFS-2029.15.03: the products of a campaign, from its manifest ---------------

#: The manifest of the products: which file came from which runs and pproc.
PRODUCTS_MANIFEST = "products.json"


# The post's log beside the manifest, and its machine-readable twin (R02).
# Private so the public surface does not grow: the manifest names both, under
# `log` and `log_json`, and a reader takes the names from there.
_POST_LOG = "post.log"


_POST_LOG_JSON = "post.log.json"


#: The matrix's per-polar CSV and .dat folder (FR-88). Campaign-level
#: products.json and campaign_sweep.csv stay at the campaign level because
#: they describe more than one polar.
POLARS_DIR = "polars"


#: The folder of the per-point sections tables, under the products folder. One
#: constant like its siblings, so the writer of the recorded tables and the
#: stage cannot spell the folder two ways.
SECTIONS_DIR = "sections"


#: The matrix folder for point flow-field samples (FR-87), independent
#: of run type: unsteady plots, their reductions and probe-point tables
#: all belong here.
PROBES_DIR = "probes"


#: The moment point, stated wherever a table carries a moment.
_MOMENT_POINT_COLUMNS: tuple[str, ...] = ("XMOM", "YMOM", "ZMOM")


#: The columns of a plots table that state WHEN a sample was taken rather than
#: WHAT was measured. They are the table's axis, not its data, and a product
#: that averages them publishes the mean of a step number beside a coefficient.
#:
#: BOTH SPELLINGS, because a table may carry either or both: `Time-step` is what
#: this package writes and reads as the clock, and `Time (sec)` is what the
#: solver's own export prints.
_PLOTS_CLOCK_COLUMNS = frozenset({PLOTS_STEP_COLUMN, "Time (sec)", "Time"})


#: The characters an alias may carry into a file name. Everything else is
#: replaced, because a rotor's alias is a word the user chose and a file
#: name is a thing the operating system parses.
_SAFE_IN_A_FILE_NAME = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _a_name_a_file_may_carry(alias: str) -> str:
    """Return ``alias`` reduced to characters a file name may hold (FR-68).

    A ROTOR'S ALIAS IS UNCONSTRAINED by the model: `RotorBlock.alias` is a
    string with no pattern, so a slash, a colon, a star or a trailing dot
    can reach a path, and a slash writes outside the folder the manifest
    keys the file under. This package
    already sanitises an identifier before it becomes a file name, in
    `provenance_file_name` below, and the precedent is followed rather than
    argued with.

    The rotor's OWN spelling is still recorded, in the manifest entry's
    ``rotor`` field, so nothing is lost by the substitution: the file name
    is for the file system and the field is for the reader.
    """
    cleaned = "".join(
        character if character in _SAFE_IN_A_FILE_NAME else "_" for character in alias
    )
    return cleaned.strip("._ ") or "rotor"


def _refuse_aliases_a_file_name_cannot_tell_apart(
    plans: Mapping[str, Mapping[str, object] | None], sim_id: str
) -> None:
    """Refuse two rotor aliases that sanitize to one file name (PFS-2038.03).

    THE COMPLETE TARGET SET, RESOLVED BEFORE ANY WRITE. `A/B` and `A:B`
    are both valid aliases and both become `A_B`, and the product path
    writes with overwrite: the reviewer measured two writes reported and
    one file left, carrying the second rotor's identity. Silent
    replacement of a derived result is the worst failure class here.

    Keep readable names and refuse aliases that collide after sanitisation.
    The check prevents one rotor's product from overwriting another's.
    """
    by_safe: dict[str, list[str]] = {}
    for plan in plans.values():
        rotors = plan.get(ROTORS_KEY) if isinstance(plan, Mapping) else None
        if not isinstance(rotors, Mapping):
            continue
        for alias in rotors:
            spelling = str(alias)
            # COMPARED WITHOUT CASE: `Rotor` and `rotor` are one file on a case-insensitive disk.
            held = by_safe.setdefault(_a_name_a_file_may_carry(spelling).casefold(), [])
            if spelling not in held:
                held.append(spelling)
    collisions = {safe: names for safe, names in by_safe.items() if len(names) > 1}
    if not collisions:
        return
    detail = "; ".join(
        f"{' and '.join(repr(name) for name in names)} both become the file name "
        f"{_a_name_a_file_may_carry(names[0])!r} (names are compared without case)"
        for safe, names in sorted(collisions.items())
    )
    raise ProductError(
        f"simulation {sim_id!r} names rotors a file name cannot tell apart: {detail}. Each "
        "rotor's passage reductions land in a file named for its alias, so one rotor's "
        "result would be written over another's and the file left would carry the wrong "
        "rotor's identity. Nothing has been written. Rename these rotors so they differ in "
        "letters, digits, hyphens, underscores or dots, which are the characters a file "
        "name keeps; the alias you choose is recorded verbatim in the manifest either way."
    )


def freeze_of_log(log_path: Path, *, steady: bool = False) -> FrozenSolve | None:
    r"""Read a native log tolerantly, caching each path and fallback solver mode.

    The log's printed solver mode takes precedence. If unknown, ``steady``
    supplies the caller's fallback from the loads export; without either fact,
    unsteady evidence is required. Missing files remain unjudgeable in either mode.

    Examples
    --------
    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as folder:
    ...     log = Path(folder) / "point_log.txt"
    ...     _ = log.write_text("FlightStream log header only\n")
    ...     unread = isinstance(freeze_of_log(log), UnjudgeableSolve)
    ...     steady = freeze_of_log(log, steady=True)
    >>> unread, steady
    (True, None)
    """
    verdicts = _POST_VERDICTS.get()
    if verdicts is None:
        return _read_freeze_of_log(log_path, steady=steady)
    key = (log_path, steady)
    if key not in verdicts:
        verdicts[key] = _read_freeze_of_log(log_path, steady=steady)
    return verdicts[key]


def _read_freeze_of_log(log_path: Path, *, steady: bool = False) -> FrozenSolve | None:
    """Return this point's freeze verdict, or None, and never raise for the log.

    THE POST STAGE MUST SURVIVE A LOG IT CANNOT READ. The detector refuses a
    residual table that ends mid-write, which is what a stopped or killed run
    leaves behind. Keep that refusal local so one cut log cannot end the
    campaign post or withhold later simulations' products.

    An unreadable log returns `UnjudgeableSolve`. The stage warns by default
    and refuses affected averages only with check_frozen=True.
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return UnjudgeableSolve(
            first_step=1, count=0, steps=(), detail=f"the log cannot be read: {error}"
        )
    text = text.replace("\x00", "")  # Match the residual detector's native-log normalization.
    mode = parse_log_times(text).solver_mode
    # For a log with no printed mode, use the loads export's mode supplied by
    # the caller. With neither fact, require unsteady evidence conservatively.
    is_steady = mode == "steady" if mode is not None else steady
    if not is_steady and not re.search(r"Solving unsteady time-step iteration \(\d+/\d+\)", text):
        return UnjudgeableSolve(
            first_step=1,
            count=0,
            steps=(),
            detail=f"{log_path} holds no unsteady residual evidence",
        )
    # THE BLOCKS THE SOLVER DID FINISH ARE STILL EVIDENCE, and on a real log they
    # are nearly all of it: a log the walltime guard stopped can end in a header
    # that cannot be read (no committed report measures such a log). A
    # freeze found in the readable blocks wins, because it is evidence; otherwise
    # the unreadable steps are named and only the windows containing them lose
    # their averages.
    unjudged: list[int] = []
    verdict = frozen_time_steps(text, unjudged=unjudged)
    if verdict is not None and not unjudged:
        return verdict
    if unjudged:
        # BOTH KINDS OF EVIDENCE OR NEITHER. Returning the confirmed freeze alone
        # dropped the unread steps, and a window before the freeze then published
        # an average over blocks nobody read; returning the unread steps alone
        # would drop the freeze the read blocks prove.
        steps = tuple(sorted(set(unjudged)))
        return UnjudgeableSolve(
            first_step=min(steps if verdict is None else (*steps, verdict.first_step)),
            count=len(steps),
            steps=steps,
            frozen_from=None if verdict is None else verdict.first_step,
            detail="a residual block ends without its closing separator line",
        )
    return None


_PER_BLADE = "per_blade"


_PHASE_LOCKED = "phase_locked"


#: The reduction the per-revolution product is, as `REDUCTION` states it.
_PER_REVOLUTION = "per_revolution"


#: One record of the post log: the keys `point`, `product`, `message` and
#: `remedy`, the last None when the message states no remedy apart from itself.
_LogRecord = dict[str, str | None]


#: A warning that names its own point and product, as most of the package's do.
#: The POINT may hold spaces (a campaign named `wind tunnel` gives run ids
#: `wind tunnel/sim_7001/AL-020`), so it runs to the first ` product=`; a
#: product name never holds one.
_NAMED_WARNING = re.compile(r"^point=(.+?) product=(\S+): (.*)$", re.S)


def _log_record(
    point: str, product: str, message: str, remedy: str | None, *, severity: str = "warning"
) -> _LogRecord:
    """Return one post-log record, the single source of a WARNING line and its JSON (R02)."""
    from pyflightstream.post.diagnostics import warning_category

    return {
        "point": point,
        "product": product,
        "message": message,
        "remedy": remedy,
        "category": warning_category(product, message),
        "severity": severity,
    }


@contextmanager
def post_notes() -> Iterator[list[_LogRecord]]:
    """Keep the INFO lines :func:`post_note` records in this context, and only here.

    Yields
    ------
    list of dict
        The records so far, filled as they are noted; the caller writes them to the log.
    """
    notes: list[_LogRecord] = []
    token = _POST_NOTES.set(notes)
    try:
        yield notes
    finally:
        _POST_NOTES.reset(token)


def post_note(point: str, product: str, message: str) -> None:
    """Record one INFO line of ``post.log``: a fact of this post that is no warning and no skip.

    Parameters
    ----------
    point, product : str
        The point and the product the line is about.
    message : str
        The line, on one line.
    """
    notes = _POST_NOTES.get()
    if notes is not None:
        notes.append(
            _log_record(point, product, " ".join(message.splitlines()), None, severity="info")
        )


def _warning_record(text: str) -> _LogRecord:
    """Return the record of one collected warning, on one line.

    A warning that begins ``point=X product=Y:`` is recorded under that point
    and product; any other is the stage's own, under ``campaign`` and
    ``stage``. The remedy is None: the package's warnings state what would
    settle them inside their prose, in shapes too varied for a parser to lift
    honestly, so the message is kept whole.
    """
    flat = " ".join(text.splitlines())
    named = _NAMED_WARNING.match(flat)
    if named is None:
        return _log_record("campaign", "stage", flat, None)
    point, product, message = named.groups()
    return _log_record(point, product, message, None)


def _log_line(record: _LogRecord) -> str:
    """Render one record as its ``post.log`` line."""
    remedy = f" Remedy: {record['remedy']}" if record["remedy"] else ""
    return (
        f"{str(record['severity']).upper()} point={record['point']} product={record['product']}: "
        f"{record['message']}{remedy}\n"
    )


def _run_log_records(
    workspace: CampaignWorkspace, matrix_stem: str | None, selected: frozenset[str] | None
) -> list[_LogRecord]:
    """Return the log records the matrix's recorded runs carry: warnings and wake notes."""
    records: list[_LogRecord] = []
    try:
        status_records = workspace.read_manifest()
    except (OSError, ValueError):
        status_records = []
    for run_record in status_records:
        if run_record.matrix_stem != matrix_stem:
            continue
        records.extend(
            _log_record(run_record.run_id, "run-status", message, None)
            for message in run_record.warnings
        )
        if selected is None or run_record.sim_id in selected:
            from pyflightstream.results.log import lifting_log_warnings

            for output in run_record.outputs:
                if str(output).endswith("_log.txt") or str(output).endswith(".log"):
                    log = workspace.sim_dir(run_record.sim_id) / output
                    try:
                        messages = lifting_log_warnings(
                            log.read_text(encoding="utf-8", errors="replace")
                        )
                    except OSError:
                        continue
                    records.extend(
                        _log_record(run_record.run_id, "lifting-wake", message, None)
                        for message in messages
                    )
    return records


def _manifest_skip_records(manifest_path: Path) -> list[_LogRecord]:
    """Return one log record per skip the written ``products.json`` names."""
    if not manifest_path.is_file():
        return []
    document = json.loads(manifest_text(manifest_path.parent))
    return [
        _log_record(
            name,
            name,
            " ".join(str(reason).splitlines()),
            "restore the required data or correct the stated inputs and post again.",
        )
        for name, reason in document.get("skipped", {}).items()
    ]


# --- REL-R2-017: two posts of one matrix in two processes ------------------------
#
# Two `pyfs-matrix run <matrix> --sims ...` in parallel each post per polar, and
# each rewrote products.json from the copy it read when its post began, so the
# later write lost the other's entries. `products.json` itself is the one
# campaign lock: a post takes it to read the manifest, to write it (re-reading it
# and merging), to append its log block, and the run to rewrite the sweep table.
# The lock is held for those moments only, never for a whole post.


def campaign_lock(out: Path) -> AbstractContextManager[IO[bytes] | None]:
    """Hold the products folder's ``products.json`` locked; None after the wait (warn, skip)."""
    return _textio.exclusive(out / PRODUCTS_MANIFEST, wait=_textio.LOCK_WAIT)


def _parsed(text: str) -> dict[str, Any] | None:
    try:
        document = json.loads(text)
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


def manifest_text(out: Path) -> str:
    """Read ``products.json`` under the campaign lock, ``{}`` for an empty file.

    A manifest cut off while it was rewritten in place is read from the staged
    copy the write leaves beside it until the rewrite completes.
    """
    target = out / PRODUCTS_MANIFEST
    with campaign_lock(out) as handle:
        if handle is None:
            text = target.read_text(encoding="utf-8")
        else:
            handle.seek(0)
            text = handle.read().decode("utf-8")
    staged = target.with_name(f"{target.name}.tmp")
    if text.strip() and _parsed(text) is None and staged.is_file():
        if _parsed(backup := staged.read_text(encoding="utf-8")) is not None:
            return backup
    return text if text.strip() else "{}"


@dataclass
class ManifestMerge:
    """What a post's ``products.json`` write merges with the file it finds on disk.

    ``base`` is the manifest as this post last read or wrote it, ``sims`` every
    simulation it handled and ``ids`` their run, point and extraction ids. An
    entry of those simulations is this post's; an entry of another that the file
    on disk changed since ``base`` is the other post's and is kept as found;
    ``others`` holds those changes, per section, for every later write.
    """

    base: dict[str, Any]
    sims: frozenset[str]
    ids: frozenset[str]
    others: dict[str, dict[str, Any]] = field(default_factory=dict)


def note_debug_artifacts(
    manifest: dict[str, object],
    workspace: CampaignWorkspace,
    points: Sequence[RunRecord],
    sims: frozenset[str] | None,
) -> None:
    """Name each debug ``.fsm`` of the posted points under ``debug_artifacts``, when any."""
    debug_artifacts = [
        {
            "kind": "debug_fsm",
            "run_id": point.run_id,
            "path": (workspace.sim_dir(point.sim_id) / name).relative_to(workspace.root).as_posix(),
        }
        for point in points
        if sims is None or point.sim_id in sims
        for name in point.outputs
        if name.endswith("_debug.fsm")
    ]
    if debug_artifacts:
        manifest["debug_artifacts"] = debug_artifacts


def manifest_merge(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    sims: frozenset[str] | None,
    base: Mapping[str, Any],
) -> ManifestMerge:
    """Return the merge of a post of ``sims`` (None: every simulation of ``records``)."""
    handled = frozenset(record.sim_id for record in records) if sims is None else sims
    own = [record for record in records if record.sim_id in handled]
    ids = {record.run_id for record in own} | {
        point.run_id for record in own for point in record.as_points()
    }
    ids |= {
        extraction.extraction_id
        for extraction in workspace.read_additional()
        if extraction.sim_id in handled
    }
    # A copy, as JSON: the post goes on mutating the entries it read.
    return ManifestMerge(json.loads(json.dumps(base)), handled, frozenset(ids))


_ABSENT = object()


#: The sections of ``products.json`` keyed by entry, each entry one simulation's or none.
_MERGED_SECTIONS = ("products", "provenance", "skipped", "debug_artifacts")


def _keyed(doc: Mapping[str, Any], name: str) -> dict[str, Any]:
    if name == "debug_artifacts":
        return {str(item.get("path")): item for item in doc.get(name) or ()}
    return dict(doc.get(name) or {})


def _is_mine(merge: ManifestMerge, name: str, key: str, every: Mapping[str, Any]) -> bool:
    """Whether ``key`` of section ``name`` is an entry of a simulation this post handled."""
    entry = every.get(name, {}).get(key)
    entry = entry if isinstance(entry, Mapping) else {}
    if name == "products":
        return entry.get("sim_id") in merge.sims
    if name == "debug_artifacts":
        return entry.get("run_id") in merge.ids
    if name == "provenance":
        return key in merge.ids
    return _a_key_of_the_simulations(key, merge.sims, set(merge.ids), every.get("products", {}))


def merged_manifest(
    ours: Mapping[str, Any], theirs: Mapping[str, Any] | None, merge: ManifestMerge | None
) -> dict[str, Any]:
    """Return the manifest to write: ``ours``, with what other posts changed on disk.

    A change is an entry of another simulation that the file on disk holds
    otherwise than ``merge.base``, the file as this post last read or wrote it.
    It is kept in ``merge.others`` and laid over every later write of the post,
    so a post that writes the manifest twice keeps it the second time too. A
    post alone finds no change and writes ``ours`` unchanged.
    """
    if merge is None:
        return dict(ours)
    docs = [merge.base, ours] if theirs is None else [merge.base, ours, theirs]
    every = {
        name: {k: v for d in docs for k, v in _keyed(d, name).items()} for name in _MERGED_SECTIONS
    }
    document = dict(ours)
    for name in _MERGED_SECTIONS:
        found = merge.others.setdefault(name, {})
        if theirs is not None:
            seen, now = _keyed(merge.base, name), _keyed(theirs, name)
            for key in dict.fromkeys([*seen, *now]):
                if now.get(key, _ABSENT) != seen.get(key, _ABSENT):
                    if not _is_mine(merge, name, key, every):
                        found[key] = now.get(key, _ABSENT)
        if not found:
            continue
        section = _keyed(ours, name)
        for key, value in found.items():
            if value is _ABSENT:
                section.pop(key, None)
            else:
                section[key] = value
        document[name] = list(section.values()) if name == "debug_artifacts" else section
    return document


def write_manifest(out: Path, manifest: Mapping[str, Any], merge: ManifestMerge | None) -> None:
    """Write ``products.json`` under the campaign lock, merged with the file found there.

    Staged whole as ``products.json.tmp`` first (a write that fails there leaves
    the manifest untouched), then rewritten in place through the locked handle,
    since Windows refuses a replace onto a file a process holds open; the staged
    copy is removed once the rewrite completed. A lock still held by another post
    after ``_textio.LOCK_WAIT`` seconds is warned and the write skipped: every
    product stays on disk and the next post of the matrix names it again.
    """
    target = out / PRODUCTS_MANIFEST
    staged = target.with_name(f"{target.name}.tmp")
    with campaign_lock(out) as handle:
        if handle is None:
            warn(
                f"{target} stayed locked by another post of this matrix for "
                f"{_textio.LOCK_WAIT:.0f} s, so this post did not rewrite it; every product "
                "stays on disk. Post the matrix again once the other post has finished.",
                PyflightstreamWarning,
                stacklevel=2,
            )
            return
        document = merged_manifest(manifest, _parsed(manifest_text(out)) or None, merge)
        text = json.dumps(document, indent=1) + "\n"
        try:
            _textio.write_text(staged, text)
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
        _textio.replace_content(handle, text)
        staged.unlink(missing_ok=True)
    if merge is not None:
        merge.base = json.loads(text)  # the file as written, not the post's live dicts


def append_log_block(
    stream: IO[str], out: Path, header: Mapping[str, Any], records: Sequence[_LogRecord]
) -> None:
    """Append one post's block to ``post.log``, its header and its records, in one write.

    Under the campaign lock, so two posts of the matrix keep two whole blocks.
    """
    sims = f"sims={','.join(header['sims'])}\n" if "sims" in header else ""
    block = (
        f"pyflightstream {header['version']} post\n"
        f"workspace={header['workspace']}\nmatrix={header['matrix']}\n"
        f"time={header['time']}\n"
        f"check_frozen={header['check_frozen']} (refuse instead of warn)\n{sims}"
    )
    with campaign_lock(out):
        stream.write(block + "".join(_log_line(record) for record in records))
        stream.flush()


def _replay_held_warnings(held: Sequence[warnings.WarningMessage]) -> None:
    """Give the warnings held for the log to the caller's filters, unless a CLI reports them."""
    if post_warning_policy() is None:
        for warning in held:
            warnings.warn_explicit(
                warning.message, warning.category, warning.filename, warning.lineno
            )


def _hand_back_warnings(
    caught: Sequence[warnings.WarningMessage], records: list[_LogRecord], log_json: Path
) -> None:
    """Replay the post's warnings to the caller, or report their totals under a CLI policy."""
    if post_warning_policy() is None:
        _replay_held_warnings(caught)
    else:
        from pyflightstream.post.diagnostics import report_post_warnings

        report_post_warnings(records, log_json)


@dataclass
class _PartialPost:
    """What a post limited to some simulations keeps of the previous manifest (FR-307).

    ``products``, ``skipped`` and ``provenance`` are the previous entries of
    every other simulation, carried unchanged, their super files included.
    ``not_rebuilt`` names each product left as the last whole post wrote it,
    with the reason; it is the manifest's ``partial.not_rebuilt`` and the post
    log's warning. ``rebuild_sections`` says whether the sections measurement,
    which reads every recorded point's script, can be rebuilt as a whole post
    rebuilds it.

    ``super_columns`` (PFS-2185.18) is the column set the other simulations'
    super files carry, read from the last superfile measurement, and empty when
    no other simulation has a super file. A super file's columns are the union
    over every simulation of the matrix, so the named simulations' super files
    are written under that set, and a post limited to one polar leaves that
    polar's super file beside the others'. None when the set cannot be read
    while other super files stand: every super file, the named ones included,
    is then left as the last whole post wrote it and named in ``not_rebuilt``.
    ``super_report_files`` holds each file of that measurement by name, with
    its columns and its row count, for the measurement this post rewrites.
    """

    sims: frozenset[str]
    products: dict[str, dict[str, object]]
    skipped: dict[str, str]
    provenance: dict[str, str]
    not_rebuilt: dict[str, str]
    rebuild_sections: bool
    whole: str
    super_columns: tuple[str, ...] | None = None
    super_report_files: dict[str, tuple[tuple[str, ...], int]] = field(default_factory=dict)


def _is_a_super_file(name: str) -> bool:
    """Whether a products.json name is a super file, the cross-simulation product (FR-89)."""
    return name.startswith(f"{POLARS_DIR}/") and Path(name).name.startswith(SUPER_FILE_PREFIX)


def _a_key_of_the_simulations(
    key: str,
    sims: frozenset[str],
    ids: set[str],
    previous_products: Mapping[str, Mapping[str, object]],
) -> bool:
    """Whether a ``skipped`` key of a previous manifest belongs to one of ``sims``.

    A skip is keyed by the simulation id, by ``runs/``, ``series/`` or
    ``tecplot/`` and a run id, by ``additional/<pid>/runs/`` and an extraction
    id, or by the path the product would have had, with or without a
    ``#marker``: a path a previous entry of the simulation holds, a path under
    ``sims/sim_<id>/``, or a file name of the simulation (``P<id>-``,
    ``POLAR-<id>_``, ``SUPER-<id>-``, ``<id>#rotor_tables``). ``ids`` are the
    run and extraction ids of ``sims``.
    """
    if key in sims:
        return True
    if key.partition("/")[2] in ids or key.partition("/runs/")[2] in ids:
        return True
    base = key.split("#", 1)[0]
    entry = previous_products.get(base)
    if isinstance(entry, Mapping) and entry.get("sim_id") in sims:
        return True
    parts = base.split("/")
    if any(part == f"sim_{sim}" for part in parts for sim in sims):
        return True
    return any(
        re.match(rf"^(?:[A-Za-z]+-?)?{re.escape(sim)}(?:[-_.]|$)", parts[-1]) for sim in sims
    )


def _partial_post(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    sims: frozenset[str],
    previous: Mapping[str, Any],
    *,
    matrix_stem: str | None,
) -> _PartialPost:
    """Return what a post limited to ``sims`` keeps of the ``previous`` manifest (FR-307)."""
    previous_products: Mapping[str, Mapping[str, object]] = previous.get("products") or {}
    ids = set(manifest_merge(workspace, records, sims, previous).ids)
    label = ", ".join(sorted(sims))
    whole = f"pyfs-matrix post {matrix_stem}" if matrix_stem else "pyfs-matrix post"
    others_super = any(
        _is_a_super_file(name) and entry.get("sim_id") not in sims
        for name, entry in previous_products.items()
    )
    super_columns, super_report_files = (
        _previous_superfiles(workspace, previous) if others_super else ((), {})
    )
    products = {
        name: dict(entry)
        for name, entry in previous_products.items()
        if entry.get("sim_id") not in sims or (_is_a_super_file(name) and super_columns is None)
    }
    not_rebuilt = {
        name: (
            "a super file's columns are the union over every simulation of the matrix, so the "
            f"post limited to simulation(s) {label} does not rebuild it; this is the file the "
            f"last whole post wrote, and {whole} rebuilds it"
        )
        for name in products
        if _is_a_super_file(name) and super_columns is None
    }
    if previous.get("superfile_report") and super_columns is None:
        not_rebuilt["superfile_report"] = (
            "the measurement of the super files, which this post did not rebuild; it is the "
            f"one the last whole post wrote, and {whole} rebuilds it"
        )
    others = sorted({record.sim_id for record in records} - sims)
    unread = [sim for sim in others if not workspace.sim_dir(sim).is_dir()]
    if unread:
        not_rebuilt["sections_report"] = (
            "the sections measurement reads the script of every recorded point of the matrix, "
            f"and simulation(s) {', '.join(unread)} have no folder under sims/ to read "
            f"(compacted or deleted), which only a whole post restores; {whole} rebuilds it"
        )
    return _PartialPost(
        sims=sims,
        products=products,
        skipped={
            key: reason
            for key, reason in (previous.get("skipped") or {}).items()
            if not _a_key_of_the_simulations(key, sims, ids, previous_products)
            or key.split("#", 1)[0] in not_rebuilt
        },
        provenance={
            run_id: relative
            for run_id, relative in (previous.get("provenance") or {}).items()
            if run_id not in ids
        },
        not_rebuilt=not_rebuilt,
        rebuild_sections=not unread,
        whole=whole,
        super_columns=super_columns,
        super_report_files=super_report_files,
    )


def _previous_superfiles(
    workspace: CampaignWorkspace, previous: Mapping[str, Any]
) -> tuple[tuple[str, ...] | None, dict[str, tuple[tuple[str, ...], int]]]:
    """Return the super files' columns the last superfile measurement names, and its files.

    PFS-2185.18. The columns in the order its files carry them, a column first
    met in a later file after those of the earlier ones, and each file by name
    with its columns and rows. The columns are None when the previous manifest
    names no measurement, or it cannot be read.
    """
    relative = previous.get("superfile_report")
    if not isinstance(relative, str):
        return None, {}
    columns: list[str] = []
    files: dict[str, tuple[tuple[str, ...], int]] = {}
    try:
        report = json.loads((workspace.root / relative).read_text(encoding="utf-8"))
        for entry in report["files"]:
            held = tuple(map(str, entry["columns"]))
            files[str(entry["name"])] = (held, int(entry["rows"]))
            columns.extend(column for column in held if column not in columns)
    except (OSError, ValueError, KeyError, TypeError):
        return None, {}
    return (tuple(columns) or None), files


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _rotor_row(
    manifest: Mapping[str, Any], out: Path, run_id: str, rotor: str | None
) -> tuple[str, str, dict[str, str]]:
    """Return the rotor table row of a run: (table, alias, row)."""
    found = []
    for relative, entry in (manifest.get("products") or {}).items():
        if not relative.endswith(ROTOR_TABLE_SUFFIX) or not isinstance(entry, Mapping):
            continue
        runs = entry.get("runs")
        if not isinstance(runs, list) or run_id not in runs:
            continue
        if rotor is not None and str(entry.get("rotor")) != rotor:
            continue
        found.append((relative, str(entry.get("rotor")), runs))
    if len(found) != 1:
        raise CalibrationError(
            f"run {run_id!r} is a row of {len(found)} rotor tables of {out / PRODUCTS_MANIFEST}"
            + (f" for rotor {rotor!r}" if rotor else "")
            + "; the helper reads exactly one. Post the campaign first, or name the rotor"
        )
    relative, alias, runs = found[0]
    _, rows = read_csv_table(out / relative)
    if len(rows) != len(runs):
        raise CalibrationError(
            f"{relative} holds {len(rows)} rows and its entry names {len(runs)} runs, so the "
            f"row of {run_id!r} cannot be told"
        )
    return relative, alias, rows[runs.index(run_id)]


def _loads_of(row: Mapping[str, str], alias: str, where: str) -> dict[str, float]:
    values = {
        name: _number(row.get(column))
        for name, column in (
            ("J", f"J_{alias}"),
            ("CT", f"CT_{alias}"),
            ("CQ", f"CQ_{alias}"),
            ("RPM", f"RPM_{alias}"),
            ("D", f"DIAMETER_{alias}"),
            ("RHO", "RHO"),
            ("ALPHA", "ALPHA"),
            ("BETA", "BETA"),
        )
    }
    missing = sorted(name for name, value in values.items() if value is None)
    if missing:
        raise CalibrationError(f"the rotor table row of {where} states no {', '.join(missing)}")
    known = {name: float(value) for name, value in values.items() if value is not None}
    rate = abs(known["RPM"]) / 60.0
    known["THRUST"] = known["CT"] * known["RHO"] * rate**2 * known["D"] ** 4
    known["TORQUE"] = known["CQ"] * known["RHO"] * rate**2 * known["D"] ** 5
    return known


def _whole_rotor_gap(space: Any, record: Any) -> str | None:
    """Why a sector run's record does not prove whole-rotor loads; None where it does.

    Read from the run's own script, hashed as recorded: a solve under a
    ``SYMMETRY`` other than ``NONE`` (a periodic sector, a mirrored half)
    exports the whole rotor only where every ``SET_ANALYSIS_SYMMETRY_LOADS`` of
    the script is ``ENABLE``; a solve with no symmetry has no copies to omit.
    """
    script, digest = getattr(record, "script_path", None), getattr(record, "script_sha256", None)
    if not script or not digest:
        return "its record names no hashed script"
    try:
        text = (space.sim_dir(record.sim_id) / script).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return f"its script cannot be read ({error})"
    if text_sha256(text) != digest:
        return f"its script {script} no longer hashes as recorded"
    words = [line.split() for line in text.splitlines()]
    modes = [" ".join(w[1:]) for w in words if len(w) > 1 and w[0] == "SYMMETRY"]
    partial = [mode for mode in modes if mode.upper() != "NONE"]
    loads = [w[1].upper() for w in words if len(w) > 1 and w[0] == "SET_ANALYSIS_SYMMETRY_LOADS"]
    if not partial or (loads and set(loads) == {"ENABLE"}):
        return None
    stated = ", ".join(loads) if loads else "not stated"
    return (
        f"its script solves SYMMETRY {partial[-1]} with SET_ANALYSIS_SYMMETRY_LOADS {stated}, "
        "so its loads export carries the modelled part alone"
    )
