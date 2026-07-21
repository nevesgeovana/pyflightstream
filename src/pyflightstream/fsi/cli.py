"""``pyfs-fsi`` console entry point: the FSI coupling executable.

Pipeline role: WP1 of DLV-007. FlightStream's Aeroelastic Toolbox
calls an external executable between coupling iterations
(``SET_MOTION_FSI_EXECUTABLE`` family, SRC-003 pp.335-336). This
module is that executable. Today it implements the dummy mode of the
WP1 dry run: write zero displacements so the blade stays rigid, and
archive every interface file FlightStream produces, so the loads
parser (WP2) is later written against real fixtures instead of
documentation. The coupled driver (WP6) will plug into the same entry
point.

The Toolbox may call the executable with no arguments and an unknown
working directory; both are open questions the dry run closes. The
dummy therefore takes its settings from a ``pyfs_fsi_dummy.json``
placed in the working directory beforehand (``pyfs-fsi init-dummy``),
and logs everything it sees to files, since nothing printed to stdout
is visible from inside the solver.
"""

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

DUMMY_CONFIG = "pyfs_fsi_dummy.json"
STATE_FILE = "pyfs_fsi_dummy_state.json"
DISPLACEMENT_FILE = "FSIDisp.txt"
CALL_LOG = "pyfs_fsi_calls.log"
ERROR_LOG = "pyfs_fsi_error.log"
ARCHIVE_DIR = "fsi_archive"
# Interface files worth archiving on every call. The exact export set
# and cadence are WP1 open questions; the directory listing recorded in
# every archive folder catches anything not matched here.
ARCHIVE_PATTERNS = ("FS_*.txt", "*.sldl", "FSIDisp.txt")


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

    zero_line = "0.000000000000e+00 0.000000000000e+00 0.000000000000e+00"
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


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ``pyfs-fsi`` console script."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        # FlightStream calls the executable bare: one dummy coupling step.
        return dummy_step(Path.cwd())
    if argv[0] not in ("init-dummy", "step", "-h", "--help"):
        # Unknown call convention: the Toolbox may pass arguments of its
        # own (a WP1 open question). Execute the coupling step anyway and
        # record the arguments as evidence instead of dying on argparse.
        return dummy_step(Path.cwd(), received_argv=tuple(argv))
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
    return dummy_step(args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
