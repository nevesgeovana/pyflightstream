"""The acoustic signals of a point: their emission by the run and the contract of their reading.

Pipeline role: the cases row, because both sides of the contract name it: the
setup and the end of an unsteady point emit the solver's acoustic toolbox and
declare its export (work package E2, here), and the post stage reads that
export back (work package E1, :mod:`pyflightstream.post.acoustics`), and the
post row may import the cases row and never the reverse. The contract the two
packages code against:

* :class:`AcousticSignal`, one observer's signal as the post stage hands it on;
* :data:`ACOUSTIC_SIGNALS_SUFFIX`, the end of the name of the file a point's
  acoustic export is written to.

WHAT A ROW STATES (0.32.0, FR-265 to FR-269). Five keys of the
``VAR_NAMES_VALUES`` cell, registered on the two unsteady run types
(``unsteady`` and ``unsteady_rotor``) and on no steady one:

* ``ACOUSTIC_SOURCES: ENABLE`` (or ``DISABLE``, the control) switches the
  recording of acoustic sources during the march. It is a setup command the
  manual places before the solver initialises, and the builder emits it there;
* ``ACOUSTIC_OBSERVERS: MIC1 0.0 10.0 0.0, MIC2 0.0 -10.0 0.0`` declares named
  observer points, each ``NAME X Y Z`` in metres in the reference coordinate
  system, observers separated by commas;
* ``ACOUSTIC_OBSERVERS_FILE: <stem>`` names ``inputs/acoustics/<stem>.csv``,
  the solver's own observer file (a count line, then that many ``x,y,z``
  lines), resolved when the row binds and imported by the solver from the
  point's own copy;
* ``ACOUSTIC_OBSERVER_TIME: T0 T1 N`` is the observers' time window in seconds
  and its number of samples, required whenever an observer is declared;
* ``ACOUSTIC_SECTION: {PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 /
  AZIMUTH_OBSERVERS:4 / INNER_RADIUS:5.0 / OUTER_RADIUS:10.0}`` declares one
  annular grid of observers (an arc or a disc in a plane), lengths in metres,
  in the frame ``FRAME`` names (a frame the run creates, such as ``MRP``) or
  in the reference coordinate system when it names none.

At the end of the march, after the solve and before the export phase, a row
that declares any observer emits ``COMPUTE_ACOUSTIC_SIGNALS``; a row with
point or file observers then exports every observer's signal to ONE file,
``<point>_acoustic_signals.txt``, which the point declares, collects and
hashes like its other outputs; a section then writes its VTK files into the
folder ``<point>_acoustic_section/`` beside them, which the run creates, and
the collect lists and hashes each file it holds. The order is the one the
licensed round-1 probe A1 ran on FlightStream 26.124 (the compat report
``reports/compat/CMP-26124_2026-09-30_acoustics.yaml``).

WHAT THE PROBE MEASURED about the export (A1 against its control A0, which
differ in the ``ACOUSTIC_SOURCES`` token only): one block per observer, a
line ``Observer: <name>``, a line ``Position: x,y,z``, a line ``Columns:
Observer time (sec), PL (Pa), PT (Pa), PO (Pa)``, then one row per sample of
the observer time window, the first at ``T0`` and ``N`` rows spaced by
``(T1 - T0) / N``; an imported observer is named ``Observer <n>``, its place in
the solver's own list; with ``DISABLE`` every pressure is zero. The section
wrote one VTK file per sample of the time window, ``VTK_output-NNN.vtk``, each
holding every observer of the grid. The name the export is written under is
this package's choice, and the probe confirmed the solver writes the path it
is given: the suffix below stands.

WHAT STAYS UNMEASURED: whether the solver creates a section folder that does
not exist (the run creates it, so it need not), how a relative ``STORAGE_PATH``
resolves (the builder writes the folder's full path wherever the run names
the folder the point runs in), and the length unit of the exported
coordinates on a simulation not in metres. The metre and pascal of
:class:`AcousticSignal` are the contract's units, so a reader converts to
them; they are not a claim about the file.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from typing import TYPE_CHECKING

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import CampaignConfigError, InputKey, classify_outputs

if TYPE_CHECKING:
    from pyflightstream.cases import SimCase
    from pyflightstream.script import Script

__all__ = [
    "ACOUSTICS_DIR",
    "ACOUSTIC_KEYS",
    "ACOUSTIC_KEY_MEANINGS",
    "ACOUSTIC_OBSERVERS_FILE_VARIABLE",
    "ACOUSTIC_OBSERVERS_VARIABLE",
    "ACOUSTIC_OBSERVER_TIME_VARIABLE",
    "ACOUSTIC_SECTION_NOTE",
    "ACOUSTIC_SECTION_SUFFIX",
    "ACOUSTIC_SECTION_VARIABLE",
    "ACOUSTIC_SIGNALS_SUFFIX",
    "ACOUSTIC_SOURCES_VARIABLE",
    "AcousticObserver",
    "AcousticRequest",
    "AcousticSection",
    "AcousticSignal",
    "OBSERVERS_COPY_SUFFIX",
    "ObserverTime",
    "REFERENCE_FRAME_INDEX",
    "SECTION_KEYS",
    "SECTION_PLANES",
    "SOURCE_MODES",
    "acoustic_request",
    "acoustic_section_leftovers",
    "acoustic_section_outputs",
    "acoustic_signals_output",
    "emit_acoustic_setup",
    "emit_acoustic_signals",
    "is_acoustic_output",
    "read_observers_file",
    "refuse_acoustics_on_a_continuation",
    "resolve_observers_file",
    "with_acoustic_signals",
]

#: The end of the name of a point's acoustic export, written beside its
#: other exports as ``<point><suffix>``. Confirmed by the round-1 probe A1 on
#: 26.124: the solver writes the export to the path it is given, and the file
#: is text (``Observer:``, ``Position:`` and ``Columns:`` lines, then rows).
ACOUSTIC_SIGNALS_SUFFIX = "_acoustic_signals.txt"

#: The end of the name of the folder a point's acoustic section writes its VTK
#: files into, ``<point><suffix>/``, beside the point's other exports.
ACOUSTIC_SECTION_SUFFIX = "_acoustic_section"

#: The note the run writes into the section's folder before the solver starts,
#: which is how the folder exists when the solver writes into it. It states
#: the section the row declared; the collect lists every other file.
ACOUSTIC_SECTION_NOTE = "pyfs-acoustic-section.txt"

#: The end of the name of the point's own copy of a row's observer file, in the
#: folder the point runs in; the solver imports the copy, which the run hashes.
OBSERVERS_COPY_SUFFIX = ".acoustic_observers.csv"

#: The folder of the input library a row's observer file lives in.
ACOUSTICS_DIR = "acoustics"

ACOUSTIC_SOURCES_VARIABLE = "ACOUSTIC_SOURCES"
ACOUSTIC_OBSERVERS_VARIABLE = "ACOUSTIC_OBSERVERS"
ACOUSTIC_OBSERVERS_FILE_VARIABLE = "ACOUSTIC_OBSERVERS_FILE"
ACOUSTIC_OBSERVER_TIME_VARIABLE = "ACOUSTIC_OBSERVER_TIME"
ACOUSTIC_SECTION_VARIABLE = "ACOUSTIC_SECTION"

#: The row keys this module reads, registered on the two unsteady run types.
ACOUSTIC_KEYS: tuple[str, ...] = (
    ACOUSTIC_SOURCES_VARIABLE,
    ACOUSTIC_OBSERVERS_VARIABLE,
    ACOUSTIC_OBSERVERS_FILE_VARIABLE,
    ACOUSTIC_OBSERVER_TIME_VARIABLE,
    ACOUSTIC_SECTION_VARIABLE,
)

#: The two values of ``ACOUSTIC_SOURCES``, the command's own.
SOURCE_MODES: tuple[str, ...] = ("ENABLE", "DISABLE")

#: The keys of an ``ACOUSTIC_SECTION`` record, as the command spells its own
#: keywords; ``FRAME`` alone may be left out.
SECTION_KEYS: tuple[str, ...] = (
    "FRAME",
    "PLANE",
    "OFFSET",
    "RADIAL_OBSERVERS",
    "AZIMUTH_OBSERVERS",
    "INNER_RADIUS",
    "OUTER_RADIUS",
)

#: The planes a section is cut in, the command's own values.
SECTION_PLANES: tuple[str, ...] = ("XY", "XZ", "YZ")

#: The solver's reference coordinate system, the frame a section is placed in
#: when its record names none (the index the round-1 probe used).
REFERENCE_FRAME_INDEX = 1

_OBSERVER_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")

#: What each key sets, merged into the run types' glossary
#: (:data:`pyflightstream.cases.workflows.ROW_KEY_MEANINGS`).
ACOUSTIC_KEY_MEANINGS: Mapping[str, InputKey] = {
    ACOUSTIC_SOURCES_VARIABLE: InputKey(
        "Record the acoustic sources during the unsteady march, set up before the solver "
        "initialises; DISABLE is the control, whose signals are zero.",
        "ENABLE or DISABLE",
        "ACOUSTIC_SOURCES",
    ),
    ACOUSTIC_OBSERVERS_VARIABLE: InputKey(
        "Named acoustic observer points, each NAME X Y Z in metres in the reference "
        "coordinate system, observers separated by commas; their signals are computed "
        "and exported to <point>_acoustic_signals.txt at the end of the run.",
        "NAME X Y Z, NAME X Y Z (metres)",
        "CREATE_NEW_ACOUSTIC_OBSERVER, COMPUTE_ACOUSTIC_SIGNALS, EXPORT_ACOUSTIC_SIGNALS",
    ),
    ACOUSTIC_OBSERVERS_FILE_VARIABLE: InputKey(
        "Acoustic observers imported by the solver from a file of the input library (a "
        "count line, then that many x,y,z lines in the simulation's length unit, which "
        "must be metres); the point imports its own hashed copy.",
        "the stem of a file of inputs/acoustics/ (<stem>.csv)",
        "ACOUSTIC_OBSERVERS_IMPORT, COMPUTE_ACOUSTIC_SIGNALS, EXPORT_ACOUSTIC_SIGNALS",
    ),
    ACOUSTIC_OBSERVER_TIME_VARIABLE: InputKey(
        "The observers' time window and its number of samples, required with any "
        "observer: the signal is sampled N times from T0, spaced by (T1 - T0) / N.",
        "T0 T1 N (seconds, seconds, a count)",
        "SET_ACOUSTIC_OBSERVER_TIME",
    ),
    ACOUSTIC_SECTION_VARIABLE: InputKey(
        "One annular grid of acoustic observers in a plane, whose VTK files are written "
        "into <point>_acoustic_section/ after the signals are computed; lengths in "
        "metres, FRAME a frame the run creates or the reference coordinate system.",
        "{PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 / AZIMUTH_OBSERVERS:4 / "
        "INNER_RADIUS:5.0 / OUTER_RADIUS:10.0}, FRAME optional",
        "CREATE_ACOUSTIC_SECTION",
    ),
}


@dataclass(frozen=True)
class AcousticSignal:
    """One observer's acoustic pressure signal.

    Parameters
    ----------
    observer : str
        The observer's name, as its creation named it.
    x_m, y_m, z_m : float
        The observer's position in the reference coordinate system, in metres.
    time_s : tuple of float
        The observer's time samples, in seconds.
    pressure_pa : tuple of float
        The acoustic pressure at each time sample, in pascals.
    """

    observer: str
    x_m: float
    y_m: float
    z_m: float
    time_s: tuple[float, ...]
    pressure_pa: tuple[float, ...]


@dataclass(frozen=True)
class AcousticObserver:
    """One named observer point a row declares, in metres, reference coordinate system."""

    name: str
    x_m: float
    y_m: float
    z_m: float


@dataclass(frozen=True)
class ObserverTime:
    """The observers' time window, in seconds, and its number of samples."""

    initial_s: float
    final_s: float
    steps: int


