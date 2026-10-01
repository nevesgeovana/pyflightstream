#!/bin/sh
# Copyright (c) 2026 Geovana Neves. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). See LICENSE-AND-AUTHORSHIP.md.
#
# build-all.sh
#
# Builds the eight guide decks, 00 to 07, from this folder and copies each
# final PDF, named pyfts-guide-<folder>.pdf, one level up (guide/ in the
# repository, docs/ in a kit), overwriting. Auxiliary files stay in build/
# here, which is never versioned. The two cheatsheets of cheatsheet/ are
# built after the decks and copied the same way: the pyfs-matrix cheatsheet,
# pyfts-cheatsheet-pyfs-matrix.pdf (two pages: pyfs-matrix, then every other
# command-line tool), and the cheatsheet by stage, pyfts-cheatsheet-by-stage.pdf
# (eight pages, one per stage of the workflow).
#
#   sh build-all.sh            all eight decks and both cheatsheets
#   sh build-all.sh 00         only guide 00, the overview (00-fts-overview)
#   sh build-all.sh 03         only the deck whose folder starts with 03
#   sh build-all.sh cheatsheet only the two cheatsheets
#
# Needs pdflatex (TeX Live or MiKTeX) with the beamer, tcolorbox, listings,
# tikz, adjustbox, microtype and underscore packages. The compiler runs with
# shared/ as the working directory, so every ../shared/ in the preamble
# resolves inside this folder; each deck's own folder is handed to it as an
# include directory. Nothing outside this folder is read.

here=$(cd "$(dirname "$0")" && pwd)
docs=$(dirname "$here")
only=$1
status=0

# No em dashes and no en dashes in any source.
if grep -rl "$(printf '\342\200\224')\|$(printf '\342\200\223')" --include='*.tex' "$here" >/dev/null 2>&1; then
    echo "em or en dash found in a source:"; grep -rl "$(printf '\342\200\224')\|$(printf '\342\200\223')" --include='*.tex' "$here"
    exit 1
fi

for deck in "$here"/0*/; do
    name=$(basename "$deck")
    case "$name" in "$only"*) ;; *) continue ;; esac
    job="pyfts-guide-$name"
    out="$here/build/$name"
    mkdir -p "$out"
    ok=1
    for pass in 1 2 3; do
        if [ -x "$(command -v miktex-pdftex 2>/dev/null)" ] || pdflatex --version 2>/dev/null | grep -q MiKTeX; then
            inc="-include-directory=$deck -include-directory=$here/shared"
            (cd "$here/shared" && pdflatex -interaction=nonstopmode -halt-on-error $inc \
                -output-directory="$out" -jobname="$job" "$deck/main.tex" >/dev/null 2>&1) || ok=0
        else
            (cd "$here/shared" && TEXINPUTS="$deck//:$here/shared//:" pdflatex -interaction=nonstopmode \
                -halt-on-error -output-directory="$out" -jobname="$job" "$deck/main.tex" >/dev/null 2>&1) || ok=0
        fi
        [ $ok = 1 ] || break
    done
    if [ $ok = 0 ]; then
        echo "FAILED $job; see $out/$job.log"; status=1; continue
    fi
    over=$(grep -c '^Overfull' "$out/$job.log")
    cp -f "$out/$job.pdf" "$docs/$job.pdf"
    echo "built $docs/$job.pdf (Overfull boxes: $over)"
done

# The two cheatsheets, built with the decks (or alone with the argument
# cheatsheet) and copied beside them: pyfts-cheatsheet-pyfs-matrix.pdf and,
# since 0.34.0, pyfts-cheatsheet-by-stage.pdf. Each runs from its own folder, so
# its ../shared/info.tex resolves here; two passes, and the overfull count must
# be zero for each page to keep its sheet (a tier-1 test counts the pages).
case "cheatsheet" in "$only"*)
    out="$here/build/cheatsheet"
    mkdir -p "$out"
    for job in pyfts-cheatsheet-pyfs-matrix pyfts-cheatsheet-by-stage; do
        ok=1
        for pass in 1 2; do
            (cd "$here/cheatsheet" && pdflatex -interaction=nonstopmode -halt-on-error \
                -output-directory="$out" "$job.tex" >/dev/null 2>&1) || { ok=0; break; }
        done
        if [ $ok = 0 ]; then
            echo "FAILED $job; see $out/$job.log"; status=1
        else
            over=$(grep -c '^Overfull' "$out/$job.log")
            cp -f "$out/$job.pdf" "$docs/$job.pdf"
            echo "built $docs/$job.pdf (Overfull boxes: $over)"
        fi
    done
    ;;
esac
exit $status
