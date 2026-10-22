#!/usr/bin/env python3
"""Prove that a release does everything the previous release did (GOAL-038 arm R1).

    python scripts/check_parity.py --workspace <recorded campaign> --out <parity.json>
    python scripts/check_parity.py --base v0.32.0 --release HEAD --workspace W --out F

WHAT IS COMPARED. Two trees of this repository, the base tag and the release
commit, each exported from git (never the working tree), each exercised in its
own interpreter process whose ``pyflightstream`` is asserted to be imported
from that tree:

1. **api**: every name in every ``__all__`` of the base still imports from the
   same dotted path at the release, and so does every public name a base module
   WITHOUT ``__all__`` offers (bound at module level, not starting with ``_``,
   not a module, not imported from outside the package; see
   :func:`offered_names`). Modules with a private dotted segment are excluded
   (AD-15). Only the fully qualified retired bindings in ``API_EXEMPT`` are exempt.
2. **cli**: every console script of the base ``pyproject.toml``, every
   subcommand, every option string and every ``choices`` value is still in the
   release parser (a parser diff; each parser is captured at the moment its
   ``main`` calls ``parse_args``).
3. **scripts**: the emitted scripts of the golden campaign set
   (``GOLDEN_RENDERS`` of ``tests/tier1_offline/test_workflows.py``) and of the
   tier-3 matrices (``tests.tier3_licensed.offline.render``), each rendered by
   its own tree, are byte-identical. The workspace matrices are also planned
   in per-point, batch and polar-sweep modes. A non-submitting executor writes
   their scripts on disposable copies; no solver or scheduler is started.
   Grouped exclusions retain the planner's reasons in ``grouped_skipped``; a changed
   left-out reason of a row is a difference of kind ``left_out`` (FR-421 R2).
   Matrix/config refusals are listed by matrix, mode and version in
   ``workspace_refused``. Reasons use structured ``(run_id, error)`` pairs from
   ``plan.json`` where available; parsing the message is a fallback. Equal
   per-row reasons at both versions are unchanged;
   one-sided refusals or changed reasons are differences, without counting as
   compared scripts.
   Each attempted grouped mode must contribute compared scripts, unless
   ``--allow-no-grouped`` explicitly permits missing coverage in the receipt.
   ``workspace_compared`` counts workspace scripts separately from golden and
   tier-3 renders. ``workspace_coverage`` lists rendered and refused matrix/mode
   pairs by version. With ``--workspace``, zero workspace scripts compared
   always fails, naming the refusals, even with ``--allow-no-grouped``.
   The non-submitting write path requires both private CLI dispatch helpers,
   ``runner_for`` and ``planner_for``, and mirrors the CLI's plan arguments.
4. **post**: ``pyfs-matrix post`` over one recorded workspace, run by each
   tree's console-script target on a fresh copy at the same path, writes the
   same ``post/`` bytes, ``products.json`` included.

A difference in 3 or 4 passes only when :data:`NAMED_DIFFERENCES` names it with
a requirement that the release SRS defines, and, where the entry gives a line
pattern, only when every changed line matches it. Anything else is a failure.

CONTROLS. A comparator that cannot see a difference would report parity for
everything, so each run plants one difference per comparison into the real
observations (a name no module exports, a name a module without ``__all__``
lacks, a flag no parser has, one changed line of a render, one changed byte of
a product) and requires each to be caught; the reader of a module without
``__all__`` is also run over a planted module whose offered names are known. The
receipt records ``caught <k> of <k>``; anything less is PARITY: FAIL.

TEMPORARY FILES. The exported trees, the renders and the workspace copy live in
one temporary folder, deleted at the end of the run (``--keep`` keeps it).

The receipt names the SHA-256 of this script as committed at the release; a run
whose own bytes differ from that revision concludes PARITY: FAIL, because its
receipt would otherwise claim a script that did not produce it.
"""

from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import difflib
import fnmatch
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import types
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _requirements_paths import (  # noqa: E402
    REQUIREMENTS_DIR,
    read_l3,
    requirement_pages,
    requirement_rows,
)

REPO = Path(__file__).resolve().parent.parent
SCRIPT = "scripts/check_parity.py"
EXPORTED = (
    "src",
    "tests",
    "docs/srs",
    REQUIREMENTS_DIR.as_posix(),
    "pyproject.toml",
    "scripts/_requirements_paths.py",
)
PACKAGE = "pyflightstream"
MATRIX_CONSOLE = "pyfs-matrix"

#: Base names that may be absent at the release, with the decision that removed them.
API_EXEMPT = {
    "pyflightstream.cases.stamp_derived_campaign": "0.33 scope decision 9 deletes it",
    "pyflightstream.farfield.rothalpy": "FR-458 (0.40.0) hands it to ITACA",
    "pyflightstream.farfield.irreversible_deficit": "FR-458 (0.40.0) hands it to ITACA",
    "pyflightstream.farfield.lattice_dataset": "FR-457 R3 retires it for farfield.lattice_fields",
    "pyflightstream.post.dataset_to_points": "FR-457 R3 retires it for LatticeFields.points",
    "pyflightstream.post.writers.dataset_to_points": "FR-457 R3: use LatticeFields.points",
}

#: The message of a per-revolution drift warning, old or new wording: the column
#: drifts by a percentage of itself or, for a force or moment column, of the
#: scale of its group, between two revolutions, over the limit.
_DRIFT_MESSAGE = (
    r"rotor '[^']*' column \w+ drifts [+-][\d.]+ per cent "
    r"(?:of its scale [\d.eE+-]+ \(the magnitude of \w+, the largest (?:force|moment) mean "
    r"of its group in the earlier revolution; a change of [+-][\d.eE+-]+\) )?"
    r"between revolution \d+ and revolution \d+, over the drift limit of [\d.]+ per cent "
    r"\(\[per_revolution\] drift_limit_pct\): the last revolution is still moving"
)

#: A toggle line of the five solver-settings commands FR-349 (0.34.0) resolves.
_TOGGLE_LINE = (
    r"(?:VALAREZO_CRITERION|SET_WAKE_RELAXATION|SET_WAKE_STREAMWISE_AGGLOMERATION"
    r"|SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER|SOLVER_VORTEX_RING_NORMALIZATION)"
    r" (?:ENABLE|DISABLE)"
)

#: The vorticity drag list as the emitter writes it, its blank line included: the
#: count -1 alone (every boundary), or a count and its comma-separated indices.
_VORTICITY_LIST = r"SET_VORTICITY_DRAG_BOUNDARIES (?:-1|\d+\n\d+(?:,\d+)*)\n\n"

#: A script that turns a rotor in time: an unsteady solver and a rotor motion
#: (the condition the FR-321 entries state, written once more for FR-318).
_ROTOR_MARCH = (
    r"(?=.*^SET_SOLVER_UNSTEADY$)"
    r"(?=.*^(?:CREATE_NEW_MOTION ROTARY|SET_MOTION_IS_ROTOR \d+ ENABLE\b"
    r"|SET_MOTION_ANGULAR_VELOCITY \d+ [^\n]*[1-9]))"
)

#: One line of the INITIALIZE_SOLVER block 0.34.0 emitted on a continuation, and
#: one line of an unsteady action registration it emitted there (FR-396).
_INITIALIZATION_LINE = (
    r"(?:SOLVER_MODEL|SURFACES|WAKE_TERMINATION_X|SYMMETRY|SYMMETRY_TYPE"
    r"|WALL_COLLISION_AVOIDANCE|ENABLE|DISABLE)\b[^\n]*"
)
_ACTION_HEAD = r"SET_NEW_UNSTEADY_SOLVER_ACTION (?:COMMAND_LINE|SCRIPT) pfs_\w+"
_ACTION_FILE = r'(?:"[^"\n]+" "actions/pfs_\w+\.py"|actions/pfs_\w+\.txt)'

#: The post's warning on a continuation whose plots export adds no time step (FR-396 R3).
_NO_STEP_MESSAGE = (
    r"this continuation of '[^']*' adds no time step to its march: '[^']*' had reached step "
    r"\d+ and the continuation's plots export ends there or before, so no continued step is "
    r"in the table\. A continuation that clears the reopened state marches again from step 1 "
    r"\(RPT-134\); the table is posted as the march stands\."
)

#: The left-out reason of a coupled steady or quasi-steady row, as the base (0.36.0) printed it
#: and as the release prints it (FR-421 R2): the one named difference of the grouped plan text.
LEFT_OUT_BEFORE = (
    "a coupled row on steady or qsteady_rotor: its coupling loop starts only after the script "
    "ends, and on 26.124 the next point of the job crashed the instance (RPT-150)"
)
LEFT_OUT_AFTER = (
    "a coupled row on steady or qsteady_rotor: its coupling loop starts only after the script "
    "ends, and on 26.124 the next point of the job crashed the instance; run these rows "
    "point by point, without --batch or --polar-sweep"
)

#: FR-419: the two INFO messages of the settings table (a point without a row, and a matrix
#: without any), and the lines of the manifest that name the settings products.
_NO_SNAPSHOT_MESSAGE = (
    r"(?:no row in the settings table: its record holds no solver-setup snapshot[^\"\n]*"
    r"|no point of the matrix has a solver-setup snapshot, so the settings table "
    r"and its codebook are not written)"
)
_SETTINGS_MANIFEST_LINE = (
    r'(?:  "settings/[^"]+": \{|   "kind": "settings_codebook",|   "runs": \[|    "[^"]+",?'
    r"|   \]|  \},?)"
)

#: FR-89, P0370-S11-SUPER-DIAMETER (0.37.0): the columns the super content inserts (each
#: rotor's speed and diameter), the clock columns a quasi-steady point fills, and a cell of
#: either (a number as the products write it, fixed or free).
_S11_INSERTED = r"(?:RPM|DIAMETER)_[A-Za-z0-9_]+"
_S11_FILLED = r"J_CLOCK|RPM_CLOCK"
_S11_NUMBER = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_S11_WHY = (
    "P0370-S11-SUPER-DIAMETER: the super content states each rotor's diameter, the rotor "
    "block's diameter_m the rotor table divides by, beside its speed, and a quasi-steady "
    "point's speed and clock from its quasi-steady record where its plan states none; the "
    "owner's decision of 2026-10-05 on her report that the diameter did not reach the "
    "super file"
)