@dataclass(frozen=True)
class AcousticSection:
    """The one annular grid of observers a row declares, lengths in metres."""

    frame: str | None
    plane: str
    offset_m: float
    radial_observers: int
    azimuth_observers: int
    inner_radius_m: float
    outer_radius_m: float


@dataclass(frozen=True)
class AcousticRequest:
    """What a row's acoustic keys ask of the run, read and checked once.

    Attributes
    ----------
    sources : str or None
        ``ENABLE`` or ``DISABLE``, the value of ``ACOUSTIC_SOURCES``.
    observers : tuple of AcousticObserver
        The named points of ``ACOUSTIC_OBSERVERS``, in the order written.
    observers_file : str or None
        The absolute path of the file ``ACOUSTIC_OBSERVERS_FILE`` names, as the
        row's binding resolved it.
    time : ObserverTime or None
        ``ACOUSTIC_OBSERVER_TIME``.
    section : AcousticSection or None
        ``ACOUSTIC_SECTION``.
    """

    sources: str | None
    observers: tuple[AcousticObserver, ...]
    observers_file: str | None
    time: ObserverTime | None
    section: AcousticSection | None

    @property
    def exports_signals(self) -> bool:
        """Whether the run exports a signals file: some point or file observer exists."""
        return bool(self.observers) or self.observers_file is not None

    @property
    def computes(self) -> bool:
        """Whether the run computes signals at all: any observer or a section."""
        return self.exports_signals or self.section is not None


