# Builds the beamer user guide pdf locally. The pdf never enters Git
# (repository guard rejects tracked pdf files); only the .tex source
# is committed.
param(
    [string]$TexFile = "guide\pyflightstream_user_guide.tex"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $TexFile)) {
    Write-Error "LaTeX source not found: $TexFile"
    exit 1
}

$texPath = Resolve-Path $TexFile
$workDir = Split-Path $texPath
$fileName = Split-Path $texPath -Leaf
$baseName = [System.IO.Path]::GetFileNameWithoutExtension($fileName)

Push-Location $workDir
try {
    $latexmk = Get-Command "latexmk" -ErrorAction SilentlyContinue
    if ($null -ne $latexmk) {
        Write-Host "Building with latexmk..." -ForegroundColor Cyan
        latexmk -pdf -interaction=nonstopmode -halt-on-error $fileName
        if ($LASTEXITCODE -ne 0) {
            throw "latexmk failed with exit code $LASTEXITCODE"
        }
    } else {
        $pdflatex = Get-Command "pdflatex" -ErrorAction SilentlyContinue
        if ($null -eq $pdflatex) {
            throw "Neither latexmk nor pdflatex is available. Install MiKTeX or TeX Live."
        }
        Write-Host "Building with pdflatex (two passes)..." -ForegroundColor Cyan
        pdflatex -interaction=nonstopmode -halt-on-error $fileName
        if ($LASTEXITCODE -ne 0) { throw "pdflatex pass 1 failed" }
        pdflatex -interaction=nonstopmode -halt-on-error $fileName
        if ($LASTEXITCODE -ne 0) { throw "pdflatex pass 2 failed" }
    }
    Write-Host "Built $baseName.pdf" -ForegroundColor Green
} finally {
    Pop-Location
}
