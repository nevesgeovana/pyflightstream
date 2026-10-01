## Added

- The cheatsheet is one document of ten pages, `guide/pyfts-guide-04-cheatsheet.pdf`: page 1 is every subcommand and option of `pyfs-matrix`, page 2 every other console tool (`pyfs-workspace`, `pyfs-qa`, `pyfs-fsi`, `pyfs-manual` and the `python -m` entries), and pages 3 to 10 the eight stages of the campaign workflow, one page each with its commands and options, the files it reads and writes, its common errors and a figure. A tier-1 test walks the parser of every console tool and refuses the source when a command or an option is missing, or when it names one no parser has (FR-328).

## Changed

- The guides are numbered from 01 and the cheatsheet is guide 04: 01 overview, 02 workspaces, 03 GUI to pyfs, 04 cheatsheet, 05 references, 06 solver setup, 07 post-processing definitions, 08 FSI, 09 Python environment for offline machines. The PDF files, the source folders under `guide/latex-sources/`, the build scripts, the admitted-PDF rule (house-style test, ignore file, pre-commit hook and CI guard), the guide pages and the cross-references between the decks follow the new numbers, and no tracked file names the old overview (FR-329).
- The two cheatsheet PDFs of the 0.34.0 development branch, the `pyfs-matrix` sheet and the sheet by stage, are one PDF built from one source folder, `guide/latex-sources/04-cheatsheet/` (FR-328).

## Migration

- The guide files are renamed and none of the old names resolves: the overview was `pyfts-guide-00-fts-overview.pdf` and is `pyfts-guide-01-fts-overview.pdf`; workspaces was 01, now 02; GUI to pyfs was 02, now 03; the cheatsheet is new as a numbered guide, 04 (it replaces `pyfts-cheatsheet-pyfs-matrix.pdf`); references was 03, now 05; solver setup was 04, now 06; post-processing definitions was 05, now 07; FSI was 06, now 08; the Python environment for offline machines was 07, now 09. A link, a bookmark or a script that names a guide by its file name is updated by this map (FR-329).