def _stated(case: SimCase, key: str) -> str | None:
    """Return the row's value for one key, stripped, or None when absent or empty."""
    value = case.variables.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(case: SimCase, key: str, token: str, what: str) -> float:
    try:
        value = float(token)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} with {what} {token!r}, which is not a number."
        ) from None
    if not math.isfinite(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} with {what} {token!r}, which is not finite."
        )
    return value


def _count(case: SimCase, key: str, token: str, what: str) -> int:
    if not re.fullmatch(r"\d+", token.strip()) or int(token) < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} with {what} {token!r}; it is a count, a "
            "whole number of at least 1."
        )
    return int(token)


def _observers(case: SimCase, text: str) -> tuple[AcousticObserver, ...]:
    key = ACOUSTIC_OBSERVERS_VARIABLE
    observers: list[AcousticObserver] = []
    for entry in text.split(","):
        tokens = entry.split()
        if len(tokens) != 4:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key} with the entry {entry.strip()!r}; each "
                "observer is NAME X Y Z, its name then its position in metres in the "
                "reference coordinate system, and observers are separated by commas: "
                f"'{key}: MIC1 0.0 10.0 0.0, MIC2 0.0 -10.0 0.0'."
            )
        name = tokens[0]
        if not _OBSERVER_NAME.match(name):
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key} naming an observer {name!r}; a name is "
                "one word of letters, digits, '_', '.' or '-', which the solver prints back "
                "on the observer's block of the export."
            )
        x, y, z = (_float(case, key, token, f"the {name} coordinate") for token in tokens[1:])
        observers.append(AcousticObserver(name, x, y, z))
    names = [observer.name for observer in observers]
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} naming {', '.join(twice)} more than once; "
            "the export names each observer's block by its name, so two observers of one "
            "name could not be told apart in it."
        )
    return tuple(observers)