#: Differences a named 0.33 requirement states. ``kind`` is "scripts" or "post";
#: ``pattern`` is an fnmatch glob over the render name or the post-relative file;
#: ``lines``, when given, is a regex every changed line must match; ``block``,
#: when given, is a regex the changed lines of one file, joined by line feeds,
#: must match whole, so a difference is held to its lines, their order and
#: their number; ``release_lacks``, when given, is a regex the release's own
#: text must NOT match, so a difference that removes lines is held to its
#: direction and to the state the requirement names; ``release_has``, when
#: given, is a regex the release's own text MUST match, and ``base_lacks`` one
#: the base's text must NOT match, so a difference that adds lines is held to
#: its direction and to the scripts the requirement names.
#: ``appended_column``, when given, names the one CSV column the release appends
#: LAST to the file, and ``cells`` the regex each of its cells must match whole, so
#: the difference is held to that column, its place and its cells
#: (:func:`appends_one_column`).
#: ``inserted_columns``, when given, is the regex every column the release INSERTS must
#: match whole (an empty string inserts none), and ``filled_columns`` the regex of the
#: columns whose cells may change, only from ``NA`` to a cell matching ``cells``; every
#: other column keeps its name, its order and its cells (:func:`inserts_and_fills`).
#: ``since`` is the release that introduced the difference: an entry names a
#: difference only against a base OLDER than it. Against a base at or past it the
#: difference is already in the base, so the same lines differing again are a
#: revert or a new change and must be named anew; without the scope a release
#: that reverted a fix passed as named.
NAMED_DIFFERENCES: list[dict[str, str]] = [
    {
        "kind": "post",
        "pattern": "*/polars/*.csv",
        "csv_rounding": "base",
        "requirement": "FR-124",
        "since": "0.40.0",
        "why": "c61eb487 (PFS-2081.53): coefficients retain six significant figures",
    },
    {
        "kind": "post",
        "pattern": "*/sections/*.csv",
        "csv_rounding": "base",
        "requirement": "FR-124",
        "since": "0.40.0",
        "why": (
            "505c8dc0, extended by a9d674f1 (PFS-2105.041): "
            "small dimensional values retain significant digits"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/settings/*_settings.csv",
        "csv_rounding": "coarser",
        "csv_inserted_columns": r"f\d+_kind",
        "requirement": "FR-419",
        "since": "0.40.0",
        "why": (
            "6a9ee69f (PFS-2105.042): setting kinds distinguish codes from list lengths; "
            "68755be9 (PFS-2105.020): settings convergence precision correction replaces "
            "five-decimal rounding with the shortest exact spelling"
        ),
    },
    {
        "kind": "left_out",
        "pattern": "*",
        # The reason the grouped plan prints for a coupled row on steady or qsteady_rotor,
        # the only changed text: the evidence id leaves it and the remedy joins it
        # (FR-421 R2). FR-410's exclusion itself is unchanged. Only the exact complete pair
        # matches, old equal to the 0.36.0 text and new equal to the release text, line
        # endings included: an appended line, a trailing newline, the reverse direction or
        # any other reason is unnamed.
        "old_text": LEFT_OUT_BEFORE,
        "new_text": LEFT_OUT_AFTER,
        "requirement": "FR-421",
        "since": "0.37.0",
        "why": (
            "the plan's left-out line of a coupled steady or quasi-steady row names the "
            "remedy (run those rows point by point) and no longer cites a report id; the "
            "exclusion itself is FR-410's, unchanged"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*_rotor__*__26.100*",
        # A rotor render on 26.100 is a refusal and nothing else: the whole
        # release text is the refusal of the rotor rows on that build, whose
        # angular-velocity unit is unmeasured (FR-101 as amended in 0.40.0,
        # PFS-2088.010); any other text on either side stays unnamed.
        "release_has": (
            r"\AREFUSED CommandArgumentError\ncase '\d+': FlightStream 26\.100: rotary_motion, "
            r"unsteady_rotor and rotor-speed rows are refused until the angular-velocity unit "
            r"is measured\.[^\n]*\n?\Z"
        ),
        "requirement": "FR-101",
        "since": "0.40.0",
        "why": (
            "a rotor row on 26.100 is refused by name until a rotation null probe measures "
            "the unit of that build's angular velocity; 0.39.0 wrote the speed in rev/min as "
            "a maintainer decision (RPT-051) where the manual tutorial gives rad/s"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The disc speed lines and nothing else, each removed line followed by
        # the added line of the same disc index and the same magnitude with
        # the other sign: 0.33.0 handed the solver plus the block's hand times
        # the speed, 0.34.0 hands it minus (FR-331, measured in RPT-137).
        "lines": r"^SET_PROP_ACTUATOR_RPM \d+ -?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$",
        "block": (
            r"(?:SET_PROP_ACTUATOR_RPM (\d+) "
            r"(?:-(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\nSET_PROP_ACTUATOR_RPM \1 \2"
            r"|(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\nSET_PROP_ACTUATOR_RPM \1 -\3)"
            r"(?:\n|$))+"
        ),
        "requirement": "FR-331",
        "since": "0.34.0",
        "why": (
            "an actuator disc swirls its wake the way a rotor of the same rpm_sign "
            "turns: the disc speed handed to the solver is minus the block's hand "
            "times the speed, where 0.33.0 handed plus, the sense measured on 26.124 "
            "to swirl with the rotor"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # One termination line ADDED, the only changed line of the script, to a
        # script that turns a rotor in time (an unsteady solver and a rotor
        # motion in the release) and whose base wrote no termination line: the
        # 4R default of a rotor row that states no wake termination, converted
        # into steps. A removed line, a changed count, a second termination
        # line, any other changed line, and a steady or rotorless script do not
        # match. The rotor motion is ROTARY, or marked a rotor, or, on 26.100,
        # whose database has no SET_MOTION_IS_ROTOR (RPT-049), a EUCLIDEAN
        # motion with a non-zero angular velocity.
        "lines": r"^SET_WAKE_TERMINATION_TIME_STEPS \d+$",
        "block": r"SET_WAKE_TERMINATION_TIME_STEPS \d+",
        "release_has": (
            r"(?ms)\A(?=.*^SET_SOLVER_UNSTEADY$)"
            r"(?=.*^(?:CREATE_NEW_MOTION ROTARY|SET_MOTION_IS_ROTOR \d+ ENABLE\b"
            r"|SET_MOTION_ANGULAR_VELOCITY \d+ [^\n]*[1-9]))"
        ),
        "base_lacks": r"(?m)^SET_WAKE_TERMINATION_TIME_STEPS\b",
        "requirement": "FR-321",
        "since": "0.34.0",
        "why": (
            "a rotor row that states no wake termination keeps a wake of 4 rotor radii, "
            "converted into the steps SET_WAKE_TERMINATION_TIME_STEPS takes, where 0.33.0 "
            "emitted no termination line"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The section Cp plot's three export lines and the blank line closing
        # them, REMOVED from a script that cuts no section: the release must
        # carry neither a section command nor a section Cp plot, so a drop from
        # a row that still cuts a section, or an added plot, does not match.
        "lines": r"^(SET_PLOT_TYPE SECTIONS_CP|SAVE_PLOT_TO_FILE|.+_plot_cp_sections\.txt|)$",
        "block": (
            r"(SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n[^\n]+_plot_cp_sections\.txt\n"
            r"|\nSET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n[^\n]+_plot_cp_sections\.txt)"
        ),
        "release_lacks": r"(?m)^(NEW_SURFACE_SECTION_DISTRIBUTION|SET_PLOT_TYPE SECTIONS_CP)\b",
        "requirement": "FR-51",
        "since": "0.33.1",
        "why": (
            "P0331-SECTIONS-ABSENT-FAMILY: a row whose geometry carries no family a "
            "section distribution of its artifact cuts declares and exports no section "
            "Cp plot; the solver writes no such file with no section to plot"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The FR-321 and FR-51 differences together in one script, and nothing
        # else: the one termination line ADDED first, then the section Cp plot's
        # three export lines and their blank line REMOVED, in the order the diff
        # lists them. Each condition is its single entry's own: the release
        # turns a rotor in time and the base wrote no termination line (FR-321),
        # and the release cuts no section and plots none (FR-51). Either part
        # alone goes to its single entry; a second termination line, any other
        # changed line, the other order, a steady or rotorless script, a base
        # that had a termination line, and a release that still plots or cuts a
        # section do not match. Measured on tier3/matriz/P1021 against v0.33.0.
        "lines": (
            r"^(SET_WAKE_TERMINATION_TIME_STEPS \d+|SET_PLOT_TYPE SECTIONS_CP|SAVE_PLOT_TO_FILE"
            r"|.+_plot_cp_sections\.txt|)$"
        ),
        "block": (
            r"SET_WAKE_TERMINATION_TIME_STEPS \d+\n"
            r"(SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n[^\n]+_plot_cp_sections\.txt\n"
            r"|\nSET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n[^\n]+_plot_cp_sections\.txt)"
        ),
        "release_has": (
            r"(?ms)\A(?=.*^SET_SOLVER_UNSTEADY$)"
            r"(?=.*^(?:CREATE_NEW_MOTION ROTARY|SET_MOTION_IS_ROTOR \d+ ENABLE\b"
            r"|SET_MOTION_ANGULAR_VELOCITY \d+ [^\n]*[1-9]))"
        ),
        "release_lacks": r"(?m)^(NEW_SURFACE_SECTION_DISTRIBUTION|SET_PLOT_TYPE SECTIONS_CP)\b",
        "base_lacks": r"(?m)^SET_WAKE_TERMINATION_TIME_STEPS\b",
        "requirement": "FR-321",
        "since": "0.34.0",
        # The section part is FR-51's: the composite names the pair only when
        # the release SRS defines both, as the two single entries together would.
        "also_requires": "FR-51",
        "why": (
            "a rotor row that states no wake termination keeps a wake of 4 rotor radii, "
            "converted into the steps SET_WAKE_TERMINATION_TIME_STEPS takes, where 0.33.0 "
            "emitted no termination line (FR-321); and the same row, whose geometry carries "
            "no family a section distribution of its artifact cuts, declares and exports no "
            "section Cp plot, P0331-SECTIONS-ABSENT-FAMILY (FR-51, shipped in 0.33.1)"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The three lines of the counter's registration and nothing else: its
        # head, its command line (the interpreter as the render spells it, then
        # the program) and the blank line that closes the action. The diff may
        # place the blank line before or after the two, and nothing else.
        "lines": (
            r"^(SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter"
            r'|"[^"]+" "actions/pfs_unsteady_actions\.py"|)$'
        ),
        "block": (
            r"(SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter\n"
            r'"[^"\n]+" "actions/pfs_unsteady_actions\.py"\n'
            r"|\nSET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter\n"
            r'"[^"\n]+" "actions/pfs_unsteady_actions\.py")'
        ),
        "requirement": "FR-314",
        "since": "0.33.0",
        "why": (
            "every unsteady row registers the step counter; a row asking no per-step "
            "export gains the count-only counter's registration, on a build that "
            "documents the unsteady solver action"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # A toggle line of the five commands the 0.33.0 defect wrote as ENABLE
        # whatever was asked, and nothing else: the removed and the added line
        # are each one of those commands with a state. The release is held to
        # the state a row asked by the tier-1 tests of FR-349.
        "lines": rf"^{_TOGGLE_LINE}$",
        "block": rf"(?:{_TOGGLE_LINE}(?:\n|$))+",
        "requirement": "FR-349",
        "directed_toggles": "true",
        "since": "0.34.0",
        "why": (
            "P0340-TOGGLES: a row that asks DISABLE for valarezo_criterion, wake_relaxation, "
            "wake_streamwise_agglomeration, adverse_gradient_boundary_layer or "
            "vortex_ring_normalization now gets DISABLE, where 0.33.0 wrote ENABLE"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log",
        # Only a per-revolution drift WARNING record: the whole line, down to
        # the closing clause. A changed line of any other warning, or of this
        # warning with another wording, does not match and fails.
        "lines": (
            r"^WARNING point=\S+ product=probes/\S+_per_revolution_\S+\.csv: "
            rf"{_DRIFT_MESSAGE}$"
        ),
        "requirement": "FR-180",
        "since": "0.33.0",
        "why": (
            "a force or moment column's per-revolution drift is judged against the "
            "scale of its group, so the warning records are worded and counted anew; "
            "the products are byte-identical"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log.json",
        # The record's own fixed lines as the log writes them (indent 1 and 3),
        # its point, its per-revolution product, its message and its constant
        # category. A line of any other record, or of another level, fails.
        "lines": (
            r"^(  \{|  \},?"
            r'|   "point": "P\d+-[^"]*",'
            r'|   "product": "probes/[^"]*_per_revolution_[^"]*\.csv",'
            rf'|   "message": "{_DRIFT_MESSAGE}",'
            r'|   "remedy": null,|   "category": "postprocessing",|   "severity": "warning")$'
        ),
        "requirement": "FR-180",
        "since": "0.33.0",
        "why": (
            "the machine-readable form of the same per-revolution drift warning "
            "records, which FR-180 words and counts anew"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/SUPER-*.csv",
        # The super file gains ONE column, MESH_FACES, after every column 0.33.1
        # wrote, its cells NA or a whole number, and nothing else changes: the
        # header and each row are the 0.33.1 line with that one cell appended,
        # after a comma, or as one more 16-wide field in the legacy_polar form.
        "appended_column": "MESH_FACES",
        "cells": r"NA|\d+",
        "requirement": "FR-348",
        "since": "0.34.0",
        "why": (
            "the super file carries the face count of each row's geometry as its boundary "
            "inventory states it, NA where it states none, in a new last column"
        ),
    },
    {
        "kind": "post",
        "pattern": "*_uns_avg.csv",
        # The unsteady polar gains ONE column, MESH_FACES, after every column 0.33.1
        # wrote, its cells NA or a whole number, and nothing else changes: the
        # header and each row are the 0.33.1 line with that one cell appended.
        "appended_column": "MESH_FACES",
        "cells": r"NA|\d+",
        "requirement": "FR-348",
        "since": "0.34.0",
        "why": (
            "the unsteady polar carries the face count of each row's geometry as its boundary "
            "inventory states it, NA where it states none, in a new last column"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The vorticity drag list of a rotor march moved from right after
        # START_SOLVER to right before it, and nothing else. The diff keeps the
        # longer common run, so it reads the move as START_SOLVER removed after
        # the list's place in 0.34.0 and added after the list: the changed lines
        # are START_SOLVER twice. The base held the list right after every
        # START_SOLVER; the release holds it right before, never after, in a
        # script that turns a rotor in time. Measured on 26.124 in RPT-133.
        "lines": r"^START_SOLVER$",
        "block": r"START_SOLVER\nSTART_SOLVER",
        "release_has": rf"(?ms)\A{_ROTOR_MARCH}(?=.*^{_VORTICITY_LIST}START_SOLVER$)",
        "release_lacks": r"(?m)^START_SOLVER\nSET_VORTICITY_DRAG_BOUNDARIES\b",
        "base_lacks": rf"(?m)^START_SOLVER\n(?!{_VORTICITY_LIST})",
        "requirement": "FR-318",
        "since": "0.35.0",
        "why": (
            "P0350-VORTICITY-BEFORE-SOLVE: a row turning a rotor in time that states "
            "vorticity_drag_families emits SET_VORTICITY_DRAG_BOUNDARIES right before "
            "START_SOLVER, where 0.34.0 emitted it right after, so every step export carries "
            "the list (FR-318 R6, RPT-133)"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # A continuation's unsteady action registrations and its INITIALIZE_SOLVER
        # block REMOVED, and nothing else: each registration its head and its
        # command or script file, each followed by the blank line that closes it,
        # then the initialization's keyword lines. The release reopens a saved
        # state (OPEN ... ENABLE) and carries neither command.
        "lines": rf"^(?:{_ACTION_HEAD}|{_ACTION_FILE}|INITIALIZE_SOLVER|{_INITIALIZATION_LINE}|)$",
        "block": (
            rf"\n?(?:{_ACTION_HEAD}\n{_ACTION_FILE}\n\n)*"
            rf"INITIALIZE_SOLVER(?:\n{_INITIALIZATION_LINE})+\n?"
        ),
        "release_has": r"(?m)^LOAD_SOLVER_INITIALIZATION ENABLE$",
        "release_lacks": r"(?m)^(?:INITIALIZE_SOLVER|SET_NEW_UNSTEADY_SOLVER_ACTION)\b",
        "requirement": "FR-396",
        "since": "0.35.0",
        "why": (
            "P0350-CONTINUATION-NO-REINIT, P0350-CONTINUATION-ACTIONS-ONCE: a continuation that "
            "reopens a saved state emits no INITIALIZE_SOLVER, which cleared the reopened "
            "solution and restarted the march at step 1, and registers none of the unsteady "
            "actions the saved file carries, which then ran twice a step (RPT-134)"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log",
        # Only the warning on a continuation that adds no time step, whole.
        "lines": rf"^WARNING point=\S+ product=plots: {_NO_STEP_MESSAGE}$",
        "requirement": "FR-396",
        "since": "0.35.0",
        "why": (
            "P0350-CONTINUATION-WARN: the post warns on a continuation whose plots export adds "
            "no time step to the march it continues, naming both runs (FR-396 R3)"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/settings/*",
        # A FILE ADDED AT THE RELEASE, never a changed one: the settings table and
        # its codebook, which a pproc that does not state `settings_codebook =
        # false` now gets (the owner's decision of 2026-10-05).
        "added": "true",
        "requirement": "FR-419",
        "since": "0.37.0",
        "why": (
            "the settings table and its codebook are written by default, one pair per "
            "matrix under settings/, unless the pproc states settings_codebook = false"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/products.json",
        # Only the manifest's lines for those files: their two entries (kind and runs).
        "lines": rf"^{_SETTINGS_MANIFEST_LINE}$",
        "block": rf"(?:{_SETTINGS_MANIFEST_LINE}(?:\n|$))+",
        "requirement": "FR-419",
        "since": "0.37.0",
        "why": (
            "the manifest lists the settings table and its codebook with kind settings_codebook"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log",
        # Only the INFO line of a point without a snapshot, or of a matrix without any, whole.
        "lines": rf"^INFO point=.+? product=settings/\S+\.csv: {_NO_SNAPSHOT_MESSAGE}$",
        "requirement": "FR-419",
        "since": "0.37.0",
        "why": (
            "a point whose record holds no solver-setup snapshot is named in post.log by an "
            "INFO line as having no row in the settings table (FR-419 R1)"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log.json",
        # The same INFO record as the log writes it (indent 1 and 3).
        "lines": (
            r"^(  \{|  \},?"
            r'|   "point": "[^"]+",'
            r'|   "product": "settings/[^"]+\.csv",'
            rf'|   "message": "{_NO_SNAPSHOT_MESSAGE}",'
            r'|   "remedy": null,|   "category": "[a-z_]+",|   "severity": "info")$'
        ),
        "requirement": "FR-419",
        "since": "0.37.0",
        "why": "the machine-readable form of the same no-snapshot INFO records (FR-419 R1)",
    },
    {
        "kind": "post",
        "pattern": "*/post.log.json",
        # The same warning's record as the log writes it (indent 1 and 3).
        "lines": (
            r"^(  \{|  \},?"
            r'|   "point": "[^"]+",'
            r'|   "product": "plots",'
            rf'|   "message": "{_NO_STEP_MESSAGE}",'
            r'|   "remedy": null,|   "category": "[a-z_]+",|   "severity": "warning")$'
        ),
        "requirement": "FR-396",
        "since": "0.35.0",
        "why": (
            "the machine-readable form of the same warning on a continuation that adds no "
            "time step (FR-396 R3)"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/SUPER-*.csv",
        # P0370-S11-SUPER-DIAMETER: each rotor's DIAMETER_<alias> beside its RPM_<alias>
        # (and RPM_<alias> itself on a quasi-steady point, whose plan states no speed),
        # columns INSERTED, each cell NA or a number; and the clock cells J_CLOCK and
        # RPM_CLOCK FILLED, NA in the base and a number in the release. Every other
        # column keeps its name, its order and every cell (:func:`inserts_and_fills`).
        "inserted_columns": _S11_INSERTED,
        "filled_columns": _S11_FILLED,
        "cells": _S11_NUMBER,
        "requirement": "FR-89",
        "since": "0.37.0",
        "why": _S11_WHY,
    },
    {
        "kind": "post",
        "pattern": "*_uns_avg.csv",
        # The unsteady polar carries the super content, so the same two changes.
        "inserted_columns": _S11_INSERTED,
        "filled_columns": _S11_FILLED,
        "cells": _S11_NUMBER,
        "requirement": "FR-89",
        "since": "0.37.0",
        "why": _S11_WHY,
    },
    {
        "kind": "post",
        "pattern": "*.csv",
        # Every other product that states the condition block: only the clock cells
        # FILLED, NA to a number, and no column inserted, removed or moved.
        "inserted_columns": "",
        "filled_columns": _S11_FILLED,
        "cells": _S11_NUMBER,
        "requirement": "FR-89",
        "since": "0.37.0",
        "why": (
            "P0370-S11-SUPER-DIAMETER: a quasi-steady point's clock, J_CLOCK and RPM_CLOCK, "
            "is taken from the speed its quasi-steady record states where its plan states "
            "none, the speed its rotor table already used; it read NA (the owner's decision "
            "of 2026-10-05)"
        ),
    },
]

#: Rewrites applied to both sides of a post file before comparison, as
#: (file glob, regex, replacement, reason). Only measured volatile fields.
_STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:[+-]\d\d:\d\d|Z)"
POST_NORMALIZE: list[tuple[str, str, str, str]] = [
    (
        "*/post.log",
        rf"(?m)^time={_STAMP}(?=\r?$)",
        "time=<TIME>",
        "the wall-clock stamp of each log record; measured 2026-09-30 as the only difference",
    ),
    (
        "*/post.log.json",
        rf'"time": "{_STAMP}"',
        '"time": "<TIME>"',
        "the same stamp in the machine-readable log",
    ),
    (
        "*.dat",
        r"\A(FlightStream - [^\n]*\n[^\n]*\n)"
        r"[A-Z][a-z]{2} [A-Z][a-z]{2} \d\d \d\d:\d\d:\d\d  \d{4}(?=\r?\n)",
        r"\1<TIME>",
        "the custom polar format (PFS-2014.01.02, post/custom_polar.py "
        "write_custom_polar_format) defines line 3 as the write time, with "
        "FlightStream - ... as the title on line 1; measured 2026-10-03: "
        "research-corpus parity at 20d23064 found 305 custom polar files differing "
        "on that line only; at d51347d9, 90 named-group *_ROTOR.dat files differed "
        "on that line only (parity_research_d51347d9_rotor-evidence.json, "
        "retained outside the tree; SHA-256 "
        "6b84ee2e873ec608296e3ad1a66dcc9503a9245c41a69b483b875b50564e5b70)",
    ),
    (
        "*/post.log",
        r"(?m)^pyflightstream \d+\.\d+\.\d+(?:\.dev\d+)? post",
        "pyflightstream <VERSION> post",
        "the package version the run was posted with (post/products.py header line), which "
        "differs between any two releases by construction (measured 2026-10-11, 0.38.0 "
        "against 0.39.0: the only post difference)",
    ),
    (
        "*/post.log.json",
        r'"version": "\d+\.\d+\.\d+(?:\.dev\d+)?"',
        '"version": "<VERSION>"',
        "the package version the run was posted with (the header key of the machine-readable "
        "log), which differs between any two releases by construction (measured 2026-10-11, "
        "0.38.0 against 0.39.0: the only post difference)",
    ),
    (
        "*/products.json",
        r'"(superfile|sections)_report": "reports/(superfile|sections)-'
        r'\d+(?:-\d+-\d+)?(?:(?:a|b|rc)\d+)?\.json"',
        r'"\1_report": "reports/\2-<VERSION>.json"',
        "the package version the run was posted with, as the release tag in the report "
        "names (post/superfile.py release_tag: compact numbers when major and patch "
        "each have one digit, otherwise hyphen-separated, with a pre-release label), "
        "which differs between any two "
        "releases by construction (measured 2026-10-11, 0.38.0 against 0.39.0: the only "
        "post difference)",
    ),
]

#: The one difference of NFR-32, named whole: a text file of 0.33.0 holds CR before LF where
#: Windows wrote it in text mode, and the file of 0.34.0 holds LF. The comparison removes CR before
#: LF on the 0.33.0 side (:func:`lf`), so a file that differs ONLY by it is equal; it is listed in
#: the receipt under ``cr_removed`` with this requirement, and a file that differs by anything
#: else still goes through :data:`NAMED_DIFFERENCES`.
LF_REQUIREMENT = "NFR-32"
LF_WHY = (
    "LF line ends in every text file the package writes: 0.33.0 wrote CRLF on Windows where "
    "the text mode of the platform ended a line, 0.34.0 writes LF on every platform"
)

TEXT_SUFFIXES = {".csv", ".json", ".log", ".txt", ".md", ".dat", ".vtk", ".toml", ".fs"}
PLANTED_NAME = "__parity_control_name__"
PLANTED_FLAG = "--parity-control-flag"


def cli_refused(base: set[str], release: set[str]) -> list[str]:
    """Return the command-line spellings the base accepts and the release no longer does."""
    return sorted(base - release)


#: The planted controls a run must catch: three api, one cli, one scripts, two post (a changed
#: byte and a planted CR).
CONTROLS = 7


# --------------------------------------------------------------------------- collectors
# These run inside a child interpreter whose sys.path starts at one exported tree.


def _assert_tree(tree: Path) -> None:
    module = importlib.import_module(PACKAGE)
    where = Path(module.__file__ or "").resolve()
    if tree.resolve() not in where.parents:
        raise SystemExit(f"{PACKAGE} imported from {where}, not from the tree {tree}")


def _is_package_import(node: ast.ImportFrom) -> bool:
    """Return whether a ``from ... import`` statement reads from this package."""
    module = node.module or ""
    return node.level > 0 or module == PACKAGE or module.startswith(f"{PACKAGE}.")


def _module_bindings(source: str) -> dict[str, set[str]]:
    """Map every name bound at module level to how it is bound.

    The kinds are ``defined`` (a def, a class, an assignment or any other
    binding statement), ``package`` (imported from this package) and
    ``outside`` (imported from anywhere else). Statements nested in a module
    level ``if``, ``try`` or ``with`` count; function and class bodies do not.
    """
    kinds: dict[str, set[str]] = {}

    def bind(name: str, kind: str) -> None:
        kinds.setdefault(name, set()).add(kind)

    def targets(node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                bind(sub.id, "defined")

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bind(node.name, "defined")
            elif isinstance(node, ast.ImportFrom):
                kind = "package" if _is_package_import(node) else "outside"
                for alias in node.names:
                    if alias.name != "*":
                        bind(alias.asname or alias.name, kind)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bind(alias.asname or alias.name.partition(".")[0], "outside")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    targets(target)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets(node.target)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                targets(node.target)
                visit(node.body + node.orelse)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        targets(item.optional_vars)
                visit(node.body)
            elif isinstance(node, ast.If):
                visit(node.body + node.orelse)
            elif isinstance(node, ast.Try):
                handlers = [stmt for h in node.handlers for stmt in h.body]
                visit(node.body + handlers + node.orelse + node.finalbody)

    visit(ast.parse(source).body)
    return kinds


def offered_names(module: Any, source: str) -> list[str]:
    """Return the public names a module without ``__all__`` offers.

    A name is offered when it is bound at module level, does not start with
    ``_``, is not a module object, and is not imported from outside this
    package: it is defined in the module, or re-exported from another module of
    the package. A function or class re-exported from the package whose own
    ``__module__`` lies outside it (``Path`` passed along by a sibling) is not
    offered by the package, and neither is a name the source never binds
    unless its object's ``__module__`` is in the package.
    """
    kinds = _module_bindings(source)
    offered = []
    for name, value in vars(module).items():
        if name.startswith("_") or inspect.ismodule(value):
            continue
        bound = kinds.get(name, set())
        owner = getattr(value, "__module__", None)
        named_object = inspect.isclass(value) or inspect.isroutine(value)
        foreign = (
            named_object
            and isinstance(owner, str)
            and owner != PACKAGE
            and not owner.startswith(f"{PACKAGE}.")
        )
        if "defined" in bound:
            offered.append(name)
        elif "package" in bound:
            if not foreign:
                offered.append(name)
        elif not bound and named_object and not foreign:
            offered.append(name)
    return sorted(offered)


#: The classifier's control: a planted module source and the names it must offer.
_CLASSIFIER_SOURCE = (
    "from __future__ import annotations\n"
    "import os\n"
    "from pathlib import Path\n"
    f"from {PACKAGE} import __name__ as package_name\n"
    "LIMIT = 3\n"
    "def act() -> None: ...\n"
    "class Kind: ...\n"
    "_hidden = 1\n"
)
_CLASSIFIER_OFFERS = ["Kind", "LIMIT", "act", "package_name"]


def classifier_control() -> bool:
    """Run :func:`offered_names` over a planted module; return whether it is exact."""
    planted = types.ModuleType(f"{PACKAGE}._parity_control_module")
    exec(compile(_CLASSIFIER_SOURCE, "<parity control>", "exec"), planted.__dict__)  # noqa: S102
    return offered_names(planted, _CLASSIFIER_SOURCE) == _CLASSIFIER_OFFERS


def collect_api(tree: Path) -> dict[str, Any]:
    """Every ``__all__`` of the tree, the names of each module without one, and failures.

    ``exports`` holds each ``__all__`` by module; ``offered`` holds, for every
    module that has no ``__all__``, the public names :func:`offered_names` finds.
    """
    src = tree / "src"
    exports: dict[str, list[str]] = {}
    offered: dict[str, list[str]] = {}
    unimportable: dict[str, str] = {}
    for path in sorted((src / PACKAGE).rglob("*.py")):
        rel = path.relative_to(src).with_suffix("")
        if rel.name == "__main__":
            continue
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        if any(part.startswith("_") for part in parts):
            continue
        name = ".".join(parts)
        try:
            module = importlib.import_module(name)
        except BaseException as exc:  # noqa: BLE001 - a module that exits is reported
            unimportable[name] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        names = getattr(module, "__all__", None)
        if names is not None:
            exports[name] = sorted(str(n) for n in names)
        else:
            offered[name] = offered_names(module, path.read_text(encoding="utf-8"))
    return {
        "exports": exports,
        "offered": offered,
        "unimportable": unimportable,
        "classifier_control": classifier_control(),
    }


def resolve_api(pairs: list[list[str]]) -> list[str]:
    """Return ``module.name`` for every pair that no longer imports."""
    missing = []
    for module_name, name in pairs:
        try:
            module = importlib.import_module(module_name)
            if not hasattr(module, name):
                importlib.import_module(f"{module_name}.{name}")
        except BaseException:  # noqa: BLE001 - any failure to import is the finding
            missing.append(f"{module_name}.{name}")
    return missing


class _CapturedError(Exception):
    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__("parser captured")
        self.parser = parser


def _capture_parser(target: str) -> argparse.ArgumentParser:
    module_name, _, attr = target.partition(":")
    main = getattr(importlib.import_module(module_name), attr)

    def grab(self: argparse.ArgumentParser, *args: Any, **kwargs: Any) -> Any:
        raise _CapturedError(self)

    saved = argparse.ArgumentParser.parse_args, argparse.ArgumentParser.parse_known_args
    argparse.ArgumentParser.parse_args = grab  # type: ignore[method-assign,assignment]
    argparse.ArgumentParser.parse_known_args = grab  # type: ignore[method-assign,assignment]
    try:
        # "--help", never an empty argv: pyfs-fsi called bare runs a coupling
        # step in the working directory. The parse is intercepted before help.
        main(["--help"])
    except _CapturedError as caught:
        return caught.parser
    finally:
        argparse.ArgumentParser.parse_args = saved[0]  # type: ignore[method-assign]
        argparse.ArgumentParser.parse_known_args = saved[1]  # type: ignore[method-assign]
    raise RuntimeError(f"{target} returned without parsing its arguments")


def _spellings(parser: argparse.ArgumentParser, path: str, out: set[str]) -> None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out.add(f"{path} {name}")
                _spellings(sub, f"{path} {name}", out)
            continue
        label = " ".join(action.option_strings) if action.option_strings else None
        for option in action.option_strings:
            out.add(f"{path} {option}")
        if action.choices is not None and not isinstance(action.choices, dict):
            key = action.option_strings[0] if label else f"<{action.dest}>"
            for choice in action.choices:
                out.add(f"{path} {key}={choice}")


def collect_cli(tree: Path) -> dict[str, Any]:
    """Every console script of the tree's pyproject and its accepted spellings."""
    project = tomllib.loads((tree / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]
    spellings: set[str] = set()
    unavailable: dict[str, str] = {}
    for console, target in sorted(scripts.items()):
        try:
            parser = _capture_parser(target)
        except BaseException as exc:  # noqa: BLE001 - reported per console script
            unavailable[console] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        spellings.add(console)
        _spellings(parser, console, spellings)
    return {"targets": dict(scripts), "spellings": sorted(spellings), "unavailable": unavailable}


def collect_scripts(tree: Path) -> dict[str, str]:
    """Every golden-campaign and tier-3 render of the tree, by name."""
    sys.path.insert(0, str(tree / "tests" / "tier1_offline"))
    from test_workflows import GOLDEN_RENDERS, golden_name, render_or_refusal
    from tests.tier3_licensed import offline

    renders: dict[str, str] = {}
    for name, label, build in GOLDEN_RENDERS:
        renders[f"workflows/{golden_name(name, label, build)}"] = render_or_refusal(
            name, label, build
        )
    for matrix in offline.matrices():
        _, rendered = offline.render(matrix)
        for stem, text in rendered.items():
            renders[f"tier3/{matrix.stem}/{stem}"] = text
    return renders


def _workspace_render(matrix: Path, ws: Path, flags: list[str]) -> dict[str, Any]:
    """Use the CLI's dispatchers to plan and write without submitting."""
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import LoadsAssessor, SubmittingExecutor

    # Deliberately use the CLI's private write path without submission.
    try:
        from pyflightstream.run._grouped import planner_for, runner_for
    except ImportError as exc:
        raise RuntimeError(
            "parity requires pyflightstream.run._grouped.runner_for and "
            "pyflightstream.run._grouped.planner_for"
        ) from exc

    from pyflightstream.run.matrix import plan_matrix, run_matrix
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.hpc import HpcProfile, resolve_hpc_profile

    # Compare whole scripts, independent of cost-fit changes to batch boundaries
    # (5469cef0, PFS-2094.014; 496b8720, PFS-2094.015). FR-362 tests the split.
    args = argparse.Namespace(
        batch=1 if "--batch" in flags else None, polar_sweep="--polar-sweep" in flags
    )
    # The CLI catches config refusals and returns 2. Use its library dispatcher
    # so expected exception types and their complete messages survive collection.
    planner_for(args, plan_matrix)(
        matrix,
        CampaignWorkspace(ws),
        name=ws.resolve().name,
        name_from="directory",
        recipes={},
        recipe_registry=workflow_registry(),
    )
    payload = json.loads((ws / "post" / matrix.stem / "plan.json").read_text(encoding="utf-8"))
    grouping = payload.get("grouping")
    reasons = []
    if grouping is not None:
        reasons.extend(grouping["left_out"])
        reasons.extend(
            {"run_id": point["run_id"], "reason": point["error"]}
            for point in payload["points"]
            if point.get("error")
        )
        if not grouping["batches"]:
            return {"scripts": {}, "skipped": reasons}
    profile = resolve_hpc_profile(ws / "inputs") or HpcProfile(
        application_id="flightstream",
        descriptor_format="json",
        descriptor_name="submit.json",
        fields={},
        submit=(),
        path=ws / "inputs" / "hpc" / "parity.toml",
    )
    executor = SubmittingExecutor(profile, values={}, submit=False)
    runner_for(args, run_matrix)(
        matrix,
        CampaignWorkspace(ws),
        name=payload["campaign"],
        recipes={},
        recipe_registry=workflow_registry(),
        executor=executor,
        assess=LoadsAssessor(),
    )
    if grouping is None:
        names = {point["script_name"] for point in payload["points"]}
        paths = sorted(path for path in (ws / "sims").rglob("*.txt") if path.name in names)
    else:
        paths = [ws / job["script"] for job in grouping["batches"]]
    scripts = {}
    for path in paths:
        name = path.relative_to(ws).as_posix()
        if grouping is not None:
            prefix = "BATCH-" if grouping["mode"] == "batch" else "FULL-POLAR-"
            label = path.name if path.name.startswith(prefix) else prefix + path.name
            name = f"{label}/{matrix.name}/{name}"
        # Match the render collectors' logical text on either host newline convention.
        scripts[name] = path.read_text(encoding="utf-8")
    return {"scripts": scripts, "skipped": reasons}


def _workspace_refusal(error: Exception, matrix: Path, ws: Path) -> dict[str, Any]:
    """Keep the refusal message and structured blocked point reasons when available."""
    message = str(error)
    # A config refusal before planning must not read a copied, older plan.
    if not message.startswith("pre-flight blocked"):
        return {"message": message}
    plan_file = ws / "post" / matrix.stem / "plan.json"
    if not plan_file.is_file():
        return {"message": message}
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    reasons = sorted(
        (point["run_id"], point["error"]) for point in plan["points"] if point.get("error")
    )
    if not reasons:
        return {"message": message}
    message = "\n".join([message.splitlines()[0], *(f"  {r}: {e}" for r, e in reasons)])
    return {"message": message, "reasons": [{"run_id": r, "error": e} for r, e in reasons]}


def collect_workspace_scripts(source: Path, ws: Path) -> dict[str, Any]:
    """Collect per-point and grouped scripts from fresh copies at one fixed path."""
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.matrix import MatrixError

    matrices = sorted({*source.glob("*.fs"), *(source / "inputs" / "matrices").rglob("*.fs")})
    scripts: dict[str, str] = {}
    skipped = []
    refused = []
    rendered = []
    attempted: set[str] = set()
    for matrix in matrices:
        relative = matrix.relative_to(source)
        for flags in ([], ["--batch", "2"], ["--polar-sweep"]):
            if flags:
                attempted.add(flags[0])
            if ws.exists():
                shutil.rmtree(ws)
            shutil.copytree(source, ws)
            try:
                result = _workspace_render(ws / relative, ws, flags)
            except (MatrixError, CampaignConfigError) as error:
                refused.append(
                    {
                        "matrix": relative.as_posix(),
                        "mode": flags[0] if flags else "--per-point",
                        **_workspace_refusal(error, ws / relative, ws),
                    }
                )
                continue
            scripts.update(result["scripts"])
            if result["scripts"]:
                rendered.append(
                    {"matrix": relative.as_posix(), "mode": flags[0] if flags else "--per-point"}
                )
            if result["skipped"]:
                skipped.append(
                    {"matrix": relative.as_posix(), "mode": flags[0], "reasons": result["skipped"]}
                )
    return {
        "scripts": scripts,
        "grouped_skipped": skipped,
        "grouped_attempted": sorted(attempted),
        "workspace_refused": refused,
        "workspace_rendered": rendered,
    }


def child(mode: str, tree: Path, out: Path, argument: Path | None) -> int:
    """Run one collector in this process and write its JSON result."""
    _assert_tree(tree)
    result: Any
    if mode == "api":
        result = collect_api(tree)
    elif mode == "resolve":
        assert argument is not None
        result = resolve_api(json.loads(argument.read_text(encoding="utf-8")))
    elif mode == "cli":
        result = collect_cli(tree)
    elif mode == "workspace-scripts":
        assert argument is not None
        request = json.loads(argument.read_text(encoding="utf-8"))
        result = collect_workspace_scripts(Path(request["source"]), Path(request["ws"]))
    elif mode == "scripts":
        result = collect_scripts(tree)
    else:
        raise SystemExit(f"unknown collector {mode!r}")
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0


# --------------------------------------------------------------------------- the parent


def git(*args: str, binary: bool = False) -> Any:
    """Run git in this repository and return its output."""
    done = subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=True,
        capture_output=True,
        # Explicit, and identical to the inherited default: git needs the
        # ambient environment to find its own configuration.
        env=os.environ.copy(),
    )
    return done.stdout if binary else done.stdout.decode("utf-8").strip()


def export(sha: str, tree: Path) -> None:
    """Extract ``EXPORTED`` of one commit into ``tree``, replacing what is there."""
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    # Requirements moved between releases. Git archive refuses an absent
    # pathspec, so select each revision's actual paths before exporting it.
    present = git("ls-tree", "-r", "--name-only", sha).splitlines()
    exported = [
        path
        for path in EXPORTED
        if any(name == path or name.startswith(path + "/") for name in present)
    ]
    if not exported:
        raise ValueError(f"no parity source paths exist at {sha}")
    data = git("archive", "--format=tar", sha, "--", *exported, binary=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(tree, filter="data")


def child_env(tree: Path) -> dict[str, str]:
    """Return the environment in which a child imports ``tree``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(tree / "src"), str(tree)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_child(python: str, mode: str, tree: Path, work: Path, argument: Path | None = None) -> Any:
    """Run one collector in a child interpreter over ``tree`` and return its result."""
    out = work / f"{mode}.json"
    command = [python, str(Path(__file__).resolve()), "--collect", mode, "--tree", str(tree)]
    command += ["--collect-out", str(out)]
    if argument is not None:
        command += ["--collect-arg", str(argument)]
    # 4 h: the research workspace planned in the single, batch and polar-sweep modes
    # measured past 3600 s per tree
    # on 2026-10-04 (the gate leg timed out at 3600 s).
    done = subprocess.run(
        command, cwd=tree, env=child_env(tree), capture_output=True, timeout=14400
    )
    if done.returncode != 0:
        stderr = done.stderr.decode("utf-8", "replace")
        raise SystemExit(f"collector {mode} failed in {tree} (exit {done.returncode}):\n{stderr}")
    return json.loads(out.read_text(encoding="utf-8"))


def run_post(python: str, tree: Path, source: Path, ws: Path, keep: Path) -> dict[str, Any]:
    """Post a fresh copy of ``source`` at ``ws`` with the tree's pyfs-matrix; keep post/."""
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(source, ws, ignore=lambda d, names: ["post"] if Path(d) == source else [])
    project = tomllib.loads((tree / "pyproject.toml").read_text(encoding="utf-8"))
    module_name, _, attr = project["project"]["scripts"][MATRIX_CONSOLE].partition(":")
    code = f"import sys; from {module_name} import {attr} as m; sys.exit(m(sys.argv[1:]))"
    command = [python, "-c", code, "post", "--workspace", str(ws)]
    # 4 h: the research workspace planned in the single, batch and polar-sweep modes
    # measured past 3600 s per tree
    # on 2026-10-04 (the gate leg timed out at 3600 s).
    done = subprocess.run(command, cwd=ws, env=child_env(tree), capture_output=True, timeout=14400)
    if keep.exists():
        shutil.rmtree(keep)
    if (ws / "post").exists():
        shutil.move(str(ws / "post"), str(keep))
    shutil.rmtree(ws)
    return {
        "exit": done.returncode,
        "stderr_tail": done.stderr.decode("utf-8", "replace")[-800:],
    }


def read_tree(root: Path) -> dict[str, bytes]:
    """Return every file under ``root`` by its relative POSIX path."""
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def normalize(name: str, data: bytes) -> bytes:
    """Apply the :data:`POST_NORMALIZE` rules whose glob matches ``name``."""
    rules = [r for r in POST_NORMALIZE if fnmatch.fnmatch(name, r[0])]
    if not rules:
        return data
    text = data.decode("utf-8")
    for _, pattern, replacement, _ in rules:
        text = re.sub(pattern, replacement, text)
    return text.encode("utf-8")


def lf(data: bytes | str) -> Any:
    """Remove CR before LF, the 0.33.0 side's line end on Windows (NFR-32 R4)."""
    if isinstance(data, str):
        return data.replace("\r\n", "\n")
    return data.replace(b"\r\n", b"\n")


def count_cr_files(files: dict[str, bytes]) -> int:
    """Count the text products of ``files`` that hold a CR byte (NFR-32 R3)."""
    return sum(
        1 for n, d in files.items() if Path(n).suffix.lower() in TEXT_SUFFIXES and b"\r" in d
    )


def release_version(text: str) -> tuple[int, ...]:
    """Return the numeric version a tag or a version string names: ``v0.39.0`` is (0, 39, 0)."""
    found = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if found is None:
        raise ValueError(f"{text!r} names no release version")
    return tuple(int(part) for part in found.groups())


def in_scope(named: dict[str, str], base_version: str | None) -> bool:
    """Whether a named entry may name a difference against ``base_version`` (``since``)."""
    if base_version is None:
        return True
    return release_version(base_version) < release_version(named["since"])


def changed_lines(old: str, new: str) -> list[str]:
    """Return the removed and added lines between two texts."""
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
    return [line[1:] for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def appends_one_column(old: str, new: str, column: str, cells: str) -> bool:
    """Whether ``new`` is ``old`` with one column ``column`` appended last, and nothing else.

    The header must be the old header and ``,column`` (the CSV form), or the
    old header and ``column`` right-justified in one more field of
    :data:`LEGACY_FIELD` characters (the super file's ``legacy_polar`` form);
    every other line the old line and one cell, in the same form, that matches
    ``cells`` whole; the line count and the final line end the same.
    """
    before, after = old.splitlines(), new.splitlines()
    if not before or len(before) != len(after) or old.endswith("\n") != new.endswith("\n"):
        return False
    if after[0] == f"{before[0]},{column}":
        split = _csv_cell
    elif after[0] == before[0] + column.rjust(LEGACY_FIELD):
        split = _legacy_cell
    else:
        return False
    for was, now in zip(before[1:], after[1:], strict=True):
        head, cell = split(now)
        if cell is None or head != was or not re.fullmatch(cells, cell):
            return False
    return True


#: The width of each field of a super file in the ``legacy_polar`` form.
LEGACY_FIELD = 16


def _fields(line: str, legacy: bool) -> list[str]:
    """Split one line of a product into its cells, CSV or ``legacy_polar`` fixed width."""
    if not legacy:
        return line.split(",")
    return [line[i : i + LEGACY_FIELD].strip(" ") for i in range(0, len(line), LEGACY_FIELD)]


def inserts_and_fills(old: str, new: str, inserted: str, filled: str, cells: str) -> bool:
    """Whether ``new`` is ``old`` with columns inserted and NA cells filled, and nothing else.

    Every column of ``new`` that ``old`` lacks must match ``inserted`` whole (an
    empty ``inserted`` admits none), and its every cell be ``NA`` or match
    ``cells``. Taken out, the header must be ``old``'s, in its order. A cell of
    a column matching ``filled`` may go from ``NA`` to a cell matching
    ``cells``; every other cell is the old one. The line count and the final
    line end are the same, and the two texts differ.
    """
    before, after = old.splitlines(), new.splitlines()
    if not before or len(before) != len(after) or old.endswith("\n") != new.endswith("\n"):
        return False
    legacy = "," not in before[0] and len(before[0]) % LEGACY_FIELD == 0
    if legacy and len(after[0]) % LEGACY_FIELD:
        return False
    head_old, head_new = _fields(before[0], legacy), _fields(after[0], legacy)
    kept = [i for i, name in enumerate(head_new) if name in head_old]
    added = [i for i, name in enumerate(head_new) if name not in head_old]
    if [head_new[i] for i in kept] != head_old or len(set(head_new)) != len(head_new):
        return False
    if added and not (inserted and all(re.fullmatch(inserted, head_new[i]) for i in added)):
        return False
    for was, now in zip(before[1:], after[1:], strict=True):
        old_cells, new_cells = _fields(was, legacy), _fields(now, legacy)
        if len(old_cells) != len(head_old) or len(new_cells) != len(head_new):
            return False
        if not all(re.fullmatch(rf"NA|{cells}", new_cells[i]) for i in added):
            return False
        for name, cell, i in zip(head_old, old_cells, kept, strict=True):
            fresh = new_cells[i]
            if fresh == cell:
                continue
            if not (re.fullmatch(filled, name) and cell == "NA" and re.fullmatch(cells, fresh)):
                return False
    return old != new


def _csv_cell(line: str) -> tuple[str, str | None]:
    """Split a CSV line into everything before its last cell and that cell."""
    head, comma, cell = line.rpartition(",")
    return head, cell if comma else None


def _legacy_cell(line: str) -> tuple[str, str | None]:
    """Split a fixed-width line into everything before its last field and that field's cell."""
    head, field = line[:-LEGACY_FIELD], line[-LEGACY_FIELD:]
    return head, field.lstrip(" ") if len(field) == LEGACY_FIELD else None


def _toggle_correction(old: str, new: str) -> bool:
    """Accept only ENABLE to DISABLE replacements of the same toggle commands."""
    removed, added = [], []
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        if line.startswith("- "):
            removed.append(line[2:])
        elif line.startswith("+ "):
            added.append(line[2:])
    return (
        bool(removed)
        and len(removed) == len(added)
        and all(
            before.endswith(" ENABLE") and after == before.removesuffix("ENABLE") + "DISABLE"
            for before, after in zip(removed, added, strict=True)
        )
    )


def _within_printed_rounding(old: str, new: str, *, coarser: bool) -> bool:
    """Keep text identical; admit finite numbers only within the writer's precision."""
    if old == new:
        return True
    # The base CSV funnel rounded floats to five decimal places. Integers
    # and text were written literally, so their spelling implies no lost digits.
    if not re.fullmatch(r"-?\d+\.\d{5}", old):
        return False
    if not re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", new):
        return False
    try:
        before, after = Decimal(old), Decimal(new)
        if not before.is_finite() or not after.is_finite():
            return False
        if coarser:
            quantum = max(
                Decimal(1).scaleb(int(before.as_tuple().exponent)),
                Decimal(1).scaleb(int(after.as_tuple().exponent)),
            )
            return before.quantize(quantum, rounding=ROUND_HALF_EVEN) == after.quantize(
                quantum, rounding=ROUND_HALF_EVEN
            )
        return abs(before - after) <= Decimal("0.000005")
    except (InvalidOperation, ValueError):
        return False


def _csv_rounding(old: str, new: str, inserted: str = "", *, coarser: bool = False) -> bool:
    """Compare rows in order, allowing only named columns and printed rounding."""
    before, after = list(csv.reader(io.StringIO(old))), list(csv.reader(io.StringIO(new)))
    if not before or len(before) != len(after):
        return False
    old_header, new_header = before[0], after[0]
    if len(set(old_header)) != len(old_header) or len(set(new_header)) != len(new_header):
        return False
    if [column for column in new_header if column in old_header] != old_header:
        return False
    if any(
        not inserted or not re.fullmatch(inserted, column)
        for column in new_header
        if column not in old_header
    ):
        return False
    indexes = [new_header.index(column) for column in old_header]
    kind_columns = [column for column in new_header if column not in old_header]
    if inserted:
        # FR-419 adds one kind for each existing value/provenance pair.
        # The old lossy values cannot identify an ambiguous kind, but the
        # frozen encoding still bounds its domain (settings_table.VALUE_KINDS).
        expected = {
            column.removesuffix("_value") + "_kind"
            for column in old_header
            if re.fullmatch(r"f\d+_value", column)
        }
        if set(kind_columns) != expected or any(
            column.removesuffix("_kind") + "_prov" not in old_header for column in kind_columns
        ):
            return False
    kind_indexes = [new_header.index(column) for column in kind_columns]
    for old_row, new_row in zip(before[1:], after[1:], strict=True):
        if len(old_row) != len(old_header) or len(new_row) != len(new_header):
            return False
        if any(
            new_row[index] not in {"1", "2", "3", "4", "5", "6", "NA"} for index in kind_indexes
        ):
            return False
        if not all(
            _within_printed_rounding(cell, new_row[index], coarser=coarser)
            for cell, index in zip(old_row, indexes, strict=True)
        ):
            return False
    return True


def name_difference(
    kind: str,
    name: str,
    old: str | None,
    new: str | None,
    defined: set[str],
    base_version: str | None = None,
) -> dict[str, Any]:
    """Describe one difference and attach the requirement that states it, if any.

    ``base_version`` is the base tree's version; an entry whose ``since`` is not newer
    than it names nothing (:func:`in_scope`). None leaves every entry in scope.
    """
    entry: dict[str, Any] = {"state": "missing" if new is None else "changed"}
    lines = changed_lines(old or "", new or "") if old is not None and new is not None else []
    if lines:
        entry["first_changed_lines"] = lines[:6]
        entry["changed_line_count"] = len(lines)
    for named in NAMED_DIFFERENCES:
        if named["kind"] != kind or not fnmatch.fnmatch(name, named["pattern"]):
            continue
        if not in_scope(named, base_version):
            continue
        if new is None or (old is None) != bool(named.get("added")):
            continue
        if "old_text" in named and (old, new) != (named["old_text"], named["new_text"]):
            continue
        pattern = named.get("lines")
        # A difference with NO changed line (a trailing newline added or
        # removed) is not one a lines-only entry states: all() over nothing
        # is True, so it used to be named under any requirement.
        if pattern and (not lines or not all(re.search(pattern, line) for line in lines)):
            continue
        block = named.get("block")
        if block and not re.fullmatch(block, "\n".join(lines)):
            continue
        if named.get("directed_toggles") and not _toggle_correction(old or "", new):
            continue
        if named.get("csv_rounding") and not _csv_rounding(
            old or "",
            new,
            named.get("csv_inserted_columns", ""),
            coarser=named["csv_rounding"] == "coarser",
        ):
            continue
        lacks = named.get("release_lacks")
        if lacks and re.search(lacks, new):
            continue
        has = named.get("release_has")
        if has and not re.search(has, new):
            continue
        base_lacks = named.get("base_lacks")
        if base_lacks and (old is None or re.search(base_lacks, old)):
            continue
        appended = named.get("appended_column")
        if appended and not appends_one_column(old or "", new, appended, named["cells"]):
            continue
        if "inserted_columns" in named and not inserts_and_fills(
            old or "", new, named["inserted_columns"], named["filled_columns"], named["cells"]
        ):
            continue
        if named["requirement"] not in defined:
            entry["unnamed_because"] = f"{named['requirement']} is not defined in the release SRS"
            continue
        also = named.get("also_requires")
        if also and also not in defined:
            entry["unnamed_because"] = f"{also} is not defined in the release SRS"
            continue
        entry["requirement"] = named["requirement"]
        entry["why"] = named["why"]
        break
    return entry


def compare_texts(
    kind: str,
    key: str,
    base: dict[str, str],
    release: dict[str, str],
    defined: set[str],
    base_version: str | None = None,
) -> dict[str, Any]:
    """Compare every base item with its release counterpart, naming each difference."""
    differing = []
    cr_removed = []
    for name in sorted(base):
        new = release.get(name)
        old = lf(base[name])
        if old != base[name]:
            cr_removed.append({key: name, "requirement": LF_REQUIREMENT})
        if new == old:
            continue
        differing.append(
            {key: name, **name_difference(kind, name, old, new, defined, base_version)}
        )
    added = [
        {key: name, **name_difference(kind, name, None, release[name], defined, base_version)}
        for name in sorted(set(release) - set(base))
    ]
    return {
        "checked": len(base),
        "compared": sorted(base),
        "differing": differing,
        "added_at_release": sorted(set(release) - set(base)),
        "added_named": [entry for entry in added if "requirement" in entry],
        "cr_removed": cr_removed,
    }


def text_control(
    kind: str,
    key: str,
    base: dict[str, str],
    planted: str,
    defined: set[str],
    base_version: str | None = None,
) -> str | None:
    """Plant ``planted`` at the end of the first base item; return it if caught alone.

    The release side of :func:`compare_texts` is compared as written and the
    base side with CR removed before LF (NFR-32 R4), so the control mutates the
    base AS COMPARED. Mutating the raw base would make every CRLF file of a
    0.33 base on Windows differ beside the victim, and the control would fail
    for a reason that is not the comparator's blindness.
    """
    victim = sorted(base)[0]
    compared = {name: lf(text) for name, text in base.items()}
    mutated = {**compared, victim: compared[victim] + planted}
    probe = compare_texts(kind, key, base, mutated, defined, base_version)["differing"]
    return victim if [d[key] for d in probe if "requirement" not in d] == [victim] else None


def srs_ids(tree: Path) -> set[str]:
    """Return requirement ids defined by the tree's retained specification pages.

    A box, not a mention: an id cited in passing on any page used to count as
    defined, so a named entry stayed live for a requirement the release no longer states.
    """
    pages = (*requirement_pages(tree / REQUIREMENTS_DIR), *(tree / "docs/srs").rglob("*.md"))
    sources = {p: p.read_text(encoding="utf-8", errors="replace") for p in pages}
    text = "\n".join(sources.values())
    legacy = re.findall(r'!!! requirement "((?:FR|NFR|IR|DR|AD|CR|SR|QR)-\d+[a-z]?)\b', text)
    compact = [
        row["uid"]
        for path, source in sources.items()
        if path.parent == tree / REQUIREMENTS_DIR or "| UID | Parent |" in source
        for row in requirement_rows(source, str(path))
    ]
    detail = [row["uid"] for row in read_l3(tree)]  # L3 rows live beside the tests (0.43.0)
    return set(legacy + compact + detail)


def api_pairs(api: dict[str, Any], key: str = "exports") -> list[list[str]]:
    """Flatten the collected ``exports`` (or ``offered``) into ``[module, name]`` pairs."""
    return [[m, n] for m, names in sorted(api[key].items()) for n in names]


def as_text(files: dict[str, bytes]) -> dict[str, str]:
    """Decode post products for comparison; a non-text file compares by its digest."""
    out = {}
    for name, data in files.items():
        data = normalize(name, data)
        if Path(name).suffix.lower() in TEXT_SUFFIXES:
            out[name] = data.decode("utf-8", "replace")
        else:
            out[name] = "sha256:" + hashlib.sha256(data).hexdigest()
    return out


def _compare_workspace_refusals(
    scripts: dict[str, Any],
    base: dict[str, Any],
    release: dict[str, Any],
    versions: dict[str, str],
) -> None:
    """List refused matrix/mode pairs and add asymmetric or changed reasons to differing."""
    observations = {"base": base, "release": release}
    indexed = {}
    scripts["workspace_refused"] = []
    for side, collected in observations.items():
        rows = collected.get("workspace_refused", [])
        scripts["workspace_refused"].extend({**row, "version": versions[side]} for row in rows)
        indexed[side] = {(row["matrix"], row["mode"]): row for row in rows}
    for matrix, mode in sorted(indexed["base"].keys() | indexed["release"].keys()):
        before = indexed["base"].get((matrix, mode))
        after = indexed["release"].get((matrix, mode))
        # With per-row reasons, the heading does not define equality. Without
        # them (a refusal before planning), compare the entire config message.
        old = _refusal_reasons(before)
        new = _refusal_reasons(after)
        if before is not None and after is not None and old == new:
            continue
        scripts["differing"].append(
            {
                "name": f"workspace/{matrix} ({mode})",
                "matrix": matrix,
                "mode": mode,
                "state": "workspace_refused",
                "base": before["message"] if before is not None else None,
                "release": after["message"] if after is not None else None,
            }
        )


def _compare_left_out(
    scripts: dict[str, Any],
    base: dict[str, Any],
    release: dict[str, Any],
    defined: set[str],
    base_version: str | None = None,
) -> None:
    """Add every changed left-out reason of the grouped plan to differing, named when stated.

    Each side's ``grouped_skipped`` holds the rows the grouped plan left out (``sim``) and the
    points it blocked (``run_id``), each with its reason. The identity is (matrix, mode, kind,
    id) and the UNION of both sides is compared: a reason that changed, one the release added
    and one it dropped are differences that only a named entry (kind ``left_out``) can excuse
    (FR-421 R2).
    """

    def indexed(collected: dict[str, Any]) -> dict[tuple[str, str, str, str], str]:
        found = {}
        for group in collected.get("grouped_skipped", []):
            for row in group["reasons"]:
                kind, ident = ("sim", row["sim"]) if "sim" in row else ("point", row.get("run_id"))
                if ident is not None:
                    found[(group["matrix"], group["mode"], kind, ident)] = row["reason"]
        return found

    before, after = indexed(base), indexed(release)
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        if new == old:
            continue
        matrix, mode, kind, ident = key
        name = f"workspace/{matrix} ({mode}) left out {kind} {ident}"
        scripts["differing"].append(
            {"name": name, **name_difference("left_out", name, old, new, defined, base_version)}
        )


def _refusal_reasons(refusal: dict[str, Any] | None) -> list[Any]:
    """Compare per-point errors when present, otherwise the complete config refusal."""
    if refusal is None:
        return []
    if "reasons" in refusal:
        return sorted((row["run_id"], row["error"]) for row in refusal["reasons"])
    message = refusal["message"]
    # Message-regex fallback for refusals without structured plan.json reasons.
    lines = message.splitlines()
    if len(lines) > 1 and re.match(r"\s*\S+/sim_[^:]+:", lines[1]):
        rows = re.split(r"(?m)(?=^[ \t]*\S+/sim_[^:]+:)", "\n".join(lines[1:]))
        return sorted(row.rstrip("\n") for row in rows if row)
    return [message]


def parity(args: argparse.Namespace) -> dict[str, Any]:
    """Measure both trees and return the receipt."""
    base_sha = git("rev-parse", f"{args.base}^{{commit}}")
    release_sha = git("rev-parse", f"{args.release}^{{commit}}")
    # The base tree's OWN version scopes the named differences (``since``),
    # read from its pyproject so a sha or a branch works as well as a tag.
    stated = re.search(r'(?m)^version = "([^"]+)"', git("show", f"{base_sha}:pyproject.toml"))
    if stated is None:
        raise SystemExit(f"the base {args.base} states no version in its pyproject.toml")
    base_version = stated.group(1)
    try:
        committed = git("show", f"{release_sha}:{SCRIPT}", binary=True)
    except subprocess.CalledProcessError:
        committed = None
    running = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    failures: list[str] = []
    if committed is None:
        failures.append(f"{SCRIPT} is not committed at the release {release_sha[:8]}")
    elif committed.replace(b"\r\n", b"\n") != running:
        failures.append(f"the running {SCRIPT} differs from its revision at {release_sha[:8]}")

    temp = Path(tempfile.mkdtemp(prefix="pfs-parity-", dir=args.temp))
    tree, ws = temp / "tree", temp / "ws"
    python = args.python
    workspace_request = temp / "workspace-request.json"
    workspace_request.write_text(
        json.dumps({"source": str(args.workspace), "ws": str(ws)}), encoding="utf-8"
    )
    try:
        # The base tree first, then the release tree AT THE SAME PATH, so no
        # absolute path in a render or a product can differ between them.
        export(base_sha, tree)
        (temp / "base").mkdir()
        api_base = run_child(python, "api", tree, temp / "base")
        cli_base = run_child(python, "cli", tree, temp / "base")
        scripts_base = run_child(python, "scripts", tree, temp / "base")
        workspace_base = run_child(
            python, "workspace-scripts", tree, temp / "base", workspace_request
        )
        overlap = set(scripts_base) & set(workspace_base["scripts"])
        assert not overlap, f"base workspace script names overlap render keys: {sorted(overlap)}"
        scripts_base.update(workspace_base["scripts"])
        post_run_base = run_post(python, tree, args.workspace, ws, temp / "post-base")

        export(release_sha, tree)
        (temp / "release").mkdir()
        listed = api_pairs(api_base)
        offered = api_pairs(api_base, "offered")
        listed_pairs = [p for p in listed if ".".join(p) not in API_EXEMPT]
        offered_pairs = [p for p in offered if ".".join(p) not in API_EXEMPT]
        pairs = [*listed_pairs, *offered_pairs]
        exempt = [f"{m}.{n}" for m, n in [*listed, *offered] if f"{m}.{n}" in API_EXEMPT]
        # The second planted name sits in the first module without __all__, so
        # the path that reads such modules is itself shown able to fail.
        planted_module = min(api_base["offered"], default=PACKAGE)
        planted = [*pairs, [PACKAGE, PLANTED_NAME], [planted_module, PLANTED_NAME]]
        request = temp / "release" / "pairs.json"
        request.write_text(json.dumps(planted), encoding="utf-8")
        missing_api = run_child(python, "resolve", tree, temp / "release", request)
        cli_release = run_child(python, "cli", tree, temp / "release")
        scripts_release = run_child(python, "scripts", tree, temp / "release")
        workspace_release = run_child(
            python, "workspace-scripts", tree, temp / "release", workspace_request
        )
        overlap = set(scripts_release) & set(workspace_release["scripts"])
        assert not overlap, f"release workspace script names overlap render keys: {sorted(overlap)}"
        scripts_release.update(workspace_release["scripts"])
        post_run_release = run_post(python, tree, args.workspace, ws, temp / "post-release")
        defined = srs_ids(tree)

        post_base_raw = read_tree(temp / "post-base")
        post_release_raw = read_tree(temp / "post-release")
        post_base = as_text(post_base_raw)
        post_release = as_text(post_release_raw)
    finally:
        if args.keep:
            print(f"kept {temp}")
        else:
            shutil.rmtree(temp, ignore_errors=True)

    controls: list[str] = []
    planted_key = f"{PACKAGE}.{PLANTED_NAME}"
    planted_offered = f"{planted_module}.{PLANTED_NAME}"
    if planted_key in missing_api:
        controls.append("api: a name no module exports was reported missing")
    if planted_module != PACKAGE and planted_offered in missing_api:
        controls.append(
            f"api: a name {planted_module} (no __all__) lacks at the release was reported missing"
        )
    if api_base.get("classifier_control") is True:
        controls.append(
            "api: the reader of a module without __all__ offered exactly its defined and "
            "package names of a planted module, and none of its outside imports"
        )
    missing_api = [m for m in missing_api if m not in (planted_key, planted_offered)]
    offered_keys = {f"{m}.{n}" for m, n in offered_pairs}
    api = {
        "checked": len(pairs),
        "checked_from_all": len(listed_pairs),
        "checked_without_all": len(offered_pairs),
        "modules": len(api_base["exports"]),
        "modules_without_all": len(api_base["offered"]),
        "missing": missing_api,
        "missing_without_all": [m for m in missing_api if m in offered_keys],
        "exempt": {name: API_EXEMPT[name] for name in exempt},
        "unimportable_at_base": api_base["unimportable"],
    }

    base_spellings, release_spellings = set(cli_base["spellings"]), set(cli_release["spellings"])
    planted_flag = f"{MATRIX_CONSOLE} {PLANTED_FLAG}"
    # The control goes through the same comparison the report uses, so a broken
    # comparison cannot leave it true.
    if planted_flag in cli_refused(base_spellings | {planted_flag}, release_spellings):
        controls.append("cli: a flag no parser has was reported refused")
    cli = {
        "checked": len(base_spellings),
        "missing": cli_refused(base_spellings, release_spellings),
        "added_at_release": len(release_spellings - base_spellings),
        "unavailable_at_base": cli_base["unavailable"],
        "unavailable_at_release": cli_release["unavailable"],
    }

    scripts = compare_texts("scripts", "name", scripts_base, scripts_release, defined, base_version)
    workspace_names = set(workspace_base["scripts"]) | set(workspace_release["scripts"])
    scripts["workspace_compared"] = len(workspace_names.intersection(scripts["compared"]))
    _compare_workspace_refusals(
        scripts, workspace_base, workspace_release, {"base": args.base, "release": args.release}
    )
    _compare_left_out(scripts, workspace_base, workspace_release, defined, base_version)
    scripts["workspace_coverage"] = {
        "rendered": [
            {**row, "version": version}
            for collected, version in (
                (workspace_base, args.base),
                (workspace_release, args.release),
            )
            for row in collected.get("workspace_rendered", [])
        ],
        "refused": scripts["workspace_refused"],
    }
    if args.workspace is not None and scripts["workspace_compared"] == 0:
        failures.append(
            f"no workspace scripts were compared; workspace_refused: {scripts['workspace_refused']}"
        )
    scripts["grouped_skipped"] = {
        "base": workspace_base["grouped_skipped"],
        "release": workspace_release["grouped_skipped"],
    }
    scripts["grouped_attempted"] = {
        "base": workspace_base["grouped_attempted"],
        "release": workspace_release["grouped_attempted"],
    }
    scripts["allow_no_grouped"] = args.allow_no_grouped
    for mode, prefix in (("--batch", "BATCH-"), ("--polar-sweep", "FULL-POLAR-")):
        attempted = any(mode in modes for modes in scripts["grouped_attempted"].values())
        if attempted and not any(name.startswith(prefix) for name in scripts["compared"]):
            reasons = {
                side: [row for row in rows if row["mode"] == mode]
                for side, rows in scripts["grouped_skipped"].items()
            }
            if not args.allow_no_grouped:
                failures.append(
                    f"no {mode} grouped scripts were compared; grouped_skipped: {reasons}"
                )
    post = compare_texts("post", "file", post_base, post_release, defined, base_version)
    post["workspace"] = str(args.workspace)
    post["cr_normalised"] = True
    post["cr_in_release"] = count_cr_files(post_release_raw)
    post["cr_in_base"] = count_cr_files(post_base_raw)
    post["exit"] = {"base": post_run_base["exit"], "release": post_run_release["exit"]}
    for side, run in (("base", post_run_base), ("release", post_run_release)):
        if run["exit"] != 0:
            post[f"stderr_{side}"] = run["stderr_tail"]
    post["normalized"] = [
        {"files": g, "pattern": p, "replacement": r, "why": why} for g, p, r, why in POST_NORMALIZE
    ]

    # The two text controls: one changed line of a real render and one changed
    # byte of a real product must each come back differing and unnamed.
    if scripts_base:
        victim = text_control("scripts", "name", scripts_base, "PARITY CONTROL\n", defined)
        if victim:
            controls.append(f"scripts: a changed line of {victim} was reported unnamed")
    if post_base:
        victim = text_control("post", "file", post_base, "\x00", defined)
        if victim:
            controls.append(f"post: a changed byte of {victim} was reported unnamed")

    if post_release_raw:
        victim = next(iter(sorted(post_release_raw)))
        planted_cr = {**post_release_raw, "planted.csv": post_release_raw[victim] + b"\r\n"}
        if count_cr_files(planted_cr) == post["cr_in_release"] + 1:
            controls.append("post: a planted CR in a release product was counted")
    if post["cr_in_release"]:
        failures.append(f"{post['cr_in_release']} release products hold a CR byte (NFR-32)")
    if not pairs:
        failures.append("no public name was compared")
    if missing_api:
        failures.append(f"{len(missing_api)} public names of the base no longer import")
    if not base_spellings or cli["missing"]:
        failures.append(f"{len(cli['missing'])} console spellings of the base are refused")
    if cli_release["unavailable"]:
        failures.append(
            f"console scripts do not build at the release: {cli_release['unavailable']}"
        )
    for kind, block, key in (("scripts", scripts, "name"), ("post", post, "file")):
        if not block["checked"]:
            failures.append(f"no {kind} were compared")
        loose = [d[key] for d in block["differing"] if "requirement" not in d]
        if loose:
            failures.append(f"{len(loose)} {kind} differ without a named requirement: {loose[:3]}")
    if post["exit"] != {"base": 0, "release": 0}:
        failures.append(f"post exited {post['exit']}")
    if len(controls) != CONTROLS:
        failures.append(f"the planted controls caught {len(controls)} of {CONTROLS}")

    return {
        "script": SCRIPT,
        "script_sha256": hashlib.sha256(committed).hexdigest() if committed is not None else None,
        "base_ref": args.base,
        "base_sha": base_sha,
        "release_ref": args.release,
        "release_sha": release_sha,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "api": api,
        "cli": cli,
        "scripts": scripts,
        "post": post,
        "named_differences": NAMED_DIFFERENCES,
        "controls": {"caught": f"caught {len(controls)} of {CONTROLS}", "detail": controls},
        "failures": failures,
        "verdict": "PARITY: FAIL" if failures else "PARITY: PASS",
    }


def main(argv: list[str] | None = None) -> int:
    """Compare the base and the release trees and write the parity receipt."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--base",
        default="v0.32.0",
        help=(
            "the release tag to compare against (default: v0.32.0, the parity baseline, "
            "not the previous release)"
        ),
    )
    parser.add_argument("--release", default="HEAD", help="the release commit")
    parser.add_argument("--workspace", type=Path, help="a recorded campaign workspace to post")
    parser.add_argument("--out", type=Path, help="where the JSON receipt is written")
    parser.add_argument("--python", default=sys.executable, help="interpreter for both trees")
    parser.add_argument("--temp", default=None, help="parent of the one temporary folder")
    parser.add_argument("--keep", action="store_true", help="keep the temporary folder")
    parser.add_argument(
        "--allow-no-grouped",
        action="store_true",
        help="allow attempted grouped modes with no compared scripts; recorded in the receipt",
    )
    parser.add_argument("--collect", help=argparse.SUPPRESS)
    parser.add_argument("--tree", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--collect-out", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--collect-arg", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.collect:
        return child(args.collect, args.tree, args.collect_out, args.collect_arg)
    if args.workspace is None or args.out is None:
        parser.error("--workspace and --out are required")
    if not (args.workspace / "runs.json").is_file():
        parser.error(f"{args.workspace} is not a recorded workspace (no runs.json)")

    receipt = parity(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"api {receipt['api']['checked']} names, cli {receipt['cli']['checked']} spellings, "
        f"scripts {receipt['scripts']['checked']}, post {receipt['post']['checked']} files, "
        f"{receipt['controls']['caught']}"
    )
    for failure in receipt["failures"]:
        print(f"FAIL: {failure}")
    print(receipt["verdict"])
    return 0 if receipt["verdict"] == "PARITY: PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
