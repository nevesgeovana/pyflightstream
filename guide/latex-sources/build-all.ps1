# Copyright (c) 2026 Geovana Neves. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). See LICENSE-AND-AUTHORSHIP.md.
#
# build-all.ps1
#
# Builds the nine guides, 01 to 09, from this folder and copies each final PDF,
# named pyfts-guide-<folder>.pdf, one level up (guide/ in the repository, docs/
# in a kit), overwriting. Auxiliary files stay in build/ here, which is never
# versioned. Guide 04 is the cheatsheet, one document of ten pages (04-cheatsheet),
# built and copied like the decks.
#
#   .\build-all.ps1            all nine guides
#   .\build-all.ps1 -Only 01   only guide 01, the overview (01-fts-overview)
#   .\build-all.ps1 -Only 04   only guide 04, the cheatsheet (04-cheatsheet)
#
# Needs pdflatex on the PATH (MiKTeX installs it; TeX Live works too) with the
# beamer, tcolorbox, listings, tikz, adjustbox, microtype and underscore
# packages; MiKTeX fetches a missing package on first use. The compiler runs
# with shared/ as the working directory, so every ../shared/ in the preamble
# resolves inside this folder; each deck's own folder and shared/ are handed
# to it as include directories. Nothing outside this folder is read.
# Three passes per guide, for the table of contents and the frame counts.

param([string]$Only = "")
$ErrorActionPreference = "Stop"

$here   = $PSScriptRoot
$docs   = Split-Path $here -Parent
$shared = Join-Path $here "shared"

# No em dashes and no en dashes in any source.
$dash = Get-ChildItem $here -Recurse -Include *.tex |
    Where-Object { $_.FullName -notmatch '\\build\\' } |
    Select-String -Pattern "[$([char]0x2014)$([char]0x2013)]"
if ($dash) { $dash | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }; throw "em or en dash found" }

$failed = 0
foreach ($deck in Get-ChildItem $here -Directory | Where-Object { $_.Name -match '^0\d-' } | Sort-Object Name) {
    if ($Only -and -not $deck.Name.StartsWith($Only)) { continue }
    $job = "pyfts-guide-$($deck.Name)"
    $out = Join-Path $here "build\$($deck.Name)"
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $flags = @("-include-directory=$($deck.FullName)", "-include-directory=$shared")
    $ok = $true
    Push-Location $shared
    try {
        foreach ($pass in 1..3) {
            if (Get-Command miktex-pdftex -ErrorAction SilentlyContinue) {
                & pdflatex -interaction=nonstopmode -halt-on-error @flags `
                    "-output-directory=$out" "-jobname=$job" (Join-Path $deck.FullName "main.tex") | Out-Null
            } else {
                $env:TEXINPUTS = "$($deck.FullName)//;$shared//;"
                & pdflatex -interaction=nonstopmode -halt-on-error `
                    "-output-directory=$out" "-jobname=$job" (Join-Path $deck.FullName "main.tex") | Out-Null
            }
            if ($LASTEXITCODE -ne 0) { $ok = $false; break }
        }
    } finally { Pop-Location }
    if (-not $ok) { Write-Host "FAILED $job; see $out\$job.log" -ForegroundColor Red; $failed++; continue }
    $log  = Get-Content (Join-Path $out "$job.log") -Raw
    $over = ([regex]::Matches($log, '(?m)^Overfull')).Count
    Copy-Item (Join-Path $out "$job.pdf") (Join-Path $docs "$job.pdf") -Force
    Write-Host "built $docs\$job.pdf (Overfull boxes: $over)" -ForegroundColor Green
}

if ($failed) { exit 1 }
