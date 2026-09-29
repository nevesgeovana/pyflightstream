<!-- Copyright (c) 2026 Geovana Neves. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). See LICENSE-AND-AUTHORSHIP.md. -->

# License and authorship of the guides

**Author and copyright holder: Geovana Neves.**
Copyright (c) 2026 Geovana Neves. The guides in this folder were written by
her, as part of the pyflightstream project, and are licensed as stated below.
Keep this file with the folder.

## What is in this folder, and under which license

| Material | License |
|---|---|
| `pyfts-guide-00-fts-overview.pdf` to `pyfts-guide-07-python-environment-offline.pdf`: the eight guides, 0 to 7 (slide decks) | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| `latex-sources/`: the LaTeX sources of those guides, their figures and their build recipe | CC BY 4.0 |
| `README.md` and `LICENSE-AND-AUTHORSHIP.md` (this file) | CC BY 4.0 |
| `pyflightstream_user_guide.tex`: the guide to the Python library | MIT License, as the rest of the repository (`LICENSE` at its root) |

Every file of the eight guides repeats, in its first lines, who wrote it and
under which license it is published; each PDF carries the notice on its title
page, on the foot of every page and in its metadata.

To rebuild the eight PDFs from their sources, run `latex-sources/build-all.ps1`
(Windows) or `latex-sources/build-all.sh` (Linux); each copies the finished
PDFs into this folder, overwriting them. The header of each script says what
the build needs.

## What the license allows and requires

**CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/legalcode). You may
copy, share and adapt the guides, for any purpose, provided that you:

- credit the author, **Geovana Neves**, and name the work ("pyflightstream
  guides");
- link to the license, and say whether you changed the material;
- do not suggest that the author endorses you or your use.

## How to cite

Geovana Neves, *pyflightstream*, Zenodo, https://doi.org/10.5281/zenodo.21482924
(the concept DOI, which resolves to the newest release; the DOI of each version
is in the repository's `CITATION.cff`).

## What this license does not cover

- **FlightStream** is a separate, commercially licensed product of its own
  vendor and is not part of this material. Its name is used only to say what
  this software drives. Nothing from its manuals is reproduced here; facts
  taken from them are paraphrased with a page reference.
- Third-party works the guides cite (textbooks, papers, public geometry
  records) keep their own licenses; the guides cite them and reproduce none of
  them.
- The license grants no right to use the author's name, except to credit her
  as it requires.
- No warranty: the guides are provided as they are.
