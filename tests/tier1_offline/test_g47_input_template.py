"""Tier 1, 0.28.0 item G47: ``inputs/input_template.md``, a template of every input file.

THE ITEM: a Markdown page at the root of a workspace's ``inputs/`` folder that
explains the format of every input file a user writes, the ones in
``profiles/`` included, so a user can write their own. The input glossary,
``inputs/pproc/INPUTS.md``, stays where it is and the template links to it.

WHAT THESE TESTS HOLD, and each holds it against the package rather than
against the generator:

* ``pyfs-workspace init`` writes the page, and a second init leaves it byte
  for byte as it was;
* every example block of the page, written to the path its title names, is
  ACCEPTED BY THE PACKAGE'S OWN READER for that kind of file: the matrix is
  read, bound to the workspace and planned; the setup, the pproc and the
  reference are resolved; the sidecars, the points file, the profiles, the
  free stream, the HPC profile, the build registry and the named points are
  each read by the function the run reads them with;
* every kind of input file is covered, enumerated HERE from the workspace's
  own constants and from what init creates, so a kind the page omits fails;
* every key of the registries the input glossary's test enumerates is either
  stated by an example or named on the page as left out of it, so a key added
  to the code without a place in the template fails;
* a broken example is refused by the same reader, measured beside its
  unbroken control, so the acceptance above is not satisfied by a reader that
  accepts everything.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import SolverSettings
from pyflightstream.cases.matrix import _COLUMNS, read_matrix
from pyflightstream.cases.workflows import (
    FREESTREAM_FORMS,
    _read_custom_freestream,
    _read_probe_profile,
    read_actuator_profile,
    workflow_registry,
)
from pyflightstream.run import PlanStatus, render_descriptor
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import (
    INPUT_KINDS,
    REFERENCE_POINTS_FILE,
    CampaignWorkspace,
    write_input_guides,
)
from pyflightstream.workspace.inputs import (
    EXECUTABLE_ENTRY_KEYS,
    EXECUTABLES_FILE,
    HPC_LOG_KEYS,
    HPC_PROFILE_KEYS,
    INVENTORY_SUFFIX,
    LOCAL_EXECUTABLES_FILE,
    PROVENANCE_SUFFIX,
    PointXyz,
    read_hpc_profile,
    read_inventory,
    read_mesh_import,
    read_raw_mesh_conditions,
    resolve_build,
    resolve_geometry,
    resolve_hpc_profile,
    resolve_pproc,
    resolve_reference,
    resolve_setup,
)
from pyflightstream.workspace.matrix import resolve_matrix
from pyflightstream.workspace.wake_edges import read_trailing_edge_points
from tests.tier1_offline.test_goal031_g08_input_glossary import expected_tables

REPO = Path(__file__).resolve().parents[2]

#: The page's name and place, spelled here rather than imported, so that a
#: tree without the page fails on the page and not on an import.
TEMPLATE = "input_template.md"

#: The generated pages init writes into the library, which are not input
#: files a user writes and so need no template.
GENERATED = {TEMPLATE, "pproc/VARIABLES.md", "pproc/WRITING-EQUATIONS.md", "pproc/INPUTS.md"}

#: The five artifacts the input glossary covers, by the section heading the
#: template gives each; the headings are the glossary's own.
GLOSSARY_ARTIFACTS = ("matrix", "setup", "pproc", "reference", "geometry")

_BLOCK = re.compile(
    r'^```(?P<lang>[\w-]+) title="(?P<path>[^"]+)"\n(?P<body>.*?)^```$',
    re.MULTILINE | re.DOTALL,
)
_LEFT_OUT = re.compile(r"^- \*\*(?P<table>.+?)\*\* \((?P<reason>[^()]+)\): (?P<keys>.+)\.$")


def sections(text: str) -> dict[str, str]:
    """The page's second-level sections, heading to body."""
    found: dict[str, str] = {}
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    for heading, body in zip(parts[1::2], parts[2::2], strict=True):
        assert heading not in found, f"the section {heading!r} is written twice"
        found[heading.strip()] = body
    return found


def examples(text: str) -> list[tuple[str, str, str]]:
    """Every example block of a page: (language, path it is written to, body)."""
    return [(m["lang"], m["path"], m["body"]) for m in _BLOCK.finditer(text)]


