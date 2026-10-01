"""The post stage's shared vocabulary: layout, verdicts, names, plans and the log.

A private module below every product family of :mod:`pyflightstream.post`
(AD-13, work package WP5 of 0.33.0). The families
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

import re
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.cases.windows import AZIMUTHAL
from pyflightstream.cases.workflows import ROTORS_KEY
from pyflightstream.post._tables import _PLOTS_STEP_COLUMN as PLOTS_STEP_COLUMN
from pyflightstream.post._tables import ProductError
from pyflightstream.post.unsteady import TimestepSeries, blade_passage_average, phase_locked_rows
from pyflightstream.results import FrozenSolve, UnjudgeableSolve, frozen_time_steps, parse_log_times
from pyflightstream.workspace.naming import SUPER_FILE_PREFIX

if TYPE_CHECKING:
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


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


_POST_REFUSES: ContextVar[bool] = ContextVar("post_refuses", default=True)


_POST_VERDICTS: ContextVar[dict[tuple[Path, bool], FrozenSolve | None] | None] = ContextVar(
    "post_verdicts", default=None
)


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


#: The folder under a matrix's products where the per-polar tables and
#: their ``.dat`` companions land (FR-88).
#:
#: WHY THEY MOVED. Measured in the reference workspace recorded after
#: running 0.15.0: `post/matriz/` held the polar tables LOOSE at its top
#: level beside `sections/`, `plots/` and `provenance/`, so the same
#: folder read as a directory and as a drawer at once. Every other family
#: of file already had a directory and this one did not.
#:
#: THE CAMPAIGN-LEVEL FILES DO NOT MOVE HERE, and that is the half a
#: check for an empty top level would not see: `products.json` and
#: `campaign_sweep.csv` are about the CAMPAIGN rather than about one
#: polar's sweep, so sweeping them in would be wrong in exactly the way
#: that passes a shallower test.
POLARS_DIR = "polars"


#: The folder of the per-point sections tables, under the products folder. One
#: constant like its siblings, so the writer of the recorded tables and the
#: stage cannot spell the folder two ways (0.24.0).
SECTIONS_DIR = "sections"


#: The folder under a matrix's products where the FLOW-FIELD SAMPLES of a
#: point land, whatever the run type was (FR-87).
#:
#: IT WAS ``plots`` UNTIL 0.16.0, after the solver verb that produced the
#: file rather than after what the file holds. THE GENERICITY IS THE
#: REQUIREMENT and not a side effect of the rename: a reader of a
#: finished campaign should not have to know whether a row was steady or
#: unsteady to know where the flow-field samples are, so the unsteady
#: plots table, its reductions and the probe-points table of any row all
#: land here.
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
    keys the file under (the architecture lens, 2026-09-10). This package
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

    WHAT IS NOT TAKEN is the review's other option, a collision-resistant
    filename encoding. The readable point name is a deliberate convention
    of this release and hashing it, to close a case that has never
    occurred, would cost every file a reader opens. MEASURED 2026-09-11:
    all 14 rotor aliases declared in every reference here are letters and
    underscores only, so nothing in these workspaces is refused by this;
    it is for the users the package now has.
    """
    by_safe: dict[str, list[str]] = {}
    for plan in plans.values():
        rotors = plan.get(ROTORS_KEY) if isinstance(plan, Mapping) else None
        if not isinstance(rotors, Mapping):
            continue
        for alias in rotors:
            spelling = str(alias)
            held = by_safe.setdefault(_a_name_a_file_may_carry(spelling), [])
            if spelling not in held:
                held.append(spelling)
    collisions = {safe: names for safe, names in by_safe.items() if len(names) > 1}
    if not collisions:
        return
    detail = "; ".join(
        f"{' and '.join(repr(name) for name in names)} both become {safe!r}"
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
    leaves behind; until 2026-09-22 that exception travelled out of
    `write_campaign_products` and ended the campaign's whole post, so ONE cut
    log cost every product of every simulation after it. It was measured on a
    cluster campaign recorded with 0.24.0 and posted with 0.25.0 (2026-09-22).

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
    # are nearly all of it: the one measured here carries 144 step blocks of which
    # exactly ONE cannot be read, a header the walltime guard stopped under. A
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


@dataclass
class _PartialPost:
    """What a post limited to some simulations keeps of the previous manifest (FR-307).

    ``products``, ``skipped`` and ``provenance`` are the previous entries of
    every other simulation, carried unchanged, and the entries of every
    CROSS-SIMULATION product, which such a post does not rebuild: the super
    files, whose columns are the union over every simulation of the matrix.
    ``not_rebuilt`` names each product left as the last whole post wrote it,
    with the reason; it is the manifest's ``partial.not_rebuilt`` and the post
    log's warning. ``rebuild_sections`` says whether the sections measurement,
    which reads every recorded point's script, can be rebuilt as a whole post
    rebuilds it.
    """

    sims: frozenset[str]
    products: dict[str, dict[str, object]]
    skipped: dict[str, str]
    provenance: dict[str, str]
    not_rebuilt: dict[str, str]
    rebuild_sections: bool
    whole: str


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
    own = [record for record in records if record.sim_id in sims]
    ids = {record.run_id for record in own} | {
        point.run_id for record in own for point in record.as_points()
    }
    ids |= {
        extraction.extraction_id
        for extraction in workspace.read_additional()
        if extraction.sim_id in sims
    }
    label = ", ".join(sorted(sims))
    whole = f"pyfs-matrix post {matrix_stem}" if matrix_stem else "pyfs-matrix post"
    products = {
        name: dict(entry)
        for name, entry in previous_products.items()
        if entry.get("sim_id") not in sims or _is_a_super_file(name)
    }
    not_rebuilt = {
        name: (
            "a super file's columns are the union over every simulation of the matrix, so the "
            f"post limited to simulation(s) {label} does not rebuild it; this is the file the "
            f"last whole post wrote, and {whole} rebuilds it"
        )
        for name in products
        if _is_a_super_file(name)
    }
    if previous.get("superfile_report"):
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
        },
        provenance={
            run_id: relative
            for run_id, relative in (previous.get("provenance") or {}).items()
            if run_id not in ids
        },
        not_rebuilt=not_rebuilt,
        rebuild_sections=not unread,
        whole=whole,
    )
