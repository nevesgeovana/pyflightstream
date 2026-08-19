"""Tier 1: every FSI physics function cites its formula source.

DLV-007 Section 2: the primary sources of the structural model have not
been independently checked against the implemented formulas, so every
physics formula must live in a small function whose docstring states
the formula source. This schema test keeps that discipline mechanical:
physics functions must carry a "Source:" line, and every public
function of the physics modules must be classified as physics or not,
so new functions cannot slip in unlabeled.

THE SHIPPED PACKAGE NAMES NO TRACKING IDENTIFIER for that unverified
status, and one of the tests below is what holds that. Five docstrings
and a README paragraph used to carry a private tracker id whose only
home was another repository: reports/ runs RPT-001 to RPT-012 and then
RPT-014, so there was never a report for a reader to open and no path
that could be repointed. An identifier a reader cannot resolve looks
like process where there is none, which is worse for that reader than
the plain sentence that replaced it (PFS-2017.01.02).

The other new test is the one that makes the wording change safe. The
Source lines were EDITED, not left alone, so the guard that says
"Source: is present" could not tell a careful edit from one that lost a
citation. The citations each physics function names are pinned here.
"""

import inspect
from pathlib import Path

from pyflightstream.fsi import beam, centrifugal, driver, kinematics, loads, nodes, state

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "src" / "pyflightstream"

#: The retired tracker id, built by concatenation so this module can
#: hunt it without re-planting it in the tree it is hunting.
RETIRED_TRACKER_ID = "TSR" + "-014"

#: The primary source each physics function names. Substrings, because
#: the sentence around them is prose and may be reworded; the CITATION
#: is what must not move. Written out per function rather than derived,
#: so a citation silently copied from one function to another fails.
REQUIRED_CITATIONS = {
    (centrifugal, "axial_load_distribution"): ("FSI Blade Coupling Plan rev. 2",),
    (centrifugal, "axial_tension"): ("FSI Blade Coupling Plan rev. 2",),
    (centrifugal, "total_pitch_rad"): ("FSI Blade Coupling Plan rev. 2",),
    (centrifugal, "propeller_moment_distribution"): (
        "FSI Blade Coupling Plan rev. 2",
        "Houbolt and Brooks, NACA Report 1346",
    ),
    (centrifugal, "propeller_moment_twist_stiffness"): (
        "FSI Blade Coupling Plan rev. 2",
        "Houbolt and Brooks, NACA Report 1346",
    ),
    (centrifugal, "southwell_fit"): (
        "FSI Blade Coupling Plan rev. 2",
        "Bielawa",
        "Rotary Wing Structural Dynamics",
    ),
    (beam, "lumped_station_masses"): ("Cook, Malkus, Plesha, Witt",),
    (beam, "_condense_massless"): ("R. J. Guyan", "AIAA Journal 3(2), 1965"),
    (loads, "transfer_moment_to_elastic_axis"): ("DLV-007 Section 4.3",),
    (loads, "project_rotor_frame_loads"): ("DLV-007 Section 4.2",),
    (kinematics, "station_normal_translation"): ("DLV-007 Section 4.4",),
    (kinematics, "twist_from_node_translations"): ("DLV-007 Section 4.4",),
    (driver, "relax_displacements"): ("DLV-007 Section 4.5",),
    (driver, "revolutions_per_step"): ("DLV-007 Section 4.5",),
}

PHYSICS_FUNCTIONS = [
    (centrifugal, "axial_load_distribution"),
    (centrifugal, "axial_tension"),
    (centrifugal, "total_pitch_rad"),
    (centrifugal, "propeller_moment_distribution"),
    (centrifugal, "propeller_moment_twist_stiffness"),
    (centrifugal, "southwell_fit"),
    (beam, "lumped_station_masses"),
    (beam, "_condense_massless"),
    (loads, "transfer_moment_to_elastic_axis"),
    (loads, "project_rotor_frame_loads"),
    (kinematics, "station_normal_translation"),
    (kinematics, "twist_from_node_translations"),
    (driver, "relax_displacements"),
    (driver, "revolutions_per_step"),
]