def left_out(body: str) -> dict[str, tuple[set[str], bool]]:
    """What a section says its examples leave out: table to (keys, every key)."""
    found: dict[str, tuple[set[str], bool]] = {}
    for line in body.splitlines():
        match = _LEFT_OUT.match(line.strip())
        if not match:
            continue
        table = match["table"]
        every = match["keys"] == "every key"
        keys = set() if every else set(re.findall(r"`([^`]+)`", match["keys"]))
        assert every or keys, f"a left-out line names no key: {line!r}"
        held, whole = found.get(table, (set(), False))
        found[table] = (held | keys, whole or every)
    return found


def init_with_the_examples(root: Path) -> tuple[CampaignWorkspace, str, list[tuple]]:
    """Init a workspace, read its template, write every example where its title says.

    The one thing a user never writes, the geometry file itself, is staged as a
    placeholder under the name each geometry sidecar's ``file`` key gives it.
    """
    workspace = CampaignWorkspace.init(root)
    page = workspace.inputs_dir / TEMPLATE
    assert page.is_file(), f"pyfs-workspace init wrote no inputs/{TEMPLATE}"
    text = page.read_text(encoding="utf-8")
    blocks = examples(text)
    assert blocks, "the template carries no example block with a title"
    for _lang, relative, body in blocks:
        target = workspace.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    for sidecar in workspace.inputs_dir.glob(f"geometries/**/*{INVENTORY_SUFFIX}"):
        geometry = sidecar.parent / tomllib.loads(sidecar.read_text(encoding="utf-8"))["file"]
        geometry.write_bytes(b"a placeholder for the mesh the user stages")
    return workspace, text, blocks


def _matrices(workspace: CampaignWorkspace, blocks) -> list[Path]:
    return [workspace.root / path for _lang, path, _body in blocks if path.endswith(".fs")]