def _time(case: SimCase, text: str) -> ObserverTime:
    key = ACOUSTIC_OBSERVER_TIME_VARIABLE
    tokens = text.split()
    if len(tokens) != 3:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key}: {text}; it is T0 T1 N, the first and last "
            "time of the observers' window in seconds and its number of samples: "
            f"'{key}: 0.05 0.2 16'."
        )
    initial = _float(case, key, tokens[0], "the initial time")
    final = _float(case, key, tokens[1], "the final time")
    steps = _count(case, key, tokens[2], "the number of samples")
    if initial < 0.0 or final <= initial:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key}: {text}; the window runs forward from a time "
            "of at least zero, so T1 is above T0 and T0 is not negative."
        )
    return ObserverTime(initial, final, steps)


def _section(case: SimCase, text: str) -> AcousticSection:
    key = ACOUSTIC_SECTION_VARIABLE
    body = text.strip()
    if not (body.startswith("{") and body.endswith("}")):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key}: {text}; a section is one record in braces, "
            "its pairs separated by '/': "
            f"'{key}: {{PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 / AZIMUTH_OBSERVERS:4 / "
            "INNER_RADIUS:5.0 / OUTER_RADIUS:10.0}'."
        )
    record: dict[str, str] = {}
    for pair in body[1:-1].split("/"):
        name, separator, value = pair.partition(":")
        name = name.strip().upper()
        if not separator or not name:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key} with {pair.strip()!r}, which is not a "
                "KEY:VALUE pair."
            )
        if name in record:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key} with {name} twice; a record states each "
                "key once."
            )
        record[name] = value.strip()
    unknown = sorted(set(record) - set(SECTION_KEYS))
    missing = [name for name in SECTION_KEYS if name != "FRAME" and name not in record]
    if unknown or missing:
        said = []
        if unknown:
            said.append(f"states {', '.join(unknown)}, which a section does not read")
        if missing:
            said.append(f"does not state {', '.join(missing)}")
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the {key} record {' and '.join(said)}. A section states "
            f"{', '.join(name for name in SECTION_KEYS if name != 'FRAME')}, lengths in "
            "metres, and FRAME when it is placed in a frame the run creates."
        )
    plane = record["PLANE"].upper()
    if plane not in SECTION_PLANES:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} with PLANE {record['PLANE']!r}; a section is "
            f"cut in one of {', '.join(SECTION_PLANES)}."
        )
    inner = _float(case, key, record["INNER_RADIUS"], "INNER_RADIUS")
    outer = _float(case, key, record["OUTER_RADIUS"], "OUTER_RADIUS")
    if inner < 0.0 or outer <= inner:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} with INNER_RADIUS {inner} and OUTER_RADIUS "
            f"{outer}; the ring runs outward from an inner radius of at least zero."
        )
    return AcousticSection(
        frame=record.get("FRAME") or None,
        plane=plane,
        offset_m=_float(case, key, record["OFFSET"], "OFFSET"),
        radial_observers=_count(case, key, record["RADIAL_OBSERVERS"], "RADIAL_OBSERVERS"),
        azimuth_observers=_count(case, key, record["AZIMUTH_OBSERVERS"], "AZIMUTH_OBSERVERS"),
        inner_radius_m=inner,
        outer_radius_m=outer,
    )


def acoustic_request(case: SimCase) -> AcousticRequest | None:
    """Read and check the row's acoustic keys, or return None when it states none.

    Parameters
    ----------
    case : SimCase
        The case, its variables as the matrix row wrote them and
        :attr:`~pyflightstream.cases.SimCase.acoustic_observers_file` as the
        binding resolved it.

    Returns
    -------
    AcousticRequest or None
        None for a case stating no acoustic key.

    Raises
    ------
    CampaignConfigError
        A value not in its form; an observer, a file or a section without
        ``ACOUSTIC_SOURCES``, which is refused rather than defaulted since a
        signal computed with no source recorded is zero; observers without
        ``ACOUSTIC_OBSERVER_TIME``, or the time without an observer; the file key
        with no resolved file.
    """
    stated = {key: _stated(case, key) for key in ACOUSTIC_KEYS}
    path = case.acoustic_observers_file
    if not any(stated.values()) and path is None:
        return None
    sources = stated[ACOUSTIC_SOURCES_VARIABLE]
    if sources is not None:
        sources = sources.upper()
        if sources not in SOURCE_MODES:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ACOUSTIC_SOURCES_VARIABLE}: "
                f"{stated[ACOUSTIC_SOURCES_VARIABLE]}; it is ENABLE, or DISABLE for a "
                "control whose signals are zero."
            )
    stem = stated[ACOUSTIC_OBSERVERS_FILE_VARIABLE]
    if stem is not None and path is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ACOUSTIC_OBSERVERS_FILE_VARIABLE}: {stem} and "
            "carries no resolved file. A matrix row's file is resolved against the "
            f"workspace's inputs/{ACOUSTICS_DIR}/ when the row binds; a case built in Python "
            "sets acoustic_observers_file to the file's absolute path."
        )
    text = stated[ACOUSTIC_OBSERVERS_VARIABLE]
    observers = _observers(case, text) if text is not None else ()
    section_text = stated[ACOUSTIC_SECTION_VARIABLE]
    section = _section(case, section_text) if section_text is not None else None
    time_text = stated[ACOUSTIC_OBSERVER_TIME_VARIABLE]
    time = _time(case, time_text) if time_text is not None else None
    request = AcousticRequest(sources, observers, path, time, section)
    if request.computes and sources is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares acoustic observers and states no "
            f"{ACOUSTIC_SOURCES_VARIABLE}. The signals are computed from the sources the "
            "march records, and none is recorded unless the setup switches them on; state "
            f"'{ACOUSTIC_SOURCES_VARIABLE}: ENABLE', or DISABLE for a control whose "
            "signals are zero."
        )
    if request.computes and time is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares acoustic observers and states no "
            f"{ACOUSTIC_OBSERVER_TIME_VARIABLE}. The observers' window is their own and "
            "not the march's (a signal arrives after a propagation delay), so the row "
            f"states it: '{ACOUSTIC_OBSERVER_TIME_VARIABLE}: 0.05 0.2 16'."
        )
    if time is not None and not request.computes:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ACOUSTIC_OBSERVER_TIME_VARIABLE} and declares no "
            f"observer ({ACOUSTIC_OBSERVERS_VARIABLE}, {ACOUSTIC_OBSERVERS_FILE_VARIABLE} or "
            f"{ACOUSTIC_SECTION_VARIABLE}), so the window would sample nothing."
        )
    return request


