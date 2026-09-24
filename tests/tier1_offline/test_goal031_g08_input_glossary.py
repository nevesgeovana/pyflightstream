"""Tier 1, 0.27.0 items G08 and D08: the input glossary, ``INPUTS.md``, is GENERATED.

THE OWNER'S SCOPE OF 2026-09-23, item G08:

    "Um glossario dos parametros de ENTRADA, gerado do codigo (`INPUTS.md` ao
    lado do `VARIABLES.md`)" -- and its exit: "uma chave nova sem linha no
    glossario faz um teste falhar, como no `VARIABLES.md`".

What was there before: the meaning of each input key in prose, spread over the
workflows page, and nothing that failed when a key arrived without it.

WHAT THESE TESTS HOLD, and the direction matters. The expected keys are read
HERE, from the registries the readers and the builders use (the run types' key
tables, the matrix columns, the flight-condition vocabulary, the models' fields,
the preset tables, the export kinds, the sidecar readers' keys), and never from
the generator's own enumeration. The page is then PARSED and every one of those
keys must hold exactly one row with a meaning in it. So a key added to any of
those registries without a line of meaning in the code fails here, and so does
a table or a key the generator stopped writing.

D08 is the citation: the user guide and the workflows page name the page, and
the docs site renders it from the same function.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pyflightstream.post.guides as guides
from pyflightstream.cases import (
    EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
    ActuatorBlock,
    BladeDatum,
    CustomFlag,
    EquationSpec,
    ForcePlotGroup,
    FrameSpec,
    MeshImport,
    MeshOperation,
    PhaseLockedSpec,
    PlotsSpec,
    PprocSpec,
    ProbeCircle,
    ProbeLine,
    ProbeRectangle,
    ProbesSpec,
    ProductsSpec,
    RawCommand,
    RotorBlock,
    SectionDistribution,
    SectionsSpec,
    SolverSettings,
    SurfaceTimeAveragingSpec,
    VolumeSectionSpec,
)
from pyflightstream.cases.matrix import _COLUMNS, ATTITUDE_KEYS, FLIGHT_CONDITION_KEYS
from pyflightstream.cases.workflows import RATE_VARIABLES, RAW_VARIABLE, WORKFLOWS
from pyflightstream.commands import CommandRegistry
from pyflightstream.workspace.flight_condition import PINNED_KEYS
from pyflightstream.workspace.inputs import (
    _DETECT_KEYS,
    _TRAILING_EDGE_KEYS,
    FLAGS_TABLE,
    IMPORT_TABLE,
    RAW_MESH_CONDITION_TABLES,
    RAW_TABLE,
    PointXyz,
    ReferenceArtifact,
    RotorReference,
)
from pyflightstream.workspace.matrix import (
    _FLIGHT_CONDITION_TABLE,
    _PRESET_ALIASES,
    _PRESET_RECORDED_ONLY,
    _PRESET_RECORDED_ONLY_KEY,
)

REPO = Path(__file__).resolve().parents[2]

#: The five artifacts, in the page's order, by the heading the page gives each.
ARTIFACTS = ("matrix", "setup", "pproc", "reference", "geometry")


def _fields(model: type, *, dropping: tuple[str, ...] = ()) -> set[str]:
    """The keys a model table must carry: its fields, less the ones the package sets."""
    package_set = {field for owner, field in guides.PACKAGE_SET_FIELDS if owner == model.__name__}
    return set(model.model_fields) - package_set - set(dropping)


def expected_tables() -> dict[tuple[str, str], set[str]]:
    """Every table the page must carry and every key it must hold, from the registries.

    Keyed by (artifact, heading). READ FROM THE REGISTRIES THE CODE USES, never
    from the generator: that independence is what lets a key the generator
    drops fail here, and not only a key the code adds.
    """
    row_keys = {key for workflow in WORKFLOWS.values() for key in workflow.keys}
    exports = {kind for kind, _, _, _ in EXPORT_KINDS} - set(VOLUME_SECTION_KINDS.values())
    blocks = guides.REFERENCE_BLOCK_HEADINGS
    return {
        # --- the run matrix -------------------------------------------------
        ("matrix", "The columns"): set(_COLUMNS),
        ("matrix", "The `FLIGHT_CONDITION` cell"): set(FLIGHT_CONDITION_KEYS) | set(ATTITUDE_KEYS),
        ("matrix", "The row keys, by run type"): row_keys | {RAW_VARIABLE},
        # --- the setup artifact ---------------------------------------------
        ("setup", "Solver settings"): _fields(SolverSettings),
        ("setup", "The solver's own names, read as aliases"): set(_PRESET_ALIASES),
        ("setup", "Recorded, and emitting nothing"): set(_PRESET_RECORDED_ONLY),
        ("setup", "Tables and reserved keys"): {
            _PRESET_RECORDED_ONLY_KEY,
            _FLIGHT_CONDITION_TABLE,
            "stabilization",
            "stabilization_strength",
            RAW_TABLE,
            FLAGS_TABLE,
        },
        ("setup", "`[flight_condition]`"): set(PINNED_KEYS),
        ("setup", "`[[raw]]`"): _fields(RawCommand),
        ("setup", "`[[flags]]`"): _fields(CustomFlag),
        # --- the post-processing artifact -----------------------------------
        ("pproc", "The tables and top-level keys"): _fields(PprocSpec),
        ("pproc", "`[exports]`"): exports,
        ("pproc", "`[phase_locked]`"): _fields(PhaseLockedSpec),
        ("pproc", "`[equations.<NAME>]`"): _fields(EquationSpec),
        ("pproc", "`[time_averaging]`"): _fields(SurfaceTimeAveragingSpec),
        ("pproc", "`[sections]`"): _fields(SectionsSpec),
        ("pproc", "`[[sections.distributions]]`"): _fields(SectionDistribution),
        ("pproc", "`[volume_section]`"): _fields(VolumeSectionSpec),
        ("pproc", "`[plots]`"): _fields(PlotsSpec),
        ("pproc", "`[[plots.groups]]`"): _fields(ForcePlotGroup),
        ("pproc", "`[[probes]]`"): _fields(ProbesSpec),
        ("pproc", "`[[probes.lines]]`"): _fields(ProbeLine),
        ("pproc", "`[[probes.rectangles]]`"): _fields(ProbeRectangle),
        ("pproc", "`[[probes.circles]]`"): _fields(ProbeCircle),
        ("pproc", "`[products]`"): _fields(ProductsSpec),
        # --- the reference artifact -----------------------------------------
        ("reference", "Top-level keys and tables"): _fields(
            ReferenceArtifact, dropping=tuple(blocks)
        ),
        ("reference", "`[moment_point]`"): _fields(PointXyz),
        ("reference", "`[body_axes]`"): {axis for _rate, axis in RATE_VARIABLES},
        ("reference", "`[rotor]`"): _fields(RotorReference),
        ("reference", "`[rotor.position]`"): _fields(PointXyz),
        ("reference", "`[[frames]]`"): _fields(FrameSpec),
        ("reference", blocks["rotors"]): _fields(RotorBlock),
        ("reference", "`[<NAME>.blade1]`"): _fields(BladeDatum),
        ("reference", blocks["actuators"]): _fields(ActuatorBlock),
        ("reference", blocks["points"]): _fields(PointXyz),
        # --- the geometry sidecar -------------------------------------------
        ("geometry", "Top-level keys and tables"): {
            "boundaries",
            "file",
            IMPORT_TABLE,
            *RAW_MESH_CONDITION_TABLES,
        },
        ("geometry", "`[import]`"): _fields(MeshImport),
        ("geometry", "`[[import.operations]]`"): _fields(MeshOperation),
        ("geometry", "`[trailing_edges]`"): set(_TRAILING_EDGE_KEYS),
        ("geometry", "`detect = { ... }` of `[trailing_edges]`"): set(_DETECT_KEYS),
        ("geometry", "`[wake_termination]`"): {"detect"},
        ("geometry", "`[base_regions]`"): {"detect"},
    }


_ROW = re.compile(r"^\| `(?P<key>[^`]+)` \|(?P<rest>.*)\|$")


def parsed_page(text: str) -> dict[tuple[str, str], list[tuple[str, list[str]]]]:
    """Read the rendered page back: (artifact, heading) to its rows, in order.

    Parsing the MARKDOWN rather than trusting the structure the generator
    returns is the point: the page is what a reader holds, and a row the
    renderer lost is a row the reader never sees.
    """
    artifact_by_heading = {guides.ARTIFACT_HEADINGS[name]: name for name in ARTIFACTS}
    tables: dict[tuple[str, str], list[tuple[str, list[str]]]] = {}
    artifact = heading = None
    for line in text.splitlines():
        if line.startswith("## "):
            artifact = artifact_by_heading.get(line[3:].strip())
            heading = None
        elif line.startswith("### "):
            heading = line[4:].strip()
            assert artifact is not None, f"table {heading!r} sits under no artifact"
            assert (artifact, heading) not in tables, f"the table {heading!r} is written twice"
            tables[(artifact, heading)] = []
        elif artifact and heading and (match := _ROW.match(line)):
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", match.group("rest"))]
            tables[(artifact, heading)].append((match.group("key"), cells))
    return tables


@pytest.fixture(scope="module")
def page() -> dict[tuple[str, str], list[tuple[str, list[str]]]]:
    return parsed_page(guides.input_glossary_markdown())


def test_every_registered_key_has_exactly_one_row(page):
    """THE EXIT OF G08: a key of any registry is a row of the page, once.

    A table the registries imply and the page lacks, a table the page carries
    and nothing implies, a key missing from its table, a key written twice and
    a key no registry holds are each a failure, named.
    """
    expected = expected_tables()
    assert set(page) == set(expected), (
        f"tables the page lacks: {sorted(set(expected) - set(page))}; "
        f"tables nothing implies: {sorted(set(page) - set(expected))}"
    )
    problems = []
    for where, keys in expected.items():
        written = [key for key, _cells in page[where]]
        twice = sorted({key for key in written if written.count(key) > 1})
        missing = sorted(keys - set(written))
        stray = sorted(set(written) - keys)
        for label, names in (("twice", twice), ("missing", missing), ("stray", stray)):
            if names:
                problems.append(f"{where}: {label} {names}")
    assert not problems, "\n".join(problems)


def test_every_row_states_its_meaning_from_the_code(page):
    """A row with no meaning is the failure a new key without its line produces.

    The page is generated from the registries, so a key added to one arrives as
    a row by itself. What it cannot bring with it is WHAT IT MEANS: that comes
    from the code beside the key (a Field description, an Attributes entry, a
    ``#:`` comment, or the registry's own entry), and a key that has none is a
    row this test refuses.
    """
    empty = [
        f"{artifact} / {heading}: {key}"
        for (artifact, heading), rows in page.items()
        for key, cells in rows
        if not cells or not cells[0].strip() or cells[0].strip() == "-"
    ]
    assert not empty, (
        "these keys have no meaning in the code; write it where the key is "
        "registered (the registry entry, a Field description, the model's "
        "Attributes section or a #: comment), never in the page:\n  " + "\n  ".join(empty)
    )


def test_no_meaning_is_kept_for_a_key_no_registry_holds():
    """The mirror: a registry of meanings may not outlive the keys it explains."""
    from pyflightstream.cases import EXPORT_KIND_MEANINGS, SOLVER_SETTING_COMMANDS
    from pyflightstream.cases.matrix import COLUMN_MEANINGS
    from pyflightstream.cases.workflows import ROW_KEY_MEANINGS

    row_keys = {key for workflow in WORKFLOWS.values() for key in workflow.keys}
    assert set(ROW_KEY_MEANINGS) == row_keys | {RAW_VARIABLE}
    assert set(COLUMN_MEANINGS) == set(_COLUMNS)
    assert set(EXPORT_KIND_MEANINGS) == {kind for kind, _, _, _ in EXPORT_KINDS} - set(
        VOLUME_SECTION_KINDS.values()
    )
    assert set(SOLVER_SETTING_COMMANDS) <= set(SolverSettings.model_fields)
    assert set(guides.PACKAGE_SET_FIELDS) == {
        ("ProbesSpec", "resolved_points_file"),
        ("RawCommand", "setup"),
        ("RawCommand", "source"),
        ("CustomFlag", "setup"),
    }


def test_every_command_the_glossary_names_is_in_the_command_database():
    """A command named on a page that says it is generated is trusted, so it is checked."""
    known = CommandRegistry.load().commands
    named = []
    for table in guides.input_glossary_tables():
        named += [(table.heading, "table", command) for command in table.commands]
        named += [
            (table.heading, row.key, command) for row in table.rows for command in row.commands
        ]
    assert len(named) >= 40, f"only {len(named)} commands named; the column went quiet"
    unknown = [
        f"{heading} / {key}: {command}" for heading, key, command in named if command not in known
    ]
    assert not unknown, "\n".join(unknown)


def test_the_keys_of_blocks_four_and_five_are_on_the_page(page):
    """The keys 0.27.0 added, named one by one, so a regrouping cannot hide one."""

    def keys(artifact: str, heading: str) -> set[str]:
        return {key for key, _cells in page[(artifact, heading)]}

    # G04: the solver's own plots; G10: the force distribution.
    assert {"plot_residuals", "plot_loads", "plot_sections_cp", "force_distributions"} <= keys(
        "pproc", "`[exports]`"
    )
    # G05: the volume section, its lengths named with their unit since block 6.
    assert {
        "shape",
        "frame",
        "plane",
        "offset_m",
        "corners_m",
        "radii_m",
        "points",
        "format",
    } <= keys("pproc", "`[volume_section]`")
    assert "volume_section" in keys("pproc", "The tables and top-level keys")
    # G06: the actuator disc, its row keys and its reference block.
    assert {"ACTUATOR", "ACTUATOR_RPM", "ACTUATOR_THRUST", "PROFILE"} <= keys(
        "matrix", "The row keys, by run type"
    )
    assert {"frame", "axis", "tip_radius_m", "hub_radius_m", "swirl", "profile_units"} <= keys(
        "reference", guides.REFERENCE_BLOCK_HEADINGS["actuators"]
    )
    # G09 and G14: the setup keys and the solver's own names for them.
    assert {
        "analysis_families",
        "load_units",
        "inviscid_loads",
        "vorticity_lift_model",
        "unsteady_viscous_coupling_iteration",
    } <= keys("setup", "Solver settings")
    assert {
        "set_solver_analysis_boundaries",
        "set_loads_and_moments_units",
        "set_inviscid_loads",
        "set_vorticity_lift_model",
        "set_unsteady_viscous_coupling_iteration",
    } <= keys("setup", "The solver's own names, read as aliases")
    # Block 4: the raw mesh's sidecar.
    assert {"import", "trailing_edges", "wake_termination", "base_regions"} <= keys(
        "geometry", "Top-level keys and tables"
    )
    assert {"op", "surface", "factors", "vector", "axis", "angle_deg", "plane", "to"} <= keys(
        "geometry", "`[[import.operations]]`"
    )


def test_a_key_the_registry_marks_for_a_run_type_or_a_build_says_so(page):
    """ "The run types or builds that accept it, where the code says."""
    rows = dict(page[("matrix", "The row keys, by run type")])
    accepted = guides.GLOSSARY_COLUMNS.index("Accepted by") - 1
    # The run types come off the WORKFLOWS registry, key by key.
    for key in ("LAST_REVS_AVG", "DELTA_TIME", "GEOMETRY"):
        readers = [name for name, workflow in WORKFLOWS.items() if key in workflow.keys]
        stated = rows[key][accepted].split(";")[0]
        expected = "every run type" if len(readers) == len(WORKFLOWS) else ", ".join(readers)
        assert stated == expected, (key, stated, expected)
    assert rows["LAST_REVS_AVG"][accepted] == "unsteady_rotor"
    settings = dict(page[("setup", "Solver settings")])
    # G14: the coupling step is documented by three editions alone.
    assert "26.000" in settings["unsteady_viscous_coupling_iteration"][accepted]
    assert "26.124" not in settings["unsteady_viscous_coupling_iteration"][accepted]
    # G09: the loads selections are the steady run type's.
    assert "steady" in settings["analysis_families"][accepted]


def test_init_writes_the_page_beside_variables_and_only_when_it_differs(tmp_path):
    """Where a user meets it: beside VARIABLES.md, written by init, plan and post."""
    from pyflightstream.workspace import CampaignWorkspace, write_input_guides

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    folder = workspace.inputs_dir / "pproc"
    page = folder / guides.INPUT_GLOSSARY_NAME
    assert guides.INPUT_GLOSSARY_NAME == "INPUTS.md"
    assert page.is_file() and (folder / "VARIABLES.md").is_file()
    assert page.read_text(encoding="utf-8") == guides.input_glossary_markdown()
    before = (page.stat().st_mtime_ns, page.read_bytes())
    assert write_input_guides(workspace.inputs_dir) == []
    assert (page.stat().st_mtime_ns, page.read_bytes()) == before

    page.write_text("stale\n", encoding="utf-8")
    assert write_input_guides(workspace.inputs_dir) == [page]
    assert page.read_text(encoding="utf-8") == guides.input_glossary_markdown()


def test_the_post_stage_refreshes_the_page_too(tmp_path):
    """``pyfs-matrix post`` refreshes the guides; the glossary is one of them."""
    from pyflightstream.post import _the_guides_stage

    class Workspace:
        inputs_dir = tmp_path / "inputs"

    assert _the_guides_stage(Workspace()) == []
    assert (tmp_path / "inputs" / "pproc" / guides.INPUT_GLOSSARY_NAME).is_file()


def test_the_guides_cite_the_page_and_the_site_renders_it():
    """D08: the user guide and the workflows page name it, and the docs build writes it."""
    guide = (REPO / "guide" / "pyflightstream_user_guide.tex").read_text(encoding="utf-8")
    workflows = (REPO / "docs" / "workspace-and-workflows.md").read_text(encoding="utf-8")
    assert "INPUTS.md" in guide, "the user guide does not cite the input glossary"
    assert "INPUTS.md" in workflows, "the workflows page does not cite the input glossary"
    assert "pproc/INPUTS.md" in workflows, "the input library listing does not show where it is"
    generator = (REPO / "scripts" / "gen_docs_pages.py").read_text(encoding="utf-8")
    assert "input_glossary_markdown" in generator
    nav = (REPO / "properdocs.yml").read_text(encoding="utf-8")
    assert "inputs.md" in nav, "the site's nav does not reach the generated glossary page"


def test_the_page_says_it_is_generated_and_names_no_machine_path():
    text = guides.input_glossary_markdown()
    assert text.startswith("# Inputs\n")
    assert "GENERATED FROM THE CODE" in text
    assert "VARIABLES.md" in text
    assert not re.search(r"[A-Za-z]:[\\/]", text), "the page names a machine-local path"
