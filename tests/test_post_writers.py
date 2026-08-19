"""Tier 1: VTK and Tecplot probe-data writers, byte-exact goldens.

Pipeline role: quality gate on the two files the post-processing layer
writes today. Two claims are held here and they are different claims:
the NUMBERS are byte-exact against committed goldens, and since
PFS-2012.11 the MEANING of those numbers travels with them.

THE REPRODUCTION (PFS-2012.11, FR-31). Until 2026-08-19 both writers
took coordinates, fields and a title string and nothing else::

    write_vtk_points(path, points, fields)

so the file said what was measured and nothing at all about the solver
settings that produced it. Every flag had to be recovered by joining the
file back to ``runs.json`` through a run identifier the file did not
carry either, and a file that needs another file is the opposite of
self-contained: separate the two and the numbers survive while their
meaning does not.

Both writers now take a required ``provenance`` keyword and return the
PAIR ``(output, record)``: the record is a JSON sidecar under the same
stem, carrying the run identity and one entry per flag of
``FLAG_SPECS`` with its value, its provenance and its citation. An
unknown flag is PRESENT and named unknown, never omitted, because
"nobody has established this for this build" and "this flag does not
exist" are different facts and the file has to be able to say which one
it means.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.farfield import lattice_dataset
from pyflightstream.post import (
    OutputProvenance,
    dataset_to_points,
    write_tecplot_points,
    write_vtk_points,
)
from pyflightstream.post.writers import PROVENANCE_SCHEMA, settings_records
from pyflightstream.probes import ProbeLattice
from pyflightstream.script import Script, helpers
from pyflightstream.script.solver_setup import FLAG_SPECS

GOLDENS = Path(__file__).parent / "goldens"

POINTS = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
FIELDS = {
    "cp": np.array([1.0, -0.5]),
    "vel": np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]),
}


def make_provenance(run_id: str = "matrix/sim_8001/a+00.0") -> OutputProvenance:
    """A provenance record from a real snapshot, not a hand-built one.

    The snapshot comes from ``helpers.solver_settings`` so the record
    under test is the one a campaign actually produces: on a bare
    26.120 call one flag is explicit, seven carry a documented default
    and the rest are honestly unknown.
    """
    script = Script(version="26.120")
    setup = helpers.solver_settings(script, velocity=30.0)
    return OutputProvenance(run_id=run_id, campaign="matrix", setup=setup)


WRITERS = [(write_vtk_points, ".vtk"), (write_tecplot_points, ".dat")]


# --- the numbers: unchanged, byte-exact -------------------------------------


def test_vtk_writer_matches_the_golden(tmp_path):
    written, _record = write_vtk_points(
        tmp_path / "probes.vtk", POINTS, FIELDS, provenance=make_provenance()
    )
    golden = (GOLDENS / "planar_probes.vtk").read_text(encoding="utf-8")
    assert written.read_text(encoding="utf-8") == golden


def test_tecplot_writer_matches_the_golden(tmp_path):
    written, _record = write_tecplot_points(
        tmp_path / "probes.dat", POINTS, FIELDS, provenance=make_provenance()
    )
    golden = (GOLDENS / "planar_probes.dat").read_text(encoding="utf-8")
    assert written.read_text(encoding="utf-8") == golden


def test_writers_validate_shapes_didactically(tmp_path):
    provenance = make_provenance()
    with pytest.raises(ValueError, match=r"shape \(n, 3\)"):
        write_vtk_points(tmp_path / "bad.vtk", np.zeros((3, 2)), provenance=provenance)
    with pytest.raises(ValueError, match="one scalar or one 3-vector"):
        write_tecplot_points(
            tmp_path / "bad.dat", POINTS, {"cp": np.zeros(3)}, provenance=provenance
        )


def test_farfield_dataset_flattens_into_the_writers(tmp_path):
    lattice = ProbeLattice(
        tip_radius=2.0,
        stations=(0.5,),
        ring_edges=(0.5, 1.0),
        n_psi=8,
    )
    shape = (1, 1, 8)
    ds = lattice_dataset(lattice, {"u": np.full(shape, 30.0)})
    points, fields = dataset_to_points(ds)
    assert points.shape == (8, 3)
    # First sample: station 0.5, ring center 0.75, psi 0, tip radius 2:
    # x = 1.0, y = 0.0, z = 1.5 (z up at psi = 0).
    assert points[0] == pytest.approx([1.0, 0.0, 1.5])
    assert fields["u"] == pytest.approx(np.full(8, 30.0))
    provenance = make_provenance()
    vtk, vtk_record = write_vtk_points(tmp_path / "ring.vtk", points, fields, provenance=provenance)
    dat, dat_record = write_tecplot_points(
        tmp_path / "ring.dat", points, fields, provenance=provenance
    )
    assert vtk.is_file() and dat.is_file()
    assert vtk_record.is_file() and dat_record.is_file()
    assert vtk_record != dat_record, (
        "two exports of one survey share a stem, so a record named for the STEM "
        "would be one file describing both; this call is why the suffix is appended"
    )


# --- the meaning: PFS-2012.11 ----------------------------------------------


@pytest.mark.parametrize(("writer", "suffix"), WRITERS)
def test_a_writer_refuses_a_call_that_carries_no_settings_record(writer, suffix, tmp_path):
    """The keyword is REQUIRED, so no path writes an orphan file.

    A default would have made the record opt-in, and an opt-in record is
    absent exactly where it matters: the run that nobody thought about
    while writing the call.
    """
    with pytest.raises(TypeError, match="provenance"):
        writer(tmp_path / f"orphan{suffix}", POINTS, FIELDS)
    assert not (tmp_path / f"orphan{suffix}").exists(), (
        "the refused call still created the file it refused to describe"
    )


@pytest.mark.parametrize(("writer", "suffix"), WRITERS)
def test_the_written_pair_lets_the_file_be_read_alone(writer, suffix, tmp_path):
    """The whole point: delete runs.json and the file still means this.

    The record carries the run identity, the FlightStream version it was
    built for, and the name of the file it describes, so a reader holding
    the two files and nothing else can say where the numbers came from.
    """
    destination = tmp_path / f"probes{suffix}"
    written, record = writer(destination, POINTS, FIELDS, provenance=make_provenance())

    assert written == destination
    assert record == destination.with_name(destination.name + ".provenance.json")
    assert record.is_file()

    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["provenance_schema"] == PROVENANCE_SCHEMA
    assert payload["run_id"] == "matrix/sim_8001/a+00.0"
    assert payload["campaign"] == "matrix"
    assert payload["fs_version"] == "26.120"
    assert payload["describes"] == destination.name


@pytest.mark.parametrize(("writer", "suffix"), WRITERS)
def test_the_record_carries_every_flag_with_unknown_named(writer, suffix, tmp_path):
    """All of them, and the unknown ones by name rather than by absence.

    On a bare 26.120 call fifty-seven of the sixty-five flags are
    unknown. Omitting them would leave a reader unable to tell a flag
    nobody has established from a flag that does not exist, which is the
    distinction the snapshot was built to keep (FR-31, FR-22c).
    """
    destination = tmp_path / f"probes{suffix}"
    _written, record = writer(destination, POINTS, FIELDS, provenance=make_provenance())
    payload = json.loads(record.read_text(encoding="utf-8"))

    flags = payload["flags"]
    expected = [spec.command for spec in FLAG_SPECS]
    assert [flag["command"] for flag in flags] == expected
    assert len(flags) == len(set(expected)), "a command appears twice in the record"

    unknown = [flag for flag in flags if flag["provenance"] == "unknown"]
    assert unknown, "no flag is recorded unknown, which no bare call can be true of"
    for flag in unknown:
        assert flag["value"] is None, (
            "an unknown flag carries a value, so the record is guessing; the snapshot "
            "records unknown precisely because an opened simulation file can carry "
            "settings this library has no evidence for"
        )
    assert {"command", "family", "provenance", "value", "emitted", "evidence"} <= set(flags[0])

    explicit = [flag for flag in flags if flag["provenance"] == "explicit"]
    assert [flag["command"] for flag in explicit] == ["SOLVER_SET_VELOCITY"]


def test_a_snapshot_missing_a_flag_is_completed_as_unknown():
    """Completeness is the writer's job, not the caller's.

    A snapshot built by some other route may carry fewer than the full
    set. The record still names every flag: silence about a flag is the
    one thing this file may not do.
    """
    full = make_provenance().setup
    thinned = full.model_copy(
        update={"flags": {k: v for k, v in full.flags.items() if k != "SOLVER_SET_AOA"}}
    )
    records = settings_records(thinned)
    assert [record.command for record in records] == [spec.command for spec in FLAG_SPECS]
    filled = next(record for record in records if record.command == "SOLVER_SET_AOA")
    assert filled.provenance == "unknown"
    assert filled.value is None


@pytest.mark.parametrize(("writer", "suffix"), WRITERS)
def test_the_record_honours_the_no_silent_overwrite_rule(writer, suffix, tmp_path):
    """The sidecar is a written file and takes the same refusal.

    A guard on one half of a pair is not a guard: a second call that
    refused the data file but replaced its record would leave the numbers
    of the first run described by the settings of the second.
    """
    from pyflightstream.exceptions import OutputExistsError

    destination = tmp_path / f"probes{suffix}"
    _written, record = writer(destination, POINTS, FIELDS, provenance=make_provenance())
    first = record.read_text(encoding="utf-8")

    destination.unlink()  # only the record survives, so only it can refuse
    with pytest.raises(OutputExistsError, match="already exists"):
        writer(destination, POINTS, FIELDS, provenance=make_provenance("other/run"))

    assert record.read_text(encoding="utf-8") == first, "a refused write still replaced the record"
    assert not destination.exists(), (
        "the data file was written although the pair was refused, so the refusal left "
        "half a pair behind"
    )