def acoustic_signals_output(case: SimCase, stem: str) -> str | None:
    """Return the name a point exports its signals to, or None when it exports none.

    Parameters
    ----------
    case : SimCase
        The case whose row may declare observers.
    stem : str
        The point's rendered stem, the name every export of the point carries.

    Returns
    -------
    str or None
        ``<stem>_acoustic_signals.txt`` where the row declares a point or a file
        observer; None otherwise, for a case stating no acoustic key, and for
        one whose acoustic keys are not in their form: the point is named by the
        run layer before its script is built, and the builder then refuses the
        row with the sentence that names the key, as a blocked point and not as
        a stopped campaign.
    """
    try:
        request = acoustic_request(case)
    except CampaignConfigError:
        return None
    if request is None or not request.exports_signals:
        return None
    return f"{stem}{ACOUSTIC_SIGNALS_SUFFIX}"


def with_acoustic_signals(outputs: Sequence[str], case: SimCase, stem: str) -> list[str]:
    """Return a point's outputs with its acoustic export declared last, where it has one.

    The run layer's one hook (``run._ids._point_names``), for the plan and the run
    alike, so the plan judges the script the run will execute and the collect
    looks for the file the script writes. Declared last so the loads table,
    which :func:`~pyflightstream.cases.classify_outputs` finds by its ``.txt``,
    is claimed first; the classifier leaves the acoustic export out anyway.

    Parameters
    ----------
    outputs : sequence of str
        The point's declared outputs.
    case : SimCase
        The point's case.
    stem : str
        The point's rendered file stem.

    Returns
    -------
    list of str
        ``outputs`` with the signals export appended when the case declares one and it is not
        already listed.
    """
    name = acoustic_signals_output(case, stem)
    listed = list(outputs)
    if name is not None and name not in listed:
        listed.append(name)
    return listed


def is_acoustic_output(name: str | PurePath) -> bool:
    """Whether a declared or recorded output is an acoustic file, never a surface export.

    The signals export ends in ``.txt`` like the loads table, and a section's
    files end in ``.vtk`` like the surface export, so the classifier asks this
    before it pairs a name with a kind.

    Parameters
    ----------
    name : str or PurePath
        A declared or recorded output name.

    Returns
    -------
    bool
        True for the signals export and for any file inside an acoustic section folder.
    """
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.name.lower().endswith(ACOUSTIC_SIGNALS_SUFFIX):
        return True
    return any(part.lower().endswith(ACOUSTIC_SECTION_SUFFIX) for part in path.parts[:-1])


def refuse_acoustics_on_a_continuation(case: SimCase) -> None:
    """Refuse a continuation of a row that asks for acoustic signals.

    A continuation reopens the simulation a stopped march saved and runs the
    steps it owes; whether the sources recorded before the stop survive the
    save is not measured, so a signal computed at its end could cover part of
    the march with nothing saying which part.

    Parameters
    ----------
    case : SimCase
        The case of the continuation.

    Raises
    ------
    CampaignConfigError
        The case states any acoustic key.
    """
    if acoustic_request(case) is None:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} continues a stopped run and states acoustic keys. Whether the "
        "acoustic sources recorded before the stop survive the saved simulation is not "
        "measured, so the signals of a continued march could cover part of it with nothing "
        "saying which; run the point again from its mesh, or drop the acoustic keys from "
        "the continuation."
    )


def _in_the_point_folder(script: Script, name: str) -> str:
    """Name a file of the point in the folder the point runs in."""
    return name if script.working_dir is None else str(PurePath(script.working_dir) / name)


def _reached(script: Script, command: str) -> bool:
    """Whether the script already emitted ``command`` as a line of its own."""
    return any(line.split(" ", 1)[0] == command for line in script.render().splitlines())


