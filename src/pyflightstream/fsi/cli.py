"""``pyfs-fsi`` console entry point: the FSI coupling executable.

Pipeline role: FlightStream's Aeroelastic Coupling Toolbox calls an
external executable bare, once per time step, in the directory set by
``SET_AEROELASTIC_WORKING_DIRECTORY`` (SRC-003 pp.375-376; evidence
reports/RPT-005). This module is that executable, with two modes
dispatched on the run folder's content:

* Coupled mode (WP7): a ``config.json`` in the working directory makes
  every call run :func:`pyflightstream.fsi.driver.coupling_step`, the
  complete four-phase machine of WP6. The loads and displacement
  files of every call are archived under ``fsi_archive/`` so a run is
  replayable offline afterwards.
* Dummy mode (WP1, kept as the fallback): with no ``config.json``,
  write zero displacements so the blade stays rigid and archive every
  interface file FlightStream produces; this is how the dry-run
  fixtures were collected.

Nothing printed to stdout is visible from inside the solver, so both
modes log to files and any coupled-mode failure lands with its
traceback in ``pyfs_fsi_error.log`` instead of a silent nonzero exit.
"""

import argparse
import datetime
import json
import shutil
import sys
import traceback
from pathlib import Path

COUPLED_CONFIG = "config.json"

DUMMY_CONFIG = "pyfs_fsi_dummy.json"
STATE_FILE = "pyfs_fsi_dummy_state.json"
DISPLACEMENT_FILE = "FSIDisp.txt"
CALL_LOG = "pyfs_fsi_calls.log"
ERROR_LOG = "pyfs_fsi_error.log"
ARCHIVE_DIR = "fsi_archive"
# Interface files worth archiving on every call. The exact export set
# and cadence are WP1 open questions; the directory listing recorded in
# every archive folder catches anything not matched here.
ARCHIVE_PATTERNS = ("FS_*.txt", "FSLoad*", "FSI_output.txt", "FSIDisp.txt", "*.sldl")


def init_dummy(directory: Path, node_count: int) -> None:
    """Write the dummy configuration into the future run directory.

    Parameters
    ----------
    directory : Path
        Directory FlightStream will run the executable in (the
        simulation folder of the dry run).
    node_count : int
        Number of structural nodes of the imported node list; the
        dummy writes one zero translation per node, in list order.
    """
    directory.mkdir(parents=True, exist_ok=True)
    config = {"node_count": node_count}
    (directory / DUMMY_CONFIG).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"dummy config written: {directory / DUMMY_CONFIG} (node_count {node_count})")


def coupled_step(cwd: Path, received_argv: tuple[str, ...] = ()) -> int:
    """Execute one real coupling call in ``cwd`` (WP7 wiring).

    Runs :func:`pyflightstream.fsi.driver.coupling_step`, archives the
    call's loads and displacement files for offline replay, and logs
    the outcome. Any failure writes its traceback to the error log
    and returns a nonzero exit code, which aborts the FlightStream
    coupling instead of silently continuing rigid.
    """
    stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
    argv_note = f"argv {list(received_argv)}" if received_argv else "argv none"
    # PyNite lives behind the optional [fsi] extra; import at call time
    # so the dummy mode keeps working without it.
    from pyflightstream.fsi import driver

    try:
        result = driver.coupling_step(cwd)
    except Exception:
        with (cwd / ERROR_LOG).open("a", encoding="utf-8") as log:
            log.write(f"{stamp} coupled step failed in {cwd} ({argv_note})\n")
            log.write(traceback.format_exc() + "\n")
        return 1
    archive = cwd / ARCHIVE_DIR / f"call_{result.call:04d}"
    archive.mkdir(parents=True, exist_ok=True)
    for name in (driver.LOADS_FILE, driver.DISPLACEMENT_FILE):
        source = cwd / name
        if source.is_file():
            shutil.copy2(source, archive / name)
    with (cwd / CALL_LOG).open("a", encoding="utf-8") as log:
        log.write(
            f"{stamp} coupled call {result.call} (step {result.step}, phase "
            f"{result.phase}, cwd {cwd}, {argv_note}): FSIDisp written\n"
        )
    return 0


