param([switch]$CheckOnly, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $PSScriptRoot
$appFile = Join-Path $PSScriptRoot 'app.py'
if (-not (Test-Path -LiteralPath $appFile)) { throw 'app.py is missing. Extract the entire ZIP before running.' }
$candidates = @(
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
)
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) { $candidates += $pythonCommand.Source }
$selectedPython = $null
$prefixArgs = @()
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate)) { continue }
    try {
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
    } catch { }
}
if (-not $selectedPython) {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        try {
            & $pyCommand.Source -3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $selectedPython = $pyCommand.Source; $prefixArgs = @('-3') }
        } catch { }
    }
}
if (-not $selectedPython) { throw 'No working Python 3.10+ was found. Install Python from python.org and retry.' }
Write-Host ('Python: ' + $selectedPython)
if ($CheckOnly) {
    & $selectedPython @prefixArgs -c 'import sqlite3,ssl,sys; print(sys.version.split()[0])'
    exit $LASTEXITCODE
}
$launchArgs = @()
if ($NoBrowser) { $launchArgs += '--no-browser' }
& $selectedPython @prefixArgs $appFile @launchArgs
exit $LASTEXITCODE
