# RPT-032: the executables in hand, by digest, before the licence swap (2026-08-19)

The licence in use is temporary and a replacement executable is expected
on the vendor's unit-based licensing. When it arrives, one cheap question
decides whether every licensed seat already spent still counts: is the
new binary the one this repository's evidence was gathered on, and if not,
does it print the build number the registry records for the version it
claims?

That question has two sides and only one of them existed. The NEW side is
free to obtain, since an identity-only probe prints the build number. The
OLD side did not exist at all: nothing in this repository recorded which
bytes produced any of the committed evidence, so on the day of the swap
there would have been nothing to compare against. This report is that old
side, measured now, with no solver started and no seat spent.

## What was measured, and how

Every FlightStream executable held locally under `_private/exe/` was
hashed with `pyflightstream._digest.file_sha256`, which reads the raw
bytes of the file in blocks and decodes nothing. The binaries are
licensed vendor software: they live outside Git and only these digests
are committed. No process was started, so this report costs no licensed
seat and could be reproduced on an expired licence.

Two files carry the same bytes in every install directory: the name the
vendor installer writes, and a version-named copy the author keeps so a
campaign can name the build it means. Both were hashed and, in all nine
directories, the pair agrees, so the table records one digest per build
and names both files.

## The baseline

| Version | Build | Names | sha256 | Bytes |
|---|---|---|---|---|
| 25.000 | 12162024 | FlightStream.exe, FlightStream_25000.exe | withheld; build 12162024 | 17003336 |
| 25.100 | 5062025 | FlightStream_25_1.exe, FlightStream_25100.exe | withheld; build 5062025 | 17088336 |
| 26.000 | 10202025 | FlightStream.exe, FlightStream_26000.exe | withheld; build 10202025 | 17006984 |
| 26.100 | 2122026 | FlightStream_26_1.exe, FlightStream_26100.exe | withheld; build 2122026 | 18011528 |
| 26.101 | 5012026 | FlightStream.exe, FlightStream_26101.exe | withheld; build 5012026 | 18939720 |
| 26.120 | 7012026 | Flightstream_2612.exe, FlightStream_26120.exe | withheld; build 7012026 | 18992520 |
| 26.121 | 7262026 | Flightstream_2612.exe, FlightStream_26121.exe | withheld; build 7262026 | 19134856 |
| 26.122 | 8092026 | Flightstream_2612.exe, FlightStream_26122.exe | withheld; build 8092026 | 19169160 |
| 26.123 | 8112026 | Flightstream_2612.exe, FlightStream_26123.exe | withheld; build 8112026 | 19194760 |
| 26.124 | 8172026 | Flightstream_26124.exe | withheld; build 8172026 | 19197320 |

The 26.124 row was ADDED ON 2026-09-14, when that build was registered, from
the digest its identity run recorded (`reports/compat/CMP-26124_2026-09-14.yaml`);
its size is not in that file and is read in
`reports/RPT-050_the-26124-package-against-26123_2026-09-15.md`, which measures
the whole package. Every other row is this report's own measurement of
2026-08-19.

EVERY DIGEST IS WITHHELD from the public tree since 2026-09-30 (NFR-31):
the public tree carries no identity of a user's machine, and each row states
its build, which identifies that executable. The ten digests were measured
and still exist on the measuring machine; only their committed copies are
gone. `read_executable_baseline` reads a cell that starts with `withheld` as a
row whose digest is not public, so `classify_executable` compares a binary by
its build (the identity-only probe) instead of by its bytes; a byte
comparison reads the same table from a local, uncommitted copy that keeps the
digests (for example under `_private/exe/`). The findings below are
unchanged: they were measured on the digests, and the table keeps the names,
builds and sizes they rest on.

The Build column is the registry's number for that canonical version, not
a second measurement: it is reproduced here so the two sides of a future
comparison sit on one page. The table is read by
`pyflightstream.qa.compat.read_executable_baseline`, which resolves every
column BY LABEL, so the column order above carries no meaning and may be
changed without breaking anything.

## The finding this makes concrete

Nine builds, nine distinct digests, and six file names between them. Two
of those names each cover several builds:

* `Flightstream_2612.exe` is the installer's name for FOUR registered
  builds, 26.120, 26.121, 26.122 and 26.123;
* `FlightStream.exe` is the installer's name for THREE, 25.000, 26.000
  and 26.101.

The committed compatibility reports record the executable by that name.
So until now a report could not answer which binary produced it, and the
question is about to stop being academic: a replacement binary can arrive
under either of those names.

## The rule this report exists to serve

Before ANY campaign, probe or physics run against a replacement
executable:

1. hash it and compare against this table, which
   `pyflightstream.qa.compat.classify_executable` does and which starts
   no process;
2. if the digest is one of the nine above, it is the binary the evidence
   was gathered on and every row of that version's evidence transfers
   untouched, with both digests named. No seat is spent;
3. if the digest is not here, nothing is known about the binary yet. The
   ONLY licensed work authorised at that point is the identity-only
   probe, `pyfs-qa probe --fs-version <v> --fs-exe <path>
   --identity-only`, which judges no command and reads the solver's own
   banner;
4. compare the build number it printed against the one the registry
   records. Equal, and the evidence transfers, with both digests and both
   numbers recorded. Different, and it is a DIFFERENT build: no further
   licensed work starts on that identifier and the disagreement is
   reported with both numbers.

## Limits, stated rather than left to be discovered

A digest identifies a FILE, not a licence. Two runs of the same binary
under two licence tiers produce the same digest and can behave
differently, and this report says nothing about that; what a licence tier
may refuse is the separate question recorded against the version rows in
`src/pyflightstream/commands/_meta.yaml` and in
`reports/compat/README.md`.

The nine rows are the executables in hand on the date in the title. The
replacement is not among them, and nothing here is a measurement of a
build nobody has: no row describes a binary that has not been hashed.

The Build column reproduces the registry, so it is the one column here
that is not an independent measurement. Where a build number is in doubt,
the committed identity report for that version is the authority, not this
table.