def dummy_step(cwd: Path, received_argv: tuple[str, ...] = ()) -> int:
    """Execute one dummy coupling call in ``cwd``.

    Archives the visible interface files, writes zero displacements,
    and appends to the call log. The working directory and any
    received arguments are recorded on every call: both are open
    questions of the WP1 dry run. Returns a process exit code.
    """
    stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
    argv_note = f"argv {list(received_argv)}" if received_argv else "argv none"
    config_path = cwd / DUMMY_CONFIG
    if not config_path.is_file():
        listing = "\n".join(sorted(p.name for p in cwd.iterdir()))
        (cwd / ERROR_LOG).write_text(
            f"{stamp} pyfs-fsi called without {DUMMY_CONFIG} in {cwd} ({argv_note})\n"
            f"directory listing:\n{listing}\n",
            encoding="utf-8",
        )
        return 1
    node_count = json.loads(config_path.read_text(encoding="utf-8"))["node_count"]

    state_path = cwd / STATE_FILE
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {"calls": 0}
    call_number = state["calls"] + 1

    archive = cwd / ARCHIVE_DIR / f"call_{call_number:04d}"
    archive.mkdir(parents=True, exist_ok=True)
    copied = []
    for pattern in ARCHIVE_PATTERNS:
        for path in sorted(cwd.glob(pattern)):
            shutil.copy2(path, archive / path.name)
            copied.append(path.name)
    listing_lines = [
        f"{p.name}\t{p.stat().st_size}\t{datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')}"
        for p in sorted(cwd.iterdir())
        if p.is_file()
    ]
    (archive / "directory_listing.txt").write_text(
        "\n".join(listing_lines) + "\n", encoding="utf-8"
    )

    # Comma separated per the FSIDisp.txt format of SRC-003 p.273.
    zero_line = "0.000000000000e+00,0.000000000000e+00,0.000000000000e+00"
    (cwd / DISPLACEMENT_FILE).write_text(
        "\n".join([zero_line] * node_count) + "\n", encoding="utf-8"
    )

    state["calls"] = call_number
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state) + "\n", encoding="utf-8")
    tmp.replace(state_path)

    with (cwd / CALL_LOG).open("a", encoding="utf-8") as log:
        log.write(
            f"{stamp} call {call_number} (cwd {cwd}, {argv_note}): wrote "
            f"{node_count} zero displacement vectors; archived {copied or 'nothing'}\n"
        )
    return 0


def _step(cwd: Path, received_argv: tuple[str, ...] = ()) -> int:
    """Dispatch one coupling call: coupled if configured, dummy otherwise."""
    if (cwd / COUPLED_CONFIG).is_file():
        return coupled_step(cwd, received_argv=received_argv)
    return dummy_step(cwd, received_argv=received_argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ``pyfs-fsi`` console script."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        # FlightStream calls the executable bare: one coupling step,
        # coupled when the working directory carries a config.json.
        return _step(Path.cwd())
    if argv[0] not in ("init-dummy", "step", "-h", "--help"):
        # Unknown call convention: the Toolbox may pass arguments of its
        # own. Execute the coupling step anyway and record the arguments
        # as evidence instead of dying on argparse.
        return _step(Path.cwd(), received_argv=tuple(argv))
    parser = argparse.ArgumentParser(
        prog="pyfs-fsi",
        description=(
            "FSI coupling executable for the FlightStream Aeroelastic Toolbox. "
            "Called with no arguments it executes one coupling step in the "
            "current directory (dummy mode until the coupled driver lands)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init-dummy", help="write the dummy configuration into a run directory")
    p_init.add_argument("--node-count", type=int, required=True)
    p_init.add_argument("--dir", type=Path, default=Path.cwd())
    p_step = sub.add_parser("step", help="execute one coupling step explicitly")
    p_step.add_argument("--dir", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if args.command == "init-dummy":
        if args.node_count < 1:
            parser.error("a structural node list has at least one node")
        init_dummy(args.dir, args.node_count)
        return 0
    return _step(args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
