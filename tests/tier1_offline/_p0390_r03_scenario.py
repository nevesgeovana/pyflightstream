"""The synthetic workspace of P0390-R03 (the workspace settings files), and its R10 scenario.

Data and functions only, no test: ``test_p0390_r03.py`` builds every workspace
through :func:`make_workspace`, and the R10 byte comparison runs
:func:`r10_outputs` on this tree and compares it with what the same function
gave on v0.38.0, committed under ``fixtures/p0390_r03_v0380/``.

The module imports only what v0.38.0 already had, so the fixtures are captured
by running it as a program under an installation of v0.38.0, from the
repository root, which leaves ``src/`` off the import path::

    <python of a v0.38.0 install> -m tests.tier1_offline._p0390_r03_scenario <folder>

It writes each output into ``<folder>`` under its name and prints the version
it ran on (``fixtures/p0390_r03_v0380/README.md`` records the capture).

A stub process stands in for FlightStream: it prints build #7000002 to the
identity pre-flight, where 26.120 is registered as build #7012026, and writes
the committed synthetic loads table wherever a point's script exports one.
"""

from __future__ import annotations

import contextlib
import csv
import getpass
import hashlib
import io
import json
import random
import re
import sys
import tempfile
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path

import pyflightstream
import pyflightstream._cli as _cli
import pyflightstream.run.matrix as _run_matrix
from pyflightstream.run import LocalExecutor
from pyflightstream.run.cli import main as matrix_main
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.costs import select_cost_file
from pyflightstream.workspace.hpc import select_hpc_profile

FIXTURES = Path(__file__).parent / "fixtures"
LOADS = FIXTURES / "loads_steady_26.120.txt"
V0380 = FIXTURES / "p0390_r03_v0380"

#: The build the stub reports; 26.120 is registered as build #7012026.
INSTALLED = "7000002"

#: The stub solver: the identity pre-flight reads build #7000002 from the log it
#: asks for; a point's script gets the committed loads table, its angle of attack
#: rewritten to the one the script asked for, and its saved simulation and plots.
STUB = (
    "import pathlib, re, sys\n"
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines()\n"
    "if any('PYFS_PREFLIGHT' in line for line in lines):\n"
    "    for i, line in enumerate(lines):\n"
    "        if line == 'EXPORT_LOG':\n"
    "            pathlib.Path(lines[i + 1]).write_text(\n"
    f"                'Software : Flightstream version 26.1, build #{INSTALLED}' + chr(10))\n"
    "    raise SystemExit(0)\n"
    f"template = pathlib.Path({LOADS.as_posix()!r}).read_text(encoding='utf-8')\n"
    "alpha = None\n"
    "pattern = r'(Angle of attack .Deg.\\s+)[-+0-9.]+'\n"
    "for i, line in enumerate(lines):\n"
    "    if line.startswith('SOLVER_SET_AOA'):\n"
    "        alpha = float(line.split()[1])\n"
    "    elif line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET':\n"
    "        body = template if alpha is None else re.sub("
    "pattern, lambda f: f.group(1) + ('%.3f' % alpha), template)\n"
    "        pathlib.Path(lines[i + 1]).write_text(body, encoding='utf-8')\n"
    "    elif line in ('SAVEAS', 'SAVE_PLOT_TO_FILE'):\n"
    "        pathlib.Path(lines[i + 1]).write_text('STUB', encoding='utf-8')\n"
)