def _read_every_example(workspace: CampaignWorkspace, blocks) -> dict[str, str]:
    """Pass every example through the package's own reader; return path to what read it.

    A file no reader claims is returned unclaimed, and the caller refuses that:
    an example nothing reads is an example nothing checks.
    """
    inputs = workspace.inputs_dir
    read: dict[str, str] = {}

    def claim(path: Path, reader: str) -> None:
        read[path.relative_to(workspace.root).as_posix()] = reader

    # The matrix: read, bound to the library, and planned with no executable.
    cited_profiles: set[str] = set()
    cited_freestreams: set[str] = set()
    for matrix in _matrices(workspace, blocks):
        rows = read_matrix(matrix, active_only=False)
        assert rows, f"{matrix.name} holds no row"
        resolved = resolve_matrix(matrix, workspace, name="campaign", fs_version=None, recipes={})
        assert resolved.campaign.sims, f"{matrix.name} resolves to no case"
        for case in resolved.campaign.sims:
            if case.actuator_profile:
                cited_profiles.add(Path(case.actuator_profile).name)
                read_actuator_profile(case.actuator_profile)
            if case.freestream_profile:
                field = Path(case.freestream_profile)
                cited_freestreams.add(field.name)
                _read_custom_freestream(str(field), FREESTREAM_FORMS[field.suffix.lower()])
            for probes in case.pproc.probes if case.pproc is not None else ():
                if probes.resolved_points_file:
                    cited_profiles.add(Path(probes.resolved_points_file).name)
                    _read_probe_profile(probes.resolved_points_file)
        plan = plan_matrix(
            matrix,
            workspace,
            name="campaign",
            recipes={},
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
        blocked = [f"{p.run_id}: {p.error}" for p in plan.points if p.status != PlanStatus.READY]
        assert plan.points and not blocked, "\n".join(blocked)
        claim(matrix, "read_matrix, resolve_matrix and plan_matrix")
    # The three artifacts a row cites by id.
    for kind, folder, resolve in (
        ("setup", "setups", resolve_setup),
        ("pproc", "pproc", resolve_pproc),
        ("reference", "references", resolve_reference),
    ):
        for path in sorted((inputs / folder).glob("*.toml")):
            resolve(inputs, path.stem)
            claim(path, f"resolve_{kind}")
    # The named points, the build registry and its overlay, the HPC profile.
    points = inputs / REFERENCE_POINTS_FILE
    if points.is_file():
        assert workspace.reference_points(), f"{points.name} declares no point"
        claim(points, "CampaignWorkspace.reference_points")
    registry = inputs / EXECUTABLES_FILE
    for build in tomllib.loads(registry.read_text(encoding="utf-8")):
        resolve_build(inputs, build)
    claim(registry, "resolve_build")
    overlay = inputs / LOCAL_EXECUTABLES_FILE
    if overlay.is_file():
        for build in tomllib.loads(overlay.read_text(encoding="utf-8")):
            assert resolve_build(inputs, build).fs_exe.as_posix() == str(
                tomllib.loads(overlay.read_text(encoding="utf-8"))[build]
            ), f"the overlay's path for {build} is not the one resolve_build returns"
        claim(overlay, "resolve_build")
    for path in sorted((inputs / "hpc").glob("*.toml")):
        profile = read_hpc_profile(path)
        # Every substitution a field writes is one a point supplies: the values
        # the run binds for a point with a build, a processor count and a wall
        # clock, and the build's name on this scheduler.
        point = {
            "sim": "1001",
            "point": "DP-M150RE310AL+000BE+000",
            "fs_build": "26.124",
            "ncpus": 8,
            "walltime": "2h",
            "walltime_s": 7200,
            "walltime_written": "2h",
            "application_id": profile.application_id,
            "script_path": "sims/sim_1001/run.fs",
            "work_dir": "sims/sim_1001",
            "fs_build_alias": profile.builds["26.124"],
        }
        assert render_descriptor(profile, point).strip()
        assert [part.format(descriptor_path="submit.yaml", **point) for part in profile.submit]
        claim(path, "read_hpc_profile and render_descriptor")
    if any((inputs / "hpc").glob("*.toml")):
        assert resolve_hpc_profile(inputs) is not None
    # The geometry library: each sidecar, the points file it cites, the record.
    for sidecar in sorted(inputs.glob(f"geometries/**/*{INVENTORY_SUFFIX}")):
        assert read_inventory(sidecar)
        read_mesh_import(sidecar)
        conditions = read_raw_mesh_conditions(sidecar)
        claim(sidecar, "read_inventory, read_mesh_import and read_raw_mesh_conditions")
        marking = None if conditions is None else conditions.trailing_edges
        if marking is not None and marking.points_file is not None:
            points_file = Path(marking.points_file)
            assert read_trailing_edge_points(points_file).points.size
            claim(points_file, "read_trailing_edge_points")
        stem = sidecar.name.removesuffix(INVENTORY_SUFFIX)
        geometry = tomllib.loads(sidecar.read_text(encoding="utf-8"))["file"]
        # The resolver finds the geometry, never a sidecar or a record beside it.
        assert resolve_geometry(inputs, geometry).name == geometry, stem
    for record in sorted(inputs.glob(f"geometries/**/*{PROVENANCE_SUFFIX}")):
        # The package reads no key of a provenance record; it keeps it beside
        # its geometry and out of what a GEOMETRY cell could name. It must
        # still be the TOML its suffix says.
        tomllib.loads(record.read_text(encoding="utf-8"))
        claim(record, "tomllib (the package keeps it and reads no key)")
    # The profiles and the free streams are read where a row or a pproc cites them.
    for path in sorted((inputs / "profiles").iterdir()):
        assert path.name in cited_profiles, (
            f"profiles/{path.name} is an example no row's PROFILE and no probe entry's "
            "points_file cites, so nothing the package runs reads it"
        )
        claim(path, "read_actuator_profile or the probe survey reader")
    for path in sorted((inputs / "freestreams").iterdir()):
        assert path.name in cited_freestreams, (
            f"freestreams/{path.name} is an example no row's FREESTREAM cites"
        )
        claim(path, "the custom free-stream reader")
    return read


def test_g47_every_example_of_the_template_init_writes_is_accepted_by_its_reader(tmp_path):
    """THE EXIT OF G47: init writes the page, and every example on it is a valid file.

    Each example is written where its title says and handed to the reader the
    run itself uses for that kind; the matrix is planned, which builds every
    point's script, so an example that reads but cannot run is a failure too.
    A second init leaves the page byte for byte as it was.
    """
    workspace, text, blocks = init_with_the_examples(tmp_path / "camp")
    read = _read_every_example(workspace, blocks)
    written = {path for _lang, path, _body in blocks}
    unread = sorted(written - set(read))
    assert not unread, f"examples no reader of the package read: {unread}"
    page = workspace.inputs_dir / TEMPLATE
    before = page.read_bytes()
    CampaignWorkspace.init(workspace.root)
    assert page.read_bytes() == before, "a second init changed the template"
    assert text.startswith("# ")


def test_g47_every_kind_of_input_file_has_an_example(tmp_path):
    """A kind the page omits fails, the kinds read from the workspace and not from the page.

    The library's folders (``INPUT_KINDS``), the files the workspace reads at
    the root of ``inputs/``, the run matrix in the workspace root, and the
    sidecars of a geometry. And what init itself creates is held to the same
    list, so a folder init gains without a template fails here too.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    # Every file init writes, and every folder it leaves empty, spelled with a
    # trailing slash as the locations below spell a folder.
    created = {
        path.relative_to(workspace.inputs_dir).as_posix() + ("" if path.is_file() else "/")
        for path in workspace.inputs_dir.rglob("*")
        if path.is_file() or not any(path.iterdir())
    }
    locations = {f"{kind}/" for kind in INPUT_KINDS} | {
        EXECUTABLES_FILE,
        LOCAL_EXECUTABLES_FILE,
        REFERENCE_POINTS_FILE,
    }
    unexplained = sorted(
        entry
        for entry in created - GENERATED
        if entry not in locations
        and not any(entry.startswith(folder) for folder in locations if folder.endswith("/"))
    )
    assert not unexplained, f"init creates {unexplained}, which no template kind covers"
    text = (workspace.inputs_dir / TEMPLATE).read_text(encoding="utf-8")
    paths = [path for _lang, path, _body in examples(text)]
    missing = sorted(
        location
        for location in locations
        if not any(
            path == f"inputs/{location}" or path.startswith(f"inputs/{location}") for path in paths
        )
    )
    assert not missing, f"the template has no example under inputs/ for {missing}"
    assert any("/" not in path and path.endswith(".fs") for path in paths), (
        "the template has no run matrix in the workspace root"
    )
    for suffix in (INVENTORY_SUFFIX, PROVENANCE_SUFFIX):
        assert any(path.endswith(suffix) for path in paths), f"no geometry {suffix} example"
    # `profiles/` holds two kinds of file, and both are shown: the radial thrust
    # profile a row's PROFILE names by stem, and the survey a probe entry's
    # points_file names by file name.
    blocks = examples(text)
    profiles = {Path(path).name for path in paths if path.startswith("inputs/profiles/")}
    stems = {
        pair.split(":", 1)[1].strip()
        for _lang, path, body in blocks
        if path.endswith(".fs")
        for line in body.splitlines()[1:]
        for pair in re.split(r"\s/\s", line.split("|")[-1])
        if pair.split(":", 1)[0].strip() == "PROFILE"
    }
    surveys = {
        probe["points_file"]
        for _lang, path, body in blocks
        if path.startswith("inputs/pproc/")
        for probe in tomllib.loads(body).get("probes", [])
        if "points_file" in probe
    }
    assert stems & {Path(name).stem for name in profiles}, (
        f"no example of profiles/ is a radial thrust profile a row's PROFILE names: {profiles}"
    )
    assert surveys & profiles, (
        f"no example of profiles/ is a probe survey a pproc cites: {profiles}"
    )
    # A raw mesh's sidecar and a saved simulation's are two shapes; both are shown.
    sidecars = [
        tomllib.loads(body)
        for _lang, path, body in examples(text)
        if path.endswith(INVENTORY_SUFFIX)
    ]
    assert any("import" in data for data in sidecars), "no raw mesh sidecar example"
    assert any("import" not in data for data in sidecars), "no saved simulation sidecar"


def _shown(artifact: str, heading: str, data: list[dict], matrices: list[str]) -> set[str]:
    """The keys the examples state for one table of the glossary, read off the parsed files."""

    def union(entries) -> set[str]:
        return {key for entry in entries for key in entry}

    def blocks_of(kind) -> list[dict]:
        return [
            value
            for file in data
            for value in file.values()
            if isinstance(value, dict) and kind(value.get("kind"))
        ]

    top = union(data)
    if artifact == "matrix":
        header_and_rows = [
            [cell.strip() for cell in line.split("|")]
            for text in matrices
            for line in text.splitlines()
            if line.strip() and not set(line.strip()) <= {"-"}
        ]
        if heading == "The columns":
            return {cell for rows in header_and_rows[:1] for cell in rows}
        rows = [dict(zip(header_and_rows[0], row, strict=True)) for row in header_and_rows[1:]]
        if heading == "The `FLIGHT_CONDITION` cell":
            return {
                pair.split(":")[0].strip()
                for row in rows
                for pair in row["FLIGHT_CONDITION"].split(",")
            }
        return {
            pair.split(":")[0].strip()
            for row in rows
            for pair in re.split(r"\s/\s", row["VAR_NAMES_VALUES"])
            if ":" in pair
        }
    if heading in (
        "Solver settings",
        "The solver's own names, read as aliases",
        "Recorded, and emitting nothing",
        "Tables and reserved keys",
        "The tables and top-level keys",
    ):
        return top
    if artifact == "reference" and heading == "Top-level keys and tables":
        return {
            key
            for file in data
            for key, value in file.items()
            if not (isinstance(value, dict) and "kind" in value)
        }
    if artifact == "geometry" and heading == "Top-level keys and tables":
        return top
    rotor_blocks = blocks_of(lambda kind: kind == "rotor")
    tables = {
        "`[flight_condition]`": [f.get("flight_condition", {}) for f in data],
        "`[[raw]]`": [e for f in data for e in f.get("raw", [])],
        "`[[flags]]`": [e for f in data for e in f.get("flags", [])],
        "`[phase_locked]`": [f.get("phase_locked", {}) for f in data],
        "`[equations.<NAME>]`": [e for f in data for e in f.get("equations", {}).values()],
        "`[exports]`": [f.get("exports", {}) for f in data],
        "`[time_averaging]`": [f.get("time_averaging", {}) for f in data],
        "`[sections]`": [f.get("sections", {}) for f in data],
        "`[[sections.distributions]]`": [
            e for f in data for e in f.get("sections", {}).get("distributions", [])
        ],
        "`[volume_section]`": [f.get("volume_section", {}) for f in data],
        "`[plots]`": [f.get("plots", {}) for f in data],
        "`[[plots.groups]]`": [e for f in data for e in f.get("plots", {}).get("groups", [])],
        "`[[probes]]`": [e for f in data for e in f.get("probes", [])],
        "`[[probes.lines]]`": [
            e for f in data for p in f.get("probes", []) for e in p.get("lines", [])
        ],
        "`[[probes.rectangles]]`": [
            e for f in data for p in f.get("probes", []) for e in p.get("rectangles", [])
        ],
        "`[[probes.circles]]`": [
            e for f in data for p in f.get("probes", []) for e in p.get("circles", [])
        ],
        "`[products]`": [f.get("products", {}) for f in data],
        "`[moment_point]`": [f.get("moment_point", {}) for f in data],
        "`[body_axes]`": [f.get("body_axes", {}) for f in data],
        "`[rotor]`": [f.get("rotor", {}) for f in data],
        "`[rotor.position]`": [f.get("rotor", {}).get("position", {}) for f in data],
        "`[[frames]]`": [e for f in data for e in f.get("frames", [])],
        '`[<NAME>]` with `kind = "rotor"`': rotor_blocks,
        "`[<NAME>.blade1]`": [b.get("blade1", {}) for b in rotor_blocks],
        '`[<NAME>]` with `kind = "actuator"`': blocks_of(lambda kind: kind == "actuator"),
        "`[<NAME>]` with any other `kind`": blocks_of(
            lambda kind: kind not in (None, "rotor", "actuator")
        ),
        "`[import]`": [f.get("import", {}) for f in data],
        "`[[import.operations]]`": [
            e for f in data for e in f.get("import", {}).get("operations", [])
        ],
        "`[trailing_edges]`": [f.get("trailing_edges", {}) for f in data],
        "`detect = { ... }` of `[trailing_edges]`": [
            f["trailing_edges"]["detect"]
            for f in data
            if isinstance(f.get("trailing_edges", {}).get("detect"), dict)
        ],
        "`[wake_termination]`": [f.get("wake_termination", {}) for f in data],
        "`[base_regions]`": [f.get("base_regions", {}) for f in data],
    }
    assert heading in tables, f"the test does not know where {artifact} / {heading} is written"
    return union(tables[heading])


def test_g47_every_registered_key_is_in_an_example_or_named_as_left_out(tmp_path):
    """A key added to the code without a place in the template fails here.

    The keys are the input glossary test's own enumeration of the registries
    (never the template's); each must be stated by an example of its artifact
    or named, with a reason, in that section's list of what the examples leave
    out. A key named as left out that the example also states, or that no
    registry holds, fails too.
    """
    import pyflightstream.post.guides as guides

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    text = (workspace.inputs_dir / TEMPLATE).read_text(encoding="utf-8")
    found = sections(text)
    problems: list[str] = []
    expected = expected_tables()
    for artifact in GLOSSARY_ARTIFACTS:
        heading = guides.ARTIFACT_HEADINGS[artifact]
        assert heading in found, f"no section headed {heading!r}"
        body = found[heading]
        bodies = [(lang, body_text) for lang, _path, body_text in examples(body)]
        data = [tomllib.loads(b) for lang, b in bodies if lang == "toml"]
        matrices = [b for lang, b in bodies if lang != "toml"] if artifact == "matrix" else []
        declared = left_out(body)
        tables = {h: keys for (a, h), keys in expected.items() if a == artifact}
        stale_tables = sorted(set(declared) - set(tables))
        if stale_tables:
            problems.append(f"{artifact}: left-out lines name no table of it: {stale_tables}")
        for table, keys in tables.items():
            shown = _shown(artifact, table, data, matrices) & keys
            named, every = declared.get(table, (set(), False))
            named = keys if every else named
            if missing := sorted(keys - shown - named):
                problems.append(
                    f"{artifact} / {table}: {missing} neither in an example nor named as "
                    "left out; state it in the example, or add it to the template's "
                    "left-out list for this table with the reason"
                )
            if not every and (both := sorted(shown & named)):
                problems.append(f"{artifact} / {table}: {both} is shown AND named as left out")
            if stale := sorted(named - keys):
                problems.append(
                    f"{artifact} / {table}: named as left out, held by no registry: {stale}"
                )
    assert not problems, "\n".join(problems)
    # The files outside the glossary state every key their readers read.
    parsed = {path: tomllib.loads(body) for lang, path, body in examples(text) if lang == "toml"}
    hpc = [data for path, data in parsed.items() if path.startswith("inputs/hpc/")]
    assert hpc and set().union(*hpc) == HPC_PROFILE_KEYS, set().union(*hpc) ^ HPC_PROFILE_KEYS
    assert {key for data in hpc for key in data["log"]} == HPC_LOG_KEYS
    entries = [
        entry
        for path, data in parsed.items()
        if path in (f"inputs/{EXECUTABLES_FILE}", f"inputs/{LOCAL_EXECUTABLES_FILE}")
        for entry in data.values()
    ]
    assert {key for entry in entries if isinstance(entry, dict) for key in entry} == set(
        EXECUTABLE_ENTRY_KEYS
    )
    assert any(isinstance(entry, str) for entry in entries), "the bare-path entry is not shown"
    named_points = parsed[f"inputs/{REFERENCE_POINTS_FILE}"]
    assert {key for point in named_points.values() for key in point} == set(PointXyz.model_fields)


def test_g47_the_setup_example_states_the_far_field_layers():
    """Every setup a user starts from states the far-field layers, and at five."""
    import pyflightstream.post.guides as guides

    text = guides.input_template_markdown()
    setups = [
        tomllib.loads(body)
        for _lang, path, body in examples(text)
        if path.startswith("inputs/setups/")
    ]
    assert setups and all(data.get("farfield_layers") == 5 for data in setups)
    assert "farfield_layers" in SolverSettings.model_fields


#: How each example is broken: its title, the text replaced and what replaces
#: it. Each is a misspelled key, or a line out of the file's form, that the
#: reader of that kind must refuse.
BREAKS: dict[str, tuple[str, str]] = {
    "campaign.fs": ("| FLIGHT_CONDITION ", "| FLIGHT_CONDITIONS "),
    "inputs/setups/s001.toml": ("\niterations =", "\niteratoins ="),
    "inputs/pproc/p001.toml": ("\nblade_pattern =", "\nblade_patern ="),
    "inputs/references/r001.toml": ("\narea_m2 =", "\narea_m3 ="),
    f"inputs/{REFERENCE_POINTS_FILE}": ("\nx_m =", "\nx_mm ="),
    "inputs/geometries/aircraft/aircraft.boundaries.toml": ("\nboundaries =", "\nboundary ="),
    "inputs/geometries/wing_raw/wing_raw.boundaries.toml": ("\ntolerance =", "\ntolerence ="),
    "inputs/geometries/wing_raw/wing_raw.te.txt": ("METER\n", ""),
    "inputs/profiles/prop_thrust.txt": ("", "r_R,F\n"),
    "inputs/profiles/wake_survey.csv": ("", "9\n"),
    "inputs/freestreams/gust.txt": ("", "3 3\n"),
    "inputs/hpc/h001.toml": ("\napplication_id =", "\naplication_id ="),
    f"inputs/{EXECUTABLES_FILE}": ("version =", "verison ="),
    f"inputs/{LOCAL_EXECUTABLES_FILE}": ('"26.124" =', '"26.999" ='),
}


def _break(body: str, old: str, new: str) -> str:
    if old == "":
        return new + body
    assert old in body, f"the break's anchor {old!r} is not in the example"
    return body.replace(old, new, 1)


@pytest.mark.parametrize("title", sorted(BREAKS))
def test_g47_a_broken_example_is_refused_by_the_same_reader(title, tmp_path):
    """The control reads, then the same file with one misspelling is refused.

    Measured in one workspace: the unbroken example passes every reader first,
    so the refusal is the break's and not the workspace's.
    """
    workspace, _text, blocks = init_with_the_examples(tmp_path / "camp")
    _read_every_example(workspace, blocks)
    body = {path: text for _lang, path, text in blocks}[title]
    old, new = BREAKS[title]
    broken = _break(body, old, new)
    assert broken != body, "the break changed nothing, so it proves nothing"
    (workspace.root / title).write_text(broken, encoding="utf-8")
    with pytest.raises(PyflightstreamError):
        _read_every_example(workspace, blocks)


def test_g47_every_example_that_can_be_broken_is(tmp_path):
    """No example escapes the refusal test but the one the package reads no key of."""
    import pyflightstream.post.guides as guides

    titles = {path for _lang, path, _body in examples(guides.input_template_markdown())}
    unbroken = sorted(
        title for title in titles - set(BREAKS) if not title.endswith(PROVENANCE_SUFFIX)
    )
    assert not unbroken, f"examples with no break in BREAKS: {unbroken}"


def test_g47_the_plan_and_the_post_write_the_page_too(tmp_path):
    """The page reaches a workspace made before it existed, as the glossary does."""
    from pyflightstream.post import _the_guides_stage

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    page = workspace.inputs_dir / TEMPLATE
    page.unlink()
    assert write_input_guides(workspace.inputs_dir) == [page]
    assert write_input_guides(workspace.inputs_dir) == []
    page.write_text("stale\n", encoding="utf-8")

    class Workspace:
        inputs_dir = workspace.inputs_dir

    assert _the_guides_stage(Workspace()) == []
    import pyflightstream.post.guides as guides

    assert page.read_text(encoding="utf-8") == guides.input_template_markdown()


def _declared_site() -> str:
    """The documentation site the project declares, read where it is declared."""
    urls = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]
    return urls["Documentation"].rstrip("/") + "/"


def test_g47_the_page_links_the_glossary_and_real_pages_and_names_no_machine_path():
    """Each section links the glossary and a page of docs/, at the site the project declares."""
    import pyflightstream.post.guides as guides

    text = guides.input_template_markdown()
    assert text.startswith("# ")
    assert "GENERATED FROM THE CODE" in text
    site = _declared_site()
    for heading, body in sections(text).items():
        assert "pproc/INPUTS.md" in body, f"the section {heading!r} does not link INPUTS.md"
        assert site in body, f"the section {heading!r} links no page of the documentation site"
    linked = set(re.findall(re.escape(site) + r"([a-z0-9-]+)/", text))
    assert linked, "the page links no documentation page"
    missing = sorted(page for page in linked if not (REPO / "docs" / f"{page}.md").is_file())
    assert not missing, f"linked pages docs/ does not hold: {missing}"
    # A drive letter is allowed only in the placeholder the build registry shows.
    paths = re.findall(r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"']*", text)
    assert all(path.startswith("C:/path/to/") for path in paths), paths


def test_g47_without_the_metadata_a_page_is_named_by_its_file(monkeypatch):
    """The source tree imported with nothing installed names each page by its file."""
    import pyflightstream.post.guides as guides

    def not_installed(_name):
        raise guides.PackageNotFoundError(_name)

    monkeypatch.setattr(guides, "distribution_metadata", not_installed)
    guides._documentation_site.cache_clear()
    try:
        text = guides.input_template_markdown()
    finally:
        guides._documentation_site.cache_clear()
    assert _declared_site() not in text
    named = set(re.findall(r"\(`docs/([a-z0-9-]+)\.md`\)", text))
    assert named and all((REPO / "docs" / f"{page}.md").is_file() for page in named), named


def test_g47_the_docs_and_the_changelog_name_the_page():
    """Where INPUTS.md is documented, the template is named beside it."""
    workflows = (REPO / "docs" / "workspace-and-workflows.md").read_text(encoding="utf-8")
    migrating = (REPO / "docs" / "migrating-to-0.28.0.md").read_text(encoding="utf-8")
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    # The section that describes 0.28.0: [Unreleased] until the release commit
    # dates it, [0.28.0] after.
    heading = "\n## [0.28.0]" if "\n## [0.28.0]" in changelog else "\n## [Unreleased]"
    release = changelog.split(heading, 1)[1].split("\n## [", 1)[0]
    assert "inputs/input_template.md" in workflows
    assert re.search(r"^## \d+\. A template of every input file \(G47\)$", migrating, re.M)
    assert "input_template.md" in release.split("### Added", 1)[1].split("\n### ", 1)[0]


def test_g47_the_columns_of_the_matrix_example_are_the_layout():
    """The matrix example's header is the verified layout, in order."""
    import pyflightstream.post.guides as guides

    matrices = [
        body
        for _lang, path, body in examples(guides.input_template_markdown())
        if path.endswith(".fs")
    ]
    header = next(line for line in matrices[0].splitlines() if line.strip())
    assert tuple(cell.strip() for cell in header.split("|")) == _COLUMNS


# --- three readers the examples proved wrong, each held on its own ------------


def _library(tmp_path: Path) -> Path:
    inputs = tmp_path / "inputs"
    for folder in ("references", "pproc"):
        (inputs / folder).mkdir(parents=True)
    return inputs


def test_g47_a_recorded_rotor_stating_its_hub_radius_is_read(tmp_path):
    """``[rotor]``'s own ``hub_radius_m`` is not a disc that forgot its kind.

    The guard for a block with no ``kind`` read ``hub_radius_m`` as a disc's key
    and refused the documented ``[rotor]`` table. The guard itself is kept: a
    top-level table of the user's own naming with a disc's keys and no kind is
    still refused, naming the kind to add.
    """
    inputs = _library(tmp_path)
    head = "area_m2 = 1.0\nchord_m = 1.0\nspan_m = 1.0\nrotor_diameter_m = 1.2\n"
    rotor = "\n[rotor]\nradius_m = 0.6\nhub_radius_m = 0.1\nn_blades = 3\n"
    (inputs / "references" / "r001.toml").write_text(head + rotor, encoding="utf-8")
    assert resolve_reference(inputs, "r001").rotor.hub_radius_m == 0.1
    disc = '\n[DISC]\nframe = "MRP"\naxis = "X"\ntip_radius_m = 0.5\nhub_radius_m = 0.1\n'
    (inputs / "references" / "r002.toml").write_text(head + disc, encoding="utf-8")
    with pytest.raises(PyflightstreamError, match='add kind = "actuator"'):
        resolve_reference(inputs, "r002")


def test_g47_a_pproc_stating_vtk_variables_is_read(tmp_path):
    """The top-level ``vtk_variables`` list is the model's, not a group of the old shape.

    A top-level list the model does not define is still a groups file of the
    shape before 0.11.0, and still refused naming the migration.
    """
    inputs = _library(tmp_path)
    pproc = inputs / "pproc"
    (pproc / "p001.toml").write_text('vtk_variables = ["CP_FREESTREAM", "VX"]\n', encoding="utf-8")
    assert resolve_pproc(inputs, "p001").vtk_variables == ["CP_FREESTREAM", "VX"]
    (pproc / "p002.toml").write_text('wing = ["Wing"]\n', encoding="utf-8")
    with pytest.raises(PyflightstreamError, match="migrate_groups_to_pproc"):
        resolve_pproc(inputs, "p002")


def test_g47_a_steady_rectangle_or_circle_emits_volume_probe_points(tmp_path):
    """A steady row's drawn plane reaches the script as ``NEW_PROBE_POINT VOLUME``.

    The command's ``type`` is required on every build; without it no steady
    row drawing a rectangle or a circle built, on any build.
    """
    from pyflightstream.cases import PprocSpec
    from pyflightstream.versions import known_versions
    from tests.tier1_offline.test_workflows import (
        _wb_geometry,
        _with_pproc,
        rendered,
        steady_case,
    )

    pproc = PprocSpec.model_validate(
        {
            "probes": [
                {
                    "frame": "MRP",
                    "parameters": ["VX"],
                    "rectangles": [
                        {
                            "origin": [1.0, 0.0, 0.0],
                            "along_u": [1.0, 1.0, 0.0],
                            "along_v": [1.0, 0.0, 1.0],
                            "points_u": 2,
                            "points_v": 3,
                        }
                    ],
                    "circles": [
                        {
                            "center": [2.0, 0.0, 0.0],
                            "normal": [1.0, 0.0, 0.0],
                            "radius": 0.5,
                            "points_radial": 2,
                            "points_azimuth": 4,
                        }
                    ],
                }
            ]
        }
    )
    case = _with_pproc(steady_case(), _wb_geometry(tmp_path), pproc=pproc)
    builds = [v.canonical for v in known_versions() if v.canonical in ("26.120", "26.124")]
    assert builds, "neither build the assertion names is registered"
    for build in builds:
        lines = [line for line in rendered(case, build).splitlines() if "NEW_PROBE_POINT" in line]
        # Six grid points of the rectangle; the circle's centre once and one
        # ring of four.
        assert len(lines) == 6 + 1 + 4, (build, lines)
        assert all(line.startswith("NEW_PROBE_POINT VOLUME ") for line in lines), lines