# Public functions that orchestrate solves or bookkeeping but contain no
# physical formula of their own (their physics is delegated to the list
# above). A new public function must land in exactly one of the two sets.
NON_PHYSICS_PUBLIC = {
    "centrifugal": {"solve_rotating_static", "rotating_frequencies", "campbell_sweep"},
    "beam": {
        "station_name",
        "build_beam_model",
        "apply_station_loads",
        "solve_static",
        "extract_solution",
        "modal_frequencies",
        "tributary_lengths",
    },
    "loads": {"parse_sectional_loads", "to_elastic_axis", "cross_check_totals"},
    "kinematics": {"encode_station_translations", "decode_station_translations"},
    "nodes": {
        "generate_node_layout",
        "station_triads",
        "node_positions",
        "write_node_file",
        "write_node_map",
        "load_node_map",
        "flatten_blade_translations",
        "unflatten_translations",
        "write_fsidisp",
        "read_fsidisp",
    },
    "driver": {"coupling_step"},
    # check_state_matches_config is a SHAPE check on a resumed state, not an
    # equation: it compares array dimensions against the configured blade
    # count and station count and cites no physical source (PYFS-012).
    "state": {
        "check_state_matches_config",
        "initial_state",
        "load_state",
        "write_state_atomic",
    },
}


def _public_functions(module):
    return {
        name
        for name, obj in vars(module).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == module.__name__
    }


def test_physics_functions_cite_their_source():
    missing = []
    for module, name in PHYSICS_FUNCTIONS:
        doc = inspect.getdoc(getattr(module, name)) or ""
        if "Source:" not in doc:
            missing.append(f"{module.__name__}.{name}")
    assert not missing, f"physics functions without a Source citation: {missing}"


def test_no_shipped_file_names_a_tracker_a_reader_cannot_open():
    """The identifier is dead, so it must not ship.

    reports/ holds RPT-001 to RPT-012 and then RPT-014, so there is no
    report the retired id could have been repointed at: deletion was the
    only move. The walk is over the whole package rather than over the
    five known sites, because the next such id will be somewhere else,
    and it includes ``fsi/README.md``, which sits inside ``src/`` and
    reaches readers through the repository even though the wheel does
    not carry it.
    """
    offenders = []
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if RETIRED_TRACKER_ID in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert not offenders, (
        "a shipped file names a tracking identifier whose only home is another "
        f"repository, so a reader following it reaches nothing: {offenders}. "
        "State the status in plain words instead."
    )


def test_the_unverified_status_is_stated_in_plain_words():
    """Deleting the id must not delete the WARNING it stood for.

    The whole hazard of dropping a tracker is that the caveat goes with
    it, leaving a module that reads as verified. Both places a reader
    meets the model, its own top docstring and the developer README,
    must still say the sources have not been independently checked.
    """
    readme = (PACKAGE / "fsi" / "README.md").read_text(encoding="utf-8")
    module_doc = inspect.getdoc(centrifugal) or ""

    for label, raw in (
        ("the centrifugal module docstring", module_doc),
        ("fsi/README.md", readme),
    ):
        # Whitespace-collapsed: both sentences wrap, and a guard that a line
        # break can satisfy is a guard about typography.
        text = " ".join(raw.split())
        assert "not been independently checked" in text, (
            f"{label} no longer says in plain words that the primary sources have "
            "not been independently checked against the implemented formulas"
        )


def test_each_physics_function_still_names_its_primary_source():
    """A "Source:" line is present is not the same as the SOURCE is right.

    The existing schema test above passes on a docstring reading
    "Source: see above", and it passed unchanged while these Source
    sentences were reworded. This pins the citation each function
    carries, which is the part the rewording had to leave alone.
    """
    assert set(REQUIRED_CITATIONS) == set(PHYSICS_FUNCTIONS), (
        "the citation table and PHYSICS_FUNCTIONS have drifted apart, so a "
        "function could carry a Source line nothing checks"
    )

    wrong = []
    for (module, name), citations in REQUIRED_CITATIONS.items():
        doc = inspect.getdoc(getattr(module, name)) or ""
        source = doc[doc.index("Source:") :] if "Source:" in doc else ""
        # Whitespace-collapsed, because a citation is wrapped across lines
        # in the source file and a raw substring test would then report a
        # citation missing that is plainly there.
        source = " ".join(source.split())
        for citation in citations:
            if citation not in source:
                wrong.append(f"{module.__name__}.{name} no longer cites {citation!r}")
    assert not wrong, "a Source line lost the primary source it named: " + "; ".join(wrong)


def test_every_public_function_is_classified():
    modules = (
        (centrifugal, "centrifugal"),
        (beam, "beam"),
        (loads, "loads"),
        (kinematics, "kinematics"),
        (nodes, "nodes"),
        (driver, "driver"),
        (state, "state"),
    )
    for module, key in modules:
        listed = {name for mod, name in PHYSICS_FUNCTIONS if mod is module}
        unclassified = _public_functions(module) - listed - NON_PHYSICS_PUBLIC[key]
        assert not unclassified, (
            f"unclassified public functions in {module.__name__}: {unclassified}; "
            "add each to PHYSICS_FUNCTIONS (with a Source: line) or to "
            "NON_PHYSICS_PUBLIC"
        )