class BuildSolver(LocalExecutor):
    """FlightStream, replaced by one python process reporting build #7000002."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(fs_exe=sys.executable, hidden=True)

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", STUB, str(script_path)]


HEADER = (
    "POL | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION | "
    "SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | "
    "WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n" + "-" * 120 + "\n"
)


def matrix_row(pol: str, build: str = " ") -> str:
    """One steady matrix row, POL ``pol``, naming ``build`` (none when blank)."""
    return (
        f"{pol} | 1 | 1 | Rig | - | STEADY | TASmps:30.0, REmi:1.20, ALPHA:sweep | 0.0 | - | "
        f"r003 | s002 | p001 | - | - | - | - | {build} | steady | VELOCITY: 30.0\n"
    )


def make_workspace(
    tmp_path: Path,
    rows: str = matrix_row("7002"),
    *,
    profiles: bool = False,
    costs: bool = False,
) -> Path:
    """A synthetic campaign workspace: one steady row naming no build, run by the stub."""
    root = CampaignWorkspace.init(tmp_path / "camp").root
    inputs = root / "inputs"
    (inputs / "references" / "r003.toml").write_text(
        "area_m2 = 11.5\nchord_m = 1.5\nspan_m = 8.0\n", encoding="utf-8"
    )
    (inputs / "setups" / "s002.toml").write_text(
        "iterations = 500\nconvergence = 1e-5\n", encoding="utf-8"
    )
    (inputs / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "Wing"\n\n[exports]\ntecplot = false\n'
        "sections = false\nsectional_loads = false\nprobes = false\nplots = false\n"
        "log = false\n",
        encoding="utf-8",
    )
    exe = Path(sys.executable).as_posix()
    with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write(f'"26.120" = "{exe}"\n"26.124" = "{exe}"\n')
    (root / "polars.fs").write_text(HEADER + rows, encoding="utf-8")
    if profiles:
        hpc = inputs / "hpc"
        hpc.mkdir(exist_ok=True)
        for stem in ("h001", "h002"):
            (hpc / f"{stem}.toml").write_text(
                f'application_id = "app-{stem}"\n\n[descriptor]\ntemplate = "d.tmpl"\n\n'
                '[descriptor.fields]\nwalltime = "{walltime}"\n\n'
                '[submit]\ncommand = ["sbatch", "{descriptor}"]\n',
                encoding="utf-8",
            )
    if costs:
        example = Path(__file__).resolve().parents[2] / "examples" / "costs" / "c000.toml"
        (inputs / "costs").mkdir(exist_ok=True)
        for stem in ("c001", "c002"):
            text = example.read_text(encoding="utf-8").replace("example-machine", f"m-{stem}")
            (inputs / "costs" / f"{stem}.toml").write_text(text, encoding="utf-8")
    return root


# --- R10: the scenario run with no settings file -------------------------------------

#: The folders and files of the workspace whose bytes R10 compares: every record,
#: the plan, every emitted script, every solver output and every post product.
COMPARED = ("runs.json", "logs/activity.log", "post/", "sims/")


#: The columns of a CSV product holding a time the run measured, not its content.
TIME_COLUMNS = frozenset(
    {"wall_time_s", "duration_s", "solver_run_time_s", "solver_initialization_s"}
)


def _csv_text(rows: list[list[str]], terminator: str) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator=terminator).writerows(rows)
    return out.getvalue()


def untimed_csv(text: str) -> str:
    """Write ``<S>`` for each value a CSV product holds under a column of :data:`TIME_COLUMNS`.

    The table is read with the csv module and the columns are found by their header
    names; only the cells of those columns are replaced, so a cell of any other
    column keeps its value even where it equals a time of the same row. A product
    the csv module would not write back unchanged is refused, rather than compared
    on rewritten bytes.
    """
    rows = list(csv.reader(io.StringIO(text, newline="")))
    columns = [index for index, name in enumerate(rows[0] if rows else []) if name in TIME_COLUMNS]
    if not columns:
        return text
    terminator = "\r\n" if "\r\n" in text else "\n"
    if _csv_text(rows, terminator) != text:
        raise ValueError("the CSV product does not write back unchanged; its times are kept")
    for row in rows[1:]:
        for index in columns:
            if index < len(row) and row[index] not in ("", "NA"):
                row[index] = "<S>"
    return _csv_text(rows, terminator)


def normal(text: str, root: Path, digests: dict[str, str] | None = None) -> str:
    """Take out of a text only what differs between two runs of one scenario.

    The workspace and temporary paths, the interpreter, times and stamps, process
    ids, the user, and the identity of the installed package (its version, the
    release tag of the superfile report named after it, and the commit a source
    checkout records and a wheel does not): nothing of the content. A sha256
    digest is kept as written unless it is the digest of a file of the workspace,
    which differs only because that file names the workspace's own path; it reads
    ``<SHA:path>``, naming that file, whose own bytes are compared on their own.
    """
    text = text.replace("\r\n", "\n")
    # The stand-in executable's digest names a machine (NFR-31): it is replaced, not kept.
    text = re.sub(
        r'"((?:pyfs:)?(?:fs_exe|executable)_sha256)": "[0-9a-f]{64}"', r'"\1": "<EXE-SHA>"', text
    )
    for digest, name in (digests or {}).items():
        text = text.replace(digest, f"<SHA:{name}>")
    text = text.replace(pyflightstream.__version__, "<V>")
    text = re.sub(r"superfile-\d+(?=\.json)", "superfile-<V>", text)
    text = re.sub(r',\s*"pyfs:(commit|dirty)": ("[^"]*"|true|false|null)', "", text)
    temp = Path(tempfile.gettempdir())
    for value, token in (
        (STUB, "<STUB>"),
        (str(root), "<ROOT>"),
        (sys.executable, "<PYTHON>"),
        # The resolved form first: on Windows the temporary folder may be named by its 8.3
        # short form (a segment such as PROGRA~1) while a child process prints the long one.
        (str(temp.resolve()), "<TEMP>"),
        (str(temp), "<TEMP>"),
    ):
        for form in (json.dumps(value)[1:-1], value, Path(value).as_posix()):
            text = text.replace(form, token)
    text = text.replace("\\\\", "/").replace("\\", "/")
    # An ISO stamp with its offset whole, whichever sign: the two runs of the scenario may be
    # stamped in zones of different sign, and a -hh:mm left behind read as a clock.
    text = re.sub(r"\d{4}-\d\d-\d\dT[0-9:.]+(?:Z|[+-]\d\d:\d\d)?", "<TIME>", text)
    text = re.sub(r"\d{8}T\d{6}Z(-\d+)?", "<STAMP>", text)
    text = re.sub(
        r'"((?:pyfs:)?(?:duration_s|wall_time_s|solver_run_time_s|solver_initialization_s))": '
        r"[0-9.e-]+",
        r'"\1": <S>',
        text,
    )
    text = re.sub(r"\b\d+:\d\d:\d\d\b|\b\d\d:\d\d\b", "<CLOCK>", text)
    text = re.sub(
        r'"(package_version|pyflightstream_version|package_commit|package_dirty)": '
        r'("[^"]*"|null|true|false)',
        r'"\1": "<V>"',
        text,
    )
    text = re.sub(r"pyflightstream \d+\.\d+\.\d+\S*", "pyflightstream <V>", text)
    text = re.sub(r"pyfs-preflight-\w+", "pyfs-preflight-<TMP>", text)
    text = re.sub(r'"(submitted_by|host|hostname|operator|user)": "[^"]*"', r'"\1": "<WHO>"', text)
    text = re.sub(r'"(pid|process_id)": \d+', r'"\1": <PID>', text)
    # Last, once the paths that may hold the user's name are tokens.
    user = re.escape(getpass.getuser())
    return re.sub(rf"(?<![A-Za-z0-9]){user}(?![A-Za-z0-9])", "<WHO>", text)


def _said(argv: list[str]) -> str:
    """Run one ``pyfs-matrix`` command line; return its exit code and both streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = matrix_main(argv)
        except SystemExit as error:
            code = error.code if isinstance(error.code, int) else 1
    return f"exit {int(code or 0)}\n--- stdout\n{out.getvalue()}--- stderr\n{err.getvalue()}"


