# Acoustic signals from an unsteady run

A matrix row of the `unsteady` or `unsteady_rotor` run type can
switch on the solver's acoustic toolbox, declare observers, and have the run
compute and export the acoustic signal at each of them. Five keys of the
`VAR_NAMES_VALUES` cell carry it; a steady row does not read them and is
refused if it states one. The signals are read back by the post stage, whose
products are defined in [post-processing definitions](post-processing-definitions.md).

## The keys

| Key | Value | What it does |
|---|---|---|
| `ACOUSTIC_SOURCES` | `ENABLE` or `DISABLE` | records the acoustic sources during the march; set before the solver initialises. `DISABLE` is the control: its signals are zero |
| `ACOUSTIC_OBSERVERS` | `NAME X Y Z, NAME X Y Z` | named observer points, metres, in the reference coordinate system |
| `ACOUSTIC_OBSERVERS_FILE` | a stem | the file `inputs/acoustics/<stem>.csv`, imported by the solver |
| `ACOUSTIC_OBSERVER_TIME` | `T0 T1 N` | the observers' time window in seconds and its number of samples |
| `ACOUSTIC_SECTION` | a record in braces | one annular grid of observers in a plane (an arc or a disc) |

A row that declares any observer (points, a file or a section) states both
`ACOUSTIC_SOURCES` and `ACOUSTIC_OBSERVER_TIME`; either one missing is refused
when the row is planned, since a signal computed with no source recorded is
zero, and the observers' window is their own and not the march's (a signal
arrives after a propagation delay). `ACOUSTIC_SOURCES` alone records the
sources and computes nothing.

A row of an `unsteady_rotor` campaign, far-field layers set in its setup as
always:

```text
DELTA_THETA:5 / REVOLUTIONS:3 / LAST_REVS_AVG:1 / ACOUSTIC_SOURCES:ENABLE / ACOUSTIC_OBSERVERS:MIC1 0.0 10.0 0.0, MIC2 0.0 -10.0 0.0 / ACOUSTIC_OBSERVERS_FILE:ring / ACOUSTIC_OBSERVER_TIME:0.05 0.2 16 / ACOUSTIC_SECTION:{PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 / AZIMUTH_OBSERVERS:4 / INNER_RADIUS:5.0 / OUTER_RADIUS:10.0}
```

## Observers

**Points.** Each observer is a name (one word of letters, digits, `_`, `.` or
`-`) and its position in metres in the reference coordinate system; the
package converts the metres to the simulation's length unit. Two observers of
one name are refused, because the export names each observer's block by its
name.

**A file.** `ACOUSTIC_OBSERVERS_FILE: ring` names `inputs/acoustics/ring.csv`
in the solver's own form: a first line with the number of observers, then
that many lines `x,y,z`:

```text
2
0.0,-10.0,0.0
5.0,0.0,10.0
```

The file is checked when the row is planned (a missing file, a first line
that is not a count, a line that is not three numbers, or a count that is not
the number of lines is refused naming the file and the line). The run writes
the point's own copy, `ring.acoustic_observers.csv`, in the folder the point
runs in, hashes it into the record, and the solver imports the copy. The
solver reads the coordinates in the simulation's length unit, which the
package cannot convert in a file it hands over, so the key is refused on a
simulation not in metres. The solver names an imported observer by its place
in its own list: `Observer 2`, `Observer 3`.

**A section.** `ACOUSTIC_SECTION` is one record in braces, its pairs separated
by `/`: `PLANE` (`XY`, `XZ` or `YZ`), `OFFSET`, `RADIAL_OBSERVERS`,
`AZIMUTH_OBSERVERS`, `INNER_RADIUS` and `OUTER_RADIUS`, lengths in metres, and
`FRAME` when the grid is placed in a frame the run creates (`MRP`, a rotor's
`<ALIAS>_SMRP`); without `FRAME` it is placed in the reference coordinate
system. A frame the run does not create is refused naming the frames it does.

**The time window.** `ACOUSTIC_OBSERVER_TIME: 0.05 0.2 16` samples each
observer 16 times starting at 0.05 s, spaced by (0.2 - 0.05) / 16 = 0.009375 s; the
final time itself is not a sample (measured on 26.124).

## What the run writes

At the end of the march, after the solve and before the point's other
exports:

- `COMPUTE_ACOUSTIC_SIGNALS`, where the row declares any observer;
- `EXPORT_ACOUSTIC_SIGNALS` to `<point>_acoustic_signals.txt`, where it
  declares points or a file: ONE file holding every such observer, one block
  each (`Observer: <name>`, `Position: x,y,z`, `Columns: Observer time (sec),
  PL (Pa), PT (Pa), PO (Pa)`, then one row per sample). The point declares the
  file among its outputs, so the collect files it in the point's datapoint
  folder and the record lists it, with its sha256 on a local run;
- `CREATE_ACOUSTIC_SECTION` into `<point>_acoustic_section/`, where it declares
  a section: one VTK file per sample of the time window, `VTK_output-001.vtk`
  onwards, each holding every observer of the grid. The run creates the
  folder before the solver starts, by writing the note
  `pyfs-acoustic-section.txt` into it; after the run the collect lists every
  other file of the folder in the record, each with its sha256 on a local run
  (a submitted point that `pyfs-matrix collect` completes hashes none of its
  outputs).

None of these files is ever read as a surface export or a loads table.

## What is refused

- An acoustic key on a steady or `qsteady_rotor` row: the key guard names the
  run types that read it.
- A declaration not in its form, each naming the key and the form.
- A continuation (`RESTART`) of a row that states acoustic keys: whether the
  sources recorded before the stop survive the saved simulation is not
  measured, so the signals could cover part of the march with nothing saying
  which.
- A point whose `<point>_acoustic_section/` already holds a file before the
  solver runs: the collect lists the folder after the run and could not tell
  that file from one the solver wrote. Redo the point with `--force-rerun`,
  which archives what is there, or remove the leftover.
- In the Python API, the acoustic setup emitted after `INITIALIZE_SOLVER`, and
  the computation or the exports emitted on a steady run or before
  `START_SOLVER`.

## What is measured, and what is not

The whole chain ran on FlightStream 26.124 (build 8172026) in a licensed
probe: sources, a named observer, an imported file, the time window, the
export and the section, with the sources switched on against a control with
them off (`reports/compat/CMP-26124_2026-09-30_acoustics.yaml`, a
transcription of the release harness's probes that promotes nothing). The seven
commands stay `documented` on 26.124: `verified` goes only through a
`qa.specs` entry and a `pyfs-qa probe` run. Six showed their effect in the
exported signals; `COMPUTE_ACOUSTIC_SIGNALS` was accepted and its own effect
was not isolated. Not measured: whether the solver creates
a section folder that does not exist (the run creates it), and the length
unit of the exported coordinates on a simulation not in metres.