def emit_acoustic_setup(
    case: SimCase, script: Script, *, from_metres: Callable[[str], float]
) -> None:
    """Emit the acoustic setup a row states, before the solver initialises.

    ``ACOUSTIC_SOURCES``, then each named observer, then the imported file (the
    point's own copy, parked for the run to write and hash), then the observer
    time window: the order of the round-1 probe A1. A case stating no acoustic
    key emits nothing.

    Parameters
    ----------
    case : SimCase
        The point's case.
    script : Script
        The script being built, still in its setup phase.
    from_metres : callable
        The builder's factor from metres to the simulation's length unit, asked
        with a description of what is converted.

    Raises
    ------
    CampaignConfigError
        The script already initialised the solver: sources switched on after
        ``INITIALIZE_SOLVER`` record nothing (the manual's ordering rule); a
        file of observers on a simulation not in metres, whose coordinates the
        package cannot convert because the solver reads the file itself.
    """
    request = acoustic_request(case)
    if request is None:
        return
    if _reached(script, "INITIALIZE_SOLVER"):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {ACOUSTIC_SOURCES_VARIABLE} would follow "
            "INITIALIZE_SOLVER, and the manual has the sources switched on before the solver "
            "initialises; after it the march runs and records no source, so the signals "
            "would be computed from nothing. The acoustic setup belongs to the setup phase."
        )
    if request.sources is not None:
        script.emit("ACOUSTIC_SOURCES", request.sources)
    if request.observers:
        factor = from_metres(f"the coordinates of {ACOUSTIC_OBSERVERS_VARIABLE}")
        for observer in request.observers:
            script.emit(
                "CREATE_NEW_ACOUSTIC_OBSERVER",
                observer.name,
                observer.x_m * factor,
                observer.y_m * factor,
                observer.z_m * factor,
            )
    if request.observers_file is not None:
        factor = from_metres(f"the observers of {ACOUSTIC_OBSERVERS_FILE_VARIABLE}")
        if factor != 1.0:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ACOUSTIC_OBSERVERS_FILE_VARIABLE} on a "
                "simulation whose length unit is not the metre. The solver reads the file's "
                "coordinates in the simulation's own unit and the package does not rewrite "
                f"the file, so declare these observers in {ACOUSTIC_OBSERVERS_VARIABLE}, "
                "whose metres the package converts."
            )
        source = Path(request.observers_file)
        read_observers_file(source)
        copy = _in_the_point_folder(script, f"{source.stem}{OBSERVERS_COPY_SUFFIX}")
        script._pending_input_files[copy] = source.read_bytes()
        script.emit("ACOUSTIC_OBSERVERS_IMPORT", copy)
    if request.time is not None:
        script.emit(
            "SET_ACOUSTIC_OBSERVER_TIME",
            request.time.initial_s,
            request.time.final_s,
            request.time.steps,
        )


def _frame_index(case: SimCase, frames: Mapping[str, object] | None, name: str | None) -> int:
    if name is None:
        return REFERENCE_FRAME_INDEX
    index = (frames or {}).get(name)
    if isinstance(index, int) and not isinstance(index, bool):
        return index
    named = sorted(key for key, value in (frames or {}).items() if isinstance(value, int))
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {ACOUSTIC_SECTION_VARIABLE} in the frame {name!r}, which "
        f"this run does not create; the frames it creates are {', '.join(named) or 'none'}. "
        "Leave FRAME out to place the section in the reference coordinate system."
    )


def _point_stem(case: SimCase) -> str:
    """Return the point's stem, read off its declared loads table (``<stem>.txt``)."""
    loads = classify_outputs([str(name) for name in case.outputs]).get("loads")
    if loads is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares an acoustic section and no loads table among its "
            "outputs, which is the name the section's folder is named after."
        )
    return PurePath(loads).stem