@contextlib.contextmanager
def _stubbed() -> Iterator[None]:
    """The stub solver, seeded drawings, no selection, no warning filter of the caller."""
    executor, chooser, state = _run_matrix.LocalExecutor, _cli._RNG, random.getstate()
    _run_matrix.LocalExecutor = BuildSolver  # type: ignore[misc]
    _cli._RNG = random.Random(20261010)
    # The run banner draws one of its two aircraft from the module `random`.
    random.seed(20261010)
    select_hpc_profile(None)
    select_cost_file(None)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            yield
    finally:
        _run_matrix.LocalExecutor = executor  # type: ignore[misc]
        _cli._RNG = chooser
        random.setstate(state)
        select_hpc_profile(None)
        select_cost_file(None)


def _compared_files(root: Path) -> list[Path]:
    found = [path for path in sorted(root.rglob("*")) if path.is_file()]
    return [
        path
        for path in found
        if any(
            path.relative_to(root).as_posix() == item
            or path.relative_to(root).as_posix().startswith(item)
            for item in COMPARED
        )
    ]


def r10_outputs(tmp_path: Path) -> dict[str, str]:
    """Run the R10 scenario, with no settings file, and return its normalized outputs.

    ``plan``, ``run``, ``post`` and ``collect`` in a workspace holding neither
    ``pyfs.toml`` nor ``pyfs.local.toml``: each command's console, then every
    file :data:`COMPARED` names, each under ``tree/<its path>``.
    """
    root = make_workspace(tmp_path)
    exe = Path(sys.executable).as_posix()
    (root / "inputs" / "executables.toml").write_text(f'"26.120" = "{exe}"\n', encoding="utf-8")
    outputs: dict[str, str] = {}
    accept = "--accept-unregistered-build"
    with _stubbed():
        for name, argv in (
            ("plan", ["plan", "polars.fs", "--fs-version", "26.120", accept]),
            ("run", ["run", "polars.fs", "--fs-version", "26.120", accept]),
            ("post", ["post", "polars"]),
            ("collect", ["collect"]),
        ):
            outputs[f"{name}.console"] = _said([*argv, "--workspace", str(root)])
    every = [path for path in sorted(root.rglob("*")) if path.is_file()]
    digests = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path.relative_to(root).as_posix()
        for path in every
    }
    shown: Callable[[str], str] = lambda text: normal(text, root, digests)  # noqa: E731
    outputs = {name: shown(text) for name, text in outputs.items()}
    for path in _compared_files(root):
        text = path.read_bytes().decode("utf-8", errors="backslashreplace")
        if path.suffix == ".csv":
            text = untimed_csv(text)
        # A file name holds no `<` or `>`, so a token in a path is written with `_`.
        name = re.sub(r"[<>:]", "_", shown(path.relative_to(root).as_posix()))
        outputs[f"tree/{name}"] = shown(text)
    return outputs


def write_outputs(outputs: dict[str, str], target: Path) -> None:
    """Write each output under ``target`` at its own name, as the fixtures hold them."""
    for name, text in outputs.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as scratch:
        write_outputs(r10_outputs(Path(scratch)), folder)
    print(f"captured with pyflightstream {pyflightstream.__version__} into {folder}")
