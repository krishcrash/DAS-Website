# Local preview: rebuild the data + charts from master-data/, then serve the site.
#
#   .\dev.ps1            build data, build charts, start the dev server
#   .\dev.ps1 -Install   also (re)install the Python dependencies first
#
# Then open http://localhost:1313 — pages reload as you edit templates, CSS,
# JS or content. After editing a CSV in master-data/, stop (Ctrl+C) and re-run.

param([switch]$Install)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Python: prefer the Windows launcher, fall back to python on PATH.
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }

# Hugo: on PATH, or where winget puts it if this terminal predates the install.
$hugo = (Get-Command hugo -ErrorAction SilentlyContinue).Source
if (-not $hugo) {
    $hugo = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Hugo.Hugo.Extended*\hugo.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $hugo) { throw "Hugo not found. Install it with: winget install Hugo.Hugo.Extended" }

if ($Install) { & $py -m pip install -r scripts/requirements.txt }

& $py scripts/build_data.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $py scripts/build_charts.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }

& $hugo server --port 1313 --navigateToChanged