def emit_acoustic_signals(
    case: SimCase,
    script: Script,
    *,
    unsteady: bool,
    frames: Mapping[str, object] | None,
    from_metres: Callable[[str], float],
) -> None:
    """Emit the computation and the exports of the signals, after the solve.

    ``COMPUTE_ACOUSTIC_SIGNALS`` where the row declares any observer, then
    ``EXPORT_ACOUSTIC_SIGNALS`` to the point's declared
    ``<point>_acoustic_signals.txt`` where it declares a point or a file
    observer, then ``CREATE_ACOUSTIC_SECTION`` into ``<point>_acoustic_section/``
    where it declares a section, whose folder the run creates by writing
    :data:`ACOUSTIC_SECTION_NOTE` into it. The analysis phase, before the
    point's other exports. A case stating no observer emits nothing.

    Parameters
    ----------
    case : SimCase
        The point's case, carrying its acoustic keys.
    script : Script
        The script being built; the commands are appended to it.
    unsteady : bool
        Whether the run is unsteady; a steady run with acoustic keys is refused.
    frames : mapping of str to object, or None
        The frames this run creates, by name, each with its index; a section stated in a frame the
        run does not create is refused, and one stating none is placed in the reference frame.
    from_metres : callable
        The builder's factor from metres to the simulation's length unit, asked with a description
        of what is converted.

    Raises
    ------
    CampaignConfigError
        The run is steady, or the script has not started the solver: the three
        commands read the sources an unsteady march recorded, and there is none;
        the point declares no acoustic export for its point or file observers.
    """
    request = acoustic_request(case)
    if request is None or not request.computes:
        return
    if not unsteady or not _reached(script, "START_SOLVER"):
        why = "the run is steady" if not unsteady else "the solver has not been started"
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks for acoustic signals and {why}. "
            "COMPUTE_ACOUSTIC_SIGNALS and the acoustic exports read the sources an unsteady "
            "march records, so they follow the solve of an unsteady run: the acoustic keys "
            "belong to the unsteady and unsteady_rotor run types."
        )
    script.emit("COMPUTE_ACOUSTIC_SIGNALS")
    if request.exports_signals:
        signals = [
            str(name)
            for name in case.outputs
            if str(name).lower().endswith(ACOUSTIC_SIGNALS_SUFFIX)
        ]
        if not signals:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares acoustic observers and no output named "
                f"<point>{ACOUSTIC_SIGNALS_SUFFIX}. The run layer declares it for a matrix "
                "row; a case built in Python adds it to its outputs "
                "(pyflightstream.cases.acoustics.with_acoustic_signals)."
            )
        script.emit("EXPORT_ACOUSTIC_SIGNALS", signals[0])
    section = request.section
    if section is None:
        return
    frame = _frame_index(case, frames, section.frame)
    factor = from_metres(
        f"the OFFSET, INNER_RADIUS and OUTER_RADIUS of {ACOUSTIC_SECTION_VARIABLE}"
    )
    folder = _in_the_point_folder(script, f"{_point_stem(case)}{ACOUSTIC_SECTION_SUFFIX}")
    script._pending_input_files[str(PurePath(folder) / ACOUSTIC_SECTION_NOTE)] = (
        "pyflightstream acoustic section of this point\n"
        f"frame {frame}\nplane {section.plane}\noffset_m {section.offset_m}\n"
        f"radial_observers {section.radial_observers}\n"
        f"azimuth_observers {section.azimuth_observers}\n"
        f"inner_radius_m {section.inner_radius_m}\nouter_radius_m {section.outer_radius_m}\n"
    )
    script.emit(
        "CREATE_ACOUSTIC_SECTION",
        frame=frame,
        plane=section.plane,
        offset=section.offset_m * factor,
        radial_observers=section.radial_observers,
        azimuth_observers=section.azimuth_observers,
        inner_radius=section.inner_radius_m * factor,
        outer_radius=section.outer_radius_m * factor,
        storage_path=folder,
    )


def read_observers_file(path: str | Path) -> tuple[tuple[float, float, float], ...]:
    """Read the solver's observer file: a count line, then that many ``x,y,z`` lines.

    The form the manual gives ``ACOUSTIC_OBSERVERS_IMPORT`` and the round-1
    probe A1 imported on 26.124. Blank lines are skipped.

    Parameters
    ----------
    path : str or Path
        The observer file.

    Returns
    -------
    tuple of (float, float, float)
        The observer positions, in the order written.

    Raises
    ------
    CampaignConfigError
        The file cannot be read, its first line is not a count of at least one,
        a line is not three comma-separated numbers, or the count is not the
        number of lines that follow.
    """
    where = Path(path)
    try:
        lines = [line.strip() for line in where.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError) as error:
        raise CampaignConfigError(
            f"the acoustic observer file {where} cannot be read ({error})."
        ) from None
    rows = [line for line in lines if line]
    if not rows or not re.fullmatch(r"\d+", rows[0]) or int(rows[0]) < 1:
        raise CampaignConfigError(
            f"the acoustic observer file {where} does not open with a count of observers: its "
            "first line is how many x,y,z lines follow, at least 1."
        )
    count = int(rows[0])
    points: list[tuple[float, float, float]] = []
    for number, row in enumerate(rows[1:], start=2):
        cells = [cell.strip() for cell in row.split(",")]
        try:
            x, y, z = (float(cell) for cell in cells)
        except ValueError:
            raise CampaignConfigError(
                f"the acoustic observer file {where}, line {number}, reads {row!r}; each "
                "observer is one line of three comma-separated numbers, x,y,z."
            ) from None
        if not all(math.isfinite(value) for value in (x, y, z)):
            raise CampaignConfigError(
                f"the acoustic observer file {where}, line {number}, reads {row!r}, which is "
                "not finite."
            )
        points.append((x, y, z))
    if len(points) != count:
        raise CampaignConfigError(
            f"the acoustic observer file {where} states {count} observer(s) on its first line "
            f"and holds {len(points)}; the solver reads the count and then that many lines."
        )
    return tuple(points)


