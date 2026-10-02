"""The files a run writes before the solver starts, and the logs it declares.

Private to :mod:`pyflightstream.run`. :func:`_write_pending_files` writes
every file a script parked for the run (child scripts and the data files a
command reads), one key for one file; the helpers beside it name the
descriptor a scheduler reads, the logs a script declares and the
observed walltime stop. The point and the sweep paths both call them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream._digest import (
    aliased_name_fault,
    file_sha256,
    one_file_key,
)
from pyflightstream._errors import (
    PyflightstreamError,
)
from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)
from pyflightstream.cases.workflows import (
    LOG_OUTPUT_VARIABLE,
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_PROGRAM,
    WALLTIME_CLOCK_PROGRAM,
    WALLTIME_CLOCK_STATE,
    effective_fsi_config,
)
from pyflightstream.run._executors import (
    ExecutionResult,
)
from pyflightstream.run._wake_edge_verdict import (
    collected_solver_log,
    script_log_names,
)
from pyflightstream.script import Script
from pyflightstream.workspace import (
    SIM_DATAPOINTS_DIR,
)


def _write_probe_points(
    sim_dir: Path, sim_id: str, points: Sequence[tuple[int, float, float, float, str]]
) -> str | None:
    """Write one simulation's probe positions, and name the file (FR-91).

    Parameters
    ----------
    sim_dir : Path
        The simulation folder.
    sim_id : str
        The simulation, which names the file.
    points : sequence
        ``(vertex, x, y, z, frame)`` in creation order, as the builder
        recorded them while emitting each point.

    Returns
    -------
    str or None
        The path relative to ``sim_dir``, or None when the row placed no
        probe point, which is every row that declares none and every row
        whose entry cites a points file the user wrote.

    Notes
    -----
    IDEMPOTENT BY CONSTRUCTION AND NOT BY A GUARD. Every point of a sweep
    writes this same path, and a probe layout is the artifact's and the
    row's rather than the point's, so the bytes are the same each time.
    The alternative -- one file per point -- would put a hundred identical
    files in the folder and say the layout depends on the angle of attack.
    """
    from pyflightstream.cases.workflows import PROBE_POSITION_COLUMNS, PROBE_PROFILE_DIR

    if not points:
        return None
    relative = f"{PROBE_PROFILE_DIR}/{sim_id}_probe_points.csv"
    target = sim_dir / relative
    # A USER'S FILE MAY BE IN THIS FOLDER TOO. A cited survey (FR-80) is read
    # where it lives, under the workspace's `inputs/profiles/`, and is not
    # staged here; but a user may still have put a file of this exact name in
    # the simulation's `profiles/`, and it would have been overwritten without
    # a word. Destroying user input is not a thing to do quietly, and a
    # refusal naming both the file and the fix costs one rename (the
    # interface, architecture and verification lenses, 2026-09-11).
    if target.is_file():
        existing = target.read_text(encoding="utf-8", errors="replace").splitlines()
        header = existing[0].strip() if existing else ""
        # AN EMPTY FILE IS NOT THIS WRITER'S EITHER. The guard read
        # `if header and ...`, so a file with no first line, or a blank one,
        # fell through and was overwritten in silence while the message above
        # and the page both said it would not be (the technical writing lens,
        # round two, 2026-09-11). The absolute is made TRUE rather than the
        # sentence softened: the one file this writer may replace is one
        # carrying its own header.
        if header != ",".join(PROBE_POSITION_COLUMNS):
            raise PyflightstreamError(
                f"{target} already exists and is not a probe positions file "
                f"(its first line reads {header!r}, empty if the file is, and "
                f"this writer's is "
                f"{','.join(PROBE_POSITION_COLUMNS)!r}). This is where the package "
                "records where it put this simulation's probe points, and it will "
                "not overwrite a file it did not write. Rename the points file "
                f"your artifact cites, or rename simulation {sim_id!r}."
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    # THROUGH `csv`, not through an f-string. A frame name carrying a comma,
    # a quote or a newline produced a row the reader silently dropped, and
    # the probe table then showed empty coordinates with nothing recorded.
    with _textio.open_text(target, "w") as handle:
        writer = _textio.csv_writer(handle)
        writer.writerow(PROBE_POSITION_COLUMNS)
        writer.writerows(points)
    return relative


def _write_pending_files(
    script: Script,
    work_dir: Path,
    *,
    case: SimCase,
    recorded: Mapping[str, str],
    run_writes: Sequence[Path] = (),
) -> dict[str, str]:
    """Write every file the script parked for the run, before the solver starts.

    Two kinds, both named by the script and written where it names them (a
    relative path lands in ``work_dir``, the solver's working directory):
    the child scripts of SCRIPT actions (PFS-2031.13) and the data files a
    command reads, the trailing-edge node file (G02) and the run's own copy
    of an actuator disc's radial thrust profile (G06). One writer for all,
    called by the point path and by the sweep path alike; the sweep path
    wrote neither kind until 0.27.0.

    A data file parked as TEXT is written in text mode, as the node file
    always was; one parked as BYTES is written exactly as it is, which is how
    the profile's copy keeps the one form 26.124 was measured to read: rows
    joined by a newline and no final newline (RPT-070).

    ONE KEY, ONE FILE. The record keys each input the solver reads by its file
    name, and ``recorded`` holds the ones the case declared, hashed when it was
    prepared: its staged geometry and its custom free stream (G15), which is
    read where it lives. A data file written here under a name already held by
    a DIFFERENT file, one of those or another written here, would replace that
    file's digest in the record, which would then name bytes the solver did not
    read under that name and leave the others unverified: a free stream named
    ``wing.wake_nodes.txt`` beside the node file of ``wing.stl``. So that is
    refused, naming the key and both files, before the solver starts. The same
    bytes arriving twice under one name are one file's digest, not two files.
    Names are compared ignoring case: ``prop.txt`` and ``PROP.txt`` are one
    file on a case-insensitive file system (Windows), where the second write
    replaces the first and the digest recorded under the first name is of
    bytes the solver never read. The record keeps each name as the script
    spelled it.

    Returns
    -------
    dict of str to str
        The sha256 of each DATA file, keyed by its file name, for the
        record's ``inputs_sha256``: each is an input the solver read, and a
        record that could not say which bytes it read could not be
        reproduced. The action scripts are hashed nowhere, as before.

    Raises
    ------
    CampaignConfigError
        If a data file's name, ignoring case, is a key ``recorded`` or
        another data file holds with a different digest.
    """
    pending_inputs = script.pending_input_files
    for name, content in pending_inputs.items():
        if not (name.startswith("pfs-field-") and name.endswith(".provenance.json")):
            continue
        provenance = json.loads(content)
        source = Path(provenance["source_path"])
        expected = provenance["source_sha256"]
        if recorded.get(source.name) != expected or file_sha256(source) != expected:
            raise CampaignConfigError(
                f"Custom field {source} changed between preparation and staging; rebuild the run."
            )
    if case.fsi is not None:
        # FSI files are point-owned inputs and use the existing guarded writer,
        # never the simulation inputs folder which may link to geometry data.
        # THE CONFIGURATION THE BUILDER WIRED (0.30.0): a quasi-steady sector's
        # structure turns at the speed its row turns the free stream, so its
        # omega is the row's and not the input's; the provenance says so.
        effective = effective_fsi_config(case)
        assert effective is not None  # case.fsi is not None
        provenance = dict(case.fsi_provenance)
        if effective.omega_rad_per_s != case.fsi.omega_rad_per_s:
            provenance["omega_rad_per_s_from_row"] = {
                "input": case.fsi.omega_rad_per_s,
                "staged": effective.omega_rad_per_s,
                "rule": "qsteady_rotor sector: the structure turns at the row's RPM",
            }
        payloads = {
            "config.json": effective.model_dump_json(indent=2) + "\n",
            "fsi-provenance.json": json.dumps(provenance, indent=2) + "\n",
        }
        source_name = case.fsi_provenance.get("source")
        if source_name:
            source = Path(str(source_name))
            if not source.is_file() or file_sha256(source) != case.fsi_provenance.get(
                "source_sha256"
            ):
                raise CampaignConfigError(
                    f"case {case.sim_id}: FSI source {source} changed; resolve the matrix again."
                )
            original = source.read_bytes()
            previous_source = pending_inputs.get(source.name)
            if previous_source is not None and previous_source != original:
                raise CampaignConfigError(
                    f"case {case.sim_id}: {source.name} conflicts with the FSI source artifact."
                )
            pending_inputs[source.name] = original
        for name, content in payloads.items():
            previous = pending_inputs.get(name)
            if previous is not None and previous != content:
                raise CampaignConfigError(
                    f"case {case.sim_id}: {name} conflicts with the resolved FSI configuration."
                )
            pending_inputs[name] = content

    def placed(name: str) -> Path:
        target = Path(name)
        return target if target.is_absolute() else work_dir / target

    # ONE PATH, ONE FILE, BEFORE ANY IS WRITTEN. The action scripts and the data
    # files are written into one folder, and two of them whose paths are equal
    # but for case are one file on a case-insensitive file system, as on
    # Windows: the second would replace the first, and an action or an import
    # would read the other's text. Different contents under such paths are
    # refused before a byte is written; the same contents are one file.
    # A path through a parent folder names the file its folded form names, so
    # the key is the normalised path, case-folded. The files the run writes
    # ITSELF after these, the counter and clock programs and the state files it
    # removes, are reserved: a file parked on one would be replaced or deleted
    # after its digest was recorded.
    def one_file(target: Path) -> str:
        return one_file_key(target)

    reserved = {
        one_file(placed(own)): own
        for own in (
            UNSTEADY_ACTION_PROGRAM,
            UNSTEADY_ACTION_COUNT,
            WALLTIME_CLOCK_PROGRAM,
            WALLTIME_CLOCK_STATE,
        )
    }
    # And the files the caller already wrote and hashed: the point's main
    # script and its probe points file. A file parked there would replace
    # them, and the solver would run other commands than script_sha256 names.
    # The run's own files, checked against one another: a machine profile's
    # descriptor name on a program's path would replace that program, hashed
    # into the record, when the point is submitted.
    for own in run_writes:
        key = one_file(placed(str(own)))
        own_alias = aliased_name_fault(Path(own).name)
        if own_alias is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run would write {own}, and its name {own_alias}. "
                "Name it plainly (the machine profile's descriptor name, for one); the "
                "solver was not started."
            )
        if key in reserved:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {own} is written by the run for two things: it is "
                f"{reserved[key]}, which the run writes itself and hashes, and a file the "
                "caller writes too (the machine profile's descriptor name, the main "
                "script, the probe points file). Rename the descriptor in the machine "
                "profile; the solver was not started."
            )
        reserved[key] = str(own)
    hashed = set(recorded.values())
    untouched: set[str] = set()
    # A DATA FILE THE RUN WRITES AND HASHES IS THE POINT'S OWN, written in the
    # folder the point runs in. One parked anywhere else, a path several points
    # share, is rewritten by the next point's run while an earlier point that
    # was submitted and has not read it yet keeps the digest of the first bytes.
    # Action scripts are hashed nowhere and keep their paths (RPT-030).
    # AN ACTION SCRIPT IS WRITTEN IN THE FOLDER THE POINT RUNS IN, as a data file
    # is: a point runs in sims/sim_<id>/datapoints/DP-<tag>/, and anywhere else
    # (the simulation folder, where a queued steady job's hashed copies live;
    # another point's folder; another simulation or workspace) holds files other
    # records name. A steady job runs in sims/sim_<id>/ and stays out of its
    # scripts/ folder, which holds every point's hashed script, and its
    # datapoints/ folder, where the points' own files are.
    own_key = one_file_key(work_dir)
    in_datapoints = Path(work_dir).parent.name.casefold() == SIM_DATAPOINTS_DIR.casefold()
    for parked in script.pending_action_scripts:
        key = one_file_key(placed(parked))
        inside = key.startswith(own_key + "/")
        parts = key[len(own_key) + 1 :].split("/") if inside else []
        elsewhere = not inside or (
            not in_datapoints
            and len(parts) > 1
            and parts[0] in ("scripts", SIM_DATAPOINTS_DIR.casefold())
        )
        if elsewhere:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run would write the action script "
                f"{placed(parked)} outside the folder the point runs in, or in the "
                "scripts or datapoint folders of its simulation, where the records of "
                "other points name the files their solvers read. Park it in the point's "
                "own folder (a name relative to script.working_dir); the solver was not "
                "started."
            )
    # Through the resolved path, so a link or a junction inside the point's
    # folder that leads elsewhere is outside it.
    root = one_file_key(work_dir)
    for parked in pending_inputs:
        here = one_file_key(placed(parked))
        if here != root and not here.startswith(root + "/"):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run would write {placed(parked)} for the solver "
                f"and record its digest, and it is outside {work_dir}, the folder the "
                "point runs in. A data file the run writes is the point's own: another "
                "point's run would rewrite a shared one before this point's solver read "
                "it. Give it a path relative to the point's folder; the solver was not "
                "started."
            )
    targets: dict[str, tuple[Path, bytes]] = {}
    for parked, content in (
        *script.pending_action_scripts.items(),
        *pending_inputs.items(),
    ):
        target = placed(parked)
        alias = aliased_name_fault(target.name)
        if alias is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run would write {target} for the solver, and "
                f"its name {alias}. Name it plainly; the solver was not started."
            )
        if one_file(target) in reserved:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run writes {reserved[one_file(target)]} itself, "
                f"after the files a script parks, and {target} is that file, so what was "
                "parked there would be replaced or removed after its digest was "
                "recorded. Rename it; the solver was not started."
            )
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        # AN INPUT THE RECORD ALREADY HASHED IS NEVER WRITTEN OVER. The staged
        # geometry may be the library's own file through the inputs junction,
        # and a file parked on its path would replace it before the check below
        # could refuse the run. The same bytes are the same file.
        if target.is_file() and file_sha256(target) in hashed:
            existing = target.read_bytes()
            if existing not in (data, data.replace(b"\n", b"\r\n")):
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: {target} is an input the run already hashed "
                    "(inputs_sha256), and a file the script parks would replace it before "
                    "the solver starts. Park it under another name; the solver was not "
                    "started and the input was not written."
                )
            # The same bytes are the same file, and it is LEFT AS IT IS: a text-mode
            # rewrite would change its line ends on Windows under the kept digest.
            untouched.add(one_file(target))
        first = targets.setdefault(one_file(target), (target, data))
        if first[1] != data:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run writes {first[0]} and {target} for the "
                "solver with different contents, and on a case-insensitive file system, "
                "as on Windows, the two paths are one file, so the second would replace "
                "the first and the record, which keys each input by its file name "
                "(inputs_sha256), could not say which bytes the solver read. Rename one "
                "of them; the solver was not started."
            )
    for action_file, action_text in script.pending_action_scripts.items():
        target = placed(action_file)
        if one_file(target) in untouched:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _textio.write_text(target, action_text)
    digests: dict[str, str] = {}
    written: dict[str, Path] = {}
    # Each name held, by its case-folded form: (the name as spelled, its digest).
    held: dict[str, tuple[str, str]] = {
        key.casefold(): (key, digest) for key, digest in recorded.items()
    }
    for input_file, content in pending_inputs.items():
        target = placed(input_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        if one_file(target) in untouched:
            pass
        elif isinstance(content, bytes):
            target.write_bytes(content)
        else:
            _textio.write_text(target, content)
        name, digest = target.name, file_sha256(target)
        key, held_digest = held.get(name.casefold(), (name, None))
        if held_digest is not None and held_digest != digest:
            other = str(written[key]) if key in written else _declared_input(case, key)
            if key == name:
                why = (
                    "is a different file of the same name. The record keys each input the "
                    f"solver reads by its file name (inputs_sha256), so {name!r} would hold "
                    "one digest for two files and could not say which bytes the solver read."
                )
            else:
                why = (
                    f"is a different file named {key!r}, the same name but for case. The "
                    "record keys each input the solver reads by its file name "
                    "(inputs_sha256), and on a case-insensitive file system, as on Windows, "
                    "names equal but for case are one file, so the two keys could not say "
                    "which bytes the solver read."
                )
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the run writes {target} for the solver to read, and "
                f"{other} {why} Rename one of them; the solver was not started."
            )
        digests[name] = digest
        written[name] = target
        held[name.casefold()] = (name, digest)
    return digests


def _descriptor_of(executor: object, work_dir: Path) -> list[Path]:
    """Return the submission descriptor a submitting executor writes into ``work_dir``.

    It is written when the point is submitted, after the parked files, so a
    file parked under its name would be replaced after its digest was
    recorded; an executor with no profile writes none.
    """
    name = getattr(getattr(executor, "profile", None), "descriptor_name", None)
    return [Path(work_dir) / str(name)] if name else []


def _declared_input(case: SimCase, name: str) -> str:
    """Name the input of ``case`` the record holds under ``name``, for a refusal."""
    if case.freestream_profile is not None and Path(case.freestream_profile).name == name:
        return f"the row's custom free stream {case.freestream_profile}"
    if case.geometry is not None and Path(case.geometry).name == name:
        return f"the row's geometry {case.geometry}"
    return f"the row's input {name!r}"


def _run_log_text(
    sim_dir: Path, collected: Sequence[str], log_file_used: str | None, result: ExecutionResult
) -> str | None:
    """Return a point's solver log: the collected one, else the run's own.

    The collected log is the one the script exported, found among the
    point's collected outputs whichever assessor judged the point
    (:func:`~pyflightstream.run._wake_edge_verdict.collected_solver_log`):
    the file the assessor names when it names one, else the one collected
    output that reads as a residual history. Without one, the log the
    executor read after the process (``FlightStreamLog.txt``). None when
    neither exists.
    """
    collected_log = collected_solver_log(sim_dir, collected, log_file_used)
    return collected_log if collected_log is not None else result.log_text


def _declared_logs(case: SimCase, script_text: str) -> list[str]:
    """Name every output of a point that is its solver log, whatever its name (G06).

    The files the point's script (``script_text``, as rendered) tells the
    solver to write its log to, every EXPORT_LOG line, and the output the
    case's LOG_OUTPUT names, counted from 1 among its outputs as the builders
    count it. A case built in Python and a LEGACY row's recipe name the log as
    they like, so the ``_log.txt`` suffix does not find it, and a line refusing
    the disc's profile file was left unread in it. A LOG_OUTPUT that is not a
    position among the outputs names nothing here; the builders that export it
    refuse it before a line.
    """
    names = script_log_names(script_text)
    stated = str(case.variables.get(LOG_OUTPUT_VARIABLE) or "").strip()
    position = int(stated) if stated.isdecimal() else 0
    if 1 <= position <= len(case.outputs):
        name = Path(case.outputs[position - 1]).name
        if name not in names:
            names.append(name)
    return names


def _walltime_stop(state_path: Path) -> dict | None:
    """Where the wall-clock watchdog stopped this run, or None if it did not.

    None covers three cases that are all the same answer to the caller: no
    clock on the row, a clock that never fired, and a state file the
    program never got to write. A run that ended for its own reasons is
    not a run the clock stopped, and saying so is the whole value.
    """
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not state.get("fired"):
        return None
    stopped = state.get("stopped_at")
    if not isinstance(stopped, dict):
        return None
    observed = state.get("steps")
    claimed = stopped.get("step")
    # A callback may abort its own script while the solver keeps marching.
    # Only a matching final callback count can support the stop marker.
    if (
        not isinstance(observed, int)
        or isinstance(observed, bool)
        or not isinstance(claimed, int)
        or isinstance(claimed, bool)
        or claimed < 1
        or observed != claimed
    ):
        return None
    return dict(stopped)