def resolve_observers_file(
    inputs_dir: str | Path, variables: Mapping[str, object], *, pol: str, legacy: bool
) -> str | None:
    """Resolve a row's ``ACOUSTIC_OBSERVERS_FILE`` to its file's absolute path, when it binds.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace's input library, whose ``acoustics/`` folder holds the file.
    variables : mapping
        The row's ``VAR_NAMES_VALUES`` cell.
    pol : str
        The row's POL, for the message.
    legacy : bool
        Whether the row is ``LEGACY``, whose recipe reads its own keys: refused.

    Returns
    -------
    str or None
        The absolute path of ``inputs/acoustics/<stem>.csv``; None for a row
        stating no file.

    Raises
    ------
    InputArtifactError
        The key on a ``LEGACY`` row; no such file; a file not in its form.
    """
    stem = str(variables.get(ACOUSTIC_OBSERVERS_FILE_VARIABLE) or "").strip()
    if not stem:
        return None
    if legacy:
        raise InputArtifactError(
            f"matrix row POL {pol} writes LEGACY and states {ACOUSTIC_OBSERVERS_FILE_VARIABLE}: "
            f"{stem}. The acoustic observers are emitted by an unsteady run type, and a LEGACY "
            "row's script is its own recipe's; name a run type in the WORKFLOW column, or "
            "drop the key.",
            kind="acoustics",
            artifact_id=stem,
        )
    folder = Path(inputs_dir) / ACOUSTICS_DIR
    file = folder / f"{stem}.csv"
    if not file.is_file():
        held = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
        raise InputArtifactError(
            f"matrix row POL {pol}: {ACOUSTIC_OBSERVERS_FILE_VARIABLE} names {stem!r}, and "
            f"{folder} holds no {stem}.csv"
            + (f"; it holds {', '.join(held)}" if held else ", or holds nothing")
            + f". An acoustic observer file lives in the workspace's inputs/{ACOUSTICS_DIR}/ "
            "folder, and the cell names it by its stem, without the extension.",
            kind="acoustics",
            artifact_id=stem,
        )
    try:
        read_observers_file(file)
    except CampaignConfigError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: {ACOUSTIC_OBSERVERS_FILE_VARIABLE} names {stem!r}, and {error}",
            kind="acoustics",
            artifact_id=stem,
        ) from None
    return str(file.resolve())


def acoustic_section_leftovers(work_dir: Path, sim_dir: Path) -> str | None:
    """Return the refusal of a point whose section folder already holds a file, or None.

    0.32.0 (E2, FR-268). The section's files are listed after the run from the
    folder the solver writes into, so a file already there before the solver
    starts (an aborted run's, a hand copy) would be listed and hashed as this
    run's evidence, which is the defect a declared output is refused for when
    it exists before its run (PYFS-006). The run's own note is not a leftover:
    the run writes it before this is asked.

    Parameters
    ----------
    work_dir : Path
        The folder the point runs in, its datapoint folder.
    sim_dir : Path
        The simulation folder, for the names the sentence gives.

    Returns
    -------
    str or None
        The sentence of the refusal, naming each leftover; None where no section
        folder of the point holds a file other than the note.
    """
    where = Path(work_dir)
    leftovers = sorted(
        path.relative_to(sim_dir).as_posix()
        for section in where.glob(f"*{ACOUSTIC_SECTION_SUFFIX}")
        if section.is_dir()
        for path in section.rglob("*")
        if path.is_file() and path.name != ACOUSTIC_SECTION_NOTE
    )
    if not leftovers:
        return None
    return (
        f"acoustic section file(s) {', '.join(leftovers)} already exist in "
        f"{where.relative_to(sim_dir).as_posix()}/, the folder this point runs in, before "
        "it ran. The collect lists every file of a section folder after the run, and it "
        "cannot tell a file this solver wrote from one that was already there. Redo the "
        "point with pyfs-matrix run --force-rerun <point>, which archives what is there "
        "first, or remove the leftover, then re-run."
    )


def acoustic_section_outputs(sim_dir: Path, collected: Sequence[str]) -> list[str]:
    """Return the collected outputs with every file of the point's acoustic sections added.

    0.32.0 (E2, FR-268). A section writes one VTK file per sample of the observer
    time window into ``<point>_acoustic_section/``, a folder in the point's own
    datapoint folder, and how many files that is the solver decides, so they
    are not declared before the run: they are listed here, after the declared
    outputs are collected, from the datapoint folders those outputs sit in,
    each file but the note the run itself wrote to create the folder, sorted.
    The caller hashes the list, so each file is named in the record and bound
    to its bytes like any declared output.

    Parameters
    ----------
    sim_dir : Path
        The simulation folder the names are relative to.
    collected : sequence of str
        The collected outputs, ``datapoints/DP-<point>/<name>``.

    Returns
    -------
    list of str
        ``collected``, then each section file not already in it; unchanged
        where no section wrote.
    """
    listed = list(collected)
    folders = sorted({PurePosixPath(str(name)).parent for name in collected})
    for folder in folders:
        where = Path(sim_dir) / folder
        if not where.is_dir():
            continue
        for section in sorted(where.glob(f"*{ACOUSTIC_SECTION_SUFFIX}")):
            if not section.is_dir():
                continue
            for path in sorted(section.rglob("*")):
                if not path.is_file() or path.name == ACOUSTIC_SECTION_NOTE:
                    continue
                name = (folder / section.name / path.relative_to(section).as_posix()).as_posix()
                if name not in listed:
                    listed.append(name)
    return listed
